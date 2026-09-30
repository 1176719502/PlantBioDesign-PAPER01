from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from services.generated_output_boundary import normalize_generated_output_claims, normalize_generated_output_text
from services.expression_construct_review_action_panel_presenter import (
    build_expression_construct_review_action_panel,
)
from services.expression_construct_review_decision_summary_presenter import (
    build_expression_construct_review_decision_summary,
)
from services.placeholder_review_value import clean_review_value, has_recorded_review_value


PACKAGE_TYPE = "Plant Design Review Package"
PROJECT_DIRECTION = "Plant recombinant protein / molecular farming"
REPORT_SCOPE = "Documentation-only pre-experiment design review"
SNAPSHOT_PREFIX = "BDS-PLANT-R310"
CHECKSUM_ALGORITHM = "MD5"
QR_PAYLOAD_PREFIX = "BioDesignStudioPlant|PlantDesignReviewPackage"
QR_DEPENDENCY_NOTE = (
    "Payload-only QR payload preview is used; no QR image is rendered and no new QR dependency is required."
)
IDENTITY_BOUNDARY_NOTES = [
    "QR/MD5 verifies only the report/package snapshot identity.",
    "QR/MD5 does not validate construct readiness.",
    "QR/MD5 does not validate plant lines.",
    "QR/MD5 does not prove biological function.",
    "QR/MD5 does not predict yield.",
    "QR/MD5 does not certify experiment success.",
]
PACKAGE_BOUNDARY_NOTES = [
    "This Plant Design Review Package is a documentation-only skeleton/readback.",
    "It summarizes available project, construct, Component Library, and review-gap context only.",
    "It does not add biological design automation, component selection advice, sequence optimization output, protocol generation, plant-line validation, construct-readiness claims, phenotype guarantees, or yield forecasts.",
]


def _text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return clean_review_value(normalize_generated_output_text(value), fallback)


def _first_recorded(source: Mapping[str, Any], keys: tuple[str, ...], fallback: str = "NOT_AVAILABLE") -> str:
    for key in keys:
        value = source.get(key)
        if has_recorded_review_value(value):
            return _text(value, fallback)
    return fallback


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _timestamp_for_snapshot(generated_at: str | None = None) -> str:
    raw = str(generated_at or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
        compact = re.sub(r"[^0-9]", "", raw)
        if len(compact) >= 14:
            return f"{compact[:8]}-{compact[8:14]}"
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _checksum(data: Mapping[str, Any]) -> str:
    return hashlib.md5(_canonical_json(data).encode("utf-8")).hexdigest()


def _markdown_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return _text(value, fallback).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _section_row(key: str, title: str, readback: str, follow_up: str) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "readback": _text(readback),
        "manual_follow_up": _text(follow_up, "Manual documentation review remains required."),
    }


def _project_direction(project: Mapping[str, Any]) -> str:
    return _first_recorded(
        project,
        ("project_direction", "workflow_direction", "mvp_direction", "application_direction"),
        PROJECT_DIRECTION,
    )


def _target_product(project: Mapping[str, Any], construct_documentation: Mapping[str, Any]) -> str:
    value = _first_recorded(
        project,
        ("target_product", "target_protein", "protein", "project_name", "name"),
        "",
    )
    if value:
        return value
    for row in _rows(construct_documentation.get("linked_gene_rows")):
        value = _first_recorded(row, ("gene_label", "gene_reference", "source_reference"), "")
        if value:
            return value
    return "NOT_AVAILABLE"


def _plant_host_context(project: Mapping[str, Any], host_chassis_context: Mapping[str, Any]) -> str:
    value = _first_recorded(project, ("plant_species", "host", "organism", "organism_source"), "")
    if value:
        return value
    rows = _rows(host_chassis_context.get("rows"))
    for row in rows:
        if _text(row.get("normalized_context_label"), "").casefold() == "plant":
            return _text(row.get("source_value"))
    return "NOT_AVAILABLE"


def _cassette_part_by_role(construct_documentation: Mapping[str, Any], role_terms: tuple[str, ...]) -> str:
    for row in _rows(construct_documentation.get("cassette_part_rows")):
        role = _text(row.get("part_role"), "").casefold()
        label = _text(row.get("part_label"), "")
        reference = _text(row.get("part_reference"), "")
        if any(term in role for term in role_terms):
            parts = [part for part in (label, reference) if part]
            return " / ".join(parts) if parts else "Recorded cassette part context"
    return "NOT_AVAILABLE"


