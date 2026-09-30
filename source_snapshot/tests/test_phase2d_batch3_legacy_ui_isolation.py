from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from views.legacy_ui_registry import LEGACY_UI_MODULE_PATHS, load_legacy_ui_module
from views import tool_typography


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PYTHON = ROOT / ".venv312" / "Scripts" / "python.exe"
PYTHON = REPOSITORY_PYTHON if REPOSITORY_PYTHON.is_file() else Path(sys.executable)
LEGACY_MODULE_PATHS = tuple(LEGACY_UI_MODULE_PATHS.values())
FORMAL_PAGE_LABELS = (
    "Project Home",
    "Six-Step Design Workspace",
    "Results and Export",
    "Plant Component Library",
    "Sequence Toolbox",
)
SIDEBAR_PAGE_LABELS = (
    "Project Home",
    "Agent V1 Workspace",
    "Six-Step Design Workspace",
    "Plant Component Library",
    "Sequence Toolbox",
    "CRISPR V1 Workflow",
)
CRISPR_PAGE_LABEL = "CRISPR V1 Workflow"
AGENT_PAGE_LABEL = "Agent V1 Workspace"


def _run_fresh_python(code: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "BIODESIGN_DB_PATH": str(tmp_path / "runtime.db"),
            "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(tmp_path / "drafts"),
            "pydna_log_dir": str(tmp_path / "pydna"),
        }
    )
    return subprocess.run(
        [str(PYTHON), "-c", code],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _json_result(result: subprocess.CompletedProcess[str], marker: str) -> dict[str, object]:
    line = next(line for line in result.stdout.splitlines() if line.startswith(marker))
    return json.loads(line.removeprefix(marker))


def test_formal_app_import_keeps_legacy_modules_out_of_sys_modules(tmp_path: Path) -> None:
    code = f"""
import json
import sys
import app
legacy = {LEGACY_MODULE_PATHS!r}
print('RESULT=' + json.dumps({{
    'loaded': {{name: name in sys.modules for name in legacy}},
    'pages': app._ALL_PAGES,
    'primary_pages': app._PRIMARY_NAV_PAGES,
    'route_aliases': app._PRIMARY_NAV_ROUTE_ALIASES,
    'mvp_app_loaded': 'mvp_app' in sys.modules,
}}))
"""

    payload = _json_result(_run_fresh_python(code, tmp_path), "RESULT=")

    assert payload["loaded"] == {name: False for name in LEGACY_MODULE_PATHS}
    assert payload["pages"] == [*FORMAL_PAGE_LABELS, CRISPR_PAGE_LABEL, AGENT_PAGE_LABEL]
    assert [page for page in payload["pages"] if page not in {CRISPR_PAGE_LABEL, AGENT_PAGE_LABEL}] == list(FORMAL_PAGE_LABELS)
    assert payload["primary_pages"] == list(SIDEBAR_PAGE_LABELS)
    assert CRISPR_PAGE_LABEL not in payload["route_aliases"]
    assert payload["mvp_app_loaded"] is False


def test_legacy_registry_import_is_lazy(tmp_path: Path) -> None:
    code = f"""
import json
import sys
import views.legacy_ui_registry
legacy = {LEGACY_MODULE_PATHS!r}
print('RESULT=' + json.dumps({{name: name in sys.modules for name in legacy}}))
"""

    payload = _json_result(_run_fresh_python(code, tmp_path), "RESULT=")

    assert payload == {name: False for name in LEGACY_MODULE_PATHS}


@pytest.mark.parametrize(("page_id", "module_path"), LEGACY_UI_MODULE_PATHS.items())
def test_legacy_registry_preserves_public_import_paths(page_id: str, module_path: str) -> None:
    module = load_legacy_ui_module(page_id)

    assert module.__name__ == module_path
    assert callable(module.render)


def test_legacy_compatibility_imports_do_not_open_sqlite_or_write_session_state(tmp_path: Path) -> None:
    code = """
import json
import sqlite3
import streamlit as st

state = {'sentinel': 'unchanged'}
st.session_state = state

def blocked_connect(*args, **kwargs):
    raise AssertionError('legacy module import opened SQLite')

sqlite3.connect = blocked_connect
from views.legacy_ui_registry import load_all_legacy_ui_modules
modules = load_all_legacy_ui_modules()
print('RESULT=' + json.dumps({
    'modules': {key: module.__name__ for key, module in modules.items()},
    'state': state,
}))
"""

    payload = _json_result(_run_fresh_python(code, tmp_path), "RESULT=")

    assert payload["modules"] == dict(LEGACY_UI_MODULE_PATHS)
    assert payload["state"] == {"sentinel": "unchanged"}


def test_unknown_legacy_page_id_is_rejected_without_importing_a_module() -> None:
    before = set(sys.modules)

    with pytest.raises(KeyError, match="Unknown legacy UI page"):
        load_legacy_ui_module("not_a_legacy_page")

    assert set(sys.modules) == before


def test_temporary_typography_streamlit_binding_restores_after_exception() -> None:
    original_st = tool_typography.st
    fake_st = SimpleNamespace(markdown=lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="render failed"):
        with tool_typography.temporary_streamlit_binding(fake_st):
            assert tool_typography.st is fake_st
            raise RuntimeError("render failed")

    assert tool_typography.st is original_st
