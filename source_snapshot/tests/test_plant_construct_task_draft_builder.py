# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

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


def _slot_map(draft: dict[str, object]) -> dict[str, dict[str, object]]:
    return {slot["slot_name"]: slot for slot in draft["construct_slots"]}  # type: ignore[index]


def test_allowed_route_construct_tasks_create_incomplete_construct_draft() -> None:
    task_result = _bridge_task_result()
    tasks = list(task_result["construct_tasks"])  # type: ignore[index]
    task_result["construct_tasks"] = [
        {**task, "missing_reason": "source record missing from route-derived task"}
        if task["slot"] == "vector_backbone_need"
        else task
        for task in tasks
    ]
    task_result["missing_fields"] = ["vector_backbone_need"]

    draft = draft_service.build_plant_construct_task_draft(task_result)
    by_slot = _slot_map(draft)

    assert draft["construct_draft_status"] == draft_service.CONSTRUCT_DRAFT_STATUS_CREATED
    assert draft["source_route_id"] == "protein-route-candidate"
    assert draft["draft_status"] == draft_service.DRAFT_STATUS_INCOMPLETE
    assert draft["manual_review_required"] is True
    assert {
        "promoter",
        "cds_payload_gene_or_enzyme",
        "terminator",
        "selectable_marker",
        "vector_backbone",
        "plant_host_context",
    } <= set(by_slot)
    assert by_slot["vector_backbone"]["status"] == draft_service.SLOT_STATUS_NEEDS_SOURCE
    assert by_slot["vector_backbone"]["missing_reason"] == "source record missing from route-derived task"


def test_complete_confirmed_task_list_remains_pending_review_without_unsafe_language() -> None:
    task_result = {
        "route_id": "confirmed-route",
        "route_label": "case-supported option",
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

    draft = draft_service.build_plant_construct_task_draft(task_result)

    assert draft["draft_status"] == draft_service.DRAFT_STATUS_COMPLETE_PENDING_REVIEW
    assert draft["manual_review_required"] is True
    assert draft["required_slots_explicitly_confirmed"] is True
    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in str(draft).lower()


def test_missing_promoter_and_vector_evidence_preserves_missing_reasons() -> None:
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
                    "evidence_source_ids": [],
                    "missing_source": True,
                    "missing_reason": "vector source evidence not provided",
                }
            )
        else:
            tasks.append(task)
    task_result["construct_tasks"] = tasks

    draft = draft_service.build_plant_construct_task_draft(task_result)
    by_slot = _slot_map(draft)

    assert by_slot["promoter"]["status"] == draft_service.SLOT_STATUS_NEEDS_SOURCE
    assert by_slot["vector_backbone"]["status"] == draft_service.SLOT_STATUS_NEEDS_SOURCE
    assert by_slot["promoter"]["missing_reason"] == "promoter source evidence not provided"
    assert by_slot["vector_backbone"]["missing_reason"] == "vector source evidence not provided"
    assert by_slot["promoter"]["evidence_ids"] == []
    assert by_slot["vector_backbone"]["evidence_ids"] == []


def test_blocked_route_refuses_construct_draft_creation() -> None:
    result = draft_service.build_plant_construct_task_draft(
        {
            "route_generation_status": route_service.ROUTE_GENERATION_BLOCKED,
            "candidate_route": None,
            "evidence_gaps": ["direct or adjacent plant case evidence"],
        }
    )

    assert result["construct_draft_status"] == draft_service.CONSTRUCT_DRAFT_STATUS_BLOCKED
    assert result["reason"] == "route not allowed / route generation blocked"
    assert result["construct_slots"] == []
    assert result["manual_review_required"] is True


def test_construct_draft_builder_copy_avoids_unsafe_claims() -> None:
    result_text = str(draft_service.build_plant_construct_task_draft(_bridge_task_result())).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_construct_task_draft_builder.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in result_text
        assert forbidden not in service_text


def test_construct_draft_builder_accepts_r329_bridge_output_and_preserves_ids() -> None:
    task_result = _bridge_task_result()

    draft = draft_service.build_plant_construct_task_draft(task_result)
    by_slot = _slot_map(draft)

    assert draft["construct_draft_status"] == draft_service.CONSTRUCT_DRAFT_STATUS_CREATED
    assert by_slot["promoter"]["evidence_ids"] == ["SRC-PROMOTER-001"]
    assert by_slot["cds_payload_gene_or_enzyme"]["evidence_ids"] == ["SRC-CDS-001"]
    assert by_slot["terminator"]["status"] == draft_service.SLOT_STATUS_NEEDS_CONFIRMATION
    assert by_slot["tag"]["status"] == draft_service.SLOT_STATUS_NOT_APPLICABLE


def test_construct_draft_builder_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant construct draft builder must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = draft_service.build_plant_construct_task_draft(_bridge_task_result())

    assert result["construct_draft_status"] == draft_service.CONSTRUCT_DRAFT_STATUS_CREATED
    importlib.reload(draft_service)
