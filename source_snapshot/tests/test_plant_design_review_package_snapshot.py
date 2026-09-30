from __future__ import annotations

from pathlib import Path

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_design_review_package_snapshot import (
    SNAPSHOT_KEYS,
    build_plant_design_review_package_snapshot,
)
from services.plant_route_draft_presenter import present_plant_route_draft
from services.plant_route_gap_manual_review_queue import build_plant_route_gap_manual_review_queue
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
    "best",
}


def _rice_route_draft() -> dict[str, object]:
    return build_plant_expression_route_draft(
        {
            "target_name": "OsALB package snapshot target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-386",
            "known_component_ids": {
                "promoter": "SRC-PROMOTER-386",
            },
            "known_vector_or_backbone": "SRC-BACKBONE-386",
            "evidence_sources": {
                "SRC-RICE-386": "rice host context source pointer",
                "SRC-CDS-386": "target CDS source pointer",
            },
            "notes": "Manual documentation review note.",
        }
    )


def _candidate_payload(draft: dict[str, object]) -> dict[str, object]:
    return build_plant_component_candidate_match_readback(
        draft,
        [
            {
                "component_id": "COMP-PROMOTER-386",
                "component_name": "Rice promoter candidate record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-PROMOTER-386",
                "source_label": "promoter source record",
                "review_status": "manual review pending",
            }
        ],
    )


def _snapshot(package_metadata: dict[str, object] | None = None) -> dict[str, object]:
    draft = _rice_route_draft()
    presenter = present_plant_route_draft(draft)
    candidates = _candidate_payload(draft)
    gap_queue = build_plant_route_gap_manual_review_queue(draft, presenter, candidates)
    return build_plant_design_review_package_snapshot(
        route_draft=draft,
        route_presenter_payload=presenter,
        candidate_match_payload=candidates,
        gap_queue_payload=gap_queue,
        package_metadata=package_metadata or {"review_batch": "R386"},
    )


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _walk_dicts(value: object) -> list[dict[str, object]]:
    dicts: list[dict[str, object]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            dicts.extend(_walk_dicts(nested))
    return dicts


def test_normal_rice_route_draft_creates_package_sections() -> None:
    snapshot = _snapshot()

    assert list(snapshot) == list(SNAPSHOT_KEYS)
    assert snapshot["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert snapshot["package_status"] == "manual_review_required"
    assert snapshot["package_scope"] == "plant_expression_vector_design_review_snapshot"
    assert [section["section_id"] for section in snapshot["package_sections"]] == [  # type: ignore[index]
        "route_summary",
        "design_intent_section",
        "plant_context_section",
        "construct_slot_plan_section",
        "component_candidate_section",
        "evidence_summary_section",
        "gap_queue_section",
        "manual_review_section",
        "boundary_section",
    ]


def test_empty_input_returns_safe_package_empty_state() -> None:
    snapshot = build_plant_design_review_package_snapshot()

    assert list(snapshot) == list(SNAPSHOT_KEYS)
    assert snapshot["package_status"] == "needs_input"
    assert snapshot["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert snapshot["route_summary"]["route_id"] == ""  # type: ignore[index]
    assert "documentation-only" in snapshot["boundary_section"]["boundary_notice"]["notice"].casefold()  # type: ignore[index]


def test_package_identity_is_deterministic_for_identical_input() -> None:
    first = _snapshot()
    second = _snapshot()

    assert first["package_id"] == second["package_id"]
    assert first["identity_payload"] == second["identity_payload"]
    assert first["identity_md5"] == second["identity_md5"]


def test_identity_md5_changes_when_identity_payload_changes() -> None:
    first = _snapshot({"review_batch": "R386-A"})
    second = _snapshot({"review_batch": "R386-B"})

    assert first["identity_payload"] != second["identity_payload"]
    assert first["identity_md5"] != second["identity_md5"]
    assert first["package_id"] != second["package_id"]


def test_route_summary_and_plant_context_are_preserved() -> None:
    draft = _rice_route_draft()
    snapshot = build_plant_design_review_package_snapshot(route_draft=draft)

    assert snapshot["route_summary"]["route_id"] == draft["route_id"]  # type: ignore[index]
    assert snapshot["route_summary"]["route_name"] == draft["route_name"]  # type: ignore[index]
    assert snapshot["route_summary"]["route_type"] == draft["route_type"]  # type: ignore[index]
    assert snapshot["route_summary"]["plant_context"] == draft["plant_context"]  # type: ignore[index]


def test_construct_slot_plan_section_is_present() -> None:
    snapshot = _snapshot()

    assert snapshot["construct_slot_plan_section"]["construct_slot_rows"]  # type: ignore[index]
    assert snapshot["construct_slot_plan_section"]["section_status"] == "manual_review_required"  # type: ignore[index]


def test_component_candidate_section_does_not_select_final_components() -> None:
    snapshot = _snapshot()
    section = snapshot["component_candidate_section"]

    assert section["slot_candidate_rows"]  # type: ignore[index]
    assert section["selection_status"] == "candidate_readback_no_selection"  # type: ignore[index]
    assert "selected_component" not in str(section).casefold()
    assert "final_component" not in str(section).casefold()


def test_gap_queue_section_preserves_unresolved_and_manual_review_items() -> None:
    snapshot = _snapshot()

    assert snapshot["gap_queue_section"]["queue_items"]  # type: ignore[index]
    assert snapshot["gap_queue_section"]["unresolved_items"]  # type: ignore[index]
    assert snapshot["manual_review_section"]["manual_review_items"]  # type: ignore[index]
    assert snapshot["manual_review_section"]["manual_review_required"] is True  # type: ignore[index]


def test_boundary_section_is_present() -> None:
    snapshot = _snapshot()
    boundary = snapshot["boundary_section"]

    assert "documentation-only" in boundary["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert "blocked output" in boundary["blocked_outputs_notice"]["title"].casefold()  # type: ignore[index]


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(_snapshot())


def test_no_unsafe_fields_are_present_anywhere_in_output() -> None:
    snapshot = _snapshot()

    for item in _walk_dicts(snapshot):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)


def test_no_ui_db_import_export_package_export_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_design_review_package_snapshot.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "package_export_service",
        "expression_wizard",
        "component_library",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
        "qr",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source
