# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_candidate_route_decision_matrix as matrix


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("valid", "ated ", "con", "struct"),
    _term("optimized ", "pathway"),
    _term("yield ", "pre", "diction"),
    _term("recom", "mended"),
    _term("best"),
    _term("top ", "route"),
    _term("rank", "ing"),
    _term("scor", "ing"),
    _term("optim", "ization"),
    _term("pre", "diction"),
    _term("vali", "dated"),
    _term("experimentally ", "confirmed"),
    _term("ready ", "for synthesis"),
    _term("ready ", "for wet lab"),
)


def _complete_route(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "route_label": "Route A documentation follow-up",
        "route_type": "Plant expression construct review",
        "plant_host_context": "Oryza sativa documentation context",
        "tissue_or_compartment_context": "seed tissue review context",
        "expression_mode_context": "stable expression documentation context",
        "component_context_summary": "promoter/CDS/terminator records linked for review",
        "linked_evidence_notes": "local source records and literature notes recorded",
        "route_risk_notes": "source lineage requires manual review",
        "missing_information": "none recorded",
        "manual_follow_up": "Review source/provenance notes with project reviewer.",
        "decision_status": "Selected for documentation follow-up",
        "decision_rationale": "Human reviewer kept this row for package drafting.",
        "rejection_rationale": "",
    }
    row.update(overrides)
    return row


def test_empty_input_returns_safe_empty_state() -> None:
    view = matrix.build_route_decision_matrix([])

    assert view["rows"] == []
    assert view["summary"]["route_count"] == 0
    assert view["empty_state_message"]
    assert "documentation-only" in view["boundary_note"].lower()


def test_complete_route_preserves_user_text_and_summary_counts() -> None:
    view = matrix.build_route_decision_matrix([_complete_route()])

    assert view["summary"]["route_count"] == 1
    assert view["summary"]["documentation_complete_count"] == 1
    assert view["summary"]["documentation_gap_count"] == 0
    assert view["summary"]["selected_for_documentation_follow_up_count"] == 1

    row = view["rows"][0]
    assert row["route_label"] == "Route A documentation follow-up"
    assert row["decision_status"] == "Selected for documentation follow-up"
    assert row["missing_fields"] == []
    assert row["documentation_status"] == "documentation fields recorded"
    assert row["review_focus"] == "manual documentation review"
    assert row["gap_label"] == "No required documentation fields missing"
    assert row["next_manual_action"] == matrix.RECORDED_FIELD_ACTION


def test_missing_required_fields_create_gap_rows_and_manual_action() -> None:
    view = matrix.build_route_decision_matrix(
        [
            {
                "route_label": "Partial route",
                "route_type": "",
                "plant_host_context": "Nicotiana documentation context",
            }
        ]
    )

    row = view["rows"][0]
    assert row["documentation_status"] == "documentation gaps recorded"
    assert row["missing_fields"] == [
        "route_type",
        "linked_evidence_notes",
        "manual_follow_up",
    ]
    assert row["review_focus"] == "source/provenance review"
    assert row["next_manual_action"] == matrix.MISSING_FIELD_ACTION
    assert view["summary"]["documentation_gap_count"] == 1
    assert view["gap_rows"][0]["route_label"] == "Partial route"


def test_unknown_decision_status_is_normalized_to_under_review() -> None:
    view = matrix.build_route_decision_matrix(
        [
            _complete_route(decision_status="recommended"),
        ]
    )

    assert view["rows"][0]["decision_status"] == "Under review"
    assert view["summary"]["decision_status_counts"] == {"Under review": 1}


def test_rejection_rationale_is_preserved_without_route_choice_claim() -> None:
    view = matrix.build_route_decision_matrix(
        [
            _complete_route(
                route_label="Route excluded from follow-up",
                decision_status="Rejected by reviewer",
                rejection_rationale="Reviewer excluded this route because source provenance is incomplete.",
            )
        ]
    )

    row = view["rows"][0]
    assert row["decision_status"] == "Rejected by reviewer"
    assert row["rejection_rationale"] == (
        "Reviewer excluded this route because source provenance is incomplete."
    )
    assert view["summary"]["rejected_by_reviewer_count"] == 1
    assert view["manual_follow_up_queue"][0]["route_label"] == "Route excluded from follow-up"


def test_view_model_route_rows_are_accepted() -> None:
    view = matrix.build_route_decision_matrix(
        {
            "route_rows": [
                _complete_route(route_label="View model route"),
            ]
        }
    )

    assert [row["route_label"] for row in view["rows"]] == ["View model route"]


