"""Formal offline runtime adapter for the contracted MT-02 real case."""
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


MT02_CASE_ID = "MT-02"
MT02_CONSTRUCT = "pDOE-13"
MT02_ACCESSION_VERSION = "KM507054.1"
MT02_RESULT_KIND = MULTI_TU_EXPRESSION_ASSEMBLY
MT02_RUNTIME_SNAPSHOT_VERSION = "mt02-formal-runtime-snapshot-v1"
MT02_CONTRACT_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "real_case_contracts_v1"
    / "mt02_pdoe13"
)
MT02_CONTRACT_FILES = (
    "case_manifest.json",
    "source_contract.json",
    "extraction_contract.json",
    "component_contract.json",
    "feature_contract.json",
    "expected_hashes.json",
    "redistribution_contract.json",
)
STRICT_DNA = frozenset("ACGT")


class Mt02RuntimeError(ValueError):
    """Raised when source bytes or a saved MT-02 snapshot violate the contract."""


def _mismatch(message: str) -> Mt02RuntimeError:
    return Mt02RuntimeError(f"MT02_RUNTIME_CONTRACT_MISMATCH: {message}")


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


def _canonical_interval(value: Mapping[str, Any]) -> tuple[int, int]:
    interval = value.get("canonical_interval") or value.get("canonical_physical_interval")
    return _internal(_mapping(interval))


def _external_coordinates(start: int, end: int) -> str:
    return f"{start + 1}..{end}"


