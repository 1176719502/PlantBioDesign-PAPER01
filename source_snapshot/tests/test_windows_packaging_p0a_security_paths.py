from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import (
    RuntimePathError,
    ensure_biodesign_log_dir,
    ensure_biodesign_runtime_dir,
    resolve_biodesign_log_dir,
    resolve_biodesign_runtime_dir,
)
from services import pbi121_replacement_strategy
from services import real_genbank_asset_import
from services.pbi121_replacement_strategy import _strategy_path
from services.real_genbank_asset_import import _state_path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PYTHON = ROOT / ".venv312" / "Scripts" / "python.exe"
TEST_PYTHON = REPOSITORY_PYTHON if REPOSITORY_PYTHON.is_file() else Path(sys.executable)


def test_real_streamlit_secrets_are_not_tracked_or_distributed() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".streamlit/secrets.toml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert tracked.stdout.strip() == ""
    assert ".streamlit/secrets.toml" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert (ROOT / ".streamlit" / "secrets.example.toml").is_file()


def test_missing_secrets_does_not_block_static_imports() -> None:
    result = subprocess.run(
        [
            str(TEST_PYTHON),
            "-c",
            "import core.config; import utils.logger; import scripts.windows.biodesign_formal_launcher",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_runtime_and_logs_resolve_under_local_app_data(tmp_path: Path) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}

    assert resolve_biodesign_runtime_dir(environ) == tmp_path / "BioDesignStudio" / "runtime"
    assert resolve_biodesign_log_dir(environ) == tmp_path / "BioDesignStudio" / "logs"
    assert ensure_biodesign_runtime_dir(environ).is_dir()
    assert ensure_biodesign_log_dir(environ).is_dir()


def test_missing_local_app_data_uses_user_level_fallback(tmp_path: Path) -> None:
    environ = {"USERPROFILE": str(tmp_path)}

    assert resolve_biodesign_runtime_dir(environ) == (
        tmp_path / "AppData" / "Local" / "BioDesignStudio" / "runtime"
    )


def test_install_tree_is_not_used_for_runtime_writes(tmp_path: Path, monkeypatch) -> None:
    install_root = tmp_path / "read_only_install"
    install_root.mkdir()
    monkeypatch.chdir(install_root)
    environ = {"LOCALAPPDATA": str(tmp_path / "user_data")}

    runtime = ensure_biodesign_runtime_dir(environ)
    logs = ensure_biodesign_log_dir(environ)

    assert install_root not in runtime.parents
    assert install_root not in logs.parents
    assert list(install_root.iterdir()) == []


def test_formal_pbi121_state_defaults_to_user_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "BioDesignStudio" / "runtime"

    assert _state_path().parent == expected
    assert _strategy_path().parent == expected


def test_pbi121_defaults_do_not_write_to_read_only_install_tree(
    tmp_path: Path, monkeypatch
) -> None:
    install_root = tmp_path / "read_only_install"
    install_root.mkdir()
    before = tuple(install_root.rglob("*"))
    local_app_data = tmp_path / "isolated_user_data"
    original_mkdir = Path.mkdir
    original_open = builtins.open

    def deny_install_mkdir(path: Path, *args, **kwargs):
        if path == install_root or install_root in path.parents:
            raise PermissionError(f"write denied below install tree: {path}")
        return original_mkdir(path, *args, **kwargs)

    def deny_install_open(file, mode="r", *args, **kwargs):
        path = Path(file)
        if any(flag in mode for flag in "wax+") and (
            path == install_root or install_root in path.parents
        ):
            raise PermissionError(f"write denied below install tree: {path}")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_install_mkdir)
    monkeypatch.setattr(builtins, "open", deny_install_open)
    monkeypatch.chdir(install_root)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    state_path = _state_path()
    strategy_path = _strategy_path()
    expected_runtime = local_app_data / "BioDesignStudio" / "runtime"

    assert state_path.parent == expected_runtime
    assert strategy_path.parent == expected_runtime
    assert expected_runtime.is_dir()
    assert not (install_root / ".runtime").exists()
    assert tuple(install_root.rglob("*")) == before


def test_pbi121_missing_source_record_fails_explicitly_without_writes(
    tmp_path: Path, monkeypatch
) -> None:
    install_root = tmp_path / "read_only_install"
    install_root.mkdir()
    missing_source = install_root / "resources" / "pbi121" / "AF485783.1.gb"
    isolated_runtime = tmp_path / "isolated_user_data" / "BioDesignStudio" / "runtime"
    before = tuple(install_root.rglob("*"))
    monkeypatch.chdir(install_root)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "isolated_user_data"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "isolated_profile"))
    monkeypatch.setattr(real_genbank_asset_import, "PBI121_SOURCE_RECORD", missing_source)

    with pytest.raises(FileNotFoundError) as exc_info:
        pbi121_replacement_strategy.load_strategy(runtime_root=isolated_runtime)

    assert Path(exc_info.value.filename) == missing_source
    assert "No such file or directory" in str(exc_info.value)
    assert not missing_source.exists()
    assert not isolated_runtime.exists()
    assert tuple(install_root.rglob("*")) == before


def test_directory_creation_failure_is_explicit(tmp_path: Path) -> None:
    blocked_root = tmp_path / "not_a_directory"
    blocked_root.write_text("blocked", encoding="utf-8")

    with pytest.raises(RuntimePathError, match="Cannot create BioDesign Studio runtime directory"):
        ensure_biodesign_runtime_dir({"LOCALAPPDATA": str(blocked_root)})
