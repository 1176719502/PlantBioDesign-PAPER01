import json
from pathlib import Path

from services.plant_component_workflow_registry import library_view_records, registry_records


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
NOS_GOVERNANCE = ROOT / "audit_reports" / "rice_nos_admission_blocker_closure" / "GOVERNANCE_RECORD.json"

PROMOTER_IDS = {
    "PCLV1-PRO-35S-835",
    "PCLV1-PRO-UBQ10",
    "PCLV1-PRO-UBI1",
    "PCLV1-PRO-FMVT",
    "PCLV1-PRO-35S2-758",
    "PCLV1-PRO-RD29A-824",
    "PCLV1-PRO-E8-2164",
    "PCLV1-PRO-LEB4-2697",
}
THREE_PRIME_IDS = {
    "PCLV1-3REG-NOS-256",
    "PCLV1-3REG-NOS-253",
    "PCLV1-TER-OCS",
    "PCLV1-3REG-CAMV35S-212",
    "PCLV1-3REG-E8-140",
    "PCLV1-3REG-LEB4-123",
    "PCLV1-TER-HSP18-2-250",
    "PCLV1-TER-RBCS-E9-295",
}
EXPECTED_HASHES = {
    "PCLV1-PRO-35S-835": "4f5069bdd68260bb7a243ec7f8b628e13d52f58242c6f7acf53e3cc55a8673e2",
    "PCLV1-PRO-UBQ10": "b24922506b7b3660d7ce5e58986994888077a013da1c123a0139a2e45419c5a4",
    "PCLV1-PRO-UBI1": "821e00405808f6e0d1a84390121792189e3e4fe90715e5c6b7403eaa21bb4450",
    "PCLV1-PRO-FMVT": "47521eeaa73884edf67f1edee24494d71222904411502bfeb8047fde0cf5518d",
    "PCLV1-PRO-35S2-758": "2a8d4fc6a4e4b431437be578e741db3c9db105d88ae235c5cf900d22834a7f3d",
    "PCLV1-PRO-RD29A-824": "2d215d69cb4876c6949989f5180460b0e0d94fe6722bf291c0ff71e2d4ef5d58",
    "PCLV1-PRO-E8-2164": "ee18d306f8a4cddfe4cb0f7822500127641a188b4b475e3890a4a62e72add427",
    "PCLV1-PRO-LEB4-2697": "661c55c9dc075c2e98ca3bd3317b2304bb0b01a54f5eeb1ee09cee6fba9df1f9",
    "PCLV1-3REG-NOS-256": "6c8916397c8f95a894a870ce5620837d41d776e57c64d415d76f3f0d02eb35c4",
    "PCLV1-3REG-NOS-253": "07296665a19dbedd665dc2f350869a1474a72811f54688cbef8835e24372ab3f",
    "PCLV1-TER-OCS": "a59c971aea1ae0f1aafddce600b157c2aa2aaf6cbd2d914455757714cb9c8f7c",
    "PCLV1-3REG-CAMV35S-212": "9dcb1ca38d17df734b63b759d44b35fee363e9a7ffae7c289e8b83e86f13d705",
    "PCLV1-3REG-E8-140": "d3fadbf01d3eaa2a1f82f7cf1831222714e502954a545749a7672547a34c19f8",
    "PCLV1-3REG-LEB4-123": "12c0850ad859b015d074945d59a7de09758bae7e256cbe83f20b57f9349041ea",
    "PCLV1-TER-HSP18-2-250": "f64cc0a9ffd000d281dc8d75163b072d42ec8184ad216470461941a4e61dfd1d",
    "PCLV1-TER-RBCS-E9-295": "e4d09d94a70cfcf400736631bf58668e64f5016671b8a949a5cc92269ed35721",
}


def test_registry_has_34_records_and_all_relevant_identity_hashes_are_frozen():
    records = registry_records()
    assert len(records) == 34
    by_id = {record["component_id"]: record for record in records}
    assert set(EXPECTED_HASHES) == PROMOTER_IDS | THREE_PRIME_IDS
    for component_id, sequence_hash in EXPECTED_HASHES.items():
        row = by_id[component_id]
        assert row["sequence_sha256"] == sequence_hash
        assert row["sequence_length"] == len(row["sequence"])
        assert row["component_type"] in {"promoter", "terminator", "three_prime_regulatory_region"}
        assert row["redistribution_status"] in {
            "PUBLIC_NCBI_RECORD_NEEDS_REVIEW",
            "PUBLIC_NCBI_RECORD_RIGHTS_CAVEAT_RECORDED",
        }
        assert "admission_state" not in row
        assert "formal_selectable" not in row
        if component_id in {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}:
            assert row["host_applicability"]["status"] == "reviewed"
        else:
            assert "host_applicability" not in row
        assert "component_use_evidence" not in row


def test_rice_targeted_registry_records_are_role_incompatible_and_no_step3_row_is_selectable():
    records = registry_records()
    rice_rows = [row for row in records if "Oryza sativa" in row.get("target_host_species", [])]
    assert {row["component_id"] for row in rice_rows} == {
        "PCLV1-CDS-GUSA",
        "PCLV1-VEC-PBIN19",
    }
    assert {row["component_type"] for row in rice_rows} == {"cds", "vector_backbone"}

    view_rows = library_view_records()
    relevant = [row for row in view_rows if row["registry_component_id"] in EXPECTED_HASHES]
    assert len(relevant) == 16
    assert {
        row["registry_component_id"]
        for row in relevant
        if row["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert not any(row["registry_component_id"] in PROMOTER_IDS and "Oryza sativa" in row["target_host_species"] for row in relevant)
    assert not any(row["registry_component_id"] in THREE_PRIME_IDS and "Oryza sativa" in row["target_host_species"] for row in relevant)


def test_nos_253_related_variant_and_rights_blocker_remain_unchanged():
    records = {row["component_id"]: row for row in registry_records()}
    nos_253 = records["PCLV1-3REG-NOS-253"]
    nos_256 = records["PCLV1-3REG-NOS-256"]
    assert nos_256["sequence"].startswith(nos_253["sequence"])
    assert len(nos_256["sequence"]) - len(nos_253["sequence"]) == 3
    assert nos_253["related_records"][0]["relationship_type"] == "related_locus_source_variant"

    governance = json.loads(NOS_GOVERNANCE.read_text(encoding="utf-8"))
    assert governance["blockers"] == [
        {
            "id": "RIGHTS-REDISTRIBUTION-01",
            "status": "UNRESOLVED",
            "description": (
                "Authoritative evidence does not establish record-specific third-party "
                "permission to redistribute AF502128.1 or the exact extracted NOS "
                "sequence, and current project policy rejects raw or reconstructable "
                "sequence distribution in Git/software/packages."
            ),
            "closure_evidence_required": (
                "An accountable rights-holder or legal/governance determination that "
                "explicitly authorizes the intended exact-sequence distribution scope, "
                "followed by a separately authorized admission decision."
            ),
        }
    ]
    assert governance["scope"]["mutation_executed"] is False