def load_mt02_contracts(
    contract_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    root = Path(contract_dir) if contract_dir is not None else MT02_CONTRACT_DIR
    contracts: dict[str, dict[str, Any]] = {}
    for name in MT02_CONTRACT_FILES:
        path = root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _mismatch(f"required contract cannot be read: {path}") from exc
        if not isinstance(payload, dict):
            raise _mismatch(f"contract must be one JSON object: {path}")
        if payload.get("case_id") != MT02_CASE_ID:
            raise _mismatch(f"{name} does not identify MT-02")
        contracts[name.removesuffix(".json")] = payload
    versions = {_text(item.get("contract_version")) for item in contracts.values()}
    if len(versions) != 1 or not next(iter(versions), ""):
        raise _mismatch("contract version is missing or inconsistent")
    return contracts


def _parse_source(source_bytes: bytes) -> Any:
    if not source_bytes:
        raise Mt02RuntimeError("KM507054.1 GenBank source bytes are required.")
    try:
        text = source_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Mt02RuntimeError("The MT-02 source is not an ASCII GenBank record.") from exc
    try:
        records = list(SeqIO.parse(StringIO(text), "genbank"))
    except Exception as exc:
        raise Mt02RuntimeError("The MT-02 source cannot be parsed as GenBank.") from exc
    if len(records) != 1:
        raise Mt02RuntimeError("The MT-02 source must contain exactly one GenBank record.")
    return records[0]


def _verify_source_features(record: Any, feature_contract: Mapping[str, Any]) -> None:
    for assertion in list(feature_contract.get("source_feature_assertions") or []):
        interval = _mapping(assertion.get("source_interval"))
        expected_start = int(interval.get("start") or 0)
        expected_end = int(interval.get("end") or 0)
        expected_strand = int(assertion.get("strand") or 0)
        qualifier = _mapping(assertion.get("qualifier"))
        matches = []
        for feature in record.features:
            if _text(feature.type) != _text(assertion.get("feature_type")):
                continue
            if (
                int(feature.location.start) != expected_start
                or int(feature.location.end) != expected_end
                or int(feature.location.strand or 0) != expected_strand
            ):
                continue
            values = [
                str(item)
                for item in feature.qualifiers.get(_text(qualifier.get("key")), [])
            ]
            if _text(qualifier.get("value")) not in values:
                continue
            matches.append(feature)
        if len(matches) != 1:
            raise Mt02RuntimeError(
                "MT-02 source feature boundary/strand/qualifier mismatch: "
                f"{assertion.get('feature_id')}"
            )
        sequence = str(record.seq[expected_start:expected_end]).upper()
        if _sha256_sequence(sequence) != _text(
            assertion.get("expected_sequence_sha256")
        ):
            raise Mt02RuntimeError(
                "MT-02 source feature sequence SHA-256 mismatch: "
                f"{assertion.get('feature_id')}"
            )


def _verify_source_bytes(
    source_bytes: bytes,
    *,
    contract_dir: str | Path | None = None,
) -> tuple[Any, dict[str, Any], dict[str, dict[str, Any]]]:
    contracts = load_mt02_contracts(contract_dir)
    source_contract = contracts["source_contract"]
    expected_hashes = contracts["expected_hashes"]
    record = _parse_source(source_bytes)
    if _text(record.id) != _text(source_contract.get("record_id")):
        raise Mt02RuntimeError(
            f"MT-02 record ID mismatch: expected {MT02_ACCESSION_VERSION}, "
            f"got {_text(record.id) or '<empty>'}."
        )
    sequence = str(record.seq).upper()
    expected_length = int(source_contract["parsed_record"]["length_bp"])
    if len(sequence) != expected_length:
        raise Mt02RuntimeError(
            f"MT-02 source length mismatch: expected {expected_length}, got {len(sequence)}."
        )
    topology = _text(record.annotations.get("topology")).lower()
    expected_topology = _text(source_contract["parsed_record"]["topology"]).lower()
    if topology != expected_topology:
        raise Mt02RuntimeError(
            f"MT-02 source topology mismatch: expected {expected_topology}, "
            f"got {topology or '<empty>'}."
        )
    source_sha = _sha256_sequence(sequence)
    if source_sha != _text(expected_hashes.get("source_sequence_sha256")):
        raise Mt02RuntimeError(
            "MT-02 source sequence SHA-256 mismatch: expected "
            f"{expected_hashes['source_sequence_sha256']}, got {source_sha}."
        )
    expected_source_features = int(
        expected_hashes["drift_detection"]["source_feature_count"]
    )
    if len(record.features) != expected_source_features:
        raise Mt02RuntimeError(
            "MT-02 source feature count mismatch: expected "
            f"{expected_source_features}, got {len(record.features)}."
        )
    _verify_source_features(record, contracts["feature_contract"])
    raw_sha = _sha256_bytes(source_bytes)
    expected_raw_sha = _text(expected_hashes.get("raw_source_file_sha256"))
    expected_raw_size = int(source_contract["expected_response"]["raw_file_size_bytes"])
    if len(source_bytes) != expected_raw_size:
        raise Mt02RuntimeError(
            f"MT-02 raw source size mismatch: expected {expected_raw_size}, "
            f"got {len(source_bytes)}."
        )
    if raw_sha != expected_raw_sha:
        raise Mt02RuntimeError(
            f"MT-02 raw source SHA-256 mismatch: expected {expected_raw_sha}, got {raw_sha}."
        )
    extraction = contracts["extraction_contract"]["extraction"]
    start, end = _internal(extraction["source_interval"])
    region = sequence[start:end]
    invalid = sorted(set(region) - STRICT_DNA)
    if invalid:
        raise Mt02RuntimeError(
            "MT-02 extracted region contains unsupported nucleotide symbols: "
            + ", ".join(invalid)
            + "."
        )
    region_sha = _sha256_sequence(region)
    if len(region) != int(extraction["source_interval"]["length_bp"]):
        raise _mismatch("extracted region length differs from the contract")
    if region_sha != _text(expected_hashes.get("canonical_sequence_sha256")):
        raise Mt02RuntimeError(
            "MT-02 region SHA-256 mismatch: expected "
            f"{expected_hashes['canonical_sequence_sha256']}, got {region_sha}."
        )
    report = {
        "status": "pass",
        "case_id": MT02_CASE_ID,
        "source_accession_version": MT02_ACCESSION_VERSION,
        "record_id": _text(record.id),
        "source_length_bp": len(sequence),
        "source_topology": topology,
        "source_sequence_sha256": source_sha,
        "raw_file_size_bytes": len(source_bytes),
        "raw_file_sha256": raw_sha,
        "source_feature_count": len(record.features),
        "selected_source_feature_count": len(
            contracts["feature_contract"].get("source_feature_assertions") or []
        ),
        "region_length_bp": len(region),
        "region_sequence_sha256": region_sha,
        "source_external_coordinates": "111..6719",
    }
    return record, report, contracts


def admit_mt02_source(
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
) -> list[dict[str, Any]]:
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    components: dict[str, dict[str, Any]] = {}
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
        if _sha256_sequence(ui_input) != _text(
            item.get("expected_input_sequence_sha256")
        ):
            raise _mismatch(f"{component_id} input SHA-256 differs from the contract")
        if _sha256_sequence(physical) != _text(
            item.get("expected_physical_segment_sha256")
        ):
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
            accession_version=MT02_ACCESSION_VERSION,
            case_id=MT02_CASE_ID,
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
            "source_name": MT02_ACCESSION_VERSION,
            "source_description": _text(item.get("annotation_limitations")),
            "provenance_reference": f"{MT02_CASE_ID}:{component_id}",
            "component_reference": reference,
        }
    units = []
    for tu in list(contracts["extraction_contract"].get("transcription_units") or []):
        number = int(tu.get("tu_number") or 0)
        prefix = f"MT-02-TU{number}-"
        units.append(
            {
                "unit_id": f"TU{number}",
                "unit_name": _text(tu.get("identity")),
                "display_name": _text(tu.get("identity")),
                "orientation": _text(tu.get("orientation")),
                "order": number,
                "validation_state": "current",
                "provenance_state": DETERMINISTIC_ACCESSION_DERIVATION,
                "promoter": components[prefix + "PROMOTER-SIDE"],
                "cds": components[prefix + "CDS"],
                "3_prime_regulatory_region": components[prefix + "THREE-PRIME"],
            }
        )
    return units


