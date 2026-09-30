from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from services.ai_literature_research_service import (
    LiteratureResearchBrief,
    generate_literature_research_brief,
    unavailable_state,
)
from services import expression_construct_presenter
from services.catalog_asset_snapshot_builder import catalog_asset_snapshot_has_content
from services.candidate_evidence_human_review_queue import (
    build_candidate_evidence_human_review_queue,
)
from services.candidate_evidence_review_matrix import build_candidate_evidence_review_matrix
from services.component_library_asset_readback_presenter import (
    build_component_library_asset_readback_presenter,
)
from services.component_library_followup_queue_presenter import (
    FOLLOWUP_QUEUE_COLUMNS,
    build_component_library_followup_queue_presenter,
)
from services.documentation_review_label_helper import REVIEW_NEXT_COLUMN_LABEL
from services.expression_wizard_catalog_picker_presenter import build_expression_wizard_catalog_traceability_summary
from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
    normalize_generated_output_text,
)
from services import plant_promoter_catalog_presenter
from services import plant_promoter_evidence_gap_review_queue as plant_promoter_gap_queue
from services.host_chassis_context_presenter import build_host_chassis_context_summary
from services.local_design_asset_catalog_service import (
    load_seed_records,
    summarize_counts_by_asset_type,
    summarize_review_status,
)
from services.project_asset_linkage_service import (
    list_project_asset_links,
    report_links_needing_review,
    summarize_project_asset_links,
)
from services.project_catalog_reference_output_formatter import (
    build_linked_catalog_reference_output,
    has_staged_basket_only_markers,
)
from services.project_package_review_trail_service import build_package_exchange_review_trail
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
    project_output_boundary_notes,
)
from services.project_output_section_overview import (
    build_project_output_sections_overview,
    format_project_output_sections_overview_markdown,
)
from services.plant_design_review_package_service import (
    build_plant_design_review_package,
    format_plant_design_review_package_markdown,
)
from services.project_review_target_preview_adapter import build_project_review_target_preview_section
from services.report_identity_presenter import (
    build_report_identity_block,
    build_report_visual_narrative,
    format_report_identity_markdown,
    format_report_visual_narrative_markdown,
)
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.plant_promoter_catalog_workspace_presenter import summarize_linked_plant_promoter_references
from services.placeholder_review_value import clean_review_value, has_recorded_review_value
from services.project_review_follow_up_index import build_project_review_follow_up_index
from services.project_review_handoff_center_service import build_project_review_handoff_center
from services.project_handoff_package_preview_service import build_project_handoff_package_preview

REPORT_TITLE = "Project Review Report"
REPORT_VERSION = "1.0"
DETAILED_DOCUMENTATION_REPORT_TITLE = "Detailed Documentation Report Draft"
STATUS_AVAILABLE = "AVAILABLE"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
STATUS_WARNING = "WARNING"

BOUNDARY_NOTES = [
    PROJECT_OUTPUT_SCOPE_NOTE,
    "This report is documentation-only.",
    "This report summarizes review records and computational previews only.",
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    "This report does not forecast yield.",
    "This report does not tune pathways.",
    "This report does not provide wet-lab instructions.",
    "Import Preview is read-only and does not create a project by itself.",
    "Import execution is documentation-only.",
    "Blocked / NO-GO import states apply only to the gated create-as-new action.",
    "Allowed import execution creates a new project record instead of overwriting or merging existing projects.",
    "Any allowed import-as-new action is documentation-only, gated by explicit confirmation, and creates a new local project instead of overwriting or merging existing projects.",
]

_LINKED_ARTIFACT_BOUNDARY_NOTES = [
    "Linked artifacts are documentation records for traceability only.",
    "They do not certify downstream use state or experimental evidence.",
]

_LINKED_CATALOG_ASSET_BOUNDARY_NOTES = [
    "Linked catalog assets are documentation references only.",
    "They do not indicate biological fit, source verification, or downstream use state.",
    "Human review is required before downstream use.",
]

_COMPONENT_LIBRARY_ASSET_READBACK_REPORT_BOUNDARY_NOTES = [
    "Component Library asset readback snapshot is documentation-only report context.",
    "It reuses existing linked catalog asset rows and construct component rows only.",
    "Construct component rows are documentation records only, not biological proof records.",
    "Type-specific Component Library readback fields are intentionally deferred.",
]

_COMPONENT_LIBRARY_FOLLOWUP_QUEUE_REPORT_BOUNDARY_NOTES = [
    "Component Library follow-up queue report readback is documentation-only report context.",
    "It reuses the existing source/provenance follow-up queue presenter output.",
    "Follow-up rows are read-only review prompts for existing records.",
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    "This readback does not create component records, select components, validate constructs, claim improved pathways, generate sequences, or judge downstream use.",
]

_EXPRESSION_CONSTRUCT_BOUNDARY_NOTES = [
    "Expression construct documentation is documentation-only context for review and traceability.",
    "Expression Construct Documentation summarizes saved construct records and source/provenance context.",
    "Construct component rows record documented labels, categories, source/reference context, sequence availability status, and review gaps only.",
    "Construct component readback is recorded construct documentation, not validation, selection advice, or a downstream-use state decision.",
    "Promoter source links are evidence and provenance context, not selection advice.",
    "This section is not a biology-use recommendation, validation claim, outcome-improvement claim, or wet-lab use judgment.",
    "This section does not choose, rate, order, tune, forecast, verify, or certify downstream-use state for any construct, cassette, promoter, gene, pathway step, or report output.",
]

_PROTEIN_EXPRESSION_BOUNDARY_NOTES = [
    "Protein expression documentation readback is documentation-only context for review and traceability.",
    "This section reads existing project, construct profile, cassette, cassette part, linked gene, host/chassis, catalog reference, and review-gap records only.",
    "It is not a biological instruction, forecast, or downstream-use judgment.",
    "Signal, secretion, marker, vector, or backbone context appears only when previously recorded in existing notes or metadata.",
]

_HUMAN_REVIEW_QUEUE_BOUNDARY_NOTES = [
    "This section supports manual documentation review only.",
    "It does not rank, recommend, validate, tune, or confirm biological suitability.",
]

_PLANT_PROMOTER_EVIDENCE_GAP_BOUNDARY_NOTES = [
    "This section supports human documentation review and catalog curation only.",
    "It does not recommend, rank, validate, predict, tune, or confirm promoter suitability.",
]

_FOLLOW_UP_INDEX_BOUNDARY_NOTES = [
    "This index supports manual documentation review and triage only.",
    "It aggregates documentation and provenance follow-up items from existing read-only review queues.",
]

_HANDOFF_CENTER_BOUNDARY_NOTES = [
    *project_output_boundary_notes(include_no_data_change=True),
    "This handoff center is documentation-only and read-only.",
    "It aggregates existing review queues and documentation gaps without changing project data.",
]

_STEP2_COMPONENT_CONTEXT_APPENDIX_BOUNDARY_NOTES = [
    "Step 2 recorded Component Library context appendix is documentation-only review context.",
    "The appendix is read-only review appendix content from the current in-memory Wizard session when supplied.",
    "It is not saved as construct evidence, Wizard saved state, database data, Dashboard gap data, or package data.",
    "It is not a biological recommendation, validation claim, outcome-improvement claim, or wet-lab readiness judgment.",
]

_STEP2_COMPONENT_CONTEXT_EMPTY_APPENDIX_BOUNDARY_NOTES = [
    "Step 2 recorded Component Library context appendix is documentation-only review context.",
    "No current in-memory Step 2 Component Library context was supplied for this appendix.",
    "No construct evidence, Wizard saved state, database data, Dashboard gap data, or package data is changed.",
    "The empty appendix does not provide biological selection guidance, validation claims, outcome-improvement claims, or wet-lab readiness judgments.",
]

EXPRESSION_CONSTRUCT_SECTION_COPY = (
    "Expression Construct Documentation summarizes saved construct records and source/provenance context."
)

_SAVED_DESIGN_BOUNDARY_NOTES = [
    "Saved design snapshot restores wizard inputs and outputs only.",
    "It does not create or select a pathway project automatically.",
]

_IMPORT_SAFETY_BOUNDARY_NOTES = [
    "Import package safety checks are read-only.",
    "They do not import or modify any project.",
    "No database writes are performed.",
]

