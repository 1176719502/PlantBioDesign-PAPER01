"""Reproduce and verify the MT-01 KX758647.1 deterministic region.

The tool never emits complete DNA sequences and refuses to write source or
result files inside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Bio import SeqIO, __version__ as BIOPYTHON_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_DIR = (
    REPO_ROOT / "data" / "real_case_contracts_v1" / "mt01_pgrdl_sp"
)
CONTRACT_FILES = (
    "case_manifest.json",
    "source_contract.json",
    "extraction_contract.json",
    "component_contract.json",
    "feature_contract.json",
    "expected_hashes.json",
    "redistribution_contract.json",
)
UPSTREAM_MISMATCH = "MT01_UPSTREAM_EVIDENCE_MISMATCH"
RUNTIME_GAP = "MT01_RUNTIME_MODEL_GAP_UNANNOTATED_SEQUENCE"
STRICT_DNA = frozenset("ACGT")


class Mt01VerificationError(ValueError):
    """Raised when source bytes or a contract invariant does not match MT-01."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_sequence(sequence: str) -> str:
    return _sha256_bytes(sequence.upper().encode("ascii"))


def _reverse_complement(sequence: str) -> str:
    invalid = sorted(set(sequence.upper()) - STRICT_DNA)
    if invalid:
        raise Mt01VerificationError(
            f"Sequence contains unsupported nucleotide symbols: {', '.join(invalid)}"
        )
    return sequence.upper().translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Mt01VerificationError(f"Required contract file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise Mt01VerificationError(f"Contract file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Mt01VerificationError(f"Contract file must contain one JSON object: {path}")
    return payload


def load_contracts(contract_dir: Path = DEFAULT_CONTRACT_DIR) -> dict[str, dict[str, Any]]:
    resolved = contract_dir.resolve()
    contracts = {
        name.removesuffix(".json"): _load_json(resolved / name)
        for name in CONTRACT_FILES
    }
    for name, payload in contracts.items():
        if payload.get("case_id") != "MT-01":
            raise Mt01VerificationError(f"{name} must declare case_id MT-01.")
        if payload.get("contract_version") != "1.0.0":
            raise Mt01VerificationError(f"{name} has an unsupported contract_version.")
    verify_contract_consistency(contracts)
    return contracts


def _internal(interval: dict[str, Any]) -> tuple[int, int]:
    value = interval["internal_0_based_half_open"]
    return int(value["start"]), int(value["end"])


def _validate_interval(interval: dict[str, Any], *, label: str) -> tuple[int, int]:
    start, end = _internal(interval)
    external = interval["external_1_based_inclusive"]
    external_start = int(external["start"])
    external_end = int(external["end"])
    length = int(interval["length_bp"])
    if start < 0 or end <= start:
        raise Mt01VerificationError(f"{label} has an invalid half-open interval.")
    if external_start != start + 1 or external_end != end:
        raise Mt01VerificationError(
            f"{label} external/internal conversion is inconsistent (possible off-by-one)."
        )
    if end - start != length or external_end - external_start + 1 != length:
        raise Mt01VerificationError(f"{label} length does not match its coordinates.")
    return start, end


def _assert_contiguous(
    intervals: list[tuple[int, int, str]], *, expected_start: int, expected_end: int
) -> None:
    cursor = expected_start
    for start, end, label in intervals:
        if start != cursor:
            relation = "overlap" if start < cursor else "gap"
            raise Mt01VerificationError(
                f"Partition {relation} before {label}: expected start {cursor}, got {start}."
            )
        if end <= start:
            raise Mt01VerificationError(f"Partition item {label} is empty or reversed.")
        cursor = end
    if cursor != expected_end:
        raise Mt01VerificationError(
            f"Partition does not reach expected end {expected_end}; stopped at {cursor}."
        )


def verify_contract_consistency(contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = contracts["source_contract"]
    extraction = contracts["extraction_contract"]
    components = contracts["component_contract"]
    features = contracts["feature_contract"]
    hashes = contracts["expected_hashes"]

    if source["accession_version"] != "KX758647.1" or source["record_id"] != "KX758647.1":
        raise Mt01VerificationError("MT-01 requires exact accession/version KX758647.1.")
    if source["parsed_record"]["topology"] != "circular":
        raise Mt01VerificationError("MT-01 source topology must be circular.")
    if int(source["parsed_record"]["length_bp"]) != 7086:
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: source length contract changed.")
    if source["parsed_record"]["sequence_sha256"] != hashes["source_sequence_sha256"]:
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: source hash contracts disagree.")

    source_region = extraction["extraction"]["source_interval"]
    local_region = extraction["extraction"]["local_interval"]
    source_start, source_end = _validate_interval(source_region, label="source extraction")
    local_start, local_end = _validate_interval(local_region, label="local extraction")
    if (source_start, source_end) != (570, 4649) or (local_start, local_end) != (0, 4079):
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: extraction coordinates changed.")
    if extraction["extraction"]["sequence_sha256"] != hashes["extracted_sequence_sha256"]:
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: region hash contracts disagree.")
    if extraction["extraction"]["wraparound"] is not False:
        raise Mt01VerificationError("MT-01 extraction must not wrap around the source origin.")

    tus = extraction["transcription_units"]
    if [item["tu_number"] for item in tus] != [1, 2]:
        raise Mt01VerificationError("MT-01 transcription-unit order must be TU1 then TU2.")
    tu_source_intervals: list[tuple[int, int, str]] = []
    tu_local_intervals: list[tuple[int, int, str]] = []
    for item in tus:
        number = int(item["tu_number"])
        tu_source_intervals.append(
            (*_validate_interval(item["source_interval"], label=f"TU{number} source"), f"TU{number}")
        )
        tu_local_intervals.append(
            (*_validate_interval(item["local_interval"], label=f"TU{number} local"), f"TU{number}")
        )
    _assert_contiguous(tu_source_intervals, expected_start=570, expected_end=4649)
    _assert_contiguous(tu_local_intervals, expected_start=0, expected_end=4079)
    if [item["source_interval"]["length_bp"] for item in tus] != [1753, 2326]:
        raise Mt01VerificationError("MT-01 TU lengths must be 1753 and 2326 bp.")
    if [item["strand"] for item in tus] != [-1, 1]:
        raise Mt01VerificationError("MT-01 TU strands must be -1 and +1.")

    component_rows = components["components"]
    if len(component_rows) != 6 or len({item["component_case_id"] for item in component_rows}) != 6:
        raise Mt01VerificationError("MT-01 requires six unique component contracts.")
    expected_component_order = [
        "MT-01-TU1-THREE-PRIME",
        "MT-01-TU1-CDS",
        "MT-01-TU1-PROMOTER-SIDE",
        "MT-01-TU2-PROMOTER-SIDE",
        "MT-01-TU2-CDS",
        "MT-01-TU2-THREE-PRIME",
    ]
    if [item["component_case_id"] for item in component_rows] != expected_component_order:
        raise Mt01VerificationError("MT-01 component physical order changed.")
    component_source_intervals = []
    component_local_intervals = []
    for item in component_rows:
        component_id = item["component_case_id"]
        source_bounds = _validate_interval(
            item["source_physical_interval"], label=f"{component_id} source"
        )
        local_bounds = _validate_interval(
            item["local_physical_interval"], label=f"{component_id} local"
        )
        if local_bounds != (source_bounds[0] - source_start, source_bounds[1] - source_start):
            raise Mt01VerificationError(f"{component_id} source/local conversion is inconsistent.")
        if item["expected_input_length"] != source_bounds[1] - source_bounds[0]:
            raise Mt01VerificationError(f"{component_id} expected input length is inconsistent.")
        expected = hashes["components"][component_id]
        if item["expected_physical_segment_sha256"] != expected["physical"]:
            raise Mt01VerificationError(f"{component_id} physical hashes disagree.")
        if item["expected_input_sequence_sha256"] != expected["ui_input"]:
            raise Mt01VerificationError(f"{component_id} UI input hashes disagree.")
        component_source_intervals.append((*source_bounds, component_id))
        component_local_intervals.append((*local_bounds, component_id))
    _assert_contiguous(component_source_intervals, expected_start=570, expected_end=4649)
    _assert_contiguous(component_local_intervals, expected_start=0, expected_end=4079)

    junction_rows = components["unannotated_intervals"]
    if len(junction_rows) != 5 or [row["source_interval"]["length_bp"] for row in junction_rows] != [1, 15, 195, 6, 109]:
        raise Mt01VerificationError("MT-01 unannotated interval lengths changed.")
    junction_by_ref = {}
    for item in junction_rows:
        junction_id = item["junction_id"]
        source_bounds = _validate_interval(item["source_interval"], label=f"{junction_id} source")
        local_bounds = _validate_interval(item["local_interval"], label=f"{junction_id} local")
        if local_bounds != (source_bounds[0] - source_start, source_bounds[1] - source_start):
            raise Mt01VerificationError(f"{junction_id} source/local conversion is inconsistent.")
        if item["category"] != "UNANNOTATED_SOURCE_SEQUENCE" or item["source_annotated"] is not False:
            raise Mt01VerificationError(f"{junction_id} must remain conservatively unannotated.")
        if item["sequence_sha256"] != hashes["unannotated_intervals"][junction_id]:
            raise Mt01VerificationError(f"{junction_id} hashes disagree.")
        junction_by_ref[f"junction:{junction_id}"] = (*source_bounds, junction_id)

    source_feature_by_ref = {}
    for item in features["source_feature_assertions"]:
        feature_id = item["feature_id"]
        start = int(item["source_interval"]["start"])
        end = int(item["source_interval"]["end"])
        if end <= start:
            raise Mt01VerificationError(f"{feature_id} has an invalid source interval.")
        if item["expected_sequence_sha256"] != hashes["source_features"][feature_id]:
            raise Mt01VerificationError(f"{feature_id} hashes disagree.")
        source_feature_by_ref[f"source_feature:{feature_id}"] = (start, end, feature_id)
    atomic = []
    for reference in components["atomic_partition"]:
        item = source_feature_by_ref.get(reference) or junction_by_ref.get(reference)
        if item is None:
            raise Mt01VerificationError(f"Atomic partition references unknown item: {reference}")
        atomic.append(item)
    _assert_contiguous(atomic, expected_start=570, expected_end=4649)
    return {
        "coordinate_conversions": "pass",
        "tu_partition": "pass",
        "component_partition": "pass",
        "atomic_partition": "pass",
        "unannotated_interval_count": 5,
        "unannotated_total_bp": sum(row["source_interval"]["length_bp"] for row in junction_rows),
    }


def _find_source_feature(record: Any, assertion: dict[str, Any]) -> None:
    start = int(assertion["source_interval"]["start"])
    end = int(assertion["source_interval"]["end"])
    strand = int(assertion["strand"])
    qualifier = assertion["qualifier"]
    matches = [
        feature
        for feature in record.features
        if feature.type == assertion["feature_type"]
        and int(feature.location.start) == start
        and int(feature.location.end) == end
        and int(feature.location.strand or 0) == strand
        and qualifier["value"] in feature.qualifiers.get(qualifier["key"], [])
    ]
    if len(matches) != 1:
        raise Mt01VerificationError(
            f"Source feature boundary or qualifier mismatch: {assertion['feature_id']}"
        )


def _runtime_verify_direct(
    region: str, component_sequences: dict[str, dict[str, str]]
) -> dict[str, Any]:
    repo_root_text = str(REPO_ROOT)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)
    from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct

    def input_row(component_id: str, display_name: str) -> dict[str, str]:
        return {
            "display_name": display_name,
            "raw_text": component_sequences[component_id]["ui_input"],
            "source_type": "paste",
            "source_format": "plain",
            "source_name": "KX758647.1 accession-derived MT-01 input",
            "provenance_reference": "KX758647.1",
        }

    units = [
        {
            "unit_id": "MT-01-TU1",
            "display_name": "Renilla luciferase TU",
            "order": 1,
            "orientation": "reverse",
            "promoter": input_row("MT-01-TU1-PROMOTER-SIDE", "TU1 promoter-side span"),
            "cds": input_row("MT-01-TU1-CDS", "Renilla luciferase CDS"),
            "3_prime_regulatory_region": input_row("MT-01-TU1-THREE-PRIME", "TU1 3-prime span"),
        },
        {
            "unit_id": "MT-01-TU2",
            "display_name": "firefly luciferase TU",
            "order": 2,
            "orientation": "forward",
            "promoter": input_row("MT-01-TU2-PROMOTER-SIDE", "TU2 promoter-side span"),
            "cds": input_row("MT-01-TU2-CDS", "firefly luciferase CDS"),
            "3_prime_regulatory_region": input_row("MT-01-TU2-THREE-PRIME", "TU2 3-prime span"),
        },
    ]
    result = generate_multi_tu_combined_construct(
        project_id="mt01-external-verification",
        project_name="MT-01 external-source verification",
        expression_units=units,
    )
    canonical = result["combined_construct"]["dna"].upper()
    if canonical != region:
        raise Mt01VerificationError(
            f"{RUNTIME_GAP}: formal Multi-TU canonical does not retain all source bytes."
        )
    return {
        "status": "pass",
        "result_kind": result["result_kind"],
        "topology": "linear",
        "contains_vector": result["contains_vector"],
        "tu_count": len(result["expression_units"]),
        "canonical_length_bp": len(canonical),
        "canonical_sequence_sha256": _sha256_sequence(canonical),
        "runtime_model_gap_code": None,
    }


def _runtime_worker(
    region: str,
    component_sequences: dict[str, dict[str, str]],
    queue: Any,
) -> None:
    try:
        queue.put({"ok": True, "result": _runtime_verify_direct(region, component_sequences)})
    except Exception as exc:
        queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _runtime_verify(
    region: str,
    component_sequences: dict[str, dict[str, str]],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(
        target=_runtime_worker,
        args=(region, component_sequences, queue),
        daemon=True,
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise Mt01VerificationError(
            f"MT01_RUNTIME_EXECUTION_TIMEOUT: formal Multi-TU verification exceeded {timeout_seconds} seconds; independent source and reconstruction proofs are unaffected."
        )
    if queue.empty():
        raise Mt01VerificationError(
            f"Formal Multi-TU verification exited without a result (exit code {process.exitcode})."
        )
    message = queue.get()
    if not message["ok"]:
        raise Mt01VerificationError(f"Formal Multi-TU verification failed: {message['error']}")
    return message["result"]


def verify_source_file(
    source_path: Path,
    *,
    contract_dir: Path = DEFAULT_CONTRACT_DIR,
    verify_runtime: bool = False,
    runtime_timeout_seconds: int = 120,
    retrieval_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contracts = load_contracts(contract_dir)
    source_contract = contracts["source_contract"]
    extraction = contracts["extraction_contract"]
    components = contracts["component_contract"]
    features = contracts["feature_contract"]
    hashes = contracts["expected_hashes"]

    resolved_source = source_path.resolve()
    if not resolved_source.is_file():
        raise Mt01VerificationError(
            f"Source file is missing: {resolved_source}. Provide a local KX758647.1 GenBank file or use --accession with --cache-dir."
        )
    raw_bytes = resolved_source.read_bytes()
    raw_hash = _sha256_bytes(raw_bytes)
    if raw_hash != hashes["raw_source_file_sha256"]:
        raise Mt01VerificationError(
            "Raw source file SHA-256 does not match the audited KX758647.1 response."
        )
    if len(raw_bytes) != int(source_contract["expected_response"]["raw_file_size_bytes"]):
        raise Mt01VerificationError("Raw source file size does not match the audited response.")

    try:
        record = SeqIO.read(resolved_source, "genbank")
    except Exception as exc:
        raise Mt01VerificationError(
            f"Source file could not be parsed as one GenBank record: {resolved_source.name}"
        ) from exc
    if record.id != "KX758647.1":
        raise Mt01VerificationError(
            f"Source version mismatch: expected KX758647.1, parsed {record.id or '<empty>'}."
        )
    source_sequence = str(record.seq).upper()
    if len(source_sequence) != 7086:
        raise Mt01VerificationError(
            f"{UPSTREAM_MISMATCH}: expected source length 7086, parsed {len(source_sequence)}."
        )
    if str(record.annotations.get("topology") or "").lower() != "circular":
        raise Mt01VerificationError("Source topology mismatch: expected circular.")
    source_hash = _sha256_sequence(source_sequence)
    if source_hash != hashes["source_sequence_sha256"]:
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: source sequence SHA-256 mismatch.")
    if len(record.features) != int(source_contract["parsed_record"]["feature_count"]):
        raise Mt01VerificationError("Source feature count mismatch.")
    for assertion in features["source_feature_assertions"]:
        _find_source_feature(record, assertion)

    source_start, source_end = _internal(extraction["extraction"]["source_interval"])
    region = source_sequence[source_start:source_end]
    if len(region) != 4079:
        raise Mt01VerificationError(
            f"{UPSTREAM_MISMATCH}: expected region length 4079, extracted {len(region)}."
        )
    region_hash = _sha256_sequence(region)
    if region_hash != hashes["extracted_sequence_sha256"]:
        raise Mt01VerificationError(f"{UPSTREAM_MISMATCH}: extracted region SHA-256 mismatch.")

    component_sequences: dict[str, dict[str, str]] = {}
    component_results = []
    for item in components["components"]:
        component_id = item["component_case_id"]
        start, end = _internal(item["source_physical_interval"])
        physical = source_sequence[start:end]
        transform = item["ui_input_transformation"]
        ui_input = (
            _reverse_complement(physical)
            if transform == "reverse_complement_source_physical_span"
            else physical
        )
        if _sha256_sequence(physical) != item["expected_physical_segment_sha256"]:
            raise Mt01VerificationError(f"{component_id} physical segment SHA-256 mismatch.")
        if _sha256_sequence(ui_input) != item["expected_input_sequence_sha256"]:
            raise Mt01VerificationError(f"{component_id} UI input SHA-256 mismatch.")
        component_sequences[component_id] = {"physical": physical, "ui_input": ui_input}
        component_results.append(
            {
                "component_case_id": component_id,
                "physical_length_bp": len(physical),
                "physical_sequence_sha256": _sha256_sequence(physical),
                "ui_input_length_bp": len(ui_input),
                "ui_input_sequence_sha256": _sha256_sequence(ui_input),
                "transformation": transform,
                "status": "pass",
            }
        )

    junction_results = []
    for item in components["unannotated_intervals"]:
        start, end = _internal(item["source_interval"])
        sequence = source_sequence[start:end]
        if _sha256_sequence(sequence) != item["sequence_sha256"]:
            raise Mt01VerificationError(f"{item['junction_id']} sequence SHA-256 mismatch.")
        invalid = sorted(set(sequence) - STRICT_DNA)
        if invalid:
            raise Mt01VerificationError(
                f"{item['junction_id']} contains unknown nucleotide symbols: {', '.join(invalid)}"
            )
        junction_results.append(
            {
                "junction_id": item["junction_id"],
                "length_bp": len(sequence),
                "sequence_sha256": _sha256_sequence(sequence),
                "category": item["category"],
                "unknown_nucleotide_count": 0,
                "status": "pass",
            }
        )

    tu1_input = (
        component_sequences["MT-01-TU1-PROMOTER-SIDE"]["ui_input"]
        + component_sequences["MT-01-TU1-CDS"]["ui_input"]
        + component_sequences["MT-01-TU1-THREE-PRIME"]["ui_input"]
    )
    tu1_physical = _reverse_complement(tu1_input)
    tu2_physical = (
        component_sequences["MT-01-TU2-PROMOTER-SIDE"]["ui_input"]
        + component_sequences["MT-01-TU2-CDS"]["ui_input"]
        + component_sequences["MT-01-TU2-THREE-PRIME"]["ui_input"]
    )
    if tu1_physical != source_sequence[570:2323]:
        raise Mt01VerificationError("TU1 reverse-orientation reconstruction mismatch.")
    if tu2_physical != source_sequence[2323:4649]:
        raise Mt01VerificationError("TU2 forward reconstruction mismatch.")
    if tu1_physical + tu2_physical != region:
        raise Mt01VerificationError("TU physical concatenation does not equal the region.")

    runtime_result = (
        _runtime_verify(
            region,
            component_sequences,
            timeout_seconds=runtime_timeout_seconds,
        )
        if verify_runtime
        else {"status": "not_requested", "runtime_model_gap_code": None}
    )
    retrieval = retrieval_metadata or {
        "method": "local repository-external GenBank file",
        "retrieved_at_utc": None,
        "response_content_type": None,
    }
    return {
        "schema_version": "mt01-verification-result-v1",
        "case_id": "MT-01",
        "status": "pass",
        "source": {
            "retrieval_method": retrieval.get("method"),
            "retrieval_date_time_utc": retrieval.get("retrieved_at_utc"),
            "exact_accession_version": "KX758647.1",
            "response_content_type": retrieval.get("response_content_type"),
            "file_name": resolved_source.name,
            "raw_file_size_bytes": len(raw_bytes),
            "raw_file_sha256": raw_hash,
            "parsed_record_id": record.id,
            "parsed_sequence_length_bp": len(source_sequence),
            "parsed_topology": str(record.annotations.get("topology") or ""),
            "parsed_sequence_sha256": source_hash,
            "feature_count": len(record.features),
            "parser": "Biopython SeqIO GenBank",
            "parser_version": BIOPYTHON_VERSION,
        },
        "region": {
            "source_external_interval": "571..4649",
            "source_internal_interval": "[570,4649)",
            "wraparound": False,
            "topology": "linear",
            "length_bp": len(region),
            "sequence_sha256": region_hash,
        },
        "components": component_results,
        "unannotated_intervals": junction_results,
        "proofs": {
            "source_slice": "pass",
            "tu_physical_concatenation": "pass",
            "tu1_reverse_input_reconstruction": "pass",
            "tu2_forward_input_reconstruction": "pass",
            "atomic_partition": "pass",
            "all_nucleotides_known": True,
        },
        "runtime_verification": runtime_result,
        "redistribution_status": "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY",
    }


def _is_inside_repository(path: Path) -> bool:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def _require_external_path(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    if _is_inside_repository(resolved):
        raise Mt01VerificationError(f"{label} must be outside the repository: {resolved}")
    return resolved


def fetch_source(accession: str, cache_dir: Path, source_contract: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    if accession != "KX758647.1":
        raise Mt01VerificationError("Only exact accession/version KX758647.1 is accepted.")
    resolved_cache = _require_external_path(cache_dir, label="Source cache directory")
    resolved_cache.mkdir(parents=True, exist_ok=True)
    url = source_contract["retrieval"]["url"]
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BioDesign-Studio-MT01-contract-verifier/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw_bytes = response.read()
            content_type = response.headers.get_content_type()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Mt01VerificationError(
            "NCBI source retrieval failed. Retry later or provide an audited repository-external KX758647.1 GenBank file with --genbank."
        ) from exc
    expected_type = source_contract["expected_response"]["content_type"]
    if content_type != expected_type:
        raise Mt01VerificationError(
            f"NCBI response content type mismatch: expected {expected_type}, got {content_type}."
        )
    target = resolved_cache / source_contract["expected_response"]["file_name"]
    handle, temporary_name = tempfile.mkstemp(prefix="KX758647.1.", suffix=".download", dir=resolved_cache)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw_bytes)
        Path(temporary_name).replace(target)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return target, {
        "method": "NCBI E-utilities efetch anonymous HTTPS",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "response_content_type": content_type,
        "url": url,
    }


def _write_result(result: dict[str, Any], output_path: Path) -> None:
    resolved = _require_external_path(output_path, label="Verification JSON output")
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise Mt01VerificationError(
            f"Verification JSON could not be written to the repository-external path: {resolved}"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify MT-01 from an exact KX758647.1 GenBank source without emitting DNA sequences."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--genbank", type=Path, help="Repository-external local KX758647.1 GenBank file.")
    source.add_argument("--accession", help="Exact versioned accession; only KX758647.1 is accepted.")
    parser.add_argument("--cache-dir", type=Path, help="Required repository-external cache directory with --accession.")
    parser.add_argument("--output-json", type=Path, required=True, help="Repository-external machine-readable result path.")
    parser.add_argument("--contracts-dir", type=Path, default=DEFAULT_CONTRACT_DIR)
    parser.add_argument("--verify-runtime", action="store_true", help="Also run the existing formal Multi-TU assembly service.")
    parser.add_argument("--runtime-timeout-seconds", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contracts = load_contracts(args.contracts_dir)
        retrieval_metadata = None
        if args.accession:
            if args.cache_dir is None:
                raise Mt01VerificationError("--cache-dir is required with --accession.")
            source_path, retrieval_metadata = fetch_source(
                args.accession, args.cache_dir, contracts["source_contract"]
            )
        else:
            source_path = args.genbank
        result = verify_source_file(
            source_path,
            contract_dir=args.contracts_dir,
            verify_runtime=args.verify_runtime,
            runtime_timeout_seconds=args.runtime_timeout_seconds,
            retrieval_metadata=retrieval_metadata,
        )
        _write_result(result, args.output_json)
        print(json.dumps({"case_id": "MT-01", "status": "pass", "output_json": str(args.output_json.resolve())}))
        return 0
    except Mt01VerificationError as exc:
        print(f"MT-01 verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
