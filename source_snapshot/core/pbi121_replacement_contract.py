"""Immutable pBI121 exact-replacement contract and sequence identity guards."""
from __future__ import annotations

import copy
import hashlib
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO


PBI121_REPLACEMENT_CONTRACT_VERSION = "pbi121-exact-replacement-v1"
PBI121_REPLACEMENT_CONTRACT: dict[str, Any] = {
    "contract_version": PBI121_REPLACEMENT_CONTRACT_VERSION,
    "asset_id": "pbi121::complete_binary_vector",
    "asset_kind": "tDNA_replacement_source",
    "accession_version": "AF485783.1",
    "circular": True,
    "full_sequence_length": 14758,
    "full_sequence_sha256": "e497e664f6d6baba1bd1cafce38bceedf88c0108101bc57adf29513246497539",
    "replacement_start": 4974,
    "replacement_end": 7979,
    "coordinate_system": "1-based-inclusive",
    "normalized_replacement_start": 4973,
    "normalized_replacement_end": 7979,
    "normalized_coordinate_system": "0-based-half-open",
    "replacement_length": 3006,
    "replacement_sha256": "e010e62e9297fdda0d3956a64872766640faf24416f3fae9fac4c1fea9095d5c",
    "retained_feature_summary": [
        "T-DNA right border: 2454..2478, negative strand",
        "NOS promoter: 2519..2825",
        "nptII: 2838..3632",
        "NOS 3' regulatory region for the plant selection cassette: 4022..4277",
        "T-DNA left border: 8621..8646, negative strand",
        "ColE1 ori and ori V bacterial replication regions",
    ],
    "replaced_feature_summary": [
        "CaMV 35S promoter",
        "gusA CDS",
        "NOS 3' regulatory region for the reporter cassette",
    ],
    "requires_exact_replacement": True,
    "direct_insert_allowed": False,
    "reference_access": True,
    "supported_workflows": ["gate3_betalain_three_tu"],
    "blocked_workflows": ["formal_single_gene", "generic_multi_tu"],
    "warning_text": (
        "Complete pBI121 binary-vector source. The design sequence replaces the existing "
        "35S-gusA-NOS 3' reporter cassette exactly; the nptII plant selection cassette "
        "and both T-DNA borders are retained. Direct insertion is not allowed."
    ),
}


class Pbi121ReplacementContractError(ValueError):
    """Raised when a pBI121 source or operation differs from the fixed contract."""


def replacement_contract() -> dict[str, Any]:
    return copy.deepcopy(PBI121_REPLACEMENT_CONTRACT)


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(str(sequence or "").upper().encode("ascii")).hexdigest()


def replacement_span_zero_based_half_open() -> tuple[int, int]:
    return (
        int(PBI121_REPLACEMENT_CONTRACT["normalized_replacement_start"]),
        int(PBI121_REPLACEMENT_CONTRACT["normalized_replacement_end"]),
    )


_REVIEWED_SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "real_assets"
    / "pbi121"
    / "source_records"
    / "AF485783.1.gb"
)


def _feature_signature(feature: Any) -> tuple[Any, ...]:
    qualifiers = tuple(
        sorted(
            (
                str(key),
                tuple(str(value) for value in values),
            )
            for key, values in feature.qualifiers.items()
        )
    )
    return (
        str(feature.type or "").lower(),
        int(feature.location.start),
        int(feature.location.end),
        int(feature.location.strand or 0),
        qualifiers,
    )


def _partition_replacement_features(record: Any) -> tuple[list[Any], list[Any]]:
    start, end = replacement_span_zero_based_half_open()
    retained: list[Any] = []
    replaced: list[Any] = []
    for feature in record.features:
        feature_start = int(feature.location.start)
        feature_end = int(feature.location.end)
        overlaps = feature_start < end and feature_end > start
        if not overlaps or str(feature.type or "").lower() == "source":
            retained.append(feature)
            continue
        if feature_start < start or feature_end > end:
            raise Pbi121ReplacementContractError(
                "A pBI121 feature crosses the fixed replacement boundary; the reviewed feature contract cannot be projected."
            )
        replaced.append(feature)
    return retained, replaced


