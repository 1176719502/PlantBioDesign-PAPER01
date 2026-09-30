from __future__ import annotations

import copy
import hashlib
import json
from io import StringIO
from pathlib import Path
import sqlite3

from Bio import SeqIO
import pytest

import services.plant_component_workflow_registry as registry_service
from services.formal_report_snapshot import (
    FormalReportSnapshotError,
    build_multi_tu_snapshot,
)
from services.mvp_multi_tu_persistence import (
    MVP_MULTI_TU_PERSISTENCE_KEY,
    MvpMultiTuPersistenceError,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import (
    PlantComponentRegistryError,
    admit_registry_selection,
    build_registry_selection,
    build_user_provided_selection,
    load_registry_document,
    registry_record_is_admissible,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
)


HOST = "Oryza sativa"
REGISTRY_VERSION = "registry-v1-governed-test"


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


def _sha(sequence: str) -> str:
    return hashlib.sha256(sequence.upper().encode("ascii")).hexdigest()


def _record(component_id: str, component_type: str, sequence: str) -> dict[str, object]:
    source_digest = hashlib.sha256(
        f"synthetic source:{component_id}".encode("ascii")
    ).hexdigest()
    return {
        "component_id": component_id,
        "display_name": component_id,
        "component_type": component_type,
        "component_role": component_type,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": _sha(sequence),
        "accession_version": f"{component_id}.1",
        "source_sequence_length": len(sequence),
        "source_organism": HOST,
        "target_host_species": [HOST],
        "evidence_level": "E1",
        "source_record": f"synthetic/{component_id}.gb",
        "source_record_sha256": source_digest,
        "feature_boundary_method": {
            "method": "synthetic exact boundary",
            "start_one_based": 1,
            "end_one_based_inclusive": len(sequence),
            "strand": "+",
        },
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
            "scope": [HOST],
            "evidence_source": "synthetic-host-review",
            "evidence_version": "host-r1",
            "limitation": "Synthetic test evidence; no biological performance conclusion.",
        },
        "attribution": {
            "source_database": "synthetic test fixture",
            "record_locator": f"synthetic://{component_id}.1",
            "accession_version": f"{component_id}.1",
            "submitter_source_context": "Synthetic controlled test fixture.",
            "publication_citations": ["Synthetic controlled test citation."],
            "source_coordinates_one_based_inclusive": f"1..{len(sequence)}",
            "strand": "+",
            "feature_type": f"synthetic {component_type}",
            "retrieval_date": "2026-09-18",
            "source_record_sha256": source_digest,
            "feature_sha256": _sha(sequence),
            "rights_caveat_reference": "synthetic test fixture rights",
            "component_contract_version": "decision-r1",
            "required_notice": "Synthetic test fixture only.",
        },
    }


