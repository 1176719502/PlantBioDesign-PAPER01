from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, Mapping


REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "plant_component_registry_v1"
    / "registry.batch1.json"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_B2B_RIGHTS_PATH = "docs/qa/component_library_v1_full_evidence_completion/phase_b2b/COMPONENT_LIBRARY_V1_B2B_RIGHTS_GOVERNANCE.json"
_B2B_ATTRIBUTION_PATH = "docs/qa/component_library_v1_full_evidence_completion/phase_b2b/COMPONENT_LIBRARY_V1_B2B_ATTRIBUTION_CONTRACT.md"
_B2C_ADMISSION_PATH = "docs/qa/component_library_v1_full_evidence_completion/phase_b2c/COMPONENT_LIBRARY_V1_B2C_PRODUCT_ADMISSION.json"
_HSP_TOMATO_SCOPE_PATH = "docs/qa/V1_TOMATO_HSP18_2_HOST_SCOPE_EXTENSION_R1_20260909.json"
GOVERNANCE_EVIDENCE_SHA256 = {
    _B2B_RIGHTS_PATH: "823f2171ef2da03815a4a00d2b1ee3e7923b2c5701c607748fbce7d8268b656e",
    _B2B_ATTRIBUTION_PATH: "3367dc5113deb69a8b9582b7b47548abb8914ab29b64567c0c01a8fa98593fa7",
    _B2C_ADMISSION_PATH: "b1aa980b0aaadfd368db306668b367ac44c325ce70ebf834d38dd887c319e6a9",
    _HSP_TOMATO_SCOPE_PATH: "3822e8aaa84f6951c865439350fab830868d341b8f6f8ec2cf8173223b76acfa",
}
GOVERNANCE_EVIDENCE_POLICIES: dict[tuple[str, str], dict[str, Any]] = {
    (
        "PCLV1-PRO-E8-2164",
        "COMPONENT_LIBRARY_V1_DIRECT_USE_CONTRACT_V1",
    ): {
        "governance_locators": (_B2B_RIGHTS_PATH, _B2C_ADMISSION_PATH),
        "rights_locators": (
            _B2B_ATTRIBUTION_PATH,
            "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        ),
        "host_scope": ("Solanum lycopersicum",),
    },
    (
        "PCLV1-TER-HSP18-2-250",
        "COMPONENT_LIBRARY_V1_DIRECT_USE_CONTRACT_V1+TOMATO_HOST_SCOPE_R1",
    ): {
        "governance_locators": (
            _B2B_RIGHTS_PATH,
            _B2C_ADMISSION_PATH,
            _HSP_TOMATO_SCOPE_PATH,
        ),
        "rights_locators": (
            _B2B_ATTRIBUTION_PATH,
            "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        ),
        "host_scope": ("Arabidopsis thaliana", "Solanum lycopersicum"),
    },
}
REVIEWED_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "plant_component_registry_v1"
    / "intake_20260827"
    / "candidate_inventory.csv"
)
REVIEWED_CATALOG_SOURCE_COMMIT = "32ae705a85181b5823e8421d4f0989afb9c87155"
REVIEWED_CATALOG_SHA256 = "6edc3a34f104d609632580d59ad1845a93f8377b2068483f957103b2feb411ed"
REVIEWED_CATALOG_RECORD_COUNT = 122
CATALOG_CANDIDATE_STATUS = "CATALOG_CANDIDATE"
CATALOG_CANDIDATE_STATE = "reviewed/catalog_candidate"
REGISTRY_SOURCE_TYPE = "REGISTRY"
USER_PROVIDED_SOURCE_TYPE = "USER_PROVIDED"
REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE = "REAL_CASE_ACCESSION_DERIVED"
UNVERIFIED_USER_INPUT = "UNVERIFIED_USER_INPUT"
DETERMINISTIC_ACCESSION_DERIVATION = "DETERMINISTIC_ACCESSION_DERIVATION"
GENERIC_MULTI_TU_WORKFLOW = "generic_multi_tu"
SNAPSHOT_SCHEMA_VERSION = "plant-component-selection-snapshot-v1"
REGISTRY_SELECTION_CONTRACT_VERSION = "registry-selection-governance-v1"
HOST_APPLICABILITY_REVIEWED = "reviewed"
HOST_APPLICABILITY_NOT_PROVEN = "HOST_APPLICABILITY_NOT_PROVEN"
HOST_APPLICABILITY_WRONG_HOST = "HOST_APPLICABILITY_WRONG_HOST"
HOST_APPLICABILITY_ADMITTED = "ADMITTED"
CURRENT_PROJECT_ID_REQUIRED_CODE = "CURRENT_PROJECT_ID_REQUIRED_FOR_ASSISTED_RESOLUTION"

CATALOG_DISTRIBUTION_MODES = frozenset({"bundled", "reference_only", "deferred"})
CATALOG_SEQUENCE_AVAILABILITIES = frozenset({"local_verified", "unavailable"})
CATALOG_WORKFLOW_ADMISSION_STATUSES = frozenset(
    {"eligible", "requires_sequence", "blocked"}
)
VALID_CATALOG_GOVERNANCE_STATES = frozenset(
    {
        ("bundled", "local_verified", "eligible"),
        ("reference_only", "unavailable", "requires_sequence"),
        ("deferred", "unavailable", "blocked"),
    }
)
LEGACY_CATALOG_STATE = "legacy/unclassified"
REGISTRY_DOCUMENT_FIELDS = frozenset({"registry_version", "records"})
REVIEWED_CATALOG_FIELDS = (
    "candidate_id",
    "display_name",
    "normalized_component_family",
    "component_type",
    "exact_variant",
    "organism_source_context",
    "host_context",
    "sequence",
    "length",
    "sha256",
    "source_database",
    "accession_record_identifier",
    "source_coordinates_or_feature_identity",
    "source_url_reference",
    "evidence_publication_reference",
    "license_redistribution_note",
    "evidence_tier_proposal",
    "workflow_status",
    "duplicate_equivalence_notes",
    "confidence_issues",
)

ROLE_COMPONENT_TYPES = {
    "promoter": frozenset({"promoter"}),
    "five_prime_region": frozenset({"five_prime_utr"}),
    "cds": frozenset({"cds"}),
    "3_prime_regulatory_region": frozenset(
        {"terminator", "three_prime_regulatory_region"}
    ),
    "terminator": frozenset({"terminator"}),
}
EDITABLE_WORKFLOW_TYPES = {
    GENERIC_MULTI_TU_WORKFLOW: frozenset(
        {
            "promoter",
            "five_prime_utr",
            "cds",
            "terminator",
            "three_prime_regulatory_region",
        }
    )
}


class PlantComponentRegistryError(ValueError):
    """Raised when a Registry record or component selection is not admissible."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strict_nonempty_string(
    record: Mapping[str, Any], field: str, *, context: str
) -> str:
    raw_value = record.get(field)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise PlantComponentRegistryError(
            f"{context} requires {field} to be a non-empty string."
        )
    return raw_value.strip()


def _validate_registry_document_structure(
    payload: Any,
) -> tuple[dict[str, Any], list[Any]]:
    if not isinstance(payload, Mapping):
        raise PlantComponentRegistryError(
            "Plant Component Registry V1 must be an object."
        )
    document = dict(payload)
    unexpected_fields = set(document) - REGISTRY_DOCUMENT_FIELDS
    if unexpected_fields:
        raise PlantComponentRegistryError(
            "Plant Component Registry V1 contains unsupported top-level fields."
        )
    _strict_nonempty_string(
        document, "registry_version", context="Plant Component Registry V1"
    )
    records = document.get("records")
    if not isinstance(records, list):
        raise PlantComponentRegistryError("Plant Component Registry V1 is incomplete.")
    return document, records


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_sequence(value: str) -> str:
    return hashlib.sha256(value.upper().encode("ascii")).hexdigest()


def _citation_identity(value: Any) -> str:
    citation = _text(value)
    doi = re.search(r"DOI\s+([^, )]+)", citation, flags=re.IGNORECASE)
    if doi:
        return f"doi:{doi.group(1).lower()}"
    direct_submission = re.match(
        r"NCBI GenBank\s+(\S+)\s+direct submission", citation, flags=re.IGNORECASE
    )
    if direct_submission:
        return f"genbank:{direct_submission.group(1).upper()}"
    return citation


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(snapshot))
    payload.pop("snapshot_sha256", None)
    payload.pop("registry_comparison", None)
    return _sha256_text(_canonical_json(payload))


def _governance_decision(record: Mapping[str, Any]) -> tuple[str, str]:
    source = _strict_nonempty_string(
        record, "governance_decision_source", context="Admissible Registry records"
    )
    version = _strict_nonempty_string(
        record, "governance_decision_version", context="Admissible Registry records"
    )
    return source, version


def _evidence_json(path: str) -> dict[str, Any]:
    expected_digest = GOVERNANCE_EVIDENCE_SHA256.get(path)
    if not expected_digest:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence locator is not governed."
        )
    candidate = (REPOSITORY_ROOT / Path(path)).resolve()
    evidence_root = REPOSITORY_ROOT.resolve()
    try:
        candidate.relative_to(evidence_root)
    except ValueError as exc:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence locator escapes the governed tree."
        ) from exc
    if not candidate.is_file():
        raise PlantComponentRegistryError(
            "Direct-use governance evidence locator does not resolve."
        )
    content = candidate.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence does not match its sealed digest."
        )
    if candidate.suffix.lower() != ".json":
        return {}
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence is malformed."
        ) from exc
    if not isinstance(payload, Mapping):
        raise PlantComponentRegistryError(
            "Direct-use governance evidence has an invalid document identity."
        )
    return dict(payload)


def _evidence_record(payload: Mapping[str, Any], component_id: str) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise PlantComponentRegistryError(
            "Direct-use governance evidence does not contain governed records."
        )
    matches = [
        _mapping(item)
        for item in records
        if _text(_mapping(item).get("component_id")) == component_id
    ]
    if len(matches) != 1:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence does not bind one component identity."
        )
    return matches[0]


def _durable_governance_evidence(record: Mapping[str, Any]) -> None:
    component_id = _text(record.get("component_id"))
    source, version = _governance_decision(record)
    policy = GOVERNANCE_EVIDENCE_POLICIES.get((component_id, version))
    if not policy:
        raise PlantComponentRegistryError(
            "Direct-use governance evidence identity is not adopted."
        )
    locators = tuple(item.strip() for item in source.split(";"))
    if any(not item for item in locators) or locators != tuple(
        policy["governance_locators"]
    ):
        raise PlantComponentRegistryError(
            "Direct-use governance evidence locator is missing or does not match the adopted identity."
        )
    rights_reference = _strict_nonempty_string(
        _mapping(record.get("attribution")),
        "rights_caveat_reference",
        context="Direct-use Registry attribution",
    )
    rights_locators = tuple(item.strip() for item in rights_reference.split(";"))
    if rights_locators != tuple(policy["rights_locators"]):
        raise PlantComponentRegistryError(
            "Direct-use rights evidence locator is missing or does not match the adopted identity."
        )

    evidence = {path: _evidence_json(path) for path in set(locators + (rights_locators[0],))}
    b2b = _evidence_record(evidence[_B2B_RIGHTS_PATH], component_id)
    b2c = _evidence_record(evidence[_B2C_ADMISSION_PATH], component_id)
    technical = _mapping(b2b.get("b2a_technical_evidence"))
    canonical = _mapping(b2c.get("canonical_sequence_contract"))
    versioning = _mapping(b2c.get("versioning_contract"))
    retained_attribution = _mapping(
        _mapping(b2c.get("attribution_contract")).get("retained_values")
    )
    formal_fields = _mapping(
        _mapping(b2c.get("formal_selectability_requirements")).get(
            "existing_registry_fields_to_adopt"
        )
    )
    attribution = _mapping(record.get("attribution"))
    expected_coordinates = _text(
        _mapping(record.get("attribution")).get(
            "source_coordinates_one_based_inclusive"
        )
    )
    if any(
        (
            _text(b2b.get("raw_accession")) != _text(record.get("accession_version")),
            _text(technical.get("source_record_sha256"))
            != _text(record.get("source_record_sha256")),
            _text(technical.get("feature_sha256"))
            != _text(record.get("sequence_sha256")),
            _text(b2b.get("bundling_governance_verdict"))
            != "BUNDLING_GOVERNANCE_READY_WITH_ATTRIBUTION",
            _text(evidence[_B2B_RIGHTS_PATH].get("final_verdict"))
            != "COMPONENT_LIBRARY_V1_RIGHTS_GOVERNANCE_B2B_COMPLETE",
            _text(b2c.get("admission_verdict"))
            != "DIRECT_USE_PRODUCT_ADMISSION_READY",
            _text(evidence[_B2C_ADMISSION_PATH].get("final_verdict"))
            != "COMPONENT_LIBRARY_V1_DIRECT_USE_PRODUCT_ADMISSION_B2C_COMPLETE",
            _text(canonical.get("component_id")) != component_id,
            _text(canonical.get("accession_version"))
            != _text(record.get("accession_version")),
            _text(canonical.get("source_coordinates_one_based_inclusive"))
            != expected_coordinates,
            _text(canonical.get("strand"))
            != _text(_mapping(record.get("feature_boundary_method")).get("strand")),
            _text(canonical.get("sequence_sha256"))
            != _text(record.get("sequence_sha256")),
            _text(canonical.get("source_record_sha256"))
            != _text(record.get("source_record_sha256")),
            _text(versioning.get("component_contract_version"))
            not in {version, "COMPONENT_LIBRARY_V1_DIRECT_USE_CONTRACT_V1"},
            _text(formal_fields.get("rights_classification"))
            != _text(record.get("rights_classification")),
            _text(retained_attribution.get("source_database"))
            != _text(attribution.get("source_database")),
            _text(retained_attribution.get("accession_version"))
            != _text(attribution.get("accession_version")),
            _text(retained_attribution.get("submitter_source_context"))
            != _text(attribution.get("submitter_source_context")),
            _text(retained_attribution.get("source_coordinates_one_based_inclusive"))
            != expected_coordinates,
            _text(retained_attribution.get("strand"))
            != _text(attribution.get("strand")),
            _text(retained_attribution.get("source_record_sha256"))
            != _text(attribution.get("source_record_sha256")),
            _text(retained_attribution.get("feature_sha256"))
            != _text(attribution.get("feature_sha256")),
            not {
                _citation_identity(item)
                for item in retained_attribution.get("publication_citations") or ()
            }.issubset(
                {
                    _citation_identity(item)
                    for item in attribution.get("publication_citations") or ()
                }
            ),
        )
    ):
        raise PlantComponentRegistryError(
            "Direct-use governance evidence does not match the governed component identity."
        )
    host_scope = tuple(_host_applicability_evidence(record)["scope"])
    if host_scope != tuple(policy["host_scope"]):
        raise PlantComponentRegistryError(
            "Direct-use governance evidence does not match the reviewed host scope."
        )
    if _HSP_TOMATO_SCOPE_PATH in locators:
        host_evidence = evidence[_HSP_TOMATO_SCOPE_PATH]
        binding = _mapping(host_evidence.get("binding_matrix"))
        identity = _mapping(host_evidence.get("target_identity"))
        rights = _mapping(host_evidence.get("rights"))
        if any(
            (
                _text(binding.get("component_id")) != component_id,
                tuple(binding.get("proposed_host_scope") or ()) != host_scope,
                _text(binding.get("exact_sequence_sha256"))
                != _text(record.get("sequence_sha256")),
                binding.get("rights_ready") is not True,
                _text(identity.get("accession_version"))
                != _text(record.get("accession_version")),
                _text(identity.get("coordinates_one_based_inclusive"))
                != expected_coordinates,
                _text(identity.get("sequence_sha256"))
                != _text(record.get("sequence_sha256")),
                rights.get("not_freedom_to_operate_clearance") is not True,
            )
        ):
            raise PlantComponentRegistryError(
                "Direct-use host-scope evidence is stale or mismatched."
            )


def _host_applicability_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(record.get("host_applicability"))
    if _text(evidence.get("status")) != HOST_APPLICABILITY_REVIEWED:
        raise PlantComponentRegistryError(
            "Admissible Registry records require reviewed host-applicability evidence."
        )
    scope = evidence.get("scope")
    if not isinstance(scope, list) or not scope or any(
        not isinstance(item, str) or not item.strip() for item in scope
    ):
        raise PlantComponentRegistryError(
            "Reviewed host-applicability evidence requires a non-empty species scope."
        )
    source = _strict_nonempty_string(
        evidence, "evidence_source", context="Host-applicability evidence"
    )
    version = _strict_nonempty_string(
        evidence, "evidence_version", context="Host-applicability evidence"
    )
    limitation = _strict_nonempty_string(
        evidence, "limitation", context="Host-applicability evidence"
    )
    return {
        "status": HOST_APPLICABILITY_REVIEWED,
        "scope": [item.strip() for item in scope],
        "evidence_source": source,
        "evidence_version": version,
        "limitation": limitation,
    }


def host_applicability_gate(record: Mapping[str, Any], requested_host: str) -> str:
    """Classify host admission; an empty scope is never a wildcard."""
    host = _text(requested_host)
    if not host:
        return "NOT_REQUIRED"
    try:
        evidence = _host_applicability_evidence(record)
    except PlantComponentRegistryError:
        return HOST_APPLICABILITY_NOT_PROVEN
    return (
        HOST_APPLICABILITY_ADMITTED
        if host in set(evidence["scope"])
        else HOST_APPLICABILITY_WRONG_HOST
    )


def _direct_use_attribution(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate attribution against the exact admitted Registry identity."""
    attribution = _mapping(record.get("attribution"))
    required_strings = (
        "source_database",
        "record_locator",
        "accession_version",
        "submitter_source_context",
        "source_coordinates_one_based_inclusive",
        "strand",
        "feature_type",
        "retrieval_date",
        "source_record_sha256",
        "feature_sha256",
        "rights_caveat_reference",
        "component_contract_version",
        "required_notice",
    )
    for field in required_strings:
        _strict_nonempty_string(
            attribution, field, context="Direct-use Registry attribution"
        )
    citations = attribution.get("publication_citations")
    if not isinstance(citations, list) or not citations or any(
        not isinstance(item, str) or not item.strip() for item in citations
    ):
        raise PlantComponentRegistryError(
            "Direct-use Registry attribution requires publication citations."
        )
    boundary = _mapping(record.get("feature_boundary_method"))
    expected_coordinates = (
        f"{int(boundary.get('start_one_based') or 0)}.."
        f"{int(boundary.get('end_one_based_inclusive') or 0)}"
    )
    matching_fields = {
        "accession_version": _text(record.get("accession_version")),
        "source_coordinates_one_based_inclusive": expected_coordinates,
        "strand": _text(boundary.get("strand")),
        "source_record_sha256": _text(record.get("source_record_sha256")),
        "feature_sha256": _text(record.get("sequence_sha256")),
        "component_contract_version": _text(
            record.get("governance_decision_version")
        ),
    }
    if any(
        _text(attribution.get(field)) != expected
        for field, expected in matching_fields.items()
    ):
        raise PlantComponentRegistryError(
            "Direct-use Registry attribution does not match the governed component identity."
        )
    return copy.deepcopy(attribution)


def _registry_selection_governance(snapshot: Mapping[str, Any]) -> tuple[str, str, str]:
    if _text(snapshot.get("registry_selection_contract_version")) != REGISTRY_SELECTION_CONTRACT_VERSION:
        raise PlantComponentRegistryError(
            "Legacy/unclassified Registry selection is blocked from formal downstream use."
        )
    if _text(snapshot.get("selection_source")) != REGISTRY_SOURCE_TYPE:
        raise PlantComponentRegistryError(
            "Registry selection_source must remain REGISTRY."
        )
    if not _text(snapshot.get("registry_version")):
        raise PlantComponentRegistryError(
            "Registry selection requires its selection-time Registry version."
        )
    current_fields = (
        "distribution_mode",
        "sequence_availability",
        "workflow_admission_status",
    )
    selection_fields = (
        "distribution_mode_at_selection",
        "sequence_availability_at_selection",
        "workflow_admission_status_at_selection",
    )
    current = tuple(_text(snapshot.get(field)) for field in current_fields)
    selected = tuple(_text(snapshot.get(field)) for field in selection_fields)
    if any(not value for value in current + selected):
        raise PlantComponentRegistryError(
            "Registry selection governance triad facts are missing."
        )
    if current != selected or selected not in VALID_CATALOG_GOVERNANCE_STATES:
        raise PlantComponentRegistryError(
            "Registry selection governance triad does not permit formal downstream use because its facts are inconsistent."
        )
    if selected != ("bundled", "local_verified", "eligible"):
        raise PlantComponentRegistryError(
            "Registry selection governance facts do not permit formal downstream use."
        )
    for field in (
        "governance_decision_source",
        "governance_decision_version",
        "provenance_origin",
        "requested_host",
    ):
        if not _text(snapshot.get(field)):
            raise PlantComponentRegistryError(
                f"Registry selection requires {field}."
            )
    evidence = _host_applicability_evidence(
        {"host_applicability": snapshot.get("host_applicability_at_selection")}
    )
    if _text(snapshot.get("requested_host")) not in evidence["scope"]:
        raise PlantComponentRegistryError(
            "Registry selection requested host is outside the reviewed host-applicability scope."
        )
    return selected


def catalog_governance_state(record: Mapping[str, Any]) -> str | tuple[str, str, str]:
    """Return the persisted governance state without inferring missing fields.

    Records from before the V1 governance contract remain recognizable as an
    internal legacy state.  They are never treated as a public distribution
    mode and are never admitted by the Registry gate.
    """
    fields = (
        "distribution_mode",
        "sequence_availability",
        "workflow_admission_status",
    )
    present = [field in record for field in fields]
    if not any(present):
        return LEGACY_CATALOG_STATE
    if not all(present):
        raise PlantComponentRegistryError(
            "Registry governance fields must be provided together."
        )
    state = tuple(_text(record.get(field)) for field in fields)
    if any(not value for value in state):
        raise PlantComponentRegistryError("Registry governance fields cannot be empty.")
    if state not in VALID_CATALOG_GOVERNANCE_STATES:
        raise PlantComponentRegistryError(
            "Registry governance fields contain an invalid persisted combination."
        )
    return state


def validate_catalog_record(record: Mapping[str, Any]) -> str | tuple[str, str, str]:
    """Validate the complete record contract used by Registry admission."""
    _strict_nonempty_string(record, "component_id", context="Registry records")
    state = catalog_governance_state(record)
    requires_local_sequence = (
        state == LEGACY_CATALOG_STATE or state == ("bundled", "local_verified", "eligible")
    )
    if requires_local_sequence:
        raw_sequence = record.get("sequence")
        if not isinstance(raw_sequence, str) or not raw_sequence or set(raw_sequence.upper()) - set("ACGT"):
            raise PlantComponentRegistryError(
                "Bundled and legacy Registry records require a complete strict-DNA sequence."
            )
        sequence = raw_sequence.upper()
        sequence_length = record.get("sequence_length")
        if (
            isinstance(sequence_length, bool)
            or not isinstance(sequence_length, int)
            or sequence_length != len(sequence)
        ):
            raise PlantComponentRegistryError("Registry record sequence length does not match.")
        if _text(record.get("sequence_sha256")) != _sha256_sequence(sequence):
            raise PlantComponentRegistryError("Registry record sequence SHA-256 does not match.")
    else:
        _, sequence_availability, _ = state
        if sequence_availability != "unavailable":
            raise PlantComponentRegistryError(
                "Non-bundled Registry records must declare sequence unavailable."
            )
        if "sequence" in record and record.get("sequence") is not None:
            raise PlantComponentRegistryError(
                "Non-bundled Registry record sequence must be absent or null."
            )
    return state


def registry_record_is_admissible(record: Mapping[str, Any]) -> bool:
    """Return whether a record satisfies the complete direct-use contract."""
    try:
        state = validate_catalog_record(record)
        _governance_decision(record)
        _host_applicability_evidence(record)
        _direct_use_attribution(record)
        _durable_governance_evidence(record)
        boundary = _mapping(record.get("feature_boundary_method"))
        source_length = record.get("source_sequence_length")
        start = boundary.get("start_one_based")
        end = boundary.get("end_one_based_inclusive")
    except (PlantComponentRegistryError, TypeError, ValueError):
        return False
    return bool(
        state == ("bundled", "local_verified", "eligible")
        and _text(record.get("rights_classification"))
        == "RIGHTS_CLEAR_FOR_CURRENT_USE"
        and _text(record.get("review_status")) == "source_and_boundary_reviewed"
        and record.get("role_semantics_reviewed") is True
        and record.get("host_applicability_reviewed") is True
        and record.get("alias_collision_reviewed") is True
        and record.get("formal_export_compatible") is True
        and _text(record.get("component_type"))
        in EDITABLE_WORKFLOW_TYPES[GENERIC_MULTI_TU_WORKFLOW]
        and isinstance(source_length, int)
        and not isinstance(source_length, bool)
        and source_length > 0
        and isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 1 <= start <= end <= source_length
        and end - start + 1 == int(record.get("sequence_length") or 0)
    )


def load_reviewed_catalog_candidates(
    path: str | Path | None = None,
) -> list[dict[str, str]]:
    """Load the reviewed intake as identity-preserving, browse-only records.

    The CSV is kept as the exact reviewed Git blob after line-ending
    normalization.  These records are deliberately outside the authoritative
    Registry document and therefore outside every admission and selection
    function in this module.
    """
    candidate_path = Path(path) if path is not None else REVIEWED_CATALOG_PATH
    try:
        raw_bytes = candidate_path.read_bytes()
    except OSError as exc:
        raise PlantComponentRegistryError(
            "Reviewed plant component catalog candidates cannot be read."
        ) from exc
    reviewed_bytes = raw_bytes.replace(b"\r\n", b"\n")
    if path is None and hashlib.sha256(reviewed_bytes).hexdigest() != REVIEWED_CATALOG_SHA256:
        raise PlantComponentRegistryError(
            "Reviewed plant component catalog candidate inventory identity does not match."
        )
    try:
        text = reviewed_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlantComponentRegistryError(
            "Reviewed plant component catalog candidates must be UTF-8."
        ) from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != REVIEWED_CATALOG_FIELDS:
        raise PlantComponentRegistryError(
            "Reviewed plant component catalog candidate fields do not match."
        )

    records: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    for row_number, raw_record in enumerate(reader, start=2):
        record = {field: str(raw_record.get(field) or "") for field in REVIEWED_CATALOG_FIELDS}
        if None in raw_record or any(not value for value in record.values()):
            raise PlantComponentRegistryError(
                f"Reviewed catalog candidate row {row_number} is incomplete."
            )
        candidate_id = record["candidate_id"]
        sequence = record["sequence"]
        sequence_hash = record["sha256"]
        if candidate_id in seen_ids:
            raise PlantComponentRegistryError(
                "Reviewed catalog candidate IDs must be unique."
            )
        if sequence_hash in seen_hashes:
            raise PlantComponentRegistryError(
                "Reviewed catalog candidate sequence hashes must be unique."
            )
        if record["workflow_status"] != CATALOG_CANDIDATE_STATUS:
            raise PlantComponentRegistryError(
                "Reviewed catalog candidates must remain CATALOG_CANDIDATE."
            )
        if not sequence or sequence != sequence.upper() or set(sequence) - set("ACGTN"):
            raise PlantComponentRegistryError(
                f"Reviewed catalog candidate {candidate_id} requires exact normalized DNA."
            )
        try:
            declared_length = int(record["length"])
        except ValueError as exc:
            raise PlantComponentRegistryError(
                f"Reviewed catalog candidate {candidate_id} has an invalid length."
            ) from exc
        if declared_length != len(sequence):
            raise PlantComponentRegistryError(
                f"Reviewed catalog candidate {candidate_id} length does not match."
            )
        if hashlib.sha256(sequence.encode("ascii")).hexdigest() != sequence_hash:
            raise PlantComponentRegistryError(
                f"Reviewed catalog candidate {candidate_id} SHA-256 does not match."
            )
        seen_ids.add(candidate_id)
        seen_hashes.add(sequence_hash)
        records.append(record)

    if path is None and len(records) != REVIEWED_CATALOG_RECORD_COUNT:
        raise PlantComponentRegistryError(
            "Reviewed plant component catalog candidate count does not match."
        )
    return copy.deepcopy(records)


def load_registry_document(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path is not None else REGISTRY_PATH
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlantComponentRegistryError("Plant Component Registry V1 cannot be read.") from exc
    payload, records = _validate_registry_document_structure(payload)
    seen_ids: set[str] = set()
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            raise PlantComponentRegistryError("Registry records must be objects.")
        record = dict(raw_record)
        component_id = _strict_nonempty_string(
            record, "component_id", context="Registry records"
        )
        if component_id in seen_ids:
            raise PlantComponentRegistryError("Registry component_id values must be non-empty and unique.")
        seen_ids.add(component_id)
        try:
            validate_catalog_record(record)
        except PlantComponentRegistryError as exc:
            raise PlantComponentRegistryError(
                f"Registry record {component_id} has invalid governance metadata."
            ) from exc
    return payload


def registry_records(path: str | Path | None = None) -> list[dict[str, Any]]:
    payload = load_registry_document(path)
    return [copy.deepcopy(_mapping(record)) for record in payload["records"]]


def registry_record(component_id: str, path: str | Path | None = None) -> dict[str, Any]:
    requested = _text(component_id)
    for record in registry_records(path):
        if _text(record.get("component_id")) == requested:
            return record
    raise PlantComponentRegistryError(f"Registry component_id does not exist: {requested or '<empty>'}.")


def workflow_uses_for_record(record: Mapping[str, Any]) -> list[str]:
    component_type = _text(record.get("component_type"))
    return [
        workflow_id
        for workflow_id, allowed_types in EDITABLE_WORKFLOW_TYPES.items()
        if component_type in allowed_types
    ]


def record_limitation(record: Mapping[str, Any]) -> str:
    component_type = _text(record.get("component_type"))
    if component_type == "vector_backbone":
        return "Reference-only vector source; it is not selectable as an expression component."
    if _text(record.get("evidence_level")) == "E2":
        return (
            "E2 preserves a reproducible deposited sequence boundary with a recorded caveat; "
            "it is not equivalent to E1 source-coordinate evidence."
        )
    return (
        "Evidence describes sequence identity and source completeness, not expression performance. "
        "Recorded host metadata does not guarantee behavior under current experimental conditions."
    )


def _component_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    boundary = copy.deepcopy(_mapping(record.get("feature_boundary_method")))
    attribution = (
        _direct_use_attribution(record)
        if record.get("formal_export_compatible") is True
        else copy.deepcopy(_mapping(record.get("attribution")))
    )
    return {
        "component_id": _text(record.get("component_id")),
        "component_type": _text(record.get("component_type")),
        "display_name": _text(record.get("display_name")),
        "component_role": _text(record.get("component_role")),
        "sequence": _text(record.get("sequence")).upper(),
        "sequence_length": int(record.get("sequence_length") or 0),
        "sequence_sha256": _text(record.get("sequence_sha256")),
        "accession": _text(record.get("accession")),
        "accession_version": _text(record.get("accession_version")),
        "source_organism": _text(record.get("source_organism")),
        "target_host_species": [str(item) for item in list(record.get("target_host_species") or [])],
        "host_group": [str(item) for item in list(record.get("host_group") or [])],
        "evidence_tier": _text(record.get("evidence_level")),
        "primary_reference": _text(record.get("primary_reference")),
        "source_record": _text(record.get("source_record")),
        "source_record_sha256": _text(record.get("source_record_sha256")),
        "feature_boundary_method": boundary,
        "redistribution_status": _text(record.get("redistribution_status")),
        "notes": _text(record.get("notes")),
        "attribution": attribution,
    }


def build_registry_selection(
    component_id: str,
    *,
    role: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
    requested_host: str = "",
    path: str | Path | None = None,
) -> dict[str, Any]:
    payload = load_registry_document(path)
    record = next(
        (
            _mapping(item)
            for item in payload["records"]
            if _text(_mapping(item).get("component_id")) == _text(component_id)
        ),
        None,
    )
    if record is None:
        raise PlantComponentRegistryError(f"Registry component_id does not exist: {_text(component_id) or '<empty>'}.")
    if not registry_record_is_admissible(record):
        raise PlantComponentRegistryError(
            f"Registry component {component_id} is not admitted for direct selection."
        )
    expected_types = ROLE_COMPONENT_TYPES.get(_text(role))
    if not expected_types:
        raise PlantComponentRegistryError(f"Unsupported formal component role: {_text(role) or '<empty>'}.")
    component_type = _text(record.get("component_type"))
    if component_type not in expected_types:
        raise PlantComponentRegistryError(
            f"Registry component {component_id} type {component_type} is not allowed for role {role}."
        )
    if component_type not in EDITABLE_WORKFLOW_TYPES.get(_text(workflow_id), frozenset()):
        raise PlantComponentRegistryError(
            f"Registry component {component_id} is not admitted to workflow {workflow_id}."
        )
    resolved_host = _text(requested_host)
    if not resolved_host:
        raise PlantComponentRegistryError(
            "Registry selection requires an explicit requested host context."
        )
    host_status = host_applicability_gate(record, resolved_host)
    if host_status == HOST_APPLICABILITY_NOT_PROVEN:
        raise PlantComponentRegistryError(
            f"{HOST_APPLICABILITY_NOT_PROVEN}: reviewed host-applicability scope is required."
        )
    if host_status != HOST_APPLICABILITY_ADMITTED:
        raise PlantComponentRegistryError(
            "Registry component is not admitted for the requested host context."
        )
    governance_decision_source, governance_decision_version = _governance_decision(record)
    host_applicability = _host_applicability_evidence(record)
    snapshot = _component_snapshot(record)
    governance_state = catalog_governance_state(record)
    selection = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "registry_selection_contract_version": REGISTRY_SELECTION_CONTRACT_VERSION,
        "registry_version": _text(payload.get("registry_version")),
        "source_type": REGISTRY_SOURCE_TYPE,
        "selection_source": REGISTRY_SOURCE_TYPE,
        "workflow_context": _text(workflow_id),
        "tu_role": _text(role),
        "registry_component_id": snapshot["component_id"],
        "component_type": snapshot["component_type"],
        "display_name": snapshot["display_name"],
        "accession_version": snapshot["accession_version"],
        "selected_sequence": snapshot["sequence"],
        "selected_length": snapshot["sequence_length"],
        "sequence_sha256": snapshot["sequence_sha256"],
        "evidence_tier": snapshot["evidence_tier"],
        "source_organism": snapshot["source_organism"],
        "target_host_species": list(snapshot["target_host_species"]),
        "component_snapshot": snapshot,
        "workflow_compatibility": workflow_uses_for_record(record),
        "formal_selection_confirmed": False,
        "limitation": record_limitation(record),
        "governance_decision_source": governance_decision_source,
        "governance_decision_version": governance_decision_version,
        "provenance_origin": _strict_nonempty_string(
            record, "source_record", context="Admissible Registry records"
        ),
        "requested_host": resolved_host,
        "host_applicability_at_selection": host_applicability,
    }
    if governance_state == LEGACY_CATALOG_STATE:
        selection["governance_state"] = LEGACY_CATALOG_STATE
    else:
        selection.update(
            {
                "distribution_mode": governance_state[0],
                "sequence_availability": governance_state[1],
                "workflow_admission_status": governance_state[2],
                "distribution_mode_at_selection": governance_state[0],
                "sequence_availability_at_selection": governance_state[1],
                "workflow_admission_status_at_selection": governance_state[2],
            }
        )
    selection["snapshot_sha256"] = _snapshot_digest(selection)
    return selection


def build_user_provided_selection(
    *,
    role: str,
    display_name: str,
    sequence: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
    reference_component_id: str = "",
    reference_registry_version: str = "",
    assisted_resolution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_types = ROLE_COMPONENT_TYPES.get(_text(role))
    if not expected_types:
        raise PlantComponentRegistryError(f"Unsupported formal component role: {_text(role) or '<empty>'}.")
    normalized = _text(sequence).upper()
    if not normalized or set(normalized) - set("ACGT"):
        raise PlantComponentRegistryError("User-provided component requires a complete strict-DNA sequence.")
    component_type = (
        "three_prime_regulatory_region"
        if _text(role) == "3_prime_regulatory_region"
        else "five_prime_utr"
        if _text(role) == "five_prime_region"
        else _text(role)
    )
    selection = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "registry_version": "",
        "source_type": USER_PROVIDED_SOURCE_TYPE,
        "workflow_context": _text(workflow_id),
        "tu_role": _text(role),
        "registry_component_id": "",
        "component_type": component_type,
        "display_name": _text(display_name) or _text(role),
        "accession_version": "",
        "selected_sequence": normalized,
        "selected_length": len(normalized),
        "sequence_sha256": _sha256_sequence(normalized),
        "evidence_tier": UNVERIFIED_USER_INPUT,
        "source_organism": "",
        "target_host_species": [],
        "component_snapshot": {},
        "workflow_compatibility": [_text(workflow_id)],
        "limitation": (
            "User-provided sequence; accession, source organism, target-host evidence, and "
            "experimental performance are unavailable unless separately reviewed."
        ),
    }
    reference_id = _text(reference_component_id)
    reference_version = _text(reference_registry_version)
    if bool(reference_id) != bool(reference_version):
        raise PlantComponentRegistryError(
            "User-provided Registry reference linkage requires both component ID and Registry version."
        )
    if reference_id:
        selection["reference_component_link"] = {
            "registry_component_id": reference_id,
            "registry_version": reference_version,
            "authority": "non_authoritative_identity_link",
        }
    if assisted_resolution is not None:
        resolution = _mapping(assisted_resolution)
        if _text(resolution.get("governance_status")) != "USER_SEQUENCE_ASSISTED":
            raise PlantComponentRegistryError(
                "Assisted user selection requires USER_SEQUENCE_ASSISTED resolution evidence."
            )
        selection["assisted_resolution"] = copy.deepcopy(resolution)
        selection["catalog_component_id"] = _text(
            resolution.get("catalog_component_id")
        )
        selection["catalog_name"] = _text(resolution.get("catalog_name"))
        selection["governance_status"] = "USER_SEQUENCE_ASSISTED"
        selection["admission_mode"] = "USER_SEQUENCE_ASSISTED"
        selection["project_id"] = _text(resolution.get("project_id"))
    selection["snapshot_sha256"] = _snapshot_digest(selection)
    return selection


def build_accession_derived_case_selection(
    *,
    role: str,
    display_name: str,
    sequence: str,
    accession_version: str,
    case_id: str,
    contract_version: str,
    component_case_id: str,
    source_interval: Mapping[str, Any],
    input_transformation: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
) -> dict[str, Any]:
    """Build an immutable non-Registry selection for a contracted real case."""
    expected_types = ROLE_COMPONENT_TYPES.get(_text(role))
    if not expected_types:
        raise PlantComponentRegistryError(
            f"Unsupported formal component role: {_text(role) or '<empty>'}."
        )
    normalized = _text(sequence).upper()
    if not normalized or set(normalized) - set("ACGT"):
        raise PlantComponentRegistryError(
            "Accession-derived component requires a complete strict-DNA sequence."
        )
    component_type = (
        "three_prime_regulatory_region"
        if _text(role) == "3_prime_regulatory_region"
        else "five_prime_utr"
        if _text(role) == "five_prime_region"
        else _text(role)
    )
    if component_type not in expected_types:
        raise PlantComponentRegistryError(
            "Accession-derived component type does not match its TU role."
        )
    identity = {
        "case_id": _text(case_id),
        "contract_version": _text(contract_version),
        "component_case_id": _text(component_case_id),
        "source_accession_version": _text(accession_version),
        "source_interval": copy.deepcopy(dict(source_interval)),
        "input_transformation": _text(input_transformation),
        "selected_sequence": normalized,
        "selected_length": len(normalized),
        "sequence_sha256": _sha256_sequence(normalized),
    }
    if any(not identity[key] for key in (
        "case_id",
        "contract_version",
        "component_case_id",
        "source_accession_version",
        "input_transformation",
    )):
        raise PlantComponentRegistryError(
            "Accession-derived component requires complete case provenance."
        )
    selection = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "registry_version": "",
        "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
        "workflow_context": _text(workflow_id),
        "tu_role": _text(role),
        "registry_component_id": "",
        "component_type": component_type,
        "display_name": _text(display_name) or _text(role),
        "accession_version": identity["source_accession_version"],
        "selected_sequence": normalized,
        "selected_length": len(normalized),
        "sequence_sha256": identity["sequence_sha256"],
        "evidence_tier": DETERMINISTIC_ACCESSION_DERIVATION,
        "source_organism": "",
        "target_host_species": [],
        "component_snapshot": identity,
        "workflow_compatibility": [_text(workflow_id)],
        "limitation": (
            "Sequence identity is derived deterministically from a versioned accession "
            "and case contract; experimental performance is not assessed."
        ),
    }
    selection["snapshot_sha256"] = _snapshot_digest(selection)
    return selection


