# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_evidence_review_worksheet_presenter as worksheet_presenter
from services import plant_review_handoff_data_adapter as adapter
from services import plant_review_workflow_scenario_fixtures as fixtures
from services import plant_route_construct_traceability_readback as route_construct_readback


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


def _scenario_result(scenario_id: str) -> dict:
    return fixtures.run_plant_review_workflow_scenario_fixture(scenario_id)


def test_coherent_chain_result_converts_to_handoff_payload() -> None:
    chain = _scenario_result(fixtures.PLANT_TRANSIENT_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(
        chain,
        {"reviewer": "local-review"},
    )

    assert payload["handoff_schema_version"] == adapter.HANDOFF_SCHEMA_VERSION
    assert payload["handoff_status"] == "manual_review_required"
    assert payload["package_header"]["route_id"] == "plant_transient_expression_review"
    assert payload["package_header"]["package_id"]
    assert payload["manual_review_required"] is True
    assert payload["required_review_items"]
    assert payload["source_traceability"]["source_kind"] == "chain_result"
    assert payload["source_traceability"]["handoff_context"]["reviewer"] == "local-review"
    _assert_plain_data(payload)


def test_missing_evidence_flows_to_missing_information_items() -> None:
    chain = _scenario_result(fixtures.GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)

    categories = {item["category"] for item in payload["missing_information_items"]}
    assert "evidence_gap" in categories
    assert "required_slot_gap" in categories
    assert len(payload["missing_information_items"]) > 0


def test_component_provenance_gap_remains_required_review_item() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)

    provenance_items = [
        item for item in payload["required_review_items"] if item["category"] == "provenance_gap"
    ]
    assert provenance_items
    assert any("R77-RICE-COMP-PROMOTER-GAP" in item["component_ids"] for item in provenance_items)


def test_unsupported_non_plant_scope_returns_blocked_handoff() -> None:
    chain = _scenario_result(fixtures.UNSUPPORTED_NON_PLANT_SCOPE)
    payload = adapter.build_plant_review_handoff_payload(chain)

    assert payload["handoff_status"] == "blocked"
    assert payload["manual_review_required"] is True
    assert payload["reviewer_summary"]["blocked"] is True
    assert payload["package_header"]["package_status"] == "blocked"
    assert any(item["category"] == "unsupported_scope" for item in payload["required_review_items"])


def test_malformed_input_returns_safe_empty_manual_review_handoff() -> None:
    payload = adapter.build_plant_review_handoff_payload(["not", "a", "mapping"])  # type: ignore[arg-type]

    assert payload["handoff_status"] == "manual_review_required"
    assert payload["manual_review_required"] is True
    assert payload["package_header"] == {}
    assert payload["required_review_items"] == []
    assert payload["warnings"]
    assert payload["source_traceability"]["source_kind"] == "malformed"


def test_blocked_output_categories_preserved_only_as_boundaries() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)

    assert "protocol" in payload["blocked_output_boundaries"]
    assert "optimized_sequence" in payload["blocked_output_boundaries"]
    assert "blocked_output_boundaries" in payload
    assert "blocked_output_categories" not in str(payload["reviewer_summary"])


def test_no_recommendation_or_final_choice_fields_in_handoff_payload() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)

    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        _assert_no_field_fragment(payload, fragment)


def test_readback_presenter_input_converts_without_full_chain() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    presenter = chain["readback_presenter"]
    payload = adapter.build_plant_review_handoff_payload(presenter)

    assert payload["source_traceability"]["source_kind"] == "readback_presenter"
    assert payload["package_header"]["route_id"] == "rice_seed_protein_expression"
    assert payload["required_review_items"]
    assert payload["blocked_output_boundaries"]


def test_traceability_preserves_evidence_component_and_source_items() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)

    evidence_ids = {item["evidence_id"] for item in payload["evidence_traceability_items"]}
    component_ids = {item["component_id"] for item in payload["component_traceability_items"]}
    assert "R77-RICE-EV-CDS" in evidence_ids
    assert "R77-RICE-COMP-CDS" in component_ids
    assert payload["source_traceability"]["readback_traceability"]["route_ids"]