def _write_registry(tmp_path: Path) -> Path:
    path = tmp_path / "registry.json"
    payload = {
        "registry_version": REGISTRY_VERSION,
        "records": [
            _record("TEST-PROMOTER", "promoter", "ACGTACGTACGT"),
            _record("TEST-CDS", "cds", "ATGGCCGCCTAA"),
            _record(
                "TEST-3REG",
                "three_prime_regulatory_region",
                "TTTTACGTACGT",
            ),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _initialize_project_history_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE project_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                version INTEGER,
                chassis TEXT,
                design_data TEXT,
                created_at TEXT,
                creator TEXT,
                status TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def _selection(registry_path: Path, component_id: str, role: str) -> dict[str, object]:
    return build_registry_selection(
        component_id,
        role=role,
        requested_host=HOST,
        path=registry_path,
    )


def _registry_input(registry_path: Path, component_id: str, role: str) -> dict[str, object]:
    reference = _selection(registry_path, component_id, role)
    return {
        "display_name": reference["display_name"],
        "raw_text": reference["selected_sequence"],
        "source_type": "REGISTRY",
        "source_format": "plain",
        "source_name": reference["accession_version"],
        "provenance_reference": reference["provenance_origin"],
        "component_reference": reference,
    }


def _registry_result(
    registry_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", registry_path)
    result = generate_multi_tu_combined_construct(
        project_id="registry-impl02-project",
        project_name="Registry Impl-02 project",
        expression_units=[
            {
                "unit_id": "tu-1",
                "display_name": "TU 1",
                "order": 1,
                "orientation": "forward",
                "promoter": _registry_input(
                    registry_path, "TEST-PROMOTER", "promoter"
                ),
                "cds": _registry_input(registry_path, "TEST-CDS", "cds"),
                "3_prime_regulatory_region": _registry_input(
                    registry_path,
                    "TEST-3REG",
                    "3_prime_regulatory_region",
                ),
            }
        ],
    )
    result["formal_project_context"] = {
        "host_key": HOST,
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }
    return result


def _user_provided_result() -> dict[str, object]:
    promoter = build_user_provided_selection(
        role="promoter",
        display_name="User promoter",
        sequence="ACGTACGTACGT",
        reference_component_id="REFERENCE-PROMOTER",
        reference_registry_version="reference-catalog-r1",
    )
    return generate_multi_tu_combined_construct(
        project_id="user-provided-project",
        project_name="User-provided project",
        expression_units=[
            {
                "unit_id": "tu-user",
                "display_name": "User TU",
                "order": 1,
                "orientation": "forward",
                "promoter": {
                    "display_name": "User promoter",
                    "raw_text": promoter["selected_sequence"],
                    "component_reference": promoter,
                },
                "cds": {"display_name": "User CDS", "raw_text": "ATGGCCGCCTAA"},
                "3_prime_regulatory_region": {
                    "display_name": "User 3-prime region",
                    "raw_text": "TTTTACGTACGT",
                },
            }
        ],
    )


def _saved_selection(document: dict[str, object], role: str = "promoter") -> dict[str, object]:
    snapshot = document["manual_review_state"][MVP_MULTI_TU_PERSISTENCE_KEY]
    return snapshot["original_input"]["expression_units"][0][role][
        "component_reference"
    ]


def _recompute_selection_digest(selection: dict[str, object]) -> None:
    payload = copy.deepcopy(selection)
    payload.pop("snapshot_sha256", None)
    payload.pop("registry_comparison", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    selection["snapshot_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_selection_snapshot_persists_governance_sequence_host_and_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = _write_registry(tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    result = _registry_result(registry_path, monkeypatch)

    saved = save_mvp_multi_tu_design(
        result, repository=repository, registry_path=registry_path
    )
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
        registry_path=registry_path,
    )
    reference = reopened["original_input"]["expression_units"][0]["promoter"][
        "component_reference"
    ]

    assert reference["selection_source"] == "REGISTRY"
    assert reference["registry_component_id"] == "TEST-PROMOTER"
    assert reference["registry_version"] == REGISTRY_VERSION
    assert reference["distribution_mode_at_selection"] == "bundled"
    assert reference["sequence_availability_at_selection"] == "local_verified"
    assert reference["workflow_admission_status_at_selection"] == "eligible"
    assert reference["governance_decision_source"] == "synthetic-governance-record"
    assert reference["governance_decision_version"] == "decision-r1"
    assert reference["provenance_origin"] == "synthetic/TEST-PROMOTER.gb"
    assert reference["requested_host"] == HOST
    assert reference["host_applicability_at_selection"]["scope"] == [HOST]
    assert reference["selected_sequence"] == "ACGTACGTACGT"
    assert reference["selected_length"] == 12
    assert reference["sequence_sha256"] == _sha("ACGTACGTACGT")
    assert reopened["registry_comparisons"]["tu-1"]["promoter"]["status"] == "current"

    canonical = reopened["combined_construct"]["dna"]
    fasta = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_fasta"]["data"]),
            "fasta",
        )
    )
    genbank = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_genbank"]["data"]),
            "genbank",
        )
    )
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical


