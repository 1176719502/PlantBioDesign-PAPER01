from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from services.documentation_review_label_helper import (
    NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL,
    format_review_next_label,
)
from services.placeholder_review_value import has_recorded_review_value, is_placeholder_review_value
from services.project_catalog_reference_output_formatter import build_linked_catalog_reference_output


DOCUMENTATION_BOUNDARY_NOTE = (
    "Documentation-only Component Library asset readback. This presenter summarizes existing "
    "source/provenance and record review context for traceability only; it does not recommend, validate, optimize, "
    "predict outcomes, or judge wet-lab use."
)

NO_SOURCE_PROVENANCE_IDENTITY = "No source/provenance identity recorded"
NO_SOURCE_REFERENCE_CONTEXT = "No source/reference context recorded"
RECORDED_REVIEW_ACTION = (
    "review recorded source/provenance and record review status in the existing review surface "
    "before documentation reuse."
)

ASSET_READBACK_COLUMNS = [
    "Asset label",
    "Asset type",
    "Domain/chassis context",
    "Source/provenance identity",
    "Record review status",
    NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL,
    "Documentation context note",
    "Type-specific notes",
    "Documentation boundary note",
]

GENERIC_ASSET_TYPE_LABELS = {
    "promoter": "promoter",
    "plant_promoter_profile": "promoter",
    "terminator": "terminator",
    "cds_target": "CDS / gene",
    "cds_gene": "CDS / gene",
    "cds": "CDS / gene",
    "coding sequence": "CDS / gene",
    "gene": "CDS / gene",
    "marker_metadata": "marker / reporter",
    "reporter": "marker / reporter",
    "plasmid_backbone": "vector backbone",
    "vector_backbone": "vector backbone",
    "rbs_5utr": "UTR / RBS / Kozak",
    "5' utr": "UTR / RBS / Kozak",
    "rbs": "UTR / RBS / Kozak",
    "kozak": "UTR / RBS / Kozak",
    "literature_source_note": "source / reference",
    "source_reference": "source / reference",
    "origin_metadata": "source / reference",
    "host_chassis_context_note": "source / reference",
    "evidence_review_metadata": "evidence / record review status",
    "construct_component_reference": "construct component reference",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace("|", ";").split(";")
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    return sorted({_text(item) for item in raw_values if _text(item)}, key=str.casefold)


def _join(values: Iterable[Any], fallback: str = "Not recorded") -> str:
    clean = [_text(value) for value in values if has_recorded_review_value(value)]
    return "; ".join(clean) if clean else fallback


def _needs_source_follow_up(value: Any) -> bool:
    text = _text(value).casefold()
    return is_placeholder_review_value(text) or any(
        marker in text
        for marker in (
            NO_SOURCE_PROVENANCE_IDENTITY.casefold(),
            NO_SOURCE_REFERENCE_CONTEXT.casefold(),
            "source review needed",
            "source status not recorded",
            "source not recorded",
            "no source",
            "identifier not recorded",
            "missing source",
        )
    )


def _needs_review_follow_up(value: Any) -> bool:
    text = _text(value).casefold()
    return is_placeholder_review_value(text) or any(
        marker in text
        for marker in (
            "human review needed",
            "review needed",
            "review metadata gap",
            "metadata gap",
            "not recorded",
            "missing",
        )
    )


def _next_review_action(source_identity: Any, review_metadata: Any) -> str:
    source_gap = _needs_source_follow_up(source_identity)
    review_gap = _needs_review_follow_up(review_metadata)
    if source_gap and review_gap:
        return format_review_next_label(
            "record source/provenance identity and record review status in the existing review surface."
        )
    if source_gap:
        return format_review_next_label("record source/provenance identity in the existing review surface.")
    if review_gap:
        return format_review_next_label("record review status in the existing review surface.")
    return format_review_next_label(RECORDED_REVIEW_ACTION)


def _field_note(row: dict[str, str], note: str) -> dict[str, str]:
    row["Documentation context note"] = note
    row["documentation_context_note"] = note
    return row


def normalize_asset_type_label(asset_type: Any, *, component_category: Any = "") -> str:
    raw = _text(asset_type).casefold()
    category = _text(component_category).casefold()
    if raw in GENERIC_ASSET_TYPE_LABELS:
        return GENERIC_ASSET_TYPE_LABELS[raw]
    if category in GENERIC_ASSET_TYPE_LABELS:
        return GENERIC_ASSET_TYPE_LABELS[category]
    if category:
        return category
    return _text(asset_type, "component asset")


def _local_design_asset_row(record: dict[str, Any]) -> dict[str, str]:
    aliases = _text_list(record.get("aliases"))
    tags = _text_list(record.get("tags"))
    sequence_state = "sequence metadata recorded" if record.get("sequence_available") else "sequence metadata not recorded"
    type_notes = _join(
        [
            _text(record.get("short_description")),
            f"aliases: {', '.join(aliases)}" if aliases else "",
            f"tags: {', '.join(tags)}" if tags else "",
            sequence_state,
        ]
    )
    source_identity = _join(
        [
            "Local Design Asset Catalog",
            _text(record.get("asset_id")),
            _text(record.get("provenance_status")),
            _text(record.get("version_context")),
        ]
    )
    review_metadata = _join(
        [
            _text(record.get("review_status")),
            _text(record.get("human_review_notes")),
        ]
    )
    source_identity_display = (
        source_identity if source_identity != "Local Design Asset Catalog" else NO_SOURCE_PROVENANCE_IDENTITY
    )
    row = {
        "Asset label": _text(record.get("display_name") or record.get("asset_id"), "Unnamed Component Library asset"),
        "Asset type": normalize_asset_type_label(record.get("asset_type")),
        "Domain/chassis context": _text(record.get("organism_or_source_context"), "Not recorded"),
        "Source/provenance identity": source_identity_display,
        "Record review status": review_metadata,
        NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL: _next_review_action(source_identity_display, review_metadata),
        "Type-specific notes": type_notes,
        "Documentation boundary note": _text(record.get("documentation_boundary_note"), DOCUMENTATION_BOUNDARY_NOTE),
    }
    return _field_note(
        row,
        "Linked catalog documentation context is not recorded for this Local Design Asset Catalog row.",
    )


def _linked_catalog_documentation_context_note(output: dict[str, Any]) -> str:
    return (
        f"Documentation context: {_text(output.get('project_documentation_context'), 'Documentation context not provided')}; "
        f"origin: {_text(output.get('reference_origin'), 'Project documentation reference')}; "
        f"role: {_text(output.get('linkage_role'), 'Not recorded')}; "
        f"link state: {_text(output.get('linked_persisted_status'), 'Linked catalog reference')}. "
        "Source/provenance identity remains "
        f"{_text(output.get('catalog_label'), 'Source not recorded')} / "
        f"{_text(output.get('record_identifier'), 'identifier not recorded')}."
    )


def _linked_catalog_asset_row(link: dict[str, Any]) -> dict[str, str]:
    output = build_linked_catalog_reference_output(link)
    snapshot = output.get("asset_snapshot") if isinstance(output.get("asset_snapshot"), dict) else {}
    source = output.get("source_context_snapshot") if isinstance(output.get("source_context_snapshot"), dict) else {}
    domain_context = _join(
        [
            snapshot.get("species"),
            snapshot.get("clade"),
            source.get("host_context"),
            source.get("chassis_context"),
            source.get("organism_or_source_context"),
        ]
    )
    tissue_contexts = _text_list(snapshot.get("tissue_contexts"))
    motif_labels = _text_list(snapshot.get("motif_labels"))
    type_notes = _join(
        [
            f"linkage role: {output.get('linkage_role')}" if _text(output.get("linkage_role")) != "Not recorded" else "",
            f"reference origin: {output.get('reference_origin')}",
            f"project context: {output.get('project_documentation_context')}",
            f"tissue/context notes: {', '.join(tissue_contexts)}" if tissue_contexts else "",
            f"motif notes: {', '.join(motif_labels)}" if motif_labels else "",
            _text(snapshot.get("limitation_note")),
            (
                "Plant Promoter Catalog source identity preserved for this promoter asset reference."
                if output.get("catalog_label") == "Plant Promoter Catalog"
                else ""
            ),
        ]
    )
    source_identity = _join(
        [
            output.get("catalog_label"),
            output.get("record_identifier"),
            output.get("source_label"),
            output.get("snapshot_state"),
        ]
    )
    review_metadata = _join(
        [
            output.get("documentation_status"),
            output.get("review_needed_context"),
            output.get("metadata_gap_context"),
        ]
    )
    row = {
        "Asset label": _text(output.get("asset_display_name"), "Unnamed linked Component Library asset"),
        "Asset type": normalize_asset_type_label(output.get("asset_type")),
        "Domain/chassis context": domain_context,
        "Source/provenance identity": source_identity,
        "Record review status": review_metadata,
        NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL: _next_review_action(source_identity, review_metadata),
        "Type-specific notes": type_notes,
        "Documentation boundary note": DOCUMENTATION_BOUNDARY_NOTE,
    }
    return _field_note(row, _linked_catalog_documentation_context_note(output))


def _construct_component_row(row: dict[str, Any]) -> dict[str, str]:
    source_identity = _text(row.get("component_reference_label"))
    if is_placeholder_review_value(source_identity):
        source_identity = NO_SOURCE_REFERENCE_CONTEXT
    review_metadata = _join(
        [
            row.get("review_metadata_status"),
            row.get("review_note"),
        ]
    )
    output = {
        "Asset label": _text(row.get("component_label"), "Unnamed construct component"),
        "Asset type": "construct component reference",
        "Domain/chassis context": _text(row.get("cassette_label"), "Construct cassette context not recorded"),
        "Source/provenance identity": source_identity,
        "Record review status": review_metadata,
        NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL: _next_review_action(source_identity, review_metadata),
        "Type-specific notes": _join(
            [
                f"component category: {normalize_asset_type_label(row.get('component_category'))}",
                row.get("sequence_availability_status"),
            ]
        ),
        "Documentation boundary note": DOCUMENTATION_BOUNDARY_NOTE,
    }
    return _field_note(
        output,
        "Linked catalog documentation context is not recorded for this construct component row.",
    )


def build_component_library_asset_readback_rows(
    *,
    local_design_assets: Iterable[dict[str, Any]] | None = None,
    linked_catalog_assets: Iterable[dict[str, Any]] | None = None,
    construct_component_rows: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Normalize current asset-like records into generic documentation-only readback rows."""
    rows: list[dict[str, str]] = []
    rows.extend(_local_design_asset_row(dict(record)) for record in local_design_assets or [])
    rows.extend(_linked_catalog_asset_row(dict(link)) for link in linked_catalog_assets or [])
    rows.extend(_construct_component_row(dict(row)) for row in construct_component_rows or [])
    return rows


def summarize_asset_readback(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    row_list = [dict(row) for row in rows]
    type_counts = Counter(_text(row.get("Asset type"), "component asset") for row in row_list)
    source_identity_count = sum(
        1
        for row in row_list
        if has_recorded_review_value(row.get("Source/provenance identity"))
        and _text(row.get("Source/provenance identity"))
        not in (NO_SOURCE_PROVENANCE_IDENTITY, NO_SOURCE_REFERENCE_CONTEXT)
    )
    review_metadata_count = sum(
        1
        for row in row_list
        if has_recorded_review_value(row.get("Record review status") or row.get("Evidence/review metadata"))
    )
    action_count = sum(
        1
        for row in row_list
        if _text(row.get(NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL))
        and _text(row.get(NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL)) != format_review_next_label(RECORDED_REVIEW_ACTION)
    )
    boundary_note_count = sum(
        1
        for row in row_list
        if "documentation-only" in _text(row.get("Documentation boundary note")).casefold()
    )
    return {
        "total_asset_rows": len(row_list),
        "asset_type_counts": dict(sorted(type_counts.items(), key=lambda item: item[0].casefold())),
        "asset_type_count": len(type_counts),
        "rows_with_source_provenance_identity": source_identity_count,
        "rows_with_evidence_review_metadata": review_metadata_count,
        "rows_with_next_documentation_review_action": action_count,
        "rows_with_documentation_boundary_note": boundary_note_count,
        "documentation_boundary_note": DOCUMENTATION_BOUNDARY_NOTE,
    }


def build_component_library_asset_readback_presenter(
    *,
    local_design_assets: Iterable[dict[str, Any]] | None = None,
    linked_catalog_assets: Iterable[dict[str, Any]] | None = None,
    construct_component_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = build_component_library_asset_readback_rows(
        local_design_assets=local_design_assets,
        linked_catalog_assets=linked_catalog_assets,
        construct_component_rows=construct_component_rows,
    )
    return {
        "title": "Generic Component Library asset readback",
        "summary": summarize_asset_readback(rows),
        "rows": rows,
        "columns": list(ASSET_READBACK_COLUMNS),
        "empty_state": (
            "No Component Library source/provenance or record review status is available for generic readback. Review next: clear active "
            "filters or use existing review surfaces for saved component asset rows, linked catalog references, "
            "or construct component rows when source/provenance context is needed."
        ),
        "documentation_boundary_note": DOCUMENTATION_BOUNDARY_NOTE,
        "source_identity_note": (
            "Stored route, source, provenance, package, and saved-record identifiers are preserved; "
            "the Review next column points to missing source/provenance or record review status in existing "
            "review surfaces without changing records."
        ),
    }