def validate_saved_selection(
    selection: Mapping[str, Any],
    *,
    role: str,
    sequence: str,
    current_project_id: str | None = None,
    project_repository: Any = None,
) -> dict[str, Any]:
    snapshot = copy.deepcopy(_mapping(selection))
    if _text(snapshot.get("snapshot_schema_version")) != SNAPSHOT_SCHEMA_VERSION:
        raise PlantComponentRegistryError("Component selection snapshot version is not supported.")
    if _text(snapshot.get("tu_role")) != _text(role):
        raise PlantComponentRegistryError("Component selection role does not match its TU role.")
    if _text(snapshot.get("snapshot_sha256")) != _snapshot_digest(snapshot):
        raise PlantComponentRegistryError("Component selection snapshot checksum does not match.")
    normalized = _text(sequence).upper()
    if _text(snapshot.get("selected_sequence")).upper() != normalized:
        raise PlantComponentRegistryError("Component selection sequence does not match the canonical input.")
    if int(snapshot.get("selected_length") or 0) != len(normalized):
        raise PlantComponentRegistryError("Component selection length does not match its sequence.")
    if _text(snapshot.get("sequence_sha256")) != _sha256_sequence(normalized):
        raise PlantComponentRegistryError("Component selection sequence SHA-256 does not match.")
    expected_types = ROLE_COMPONENT_TYPES.get(_text(role), frozenset())
    if _text(snapshot.get("component_type")) not in expected_types:
        raise PlantComponentRegistryError("Component selection type does not match its TU role.")
    source_type = _text(snapshot.get("source_type"))
    selection_source = _text(snapshot.get("selection_source"))
    if source_type != REGISTRY_SOURCE_TYPE and selection_source and selection_source != source_type:
        raise PlantComponentRegistryError(
            "Component selection_source does not match source_type."
        )
    if source_type == REGISTRY_SOURCE_TYPE:
        _registry_selection_governance(snapshot)
        if not _text(snapshot.get("registry_component_id")):
            raise PlantComponentRegistryError("Registry selection requires registry_component_id.")
        component_snapshot = _mapping(snapshot.get("component_snapshot"))
        immutable_pairs = {
            "component_id": "registry_component_id",
            "component_type": "component_type",
            "accession_version": "accession_version",
            "sequence": "selected_sequence",
            "sequence_length": "selected_length",
            "sequence_sha256": "sequence_sha256",
            "evidence_tier": "evidence_tier",
            "source_organism": "source_organism",
        }
        if any(
            _text(component_snapshot.get(source_key)) != _text(snapshot.get(snapshot_key))
            for source_key, snapshot_key in immutable_pairs.items()
        ):
            raise PlantComponentRegistryError("Registry component snapshot identity has been modified.")
    elif source_type == USER_PROVIDED_SOURCE_TYPE:
        if _text(snapshot.get("registry_component_id")) or _text(snapshot.get("accession_version")):
            raise PlantComponentRegistryError("User-provided sequence cannot claim Registry identity or accession.")
        if _text(snapshot.get("evidence_tier")) != UNVERIFIED_USER_INPUT:
            raise PlantComponentRegistryError("User-provided sequence must remain UNVERIFIED_USER_INPUT.")
        forbidden_governance_fields = (
            "registry_selection_contract_version",
            "distribution_mode",
            "sequence_availability",
            "workflow_admission_status",
            "distribution_mode_at_selection",
            "sequence_availability_at_selection",
            "workflow_admission_status_at_selection",
            "governance_decision_source",
            "governance_decision_version",
            "host_applicability_at_selection",
        )
        if any(field in snapshot for field in forbidden_governance_fields):
            raise PlantComponentRegistryError(
                "User-provided sequence cannot claim Registry governance facts."
            )
        assisted_resolution = snapshot.get("assisted_resolution")
        if assisted_resolution is not None:
            resolution = _mapping(assisted_resolution)
            if not _text(snapshot.get("catalog_component_id")):
                raise PlantComponentRegistryError(
                    "Assisted user-provided selection requires catalog_component_id."
                )
            if _text(snapshot.get("governance_status")) != "USER_SEQUENCE_ASSISTED":
                raise PlantComponentRegistryError(
                    "Assisted user-provided selection must remain USER_SEQUENCE_ASSISTED."
                )
            expected_project_id = _text(current_project_id) or _text(
                snapshot.get("project_id")
            )
            if not expected_project_id:
                raise PlantComponentRegistryError(
                    f"{CURRENT_PROJECT_ID_REQUIRED_CODE}: "
                    "Project-scoped assisted selection requires the current project identity."
                )
            try:
                from services.component_library_v2_adoption import (
                    validate_v2_project_resolution,
                )

                validate_v2_project_resolution(
                    resolution,
                    project_id=expected_project_id,
                    sequence=normalized,
                    repository=project_repository,
                )
            except ValueError as exc:
                raise PlantComponentRegistryError(
                    f"Assisted user-provided resolution is invalid: {exc}"
                ) from exc
        reference_link = snapshot.get("reference_component_link")
        if reference_link is not None:
            link = _mapping(reference_link)
            if (
                not _text(link.get("registry_component_id"))
                or not _text(link.get("registry_version"))
                or _text(link.get("authority")) != "non_authoritative_identity_link"
            ):
                raise PlantComponentRegistryError(
                    "User-provided Registry reference linkage is incomplete or overstates authority."
                )
    elif source_type == REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE:
        if _text(snapshot.get("registry_component_id")):
            raise PlantComponentRegistryError(
                "Accession-derived real-case component cannot claim Registry identity."
            )
        if not _text(snapshot.get("accession_version")):
            raise PlantComponentRegistryError(
                "Accession-derived real-case component requires an exact accession/version."
            )
        if _text(snapshot.get("evidence_tier")) != DETERMINISTIC_ACCESSION_DERIVATION:
            raise PlantComponentRegistryError(
                "Accession-derived real-case component evidence class has been modified."
            )
        component_snapshot = _mapping(snapshot.get("component_snapshot"))
        immutable_pairs = {
            "source_accession_version": "accession_version",
            "selected_sequence": "selected_sequence",
            "selected_length": "selected_length",
            "sequence_sha256": "sequence_sha256",
        }
        if any(
            component_snapshot.get(source_key) != snapshot.get(snapshot_key)
            for source_key, snapshot_key in immutable_pairs.items()
        ):
            raise PlantComponentRegistryError(
                "Accession-derived component snapshot identity has been modified."
            )
        if any(
            not _text(component_snapshot.get(key))
            for key in (
                "case_id",
                "contract_version",
                "component_case_id",
                "source_accession_version",
                "input_transformation",
            )
        ):
            raise PlantComponentRegistryError(
                "Accession-derived component snapshot provenance is incomplete."
            )
    else:
        raise PlantComponentRegistryError("Component selection source_type is not supported.")
    return snapshot