def test_sqlite_formal_save_and_fresh_reopen_preserve_registry_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = _write_registry(tmp_path)
    database_path = tmp_path / "formal-projects.db"
    _initialize_project_history_database(database_path)
    repository = SqlitePlantProjectDraftRepository(database_path)

    saved = save_mvp_multi_tu_design(
        _registry_result(registry_path, monkeypatch),
        repository=repository,
        registry_path=registry_path,
    )
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=SqlitePlantProjectDraftRepository(database_path),
        registry_path=registry_path,
    )
    reference = reopened["original_input"]["expression_units"][0]["promoter"][
        "component_reference"
    ]

    assert reference["source_type"] == "REGISTRY"
    assert reference["selection_source"] == "REGISTRY"
    assert reference["registry_component_id"] == "TEST-PROMOTER"
    assert reference["registry_version"] == REGISTRY_VERSION
    assert reference["distribution_mode_at_selection"] == "bundled"
    assert reference["sequence_availability_at_selection"] == "local_verified"
    assert reference["workflow_admission_status_at_selection"] == "eligible"
    assert reference["governance_decision_source"] == "synthetic-governance-record"
    assert reference["governance_decision_version"] == "decision-r1"
    assert reference["requested_host"] == HOST
    assert reference["host_applicability_at_selection"] == {
        "status": "reviewed",
        "scope": [HOST],
        "evidence_source": "synthetic-host-review",
        "evidence_version": "host-r1",
        "limitation": "Synthetic test evidence; no biological performance conclusion.",
    }
    assert reference["selected_sequence"] == "ACGTACGTACGT"
    assert reference["selected_length"] == 12
    assert reference["sequence_sha256"] == _sha("ACGTACGTACGT")
    assert reopened["registry_comparisons"]["tu-1"]["promoter"]["status"] == "current"
    assert admit_registry_selection(
        reference,
        role="promoter",
        sequence=reference["selected_sequence"],
        path=registry_path,
    ) == reference

    canonical = reopened["combined_construct"]["dna"]
    fasta = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_fasta"]["data"]),
            "fasta",
        )
    )
    genbank = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_genbank"]["data"]),
            "genbank",
        )
    )
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda ref: ref.__setitem__("selected_sequence", "AAAA"),
            id="selected-sequence-changed",
        ),
        pytest.param(
            lambda ref: ref.pop("selected_sequence"),
            id="selected-sequence-removed",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("selected_length", 4),
            id="sequence-length-changed",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("sequence_sha256", "0" * 64),
            id="sequence-sha-changed",
        ),
        pytest.param(
            lambda ref: ref.pop("distribution_mode_at_selection"),
            id="distribution-mode-removed",
        ),
        pytest.param(
            lambda ref: ref.pop("sequence_availability_at_selection"),
            id="sequence-availability-removed",
        ),
        pytest.param(
            lambda ref: ref.pop("workflow_admission_status_at_selection"),
            id="workflow-admission-removed",
        ),
        pytest.param(
            lambda ref: ref.__setitem__(
                "distribution_mode_at_selection", "reference_only"
            ),
            id="distribution-mode-altered",
        ),
        pytest.param(
            lambda ref: ref.__setitem__(
                "sequence_availability_at_selection", "unavailable"
            ),
            id="sequence-availability-altered",
        ),
        pytest.param(
            lambda ref: ref.__setitem__(
                "workflow_admission_status_at_selection", "blocked"
            ),
            id="workflow-admission-altered",
        ),
        pytest.param(
            lambda ref: ref.pop("governance_decision_source"),
            id="governance-source-removed",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("governance_decision_source", "other-source"),
            id="governance-source-altered",
        ),
        pytest.param(
            lambda ref: ref.pop("governance_decision_version"),
            id="governance-version-removed",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("governance_decision_version", "decision-r2"),
            id="governance-version-altered",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("registry_component_id", "OTHER"),
            id="component-identity-altered",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("registry_version", "registry-v2"),
            id="registry-version-altered",
        ),
    ],
)
def test_tampered_saved_registry_selection_fails_even_after_generic_digest_recompute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
) -> None:
    registry_path = _write_registry(tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _registry_result(registry_path, monkeypatch),
        repository=repository,
        registry_path=registry_path,
    )
    project_path = repository.storage_dir / f"{saved.project_id}.json"
    document = json.loads(project_path.read_text(encoding="utf-8"))
    reference = _saved_selection(document)
    mutation(reference)
    _recompute_selection_digest(reference)
    project_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MvpMultiTuPersistenceError):
        open_mvp_multi_tu_design(
            saved.project_id, repository=repository, registry_path=registry_path
        )


