from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
)
from services.project_package_review_trail_service import build_package_exchange_review_trail
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
)
from services.expression_wizard_catalog_picker_presenter import build_expression_wizard_catalog_traceability_summary
from services.catalog_asset_snapshot_builder import catalog_asset_snapshot_has_content
from services.host_chassis_context_presenter import build_host_chassis_context_summary
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_asset_linkage_service import merge_project_asset_links
from services.plant_promoter_catalog_workspace_presenter import summarize_linked_plant_promoter_references

DASHBOARD_TITLE = "Project Quality Dashboard"
DASHBOARD_VERSION = "1.0"

STATUS_COMPLETE_ENOUGH_FOR_REVIEW = "COMPLETE_ENOUGH_FOR_REVIEW"
STATUS_NEEDS_DOCUMENTATION = "NEEDS_DOCUMENTATION"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
STATUS_AVAILABLE = "AVAILABLE"
STATUS_COMPLETE = "COMPLETE"
STATUS_MISSING = "MISSING"

BOUNDARY_NOTES = [
    PROJECT_OUTPUT_SCOPE_NOTE,
    "This dashboard summarizes documentation completeness only.",
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    "It does not certify experiment-use state.",
    "It does not forecast yield.",
    "It does not tune pathways.",
    "It does not provide wet-lab instructions.",
    "Import Preview remains read-only and does not create a project by itself.",
    "Blocked / NO-GO import states apply only to the gated create-as-new action or to prohibited biological execution, validation, optimization, or wet-lab readiness claims.",
    "When allowed, the gated import-as-new path creates a local documentation-only project only after validation, safety review, dry-run planning, and explicit confirmation.",
]

LINKED_ARTIFACT_NOTES = [
    "Linked artifacts are documentation records for traceability only.",
    "They do not certify downstream use state or experimental evidence.",
]

SAVED_DESIGN_NOTES = [
    "Saved design snapshots do not create or select pathway projects automatically.",
]

IMPORT_SAFETY_NOTES = [
    "Import package safety checks are read-only.",
    "They do not import or modify any project.",
    "No database writes are performed.",
    "Blocked / NO-GO safety states stop the gated create-as-new action.",
    "A separate gated create-as-new action may create a local documentation-only project only after validation, safety review, dry-run planning, and explicit confirmation.",
]

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _project_identity(project: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "project_id": _first_present(project, ("project_id", "id")),
        "project_name": _first_present(project, ("project_name", "name", "target_product")),
        "description": _first_present(project, ("description", "project_description")),
        "active_project_status": _first_present(project, ("active_project_status", "status")),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
    }
    missing = [key for key, value in fields.items() if key in {"project_id", "project_name", "description"} and value in (None, "")]
    return {"status": STATUS_NEEDS_REVIEW if missing else STATUS_COMPLETE, "fields": fields, "missing_fields": missing}


def _summarize_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not steps:
        return {
            "status": STATUS_MISSING,
            "count": 0,
            "missing_step_fields": [],
            "summaries": [],
            "message": "No pathway steps are documented yet.",
            "guidance": "Add pathway documentation steps before treating this project record as complete.",
        }
    summaries: list[dict[str, Any]] = []
    all_missing: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        fields = {
            "step_id": _first_present(step, ("step_id", "id")),
            "step_order": step.get("step_order") or index,
            "title": _first_present(step, ("step_name", "title", "reaction_name", "name")),
            "organism": _first_present(step, ("organism", "organism_source", "source_organism")),
            "enzyme": _first_present(step, ("enzyme", "enzyme_name")),
            "gene": _first_present(step, ("gene", "gene_name")),
            "notes": step.get("notes"),
        }
        missing = [key for key in ("title", "organism", "enzyme", "gene") if fields.get(key) in (None, "")]
        if missing:
            all_missing.append({"step_order": fields["step_order"], "missing_fields": missing})
        summaries.append({"status": STATUS_NEEDS_REVIEW if missing else STATUS_COMPLETE, "fields": fields, "missing_fields": missing})
    return {"status": STATUS_NEEDS_REVIEW if all_missing else STATUS_COMPLETE, "count": len(summaries), "missing_step_fields": all_missing, "summaries": summaries}


