"""Immutable AF234296.1 exact-insertion contract and sequence guards."""
from __future__ import annotations

import copy
import hashlib
from typing import Any


PCAMBIA1300_EXACT_INSERTION_CONTRACT_VERSION = "pcambia1300-af234296.1-xbai-v1"
PCAMBIA1300_EXACT_INSERTION_CONTRACT: dict[str, Any] = {
    "contract_version": PCAMBIA1300_EXACT_INSERTION_CONTRACT_VERSION,
    "asset_id": "pcambia1300_af234296_1",
    "asset_kind": "exact_insertion_source",
    "accession_version": "AF234296.1",
    "circular": True,
    "full_sequence_length": 8958,
    "full_sequence_sha256": "83c7d28d071a9ff167dbe78817b2b20a5e285dcc6e1637e7392adb9f7be89de6",
    "external_cut_boundary": "27|28",
    "internal_cut_index": 27,
    "coordinate_system": "0-based insertion index",
    "insertion_method": "source[:27] + cassette + source[27:]",
    "source_feature": "pUC18 MCS / polylinker; XbaI site at 27..32",
    "retained_feature_summary": [
        "T-DNA right border: 298..323",
        "T-DNA left border: 6557..6582",
        "hptII cassette envelope: 6649..8714",
        "bacterial replication and selection regions",
    ],
    "disrupted_feature_summary": [
        "XbaI recognition site at 27..32",
        "pUC18 MCS / polylinker annotation at 28..78 is superseded",
        "LacZ alpha annotation is interrupted",
    ],
    "requires_exact_insertion": True,
    "supported_workflows": ["rice_alb_single_gene"],
    "blocked_workflows": ["generic_multi_tu", "gate3"],
    "arbitrary_insert_allowed": False,
    "direct_arbitrary_insert_allowed": False,
    "preserve_hptII": True,
    "preserve_borders": True,
    "reference_access": True,
    "warning_text": (
        "Complete pCAMBIA-1300 binary-vector source. The expression cassette is inserted "
        "at the fixed XbaI boundary 27|28 in the annotated pUC18 MCS. The hptII plant "
        "selection cassette and both T-DNA borders are retained. User-defined insertion "
        "coordinates are not allowed."
    ),
}


class Pcambia1300ExactInsertionContractError(ValueError):
    """Raised when AF234296.1 or its requested operation differs from the contract."""


def exact_insertion_contract() -> dict[str, Any]:
    return copy.deepcopy(PCAMBIA1300_EXACT_INSERTION_CONTRACT)


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(str(sequence or "").upper().encode("ascii")).hexdigest()


def is_pcambia1300_sequence(sequence: str) -> bool:
    normalized = str(sequence or "").upper()
    return (
        len(normalized) == PCAMBIA1300_EXACT_INSERTION_CONTRACT["full_sequence_length"]
        and sequence_sha256(normalized)
        == PCAMBIA1300_EXACT_INSERTION_CONTRACT["full_sequence_sha256"]
    )


def is_pcambia1300_record(record: dict[str, Any]) -> bool:
    sequence = str(record.get("normalized_sequence") or "").upper()
    identifiers = {
        str(record.get(key) or "").strip().upper()
        for key in (
            "source_accession_version",
            "original_record_identifier",
            "source_reference",
            "source_name",
            "display_name",
        )
    }
    return is_pcambia1300_sequence(sequence) or any(
        value == "AF234296.1" or "PCAMBIA-1300" in value or "PCAMBIA1300" in value
        for value in identifiers
    )


def validate_pcambia1300_source(
    sequence: str, *, accession_version: str, circular: bool
) -> dict[str, Any]:
    contract = exact_insertion_contract()
    normalized = str(sequence or "").upper()
    if str(accession_version or "") != contract["accession_version"]:
        raise Pcambia1300ExactInsertionContractError(
            "The source accession/version is not AF234296.1, so the pCAMBIA-1300 exact-insertion contract cannot be used."
        )
    if not bool(circular):
        raise Pcambia1300ExactInsertionContractError(
            "AF234296.1 must be recorded as a circular complete binary vector."
        )
    if len(normalized) != contract["full_sequence_length"]:
        raise Pcambia1300ExactInsertionContractError(
            "The AF234296.1 source sequence must be exactly 8,958 bp."
        )
    if sequence_sha256(normalized) != contract["full_sequence_sha256"]:
        raise Pcambia1300ExactInsertionContractError(
            "The source sequence SHA-256 does not match the reviewed AF234296.1 record."
        )
    if normalized[26:32] != "TCTAGA":
        raise Pcambia1300ExactInsertionContractError(
            "The reviewed AF234296.1 XbaI recognition sequence at 27..32 is missing."
        )
    return contract


