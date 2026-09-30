from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import services.plant_component_workflow_registry as registry_service
from services.plant_component_workflow_registry import (
    CATALOG_DISTRIBUTION_MODES,
    CATALOG_SEQUENCE_AVAILABILITIES,
    CATALOG_WORKFLOW_ADMISSION_STATUSES,
    LEGACY_CATALOG_STATE,
    PlantComponentRegistryError,
    admit_registry_selection,
    build_registry_selection,
    build_user_provided_selection,
    catalog_governance_state,
    library_view_records,
    load_registry_document,
    registry_record_is_admissible,
    registry_records,
    validate_catalog_record,
    validate_saved_selection,
    workflow_component_options,
)


REGISTRY_ROOT = (
    Path(__file__).resolve().parents[1] / "data" / "plant_component_registry_v1"
)
SCHEMA = json.loads((REGISTRY_ROOT / "registry.schema.json").read_text(encoding="utf-8"))
SCHEMA_VALIDATOR = Draft202012Validator(SCHEMA)
GOVERNANCE_FIELDS = (
    "distribution_mode",
    "sequence_availability",
    "workflow_admission_status",
)
_MISSING = object()


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


def _record(
    state: tuple[str, str, str], sequence: object = _MISSING
) -> dict[str, object]:
    mode, availability, admission = state
    record: dict[str, object] = {
        "component_id": "TEST-1",
        "display_name": "Test CDS",
        "component_type": "cds",
        "source_record": "synthetic/TEST-1.gb",
        "distribution_mode": mode,
        "sequence_availability": availability,
        "workflow_admission_status": admission,
        "governance_decision_source": "synthetic-governance-record",
        "governance_decision_version": "decision-r1",
        "host_applicability": {
            "status": "reviewed",
            "scope": ["Oryza sativa"],
            "evidence_source": "synthetic-host-review",
            "evidence_version": "host-r1",
            "limitation": "Synthetic fixture; no biological performance conclusion.",
        },
    }
    if sequence is _MISSING and mode == "bundled":
        sequence = "ACGT"
    if sequence is not _MISSING:
        record["sequence"] = sequence
        if isinstance(sequence, str) and sequence:
            record["sequence_length"] = len(sequence)
            record["sequence_sha256"] = hashlib.sha256(
                sequence.upper().encode("ascii")
            ).hexdigest()
            if state == ("bundled", "local_verified", "eligible"):
                source_digest = hashlib.sha256(b"synthetic source record").hexdigest()
                record.update(
                    {
                        "accession_version": "TEST-1.1",
                        "source_sequence_length": len(sequence),
                        "source_record_sha256": source_digest,
                        "feature_boundary_method": {
                            "method": "synthetic exact boundary",
                            "start_one_based": 1,
                            "end_one_based_inclusive": len(sequence),
                            "strand": "+",
                        },
                        "rights_classification": "RIGHTS_CLEAR_FOR_CURRENT_USE",
                        "review_status": "source_and_boundary_reviewed",
                        "role_semantics_reviewed": True,
                        "host_applicability_reviewed": True,
                        "alias_collision_reviewed": True,
                        "formal_export_compatible": True,
                        "attribution": {
                            "source_database": "synthetic test fixture",
                            "record_locator": "synthetic://TEST-1.1",
                            "accession_version": "TEST-1.1",
                            "submitter_source_context": "Synthetic controlled test fixture.",
                            "publication_citations": ["Synthetic controlled test citation."],
                            "source_coordinates_one_based_inclusive": f"1..{len(sequence)}",
                            "strand": "+",
                            "feature_type": "synthetic CDS",
                            "retrieval_date": "2026-09-18",
                            "source_record_sha256": source_digest,
                            "feature_sha256": record["sequence_sha256"],
                            "rights_caveat_reference": "synthetic test fixture rights",
                            "component_contract_version": "decision-r1",
                            "required_notice": "Synthetic test fixture only.",
                        },
                    }
                )
    return record


def _legacy_record() -> dict[str, object]:
    sequence = "ACGT"
    return {
        "component_id": "LEGACY",
        "display_name": "Legacy CDS",
        "component_type": "cds",
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
    }


def _payload(record: dict[str, object]) -> dict[str, object]:
    return {"registry_version": "test", "records": [record]}


