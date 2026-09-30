from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

from Bio import SeqIO
import pytest

import services.plant_component_workflow_registry as registry_service
from services.agent_product_adapter import AgentProductAdapter
from services.formal_step3_component_authority import (
    formal_agent_component_admission,
    formal_step3_component_options,
)
from services.mvp_multi_tu_persistence import (
    MvpMultiTuPersistenceError,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import (
    PlantComponentRegistryError,
    build_registry_selection,
    registry_record,
    registry_record_is_admissible,
    workflow_component_options,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
E8 = "PCLV1-PRO-E8-2164"
HSP = "PCLV1-TER-HSP18-2-250"
TOMATO = "Solanum lycopersicum"
ARABIDOPSIS = "Arabidopsis thaliana"


def _user_input(name: str, sequence: str) -> dict[str, object]:
    return {
        "display_name": name,
        "raw_text": sequence,
        "source_type": "paste",
        "source_format": "plain",
        "source_name": "user input",
        "provenance_reference": "",
    }


def _registry_input(component_id: str, role: str, host: str) -> dict[str, object]:
    reference = build_registry_selection(
        component_id,
        role=role,
        requested_host=host,
    )
    return {
        "display_name": reference["display_name"],
        "raw_text": reference["selected_sequence"],
        "source_type": "REGISTRY",
        "source_format": "plain",
        "source_name": reference["accession_version"],
        "provenance_reference": reference["provenance_origin"],
        "component_reference": reference,
    }


def _tomato_result() -> dict[str, object]:
    result = generate_multi_tu_combined_construct(
        project_id="plant-authority-closure-r1",
        project_name="Plant authority closure R1 trace",
        expression_units=[
            {
                "unit_id": "tu-1",
                "display_name": "TU 1",
                "order": 1,
                "orientation": "forward",
                "promoter": _registry_input(E8, "promoter", TOMATO),
                "cds": _user_input("User CDS", "ATGGCCGCCTAA"),
                "3_prime_regulatory_region": _registry_input(
                    HSP, "3_prime_regulatory_region", TOMATO
                ),
            }
        ],
    )
    result["formal_project_context"] = {
        "host_key": TOMATO,
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }
    return result


@pytest.mark.parametrize(
    ("component_id", "length", "digest", "accession", "coordinates"),
    (
        (E8, 2164, "ee18d306f8a4cddfe4cb0f7822500127641a188b4b475e3890a4a62e72add427", "KJ561284.1", "1..2164"),
        (HSP, 250, "f64cc0a9ffd000d281dc8d75163b072d42ec8184ad216470461941a4e61dfd1d", "PP558908.1", "852..1101"),
    ),
)
def test_admitted_identity_is_exact_and_attribution_bound(
    component_id: str,
    length: int,
    digest: str,
    accession: str,
    coordinates: str,
) -> None:
    record = registry_record(component_id)
    sequence = record["sequence"]
    attribution = record["attribution"]

    assert registry_record_is_admissible(record)
    assert len(sequence) == record["sequence_length"] == length
    assert hashlib.sha256(sequence.encode("ascii")).hexdigest() == digest
    assert record["sequence_sha256"] == attribution["feature_sha256"] == digest
    assert record["accession_version"] == attribution["accession_version"] == accession
    assert attribution["source_coordinates_one_based_inclusive"] == coordinates
    assert attribution["component_contract_version"] == record[
        "governance_decision_version"
    ]


def test_host_and_role_shortlists_fail_closed() -> None:
    assert [
        row["registry_component_id"]
        for row in workflow_component_options(role="promoter", target_host_species=TOMATO)
    ] == [E8]
    assert [
        row["registry_component_id"]
        for row in workflow_component_options(
            role="3_prime_regulatory_region", target_host_species=TOMATO
        )
    ] == [HSP]
    assert [
        row["registry_component_id"]
        for row in workflow_component_options(
            role="3_prime_regulatory_region", target_host_species=ARABIDOPSIS
        )
    ] == [HSP]

    for host in ("Oryza sativa", "Nicotiana benthamiana", "Zea mays", "Glycine max"):
        assert workflow_component_options(role="promoter", target_host_species=host) == []
        assert workflow_component_options(
            role="3_prime_regulatory_region", target_host_species=host
        ) == []

    with pytest.raises(PlantComponentRegistryError, match="not allowed for role"):
        build_registry_selection(E8, role="3_prime_regulatory_region", requested_host=TOMATO)
    with pytest.raises(PlantComponentRegistryError, match="requested host"):
        build_registry_selection(E8, role="promoter", requested_host=ARABIDOPSIS)


def test_formal_step3_and_agent_share_one_tomato_pair() -> None:
    promoter = formal_step3_component_options(role="promoter", target_host_species=TOMATO)
    three_prime = formal_step3_component_options(
        role="3_prime_regulatory_region", target_host_species=TOMATO
    )
    assert [item["registry_component_id"] for item in promoter] == [E8]
    assert [item["registry_component_id"] for item in three_prime] == [HSP]

    formal = formal_agent_component_admission(
        workflow_type="single_gene", target_host_species=TOMATO
    )
    formal_ids = {
        role["role"]: {option["registry_component_id"] for option in role["options"]}
        for role in formal["roles"]
    }
    assert formal_ids == {
        "promoter": {E8},
        "3_prime_regulatory_region": {HSP},
    }
    shortlist = AgentProductAdapter().component_shortlist(
        workflow_type="single_gene", host=TOMATO
    )
    assert {
        role["role"]: {option["component_id"] for option in role["options"]}
        for role in shortlist["roles"]
    } == formal_ids


@pytest.mark.parametrize(
    "mutation",
    (
        lambda row: row.update(sequence_sha256="0" * 64),
        lambda row: row["host_applicability"].update(evidence_version=""),
        lambda row: row.update(rights_classification="RIGHTS_REVIEW_REQUIRED"),
        lambda row: row.update(workflow_admission_status="blocked"),
        lambda row: row.update(role_semantics_reviewed=False),
        lambda row: row["attribution"].update(feature_sha256="0" * 64),
    ),
)
def test_direct_use_contract_rejects_drift(mutation) -> None:
    record = copy.deepcopy(registry_record(E8))
    mutation(record)
    assert registry_record_is_admissible(record) is False


@pytest.mark.parametrize(
    "locator",
    (
        "",
        "docs/qa/does-not-exist.json",
        "../outside-governed-tree.json",
    ),
)
def test_direct_use_rejects_empty_missing_or_malformed_governance_locator(
    locator: str,
) -> None:
    record = copy.deepcopy(registry_record(E8))
    record["governance_decision_source"] = locator
    assert registry_record_is_admissible(record) is False


@pytest.mark.parametrize(
    "locator",
    (
        r"C:\governance\sealed-evidence.json",
        r"docs\qa\sealed-evidence.json",
        r"docs\qa\..\..\..\outside-governed-tree.json",
    ),
)
def test_direct_use_rejects_windows_absolute_backslash_and_traversal_locators(
    locator: str,
) -> None:
    record = copy.deepcopy(registry_record(E8))
    record["governance_decision_source"] = locator

    assert registry_record_is_admissible(record) is False


def test_direct_use_rejects_altered_rights_locator() -> None:
    record = copy.deepcopy(registry_record(E8))
    record["attribution"]["rights_caveat_reference"] = (
        "docs/qa/does-not-exist.md"
    )
    assert registry_record_is_admissible(record) is False


def _copy_governance_evidence(destination_root: Path) -> None:
    for relative_path in registry_service.GOVERNANCE_EVIDENCE_SHA256:
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, destination)


def test_direct_use_rejects_governed_evidence_byte_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_governance_evidence(tmp_path)
    monkeypatch.setattr(registry_service, "REPOSITORY_ROOT", tmp_path)
    evidence_path = tmp_path / registry_service._B2C_ADMISSION_PATH
    evidence_path.write_bytes(evidence_path.read_bytes() + b"\n")

    assert registry_record_is_admissible(registry_record(E8)) is False


def test_direct_use_rejects_stale_expected_evidence_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_governance_evidence(tmp_path)
    monkeypatch.setattr(registry_service, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setitem(
        registry_service.GOVERNANCE_EVIDENCE_SHA256,
        registry_service._B2C_ADMISSION_PATH,
        "0" * 64,
    )

    assert registry_record_is_admissible(registry_record(E8)) is False


def test_direct_use_rejects_wrong_sealed_evidence_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = copy.deepcopy(registry_record(E8))
    policy_key = (E8, record["governance_decision_version"])
    wrong_path = registry_service._HSP_TOMATO_SCOPE_PATH
    policy = copy.deepcopy(registry_service.GOVERNANCE_EVIDENCE_POLICIES[policy_key])
    policy["governance_locators"] = (
        registry_service._B2B_RIGHTS_PATH,
        registry_service._B2C_ADMISSION_PATH,
        wrong_path,
    )
    monkeypatch.setitem(
        registry_service.GOVERNANCE_EVIDENCE_POLICIES, policy_key, policy
    )
    record["governance_decision_source"] = "; ".join(
        policy["governance_locators"]
    )

    assert registry_record_is_admissible(record) is False


def test_assisted_reference_and_nonadmitted_records_stay_closed() -> None:
    for component_id in (
        "PCLV1-PRO-UBQ10",
        "PCLV1-PRO-35S-835",
        "PCLV1-3REG-NOS-256",
    ):
        assert registry_record_is_admissible(registry_record(component_id)) is False
    assert formal_step3_component_options(
        role="promoter", target_host_species=ARABIDOPSIS
    ) == []


def test_tomato_pair_save_cold_reopen_and_exports_are_canonical(tmp_path: Path) -> None:
    result = _tomato_result()
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    canonical = reopened["combined_construct"]["dna"]
    fasta = SeqIO.read(
        StringIO(reopened["exports"]["combined_construct_fasta"]["data"]), "fasta"
    )
    genbank = SeqIO.read(
        StringIO(reopened["exports"]["combined_construct_genbank"]["data"]),
        "genbank",
    )
    feature_ids = {
        (feature.qualifiers.get("component_id") or [""])[0]
        for feature in genbank.features
    }

    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    assert registry_record(E8)["sequence"] in canonical
    assert registry_record(HSP)["sequence"] in canonical
    assert {E8, HSP} <= feature_ids
    assert reopened["registry_comparisons"]["tu-1"]["promoter"]["status"] == "current"
    assert reopened["registry_comparisons"]["tu-1"]["3_prime_regulatory_region"]["status"] == "current"


def test_cold_reopen_rejects_current_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", registry_path)
    result = _tomato_result()
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        result, repository=repository, registry_path=registry_path
    )
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    e8 = next(row for row in payload["records"] if row["component_id"] == E8)
    e8["host_applicability"]["evidence_version"] = "stale"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MvpMultiTuPersistenceError, match="current approved record"):
        open_mvp_multi_tu_design(
            saved.project_id,
            repository=repository,
            registry_path=registry_path,
        )


