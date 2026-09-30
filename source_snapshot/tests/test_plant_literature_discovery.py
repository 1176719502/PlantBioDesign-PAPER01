# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_literature_discovery as discovery_service
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
    _term("pdf downloaded"),
    _term("full text stored"),
)


def test_sugarcane_healthy_sugar_generates_expected_offline_queries() -> None:
    plan = discovery_service.build_plant_literature_discovery_plan("\u7518\u8517 \u5065\u5eb7\u7cd6")

    assert plan["matched_goal_type_id"] == "plant_metabolic_engineering_sugar_metabolism"
    assert plan["queries"][:7] == [
        "sugarcane sucrose metabolism engineering",
        "Saccharum sugar metabolism transgenic",
        "sugarcane rare sugar metabolic engineering",
        "plant rare sugar pathway engineering",
        "sugarcane sucrose transporter engineering",
        "sugarcane promoter stem expression",
        "sugarcane transformation expression vector",
    ]
    assert plan["source_policy"]["offline_deterministic"] is True
    assert plan["source_policy"]["pdf_download_allowed"] is False
    assert plan["source_policy"]["full_text_storage_allowed"] is False


def test_search_intents_cover_supported_metadata_sources_without_network_dependency() -> None:
    plan = discovery_service.build_plant_literature_discovery_plan("\u7518\u8517 \u5065\u5eb7\u7cd6")

    first_query_intents = plan["search_intents"][:4]
    assert [intent["source"] for intent in first_query_intents] == [
        "PubMed",
        "Europe PMC",
        "Crossref",
        "Semantic Scholar",
    ]
    assert {intent["storage_policy"] for intent in first_query_intents} == {
        "metadata/query intent only; no PDFs or full text"
    }
    assert plan["source_policy"]["api_required_for_tests"] is False


def test_evidence_gap_tasks_preserve_r325_missing_information() -> None:
    intake = kb_service.build_plant_goal_evidence_intake("\u7518\u8517 \u5065\u5eb7\u7cd6")
    plan = discovery_service.build_plant_literature_discovery_plan(
        "\u7518\u8517 \u5065\u5eb7\u7cd6",
        intake=intake,
    )

    gap_fields = {task["gap_field"] for task in plan["evidence_gap_search_tasks"]}
    assert "target_trait_or_metabolite" in gap_fields
    assert "candidate_pathway" in gap_fields
    assert "candidate_gene_or_enzyme" in gap_fields
    assert any("identify candidate pathway" == task["task"] for task in plan["evidence_gap_search_tasks"])


def test_recorded_context_still_returns_manual_review_search_tasks() -> None:
    plan = discovery_service.build_plant_literature_discovery_plan(
        "Sugarcane rare sugar metabolism documentation",
        user_context={
            "plant_context": "Saccharum context from manual note",
            "target_trait_or_metabolite": "rare sugar target recorded by user",
            "candidate_pathway": "pathway family recorded by user",
            "candidate_gene_or_enzyme": "candidate enzyme recorded by user",
            "tissue_context": "stem context recorded by user",
            "evidence_context": "manual evidence note recorded by user",
        },
    )

    assert plan["evidence_gap_search_tasks"]
    assert {task["gap_field"] for task in plan["evidence_gap_search_tasks"]} == {
        "recorded_context_review"
    }
    assert all(task["status"] == "manual_review_required" for task in plan["evidence_gap_search_tasks"])


def test_literature_discovery_copy_avoids_forbidden_claims() -> None:
    plan_text = str(discovery_service.build_plant_literature_discovery_plan("\u7518\u8517 \u5065\u5eb7\u7cd6")).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_literature_discovery.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in plan_text
        assert forbidden not in service_text


def test_literature_discovery_service_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant literature discovery must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    plan = discovery_service.build_plant_literature_discovery_plan("\u7518\u8517 \u5065\u5eb7\u7cd6")

    assert plan["source_policy"]["offline_deterministic"] is True
    importlib.reload(discovery_service)