def admit_registry_selection(
    selection: Mapping[str, Any],
    *,
    role: str,
    sequence: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
    path: str | Path | None = None,
) -> dict[str, Any]:
    saved = validate_saved_selection(selection, role=role, sequence=sequence)
    if _text(saved.get("source_type")) != REGISTRY_SOURCE_TYPE:
        raise PlantComponentRegistryError("Registry admission requires a REGISTRY selection.")
    requested_host = _text(saved.get("requested_host"))
    record = registry_record(_text(saved.get("registry_component_id")), path)
    try:
        saved_governance_state = catalog_governance_state(saved)
    except PlantComponentRegistryError as exc:
        raise PlantComponentRegistryError(
            "Registry selection governance triad is missing or invalid."
        ) from exc
    if saved_governance_state != ("bundled", "local_verified", "eligible"):
        raise PlantComponentRegistryError(
            "Registry selection governance triad does not permit formal admission."
        )
    if not registry_record_is_admissible(record):
        raise PlantComponentRegistryError(
            "Registry component is not admitted for direct selection."
        )
    current = build_registry_selection(
        _text(saved.get("registry_component_id")),
        role=role,
        workflow_id=workflow_id,
        requested_host=requested_host,
        path=path,
    )
    comparable_fields = (
        "registry_version",
        "registry_selection_contract_version",
        "selection_source",
        "registry_component_id",
        "component_type",
        "display_name",
        "accession_version",
        "selected_sequence",
        "selected_length",
        "sequence_sha256",
        "evidence_tier",
        "source_organism",
        "target_host_species",
        "formal_selection_confirmed",
        "distribution_mode",
        "sequence_availability",
        "workflow_admission_status",
        "distribution_mode_at_selection",
        "sequence_availability_at_selection",
        "workflow_admission_status_at_selection",
        "governance_decision_source",
        "governance_decision_version",
        "provenance_origin",
        "requested_host",
        "host_applicability_at_selection",
        "component_snapshot",
    )
    if any(saved.get(field) != current.get(field) for field in comparable_fields):
        raise PlantComponentRegistryError("Registry selection does not match the current approved record.")
    return saved