@lru_cache(maxsize=1)
def _reviewed_feature_contract() -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    try:
        reviewed = SeqIO.read(_REVIEWED_SOURCE_PATH, "genbank")
    except Exception as exc:
        raise Pbi121ReplacementContractError(
            "The packaged reviewed AF485783.1 source record cannot be parsed."
        ) from exc
    validate_pbi121_source(str(reviewed.seq), accession_version=reviewed.id)
    if str(reviewed.annotations.get("topology") or "").lower() != "circular":
        raise Pbi121ReplacementContractError(
            "The packaged reviewed AF485783.1 source record must be circular."
        )
    retained, replaced = _partition_replacement_features(reviewed)
    return (
        tuple(_feature_signature(feature) for feature in retained),
        tuple(_feature_signature(feature) for feature in replaced),
    )


def _validate_projection_features(source_record: Any) -> tuple[list[Any], bool]:
    expected_retained, expected_replaced = _reviewed_feature_contract()
    retained, replaced = _partition_replacement_features(source_record)
    observed_retained = tuple(_feature_signature(feature) for feature in retained)
    observed_replaced = tuple(_feature_signature(feature) for feature in replaced)
    if observed_retained != expected_retained:
        raise Pbi121ReplacementContractError(
            "The pBI121 retained and protected annotations do not match the reviewed AF485783.1 feature contract."
        )
    if observed_replaced not in (expected_replaced, ()):
        raise Pbi121ReplacementContractError(
            "The pBI121 annotations inside 4974..7979 do not match the reviewed replaced-feature contract."
        )
    return retained, observed_replaced == ()


def prepare_pbi121_backbone_record_for_replacement(record: dict[str, Any]) -> dict[str, Any]:
    """Build the reviewed runtime feature projection without trusting caller metadata."""
    prepared = copy.deepcopy(dict(record))
    sequence = str(prepared.get("normalized_sequence") or "").upper()
    accession = str(
        prepared.get("source_accession_version")
        or prepared.get("original_record_identifier")
        or ""
    )
    validate_pbi121_source(sequence, accession_version=accession)
    if str(prepared.get("topology") or "").lower() != "circular":
        raise Pbi121ReplacementContractError(
            "The pBI121 replacement source must retain circular topology."
        )
    raw_text = str(prepared.get("original_text") or "")
    if not raw_text:
        raise Pbi121ReplacementContractError(
            "The reviewed pBI121 GenBank source record is required for exact replacement."
        )
    try:
        source_record = SeqIO.read(StringIO(raw_text), "genbank")
    except Exception as exc:
        raise Pbi121ReplacementContractError(
            "The reviewed pBI121 GenBank source record cannot be parsed."
        ) from exc
    if source_record.id != PBI121_REPLACEMENT_CONTRACT["accession_version"]:
        raise Pbi121ReplacementContractError(
            "The pBI121 GenBank record identifier must be AF485783.1."
        )
    if str(source_record.annotations.get("topology") or "").lower() != "circular":
        raise Pbi121ReplacementContractError(
            "The pBI121 GenBank record must retain circular topology."
        )
    parsed_sequence = str(source_record.seq).upper()
    validate_pbi121_source(parsed_sequence, accession_version=source_record.id)
    if parsed_sequence != sequence:
        raise Pbi121ReplacementContractError(
            "The pBI121 GenBank source sequence differs from the admitted vector sequence."
        )

    retained_features, already_projected = _validate_projection_features(source_record)
    expected_removed_count = len(_reviewed_feature_contract()[1])
    projection_contract = {
        "contract_version": PBI121_REPLACEMENT_CONTRACT_VERSION,
        "sequence_unchanged": True,
        "removed_feature_count": expected_removed_count,
        "replacement_start": PBI121_REPLACEMENT_CONTRACT["replacement_start"],
        "replacement_end": PBI121_REPLACEMENT_CONTRACT["replacement_end"],
    }
    if already_projected:
        prepared["pbi121_replacement_feature_projection"] = projection_contract
        return prepared

    source_record.features = retained_features
    output = StringIO()
    SeqIO.write(source_record, output, "genbank")
    projected_text = output.getvalue()
    try:
        projected = SeqIO.read(StringIO(projected_text), "genbank")
    except Exception as exc:
        raise Pbi121ReplacementContractError(
            "The pBI121 runtime projection cannot be parsed."
        ) from exc
    validate_pbi121_source(str(projected.seq), accession_version=projected.id)
    _validate_projection_features(projected)
    prepared["original_text"] = projected_text
    prepared["pbi121_replacement_feature_projection"] = projection_contract
    return prepared


