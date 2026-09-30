from __future__ import annotations

import copy
import hashlib
import json
from io import StringIO
from pathlib import Path

from Bio import SeqIO
import pytest

from services import plant_component_workflow_registry as registry_service
from services.mvp_multi_tu_persistence import (
    MVP_MULTI_TU_PERSISTENCE_KEY,
    MvpMultiTuPersistenceError,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import (
    PlantComponentRegistryError,
    UNVERIFIED_USER_INPUT,
    build_registry_selection,
    build_user_provided_selection,
    library_view_records,
    load_registry_document,
    registry_records,
    workflow_component_options,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


@pytest.fixture(autouse=True)
def _synthetic_governance_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    production_resolver = registry_service._durable_governance_evidence

    def resolve(record: dict[str, object]) -> None:
        if record.get("governance_decision_source") == "synthetic-governance-record":
            attribution = record.get("attribution")
            assert isinstance(attribution, dict)
            if attribution.get("rights_caveat_reference") != "synthetic test fixture rights":
                raise PlantComponentRegistryError("Synthetic fixture rights evidence is invalid.")
            return
        production_resolver(record)

    monkeypatch.setattr(registry_service, "_durable_governance_evidence", resolve)


def _registry_input(component_id: str, role: str, registry_path: Path) -> dict[str, object]:
    reference = build_registry_selection(
        component_id,
        role=role,
        requested_host="Oryza sativa",
        path=registry_path,
    )
    return {
        "display_name": reference["display_name"],
        "raw_text": reference["selected_sequence"],
        "source_type": "REGISTRY",
        "source_format": "plain",
        "source_name": reference["accession_version"],
        "provenance_reference": reference["accession_version"],
        "component_reference": reference,
    }


def _user_input(role: str, name: str, sequence: str) -> dict[str, object]:
    return {
        "display_name": name,
        "raw_text": sequence,
        "source_type": "paste",
        "source_format": "plain",
        "source_name": "user input",
        "provenance_reference": "",
    }


def _write_governed_registry(tmp_path: Path) -> Path:
    records = [
        ("TEST-PRO", "Synthetic promoter", "promoter", "AACCGGTT"),
        ("TEST-CDS", "Synthetic CDS", "cds", "ATGGCCGCCTAA"),
        ("TEST-3PR", "Synthetic 3-prime region", "three_prime_regulatory_region", "TTTTACGT"),
        ("TEST-5PR", "Synthetic five-prime region", "five_prime_utr", "CCGGAATT"),
    ]
    payload_records = []
    for component_id, display_name, component_type, sequence in records:
        source_digest = hashlib.sha256(
            f"synthetic source:{component_id}".encode("ascii")
        ).hexdigest()
        payload_records.append(
            {
                "component_id": component_id,
                "display_name": display_name,
                "component_type": component_type,
                "sequence": sequence,
                "sequence_length": len(sequence),
                "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                "source_organism": "synthetic source",
                "target_host_species": ["Oryza sativa"],
                "host_group": ["monocot"],
                "accession": f"SYN-{component_id}",
                "accession_version": f"SYN-{component_id}.1",
                "source_sequence_length": len(sequence),
                "primary_reference": "synthetic governed fixture",
                "evidence_level": "E1",
                "feature_boundary_method": {
                    "method": "synthetic fixture boundary",
                    "start_one_based": 1,
                    "end_one_based_inclusive": len(sequence),
                    "strand": "+",
                },
                "source_record": f"synthetic/{component_id}.gb",
                "source_record_sha256": source_digest,
                "redistribution_status": "SYNTHETIC_TEST_FIXTURE",
                "distribution_mode": "bundled",
                "sequence_availability": "local_verified",
                "workflow_admission_status": "eligible",
                "governance_decision_source": "synthetic-governance-record",
                "governance_decision_version": "decision-r1",
                "rights_classification": "RIGHTS_CLEAR_FOR_CURRENT_USE",
                "review_status": "source_and_boundary_reviewed",
                "role_semantics_reviewed": True,
                "host_applicability_reviewed": True,
                "alias_collision_reviewed": True,
                "formal_export_compatible": True,
                "host_applicability": {
                    "status": "reviewed",
                    "scope": ["Oryza sativa"],
                    "evidence_source": "synthetic-host-review",
                    "evidence_version": "host-r1",
                    "limitation": "Synthetic fixture; no biological performance conclusion.",
                },
                "attribution": {
                    "source_database": "synthetic test fixture",
                    "record_locator": f"synthetic://SYN-{component_id}.1",
                    "accession_version": f"SYN-{component_id}.1",
                    "submitter_source_context": "Synthetic controlled test fixture.",
                    "publication_citations": ["Synthetic controlled test citation."],
                    "source_coordinates_one_based_inclusive": f"1..{len(sequence)}",
                    "strand": "+",
                    "feature_type": f"synthetic {component_type}",
                    "retrieval_date": "2026-09-18",
                    "source_record_sha256": source_digest,
                    "feature_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                    "rights_caveat_reference": "synthetic test fixture rights",
                    "component_contract_version": "decision-r1",
                    "required_notice": "Synthetic test fixture only.",
                },
            }
        )
    path = tmp_path / "governed-registry.json"
    path.write_text(
        json.dumps({"registry_version": "synthetic-governed-v1", "records": payload_records}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def governed_registry_path(tmp_path: Path) -> Path:
    return _write_governed_registry(tmp_path)


def _mixed_two_tu_result(registry_path: Path) -> dict[str, object]:
    units = [
        {
            "unit_id": "trace-tu-1",
            "display_name": "Registry TU",
            "order": 1,
            "orientation": "forward",
            "promoter": _registry_input("TEST-PRO", "promoter", registry_path),
            "cds": _registry_input("TEST-CDS", "cds", registry_path),
            "3_prime_regulatory_region": _registry_input(
                "TEST-3PR", "3_prime_regulatory_region", registry_path
            ),
        },
        {
            "unit_id": "trace-tu-2",
            "display_name": "User TU",
            "order": 2,
            "orientation": "reverse",
            "promoter": _user_input("promoter", "User promoter", "ACGTACGTACGT"),
            "cds": _user_input("cds", "User CDS", "ATGGCCGCCTAA"),
            "3_prime_regulatory_region": _user_input(
                "3_prime_regulatory_region", "User 3-prime region", "TTTTACGTACGT"
            ),
        },
    ]
    result = generate_multi_tu_combined_construct(
        project_id="registry-trace-project",
        project_name="Registry trace project",
        expression_units=units,
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }
    return result


def test_registry_inventory_and_formal_display_are_the_same_expanded_records() -> None:
    payload = load_registry_document()
    records = registry_records()
    display = library_view_records()

    assert payload["registry_version"] == "v1-publication-minimum-expansion-20260824-draft"
    assert len(records) == len(display) == 34
    assert sum(item["evidence_level"] == "E1" for item in records) == 24
    assert sum(item["evidence_level"] == "E2" for item in records) == 10
    assert {item["component_id"] for item in records} == {
        item["registry_component_id"] for item in display
    }
    assert all("source_organism" in item and "target_host_species" in item for item in display)
    assert any(
        item["source_organism"] not in item["target_host_species"]
        for item in display
    )


def test_workflow_filters_keep_component_roles_distinct_and_exclude_vector(
    governed_registry_path: Path,
) -> None:
    catalog = library_view_records()
    assert len(catalog) == 34
    assert {
        item["registry_component_id"]
        for item in catalog
        if item["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert [
        item["registry_component_id"]
        for item in workflow_component_options(
            role="promoter", target_host_species="Solanum lycopersicum"
        )
    ] == ["PCLV1-PRO-E8-2164"]
    assert [
        item["registry_component_id"]
        for item in workflow_component_options(
            role="3_prime_regulatory_region",
            target_host_species="Solanum lycopersicum",
        )
    ] == ["PCLV1-TER-HSP18-2-250"]
    with pytest.raises(PlantComponentRegistryError, match="not admitted for direct selection"):
        build_registry_selection("PCLV1-PRO-35S-835", role="promoter")

    registry_path = governed_registry_path
    promoters = workflow_component_options(role="promoter", path=registry_path, target_host_species="Oryza sativa")
    cds = workflow_component_options(role="cds", path=registry_path, target_host_species="Oryza sativa")
    three_prime = workflow_component_options(
        role="3_prime_regulatory_region", path=registry_path, target_host_species="Oryza sativa"
    )
    five_prime = workflow_component_options(
        role="five_prime_region", path=registry_path, target_host_species="Oryza sativa"
    )

    assert len(promoters) == len(cds) == len(three_prime) == len(five_prime) == 1
    assert {item["component_type"] for item in three_prime} == {
        "three_prime_regulatory_region",
    }
    assert all(item["component_type"] != "vector_backbone" for item in promoters + cds + three_prime)
    with pytest.raises(PlantComponentRegistryError, match="not allowed for role"):
        build_registry_selection("TEST-CDS", role="promoter", requested_host="Oryza sativa", path=registry_path)


def test_user_selection_cannot_claim_registry_evidence_or_accession() -> None:
    selection = build_user_provided_selection(
        role="cds", display_name="Manual CDS", sequence="ATGGCCGCCTAA"
    )

    assert selection["source_type"] == "USER_PROVIDED"
    assert selection["evidence_tier"] == UNVERIFIED_USER_INPUT
    assert selection["registry_component_id"] == ""
    assert selection["accession_version"] == ""


def test_mixed_registry_and_user_components_reach_canonical_and_genbank_traceability(
    governed_registry_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", governed_registry_path)
    result = _mixed_two_tu_result(governed_registry_path)

    assert result["contains_vector"] is False
    assert [item["orientation"] for item in result["expression_units"]] == [
        "forward",
        "reverse",
    ]
    references = result["expression_units"][0]["component_references"]
    assert references["promoter"]["registry_component_id"] == "TEST-PRO"
    assert references["cds"]["evidence_tier"] == "E1"
    user_references = result["expression_units"][1]["component_references"]
    assert {item["source_type"] for item in user_references.values()} == {"USER_PROVIDED"}
    assert {item["evidence_tier"] for item in user_references.values()} == {
        UNVERIFIED_USER_INPUT
    }

    canonical = result["combined_construct"]["dna"]
    fasta = next(
        SeqIO.parse(
            StringIO(result["exports"]["combined_construct_fasta"]["data"]), "fasta"
        )
    )
    genbank = next(
        SeqIO.parse(
            StringIO(result["exports"]["combined_construct_genbank"]["data"]),
            "genbank",
        )
    )
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    traceable = [
        feature
        for feature in genbank.features
        if (feature.qualifiers.get("biological_role") or [""])[0]
        in {"promoter", "cds", "3_prime_regulatory_region"}
    ]
    assert len(traceable) == 6
    for feature in traceable:
        assert feature.qualifiers["component_id"]
        assert feature.qualifiers["component_type"]
        assert feature.qualifiers["accession_version"]
        assert feature.qualifiers["evidence_tier"]
        assert feature.qualifiers["source_organism"]
        assert feature.qualifiers["target_host_species"]
        assert feature.qualifiers["sequence_sha256"]
        assert feature.qualifiers["source_type"]


def test_save_cold_reopen_preserves_snapshots_boundaries_exports_and_detects_tampering(
    tmp_path: Path,
    governed_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", governed_registry_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    registry_path = governed_registry_path
    result = _mixed_two_tu_result(registry_path)
    saved = save_mvp_multi_tu_design(
        result, repository=repository, registry_path=registry_path
    )
    reopened = open_mvp_multi_tu_design(
        saved.project_id, repository=repository, registry_path=registry_path
    )

    assert reopened["original_input"] == result["original_input"]
    assert reopened["expression_units"] == result["expression_units"]
    assert reopened["combined_construct"] == result["combined_construct"]
    assert reopened["exports"] == result["exports"]
    assert reopened["registry_comparisons"]["trace-tu-1"]["promoter"]["status"] == "current"
    assert reopened["registry_comparisons"]["trace-tu-2"]["cds"]["status"] == "not_applicable"

    path = repository.storage_dir / f"{saved.project_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["manual_review_state"][MVP_MULTI_TU_PERSISTENCE_KEY]
    reference = snapshot["original_input"]["expression_units"][0]["promoter"][
        "component_reference"
    ]
    reference["evidence_tier"] = "E2"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(MvpMultiTuPersistenceError, match="checksum|modified"):
        open_mvp_multi_tu_design(saved.project_id, repository=repository)


def test_registry_selection_rejects_forged_id_sequence_and_metadata(
    governed_registry_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(PlantComponentRegistryError, match="does not exist"):
        build_registry_selection("PCLV1-FAKE", role="promoter")

    with pytest.raises(PlantComponentRegistryError, match="not admitted for direct selection"):
        build_registry_selection("PCLV1-PRO-35S-835", role="promoter")

    monkeypatch.setattr(registry_service, "REGISTRY_PATH", governed_registry_path)
    selected = build_registry_selection(
        "TEST-PRO",
        role="promoter",
        requested_host="Oryza sativa",
        path=governed_registry_path,
    )
    forged = copy.deepcopy(selected)
    forged["accession_version"] = "FAKE.1"
    with pytest.raises(PlantComponentRegistryError, match="checksum"):
        from services.plant_component_workflow_registry import validate_saved_selection

        validate_saved_selection(
            forged, role="promoter", sequence=forged["selected_sequence"]
        )