def test_legacy_registry_selection_remains_readable_but_formal_reopen_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = _write_registry(tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _registry_result(registry_path, monkeypatch),
        repository=repository,
        registry_path=registry_path,
    )
    project_path = repository.storage_dir / f"{saved.project_id}.json"
    document = json.loads(project_path.read_text(encoding="utf-8"))
    reference = _saved_selection(document)
    for field in (
        "registry_selection_contract_version",
        "selection_source",
        "distribution_mode_at_selection",
        "sequence_availability_at_selection",
        "workflow_admission_status_at_selection",
        "governance_decision_source",
        "governance_decision_version",
        "provenance_origin",
        "requested_host",
        "host_applicability_at_selection",
    ):
        reference.pop(field, None)
    _recompute_selection_digest(reference)
    project_path.write_text(json.dumps(document), encoding="utf-8")

    assert repository.load(saved.project_id).project_id == saved.project_id
    with pytest.raises(MvpMultiTuPersistenceError, match="Legacy/unclassified"):
        open_mvp_multi_tu_design(
            saved.project_id, repository=repository, registry_path=registry_path
        )
    unchanged = json.loads(project_path.read_text(encoding="utf-8"))
    assert "registry_selection_contract_version" not in _saved_selection(unchanged)


@pytest.mark.parametrize(
    "drift",
    [
        "sequence",
        "governance",
        "removed",
        "registry_version",
    ],
)
def test_live_registry_drift_blocks_formal_reopen_without_mutating_saved_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    registry_path = _write_registry(tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _registry_result(registry_path, monkeypatch),
        repository=repository,
        registry_path=registry_path,
    )
    project_path = repository.storage_dir / f"{saved.project_id}.json"
    before = json.loads(project_path.read_text(encoding="utf-8"))
    saved_reference = copy.deepcopy(_saved_selection(before))

    live = json.loads(registry_path.read_text(encoding="utf-8"))
    promoter = next(
        item for item in live["records"] if item["component_id"] == "TEST-PROMOTER"
    )
    if drift == "sequence":
        promoter["sequence"] = "CCCC"
        promoter["sequence_length"] = 4
        promoter["sequence_sha256"] = _sha("CCCC")
    elif drift == "governance":
        promoter["distribution_mode"] = "deferred"
        promoter["sequence_availability"] = "unavailable"
        promoter["workflow_admission_status"] = "blocked"
        promoter["sequence"] = None
        promoter.pop("sequence_length", None)
        promoter.pop("sequence_sha256", None)
    elif drift == "removed":
        live["records"] = [
            item for item in live["records"] if item["component_id"] != "TEST-PROMOTER"
        ]
    else:
        live["registry_version"] = "registry-v1-governed-test-r2"
    registry_path.write_text(json.dumps(live), encoding="utf-8")

    with pytest.raises(MvpMultiTuPersistenceError):
        open_mvp_multi_tu_design(
            saved.project_id, repository=repository, registry_path=registry_path
        )
    after = json.loads(project_path.read_text(encoding="utf-8"))
    assert _saved_selection(after) == saved_reference


