from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_plant_knowledge_layer_v1 import BUNDLE_PATH, EXPECTED_IDS, validate


ROOT = Path(__file__).resolve().parents[1]


def test_expanded_plant_knowledge_layer_dataset_validates() -> None:
    assert validate() == []


def test_dataset_contains_all_registry_links_without_sequence_data() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert {row["component_id"] for row in payload["records"]} == EXPECTED_IDS
    assert len(payload["records"]) == 20
    serialized = json.dumps(payload, sort_keys=True)
    assert '"sequence":' not in serialized
    assert all(row["review"] == {
        "record_status": "DRAFT",
        "human_review_status": "PENDING_HUMAN_REVIEW",
        "reviewer": None,
        "reviewed_at_utc": None,
        "review_notes": "Initial evidence context only; human source and claim review is required.",
    } for row in payload["records"])


def test_each_object_has_provenance_claims_context_and_limitations() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    for row in payload["records"]:
        assert row["registry_reference"]["component_id"] == row["component_id"]
        assert row["literature_references"]
        assert row["biological_context"]
        assert row["evidence_claims"]
        assert row["engineering_context_notes"]
        assert row["limitations"]
        assert all(claim["unknown_reason"] for claim in row["evidence_claims"])
        assert all(claim["evidence_level"] in {"E1", "E2", "UNKNOWN"} for claim in row["evidence_claims"])
        assert all(lit["source_database"] for lit in row["literature_references"])


def test_publication_minimum_objects_cover_dq_group_and_two_terminators() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    records = {row["component_id"]: row for row in payload["records"]}
    expected = {
        "PCLV1-PRO-35S2-758",
        "PCLV1-5UTR-TEV-136",
        "PCLV1-CDS-SGFP",
        "PCLV1-3REG-CAMV35S-212",
        "PCLV1-VEC-PCSGFPBT",
        "PCLV1-TER-HSP18-2-250",
        "PCLV1-TER-RBCS-E9-295",
    }
    assert expected <= records.keys()
    for component_id in expected:
        row = records[component_id]
        assert {claim["claim_type"] for claim in row["evidence_claims"]} >= {
            "IDENTITY",
            "BOUNDARY",
            "FUNCTION",
        }
        assert row["review"]["human_review_status"] == "PENDING_HUMAN_REVIEW"
    hsp_literature = records["PCLV1-TER-HSP18-2-250"]["literature_references"]
    e9_literature = records["PCLV1-TER-RBCS-E9-295"]["literature_references"]
    assert any(item["pmid"] == "20040586" and item["doi"] == "10.1093/pcp/pcp188" for item in hsp_literature)
    assert any(item["pmid"] == "11069700" and item["doi"] == "10.1046/j.1365-313x.2000.00868.x" for item in e9_literature)


def test_registry_and_runtime_boundaries_are_not_changed_by_dataset() -> None:
    assert (ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json").is_file()
    assert (ROOT / "app.py").is_file()
