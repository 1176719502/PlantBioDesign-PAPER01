# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_construct_draft_readback_adapter as readback_service
from services import plant_construct_task_draft_builder as draft_service
from services import plant_goal_route_generator as route_service
from services import plant_route_construct_task_bridge as bridge_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("best ", "route"),
    _term("correct ", "route"),
    _term("valid", "ated"),
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("proto", "col"),
    _term("opti", "mized"),
    _term("yield ", "pre", "diction"),
    _term("expression ", "pre", "diction"),
    _term("guaranteed ", "expression"),
    _term("experiment", "-ready"),
)


def _allowed_route(**overrides: object) -> dict[str, object]:
    route: dict[str, object] = {
        "plant_goal": "Plant protein expression review",
        "matched_goal_type_id": "plant_molecular_farming_protein_expression",
        "route_generation_status": route_service.ROUTE_GENERATION_ALLOWED,
        "manual_review_required": True,
        "candidate_route": {
            "route_id": "protein-route-candidate",
            "route_framing": "case-supported option",
            "supporting_source_ids": ["SRC-PROTEIN-001"],
            "required_component_slots": [
                "plant_context",
                "target_product",
                "promoter",
                "terminator",
                "marker",
                "vector",
            ],
            "slot_source_ids": {
                "plant_species": ["SRC-PLANT-001"],
                "cds": ["SRC-CDS-001"],
                "promoter": ["SRC-PROMOTER-001"],
                "terminator": ["SRC-TERM-001"],
                "marker": ["SRC-MARKER-001"],
                "vector": ["SRC-VECTOR-001"],
            },
            "missing_fields": [],
            "manual_review_required": True,
        },
    }
    route.update(overrides)
    return route


def _bridge_task_result(route: dict[str, object] | None = None) -> dict[str, object]:
    result = bridge_service.build_plant_construct_task_requirements(route or _allowed_route())
    result["goal_type"] = "plant_molecular_farming_protein_expression"
    result["route_type"] = "case-supported option"
    return result


def _draft_from_task_result(task_result: dict[str, object] | None = None) -> dict[str, object]:
    return draft_service.build_plant_construct_task_draft(task_result or _bridge_task_result())


def _slot_map(readback: dict[str, object]) -> dict[str, dict[str, object]]:
    return {slot["slot_name"]: slot for slot in readback["slot_rows"]}  # type: ignore[index]


def test_basic_r330_draft_readback_includes_core_fields_and_slots() -> None:
    readback = readback_service.build_plant_construct_draft_readback(_draft_from_task_result())
    by_slot = _slot_map(readback)

    assert readback["readback_status"] == readback_service.READBACK_STATUS_READY
    assert readback["draft_id"] == "construct-draft-protein-route-candidate"
    assert readback["draft_status"] == draft_service.DRAFT_STATUS_NEEDS_MANUAL_REVIEW
    assert readback["manual_review_required"] is True
    assert readback["route_source_label"] == "case-supported option"
    assert readback["plant_host_or_context"]
    assert readback["goal_type"] == "plant_molecular_farming_protein_expression"
    assert readback["route_type"] == "case-supported option"
    assert {
        "promoter",
        "cds_payload_gene_or_enzyme",
        "terminator",
        "selectable_marker",
        "vector_backbone",
    } <= set(by_slot)


def test_missing_fields_preserve_reason_and_safe_status_text() -> None:
    task_result = _bridge_task_result()
    tasks = []
    for task in task_result["construct_tasks"]:  # type: ignore[index]
        if task["slot"] == "promoter_need":
            tasks.append(
                {
                    **task,
                    "evidence_source_ids": [],
                    "missing_source": True,
                    "missing_reason": "promoter source evidence not provided",
                }
            )
        elif task["slot"] == "vector_backbone_need":
            tasks.append(
                {
                    **task,
                    "evidence_source_ids": ["SRC-VECTOR-001"],
                    "status": "manual review required",
                    "missing_source": False,
                }
            )
        else:
            tasks.append(task)
    task_result["construct_tasks"] = tasks

    readback = readback_service.build_plant_construct_draft_readback(_draft_from_task_result(task_result))
    by_slot = _slot_map(readback)

    assert readback["needs_source_count"] == 1
    assert readback["needs_confirmation_count"] >= 1
    assert readback["missing_slot_count"] == 0
    assert by_slot["promoter"]["missing_reason"] == "promoter source evidence not provided"
    assert by_slot["promoter"]["safe_status_text"] == "missing source; manual review required"
    assert by_slot["vector_backbone"]["safe_status_text"] == "needs confirmation; manual review required"