def _cassette_gene_source(construct_documentation: Mapping[str, Any]) -> str:
    for row in _rows(construct_documentation.get("linked_gene_rows")):
        parts = [
            _text(row.get("gene_label"), ""),
            _text(row.get("gene_reference"), ""),
            _text(row.get("source_reference"), ""),
            _text(row.get("provenance_note"), ""),
        ]
        parts = [part for part in parts if part]
        if parts:
            return "; ".join(parts)
    return _cassette_part_by_role(construct_documentation, ("cds", "coding", "gene"))


def _construct_field(construct_documentation: Mapping[str, Any], row_name: str, keys: tuple[str, ...]) -> str:
    for row in _rows(construct_documentation.get(row_name)):
        value = _first_recorded(row, keys, "")
        if value:
            return value
    return "NOT_AVAILABLE"


def _component_source_review(linked_catalog_assets: Mapping[str, Any]) -> str:
    total = int(linked_catalog_assets.get("total_linked_assets") or linked_catalog_assets.get("linked_catalog_asset_count") or 0)
    plant_promoters = int(
        linked_catalog_assets.get("linked_plant_promoter_count")
        or (linked_catalog_assets.get("plant_promoter_reference_summary") or {}).get("linked_promoter_count")
        or 0
    )
    gaps = int(
        linked_catalog_assets.get("missing_source_or_review_metadata_count")
        or (linked_catalog_assets.get("plant_promoter_reference_summary") or {}).get("missing_metadata_count")
        or 0
    )
    return (
        f"{total} linked Component Library/catalog reference(s); "
        f"{plant_promoters} plant promoter reference(s); {gaps} source/provenance review gap(s)."
    )


def _evidence_gap_summary(
    linked_catalog_assets: Mapping[str, Any],
    construct_documentation: Mapping[str, Any],
) -> str:
    metadata_gaps = int(linked_catalog_assets.get("missing_source_or_review_metadata_count") or 0)
    construct_gaps = len(_rows(construct_documentation.get("construct_component_gap_queue")))
    review_gaps = len(_rows(construct_documentation.get("review_gap_rows")))
    return (
        f"{metadata_gaps} linked-source metadata gap(s); "
        f"{construct_gaps} construct component follow-up row(s); {review_gaps} construct review gap row(s)."
    )