_PROTEIN_EXPRESSION_UNSAFE_PHRASES = (
    "recommended",
    "recommend",
    "validate",
    "validated",
    "validation",
    "opti" + "mize",
    "opti" + "mized",
    "optimi" + "zation",
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


def _clean_text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _review_text(value: Any, fallback: str = "") -> str:
    return clean_review_value(value, fallback)


def _review_items(value: Any) -> list[str]:
    return [clean for item in _as_list(value) if (clean := _review_text(item, ""))]


def _first_recorded_review_value(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if isinstance(value, (list, tuple)):
            if _review_items(value):
                return value
            continue
        if has_recorded_review_value(value):
            return value
    return None


def _sanitize_protein_expression_readback_text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    text = normalize_generated_output_text(_clean_text(value, fallback))
    for phrase in _PROTEIN_EXPRESSION_UNSAFE_PHRASES:
        pattern = re.escape(phrase)
        if phrase.replace("-", "").replace(" ", "").isalpha():
            pattern = rf"\b{pattern}\b"
        text = re.sub(pattern, "[context term withheld for documentation review]", text, flags=re.IGNORECASE)
    return text


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
        "active_project_status": _first_present(project, ("active_project_status", "status")),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "description": _first_present(project, ("description", "project_description")),
    }
    missing = [key for key, value in fields.items() if value in (None, "")]
    return {
        "status": STATUS_WARNING if missing else STATUS_AVAILABLE,
        "fields": fields,
        "missing_fields": missing,
    }


def _project_summary(project: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "target_product": project.get("target_product"),
        "host": project.get("host"),
        "organism": _first_present(project, ("organism", "organism_source")),
        "notes": _first_recorded_review_value(project, ("notes", "review_notes")),
    }
    return {"status": STATUS_AVAILABLE, "fields": fields}


def _documentation_review(project: dict[str, Any]) -> dict[str, Any]:
    value = project.get("documentation_review")
    return value if isinstance(value, dict) else {}


def _review_notes(project: dict[str, Any]) -> list[str]:
    documentation_review = _documentation_review(project)
    notes: list[str] = []

    review_note = _first_recorded_review_value(documentation_review, ("review_notes",))
    if review_note:
        notes.append(_review_text(review_note))

    reviewer = _first_recorded_review_value(documentation_review, ("reviewer", "reviewer_name", "reviewer_initials"))
    review_date = _first_recorded_review_value(documentation_review, ("review_date", "reviewed_at", "updated_at"))
    if reviewer:
        notes.append(f"Reviewer: {_review_text(reviewer)}")
    if review_date:
        notes.append(f"Review date: {_review_text(review_date)}")

    follow_up_actions = _review_items(documentation_review.get("follow_up_actions"))
    if follow_up_actions:
        notes.append("Follow-up actions:")
        notes.extend(f"  - {action}" for action in follow_up_actions)

    unresolved_items = _review_items(documentation_review.get("unresolved_items"))
    if unresolved_items:
        notes.append("Unresolved documentation items:")
        notes.extend(f"  - {item}" for item in unresolved_items)

    if notes:
        return notes

    legacy_note = _first_recorded_review_value(project, ("review_notes", "notes"))
    if legacy_note:
        return [_review_text(legacy_note)]

    return ["No review notes are recorded."]


def _has_review_content(project: dict[str, Any]) -> bool:
    documentation_review = _documentation_review(project)
    if any(
        _first_recorded_review_value(documentation_review, (key,))
        for key in ("review_notes", "follow_up_actions", "unresolved_items")
    ):
        return True
    return bool(_first_recorded_review_value(project, ("review_notes", "notes")))


def _pathway_steps_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not steps:
        return {
            "status": STATUS_WARNING,
            "step_count": 0,
            "steps": [],
            "message": "No pathway steps are documented yet.",
            "guidance": "Add pathway documentation steps before treating this project record as complete.",
        }

    summarized_steps = []
    for index, step in enumerate(steps, start=1):
        title = _first_present(step, ("step_name", "title", "reaction_name", "name")) or f"Step {index}"
        fields = {
            "step_id": _first_present(step, ("step_id", "id")),
            "step_order": step.get("step_order") or index,
            "title": title,
            "organism": _first_present(step, ("organism", "organism_source", "source_organism")),
            "enzyme": _first_present(step, ("enzyme", "enzyme_name")),
            "gene": _first_present(step, ("gene", "gene_name")),
            "metabolite": _first_present(step, ("metabolite", "substrate", "product")),
            "reaction_name": step.get("reaction_name"),
            "notes": step.get("notes"),
        }
        missing = [key for key in ("title", "organism", "enzyme", "gene", "metabolite") if fields.get(key) in (None, "")]
        summarized_steps.append({"status": STATUS_WARNING if missing else STATUS_AVAILABLE, "fields": fields, "missing_fields": missing})

    return {"status": STATUS_AVAILABLE, "step_count": len(summarized_steps), "steps": summarized_steps}


def _linked_artifacts_summary(linked_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    if not linked_artifacts:
        return {
            "status": STATUS_WARNING,
            "artifact_count": 0,
            "artifacts": [],
            "message": "No linked documentation artifacts are attached to this project yet.",
            "boundary_notes": _LINKED_ARTIFACT_BOUNDARY_NOTES,
        }
    artifacts = []
    for artifact in linked_artifacts:
        raw_payload_available = any(key in artifact for key in ("payload_json", "raw_payload", "payload"))
        artifacts.append(
            {
                "artifact_id": _first_present(artifact, ("artifact_id", "id")),
                "artifact_type": _first_present(artifact, ("artifact_type", "type")),
                "source": _first_present(artifact, ("source", "source_module")),
                "title": _first_present(artifact, ("title", "name")),
                "created_at": artifact.get("created_at"),
                "linked_project_id": _first_present(artifact, ("linked_project_id", "project_id")),
                "raw_payload_status": "PRESENT_NOT_EXPANDED" if raw_payload_available else STATUS_NOT_AVAILABLE,
            }
        )
    return {
        "status": STATUS_AVAILABLE,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "traceability_note": "Linked artifacts are documentation records for traceability only.",
        "boundary_notes": _LINKED_ARTIFACT_BOUNDARY_NOTES,
    }


def _saved_design_snapshot_summary(saved_designs: list[dict[str, Any]]) -> dict[str, Any]:
    if not saved_designs:
        return {
            "status": STATUS_NOT_AVAILABLE,
            "message": "No saved design snapshot is linked to this pathway project.",
            "guidance": "Load or save wizard snapshots separately; link artifacts or records only when traceability is needed.",
            "snapshots": [],
            "boundary_notes": _SAVED_DESIGN_BOUNDARY_NOTES,
        }
    snapshots = []
    for design in saved_designs:
        snapshots.append(
            {
                "design_id": _first_present(design, ("design_id", "id")),
                "display_name": _first_present(design, ("display_name", "name", "title")),
                "source_saved_design_id": design.get("source_saved_design_id"),
                "saved_design_version": _first_present(design, ("saved_design_version", "version")),
                "identity_source": _first_present(design, ("identity_source", "source")),
            }
        )
    return {"status": STATUS_AVAILABLE, "snapshot_count": len(snapshots), "snapshots": snapshots, "boundary_notes": _SAVED_DESIGN_BOUNDARY_NOTES}


def _export_package_summary(export_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not export_summary:
        return {
            "status": STATUS_NOT_AVAILABLE,
            "message": "No export package status is recorded in this project review report.",
            "guidance": "Use the documentation-only project export package preview when a review package is needed.",
            "documentation_only_boundary": "Export packages are documentation-only review packages.",
        }
    return {
        "status": export_summary.get("status") or STATUS_AVAILABLE,
        "package_contents_preview_status": export_summary.get("package_contents_preview_status") or export_summary.get("contents_preview_status") or STATUS_AVAILABLE,
        "last_export_status": export_summary.get("last_export_status") or STATUS_NOT_AVAILABLE,
        "documentation_only_boundary": export_summary.get("documentation_only_boundary") or "Export packages are documentation-only review packages.",
    }


def _import_safety_summary(import_safety_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not import_safety_summary:
        return {
            "status": STATUS_NOT_AVAILABLE,
            "message": "No import package safety check report is attached to this project review report.",
            "guidance": "Attach a read-only Import Package Safety Check Report when reviewing an exported package.",
            "boundary_notes": _IMPORT_SAFETY_BOUNDARY_NOTES,
        }
    check_items = _as_list(import_safety_summary.get("check_items"))
    not_evaluated_count = sum(1 for item in check_items if isinstance(item, dict) and item.get("status") == "NOT_EVALUATED")
    return {
        "status": import_safety_summary.get("status") or STATUS_AVAILABLE,
        "overall_status": import_safety_summary.get("overall_status") or STATUS_NOT_AVAILABLE,
        "blocking_issue_count": len(_as_list(import_safety_summary.get("blocking_issues"))),
        "warning_count": len(_as_list(import_safety_summary.get("warnings"))),
        "not_evaluated_count": import_safety_summary.get("not_evaluated_count", not_evaluated_count),
        "manifest_summary": import_safety_summary.get("manifest_summary") if isinstance(import_safety_summary.get("manifest_summary"), dict) else {},
        "read_only_notes": _IMPORT_SAFETY_BOUNDARY_NOTES,
        "boundary_notes": _IMPORT_SAFETY_BOUNDARY_NOTES,
    }


def _gap(gap_id: str, severity: str, summary: str, guidance: str) -> dict[str, str]:
    return {"gap_id": gap_id, "severity": severity, "summary": summary, "user_guidance": guidance}


def _missing_fields(
    project_identity: dict[str, Any],
    steps: dict[str, Any],
    artifacts: dict[str, Any],
    linked_catalog_assets: dict[str, Any],
    saved_designs: dict[str, Any],
    export_summary: dict[str, Any],
    import_safety: dict[str, Any],
    project: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not project_identity["fields"].get("description"):
        gaps.append(_gap("project_description_missing", "INFO", "Project description missing.", "Add a concise documentation project description."))
    if steps.get("step_count", 0) == 0:
        gaps.append(_gap("no_pathway_steps_documented", "WARNING", "No pathway steps documented.", "Add pathway documentation steps before review completion."))
    if artifacts.get("artifact_count", 0) == 0:
        gaps.append(_gap("no_linked_documentation_artifacts", "WARNING", "No linked documentation artifacts.", "Link documentation artifacts when traceability is needed."))
    if linked_catalog_assets.get("missing_source_or_review_metadata_count", 0):
        missing_count = linked_catalog_assets.get("missing_source_or_review_metadata_count", 0)
        gaps.append(
            _gap(
                "linked_catalog_reference_metadata_review_needed",
                "WARNING",
                f"{missing_count} linked catalog reference(s) still need source/provenance or record review follow-up.",
                "Review linked catalog references and record missing source/provenance fields or record review status before using them in report-facing documentation context.",
            )
        )
    if saved_designs.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_saved_design_snapshot_linked", "INFO", "No saved design snapshot linked.", "Link a saved design snapshot only when identity traceability is needed."))
    if export_summary.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_export_package_status_recorded", "INFO", "No export package status recorded.", "Generate an export preview/package when a review artifact is needed."))
    if import_safety.get("status") == STATUS_NOT_AVAILABLE:
        gaps.append(_gap("no_import_safety_check_report_attached", "INFO", "No import safety check report attached.", "Attach a read-only safety check report for imported packages."))
    if not _has_review_content(project):
        gaps.append(_gap("review_notes_missing", "INFO", "Review notes missing.", "Add human review notes, unresolved items, or follow-up actions."))
    return gaps


def _package_exchange_review_trail(export_summary: dict[str, Any], import_safety: dict[str, Any]) -> dict[str, Any]:
    return build_package_exchange_review_trail(export_summary, import_safety)


def _row_text(row: dict[str, Any], key: str, fallback: str = "") -> str:
    return _clean_text(row.get(key), fallback)


def _pathway_step_ids(project: dict[str, Any], steps: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = _first_present(step, ("step_id", "id", "pathway_step_id"))
        if step_id not in (None, ""):
            ids.add(_clean_text(step_id, ""))
    for key in ("pathway_step_ids", "linked_pathway_step_ids"):
        for value in _as_list(project.get(key)):
            clean = _clean_text(value, "")
            if clean:
                ids.add(clean)
    return ids


def _construct_summary_counts(section_rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {
        "construct_profile_count": len(section_rows["construct_profile_rows"]),
        "cassette_count": len(section_rows["cassette_rows"]),
        "cassette_part_count": len(section_rows["cassette_part_rows"]),
        "gene_link_count": len(section_rows["linked_gene_rows"]),
        "pathway_step_link_count": len(section_rows["linked_pathway_step_rows"]),
        "project_link_count": len(section_rows["project_link_rows"]),
        "review_gap_count": len(section_rows["review_gap_rows"]),
    }


def _construct_component_manual_follow_up_readback(gap_queue_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in _as_list(gap_queue_rows) if isinstance(row, dict)]
    role_issue_type = expression_construct_presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE
    duplicate_issue_type = expression_construct_presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE
    conservation_issue_type = expression_construct_presenter.CONSERVATION_REVIEW_ISSUE_TYPE
    role_count = sum(1 for row in rows if _clean_text(row.get("Issue type"), "") == role_issue_type)
    duplicate_count = sum(1 for row in rows if _clean_text(row.get("Issue type"), "") == duplicate_issue_type)
    conservation_count = sum(1 for row in rows if _clean_text(row.get("Issue type"), "") == conservation_issue_type)
    total_count = len(rows)
    return {
        "status": STATUS_AVAILABLE if rows else STATUS_NOT_AVAILABLE,
        "title": "Construct component manual follow-up readback",
        "total_manual_follow_up_items": total_count,
        "role_label_review_count": role_count,
        "duplicate_label_review_count": duplicate_count,
        "conservation_review_follow_up_count": conservation_count,
        "other_documentation_follow_up_count": max(total_count - role_count - duplicate_count - conservation_count, 0),
        "manual_review_boundary": (
            "Manual documentation review only; preserves existing component-row follow-up detection and ordering."
        ),
        "clarity_notes": [
            "Role-label review rows mean the component role is missing or recorded as other documented component.",
            (
                "Duplicate-label review rows mean the same visible component label appears more than once in the "
                "same construct/cassette documentation context."
            ),
            (
                "Conservation review rows mean source organism/source context, sequence source, literature or "
                "database evidence, conservation note, or manual reviewer note still needs documentation review."
            ),
            "This readback does not add gap types, biological scoring, or documentation follow-up status judgments.",
        ],
    }


def _empty_construct_documentation_summary(project_scoped_filtering: str) -> dict[str, Any]:
    rows = {
        "construct_profile_rows": [],
        "cassette_rows": [],
        "cassette_part_rows": [],
        "construct_component_rows": [],
        "construct_component_gap_queue": [],
        "linked_gene_rows": [],
        "linked_pathway_step_rows": [],
        "project_link_rows": [],
        "review_gap_rows": [],
    }
    return {
        "status": STATUS_NOT_AVAILABLE,
        "section_title": "Expression Construct Documentation",
        "summary_counts": _construct_summary_counts(rows),
        **rows,
        "construct_component_review_summary": expression_construct_presenter.build_construct_component_review_summary([], []),
        "construct_component_manual_follow_up_readback": _construct_component_manual_follow_up_readback([]),
        "part_role_counts": {},
        "message": "No expression construct documentation records are available for this report.",
        "project_scoped_filtering": project_scoped_filtering,
        "boundary_notes": _EXPRESSION_CONSTRUCT_BOUNDARY_NOTES,
    }


def _construct_documentation_summary(project: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    project_step_ids = _pathway_step_ids(project, steps)
    project_id = _clean_text(_first_present(project, ("project_id", "id")), "")
    explicit_project_views = (
        expression_construct_presenter.build_expression_construct_report_views(project_id=project_id)
        if project_id
        else []
    )
    report_views = explicit_project_views or expression_construct_presenter.build_expression_construct_report_views()
    if not report_views:
        return _empty_construct_documentation_summary("no construct profiles available")

    selected_views: list[dict[str, Any]] = []
    project_scoped_filtering = (
        "project-level construct links"
        if explicit_project_views
        else "deferred: no project-scoped construct profile link is recorded"
    )
    for view in report_views:
        if explicit_project_views:
            selected_views.append(view)
            continue
        pathway_links = [
            row
            for row in _as_list(view.get("linked_pathway_step_rows"))
            if isinstance(row, dict)
        ]
        if project_step_ids:
            matching_links = [
                row
                for row in pathway_links
                if _row_text(row, "pathway_step_id") in project_step_ids
            ]
            if not matching_links:
                continue
            scoped_view = dict(view)
            scoped_view["linked_pathway_step_rows"] = matching_links
            selected_views.append(scoped_view)
            project_scoped_filtering = "pathway_step_id links"
        else:
            selected_views.append(view)

    if project_step_ids and not selected_views:
        summary = _empty_construct_documentation_summary("pathway_step_id links")
        summary["status"] = STATUS_NOT_AVAILABLE
        summary["message"] = "No expression construct rows are linked to the supplied pathway step identifiers."
        return summary

    rows = {
        "construct_profile_rows": [],
        "cassette_rows": [],
        "cassette_part_rows": [],
        "construct_component_rows": [],
        "construct_component_gap_queue": [],
        "linked_gene_rows": [],
        "linked_pathway_step_rows": [],
        "project_link_rows": [],
        "review_gap_rows": [],
    }
    part_role_counts: dict[str, int] = {}
    supported_component_vocabulary: list[str] = []
    for view in selected_views:
        for key in rows:
            rows[key].extend(
                row
                for row in _as_list(view.get(key))
                if isinstance(row, dict)
            )
        for role, count in dict(view.get("part_role_counts") or {}).items():
            role_key = _clean_text(role, "other")
            part_role_counts[role_key] = part_role_counts.get(role_key, 0) + int(count or 0)
        for label in _as_list(view.get("supported_component_vocabulary")):
            clean_label = _clean_text(label, "")
            if clean_label and clean_label not in supported_component_vocabulary:
                supported_component_vocabulary.append(clean_label)

    return {
        "status": STATUS_AVAILABLE,
        "section_title": "Expression Construct Documentation",
        "summary_counts": _construct_summary_counts(rows),
        **rows,
        "construct_component_review_summary": expression_construct_presenter.build_construct_component_review_summary(
            rows["construct_component_rows"],
            rows["construct_component_gap_queue"],
        ),
        "construct_component_manual_follow_up_readback": _construct_component_manual_follow_up_readback(
            rows["construct_component_gap_queue"]
        ),
        "part_role_counts": part_role_counts,
        "supported_component_vocabulary": supported_component_vocabulary,
        "message": "",
        "project_scoped_filtering": project_scoped_filtering,
        "boundary_notes": _EXPRESSION_CONSTRUCT_BOUNDARY_NOTES,
    }


def _protein_expression_documentation_readback(
    project: dict[str, Any],
    constructs: dict[str, Any],
    host_context: dict[str, Any],
    linked_catalog_assets: dict[str, Any],
) -> dict[str, Any]:
    summary_counts = constructs.get("summary_counts") if isinstance(constructs.get("summary_counts"), dict) else {}
    has_records = any(
        int(summary_counts.get(key, 0) or 0) > 0
        for key in (
            "construct_profile_count",
            "cassette_count",
            "cassette_part_count",
            "gene_link_count",
            "project_link_count",
            "review_gap_count",
        )
    )
    if not has_records:
        return {
            "status": STATUS_NOT_AVAILABLE,
            "section_title": "Protein Expression Documentation Readback",
            "message": "No protein expression construct or cassette documentation rows are available for this readback.",
            "documentation_mode": "protein_expression_context",
            "target_context": {},
            "host_chassis_context": {},
            "construct_profiles": [],
            "cassette_summary_rows": [],
            "cassette_part_rows": [],
            "linked_gene_rows": [],
            "existing_note_context_rows": [],
            "catalog_reference_summary": {},
            "review_gap_rows": [],
            "boundary_notes": _PROTEIN_EXPRESSION_BOUNDARY_NOTES,
        }

    target_context = {
        "target_protein": _sanitize_protein_expression_readback_text(
            _first_present(project, ("target_protein", "protein_target", "target_product", "name", "project_name")),
            "NOT_AVAILABLE",
        ),
        "linked_gene_context": _compact_summary(
            [
                _sanitize_protein_expression_readback_text(row.get("gene_label"), "")
                for row in constructs.get("linked_gene_rows") or []
                if isinstance(row, dict) and _sanitize_protein_expression_readback_text(row.get("gene_label"), "")
            ]
        ),
        "cds_context": _compact_summary(
            [
                _sanitize_protein_expression_readback_text(row.get("part_label"), "")
                for row in constructs.get("cassette_part_rows") or []
                if isinstance(row, dict) and _sanitize_protein_expression_readback_text(row.get("part_role"), "").lower() == "cds"
            ]
        ),
    }
    host_chassis_context = {
        "active_project_context": _sanitize_protein_expression_readback_text(host_context.get("project_context_label"), "Generic / unspecified"),
        "contexts_present": _compact_summary(
            [
                _sanitize_protein_expression_readback_text(label, "")
                for label in host_context.get("contexts_present_labels") or []
                if _sanitize_protein_expression_readback_text(label, "")
            ]
        ),
        "documentation_boundary": _sanitize_protein_expression_readback_text(
            host_context.get("documentation_only_note"),
            "Host / chassis context readback is documentation context only.",
        ),
    }
    cassette_summary_rows = [
        {
            "cassette_label": _sanitize_protein_expression_readback_text(row.get("cassette_label"), "NOT_AVAILABLE"),
            "cassette_role": _sanitize_protein_expression_readback_text(row.get("cassette_role"), "NOT_AVAILABLE"),
            "promoter_label": _sanitize_protein_expression_readback_text(row.get("promoter_label"), "NOT_AVAILABLE"),
            "gene_label": _sanitize_protein_expression_readback_text(row.get("gene_label"), "NOT_AVAILABLE"),
            "terminator_label": _sanitize_protein_expression_readback_text(row.get("terminator_label"), "NOT_AVAILABLE"),
            "source_reference": _sanitize_protein_expression_readback_text(row.get("source_reference"), "NOT_AVAILABLE"),
        }
        for row in constructs.get("cassette_rows") or []
        if isinstance(row, dict)
    ]
    part_rows = [
        {
            "cassette_label": _sanitize_protein_expression_readback_text(row.get("cassette_label"), "NOT_AVAILABLE"),
            "part_role": _sanitize_protein_expression_readback_text(row.get("part_role"), "NOT_AVAILABLE"),
            "part_label": _sanitize_protein_expression_readback_text(row.get("part_label"), "NOT_AVAILABLE"),
            "part_reference": _sanitize_protein_expression_readback_text(row.get("part_reference"), "NOT_AVAILABLE"),
            "source_catalog": _sanitize_protein_expression_readback_text(row.get("source_catalog"), "NOT_AVAILABLE"),
            "source_record_label": _sanitize_protein_expression_readback_text(row.get("source_record_label"), "NOT_AVAILABLE"),
            "evidence_context_note": _sanitize_protein_expression_readback_text(row.get("evidence_context_note"), "NOT_AVAILABLE"),
        }
        for row in constructs.get("cassette_part_rows") or []
        if isinstance(row, dict)
    ]
    note_context_rows: list[dict[str, str]] = []
    note_keywords = ("signal", "secretion", "secretory", "marker", "vector", "backbone")
    note_sources = (
        ("Project notes", _first_present(project, ("notes", "review_notes", "description", "project_description"))),
    )
    for source_label, value in note_sources:
        note_text = _sanitize_protein_expression_readback_text(value, "")
        if note_text and any(keyword in note_text.lower() for keyword in note_keywords):
            note_context_rows.append(
                {
                    "source": source_label,
                    "context": note_text,
                    "boundary": "Existing note context only; documentation context only.",
                }
            )
    for row in constructs.get("construct_profile_rows") or []:
        if not isinstance(row, dict):
            continue
        for key in ("plasmid_backbone", "host_context_note", "source_reference", "provenance_note", "documentation_scope_note"):
            note_text = _sanitize_protein_expression_readback_text(row.get(key), "")
            if note_text and any(keyword in note_text.lower() for keyword in note_keywords):
                note_context_rows.append(
                    {
                        "source": f"Construct profile {key}",
                        "context": note_text,
                        "boundary": "Existing profile context only; documentation context only.",
                    }
                )
    for row in part_rows:
        note_text = " ".join(
            _clean_text(row.get(key), "")
            for key in ("part_role", "part_label", "part_reference", "source_record_label", "evidence_context_note")
        )
        if note_text and any(keyword in note_text.lower() for keyword in note_keywords):
            note_context_rows.append(
                {
                    "source": f"Cassette part {row['part_role']}",
                    "context": note_text,
                    "boundary": "Existing cassette part context only; documentation context only.",
                }
            )

    return {
        "status": STATUS_AVAILABLE,
        "section_title": "Protein Expression Documentation Readback",
        "message": "",
        "documentation_mode": "protein_expression_context",
        "target_context": target_context,
        "host_chassis_context": host_chassis_context,
        "construct_profiles": list(constructs.get("construct_profile_rows") or []),
        "cassette_summary_rows": cassette_summary_rows,
        "cassette_part_rows": part_rows,
        "linked_gene_rows": list(constructs.get("linked_gene_rows") or []),
        "existing_note_context_rows": note_context_rows,
        "catalog_reference_summary": {
            "linked_catalog_asset_count": linked_catalog_assets.get("total_linked_assets", 0),
            "linked_plant_promoter_count": (linked_catalog_assets.get("plant_promoter_reference_summary") or {}).get("linked_promoter_count", 0),
            "missing_metadata_count": (linked_catalog_assets.get("plant_promoter_reference_summary") or {}).get("missing_metadata_count", 0),
            "documentation_contexts": linked_catalog_assets.get("project_documentation_contexts") or [],
        },
        "review_gap_rows": list(constructs.get("review_gap_rows") or []),
        "boundary_notes": _PROTEIN_EXPRESSION_BOUNDARY_NOTES,
    }


def _append_protein_expression_markdown(lines: list[str], section: dict[str, Any]) -> None:
    lines += ["## Protein Expression Documentation Readback"]
    for note in section.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if section.get("message"):
        lines.append(f"- Status: {_markdown_value(section.get('status'))} - {_markdown_value(section.get('message'))}")
        lines.append("")
        return
    target = section.get("target_context") or {}
    lines += [
        f"- Documentation mode: {_markdown_value(section.get('documentation_mode'))}",
        f"- Target protein context: {_markdown_value(target.get('target_protein'))}",
        f"- Linked gene context: {_markdown_value(target.get('linked_gene_context'))}",
        f"- CDS context: {_markdown_value(target.get('cds_context'))}",
    ]
    host = section.get("host_chassis_context") or {}
    lines += [
        f"- Host / chassis context: {_markdown_value(host.get('active_project_context'))}",
        f"- Host / chassis readback contexts: {_markdown_value(host.get('contexts_present'))}",
        f"- Host / chassis boundary: {_markdown_value(host.get('documentation_boundary'))}",
    ]
    if section.get("construct_profiles"):
        lines += [
            "### Construct profile context",
            "| construct_label | construct_type | host_context_note | plasmid_backbone | documentation_scope_note |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in section.get("construct_profiles") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("construct_label"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("construct_type"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("host_context_note"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("plasmid_backbone"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("documentation_scope_note"))),
                    ]
                )
                + " |"
            )
    if section.get("cassette_summary_rows"):
        lines += [
            "### Cassette context",
            "| cassette_label | cassette_role | promoter_label | gene_label | terminator_label | source_reference |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in section.get("cassette_summary_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("cassette_label")),
                        _markdown_table_value(row.get("cassette_role")),
                        _markdown_table_value(row.get("promoter_label")),
                        _markdown_table_value(row.get("gene_label")),
                        _markdown_table_value(row.get("terminator_label")),
                        _markdown_table_value(row.get("source_reference")),
                    ]
                )
                + " |"
            )
    if section.get("cassette_part_rows"):
        lines += [
            "### Recorded cassette part context",
            "| cassette_label | part_role | part_label | part_reference | source_catalog | source_record_label | evidence_context_note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in section.get("cassette_part_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("cassette_label")),
                        _markdown_table_value(row.get("part_role")),
                        _markdown_table_value(row.get("part_label")),
                        _markdown_table_value(row.get("part_reference")),
                        _markdown_table_value(row.get("source_catalog")),
                        _markdown_table_value(row.get("source_record_label")),
                        _markdown_table_value(row.get("evidence_context_note")),
                    ]
                )
                + " |"
            )
    if section.get("linked_gene_rows"):
        lines += [
            "### Linked gene context",
            "| gene_label | gene_reference | source_reference | provenance_note |",
            "| --- | --- | --- | --- |",
        ]
        for row in section.get("linked_gene_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("gene_label"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("gene_reference"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("source_reference"))),
                        _markdown_table_value(_sanitize_protein_expression_readback_text(row.get("provenance_note"))),
                    ]
                )
                + " |"
            )
    if section.get("existing_note_context_rows"):
        lines += [
            "### Existing signal, secretion, marker, vector, or backbone context",
            "| source | context | boundary |",
            "| --- | --- | --- |",
        ]
        for row in section.get("existing_note_context_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("source")),
                        _markdown_table_value(row.get("context")),
                        _markdown_table_value(row.get("boundary")),
                    ]
                )
                + " |"
            )
    catalog = section.get("catalog_reference_summary") or {}
    lines += [
        "### Catalog reference and review-gap context",
        f"- Linked catalog references: {_markdown_value(catalog.get('linked_catalog_asset_count', 0))}",
        "- Linked Component Library promoter asset references: "
        f"{_markdown_value(catalog.get('linked_plant_promoter_count', 0))}",
        f"- Catalog/reference review gaps: {_markdown_value(catalog.get('missing_metadata_count', 0))}",
        f"- Project documentation contexts: {_compact_summary(catalog.get('documentation_contexts') or [])}",
        f"- Construct review gaps: {len(section.get('review_gap_rows') or [])}",
        "",
    ]


