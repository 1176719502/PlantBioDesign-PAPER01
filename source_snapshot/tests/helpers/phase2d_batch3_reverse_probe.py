"""Diagnostic-only pytest plugin for locating reverse-order Streamlit drift.

Load explicitly with ``-p tests.helpers.phase2d_batch3_reverse_probe``.
The default suite does not import this module.
"""
from __future__ import annotations

import sys

import pytest


_previous_nodeid: str | None = None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    items.reverse()


def pytest_runtest_setup(item: pytest.Item) -> None:
    import views.DesignLibrary as design_library
    import views.tool_typography as tool_typography

    streamlit_module = sys.modules.get("streamlit")
    if design_library.st is tool_typography.st is streamlit_module:
        return

    details = (
        "Streamlit identity drift located: "
        f"previous={_previous_nodeid}; current={item.nodeid}; "
        f"DesignLibrary.st={design_library.st!r}; "
        f"tool_typography.st={tool_typography.st!r}; "
        f"sys.modules['streamlit']={streamlit_module!r}"
    )
    print(details, file=sys.__stdout__, flush=True)
    pytest.exit(details, returncode=3)


def pytest_runtest_teardown(item: pytest.Item) -> None:
    global _previous_nodeid
    _previous_nodeid = item.nodeid