def _summarize_artifacts(linked_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    if not linked_artifacts:
        return {"status": STATUS_MISSING, "count": 0, "artifact_types": [], "sources": [], "titles": [], "message": "No linked documentation artifacts are attached to this project yet.", "traceability_note": "Linked artifacts are documentation records for traceability only.", "boundary_notes": LINKED_ARTIFACT_NOTES}
    artifact_types = [_first_present(item, ("artifact_type", "type")) for item in linked_artifacts]
    sources = [_first_present(item, ("source", "source_module")) for item in linked_artifacts]
    titles = [_first_present(item, ("title", "name")) for item in linked_artifacts]
    return {"status": STATUS_COMPLETE, "count": len(linked_artifacts), "artifact_types": artifact_types, "sources": sources, "titles": titles, "traceability_note": "Linked artifacts are documentation records for traceability only.", "boundary_notes": LINKED_ARTIFACT_NOTES}


def _summarize_saved_designs(saved_designs: list[dict[str, Any]]) -> dict[str, Any]:
    if not saved_designs:
        return {"status": STATUS_NOT_AVAILABLE, "count": 0, "message": "No saved design snapshot is linked to this pathway project.", "guidance": "Saved design snapshots restore wizard inputs and outputs only; link records only when traceability is needed.", "boundary_notes": SAVED_DESIGN_NOTES}
    snapshots = [{"design_id": _first_present(item, ("design_id", "id")), "display_name": _first_present(item, ("display_name", "name", "title")), "source_saved_design_id": item.get("source_saved_design_id"), "saved_design_version": _first_present(item, ("saved_design_version", "version")), "identity_source": _first_present(item, ("identity_source", "source")), "status": STATUS_AVAILABLE} for item in saved_designs]
    first = snapshots[0]
    return {"status": STATUS_AVAILABLE, "count": len(snapshots), "snapshots": snapshots, **first, "boundary_notes": SAVED_DESIGN_NOTES}


def _summarize_export(export_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not export_summary:
        return {"status": STATUS_NOT_AVAILABLE, "message": "No export package status is recorded for this project quality dashboard.", "reason": "No export summary was provided.", "user_guidance": "Export a documentation-only project package when a portable review package is needed.", "documentation_only_package_note": "Export packages are documentation-only project packages."}
    return {"status": export_summary.get("status") or STATUS_AVAILABLE, "contents_preview_availability": export_summary.get("contents_preview_availability") or export_summary.get("package_contents_preview_status") or export_summary.get("contents_preview_status") or STATUS_AVAILABLE, "documentation_only_package_note": export_summary.get("documentation_only_package_note") or "Export packages are documentation-only project packages."}


def _summarize_import_safety(import_safety_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not import_safety_summary:
        return {"status": STATUS_NOT_AVAILABLE, "message": "No import package safety check report is attached to this project quality dashboard.", "reason": "No import safety summary was provided.", "user_guidance": "Run Import Package Safety Check on an exported package for read-only review.", "boundary_notes": IMPORT_SAFETY_NOTES}
    check_items = [item for item in _as_list(import_safety_summary.get("check_items")) if isinstance(item, dict)]
    not_evaluated = import_safety_summary.get("not_evaluated_count")
    if not_evaluated is None:
        not_evaluated = sum(1 for item in check_items if item.get("status") == "NOT_EVALUATED")
    return {
        "status": import_safety_summary.get("status") or STATUS_AVAILABLE,
        "overall_status": import_safety_summary.get("overall_status") or STATUS_NOT_AVAILABLE,
        "blocking_issue_count": len(_as_list(import_safety_summary.get("blocking_issues"))),
        "warning_count": len(_as_list(import_safety_summary.get("warnings"))),
        "not_evaluated_count": not_evaluated,
        "manifest_summary": import_safety_summary.get("manifest_summary") if isinstance(import_safety_summary.get("manifest_summary"), dict) else {},
        "read_only_notes": IMPORT_SAFETY_NOTES,
        "boundary_notes": IMPORT_SAFETY_NOTES,
    }


def _summarize_linked_catalog_assets(linked_catalog_assets: list[dict[str, Any]]) -> dict[str, Any]:
    promoter_summary = summarize_linked_plant_promoter_references(linked_catalog_assets)
    host_context_summary = build_host_chassis_context_summary(linked_catalog_assets)
    wizard_traceability = build_expression_wizard_catalog_traceability_summary(linked_catalog_assets)
    pinned_snapshot_count = sum(
        1
        for link in linked_catalog_assets
        if catalog_asset_snapshot_has_content(link.get("asset_snapshot"))
    )
    catalog_summary = {
        "linked_catalog_asset_count": len(linked_catalog_assets),
        "linked_plant_promoter_count": promoter_summary.get("linked_promoter_count", 0),
        "missing_source_or_review_metadata_count": promoter_summary.get("missing_metadata_count", 0),
        "expression_wizard_catalog_reference_count": wizard_traceability.get("reference_count", 0),
        "expression_wizard_plant_promoter_reference_count": wizard_traceability.get("plant_promoter_reference_count", 0),
        "expression_wizard_catalog_missing_metadata_count": wizard_traceability.get("missing_metadata_count", 0),
        "catalog_links_with_pinned_snapshots_count": pinned_snapshot_count,
        "catalog_links_missing_snapshots_count": len(linked_catalog_assets) - pinned_snapshot_count,
        "catalog_links_malformed_snapshot_warning_count": sum(
            1 for link in linked_catalog_assets if link.get("asset_snapshot_warning")
        ),
    }
    return {
        "status": STATUS_AVAILABLE if linked_catalog_assets else STATUS_NOT_AVAILABLE,
        "linked_catalog_asset_count": len(linked_catalog_assets),
        "plant_promoter_reference_summary": promoter_summary,
        "host_chassis_context_summary": host_context_summary,
        "expression_wizard_catalog_traceability": wizard_traceability,
        **catalog_summary,
        "boundary_note": promoter_summary.get("boundary_note"),
        "limitation_note": promoter_summary.get("limitation_note"),
    }


def _gap(gap_id: str, severity: str, summary: str, guidance: str) -> dict[str, str]:
    return {"gap_id": gap_id, "severity": severity, "summary": summary, "user_guidance": guidance}


def _review_gaps(
    project: dict[str, Any],
    identity: dict[str, Any],
    steps: dict[str, Any],
    artifacts: dict[str, Any],
    linked_catalog: dict[str, Any],
    saved: dict[str, Any],
    export: dict[str, Any],
    safety: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not identity["fields"].get("description"):
        gaps.append(_gap("project_description_missing", "INFO", "Project description missing.", "Add a concise documentation project description."))
    if steps.get("count", 0) == 0:
        gaps.append(_gap("no_pathway_steps_documented", "WARNING", "No pathway steps documented.", "Add pathway documentation steps."))
    if artifacts.get("count", 0) == 0:
        gaps.append(_gap("no_linked_documentation_artifacts", "WARNING", "No linked documentation artifacts.", "Link documentation artifacts for traceability."))
    if linked_catalog.get("missing_source_or_review_metadata_count", 0):
        missing_count = linked_catalog.get("missing_source_or_review_metadata_count", 0)
        gaps.append(
            _gap(
                "linked_catalog_reference_metadata_review_needed",
                "WARNING",
                f"{missing_count} linked catalog reference(s) still need source/provenance or manual review follow-up.",
                "Review linked catalog references in the existing review surfaces and record missing source/provenance fields or manual review status before project documentation review.",
            )
        )
    if saved.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_saved_design_snapshot_linked", "INFO", "No saved design snapshot linked.", "Save or link a wizard design snapshot when needed."))
    if export.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_export_package_status_recorded", "INFO", "No export package status recorded.", "Export a documentation-only project package when needed."))
    if safety.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_import_safety_check_report_attached", "INFO", "No import safety check report attached.", "Run Import Package Safety Check on an exported package for read-only review."))
    if not _first_present(project, ("review_notes", "notes")):
        gaps.append(_gap("review_notes_missing", "INFO", "Review notes missing.", "Add review notes, unresolved items, or follow-up actions."))
    return gaps


def _checklist_item(item_id: str, label: str, status: str, summary: str, guidance: str) -> dict[str, str]:
    return {"item_id": item_id, "label": label, "status": status, "summary": summary, "user_guidance": guidance}


def _documentation_completeness(
    project: dict[str, Any],
    identity: dict[str, Any],
    steps: dict[str, Any],
    artifacts: dict[str, Any],
    linked_catalog: dict[str, Any],
    saved: dict[str, Any],
    export: dict[str, Any],
    safety: dict[str, Any],
) -> list[dict[str, str]]:
    notes_available = bool(_first_present(project, ("review_notes", "notes")))
    missing_catalog_metadata_count = linked_catalog.get("missing_source_or_review_metadata_count", 0)
    return [
        _checklist_item("project_identity_documented", "Project identity documented", STATUS_COMPLETE if not identity.get("missing_fields") else STATUS_MISSING, "Project identity fields are summarized for documentation review.", "Fill missing project identity fields."),
        _checklist_item("pathway_steps_documented", "Pathway steps documented", STATUS_COMPLETE if steps.get("count", 0) else STATUS_MISSING, f"Pathway steps count: {steps.get('count', 0)}.", "Add pathway documentation steps."),
        _checklist_item("linked_documentation_artifacts_attached", "Linked documentation artifacts attached", STATUS_COMPLETE if artifacts.get("count", 0) else STATUS_MISSING, f"Linked artifacts count: {artifacts.get('count', 0)}.", "Link documentation artifacts for traceability."),
        _checklist_item(
            "linked_catalog_reference_metadata_reviewed",
            "Linked catalog reference metadata reviewed",
            STATUS_COMPLETE if missing_catalog_metadata_count == 0 else STATUS_NEEDS_REVIEW,
            "Linked catalog reference source/provenance and manual review status are recorded."
            if missing_catalog_metadata_count == 0
            else f"Linked catalog references with source/provenance or manual review gaps: {missing_catalog_metadata_count}.",
            "Review linked catalog references and record missing source/provenance fields or manual review status when needed.",
        ),
        _checklist_item("saved_design_snapshot_linked_or_traceable", "Saved design snapshot linked or traceable", STATUS_COMPLETE if saved.get("status") == STATUS_AVAILABLE else STATUS_NOT_AVAILABLE, saved.get("message") or "Saved design snapshot metadata is available.", "Link snapshots only when traceability is needed."),
        _checklist_item("export_package_status_available", "Export package status available", STATUS_COMPLETE if export.get("status") != STATUS_NOT_AVAILABLE else STATUS_NOT_AVAILABLE, export.get("message") or "Export package status is available.", "Generate a documentation-only export package when needed."),
        _checklist_item("import_package_safety_check_available", "Import package safety check available", STATUS_COMPLETE if safety.get("status") != STATUS_NOT_AVAILABLE else STATUS_NOT_AVAILABLE, safety.get("message") or "Import package safety check summary is available.", "Use read-only import safety checks for package review."),
        _checklist_item("review_notes_available", "Review notes available", STATUS_COMPLETE if notes_available else STATUS_MISSING, "Review notes are present." if notes_available else "Review notes are missing.", "Add human review notes or follow-up actions."),
        _checklist_item("boundary_notes_visible", "Boundary notes visible", STATUS_COMPLETE, "Dashboard safety and documentation boundaries are visible.", "Keep boundary notes visible in user-facing review views."),
    ]


def _review_guidance(gaps: list[dict[str, str]]) -> list[str]:
    guidance = [
        "Generate a Project Review Report.",
        "Export a documentation-only project package.",
        "Run Import Package Safety Check on an exported package for read-only review.",
    ]
    gap_ids = {gap["gap_id"] for gap in gaps}
    if "no_pathway_steps_documented" in gap_ids:
        guidance.insert(0, "Add pathway documentation steps.")
    if "no_linked_documentation_artifacts" in gap_ids:
        guidance.insert(1, "Link documentation artifacts for traceability.")
    if "linked_catalog_reference_metadata_review_needed" in gap_ids:
        guidance.insert(2, "Review linked catalog references for source/provenance gaps and manual review status.")
    if "no_saved_design_snapshot_linked" in gap_ids:
        guidance.insert(3, "Save or link a wizard design snapshot when needed.")
    return guidance


def build_project_quality_dashboard(
    project: dict[str, Any] | None,
    linked_artifacts: list[dict[str, Any]] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
    saved_designs: list[dict[str, Any]] | None = None,
    export_summary: dict[str, Any] | None = None,
    import_safety_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only documentation completeness dashboard for a pathway project."""
    project_data = project if isinstance(project, dict) else {}
    step_list = [item for item in _as_list(project_data.get("steps") or project_data.get("pathway_steps")) if isinstance(item, dict)]
    artifact_list = [item for item in _as_list(linked_artifacts) if isinstance(item, dict)]
    linked_catalog_asset_list = [item for item in _as_list(linked_catalog_assets) if isinstance(item, dict)]
    project_id = _first_present(project_data, ("project_id", "id"))
    if project_id not in (None, ""):
        try:
            persisted_catalog_links = project_catalog_link_repo.list_project_catalog_asset_links(project_id)
        except Exception:
            persisted_catalog_links = []
        linked_catalog_asset_list = merge_project_asset_links(
            persisted_catalog_links,
            linked_catalog_asset_list,
        )
    saved_design_list = [item for item in _as_list(saved_designs) if isinstance(item, dict)]

    identity = _project_identity(project_data)
    steps = _summarize_steps(step_list)
    artifacts = _summarize_artifacts(artifact_list)
    linked_catalog = _summarize_linked_catalog_assets(linked_catalog_asset_list)
    host_context = build_host_chassis_context_summary(project_data, linked_catalog_asset_list)
    saved = _summarize_saved_designs(saved_design_list)
    export = _summarize_export(export_summary)
    safety = _summarize_import_safety(import_safety_summary)
    package_exchange_trail = build_package_exchange_review_trail(export, safety)
    gaps = _review_gaps(project_data, identity, steps, artifacts, linked_catalog, saved, export, safety)
    blocking_gaps = [gap for gap in gaps if gap["severity"] == "WARNING"]

    if not project_data:
        overall_status = STATUS_NOT_AVAILABLE
    elif blocking_gaps:
        overall_status = STATUS_NEEDS_DOCUMENTATION
    elif gaps:
        overall_status = STATUS_NEEDS_REVIEW
    else:
        overall_status = STATUS_COMPLETE_ENOUGH_FOR_REVIEW

    review_guidance = _review_guidance(gaps)

    dashboard = {
        "dashboard_title": DASHBOARD_TITLE,
        "dashboard_version": DASHBOARD_VERSION,
        "generated_at": _now_iso(),
        "overall_documentation_status": overall_status,
        "project_identity": identity,
        "metrics": {
            "pathway_steps_count": steps.get("count", 0),
            "linked_artifacts_count": artifacts.get("count", 0),
            "linked_catalog_assets_count": linked_catalog.get("linked_catalog_asset_count", 0),
            "linked_plant_promoter_profile_count": linked_catalog.get("plant_promoter_reference_summary", {}).get("linked_promoter_count", 0),
            "plant_promoter_missing_metadata_count": linked_catalog.get("plant_promoter_reference_summary", {}).get("missing_metadata_count", 0),
            "linked_host_chassis_context_count": linked_catalog.get("host_chassis_context_summary", {}).get("reference_count", 0),
            "linked_non_plant_host_context_count": linked_catalog.get("host_chassis_context_summary", {}).get("non_plant_context_count", 0),
            "linked_plant_host_context_count": linked_catalog.get("host_chassis_context_summary", {}).get("plant_reference_count", 0),
            "linked_catalog_reference_count": linked_catalog.get("linked_catalog_asset_count", 0),
            "linked_plant_promoter_reference_count": linked_catalog.get("linked_plant_promoter_count", 0),
            "missing_source_or_review_metadata_count": linked_catalog.get("missing_source_or_review_metadata_count", 0),
            "host_context_record_count": host_context.get("context_count", 0),
            "expression_wizard_catalog_reference_count": linked_catalog.get("expression_wizard_catalog_reference_count", 0),
            "expression_wizard_plant_promoter_reference_count": linked_catalog.get("expression_wizard_plant_promoter_reference_count", 0),
            "expression_wizard_catalog_missing_metadata_count": linked_catalog.get("expression_wizard_catalog_missing_metadata_count", 0),
            "catalog_links_with_pinned_snapshots_count": linked_catalog.get("catalog_links_with_pinned_snapshots_count", 0),
            "catalog_links_missing_snapshots_count": linked_catalog.get("catalog_links_missing_snapshots_count", 0),
            "catalog_links_malformed_snapshot_warning_count": linked_catalog.get("catalog_links_malformed_snapshot_warning_count", 0),
            "saved_design_snapshots_count": saved.get("count", 0),
            "review_gap_count": len(gaps),
            "blocking_documentation_gap_count": len(blocking_gaps),
            "warning_gap_count": len(blocking_gaps),
            "import_safety_status_available": safety.get("status") != STATUS_NOT_AVAILABLE,
            "export_status_available": export.get("status") != STATUS_NOT_AVAILABLE,
        },
        "documentation_completeness": _documentation_completeness(project_data, identity, steps, artifacts, linked_catalog, saved, export, safety),
        "pathway_steps_status": steps,
        "linked_artifacts_status": artifacts,
        "linked_catalog_assets_status": linked_catalog,
        "host_chassis_context_status": host_context,
        "saved_design_snapshot_status": saved,
        "export_package_status": export,
        "import_safety_status": safety,
        "package_exchange_review_trail": package_exchange_trail,
        "review_gaps": gaps,
        "review_guidance": review_guidance,
        "next_actions": review_guidance,
        "boundary_notes": BOUNDARY_NOTES,
    }

    dashboard = normalize_generated_output_claims(dashboard)
    assert_no_misleading_generated_claims(dashboard, context="dashboard")
    return dashboard
