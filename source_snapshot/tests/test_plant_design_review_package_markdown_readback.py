from __future__ import annotations

from pathlib import Path

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_design_review_package_markdown_readback import (
    MARKDOWN_READBACK_KEYS,
    SECTION_ORDER,
    build_plant_design_review_package_markdown_readback,
)
from services.plant_design_review_package_snapshot import build_plant_design_review_package_snapshot
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

FORBIDDEN_COPY = (
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "wet-lab ready",
    "feasible",
    "yield prediction",
)


def _rice_route_draft() -> dict[str, object]:
    return build_plant_expression_route_draft(
        {
            "target_name": "OsALB markdown readback target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-387",
            "known_component_ids": {"promoter": "SRC-PROMOTER-387"},
            "known_vector_or_backbone": "SRC-BACKBONE-387",
            "evidence_sources": {"SRC-RICE-387": "rice host context source pointer"},
            "notes": "Manual documentation review note.",
        }
    )


def _package_snapshot() -> dict[str, object]:
    draft = _rice_route_draft()
    presenter = present_plant_route_draft(draft)
    candidates = build_plant_component_candidate_match_readback(
        draft,
        [
            {
                "component_id": "COMP-PROMOTER-387",
                "component_name": "Rice promoter candidate record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-PROMOTER-387",
                "source_label": "promoter source record",
                "review_status": "manual review pending",
            }
        ],
    )
    gap_queue = build_plant_route_gap_manual_review_queue(draft, presenter, candidates)
    return build_plant_design_review_package_snapshot(draft, presenter, candidates, gap_queue)


def _readback() -> dict[str, object]:
    return build_plant_design_review_package_markdown_readback(_package_snapshot())


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


def test_normal_package_snapshot_renders_deterministic_markdown_readback() -> None:
    first = _readback()
    second = _readback()

    assert list(first) == list(MARKDOWN_READBACK_KEYS)
    assert first == second
    assert first["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert first["markdown_text"].startswith("# Plant Design Review Package Snapshot")  # type: ignore[union-attr]


def test_empty_snapshot_returns_safe_empty_state() -> None:
    readback = build_plant_design_review_package_markdown_readback()

    assert list(readback) == list(MARKDOWN_READBACK_KEYS)
    assert readback["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert "documentation-only" in readback["markdown_text"].casefold()  # type: ignore[union-attr]
    assert readback["identity_payload"] == {}
    assert readback["identity_md5"] == ""


def test_sections_appear_in_stable_order() -> None:
    readback = _readback()
    text = readback["markdown_text"]

    assert readback["section_order"] == list(SECTION_ORDER)
    expected_headings = [
        "# Plant Design Review Package Snapshot",
        "## Scope",
        "## Route Summary",
        "## Design Intent",
        "## Plant Context",
        "## Construct Slot Plan",
        "## Component Candidate Readback",
        "## Evidence Summary",
        "## Gap Queue",
        "## Manual Review Checklist",
        "## Boundary Notice",
        "## Identity",
    ]
    positions = [text.index(heading) for heading in expected_headings]  # type: ignore[union-attr]
    assert positions == sorted(positions)


def test_identity_payload_and_md5_are_preserved() -> None:
    snapshot = _package_snapshot()
    readback = build_plant_design_review_package_markdown_readback(snapshot)

    assert readback["identity_payload"] == snapshot["identity_payload"]
    assert readback["identity_md5"] == snapshot["identity_md5"]
    assert snapshot["identity_md5"] in readback["markdown_text"]  # type: ignore[operator]


def test_gap_queue_and_manual_review_checklist_are_rendered() -> None:
    readback = _readback()
    text = readback["markdown_text"]

    assert "## Gap Queue" in text  # type: ignore[operator]
    assert "plant-route-gap-" in text  # type: ignore[operator]
    assert "## Manual Review Checklist" in text  # type: ignore[operator]
    assert "manual_review" in text  # type: ignore[operator]


def test_component_candidates_are_manual_review_readback_not_final_selection() -> None:
    readback = _readback()
    text = readback["markdown_text"].casefold()  # type: ignore[union-attr]

    assert "component candidate readback" in text
    assert "manual review" in text
    assert "not final selections" in text
    assert "selected_component" not in text
    assert "final_component" not in text


def test_boundary_notice_is_rendered() -> None:
    readback = _readback()

    assert "documentation-only" in readback["markdown_text"].casefold()  # type: ignore[union-attr]
    assert "blocked output" in readback["blocked_outputs_notice"]["title"].casefold()  # type: ignore[index]


def test_no_unsafe_fields_or_product_claims_appear() -> None:
    readback = _readback()
    text = readback["markdown_text"].casefold()  # type: ignore[union-attr]

    for item in _walk_dicts(readback):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)
    for forbidden in FORBIDDEN_COPY:
        assert forbidden not in text


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(_readback())


def test_no_ui_db_import_export_package_export_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_design_review_package_markdown_readback.py").read_text(encoding="utf-8").casefold()

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
