# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any


WINDOWS_SAFE_TMP_MODE = 0o777


def install_windows_pytest_temp_mode_compat() -> bool:
    """Avoid pytest's 0o700 temp-dir mode on Windows builds where it is unreadable."""
    if sys.platform != "win32":
        return False

    import _pytest.tmpdir as pytest_tmpdir
    from _pytest.pathlib import (
        LOCK_TIMEOUT,
        make_numbered_dir,
        make_numbered_dir_with_cleanup,
        rm_rf,
    )

    factory_cls = pytest_tmpdir.TempPathFactory
    if getattr(factory_cls, "_biodesign_windows_temp_mode_compat", False):
        return True

    def getbasetemp(self: Any) -> Path:
        if self._basetemp is not None:
            return self._basetemp

        if self._given_basetemp is not None:
            basetemp = self._given_basetemp
            if basetemp.exists():
                rm_rf(basetemp)
            basetemp.mkdir(mode=WINDOWS_SAFE_TMP_MODE)
            basetemp = basetemp.resolve()
        else:
            from_env = os.environ.get("PYTEST_DEBUG_TEMPROOT")
            temproot = Path(from_env or tempfile.gettempdir()).resolve()
            user = pytest_tmpdir.get_user() or "unknown"
            rootdir = temproot.joinpath(f"pytest-of-{user}")
            try:
                rootdir.mkdir(mode=WINDOWS_SAFE_TMP_MODE, exist_ok=True)
            except OSError:
                rootdir = temproot.joinpath("pytest-of-unknown")
                rootdir.mkdir(mode=WINDOWS_SAFE_TMP_MODE, exist_ok=True)

            keep = self._retention_count
            if self._retention_policy == "none":
                keep = 0
            basetemp = make_numbered_dir_with_cleanup(
                prefix="pytest-",
                root=rootdir,
                keep=keep,
                lock_timeout=LOCK_TIMEOUT,
                mode=WINDOWS_SAFE_TMP_MODE,
            )

        self._basetemp = basetemp
        self._trace("new basetemp", basetemp)
        return basetemp

    def mktemp(self: Any, basename: str, numbered: bool = True) -> Path:
        basename = self._ensure_relative_to_basetemp(basename)
        if not numbered:
            path = self.getbasetemp().joinpath(basename)
            path.mkdir(mode=WINDOWS_SAFE_TMP_MODE)
        else:
            path = make_numbered_dir(
                root=self.getbasetemp(),
                prefix=basename,
                mode=WINDOWS_SAFE_TMP_MODE,
            )
            self._trace("mktemp", path)
        return path

    factory_cls.getbasetemp = getbasetemp
    factory_cls.mktemp = mktemp
    factory_cls._biodesign_windows_temp_mode_compat = True
    return True
