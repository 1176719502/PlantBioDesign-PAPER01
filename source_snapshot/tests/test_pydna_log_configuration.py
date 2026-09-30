from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core import config


ROOT = Path(__file__).resolve().parents[1]


def test_default_log_directory_uses_local_app_data(tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path)}

    resolved = config.resolve_pydna_log_dir(env)

    assert resolved == (tmp_path / "BioDesignStudio" / "logs" / "pydna").resolve()
    assert resolved != (tmp_path / "pydna" / "pydna" / "Logs").resolve()


@pytest.mark.parametrize("env_name", [config.BIODESIGN_PYDNA_LOG_DIR_ENV, "LOCALAPPDATA"])
def test_environment_changes_are_respected(tmp_path: Path, env_name: str) -> None:
    root = tmp_path / env_name
    env = {env_name: str(root)}

    resolved = config.resolve_pydna_log_dir(env)

    expected = root if env_name == config.BIODESIGN_PYDNA_LOG_DIR_ENV else root / "BioDesignStudio" / "logs" / "pydna"
    assert resolved == expected.resolve()


def test_configure_creates_missing_directory_and_sets_environment(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "pydna"
    env = {
        config.BIODESIGN_PYDNA_LOG_DIR_ENV: str(target),
        "LOCALAPPDATA": str(tmp_path),
    }

    selected = config.configure_pydna_log_dir(env)

    assert selected == target.resolve()
    assert selected.is_dir()
    assert env[config.PYDNA_LOG_DIR_ENV] == str(selected)
    assert env[config.PYDNA_CONFIG_DIR_ENV] == str(
        (tmp_path / "BioDesignStudio" / "pydna" / "config").resolve()
    )
    assert env[config.PYDNA_DATA_DIR_ENV] == str(
        (tmp_path / "BioDesignStudio" / "pydna" / "data").resolve()
    )


def test_unwritable_default_falls_back_to_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    preferred = tmp_path / "local" / "BioDesignStudio" / "logs" / "pydna"
    fallback = tmp_path / "temp" / "BioDesignStudio" / "logs" / "pydna"
    real_check = config._ensure_writable_directory

    def fail_preferred(path: Path) -> None:
        if path == preferred.resolve():
            raise PermissionError("simulated unwritable user directory")
        real_check(path)

    monkeypatch.setattr(config, "_ensure_writable_directory", fail_preferred)
    env = {"LOCALAPPDATA": str(tmp_path / "local"), "TEMP": str(tmp_path / "temp")}

    selected = config.configure_pydna_log_dir(env)

    assert selected == fallback.resolve()
    assert selected.is_dir()
    assert env[config.PYDNA_LOG_DIR_ENV] == str(selected)


def test_configuration_is_idempotent(tmp_path: Path) -> None:
    env = {config.BIODESIGN_PYDNA_LOG_DIR_ENV: str(tmp_path / "logs")}

    first = config.configure_pydna_log_dir(env)
    second = config.configure_pydna_log_dir(env)

    assert second == first


def test_relative_pydna_paths_are_not_resolved_against_cwd(tmp_path: Path) -> None:
    local_app_data = tmp_path / "local"
    env = {
        "LOCALAPPDATA": str(local_app_data),
        config.PYDNA_CONFIG_DIR_ENV: "pydna/pydna",
        config.PYDNA_DATA_DIR_ENV: "pydna/pydna",
        config.PYDNA_LOG_DIR_ENV: ".\\pydna\\pydna\\Logs",
    }

    config.configure_pydna_log_dir(env)

    assert Path(env[config.PYDNA_CONFIG_DIR_ENV]) == (
        local_app_data / "BioDesignStudio" / "pydna" / "config"
    ).resolve()
    assert Path(env[config.PYDNA_DATA_DIR_ENV]) == (
        local_app_data / "BioDesignStudio" / "pydna" / "data"
    ).resolve()
    assert Path(env[config.PYDNA_LOG_DIR_ENV]) == (
        local_app_data / "BioDesignStudio" / "logs" / "pydna"
    ).resolve()


def test_configured_pydna_import_does_not_write_install_tree(tmp_path: Path) -> None:
    install_tree = tmp_path / "read-only-install-tree"
    local_app_data = tmp_path / "local-app-data"
    install_tree.mkdir()
    command = (
        "import json,os; "
        "from core.config import configure_pydna_log_dir; "
        "configure_pydna_log_dir(); import pydna; "
        "print(json.dumps({'file':pydna.__file__,'config':os.environ['pydna_config_dir'],"
        "'data':os.environ['pydna_data_dir'],'log':os.environ['pydna_log_dir']}))"
    )
    environment = {
        **os.environ,
        "LOCALAPPDATA": str(local_app_data),
        "PYTHONPATH": os.pathsep.join(
            [str(ROOT), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep),
        "pydna_config_dir": "pydna/pydna",
        "pydna_data_dir": "pydna/pydna",
        "pydna_log_dir": ".\\pydna\\pydna\\Logs",
    }

    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=install_tree,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert Path(payload["file"]).name == "__init__.py"
    assert Path(payload["config"]).is_relative_to(local_app_data)
    assert Path(payload["data"]).is_relative_to(local_app_data)
    assert Path(payload["log"]).is_relative_to(local_app_data)
    assert list(install_tree.iterdir()) == []


def test_formal_app_startup_does_not_write_working_directory(tmp_path: Path) -> None:
    install_tree = tmp_path / "formal-working-directory"
    local_app_data = tmp_path / "local-app-data"
    database_path = tmp_path / "db" / "biodesign_unified.db"
    install_tree.mkdir()
    environment = {
        **os.environ,
        "BIODESIGN_DB_PATH": str(database_path),
        "LOCALAPPDATA": str(local_app_data),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            [str(ROOT), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep),
        "pydna_config_dir": "pydna/pydna",
        "pydna_data_dir": "pydna/pydna",
        "pydna_log_dir": ".\\pydna\\pydna\\Logs",
    }

    completed = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=install_tree,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert database_path.is_file()
    assert list(install_tree.iterdir()) == []


@pytest.mark.parametrize("source_path", [ROOT / "app.py", ROOT / "core" / "assembly_utils.py"])
def test_pydna_environment_is_configured_before_runtime_imports(source_path: Path) -> None:
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
    calls = [
        index
        for index, node in enumerate(tree.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "configure_pydna_log_dir"
    ]
    pydna_imports = [
        index
        for index, node in enumerate(tree.body)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(alias.name.startswith("pydna") for alias in node.names)
    ]

    assert calls
    assert not pydna_imports or calls[0] < pydna_imports[0]
