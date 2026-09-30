from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SLOT_COVERAGE_MATRIX_SCHEMA_VERSION = "plant_review_slot_coverage_matrix.v2.7.r86"
SLOT_COVERAGE_MATRIX_BATCH = "v2.7-r86"

SLOT_COVERAGE_BOUNDARY_NOTE = (
    "Documentation-only slot coverage matrix for Plant review. It summarizes existing evidence, component, "
    "provenance, gap, and traceability records for manual review without selecting components, exporting files, "
    "generating sequences or procedures, ranking biology, predicting outcomes, or judging downstream use."
)

GAP_CATEGORIES = {"required_slot_gap", "evidence_gap", "component_gap", "provenance_gap", "duplicate_or_alias_review"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _unique_texts(values: Sequence[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    return unique


def _label_from_slot_id(slot_id: str) -> str:
    clean = slot_id.replace("_", " ").strip()
    return clean.title() if clean else "Unrecorded slot"


def _source_chain(source_payload: Mapping[str, Any] | None) -> tuple[dict[str, Any], str, list[str]]:
    if not isinstance(source_payload, Mapping):
        return {}, "malformed", ["slot coverage input warning: source payload is missing or malformed"]
    payload = dict(source_payload)
    chain = _mapping(payload.get("chain_result"))
    if chain:
        return chain, "workspace_workflow", []
    if "chain_schema_version" in payload or "route_draft" in payload:
        return payload, "chain_result", []
    return {}, "malformed", ["slot coverage input warning: no workflow chain result was found"]


def _ensure_row(rows: dict[str, dict[str, Any]], slot_id: str) -> dict[str, Any]:
    clean_id = _text(slot_id) or "unassigned_slot"
    row = rows.setdefault(
        clean_id,
        {
            "slot_id": clean_id,
            "slot_label": _label_from_slot_id(clean_id),
            "required_or_optional": "optional_or_review_context",
            "evidence_ids": [],
            "component_ids": [],
            "evidence_count": 0,
            "component_count": 0,
            "evidence_gap": False,
            "component_gap": False,
            "provenance_gap": False,
            "duplicate_or_alias_review": False,
            "manual_review_required": False,
            "gap_categories": [],
            "traceability_ids": [],
        },
    )
    return row


def _mark_required(row: dict[str, Any]) -> None:
    row["required_or_optional"] = "required"


def _extend_ids(row: dict[str, Any], key: str, values: Sequence[Any]) -> None:
    row[key] = _unique_texts([*row.get(key, []), *values])


def _candidate_evidence_ids(slot_match: Mapping[str, Any]) -> list[str]:
    ids: list[Any] = []
    for candidate in _list(slot_match.get("candidate_evidence")):
        candidate_data = _mapping(candidate)
        ids.append(candidate_data.get("record_id") or candidate_data.get("evidence_id") or candidate_data.get("source_id"))
    ids.extend(_list(slot_match.get("evidence_ids")))
    return _unique_texts(ids)


def _candidate_component_ids(slot_match: Mapping[str, Any]) -> list[str]:
    ids: list[Any] = []
    for candidate in _list(slot_match.get("candidate_components")):
        candidate_data = _mapping(candidate)
        ids.append(candidate_data.get("component_id") or candidate_data.get("asset_id") or candidate_data.get("record_id"))
    ids.extend(_list(slot_match.get("component_ids")))
    return _unique_texts(ids)


def _candidate_duplicate_review(slot_match: Mapping[str, Any]) -> bool:
    if bool(slot_match.get("duplicate_or_alias_flag")):
        return True
    return any(bool(_mapping(candidate).get("duplicate_or_alias_flag")) for candidate in _list(slot_match.get("candidate_components")))


def _candidate_provenance_gap(slot_match: Mapping[str, Any]) -> bool:
    status = _text(slot_match.get("provenance_status")).casefold()
    if "missing" in status or "gap" in status:
        return True
    completeness = _mapping(slot_match.get("source_completeness"))
    missing_fields = _list(completeness.get("missing_fields") or completeness.get("missing_metadata"))
    if any(_text(field).casefold() in {"provenance", "source", "doi_or_pmid", "year"} for field in missing_fields):
        return True
    return any(
        _candidate_provenance_gap(_mapping(candidate))
        for candidate in _list(slot_match.get("candidate_components"))
        if isinstance(candidate, Mapping)
    )


def _route_slots(chain: Mapping[str, Any], rows: dict[str, dict[str, Any]]) -> None:
    route = _mapping(chain.get("route_draft"))
    required_slots: set[str] = set()
    for card in _list(route.get("module_card_summaries")):
        required_slots.update(_text(slot) for slot in _list(_mapping(card).get("required_slots")) if _text(slot))
    for slot in _list(route.get("required_slots") or route.get("slots")):
        slot_data = _mapping(slot)
        slot_id = _text(slot_data.get("slot_name") or slot_data.get("slot_id"))
        if not slot_id:
            continue
        row = _ensure_row(rows, slot_id)
        row["slot_label"] = _text(slot_data.get("slot_label")) or row["slot_label"]
        if slot_id in required_slots or _text(slot_data.get("status")) in {"missing", "provided"}:
            _mark_required(row)
        if bool(slot_data.get("manual_review_required")):
            row["manual_review_required"] = True
        if _text(slot_data.get("status")) == "missing":
            row["component_gap"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "required_slot_gap"])


def _evidence_slots(chain: Mapping[str, Any], rows: dict[str, dict[str, Any]]) -> None:
    result = _mapping(chain.get("evidence_slot_match_result"))
    for slot in _list(result.get("slot_matches")):
        slot_data = _mapping(slot)
        slot_id = _text(slot_data.get("slot_id"))
        if not slot_id:
            continue
        row = _ensure_row(rows, slot_id)
        row["slot_label"] = _text(slot_data.get("slot_label")) or row["slot_label"]
        evidence_ids = _candidate_evidence_ids(slot_data)
        _extend_ids(row, "evidence_ids", evidence_ids)
        if bool(slot_data.get("manual_review_required")):
            row["manual_review_required"] = True
        if _text(slot_data.get("missing_evidence_reason")) or not evidence_ids:
            row["evidence_gap"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "evidence_gap"])
        if _candidate_provenance_gap(slot_data):
            row["provenance_gap"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "provenance_gap"])


