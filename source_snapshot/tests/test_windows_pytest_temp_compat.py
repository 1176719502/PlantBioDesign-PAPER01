# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

from tests.helpers.windows_pytest_temp_compat import (
    WINDOWS_SAFE_TMP_MODE,
    install_windows_pytest_temp_mode_compat,
)


def test_windows_pytest_temp_compat_installs_only_on_windows() -> None:
    installed = install_windows_pytest_temp_mode_compat()

    assert installed is (sys.platform == "win32")


def test_windows_pytest_temp_compat_uses_non_private_directory_mode() -> None:
    assert WINDOWS_SAFE_TMP_MODE == 0o777