def test_user_provided_reference_link_survives_without_registry_provenance_elevation(
    tmp_path: Path,
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _user_provided_result(), repository=repository
    )
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    reference = reopened["original_input"]["expression_units"][0]["promoter"][
        "component_reference"
    ]

    assert reference["source_type"] == "USER_PROVIDED"
    assert reference["selected_sequence"] == "ACGTACGTACGT"
    assert reference["sequence_sha256"] == _sha("ACGTACGTACGT")
    assert reference["reference_component_link"]["authority"] == "non_authoritative_identity_link"
    assert reference["evidence_tier"] == "UNVERIFIED_USER_INPUT"
    assert "distribution_mode_at_selection" not in reference
    assert "governance_decision_source" not in reference
    with pytest.raises(PlantComponentRegistryError, match="REGISTRY selection"):
        admit_registry_selection(
            reference,
            role="promoter",
            sequence=reference["selected_sequence"],
        )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda ref: ref.__setitem__("registry_component_id", "TEST-PROMOTER"),
            id="registry-component-id-added",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("accession_version", "TEST-PROMOTER.1"),
            id="registry-accession-added",
        ),
        pytest.param(
            lambda ref: ref.update(
                {
                    "distribution_mode_at_selection": "bundled",
                    "sequence_availability_at_selection": "local_verified",
                    "workflow_admission_status_at_selection": "eligible",
                    "governance_decision_source": "synthetic-governance-record",
                    "governance_decision_version": "decision-r1",
                }
            ),
            id="registry-governance-added",
        ),
        pytest.param(
            lambda ref: ref.__setitem__("evidence_tier", "E1"),
            id="registry-evidence-altered",
        ),
    ],
)
def test_user_provided_payload_edit_cannot_escalate_registry_provenance_after_digest_recompute(
    tmp_path: Path, mutation
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(
        _user_provided_result(), repository=repository
    )
    project_path = repository.storage_dir / f"{saved.project_id}.json"
    document = json.loads(project_path.read_text(encoding="utf-8"))
    reference = _saved_selection(document)
    mutation(reference)
    _recompute_selection_digest(reference)
    project_path.write_text(json.dumps(document), encoding="utf-8")

    assert reference["source_type"] == "USER_PROVIDED"
    assert reference["reference_component_link"]["authority"] == (
        "non_authoritative_identity_link"
    )
    with pytest.raises(MvpMultiTuPersistenceError):
        open_mvp_multi_tu_design(
            saved.project_id,
            repository=PlantProjectDraftRepository(repository.storage_dir),
        )


def test_requested_host_requires_independent_reviewed_scope(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    with pytest.raises(PlantComponentRegistryError, match="requested host"):
        build_registry_selection(
            "TEST-PROMOTER",
            role="promoter",
            requested_host="Nicotiana benthamiana",
            path=registry_path,
        )

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["records"][0].pop("host_applicability")
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlantComponentRegistryError, match="not admitted"):
        build_registry_selection(
            "TEST-PROMOTER",
            role="promoter",
            requested_host=HOST,
            path=registry_path,
        )


def test_report_snapshot_reuses_registry_downstream_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = _write_registry(tmp_path)
    result = _registry_result(registry_path, monkeypatch)
    snapshot = build_multi_tu_snapshot(
        multi_tu_result=result, registry_path=registry_path
    )
    assert snapshot["workflow_type"] == "multi_tu"

    result["original_input"]["expression_units"][0]["promoter"][
        "component_reference"
    ].pop("governance_decision_version")
    with pytest.raises(FormalReportSnapshotError, match="blocks the formal report"):
        build_multi_tu_snapshot(multi_tu_result=result, registry_path=registry_path)


def test_current_registry_catalog_bytes_and_direct_admission_count_are_stable() -> None:
    before = registry_service.REGISTRY_PATH.read_bytes()
    payload = load_registry_document()
    assert len(payload["records"]) == 34
    assert {
        record["component_id"]
        for record in payload["records"]
        if registry_record_is_admissible(record)
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert registry_service.REGISTRY_PATH.read_bytes() == before
