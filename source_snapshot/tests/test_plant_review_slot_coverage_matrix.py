# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_review_slot_coverage_matrix as matrix
from services.plant_review_workspace_workflow_orchestrator import build_plant_review_workspace_workflow
from tests.test_plant_review_workspace_workflow_orchestrator import _workspace_state


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _by_slot(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["slot_id"]: row for row in rows}


def test_slot_coverage_matrix_builds_rows_from_workspace_workflow_result() -> None:
    workflow = build_plant_review_workspace_workflow(_workspace_state())

    result = matrix.build_plant_review_slot_coverage_matrix(workflow)
    rows = _by_slot(result["rows"])

    assert result["slot_coverage_matrix_schema_version"] == matrix.SLOT_COVERAGE_MATRIX_SCHEMA_VERSION
    assert result["source_kind"] == "workspace_workflow"
    assert result["matrix_status"] == "manual_review_required"
    assert result["summary"]["slot_count"] >= 10
    assert result["summary"]["evidence_gap_count"] >= 1
    assert result["summary"]["component_gap_count"] >= 1
    assert result["summary"]["provenance_gap_count"] >= 1
    assert rows["promoter_slot"]["required_or_optional"] == "required"
    assert rows["promoter_slot"]["evidence_count"] == 1
    assert rows["promoter_slot"]["component_count"] == 1
    assert rows["promoter_slot"]["provenance_gap"] is True
    assert rows["terminator_slot"]["evidence_gap"] is True
    assert rows["terminator_slot"]["component_gap"] is True
    assert rows["cds_label"]["manual_review_required"] is True
    assert "R83-RICE-EV-CDS" in rows["promoter_slot"]["traceability_ids"]
    assert "R83-RICE-COMP-CDS" in rows["promoter_slot"]["traceability_ids"]
    _assert_plain_data(result)


def test_slot_coverage_matrix_accepts_raw_chain_result() -> None:
    workflow = build_plant_review_workspace_workflow(_workspace_state())

    result = matrix.build_plant_review_slot_coverage_matrix(workflow["chain_result"])

    assert result["source_kind"] == "chain_result"
    assert result["traceability"]["source_schema_version"].startswith("plant_review_workflow_chain")
    assert result["summary"]["slot_count"] >= 10
    assert result["manual_review_required"] is True


def test_slot_coverage_matrix_handles_missing_source_as_manual_review() -> None:
    result = matrix.build_plant_review_slot_coverage_matrix(None)

    assert result["source_kind"] == "malformed"
    assert result["matrix_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["rows"] == []
    assert result["summary"]["slot_count"] == 0
    assert any("missing or malformed" in warning for warning in result["warnings"])


def test_slot_coverage_matrix_preserves_duplicate_or_alias_review_signal() -> None:
    chain = {
        "chain_schema_version": "plant_review_workflow_chain.test",
        "chain_runner_version": "test",
        "component_candidate_match_result": {
            "slot_matches": [
                {
                    "slot_id": "promoter_slot",
                    "slot_label": "Promoter slot",
                    "candidate_components": [
                        {
                            "component_id": "COMP-A",
                            "duplicate_or_alias_flag": True,
                            "provenance_status": "source_recorded",
                        }
                    ],
                    "duplicate_or_alias_flag": True,
                    "manual_review_required": True,
                }
            ]
        },
    }

    result = matrix.build_plant_review_slot_coverage_matrix(chain)
    row = result["rows"][0]

    assert row["slot_id"] == "promoter_slot"
    assert row["component_count"] == 1
    assert row["duplicate_or_alias_review"] is True
    assert row["manual_review_required"] is True
    assert "duplicate_or_alias_review" in row["gap_categories"]


def test_slot_coverage_matrix_copy_keeps_documentation_boundary() -> None:
    source = (ROOT / "services" / "plant_review_slot_coverage_matrix.py").read_text(encoding="utf-8")
    test_source = (ROOT / "tests" / "test_plant_review_slot_coverage_matrix.py").read_text(encoding="utf-8")
    text = f"{source}\n{test_source}".casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text
    assert "documentation-only" in text
    assert "manual review" in text


def test_slot_coverage_matrix_has_no_streamlit_dependency() -> None:
    source = (ROOT / "services" / "plant_review_slot_coverage_matrix.py").read_text(encoding="utf-8")

    assert "import streamlit" not in source
