"""Formal offline runtime adapter for the contracted MT-01 real case."""
from __future__ import annotations

import copy
import hashlib
import json
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

from services.mvp_multi_tu_runtime import (
    MULTI_TU_EXPRESSION_ASSEMBLY,
    generate_multi_tu_combined_construct,
    multi_tu_assembly_snapshot,
)
from services.plant_component_workflow_registry import (
    DETERMINISTIC_ACCESSION_DERIVATION,
    REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
    build_accession_derived_case_selection,
    validate_saved_selection,
)


MT01_CASE_ID = "MT-01"
MT01_CONSTRUCT = "pGrDL_SP"
MT01_ACCESSION_VERSION = "KX758647.1"
MT01_RESULT_KIND = MULTI_TU_EXPRESSION_ASSEMBLY
MT01_RUNTIME_SNAPSHOT_VERSION = "mt01-formal-runtime-snapshot-v1"
MT01_CONTRACT_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "real_case_contracts_v1"
    / "mt01_pgrdl_sp"
)
MT01_CONTRACT_FILES = (
    "case_manifest.json",
    "source_contract.json",
    "extraction_contract.json",
    "component_contract.json",
    "feature_contract.json",
    "expected_hashes.json",
    "redistribution_contract.json",
)
STRICT_DNA = frozenset("ACGT")


class Mt01RuntimeError(ValueError):
    """Raised when source bytes or a saved MT-01 snapshot violate the contract."""


def _mismatch(message: str) -> Mt01RuntimeError:
    return Mt01RuntimeError(f"MT01_RUNTIME_CONTRACT_MISMATCH: {message}")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_sequence(value: str) -> str:
    return hashlib.sha256(value.upper().encode("ascii")).hexdigest()


def _reverse_complement(value: str) -> str:
    normalized = value.upper()
    invalid = sorted(set(normalized) - STRICT_DNA)
    if invalid:
        raise _mismatch(
            f"source contains unsupported nucleotide symbols: {', '.join(invalid)}"
        )
    return normalized.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _internal(interval: Mapping[str, Any]) -> tuple[int, int]:
    value = _mapping(interval.get("internal_0_based_half_open"))
    return int(value.get("start") or 0), int(value.get("end") or 0)


