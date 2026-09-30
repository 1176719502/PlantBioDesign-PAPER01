import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "audit_reports" / "rice_nos_admission_blocker_closure"
REGISTRY_PATH = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
COMPONENT_SHA256 = "07296665a19dbedd665dc2f350869a1474a72811f54688cbef8835e24372ab3f"


def _governance() -> dict:
    return json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))


def _registry_row() -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    rows = [
        row
        for row in registry["records"]
        if row["component_id"] == "PCLV1-3REG-NOS-253"
    ]
    assert len(rows) == 1
    return rows[0]


def test_governance_record_pins_lineage_identity_and_external_evidence():
    record = _governance()

    assert record["traceability"] == {
        "formal_base": "d083d97dd941f2dfacd401f44c25c1befb327d74",
        "reviewed_batch01_candidate": "8bfd995ac47dbad4931c426ddbad770996ee689c",
        "independent_verdict": "RICE_STEP3_COMPONENT_ADMISSION_BATCH01_REVIEW_NO_GO",
        "independent_verdict_provenance": (
            "Task-supplied independent-review disposition; no separate committed "
            "reviewer artifact was located on the reviewed candidate ref."
        ),
        "candidate_parent_matches_formal_base": True,
    }

    identity = record["nos_identity"]
    assert identity["existing_component_id"] == "PCLV1-3REG-NOS-253"
    assert identity["duplicate_status"] == "exact_duplicate"
    assert identity["source_accession_version"] == "AF502128.1"
    assert identity["source_record_raw_sha256"] == (
        "61ec94d7d5f61dbc4af1f48199267170586c4f3507f76d51d2ace27f2b92979f"
    )
    assert identity["source_record_sequence_sha256"] == (
        "5376c785ba106a30ebe52443bb43eb44a8881bd04c4ea1024a4bf433b7281347"
    )
    assert identity["deposited_regulatory_class"] == "terminator"
    assert identity["feature_location"] == "2778..3030"
    assert identity["length"] == 253
    assert identity["component_sequence_sha256"] == COMPONENT_SHA256
    assert identity["component_sequence_embedded_in_this_package"] is False

    pin = record["external_artifact_pinning"]
    assert pin["filename"] == (
        "Rice_Step3_pBI221_NOS_AF502128.1_Evidence_Closure.xlsx"
    )
    assert pin["bytes"] == 8895
    assert pin["sha256"] == (
        "616a7537e6c620baad6b3fde5380ab2f466e00a0bd2e74386716cd64731beefe"
    )
    assert pin["provenance"]["sheets"] == [
        "Rice 3Prime Review",
        "Evidence Trace",
        "Exact Sequence",
        "Claim Boundaries",
    ]
    assert pin["provenance"]["source_record_sha256"] == (
        identity["source_record_raw_sha256"]
    )


def test_rights_verdict_fails_closed_without_treating_public_access_as_permission():
    record = _governance()
    rights = record["rights_evidence"]
    redistribution = record["redistribution_verdict"]

    assert rights["decision"] == (
        "RIGHTS_REDISTRIBUTION_UNRESOLVED_FOR_EXACT_SEQUENCE_IN_GIT_SOFTWARE_OR_PACKAGE"
    )
    assert rights["not_legal_advice"] is True
    assert redistribution["public_access_is_not_treated_as_licence_permission"] is True
    assert redistribution["accession_citation_hash_and_derived_metadata_in_repository"] == (
        "APPROVE"
    )
    assert redistribution["raw_record_in_governed_external_store_for_internal_verification"] == (
        "APPROVE"
    )
    assert redistribution["raw_or_reconstructable_sequence_bytes_in_git_software_or_release_package"] == (
        "REJECT_UNDER_CURRENT_PROJECT_POLICY"
    )
    assert redistribution["exact_sequence_plus_af502128_1_provenance_as_newly_approved_project_distribution"] == (
        "NOT_ESTABLISHED"
    )
    assert record["final_verdict"] == "RICE_NOS_ADMISSION_BLOCKERS_REMAIN"
    assert record["blockers"] == [
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


def test_plan_targets_only_existing_row_and_executes_no_mutation():
    record = _governance()
    plan = record["admission_plan_if_separately_authorized"]
    row = _registry_row()

    assert record["scope"]["mutation_executed"] is False
    assert plan["target_existing_component_id"] == row["component_id"]
    assert plan["preserve_existing_identity"] is True
    assert plan["preserve_existing_exact_sequence"] is True
    assert plan["create_second_registry_row"] is False
    assert plan["change_formal_selectable_automatically"] is False
    assert plan["mutation_executed"] is False

    assert len(row["sequence"]) == 253
    assert hashlib.sha256(row["sequence"].encode("ascii")).hexdigest() == COMPONENT_SHA256
    assert row["sequence_sha256"] == COMPONENT_SHA256
    assert row["accession_version"] == "AF485783.1"
    assert row["component_type"] == "three_prime_regulatory_region"
    assert "formal_selectable" not in row


def test_package_does_not_embed_the_exact_component_sequence():
    row = _registry_row()
    exact_sequence = row["sequence"]

    for path in PACKAGE.iterdir():
        if path.is_file():
            assert exact_sequence not in path.read_text(encoding="utf-8")


def test_review_package_records_required_boundaries_and_no_go_verdict():
    review = (PACKAGE / "REVIEW_PACKAGE.md").read_text(encoding="utf-8")

    assert "Public accessibility is not treated as licence permission" in review
    assert "no second Registry row" in review
    assert "Make no automatic `formal_selectable` change" in review
    assert "RICE_NOS_ADMISSION_BLOCKERS_REMAIN" in review
    assert "RICE_NOS_ADMISSION_BLOCKERS_CLOSED_READY_FOR_REVIEW" not in review
