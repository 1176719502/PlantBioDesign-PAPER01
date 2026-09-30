# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def external_test_scratch_dir(scratch_dir_name: str) -> Path:
    """Return a test scratch directory that is guaranteed to be outside Git."""
    if not scratch_dir_name or Path(scratch_dir_name).name != scratch_dir_name:
        raise ValueError("scratch_dir_name must be one directory name")
    configured_root = os.environ.get("BIODESIGN_PYTEST_SCRATCH_ROOT")
    scratch_root = Path(
        configured_root
        or Path(tempfile.gettempdir()) / "BioDesignStudio" / "pytest_scratch"
    ).expanduser().resolve(strict=False)
    if scratch_root == ROOT or ROOT in scratch_root.parents:
        raise RuntimeError("BIODESIGN_PYTEST_SCRATCH_ROOT must be outside the repository")
    base_dir = scratch_root / scratch_dir_name
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def repo_local_sqlite_db_path(scratch_dir_name: str, filename: str) -> Path:
    """Return a clean SQLite DB path using the legacy helper API."""
    base_dir = external_test_scratch_dir(scratch_dir_name)
    path = base_dir / filename
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()
    return path
