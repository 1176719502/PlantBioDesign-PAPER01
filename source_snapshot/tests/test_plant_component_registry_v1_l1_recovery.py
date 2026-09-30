from __future__ import annotations

import json

from Bio.Seq import Seq

from scripts.validate_plant_component_registry import REGISTRY_ROOT, validate


RECOVERY_IDS = {
    "PCLV1-PRO-UBQ10",
    "PCLV1-PRO-UBI1",
    "PCLV1-TER-OCS",
    "PCLV1-VEC-PBIN19",
    "PCLV1-PRO-FMVT",
}


def _records() -> list[dict[str, object]]:
    payload = json.loads((REGISTRY_ROOT / "registry.batch1.json").read_text(encoding="utf-8"))
    return payload["records"]


def test_l1_recovery_threshold_and_evidence_mix() -> None:
    assert validate() == []
    records = _records()
    assert len(records) == 34
    recovery = [record for record in records if record["component_id"] in RECOVERY_IDS]
    assert len(recovery) == 5
    assert sum(record["evidence_level"] == "E1" for record in recovery) == 2
    assert sum(record["evidence_level"] == "E2" for record in recovery) == 3
    assert sum(record["component_type"] == "promoter" for record in recovery) == 3
    assert sum(record["component_type"] == "terminator" for record in recovery) == 1
    assert sum(record["component_type"] == "vector_backbone" for record in recovery) == 1


def test_recovery_sequences_are_unique_in_both_orientations() -> None:
    records = _records()
    canonical = [min(record["sequence"], str(Seq(record["sequence"]).reverse_complement())) for record in records]
    assert len(canonical) == len(set(canonical))
    assert all(record["source_organism"] not in record["host_group"] for record in records)
    native_host_records = {
        record["component_id"]
        for record in records
        if record["source_organism"] in record["target_host_species"]
    }
    assert native_host_records == {
        "PCLV1-PRO-UBQ10",
        "PCLV1-PRO-UBI1",
        "PCLV1-PRO-RD29A-824",
        "PCLV1-PRO-E8-2164",
        "PCLV1-PRO-LEB4-2697",
        "PCLV1-5UTR-E8-39",
        "PCLV1-5UTR-CYP76AD1-258",
        "PCLV1-5UTR-DODA1-59",
        "PCLV1-5UTR-CDOPA5GT-21",
        "PCLV1-3REG-E8-140",
        "PCLV1-3REG-LEB4-123",
        "PCLV1-TER-HSP18-2-250",
    }


def test_pbin19_is_a_qualified_complete_vector_source() -> None:
    record = next(record for record in _records() if record["component_id"] == "PCLV1-VEC-PBIN19")
    context = record["vector_context"]
    assert record["accession_version"] == "U09365.1"
    assert record["sequence_length"] == 11777
    assert context["t_dna_region"] == {
        "start_one_based": 6043,
        "end_one_based_inclusive": 9421,
        "length": 3379,
        "crosses_origin": False,
    }
    assert context["non_t_dna_backbone"]["segments"] == [
        {"start_one_based": 9422, "end_one_based_inclusive": 11777},
        {"start_one_based": 1, "end_one_based_inclusive": 6042},
    ]
    assert context["non_t_dna_backbone"]["length"] == 8398
    assert context["plant_selectable_cassette"]["start_one_based"] == 7501
    assert context["plant_selectable_cassette"]["end_one_based_inclusive"] == 9259
    assert context["formal_workflow_decision"] == "REQUIRES_MANUAL_T_DNA_REPLACEMENT_REVIEW"
    assert "not an empty or unqualified" in record["notes"]


def test_unresolved_hold_candidates_are_not_approved() -> None:
    ids = {record["component_id"] for record in _records()}
    assert {
        "PCLV1-PRO-ACT1",
        "PCLV1-PRO-RUBISCO",
        "PCLV1-PRO-EF1A",
    }.isdisjoint(ids)