def test_source_and_evidence_ids_are_preserved_and_aggregated() -> None:
    draft = _draft_from_task_result()
    readback = readback_service.build_plant_construct_draft_readback(draft)
    by_slot = _slot_map(readback)

    assert by_slot["promoter"]["evidence_ids"] == ["SRC-PROMOTER-001"]
    assert by_slot["cds_payload_gene_or_enzyme"]["evidence_ids"] == ["SRC-CDS-001"]
    assert by_slot["terminator"]["source_ids"] == []
    assert "SRC-PROMOTER-001" in readback["evidence_source_ids"]
    assert "SRC-CDS-001" in readback["evidence_source_ids"]
    assert "SRC-VECTOR-001" in readback["evidence_source_ids"]


def test_complete_pending_review_draft_remains_manual_review_without_unsafe_language() -> None:
    task_result = {
        "route_id": "confirmed-route",
        "route_label": "case-supported option",
        "plant_host_or_context": "rice seed context",
        "goal_type": "plant_molecular_farming_protein_expression",
        "route_type": "case-supported option",
        "construct_tasks": [
            {
                "slot": slot,
                "value": value,
                "source_ids": [source_id],
                "evidence_ids": [source_id],
                "status": "confirmed",
                "confirmed": True,
                "manual_review_required": True,
            }
            for slot, value, source_id in [
                ("promoter", "source-recorded promoter", "SRC-PROMOTER-001"),
                ("cds", "source-recorded CDS", "SRC-CDS-001"),
                ("terminator", "source-recorded terminator", "SRC-TERM-001"),
                ("marker", "source-recorded marker", "SRC-MARKER-001"),
                ("vector", "source-recorded vector backbone", "SRC-VECTOR-001"),
                ("plant_context", "rice seed context", "SRC-PLANT-001"),
            ]
        ],
    }

    readback = readback_service.build_plant_construct_draft_readback(_draft_from_task_result(task_result))

    assert readback["draft_status"] == draft_service.DRAFT_STATUS_COMPLETE_PENDING_REVIEW
    assert readback["manual_review_required"] is True
    assert readback["present_slot_count"] >= 6
    result_text = str(readback).lower()
    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in result_text


def test_invalid_or_blocked_draft_returns_safe_empty_payload() -> None:
    invalid = readback_service.build_plant_construct_draft_readback(None)
    blocked = readback_service.build_plant_construct_draft_readback(
        draft_service.build_plant_construct_task_draft(
            {
                "route_generation_status": route_service.ROUTE_GENERATION_BLOCKED,
                "candidate_route": None,
                "evidence_gaps": ["direct or adjacent plant case evidence"],
            }
        )
    )

    assert invalid["readback_status"] == readback_service.READBACK_STATUS_EMPTY
    assert invalid["slot_rows"] == []
    assert invalid["manual_review_required"] is True
    assert blocked["readback_status"] == readback_service.READBACK_STATUS_EMPTY
    assert blocked["slot_rows"] == []
    assert blocked["manual_review_required"] is True
    assert blocked["warnings"]


def test_construct_draft_readback_copy_avoids_unsafe_claims() -> None:
    readback_text = str(readback_service.build_plant_construct_draft_readback(_draft_from_task_result())).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_construct_draft_readback_adapter.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in readback_text
        assert forbidden not in service_text


def test_readback_accepts_r330_builder_output_and_preserves_draft_shape() -> None:
    task_result = _bridge_task_result()
    draft = draft_service.build_plant_construct_task_draft(task_result)

    readback = readback_service.build_plant_construct_draft_readback(draft)
    by_slot = _slot_map(readback)

    assert readback["readback_status"] == readback_service.READBACK_STATUS_READY
    assert readback["draft_id"] == draft["draft_id"]
    assert by_slot["promoter"]["status"] == draft_service.SLOT_STATUS_NEEDS_CONFIRMATION
    assert by_slot["tag"]["status"] == draft_service.SLOT_STATUS_NOT_APPLICABLE
    assert by_slot["tag"]["safe_status_text"] == "not applicable for this draft readback"


def test_construct_draft_readback_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant construct draft readback adapter must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = readback_service.build_plant_construct_draft_readback(_draft_from_task_result())

    assert result["readback_status"] == readback_service.READBACK_STATUS_READY
    importlib.reload(readback_service)