def fixed_insertion_settings() -> dict[str, Any]:
    contract = exact_insertion_contract()
    return {
        "mode": "insertion",
        "start_coordinate": 27,
        "end_coordinate": 28,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
        "construction_strategy_confirmed": True,
        "exact_insertion_contract": contract,
        "exact_insertion_contract_version": contract["contract_version"],
        "workflow_support_status": "supported_rice_alb_single_gene",
    }


def validate_pcambia1300_operation(
    *,
    source_sequence: str,
    accession_version: str,
    circular: bool,
    mode: str,
    start_coordinate: int,
    end_coordinate: int,
    insertion_orientation: str,
    workflow_id: str,
) -> dict[str, Any]:
    contract = validate_pcambia1300_source(
        source_sequence,
        accession_version=accession_version,
        circular=circular,
    )
    if str(workflow_id or "") != "rice_alb_single_gene":
        if str(workflow_id or "") == "gate3":
            workflow_message = "Gate 3"
        elif str(workflow_id or "") == "generic_multi_tu":
            workflow_message = "Multi-TU"
        else:
            workflow_message = "this workflow"
        raise Pcambia1300ExactInsertionContractError(
            f"pCAMBIA-1300 is blocked in {workflow_message}: multi-TU capacity, orientation, and promoter-interference acceptance is not complete."
        )
    if str(mode or "").lower() != "insertion":
        raise Pcambia1300ExactInsertionContractError(
            "AF234296.1 does not allow replacement or arbitrary insert modes; use its fixed exact-insertion contract."
        )
    if (int(start_coordinate), int(end_coordinate)) != (27, 28):
        if (int(start_coordinate), int(end_coordinate)) == (219, 220):
            raise Pcambia1300ExactInsertionContractError(
                "The legacy AF234296.1 boundary 219|220 is unsupported. Reapply the fixed 27|28 XbaI insertion contract."
            )
        raise Pcambia1300ExactInsertionContractError(
            "AF234296.1 insertion coordinates are fixed at external boundary 27|28 (internal index 27)."
        )
    if str(insertion_orientation or "forward").lower() != "forward":
        raise Pcambia1300ExactInsertionContractError(
            "AF234296.1 exact insertion uses the approved forward cassette orientation."
        )
    return contract


def insert_pcambia1300_cassette(
    source_sequence: str,
    cassette_sequence: str,
    *,
    accession_version: str = "AF234296.1",
    circular: bool = True,
) -> str:
    contract = validate_pcambia1300_source(
        source_sequence,
        accession_version=accession_version,
        circular=circular,
    )
    source = str(source_sequence or "").upper()
    cassette = str(cassette_sequence or "").upper()
    if not cassette:
        raise Pcambia1300ExactInsertionContractError("The insertion cassette sequence is empty.")
    cut = int(contract["internal_cut_index"])
    result = source[:cut] + cassette + source[cut:]
    if len(result) != contract["full_sequence_length"] + len(cassette):
        raise Pcambia1300ExactInsertionContractError(
            "The pCAMBIA-1300 insertion output length does not match 8,958 + cassette length."
        )
    if result[:cut] + result[cut + len(cassette) :] != source:
        raise Pcambia1300ExactInsertionContractError(
            "The pCAMBIA-1300 source sequence was not preserved exactly around the insertion."
        )
    return result


def _feature_parts(feature: dict[str, Any]) -> list[dict[str, int]]:
    parts = list(feature.get("location_parts") or [])
    if parts:
        return [
            {
                "start": int(part.get("start", 0)),
                "end": int(part.get("end", 0)),
                "strand": int(part.get("strand", feature.get("strand", 1)) or 1),
            }
            for part in parts
        ]
    return [
        {
            "start": int(feature.get("start", 0)),
            "end": int(feature.get("end", 0)),
            "strand": int(feature.get("strand", 1) or 1),
        }
    ]