def test_handoff_mounts_r118_plant_evidence_review_worksheet_payload() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)
    worksheet = payload["plant_evidence_review_worksheet"]

    assert worksheet["worksheet_schema_version"] == worksheet_presenter.WORKSHEET_SCHEMA_VERSION
    assert worksheet["worksheet_status"] == worksheet_presenter.SUPPORTED_WORKSHEET_STATUS
    assert worksheet["read_only"] is True
    assert worksheet["manual_review_required"] is True
    assert worksheet["worksheet_context"]["mount_batch"] == adapter.WORKSHEET_HANDOFF_READBACK_BATCH
    assert worksheet["worksheet_context"]["mount_surface"] == "plant_review_handoff_preview"
    assert worksheet["summary"]["evidence_row_count"] > 0
    assert worksheet["summary"]["component_slot_row_count"] > 0
    assert worksheet["summary"]["total_evidence_rows"] == worksheet["summary"]["evidence_row_count"]
    assert worksheet["summary"]["linked_component_slot_count"] > 0
    assert worksheet["summary"]["manual_review_required_count"] > 0
    assert worksheet["summary"]["overall_review_state"] == "requires manual review"
    assert worksheet["summary"]["followup_queue_count"] > 0
    assert worksheet["evidence_review_section"]["rows"]
    assert worksheet["component_slot_linkage_section"]["rows"]
    assert worksheet["followup_queue_section"]["rows"]
    assert any(row["linked_evidence_ids"] for row in worksheet["component_slot_linkage_section"]["rows"])


def test_handoff_mounts_r128_route_construct_traceability_readback() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)
    readback = payload["route_construct_traceability_readback"]
    rows = readback["traceability_section"]["rows"]

    assert readback["traceability_schema_version"] == route_construct_readback.TRACEABILITY_SCHEMA_VERSION
    assert readback["traceability_status"] == route_construct_readback.TRACEABILITY_STATUS_READY
    assert readback["read_only"] is True
    assert readback["manual_review_required"] is True
    assert readback["reuse_source"] == "plant_evidence_review_worksheet_presenter"
    assert readback["readback_context"]["mount_batch"] == adapter.ROUTE_CONSTRUCT_TRACEABILITY_MOUNT_BATCH
    assert readback["readback_context"]["mount_surface"] == "plant_review_handoff_preview"
    assert readback["summary"]["trace_row_count"] == len(rows)
    assert readback["summary"]["construct_slot_count"] > 0
    assert readback["summary"]["construct_slot_link_count"] > 0
    assert rows


def test_route_construct_evidence_component_and_construct_links_survive_handoff_mount() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    readback = adapter.build_plant_review_handoff_payload(chain)["route_construct_traceability_readback"]
    rows = readback["traceability_section"]["rows"]

    evidence_ids = {row["linked_evidence_id"] for row in rows}
    component_slots = {row["linked_component_slot"] for row in rows}
    construct_slots = {row["linked_construct_slot"] for row in rows}

    assert "R77-RICE-EV-CDS" in evidence_ids
    assert any("R77-RICE-COMP-CDS" in row["linked_component"] for row in rows)
    assert any("cds_label" in slot or "coding_sequence_slot" in slot for slot in component_slots)
    assert "cds_payload_gene_or_enzyme" in construct_slots
    assert "promoter" in construct_slots


def test_route_construct_missing_provenance_followup_reasons_remain_visible() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    readback = adapter.build_plant_review_handoff_payload(chain)["route_construct_traceability_readback"]
    text = str(readback)

    assert "provenance_gap" in text
    assert "missing_provenance_or_source" in text
    assert "manual_review_required" in text
    assert any(row["manual_review_note"] for row in readback["traceability_section"]["rows"])


def test_route_construct_empty_payload_stays_safe_in_handoff_mount() -> None:
    payload = adapter.build_plant_review_handoff_payload(["not", "a", "mapping"])  # type: ignore[arg-type]
    readback = payload["route_construct_traceability_readback"]

    assert readback["traceability_status"] == route_construct_readback.TRACEABILITY_STATUS_EMPTY
    assert readback["read_only"] is True
    assert readback["manual_review_required"] is True
    assert readback["summary"]["empty_input"] is True
    assert readback["traceability_section"]["rows"] == []
    assert readback["construct_slot_section"]["rows"] == []
    assert readback["warnings"] == [
        "traceability input warning: no readable plant route, evidence, component, or construct payload was provided"
    ]


def test_handoff_readback_includes_worksheet_summary_and_followup_status() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)
    worksheet = payload["plant_evidence_review_worksheet"]
    readback = payload["evidence_worksheet_handoff_readback"]

    assert readback["readback_batch"] == adapter.WORKSHEET_HANDOFF_READBACK_BATCH
    assert readback["read_only"] is True
    assert readback["reuse_source"] == "plant_evidence_review_worksheet_presenter"
    assert readback["worksheet_schema_version"] == worksheet_presenter.WORKSHEET_SCHEMA_VERSION
    assert readback["summary"]["overall_review_state"] == worksheet["summary"]["overall_review_state"]
    assert readback["summary"]["total_evidence_rows"] == worksheet["summary"]["total_evidence_rows"]
    assert readback["summary"]["followup_queue_count"] == worksheet["summary"]["followup_queue_count"]
    assert readback["followup_queue_status"]["total_count"] == worksheet["summary"]["followup_queue_count"]
    assert readback["followup_queue_status"]["filter_key"] == "followup_type"
    assert readback["followup_queue_status"]["group_by_type"] is True
    assert readback["followup_queue_status"]["group_counts"]
    assert "missing_provenance" in readback["followup_queue_status"]["followup_type_options"]


