from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PYTEST_RUNNER = ROOT / "scripts" / "run_pytest.py"


def _is_within_repository(path: Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    return resolved == ROOT or ROOT in resolved.parents


def test_kb_release_text_resources_have_explicit_lf_checkout_contract() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert "data/knowledge_base_v0/manifest.json text eol=lf" in attributes
    assert "services/knowledge_base/schema_v1.sql text eol=lf" in attributes


def test_repository_pytest_runner_disables_bytecode_before_importing_pytest() -> None:
    source = PYTEST_RUNNER.read_text(encoding="utf-8")

    disable_at = source.index('os.environ["PYTHONDONTWRITEBYTECODE"] = "1"')
    pytest_import_at = source.index("import pytest")
    assert disable_at < pytest_import_at


def test_pytest_runtime_artifacts_are_configured_outside_repository(
    pytestconfig: pytest.Config,
) -> None:
    assert sys.dont_write_bytecode is True
    assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
    assert pytestconfig.pluginmanager.get_plugin("cacheprovider") is None

    basetemp = Path(pytestconfig.option.basetemp)
    scratch_root = Path(os.environ["BIODESIGN_PYTEST_SCRATCH_ROOT"])
    assert not _is_within_repository(basetemp)
    assert not _is_within_repository(scratch_root)
    assert basetemp.parent.is_dir()