def _shift_or_split_parts(
    parts: list[dict[str, int]], *, cut_index: int, cassette_length: int
) -> list[dict[str, int]]:
    remapped: list[dict[str, int]] = []
    for part in parts:
        start, end, strand = part["start"], part["end"], part["strand"]
        if end <= cut_index:
            remapped.append({"start": start, "end": end, "strand": strand})
        elif start >= cut_index:
            remapped.append(
                {
                    "start": start + cassette_length,
                    "end": end + cassette_length,
                    "strand": strand,
                }
            )
        else:
            remapped.extend(
                [
                    {"start": start, "end": cut_index, "strand": strand},
                    {
                        "start": cut_index + cassette_length,
                        "end": end + cassette_length,
                        "strand": strand,
                    },
                ]
            )
    return [part for part in remapped if part["end"] > part["start"]]


def remap_pcambia1300_features(
    features: list[dict[str, Any]], *, cassette_length: int
) -> list[dict[str, Any]]:
    """Remap AF234296.1 features while marking MCS/LacZ annotations interrupted."""
    cut = int(PCAMBIA1300_EXACT_INSERTION_CONTRACT["internal_cut_index"])
    remapped: list[dict[str, Any]] = []
    for source_feature in features:
        feature = copy.deepcopy(source_feature)
        if str(feature.get("type") or "").lower() == "source":
            feature["end"] = int(feature.get("end", 0)) + cassette_length
            feature["location_parts"] = []
            remapped.append(feature)
            continue

        label = str(feature.get("label") or feature.get("name") or "")
        label_lower = label.lower()
        qualifier_text = " ".join(
            str(value)
            for values in dict(feature.get("qualifiers") or {}).values()
            for value in (values if isinstance(values, list) else [values])
        ).lower()
        parts = _feature_parts(feature)
        crosses_cut = any(part["start"] < cut < part["end"] for part in parts)
        is_mcs = "mcs" in label_lower or "polylinker" in label_lower
        is_lacz = "lacz alpha" in label_lower or "lacz alpha" in qualifier_text
        remapped_parts = _shift_or_split_parts(
            parts, cut_index=cut, cassette_length=cassette_length
        )
        feature["start"] = min(part["start"] for part in remapped_parts)
        feature["end"] = max(part["end"] for part in remapped_parts)
        feature["location_parts"] = remapped_parts if len(remapped_parts) > 1 else []

        if crosses_cut or is_mcs or is_lacz:
            status = "superseded" if is_mcs else "interrupted"
            base_label = "pUC18 MCS / polylinker" if is_mcs else ("LacZ alpha fragment" if is_lacz else label)
            feature["type"] = "misc_feature"
            feature["label"] = f"{base_label} ({status} by exact XbaI insertion)"
            feature["name"] = feature["label"]
            qualifiers = copy.deepcopy(feature.get("qualifiers") or {})
            qualifiers["label"] = [feature["label"]]
            qualifiers["feature_status"] = [status]
            qualifiers["disrupted_by"] = [PCAMBIA1300_EXACT_INSERTION_CONTRACT_VERSION]
            qualifiers.setdefault("note", []).append(
                "The original AF234296.1 annotation is not represented as an intact feature after insertion at 27|28."
            )
            feature["qualifiers"] = qualifiers
        remapped.append(feature)

    remapped.append(
        {
            "feature_id": "pcambia1300-xbai-disrupted",
            "type": "misc_feature",
            "label": "XbaI site (disrupted by exact insertion)",
            "name": "XbaI site (disrupted by exact insertion)",
            "start": 26,
            "end": 32 + cassette_length,
            "strand": 1,
            "location_parts": [
                {"start": 26, "end": 27, "strand": 1},
                {
                    "start": 27 + cassette_length,
                    "end": 32 + cassette_length,
                    "strand": 1,
                },
            ],
            "location_operator": "join",
            "qualifiers": {
                "label": ["XbaI site (disrupted by exact insertion)"],
                "feature_status": ["interrupted"],
                "disrupted_by": [PCAMBIA1300_EXACT_INSERTION_CONTRACT_VERSION],
            },
            "unsupported_location": False,
        }
    )
    return remapped