def _component_slots(chain: Mapping[str, Any], rows: dict[str, dict[str, Any]]) -> None:
    result = _mapping(chain.get("component_candidate_match_result"))
    for slot in _list(result.get("slot_matches")):
        slot_data = _mapping(slot)
        slot_id = _text(slot_data.get("slot_id"))
        if not slot_id:
            continue
        row = _ensure_row(rows, slot_id)
        row["slot_label"] = _text(slot_data.get("slot_label")) or row["slot_label"]
        component_ids = _candidate_component_ids(slot_data)
        _extend_ids(row, "component_ids", component_ids)
        if bool(slot_data.get("manual_review_required")):
            row["manual_review_required"] = True
        if _text(slot_data.get("missing_component_reason")) or not component_ids:
            row["component_gap"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "component_gap"])
        if _candidate_duplicate_review(slot_data):
            row["duplicate_or_alias_review"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "duplicate_or_alias_review"])
        if _candidate_provenance_gap(slot_data):
            row["provenance_gap"] = True
            row["manual_review_required"] = True
            row["gap_categories"] = _unique_texts([*row["gap_categories"], "provenance_gap"])


def _queue_slots(chain: Mapping[str, Any], rows: dict[str, dict[str, Any]]) -> None:
    queue_result = _mapping(chain.get("gap_manual_review_queue_result"))
    for item in _list(queue_result.get("review_items") or queue_result.get("queue")):
        item_data = _mapping(item)
        slot_id = _text(item_data.get("slot_id"))
        if not slot_id:
            continue
        row = _ensure_row(rows, slot_id)
        row["slot_label"] = _text(item_data.get("slot_label")) or row["slot_label"]
        category = _text(item_data.get("category")) or "manual_review"
        if category == "required_slot_gap":
            _mark_required(row)
            row["component_gap"] = True
        elif category == "evidence_gap":
            row["evidence_gap"] = True
        elif category == "component_gap":
            row["component_gap"] = True
        elif category == "provenance_gap":
            row["provenance_gap"] = True
        elif category == "duplicate_or_alias_review":
            row["duplicate_or_alias_review"] = True
        if category in GAP_CATEGORIES:
            row["gap_categories"] = _unique_texts([*row["gap_categories"], category])
        _extend_ids(row, "evidence_ids", _list(item_data.get("evidence_ids")))
        _extend_ids(row, "component_ids", _list(item_data.get("component_ids")))
        row["manual_review_required"] = True


