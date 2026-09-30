"""Independent MVP7 single-gene reference cases and file-format checks.

This module deliberately uses only the Python standard library plus Biopython
for independent parsing. It does not import the BioDesign production runtime,
assembly, export, or persistence services.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_DATA_PATH = REPO_ROOT / "tests" / "data" / "mvp7_single_gene_accuracy_cases.json"
MATRIX_PATH = REPO_ROOT / "docs" / "qa" / "MVP7_SINGLE_GENE_ACCURACY_VALIDATION.json"
BASELINE_COMMIT = "6ac9920efb4fe3d1cac0f82f349dc017bf944205"
VALIDATION_VERSION = "mvp7.single-gene-accuracy.v1"
DNA_ALPHABET = frozenset("ACGTNRYSWKMBDHV")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_sequence(value: str) -> str:
    return hashlib.sha256(value.upper().encode("ascii")).hexdigest()


def first_sequence_difference(expected: str, actual: str, *, radius: int = 12) -> dict[str, Any] | None:
    """Return the first exact DNA difference with compact local context."""
    limit = min(len(expected), len(actual))
    position = next((index for index in range(limit) if expected[index] != actual[index]), None)
    if position is None and len(expected) == len(actual):
        return None
    if position is None:
        position = limit
    left = max(0, position - radius)
    right = min(max(len(expected), len(actual)), position + radius + 1)
    return {
        "position_0_based": position,
        "position_1_based": position + 1,
        "expected_base": expected[position] if position < len(expected) else "<end>",
        "actual_base": actual[position] if position < len(actual) else "<end>",
        "expected_context": expected[left:right],
        "actual_context": actual[left:right],
    }


def assert_sequences_equal(expected: str, actual: str, *, label: str) -> None:
    difference = first_sequence_difference(expected, actual)
    if difference is not None:
        raise AssertionError(f"{label} sequence mismatch: {json.dumps(difference, sort_keys=True)}")


def parse_fasta_text(text: str) -> list[dict[str, str]]:
    """Parse FASTA using a small standard-library implementation."""
    records: list[dict[str, str]] = []
    title = ""
    sequence_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if title:
                records.append({"title": title, "sequence": "".join(sequence_lines).upper()})
            title = line[1:]
            sequence_lines = []
        elif title:
            sequence_lines.append("".join(line.split()))
        else:
            raise ValueError("FASTA sequence data appeared before a title line.")
    if title:
        records.append({"title": title, "sequence": "".join(sequence_lines).upper()})
    return records


def inspect_raw_genbank(text: str) -> dict[str, Any]:
    """Check required GenBank text sections without using the production exporter."""
    lines = text.splitlines()
    locus_line = next((line for line in lines if line.startswith("LOCUS")), "")
    features_index = next((index for index, line in enumerate(lines) if line.startswith("FEATURES")), -1)
    origin_index = next((index for index, line in enumerate(lines) if line.startswith("ORIGIN")), -1)
    terminated = any(line.strip() == "//" for line in lines)
    origin_lines = lines[origin_index + 1 :] if origin_index >= 0 else []
    origin_text = "".join(re.findall(r"[A-Za-z]+", "\n".join(origin_lines).split("//", 1)[0])).upper()
    length_match = re.search(r"\b(\d+)\s+bp\b", locus_line)
    declared_length = int(length_match.group(1)) if length_match else 0
    topology = "circular" if re.search(r"\bcircular\b", locus_line, re.IGNORECASE) else (
        "linear" if re.search(r"\blinear\b", locus_line, re.IGNORECASE) else ""
    )
    return {
        "has_locus": bool(locus_line),
        "topology": topology,
        "has_features": features_index >= 0,
        "has_origin": origin_index >= 0,
        "terminated": terminated,
        "declared_length": declared_length,
        "actual_sequence_length": len(origin_text),
        "origin_sequence": origin_text,
    }


def _pattern(length: int, offset: int = 0) -> str:
    alphabet = "ACGT"
    return "".join(alphabet[(index + offset) % 4] for index in range(length))


def _valid_cds(codon_count: int, codon: str = "GCT") -> str:
    return "ATG" + (codon * codon_count) + "TAA"


def _simple_feature(
    name: str,
    feature_type: str,
    start: int,
    end: int,
    *,
    strand: int = 1,
    qualifiers: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "feature_type": feature_type,
        "strand": strand,
        "parts_0_based_half_open": [{"start": start, "end": end, "strand": strand}],
        "qualifiers": qualifiers or {"label": [name]},
    }


def _compound_feature(
    name: str,
    feature_type: str,
    parts: list[tuple[int, int]],
    *,
    strand: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "feature_type": feature_type,
        "strand": strand,
        "location_operator": "join",
        "parts_0_based_half_open": [
            {"start": start, "end": end, "strand": strand} for start, end in parts
        ],
        "qualifiers": {"label": [name], "note": ["cross-origin fixture feature"]},
    }


def _case_one_seed() -> dict[str, Any]:
    fixture_root = REPO_ROOT / "examples" / "plant_single_gene_mvp"
    promoter_text = (fixture_root / "r229_promoter.fasta").read_text(encoding="utf-8")
    cds_text = (fixture_root / "r229_cds.fasta").read_text(encoding="utf-8")
    terminator_text = (fixture_root / "r229_terminator.fasta").read_text(encoding="utf-8")
    backbone_text = (fixture_root / "r229_backbone.gb").read_text(encoding="utf-8")
    promoter = str(next(SeqIO.parse(StringIO(promoter_text), "fasta")).seq).upper()
    cds = str(next(SeqIO.parse(StringIO(cds_text), "fasta")).seq).upper()
    terminator = str(next(SeqIO.parse(StringIO(terminator_text), "fasta")).seq).upper()
    record = next(SeqIO.parse(StringIO(backbone_text), "genbank"))
    features: list[dict[str, Any]] = []
    for feature in record.features:
        qualifiers = {
            str(key): [str(item) for item in values]
            for key, values in (feature.qualifiers or {}).items()
        }
        name = str((qualifiers.get("label") or qualifiers.get("gene") or [feature.type])[0])
        parts = list(getattr(feature.location, "parts", None) or [feature.location])
        features.append(
            {
                "name": name,
                "feature_type": str(feature.type),
                "strand": int(feature.location.strand or 1),
                "parts_0_based_half_open": [
                    {
                        "start": int(part.start),
                        "end": int(part.end),
                        "strand": int(part.strand or feature.location.strand or 1),
                    }
                    for part in parts
                ],
                "qualifiers": qualifiers,
            }
        )
    return {
        "case_id": "case_01_stable_example",
        "description": "Current stable example with fixed export and parsed-sequence hashes.",
        "project_name": "Plant single-gene MVP",
        "component_names": {
            "promoter": "PROMOTER_COMPONENT_R229",
            "cds": "CDS_COMPONENT_R229",
            "terminator": "TERMINATOR_COMPONENT_R229",
        },
        "promoter_sequence": promoter,
        "cds_sequence": cds,
        "terminator_sequence": terminator,
        "backbone_sequence": str(record.seq).upper(),
        "backbone_features": features,
        "backbone_input_kind": "repository_fixture_genbank",
        "backbone_input_path": "examples/plant_single_gene_mvp/r229_backbone.gb",
        "topology": "circular",
        "insertion_mode": "insertion",
        "insertion_coordinates": {"start": 2100, "end": 2101},
        "expected_removed_sequence": "",
        "stable_baseline_hashes": {
            "fasta_file_sha256": "bff837583dad749f5b7e84c40750e3d479770ac534bcf4e9a1b0d2149b1577a3",
            "genbank_file_sha256": "718a9dc01e371d6ee8e92b6f26d3f046d2de67749967a3ed458926014f23723b",
            "parsed_sequence_sha256": "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb",
        },
    }


def _seed_cases() -> list[dict[str, Any]]:
    replacement_5 = "GGGAAACCCGGGTTTAAACC"
    replacement_6 = "CCCGGGAAATT"
    replacement_10 = "TTAACCGGTTCCAAGGTTAA"
    case_5_backbone = _pattern(60, 1) + replacement_5 + _pattern(100, 2)
    case_6_backbone = "A" + replacement_6 + _pattern(128, 3)
    case_10_backbone = _pattern(140, 2) + replacement_10 + _pattern(140, 1)
    return [
        _case_one_seed(),
        {
            "case_id": "case_02_variable_user_components",
            "description": "Different user promoter, CDS, and terminator lengths at an internal insertion.",
            "project_name": "MVP7 case 02",
            "component_names": {"promoter": "USER_PROMOTER_02", "cds": "USER_CDS_02", "terminator": "USER_TERMINATOR_02"},
            "promoter_sequence": "AACCGGTTAACCGGTTA",
            "cds_sequence": _valid_cds(17, "GCC"),
            "terminator_sequence": "TTGGAATTCCGGA",
            "backbone_sequence": _pattern(180, 1),
            "backbone_features": [_simple_feature("UPSTREAM_02", "misc_feature", 10, 25), _simple_feature("DOWNSTREAM_02", "misc_feature", 110, 128)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 73, "end": 74},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_03_backbone_start_insertion",
            "description": "Insertion at the first adjacent coordinate pair with all original features downstream.",
            "project_name": "MVP7 case 03",
            "component_names": {"promoter": "PROMOTER_03", "cds": "CDS_03", "terminator": "TERMINATOR_03"},
            "promoter_sequence": "GGAACCTTAACC",
            "cds_sequence": _valid_cds(20, "GCT"),
            "terminator_sequence": "CCAATTGGCCA",
            "backbone_sequence": _pattern(140, 2),
            "backbone_features": [_simple_feature("START_A", "misc_feature", 5, 15), _simple_feature("START_B", "rep_origin", 40, 60), _simple_feature("START_C", "misc_feature", 100, 120, strand=-1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 1, "end": 2},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_04_circular_end_insertion",
            "description": "Insertion across the circular length-to-one boundary.",
            "project_name": "MVP7 case 04",
            "component_names": {"promoter": "PROMOTER_04", "cds": "CDS_04", "terminator": "TERMINATOR_04"},
            "promoter_sequence": "TTAACCGGTTA",
            "cds_sequence": _valid_cds(18, "GCA"),
            "terminator_sequence": "GGTTAACCGG",
            "backbone_sequence": _pattern(150, 3),
            "backbone_features": [_simple_feature("END_UP", "misc_feature", 5, 20), _simple_feature("END_TAIL", "misc_feature", 100, 130, strand=-1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 150, "end": 1},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_05_internal_replacement",
            "description": "Internal backbone interval replacement with exact length delta and no removed-region residue.",
            "project_name": "MVP7 case 05",
            "component_names": {"promoter": "PROMOTER_05", "cds": "CDS_05", "terminator": "TERMINATOR_05"},
            "promoter_sequence": "AACCTTGGAACCTT",
            "cds_sequence": _valid_cds(22, "GCG"),
            "terminator_sequence": "TTCCAAGGTTCC",
            "backbone_sequence": case_5_backbone,
            "backbone_features": [_simple_feature("REPLACE_UP", "misc_feature", 10, 25), _simple_feature("REPLACE_DOWN", "misc_feature", 100, 120, strand=-1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "replacement",
            "insertion_coordinates": {"start": 61, "end": 80},
            "expected_removed_sequence": replacement_5,
        },
        {
            "case_id": "case_06_boundary_replacement",
            "description": "Replacement next to the backbone origin with explicit off-by-one guards.",
            "project_name": "MVP7 case 06",
            "component_names": {"promoter": "PROMOTER_06", "cds": "CDS_06", "terminator": "TERMINATOR_06"},
            "promoter_sequence": "CGTTAACCGT",
            "cds_sequence": _valid_cds(19, "GCT"),
            "terminator_sequence": "AACCGGTTAAC",
            "backbone_sequence": case_6_backbone,
            "backbone_features": [_simple_feature("ORIGIN_EDGE", "misc_feature", 0, 1), _simple_feature("BOUNDARY_DOWN", "misc_feature", 30, 45)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "replacement",
            "insertion_coordinates": {"start": 2, "end": 12},
            "expected_removed_sequence": replacement_6,
        },
        {
            "case_id": "case_07_multiple_upstream_downstream_features",
            "description": "Multiple features before and after insertion verify unchanged and shifted coordinates.",
            "project_name": "MVP7 case 07",
            "component_names": {"promoter": "PROMOTER_07", "cds": "CDS_07", "terminator": "TERMINATOR_07"},
            "promoter_sequence": "AAGGTTCCAAGG",
            "cds_sequence": _valid_cds(24, "GCC"),
            "terminator_sequence": "CCTTAAGGCCTT",
            "backbone_sequence": _pattern(220),
            "backbone_features": [_simple_feature("UP_A", "misc_feature", 10, 20), _simple_feature("UP_B", "rep_origin", 60, 80), _simple_feature("DOWN_A", "misc_feature", 130, 150), _simple_feature("DOWN_B", "misc_feature", 180, 205)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 100, "end": 101},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_08_reverse_strand_feature",
            "description": "Reverse-strand backbone feature retains strand minus one after coordinate migration.",
            "project_name": "MVP7 case 08",
            "component_names": {"promoter": "PROMOTER_08", "cds": "CDS_08", "terminator": "TERMINATOR_08"},
            "promoter_sequence": "TTCCAAGGTTCC",
            "cds_sequence": _valid_cds(21, "GCA"),
            "terminator_sequence": "GGCCAATTGGCC",
            "backbone_sequence": _pattern(180, 1),
            "backbone_features": [_simple_feature("FORWARD_08", "misc_feature", 20, 40), _simple_feature("REVERSE_08", "CDS", 120, 150, strand=-1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 90, "end": 91},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_09_cross_origin_feature",
            "description": "Cross-origin reverse-strand CompoundLocation remains parseable after insertion.",
            "project_name": "MVP7 case 09",
            "component_names": {"promoter": "PROMOTER_09", "cds": "CDS_09", "terminator": "TERMINATOR_09"},
            "promoter_sequence": "AACCGGTTAACC",
            "cds_sequence": _valid_cds(23, "GCT"),
            "terminator_sequence": "TTAACCGGTTA",
            "backbone_sequence": _pattern(160, 2),
            "backbone_features": [_simple_feature("INTERNAL_09", "misc_feature", 25, 40), _compound_feature("CROSS_ORIGIN_09", "CDS", [(145, 160), (0, 12)], strand=-1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "insertion",
            "insertion_coordinates": {"start": 60, "end": 61},
            "expected_removed_sequence": "",
        },
        {
            "case_id": "case_10_complex_uploaded_genbank",
            "description": "Complex uploaded-style GenBank with forward, reverse, compound, replacement, save, and reopen coverage.",
            "project_name": "MVP7 case 10",
            "component_names": {"promoter": "PROMOTER_10", "cds": "CDS_10", "terminator": "TERMINATOR_10"},
            "promoter_sequence": "GGTTAACCGGTTAACC",
            "cds_sequence": _valid_cds(28, "GCG"),
            "terminator_sequence": "CCAAGGTTCCAAGG",
            "backbone_sequence": case_10_backbone,
            "backbone_features": [_simple_feature("COMPLEX_UP", "rep_origin", 25, 55), _simple_feature("COMPLEX_REVERSE", "CDS", 80, 115, strand=-1), _simple_feature("COMPLEX_DOWN", "misc_feature", 210, 245), _compound_feature("COMPLEX_CROSS", "misc_feature", [(275, 300), (0, 10)], strand=1)],
            "backbone_input_kind": "generated_fixture_genbank",
            "topology": "circular",
            "insertion_mode": "replacement",
            "insertion_coordinates": {"start": 141, "end": 160},
            "expected_removed_sequence": replacement_10,
        },
    ]


def _parts_overlap(parts: list[dict[str, int]], start: int, end: int) -> bool:
    return any(int(part["start"]) < end and int(part["end"]) > start for part in parts)


def _shift_feature(
    feature: dict[str, Any],
    *,
    mode: str,
    boundary: int,
    delta: int,
) -> dict[str, Any]:
    shifted = deepcopy(feature)
    shifted_parts: list[dict[str, int]] = []
    for part in feature["parts_0_based_half_open"]:
        start = int(part["start"])
        end = int(part["end"])
        if start >= boundary:
            start += delta
            end += delta
        shifted_parts.append({"start": start, "end": end, "strand": int(part.get("strand", feature["strand"]))})
    shifted["parts_0_based_half_open"] = shifted_parts
    shifted["source"] = "backbone"
    return shifted


def _finalize_feature(feature: dict[str, Any]) -> dict[str, Any]:
    parts = [dict(part) for part in feature["parts_0_based_half_open"]]
    start = min(int(part["start"]) for part in parts)
    end = max(int(part["end"]) for part in parts)
    return {
        "name": str(feature["name"]),
        "feature_type": str(feature["feature_type"]),
        "source": str(feature["source"]),
        "strand": int(feature["strand"]),
        "location_operator": str(feature.get("location_operator") or ("join" if len(parts) > 1 else "")),
        "start_0_based": start,
        "end_0_based_exclusive": end,
        "start_1_based": start + 1,
        "end_1_based_inclusive": end,
        "parts_0_based_half_open": parts,
        "parts_1_based_inclusive": [
            {"start": int(part["start"]) + 1, "end": int(part["end"]), "strand": int(part["strand"])}
            for part in parts
        ],
    }


def build_reference_case(seed: dict[str, Any]) -> dict[str, Any]:
    """Compute one expected result with independent string and coordinate logic."""
    case = deepcopy(seed)
    promoter = str(case["promoter_sequence"]).upper()
    cds = str(case["cds_sequence"]).upper()
    terminator = str(case["terminator_sequence"]).upper()
    backbone = str(case["backbone_sequence"]).upper()
    cassette = promoter + cds + terminator
    mode = str(case["insertion_mode"])
    coordinates = case["insertion_coordinates"]
    start_coordinate = int(coordinates["start"])
    end_coordinate = int(coordinates["end"])
    removed_sequence = ""
    if mode == "insertion":
        cut_index = start_coordinate
        plasmid = backbone[:cut_index] + cassette + backbone[cut_index:]
        feature_boundary = cut_index
        feature_delta = len(cassette)
        cassette_start = cut_index
        for feature in case["backbone_features"]:
            if any(int(part["start"]) < cut_index < int(part["end"]) for part in feature["parts_0_based_half_open"]):
                raise ValueError(f"{case['case_id']} fixture feature overlaps insertion boundary")
    elif mode == "replacement":
        start0 = start_coordinate - 1
        end0 = end_coordinate
        removed_sequence = backbone[start0:end0]
        if removed_sequence != str(case["expected_removed_sequence"]):
            raise ValueError(f"{case['case_id']} replacement fixture does not match its expected removed sequence")
        for feature in case["backbone_features"]:
            if _parts_overlap(feature["parts_0_based_half_open"], start0, end0):
                raise ValueError(f"{case['case_id']} fixture feature overlaps replacement interval")
        plasmid = backbone[:start0] + cassette + backbone[end0:]
        feature_boundary = end0
        feature_delta = len(cassette) - (end0 - start0)
        cassette_start = start0
    else:
        raise ValueError(f"Unsupported fixture insertion mode: {mode}")

    names = case["component_names"]
    cassette_features = [
        {
            "name": names["promoter"],
            "feature_type": "promoter",
            "source": "transcription_unit",
            "strand": 1,
            "parts_0_based_half_open": [{"start": cassette_start, "end": cassette_start + len(promoter), "strand": 1}],
        },
        {
            "name": names["cds"],
            "feature_type": "cds",
            "source": "transcription_unit",
            "strand": 1,
            "parts_0_based_half_open": [{"start": cassette_start + len(promoter), "end": cassette_start + len(promoter) + len(cds), "strand": 1}],
        },
        {
            "name": names["terminator"],
            "feature_type": "terminator",
            "source": "transcription_unit",
            "strand": 1,
            "parts_0_based_half_open": [{"start": cassette_start + len(promoter) + len(cds), "end": cassette_start + len(cassette), "strand": 1}],
        },
    ]
    shifted_backbone = [
        _shift_feature(feature, mode=mode, boundary=feature_boundary, delta=feature_delta)
        for feature in case["backbone_features"]
    ]
    expected_features = [_finalize_feature(feature) for feature in [*shifted_backbone, *cassette_features]]
    expected_features.sort(
        key=lambda item: (item["start_0_based"], item["end_0_based_exclusive"], item["name"])
    )
    case["coordinate_conventions"] = {
        "input_insertion_coordinates": "1-based inclusive adjacent bases for insertion; 1-based inclusive interval for replacement",
        "feature_parts": "0-based half-open and 1-based inclusive copies are both stored",
    }
    case["expected"] = {
        "cassette_sequence": cassette,
        "plasmid_sequence": plasmid,
        "cassette_length": len(cassette),
        "plasmid_length": len(plasmid),
        "cassette_span_0_based_half_open": {"start": cassette_start, "end": cassette_start + len(cassette)},
        "cassette_span_1_based_inclusive": {"start": cassette_start + 1, "end": cassette_start + len(cassette)},
        "feature_locations": expected_features,
        "expected_strands": {feature["name"]: feature["strand"] for feature in expected_features},
        "removed_sequence": removed_sequence,
        "cassette_occurrences": plasmid.count(cassette),
        "removed_sequence_occurrences": plasmid.count(removed_sequence) if removed_sequence else 0,
        "cassette_sha256": sha256_sequence(cassette),
        "plasmid_sha256": sha256_sequence(plasmid),
    }
    return case


def build_case_data() -> dict[str, Any]:
    return {
        "validation_version": VALIDATION_VERSION,
        "baseline_commit": BASELINE_COMMIT,
        "coordinate_system": "Runtime DNA uses uppercase text; feature expectations include explicit zero-based half-open parts.",
        "cases": [build_reference_case(seed) for seed in _seed_cases()],
    }


def load_case_data(path: Path = CASE_DATA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _feature_location_text(feature: dict[str, Any]) -> str:
    parts = feature["parts_0_based_half_open"]
    ranges = [f"{int(part['start']) + 1}..{int(part['end'])}" for part in parts]
    location = ranges[0] if len(ranges) == 1 else f"join({','.join(ranges)})"
    if int(feature["strand"]) == -1:
        location = f"complement({location})"
    return location


def build_fixture_genbank(case: dict[str, Any]) -> str:
    """Serialize a deterministic test-only GenBank input with the standard library."""
    sequence = str(case["backbone_sequence"]).lower()
    record_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(case["case_id"]))[:16]
    topology = str(case.get("topology") or "circular")
    lines = [
        f"LOCUS       {record_id:<16}{len(sequence):>12} bp    DNA     {topology:<8} SYN 13-JUL-2026",
        f"DEFINITION  MVP7 independent fixture for {case['case_id']}.",
        f"ACCESSION   {record_id}",
        f"VERSION     {record_id}",
        "KEYWORDS    .",
        "SOURCE      synthetic DNA construct",
        "  ORGANISM  synthetic DNA construct",
        "            other sequences; artificial sequences.",
        "FEATURES             Location/Qualifiers",
    ]
    for feature in case["backbone_features"]:
        lines.append(f"     {str(feature['feature_type']):<16}{_feature_location_text(feature)}")
        qualifiers = dict(feature.get("qualifiers") or {"label": [feature["name"]]})
        qualifiers.setdefault("label", [feature["name"]])
        for key in sorted(qualifiers):
            for value in qualifiers[key]:
                escaped = str(value).replace('"', "'")
                lines.append(f"                     /{key}=\"{escaped}\"")
    lines.append("ORIGIN")
    for offset in range(0, len(sequence), 60):
        chunk = sequence[offset : offset + 60]
        groups = " ".join(chunk[index : index + 10] for index in range(0, len(chunk), 10))
        lines.append(f"{offset + 1:>9} {groups}")
    lines.append("//")
    return "\n".join(lines) + "\n"


def _assert_reference_independence() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "services.canonical_construct_runtime",
        "services.mvp_single_gene_persistence",
        "mvp_app",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    violations = sorted(name for name in imported if name in forbidden_imports)
    if violations:
        raise AssertionError(f"Independent reference imported production modules: {violations}")


def self_check(path: Path = CASE_DATA_PATH) -> dict[str, Any]:
    _assert_reference_independence()
    generated = build_case_data()
    if path.exists():
        stored = load_case_data(path)
        if stored != generated:
            raise AssertionError("Stored MVP7 cases differ from the independently regenerated reference data.")
    checks: list[dict[str, Any]] = []
    for case in generated["cases"]:
        expected = case["expected"]
        assert len(expected["cassette_sequence"]) == expected["cassette_length"]
        assert len(expected["plasmid_sequence"]) == expected["plasmid_length"]
        assert sha256_sequence(expected["cassette_sequence"]) == expected["cassette_sha256"]
        assert sha256_sequence(expected["plasmid_sequence"]) == expected["plasmid_sha256"]
        assert expected["cassette_occurrences"] == 1
        if expected["removed_sequence"]:
            assert expected["removed_sequence_occurrences"] == 0
        fixture_text = (
            (REPO_ROOT / case["backbone_input_path"]).read_text(encoding="utf-8")
            if case.get("backbone_input_path")
            else build_fixture_genbank(case)
        )
        parsed = list(SeqIO.parse(StringIO(fixture_text), "genbank"))
        assert len(parsed) == 1
        assert str(parsed[0].seq).upper() == case["backbone_sequence"]
        checks.append(
            {
                "case_id": case["case_id"],
                "cassette_sha256": expected["cassette_sha256"],
                "plasmid_sha256": expected["plasmid_sha256"],
                "status": "passed",
            }
        )
    return {"validation_version": VALIDATION_VERSION, "case_count": len(checks), "cases": checks, "status": "passed"}


def write_case_data(path: Path = CASE_DATA_PATH) -> None:
    path.write_text(json.dumps(build_case_data(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_validation_matrix(matrix: dict[str, Any], path: Path = MATRIX_PATH) -> None:
    required = {
        "validation_version",
        "baseline_commit",
        "cases",
        "sequence_comparisons",
        "feature_comparisons",
        "export_compatibility",
        "persistence_rounds",
        "defects_found",
        "runtime_fixes",
        "remaining_limits",
    }
    missing = sorted(required - set(matrix))
    if missing:
        raise ValueError(f"Validation matrix omitted required keys: {missing}")
    path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-cases", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.write_cases:
        write_case_data()
    report = self_check()
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
