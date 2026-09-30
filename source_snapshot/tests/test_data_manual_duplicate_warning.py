# -*- coding: utf-8 -*-
"""Regression tests for Data registry manual duplicate warnings."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from views.Data import _manual_name_duplicate


def test_manual_name_duplicate_matches_existing_registry_name() -> None:
    """Manual entry should flag an exact existing name before submit."""
    existing_names = frozenset({"CaMV35S Promoter", "B0034 RBS"})

    duplicate_name = _manual_name_duplicate("CaMV35S Promoter", existing_names)

    assert duplicate_name == "CaMV35S Promoter"


def test_manual_name_duplicate_ignores_blank_and_new_names() -> None:
    """Blank or unique names should not produce a duplicate warning."""
    existing_names = frozenset({"CaMV35S Promoter"})

    assert _manual_name_duplicate("", existing_names) is None
    assert _manual_name_duplicate("New Terminator", existing_names) is None
