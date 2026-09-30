# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_workspace_state_input_extractor as extractor
from services.plant_workflow_input_adapter import prepare_plant_review_workflow_input


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


def _workspace_state() -> dict[str, Any]:
    return {
        "workspace_id": "R82-RICE-WORKSPACE",
        "workspace_name": "Rice albumin workspace state",
        "goal": "Document a rice albumin-like plant expression vector review route.",
        "target_name": "rice seed albumin-like protein",
        "gene_name": "rice albumin-like CDS",
        "plant_host": "Oryza sativa rice",
        "plant_context": "rice seed plant expression vector context",
        "route": "rice seed protein expression review",
        "slots": {"promoter": "rice seed promoter source note"},
        "component_library": [
            {
                "asset_id": "R82-RICE-COMP-CDS",
                "component_name": "Rice albumin-like CDS source component record",
                "component_type": "cds_source",
                "source_reference": "R82-RICE-EV-CDS",
            }
        ],
        "sources": [
            {
                "source_id": "R82-RICE-EV-CDS",
                "paper_title": "Rice albumin-like protein identity source",
                "summary": "Local source note for a rice seed albumin-like protein review context.",
            }
        ],
    }


def test_extracts_project_like_workspace_state_into_r81_payload_shape() -> None:
    result = extractor.extract_plant_workflow_project_payload(_workspace_state(), {"caller": "test"})

    assert result["extractor_schema_version"] == extractor.EXTRACTOR_SCHEMA_VERSION
    assert result["extractor_status"] == "ready_for_adapter"
    payload = result["project_payload"]
    assert payload["project_id"] == "R82-RICE-WORKSPACE"
    assert payload["project_name"] == "Rice albumin workspace state"
    assert payload["design_goal"].startswith("Document a rice albumin-like")
    assert payload["target_product"] == "rice seed albumin-like protein"
    assert payload["target_gene"] == "rice albumin-like CDS"
    assert payload["host_plant"] == "Oryza sativa rice"
    assert payload["expression_context"] == "rice seed plant expression vector context"
    assert payload["construct_slots"]["promoter"] == "rice seed promoter source note"
    assert payload["evidence_records"][0]["id"] == "R82-RICE-EV-CDS"
    assert payload["evidence_records"][0]["workspace_source_key"] == "sources"
    assert payload["component_records"][0]["component_id"] == "R82-RICE-COMP-CDS"
    assert payload["component_records"][0]["workspace_source_key"] == "component_library"
    assert result["traceability"]["project_source_key_map"]["project_id"] == "workspace_id"
    assert result["traceability"]["evidence_source_keys_used"] == ["sources"]
    assert result["traceability"]["component_source_keys_used"] == ["component_library"]
    assert result["traceability"]["option_keys"] == ["caller"]
    _assert_plain_data(result)


def test_extracted_payload_can_be_consumed_by_r81_adapter_without_running_r76() -> None:
    extracted = extractor.extract_plant_workflow_project_payload(_workspace_state())
    adapted = prepare_plant_review_workflow_input(extracted["project_payload"])

    assert adapted["user_intent"]["target_name"] == "rice seed albumin-like protein"
    assert adapted["traceability"]["project_id"] == "R82-RICE-WORKSPACE"
    assert adapted["traceability"]["evidence_record_ids"] == ["R82-RICE-EV-CDS"]
    assert adapted["traceability"]["component_record_ids"] == ["R82-RICE-COMP-CDS"]
    assert adapted["chain_options"]["context"]["adapter_context"]["documentation_only"] is True


def test_list_workspace_state_collects_component_like_records_and_requires_manual_review() -> None:
    result = extractor.extract_plant_workflow_project_payload(
        [
            {"component_id": "R82-LIST-COMP", "component_name": "Plant reporter component source"},
            "loose malformed component",
        ]
    )

    assert result["extractor_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["project_payload"]["component_records"][0]["component_id"] == "R82-LIST-COMP"
    assert "design_goal" in result["missing_input_fields"]
    assert any("malformed list entries" in warning for warning in result["warnings"])
    assert result["traceability"]["workspace_source_kind"] == "list"


def test_missing_or_malformed_state_returns_safe_empty_manual_review_payload() -> None:
    result = extractor.extract_plant_workflow_project_payload(None)

    assert result["extractor_status"] == "empty_or_invalid_workspace_state"
    assert result["manual_review_required"] is True
    assert result["project_payload"]["workspace_extractor_context"]["documentation_only"] is True
    assert result["missing_input_fields"] == [
        "design_goal",
        "host_plant_or_plant_context",
        "target_gene_or_target_product",
        "evidence_records",
        "component_records",
    ]
    assert any("missing or malformed" in warning for warning in result["warnings"])


def test_source_key_traceability_preserves_multiple_workspace_collections() -> None:
    state = _workspace_state()
    state["evidence_records"] = [{"id": "R82-RICE-EV-EXTRA", "title": "Extra local source"}]
    state["components"] = [{"component_id": "R82-RICE-COMP-EXTRA", "source_label": "local component source"}]

    result = extractor.extract_plant_workflow_project_payload(state)

    assert result["traceability"]["evidence_source_keys_used"] == ["evidence_records", "sources"]
    assert result["traceability"]["component_source_keys_used"] == ["components", "component_library"]
    assert [record["id"] for record in result["project_payload"]["evidence_records"]] == [
        "R82-RICE-EV-EXTRA",
        "R82-RICE-EV-CDS",
    ]
    assert [record["component_id"] for record in result["project_payload"]["component_records"]] == [
        "R82-RICE-COMP-EXTRA",
        "R82-RICE-COMP-CDS",
    ]


def test_extractor_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(extractor.extract_plant_workflow_project_payload(_workspace_state())).casefold()
    source_text = Path("services/plant_workspace_state_input_extractor.py").read_text(encoding="utf-8").casefold()
    test_text = Path("tests/test_plant_workspace_state_input_extractor.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text
        assert phrase not in test_text

    assert "documentation_only" in result_text
