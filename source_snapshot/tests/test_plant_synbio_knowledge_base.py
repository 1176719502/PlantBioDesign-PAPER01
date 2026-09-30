# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_synbio_knowledge_base as kb_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("valid", "ated ", "con", "struct"),
    _term("optimized ", "pathway"),
    _term("yield ", "pre", "diction"),
    _term("best route"),
    _term("correct route"),
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("expression ", "pre", "diction"),
    _term("guaranteed expression"),
)


def test_loads_all_r325_jsonl_knowledge_files() -> None:
    knowledge = kb_service.load_plant_synbio_knowledge_base()

    assert len(knowledge["goal_type_templates"]) >= 2
    assert len(knowledge["route_templates"]) >= 2
    assert len(knowledge["component_slot_templates"]) >= 6
    assert len(knowledge["evidence_sources"]) >= 4
    assert {
        row["goal_type_id"] for row in knowledge["goal_type_templates"]
    } >= {
        "plant_metabolic_engineering_sugar_metabolism",
        "plant_molecular_farming_protein_expression",
    }


def test_sugarcane_healthy_sugar_goal_blocks_route_generation_with_discovery_plan() -> None:
    intake = kb_service.build_plant_goal_evidence_intake("\u7518\u8517 \u5065\u5eb7\u7cd6")

    assert intake["matched_goal_type"]["matched"] is True
    assert intake["matched_goal_type"]["goal_type_id"] == "plant_metabolic_engineering_sugar_metabolism"
    assert "Plant metabolic engineering / sugar metabolism direction" == intake["matched_goal_type"]["label"]
    assert intake["can_generate_candidate_route"] is False
    assert intake["route_generation_status"] == kb_service.ROUTE_BLOCKED_STATUS
    assert "target_trait_or_metabolite" in intake["missing_information"]
    assert "candidate_pathway" in intake["missing_information"]
    assert "candidate_gene_or_enzyme" in intake["missing_information"]
    discovery_tasks = [row["task"] for row in intake["evidence_discovery_plan"]]
    assert "define exact target sugar / target metabolite" in discovery_tasks
    assert "identify candidate pathway" in discovery_tasks
    assert "identify candidate gene/enzyme" in discovery_tasks
    assert "identify plant tissue/context" in discovery_tasks
    assert "find sugarcane or adjacent plant cases" in discovery_tasks
    assert "find expression system / promoter / vector evidence" in discovery_tasks


def test_recorded_required_context_allows_template_review_without_generating_design_route() -> None:
    intake = kb_service.build_plant_goal_evidence_intake(
        "Sugarcane rare sugar metabolism documentation",
        {
            "plant_context": "Saccharum context from manual note",
            "target_trait_or_metabolite": "rare sugar target recorded by user",
            "candidate_pathway": "pathway family recorded by user",
            "candidate_gene_or_enzyme": "candidate enzyme recorded by user",
            "tissue_context": "stem context recorded by user",
            "evidence_context": "manual evidence note recorded by user",
        },
    )

    assert intake["missing_information"] == []
    assert intake["can_generate_candidate_route"] is True
    assert intake["route_generation_status"] == kb_service.ROUTE_ALLOWED_STATUS
    assert intake["evidence_discovery_plan"] == []
    assert intake["matched_route_templates"][0]["route_template_id"] == "sugar_metabolism_evidence_first_route_template"


def test_unmatched_goal_still_returns_boundary_and_blocked_status() -> None:
    intake = kb_service.build_plant_goal_evidence_intake("generic project workspace")

    assert intake["matched_goal_type"]["matched"] is False
    assert intake["matched_route_templates"] == []
    assert intake["can_generate_candidate_route"] is False
    assert intake["route_generation_status"] == kb_service.ROUTE_BLOCKED_STATUS
    assert "documentation-only" in intake["documentation_boundary"]


def test_r325_service_output_and_files_avoid_forbidden_claims() -> None:
    intake_text = str(kb_service.build_plant_goal_evidence_intake("\u7518\u8517 \u5065\u5eb7\u7cd6")).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_synbio_knowledge_base.py"
    ).read_text(encoding="utf-8").lower()
    data_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (Path(__file__).resolve().parents[1] / "data" / "plant_synbio_knowledge").glob("*.jsonl")
    )

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in intake_text
        assert forbidden not in service_text
        assert forbidden not in data_text


def test_r325_service_does_not_import_streamlit(monkeypatch) -> None:
    original_import = builtins.__import__

    def _block_streamlit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("plant synbio knowledge base must not import Streamlit")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit_import)

    intake = kb_service.build_plant_goal_evidence_intake("\u7518\u8517 \u5065\u5eb7\u7cd6")

    assert intake["route_generation_status"] == kb_service.ROUTE_BLOCKED_STATUS
    importlib.reload(kb_service)
