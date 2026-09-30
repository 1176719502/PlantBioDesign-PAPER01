"""Verify the MT-02 KM507054.1 deterministic region without emitting DNA."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from Bio import SeqIO, __version__ as BIOPYTHON_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_DIR = REPO_ROOT / "data" / "real_case_contracts_v1" / "mt02_pdoe13"
CONTRACT_FILES = (
    "case_manifest.json",
    "source_contract.json",
    "extraction_contract.json",
    "component_contract.json",
    "feature_contract.json",
    "expected_hashes.json",
    "redistribution_contract.json",
)
UPSTREAM_MISMATCH = "MT02_UPSTREAM_EVIDENCE_MISMATCH"
CONTRACT_MISMATCH = "MT02_DATA_CONTRACT_MISMATCH"
STRICT_DNA = frozenset("ACGT")


class Mt02VerificationError(ValueError):
    """Raised when source bytes or a contract invariant does not match MT-02."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_sequence(sequence: str) -> str:
    return _sha256_bytes(sequence.upper().encode("ascii"))


def _reverse_complement(sequence: str) -> str:
    normalized = sequence.upper()
    invalid = sorted(set(normalized) - STRICT_DNA)
    if invalid:
        raise Mt02VerificationError(
            f"Sequence contains unsupported nucleotide symbols: {', '.join(invalid)}"
        )
    return normalized.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Mt02VerificationError(f"Required contract file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise Mt02VerificationError(f"Contract file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Mt02VerificationError(f"Contract file must contain one JSON object: {path}")
    return payload


def load_contracts(contract_dir: Path = DEFAULT_CONTRACT_DIR) -> dict[str, dict[str, Any]]:
    resolved = contract_dir.resolve()
    contracts = {
        name.removesuffix(".json"): _load_json(resolved / name)
        for name in CONTRACT_FILES
    }
    for name, payload in contracts.items():
        if payload.get("case_id") != "MT-02":
            raise Mt02VerificationError(f"{name} must declare case_id MT-02.")
        if payload.get("contract_version") != "1.0.0":
            raise Mt02VerificationError(f"{name} has an unsupported contract_version.")
    verify_contract_consistency(contracts)
    return contracts


def _internal(interval: dict[str, Any]) -> tuple[int, int]:
    value = interval["internal_0_based_half_open"]
    return int(value["start"]), int(value["end"])


def _validate_interval(interval: dict[str, Any], *, label: str) -> tuple[int, int]:
    start, end = _internal(interval)
    external = interval["external_1_based_inclusive"]
    external_start, external_end = int(external["start"]), int(external["end"])
    length = int(interval["length_bp"])
    if start < 0 or end <= start:
        raise Mt02VerificationError(f"{label} has an invalid half-open interval.")
    if external_start != start + 1 or external_end != end:
        raise Mt02VerificationError(
            f"{label} external/internal conversion is inconsistent (possible off-by-one)."
        )
    if end - start != length or external_end - external_start + 1 != length:
        raise Mt02VerificationError(f"{label} length does not match its coordinates.")
    return start, end


def _assert_contiguous(
    intervals: list[tuple[int, int, str]], *, expected_start: int, expected_end: int
) -> None:
    cursor = expected_start
    for start, end, label in intervals:
        if start != cursor:
            relation = "overlap" if start < cursor else "gap"
            raise Mt02VerificationError(
                f"Partition {relation} before {label}: expected start {cursor}, got {start}."
            )
        if end <= start:
            raise Mt02VerificationError(f"Partition item {label} is empty or reversed.")
        cursor = end
    if cursor != expected_end:
        raise Mt02VerificationError(
            f"Partition does not reach expected end {expected_end}; stopped at {cursor}."
        )


def _pairwise_overlap_count(features: list[dict[str, Any]]) -> int:
    count = 0
    for index, left in enumerate(features):
        left_start, left_end = left["source_interval"].values()
        for right in features[index + 1 :]:
            right_start, right_end = right["source_interval"].values()
            if max(int(left_start), int(right_start)) < min(int(left_end), int(right_end)):
                count += 1
    return count


def derive_atomic_partition(
    features: list[dict[str, Any]], unannotated: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    feature_bounds = [
        (int(item["source_interval"]["start"]), int(item["source_interval"]["end"]), item["feature_id"])
        for item in features
    ]
    unannotated_bounds = {
        _internal(item["source_interval"]): item["unannotated_id"] for item in unannotated
    }
    boundaries = {110, 6719}
    for start, end, _feature_id in feature_bounds:
        boundaries.update((start, end))
    for start, end in unannotated_bounds:
        boundaries.update((start, end))
    ordered = sorted(boundaries)
    result = []
    for number, (start, end) in enumerate(zip(ordered, ordered[1:]), 1):
        result.append(
            {
                "atomic_id": f"MT-02-A{number:02d}",
                "source_interval": {"start": start, "end": end},
                "canonical_interval": {"start": start - 110, "end": end - 110},
                "length_bp": end - start,
                "source_feature_ids": [
                    feature_id
                    for feature_start, feature_end, feature_id in feature_bounds
                    if feature_start <= start and end <= feature_end
                ],
                "unannotated_interval_id": unannotated_bounds.get((start, end)),
            }
        )
    return result


def verify_contract_consistency(contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = contracts["case_manifest"]
    source = contracts["source_contract"]
    extraction = contracts["extraction_contract"]
    components = contracts["component_contract"]
    features = contracts["feature_contract"]
    hashes = contracts["expected_hashes"]

    if manifest["product_result"] != {
        "topology": "linear",
        "contains_vector": False,
        "tu_count": 3,
        "accessory_tu_count": 1,
        "target_reporter_tu_count": 2,
        "tu_identities": [
            "p19 RNA silencing suppressor",
            "X-mTq2 / mTurquoise2",
            "X-mVenus / mVenus",
        ],
        "roles": ["accessory", "target/reporter", "target/reporter"],
        "orientations": ["reverse", "forward", "forward"],
    }:
        raise Mt02VerificationError(f"{CONTRACT_MISMATCH}: product result changed.")
    if source["accession_version"] != "KM507054.1" or source["record_id"] != "KM507054.1":
        raise Mt02VerificationError("MT-02 requires exact accession/version KM507054.1.")
    parsed = source["parsed_record"]
    if parsed["topology"] != "circular" or int(parsed["length_bp"]) != 13268:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: source identity contract changed.")
    if parsed["sequence_sha256"] != hashes["source_sequence_sha256"]:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: source hash contracts disagree.")

    region = extraction["extraction"]
    source_start, source_end = _validate_interval(region["source_interval"], label="source extraction")
    canonical_start, canonical_end = _validate_interval(
        region["canonical_interval"], label="canonical extraction"
    )
    if (source_start, source_end) != (110, 6719) or (canonical_start, canonical_end) != (0, 6609):
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: extraction coordinates changed.")
    if region["wraparound"] is not False or region["topology"] != "linear":
        raise Mt02VerificationError("MT-02 canonical must be non-wrapping and linear.")
    if region["contains_vector"] is not False:
        raise Mt02VerificationError("MT-02 canonical must declare contains_vector=false.")
    if region["sequence_sha256"] != hashes["canonical_sequence_sha256"]:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: canonical hash contracts disagree.")

    tus = extraction["transcription_units"]
    expected_tus = [
        (1, "accessory", "reverse", -1, 1),
        (2, "target/reporter", "forward", 1, 0),
        (3, "target/reporter", "forward", 1, 0),
    ]
    observed_tus = [
        (item["tu_number"], item["role"], item["orientation"], item["strand"], item["whole_unit_reverse_complement_count"])
        for item in tus
    ]
    if observed_tus != expected_tus:
        raise Mt02VerificationError("MT-02 TU order, roles, orientation, or transform count changed.")
    tu_source = []
    tu_canonical = []
    for item in tus:
        number = item["tu_number"]
        source_bounds = _validate_interval(item["source_interval"], label=f"TU{number} source")
        canonical_bounds = _validate_interval(item["canonical_interval"], label=f"TU{number} canonical")
        if canonical_bounds != (source_bounds[0] - 110, source_bounds[1] - 110):
            raise Mt02VerificationError(f"TU{number} canonical coordinates are not deterministic.")
        tu_source.append((*source_bounds, f"TU{number}"))
        tu_canonical.append((*canonical_bounds, f"TU{number}"))
    _assert_contiguous(tu_source, expected_start=110, expected_end=6719)
    _assert_contiguous(tu_canonical, expected_start=0, expected_end=6609)
    if [item["source_interval"]["length_bp"] for item in tus] != [1217, 2936, 2456]:
        raise Mt02VerificationError("MT-02 TU lengths changed.")

    component_rows = components["components"]
    expected_component_order = [
        "MT-02-TU1-THREE-PRIME", "MT-02-TU1-CDS", "MT-02-TU1-PROMOTER-SIDE",
        "MT-02-TU2-PROMOTER-SIDE", "MT-02-TU2-CDS", "MT-02-TU2-THREE-PRIME",
        "MT-02-TU3-PROMOTER-SIDE", "MT-02-TU3-CDS", "MT-02-TU3-THREE-PRIME",
    ]
    if [item["component_case_id"] for item in component_rows] != expected_component_order:
        raise Mt02VerificationError("MT-02 component order changed.")
    component_source = []
    component_canonical = []
    for item in component_rows:
        component_id = item["component_case_id"]
        source_bounds = _validate_interval(item["source_physical_interval"], label=f"{component_id} source")
        canonical_bounds = _validate_interval(item["canonical_physical_interval"], label=f"{component_id} canonical")
        core_bounds = _validate_interval(item["core_source_interval"], label=f"{component_id} core")
        if not (source_bounds[0] <= core_bounds[0] < core_bounds[1] <= source_bounds[1]):
            raise Mt02VerificationError(f"{component_id} core lies outside its composite span.")
        if canonical_bounds != (source_bounds[0] - 110, source_bounds[1] - 110):
            raise Mt02VerificationError(f"{component_id} canonical coordinates are not deterministic.")
        if item["expected_input_length"] != source_bounds[1] - source_bounds[0]:
            raise Mt02VerificationError(f"{component_id} expected input length changed.")
        expected_hash = hashes["components"][component_id]
        if item["expected_physical_segment_sha256"] != expected_hash["physical"]:
            raise Mt02VerificationError(f"{component_id} physical hashes disagree.")
        if item["expected_input_sequence_sha256"] != expected_hash["ui_input"]:
            raise Mt02VerificationError(f"{component_id} input hashes disagree.")
        component_source.append((*source_bounds, component_id))
        component_canonical.append((*canonical_bounds, component_id))
    _assert_contiguous(component_source, expected_start=110, expected_end=6719)
    _assert_contiguous(component_canonical, expected_start=0, expected_end=6609)

    unannotated = components["unannotated_intervals"]
    expected_unannotated = [(362, 372), (1315, 1327), (2657, 2658), (6465, 6466)]
    observed_unannotated = []
    for item in unannotated:
        source_bounds = _validate_interval(item["source_interval"], label=item["unannotated_id"])
        canonical_bounds = _validate_interval(item["canonical_interval"], label=f"{item['unannotated_id']} canonical")
        if canonical_bounds != (source_bounds[0] - 110, source_bounds[1] - 110):
            raise Mt02VerificationError(f"{item['unannotated_id']} canonical coordinates changed.")
        if item["category"] != "UNANNOTATED_SOURCE_SEQUENCE" or item["source_annotated_as_component"] is not False:
            raise Mt02VerificationError(f"{item['unannotated_id']} must remain conservatively unannotated.")
        if item["sequence_sha256"] != hashes["unannotated_intervals"][item["unannotated_id"]]:
            raise Mt02VerificationError(f"{item['unannotated_id']} hashes disagree.")
        observed_unannotated.append(source_bounds)
    if observed_unannotated != expected_unannotated:
        raise Mt02VerificationError("MT-02 unannotated intervals changed.")
    if sum(end - start for start, end in observed_unannotated) != 24:
        raise Mt02VerificationError("MT-02 unannotated total must be 24 bp.")

    source_features = features["source_feature_assertions"]
    if len(source_features) != 33 or len({item["feature_id"] for item in source_features}) != 33:
        raise Mt02VerificationError("MT-02 requires 33 unique source feature assertions.")
    for item in source_features:
        start, end = (int(value) for value in item["source_interval"].values())
        canonical = item["canonical_interval"]
        if canonical != {"start": start - 110, "end": end - 110}:
            raise Mt02VerificationError(f"{item['feature_id']} canonical coordinates changed.")
        if len(item["expected_sequence_sha256"]) != 64:
            raise Mt02VerificationError(f"{item['feature_id']} has an invalid sequence hash.")
    overlap_count = _pairwise_overlap_count(source_features)
    if overlap_count != features["expected_pairwise_source_feature_overlap_count"] or overlap_count != 30:
        raise Mt02VerificationError("MT-02 source feature overlap count changed.")
    if len(source_features) + len(features["derived_expected_features"]) != features["expected_feature_count"]:
        raise Mt02VerificationError("MT-02 expected feature membership is incomplete.")

    derived_atoms = derive_atomic_partition(source_features, unannotated)
    stored_atoms = components["atomic_partition"]
    if len(derived_atoms) != 40 or len(stored_atoms) != 40:
        raise Mt02VerificationError("MT-02 atomic interval count changed.")
    comparable_keys = (
        "atomic_id", "source_interval", "canonical_interval", "length_bp",
        "source_feature_ids", "unannotated_interval_id",
    )
    for derived, stored in zip(derived_atoms, stored_atoms):
        if {key: stored[key] for key in comparable_keys} != derived:
            raise Mt02VerificationError(f"Atomic partition drift at {stored.get('atomic_id')}.")
        if len(stored["sequence_sha256"]) != 64:
            raise Mt02VerificationError(f"{stored['atomic_id']} has an invalid hash.")
    _assert_contiguous(
        [(item["source_interval"]["start"], item["source_interval"]["end"], item["atomic_id"]) for item in stored_atoms],
        expected_start=110,
        expected_end=6719,
    )
    if sum(item["length_bp"] for item in stored_atoms) != 6609:
        raise Mt02VerificationError("Atomic partition does not sum to 6609 bp.")
    if {item["unannotated_interval_id"] for item in stored_atoms if item["unannotated_interval_id"]} != {
        "MT-02-U01", "MT-02-U02", "MT-02-U03", "MT-02-U04"
    }:
        raise Mt02VerificationError("Atomic partition does not retain all unannotated intervals.")

    expected_junctions = []
    for index, (left, right) in enumerate(zip(component_rows, component_rows[1:]), 1):
        left_source_end = _internal(left["source_physical_interval"])[1]
        right_source_start = _internal(right["source_physical_interval"])[0]
        expected_junctions.append(
            (f"MT-02-B{index:02d}", left["component_case_id"], right["component_case_id"], left_source_end, right_source_start, left_source_end - 110)
        )
    observed_junctions = [
        (item["junction_id"], item["left_component"], item["right_component"], item["left_source_end"], item["right_source_start"], item["canonical_boundary"])
        for item in extraction["junctions"]
    ]
    if observed_junctions != expected_junctions:
        raise Mt02VerificationError("MT-02 junction contract changed or is incomplete.")

    drift = hashes["drift_detection"]
    expected_drift = {
        "exact_accession_version": "KM507054.1", "source_length_bp": 13268,
        "source_topology": "circular", "source_feature_count": 43,
        "selected_source_feature_count": 33, "expected_feature_count": 50,
        "pairwise_source_feature_overlap_count": 30, "atomic_interval_count": 40,
        "junction_count": 8, "canonical_length_bp": 6609,
        "canonical_topology": "linear", "contains_vector": False, "tu_count": 3,
        "orientations": ["reverse", "forward", "forward"],
    }
    if drift != expected_drift:
        raise Mt02VerificationError("MT-02 drift detection fields changed.")
    return {
        "coordinate_conversions": "pass",
        "tu_partition": "pass",
        "component_partition": "pass",
        "atomic_partition": "pass",
        "atomic_interval_count": 40,
        "expected_feature_count": 50,
        "source_feature_overlap_count": 30,
        "junction_count": 8,
        "unannotated_interval_count": 4,
        "unannotated_total_bp": 24,
    }


def _find_source_feature(record: Any, assertion: dict[str, Any]) -> Any:
    index = int(assertion["source_feature_index"])
    if index >= len(record.features):
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: missing {assertion['feature_id']}.")
    feature = record.features[index]
    qualifier = assertion["qualifier"]
    if (
        feature.type != assertion["feature_type"]
        or int(feature.location.start) != int(assertion["source_interval"]["start"])
        or int(feature.location.end) != int(assertion["source_interval"]["end"])
        or int(feature.location.strand or 0) != int(assertion["strand"])
        or qualifier["value"] not in feature.qualifiers.get(qualifier["key"], [])
    ):
        raise Mt02VerificationError(
            f"{UPSTREAM_MISMATCH}: source feature boundary, strand, type, or qualifier mismatch for {assertion['feature_id']}."
        )
    return feature


def verify_source_file(
    source_path: Path, *, contract_dir: Path = DEFAULT_CONTRACT_DIR
) -> dict[str, Any]:
    contracts = load_contracts(contract_dir)
    source_contract = contracts["source_contract"]
    extraction = contracts["extraction_contract"]
    components = contracts["component_contract"]
    features = contracts["feature_contract"]
    hashes = contracts["expected_hashes"]

    resolved_source = source_path.resolve()
    if not resolved_source.is_file():
        raise Mt02VerificationError(
            f"Source file is missing: {resolved_source}. Provide a repository-external KM507054.1 GenBank file."
        )
    raw_bytes = resolved_source.read_bytes()
    if _sha256_bytes(raw_bytes) != hashes["raw_source_file_sha256"]:
        raise Mt02VerificationError("Raw source file SHA-256 does not match the audited NCBI response.")
    if len(raw_bytes) != int(source_contract["expected_response"]["raw_file_size_bytes"]):
        raise Mt02VerificationError("Raw source file size does not match the audited NCBI response.")
    try:
        record = SeqIO.read(resolved_source, "genbank")
    except Exception as exc:
        raise Mt02VerificationError("Source file could not be parsed as one GenBank record.") from exc
    if record.id != "KM507054.1":
        raise Mt02VerificationError(
            f"Source version mismatch: expected KM507054.1, parsed {record.id or '<empty>'}."
        )
    if record.name != "KM507054":
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: LOCUS name mismatch.")
    if record.description.rstrip(".") != "Binary vector pDOE-13, complete sequence":
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: record definition mismatch.")
    source_sequence = str(record.seq).upper()
    if len(source_sequence) != 13268:
        raise Mt02VerificationError(
            f"{UPSTREAM_MISMATCH}: expected source length 13268, parsed {len(source_sequence)}."
        )
    if str(record.annotations.get("topology") or "").lower() != "circular":
        raise Mt02VerificationError("Source topology mismatch: expected circular.")
    if _sha256_sequence(source_sequence) != hashes["source_sequence_sha256"]:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: source sequence SHA-256 mismatch.")
    if len(record.features) != 43:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: source feature count mismatch.")
    invalid_source = sorted(set(source_sequence) - STRICT_DNA)
    if invalid_source:
        raise Mt02VerificationError(f"Source contains unknown nucleotide symbols: {', '.join(invalid_source)}")

    for assertion in features["source_feature_assertions"]:
        _find_source_feature(record, assertion)
        start, end = (int(value) for value in assertion["source_interval"].values())
        if _sha256_sequence(source_sequence[start:end]) != assertion["expected_sequence_sha256"]:
            raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: {assertion['feature_id']} sequence mismatch.")

    source_start, source_end = _internal(extraction["extraction"]["source_interval"])
    canonical = source_sequence[source_start:source_end]
    if len(canonical) != 6609 or _sha256_sequence(canonical) != hashes["canonical_sequence_sha256"]:
        raise Mt02VerificationError(f"{UPSTREAM_MISMATCH}: canonical length or SHA-256 mismatch.")

    component_sequences: dict[str, dict[str, str]] = {}
    component_results = []
    for item in components["components"]:
        component_id = item["component_case_id"]
        start, end = _internal(item["source_physical_interval"])
        physical = source_sequence[start:end]
        ui_input = (
            _reverse_complement(physical)
            if item["ui_input_transformation"] == "reverse_complement_source_physical_span"
            else physical
        )
        if _sha256_sequence(physical) != item["expected_physical_segment_sha256"]:
            raise Mt02VerificationError(f"{component_id} physical segment SHA-256 mismatch.")
        if _sha256_sequence(ui_input) != item["expected_input_sequence_sha256"]:
            raise Mt02VerificationError(f"{component_id} input SHA-256 mismatch.")
        component_sequences[component_id] = {"physical": physical, "ui_input": ui_input}
        component_results.append(
            {
                "component_case_id": component_id,
                "physical_length_bp": len(physical),
                "physical_sequence_sha256": _sha256_sequence(physical),
                "ui_input_sequence_sha256": _sha256_sequence(ui_input),
                "transformation": item["ui_input_transformation"],
                "status": "pass",
            }
        )

    tu1_input = (
        component_sequences["MT-02-TU1-PROMOTER-SIDE"]["ui_input"]
        + component_sequences["MT-02-TU1-CDS"]["ui_input"]
        + component_sequences["MT-02-TU1-THREE-PRIME"]["ui_input"]
    )
    tu1 = _reverse_complement(tu1_input)
    tu2 = (
        component_sequences["MT-02-TU2-PROMOTER-SIDE"]["ui_input"]
        + component_sequences["MT-02-TU2-CDS"]["ui_input"]
        + component_sequences["MT-02-TU2-THREE-PRIME"]["ui_input"]
    )
    tu3 = (
        component_sequences["MT-02-TU3-PROMOTER-SIDE"]["ui_input"]
        + component_sequences["MT-02-TU3-CDS"]["ui_input"]
        + component_sequences["MT-02-TU3-THREE-PRIME"]["ui_input"]
    )
    if tu1 != source_sequence[110:1327]:
        raise Mt02VerificationError("TU1 reverse-orientation reconstruction mismatch.")
    if _reverse_complement(tu1) == source_sequence[110:1327]:
        raise Mt02VerificationError("TU1 double reverse-complement guard failed.")
    if tu2 != source_sequence[1327:4263] or tu3 != source_sequence[4263:6719]:
        raise Mt02VerificationError("TU2 or TU3 forward reconstruction mismatch.")
    if tu1 + tu2 + tu3 != canonical:
        raise Mt02VerificationError("Ordered TU reconstruction does not equal canonical.")

    unannotated_results = []
    for item in components["unannotated_intervals"]:
        start, end = _internal(item["source_interval"])
        sequence = source_sequence[start:end]
        if _sha256_sequence(sequence) != item["sequence_sha256"]:
            raise Mt02VerificationError(f"{item['unannotated_id']} sequence SHA-256 mismatch.")
        unannotated_results.append(
            {"unannotated_id": item["unannotated_id"], "length_bp": len(sequence), "sequence_sha256": _sha256_sequence(sequence), "status": "pass"}
        )
    for atom in components["atomic_partition"]:
        start, end = atom["source_interval"].values()
        if _sha256_sequence(source_sequence[int(start):int(end)]) != atom["sequence_sha256"]:
            raise Mt02VerificationError(f"{atom['atomic_id']} sequence SHA-256 mismatch.")

    return {
        "schema_version": "mt02-verification-result-v1",
        "case_id": "MT-02",
        "status": "pass",
        "source": {
            "exact_accession_version": record.id,
            "locus_name": record.name,
            "definition": record.description,
            "raw_file_size_bytes": len(raw_bytes),
            "raw_file_sha256": _sha256_bytes(raw_bytes),
            "parsed_sequence_length_bp": len(source_sequence),
            "parsed_topology": str(record.annotations.get("topology") or ""),
            "parsed_sequence_sha256": _sha256_sequence(source_sequence),
            "feature_count": len(record.features),
            "parser": "Biopython SeqIO GenBank",
            "parser_version": BIOPYTHON_VERSION,
        },
        "canonical": {
            "source_external_interval": "111..6719",
            "source_internal_interval": "[110,6719)",
            "topology": "linear",
            "contains_vector": False,
            "length_bp": len(canonical),
            "sequence_sha256": _sha256_sequence(canonical),
        },
        "components": component_results,
        "unannotated_intervals": unannotated_results,
        "proofs": {
            "canonical_source_slice_byte_equality": "pass",
            "tu1_reverse_complement_exactly_once": "pass",
            "tu1_double_reverse_complement_rejected": "pass",
            "tu2_forward_identity": "pass",
            "tu3_forward_identity": "pass",
            "ordered_tu_concatenation": "pass",
            "junctions": "pass",
            "atomic_partition": "pass",
            "all_nucleotides_known": True,
            "dna_duplication_or_loss": False,
        },
        "counts": {
            "tu": 3,
            "accessory_tu": 1,
            "target_reporter_tu": 2,
            "source_features": 33,
            "expected_features": 50,
            "pairwise_source_feature_overlaps": 30,
            "atomic_intervals": 40,
            "junctions": 8,
            "unannotated_intervals": 4,
            "unannotated_bp": 24,
        },
        "redistribution_status": "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY",
    }


def _is_inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def _write_result(result: dict[str, Any], output_path: Path) -> None:
    resolved = output_path.resolve()
    if _is_inside_repository(resolved):
        raise Mt02VerificationError(f"Verification output must be outside the repository: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify MT-02 using a repository-external exact KM507054.1 GenBank file."
    )
    parser.add_argument("--genbank", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--contracts-dir", type=Path, default=DEFAULT_CONTRACT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_source_file(args.genbank, contract_dir=args.contracts_dir)
        _write_result(result, args.output_json)
        print(json.dumps({"case_id": "MT-02", "status": "pass", "output_json": str(args.output_json.resolve())}))
        return 0
    except Mt02VerificationError as exc:
        print(f"MT-02 verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
