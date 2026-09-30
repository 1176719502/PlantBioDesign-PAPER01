"""Testable Windows launcher lifecycle for the local single-gene MVP."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

STATE_FILE_NAME = "mvp_runtime.json"
MVP_TITLE = "项目首页"
ERROR_MARKERS = ("ImportError", "Traceback", "StreamlitAPIException", "ModuleNotFoundError", "Exception")
CORE_MODULES = ("services.canonical_construct_runtime", "services.mvp_cds_input", "services.mvp_single_gene_persistence", "services.plant_project_draft_repository")


class LauncherError(RuntimeError):
    def __init__(self, message: str, rejected: Sequence["CandidateProbe"] = ()) -> None:
        super().__init__(message)
        self.rejected = list(rejected)


@dataclass(frozen=True)
class PythonCommand:
    command: str
    arguments: tuple[str, ...] = ()

    def invoke(self, *args: str) -> list[str]:
        return [self.command, *self.arguments, *args]

    @property
    def label(self) -> str:
        return " ".join((self.command, *self.arguments))


@dataclass(frozen=True)
class CandidateProbe:
    candidate: PythonCommand
    accepted: bool
    reason: str
    executable: str = ""
    version: str = ""


@dataclass(frozen=True)
class SelectedPython:
    command: PythonCommand
    executable: str
    version: str


@dataclass(frozen=True)
class RuntimeState:
    pid: int
    python_executable: str
    python_version: str
    python_command: str
    python_arguments: list[str]
    process_start_time_utc: str
    repository_root: str
    mvp_entry_path: str
    port: int
    url: str


def repository_root(script_path: str | os.PathLike[str] | None = None) -> Path:
    return Path(script_path or __file__).resolve().parents[2]


def runtime_dir(root: Path) -> Path:
    return root / ".runtime"


def state_path(root: Path) -> Path:
    return runtime_dir(root) / STATE_FILE_NAME


def python_candidates(root: Path) -> list[PythonCommand]:
    return [PythonCommand(str(root / ".venv" / "Scripts" / "python.exe")), PythonCommand("py", ("-3.12",)), PythonCommand("py", ("-3.11",)), PythonCommand("python"), PythonCommand("py")]


def _run(
    command: Sequence[str],
    runner: Callable[..., Any],
    *,
    cwd: Path | None = None,
) -> Any | None:
    try:
        return runner(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _success(
    command: Sequence[str],
    runner: Callable[..., Any],
    *,
    cwd: Path | None = None,
) -> bool:
    result = _run(command, runner, cwd=cwd)
    return result is not None and result.returncode == 0


def probe_candidate(candidate: PythonCommand, root: Path, *, runner: Callable[..., Any] = subprocess.run) -> CandidateProbe:
    if not (root / "mvp_app.py").is_file():
        return CandidateProbe(candidate, False, "找不到仓库 mvp_app.py")
    metadata = _run(
        candidate.invoke("-c", "import json,sys; print(json.dumps([sys.executable,*sys.version_info[:3]]))"),
        runner,
        cwd=root,
    )
    if metadata is None or metadata.returncode != 0:
        return CandidateProbe(candidate, False, "Python 不可用")
    try:
        executable, major, minor, micro = json.loads(str(metadata.stdout).strip().splitlines()[-1])
        version = f"{major}.{minor}.{micro}"
    except (ValueError, IndexError, json.JSONDecodeError):
        return CandidateProbe(candidate, False, "无法读取 Python 版本")
    if (major, minor) < (3, 11):
        return CandidateProbe(candidate, False, "Python 版本过低", str(executable), version)
    if not _success(candidate.invoke("-c", "from datetime import UTC"), runner, cwd=root):
        return CandidateProbe(candidate, False, "不支持 datetime.UTC", str(executable), version)
    if not _success(candidate.invoke("-c", "import streamlit"), runner, cwd=root):
        return CandidateProbe(candidate, False, "未安装 Streamlit", str(executable), version)
    imports = "; ".join(f"import {module}" for module in CORE_MODULES)
    if not _success(candidate.invoke("-c", imports), runner, cwd=root):
        return CandidateProbe(candidate, False, "缺少项目依赖", str(executable), version)
    return CandidateProbe(candidate, True, "可用", str(executable), version)


def select_python(root: Path, *, runner: Callable[..., Any] = subprocess.run) -> tuple[SelectedPython, list[CandidateProbe]]:
    rejected: list[CandidateProbe] = []
    for candidate in python_candidates(root):
        result = probe_candidate(candidate, root, runner=runner)
        if result.accepted:
            return SelectedPython(candidate, result.executable, result.version), rejected
        rejected.append(result)
    raise LauncherError("未找到可运行 BioDesign MVP 的 Python 环境。需要 Python 3.11 或更高版本，并已安装 Streamlit。", rejected)


def read_state(root: Path) -> RuntimeState | None:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8-sig"))
        return RuntimeState(**{name: data[name] for name in RuntimeState.__dataclass_fields__})
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def write_state(root: Path, state: RuntimeState) -> None:
    runtime_dir(root).mkdir(parents=True, exist_ok=True)
    temp = state_path(root).with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(state_path(root))


def clear_state(root: Path) -> None:
    state_path(root).unlink(missing_ok=True)


def process_info(pid: int, runner: Callable[..., Any] = subprocess.run) -> dict[str, str] | None:
    script = "$p=Get-Process -Id " + str(pid) + " -ErrorAction SilentlyContinue;if($null -ne $p){[PSCustomObject]@{ProcessId=[string]$p.Id;ExecutablePath=[string]$p.Path;StartTime=[string]$p.StartTime.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress}"
    result = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], runner)
    if result is None or result.returncode != 0 or not str(result.stdout).strip():
        return None
    try:
        return {key: str(json.loads(result.stdout).get(key) or "") for key in ("ProcessId", "ExecutablePath", "StartTime")}
    except json.JSONDecodeError:
        return None


def owned(state: RuntimeState, actual: dict[str, str] | None) -> bool:
    if not actual or str(actual.get("ProcessId")) != str(state.pid):
        return False
    if os.path.normcase(str(actual.get("ExecutablePath"))) != os.path.normcase(state.python_executable):
        return False
    try:
        observed = datetime.fromisoformat(str(actual["StartTime"]).replace("Z", "+00:00"))
        recorded = datetime.fromisoformat(state.process_start_time_utc.replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    return abs((observed - recorded).total_seconds()) < 2 and Path(state.repository_root).resolve() == Path(state.mvp_entry_path).resolve().parent and Path(state.mvp_entry_path).name == "mvp_app.py"


def http_available(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def page_is_healthy(status: int, content: str) -> bool:
    return 200 <= status < 400 and MVP_TITLE in content and not any(marker.lower() in content.lower() for marker in ERROR_MARKERS)


def _preflight(selected: SelectedPython, app: Path, root: Path) -> None:
    source = "from streamlit.testing.v1 import AppTest; at=AppTest.from_file(r'''%s'''); at.run(timeout=30); assert not at.exception; assert any(x.value == r'''%s''' for x in at.title)" % (app, MVP_TITLE)
    env = dict(os.environ, TMP=str(runtime_dir(root)), TEMP=str(runtime_dir(root)))
    try:
        result = subprocess.run([selected.executable, "-c", source], cwd=root, env=env, capture_output=True, text=True, timeout=40, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LauncherError("MVP 页面预检查失败。") from exc
    if result.returncode != 0:
        raise LauncherError("MVP 页面预检查失败。")


def _free_port() -> int:
    for port in range(8501, 8601):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    raise LauncherError("未找到可用本地端口。")


def _kill(pid: int) -> bool:
    return _success(["taskkill", "/PID", str(pid), "/T", "/F"], subprocess.run)


def start(root: Path, *, lookup: Callable[[int], dict[str, str] | None] = process_info) -> tuple[RuntimeState, bool, list[CandidateProbe]]:
    existing = read_state(root)
    if existing and owned(existing, lookup(existing.pid)) and http_available(existing.url):
        return existing, True, []
    clear_state(root)
    selected, skipped = select_python(root)
    runtime_dir(root).mkdir(parents=True, exist_ok=True)
    app = root / "mvp_app.py"
    _preflight(selected, app, root)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    log = (runtime_dir(root) / f"mvp_streamlit.{port}.log").open("w", encoding="utf-8")
    process = subprocess.Popen([selected.executable, "-m", "streamlit", "run", str(app), "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true"], cwd=root, stdout=log, stderr=subprocess.STDOUT, text=True, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    state = RuntimeState(process.pid, selected.executable, selected.version, selected.command.command, list(selected.command.arguments), datetime.now(timezone.utc).isoformat(), str(root.resolve()), str(app.resolve()), port, url)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LauncherError("Streamlit 在启动完成前退出。")
            if http_available(url):
                write_state(root, state)
                return state, False, skipped
            time.sleep(0.5)
        raise LauncherError("本地 MVP 服务启动超时。")
    except LauncherError:
        _kill(process.pid)
        clear_state(root)
        raise
    finally:
        log.close()


def stop(root: Path, *, lookup: Callable[[int], dict[str, str] | None] = process_info) -> str:
    state = read_state(root)
    if state is None or not owned(state, lookup(state.pid)):
        clear_state(root)
        return "已清理失效的 MVP 运行状态。"
    if not _kill(state.pid):
        raise LauncherError("MVP 服务未能停止；运行状态已保留以便重试。")
    clear_state(root)
    return "本地 MVP 服务已停止。"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--repo-root", default="")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve() if args.repo_root else repository_root()
    try:
        if args.action == "start":
            state, reused, skipped = start(root)
            for item in skipped:
                print(f"BioDesign MVP: 已跳过 {item.candidate.label}（{item.reason}）。")
            print(json.dumps({"ok": True, "url": state.url, "pid": state.pid, "reused": reused}, ensure_ascii=False))
        else:
            print(json.dumps({"ok": True, "message": stop(root)}, ensure_ascii=False))
        return 0
    except LauncherError as exc:
        print(json.dumps({"ok": False, "message": str(exc), "rejected": [{"candidate": x.candidate.label, "reason": x.reason} for x in exc.rejected]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
