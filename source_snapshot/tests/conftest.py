# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import pytest

from tests.helpers.windows_pytest_temp_compat import install_windows_pytest_temp_mode_compat


install_windows_pytest_temp_mode_compat()


REPO_ROOT = Path(__file__).resolve().parents[1]
SHORT_TEMP_LAYOUT_ENV = "BIODESIGN_PYTEST_SHORT_TEMP_LAYOUT"


def _is_within_repository(path: Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    return resolved == REPO_ROOT or REPO_ROOT in resolved.parents


def _external_temp_root() -> Path:
    candidates: list[Path] = []
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Temp")
        candidates.append(Path.home() / "AppData" / "Local" / "Temp")
    candidates.append(Path(tempfile.gettempdir()))

    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if _is_within_repository(resolved):
            continue
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved
    raise RuntimeError("Could not resolve an external temporary root outside the repository.")


def pytest_configure(config: pytest.Config) -> None:
    short_layout = os.environ.get(SHORT_TEMP_LAYOUT_ENV) == "1"
    external_root = _external_temp_root() / ("p" if short_layout else "BioDesignStudio/pytest")
    external_root.mkdir(parents=True, exist_ok=True)
    configured_basetemp = config.option.basetemp
    if configured_basetemp is None:
        run_id = uuid4().hex[:8] if short_layout else uuid4().hex
        config.option.basetemp = external_root / f"{'r' if short_layout else 'run'}-{run_id}"
    elif _is_within_repository(Path(configured_basetemp)):
        raise pytest.UsageError("pytest --basetemp must be outside the repository")

    scratch_root = Path(
        os.environ.get(
            "BIODESIGN_PYTEST_SCRATCH_ROOT",
            external_root / ("s" if short_layout else "scratch"),
        )
    )
    if _is_within_repository(scratch_root):
        raise pytest.UsageError("BIODESIGN_PYTEST_SCRATCH_ROOT must be outside the repository")
    os.environ["BIODESIGN_PYTEST_SCRATCH_ROOT"] = str(
        scratch_root.expanduser().resolve(strict=False)
    )


@pytest.fixture
def external_tmp_path() -> Path:
    temp_dir = _external_temp_root() / f"biodesign-external-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        os.chmod(temp_dir, 0o777)
    except OSError:
        pass
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