def test_row_order_is_deterministic_by_label_and_route_type() -> None:
    view = matrix.build_route_decision_matrix(
        [
            _complete_route(route_label="Zulu route", route_type="B route type"),
            _complete_route(route_label="Alpha route", route_type="Z route type"),
            _complete_route(route_label="Alpha route", route_type="A route type"),
        ]
    )

    assert [(row["route_label"], row["route_type"]) for row in view["rows"]] == [
        ("Alpha route", "A route type"),
        ("Alpha route", "Z route type"),
        ("Zulu route", "B route type"),
    ]


def test_markdown_snapshot_includes_summary_gaps_and_boundary() -> None:
    snapshot = matrix.format_route_decision_matrix_markdown(
        [
            _complete_route(route_label="Complete route"),
            {"route_label": "Partial route", "route_type": "Plant expression review"},
        ]
    )

    assert snapshot.startswith("# Plant Candidate Route Decision Matrix Snapshot")
    assert "Documentation-only candidate route review" in snapshot
    assert "- route rows: 2" in snapshot
    assert "## Documentation gap rows" in snapshot
    assert "Partial route" in snapshot
    assert "## Manual follow-up queue" in snapshot
    assert "does not save structured project records" in snapshot


def test_route_evidence_cards_link_to_route_rows_without_claims() -> None:
    workspace = matrix.build_route_review_workspace(
        [
            _complete_route(route_label="Evidence route"),
            {"route_label": "Missing evidence route", "route_type": "Plant expression review"},
        ]
    )

    evidence = workspace["evidence_cards"]

    assert workspace["summary"]["route_count"] == 2
    assert workspace["summary"]["evidence_card_count"] == 2
    assert evidence["summary"]["cards_with_evidence_notes"] == 1
    assert evidence["summary"]["cards_needing_evidence_notes"] == 1
    assert evidence["cards"][0]["route_label"] == "Evidence route"
    assert evidence["cards"][0]["evidence_context_status"] == "evidence note recorded"
    assert evidence["cards"][1]["route_label"] == "Missing evidence route"
    assert evidence["cards"][1]["evidence_context_status"] == "evidence note needed"
    assert "Documentation-only" in evidence["boundary_note"]


def test_component_traceability_rows_preserve_component_context_without_selection() -> None:
    traceability = matrix.build_route_component_traceability(
        [
            _complete_route(route_label="Trace route"),
            _complete_route(route_label="No component context", component_context_summary=""),
        ]
    )

    assert traceability["summary"]["traceability_row_count"] == 2
    assert traceability["summary"]["rows_with_component_context"] == 1
    assert traceability["summary"]["rows_needing_component_context"] == 1
    assert traceability["rows"][0]["component_trace_status"] == "component context needed"
    assert traceability["rows"][1]["component_trace_status"] == "component context recorded"


def test_workspace_markdown_includes_route_evidence_component_sections() -> None:
    workspace = matrix.build_route_review_workspace(
        [
            _complete_route(route_label="Workspace route"),
        ]
    )
    snapshot = matrix.format_route_review_workspace_markdown(workspace)

    assert snapshot.startswith("# Plant Route Review Workspace Snapshot")
    assert "## Workspace summary" in snapshot
    assert "## Route rows" in snapshot
    assert "## Evidence cards" in snapshot
    assert "## Component traceability" in snapshot
    assert "Workspace route" in snapshot
    assert "does not save structured project records" in snapshot


def test_no_ordering_metric_or_selection_advice_wording_appears() -> None:
    payload_text = str(
        matrix.build_route_review_workspace(
            [
                _complete_route(route_label="Alpha route"),
                {"route_label": "Partial route"},
            ]
        )
    ).lower()
    snapshot = (
        matrix.format_route_decision_matrix_markdown(
            [_complete_route(route_label="Alpha route"), {"route_label": "Partial route"}]
        )
        + "\n"
        + matrix.format_route_review_workspace_markdown(
            [_complete_route(route_label="Alpha route"), {"route_label": "Partial route"}]
        )
    ).lower()
    service_text = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "plant_candidate_route_decision_matrix.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in payload_text
        assert forbidden not in snapshot
        assert forbidden not in service_text


def test_service_does_not_import_streamlit(monkeypatch) -> None:
    original_import = builtins.__import__

    def _block_streamlit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("plant candidate route decision matrix must not import Streamlit")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit_import)

    view = matrix.build_route_decision_matrix([_complete_route()])

    assert view["summary"]["route_count"] == 1
    importlib.reload(matrix)
