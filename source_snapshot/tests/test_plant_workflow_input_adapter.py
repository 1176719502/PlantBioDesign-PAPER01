# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_workflow_input_adapter as adapter


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

FORBIDDEN_FIELD_FRAGMENTS = (
    "final_component",
    "selected_component",
    "best_component",
    "recommended_component",
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


def _assert_no_field_fragment(value: object, fragment: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert fragment not in key.casefold()
            _assert_no_field_fragment(nested, fragment)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_field_fragment(nested, fragment)


def _rice_payload(*, include_component_provenance: bool = False) -> dict[str, Any]:
    component = {
        "component_id": "R81-RICE-COMP-CDS",
        "component_name": "Rice albumin-like CDS source component record",
        "component_type": "cds_source",
        "design_slot_tags": ["cds_label", "coding_sequence_slot"],
        "plant_context": "Oryza sativa rice seed",
    }
    if include_component_provenance:
        component.update(
            {
                "matched_evidence_ids": ["R81-RICE-EV-CDS"],
                "source_label": "local CDS source record",
                "source_reference": "R81-RICE-EV-CDS",
                "provenance_note": "Local source metadata.",
            }
        )
    return {
        "project_id": "R81-RICE-PROJECT",
        "project_name": "Rice albumin review workspace",
        "design_goal": "Document a rice seed albumin-like plant expression vector review route.",
        "target_product": "rice seed albumin-like protein",
        "target_gene": "rice albumin-like CDS",
        "cds_source": "rice albumin-like CDS source note",
        "host_plant": "Oryza sativa rice",
        "expression_context": "rice seed plant expression vector context",
        "route_hint": "rice seed protein expression review",
        "construct_slots": {"promoter": "rice seed promoter source note"},
        "component_records": [component],
        "evidence_records": [
            {
                "id": "R81-RICE-EV-CDS",
                "paper_title": "Rice albumin-like protein identity source",
                "summary": "Local source note for a rice seed albumin-like protein review context.",
                "tags": "rice, seed, albumin, plant",
                "provenance_note": "Local source metadata.",
            }
        ],
        "notes": "Local documentation-only review note.",
        "user_context": {"reviewer": "local-review"},
    }


def test_rice_albumin_like_payload_creates_plant_user_intent_and_preserves_records() -> None:
    result = adapter.prepare_plant_review_workflow_input(_rice_payload())

    assert result["adapter_schema_version"] == adapter.ADAPTER_SCHEMA_VERSION
    assert result["user_intent"]["target_name"] == "rice seed albumin-like protein"
    assert result["user_intent"]["plant_host"] == "Oryza sativa rice"
    assert result["user_intent"]["known_component_ids"]["promoter"] == "rice seed promoter source note"
    assert result["evidence_records"][0]["id"] == "R81-RICE-EV-CDS"
    assert result["component_records"][0]["component_id"] == "R81-RICE-COMP-CDS"
    assert result["manual_review_required"] is True
    assert any("source/provenance review" in warning for warning in result["warnings"])
    _assert_plain_data(result)


def test_generic_plant_expression_vector_payload_can_be_ready_for_chain() -> None:
    payload = {
        "project_id": "R81-GENERIC",
        "project_name": "Generic plant expression vector review",
        "design_goal": "Document a plant expression vector review input.",
        "target_product": "reporter protein",
        "host_plant": "plant",
        "expression_context": "general plant expression vector context",
        "component_records": [
            {
                "component_id": "R81-GENERIC-COMP-VECTOR",
                "component_name": "Plant vector source record",
                "source_reference": "R81-GENERIC-EV-VECTOR",
            }
        ],
        "evidence_records": [{"id": "R81-GENERIC-EV-VECTOR", "paper_title": "Plant vector source note"}],
    }

    result = adapter.prepare_plant_review_workflow_input(payload)

    assert result["adapter_status"] == adapter.STATUS_READY_FOR_CHAIN
    assert result["manual_review_required"] is False
    assert result["chain_options"]["context"]["adapter_context"]["documentation_only"] is True


def test_generic_plant_expression_vector_payload_with_missing_fields_requires_manual_review() -> None:
    result = adapter.prepare_plant_review_workflow_input(
        {
            "project_id": "R81-GENERIC-MISSING",
            "design_goal": "Document a plant expression vector review input.",
            "host_plant": "plant",
            "target_product": "reporter protein",
            "evidence_records": [],
            "component_records": [],
        }
    )

    assert result["adapter_status"] == adapter.STATUS_MANUAL_REVIEW_REQUIRED
    assert result["manual_review_required"] is True
    assert "evidence_records" in result["missing_input_fields"]
    assert "component_records" in result["missing_input_fields"]


def test_empty_payload_returns_empty_or_invalid_input() -> None:
    result = adapter.prepare_plant_review_workflow_input({})

    assert result["adapter_status"] == adapter.STATUS_EMPTY_OR_INVALID_INPUT
    assert result["manual_review_required"] is True
    assert result["missing_input_fields"] == [
        "design_goal",
        "host_plant_or_plant_context",
        "target_gene_or_target_product",
        "evidence_records",
        "component_records",
    ]


def test_non_plant_host_payload_blocks_active_plant_design_claim() -> None:
    result = adapter.prepare_plant_review_workflow_input(
        {
            "project_id": "R81-NON-PLANT",
            "design_goal": "Document a non-plant expression context.",
            "target_gene": "GFP",
            "host_plant": "E. coli",
            "component_records": [{"component_id": "NONPLANT-COMP", "source_reference": "NONPLANT-EV"}],
            "evidence_records": [{"id": "NONPLANT-EV"}],
        }
    )

    assert result["adapter_status"] == adapter.STATUS_UNSUPPORTED_OR_MANUAL_REVIEW
    assert result["manual_review_required"] is True
    assert result["user_intent"]["active_plant_design_claim"] is False
    assert result["traceability"]["scope_status"] == "unsupported_non_plant_scope"


def test_mixed_malformed_component_and_evidence_records_preserve_valid_records_and_warn() -> None:
    result = adapter.prepare_plant_review_workflow_input(
        {
            "design_goal": "Document a plant expression vector review input.",
            "target_gene": "plant reporter gene",
            "host_plant": "Nicotiana benthamiana",
            "component_records": [
                {"component_id": "R81-COMP-VALID", "source_reference": "R81-EV-VALID"},
                object(),
                "loose component text",
            ],
            "evidence_records": [
                {"id": "R81-EV-VALID", "paper_title": "Plant source note"},
                object(),
                "loose evidence text",
            ],
        }
    )

    assert [record["component_id"] for record in result["component_records"]] == ["R81-COMP-VALID"]
    assert [record["id"] for record in result["evidence_records"]] == ["R81-EV-VALID"]
    assert any("component warning: malformed records" in warning for warning in result["warnings"])
    assert any("evidence warning: malformed records" in warning for warning in result["warnings"])
    assert result["manual_review_required"] is True


def test_traceability_preserves_project_evidence_and_component_ids() -> None:
    result = adapter.prepare_plant_review_workflow_input(_rice_payload(include_component_provenance=True))

    assert result["traceability"]["project_id"] == "R81-RICE-PROJECT"
    assert result["traceability"]["project_name"] == "Rice albumin review workspace"
    assert "design_goal" in result["traceability"]["source_field_names_used"]
    assert result["traceability"]["evidence_record_ids"] == ["R81-RICE-EV-CDS"]
    assert result["traceability"]["component_record_ids"] == ["R81-RICE-COMP-CDS"]


def test_adapter_stays_upstream_of_r76_and_does_not_import_chain_runner(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def _block_chain_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "services.plant_review_workflow_chain_runner":
            raise AssertionError("R81 adapter must prepare input without running R76")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_chain_import)

    result = adapter.prepare_plant_review_workflow_input(_rice_payload(include_component_provenance=True))
    assert result["adapter_status"] == adapter.STATUS_READY_FOR_CHAIN


def test_adapter_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(adapter.prepare_plant_review_workflow_input(_rice_payload())).casefold()
    source_text = Path("services/plant_workflow_input_adapter.py").read_text(encoding="utf-8").casefold()
    test_text = Path("tests/test_plant_workflow_input_adapter.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text
        assert phrase not in test_text

    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        _assert_no_field_fragment(adapter.prepare_plant_review_workflow_input(_rice_payload()), fragment)

    assert "documentation_only" in result_text