def _markdown_value(value: Any) -> str:
    return _clean_text(value, "NOT_AVAILABLE")


def _markdown_table_value(value: Any) -> str:
    text = _clean_text(value, "NOT_AVAILABLE")
    return text.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _append_construct_component_markdown(lines: list[str], constructs: dict[str, Any]) -> None:
    component_summary = constructs.get("construct_component_review_summary") or {}
    follow_up_readback = constructs.get("construct_component_manual_follow_up_readback") or (
        _construct_component_manual_follow_up_readback(constructs.get("construct_component_gap_queue") or [])
    )
    lines += [
        "### Construct component documentation readback",
        "- This section reads back recorded construct documentation from documented component rows only.",
        "- It is not validation, selection advice, or a downstream-use state decision.",
        "- Construct component readback records recorded construct documentation only. They do not validate, recommend, or decide downstream-use state.",
        "- Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status.",
        "- Component conservation review is a documentation-only readback of source/evidence context and missing-review cues.",
        "- It does not run BLAST, multiple sequence alignment, conserved-domain analysis, automated conservation-status classification, component selection, expression outcome estimates, guarantees of success, or wet-lab use judgments.",
        f"- Conservation boundary: {_markdown_value(expression_construct_presenter.CONSERVATION_REVIEW_BOUNDARY_NOTE)}",
        "### Construct review summary",
        "| Review concept | Count |",
        "| --- | --- |",
    ]
    for key in (
        "total_component_rows",
        "rows_with_source_reference_context",
        "rows_missing_source_reference_context",
        "rows_with_sequence_availability_note",
        "rows_with_conservation_review_context",
        "rows_needing_conservation_follow_up",
        "rows_with_review_metadata_status",
        "rows_with_review_note",
        "rows_needing_manual_follow_up",
    ):
        label = expression_construct_presenter.COMPONENT_REVIEW_SUMMARY_LABELS.get(key, key)
        lines.append(f"| {_markdown_table_value(label)} | {_markdown_table_value(component_summary.get(key, 0))} |")
    if constructs.get("construct_component_rows"):
        lines += [
            "### Construct component rows",
            "| Component label | Component category | Source/reference context | Sequence availability note | Conservation review evidence | Conservation follow-up cue | Record review status | Review note | Cassette label |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("construct_component_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("component_label")),
                        _markdown_table_value(row.get("component_category")),
                        _markdown_table_value(row.get("component_reference_label")),
                        _markdown_table_value(row.get("sequence_availability_status")),
                        _markdown_table_value(row.get("conservation_review_evidence")),
                        _markdown_table_value(row.get("conservation_follow_up_cue")),
                        _markdown_table_value(row.get("review_metadata_status")),
                        _markdown_table_value(row.get("review_note")),
                        _markdown_table_value(row.get("cassette_label")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("- No construct component documentation rows are recorded for this report.")
        lines.append("- No construct component documentation rows are recorded in this report markdown readback.")
    if constructs.get("supported_component_vocabulary"):
        lines.append(
            "- Supported documented component vocabulary: "
            + "; ".join(_markdown_value(item) for item in constructs.get("supported_component_vocabulary") or [])
        )
    lines += [
        "### Construct component manual follow-up readback",
        f"- Status: {_markdown_value(follow_up_readback.get('status'))}",
        "- Manual documentation review items in report snapshot: "
        f"{_markdown_value(follow_up_readback.get('total_manual_follow_up_items', 0))}",
        f"- Role-label review items: {_markdown_value(follow_up_readback.get('role_label_review_count', 0))}",
        f"- Duplicate-label review items: {_markdown_value(follow_up_readback.get('duplicate_label_review_count', 0))}",
        "- Conservation review follow-up items: "
        f"{_markdown_value(follow_up_readback.get('conservation_review_follow_up_count', 0))}",
        "- Other documentation follow-up items: "
        f"{_markdown_value(follow_up_readback.get('other_documentation_follow_up_count', 0))}",
        f"- Boundary: {_markdown_value(follow_up_readback.get('manual_review_boundary'))}",
    ]
    for note in follow_up_readback.get("clarity_notes") or []:
        lines.append(f"- {_markdown_value(note)}")
    lines += [
        "### Manual follow-up queue",
        "- This queue is for manual documentation follow-up on construct component rows.",
    ]
    if constructs.get("construct_component_gap_queue"):
        lines += [
            "| Construct label | Cassette label | Component label | Component category | Issue type | Issue detail | Manual follow-up note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("construct_component_gap_queue") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("Construct label")),
                        _markdown_table_value(row.get("Cassette label")),
                        _markdown_table_value(row.get("Component label")),
                        _markdown_table_value(row.get("Component category")),
                        _markdown_table_value(row.get("Issue type")),
                        _markdown_table_value(row.get("Issue detail")),
                        _markdown_table_value(row.get("Manual follow-up note")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("- No construct component manual follow-up items are listed from available documentation rows.")


def _step2_component_context_rows_from_context(context: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        row
        for row in _as_list(context.get("rows"))
        if isinstance(row, dict)
    ]
    if not rows:
        return []
    return expression_construct_presenter.step2_component_context_table_rows(rows)


def _build_step2_component_context_appendix(
    step2_component_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = step2_component_context if isinstance(step2_component_context, dict) else {}
    if context.get("rows") and all(
        "Step 2 context category" in row
        for row in _as_list(context.get("rows"))
        if isinstance(row, dict)
    ):
        table_rows = [
            dict(row)
            for row in _as_list(context.get("rows"))
            if isinstance(row, dict)
        ]
    else:
        table_rows = _step2_component_context_rows_from_context(context)

    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    manual_follow_up_rows = int(
        summary.get("manual_follow_up_rows", 0) if isinstance(summary.get("manual_follow_up_rows", 0), int) else 0
    )
    if not summary:
        manual_follow_up_rows = sum(
            1
            for row in table_rows
            if _clean_text(row.get("Source/provenance review"), "").casefold() == "manual follow-up"
            or _clean_text(row.get("Record review status"), "").casefold() == "manual follow-up"
        )
        summary = {
            "total_rows": len(table_rows),
            "rows_with_recorded_assets": sum(
                1
                for row in table_rows
                if _clean_text(row.get("Component Library asset"), "No recorded Component Library context")
                != "No recorded Component Library context"
            ),
            "manual_follow_up_rows": manual_follow_up_rows,
        }

    total_rows = int(summary.get("total_rows", len(table_rows)) or len(table_rows))
    rows_with_assets = int(summary.get("rows_with_recorded_assets", 0) or 0)
    appendix = {
        "status": STATUS_AVAILABLE if table_rows else STATUS_NOT_AVAILABLE,
        "section_title": "Step 2 recorded Component Library context appendix",
        "subtitle": "Read-only review appendix for recorded Component Library context.",
        "rows": table_rows,
        "columns": expression_construct_presenter.STEP2_COMPONENT_CONTEXT_COLUMNS,
        "summary": {
            "total_rows": total_rows,
            "rows_with_recorded_assets": rows_with_assets,
            "manual_follow_up_rows": int(summary.get("manual_follow_up_rows", manual_follow_up_rows) or 0),
        },
        "total_rows_available": len(table_rows),
        "empty_state_message": (
            "No current Step 2 Component Library context is available for this review appendix."
        ),
        "documentation_boundary_note": (
            _clean_text(context.get("documentation_boundary_note"), "")
            or (
                "Step 2 recorded Component Library context is documentation-only read-only review context. "
                "No current context is available for this appendix."
            )
        ),
        "boundary_notes": (
            _STEP2_COMPONENT_CONTEXT_APPENDIX_BOUNDARY_NOTES[:]
            if table_rows
            else _STEP2_COMPONENT_CONTEXT_EMPTY_APPENDIX_BOUNDARY_NOTES[:]
        ),
    }
    return normalize_generated_output_claims(appendix)


def _append_step2_component_context_appendix_markdown(
    lines: list[str],
    appendix: dict[str, Any],
) -> None:
    summary = appendix.get("summary") or {}
    lines += [
        "## Step 2 recorded Component Library context appendix",
        "- Read-only review appendix for recorded Component Library context.",
        f"- Status: {_markdown_value(appendix.get('status'))}",
        f"- Rows available: {_markdown_value(appendix.get('total_rows_available', 0))}",
        f"- Rows with recorded assets: {_markdown_value(summary.get('rows_with_recorded_assets', 0))}",
        f"- Manual follow-up rows: {_markdown_value(summary.get('manual_follow_up_rows', 0))}",
        f"- Boundary: {_markdown_value(appendix.get('documentation_boundary_note'))}",
    ]
    for note in appendix.get("boundary_notes") or []:
        lines.append(f"- {note}")
    rows = [
        row
        for row in appendix.get("rows") or []
        if isinstance(row, dict)
    ]
    if rows:
        lines += [
            "| Step 2 context category | Step 2 recorded value | Component Library asset | Recorded Component Library context | Source/provenance review | Record review status | Sequence metadata | Manual follow-up |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("Step 2 context category")),
                        _markdown_table_value(row.get("Step 2 recorded value")),
                        _markdown_table_value(row.get("Component Library asset")),
                        _markdown_table_value(row.get("Recorded Component Library context")),
                        _markdown_table_value(row.get("Source/provenance review")),
                        _markdown_table_value(row.get("Record review status")),
                        _markdown_table_value(row.get("Sequence metadata")),
                        _markdown_table_value(row.get("Manual follow-up")),
                    ]
                )
                + " |"
            )
    else:
        lines.append(f"- {_markdown_value(appendix.get('empty_state_message'))}")
    lines.append("")


def _append_component_library_asset_readback_report_snapshot_markdown(
    lines: list[str],
    snapshot: dict[str, Any],
) -> None:
    summary = snapshot.get("summary") or {}
    lines += [
        "## Component Library Asset Readback Report Snapshot",
        f"- Status: {_markdown_value(snapshot.get('status'))}",
        f"- Total asset rows: {_markdown_value(summary.get('total_asset_rows', 0))}",
        f"- Asset type count: {_markdown_value(summary.get('asset_type_count', 0))}",
        "- Rows with source/provenance identity: "
        f"{_markdown_value(summary.get('rows_with_source_provenance_identity', 0))}",
        "- Rows with evidence/review metadata: "
        f"{_markdown_value(summary.get('rows_with_evidence_review_metadata', 0))}",
        f"- Presenter reuse: {_markdown_value(snapshot.get('presenter_reuse_note'))}",
        f"- Source/provenance preservation: {_markdown_value(snapshot.get('source_identity_note'))}",
        "- Generic fields represented: "
        + "; ".join(_markdown_value(item) for item in snapshot.get("generic_fields_represented") or []),
        "- Type-specific fields intentionally deferred: "
        + "; ".join(_markdown_value(item) for item in snapshot.get("type_specific_fields_deferred") or []),
    ]
    for note in snapshot.get("boundary_notes") or []:
        lines.append(f"- {note}")
    rows = [row for row in snapshot.get("rows") or [] if isinstance(row, dict)]
    columns = [column for column in snapshot.get("columns") or [] if _clean_text(column, "")]
    if rows and columns:
        lines.append("| " + " | ".join(_markdown_table_value(column) for column in columns) + " |")
        lines.append("| " + " | ".join("---" for _column in columns) + " |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(_markdown_table_value(row.get(column)) for column in columns)
                + " |"
            )
        if snapshot.get("total_rows_available", 0) > len(rows):
            lines.append(
                "- Additional Component Library asset readback rows not shown in table: "
                f"{snapshot.get('total_rows_available', 0) - len(rows)}"
            )
    else:
        lines.append(f"- {_markdown_value(snapshot.get('empty_state_message'))}")
    lines.append("")


def _append_component_library_followup_queue_report_readback_markdown(
    lines: list[str],
    snapshot: dict[str, Any],
) -> None:
    summary = snapshot.get("summary") or {}
    lines += [
        "## Component Library Source/Provenance Follow-up Queue Report Readback",
        f"- Status: {_markdown_value(snapshot.get('status'))}",
        f"- Follow-up rows: {_markdown_value(summary.get('total_followup_rows', 0))}",
        f"- Records with follow-up: {_markdown_value(summary.get('components_with_followup', 0))}",
        f"- Presenter reuse: {_markdown_value(snapshot.get('presenter_reuse_note'))}",
    ]
    if summary.get("followup_type_counts"):
        lines.append("### Follow-up row type counts")
        for label, count in summary.get("followup_type_counts", {}).items():
            lines.append(f"- {label}: {_markdown_value(count)}")
    for note in snapshot.get("boundary_notes") or []:
        lines.append(f"- {note}")

    rows = [row for row in snapshot.get("rows") or [] if isinstance(row, dict)]
    columns = [column for column in snapshot.get("columns") or [] if _clean_text(column, "")]
    if rows and columns:
        lines.append("| " + " | ".join(_markdown_table_value(column) for column in columns) + " |")
        lines.append("| " + " | ".join("---" for _column in columns) + " |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(_markdown_table_value(row.get(column)) for column in columns)
                + " |"
            )
        if snapshot.get("total_rows_available", 0) > len(rows):
            lines.append(
                "- Additional Component Library follow-up queue rows not shown in table: "
                f"{snapshot.get('total_rows_available', 0) - len(rows)}"
            )
    else:
        lines.append(f"- {_markdown_value(snapshot.get('empty_state_message'))}")
    lines.append("")


def _append_plant_design_review_package_markdown(
    lines: list[str],
    package: dict[str, Any],
) -> None:
    if package:
        lines += [format_plant_design_review_package_markdown(package), ""]


def _research_target(project: dict[str, Any]) -> str:
    return _clean_text(
        _first_present(project, ("research_target", "target_product", "project_name", "name")),
        "current project context",
    )


def _brief_section_items(brief: LiteratureResearchBrief | None, title: str) -> list[str]:
    if brief is None:
        return []
    return [_clean_text(item, "") for item in brief.sections.get(title, []) if _clean_text(item, "")]


def _research_context_summary(project: dict[str, Any]) -> dict[str, Any]:
    target = _research_target(project)
    try:
        brief = generate_literature_research_brief(target)
    except Exception as exc:
        state = unavailable_state(str(exc))
        return {
            "status": STATUS_WARNING,
            "target": target,
            "source_mode": "local deterministic stub",
            "summary_points": [state["body"]],
            "source_notes": [state["boundary"]],
            "human_review_questions": ["Which reviewer-selected sources should support the project background?"],
            "boundary_note": state["boundary"],
        }

    return {
        "status": STATUS_AVAILABLE,
        "target": brief.target,
        "source_mode": brief.source_mode,
        "summary_points": _brief_section_items(brief, "Literature context summary"),
        "source_notes": _brief_section_items(brief, "Source notes placeholder"),
        "human_review_questions": _brief_section_items(brief, "Follow-up review questions"),
        "boundary_note": _clean_text(brief.sections["Boundary note: documentation-only, not experimental guidance"][0]),
    }


def _catalog_context_summary() -> dict[str, Any]:
    try:
        records = load_seed_records()
    except Exception as exc:
        return {
            "status": STATUS_WARNING,
            "record_count": 0,
            "asset_type_counts": {},
            "source_review_needed": 0,
            "human_review_needed": 0,
            "sample_records": [],
            "message": f"Local Design Asset Catalog context unavailable: {_clean_text(exc)}",
            "boundary_note": "Catalog records are local documentation context and require source review.",
        }

    review_status = summarize_review_status(records)
    counts = summarize_counts_by_asset_type(records)
    sample_records = [
        {
            "asset_id": _clean_text(record.get("asset_id")),
            "display_name": _clean_text(record.get("display_name")),
            "asset_type": _clean_text(record.get("asset_type")),
            "provenance_status": _clean_text(record.get("provenance_status")),
            "review_status": _clean_text(record.get("review_status")),
        }
        for record in records[:5]
    ]
    return {
        "status": STATUS_AVAILABLE,
        "record_count": len(records),
        "asset_type_counts": counts,
        "source_review_needed": review_status.get("source_review_needed", 0),
        "human_review_needed": review_status.get("human_review_needed", 0),
        "sample_records": sample_records,
        "message": "Local Design Asset Catalog seed records summarized for provenance context and data completeness review.",
        "boundary_note": "Catalog records are local documentation context and require source review.",
    }


def _project_linked_catalog_assets(project: dict[str, Any]) -> list[dict[str, Any]]:
    project_id = _first_present(project, ("project_id", "id"))
    persisted_links: list[dict[str, Any]] = []
    if project_id not in (None, ""):
        try:
            persisted_links = project_catalog_link_repo.list_project_catalog_asset_links(project_id)
        except Exception:
            persisted_links = []
    normalized_links = []
    for link in list_project_asset_links(persisted_links, project_id=project_id):
        if has_staged_basket_only_markers(link):
            continue
        row = dict(link)
        if not _clean_text(row.get("asset_display_name"), ""):
            row["asset_display_name"] = _clean_text(row.get("asset_label"), "") or _clean_text(row.get("asset_id"), "")
        if _clean_text(row.get("linked_persisted_status"), "") != "Persisted linked catalog reference":
            if _clean_text(row.get("link_id"), "") or _clean_text(row.get("created_at"), "") or _clean_text(row.get("updated_at"), ""):
                row["linked_persisted_status"] = "Persisted linked catalog reference"
        normalized_links.append(row)
    return normalized_links


def _snapshot_text(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            parts.append(f"{_clean_text(key)}: {_clean_text(item)}")
        return "; ".join(parts) if parts else "Not recorded"
    return _clean_text(value, "Not recorded")


def _snapshot_summary_entries(snapshot: Any, key_fragments: tuple[str, ...]) -> list[str]:
    if not isinstance(snapshot, dict):
        return []
    entries: list[str] = []
    for key, value in snapshot.items():
        key_text = _clean_text(key, "")
        lower_key = key_text.lower()
        if not key_text or "note" in lower_key or value in (None, "", [], {}):
            continue
        if any(fragment in lower_key for fragment in key_fragments):
            entries.append(f"{key_text}: {_clean_text(value)}")
    return entries


def _compact_summary(values: list[str], limit: int = 3) -> str:
    cleaned = [_clean_text(value, "") for value in values if _clean_text(value, "")]
    if not cleaned:
        return "Not recorded"
    if len(cleaned) <= limit:
        return "; ".join(cleaned)
    remaining = len(cleaned) - limit
    return f"{'; '.join(cleaned[:limit])}; +{remaining} more"


def _linked_catalog_assets_summary(project: dict[str, Any]) -> dict[str, Any]:
    links = _project_linked_catalog_assets(project)
    promoter_summary = summarize_linked_plant_promoter_references(links)
    wizard_traceability = build_expression_wizard_catalog_traceability_summary(links, project_id=_first_present(project, ("project_id", "id")))
    if not links:
        return {
            "status": STATUS_NOT_AVAILABLE,
            "total_linked_assets": 0,
            "asset_types_represented": [],
            "linkage_roles_represented": [],
            "records_needing_human_review": 0,
            "source_context_snapshot_summary": [],
            "review_status_snapshot_summary": [],
            "documentation_notes": [],
            "linked_references": [],
            "plant_promoter_reference_summary": promoter_summary,
            "linked_catalog_asset_count": 0,
            "linked_plant_promoter_count": 0,
            "missing_source_or_review_metadata_count": 0,
            "expression_wizard_catalog_traceability": wizard_traceability,
            "message": "No linked catalog assets were recorded for this project.",
            "boundary_notes": _LINKED_CATALOG_ASSET_BOUNDARY_NOTES,
        }

    summary = summarize_project_asset_links(links)
    source_summary = sorted(
        {
            entry
            for link in links
            for entry in _snapshot_summary_entries(link.get("source_context_snapshot"), ("source", "provenance", "version"))
        }
    )
    review_summary = sorted(
        {
            entry
            for link in links
            for entry in _snapshot_summary_entries(link.get("review_status_snapshot"), ("review", "status"))
        }
    )
    documentation_notes = sorted(
        {
            _clean_text(link.get("documentation_note"), "")
            for link in links
            if _clean_text(link.get("documentation_note"), "")
        }
    )
    linked_references = [build_linked_catalog_reference_output(link) for link in links]
    pinned_count = sum(1 for link in links if catalog_asset_snapshot_has_content(link.get("asset_snapshot")))
    missing_snapshot_count = len(links) - pinned_count
    return {
        "status": STATUS_AVAILABLE,
        "total_linked_assets": summary.get("total_links", 0),
        "asset_types_represented": [key for key in summary.get("by_asset_type", {}).keys() if key],
        "linkage_roles_represented": [key for key in summary.get("by_linkage_role", {}).keys() if key],
        "records_needing_human_review": len(report_links_needing_review(links)),
        "source_context_snapshot_summary": source_summary,
        "review_status_snapshot_summary": review_summary,
        "documentation_notes": documentation_notes,
        "project_documentation_contexts": sorted(
            {
                _clean_text(reference.get("project_documentation_context"), "")
                for reference in linked_references
                if _clean_text(reference.get("project_documentation_context"), "")
            }
        ),
        "linked_references": linked_references,
        "plant_promoter_reference_summary": promoter_summary,
        "expression_wizard_catalog_traceability": wizard_traceability,
        "linked_catalog_asset_count": summary.get("total_links", 0),
        "linked_plant_promoter_count": promoter_summary.get("linked_promoter_count", 0),
        "missing_source_or_review_metadata_count": promoter_summary.get("missing_metadata_count", 0),
        "catalog_links_with_pinned_snapshots_count": pinned_count,
        "catalog_links_missing_snapshots_count": missing_snapshot_count,
        "malformed_snapshot_warning_count": sum(1 for link in links if link.get("asset_snapshot_warning")),
        "boundary_notes": _LINKED_CATALOG_ASSET_BOUNDARY_NOTES,
    }


def _component_library_asset_readback_report_snapshot(
    linked_catalog_assets: dict[str, Any],
    construct_documentation: dict[str, Any],
) -> dict[str, Any]:
    presenter = build_component_library_asset_readback_presenter(
        linked_catalog_assets=[
            row
            for row in linked_catalog_assets.get("linked_references") or []
            if isinstance(row, dict)
        ],
        construct_component_rows=[
            row
            for row in construct_documentation.get("construct_component_rows") or []
            if isinstance(row, dict)
        ],
    )
    rows = [row for row in presenter.get("rows") or [] if isinstance(row, dict)]
    columns = [
        "Asset label",
        "Asset type",
        "Domain/chassis context",
        "Source/provenance identity",
        "Record review status",
        "Documentation context note",
        "Documentation boundary note",
    ]
    for row in rows:
        if "Record review status" not in row:
            row["Record review status"] = row.get("Evidence/review metadata", "Not recorded")
    return {
        "status": STATUS_AVAILABLE if rows else STATUS_NOT_AVAILABLE,
        "section_title": "Component Library Asset Readback Report Snapshot",
        "summary": presenter.get("summary") or {},
        "columns": columns,
        "rows": [{column: row.get(column, "Not recorded") for column in columns} for row in rows[:12]],
        "total_rows_available": len(rows),
        "empty_state_message": presenter.get("empty_state")
        or "No Component Library asset metadata is available for generic readback.",
        "presenter_reuse_note": (
            "Project Review Report reuses the generic Component Library asset readback presenter "
            "without adding a universal asset database model."
        ),
        "source_identity_note": presenter.get("source_identity_note"),
        "generic_fields_represented": columns,
        "type_specific_fields_deferred": [
            "promoter-specific evidence interpretation",
            "CDS/gene-specific sequence interpretation",
            "vector/backbone-specific source interpretation",
            "host- or chassis-specific use interpretation",
        ],
        "boundary_notes": _COMPONENT_LIBRARY_ASSET_READBACK_REPORT_BOUNDARY_NOTES
        + [presenter.get("documentation_boundary_note")]
        + ([presenter.get("source_identity_note")] if presenter.get("source_identity_note") else []),
    }


def _component_library_followup_queue_report_readback_snapshot(
    linked_catalog_assets: dict[str, Any],
    construct_documentation: dict[str, Any],
) -> dict[str, Any]:
    presenter = build_component_library_followup_queue_presenter(
        local_design_assets=[],
        linked_catalog_assets=[
            row
            for row in linked_catalog_assets.get("linked_references") or []
            if isinstance(row, dict)
        ],
        construct_component_rows=[
            row
            for row in construct_documentation.get("construct_component_rows") or []
            if isinstance(row, dict)
        ],
    )
    rows = [row for row in presenter.get("rows") or [] if isinstance(row, dict)]
    columns = [
        column
        for column in FOLLOWUP_QUEUE_COLUMNS
        if column
        in {
            "Component label",
            "Component ID",
            "Component type",
            "Follow-up type",
            "Follow-up detail",
            "Manual review",
            "Boundary note",
        }
    ]
    return {
        "status": STATUS_AVAILABLE if rows else STATUS_NOT_AVAILABLE,
        "section_title": "Component Library Source/Provenance Follow-up Queue Report Readback",
        "summary": presenter.get("summary") or {},
        "columns": columns,
        "rows": [{column: row.get(column, "Not recorded") for column in columns} for row in rows[:12]],
        "total_rows_available": len(rows),
        "empty_state_message": presenter.get("empty_state")
        or "No Component Library source/provenance follow-up rows are currently flagged.",
        "presenter_reuse_note": (
            "Project Review Report reuses the existing Component Library source/provenance follow-up queue "
            "presenter without creating records or changing persistence."
        ),
        "boundary_notes": _COMPONENT_LIBRARY_FOLLOWUP_QUEUE_REPORT_BOUNDARY_NOTES
        + ([presenter.get("boundary_note")] if presenter.get("boundary_note") else []),
    }


def _host_chassis_context_report_summary(
    project: dict[str, Any],
    linked_catalog_assets: dict[str, Any],
) -> dict[str, Any]:
    links = linked_catalog_assets.get("linked_references") or []
    linked_context_rows = [
        row
        for row in links
        if isinstance(row, dict) and _clean_text(row.get("asset_type"), "") == "host_chassis_context_note"
    ]
    summary = build_host_chassis_context_summary(project, linked_context_rows)
    status = STATUS_AVAILABLE if summary.get("context_count", 0) > 0 else STATUS_NOT_AVAILABLE
    summary["status"] = status
    summary["documentation_only_note"] = (
        "Host / chassis context readback is documentation context only. "
        "It records chassis-neutral review context and does not recommend, validate, tune, "
        "rank, prove compatibility, or judge downstream readiness."
    )
    return summary


def _design_documentation_state(
    steps: dict[str, Any],
    expression_links: list[dict[str, Any]],
    saved_designs: dict[str, Any],
    completeness_result: dict[str, Any] | None,
) -> dict[str, Any]:
    completeness = completeness_result if isinstance(completeness_result, dict) else {}
    return {
        "pathway_step_count": steps.get("step_count", 0),
        "linked_expression_design_count": len(expression_links),
        "saved_design_snapshot_status": saved_designs.get("status", STATUS_NOT_AVAILABLE),
        "completeness_status": completeness.get("status") or STATUS_NOT_AVAILABLE,
        "completeness_score": completeness.get("score", STATUS_NOT_AVAILABLE),
        "notes": [
            "Pathway and Expression Wizard fields are summarized as project documentation state.",
            "Linked design records remain governed by Expression Wizard review checks, Step 6 export rules, and primer-risk semantics.",
            "Missing or unavailable design records are shown as data completeness review items.",
        ],
    }


def _candidate_evidence_record_from_linked_catalog_asset(link: dict[str, Any]) -> dict[str, Any]:
    source_context = link.get("source_context_snapshot")
    review_context = link.get("review_status_snapshot")
    asset_snapshot = link.get("asset_snapshot")
    source_context = source_context if isinstance(source_context, dict) else {}
    review_context = review_context if isinstance(review_context, dict) else {}
    asset_snapshot = asset_snapshot if isinstance(asset_snapshot, dict) else {}
    return {
        "candidate_label": _first_present(
            link,
            ("asset_display_name", "asset_label", "asset_id"),
        ),
        "source_category": _first_present(
            source_context,
            ("catalog", "source_category"),
        )
        or _first_present(link, ("asset_type",)),
        "source_identifier": _first_present(
            source_context,
            ("profile_id", "stable_source_identifier", "source_accession"),
        )
        or _first_present(link, ("asset_id",)),
        "source_hash": _first_present(
            asset_snapshot,
            ("snapshot_hash", "source_hash", "content_hash"),
        )
        or _first_present(link, ("snapshot_hash",)),
        "review_status": _first_present(
            review_context,
            ("review_status", "human_review_status", "curation_statuses", "status"),
        )
        or _first_present(link, ("review_status",)),
        "source_review_status": _first_present(
            source_context,
            ("source_review_status",),
        )
        or _first_present(review_context, ("source_review_status",)),
        "curation_status": _first_present(
            review_context,
            ("curation_status", "curation_statuses"),
        ),
        "not_runtime_seed": link.get("not_runtime_seed"),
        "snapshot_scope": asset_snapshot.get("snapshot_scope"),
    }


def _candidate_evidence_human_review_queue_summary(
    linked_catalog_assets: dict[str, Any],
) -> dict[str, Any]:
    linked_references = [
        dict(reference)
        for reference in linked_catalog_assets.get("linked_references") or []
        if isinstance(reference, dict)
    ]
    records = [
        _candidate_evidence_record_from_linked_catalog_asset(link)
        for link in linked_references
    ]
    matrix = build_candidate_evidence_review_matrix(records)
    queue = build_candidate_evidence_human_review_queue(matrix)
    queue_rows = [dict(row) for row in queue.get("rows") or [] if isinstance(row, dict)]
    summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    return {
        "title": "Candidate Evidence Human Review Queue",
        "subtitle": (
            "Read-only documentation and provenance follow-up derived from linked "
            "candidate evidence context."
        ),
        "status": STATUS_NOT_AVAILABLE if not queue_rows else STATUS_AVAILABLE,
        "summary": {
            "queue_item_count": summary.get("queue_item_count", 0),
            "candidate_count": summary.get("candidate_count", 0),
            "documentation_gap_count": summary.get("documentation_gap_count", 0),
            "provenance_gap_count": summary.get("provenance_gap_count", 0),
            "metadata_gap_count": summary.get("metadata_gap_count", 0),
            "review_follow_up_count": summary.get("review_follow_up_count", 0),
            "category_counts": dict(summary.get("category_counts") or {}),
        },
        "rows": queue_rows[:5],
        "total_rows_available": len(queue_rows),
        "empty_state_message": (
            queue.get("empty_state_message")
            or "No human review follow-up items are currently queued for this report."
        ),
        "boundary_notes": _HUMAN_REVIEW_QUEUE_BOUNDARY_NOTES + list(queue.get("boundary_notes") or []),
    }


def _plant_promoter_profile_links(
    linked_catalog_assets: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        dict(reference)
        for reference in linked_catalog_assets.get("linked_references") or []
        if isinstance(reference, dict) and _clean_text(reference.get("asset_type"), "") == "plant_promoter_profile"
    ]


def _plant_promoter_evidence_gap_review_input(
    linked_catalog_assets: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    promoter_links = _plant_promoter_profile_links(linked_catalog_assets)
    if not promoter_links:
        return {
            "profile_rows": [],
            "evidence_rows": [],
            "rows_needing_review": [],
            "context_readback_rows": [],
        }, "catalog_context"

    profile_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    rows_needing_review: list[dict[str, Any]] = []
    context_readback_rows: list[dict[str, Any]] = []

    for link in sorted(
        promoter_links,
        key=lambda row: (
            _clean_text(row.get("asset_display_name") or row.get("asset_label") or row.get("asset_id"), "").casefold(),
            _clean_text(row.get("asset_id"), "").casefold(),
        ),
    ):
        source_context = link.get("source_context_snapshot")
        review_context = link.get("review_status_snapshot")
        asset_snapshot = link.get("asset_snapshot")
        source_context = source_context if isinstance(source_context, dict) else {}
        review_context = review_context if isinstance(review_context, dict) else {}
        asset_snapshot = asset_snapshot if isinstance(asset_snapshot, dict) else {}

        part_id = _clean_text(_first_present(link, ("asset_id", "record_identifier")), "")
        promoter_label = _clean_text(
            _first_present(link, ("asset_display_name", "asset_label")),
            part_id or "Unknown promoter record",
        )
        plant_clade = _clean_text(
            _first_present(source_context, ("plant_clade", "clade")),
            plant_promoter_catalog_presenter.NO_CLADE_LABEL,
        )
        species_label = _clean_text(
            _first_present(source_context, ("species",)),
            plant_promoter_catalog_presenter.NO_SPECIES_LABEL,
        )
        promoter_type = _clean_text(
            _first_present(asset_snapshot, ("asset_type", "promoter_type")),
            "",
        )
        sequence_availability = _clean_text(_first_present(asset_snapshot, ("sequence_availability",)), "")
        tissue_context = _clean_text(
            _first_present(source_context, ("tissue_contexts", "tissue_context")),
            plant_promoter_catalog_presenter.NO_TISSUE_LABEL,
        )
        source_label = _clean_text(
            _first_present(asset_snapshot, ("source_label",))
            or _first_present(source_context, ("source_labels", "source_label")),
            plant_promoter_catalog_presenter.NO_SOURCE_LABEL,
        )
        curation_status = _clean_text(
            _first_present(review_context, ("curation_statuses", "curation_status", "review_status")),
            plant_promoter_catalog_presenter.NO_CURATION_STATUS_LABEL,
        )
        review_note = _clean_text(
            _first_present(review_context, ("review_notes", "human_review_note")),
            "",
        )
        try:
            missing_metadata_count = int(review_context.get("missing_metadata_count") or 0)
        except (TypeError, ValueError):
            missing_metadata_count = 0

        profile_rows.append(
            {
                "part_id": part_id,
                "display_name": promoter_label,
                "plant_clade": plant_clade,
                "species_label": species_label,
                "promoter_type": promoter_type,
                "sequence_availability": sequence_availability,
            }
        )
        evidence_rows.append(
            {
                "part_id": part_id,
                "promoter_label": promoter_label,
                "tissue_context": tissue_context,
                "source_database": source_label,
                "curation_status": curation_status,
                "review_note": review_note,
            }
        )

        metadata_gap_note = (
            f"Linked promoter reference keeps {missing_metadata_count} metadata gap(s) visible for documentation review."
            if missing_metadata_count > 0
            else "No metadata gap recorded"
        )
        context_readback_rows.append(
            {
                "part_id": part_id,
                "promoter_label": promoter_label,
                "catalog_context": promoter_label,
                "metadata_gap": metadata_gap_note,
            }
        )

        combined_review_context = " ".join(
            [
                curation_status,
                review_note,
                "human review needed" if link.get("human_review_required") else "",
            ]
        ).lower()
        if (
            link.get("human_review_required")
            or missing_metadata_count > 0
            or "review needed" in combined_review_context
            or "follow-up" in combined_review_context
            or "needs review" in combined_review_context
        ):
            rows_needing_review.append(
                {
                    "part_id": part_id,
                    "display_name": promoter_label,
                    "tissue_context": tissue_context,
                    "curation_status": curation_status,
                    "review_note": review_note
                    or "Project-linked Component Library promoter asset reference needs documentation follow-up.",
                }
            )

    return {
        "profile_rows": profile_rows,
        "evidence_rows": evidence_rows,
        "rows_needing_review": rows_needing_review,
        "context_readback_rows": context_readback_rows,
    }, "project_linked" if promoter_links else "catalog_context"


def _plant_promoter_evidence_gap_review_summary(
    linked_catalog_assets: dict[str, Any],
) -> dict[str, Any]:
    queue_input, context_scope = _plant_promoter_evidence_gap_review_input(linked_catalog_assets)
    queue = plant_promoter_gap_queue.build_plant_promoter_evidence_gap_review_queue(queue_input)
    summary_counts = queue.get("summary_counts") if isinstance(queue.get("summary_counts"), dict) else {}
    category_counts = queue.get("category_counts") if isinstance(queue.get("category_counts"), dict) else {}
    queue_rows = [dict(row) for row in queue.get("queue_item_rows") or [] if isinstance(row, dict)]

    if context_scope == "project_linked":
        subtitle = (
            "Read-only project-linked Component Library promoter asset documentation follow-up "
            "derived from linked catalog references."
        )
        empty_state = (
            "No Component Library promoter asset evidence gap items are currently queued for "
            "project-linked promoter asset references in this report."
        )
    else:
        subtitle = "Read-only Component Library promoter asset documentation follow-up for report review."
        empty_state = (
            "No Component Library promoter asset context is linked to this project review report, "
            "so no promoter evidence gap items are currently queued."
        )

    return {
        "title": "Component Library Promoter Asset Evidence Gap Review",
        "subtitle": subtitle,
        "status": STATUS_NOT_AVAILABLE if not queue_rows else STATUS_AVAILABLE,
        "context_scope": context_scope,
        "summary_counts": {
            "profile_count": int(summary_counts.get("profile_count", 0)),
            "queue_item_count": int(summary_counts.get("queue_item_count", 0)),
            "category_count": int(summary_counts.get("category_count", 0)),
        },
        "category_counts": {str(key): int(value or 0) for key, value in category_counts.items()},
        "rows": queue_rows[:8],
        "total_rows_available": len(queue_rows),
        "empty_state_message": empty_state,
        "boundary_notes": _PLANT_PROMOTER_EVIDENCE_GAP_BOUNDARY_NOTES + list(queue.get("boundary_notes") or []),
    }


def _traceability_summary(
    project: dict[str, Any],
    steps: dict[str, Any],
    artifacts: dict[str, Any],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "project_record_present": bool(project),
        "pathway_step_count": steps.get("step_count", 0),
        "linked_artifact_count": artifacts.get("artifact_count", 0),
        "linked_expression_design_count": len(expression_links),
        "test_record_count": len(test_records),
        "documentation_snapshot_count": len(snapshots),
        "review_signal_count": len(review_signals),
        "notes": [
            "Traceability summary reflects local records supplied to this report builder.",
            "Missing counts indicate unavailable documentation context, not biological conclusions.",
            "Source review needed and human review required items should remain visible during handoff.",
        ],
    }


def _data_completeness_summary(
    missing_fields: list[dict[str, str]],
    research: dict[str, Any],
    catalog: dict[str, Any],
    design_state: dict[str, Any],
) -> dict[str, Any]:
    missing_labels = [gap["summary"] for gap in missing_fields]
    if not research.get("summary_points"):
        missing_labels.append("Research context summary unavailable.")
    if catalog.get("record_count", 0) == 0:
        missing_labels.append("Local Design Asset Catalog records unavailable.")
    if design_state.get("pathway_step_count", 0) == 0:
        missing_labels.append("Pathway documentation state has no recorded steps.")
    if design_state.get("linked_expression_design_count", 0) == 0:
        missing_labels.append("No linked Expression Wizard design records supplied to this report draft.")
    return {
        "missing_item_count": len(missing_labels),
        "items": missing_labels or ["No missing documentation fields were identified from supplied local records."],
        "boundary_note": "Data completeness review is a documentation coverage check only.",
    }


def _human_review_questions(
    research: dict[str, Any],
    catalog: dict[str, Any],
    traceability: dict[str, Any],
    missing_fields: list[dict[str, str]],
) -> list[str]:
    questions = [
        "Which source records should support the research context in the final classroom handoff?",
        "Which catalog records need provenance context before they are referenced in project documentation?",
        "Which pathway steps or linked design records need additional documentation before report sharing?",
        "Which traceability rows should a human reviewer inspect before using this as a handoff draft?",
        "Which limitations should be called out for the teacher-facing review?",
    ]
    questions.extend(_as_list(research.get("human_review_questions"))[:3])
    if catalog.get("source_review_needed", 0):
        questions.append("Which Local Design Asset Catalog entries still need source review notes?")
    if traceability.get("linked_expression_design_count", 0) == 0:
        questions.append("Should an Expression Wizard design record be linked for this pathway project context?")
    if missing_fields:
        questions.append("Which missing documentation fields should be filled before the report is shared?")
    return [_clean_text(question) for question in questions]


def _known_limitations_for_detailed_report(catalog: dict[str, Any]) -> list[str]:
    return [
        "This documentation report draft is generated from local deterministic records only.",
        "No real AI API integration, web search, external database lookup, or external source retrieval is performed.",
        "Unavailable records are marked NOT_AVAILABLE or described as data completeness review items.",
        "Catalog context uses local seed records when available and does not make biological selection claims.",
        "The draft does not provide lab instruction steps, selection advice, behavior forecasts, tuning claims, biological-fit claims, source-verification claims, or downstream-use claims.",
        catalog.get("boundary_note", "Catalog records are local documentation context and require source review."),
    ]


def _build_detailed_report_draft_markdown(draft: dict[str, Any]) -> str:
    lines: list[str] = ["# Detailed Documentation Report Draft", ""]
    overview_markdown = format_project_output_sections_overview_markdown(
        draft.get("output_sections_overview")
    )
    if overview_markdown:
        lines += [overview_markdown, ""]
    if draft.get("report_identity"):
        lines += [format_report_identity_markdown(draft["report_identity"]), ""]
    if draft.get("visual_narrative"):
        lines += [format_report_visual_narrative_markdown(draft["visual_narrative"]), ""]
    lines += [
        "## Documentation-only boundary note",
        draft["documentation_only_boundary_note"],
        "",
        "## Project summary",
    ]
    identity = draft["project_summary"]["identity"]
    for key in ("project_id", "project_name", "active_project_status", "description"):
        lines.append(f"- {key}: {_markdown_value(identity.get(key))}")
    for key, value in draft["project_summary"]["context"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    lines.append("")

    research = draft["research_context"]
    lines += [
        "## Research context placeholder",
        f"- Target: {_markdown_value(research.get('target'))}",
        f"- Source mode: {_markdown_value(research.get('source_mode'))}",
    ]
    for item in research.get("summary_points") or []:
        lines.append(f"- {item}")
    lines.append("### Source notes placeholder")
    for item in research.get("source_notes") or []:
        lines.append(f"- {item}")
    lines.append("")

    catalog = draft["catalog_context"]
    lines += [
        "## Local Design Asset Catalog context",
        f"- Record count: {catalog.get('record_count', 0)}",
        f"- Source review needed: {catalog.get('source_review_needed', 0)}",
        f"- Human review required: {catalog.get('human_review_needed', 0)}",
        f"- Context note: {_markdown_value(catalog.get('message'))}",
    ]
    if catalog.get("asset_type_counts"):
        lines.append("### Asset type counts")
        for key, value in catalog["asset_type_counts"].items():
            lines.append(f"- {key}: {value}")
    if catalog.get("sample_records"):
        lines.append("### Catalog sample records")
        for record in catalog["sample_records"]:
            lines.append(
                f"- {record['asset_id']}: {record['display_name']} "
                f"({record['asset_type']}; {record['provenance_status']}; {record['review_status']})"
            )
    lines.append("")

    host_context = draft["host_chassis_context_summary"]
    lines += [
        "## Host / chassis documentation context",
        f"- Status: {_markdown_value(host_context.get('status'))}",
        f"- Active project context: {_markdown_value(host_context.get('project_context_label'))}",
        f"- Contexts present in readback: {_compact_summary(host_context.get('contexts_present_labels') or [])}",
        f"- Supported chassis-neutral contexts: {_compact_summary(host_context.get('supported_contexts') or [])}",
        f"- Documentation boundary: {_markdown_value(host_context.get('documentation_only_note'))}",
        f"- Limitation note: {_markdown_value(host_context.get('limitation_note'))}",
        "",
    ]
    if host_context.get("rows"):
        lines += [
            "### Host / chassis context readback",
            "| Source label | Source value | Normalized context | Record label |",
            "| --- | --- | --- | --- |",
        ]
        for row in host_context.get("rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("source_label")),
                        _markdown_table_value(row.get("source_value")),
                        _markdown_table_value(row.get("normalized_context_label")),
                        _markdown_table_value(row.get("asset_display_name")),
                    ]
                )
                + " |"
            )
        lines.append("")

    target_preview_section = draft.get("target_design_preview_report_section") or {}
    target_preview_markdown = target_preview_section.get("markdown")
    if target_preview_markdown:
        lines.append(target_preview_markdown.rstrip())
        lines.append("")

    linked_catalog_assets = draft["linked_catalog_assets"]
    lines += ["## Linked Catalog Assets"]
    for note in linked_catalog_assets.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if linked_catalog_assets.get("message"):
        lines.append(f"- {linked_catalog_assets['message']}")
        lines.append("")
    else:
        lines += [
            f"- Total linked catalog assets: {linked_catalog_assets.get('total_linked_assets', 0)}",
            f"- Asset types represented: {_compact_summary(linked_catalog_assets.get('asset_types_represented') or [])}",
            f"- Linkage roles represented: {_compact_summary(linked_catalog_assets.get('linkage_roles_represented') or [])}",
            f"- Records needing human review: {linked_catalog_assets.get('records_needing_human_review', 0)}",
            f"- Catalog links with pinned snapshots: {linked_catalog_assets.get('catalog_links_with_pinned_snapshots_count', 0)}",
            f"- Catalog links using fallback metadata: {linked_catalog_assets.get('catalog_links_missing_snapshots_count', 0)}",
            f"- Malformed snapshot warnings: {linked_catalog_assets.get('malformed_snapshot_warning_count', 0)}",
            f"- Source / review status snapshot: "
            f"source={_compact_summary(linked_catalog_assets.get('source_context_snapshot_summary') or [])}; "
            f"review={_compact_summary(linked_catalog_assets.get('review_status_snapshot_summary') or [])}",
            f"- Documentation notes: {_compact_summary(linked_catalog_assets.get('documentation_notes') or [])}",
            f"- Project documentation contexts: {_compact_summary(linked_catalog_assets.get('project_documentation_contexts') or [])}",
            "",
            "### Linked reference list",
            "| Asset display name | Record identifier | Catalog/source | Catalog/source/review status | Source context readback | Review-needed context | Review gap context | Catalog reference context | Reference origin | Project documentation context | Link state | Snapshot state | Documentation note | Asset snapshot | Source context snapshot | Review status snapshot | Human review required |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        promoter_summary = linked_catalog_assets.get("plant_promoter_reference_summary") or {}
        if promoter_summary:
            lines += [
                "### Component Library promoter asset references",
                f"- Linked promoter asset reference count: {promoter_summary.get('linked_promoter_count', 0)}",
                f"- Missing metadata count: {promoter_summary.get('missing_metadata_count', 0)}",
                f"- Source status summary: {_markdown_value(promoter_summary.get('source_status_summary'))}",
                f"- Review status summary: {_markdown_value(promoter_summary.get('review_status_summary'))}",
                f"- Limitation note: {_markdown_value(promoter_summary.get('limitation_note'))}",
                "",
            ]
        for reference in linked_catalog_assets.get("linked_references") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(reference.get("asset_display_name")),
                        _markdown_table_value(reference.get("record_identifier")),
                        _markdown_table_value(reference.get("catalog_name_source")),
                        _markdown_table_value(reference.get("catalog_source_status")),
                        _markdown_table_value(reference.get("source_context_readback")),
                        _markdown_table_value(reference.get("review_needed_context")),
                        _markdown_table_value(reference.get("metadata_gap_context")),
                        _markdown_table_value(reference.get("catalog_reference_context")),
                        _markdown_table_value(reference.get("reference_origin")),
                        _markdown_table_value(reference.get("project_documentation_context")),
                        _markdown_table_value(reference.get("linked_persisted_status")),
                        _markdown_table_value(reference.get("snapshot_status")),
                        _markdown_table_value(reference.get("documentation_note")),
                        _markdown_table_value(_snapshot_text(reference.get("asset_snapshot"))),
                        _markdown_table_value(_snapshot_text(reference.get("source_context_snapshot"))),
                        _markdown_table_value(_snapshot_text(reference.get("review_status_snapshot"))),
                        _markdown_table_value(reference.get("human_review_required")),
                    ]
                )
                + " |"
            )
        lines.append("")
        wizard_traceability = linked_catalog_assets.get("expression_wizard_catalog_traceability") or {}
        if wizard_traceability.get("traceability_rows"):
            lines += [
                "### Expression Wizard catalog traceability",
                f"- Reference count: {wizard_traceability.get('reference_count', 0)}",
                "- Component Library promoter asset reference count: "
                f"{wizard_traceability.get('plant_promoter_reference_count', 0)}",
                f"- Missing metadata count: {wizard_traceability.get('missing_metadata_count', 0)}",
                f"- Source / review status: source={wizard_traceability.get('traceability_rows')[0].get('source_label', 'Not recorded')}; "
                f"review={wizard_traceability.get('traceability_rows')[0].get('documentation_status', 'Not recorded')}",
                f"- Limitation note: {_markdown_value(wizard_traceability.get('limitation_note'))}",
                "",
                "| asset_type | asset_id | asset_label | source_label | documentation_status | linked_project_id | reference_origin | limitation_note |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
            for row in wizard_traceability.get("traceability_rows") or []:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _markdown_table_value(row.get("asset_type")),
                            _markdown_table_value(row.get("asset_id")),
                            _markdown_table_value(row.get("asset_label")),
                            _markdown_table_value(row.get("source_label")),
                            _markdown_table_value(row.get("documentation_status")),
                            _markdown_table_value(row.get("linked_project_id")),
                            _markdown_table_value(row.get("reference_origin")),
                            _markdown_table_value(row.get("limitation_note")),
                        ]
                    )
                    + " |"
                )
            lines.append("")

    constructs = draft["expression_construct_documentation"]
    lines += ["## Expression Construct Documentation"]
    for note in constructs.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if constructs.get("message"):
        lines.append(f"- {constructs['message']}")
    lines.append(f"- Project-scoped filtering: {_markdown_value(constructs.get('project_scoped_filtering'))}")
    summary = constructs.get("summary_counts") or {}
    for key in (
        "construct_profile_count",
        "cassette_count",
        "cassette_part_count",
        "gene_link_count",
        "pathway_step_link_count",
        "project_link_count",
        "review_gap_count",
    ):
        lines.append(f"- {key}: {_markdown_value(summary.get(key, 0))}")
    if constructs.get("construct_profile_rows"):
        lines += [
            "### Construct profile rows",
            "| construct_label | construct_type | host_context_note | source_reference | provenance_note | review_status | documentation_scope_note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("construct_profile_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("construct_label")),
                        _markdown_table_value(row.get("construct_type")),
                        _markdown_table_value(row.get("host_context_note")),
                        _markdown_table_value(row.get("source_reference")),
                        _markdown_table_value(row.get("provenance_note")),
                        _markdown_table_value(row.get("review_status")),
                        _markdown_table_value(row.get("documentation_scope_note")),
                    ]
                )
                + " |"
            )
    if constructs.get("cassette_rows"):
        lines += [
            "### Expression cassette rows",
            "| cassette_label | cassette_order | cassette_role | promoter_label | gene_label | terminator_label | source_reference | provenance_note |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("cassette_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("cassette_label")),
                        _markdown_table_value(row.get("cassette_order")),
                        _markdown_table_value(row.get("cassette_role")),
                        _markdown_table_value(row.get("promoter_label")),
                        _markdown_table_value(row.get("gene_label")),
                        _markdown_table_value(row.get("terminator_label")),
                        _markdown_table_value(row.get("source_reference")),
                        _markdown_table_value(row.get("provenance_note")),
                    ]
                )
                + " |"
            )
    if constructs.get("cassette_part_rows"):
        lines += [
            "### Cassette part rows",
            "| cassette_label | part_order | part_role | part_label | part_reference | source_reference | source_catalog | source_record_label | evidence_context_note | provenance_note |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("cassette_part_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("cassette_label")),
                        _markdown_table_value(row.get("part_order")),
                        _markdown_table_value(row.get("part_role")),
                        _markdown_table_value(row.get("part_label")),
                        _markdown_table_value(row.get("part_reference")),
                        _markdown_table_value(row.get("source_reference")),
                        _markdown_table_value(row.get("source_catalog")),
                        _markdown_table_value(row.get("source_record_label")),
                        _markdown_table_value(row.get("evidence_context_note")),
                        _markdown_table_value(row.get("provenance_note")),
                    ]
                )
                + " |"
            )
    _append_construct_component_markdown(lines, constructs)
    if constructs.get("linked_gene_rows"):
        lines += [
            "### Linked gene rows",
            "| gene_label | gene_reference | source_reference | provenance_note |",
            "| --- | --- | --- | --- |",
        ]
        for row in constructs.get("linked_gene_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("gene_label")),
                        _markdown_table_value(row.get("gene_reference")),
                        _markdown_table_value(row.get("source_reference")),
                        _markdown_table_value(row.get("provenance_note")),
                    ]
                )
                + " |"
            )
    if constructs.get("linked_pathway_step_rows"):
        lines += [
            "### Linked pathway step rows",
            "| pathway_step_id | pathway_step_label | source_reference | provenance_note |",
            "| --- | --- | --- | --- |",
        ]
        for row in constructs.get("linked_pathway_step_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("pathway_step_id")),
                        _markdown_table_value(row.get("pathway_step_label")),
                        _markdown_table_value(row.get("source_reference")),
                        _markdown_table_value(row.get("provenance_note")),
                    ]
                )
                + " |"
            )
    if constructs.get("project_link_rows"):
        lines += [
            "### Project-level construct link rows",
            "| project_id | construct_label | link_label | link_note | source_context | curation_status | review_note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in constructs.get("project_link_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("project_id")),
                        _markdown_table_value(row.get("construct_label")),
                        _markdown_table_value(row.get("link_label")),
                        _markdown_table_value(row.get("link_note")),
                        _markdown_table_value(row.get("source_context")),
                        _markdown_table_value(row.get("curation_status")),
                        _markdown_table_value(row.get("review_note")),
                    ]
                )
                + " |"
            )
    if constructs.get("review_gap_rows"):
        lines += [
            "### Construct review gap rows",
            "| gap_type | label | review_gap_note |",
            "| --- | --- | --- |",
        ]
        for row in constructs.get("review_gap_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("Gap type")),
                        _markdown_table_value(row.get("Label")),
                        _markdown_table_value(row.get("Review gap note")),
                    ]
                )
                + " |"
            )
    lines.append("")

    _append_step2_component_context_appendix_markdown(
        lines,
        draft.get("step2_component_context_appendix") or {},
    )

    _append_component_library_asset_readback_report_snapshot_markdown(
        lines,
        draft.get("component_library_asset_readback_snapshot") or {},
    )
    _append_component_library_followup_queue_report_readback_markdown(
        lines,
        draft.get("component_library_followup_queue_report_readback") or {},
    )

    _append_plant_design_review_package_markdown(
        lines,
        draft.get("plant_design_review_package") or {},
    )

    _append_protein_expression_markdown(lines, draft["protein_expression_documentation_readback"])

    design = draft["design_documentation_state"]
    lines += [
        "## Pathway / Expression Wizard documentation state",
        f"- Pathway step count: {design.get('pathway_step_count', 0)}",
        f"- Linked Expression Wizard design records: {design.get('linked_expression_design_count', 0)}",
        f"- Saved design snapshot status: {_markdown_value(design.get('saved_design_snapshot_status'))}",
        f"- Completeness status: {_markdown_value(design.get('completeness_status'))}",
        f"- Completeness score: {_markdown_value(design.get('completeness_score'))}",
    ]
    for item in design.get("notes") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Provenance and source review notes"]
    for item in draft["provenance_and_source_review_notes"]:
        lines.append(f"- {item}")
    lines.append("")

    traceability = draft["traceability_summary"]
    lines += ["## Traceability summary"]
    for key in (
        "project_record_present",
        "pathway_step_count",
        "linked_artifact_count",
        "linked_expression_design_count",
        "test_record_count",
        "documentation_snapshot_count",
        "review_signal_count",
    ):
        lines.append(f"- {key}: {_markdown_value(traceability.get(key))}")
    for item in traceability.get("notes") or []:
        lines.append(f"- {item}")
    lines.append("")

    completeness = draft["data_completeness_review"]
    lines += [
        "## Data completeness / missing documentation fields",
        f"- Missing item count: {completeness.get('missing_item_count', 0)}",
        f"- Boundary: {completeness.get('boundary_note')}",
    ]
    for item in completeness.get("items") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Human review questions"]
    for question in draft["human_review_questions"]:
        lines.append(f"- {question}")
    lines.append("")

    lines += ["## Known limitations"]
    for limitation in draft["known_limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")

    return "\n".join(lines)


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = ["# Project Review Report", ""]
    lines += ["## Report summary", report["overall_summary"], f"- Report version: {report['report_version']}", f"- Generated at: {report['generated_at']}", ""]
    overview_markdown = format_project_output_sections_overview_markdown(
        report.get("output_sections_overview")
    )
    if overview_markdown:
        lines += [overview_markdown, ""]
    if report.get("report_identity"):
        lines += [format_report_identity_markdown(report["report_identity"]), ""]
    if report.get("visual_narrative"):
        lines += [format_report_visual_narrative_markdown(report["visual_narrative"]), ""]

    identity = report["project_identity"]["fields"]
    lines += ["## Project identity"]
    for key in ("project_id", "project_name", "active_project_status", "created_at", "updated_at", "description"):
        lines.append(f"- {key}: {_markdown_value(identity.get(key))}")
    lines.append("")

    lines += ["## Pathway documentation summary"]
    project_summary = report["project_summary"]["fields"]
    for key, value in project_summary.items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    lines.append("")

    host_context = report["host_chassis_context_summary"]
    lines += ["## Host / chassis documentation context"]
    lines.append(f"- Status: {_markdown_value(host_context.get('status'))}")
    lines.append(f"- Active project context: {_markdown_value(host_context.get('project_context_label'))}")
    lines.append(f"- Contexts present in readback: {_compact_summary(host_context.get('contexts_present_labels') or [])}")
    lines.append(f"- Supported chassis-neutral contexts: {_compact_summary(host_context.get('supported_contexts') or [])}")
    lines.append(f"- Documentation boundary: {_markdown_value(host_context.get('documentation_only_note'))}")
    lines.append(f"- Limitation note: {_markdown_value(host_context.get('limitation_note'))}")
    if host_context.get("rows"):
        lines += [
            "| Source label | Source value | Normalized context | Record label |",
            "| --- | --- | --- | --- |",
        ]
        for row in host_context.get("rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("source_label")),
                        _markdown_table_value(row.get("source_value")),
                        _markdown_table_value(row.get("normalized_context_label")),
                        _markdown_table_value(row.get("asset_display_name")),
                    ]
                )
                + " |"
            )
    lines.append("")

    steps = report["pathway_steps_summary"]
    lines += ["## Pathway steps", f"- Step count: {steps.get('step_count', 0)}"]
    if steps.get("message"):
        lines.append(f"- Status: {steps['status']} — {steps['message']}")
        lines.append(f"- Guidance: {steps.get('guidance')}")
    for step in steps.get("steps") or []:
        fields = step["fields"]
        lines.append(f"- {fields.get('step_order')}. {_markdown_value(fields.get('title'))}")
        for key in ("organism", "enzyme", "gene", "metabolite", "reaction_name", "notes"):
            lines.append(f"  - {key}: {_markdown_value(fields.get(key))}")
        if step.get("missing_fields"):
            lines.append(f"  - missing step fields: {', '.join(step['missing_fields'])}")
    lines.append("")

    artifacts = report["linked_artifacts_summary"]
    lines += ["## Linked documentation artifacts", f"- Artifact count: {artifacts.get('artifact_count', 0)}"]
    if artifacts.get("message"):
        lines.append(f"- Status: {artifacts['status']} — {artifacts['message']}")
    for note in artifacts.get("boundary_notes") or []:
        lines.append(f"- {note}")
    for artifact in artifacts.get("artifacts") or []:
        lines.append(f"- {_markdown_value(artifact.get('title'))} ({_markdown_value(artifact.get('artifact_type'))})")
        lines.append(f"  - source: {_markdown_value(artifact.get('source'))}")
        lines.append(f"  - created_at: {_markdown_value(artifact.get('created_at'))}")
        lines.append(f"  - linked_project_id: {_markdown_value(artifact.get('linked_project_id'))}")
        lines.append(f"  - raw_payload_status: {_markdown_value(artifact.get('raw_payload_status'))}")
    lines.append("")

    saved = report["saved_design_snapshot_summary"]
    lines += ["## Saved design snapshots"]
    if saved.get("message"):
        lines.append(f"- Status: {saved['status']} — {saved['message']}")
        lines.append(f"- Guidance: {saved.get('guidance')}")
    else:
        lines.append(f"- Snapshot count: {saved.get('snapshot_count', 0)}")
    for note in saved.get("boundary_notes") or []:
        lines.append(f"- {note}")
    for snapshot in saved.get("snapshots") or []:
        lines.append(f"- design_id: {_markdown_value(snapshot.get('design_id'))}")
        lines.append(f"  - display_name: {_markdown_value(snapshot.get('display_name'))}")
        lines.append(f"  - source_saved_design_id: {_markdown_value(snapshot.get('source_saved_design_id'))}")
        lines.append(f"  - saved_design_version: {_markdown_value(snapshot.get('saved_design_version'))}")
        lines.append(f"  - identity_source: {_markdown_value(snapshot.get('identity_source'))}")
    lines.append("")

    constructs = report["expression_construct_documentation"]
    lines += ["## Expression Construct Documentation"]
    for note in constructs.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if constructs.get("message"):
        lines.append(f"- Status: {constructs['status']} - {constructs['message']}")
    lines.append(f"- Project-scoped filtering: {_markdown_value(constructs.get('project_scoped_filtering'))}")
    summary = constructs.get("summary_counts") or {}
    for key in (
        "construct_profile_count",
        "cassette_count",
        "cassette_part_count",
        "gene_link_count",
        "pathway_step_link_count",
        "project_link_count",
        "review_gap_count",
    ):
        lines.append(f"- {key}: {_markdown_value(summary.get(key, 0))}")
    for row in constructs.get("construct_profile_rows") or []:
        lines.append(f"- Construct: {_markdown_value(row.get('construct_label'))}")
        lines.append(f"  - construct_type: {_markdown_value(row.get('construct_type'))}")
        lines.append(f"  - source_reference: {_markdown_value(row.get('source_reference'))}")
        lines.append(f"  - provenance_note: {_markdown_value(row.get('provenance_note'))}")
        lines.append(f"  - review_status: {_markdown_value(row.get('review_status'))}")
    for row in constructs.get("cassette_rows") or []:
        lines.append(
            f"- Cassette: {_markdown_value(row.get('cassette_label'))} "
            f"(order {_markdown_value(row.get('cassette_order'))}; role {_markdown_value(row.get('cassette_role'))})"
        )
        lines.append(f"  - promoter_label: {_markdown_value(row.get('promoter_label'))}")
        lines.append(f"  - gene_label: {_markdown_value(row.get('gene_label'))}")
        lines.append(f"  - terminator_label: {_markdown_value(row.get('terminator_label'))}")
    for row in constructs.get("cassette_part_rows") or []:
        lines.append(
            f"- Part: {_markdown_value(row.get('part_label'))} "
            f"({_markdown_value(row.get('part_role'))}; cassette {_markdown_value(row.get('cassette_label'))})"
        )
        lines.append(f"  - source_catalog: {_markdown_value(row.get('source_catalog'))}")
        lines.append(f"  - source_record_label: {_markdown_value(row.get('source_record_label'))}")
        lines.append(f"  - evidence_context_note: {_markdown_value(row.get('evidence_context_note'))}")
    _append_construct_component_markdown(lines, constructs)
    for row in constructs.get("linked_gene_rows") or []:
        lines.append(f"- Linked gene: {_markdown_value(row.get('gene_label'))} ({_markdown_value(row.get('gene_reference'))})")
    for row in constructs.get("linked_pathway_step_rows") or []:
        lines.append(
            f"- Linked pathway step: {_markdown_value(row.get('pathway_step_label'))} "
            f"({_markdown_value(row.get('pathway_step_id'))})"
        )
    for row in constructs.get("project_link_rows") or []:
        lines.append(
            f"- Project construct link: project {_markdown_value(row.get('project_id'))} / "
            f"{_markdown_value(row.get('construct_label'))}"
        )
        lines.append(f"  - link_label: {_markdown_value(row.get('link_label'))}")
        lines.append(f"  - link_note: {_markdown_value(row.get('link_note'))}")
        lines.append(f"  - source_context: {_markdown_value(row.get('source_context'))}")
        lines.append(f"  - review_note: {_markdown_value(row.get('review_note'))}")
    for row in constructs.get("review_gap_rows") or []:
        lines.append(
            f"- Construct review gap: [{_markdown_value(row.get('Gap type'))}] "
            f"{_markdown_value(row.get('Label'))} - {_markdown_value(row.get('Review gap note'))}"
        )
    lines.append("")

    _append_step2_component_context_appendix_markdown(
        lines,
        report.get("step2_component_context_appendix") or {},
    )

    _append_component_library_asset_readback_report_snapshot_markdown(
        lines,
        report.get("component_library_asset_readback_snapshot") or {},
    )
    _append_component_library_followup_queue_report_readback_markdown(
        lines,
        report.get("component_library_followup_queue_report_readback") or {},
    )

    _append_plant_design_review_package_markdown(
        lines,
        report.get("plant_design_review_package") or {},
    )

    _append_protein_expression_markdown(lines, report["protein_expression_documentation_readback"])

    target_preview_section = report.get("target_design_preview_report_section") or {}
    target_preview_markdown = target_preview_section.get("markdown")
    if target_preview_markdown:
        lines.append(target_preview_markdown.rstrip())
        lines.append("")

    export = report["export_package_summary"]
    lines += ["## Export package status"]
    for key, value in export.items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    lines.append("")

    safety = report["import_safety_summary"]
    lines += ["## Import package safety status"]
    for key in ("status", "overall_status", "blocking_issue_count", "warning_count", "not_evaluated_count", "message"):
        if key in safety:
            lines.append(f"- {key}: {_markdown_value(safety.get(key))}")
    for note in safety.get("boundary_notes") or safety.get("read_only_notes") or []:
        lines.append(f"- {note}")
    lines.append("")

    trail = report["package_exchange_review_trail"]
    lines += ["## Package Exchange Review Trail"]
    lines.append(f"- Status: {_markdown_value(trail.get('status'))}")
    lines.append(f"- Export package status: {_markdown_value((trail.get('export_context') or {}).get('status'))}")
    lines.append(f"- Import package review status: {_markdown_value((trail.get('import_context') or {}).get('status'))}")
    manifest = trail.get("manifest_review") or {}
    lines.append(f"- Manifest review available: {_markdown_value(manifest.get('is_manifest_present'))}")
    lines.append(f"- Package schema version: {_markdown_value(manifest.get('package_schema_version'))}")
    lines.append(f"- Included sections: {_markdown_value(manifest.get('included_section_count'))}")
    counts = manifest.get("record_counts") or {}
    lines.append(f"- Manifest record count context: {_markdown_value(counts.get('record_count_total'))}")
    for item in trail.get("demo_workflow_context") or []:
        lines.append(f"- Workflow context: {_markdown_value(item)}")
    for note in trail.get("review_notes") or []:
        lines.append(f"- Review note: {_markdown_value(note)}")
    lines.append(f"- Documentation boundary: {_markdown_value(trail.get('documentation_boundary'))}")
    for note in trail.get("boundary_notes") or []:
        lines.append(f"- {note}")
    lines.append("")

    queue = report["candidate_evidence_human_review_queue"]
    queue_summary = queue.get("summary") or {}
    lines += ["## Candidate Evidence Human Review Queue"]
    lines.append(f"- Status: {_markdown_value(queue.get('status'))}")
    lines.append(f"- Queue item count: {_markdown_value(queue_summary.get('queue_item_count', 0))}")
    lines.append(f"- Candidate count: {_markdown_value(queue_summary.get('candidate_count', 0))}")
    lines.append(f"- Documentation gaps: {_markdown_value(queue_summary.get('documentation_gap_count', 0))}")
    lines.append(f"- Source/provenance gaps: {_markdown_value(queue_summary.get('provenance_gap_count', 0))}")
    lines.append(f"- Metadata needs review: {_markdown_value(queue_summary.get('metadata_gap_count', 0))}")
    lines.append(f"- Human follow-up items: {_markdown_value(queue_summary.get('review_follow_up_count', 0))}")
    for note in queue.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if queue.get("rows"):
        lines += [
            "| Queue item id | Candidate label | Category | Severity | Issue | Human follow-up | Source context |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in queue.get("rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("queue_item_id")),
                        _markdown_table_value(row.get("candidate_label")),
                        _markdown_table_value(row.get("category_label")),
                        _markdown_table_value(row.get("severity_label")),
                        _markdown_table_value(row.get("issue")),
                        _markdown_table_value(row.get("human_follow_up")),
                        _markdown_table_value(row.get("source_context")),
                    ]
                )
                + " |"
            )
        if queue.get("total_rows_available", 0) > len(queue.get("rows") or []):
            lines.append(
                f"- Additional queued items not shown in table: "
                f"{queue.get('total_rows_available', 0) - len(queue.get('rows') or [])}"
            )
    else:
        lines.append(f"- {_markdown_value(queue.get('empty_state_message'))}")
    lines.append("")

    promoter_queue = report["plant_promoter_evidence_gap_review"]
    promoter_summary = promoter_queue.get("summary_counts") or {}
    follow_up_index = report["project_review_follow_up_index"]
    follow_up_summary = follow_up_index.get("summary") or {}
    lines += ["## Project Review Follow-up Index"]
    lines.append(f"- Status: {_markdown_value(follow_up_index.get('status'))}")
    lines.append(f"- Total follow-up items: {_markdown_value(follow_up_summary.get('total_follow_up_items', 0))}")
    for source_section, count in (follow_up_summary.get("source_section_counts") or {}).items():
        lines.append(f"- Source section {source_section}: {_markdown_value(count)}")
    for category, count in (follow_up_summary.get("category_counts") or {}).items():
        lines.append(f"- Category {category}: {_markdown_value(count)}")
    for note in follow_up_index.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if follow_up_index.get("rows"):
        lines += [
            f"| Follow-up id | Source section | Item label | Category | Issue | {REVIEW_NEXT_COLUMN_LABEL} | Manual review context |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in follow_up_index.get("rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("follow_up_id")),
                        _markdown_table_value(row.get("source_section")),
                        _markdown_table_value(row.get("item_label")),
                        _markdown_table_value(row.get("category")),
                        _markdown_table_value(row.get("issue")),
                        _markdown_table_value(row.get("human_follow_up")),
                        _markdown_table_value(row.get("manual_review_context")),
                    ]
                )
                + " |"
            )
        if follow_up_index.get("total_rows_available", 0) > len(follow_up_index.get("rows") or []):
            lines.append(
                f"- Additional aggregated follow-up rows not shown in table: "
                f"{follow_up_index.get('total_rows_available', 0) - len(follow_up_index.get('rows') or [])}"
            )
    else:
        lines.append(f"- {_markdown_value(follow_up_index.get('empty_state_message'))}")
    lines.append("")

    handoff = report["project_review_handoff_center"]
    handoff_summary = handoff.get("summary") or {}
    handoff_preview = report.get("project_handoff_package_preview") or {}
    handoff_snapshot_card = handoff_preview.get("snapshot_review_card") or {}
    qr_payload = handoff_preview.get("qr_verification_payload") or {}
    traceability_summary = handoff_preview.get("traceability_matrix_summary") or {}
    traceability_rows = handoff_preview.get("traceability_matrix_rows") or []
    lines += ["## Project Review Handoff Center"]
    lines.append(f"- Status: {_markdown_value(handoff.get('status'))}")
    lines.append(f"- Total follow-up items: {_markdown_value(handoff_summary.get('total_follow_up_items', 0))}")
    lines.append(
        "- Expression construct documentation follow-up: "
        f"{_markdown_value(handoff_summary.get('expression_construct_documentation_follow_up_count', 0))}"
    )
    lines.append(f"- Candidate evidence follow-up: {_markdown_value(handoff_summary.get('candidate_evidence_follow_up_count', 0))}")
    lines.append(
        "- Component Library promoter asset source/review follow-up: "
        f"{_markdown_value(handoff_summary.get('promoter_source_review_follow_up_count', 0))}"
    )
    lines.append(
        "- Host/context documentation follow-up: "
        f"{_markdown_value(handoff_summary.get('host_context_documentation_follow_up_count', 0))}"
    )
    lines.append(
        "- Report markdown available for human review: "
        f"{_markdown_value(handoff_summary.get('report_markdown_available', False))}"
    )
    for note in handoff.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if handoff_snapshot_card:
        lines += [
            "### Handoff snapshot review card",
            f"- Snapshot title: {_markdown_value(handoff_snapshot_card.get('snapshot_title'))}",
            f"- Snapshot ID: {_markdown_value(handoff_snapshot_card.get('snapshot_id'))}",
            f"- Preview checksum: {_markdown_value(handoff_snapshot_card.get('snapshot_checksum'))}",
            f"- Checksum algorithm: {_markdown_value(handoff_snapshot_card.get('snapshot_checksum_algorithm'))}",
            "- Included documentation surfaces count: "
            f"{_markdown_value(handoff_snapshot_card.get('snapshot_included_surface_count', 0))}",
            "- Included documentation surfaces: "
            + ", ".join(
                _markdown_value(surface)
                for surface in handoff_snapshot_card.get("snapshot_included_surfaces") or []
            ),
            "- Manual follow-up item count: "
            f"{_markdown_value(handoff_snapshot_card.get('snapshot_manual_follow_up_count', 0))}",
            f"- Preview section count: {_markdown_value(handoff_snapshot_card.get('snapshot_section_count', 0))}",
            f"- Preview content length: {_markdown_value(handoff_snapshot_card.get('snapshot_content_length', 0))}",
            f"- Boundary note: {_markdown_value(handoff_snapshot_card.get('boundary_note'))}",
        ]
    if qr_payload:
        lines += [
            "### Handoff QR verification preview",
            f"- {_markdown_value(handoff_preview.get('qr_verification_intended_use'))}",
            f"- {_markdown_value(handoff_preview.get('qr_verification_dependency_decision'))}",
            f"- {_markdown_value(handoff_preview.get('qr_verification_boundary_note'))}",
            f"- Snapshot ID: {_markdown_value(qr_payload.get('snapshot_id'))}",
            f"- Checksum algorithm: {_markdown_value(qr_payload.get('checksum_algorithm'))}",
            f"- MD5 preview checksum: {_markdown_value(qr_payload.get('snapshot_checksum'))}",
            f"- Included surfaces count: {_markdown_value(qr_payload.get('included_surfaces_count', 0))}",
            f"- Manual follow-up count: {_markdown_value(qr_payload.get('manual_follow_up_count', 0))}",
            "```text",
            _clean_text(handoff_preview.get("qr_verification_payload_text")),
            "```",
        ]
    if handoff.get("checklist"):
        lines += ["### Handoff checklist"]
        for item in handoff.get("checklist") or []:
            lines.append(
                f"- {_markdown_value(item.get('label'))}: {_markdown_value(item.get('status'))} - "
                f"{_markdown_value(item.get('note'))}"
            )
    if handoff.get("follow_up_rows"):
        lines += [
            "### Handoff follow-up queue overview",
            f"| Source surface | Item label | Issue type | Manual follow-up note | {REVIEW_NEXT_COLUMN_LABEL} |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in handoff.get("follow_up_rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("source_surface")),
                        _markdown_table_value(row.get("item_label")),
                        _markdown_table_value(row.get("issue_type")),
                        _markdown_table_value(row.get("manual_follow_up_note")),
                        _markdown_table_value(row.get("where_to_review_next")),
                    ]
                )
                + " |"
            )
        if handoff.get("total_rows_available", 0) > len(handoff.get("follow_up_rows") or []):
            lines.append(
                f"- Additional handoff rows not shown in table: "
                f"{handoff.get('total_rows_available', 0) - len(handoff.get('follow_up_rows') or [])}"
            )
    else:
        lines.append(f"- {_markdown_value(handoff.get('empty_state_message'))}")
    if traceability_rows:
        lines += [
            "### Project handoff traceability matrix",
            f"- Matrix rows: {_markdown_value(traceability_summary.get('row_count', len(traceability_rows)))}",
            "- Included in review sheet: "
            f"{_markdown_value(traceability_summary.get('included_in_review_sheet_count', 0))}",
            "- Source/reference context follow-up: "
            f"{_markdown_value(traceability_summary.get('source_reference_context_follow_up_count', 0))}",
            "- Provenance/review context follow-up: "
            f"{_markdown_value(traceability_summary.get('provenance_review_context_follow_up_count', 0))}",
            f"- Boundary note: {_markdown_value(traceability_summary.get('boundary_note'))}",
            f"| Source surface | Item label | Documentation context | Source/reference context | Provenance/review context | Manual follow-up status | {REVIEW_NEXT_COLUMN_LABEL} | Included in review sheet |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in traceability_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("source_surface")),
                        _markdown_table_value(row.get("item_label")),
                        _markdown_table_value(row.get("documentation_context")),
                        _markdown_table_value(row.get("source_reference_context")),
                        _markdown_table_value(row.get("provenance_review_context")),
                        _markdown_table_value(row.get("manual_follow_up_status")),
                        _markdown_table_value(row.get("where_to_review_next")),
                        _markdown_table_value(row.get("included_in_review_sheet")),
                    ]
                )
                + " |"
            )
    lines.append("")

    lines += ["## Component Library Promoter Asset Evidence Gap Review"]
    lines.append(f"- Status: {_markdown_value(promoter_queue.get('status'))}")
    lines.append(f"- Context scope: {_markdown_value(promoter_queue.get('context_scope'))}")
    lines.append(f"- Promoter asset references in scope: {_markdown_value(promoter_summary.get('profile_count', 0))}")
    lines.append(f"- Queue item count: {_markdown_value(promoter_summary.get('queue_item_count', 0))}")
    lines.append(f"- Category count: {_markdown_value(promoter_summary.get('category_count', 0))}")
    for category, count in (promoter_queue.get("category_counts") or {}).items():
        lines.append(f"- {category}: {_markdown_value(count)}")
    for note in promoter_queue.get("boundary_notes") or []:
        lines.append(f"- {note}")
    if promoter_queue.get("rows"):
        lines += [
            "| Queue item id | Promoter label | Category | Issue | Human follow-up | Source context |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in promoter_queue.get("rows") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_value(row.get("queue_item_id")),
                        _markdown_table_value(row.get("promoter_label")),
                        _markdown_table_value(row.get("category")),
                        _markdown_table_value(row.get("issue")),
                        _markdown_table_value(row.get("human_follow_up")),
                        _markdown_table_value(row.get("source_context")),
                    ]
                )
                + " |"
            )
        if promoter_queue.get("total_rows_available", 0) > len(promoter_queue.get("rows") or []):
            lines.append(
                f"- Additional queued promoter rows not shown in table: "
                f"{promoter_queue.get('total_rows_available', 0) - len(promoter_queue.get('rows') or [])}"
            )
    else:
        lines.append(f"- {_markdown_value(promoter_queue.get('empty_state_message'))}")
    lines.append("")

    lines += ["## Missing fields and review gaps"]
    if report["missing_fields"]:
        for gap in report["missing_fields"]:
            lines.append(f"- [{gap['severity']}] {gap['summary']} Guidance: {gap['user_guidance']}")
    else:
        lines.append("- No review gaps were identified from available documentation fields.")
    lines.append("")

    lines += ["## Review notes"]
    for note in report["review_notes"]:
        lines.append(f"- {note}")
    lines.append("")

    lines += ["## Known limitations"]
    for note in report["known_limitations"]:
        lines.append(f"- {note}")
    lines.append("")

    lines += ["## Boundary notes"]
    for note in report["boundary_notes"]:
        lines.append(f"- {note}")
    lines.append("")

    lines += ["## Suggested next steps"]
    for step in report["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def build_project_review_report(
    project: dict[str, Any] | None,
    linked_artifacts: list[dict[str, Any]] | None = None,
    saved_designs: list[dict[str, Any]] | None = None,
    export_summary: dict[str, Any] | None = None,
    import_safety_summary: dict[str, Any] | None = None,
    expression_links: list[dict[str, Any]] | None = None,
    test_records: list[dict[str, Any]] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
    completeness_result: dict[str, Any] | None = None,
    target_preview_markdown: str | None = None,
    step2_component_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only documentation review report for a pathway project."""
    project_data = project if isinstance(project, dict) else {}
    steps = _as_list(project_data.get("steps") or project_data.get("pathway_steps"))
    linked_artifact_list = [item for item in _as_list(linked_artifacts) if isinstance(item, dict)]
    saved_design_list = [item for item in _as_list(saved_designs) if isinstance(item, dict)]
    expression_link_list = [item for item in _as_list(expression_links) if isinstance(item, dict)]
    test_record_list = [item for item in _as_list(test_records) if isinstance(item, dict)]
    snapshot_list = [item for item in _as_list(snapshots) if isinstance(item, dict)]
    review_signal_list = [item for item in _as_list(review_signals) if isinstance(item, dict)]

    identity = _project_identity(project_data)
    project_summary = _project_summary(project_data)
    pathway_steps = _pathway_steps_summary([item for item in steps if isinstance(item, dict)])
    artifacts = _linked_artifacts_summary(linked_artifact_list)
    saved = _saved_design_snapshot_summary(saved_design_list)
    construct_documentation = _construct_documentation_summary(project_data, [item for item in steps if isinstance(item, dict)])
    export = _export_package_summary(export_summary)
    safety = _import_safety_summary(import_safety_summary)
    package_exchange_trail = _package_exchange_review_trail(export, safety)
    research_context = _research_context_summary(project_data)
    catalog_context = _catalog_context_summary()
    linked_catalog_assets = _linked_catalog_assets_summary(project_data)
    host_chassis_context = _host_chassis_context_report_summary(project_data, linked_catalog_assets)
    protein_expression_readback = _protein_expression_documentation_readback(
        project_data,
        construct_documentation,
        host_chassis_context,
        linked_catalog_assets,
    )
    step2_component_context_appendix = _build_step2_component_context_appendix(step2_component_context)
    component_library_asset_readback_snapshot = _component_library_asset_readback_report_snapshot(
        linked_catalog_assets,
        construct_documentation,
    )
    component_library_followup_queue_report_readback = _component_library_followup_queue_report_readback_snapshot(
        linked_catalog_assets,
        construct_documentation,
    )
    gaps = _missing_fields(identity, pathway_steps, artifacts, linked_catalog_assets, saved, export, safety, project_data)
    candidate_evidence_human_review_queue = _candidate_evidence_human_review_queue_summary(linked_catalog_assets)
    plant_promoter_evidence_gap_review = _plant_promoter_evidence_gap_review_summary(linked_catalog_assets)
    project_review_follow_up_index = build_project_review_follow_up_index(
        candidate_evidence_human_review_queue,
        plant_promoter_evidence_gap_review,
    )
    project_review_handoff_center = build_project_review_handoff_center(
        expression_construct_queue={
            "summary": construct_documentation.get("construct_component_review_summary") or {},
            "rows": construct_documentation.get("construct_component_gap_queue") or [],
            "total_rows_available": len(construct_documentation.get("construct_component_gap_queue") or []),
        },
        candidate_queue=candidate_evidence_human_review_queue,
        promoter_queue=plant_promoter_evidence_gap_review,
        follow_up_index=project_review_follow_up_index,
        host_chassis_context=host_chassis_context,
        step2_component_context_appendix=step2_component_context_appendix,
        report_markdown_available=True,
    )
    project_handoff_package_preview = build_project_handoff_package_preview(
        project_review_handoff_center,
        project_label=_clean_text(_first_present(project_data, ("name", "project_name", "target_product")), "Active pathway documentation project"),
        construct_review_payload=construct_documentation,
    )
    design_state = _design_documentation_state(pathway_steps, expression_link_list, saved, completeness_result)
    traceability = _traceability_summary(
        project_data,
        pathway_steps,
        artifacts,
        expression_link_list,
        test_record_list,
        snapshot_list,
        review_signal_list,
    )
    data_completeness = _data_completeness_summary(gaps, research_context, catalog_context, design_state)
    target_preview_section = build_project_review_target_preview_section(target_preview_markdown)
    target_preview_section_model = target_preview_section.as_dict()
    target_preview_section_model["markdown"] = target_preview_section.as_markdown()
    generated_at = _now_iso()
    project_label = _clean_text(
        _first_present(project_data, ("name", "project_name", "target_product")),
        "Active pathway documentation project",
    )
    handoff_card = project_handoff_package_preview.get("snapshot_review_card") or {}
    handoff_payload = project_handoff_package_preview.get("qr_verification_payload") or {}
    report_identity = build_report_identity_block(
        report_title=REPORT_TITLE,
        project_or_case_name=project_label,
        generated_at=generated_at,
        report_version=REPORT_VERSION,
        software_version="BioDesign Studio",
        report_or_package_id=handoff_card.get("snapshot_id") or "",
        purpose="Project documentation review, provenance review, and handoff communication.",
        review_stage=f"{len(gaps)} visible documentation gap(s); {handoff_payload.get('manual_follow_up_count', 0)} handoff follow-up item(s).",
        recorded_context=(
            f"{pathway_steps.get('step_count', 0)} pathway step(s), "
            f"{construct_documentation.get('summary_counts', {}).get('construct_profile_count', 0)} construct profile(s), "
            f"{linked_catalog_assets.get('total_linked_assets', 0)} linked catalog asset(s)."
        ),
        manual_follow_up="Human/company review should resolve missing source/provenance context, report gaps, and handoff questions.",
    )
    visual_narrative = build_report_visual_narrative(
        stage=f"{len(gaps)} documentation gap(s) visible for manual review.",
        recorded_context=(
            f"Pathway steps {pathway_steps.get('step_count', 0)}; constructs "
            f"{construct_documentation.get('summary_counts', {}).get('construct_profile_count', 0)}; "
            f"catalog references {linked_catalog_assets.get('total_linked_assets', 0)}."
        ),
        manual_follow_up="Manual/company follow-up remains responsible for source review, provenance review, and report interpretation.",
    )
    plant_design_review_package = build_plant_design_review_package(
        project=project_data,
        construct_documentation=construct_documentation,
        host_chassis_context=host_chassis_context,
        linked_catalog_assets=linked_catalog_assets,
        generated_at=generated_at,
    )
    documentation_review_summary = plant_design_review_package.get("documentation_review_summary") or {}
    detailed_report_draft = {
        "report_title": DETAILED_DOCUMENTATION_REPORT_TITLE,
        "status": STATUS_AVAILABLE,
        "documentation_only_boundary_note": (
            "This documentation report draft is documentation-only. It summarizes local project records, draft "
            "research context, catalog provenance context, traceability, data completeness review, and human review "
            "questions. Human review required before using it as teacher-facing project documentation."
        ),
        "project_summary": {"identity": identity["fields"], "context": project_summary["fields"]},
        "research_context": research_context,
        "catalog_context": catalog_context,
        "host_chassis_context_summary": host_chassis_context,
        "target_design_preview_report_section": target_preview_section_model,
        "linked_catalog_assets": linked_catalog_assets,
        "expression_construct_documentation": construct_documentation,
        "step2_component_context_appendix": step2_component_context_appendix,
        "component_library_asset_readback_snapshot": component_library_asset_readback_snapshot,
        "component_library_followup_queue_report_readback": component_library_followup_queue_report_readback,
        "plant_design_review_package": plant_design_review_package,
        "documentation_review_summary": documentation_review_summary,
        "protein_expression_documentation_readback": protein_expression_readback,
        "design_documentation_state": design_state,
        "provenance_and_source_review_notes": [
            "Source review needed for research context placeholders before final classroom handoff.",
            "Catalog provenance context should be checked against reviewer-selected sources when cited.",
            "Linked catalog asset references remain documentation context only and require human review before downstream use.",
            "Linked artifacts and snapshots are local documentation records for traceability only.",
            "Unavailable source records are not inferred by this draft.",
        ],
        "traceability_summary": traceability,
        "data_completeness_review": data_completeness,
        "human_review_questions": _human_review_questions(research_context, catalog_context, traceability, gaps),
        "known_limitations": _known_limitations_for_detailed_report(catalog_context),
        "report_identity": report_identity,
        "visual_narrative": visual_narrative,
    }
    detailed_report_draft["output_sections_overview"] = build_project_output_sections_overview(
        detailed_report_draft=detailed_report_draft,
        handoff_preview=project_handoff_package_preview,
    )
    detailed_report_draft = normalize_generated_output_claims(detailed_report_draft)
    detailed_report_draft["markdown"] = _build_detailed_report_draft_markdown(detailed_report_draft)

    report: dict[str, Any] = {
        "report_title": REPORT_TITLE,
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "overall_summary": "Documentation-only review report for the active pathway documentation project.",
        "report_identity": report_identity,
        "visual_narrative": visual_narrative,
        "project_identity": identity,
        "project_summary": project_summary,
        "host_chassis_context_summary": host_chassis_context,
        "target_design_preview_report_section": target_preview_section_model,
        "pathway_steps_summary": pathway_steps,
        "linked_artifacts_summary": artifacts,
        "saved_design_snapshot_summary": saved,
        "expression_construct_documentation": construct_documentation,
        "step2_component_context_appendix": step2_component_context_appendix,
        "component_library_asset_readback_snapshot": component_library_asset_readback_snapshot,
        "component_library_followup_queue_report_readback": component_library_followup_queue_report_readback,
        "plant_design_review_package": plant_design_review_package,
        "documentation_review_summary": documentation_review_summary,
        "protein_expression_documentation_readback": protein_expression_readback,
        "export_package_summary": export,
        "import_safety_summary": safety,
        "package_exchange_review_trail": package_exchange_trail,
        "candidate_evidence_human_review_queue": candidate_evidence_human_review_queue,
        "plant_promoter_evidence_gap_review": plant_promoter_evidence_gap_review,
        "project_review_follow_up_index": {
            **project_review_follow_up_index,
            "boundary_notes": _FOLLOW_UP_INDEX_BOUNDARY_NOTES + list(project_review_follow_up_index.get("boundary_notes") or []),
            "rows": list(project_review_follow_up_index.get("rows") or [])[:10],
        },
        "project_review_handoff_center": {
            **project_review_handoff_center,
            "boundary_notes": _HANDOFF_CENTER_BOUNDARY_NOTES + list(project_review_handoff_center.get("boundary_notes") or []),
            "follow_up_rows": list(project_review_handoff_center.get("follow_up_rows") or [])[:12],
        },
        "project_handoff_package_preview": project_handoff_package_preview,
        "missing_fields": gaps,
        "review_notes": _review_notes(project_data),
        "detailed_documentation_report_draft": detailed_report_draft,
        "known_limitations": [
            "Unavailable records are marked NOT_AVAILABLE instead of inferred.",
            "Raw artifact payload content is not expanded in this report.",
            "This report summarizes documentation and review records only.",
        ],
        "boundary_notes": BOUNDARY_NOTES,
        "next_steps": [
            "Review missing fields and add documentation where needed.",
            "Review linked catalog references and record missing source/provenance fields or record review status when needed.",
            "Link documentation artifacts only when traceability is needed.",
            "Use read-only export and import safety previews for package review.",
        ],
    }
    report["output_sections_overview"] = build_project_output_sections_overview(
        report=report,
        detailed_report_draft=detailed_report_draft,
        handoff_preview=project_handoff_package_preview,
    )
    report = normalize_generated_output_claims(report)
    report["markdown"] = _build_markdown(report)
    assert_no_misleading_generated_claims(report, context="report")

    return report
