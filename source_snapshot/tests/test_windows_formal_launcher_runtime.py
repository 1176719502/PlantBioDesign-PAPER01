"""Focused checks for the formal Windows launcher and startup contract."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "windows" / "biodesign_formal_launcher.py"


@pytest.fixture(scope="module")
def launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("formal_launcher", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def isolated_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_app_data"))


def _runner(versions: dict[str, tuple[int, int, int]], failures: dict[str, str] | None = None):
    failures = failures or {}

    def run(command, **_kwargs):
        label = " ".join(command[:2])
        version = versions.get(label, versions.get(command[0]))
        code = command[-1]
        failed = failures.get(label, failures.get(command[0], ""))
        if version is None:
            return SimpleNamespace(returncode=1, stdout="")
        if "json.dumps" in code:
            return SimpleNamespace(returncode=0, stdout=json.dumps([rf"C:\\{command[0]}.exe", *version]))
        if failed == "streamlit" and "import streamlit" in code:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    return run


def test_incompatible_candidate_is_skipped_for_supported_python(launcher, tmp_path: Path) -> None:
    (tmp_path / "app.py").touch()
    runner = _runner(
        {
            str(tmp_path / ".venv312" / "Scripts" / "python.exe"): (3, 13, 1),
            "py -3.12": (3, 12, 8),
        }
    )

    selected, rejected = launcher.select_python(tmp_path, runner=runner)

    assert selected.command.command == "py"
    assert selected.command.arguments == ("-3.12",)
    assert selected.version == "3.12.8"
    assert rejected[0].reason == "Python 3.10-3.12 is required."


def test_candidate_rejection_reason_for_missing_streamlit(launcher, tmp_path: Path) -> None:
    (tmp_path / "app.py").touch()
    candidate = launcher.PythonCommand("candidate")

    result = launcher.probe_candidate(
        candidate,
        tmp_path,
        runner=_runner({"candidate": (3, 12, 5)}, {"candidate": "streamlit"}),
    )

    assert result.accepted is False
    assert result.reason == "Streamlit is not installed."


def test_start_refuses_busy_port_without_stopping_unknown_process(launcher, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").touch()
    monkeypatch.setattr(launcher, "read_state", lambda _root: None)
    monkeypatch.setattr(launcher, "_port_available", lambda _port: False)

    with pytest.raises(launcher.LauncherError, match="Port 8528 is already in use"):
        launcher.start(tmp_path)


def test_runtime_state_records_formal_entry(launcher, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").touch()
    selected = launcher.SelectedPython(
        launcher.PythonCommand("py", ("-3.12",)),
        r"C:\Python312\python.exe",
        "3.12.8",
    )
    monkeypatch.setattr(launcher, "select_python", lambda _root: (selected, []))
    monkeypatch.setattr(launcher, "_port_available", lambda _port: True)
    monkeypatch.setattr(launcher, "http_available", lambda _url: True)
    monkeypatch.setattr(launcher, "listening_pid", lambda _port: 9753)
    monkeypatch.setattr(
        launcher,
        "process_info",
        lambda _pid, runner=None: {
            "ProcessId": "9753",
            "ExecutablePath": r"C:\Python312\python.exe",
            "StartTime": "2026-01-01T00:00:01+00:00",
        },
    )

    class Process:
        pid = 2468

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    state, reused, _skipped = launcher.start(
        tmp_path,
        lookup=lambda _pid: {
            "ProcessId": "9753",
            "ExecutablePath": r"C:\Python312\python.exe",
            "StartTime": "2026-01-01T00:00:01+00:00",
        },
    )

    assert reused is False
    assert launcher.read_state(tmp_path) == state
    payload = json.loads(launcher.state_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["app_entry_path"].endswith("app.py")
    assert payload["port"] == 8528
    assert payload["pid"] == 9753
    assert payload["python_executable"] == r"C:\Python312\python.exe"
    assert launcher.state_path(tmp_path).parent == tmp_path / "local_app_data" / "BioDesignStudio" / "runtime"
    assert (tmp_path / "local_app_data" / "BioDesignStudio" / "logs" / "formal_streamlit.8528.log").is_file()


def test_stop_does_not_terminate_unrelated_python(launcher, tmp_path: Path, monkeypatch) -> None:
    state = launcher.RuntimeState(
        4321,
        r"C:\Python312\python.exe",
        "3.12.8",
        "py",
        ["-3.12"],
        "2026-01-01T00:00:01+00:00",
        str(tmp_path),
        str(tmp_path / "app.py"),
        8528,
        "http://127.0.0.1:8528",
    )
    (tmp_path / "app.py").touch()
    launcher.write_state(tmp_path, state)
    stopped: list[int] = []
    monkeypatch.setattr(launcher, "_kill", lambda pid: stopped.append(pid) or True)
    unrelated = {
        "ProcessId": "4321",
        "ExecutablePath": r"C:\Python312\python.exe",
        "StartTime": "2026-01-01T00:00:09+00:00",
    }

    assert "Cleared stale" in launcher.stop(tmp_path, lookup=lambda _pid: unrelated)
    assert stopped == []
    assert launcher.read_state(tmp_path) is None


def test_process_timestamp_parser_accepts_powershell_precision(launcher) -> None:
    parsed = launcher._parse_process_timestamp("2026-07-21T03:30:38.8850627Z")

    assert parsed.isoformat() == "2026-07-21T03:30:38.885062+00:00"


def test_shipped_scripts_delegate_to_formal_launcher() -> None:
    start_bat = (ROOT / "START.bat").read_text(encoding="utf-8")
    stop_bat = (ROOT / "Stop_BioDesign_Formal.bat").read_text(encoding="utf-8")
    start_ps1 = (ROOT / "scripts" / "windows" / "start_biodesign_formal_safe.ps1").read_text(encoding="utf-8")
    stop_ps1 = (ROOT / "scripts" / "windows" / "stop_biodesign_formal_safe.ps1").read_text(encoding="utf-8")

    assert "start_biodesign_formal_safe.ps1" in start_bat
    assert "stop_biodesign_formal_safe.ps1" in stop_bat
    assert "biodesign_formal_launcher.py" in start_ps1
    assert "biodesign_formal_launcher.py" in stop_ps1
    assert "mvp_app.py" not in start_bat
    assert "8501" not in start_bat
