"""Safe Windows launcher lifecycle for the formal app.py runtime."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.config import ensure_biodesign_log_dir, ensure_biodesign_runtime_dir

STATE_FILE_NAME = "formal_runtime.json"
FORMAL_ENTRY_NAME = "app.py"
DEFAULT_PORT = 8528


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
    app_entry_path: str
    port: int
    url: str


def repository_root(script_path: str | os.PathLike[str] | None = None) -> Path:
    return Path(script_path or __file__).resolve().parents[2]


def runtime_dir(_root: Path) -> Path:
    return ensure_biodesign_runtime_dir()


def log_dir(_root: Path) -> Path:
    return ensure_biodesign_log_dir()


def state_path(root: Path) -> Path:
    return runtime_dir(root) / STATE_FILE_NAME


def python_candidates(root: Path) -> list[PythonCommand]:
    return [
        PythonCommand(str(root / ".venv312" / "Scripts" / "python.exe")),
        PythonCommand(str(root / ".venv" / "Scripts" / "python.exe")),
        PythonCommand("py", ("-3.12",)),
        PythonCommand("py", ("-3.11",)),
        PythonCommand("py", ("-3.10",)),
        PythonCommand("python"),
        PythonCommand("py"),
    ]


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


def _version_supported(major: int, minor: int) -> bool:
    return (major, minor) >= (3, 10) and (major, minor) < (3, 13)


def probe_candidate(
    candidate: PythonCommand,
    root: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> CandidateProbe:
    if not (root / FORMAL_ENTRY_NAME).is_file():
        return CandidateProbe(candidate, False, f"Missing {FORMAL_ENTRY_NAME}.")
    metadata = _run(
        candidate.invoke("-c", "import json,sys; print(json.dumps([sys.executable,*sys.version_info[:3]]))"),
        runner,
        cwd=root,
    )
    if metadata is None or metadata.returncode != 0:
        return CandidateProbe(candidate, False, "Python command failed.")
    try:
        executable, major, minor, micro = json.loads(str(metadata.stdout).strip().splitlines()[-1])
        version = f"{major}.{minor}.{micro}"
    except (ValueError, IndexError, json.JSONDecodeError):
        return CandidateProbe(candidate, False, "Could not read Python version.")
    if not _version_supported(int(major), int(minor)):
        return CandidateProbe(candidate, False, "Python 3.10-3.12 is required.", str(executable), version)
    if not _success(candidate.invoke("-c", "import streamlit"), runner, cwd=root):
        return CandidateProbe(candidate, False, "Streamlit is not installed.", str(executable), version)
    return CandidateProbe(candidate, True, "Usable", str(executable), version)


def select_python(
    root: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[SelectedPython, list[CandidateProbe]]:
    rejected: list[CandidateProbe] = []
    for candidate in python_candidates(root):
        result = probe_candidate(candidate, root, runner=runner)
        if result.accepted:
            return SelectedPython(candidate, result.executable, result.version), rejected
        rejected.append(result)
    raise LauncherError(
        "No supported Python runtime is available. Install Python 3.10, 3.11, or 3.12 with Streamlit.",
        rejected,
    )


def read_state(root: Path) -> RuntimeState | None:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8-sig"))
        return RuntimeState(**{name: data[name] for name in RuntimeState.__dataclass_fields__})
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def write_state(root: Path, state: RuntimeState) -> None:
    temp = state_path(root).with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(state_path(root))


def clear_state(root: Path) -> None:
    state_path(root).unlink(missing_ok=True)


def process_info(pid: int, runner: Callable[..., Any] = subprocess.run) -> dict[str, str] | None:
    script = (
        "$p=Get-Process -Id "
        + str(pid)
        + " -ErrorAction SilentlyContinue;"
        + "if($null -ne $p){[PSCustomObject]@{ProcessId=[string]$p.Id;"
        + "ExecutablePath=[string]$p.Path;"
        + "StartTime=[string]$p.StartTime.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress}"
    )
    result = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], runner)
    if result is None or result.returncode != 0 or not str(result.stdout).strip():
        return None
    try:
        payload = json.loads(result.stdout)
        return {key: str(payload.get(key) or "") for key in ("ProcessId", "ExecutablePath", "StartTime")}
    except json.JSONDecodeError:
        return None


def _parse_process_timestamp(value: str) -> datetime:
    normalized = str(value).replace("Z", "+00:00")
    if "." not in normalized:
        return datetime.fromisoformat(normalized)
    head, tail = normalized.split(".", 1)
    fractional, sep, timezone_suffix = tail.partition("+")
    trimmed = fractional[:6].ljust(6, "0")
    return datetime.fromisoformat(f"{head}.{trimmed}{sep}{timezone_suffix}")


def owned(state: RuntimeState, actual: dict[str, str] | None) -> bool:
    if not actual or str(actual.get("ProcessId")) != str(state.pid):
        return False
    if os.path.normcase(str(actual.get("ExecutablePath"))) != os.path.normcase(state.python_executable):
        return False
    try:
        observed = _parse_process_timestamp(str(actual["StartTime"]))
        recorded = _parse_process_timestamp(state.process_start_time_utc)
    except (KeyError, ValueError):
        return False
    return (
        abs((observed - recorded).total_seconds()) < 2
        and Path(state.repository_root).resolve() == Path(state.app_entry_path).resolve().parent
        and Path(state.app_entry_path).name == FORMAL_ENTRY_NAME
    )


def _port_available(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def http_available(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def _kill(pid: int) -> bool:
    return _success(["taskkill", "/PID", str(pid), "/T", "/F"], subprocess.run)


def listening_pid(port: int, runner: Callable[..., Any] = subprocess.run) -> int | None:
    result = _run(["netstat", "-ano", "-p", "tcp"], runner)
    if result is None or result.returncode != 0:
        return None
    suffix = f":{port}"
    for line in str(result.stdout).splitlines():
        if "LISTENING" not in line or suffix not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address, state, pid_text = parts[1], parts[3], parts[4]
        if state == "LISTENING" and local_address.endswith(suffix):
            try:
                return int(pid_text)
            except ValueError:
                return None
    return None


def start(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    lookup: Callable[[int], dict[str, str] | None] = process_info,
) -> tuple[RuntimeState, bool, list[CandidateProbe]]:
    existing = read_state(root)
    if existing and owned(existing, lookup(existing.pid)):
        if http_available(existing.url):
            return existing, True, []
        raise LauncherError(
            f"Owned formal runtime state already exists for PID {existing.pid}, but {existing.url} is not healthy. "
            "Run the formal stop script before starting again."
        )
    clear_state(root)
    if not _port_available(port):
        raise LauncherError(
            f"Port {port} is already in use. The launcher will not stop or replace an unknown process."
        )

    selected, skipped = select_python(root)
    app = root / FORMAL_ENTRY_NAME
    url = f"http://127.0.0.1:{port}"
    log_handle = (log_dir(root) / f"formal_streamlit.{port}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            selected.executable,
            "-m",
            "streamlit",
            "run",
            str(app),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        cwd=root,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    state = RuntimeState(
        pid=process.pid,
        python_executable=selected.executable,
        python_version=selected.version,
        python_command=selected.command.command,
        python_arguments=list(selected.command.arguments),
        process_start_time_utc=datetime.now(timezone.utc).isoformat(),
        repository_root=str(root.resolve()),
        app_entry_path=str(app.resolve()),
        port=port,
        url=url,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LauncherError("The formal app process exited before becoming healthy.")
            if http_available(url):
                listener = listening_pid(port) or process.pid
                listener_info = lookup(listener)
                state = RuntimeState(
                    pid=listener,
                    python_executable=str(listener_info.get("ExecutablePath") or state.python_executable)
                    if listener_info
                    else state.python_executable,
                    python_version=state.python_version,
                    python_command=state.python_command,
                    python_arguments=state.python_arguments,
                    process_start_time_utc=str(listener_info.get("StartTime") or state.process_start_time_utc)
                    if listener_info
                    else state.process_start_time_utc,
                    repository_root=state.repository_root,
                    app_entry_path=state.app_entry_path,
                    port=state.port,
                    url=state.url,
                )
                write_state(root, state)
                return state, False, skipped
            time.sleep(0.5)
        raise LauncherError("Timed out while waiting for the formal app to become healthy.")
    except LauncherError:
        _kill(process.pid)
        clear_state(root)
        raise
    finally:
        log_handle.close()


def stop(
    root: Path,
    *,
    lookup: Callable[[int], dict[str, str] | None] = process_info,
) -> str:
    state = read_state(root)
    if state is None or not owned(state, lookup(state.pid)):
        clear_state(root)
        return "Cleared stale formal runtime state."
    if not _kill(state.pid):
        raise LauncherError("The formal app process could not be stopped. Runtime state was preserved.")
    clear_state(root)
    return "Stopped the owned formal app process."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else repository_root()
    try:
        if args.action == "start":
            state, reused, skipped = start(root, port=args.port)
            for item in skipped:
                print(
                    json.dumps(
                        {"skipped_candidate": item.candidate.label, "reason": item.reason},
                        ensure_ascii=False,
                    )
                )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "url": state.url,
                        "pid": state.pid,
                        "port": state.port,
                        "reused": reused,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(json.dumps({"ok": True, "message": stop(root)}, ensure_ascii=False))
        return 0
    except LauncherError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": str(exc),
                    "rejected": [{"candidate": x.candidate.label, "reason": x.reason} for x in exc.rejected],
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