def test_cold_reopen_rejects_disappeared_governance_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    for relative_path in registry_service.GOVERNANCE_EVIDENCE_SHA256:
        source = ROOT / relative_path
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(registry_service, "REPOSITORY_ROOT", tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _tomato_result(), repository=repository, registry_path=registry_path
    )
    (tmp_path / registry_service._B2C_ADMISSION_PATH).unlink()

    with pytest.raises(MvpMultiTuPersistenceError, match="not admitted"):
        open_mvp_multi_tu_design(
            saved.project_id,
            repository=PlantProjectDraftRepository(repository.storage_dir),
            registry_path=registry_path,
        )


def test_cold_reopen_in_fresh_process_rejects_wrong_sealed_document_identity(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    evidence_root = tmp_path / "evidence-root"
    _copy_governance_evidence(evidence_root)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _tomato_result(), repository=repository, registry_path=registry_path
    )

    wrong_document = (
        evidence_root / registry_service._B2B_RIGHTS_PATH
    ).read_bytes()
    replaced_document = evidence_root / registry_service._B2C_ADMISSION_PATH
    replaced_document.write_bytes(wrong_document)
    wrong_digest = hashlib.sha256(wrong_document).hexdigest()
    code = "\n".join(
        (
            "from pathlib import Path",
            "import services.plant_component_workflow_registry as registry_service",
            "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design",
            "from services.plant_project_draft_repository import PlantProjectDraftRepository",
            f"registry_service.REPOSITORY_ROOT = Path({str(evidence_root)!r})",
            (
                "registry_service.GOVERNANCE_EVIDENCE_SHA256["
                f"registry_service._B2C_ADMISSION_PATH] = {wrong_digest!r}"
            ),
            (
                f"open_mvp_multi_tu_design({saved.project_id!r}, "
                f"repository=PlantProjectDraftRepository(Path({str(repository.storage_dir)!r})), "
                f"registry_path=Path({str(registry_path)!r}))"
            ),
        )
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT), environment.get("PYTHONPATH", ""))
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode != 0
    assert "not admitted" in completed.stderr