def test_missing_provenance_and_manual_review_counts_survive_handoff_readback() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    readback = adapter.build_plant_review_handoff_payload(chain)["evidence_worksheet_handoff_readback"]

    assert readback["summary"]["missing_source_or_provenance_count"] > 0
    assert readback["summary"]["manual_review_required_count"] > 0
    assert readback["summary"]["followup_queue_type_counts"]["manual_review_required"] > 0
    assert readback["summary"]["followup_queue_type_counts"]["missing_provenance"] > 0


def test_handoff_worksheet_preserves_manual_review_gap_and_boundary_categories() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)
    worksheet = payload["plant_evidence_review_worksheet"]
    manual_rows = worksheet["manual_review_section"]["rows"]
    blocked_categories = worksheet["boundary_section"]["blocked_output_categories"]

    assert any(row["category"] == "provenance_gap" for row in manual_rows)
    assert any("provenance" in row["gap_reason"] for row in manual_rows)
    assert any("manual_review" in row["review_status"] for row in worksheet["evidence_review_section"]["rows"])
    assert "protocol" in blocked_categories
    assert "yield_prediction" in blocked_categories
    assert worksheet["summary"]["blocked_boundary_category_count"] == len(blocked_categories)
    assert "blocked_output_categories" not in str(worksheet["summary"])


def test_handoff_worksheet_empty_input_stays_safe_manual_review_state() -> None:
    payload = adapter.build_plant_review_handoff_payload(["not", "a", "mapping"])  # type: ignore[arg-type]
    worksheet = payload["plant_evidence_review_worksheet"]
    readback = payload["evidence_worksheet_handoff_readback"]

    assert worksheet["worksheet_status"] == worksheet_presenter.EMPTY_WORKSHEET_STATUS
    assert worksheet["summary"]["empty_input"] is True
    assert worksheet["summary"]["overall_review_state"] == "evidence incomplete"
    assert worksheet["manual_review_required"] is True
    assert worksheet["evidence_review_section"]["rows"] == []
    assert worksheet["component_slot_linkage_section"]["rows"] == []
    assert worksheet["followup_queue_section"]["rows"] == []
    assert worksheet["warnings"] == ["worksheet input warning: no readable plant review evidence payload was provided"]
    assert readback["worksheet_status"] == worksheet_presenter.EMPTY_WORKSHEET_STATUS
    assert readback["summary"]["empty_input"] is True
    assert readback["summary"]["followup_queue_count"] == 0
    assert readback["followup_queue_status"]["total_count"] == 0
    assert readback["followup_queue_status"]["followup_type_options"] == []
    assert readback["warnings"] == ["worksheet input warning: no readable plant review evidence payload was provided"]


def test_handoff_adapter_reuses_r118_presenter_without_local_worksheet_row_shaping() -> None:
    source_text = Path("services/plant_review_handoff_data_adapter.py").read_text(
        encoding="utf-8"
    )

    assert "build_plant_evidence_review_worksheet_payload" in source_text
    assert "build_followup_queue_filter_view" in source_text
    assert "EVIDENCE_REVIEW_COLUMNS" not in source_text
    assert "COMPONENT_SLOT_COLUMNS" not in source_text
    assert "MANUAL_REVIEW_COLUMNS" not in source_text


def test_handoff_adapter_reuses_r128_presenter_without_local_trace_row_shaping() -> None:
    source_text = Path("services/plant_review_handoff_data_adapter.py").read_text(encoding="utf-8")

    assert "build_plant_route_construct_traceability_readback" in source_text
    assert "TRACEABILITY_ROW_KEYS" not in source_text
    assert "trace_id" not in source_text


def test_handoff_readback_boundary_labels_remain_categories_only() -> None:
    chain = _scenario_result(fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW)
    payload = adapter.build_plant_review_handoff_payload(chain)
    readback = payload["evidence_worksheet_handoff_readback"]

    assert "protocol" in readback["blocked_output_boundary_categories"]
    assert "yield_prediction" in readback["blocked_output_boundary_categories"]
    assert readback["summary"]["blocked_boundary_category_count"] == len(
        readback["blocked_output_boundary_categories"]
    )
    assert "protocol" not in str(readback["summary"])
    assert "yield_prediction" not in str(readback["followup_queue_status"])


def test_adapter_source_and_output_keep_copy_safety_boundaries() -> None:
    payload_text = str(
        adapter.build_plant_review_handoff_payload(
            _scenario_result(fixtures.GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW)
        )
    ).casefold()
    source_text = Path("services/plant_review_handoff_data_adapter.py").read_text(
        encoding="utf-8"
    ).casefold()
    test_text = Path("tests/test_plant_review_handoff_data_adapter.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in payload_text
        assert phrase not in source_text
        assert phrase not in test_text
