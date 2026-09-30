from __future__ import annotations

import json
import re
from typing import Any

import streamlit as st

from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.catalog_asset_snapshot_builder import catalog_asset_snapshot_has_content
from services.host_chassis_context_presenter import build_host_chassis_context_summary
from services.project_documentation_package_exporter import (
    CSV_DEFERRED_NOTE,
    build_project_documentation_export_package,
    build_package_record_counts,
)
from services.project_documentation_package_importer import (
    build_manifest_review_summary,
    build_import_dry_run,
    import_package_create_as_new,
    validate_project_documentation_package,
)
from services.project_asset_linkage_service import summarize_project_asset_links
from services.expression_wizard_catalog_picker_presenter import build_expression_wizard_catalog_traceability_summary
from services.plant_promoter_catalog_workspace_presenter import summarize_linked_plant_promoter_references
from services.project_catalog_reference_output_formatter import has_staged_basket_only_markers

_MANIFEST_FIELDS = {
    "package_format",
    "package_schema_version",
    "exported_at",
    "exported_by_app",
    "source_commit_or_tag",
    "export_scope",
    "record_counts",
    "included_sections",
    "compatibility_notes",
    "documentation_boundary",
    "limitations",
}
_PACKAGE_METADATA_FIELDS = {
    "package_kind",
    "package_version",
    "package_schema_version",
    "exported_at",
    "documentation_only_boundary",
    "included_sections",
    "counts",
}
_TOP_LEVEL_FIELDS = {
    "manifest",
    "package_metadata",
    "project_metadata",
    "project_construct_links",
    "project_catalog_asset_links",
    "construct_profiles",
    "expression_cassettes",
    "cassette_parts",
    "linked_genes",
    "linked_pathway_steps",
    "review_gaps",
    "report_references",
    "integrity_summary",
    "documentation_only_boundary",
    "known_limitations",
}
_PROJECT_METADATA_FIELDS = {
    "project_id",
    "project_name",
    "target_product",
    "host",
    "status",
    "description",
    "created_at",
    "updated_at",
    "metadata_source_note",
}
_SECTION_FIELD_RULES = {
    "project_construct_links": {
        "id",
        "project_id",
        "construct_id",
        "construct_label",
        "construct_type",
        "construct_review_status",
        "link_label",
        "link_note",
        "source_context",
        "curation_status",
        "review_note",
        "created_at",
        "updated_at",
    },
    "project_catalog_asset_links": {
        "link_id",
        "project_id",
        "asset_type",
        "asset_id",
        "asset_label",
        "asset_version",
        "source_label",
        "documentation_status",
        "notes",
        "linkage_role",
        "record_identifier",
        "catalog_label",
        "catalog_name_source",
        "catalog_source_status",
        "reference_origin",
        "project_documentation_context",
        "documentation_note",
        "linked_reference_label",
        "linked_persisted_status",
        "snapshot_state",
        "snapshot_schema_version",
        "asset_snapshot",
        "snapshot_captured_at",
        "human_review_required",
        "created_at",
        "updated_at",
        "compact_metadata",
    },
    "construct_profiles": {
        "construct_id",
        "construct_label",
        "construct_type",
        "plasmid_backbone",
        "host_context_note",
        "source_reference",
        "provenance_note",
        "review_status",
        "documentation_scope_note",
        "created_at",
        "updated_at",
    },
    "expression_cassettes": {
        "cassette_id",
        "construct_id",
        "cassette_label",
        "cassette_role",
        "cassette_order",
        "promoter_label",
        "gene_label",
        "terminator_label",
        "source_reference",
        "provenance_note",
        "created_at",
        "updated_at",
    },
    "cassette_parts": {
        "id",
        "cassette_id",
        "part_order",
        "part_role",
        "part_label",
        "part_reference",
        "source_reference",
        "source_catalog",
        "source_record_id",
        "source_record_label",
        "evidence_context_note",
        "provenance_note",
        "created_at",
        "updated_at",
    },
    "linked_genes": {
        "id",
        "construct_id",
        "gene_label",
        "gene_reference",
        "source_reference",
        "provenance_note",
        "created_at",
    },
    "linked_pathway_steps": {
        "id",
        "construct_id",
        "pathway_step_id",
        "pathway_step_label",
        "source_reference",
        "provenance_note",
        "created_at",
    },
    "review_gaps": {
        "construct_id",
        "Gap type",
        "Label",
        "Review gap note",
    },
}
_COUNT_LABELS = (
    ("project_construct_links", "Project-level construct links"),
    ("project_catalog_asset_links", "Project catalog reference links"),
    ("construct_profiles", "Construct profiles"),
    ("expression_cassettes", "Expression cassettes"),
    ("cassette_parts", "Cassette parts"),
    ("linked_genes", "Linked genes"),
    ("linked_pathway_steps", "Linked pathway steps"),
    ("review_gaps", "Review gaps"),
)
_PROTEIN_EXPRESSION_UNSAFE_PHRASES = (
    "recommended",
    "recommend",
    "validate",
    "validated",
    "validation",
    "optimize",
    "optimized",
    "optimization",
    "ready",
    "readiness",
    "best",
    "preferred",
    "strongest",
    "high-expression",
    "yield",
    "productivity",
    "titer",
    "secretion success",
    "folding success",
    "glycosylation quality",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _protein_expression_text(value: Any, fallback: str = "Not available") -> str:
    text = _text(value) or fallback
    for phrase in _PROTEIN_EXPRESSION_UNSAFE_PHRASES:
        pattern = re.escape(phrase)
        if phrase.replace("-", "").replace(" ", "").isalpha():
            pattern = rf"\b{pattern}\b"
        text = re.sub(pattern, "[context term withheld for documentation review]", text, flags=re.IGNORECASE)
    return text


def _slug(value: Any, fallback: str = "project") -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", _text(value).lower()).strip("-")
    return safe[:48] or fallback


def _count_rows(package: dict[str, Any], section: str) -> int:
    rows = package.get(section)
    return len(rows) if isinstance(rows, list) else 0


def _promoter_source_link_row_count(package: dict[str, Any]) -> int:
    counts = build_package_record_counts(package if isinstance(package, dict) else {})
    return int(counts.get("promoter_source_link_row_count", 0))


def _project_metadata_availability(project_metadata: Any) -> tuple[int, int]:
    if not isinstance(project_metadata, dict):
        return 0, len(_PROJECT_METADATA_FIELDS)
    available = sum(1 for field in _PROJECT_METADATA_FIELDS if _text(project_metadata.get(field)))
    return available, len(_PROJECT_METADATA_FIELDS) - available


def _package_json_preview(package: dict[str, Any]) -> str:
    preview = {
        "manifest": package.get("manifest", {}),
        "package_metadata": package.get("package_metadata", {}),
        "project_metadata": package.get("project_metadata", {}),
        "project_construct_links": list(package.get("project_construct_links") or [])[:2],
        "project_catalog_asset_links": list(package.get("project_catalog_asset_links") or [])[:2],
        "construct_profiles": list(package.get("construct_profiles") or [])[:2],
        "expression_cassettes": list(package.get("expression_cassettes") or [])[:2],
        "cassette_parts": list(package.get("cassette_parts") or [])[:3],
        "linked_genes": list(package.get("linked_genes") or [])[:2],
        "linked_pathway_steps": list(package.get("linked_pathway_steps") or [])[:2],
        "review_gaps": list(package.get("review_gaps") or [])[:2],
        "report_references": package.get("report_references", {}),
        "integrity_summary": package.get("integrity_summary", {}),
        "documentation_only_boundary": package.get("documentation_only_boundary", ""),
        "known_limitations": package.get("known_limitations", []),
    }
    return json.dumps(preview, ensure_ascii=False, indent=2)


def _download_json_text(package: dict[str, Any]) -> str:
    return json.dumps(package, ensure_ascii=False, indent=2)


def _documentation_package_filename(project: dict[str, Any] | None) -> str:
    safe_project = project if isinstance(project, dict) else {}
    label = (
        safe_project.get("name")
        or safe_project.get("project_name")
        or safe_project.get("target_product")
        or safe_project.get("id")
        or "project"
    )
    return f"project_documentation_package_{_slug(label)}.json"


def _report_reference(project: dict[str, Any] | None) -> dict[str, Any]:
    safe_project = project if isinstance(project, dict) else {}
    return {
        "source_area": "Pathway Workspace / Project Outputs / Project Documentation Package",
        "project_id": _text(safe_project.get("id") or safe_project.get("project_id")),
        "project_name": _text(safe_project.get("name") or safe_project.get("project_name")),
        "report_note": "Compact documentation-only package preview for local review and traceability.",
    }


def _project_catalog_reference_summary(project: dict[str, Any] | None) -> dict[str, Any]:
    safe_project = project if isinstance(project, dict) else {}
    project_id = safe_project.get("id") or safe_project.get("project_id")
    try:
        links = project_catalog_link_repo.list_project_catalog_asset_links(project_id)
    except Exception:
        links = []
    links = [link for link in links if not has_staged_basket_only_markers(link)]
    summary = summarize_project_asset_links(links)
    promoter_summary = summarize_linked_plant_promoter_references(links)
    wizard_summary = build_expression_wizard_catalog_traceability_summary(links, project_id=project_id)
    return {
        "links": links,
        "linked_catalog_asset_count": summary.get("total_links", 0),
        "linked_plant_promoter_count": promoter_summary.get("linked_promoter_count", 0),
        "missing_source_or_review_metadata_count": promoter_summary.get("missing_metadata_count", 0),
        "expression_wizard_catalog_reference_count": wizard_summary.get("reference_count", 0),
        "expression_wizard_plant_promoter_reference_count": wizard_summary.get("plant_promoter_reference_count", 0),
        "expression_wizard_catalog_missing_metadata_count": wizard_summary.get("missing_metadata_count", 0),
        "catalog_links_with_pinned_snapshots_count": sum(
            1
            for link in links
            if catalog_asset_snapshot_has_content(link.get("asset_snapshot"))
        ),
        "catalog_links_missing_snapshots_count": sum(
            1
            for link in links
            if not catalog_asset_snapshot_has_content(link.get("asset_snapshot"))
        ),
        "catalog_links_malformed_snapshot_warning_count": sum(
            1 for link in links if link.get("asset_snapshot_warning")
        ),
        "project_documentation_contexts": sorted(
            {
                _text(
                    (link.get("source_context_snapshot") or {}).get("project_documentation_context")
                )
                for link in links
                if _text((link.get("source_context_snapshot") or {}).get("project_documentation_context"))
            },
            key=str.casefold,
        ),
        "limitation_note": promoter_summary.get("limitation_note"),
        "boundary_note": promoter_summary.get("boundary_note"),
        "wizard_limitation_note": wizard_summary.get("limitation_note"),
    }


def _shape_review_summary(package: dict[str, Any]) -> dict[str, list[str]]:
    missing_optional_fields: list[str] = []
    unknown_extra_fields: list[str] = []

    top_level_keys = set(package)
    for key in sorted(top_level_keys - _TOP_LEVEL_FIELDS):
        unknown_extra_fields.append(key)
    for key in sorted(_TOP_LEVEL_FIELDS - top_level_keys):
        if key not in {"report_references"}:
            missing_optional_fields.append(key)

    manifest = package.get("manifest")
    if isinstance(manifest, dict):
        for key in sorted(set(manifest) - _MANIFEST_FIELDS):
            unknown_extra_fields.append(f"manifest.{key}")
    elif "manifest" in package:
        missing_optional_fields.append("manifest")

    package_metadata = package.get("package_metadata")
    if isinstance(package_metadata, dict):
        for key in sorted(set(package_metadata) - _PACKAGE_METADATA_FIELDS):
            unknown_extra_fields.append(f"package_metadata.{key}")
    else:
        missing_optional_fields.append("package_metadata")

    project_metadata = package.get("project_metadata")
    if isinstance(project_metadata, dict):
        for key in sorted(_PROJECT_METADATA_FIELDS - set(project_metadata)):
            missing_optional_fields.append(f"project_metadata.{key}")
        for key in sorted(set(project_metadata) - _PROJECT_METADATA_FIELDS):
            unknown_extra_fields.append(f"project_metadata.{key}")
    else:
        missing_optional_fields.append("project_metadata")

    for section, expected_fields in _SECTION_FIELD_RULES.items():
        rows = package.get(section)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows[:5]):
            if not isinstance(row, dict):
                continue
            row_keys = set(row)
            for key in sorted(expected_fields - row_keys):
                missing_optional_fields.append(f"{section}[{index}].{key}")
            for key in sorted(row_keys - expected_fields):
                unknown_extra_fields.append(f"{section}[{index}].{key}")

    return {
        "missing_optional_fields": missing_optional_fields[:40],
        "unknown_extra_fields": unknown_extra_fields[:40],
    }