def _write_registry(tmp_path: Path, name: str, record: dict[str, object]) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(_payload(record)), encoding="utf-8")
    return path


def _write_payload(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _schema_accepts(record: dict[str, object]) -> bool:
    return SCHEMA_VALIDATOR.is_valid(_payload(record))


def _recompute_snapshot_hash(selection: dict[str, object]) -> None:
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
    selection["snapshot_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "state",
    [
        ("bundled", "local_verified", "eligible"),
        ("reference_only", "unavailable", "requires_sequence"),
        ("deferred", "unavailable", "blocked"),
    ],
)
def test_v1_governance_matrix_accepts_only_contract_states(state: tuple[str, str, str]) -> None:
    record = _record(state)
    assert _schema_accepts(record)
    assert catalog_governance_state(record) == state
    assert validate_catalog_record(record) == state
    assert registry_record_is_admissible(record) is (state[0] == "bundled")


@pytest.mark.parametrize(
    "state",
    [
        ("reference_only", "local_verified", "requires_sequence"),
        ("bundled", "unavailable", "eligible"),
        ("deferred", "unavailable", "eligible"),
        ("unknown", "unavailable", "blocked"),
        ("bundled", "unknown", "eligible"),
        ("bundled", "local_verified", "unknown"),
        ("", "", ""),
    ],
)
def test_invalid_governance_matrix_fails_closed(state: tuple[str, str, str]) -> None:
    with pytest.raises(PlantComponentRegistryError):
        validate_catalog_record(_record(state))
    assert registry_record_is_admissible(_record(state)) is False


def test_legacy_records_are_readable_but_not_admissible() -> None:
    legacy = _legacy_record()
    assert _schema_accepts(legacy)
    assert catalog_governance_state(legacy) == LEGACY_CATALOG_STATE
    assert validate_catalog_record(legacy) == LEGACY_CATALOG_STATE
    assert registry_record_is_admissible(legacy) is False


def test_loader_reads_legacy_fixture_without_upgrading_records(tmp_path) -> None:
    payload = {
        "registry_version": "test",
        "records": [
            {
                "component_id": "LEGACY",
                "sequence": "ACGT",
                "sequence_length": 4,
                "sequence_sha256": hashlib.sha256(b"ACGT").hexdigest(),
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_registry_document(path)
    assert "distribution_mode" not in loaded["records"][0]


@pytest.mark.parametrize(
    "state",
    [
        ("reference_only", "unavailable", "requires_sequence"),
        ("deferred", "unavailable", "blocked"),
    ],
)
def test_loader_reads_non_bundled_metadata_without_sequence(tmp_path, state) -> None:
    mode, availability, admission = state
    payload = {
        "registry_version": "test",
        "records": [
            {
                "component_id": "METADATA-ONLY",
                "distribution_mode": mode,
                "sequence_availability": availability,
                "workflow_admission_status": admission,
            }
        ],
    }
    path = tmp_path / f"{mode}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_registry_document(path)["records"][0]["component_id"] == "METADATA-ONLY"


def test_legacy_registry_selection_is_blocked_by_builder_gate() -> None:
    with pytest.raises(PlantComponentRegistryError, match="not admitted"):
        build_registry_selection("PCLV1-PRO-35S-835", role="promoter")


def test_only_bundled_local_verified_eligible_can_pass_direct_gate(tmp_path) -> None:
    sequence = "ACGT"
    record = _record(("bundled", "local_verified", "eligible"), sequence)
    record.update(
        {
            "component_id": "BUNDLED-CDS",
            "display_name": "Bundled CDS",
            "source_record": "synthetic/BUNDLED-CDS.gb",
        }
    )
    payload = {
        "registry_version": "test",
        "records": [record],
    }
    path = tmp_path / "bundled.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    selection = build_registry_selection(
        "BUNDLED-CDS", role="cds", requested_host="Oryza sativa", path=path
    )
    admitted = admit_registry_selection(
        selection, role="cds", sequence=sequence, path=path
    )
    assert admitted["distribution_mode"] == "bundled"
    assert admitted["sequence_availability"] == "local_verified"
    assert admitted["workflow_admission_status"] == "eligible"


def test_user_provided_selection_remains_separate_from_catalog_governance() -> None:
    selection = build_user_provided_selection(
        role="cds", display_name="Manual CDS", sequence="ATGGCCGCCTAA"
    )
    validated = validate_saved_selection(
        selection, role="cds", sequence=selection["selected_sequence"]
    )
    assert validated["source_type"] == "USER_PROVIDED"
    assert "distribution_mode" not in validated
    assert validated["registry_component_id"] == ""
    assert validated["selected_sequence"] == "ATGGCCGCCTAA"
    assert validated["sequence_sha256"] == hashlib.sha256(
        b"ATGGCCGCCTAA"
    ).hexdigest()
    assert validated["evidence_tier"] == "UNVERIFIED_USER_INPUT"
    assert validated["component_snapshot"] == {}


def test_governance_enums_are_closed() -> None:
    assert CATALOG_DISTRIBUTION_MODES == {"bundled", "reference_only", "deferred"}
    assert CATALOG_SEQUENCE_AVAILABILITIES == {"local_verified", "unavailable"}
    assert CATALOG_WORKFLOW_ADMISSION_STATUSES == {
        "eligible", "requires_sequence", "blocked"
    }


def test_schema_is_valid_and_accepts_governed_records_in_existing_catalog() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    payload = json.loads(
        (REGISTRY_ROOT / "registry.batch1.json").read_text(encoding="utf-8")
    )
    assert list(SCHEMA_VALIDATOR.iter_errors(payload)) == []
    assert len(payload["records"]) == 34
    governed = {
        record["component_id"]
        for record in payload["records"]
        if "distribution_mode" in record
    }
    assert governed == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}


def test_only_reviewed_e8_and_hsp18_2_records_are_directly_admissible() -> None:
    records = registry_records()
    assert len(records) == 34
    assert {
        record["component_id"]
        for record in records
        if registry_record_is_admissible(record)
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}


@pytest.mark.parametrize(
    ("component_id", "schema_accepts"),
    [
        ("BUNDLED-CDS", True),
        (123, False),
        (1.5, False),
        (True, False),
        (None, False),
        ("", False),
    ],
)
def test_component_id_schema_and_runtime_structural_parity(
    tmp_path: Path, component_id: object, schema_accepts: bool
) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record["component_id"] = component_id
    payload = _payload(record)
    assert SCHEMA_VALIDATOR.is_valid(payload) is schema_accepts
    path = _write_payload(tmp_path, f"component-id-{component_id!r}", payload)
    if schema_accepts:
        assert (
            load_registry_document(path)["records"][0]["component_id"]
            == component_id
        )
        assert build_registry_selection(
            str(component_id),
            role="cds",
            requested_host="Oryza sativa",
            path=path,
        )
    else:
        with pytest.raises(PlantComponentRegistryError):
            load_registry_document(path)


@pytest.mark.parametrize(
    ("registry_version", "schema_accepts"),
    [
        ("test", True),
        (123, False),
        (1.5, False),
        (True, False),
        (None, False),
        ("", False),
    ],
)
def test_registry_version_schema_and_runtime_structural_parity(
    tmp_path: Path, registry_version: object, schema_accepts: bool
) -> None:
    payload = _payload(_record(("bundled", "local_verified", "eligible")))
    payload["registry_version"] = registry_version
    assert SCHEMA_VALIDATOR.is_valid(payload) is schema_accepts
    path = _write_payload(tmp_path, f"registry-version-{registry_version!r}", payload)
    if schema_accepts:
        assert load_registry_document(path)["registry_version"] == registry_version
    else:
        with pytest.raises(PlantComponentRegistryError):
            load_registry_document(path)


def test_top_level_extra_property_is_rejected_by_schema_and_runtime(
    tmp_path: Path,
) -> None:
    payload = _payload(_record(("bundled", "local_verified", "eligible")))
    payload["unexpected"] = "must-not-be-ignored"
    assert not SCHEMA_VALIDATOR.is_valid(payload)
    path = _write_payload(tmp_path, "extra-top-level", payload)
    with pytest.raises(PlantComponentRegistryError, match="unsupported top-level"):
        load_registry_document(path)


def test_record_extension_remains_schema_and_runtime_admissible(
    tmp_path: Path,
) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record["documented_extension"] = "preserved"
    payload = _payload(record)
    assert SCHEMA_VALIDATOR.is_valid(payload)
    path = _write_payload(tmp_path, "record-extension", payload)
    assert (
        load_registry_document(path)["records"][0]["documented_extension"]
        == "preserved"
    )


def test_real_catalog_exposes_only_the_two_reviewed_formal_options() -> None:
    records = registry_records()
    rows = library_view_records()
    assert len(records) == 34
    assert sum(registry_record_is_admissible(record) for record in records) == 2
    assert sum(bool(row["formal_selectable"]) for row in rows) == 2
    assert [
        option["registry_component_id"]
        for option in workflow_component_options(
            role="promoter", target_host_species="Solanum lycopersicum"
        )
    ] == ["PCLV1-PRO-E8-2164"]
    assert [
        option["registry_component_id"]
        for option in workflow_component_options(
            role="3_prime_regulatory_region",
            target_host_species="Solanum lycopersicum",
        )
    ] == ["PCLV1-TER-HSP18-2-250"]
    assert workflow_component_options(role="cds") == []
    assert workflow_component_options(role="five_prime_region") == []


def test_governed_bundled_record_appears_in_workflow_options(tmp_path: Path) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record["component_id"] = "BUNDLED-CDS"
    path = _write_registry(tmp_path, "bundled-option", record)
    options = workflow_component_options(
        role="cds", target_host_species="Oryza sativa", path=path
    )
    assert [option["registry_component_id"] for option in options] == ["BUNDLED-CDS"]
    assert options[0]["formal_selectable"] is True
    assert options[0]["component_reference"]["distribution_mode"] == "bundled"


@pytest.mark.parametrize(
    "state",
    [
        ("reference_only", "unavailable", "requires_sequence"),
        ("deferred", "unavailable", "blocked"),
    ],
)
def test_valid_nonadmissible_governed_catalog_has_empty_workflow_options(
    tmp_path: Path, state: tuple[str, str, str]
) -> None:
    record = _record(state)
    path = _write_registry(tmp_path, state[0], record)
    assert library_view_records(path)[0]["formal_selectable"] is False
    assert workflow_component_options(role="cds", path=path) == []


def test_malformed_governed_catalog_is_not_hidden_as_empty_options(
    tmp_path: Path,
) -> None:
    record = _record(("bundled", "local_verified", "eligible"), "ACGN")
    payload = _payload(record)
    assert not SCHEMA_VALIDATOR.is_valid(payload)
    path = _write_payload(tmp_path, "invalid-dna", payload)
    with pytest.raises(PlantComponentRegistryError, match="invalid governance metadata"):
        workflow_component_options(role="cds", path=path)


def test_empty_registry_is_valid_but_grants_no_admission(tmp_path: Path) -> None:
    payload = {"registry_version": "empty-test", "records": []}
    assert SCHEMA_VALIDATOR.is_valid(payload)
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_registry_document(path)["records"] == []
    with pytest.raises(PlantComponentRegistryError, match="does not exist"):
        build_registry_selection("NOT-PRESENT", role="cds", path=path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("distribution_mode", "unknown"),
        ("distribution_mode", ""),
        ("sequence_availability", "unknown"),
        ("sequence_availability", ""),
        ("workflow_admission_status", "unknown"),
        ("workflow_admission_status", ""),
    ],
)
def test_schema_rejects_unknown_or_empty_governance_enums(
    field: str, value: str
) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record[field] = value
    assert not _schema_accepts(record)


@pytest.mark.parametrize(
    "state",
    [
        ("reference_only", "local_verified", "requires_sequence"),
        ("bundled", "unavailable", "eligible"),
        ("deferred", "unavailable", "eligible"),
    ],
)
def test_schema_rejects_invalid_governance_combinations(
    state: tuple[str, str, str],
) -> None:
    assert not _schema_accepts(_record(state))


@pytest.mark.parametrize("sequence", [_MISSING, None])
def test_reference_only_sequence_may_be_missing_or_null(
    tmp_path: Path, sequence: object
) -> None:
    record = _record(("reference_only", "unavailable", "requires_sequence"), sequence)
    assert _schema_accepts(record)
    assert validate_catalog_record(record) == (
        "reference_only",
        "unavailable",
        "requires_sequence",
    )
    path = _write_registry(tmp_path, "reference", record)
    assert load_registry_document(path)["records"][0]["component_id"] == "TEST-1"


def test_reference_only_empty_string_sequence_is_rejected(tmp_path: Path) -> None:
    record = _record(("reference_only", "unavailable", "requires_sequence"), "")
    assert not _schema_accepts(record)
    with pytest.raises(PlantComponentRegistryError, match="absent or null"):
        validate_catalog_record(record)
    path = _write_registry(tmp_path, "reference-empty", record)
    with pytest.raises(PlantComponentRegistryError):
        load_registry_document(path)


@pytest.mark.parametrize("missing_field", ["sequence", "sequence_length", "sequence_sha256"])
def test_malformed_bundled_missing_required_sequence_fact_is_inadmissible(
    tmp_path: Path, missing_field: str
) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record.pop(missing_field)
    assert not _schema_accepts(record)
    with pytest.raises(PlantComponentRegistryError):
        validate_catalog_record(record)
    assert registry_record_is_admissible(record) is False
    path = _write_registry(tmp_path, f"missing-{missing_field}", record)
    with pytest.raises(PlantComponentRegistryError):
        build_registry_selection("TEST-1", role="cds", path=path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("sequence_length", 3), ("sequence_sha256", "0" * 64)],
)
def test_bundled_length_and_hash_mismatch_are_inadmissible(
    field: str, value: object
) -> None:
    record = _record(("bundled", "local_verified", "eligible"))
    record[field] = value
    with pytest.raises(PlantComponentRegistryError):
        validate_catalog_record(record)
    assert registry_record_is_admissible(record) is False