def normalize_component_selection(
    component_input: Mapping[str, Any],
    *,
    role: str,
    sequence: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
    current_project_id: str | None = None,
    project_repository: Any = None,
) -> dict[str, Any]:
    source = _mapping(component_input)
    resolved_project_id = _text(current_project_id) or _text(
        source.get("_runtime_project_id")
    )
    selection = _mapping(source.get("component_reference"))
    if _text(selection.get("source_type")) == REGISTRY_SOURCE_TYPE:
        return admit_registry_selection(
            selection,
            role=role,
            sequence=sequence,
            workflow_id=workflow_id,
        )
    if selection:
        return validate_saved_selection(
            selection,
            role=role,
            sequence=sequence,
            current_project_id=resolved_project_id,
            project_repository=project_repository,
        )
    return build_user_provided_selection(
        role=role,
        display_name=_text(source.get("display_name")),
        sequence=sequence,
        workflow_id=workflow_id,
    )


def compare_selection_to_current_registry(
    selection: Mapping[str, Any],
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    snapshot = _mapping(selection)
    if _text(snapshot.get("source_type")) != REGISTRY_SOURCE_TYPE:
        return {"status": "not_applicable", "changed_fields": []}
    component_id = _text(snapshot.get("registry_component_id"))
    try:
        payload = load_registry_document(path)
        current = next(
            (
                _mapping(item)
                for item in payload["records"]
                if _text(_mapping(item).get("component_id")) == component_id
            ),
            None,
        )
    except PlantComponentRegistryError:
        return {"status": "missing_from_current_registry", "changed_fields": ["component_id"]}
    if current is None:
        return {"status": "missing_from_current_registry", "changed_fields": ["component_id"]}
    current_snapshot = _component_snapshot(current)
    saved_snapshot = _mapping(snapshot.get("component_snapshot"))
    changed = {
        key
        for key in set(saved_snapshot) | set(current_snapshot)
        if saved_snapshot.get(key) != current_snapshot.get(key)
    }
    governance_fields = {
        "distribution_mode": "distribution_mode_at_selection",
        "sequence_availability": "sequence_availability_at_selection",
        "workflow_admission_status": "workflow_admission_status_at_selection",
        "governance_decision_source": "governance_decision_source",
        "governance_decision_version": "governance_decision_version",
        "source_record": "provenance_origin",
    }
    for current_field, saved_field in governance_fields.items():
        if _text(current.get(current_field)) != _text(snapshot.get(saved_field)):
            changed.add(current_field)
    try:
        current_host_evidence = _host_applicability_evidence(current)
    except PlantComponentRegistryError:
        changed.add("host_applicability")
    else:
        if current_host_evidence != _mapping(snapshot.get("host_applicability_at_selection")):
            changed.add("host_applicability")
        if _text(snapshot.get("requested_host")) not in current_host_evidence["scope"]:
            changed.add("requested_host")
    current_registry_version = _text(payload.get("registry_version"))
    if current_registry_version != _text(snapshot.get("registry_version")):
        changed.add("registry_version")
    changed_fields = sorted(changed)
    return {
        "status": "review_required" if changed_fields else "current",
        "changed_fields": changed_fields,
        "saved_registry_version": _text(snapshot.get("registry_version")),
        "current_registry_version": current_registry_version,
    }


def selection_qualifiers(selection: Mapping[str, Any]) -> dict[str, list[str]]:
    from services.component_output_provenance import assisted_component_provenance

    snapshot = _mapping(selection)
    attribution = _mapping(
        _mapping(snapshot.get("component_snapshot")).get("attribution")
    )
    accession = _text(snapshot.get("accession_version")) or "unavailable"
    component_id = _text(snapshot.get("registry_component_id")) or "USER_PROVIDED"
    qualifiers = {
        "component_id": [component_id],
        "component_type": [_text(snapshot.get("component_type"))],
        "accession_version": [accession],
        "evidence_tier": [_text(snapshot.get("evidence_tier"))],
        "source_organism": [_text(snapshot.get("source_organism")) or "unavailable"],
        "target_host_species": list(snapshot.get("target_host_species") or []) or ["unavailable"],
        "sequence_sha256": [_text(snapshot.get("sequence_sha256"))],
        "source_type": [_text(snapshot.get("source_type"))],
    }
    assisted = _mapping(snapshot.get("assisted_resolution"))
    if assisted:
        qualifiers.update(
            {
                "catalog_component_id": [_text(assisted.get("catalog_component_id"))],
                "catalog_name": [_text(assisted.get("catalog_name"))],
                "governance_status": [_text(assisted.get("governance_status"))],
                "admission_mode": [_text(assisted.get("admission_mode"))],
                "resolution_id": [_text(assisted.get("resolution_id"))],
                "user_sequence_sha256": [_text(assisted.get("sequence_sha256"))],
            }
        )
    provenance = assisted_component_provenance(snapshot)
    if provenance:
        if provenance['source_accession']:
            qualifiers['accession_version'] = [provenance['source_accession']]
        for qualifier, field in (
            ('catalog_component_type', 'catalog_component_type'),
            ('source_accession', 'source_accession'),
            ('sequence_authority', 'authority'),
            ('user_sequence_source', 'source_label'),
            ('reviewed_source_boundary', 'reviewed_source_boundary'),
            ('project_id', 'project_id'),
            ('confirmation_mode', 'confirmation_mode'),
        ):
            if provenance[field]:
                qualifiers[qualifier] = [provenance[field]]
        for field in ('accession_verified', 'boundary_verified_by_software'):
            value = provenance[field]
            qualifiers[field] = [str(value).lower() if isinstance(value, bool) else 'not_recorded']
    if attribution:
        qualifiers.update(
            {
                "source_database": [_text(attribution.get("source_database"))],
                "source_coordinates": [
                    _text(
                        attribution.get(
                            "source_coordinates_one_based_inclusive"
                        )
                    )
                ],
                "source_strand": [_text(attribution.get("strand"))],
                "source_record_sha256": [
                    _text(attribution.get("source_record_sha256"))
                ],
                "feature_sha256": [_text(attribution.get("feature_sha256"))],
                "component_contract": [
                    _text(attribution.get("component_contract_version"))
                ],
                "retrieval_date": [_text(attribution.get("retrieval_date"))],
                "citation": [
                    str(item)
                    for item in list(attribution.get("publication_citations") or [])
                ],
            }
        )
    return {key: values for key, values in qualifiers.items() if all(values)}


def library_view_records(path: str | Path | None = None) -> list[dict[str, Any]]:
    payload = load_registry_document(path)
    rows: list[dict[str, Any]] = []
    for raw_record in payload["records"]:
        record = _mapping(raw_record)
        component_type = _text(record.get("component_type"))
        governance_state = catalog_governance_state(record)
        governed_state = (
            governance_state
            if isinstance(governance_state, tuple)
            else ("", "", "")
        )
        rows.append(
            {
                "id": _text(record.get("component_id")),
                "catalog_record_id": _text(record.get("component_id")),
                "record_authority": "authoritative_registry",
                "catalog_status": "AUTHORITATIVE_REGISTRY",
                "registry_component_id": _text(record.get("component_id")),
                "candidate_id": "",
                "name": _text(record.get("display_name")),
                "aliases": [str(item) for item in list(record.get("aliases") or [])],
                "normalized_component_family": _text(record.get("normalized_component_family")),
                "component_role": _text(record.get("component_role")),
                "component_type": component_type,
                "type": component_type,
                "exact_variant": "",
                "sequence": _text(record.get("sequence")).upper(),
                "length": int(record.get("sequence_length") or 0),
                "sequence_sha256": _text(record.get("sequence_sha256")),
                "source_organism": _text(record.get("source_organism")),
                "organism_source_context": _text(record.get("source_organism")),
                "host_context": ", ".join(
                    str(item) for item in list(record.get("target_host_species") or [])
                ),
                "target_host_species": [str(item) for item in list(record.get("target_host_species") or [])],
                "host_applicability_scope": [
                    str(item)
                    for item in list(
                        _mapping(record.get("host_applicability")).get("scope") or []
                    )
                ],
                "evidence_tier": _text(record.get("evidence_level")),
                "accession": _text(record.get("accession_version")),
                "source": _text(record.get("primary_reference")),
                "source_database": _text(
                    _mapping(record.get("attribution")).get("source_database")
                ),
                "source_coordinates": _text(
                    _mapping(record.get("attribution")).get(
                        "source_coordinates_one_based_inclusive"
                    )
                ),
                "source_url_reference": _text(
                    _mapping(record.get("attribution")).get("record_locator")
                ),
                "feature_boundary_method": copy.deepcopy(_mapping(record.get("feature_boundary_method"))),
                "workflow_compatibility": workflow_uses_for_record(record),
                "catalog_governance_state": governance_state,
                "distribution_mode": governed_state[0],
                "sequence_availability": governed_state[1],
                "workflow_admission_status": governed_state[2],
                "formal_selectable": (
                    registry_record_is_admissible(record)
                    and bool(workflow_uses_for_record(record))
                ),
                "limitation": record_limitation(record),
                "notes": _text(record.get("notes")),
                "identity_review_status": _text(record.get("identity_review_status")) or "resolved_by_registry_record",
                "boundary_review_status": _text(record.get("boundary_review_status")) or (
                    "human_review" if any(term in (_text(record.get("notes")) + " " + _text(record.get("limitations"))).casefold() for term in ("fuzzy", "human review", "boundary")) else "reviewed"
                ),
                "source_annotations": list(record.get("source_annotations") or []) or (
                    ["来源记录注释：" + _text(record.get("component_role"))]
                    if any(term in (_text(record.get("component_role")) + " " + _text(record.get("display_name"))).casefold() for term in ("constitutive", "resistance")) else []
                ),
                "provenance_origin": _text(record.get("source_record")),
                "redistribution_status": _text(record.get("redistribution_status")),
                "registry_version": _text(payload.get("registry_version")),
            }
        )
    return rows


def reviewed_catalog_candidate_view_records(
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Project reviewed candidates into the existing Catalog row shape only."""
    rows: list[dict[str, Any]] = []
    for record in load_reviewed_catalog_candidates(path):
        candidate_id = record["candidate_id"]
        rows.append(
            {
                "id": candidate_id,
                "catalog_record_id": candidate_id,
                "record_authority": "reviewed_catalog_candidate",
                "catalog_status": CATALOG_CANDIDATE_STATUS,
                "registry_component_id": "",
                "candidate_id": candidate_id,
                "name": record["display_name"],
                "aliases": [],
                "normalized_component_family": record["normalized_component_family"],
                "component_type": record["component_type"],
                "type": record["component_type"],
                "exact_variant": record["exact_variant"],
                "sequence": record["sequence"],
                "length": int(record["length"]),
                "sequence_sha256": record["sha256"],
                "source_organism": record["organism_source_context"],
                "organism_source_context": record["organism_source_context"],
                "host_context": record["host_context"],
                # Intake host_context is provenance context, not reviewed host
                # applicability and must not enter Registry host matching.
                "target_host_species": [],
                "evidence_tier": record["evidence_tier_proposal"],
                "accession": record["accession_record_identifier"],
                "source": record["evidence_publication_reference"],
                "source_database": record["source_database"],
                "source_coordinates": record["source_coordinates_or_feature_identity"],
                "source_url_reference": record["source_url_reference"],
                "feature_boundary_method": {},
                "workflow_compatibility": [],
                "catalog_governance_state": CATALOG_CANDIDATE_STATE,
                "distribution_mode": "",
                "sequence_availability": "reviewed_intake_sequence",
                "workflow_admission_status": "not_admitted",
                "formal_selectable": False,
                "limitation": record["confidence_issues"],
                "notes": record["duplicate_equivalence_notes"],
                "identity_review_status": (
                    "human_review"
                    if any(term.casefold() in (record["confidence_issues"] + " " + record["duplicate_equivalence_notes"] + " " + record["normalized_component_family"]).casefold() for term in ("identity", "ambiguous", "aadA", "nptII", "bar/pat"))
                    else "catalog_candidate"
                ),
                "boundary_review_status": (
                    "human_review"
                    if "boundary" in (record["confidence_issues"] + " " + record["duplicate_equivalence_notes"]).casefold()
                    else "catalog_candidate"
                ),
                "source_annotations": (
                    ["来源记录注释：" + record["display_name"]]
                    if any(term in record["display_name"].casefold() for term in ("confers resistance", "constitutive")) else []
                ),
                "provenance_origin": (
                    f"{REVIEWED_CATALOG_SOURCE_COMMIT}:"
                    "data/plant_component_registry_v1/intake_20260827/candidate_inventory.csv"
                ),
                "redistribution_status": record["license_redistribution_note"],
                "registry_version": "",
                "reviewed_catalog_source_commit": REVIEWED_CATALOG_SOURCE_COMMIT,
            }
        )
    return rows


def catalog_library_view_records(
    *,
    registry_path: str | Path | None = None,
    candidate_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return one browse/search Catalog without changing Registry authority."""
    return [
        *library_view_records(registry_path),
        *reviewed_catalog_candidate_view_records(candidate_path),
    ]


_RUBY_TERMS = {"ruby", "betalain", "betalain reporter", "betalain-reporter"}


def _search_tokens(value: Any) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[a-z0-9]+", _text(value).casefold()) if token)


def catalog_search_records(records: list[Mapping[str, Any]], query: str) -> list[dict[str, Any]]:
    """Search component identity fields first; retain source context as related results."""
    terms = _search_tokens(query)
    if not terms:
        return [dict(row, search_match_kind="all", search_match_fields=[]) for row in records]
    expanded = set(terms)
    if expanded & {"ruby", "betalain"}:
        expanded.update({"cyp76ad1", "doda1", "cdopa5gt"})
    direct_fields = ("name", "normalized_component_family", "aliases", "exact_variant", "accession", "catalog_record_id", "registry_component_id", "candidate_id")
    related_fields = ("source", "source_database", "source_organism", "organism_source_context", "host_context", "source_coordinates")
    matches: list[dict[str, Any]] = []
    for row in records:
        direct_blob = " ".join(str(row.get(field) or "") if not isinstance(row.get(field), list) else " ".join(map(str, row.get(field) or [])) for field in direct_fields)
        related_blob = " ".join(str(row.get(field) or "") for field in related_fields)
        direct_tokens = set(_search_tokens(direct_blob))
        related_tokens = set(_search_tokens(related_blob))
        direct = bool(expanded <= direct_tokens or any(term in direct_tokens for term in expanded))
        related = not direct and bool(expanded <= related_tokens or any(term in related_tokens for term in expanded))
        if direct or related:
            matches.append(dict(row, search_match_kind="direct" if direct else "related", search_match_fields=[field for field in direct_fields if any(term in set(_search_tokens(str(row.get(field) or ""))) for term in expanded)]))
    return sorted(matches, key=lambda row: (0 if row["search_match_kind"] == "direct" else 1, str(row.get("name") or "").casefold(), str(row.get("catalog_record_id") or "")))


def workflow_component_options(
    *,
    role: str,
    workflow_id: str = GENERIC_MULTI_TU_WORKFLOW,
    target_host_species: str = "",
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    expected_types = ROLE_COMPONENT_TYPES.get(_text(role), frozenset())
    target = _text(target_host_species)
    options: list[dict[str, Any]] = []
    for row in library_view_records(path):
        if not row.get("formal_selectable"):
            continue
        if _text(row.get("component_type")) not in expected_types:
            continue
        if _text(workflow_id) not in list(row.get("workflow_compatibility") or []):
            continue
        try:
            selection = build_registry_selection(
                _text(row.get("registry_component_id")),
                role=role,
                workflow_id=workflow_id,
                requested_host=target,
                path=path,
            )
        except PlantComponentRegistryError:
            continue
        hosts = list(
            _mapping(selection.get("host_applicability_at_selection")).get("scope")
            or []
        )
        options.append(
            {
                **row,
                "target_host_match": bool(target and target in hosts),
                "component_reference": selection,
            }
        )
    return sorted(
        options,
        key=lambda item: (
            0 if item.get("target_host_match") else 1,
            0 if _text(item.get("evidence_tier")) == "E1" else 1,
            _text(item.get("name")).casefold(),
            _text(item.get("registry_component_id")),
        ),
    )


def exact_registry_evidence(*, sequence: str, component_types: set[str] | None = None) -> list[dict[str, Any]]:
    normalized = _text(sequence).upper()
    allowed = set(component_types or [])
    return [
        row
        for row in library_view_records()
        if _text(row.get("sequence")).upper() == normalized
        and (not allowed or _text(row.get("component_type")) in allowed)
    ]