def _finalize_rows(rows: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    final_rows: list[dict[str, Any]] = []
    for row in sorted(rows.values(), key=lambda item: (item["required_or_optional"] != "required", item["slot_id"])):
        evidence_ids = _unique_texts(row.get("evidence_ids", []))
        component_ids = _unique_texts(row.get("component_ids", []))
        traceability_ids = _unique_texts([*evidence_ids, *component_ids, *row.get("traceability_ids", [])])
        final_rows.append(
            {
                "slot_id": row["slot_id"],
                "slot_label": row["slot_label"],
                "required_or_optional": row["required_or_optional"],
                "evidence_count": len(evidence_ids),
                "component_count": len(component_ids),
                "evidence_gap": bool(row["evidence_gap"]),
                "component_gap": bool(row["component_gap"]),
                "provenance_gap": bool(row["provenance_gap"]),
                "duplicate_or_alias_review": bool(row["duplicate_or_alias_review"]),
                "manual_review_required": bool(row["manual_review_required"]),
                "evidence_traceability_ids": evidence_ids,
                "component_traceability_ids": component_ids,
                "traceability_ids": traceability_ids,
                "gap_categories": _unique_texts(row.get("gap_categories", [])),
            }
        )
    return final_rows


def _summary(rows: Sequence[Mapping[str, Any]], warnings: Sequence[str]) -> dict[str, Any]:
    return {
        "slot_count": len(rows),
        "required_slot_count": sum(1 for row in rows if row.get("required_or_optional") == "required"),
        "evidence_gap_count": sum(1 for row in rows if row.get("evidence_gap")),
        "component_gap_count": sum(1 for row in rows if row.get("component_gap")),
        "provenance_gap_count": sum(1 for row in rows if row.get("provenance_gap")),
        "duplicate_or_alias_review_count": sum(1 for row in rows if row.get("duplicate_or_alias_review")),
        "manual_review_slot_count": sum(1 for row in rows if row.get("manual_review_required")),
        "warning_count": len(warnings),
    }


def build_plant_review_slot_coverage_matrix(
    source_payload: Mapping[str, Any] | None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic slot coverage matrix from an R83 workflow result or R76 chain result."""
    _ = _mapping(options)
    chain, source_kind, warnings = _source_chain(source_payload)
    rows_by_slot: dict[str, dict[str, Any]] = {}
    if chain:
        _route_slots(chain, rows_by_slot)
        _evidence_slots(chain, rows_by_slot)
        _component_slots(chain, rows_by_slot)
        _queue_slots(chain, rows_by_slot)
    rows = _finalize_rows(rows_by_slot)
    manual_review_required = bool(warnings) or any(row["manual_review_required"] for row in rows)
    matrix_status = "manual_review_required" if manual_review_required else "review_ready"
    return _plain_value(
        {
            "slot_coverage_matrix_schema_version": SLOT_COVERAGE_MATRIX_SCHEMA_VERSION,
            "slot_coverage_matrix_batch": SLOT_COVERAGE_MATRIX_BATCH,
            "matrix_status": matrix_status,
            "source_kind": source_kind,
            "rows": rows,
            "summary": _summary(rows, warnings),
            "manual_review_required": manual_review_required,
            "warnings": _unique_texts(warnings),
            "boundary_note": SLOT_COVERAGE_BOUNDARY_NOTE,
            "traceability": {
                "source_schema_version": _text(chain.get("chain_schema_version")) if chain else "",
                "source_runner_version": _text(chain.get("chain_runner_version")) if chain else "",
                "source_payload_kind": source_kind,
            },
        }
    )
