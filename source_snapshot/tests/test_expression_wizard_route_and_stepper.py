from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_direct_expression_wizard_query_overrides_stale_session_page() -> None:
    from core.page_routing import reconcile_selected_page_from_query

    session_state = {"selected_page": "Homepage"}
    query_params = {"page": "Expression Wizard"}

    selected = reconcile_selected_page_from_query(
        session_state,
        query_params,
        ["Homepage", "Expression Wizard", "Dashboard"],
        selected_page_key="selected_page",
        default_page="Expression Wizard",
    )

    assert selected == "Expression Wizard"
    assert session_state["selected_page"] == "Expression Wizard"


def test_invalid_page_state_falls_back_to_expression_wizard() -> None:
    from core.page_routing import reconcile_selected_page_from_query

    session_state = {"selected_page": ""}
    query_params = {"page": "Unknown"}

    selected = reconcile_selected_page_from_query(
        session_state,
        query_params,
        ["Homepage", "Expression Wizard", "Dashboard"],
        selected_page_key="selected_page",
        default_page="Expression Wizard",
    )

    assert selected == "Expression Wizard"
    assert session_state["selected_page"] == "Expression Wizard"


def test_sidebar_navigation_updates_page_query_param() -> None:
    app_source = Path(ROOT, "app.py").read_text(encoding="utf-8")

    assert 'st.query_params["page"] = target' in app_source
    assert "reconcile_selected_page_from_query(" in app_source


def test_expression_wizard_stepper_uses_two_readable_rows() -> None:
    from views.wizard_steps._shared import _step_indicator_rows

    rows = _step_indicator_rows(
        [
            "Gene Input",
            "Host & Regulatory Elements",
            "Codon Usage Preview & Expression Frame",
            "Cassette / Boundary Review",
            "Review Checks",
            "Output",
        ],
        per_row=3,
    )

    assert rows == [
        [
            (1, "Gene Input"),
            (2, "Host & Regulatory Elements"),
            (3, "Codon Usage Preview & Expression Frame"),
        ],
        [
            (4, "Cassette / Boundary Review"),
            (5, "Review Checks"),
            (6, "Output"),
        ],
    ]