def build_plant_design_review_package(
    *,
    project: Mapping[str, Any] | None = None,
    construct_documentation: Mapping[str, Any] | None = None,
    host_chassis_context: Mapping[str, Any] | None = None,
    linked_catalog_assets: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a documentation-only plant review package readback skeleton."""
    project_data = dict(project or {})
    constructs = dict(construct_documentation or {})
    host_context = dict(host_chassis_context or {})
    catalog_assets = dict(linked_catalog_assets or {})
    snapshot_id = f"{SNAPSHOT_PREFIX}-{_timestamp_for_snapshot(generated_at)}"
    documentation_review_summary = build_expression_construct_review_decision_summary(constructs)
    review_action_panel = build_expression_construct_review_action_panel(
        constructs,
        documentation_review_summary,
    )

    project_direction = _project_direction(project_data)
    sections = [
        _section_row("project_direction", "Project direction", project_direction, "Confirm the recorded plant project direction with the human reviewer."),
        _section_row("target_product", "Target product / protein", _target_product(project_data, constructs), "Record target product/protein source context if missing."),
        _section_row("plant_species", "Plant species / host context", _plant_host_context(project_data, host_context), "Confirm plant species/host context from project notes or source records."),
        _section_row("target_tissue", "Target tissue / organ / expression compartment", _first_recorded(project_data, ("target_tissue", "target_organ", "expression_compartment", "tissue_context")), "Record tissue, organ, or compartment context when relevant."),
        _section_row("expression_mode", "Expression mode", _first_recorded(project_data, ("expression_mode", "expression_strategy", "expression_system")), "Record whether expression-mode context is transient, stable, seed-specific, tissue-context, or not yet recorded."),
        _section_row("gene_cds_source", "Gene / CDS source provenance", _cassette_gene_source(constructs), "Review source/provenance notes for gene or CDS records."),
        _section_row("plant_promoter", "Plant promoter context", _construct_field(constructs, "cassette_rows", ("promoter_label", "source_reference", "provenance_note")) if _construct_field(constructs, "cassette_rows", ("promoter_label", "source_reference", "provenance_note")) != "NOT_AVAILABLE" else _cassette_part_by_role(constructs, ("promoter",)), "Review Plant Promoter Catalog or Component Library source/provenance context."),
        _section_row("utr_kozak", "5' UTR / Kozak-like context if applicable", _cassette_part_by_role(constructs, ("5' utr", "utr", "kozak")), "Record 5' UTR or Kozak-like context only when applicable."),
        _section_row("signal_transit_targeting", "Signal peptide / transit peptide / subcellular targeting if applicable", _cassette_part_by_role(constructs, ("signal", "transit", "targeting", "subcellular")), "Record signal peptide, transit peptide, or subcellular targeting notes only when applicable."),
        _section_row("terminator", "Terminator", _construct_field(constructs, "cassette_rows", ("terminator_label", "source_reference", "provenance_note")) if _construct_field(constructs, "cassette_rows", ("terminator_label", "source_reference", "provenance_note")) != "NOT_AVAILABLE" else _cassette_part_by_role(constructs, ("terminator",)), "Review terminator source/provenance context."),
        _section_row("selectable_marker_reporter", "Selectable marker / reporter", _cassette_part_by_role(constructs, ("marker", "reporter")), "Record marker/reporter documentation context if used."),
        _section_row("vector_backbone", "Vector / backbone context", _first_recorded(project_data, ("vector", "backbone", "vector_backbone")) if _first_recorded(project_data, ("vector", "backbone", "vector_backbone")) != "NOT_AVAILABLE" else _construct_field(constructs, "construct_profile_rows", ("construct_label", "source_reference", "provenance_note")), "Review vector/backbone source context in existing records."),
        _section_row("transformation_context", "Transformation context as documentation-only context", _first_recorded(project_data, ("transformation_context", "transformation_method", "delivery_context")), "Record transformation context only as documentation context; no protocol is generated."),
        _section_row("component_source_review", "Component source / provenance review", _component_source_review(catalog_assets), "Resolve missing source/provenance fields in existing review surfaces."),
        _section_row("evidence_gaps", "Evidence / provenance gaps", _evidence_gap_summary(catalog_assets, constructs), "Use manual review queues to resolve evidence/provenance gaps."),
        _section_row("manual_follow_up", "Manual follow-up", _first_recorded(project_data, ("manual_follow_up", "review_notes", "notes")), "Document unresolved review questions before handoff."),
        _section_row("report_handoff_notes", "Report handoff notes", _first_recorded(project_data, ("report_handoff_notes", "handoff_notes", "documentation_handoff_notes")), "Use this section for review handoff notes only."),
    ]

    identity_source = {
        "package_type": PACKAGE_TYPE,
        "project_direction": project_direction,
        "report_scope": REPORT_SCOPE,
        "snapshot_id": snapshot_id,
        "section_rows": sections,
        "boundary_notes": IDENTITY_BOUNDARY_NOTES,
    }
    checksum = _checksum(identity_source)
    qr_payload = f"{QR_PAYLOAD_PREFIX}|snapshot={snapshot_id}|md5={checksum}"
    package = {
        "title": PACKAGE_TYPE,
        "status": "SKELETON_READBACK",
        "subtitle": "Documentation-only plant review package skeleton/readback.",
        "documentation_review_summary": documentation_review_summary,
        "review_action_panel": review_action_panel,
        "identity": {
            "section_title": "Report Identity / Verification",
            "package_type": PACKAGE_TYPE,
            "project_direction": project_direction,
            "report_scope": REPORT_SCOPE,
            "snapshot_id": snapshot_id,
            "checksum_algorithm": CHECKSUM_ALGORITHM,
            "md5_checksum": checksum,
            "qr_payload": qr_payload,
            "qr_payload_status": "PAYLOAD_ONLY",
            "qr_dependency_note": QR_DEPENDENCY_NOTE,
            "boundary_notes": IDENTITY_BOUNDARY_NOTES,
        },
        "sections": sections,
        "summary": {
            "section_count": len(sections),
            "not_available_count": sum(1 for section in sections if section["readback"] == "NOT_AVAILABLE"),
            "manual_follow_up_count": sum(1 for section in sections if section["manual_follow_up"] != "NOT_AVAILABLE"),
        },
        "boundary_notes": PACKAGE_BOUNDARY_NOTES,
    }
    package = normalize_generated_output_claims(package)
    package["markdown"] = format_plant_design_review_package_markdown(package)
    return package


def format_plant_design_review_package_markdown(package: Mapping[str, Any]) -> str:
    identity = dict(package.get("identity") or {})
    documentation_review_summary = dict(package.get("documentation_review_summary") or {})
    review_action_panel = dict(package.get("review_action_panel") or {})
    sections = _rows(package.get("sections"))
    lines = [
        "## Plant Design Review Package",
        f"- Status: {_markdown_value(package.get('status'))}",
        f"- Scope: {_markdown_value(package.get('subtitle'))}",
        "",
        "### Report Identity / Verification",
        f"- Package type: {_markdown_value(identity.get('package_type'))}",
        f"- Project direction: {_markdown_value(identity.get('project_direction'))}",
        f"- Report scope: {_markdown_value(identity.get('report_scope'))}",
        f"- Snapshot ID: {_markdown_value(identity.get('snapshot_id'))}",
        f"- MD5 checksum: {_markdown_value(identity.get('md5_checksum'))}",
        f"- QR payload: {_markdown_value(identity.get('qr_payload'))}",
        f"- QR payload status: {_markdown_value(identity.get('qr_payload_status'))}",
        f"- QR dependency note: {_markdown_value(identity.get('qr_dependency_note'))}",
    ]
    for note in identity.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if documentation_review_summary:
        lines += [
            "",
            "### Documentation review summary",
            f"- Review status: {_markdown_value(documentation_review_summary.get('review_summary_status'))}",
            f"- Documented slots: {_markdown_value(documentation_review_summary.get('documented_slots_count'))}",
            f"- Missing slots: {_markdown_value(documentation_review_summary.get('missing_slots_count'))}",
            f"- Manual follow-up: {_markdown_value(documentation_review_summary.get('manual_follow_up_count'))}",
            f"- Source/provenance coverage: {_markdown_value(documentation_review_summary.get('source_provenance_coverage_count'))}",
            f"- Coverage label: {_markdown_value(documentation_review_summary.get('source_provenance_coverage_label'))}",
            f"- Boundary notes: {_markdown_value(documentation_review_summary.get('review_summary_note'))}",
        ]
        for note in documentation_review_summary.get("boundary_notes") or []:
            lines.append(f"- {note}")
        for warning in documentation_review_summary.get("warnings") or []:
            lines.append(f"- {warning}")
    if review_action_panel:
        lines += [
            "",
            "### Review action panel",
            f"- Status: {_markdown_value(review_action_panel.get('status'))}",
            f"- Review status: {_markdown_value(review_action_panel.get('review_summary_status'))}",
            f"- Note: {_markdown_value(review_action_panel.get('panel_note'))}",
            "| Action row | Status | Count | Review action | Source | Boundary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in _rows(review_action_panel.get("rows")):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_value(row.get("label")),
                        _markdown_value(row.get("status")),
                        _markdown_value(row.get("count")),
                        _markdown_value(row.get("review_action")),
                        _markdown_value(row.get("source")),
                        _markdown_value(row.get("boundary_note")),
                    ]
                )
                + " |"
            )
        for note in review_action_panel.get("boundary_notes") or []:
            lines.append(f"- {note}")
    lines += [
        "",
        "### Plant review readback sections",
        "| Section | Readback | Manual follow-up |",
        "| --- | --- | --- |",
    ]
    for section in sections:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_value(section.get("title")),
                    _markdown_value(section.get("readback")),
                    _markdown_value(section.get("manual_follow_up")),
                ]
            )
            + " |"
        )
    lines += ["", "### Package boundary"]
    for note in package.get("boundary_notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines)
