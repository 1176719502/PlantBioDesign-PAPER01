# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_review_workspace_workflow_orchestrator as orchestrator


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


def _workspace_state(*, host: str = "Oryza sativa rice") -> dict[str, Any]:
    return {
        "workspace_id": "R83-RICE-WORKSPACE",
        "workspace_name": "Rice albumin workspace state",
        "goal": "Document a rice albumin-like plant expression vector review route.",
        "target_name": "rice seed albumin-like protein",
        "gene_name": "rice albumin-like CDS",
        "plant_host": host,
        "plant_context": "rice seed plant expression vector context",
        "route": "rice seed protein expression review",
        "slots": {"promoter": "rice seed promoter source note"},
        "component_library": [
            {
                "asset_id": "R83-RICE-COMP-CDS",
                "component_name": "Rice albumin-like CDS source component record",
                "component_type": "cds_source",
                "source_reference": "R83-RICE-EV-CDS",
                "matched_evidence_ids": ["R83-RICE-EV-CDS"],
            }
        ],
        "sources": [
            {
                "source_id": "R83-RICE-EV-CDS",
                "paper_title": "Rice albumin-like protein identity source",
                "summary": "Local source note for a rice seed albumin-like protein review context.",
                "tags": "rice, seed, albumin, plant",
            }
        ],
    }


def test_workspace_workflow_runs_r82_r81_r76_r75_and_r79_path() -> None:
    result = orchestrator.build_plant_review_workspace_workflow(
        _workspace_state(),
        {"handoff_context": {"review_surface": "workspace"}},
    )

    assert result["workspace_workflow_schema_version"] == orchestrator.WORKSPACE_WORKFLOW_SCHEMA_VERSION
    assert result["project_payload"]["project_id"] == "R83-RICE-WORKSPACE"
    assert result["adapter_input"]["traceability"]["project_id"] == "R83-RICE-WORKSPACE"
    assert result["chain_result"]["chain_schema_version"].startswith("plant_review_workflow_chain")
    assert result["presenter_sections"]["package_header"]["package_id"]
    assert result["handoff_preview_payload"]["handoff_schema_version"].startswith("plant_review_handoff_data_adapter")
    assert result["handoff_preview_payload"]["plant_evidence_review_worksheet"]["worksheet_status"] in {
        "plant_evidence_review_worksheet",
        "empty_manual_review_required",
    }
    assert result["traceability"]["upstream_statuses"]["extractor"] == "ready_for_adapter"
    assert result["traceability"]["upstream_statuses"]["adapter"] == "ready_for_chain"
    assert result["traceability"]["upstream_statuses"]["handoff"] in {"manual_review_required", "review_ready"}
    assert result["handoff_preview_payload"]["source_traceability"]["handoff_context"] == {
        "review_surface": "workspace"
    }
    _assert_plain_data(result)


def test_empty_workspace_state_preserves_safe_partial_results() -> None:
    result = orchestrator.build_plant_review_workspace_workflow(None)

    assert result["workflow_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["blocked"] is False
    assert result["project_payload"]["workspace_extractor_context"]["documentation_only"] is True
    assert result["adapter_input"]["adapter_status"] == "manual_review_required"
    assert result["chain_result"]["chain_schema_version"].startswith("plant_review_workflow_chain")
    assert result["presenter_sections"]["package_header"]
    assert result["handoff_preview_payload"]["manual_review_required"] is True
    assert any("missing or malformed" in warning for warning in result["warnings"])


def test_unsupported_non_plant_workspace_state_blocks_without_losing_handoff_preview() -> None:
    result = orchestrator.build_plant_review_workspace_workflow(_workspace_state(host="E. coli"))

    assert result["workflow_status"] == "blocked"
    assert result["blocked"] is True
    assert result["manual_review_required"] is True
    assert result["adapter_input"]["adapter_status"] == "unsupported_or_manual_review"
    assert result["adapter_input"]["user_intent"]["active_plant_design_claim"] is False
    assert result["handoff_preview_payload"]["handoff_status"] == "blocked"
    assert result["traceability"]["upstream_statuses"]["adapter"] == "unsupported_or_manual_review"


def test_workspace_workflow_preserves_traceability_across_sources() -> None:
    result = orchestrator.build_plant_review_workspace_workflow(_workspace_state())

    extractor_traceability = result["traceability"]["extractor_traceability"]
    adapter_traceability = result["traceability"]["adapter_traceability"]
    chain_traceability = result["traceability"]["chain_traceability"]
    handoff_traceability = result["traceability"]["handoff_source_traceability"]

    assert extractor_traceability["source_keys_used"] == [
        "workspace_id",
        "workspace_name",
        "goal",
        "target_name",
        "gene_name",
        "plant_host",
        "plant_context",
        "route",
        "slots",
        "sources",
        "component_library",
    ]
    assert adapter_traceability["evidence_record_ids"] == ["R83-RICE-EV-CDS"]
    assert adapter_traceability["component_record_ids"] == ["R83-RICE-COMP-CDS"]
    assert chain_traceability["input_summary"]["evidence_record_count"] == 1
    assert handoff_traceability["source_kind"] == "chain_result"


def test_workspace_workflow_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(orchestrator.build_plant_review_workspace_workflow(_workspace_state())).casefold()
    source_text = Path("services/plant_review_workspace_workflow_orchestrator.py").read_text(encoding="utf-8").casefold()
    test_text = Path("tests/test_plant_review_workspace_workflow_orchestrator.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text
        assert phrase not in test_text

    assert "documentation_only" in result_text
