# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_evidence_case_curation as curation_service


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
    _term("recommended promoter"),
    _term("recommended vector"),
)


def _direct_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "source_id": "SRC-001",
        "doi": "10.0000/example",
        "title": "Sugarcane sugar metabolism evidence metadata",
        "year": "2024",
        "evidence_classification": "direct",
        "plant_species": "Saccharum officinarum",
        "target_trait_or_product": "rare sugar context",
        "pathway": "sugar metabolism pathway family",
        "gene": "manual gene note",
        "enzyme": "manual enzyme note",
        "promoter": "manual promoter note",
        "cds": "manual CDS note",
        "vector": "manual vector note",
        "tissue_context": "stem",
        "evidence_summary": "Manually annotated metadata summary.",
    }
    record.update(overrides)
    return record


def test_direct_evidence_candidate_creates_case_draft_with_source_reference() -> None:
    result = curation_service.curate_plant_evidence_case_candidates([_direct_record()])

    assert result["summary"]["case_draft_count"] == 1
    draft = result["case_drafts"][0]
    assert draft["case_draft_allowed"] is True
    assert draft["classification"] == "direct"
    assert draft["source_reference"] == {
        "source_id": "SRC-001",
        "doi": "10.0000/example",
        "title": "Sugarcane sugar metabolism evidence metadata",
        "year": "2024",
    }
    assert draft["component_context"]["promoter"] == "manual promoter note"


def test_adjacent_evidence_candidate_creates_case_draft_but_preserves_missing_fields() -> None:
    result = curation_service.curate_plant_evidence_case_candidates(
        [
            _direct_record(
                source_id="SRC-ADJ",
                evidence_classification="adjacent",
                promoter="",
                cds="",
                vector="",
                gene="",
                missing_fields=["promoter", "cds", "vector", "gene"],
            )
        ]
    )

    draft = result["case_drafts"][0]
    assert draft["classification"] == "adjacent"
    assert draft["component_context"]["promoter"] == ""
    assert draft["component_context"]["cds"] == ""
    assert draft["component_context"]["vector"] == ""
    assert draft["component_context"]["gene"] == ""
    assert {"promoter", "cds", "vector", "gene"} <= set(draft["missing_fields"])


def test_irrelevant_evidence_candidate_is_skipped_without_case_draft() -> None:
    result = curation_service.curate_plant_evidence_case_candidates(
        [
            _direct_record(
                source_id="SRC-IRR",
                evidence_classification="irrelevant",
                title="Non-plant metadata",
            )
        ]
    )

    assert result["case_drafts"] == []
    assert result["summary"]["skipped_count"] == 1
    assert result["skipped_records"][0]["case_draft_allowed"] is False
    assert result["skipped_records"][0]["reason"] == "Evidence candidate is not direct or adjacent plant evidence."


def test_classifier_can_infer_direct_adjacent_and_irrelevant_from_manual_metadata() -> None:
    direct = {
        "plant_species": "Saccharum officinarum",
        "goal_plant_species": "Saccharum officinarum",
        "target_trait_or_product": "rare sugar context",
        "goal_target": "rare sugar context",
    }
    adjacent = {"plant_species": "Oryza sativa", "adjacent_reason": "adjacent plant sugar evidence"}
    irrelevant = {"relevance": "not relevant to plant evidence"}

    assert curation_service.classify_plant_evidence_candidate(direct) == "direct"
    assert curation_service.classify_plant_evidence_candidate(adjacent) == "adjacent"
    assert curation_service.classify_plant_evidence_candidate(irrelevant) == "irrelevant"


def test_case_curation_copy_avoids_forbidden_claims() -> None:
    result_text = str(curation_service.curate_plant_evidence_case_candidates([_direct_record()])).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_evidence_case_curation.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in result_text
        assert forbidden not in service_text


def test_case_curation_service_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant evidence case curation must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = curation_service.curate_plant_evidence_case_candidates([_direct_record()])

    assert result["summary"]["case_draft_count"] == 1
    importlib.reload(curation_service)
