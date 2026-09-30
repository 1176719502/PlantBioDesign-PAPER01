from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validate_plant_component_registry import REGISTRY_ROOT, validate


ROOT = Path(__file__).resolve().parents[1]


def test_batch1_registry_offline_contract() -> None:
    assert validate() == []
    payload = json.loads((REGISTRY_ROOT / "registry.batch1.json").read_text(encoding="utf-8"))
    records = payload["records"]
    assert len(records) == 34
    assert {
        "PCLV1-PRO-35S-835",
        "PCLV1-3REG-NOS-256",
        "PCLV1-3REG-NOS-253",
        "PCLV1-CDS-NPTII",
        "PCLV1-CDS-GUSA",
        "PCLV1-CDS-CYP76AD1",
        "PCLV1-CDS-DODA1",
        "PCLV1-CDS-CDOPA5GT",
        "PCLV1-PRO-35S2-758",
        "PCLV1-PRO-RD29A-824",
        "PCLV1-PRO-E8-2164",
        "PCLV1-PRO-LEB4-2697",
        "PCLV1-5UTR-E8-39",
        "PCLV1-5UTR-TEV-136",
        "PCLV1-3REG-CAMV35S-212",
        "PCLV1-CDS-HPTII",
        "PCLV1-CDS-BAR",
        "PCLV1-CDS-SGFP",
        "PCLV1-VEC-PCAMBIA1300",
        "PCLV1-VEC-PPZP201",
        "PCLV1-VEC-PCSGFPBT",
        "PCLV1-VEC-PGWB8",
        "PCLV1-TER-HSP18-2-250",
        "PCLV1-TER-RBCS-E9-295",
    } <= {record["component_id"] for record in records}
    assert len({record["component_id"] for record in records}) == len(records)
    assert len({record["sequence_sha256"] for record in records}) == len(records)
    assert {record["component_type"] for record in records} >= {
        "promoter",
        "five_prime_utr",
        "three_prime_regulatory_region",
        "terminator",
        "cds",
        "vector_backbone",
    }
    hosts = {host for record in records for host in record["target_host_species"]}
    assert {"Arabidopsis thaliana", "Oryza sativa", "Zea mays", "Solanum lycopersicum"} <= hosts
    groups = {group for record in records for group in record["host_group"]}
    assert {"dicot", "monocot"} <= groups
    for record in records:
        sequence = record["sequence"]
        assert record["sequence_length"] == len(sequence)
        assert record["sequence_sha256"] == hashlib.sha256(sequence.encode("ascii")).hexdigest()
        assert (REGISTRY_ROOT / "sequences" / f"{record['component_id']}.fasta").is_file()
        assert record["primary_reference"]
        assert record["evidence_context"]
        assert record["limitations"]
        assert record["review_status"] in {
            "source_and_boundary_reviewed",
            "source_sequence_reviewed_context_limited",
            "manual_context_review_required",
        }


def test_two_publication_terminators_have_exact_source_boundaries_and_literature() -> None:
    records = {
        record["component_id"]: record
        for record in json.loads(
            (REGISTRY_ROOT / "registry.batch1.json").read_text(encoding="utf-8")
        )["records"]
    }
    expected = {
        "PCLV1-TER-HSP18-2-250": {
            "accession_version": "PP558908.1",
            "start": 852,
            "end": 1101,
            "length": 250,
            "pmid": "PMID:20040586",
            "doi": "DOI:10.1093/pcp/pcp188",
        },
        "PCLV1-TER-RBCS-E9-295": {
            "accession_version": "AF309825.2",
            "start": 1882,
            "end": 2176,
            "length": 295,
            "pmid": "PMID:11069700",
            "doi": "DOI:10.1046/j.1365-313x.2000.00868.x",
        },
    }
    for component_id, identity in expected.items():
        record = records[component_id]
        boundary = record["feature_boundary_method"]
        assert record["component_type"] == "terminator"
        assert record["accession_version"] == identity["accession_version"]
        assert boundary["start_one_based"] == identity["start"]
        assert boundary["end_one_based_inclusive"] == identity["end"]
        assert boundary["strand"] == "+"
        assert record["sequence_length"] == identity["length"]
        assert identity["pmid"] in record["primary_reference"]
        assert identity["doi"] in record["primary_reference"]
        assert record["redistribution_status"] == "PUBLIC_NCBI_RECORD_RIGHTS_CAVEAT_RECORDED"


def test_nos_records_are_related_source_variants_not_independent_diversity() -> None:
    records = {
        record["component_id"]: record
        for record in json.loads(
            (REGISTRY_ROOT / "registry.batch1.json").read_text(encoding="utf-8")
        )["records"]
    }
    nos_256 = records["PCLV1-3REG-NOS-256"]
    nos_253 = records["PCLV1-3REG-NOS-253"]
    assert nos_256["sequence"].startswith(nos_253["sequence"])
    assert len(nos_256["sequence"]) - len(nos_253["sequence"]) == 3
    assert nos_256["related_records"][0]["component_id"] == nos_253["component_id"]
    assert nos_253["related_records"][0]["component_id"] == nos_256["component_id"]
    assert {
        nos_256["related_records"][0]["relationship_type"],
        nos_253["related_records"][0]["relationship_type"],
    } == {"related_locus_source_variant"}


def test_batch_does_not_modify_formal_runtime_or_database() -> None:
    assert (ROOT / "app.py").is_file()
    assert not (ROOT / "data" / "biodesign_unified.db").exists()