def _record_count_lines(report: dict[str, Any], package: dict[str, Any]) -> list[str]:
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    return [
        f"Project-level construct links: {counts.get('project_construct_links', _count_rows(package, 'project_construct_links'))}",
        f"Project catalog reference links: {counts.get('project_catalog_asset_links', _count_rows(package, 'project_catalog_asset_links'))}",
        "Linked Component Library promoter asset references: "
        f"{counts.get('linked_plant_promoter_catalog_references', 0)}",
        f"Catalog references missing source/review metadata: {counts.get('catalog_reference_missing_metadata_count', 0)}",
        f"Construct profiles: {counts.get('construct_profiles', _count_rows(package, 'construct_profiles'))}",
        f"Expression cassettes: {counts.get('expression_cassettes', _count_rows(package, 'expression_cassettes'))}",
        f"Cassette parts: {counts.get('cassette_parts', _count_rows(package, 'cassette_parts'))}",
        f"Promoter source-link rows: {counts.get('promoter_source_link_rows', _promoter_source_link_row_count(package))}",
        f"Linked genes: {counts.get('linked_genes', _count_rows(package, 'linked_genes'))}",
        f"Linked pathway steps: {counts.get('linked_pathway_steps', _count_rows(package, 'linked_pathway_steps'))}",
        f"Review gaps: {counts.get('review_gaps', _count_rows(package, 'review_gaps'))}",
    ]


