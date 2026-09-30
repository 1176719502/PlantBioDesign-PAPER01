# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_goal_route_generator as route_service
from services import plant_route_construct_task_bridge as bridge_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("best"),
    _term("correct"),
    _term("valid", "ated"),
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("proto", "col"),
    _term("optimized"),
    _term("yield"),
    _term("expression ", "pre", "diction"),
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
                "gene_or_cds_source",
                "promoter",
                "terminator",
                "marker",
                "vector",
            ],
            "slot_source_ids": {
                "plant_species": ["SRC-PROTEIN-001"],
                "cds": ["SRC-PROTEIN-001"],
                "promoter": ["SRC-PROTEIN-001"],
                "terminator": ["SRC-PROTEIN-001"],
                "marker": ["SRC-PROTEIN-001"],
                "vector": ["SRC-PROTEIN-001"],
            },
            "missing_fields": [],
            "manual_review_required": True,
        },
    }
    route.update(overrides)
    return route


def test_allowed_candidate_route_creates_required_construct_slot_tasks() -> None:
    result = bridge_service.build_plant_construct_task_requirements(_allowed_route())

    assert result["construct_task_status"] == bridge_service.CONSTRUCT_TASK_STATUS_CREATED
    slots = [task["slot"] for task in result["construct_tasks"]]
    assert slots == [
        "plant_host_context",
        "target_payload_cds_or_gene_enzyme",
        "promoter_need",
        "terminator_need",
        "marker_need",
        "vector_backbone_need",
    ]
    assert all(task["manual_review_required"] is True for task in result["construct_tasks"])
    assert result["manual_review_required"] is True
    assert result["task_list_only"] is True


def test_missing_promoter_and_vector_sources_are_preserved_as_needs_source() -> None:
    route = _allowed_route()
    candidate = dict(route["candidate_route"])  # type: ignore[index]
    candidate["slot_source_ids"] = {
        "plant_species": ["SRC-PROTEIN-001"],
        "cds": ["SRC-PROTEIN-001"],
        "terminator": ["SRC-PROTEIN-001"],
        "marker": ["SRC-PROTEIN-001"],
    }
    candidate["missing_fields"] = ["promoter", "vector"]
    route["candidate_route"] = candidate

    result = bridge_service.build_plant_construct_task_requirements(route)
    by_slot = {task["slot"]: task for task in result["construct_tasks"]}

    assert by_slot["promoter_need"]["status"] == bridge_service.SLOT_STATUS_NEEDS_SOURCE
    assert by_slot["vector_backbone_need"]["status"] == bridge_service.SLOT_STATUS_NEEDS_SOURCE
    assert by_slot["promoter_need"]["evidence_source_ids"] == []
    assert by_slot["vector_backbone_need"]["evidence_source_ids"] == []
    assert {"promoter_need", "vector_backbone_need", "promoter", "vector"} <= set(result["missing_fields"])


def test_blocked_route_refuses_construct_task_creation() -> None:
    result = bridge_service.build_plant_construct_task_requirements(
        {
            "route_generation_status": route_service.ROUTE_GENERATION_BLOCKED,
            "candidate_route": None,
            "evidence_gaps": ["direct or adjacent plant case evidence"],
        }
    )

    assert result["construct_task_status"] == bridge_service.CONSTRUCT_TASK_STATUS_REFUSED
    assert result["reason"] == "route not allowed"
    assert result["construct_tasks"] == []
    assert result["manual_review_required"] is True


def test_optional_tag_signal_or_localization_slot_is_included_when_present() -> None:
    route = _allowed_route()
    candidate = dict(route["candidate_route"])  # type: ignore[index]
    candidate["required_component_slots"] = [*candidate["required_component_slots"], "localization"]  # type: ignore[index]
    candidate["slot_source_ids"] = {
        **candidate["slot_source_ids"],  # type: ignore[arg-type]
        "localization": ["SRC-PROTEIN-001"],
    }
    route["candidate_route"] = candidate

    result = bridge_service.build_plant_construct_task_requirements(route)
    slots = [task["slot"] for task in result["construct_tasks"]]

    assert "optional_tag_signal_peptide_localization" in slots


def test_construct_task_bridge_copy_avoids_unsafe_claims() -> None:
    result_text = str(bridge_service.build_plant_construct_task_requirements(_allowed_route())).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_route_construct_task_bridge.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in result_text
        assert forbidden not in service_text


def test_construct_task_bridge_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant route construct task bridge must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = bridge_service.build_plant_construct_task_requirements(_allowed_route())

    assert result["construct_task_status"] == bridge_service.CONSTRUCT_TASK_STATUS_CREATED
    importlib.reload(bridge_service)
