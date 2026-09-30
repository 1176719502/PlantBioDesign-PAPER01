"""Focused M4 checks for compatible interpreter selection and PID ownership."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "windows" / "biodesign_mvp_launcher.py"


@pytest.fixture(scope="module")
def launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mvp_launcher", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runner(versions: dict[str, tuple[int, int, int]], failures: dict[str, str] | None = None):
    failures = failures or {}

    def run(command, **_kwargs):
        label = " ".join(command[:2])
        version = versions.get(label, versions.get(command[0], (3, 11, 0)))
        code = command[-1]
        failed = failures.get(label, failures.get(command[0], ""))
        if "json.dumps" in code:
            return SimpleNamespace(returncode=0, stdout=json.dumps([rf"C:\\{command[0]}.exe", *version]))
        if failed == "utc" and "datetime import UTC" in code:
            return SimpleNamespace(returncode=1, stdout="")
        if failed == "streamlit" and "import streamlit" in code:
            return SimpleNamespace(returncode=1, stdout="")
        if failed == "core" and "canonical_construct_runtime" in code:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    return run


def test_incompatible_venv_is_skipped_for_system_python(launcher, tmp_path: Path) -> None:
    (tmp_path / "mvp_app.py").touch()
    runner = _runner({str(tmp_path / ".venv" / "Scripts" / "python.exe"): (3, 10, 11), "py -3.12": (3, 10, 11), "py -3.11": (3, 10, 11), "py": (3, 10, 11), "python": (3, 13, 9)})

    selected, rejected = launcher.select_python(tmp_path, runner=runner)

    assert selected.command.command == "python"
    assert selected.version == "3.13.9"
    assert rejected[0].reason == "Python 版本过低"


@pytest.mark.parametrize(("failure", "reason"), [("utc", "不支持 datetime.UTC"), ("streamlit", "未安装 Streamlit"), ("core", "缺少项目依赖")])
def test_candidate_rejection_reasons(launcher, tmp_path: Path, failure: str, reason: str) -> None:
    (tmp_path / "mvp_app.py").touch()
    candidate = launcher.PythonCommand("candidate")

    result = launcher.probe_candidate(candidate, tmp_path, runner=_runner({"candidate": (3, 11, 8)}, {"candidate": failure}))

    assert result.accepted is False
    assert result.reason == reason


def test_all_candidates_rejected_exits_without_starting(launcher, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "mvp_app.py").touch()
    monkeypatch.setattr(launcher, "python_candidates", lambda _root: [launcher.PythonCommand("old")])

    with pytest.raises(launcher.LauncherError, match="Python 3.11"):
        launcher.select_python(tmp_path, runner=_runner({"old": (3, 10, 9)}))


def test_candidate_probes_run_from_repository_root(launcher, tmp_path: Path) -> None:
    (tmp_path / "mvp_app.py").touch()
    observed_cwds: list[Path | None] = []
    runner = _runner({"candidate": (3, 13, 9)})

    def recording_runner(command, **kwargs):
        observed_cwds.append(kwargs.get("cwd"))
        return runner(command, **kwargs)

    result = launcher.probe_candidate(
        launcher.PythonCommand("candidate"),
        tmp_path,
        runner=recording_runner,
    )

    assert result.accepted is True
    assert observed_cwds
    assert set(observed_cwds) == {tmp_path}


def test_http_error_page_is_not_healthy(launcher) -> None:
    assert launcher.page_is_healthy(200, "项目首页") is True
    assert launcher.page_is_healthy(200, "ImportError Traceback 项目首页") is False
    assert launcher.page_is_healthy(500, "项目首页") is False


def test_runtime_state_records_actual_runtime(launcher, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "mvp_app.py").touch()
    selected = launcher.SelectedPython(launcher.PythonCommand("py", ("-3.11",)), r"C:\Python311\python.exe", "3.11.9")
    monkeypatch.setattr(launcher, "select_python", lambda _root: (selected, []))
    monkeypatch.setattr(launcher, "_preflight", lambda *_args: None)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8517)
    monkeypatch.setattr(launcher, "http_available", lambda _url: True)

    class Process:
        pid = 9876

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    state, reused, _skipped = launcher.start(tmp_path)

    assert reused is False
    assert launcher.read_state(tmp_path) == state
    payload = json.loads(launcher.state_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["python_executable"] == r"C:\Python311\python.exe"
    assert payload["python_version"] == "3.11.9"
    assert payload["python_command"] == "py"
    assert payload["python_arguments"] == ["-3.11"]


def test_stop_does_not_terminate_unrelated_python(launcher, tmp_path: Path, monkeypatch) -> None:
    state = launcher.RuntimeState(4321, r"C:\Python311\python.exe", "3.11.9", "py", ["-3.11"], "2026-01-01T00:00:01+00:00", str(tmp_path), str(tmp_path / "mvp_app.py"), 8501, "http://127.0.0.1:8501")
    (tmp_path / "mvp_app.py").touch()
    launcher.write_state(tmp_path, state)
    stopped: list[int] = []
    monkeypatch.setattr(launcher, "_kill", lambda pid: stopped.append(pid) or True)
    unrelated = {"ProcessId": "4321", "ExecutablePath": r"C:\Python311\python.exe", "StartTime": "2026-01-01T00:00:09+00:00"}

    assert "失效" in launcher.stop(tmp_path, lookup=lambda _pid: unrelated)
    assert stopped == []
    assert launcher.read_state(tmp_path) is None


def test_shipped_scripts_delegate_to_pid_scoped_launcher() -> None:
    start = (ROOT / "scripts" / "windows" / "start_biodesign_mvp_safe.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts" / "windows" / "stop_biodesign_mvp_safe.ps1").read_text(encoding="utf-8")

    assert "biodesign_mvp_launcher.py" in start and "biodesign_mvp_launcher.py" in stop
    assert "Stop-Process -Name" not in stop
    assert "taskkill /IM" not in stop