def _protein_expression_package_readback(
    package: dict[str, Any],
    host_context_summary: dict[str, Any],
) -> dict[str, Any]:
    profiles = [row for row in package.get("construct_profiles") or [] if isinstance(row, dict)]
    cassettes = [row for row in package.get("expression_cassettes") or [] if isinstance(row, dict)]
    parts = [row for row in package.get("cassette_parts") or [] if isinstance(row, dict)]
    genes = [row for row in package.get("linked_genes") or [] if isinstance(row, dict)]
    gaps = [row for row in package.get("review_gaps") or [] if isinstance(row, dict)]
    metadata = package.get("project_metadata") if isinstance(package.get("project_metadata"), dict) else {}
    target_labels = [
        _protein_expression_text(metadata.get("target_product"), "")
        or _protein_expression_text(metadata.get("project_name"), "")
    ]
    target_labels.extend(_protein_expression_text(row.get("gene_label"), "") for row in genes)
    target_labels.extend(
        _protein_expression_text(row.get("part_label"), "")
        for row in parts
        if _text(row.get("part_role")).lower() == "cds"
    )
    promoter_rows = [row for row in parts if _text(row.get("part_role")).lower() == "promoter"]
    cds_rows = [row for row in parts if _text(row.get("part_role")).lower() == "cds"]
    terminator_rows = [row for row in parts if _text(row.get("part_role")).lower() == "terminator"]
    note_context_rows: list[dict[str, str]] = []
    note_keywords = ("signal", "secretion", "secretory", "marker", "vector", "backbone")
    for row in profiles:
        for key in ("plasmid_backbone", "host_context_note", "source_reference", "provenance_note", "documentation_scope_note"):
            note = _protein_expression_text(row.get(key), "")
            if note and any(keyword in note.lower() for keyword in note_keywords):
                note_context_rows.append({"source": f"construct profile {key}", "context": note})
    for row in parts:
        note = " ".join(
            _protein_expression_text(row.get(key), "")
            for key in ("part_role", "part_label", "part_reference", "source_record_label", "evidence_context_note")
        )
        if note and any(keyword in note.lower() for keyword in note_keywords):
            note_context_rows.append({"source": f"cassette part {_protein_expression_text(row.get('part_role'))}", "context": note})
    return {
        "status": "AVAILABLE" if profiles or cassettes or parts or genes else "NOT_AVAILABLE",
        "target_context": "; ".join(sorted({label for label in target_labels if label}, key=str.casefold)) or "Not available",
        "host_context": _protein_expression_text(host_context_summary.get("project_context_label"), "Generic / unspecified"),
        "contexts_present": "; ".join(host_context_summary.get("contexts_present_labels") or ["Generic / unspecified"]),
        "construct_count": len(profiles),
        "cassette_count": len(cassettes),
        "promoter_count": len(promoter_rows),
        "cds_count": len(cds_rows),
        "terminator_count": len(terminator_rows),
        "linked_gene_count": len(genes),
        "review_gap_count": len(gaps),
        "existing_note_context_rows": note_context_rows,
        "boundary_note": "Protein expression package readback is documentation-only context for review and traceability.",
        "schema_note": "This readback uses existing package rows only and does not add package schema fields.",
    }