def validate_pbi121_backbone_record_for_replacement(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Revalidate a full or reviewed projected record at an admission boundary."""
    prepare_pbi121_backbone_record_for_replacement(record)
    return replacement_contract()


def is_pbi121_sequence(sequence: str) -> bool:
    normalized = str(sequence or "").upper()
    return (
        len(normalized) == int(PBI121_REPLACEMENT_CONTRACT["full_sequence_length"])
        and sequence_sha256(normalized) == PBI121_REPLACEMENT_CONTRACT["full_sequence_sha256"]
    )


def validate_pbi121_source(sequence: str, *, accession_version: str) -> dict[str, Any]:
    contract = replacement_contract()
    normalized = str(sequence or "").upper()
    if str(accession_version or "") != contract["accession_version"]:
        raise Pbi121ReplacementContractError(
            "The source accession/version is not AF485783.1, so the pBI121 replacement contract cannot be used."
        )
    if len(normalized) != contract["full_sequence_length"]:
        raise Pbi121ReplacementContractError("The pBI121 source sequence must be exactly 14,758 bp.")
    if sequence_sha256(normalized) != contract["full_sequence_sha256"]:
        raise Pbi121ReplacementContractError(
            "The pBI121 source sequence SHA-256 does not match the reviewed AF485783.1 record."
        )
    start, end = replacement_span_zero_based_half_open()
    replacement = normalized[start:end]
    if len(replacement) != contract["replacement_length"]:
        raise Pbi121ReplacementContractError("The fixed pBI121 replacement interval is not 3,006 bp.")
    if sequence_sha256(replacement) != contract["replacement_sha256"]:
        raise Pbi121ReplacementContractError(
            "The pBI121 4974..7979 replacement interval SHA-256 does not match the reviewed source record."
        )
    return contract


def validate_pbi121_operation(
    *,
    source_sequence: str,
    accession_version: str,
    mode: str,
    replacement_start: int,
    replacement_end: int,
) -> dict[str, Any]:
    contract = validate_pbi121_source(source_sequence, accession_version=accession_version)
    if str(mode or "").lower() != "replacement":
        raise Pbi121ReplacementContractError(
            "Direct insertion into pBI121 is not allowed; use the fixed exact-replacement workflow."
        )
    if (int(replacement_start), int(replacement_end)) != (
        contract["replacement_start"],
        contract["replacement_end"],
    ):
        raise Pbi121ReplacementContractError(
            "pBI121 replacement coordinates are fixed at 4974..7979 (1-based inclusive)."
        )
    return contract


def replace_pbi121_reporter_cassette(
    source_sequence: str,
    design_sequence: str,
    *,
    accession_version: str,
    mode: str = "replacement",
    replacement_start: int = 4974,
    replacement_end: int = 7979,
) -> str:
    contract = validate_pbi121_operation(
        source_sequence=source_sequence,
        accession_version=accession_version,
        mode=mode,
        replacement_start=replacement_start,
        replacement_end=replacement_end,
    )
    design = str(design_sequence or "").upper()
    if not design:
        raise Pbi121ReplacementContractError("The replacement design sequence is empty.")
    start, end = replacement_span_zero_based_half_open()
    result = str(source_sequence).upper()[:start] + design + str(source_sequence).upper()[end:]
    expected_length = contract["full_sequence_length"] - contract["replacement_length"] + len(design)
    if len(result) != expected_length:
        raise Pbi121ReplacementContractError("The pBI121 replacement output length does not match the contract formula.")
    return result