def _expected_features(
    canonical_sequence: str,
    contracts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for raw in list(contracts["feature_contract"].get("source_feature_assertions") or []):
        item = copy.deepcopy(dict(raw))
        source = _mapping(item.get("source_interval"))
        canonical = _mapping(item.get("canonical_interval"))
        qualifier = _mapping(item.get("qualifier"))
        features.append(
            {
                "feature_id": _text(item.get("feature_id")),
                "feature_type": _text(item.get("feature_type")),
                "role": "source_annotation",
                "label": _text(qualifier.get("value")),
                "canonical_start": int(canonical.get("start") or 0),
                "canonical_end": int(canonical.get("end") or 0),
                "strand": int(item.get("strand") or 0),
                "source_coordinates": _external_coordinates(
                    int(source.get("start") or 0), int(source.get("end") or 0)
                ),
                "expected_sequence_sha256": _text(
                    item.get("expected_sequence_sha256")
                ),
                "evidence_classification": _text(
                    item.get("evidence_classification")
                ),
                "annotation_status": "SOURCE_ANNOTATED",
                "source_qualifier_key": _text(qualifier.get("key")),
                "source_qualifier_value": _text(qualifier.get("value")),
            }
        )
    extraction = contracts["extraction_contract"]
    extraction_item = extraction["extraction"]
    source_start, source_end = _internal(extraction_item["source_interval"])
    features.append(
        {
            "feature_id": "MT-02-EF-SOURCE",
            "feature_type": "source",
            "role": "source_region",
            "label": "KM507054.1 deterministic source region",
            "canonical_start": 0,
            "canonical_end": len(canonical_sequence),
            "strand": 1,
            "source_coordinates": _external_coordinates(source_start, source_end),
            "expected_sequence_sha256": _sha256_sequence(canonical_sequence),
            "evidence_classification": "DETERMINISTIC_DERIVATION",
            "annotation_status": "DETERMINISTIC_DERIVATION",
        }
    )
    for tu in list(extraction.get("transcription_units") or []):
        number = int(tu.get("tu_number") or 0)
        start, end = _canonical_interval(tu)
        source_start, source_end = _internal(tu["source_interval"])
        features.append(
            {
                "feature_id": f"MT-02-EF-TU{number}",
                "feature_type": "transcription_unit",
                "role": _text(tu.get("role")),
                "label": _text(tu.get("identity")),
                "canonical_start": start,
                "canonical_end": end,
                "strand": int(tu.get("strand") or 0),
                "source_coordinates": _external_coordinates(source_start, source_end),
                "expected_sequence_sha256": _sha256_sequence(
                    canonical_sequence[start:end]
                ),
                "evidence_classification": "DETERMINISTIC_DERIVATION",
                "annotation_status": "DETERMINISTIC_DERIVATION",
                "tu_number": number,
            }
        )
    for index, raw in enumerate(
        list(contracts["component_contract"].get("components") or []), start=1
    ):
        item = dict(raw)
        start, end = _canonical_interval(item)
        source_start, source_end = _internal(item["source_physical_interval"])
        role = _text(item.get("role"))
        features.append(
            {
                "feature_id": f"MT-02-EF-C{index:02d}",
                "feature_type": "CDS" if role == "cds" else "regulatory_region",
                "role": role,
                "label": _text(item.get("display_name")),
                "canonical_start": start,
                "canonical_end": end,
                "strand": int(item.get("strand") or 0),
                "source_coordinates": _external_coordinates(source_start, source_end),
                "expected_sequence_sha256": _text(
                    item.get("expected_physical_segment_sha256")
                ),
                "evidence_classification": "DETERMINISTIC_DERIVATION",
                "annotation_status": "DETERMINISTIC_DERIVATION",
                "tu_number": int(item.get("tu_number") or 0),
            }
        )
    for index, raw in enumerate(
        list(contracts["component_contract"].get("unannotated_intervals") or []),
        start=1,
    ):
        item = dict(raw)
        start, end = _canonical_interval(item)
        source_start, source_end = _internal(item["source_interval"])
        features.append(
            {
                "feature_id": f"MT-02-EF-U{index:02d}",
                "feature_type": "misc_feature",
                "role": "unannotated_source_sequence",
                "label": _text(item.get("unannotated_id")),
                "canonical_start": start,
                "canonical_end": end,
                "strand": 1,
                "source_coordinates": _external_coordinates(source_start, source_end),
                "expected_sequence_sha256": _text(item.get("sequence_sha256")),
                "evidence_classification": "DETERMINISTIC_DERIVATION",
                "annotation_status": "UNANNOTATED_SOURCE_SEQUENCE",
            }
        )
    expected_count = int(contracts["feature_contract"].get("expected_feature_count") or 0)
    if len(features) != expected_count:
        raise _mismatch(
            f"expected feature count is {len(features)}, contract requires {expected_count}"
        )
    return features


def _feature_export_type(feature_type: str) -> str:
    return feature_type if len(feature_type) <= 15 else "misc_feature"


def _mt02_genbank(
    sequence: str,
    contracts: Mapping[str, Mapping[str, Any]],
    expected_features: list[dict[str, Any]],
) -> str:
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    record = SeqRecord(
        Seq(sequence),
        id="MT02_PDOE13_3TU",
        name="MT02_PDOE13_3TU",
        description=(
            "MT-02 deterministic KM507054.1 region 111..6719; linear three-TU "
            "expression assembly without vector background"
        ),
    )
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "linear"
    record.annotations["comment"] = (
        "result_kind=MULTI_TU_EXPRESSION_ASSEMBLY; contains_vector=false; "
        "not the complete pDOE-13 construct; experimental performance not assessed"
    )
    for item in expected_features:
        strand = int(item.get("strand") or 0)
        qualifiers: dict[str, list[str]] = {
            "label": [_text(item.get("label"))],
            "feature_id": [_text(item.get("feature_id"))],
            "contract_feature_type": [_text(item.get("feature_type"))],
            "case_id": [MT02_CASE_ID],
            "contract_version": [contract_version],
            "source_accession_version": [MT02_ACCESSION_VERSION],
            "source_construct": [MT02_CONSTRUCT],
            "source_external_coordinates": [_text(item.get("source_coordinates"))],
            "source_type": [REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE],
            "case_evidence_class": [_text(item.get("evidence_classification"))],
            "role": [_text(item.get("role"))],
            "orientation": ["reverse" if strand < 0 else "forward"],
            "sequence_sha256": [_text(item.get("expected_sequence_sha256"))],
            "annotation_status": [_text(item.get("annotation_status"))],
        }
        if item.get("tu_number") is not None:
            qualifiers["TU_number"] = [str(item["tu_number"])]
        if _text(item.get("source_qualifier_key")):
            qualifiers["source_qualifier_key"] = [
                _text(item.get("source_qualifier_key"))
            ]
            qualifiers["source_qualifier_value"] = [
                _text(item.get("source_qualifier_value"))
            ]
        record.features.append(
            SeqFeature(
                SimpleLocation(
                    int(item["canonical_start"]),
                    int(item["canonical_end"]),
                    strand=strand,
                ),
                type=_feature_export_type(_text(item.get("feature_type"))),
                qualifiers=qualifiers,
            )
        )
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue()


def _mt02_exports(
    result: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
    expected_features: list[dict[str, Any]],
) -> dict[str, Any]:
    from components.export_manager import generate_fasta_string

    exports = copy.deepcopy(_mapping(result.get("exports")))
    combined = _mapping(result.get("combined_construct"))
    sequence = _text(combined.get("dna")).upper()
    sequence_sha = _text(combined.get("sequence_sha256"))
    fasta_header = (
        f"MT-02|source={MT02_ACCESSION_VERSION}|source_region=111..6719|"
        f"result_kind={MT02_RESULT_KIND}|topology=linear|contains_vector=false|"
        f"len={len(sequence)}|sha256={sequence_sha}"
    )
    exports["combined_construct_fasta"] = {
        "label": "Export MT-02 canonical FASTA (.fasta)",
        "file_name": f"MT-02_pDOE-13_3TU_{sequence_sha[:16]}.fasta",
        "mime": "text/plain",
        "data": generate_fasta_string(sequence, fasta_header),
    }
    exports["combined_construct_genbank"] = {
        "label": "Export MT-02 canonical GenBank (.gb)",
        "file_name": f"MT-02_pDOE-13_3TU_{sequence_sha[:16]}.gb",
        "mime": "text/plain",
        "data": _mt02_genbank(sequence, contracts, expected_features),
    }
    exports["metadata"] = {
        **_mapping(exports.get("metadata")),
        "case_id": MT02_CASE_ID,
        "contract_version": _text(contracts["case_manifest"].get("contract_version")),
        "source_accession_version": MT02_ACCESSION_VERSION,
        "source_external_coordinates": "111..6719",
        "result_kind": MT02_RESULT_KIND,
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
    expected_features: list[dict[str, Any]],
) -> dict[str, Any]:
    component_contract = contracts["component_contract"]
    unannotated = []
    for raw in list(component_contract.get("unannotated_intervals") or []):
        item = copy.deepcopy(dict(raw))
        source_start, source_end = _internal(item["source_interval"])
        canonical_start, canonical_end = _canonical_interval(item)
        sequence = source_sequence[source_start:source_end]
        if _sha256_sequence(sequence) != _text(item.get("sequence_sha256")):
            raise _mismatch(f"{item.get('unannotated_id')} differs from the contract")
        item["sequence"] = sequence
        item["canonical_start"] = canonical_start
        item["canonical_end"] = canonical_end
        unannotated.append(item)
    return {
        "snapshot_schema_version": MT02_RUNTIME_SNAPSHOT_VERSION,
        "verified": True,
        "case_id": MT02_CASE_ID,
        "contract_version": _text(contracts["case_manifest"].get("contract_version")),
        "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
        "case_evidence_class": DETERMINISTIC_ACCESSION_DERIVATION,
        "source_construct": MT02_CONSTRUCT,
        "source_admission": copy.deepcopy(dict(source_report)),
        "extraction": copy.deepcopy(contracts["extraction_contract"]["extraction"]),
        "transcription_units": copy.deepcopy(
            list(contracts["extraction_contract"].get("transcription_units") or [])
        ),
        "junctions": copy.deepcopy(
            list(contracts["extraction_contract"].get("junctions") or [])
        ),
        "components": copy.deepcopy(list(component_contract.get("components") or [])),
        "unannotated_intervals": unannotated,
        "atomic_partition": copy.deepcopy(
            list(component_contract.get("atomic_partition") or [])
        ),
        "expected_features": copy.deepcopy(expected_features),
        "expected_pairwise_source_feature_overlap_count": int(
            contracts["feature_contract"].get(
                "expected_pairwise_source_feature_overlap_count"
            )
            or 0
        ),
        "canonical": {
            "length_bp": int(_mapping(result.get("combined_construct")).get("total_length") or 0),
            "sequence_sha256": _text(
                _mapping(result.get("combined_construct")).get("sequence_sha256")
            ),
            "result_kind": MT02_RESULT_KIND,
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


def build_mt02_result(
    source_bytes: bytes,
    *,
    project_id: str,
    project_name: str = "MT-02: pDOE-13 three-TU real case",
    contract_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Admit KM507054.1 and build the exact assembly through generic Multi-TU."""
    record, source_report, contracts = _verify_source_bytes(
        source_bytes, contract_dir=contract_dir
    )
    source_sequence = str(record.seq).upper()
    units = _component_inputs(source_sequence, contracts)
    result = generate_multi_tu_combined_construct(
        project_id=_text(project_id),
        project_name=_text(project_name),
        expression_units=units,
    )
    result.update(
        {
            "case_id": MT02_CASE_ID,
            "case_verified": True,
            "topology": "linear",
            "contains_vector": False,
            "result_kind": MT02_RESULT_KIND,
            "case_provenance": {
                "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
                "case_id": MT02_CASE_ID,
                "case_evidence_class": DETERMINISTIC_ACCESSION_DERIVATION,
                "source_accession_version": MT02_ACCESSION_VERSION,
                "source_construct": MT02_CONSTRUCT,
                "contract_version": _text(contracts["case_manifest"].get("contract_version")),
                "source_external_coordinates": "111..6719",
                "redistribution_status": "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY",
            },
            "formal_project_context": {
                "design_scenario": "standard_plant_expression_vector",
                "host_key": "Tobacco (N. benthamiana)",
                "expression_target": "MT-02 deterministic three-TU source region",
                "construct_review_status": "current",
                "current_step": 6,
                "mt02_case_locked": True,
            },
        }
    )
    canonical_sequence = _text(result["combined_construct"].get("dna")).upper()
    expected_features = _expected_features(canonical_sequence, contracts)
    result["exports"] = _mt02_exports(result, contracts, expected_features)
    snapshot = _case_snapshot(
        source_sequence=source_sequence,
        source_report=source_report,
        result=result,
        contracts=contracts,
        expected_features=expected_features,
    )
    result["case_snapshot"] = snapshot
    result["case_snapshot_sha256"] = _snapshot_digest(snapshot, canonical_sequence)
    validate_mt02_result(result, contract_dir=contract_dir)
    return result


def is_mt02_claim(value: Mapping[str, Any] | None) -> bool:
    payload = _mapping(value)
    provenance = _mapping(payload.get("case_provenance"))
    snapshot = _mapping(payload.get("case_snapshot"))
    return MT02_CASE_ID in {
        _text(payload.get("case_id")),
        _text(provenance.get("case_id")),
        _text(snapshot.get("case_id")),
    }


def _validate_mt02_genbank(
    data: str,
    *,
    canonical_sequence: str,
    contracts: Mapping[str, Mapping[str, Any]],
    expected_features: list[dict[str, Any]],
) -> None:
    try:
        records = list(SeqIO.parse(StringIO(data), "genbank"))
    except Exception as exc:
        raise _mismatch("GenBank export cannot be parsed") from exc
    if len(records) != 1:
        raise _mismatch("GenBank export must contain exactly one record")
    record = records[0]
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
    expected = {_text(item.get("feature_id")): item for item in expected_features}
    if set(observed) != set(expected):
        raise _mismatch("GenBank expected feature set has drifted")
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    for feature_id, item in expected.items():
        feature = observed[feature_id]
        if (
            int(feature.location.start) != int(item["canonical_start"])
            or int(feature.location.end) != int(item["canonical_end"])
            or int(feature.location.strand or 0) != int(item.get("strand") or 0)
        ):
            raise _mismatch(f"GenBank feature boundary/strand drift: {feature_id}")
        strand = int(item.get("strand") or 0)
        required = {
            "case_id": MT02_CASE_ID,
            "contract_version": contract_version,
            "source_accession_version": MT02_ACCESSION_VERSION,
            "source_construct": MT02_CONSTRUCT,
            "source_external_coordinates": _text(item.get("source_coordinates")),
            "source_type": REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
            "case_evidence_class": _text(item.get("evidence_classification")),
            "role": _text(item.get("role")),
            "orientation": "reverse" if strand < 0 else "forward",
            "sequence_sha256": _text(item.get("expected_sequence_sha256")),
            "annotation_status": _text(item.get("annotation_status")),
        }
        for key, expected_value in required.items():
            actual = "".join(
                str(value) for value in feature.qualifiers.get(key, [])
            ).replace(" ", "")
            if actual != expected_value.replace(" ", ""):
                raise _mismatch(f"GenBank qualifier drift: {feature_id}.{key}")
        if item.get("tu_number") is not None and _text(
            (feature.qualifiers.get("TU_number") or [""])[0]
        ) != str(item["tu_number"]):
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


def _validate_component_references(
    payload: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> None:
    expected_components = {
        _text(item.get("component_case_id")): dict(item)
        for item in contracts["component_contract"].get("components") or []
    }
    seen: set[str] = set()
    for unit in _mapping(payload.get("original_input")).get("expression_units") or []:
        for role in ("promoter", "cds", "3_prime_regulatory_region"):
            component = _mapping(_mapping(unit).get(role))
            reference = _mapping(component.get("component_reference"))
            component_id = _text(
                _mapping(reference.get("component_snapshot")).get("component_case_id")
            )
            expected = expected_components.get(component_id)
            if expected is None or component_id in seen:
                raise _mismatch("component snapshot membership has drifted")
            seen.add(component_id)
            try:
                validate_saved_selection(
                    reference,
                    role=role,
                    sequence=_text(reference.get("selected_sequence")),
                )
            except Exception as exc:
                raise _mismatch(f"component snapshot is invalid: {component_id}") from exc
            if (
                _text(reference.get("source_type"))
                != REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
                or _text(reference.get("accession_version"))
                != MT02_ACCESSION_VERSION
                or _text(_mapping(reference.get("component_snapshot")).get("case_id"))
                != MT02_CASE_ID
                or _text(
                    _mapping(reference.get("component_snapshot")).get("contract_version")
                )
                != _text(contracts["case_manifest"].get("contract_version"))
                or _text(reference.get("sequence_sha256"))
                != _text(expected.get("expected_input_sequence_sha256"))
            ):
                raise _mismatch(f"component snapshot identity has drifted: {component_id}")
    if seen != set(expected_components):
        raise _mismatch("component snapshot set is incomplete")


def validate_mt02_result(
    result: Mapping[str, Any],
    *,
    contract_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate an MT-02 result or reject any incomplete/forged MT-02 claim."""
    payload = copy.deepcopy(dict(result))
    if not is_mt02_claim(payload):
        raise _mismatch("result does not contain a complete MT-02 identity")
    contracts = load_mt02_contracts(contract_dir)
    contract_version = _text(contracts["case_manifest"].get("contract_version"))
    provenance = _mapping(payload.get("case_provenance"))
    snapshot = _mapping(payload.get("case_snapshot"))
    canonical = _mapping(payload.get("combined_construct"))
    canonical_sequence = _text(canonical.get("dna")).upper()
    fixed_pairs = {
        "case_id": (_text(payload.get("case_id")), MT02_CASE_ID),
        "result_kind": (_text(payload.get("result_kind")), MT02_RESULT_KIND),
        "topology": (_text(payload.get("topology")), "linear"),
        "contains_vector": (bool(payload.get("contains_vector")), False),
        "contract_version": (_text(provenance.get("contract_version")), contract_version),
        "source_accession_version": (
            _text(provenance.get("source_accession_version")),
            MT02_ACCESSION_VERSION,
        ),
        "source_construct": (_text(provenance.get("source_construct")), MT02_CONSTRUCT),
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
    if _text(snapshot.get("snapshot_schema_version")) != MT02_RUNTIME_SNAPSHOT_VERSION:
        raise _mismatch("case snapshot schema version is unsupported")
    if (
        _text(snapshot.get("case_id")) != MT02_CASE_ID
        or _text(snapshot.get("contract_version")) != contract_version
        or _text(snapshot.get("source_type"))
        != REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
        or _text(snapshot.get("case_evidence_class"))
        != DETERMINISTIC_ACCESSION_DERIVATION
        or _text(snapshot.get("source_construct")) != MT02_CONSTRUCT
        or snapshot.get("extraction") != contracts["extraction_contract"].get("extraction")
    ):
        raise _mismatch("case snapshot identity or extraction contract has drifted")
    source_admission = _mapping(snapshot.get("source_admission"))
    source_contract = contracts["source_contract"]
    expected_hashes = contracts["expected_hashes"]
    source_checks = {
        "record_id": MT02_ACCESSION_VERSION,
        "source_length_bp": int(source_contract["parsed_record"]["length_bp"]),
        "source_topology": _text(source_contract["parsed_record"]["topology"]),
        "source_sequence_sha256": _text(expected_hashes["source_sequence_sha256"]),
        "raw_file_size_bytes": int(source_contract["expected_response"]["raw_file_size_bytes"]),
        "raw_file_sha256": _text(expected_hashes["raw_source_file_sha256"]),
        "source_feature_count": int(expected_hashes["drift_detection"]["source_feature_count"]),
        "selected_source_feature_count": int(
            expected_hashes["drift_detection"]["selected_source_feature_count"]
        ),
        "region_length_bp": 6609,
        "region_sequence_sha256": _text(expected_hashes["canonical_sequence_sha256"]),
        "source_external_coordinates": "111..6719",
    }
    for key, expected in source_checks.items():
        if source_admission.get(key) != expected:
            raise _mismatch(f"saved source admission field has drifted: {key}")
    if len(canonical_sequence) != 6609 or int(canonical.get("total_length") or 0) != 6609:
        raise _mismatch("canonical length is not 6,609 bp")
    canonical_sha = _sha256_sequence(canonical_sequence)
    if canonical_sha != _text(expected_hashes.get("canonical_sequence_sha256")):
        raise _mismatch("canonical sequence SHA-256 differs from the contract")
    if _text(canonical.get("sequence_sha256")) != canonical_sha:
        raise _mismatch("canonical sequence and recorded SHA-256 differ")
    if _text(payload.get("case_snapshot_sha256")) != _snapshot_digest(
        snapshot, canonical_sequence
    ):
        raise _mismatch("case snapshot checksum does not match canonical bytes")
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
    if len(units) != 3 or list(active.get("unit_order") or []) != ["TU1", "TU2", "TU3"]:
        raise _mismatch("TU count or order differs from the contract")
    for index, (unit, expected) in enumerate(zip(units, expected_tus), start=1):
        start, end = _canonical_interval(expected)
        expected_sha = _text(expected_hashes["transcription_units"][f"TU{index}_physical"])
        if (
            _text(unit.get("unit_id")) != f"TU{index}"
            or _text(unit.get("orientation")) != _text(expected.get("orientation"))
            or int(_mapping(unit.get("range")).get("start") or 0) != start + 1
            or int(_mapping(unit.get("range")).get("end") or 0) != end
            or _text(unit.get("sequence_sha256")) != expected_sha
            or _sha256_sequence(_text(unit.get("dna"))) != expected_sha
            or _text(unit.get("dna")) != canonical_sequence[start:end]
        ):
            raise _mismatch(f"TU{index} orientation, range, or bytes differ from the contract")
    _validate_component_references(payload, contracts)
    contract_unannotated = list(
        contracts["component_contract"].get("unannotated_intervals") or []
    )
    saved_unannotated = list(snapshot.get("unannotated_intervals") or [])
    if len(saved_unannotated) != 4 or len(contract_unannotated) != 4:
        raise _mismatch("unannotated interval count differs from the contract")
    unannotated_length = 0
    for saved, expected in zip(saved_unannotated, contract_unannotated):
        start, end = _canonical_interval(expected)
        sequence = canonical_sequence[start:end]
        unannotated_length += len(sequence)
        if (
            _text(saved.get("unannotated_id")) != _text(expected.get("unannotated_id"))
            or saved.get("source_interval") != expected.get("source_interval")
            or saved.get("canonical_interval") != expected.get("canonical_interval")
            or int(saved.get("canonical_start") or 0) != start
            or int(saved.get("canonical_end") or 0) != end
            or _text(saved.get("sequence")) != sequence
            or _text(saved.get("sequence_sha256")) != _sha256_sequence(sequence)
        ):
            raise _mismatch("unannotated source interval bytes or metadata have drifted")
    if unannotated_length != 24:
        raise _mismatch("unannotated source intervals do not total 24 bp")
    expected_features = _expected_features(canonical_sequence, contracts)
    if list(snapshot.get("expected_features") or []) != expected_features:
        raise _mismatch("expected feature snapshot has drifted")
    for item in expected_features:
        start = int(item["canonical_start"])
        end = int(item["canonical_end"])
        if _sha256_sequence(canonical_sequence[start:end]) != _text(
            item.get("expected_sequence_sha256")
        ):
            raise _mismatch(f"expected feature bytes have drifted: {item.get('feature_id')}")
    atomic = list(snapshot.get("atomic_partition") or [])
    expected_atomic = list(contracts["component_contract"].get("atomic_partition") or [])
    if atomic != expected_atomic or len(atomic) != 40:
        raise _mismatch("atomic partition has drifted")
    cursor = 0
    for item in atomic:
        interval = _mapping(item.get("canonical_interval"))
        start = int(interval.get("start") or 0)
        end = int(interval.get("end") or 0)
        if start != cursor or end <= start:
            raise _mismatch("atomic partition is not contiguous and non-overlapping")
        if _sha256_sequence(canonical_sequence[start:end]) != _text(
            item.get("sequence_sha256")
        ):
            raise _mismatch(f"atomic interval bytes have drifted: {item.get('atomic_id')}")
        cursor = end
    if cursor != len(canonical_sequence):
        raise _mismatch("atomic partition does not cover the canonical sequence")
    if list(snapshot.get("junctions") or []) != list(
        contracts["extraction_contract"].get("junctions") or []
    ):
        raise _mismatch("junction snapshot has drifted")
    overlap_count = int(snapshot.get("expected_pairwise_source_feature_overlap_count") or 0)
    if overlap_count != 30:
        raise _mismatch("source-feature overlap count differs from the contract")
    exports = _mapping(payload.get("exports"))
    try:
        fasta_records = list(
            SeqIO.parse(
                StringIO(_text(_mapping(exports.get("combined_construct_fasta")).get("data"))),
                "fasta",
            )
        )
    except Exception as exc:
        raise _mismatch("FASTA export cannot be parsed") from exc
    if len(fasta_records) != 1 or str(fasta_records[0].seq).upper() != canonical_sequence:
        raise _mismatch("FASTA export does not match the canonical sequence")
    fasta_description = _text(fasta_records[0].description)
    for token in (
        MT02_CASE_ID,
        MT02_ACCESSION_VERSION,
        "source_region=111..6719",
        "contains_vector=false",
    ):
        if token not in fasta_description:
            raise _mismatch(f"FASTA traceability token is missing: {token}")
    _validate_mt02_genbank(
        _text(_mapping(exports.get("combined_construct_genbank")).get("data")),
        canonical_sequence=canonical_sequence,
        contracts=contracts,
        expected_features=expected_features,
    )
    return {
        "status": "pass",
        "case_id": MT02_CASE_ID,
        "contract_version": contract_version,
        "canonical_length_bp": len(canonical_sequence),
        "canonical_sequence_sha256": canonical_sha,
        "tu_count": len(units),
        "unannotated_interval_count": len(saved_unannotated),
        "unannotated_length_bp": unannotated_length,
        "expected_feature_count": len(expected_features),
        "source_feature_overlap_count": overlap_count,
        "atomic_interval_count": len(atomic),
        "contains_vector": False,
        "topology": "linear",
    }
