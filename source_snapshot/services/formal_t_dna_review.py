"""Explicit LB/RB review records for the formal plant binary-vector workflow."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.pbi121_replacement_contract import is_pbi121_sequence
from core.pcambia1300_exact_insertion_contract import (
    Pcambia1300ExactInsertionContractError,
    is_pcambia1300_record,
    validate_pcambia1300_operation,
)
from services.vector_asset_admission import validate_vector_operation


class TDnaReviewError(ValueError):
    pass


def backbone_sequence_signature(backbone: dict[str, Any]) -> str:
    sequence = str(backbone.get("normalized_sequence") or "").upper()
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest() if sequence else ""


def imported_feature_rows(backbone: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in list(backbone.get("imported_feature_records") or []):
        if not isinstance(feature, dict) or bool(feature.get("unsupported_location")):
            continue
        start, end = int(feature.get("start") or 0), int(feature.get("end") or 0)
        if start < 0 or end <= start:
            continue
        rows.append({
            "feature_id": str(feature.get("feature_id") or ""),
            "name": str(feature.get("name") or feature.get("label") or feature.get("type") or ""),
            "type": str(feature.get("type") or "misc_feature"),
            "start": start + 1,
            "end": end,
            "strand": int(feature.get("strand") or 1),
            "qualifiers": dict(feature.get("qualifiers") or {}),
            "location_text": str(feature.get("location_text") or ""),
        })
    return rows


def imported_feature_confirmation(feature: dict[str, Any], *, role: str) -> dict[str, Any]:
    return {"role": role, "confirmation_method": "imported_annotation", "feature_id": str(feature.get("feature_id") or ""), "original_name": str(feature.get("name") or ""), "feature_type": str(feature.get("type") or ""), "start": int(feature.get("start") or 0) + 1, "end": int(feature.get("end") or 0), "strand": int(feature.get("strand") or 1), "qualifiers": dict(feature.get("qualifiers") or {}), "location_text": str(feature.get("location_text") or "")}


def manual_border_confirmation(*, role: str, start: int, end: int, direction_note: str, backbone_length: int) -> dict[str, Any]:
    if start < 1 or end < start or end > backbone_length:
        raise TDnaReviewError(f"{role} manual coordinates are outside the imported backbone.")
    if not str(direction_note or "").strip():
        raise TDnaReviewError(f"{role} manual confirmation requires a direction note.")
    return {"role": role, "confirmation_method": "manual_coordinates", "feature_id": "", "original_name": "", "feature_type": "", "start": start, "end": end, "strand": 0, "qualifiers": {}, "location_text": "", "direction_note": str(direction_note).strip()}


def build_t_dna_confirmation(backbone: dict[str, Any], *, lb: dict[str, Any], rb: dict[str, Any], direction: str) -> dict[str, Any]:
    length, topology = len(str(backbone.get("normalized_sequence") or "")), str(backbone.get("topology") or "").lower()
    if length <= 0 or topology not in {"linear", "circular"}:
        raise TDnaReviewError("An imported backbone sequence and topology are required.")
    if direction not in {"lb_to_rb", "rb_to_lb"}:
        raise TDnaReviewError("Choose the T-DNA direction explicitly.")
    if int(lb["start"]) < 1 or int(lb["end"]) > length or int(rb["start"]) < 1 or int(rb["end"]) > length:
        raise TDnaReviewError("Confirmed border coordinates are outside the imported backbone.")
    if int(lb["start"]) <= int(rb["end"]) and int(rb["start"]) <= int(lb["end"]):
        raise TDnaReviewError("LB and RB cannot overlap.")
    source, target = (lb, rb) if direction == "lb_to_rb" else (rb, lb)
    region_start, region_end = int(source["end"]) + 1, int(target["start"]) - 1
    crosses_origin = region_start > region_end
    if crosses_origin and topology != "circular":
        raise TDnaReviewError("A linear backbone cannot use a T-DNA region that crosses the sequence origin.")
    if region_start == region_end + 1 and not crosses_origin:
        raise TDnaReviewError("The confirmed borders do not leave a T-DNA interval between them.")
    payload = {"status": "confirmed", "confirmation_source": "manual_review", "backbone_sequence_signature": backbone_sequence_signature(backbone), "backbone_length": length, "topology": topology, "direction": direction, "lb": lb, "rb": rb, "region": {"start": region_start, "end": region_end, "crosses_origin": crosses_origin, "coordinate_convention": "1-based-inclusive"}}
    payload["confirmation_signature"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return payload


def confirmation_is_current(backbone: dict[str, Any], confirmation: dict[str, Any]) -> bool:
    return bool(confirmation.get("status") == "confirmed" and confirmation.get("backbone_sequence_signature") == backbone_sequence_signature(backbone) and int(confirmation.get("backbone_length") or 0) == len(str(backbone.get("normalized_sequence") or "")) and str(confirmation.get("topology") or "") == str(backbone.get("topology") or "").lower())


def _in_region(position: int, region: dict[str, Any]) -> bool:
    start, end = int(region["start"]), int(region["end"])
    return start <= position <= end if not bool(region.get("crosses_origin")) else position >= start or position <= end


def validate_t_dna_operation(backbone: dict[str, Any], *, confirmation: dict[str, Any], insertion_settings: dict[str, Any], workflow_id: str = "formal_single_gene") -> dict[str, Any]:
    unified = validate_vector_operation(
        backbone,
        workflow_id=workflow_id,
        insertion_settings=insertion_settings,
    )
    if is_pbi121_sequence(str(backbone.get("normalized_sequence") or "")):
        if unified["allowed"]:
            return unified
        return {
            "status": "dedicated_exact_replacement_required",
            "allowed": False,
            "reason": (
                "pBI121 / AF485783.1 is an exact-replacement source, not a blank backbone. "
                "Use the dedicated Gate 3 workflow; direct insertion and user-defined replacement coordinates are disabled."
            ),
        }
    if is_pcambia1300_record(backbone):
        accession_version = str(
            backbone.get("source_accession_version")
            or backbone.get("original_record_identifier")
            or backbone.get("source_name")
            or ""
        )
        try:
            contract = validate_pcambia1300_operation(
                source_sequence=str(backbone.get("normalized_sequence") or ""),
                accession_version=accession_version,
                circular=str(backbone.get("topology") or "").lower() == "circular",
                mode=str(insertion_settings.get("mode") or ""),
                start_coordinate=int(insertion_settings.get("start_coordinate") or 0),
                end_coordinate=int(insertion_settings.get("end_coordinate") or 0),
                insertion_orientation=str(insertion_settings.get("insertion_orientation") or "forward"),
                workflow_id=workflow_id,
            )
        except Pcambia1300ExactInsertionContractError as exc:
            return {
                "status": "pcambia1300_exact_insertion_blocked",
                "allowed": False,
                "reason": str(exc),
            }
        return {
            "status": "pcambia1300_exact_insertion_applied",
            "allowed": True,
            "reason": "The immutable AF234296.1 exact-insertion contract at 27|28 is active.",
            "contract_version": contract["contract_version"],
            "internal_cut_index": contract["internal_cut_index"],
        }
    return unified