def load_mt01_contracts(
    contract_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    root = Path(contract_dir) if contract_dir is not None else MT01_CONTRACT_DIR
    contracts: dict[str, dict[str, Any]] = {}
    for name in MT01_CONTRACT_FILES:
        path = root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _mismatch(f"required contract cannot be read: {path}") from exc
        if not isinstance(payload, dict):
            raise _mismatch(f"contract must be one JSON object: {path}")
        if payload.get("case_id") != MT01_CASE_ID:
            raise _mismatch(f"{name} does not identify MT-01")
        contracts[name.removesuffix(".json")] = payload
    versions = {_text(item.get("contract_version")) for item in contracts.values()}
    if len(versions) != 1 or not next(iter(versions), ""):
        raise _mismatch("contract version is missing or inconsistent")
    return contracts


def _parse_source(source_bytes: bytes) -> Any:
    if not source_bytes:
        raise Mt01RuntimeError("KX758647.1 GenBank source bytes are required.")
    try:
        text = source_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Mt01RuntimeError("The MT-01 source is not an ASCII GenBank record.") from exc
    try:
        records = list(SeqIO.parse(StringIO(text), "genbank"))
    except Exception as exc:
        raise Mt01RuntimeError("The MT-01 source cannot be parsed as GenBank.") from exc
    if len(records) != 1:
        raise Mt01RuntimeError("The MT-01 source must contain exactly one GenBank record.")
    return records[0]


def _verify_source_features(record: Any, feature_contract: Mapping[str, Any]) -> None:
    for assertion in list(feature_contract.get("source_feature_assertions") or []):
        expected_start, expected_end = (
            int(assertion["source_interval"]["start"]),
            int(assertion["source_interval"]["end"]),
        )
        expected_strand = int(assertion.get("strand") or 0)
        qualifier = _mapping(assertion.get("qualifier"))
        matches = []
        for feature in record.features:
            if _text(feature.type) != _text(assertion.get("feature_type")):
                continue
            if int(feature.location.start) != expected_start or int(feature.location.end) != expected_end:
                continue
            if int(feature.location.strand or 0) != expected_strand:
                continue
            values = [str(item) for item in feature.qualifiers.get(_text(qualifier.get("key")), [])]
            if _text(qualifier.get("value")) not in values:
                continue
            matches.append(feature)
        if len(matches) != 1:
            raise Mt01RuntimeError(
                f"MT-01 source feature boundary/strand/qualifier mismatch: {assertion.get('feature_id')}"
            )
        sequence = str(record.seq[expected_start:expected_end]).upper()
        if _sha256_sequence(sequence) != _text(assertion.get("expected_sequence_sha256")):
            raise Mt01RuntimeError(
                f"MT-01 source feature sequence SHA-256 mismatch: {assertion.get('feature_id')}"
            )


def _verify_source_bytes(
    source_bytes: bytes,
    *,
    contract_dir: str | Path | None = None,
) -> tuple[Any, dict[str, Any], dict[str, dict[str, Any]]]:
    contracts = load_mt01_contracts(contract_dir)
    source_contract = contracts["source_contract"]
    expected_hashes = contracts["expected_hashes"]
    record = _parse_source(source_bytes)
    if _text(record.id) != _text(source_contract.get("record_id")):
        raise Mt01RuntimeError(
            f"MT-01 record ID mismatch: expected {MT01_ACCESSION_VERSION}, got {_text(record.id) or '<empty>'}."
        )
    sequence = str(record.seq).upper()
    expected_length = int(source_contract["parsed_record"]["length_bp"])
    if len(sequence) != expected_length:
        raise Mt01RuntimeError(
            f"MT-01 source length mismatch: expected {expected_length}, got {len(sequence)}."
        )
    topology = _text(record.annotations.get("topology")).lower()
    expected_topology = _text(source_contract["parsed_record"]["topology"]).lower()
    if topology != expected_topology:
        raise Mt01RuntimeError(
            f"MT-01 source topology mismatch: expected {expected_topology}, got {topology or '<empty>'}."
        )
    source_sha = _sha256_sequence(sequence)
    if source_sha != _text(expected_hashes.get("source_sequence_sha256")):
        raise Mt01RuntimeError(
            f"MT-01 source sequence SHA-256 mismatch: expected {expected_hashes['source_sequence_sha256']}, got {source_sha}."
        )
    _verify_source_features(record, contracts["feature_contract"])
    raw_sha = _sha256_bytes(source_bytes)
    expected_raw_sha = _text(expected_hashes.get("raw_source_file_sha256"))
    expected_raw_size = int(source_contract["expected_response"]["raw_file_size_bytes"])
    if len(source_bytes) != expected_raw_size:
        raise Mt01RuntimeError(
            f"MT-01 raw source size mismatch: expected {expected_raw_size}, got {len(source_bytes)}."
        )
    if raw_sha != expected_raw_sha:
        raise Mt01RuntimeError(
            f"MT-01 raw source SHA-256 mismatch: expected {expected_raw_sha}, got {raw_sha}."
        )
    extraction = contracts["extraction_contract"]["extraction"]
    start, end = _internal(extraction["source_interval"])
    region = sequence[start:end]
    invalid_region_symbols = sorted(set(region) - STRICT_DNA)
    if invalid_region_symbols:
        raise Mt01RuntimeError(
            "MT-01 extracted region contains unsupported nucleotide symbols: "
            + ", ".join(invalid_region_symbols)
            + "."
        )
    region_sha = _sha256_sequence(region)
    if len(region) != int(extraction["source_interval"]["length_bp"]):
        raise _mismatch("extracted region length differs from the contract")
    if region_sha != _text(expected_hashes.get("extracted_sequence_sha256")):
        raise Mt01RuntimeError(
            f"MT-01 region SHA-256 mismatch: expected {expected_hashes['extracted_sequence_sha256']}, got {region_sha}."
        )
    report = {
        "status": "pass",
        "case_id": MT01_CASE_ID,
        "source_accession_version": MT01_ACCESSION_VERSION,
        "record_id": _text(record.id),
        "source_length_bp": len(sequence),
        "source_topology": topology,
        "source_sequence_sha256": source_sha,
        "raw_file_size_bytes": len(source_bytes),
        "raw_file_sha256": raw_sha,
        "source_feature_count": len(record.features),
        "region_length_bp": len(region),
        "region_sequence_sha256": region_sha,
        "source_external_coordinates": "571..4649",
    }
    return record, report, contracts


def admit_mt01_source(
    source_bytes: bytes,
    *,
    contract_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate repository-external source bytes without returning any DNA."""
    _record, report, _contracts = _verify_source_bytes(
        source_bytes, contract_dir=contract_dir
    )
    return report


def _component_inputs(
    source_sequence: str,
    contracts: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    components: dict[str, dict[str, Any]] = {}
    sequences: dict[str, dict[str, str]] = {}
    for raw in list(contracts["component_contract"].get("components") or []):
        item = copy.deepcopy(dict(raw))
        component_id = _text(item.get("component_case_id"))
        start, end = _internal(item["source_physical_interval"])
        physical = source_sequence[start:end]
        transform = _text(item.get("ui_input_transformation"))
        ui_input = (
            _reverse_complement(physical)
            if transform == "reverse_complement_source_physical_span"
            else physical
        )
        if len(ui_input) != int(item.get("expected_input_length") or 0):
            raise _mismatch(f"{component_id} input length differs from the contract")
        if _sha256_sequence(ui_input) != _text(item.get("expected_input_sequence_sha256")):
            raise _mismatch(f"{component_id} input SHA-256 differs from the contract")
        if _sha256_sequence(physical) != _text(item.get("expected_physical_segment_sha256")):
            raise _mismatch(f"{component_id} physical SHA-256 differs from the contract")
        contract_role = _text(item.get("role"))
        role = (
            "3_prime_regulatory_region"
            if contract_role == "three_prime_regulatory_region"
            else contract_role
        )
        reference = build_accession_derived_case_selection(
            role=role,
            display_name=_text(item.get("display_name")),
            sequence=ui_input,
            accession_version=MT01_ACCESSION_VERSION,
            case_id=MT01_CASE_ID,
            contract_version=contract_version,
            component_case_id=component_id,
            source_interval=item["source_physical_interval"],
            input_transformation=transform,
        )
        components[component_id] = {
            "display_name": _text(item.get("display_name")),
            "raw_text": ui_input,
            "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
            "source_format": "plain",
            "source_name": MT01_ACCESSION_VERSION,
            "source_description": _text(item.get("annotation_limitations")),
            "provenance_reference": f"{MT01_CASE_ID}:{component_id}",
            "component_reference": reference,
        }
        sequences[component_id] = {"physical": physical, "ui_input": ui_input}
    units = [
        {
            "unit_id": "TU1",
            "unit_name": "Renilla luciferase TU",
            "display_name": "Renilla luciferase TU",
            "orientation": "reverse",
            "order": 1,
            "validation_state": "current",
            "provenance_state": DETERMINISTIC_ACCESSION_DERIVATION,
            "promoter": components["MT-01-TU1-PROMOTER-SIDE"],
            "cds": components["MT-01-TU1-CDS"],
            "3_prime_regulatory_region": components["MT-01-TU1-THREE-PRIME"],
        },
        {
            "unit_id": "TU2",
            "unit_name": "firefly luciferase TU",
            "display_name": "firefly luciferase TU",
            "orientation": "forward",
            "order": 2,
            "validation_state": "current",
            "provenance_state": DETERMINISTIC_ACCESSION_DERIVATION,
            "promoter": components["MT-01-TU2-PROMOTER-SIDE"],
            "cds": components["MT-01-TU2-CDS"],
            "3_prime_regulatory_region": components["MT-01-TU2-THREE-PRIME"],
        },
    ]
    return units, sequences


def _feature_export_type(feature_type: str) -> str:
    return feature_type if len(feature_type) <= 15 else "misc_feature"


def _feature_annotation_status(item: Mapping[str, Any]) -> str:
    if _text(item.get("role")) == "unannotated_source_sequence":
        return "UNANNOTATED_SOURCE_SEQUENCE"
    if _text(item.get("evidence_classification")) == "FACT_FROM_VERSIONED_SOURCE_FEATURE":
        return "SOURCE_ANNOTATED"
    return "DETERMINISTIC_DERIVATION"


def _mt01_genbank(sequence: str, contracts: Mapping[str, Mapping[str, Any]]) -> str:
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    record = SeqRecord(
        Seq(sequence),
        id="MT01_PGRDL_2TU",
        name="MT01_PGRDL_2TU",
        description=(
            "MT-01 deterministic KX758647.1 region 571..4649; linear two-TU "
            "expression assembly without vector background"
        ),
    )
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "linear"
    record.annotations["comment"] = (
        "result_kind=MULTI_TU_EXPRESSION_ASSEMBLY; contains_vector=false; "
        "not the complete pGrDL_SP construct; experimental performance not assessed"
    )
    for raw in list(contracts["feature_contract"].get("expected_features") or []):
        item = dict(raw)
        start = int(item["local_start"]) - 1
        end = int(item["local_end"])
        strand = int(item.get("strand") or 0)
        orientation = "reverse" if strand < 0 else "forward"
        tu_number = item.get("tu_number")
        qualifiers: dict[str, list[str]] = {
            "label": [_text(item.get("label"))],
            "feature_id": [_text(item.get("feature_id"))],
            "contract_feature_type": [_text(item.get("feature_type"))],
            "case_id": [MT01_CASE_ID],
            "contract_version": [contract_version],
            "source_accession_version": [MT01_ACCESSION_VERSION],
            "source_construct": [MT01_CONSTRUCT],
            "source_external_coordinates": [_text(item.get("source_coordinates"))],
            "source_type": [REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE],
            "case_evidence_class": [_text(item.get("evidence_classification"))],
            "role": [_text(item.get("role"))],
            "orientation": [orientation],
            "sequence_sha256": [_text(item.get("expected_sequence_sha256"))],
            "annotation_status": [_feature_annotation_status(item)],
        }
        if tu_number is not None:
            qualifiers["TU_number"] = [str(tu_number)]
        record.features.append(
            SeqFeature(
                SimpleLocation(start, end, strand=strand),
                type=_feature_export_type(_text(item.get("feature_type"))),
                qualifiers=qualifiers,
            )
        )
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue()


def _mt01_exports(
    result: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    from components.export_manager import generate_fasta_string

    exports = copy.deepcopy(_mapping(result.get("exports")))
    combined = _mapping(result.get("combined_construct"))
    sequence = _text(combined.get("dna")).upper()
    sequence_sha = _text(combined.get("sequence_sha256"))
    fasta_header = (
        f"MT-01|source={MT01_ACCESSION_VERSION}|source_region=571..4649|"
        f"result_kind={MT01_RESULT_KIND}|topology=linear|contains_vector=false|"
        f"len={len(sequence)}|sha256={sequence_sha}"
    )
    exports["combined_construct_fasta"] = {
        "label": "Export MT-01 canonical FASTA (.fasta)",
        "file_name": f"MT-01_pGrDL_SP_2TU_{sequence_sha[:16]}.fasta",
        "mime": "text/plain",
        "data": generate_fasta_string(sequence, fasta_header),
    }
    exports["combined_construct_genbank"] = {
        "label": "Export MT-01 canonical GenBank (.gb)",
        "file_name": f"MT-01_pGrDL_SP_2TU_{sequence_sha[:16]}.gb",
        "mime": "text/plain",
        "data": _mt01_genbank(sequence, contracts),
    }
    exports["metadata"] = {
        **_mapping(exports.get("metadata")),
        "case_id": MT01_CASE_ID,
        "contract_version": _text(contracts["case_manifest"].get("contract_version")),
        "source_accession_version": MT01_ACCESSION_VERSION,
        "source_external_coordinates": "571..4649",
        "result_kind": MT01_RESULT_KIND,
        "topology": "linear",
        "contains_vector": False,
    }
    return exports


def _case_snapshot(
    *,
    source_sequence: str,
    source_report: Mapping[str, Any],
    result: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    component_contract = contracts["component_contract"]
    unannotated = []
    for raw in list(component_contract.get("unannotated_intervals") or []):
        item = copy.deepcopy(dict(raw))
        source_start, source_end = _internal(item["source_interval"])
        local_start, local_end = _internal(item["local_interval"])
        sequence = source_sequence[source_start:source_end]
        if _sha256_sequence(sequence) != _text(item.get("sequence_sha256")):
            raise _mismatch(f"{item.get('junction_id')} differs from the contract")
        item["sequence"] = sequence
        item["local_start"] = local_start
        item["local_end"] = local_end
        unannotated.append(item)
    return {
        "snapshot_schema_version": MT01_RUNTIME_SNAPSHOT_VERSION,
        "verified": True,
        "case_id": MT01_CASE_ID,
        "contract_version": _text(contracts["case_manifest"].get("contract_version")),
        "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
        "case_evidence_class": DETERMINISTIC_ACCESSION_DERIVATION,
        "source_construct": MT01_CONSTRUCT,
        "source_admission": copy.deepcopy(dict(source_report)),
        "extraction": copy.deepcopy(contracts["extraction_contract"]["extraction"]),
        "components": copy.deepcopy(list(component_contract.get("components") or [])),
        "unannotated_intervals": unannotated,
        "expected_features": copy.deepcopy(
            list(contracts["feature_contract"].get("expected_features") or [])
        ),
        "canonical": {
            "length_bp": int(_mapping(result.get("combined_construct")).get("total_length") or 0),
            "sequence_sha256": _text(
                _mapping(result.get("combined_construct")).get("sequence_sha256")
            ),
            "result_kind": MT01_RESULT_KIND,
            "topology": "linear",
            "contains_vector": False,
        },
        "redistribution_status": _text(
            contracts["redistribution_contract"].get("redistribution_status")
        ),
    }


def _snapshot_digest(snapshot: Mapping[str, Any], canonical_sequence: str) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "case_snapshot": copy.deepcopy(dict(snapshot)),
                "canonical_sequence": canonical_sequence.upper(),
            }
        )
    )


def build_mt01_result(
    source_bytes: bytes,
    *,
    project_id: str,
    project_name: str = "MT-01: pGrDL_SP two-reporter 2-TU real case",
    contract_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Admit KX758647.1 and build the exact assembly through generic Multi-TU."""
    record, source_report, contracts = _verify_source_bytes(
        source_bytes, contract_dir=contract_dir
    )
    source_sequence = str(record.seq).upper()
    units, _component_sequences = _component_inputs(source_sequence, contracts)
    result = generate_multi_tu_combined_construct(
        project_id=_text(project_id),
        project_name=_text(project_name),
        expression_units=units,
    )
    result.update(
        {
            "case_id": MT01_CASE_ID,
            "case_verified": True,
            "topology": "linear",
            "contains_vector": False,
            "result_kind": MT01_RESULT_KIND,
            "case_provenance": {
                "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
                "case_id": MT01_CASE_ID,
                "case_evidence_class": DETERMINISTIC_ACCESSION_DERIVATION,
                "source_accession_version": MT01_ACCESSION_VERSION,
                "source_construct": MT01_CONSTRUCT,
                "contract_version": _text(contracts["case_manifest"].get("contract_version")),
                "source_external_coordinates": "571..4649",
                "redistribution_status": "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY",
            },
            "formal_project_context": {
                "design_scenario": "standard_plant_expression_vector",
                "host_key": "Tobacco (N. benthamiana)",
                "expression_target": "MT-01 deterministic two-TU source region",
                "construct_review_status": "current",
                "current_step": 6,
                "mt01_case_locked": True,
            },
        }
    )
    result["exports"] = _mt01_exports(result, contracts)
    snapshot = _case_snapshot(
        source_sequence=source_sequence,
        source_report=source_report,
        result=result,
        contracts=contracts,
    )
    result["case_snapshot"] = snapshot
    result["case_snapshot_sha256"] = _snapshot_digest(
        snapshot, _text(result["combined_construct"].get("dna"))
    )
    validate_mt01_result(result, contract_dir=contract_dir)
    return result


def is_mt01_claim(value: Mapping[str, Any] | None) -> bool:
    payload = _mapping(value)
    provenance = _mapping(payload.get("case_provenance"))
    snapshot = _mapping(payload.get("case_snapshot"))
    return MT01_CASE_ID in {
        _text(payload.get("case_id")),
        _text(provenance.get("case_id")),
        _text(snapshot.get("case_id")),
    }


def _validate_mt01_genbank(
    data: str,
    *,
    canonical_sequence: str,
    contracts: Mapping[str, Mapping[str, Any]],
) -> None:
    try:
        record = next(SeqIO.parse(StringIO(data), "genbank"))
    except Exception as exc:
        raise _mismatch("GenBank export cannot be parsed") from exc
    if str(record.seq).upper() != canonical_sequence.upper():
        raise _mismatch("GenBank export does not match the canonical sequence")
    if _text(record.annotations.get("topology")).lower() != "linear":
        raise _mismatch("GenBank topology is not linear")
    observed: dict[str, Any] = {}
    for feature in record.features:
        feature_id = _text((feature.qualifiers.get("feature_id") or [""])[0])
        if feature_id:
            if feature_id in observed:
                raise _mismatch(f"GenBank feature is duplicated: {feature_id}")
            observed[feature_id] = feature
    expected = {
        _text(item.get("feature_id")): dict(item)
        for item in list(contracts["feature_contract"].get("expected_features") or [])
    }
    if set(observed) != set(expected):
        raise _mismatch("GenBank expected feature set has drifted")
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    for feature_id, item in expected.items():
        feature = observed[feature_id]
        if (
            int(feature.location.start) != int(item["local_start"]) - 1
            or int(feature.location.end) != int(item["local_end"])
            or int(feature.location.strand or 0) != int(item.get("strand") or 0)
        ):
            raise _mismatch(f"GenBank feature boundary/strand drift: {feature_id}")
        required = {
            "case_id": MT01_CASE_ID,
            "contract_version": contract_version,
            "source_accession_version": MT01_ACCESSION_VERSION,
            "source_construct": MT01_CONSTRUCT,
            "source_external_coordinates": _text(item.get("source_coordinates")),
            "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
            "case_evidence_class": _text(item.get("evidence_classification")),
            "role": _text(item.get("role")),
            "orientation": "reverse" if int(item.get("strand") or 0) < 0 else "forward",
            "sequence_sha256": _text(item.get("expected_sequence_sha256")),
            "annotation_status": _feature_annotation_status(item),
        }
        for key, expected_value in required.items():
            actual = "".join(str(value) for value in feature.qualifiers.get(key, [])).replace(" ", "")
            if actual != expected_value.replace(" ", ""):
                raise _mismatch(f"GenBank qualifier drift: {feature_id}.{key}")
        if item.get("tu_number") is not None:
            if _text((feature.qualifiers.get("TU_number") or [""])[0]) != str(item["tu_number"]):
                raise _mismatch(f"GenBank TU number drift: {feature_id}")
    forbidden = {
        value.casefold()
        for value in contracts["feature_contract"].get("forbidden_feature_classes") or []
    }
    for feature in record.features:
        tokens = {
            _text(feature.type).casefold(),
            _text((feature.qualifiers.get("role") or [""])[0]).casefold(),
            _text((feature.qualifiers.get("label") or [""])[0]).casefold(),
        }
        if any(item in token for item in forbidden for token in tokens if item):
            raise _mismatch("GenBank contains a forbidden vector feature")


def validate_mt01_result(
    result: Mapping[str, Any],
    *,
    contract_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate an MT-01 result or reject any incomplete/forged MT-01 claim."""
    payload = copy.deepcopy(dict(result))
    if not is_mt01_claim(payload):
        raise _mismatch("result does not contain a complete MT-01 identity")
    contracts = load_mt01_contracts(contract_dir)
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    provenance = _mapping(payload.get("case_provenance"))
    snapshot = _mapping(payload.get("case_snapshot"))
    canonical = _mapping(payload.get("combined_construct"))
    canonical_sequence = _text(canonical.get("dna")).upper()
    fixed_pairs = {
        "case_id": (_text(payload.get("case_id")), MT01_CASE_ID),
        "result_kind": (_text(payload.get("result_kind")), MT01_RESULT_KIND),
        "topology": (_text(payload.get("topology")), "linear"),
        "contains_vector": (bool(payload.get("contains_vector")), False),
        "contract_version": (_text(provenance.get("contract_version")), contract_version),
        "source_accession_version": (
            _text(provenance.get("source_accession_version")),
            MT01_ACCESSION_VERSION,
        ),
        "source_type": (
            _text(provenance.get("source_type")),
            REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
        ),
        "case_evidence_class": (
            _text(provenance.get("case_evidence_class")),
            DETERMINISTIC_ACCESSION_DERIVATION,
        ),
    }
    for label, (actual, expected) in fixed_pairs.items():
        if actual != expected:
            raise _mismatch(f"{label} expected {expected!r}, got {actual!r}")
    if not bool(payload.get("case_verified")) or not bool(snapshot.get("verified")):
        raise _mismatch("verified state is absent")
    if _text(snapshot.get("snapshot_schema_version")) != MT01_RUNTIME_SNAPSHOT_VERSION:
        raise _mismatch("case snapshot schema version is unsupported")
    if _text(snapshot.get("contract_version")) != contract_version:
        raise _mismatch(
            f"saved contract version {_text(snapshot.get('contract_version')) or '<empty>'} differs from current {contract_version}"
        )
    if (
        _text(snapshot.get("case_id")) != MT01_CASE_ID
        or _text(snapshot.get("source_type"))
        != REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
        or _text(snapshot.get("case_evidence_class"))
        != DETERMINISTIC_ACCESSION_DERIVATION
        or _text(snapshot.get("source_construct")) != MT01_CONSTRUCT
        or snapshot.get("extraction") != contracts["extraction_contract"].get("extraction")
    ):
        raise _mismatch("case snapshot identity or extraction contract has drifted")
    source_admission = _mapping(snapshot.get("source_admission"))
    source_contract = contracts["source_contract"]
    expected_hashes = contracts["expected_hashes"]
    source_checks = {
        "record_id": MT01_ACCESSION_VERSION,
        "source_length_bp": int(source_contract["parsed_record"]["length_bp"]),
        "source_topology": _text(source_contract["parsed_record"]["topology"]),
        "source_sequence_sha256": _text(expected_hashes["source_sequence_sha256"]),
        "raw_file_size_bytes": int(source_contract["expected_response"]["raw_file_size_bytes"]),
        "raw_file_sha256": _text(expected_hashes["raw_source_file_sha256"]),
        "region_length_bp": 4079,
        "region_sequence_sha256": _text(expected_hashes["extracted_sequence_sha256"]),
        "source_external_coordinates": "571..4649",
    }
    for key, expected in source_checks.items():
        if source_admission.get(key) != expected:
            raise _mismatch(f"saved source admission field has drifted: {key}")
    expected_snapshot_sha = _snapshot_digest(snapshot, canonical_sequence)
    if _text(payload.get("case_snapshot_sha256")) != expected_snapshot_sha:
        raise _mismatch("case snapshot checksum does not match canonical bytes")
    if len(canonical_sequence) != 4079 or int(canonical.get("total_length") or 0) != 4079:
        raise _mismatch("canonical length is not 4,079 bp")
    canonical_sha = _sha256_sequence(canonical_sequence)
    if canonical_sha != _text(expected_hashes.get("extracted_sequence_sha256")):
        raise _mismatch("canonical sequence SHA-256 differs from the contract")
    if _text(canonical.get("sequence_sha256")) != canonical_sha:
        raise _mismatch("canonical sequence and recorded SHA-256 differ")
    try:
        active = multi_tu_assembly_snapshot(_mapping(payload.get("runtime")))
    except Exception as exc:
        raise _mismatch(f"canonical runtime is invalid: {exc}") from exc
    if _mapping(active.get("combined_construct")) != canonical:
        raise _mismatch("canonical runtime and result snapshot differ")
    if (
        list(payload.get("expression_units") or [])
        != list(active.get("expression_units") or [])
        or list(payload.get("unit_order") or []) != list(active.get("unit_order") or [])
    ):
        raise _mismatch("result expression-unit snapshot differs from canonical runtime")
    units = sorted(
        list(active.get("expression_units") or []),
        key=lambda item: int(item.get("order") or 0),
    )
    expected_tus = list(contracts["extraction_contract"].get("transcription_units") or [])
    if len(units) != 2 or list(active.get("unit_order") or []) != ["TU1", "TU2"]:
        raise _mismatch("TU count or order differs from the contract")
    for index, (unit, expected) in enumerate(zip(units, expected_tus), start=1):
        local_start, local_end = _internal(expected["local_interval"])
        expected_unit_sha = _text(expected_hashes["transcription_units"][f"TU{index}"])
        if (
            _text(unit.get("unit_id")) != f"TU{index}"
            or _text(unit.get("orientation")) != _text(expected.get("orientation"))
            or int(_mapping(unit.get("range")).get("start") or 0) != local_start + 1
            or int(_mapping(unit.get("range")).get("end") or 0) != local_end
            or _text(unit.get("sequence_sha256")) != expected_unit_sha
        ):
            raise _mismatch(f"TU{index} identity/orientation/boundary/SHA has drifted")
    original_units = {
        _text(item.get("unit_id")): _mapping(item)
        for item in list(_mapping(payload.get("original_input")).get("expression_units") or [])
    }
    component_contracts = {
        _text(item.get("component_case_id")): dict(item)
        for item in list(contracts["component_contract"].get("components") or [])
    }
    for unit_id, role, component_id in (
        ("TU1", "promoter", "MT-01-TU1-PROMOTER-SIDE"),
        ("TU1", "cds", "MT-01-TU1-CDS"),
        ("TU1", "3_prime_regulatory_region", "MT-01-TU1-THREE-PRIME"),
        ("TU2", "promoter", "MT-01-TU2-PROMOTER-SIDE"),
        ("TU2", "cds", "MT-01-TU2-CDS"),
        ("TU2", "3_prime_regulatory_region", "MT-01-TU2-THREE-PRIME"),
    ):
        component_input = _mapping(original_units.get(unit_id, {}).get(role))
        reference = validate_saved_selection(
            _mapping(component_input.get("component_reference")),
            role=role,
            sequence=_text(
                _mapping(component_input.get("component_reference")).get("selected_sequence")
            ),
        )
        contract = component_contracts[component_id]
        component_snapshot = _mapping(reference.get("component_snapshot"))
        if (
            _text(reference.get("source_type")) != REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
            or _text(component_snapshot.get("component_case_id")) != component_id
            or _text(reference.get("sequence_sha256"))
            != _text(contract.get("expected_input_sequence_sha256"))
            or component_snapshot.get("source_interval")
            != contract.get("source_physical_interval")
            or _text(component_snapshot.get("input_transformation"))
            != _text(contract.get("ui_input_transformation"))
        ):
            raise _mismatch(f"component snapshot has drifted: {component_id}")
    unannotated = list(snapshot.get("unannotated_intervals") or [])
    expected_unannotated = list(
        contracts["component_contract"].get("unannotated_intervals") or []
    )
    if len(unannotated) != 5 or sum(
        int(_mapping(item.get("local_interval")).get("length_bp") or 0)
        for item in unannotated
    ) != 326:
        raise _mismatch("five unannotated source intervals totaling 326 bp are required")
    for saved, expected in zip(unannotated, expected_unannotated):
        if _text(saved.get("junction_id")) != _text(expected.get("junction_id")):
            raise _mismatch("unannotated source interval order has drifted")
        local_start, local_end = _internal(expected["local_interval"])
        interval_sequence = canonical_sequence[local_start:local_end]
        if (
            _text(saved.get("sequence")) != interval_sequence
            or _sha256_sequence(interval_sequence) != _text(expected.get("sequence_sha256"))
            or saved.get("source_interval") != expected.get("source_interval")
            or saved.get("local_interval") != expected.get("local_interval")
        ):
            raise _mismatch(f"unannotated source interval has drifted: {saved.get('junction_id')}")
    if snapshot.get("expected_features") != contracts["feature_contract"].get("expected_features"):
        raise _mismatch("expected feature snapshot differs from the contract")
    exports = _mapping(payload.get("exports"))
    try:
        fasta = next(
            SeqIO.parse(
                StringIO(_text(_mapping(exports.get("combined_construct_fasta")).get("data"))),
                "fasta",
            )
        )
    except Exception as exc:
        raise _mismatch("FASTA export cannot be parsed") from exc
    if str(fasta.seq).upper() != canonical_sequence:
        raise _mismatch("FASTA export does not match the canonical sequence")
    _validate_mt01_genbank(
        _text(_mapping(exports.get("combined_construct_genbank")).get("data")),
        canonical_sequence=canonical_sequence,
        contracts=contracts,
    )
    return {
        "status": "pass",
        "case_id": MT01_CASE_ID,
        "contract_version": contract_version,
        "canonical_length_bp": len(canonical_sequence),
        "canonical_sequence_sha256": canonical_sha,
        "tu_count": len(units),
        "unannotated_interval_count": len(unannotated),
        "unannotated_length_bp": 326,
        "contains_vector": False,
        "topology": "linear",
    }