@pytest.mark.parametrize(
    ("name", "record"),
    [
        (
            "reference-only",
            _record(("reference_only", "unavailable", "requires_sequence")),
        ),
        ("deferred", _record(("deferred", "unavailable", "blocked"))),
        ("legacy", _legacy_record()),
        (
            "invalid-state",
            _record(("reference_only", "local_verified", "requires_sequence")),
        ),
    ],
)
def test_selection_builder_rejects_nonadmissible_records(
    tmp_path: Path, name: str, record: dict[str, object]
) -> None:
    path = _write_registry(tmp_path, name, record)
    with pytest.raises(PlantComponentRegistryError):
        build_registry_selection(str(record["component_id"]), role="cds", path=path)


def _bundled_selection(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    record = _record(("bundled", "local_verified", "eligible"))
    record["component_id"] = "BUNDLED-CDS"
    path = _write_registry(tmp_path, "bundled-tamper", record)
    return path, build_registry_selection(
        "BUNDLED-CDS", role="cds", requested_host="Oryza sativa", path=path
    )


@pytest.mark.parametrize("field", GOVERNANCE_FIELDS)
def test_admission_rejects_deleted_governance_field_even_with_recomputed_hash(
    tmp_path: Path, field: str
) -> None:
    path, selection = _bundled_selection(tmp_path)
    selection.pop(field)
    _recompute_snapshot_hash(selection)
    with pytest.raises(PlantComponentRegistryError, match="governance triad"):
        admit_registry_selection(selection, role="cds", sequence="ACGT", path=path)


def test_admission_rejects_altered_governance_triad_even_with_recomputed_hash(
    tmp_path: Path,
) -> None:
    path, selection = _bundled_selection(tmp_path)
    selection.update(
        {
            "distribution_mode": "reference_only",
            "sequence_availability": "unavailable",
            "workflow_admission_status": "requires_sequence",
        }
    )
    _recompute_snapshot_hash(selection)
    with pytest.raises(PlantComponentRegistryError, match="does not permit"):
        admit_registry_selection(selection, role="cds", sequence="ACGT", path=path)


def test_recomputed_generic_hash_cannot_erase_governance_boundary(
    tmp_path: Path,
) -> None:
    path, selection = _bundled_selection(tmp_path)
    for field in GOVERNANCE_FIELDS:
        selection.pop(field)
    _recompute_snapshot_hash(selection)
    with pytest.raises(PlantComponentRegistryError, match="governance triad"):
        validate_saved_selection(selection, role="cds", sequence="ACGT")