def _manifest_summary(package: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    report_data = report if isinstance(report, dict) else {}
    manifest_summary = report_data.get("manifest_summary") if isinstance(report_data.get("manifest_summary"), dict) else {}
    if not manifest_summary:
        manifest_summary = build_manifest_review_summary(package)
    export_scope = manifest_summary.get("export_scope") if isinstance(manifest_summary.get("export_scope"), dict) else {}
    record_counts = manifest_summary.get("record_counts") if isinstance(manifest_summary.get("record_counts"), dict) else {}
    return {
        "is_manifest_present": bool(manifest_summary.get("is_manifest_present")),
        "package_format": _text(manifest_summary.get("package_format")),
        "package_schema_version": _text(
            report_data.get("package_schema_version")
            or manifest_summary.get("package_schema_version")
        ),
        "exported_at": _text(manifest_summary.get("exported_at")),
        "exported_by_app": _text(manifest_summary.get("exported_by_app")),
        "source_commit_or_tag": _text(manifest_summary.get("source_commit_or_tag")),
        "included_sections": list(manifest_summary.get("included_sections") or []),
        "compatibility_notes": list(manifest_summary.get("compatibility_notes") or []),
        "documentation_boundary": _text(manifest_summary.get("documentation_boundary")),
        "limitations": list(manifest_summary.get("limitations") or []),
        "selection_mode": _text(export_scope.get("selection_mode")),
        "export_scope_project_id": _text(export_scope.get("project_id")),
        "selected_construct_ids": list(export_scope.get("selected_construct_ids") or []),
        "record_counts": record_counts,
        "review_notes": list(manifest_summary.get("review_notes") or []),
    }


def _integrity_summary(package: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    package_summary = package.get("integrity_summary") if isinstance(package.get("integrity_summary"), dict) else {}
    report_summary = report.get("integrity_summary") if isinstance((report or {}).get("integrity_summary"), dict) else {}
    return report_summary or package_summary


def _catalog_reference_import_review_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("catalog_reference_import_review_summary")
    return summary if isinstance(summary, dict) else {}


def _render_host_chassis_context_summary(summary: dict[str, Any]) -> None:
    st.markdown("**Host / chassis documentation context**")
    st.caption(
        "Read-only host / chassis context readback for documentation package review. "
        "It preserves documentation context only and does not recommend, validate, optimize, "
        "or certify readiness."
    )
    st.caption(
        "Schema boundary: this preview/readback is review context only. "
        "It does not add a host / chassis summary field to the exported JSON package schema, "
        "and downstream package or import consumers should not assume such a field is present."
    )
    st.caption(
        str(
            summary.get("documentation_only_note")
            or "Host / chassis context readback is documentation context only."
        )
    )
    st.caption(
        f"Active project context: {summary.get('project_context_label') or 'Generic / unspecified'}"
    )
    st.caption(
        "Supported chassis-neutral contexts: "
        + ", ".join(summary.get("supported_contexts") or ["generic / unspecified"])
    )
    st.caption(
        "Contexts present in readback: "
        + ", ".join(summary.get("contexts_present_labels") or ["Generic / unspecified"])
    )
    st.caption(
        str(
            summary.get("limitation_note")
            or "Plant and Nicotiana examples remain examples, not defaults."
        )
    )
    if summary.get("rows"):
        st.dataframe(
            [
                {
                    "Source label": row.get("source_label", ""),
                    "Source value": row.get("source_value", ""),
                    "Normalized context": row.get("normalized_context_label", ""),
                    "Record label": row.get("asset_display_name", ""),
                }
                for row in summary.get("rows") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info("No host / chassis context readback rows are recorded in this package preview.")


def _render_manifest_summary(summary: dict[str, Any], *, title: str, show_empty_state: bool = False) -> None:
    st.markdown(f"**{title}**")
    if show_empty_state and not summary.get("is_manifest_present"):
        st.info("Older package format: package manifest metadata was not provided. Review package contents and boundary fields before local documentation use.")
    st.caption(f"Package format: {_text(summary.get('package_format')) or 'Not available'}")
    st.caption(f"Package schema version: {_text(summary.get('package_schema_version')) or 'Not available'}")
    st.caption(f"Exported at: {_text(summary.get('exported_at')) or 'Not available'}")
    st.caption(f"Exported by app: {_text(summary.get('exported_by_app')) or 'Not available'}")
    if _text(summary.get("source_commit_or_tag")):
        st.caption(f"Source commit or tag: {_text(summary.get('source_commit_or_tag'))}")
    st.caption(f"Export scope: {_text(summary.get('selection_mode')) or 'Not available'}")
    if _text(summary.get("export_scope_project_id")):
        st.caption(f"Export scope project ID: {_text(summary.get('export_scope_project_id'))}")
    selected_construct_ids = list(summary.get("selected_construct_ids") or [])
    if selected_construct_ids:
        st.caption(f"Selected construct IDs: {len(selected_construct_ids)}")
    included_sections = list(summary.get("included_sections") or [])
    if included_sections:
        st.caption(f"Included sections: {', '.join(included_sections)}")
    else:
        st.caption("Included sections: Not available")
    record_counts = summary.get("record_counts") if isinstance(summary.get("record_counts"), dict) else {}
    if record_counts:
        st.caption("Manifest record counts: available")
        with st.expander("Manifest record counts", expanded=False):
            for key in sorted(record_counts):
                st.caption(f"- {key}: {record_counts.get(key)}")
    else:
        st.caption("Manifest record counts: Not available")
    compatibility_notes = list(summary.get("compatibility_notes") or [])
    if compatibility_notes:
        st.caption("Compatibility notes: available")
        with st.expander("Compatibility notes", expanded=False):
            for note in compatibility_notes:
                st.caption(f"- {note}")
    else:
        st.caption("Compatibility notes: Not available")
    documentation_boundary = _text(summary.get("documentation_boundary"))
    if documentation_boundary:
        st.caption("Documentation boundary: available")
        with st.expander("Documentation boundary", expanded=False):
            st.caption(documentation_boundary)
    else:
        st.caption("Documentation boundary: Not available")
    limitations = list(summary.get("limitations") or [])
    if limitations:
        st.caption("Limitations: available")
        with st.expander("Limitations", expanded=False):
            for limitation in limitations:
                st.caption(f"- {limitation}")
    else:
        st.caption("Limitations: Not available")
    review_notes = list(summary.get("review_notes") or [])
    if review_notes:
        st.caption("Manifest review notes: needs review")
        with st.expander("Manifest review notes", expanded=False):
            for note in review_notes:
                st.caption(f"- {note}")
    else:
        st.caption("Manifest review notes: none reported.")


def _render_integrity_summary(summary: dict[str, Any]) -> None:
    if not isinstance(summary, dict) or not summary:
        return
    st.markdown("**Integrity summary**")
    st.caption(f"Package ID: {_text(summary.get('package_id')) or 'Not available'}")
    st.caption(_text(summary.get("integrity_note")) or "Lightweight package comparison summary only.")


def _render_shape_review(summary: dict[str, list[str]]) -> None:
    st.markdown("**Package shape review**")
    missing = summary.get("missing_optional_fields") or []
    extras = summary.get("unknown_extra_fields") or []

    if missing:
        st.caption("Missing optional fields: review the expander for fields that are still blank or omitted.")
        with st.expander("Missing optional fields", expanded=False):
            for item in missing:
                st.caption(f"- {item}")
    else:
        st.caption("Missing optional fields: none detected in the reviewed rows.")

    if extras:
        st.caption("Unknown extra fields: review the expander for fields that are outside the current package shape.")
        with st.expander("Unknown extra fields", expanded=False):
            for item in extras:
                st.caption(f"- {item}")
    else:
        st.caption("Unknown extra fields: none detected in the reviewed rows.")


def _render_dry_run_plan(plan: dict[str, Any]) -> None:
    st.markdown("**Dry-run import summary**")
    st.caption(
        "Default behavior is dry-run only. This preview is non-destructive and summarizes create-as-new work before any local records are created."
    )
    would_create = plan.get("would_create") if isinstance(plan.get("would_create"), dict) else {}
    st.caption(f"Package version: {_text(plan.get('package_version')) or 'Not available'}")
    st.caption(f"Package schema version: {_text(plan.get('package_schema_version')) or 'Not available'}")
    st.caption(f"Create mode: {_text(plan.get('create_mode')) or 'create_as_new_only'}")
    st.caption(f"Target project ID for imported links: {_text(plan.get('target_project_id')) or 'Not available'}")
    st.caption(f"Constructs that would be created: {would_create.get('construct_profiles', 0)}")
    st.caption(f"Cassettes that would be created: {would_create.get('expression_cassettes', 0)}")
    st.caption(f"Cassette parts that would be created: {would_create.get('cassette_parts', 0)}")
    st.caption(f"Promoter source-link rows that would be created: {would_create.get('promoter_source_link_rows', 0)}")
    st.caption(f"Gene links that would be created: {would_create.get('linked_genes', 0)}")
    st.caption(f"Pathway step links that would be created: {would_create.get('linked_pathway_steps', 0)}")
    st.caption(f"Project-level construct links that would be created: {would_create.get('project_construct_links', 0)}")
    st.caption(f"Project catalog reference links that would be created: {would_create.get('project_catalog_asset_links', 0)}")
    st.caption("Overwrite, merge, delete, and restore behaviors are deferred and are not available here.")


def _render_conflict_preview(conflicts: dict[str, Any]) -> None:
    st.markdown("**Conflict preview**")
    entries = list(conflicts.get("conflicts") or [])
    if entries:
        st.warning("Possible conflicts were detected. Review them before any create-as-new action.")
        for entry in entries:
            st.caption(
                f"- {_text(entry.get('conflict_type'))}: {_text(entry.get('detail')) or _text(entry.get('identifier'))}"
            )
    else:
        st.caption("No possible conflicts were detected in the currently supported checks.")

    structural_errors = list(conflicts.get("structural_errors") or [])
    if structural_errors:
        st.caption("Cross-reference issues found during conflict review:")
        for error in structural_errors:
            st.caption(f"- {error}")

    deferred_checks = list(conflicts.get("deferred_checks") or [])
    if deferred_checks:
        with st.expander("Deferred conflict checks", expanded=False):
            for item in deferred_checks:
                st.caption(f"- {item}")


def _render_create_result(result: dict[str, Any]) -> None:
    st.markdown("**Create-as-new import result**")
    if result.get("created"):
        st.success("Documentation project records were created as new local rows.")
    else:
        st.info("No local rows were created.")

    created_counts = result.get("created_counts") if isinstance(result.get("created_counts"), dict) else {}
    for key in (
        "construct_profiles",
        "expression_cassettes",
        "cassette_parts",
        "linked_genes",
        "linked_pathway_steps",
        "project_construct_links",
        "project_catalog_asset_links",
        "project_catalog_asset_link_duplicates",
        "project_catalog_asset_link_skipped",
    ):
        st.caption(f"{key}: {created_counts.get(key, 0)}")

    warnings = list(result.get("warnings") or [])
    if warnings:
        st.markdown("**Create warnings**")
        for warning in warnings:
            st.caption(f"- {warning}")

    errors = list(result.get("errors") or [])
    if errors:
        st.markdown("**Create errors**")
        for error in errors:
            st.caption(f"- {error}")


def render_project_documentation_package_export_panel(project: dict[str, Any] | None) -> None:
    safe_project = project if isinstance(project, dict) else {}
    catalog_reference_summary = _project_catalog_reference_summary(safe_project)
    host_context_summary = build_host_chassis_context_summary(
        safe_project,
        catalog_reference_summary.get("links") or [],
    )
    package = build_project_documentation_export_package(
        project=safe_project,
        project_id=safe_project.get("id") or safe_project.get("project_id"),
        report_reference={
            **_report_reference(safe_project),
            "linked_catalog_asset_count": catalog_reference_summary["linked_catalog_asset_count"],
            "linked_plant_promoter_count": catalog_reference_summary["linked_plant_promoter_count"],
            "missing_source_or_review_metadata_count": catalog_reference_summary["missing_source_or_review_metadata_count"],
            "catalog_reference_boundary_note": catalog_reference_summary["boundary_note"],
            "catalog_reference_limitation_note": catalog_reference_summary["limitation_note"],
        },
    )

    st.markdown("**Project Documentation Package**")
    st.caption(
        "Documentation-only JSON package preview for local review, traceability, manifest metadata review, and "
        "project record handoff. It does not recommend, score, rank, optimize, predict, validate, or certify readiness."
    )
    st.caption("Navigation cue: this panel is the Project Documentation Package surface.")
    st.caption(
        "This review surface supports package preview, manifest metadata review, and documentation-only package exchange context."
    )
    with st.expander("Package workflow and exchange trail", expanded=False):
        st.caption("Import Manifest Review belongs to the Project Documentation Package workflow.")
        st.caption(
            "Exchange trail: exported packages include manifest metadata; Import Manifest Review shows that metadata as "
            "documentation context for local review."
        )
        st.caption(
            "Package workflow: create or review project documentation; export a documentation package with manifest metadata; "
            "review it in Import Manifest Review; create a new project copy only after explicit confirmation; then inspect "
            "the Package Exchange Review Trail in the Project Review Report and Project Quality Dashboard."
        )
    available_metadata, missing_metadata = _project_metadata_availability(package.get("project_metadata"))
    metadata = package.get("package_metadata") if isinstance(package.get("package_metadata"), dict) else {}
    manifest_summary = _manifest_summary(package)
    integrity_summary = _integrity_summary(package)

    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        st.metric("Package version", _text(metadata.get("package_version")) or "Not available")
    with c2:
        st.metric("Package schema", _text(manifest_summary.get("package_schema_version")) or "Not available")
    with c3:
        st.metric("Construct profiles", _count_rows(package, "construct_profiles"))
    with c4:
        st.metric("Promoter source-link rows", _promoter_source_link_row_count(package))
    c5, c6 = st.columns(2, gap="small")
    with c5:
        st.metric("Project metadata fields", f"{available_metadata} available")
    with c6:
        st.metric("Package ID", _text(integrity_summary.get("package_id")) or "Not available")
    c7, c8 = st.columns(2, gap="small")
    with c7:
        st.metric("Linked catalog references", catalog_reference_summary["linked_catalog_asset_count"])
    with c8:
        st.metric(
            "Linked Component Library promoter asset references",
            catalog_reference_summary["linked_plant_promoter_count"],
        )

    if not available_metadata:
        st.info("No project metadata is recorded yet. The package preview can still capture local construct documentation rows.")
    if missing_metadata:
        st.caption(f"Project metadata review gaps: {missing_metadata} fields remain blank in this package preview.")
    if not _count_rows(package, "project_construct_links"):
        st.caption("No project-level construct links are recorded in this package preview.")
    if not _count_rows(package, "project_catalog_asset_links"):
        st.caption("No project catalog reference links are included in this package preview yet.")
    if not _count_rows(package, "construct_profiles"):
        st.info("No construct profiles are included yet. The package remains a documentation-only review artifact.")
    if not _count_rows(package, "expression_cassettes"):
        st.caption("No expression cassettes are included in this package preview.")
    if not _count_rows(package, "cassette_parts"):
        st.caption("No cassette parts are included in this package preview.")
    if not _promoter_source_link_row_count(package):
        st.caption("No promoter source-link rows are included in this package preview.")
    if not catalog_reference_summary["linked_catalog_asset_count"]:
        st.caption("No persisted linked catalog references are recorded for this project package summary yet.")
    if not _count_rows(package, "linked_genes"):
        st.caption("No linked genes are included in this package preview.")
    if not _count_rows(package, "linked_pathway_steps"):
        st.caption("No linked pathway steps are included in this package preview.")
    if not _count_rows(package, "review_gaps"):
        st.caption("No review gaps are currently recorded in this package preview.")

    with st.expander("Documentation package preview summary", expanded=True):
        st.caption(f"Package metadata: {_text(metadata.get('package_kind')) or 'Not available'}")
        _render_manifest_summary(manifest_summary, title="Manifest summary")
        st.caption(f"Project metadata availability: {available_metadata} available / {missing_metadata} missing")
        for section, label in _COUNT_LABELS:
            st.caption(f"{label}: {_count_rows(package, section)}")
        st.caption(f"Project catalog reference links included: {_count_rows(package, 'project_catalog_asset_links')}")
        st.caption(f"Promoter source-link rows: {_promoter_source_link_row_count(package)}")
        st.caption(
            "Linked catalog reference summary: "
            f"{catalog_reference_summary['linked_catalog_asset_count']} catalog references; "
            f"{catalog_reference_summary['linked_plant_promoter_count']} Component Library promoter asset references; "
            f"{catalog_reference_summary['missing_source_or_review_metadata_count']} missing source/review metadata fields."
        )
        if catalog_reference_summary["missing_source_or_review_metadata_count"]:
            st.caption(
                "Linked catalog reference metadata review gaps remain visible in this package summary. "
                "Review linked catalog references and record missing source or review metadata when needed."
            )
        if not catalog_reference_summary["linked_catalog_asset_count"]:
            st.caption("Linked catalog reference summary remains empty until persisted project references are available.")
        if catalog_reference_summary["project_documentation_contexts"]:
            st.caption(
                "Project documentation contexts: "
                + "; ".join(catalog_reference_summary["project_documentation_contexts"])
            )
        else:
            st.caption("Project documentation contexts: Not recorded in this package preview.")
        st.caption(
            "Catalog reference snapshot summary: "
            f"{catalog_reference_summary['catalog_links_with_pinned_snapshots_count']} pinned documentation snapshot(s); "
            f"{catalog_reference_summary['catalog_links_missing_snapshots_count']} fallback metadata link(s); "
            f"{catalog_reference_summary['catalog_links_malformed_snapshot_warning_count']} malformed snapshot warning(s)."
        )
        st.caption(
            "Expression Wizard catalog traceability: "
            f"{catalog_reference_summary['expression_wizard_catalog_reference_count']} documentation-level reference(s); "
            f"{catalog_reference_summary['expression_wizard_plant_promoter_reference_count']} "
            "Component Library promoter asset reference(s); "
            f"{catalog_reference_summary['expression_wizard_catalog_missing_metadata_count']} missing metadata field(s)."
        )
        st.caption(
            catalog_reference_summary["limitation_note"]
            or "Catalog references are documentation-level project context only."
        )
        st.caption(
            catalog_reference_summary["wizard_limitation_note"]
            or "Expression Wizard catalog references are source/review context only."
        )
        _render_integrity_summary(integrity_summary)
        st.caption("Boundary: documentation-only package for review and traceability; no readiness or experimental claims.")
        st.caption("Manifest review fields support package exchange review trail context in reports and quality review.")

    with st.expander("Host / chassis documentation context", expanded=False):
        _render_host_chassis_context_summary(host_context_summary)

    protein_expression_readback = _protein_expression_package_readback(package, host_context_summary)
    with st.expander("Protein Expression Documentation Readback", expanded=False):
        st.markdown("**Protein Expression Documentation Readback**")
        st.caption(protein_expression_readback["boundary_note"])
        st.caption(protein_expression_readback["schema_note"])
        st.caption("Single-protein records are presented as protein expression documentation context.")
        st.caption("No biological outcome or downstream-use claim is made by this readback.")
        st.caption(f"Status: {protein_expression_readback['status']}")
        st.caption(f"Target protein / linked gene / CDS context: {protein_expression_readback['target_context']}")
        st.caption(f"Host / chassis context: {protein_expression_readback['host_context']}")
        st.caption(f"Host / chassis readback contexts: {protein_expression_readback['contexts_present']}")
        st.caption(f"Construct profiles: {protein_expression_readback['construct_count']}")
        st.caption(f"Expression cassettes: {protein_expression_readback['cassette_count']}")
        st.caption(
            "Recorded cassette parts: "
            f"{protein_expression_readback['promoter_count']} promoter; "
            f"{protein_expression_readback['cds_count']} CDS; "
            f"{protein_expression_readback['terminator_count']} terminator."
        )
        st.caption(f"Linked genes: {protein_expression_readback['linked_gene_count']}")
        st.caption(f"Review gaps: {protein_expression_readback['review_gap_count']}")
        if protein_expression_readback["existing_note_context_rows"]:
            st.caption("Existing signal, secretion, marker, vector, or backbone context from notes/metadata:")
            for row in protein_expression_readback["existing_note_context_rows"][:6]:
                st.caption(f"- {row['source']}: {row['context']} (documentation context only)")
        else:
            st.caption("No signal, secretion, marker, vector, or backbone context is recorded in existing notes/metadata.")

    st.caption("Documentation package preview summary remains available for local review before JSON export.")

    with st.expander("Documentation package JSON preview", expanded=False):
        st.text_area(
            "Documentation package JSON preview",
            value=_package_json_preview(package),
            height=320,
            disabled=True,
            key=f"project_documentation_package_export_preview_{_slug(safe_project.get('id') or safe_project.get('name'))}",
        )

    clicked = st.download_button(
        "Export Documentation Package (.json)",
        data=_download_json_text(package),
        file_name=_documentation_package_filename(safe_project),
        mime="application/json",
        use_container_width=True,
    )
    if clicked:
        st.success("Documentation-only package preview completed. Keep the JSON file as a local review record.")

    st.caption(CSV_DEFERRED_NOTE)
    st.caption("Import Preview below supports structure review for pasted or uploaded documentation package JSON.")


def render_project_documentation_package_import_panel() -> None:
    st.markdown("**Documentation Package Check**")
    st.caption(
        "Review a JSON documentation package before any create-as-new workflow. Default behavior is dry-run first; "
        "manifest review and package exchange trail remain documentation-only."
    )
    with st.expander("Import review chain", expanded=False):
        st.caption(
            "Review chain: exported packages include a manifest; imported packages show Import Manifest Review; "
            "older or partial packages may show limited metadata and review notes."
        )
        st.caption(
            "Package workflow: keep the package in read-only documentation context, review manifest metadata and "
            "missing metadata notes, then create a new project copy only through explicit confirmation when the "
            "package structure is acceptable."
        )
    st.caption(
        "Boundary: package review does not create, overwrite, merge, restore, rank, optimize, predict, validate, or certify readiness for any project, construct, cassette, promoter, gene, pathway step, report, or export."
    )
    st.caption("Overwrite, merge, delete, restore, CSV or Excel import, external source imports, and complex sequence parsing remain deferred.")
    uploaded_file = st.file_uploader(
        "Upload Documentation Package (.json)",
        type=["json"],
        key="project_documentation_package_upload_json",
    )
    pasted_text = st.text_area(
        "Or paste Documentation Package JSON",
        value="",
        height=180,
        key="project_documentation_package_paste_json",
    )

    raw_text = ""
    if uploaded_file is not None:
        try:
            raw_text = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            st.error("Uploaded documentation package text could not be read as UTF-8 JSON.")
            return
    elif _text(pasted_text):
        raw_text = pasted_text

    if uploaded_file is None and not _text(pasted_text):
        st.info("Upload a documentation package JSON file or paste package JSON text to review structure.")
        return
    if not _text(raw_text):
        st.info("The provided documentation package text is empty.")
        return

    try:
        package = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        st.error("Documentation package JSON could not be parsed.")
        st.caption(f"JSON parser detail: line {exc.lineno}, column {exc.colno}.")
        return

    report = validate_project_documentation_package(package)
    shape_summary = _shape_review_summary(package if isinstance(package, dict) else {})
    dry_run = build_import_dry_run(package if isinstance(package, dict) else {})
    plan = dry_run.get("plan") if isinstance(dry_run.get("plan"), dict) else {}
    conflicts = dry_run.get("conflicts") if isinstance(dry_run.get("conflicts"), dict) else {}
    manifest_summary = _manifest_summary(package if isinstance(package, dict) else {}, report)
    integrity_summary = _integrity_summary(package if isinstance(package, dict) else {}, report)

    st.markdown("**Package check result**")
    if report.get("is_valid"):
        st.success("Accepted package for documentation-only review.")
    else:
        st.error("Package structure needs review before local documentation use.")

    st.caption(f"package_version: {_text(report.get('package_version')) or 'Not available'}")
    st.caption(f"package_schema_version: {_text(report.get('package_schema_version')) or 'Not available'}")
    st.caption(f"project_id: {_text(report.get('project_id')) or 'Not available'}")
    st.caption(f"project_name: {_text(report.get('project_name')) or 'Not available'}")
    for line in _record_count_lines(report, package if isinstance(package, dict) else {}):
        st.caption(line)
    _render_manifest_summary(manifest_summary, title="Import Manifest Review", show_empty_state=True)
    _render_integrity_summary(integrity_summary)
    catalog_import_summary = _catalog_reference_import_review_summary(report)
    if catalog_import_summary:
        st.markdown("**Linked catalog reference import review**")
        st.caption(f"Total linked catalog reference rows in package: {catalog_import_summary.get('total_rows_in_package', 0)}")
        st.caption(
            f"Rows with complete documentation context: {catalog_import_summary.get('complete_documentation_context_count', 0)}"
        )
        st.caption(
            f"Rows using safe fallback labels: {catalog_import_summary.get('safe_fallback_label_count', 0)}"
        )
        st.caption(
            f"Rows with live metadata fallback / missing snapshot state: {catalog_import_summary.get('live_metadata_fallback_count', 0)}"
        )
        st.caption(
            f"Rows with missing record identifier or source/status: {catalog_import_summary.get('missing_identifier_or_source_status_count', 0)}"
        )
        for message in catalog_import_summary.get("integrity_messages") or []:
            st.caption(message)

    _render_shape_review(shape_summary)
    _render_dry_run_plan(plan)
    _render_conflict_preview(conflicts)

    st.markdown("**Structural errors**")
    errors = list(report.get("errors") or [])
    combined_structural_errors = list(plan.get("structural_errors") or [])
    rendered_errors = []
    for error in errors + [error for error in combined_structural_errors if error not in errors]:
        rendered_errors.append(error)
    if rendered_errors:
        for error in rendered_errors:
            st.caption(f"- {error}")
    else:
        st.caption("No structural errors were reported by the package checker.")

    st.markdown("**Warnings**")
    warnings = list(report.get("warnings") or [])
    if warnings:
        for warning in warnings:
            st.caption(f"- {warning}")
    else:
        st.caption("No warnings were reported by the package checker.")

    confirmation_checked = st.checkbox(
        "I confirm that create-as-new should add new local documentation rows only and must not overwrite or merge existing rows.",
        value=False,
        key="project_documentation_package_confirm_create_as_new",
        help="Required before create-as-new import becomes available.",
    )
    st.caption("Create-as-new import stays unavailable until this confirmation is explicit.")
    create_disabled = (
        not report.get("is_valid")
        or not confirmation_checked
        or bool(plan.get("structural_errors"))
    )
    if st.button(
        "Create As New Documentation Records",
        key="project_documentation_package_create_as_new",
        disabled=create_disabled,
        use_container_width=True,
    ):
        result = import_package_create_as_new(package, confirm=True)
        st.session_state["project_documentation_package_import_result"] = result

    if not report.get("is_valid"):
        st.caption("Create-as-new import is unavailable until package structure issues are resolved.")
    elif plan.get("structural_errors"):
        st.caption("Create-as-new import is unavailable while package cross-reference issues remain.")
    elif not confirmation_checked:
        st.caption("Create-as-new import is unavailable until the explicit confirmation control is checked.")
    else:
        st.caption("Create-as-new import is available. It adds new local documentation rows only.")

    last_result = st.session_state.get("project_documentation_package_import_result")
    if isinstance(last_result, dict):
        _render_create_result(last_result)

    with st.expander("Documentation package JSON preview", expanded=False):
        st.text_area(
            "Reviewed documentation package JSON",
            value=_package_json_preview(package if isinstance(package, dict) else {}),
            height=320,
            disabled=True,
            key="project_documentation_package_import_preview_json",
        )
