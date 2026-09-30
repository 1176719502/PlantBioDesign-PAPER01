from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

from services.pathway_repository import (
    create_pathway_documentation_snapshot,
    create_pathway_project,
    create_pathway_step,
    list_pathway_projects,
)
from services.project_import_dry_run_planner import build_project_import_dry_run_plan
from services.project_import_package_validator import validate_project_import_package
from services.tool_artifact_service import create_tool_artifact

IMPORT_SERVICE_BOUNDARY_STATEMENT = (
    "This import service is documentation-only and read-only unless enable_database_write=True is explicitly supplied; "
    "no database writes are performed on the default path and real import is not implemented unless that explicit gate is enabled. "
    "Imported data remains computational previews and review records only. It does not certify experimental readiness, "
    "does not predict yield, does not optimize pathways, and does not provide wet-lab protocols. "
    "Imported linked artifacts remain computational previews / review records only."
)

PREPARE_IMPORT_MESSAGE = (
    "Import execution is disabled by default. This operation only validates the package and builds a dry-run plan."
)

EXECUTE_IMPORT_NOT_IMPLEMENTED_MESSAGE = "Import execution is disabled unless enable_database_write=True is explicitly supplied."
_LIMITED_ROLLBACK_WARNING = (
    "MVP limited rollback behavior: repository write APIs commit independently; if a later write fails, "
    "the service reports rejected/partial state and audit warnings rather than relying on a single transaction."
)
_ALLOWED_ARTIFACT_TYPES = {
    "protein_structure_analysis",
    "lab_tools_cloning_preview",
    "lab_tools_pcr_preview",
    "lab_tools_virtual_gel_preview",
    "lab_tools_sequence_export_preview",
}


def prepare_project_import(zip_bytes: bytes) -> dict[str, Any]:
    """Prepare a read-only future Import as New Project operation."""
    validation_report = validate_project_import_package(zip_bytes)
    dry_run_plan = build_project_import_dry_run_plan(zip_bytes)

    return {
        "operation": "prepare_import",
        "is_valid_package": bool(validation_report.get("is_valid")),
        "is_plan_available": bool(dry_run_plan.get("is_plan_available")),
        "validation_report": validation_report,
        "dry_run_plan": dry_run_plan,
        "can_execute_import": False,
        "execution_status": "not_implemented",
        "read_only": True,
        "database_writes_performed": False,
        "message": PREPARE_IMPORT_MESSAGE,
        "boundary_statement": IMPORT_SERVICE_BOUNDARY_STATEMENT,
    }


def _base_execution_result() -> dict[str, Any]:
    return {
        "operation": "execute_import_as_new_project",
        "executed": False,
        "execution_status": "not_implemented",
        "read_only": True,
        "database_writes_performed": False,
        "created_project_id": None,
        "created_counts": {
            "project": 0,
            "pathway_steps": 0,
            "linked_tool_artifact_summaries": 0,
            "test_record_summaries": 0,
            "documentation_snapshots": 0,
        },
        "errors": [],
        "source_project_name": None,
        "imported_project_name": None,
        "id_remapping_summary": {
            "project_id": {"source_id": None, "new_id": None},
            "pathway_step_ids": {},
            "linked_tool_artifact_ids": {},
            "test_record_ids": "stored in audit summary only",
        },
        "warnings": [],
        "message": EXECUTE_IMPORT_NOT_IMPLEMENTED_MESSAGE,
        "boundary_statement": IMPORT_SERVICE_BOUNDARY_STATEMENT,
    }


def _read_package_member(archive: zipfile.ZipFile, filename: str, fallback: Any) -> Any:
    try:
        raw = archive.read(filename)
    except (KeyError, OSError):
        return fallback
    if filename.endswith(".json"):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return fallback
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return fallback


def _load_import_package(zip_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        return {
            "manifest": _read_package_member(archive, "manifest.json", {}),
            "project_summary": _read_package_member(archive, "project_summary.json", {}),
            "pathway_steps": _read_package_member(archive, "pathway_steps.json", []),
            "test_records_summary": _read_package_member(archive, "test_records_summary.json", {}),
            "linked_expression_designs": _read_package_member(archive, "linked_expression_designs.json", {}),
            "linked_tool_artifacts": _read_package_member(archive, "linked_tool_artifacts.json", {}),
            "documentation_report": _read_package_member(archive, "documentation_report.md", ""),
            "readme_boundary": _read_package_member(archive, "README_BOUNDARY.txt", ""),
        }


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _unique_imported_project_name(proposed_name: Any) -> str:
    base_name = _safe_text(proposed_name, "Imported - Untitled Project")
    existing_names = {str(project.get("name") or "") for project in list_pathway_projects()}
    if base_name not in existing_names:
        return base_name
    suffix = 2
    while f"{base_name} ({suffix})" in existing_names:
        suffix += 1
    return f"{base_name} ({suffix})"


def _recorded_step(step_entry: Any) -> dict[str, Any]:
    if not isinstance(step_entry, dict):
        return {}
    recorded = step_entry.get("recorded_pathway_step")
    return recorded if isinstance(recorded, dict) else step_entry


def _source_step_id(step_entry: Any) -> Any:
    if isinstance(step_entry, dict) and step_entry.get("step_id") is not None:
        return step_entry.get("step_id")
    return _recorded_step(step_entry).get("id")


def _create_steps(project_id: int, pathway_steps: Any, warnings: list[str]) -> tuple[int, dict[str, int]]:
    count = 0
    remap: dict[str, int] = {}
    steps = pathway_steps if isinstance(pathway_steps, list) else []
    for index, entry in enumerate(steps, start=1):
        recorded = _recorded_step(entry)
        try:
            ok, message, new_step_id = create_pathway_step(
                project_id=project_id,
                step_order=recorded.get("step_order") or index,
                step_name=recorded.get("step_name") or recorded.get("reaction_name") or f"Imported step {index}",
                reaction_name=recorded.get("reaction_name") or "",
                substrate=recorded.get("substrate") or "",
                product=recorded.get("product") or "",
                enzyme_name=recorded.get("enzyme_name") or "",
                gene_name=recorded.get("gene_name") or "",
                gene_sequence=recorded.get("gene_sequence") or "",
                organism_source=recorded.get("organism_source") or "",
                notes="Documentation-only imported pathway step. This record does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab protocols. "
                + _safe_text(recorded.get("notes")),
            )
        except Exception as exc:
            ok, message, new_step_id = False, f"Pathway step creation failure: {exc}", None
        if ok and new_step_id is not None:
            count += 1
            source_id = _source_step_id(entry)
            if source_id is not None:
                remap[str(source_id)] = int(new_step_id)
        else:
            warnings.append(f"Pathway step {index} was not imported: {message}")
    return count, remap


def _artifact_payload_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": _safe_text(artifact.get("summary")),
        "readable_payload_summary": artifact.get("readable_payload_summary") if isinstance(artifact.get("readable_payload_summary"), list) else [],
        "boundary_label": _safe_text(artifact.get("boundary_label")),
        "source_module": _safe_text(artifact.get("source_module")),
        "artifact_type": _safe_text(artifact.get("artifact_type")),
        "title": _safe_text(artifact.get("title")),
        "notes": _safe_text(artifact.get("notes")),
        "documentation_only": True,
        "raw_payload_restored": False,
    }


def _create_artifact_summaries(project_id: int, linked_tool_artifacts: Any, warnings: list[str]) -> tuple[int, dict[str, int]]:
    count = 0
    remap: dict[str, int] = {}
    artifacts = linked_tool_artifacts.get("linked_tool_artifacts") if isinstance(linked_tool_artifacts, dict) else []
    if not isinstance(artifacts, list):
        return count, remap
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        artifact_type = _safe_text(artifact.get("artifact_type"))
        if artifact_type not in _ALLOWED_ARTIFACT_TYPES:
            warnings.append(f"Linked tool artifact {index} was summarized in audit only because its artifact_type is not supported by the artifact repository.")
            continue
        try:
            ok, message, new_artifact_id = create_tool_artifact(
                artifact_type=artifact_type,
                title=_safe_text(artifact.get("title"), f"Imported artifact summary {index}"),
                source_module=_safe_text(artifact.get("source_module"), "Project Import Service"),
                summary=_safe_text(artifact.get("summary") or artifact.get("readable_payload_summary"), "Imported documentation summary."),
                payload_json=_artifact_payload_summary(artifact),
                boundary_label=_safe_text(artifact.get("boundary_label"), IMPORT_SERVICE_BOUNDARY_STATEMENT),
                notes="Sanitized import summary only. Raw payload was not restored.",
                project_id=project_id,
            )
        except Exception as exc:
            ok, message, new_artifact_id = False, f"Artifact summary failure: {exc}", None
        if ok and new_artifact_id is not None:
            count += 1
            source_id = artifact.get("id") or artifact.get("artifact_id") or index
            remap[str(source_id)] = int(new_artifact_id)
        else:
            warnings.append(f"Linked tool artifact {index} artifact summary failure: {message}")
    return count, remap


def _count_test_record_summaries(test_records_summary: Any) -> int:
    if not isinstance(test_records_summary, dict):
        return 0
    count = 0
    for key in ("project_level_test_records_summary", "step_associated_test_records_summary"):
        summary = test_records_summary.get(key)
        if isinstance(summary, dict):
            records = summary.get("records")
            if isinstance(records, list):
                count += len(records)
            elif isinstance(summary.get("count"), int):
                count += summary["count"]
    return count


def _create_audit_snapshot(project_id: int, payload: dict[str, Any], warnings: list[str]) -> int:
    markdown = "\n\n".join(
        part for part in [str(payload.get("documentation_report") or ""), str(payload.get("readme_boundary") or "")] if part
    )
    snapshot_payload = dict(payload)
    snapshot_payload.pop("documentation_report", None)
    snapshot_payload.pop("readme_boundary", None)
    try:
        ok, message, _snapshot_id = create_pathway_documentation_snapshot(
            project_id=project_id,
            snapshot_title="Import audit summary",
            snapshot_note="Documentation-only import audit summary. Test records remain summary-only and do not boost readiness or evidence claims.",
            snapshot_payload=snapshot_payload,
            report_config={"source": "project_import_service", "summary_only": True},
            generated_markdown_text=markdown,
            include_generated_markdown=bool(markdown),
            schema_version="project_import_audit_v1",
        )
    except Exception as exc:
        ok, message = False, f"Audit snapshot failure: {exc}"
    if ok:
        return 1
    warnings.append(f"Import audit snapshot failure: {message}")
    return 0


def execute_project_import_as_new_project(zip_bytes: bytes, *, enable_database_write: bool = False, **_kwargs: Any) -> dict[str, Any]:
    """Execute controlled Import as New Project only when database writes are explicitly enabled."""
    result = _base_execution_result()
    if not enable_database_write:
        result["execution_status"] = "write_disabled"
        return result

    validation_report = validate_project_import_package(zip_bytes)
    if not validation_report.get("is_valid"):
        result["execution_status"] = "rejected"
        result["message"] = "Invalid import package rejected."
        result["validation_report"] = validation_report
        result["errors"] = list(validation_report.get("errors") or ["Invalid import package rejected."])
        return result

    dry_run_plan = build_project_import_dry_run_plan(zip_bytes)
    if not dry_run_plan.get("is_plan_available"):
        result["execution_status"] = "rejected"
        result["message"] = "Dry-run import plan is unavailable."
        result["validation_report"] = validation_report
        result["dry_run_plan"] = dry_run_plan
        result["errors"] = list(dry_run_plan.get("errors") or ["Dry-run import plan is unavailable."])
        return result

    package = _load_import_package(zip_bytes)
    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    project_summary = package.get("project_summary") if isinstance(package.get("project_summary"), dict) else {}
    source_name = _safe_text(dry_run_plan.get("source_project_name") or validation_report.get("project_name"), "Unnamed Project")
    imported_name = _unique_imported_project_name(dry_run_plan.get("proposed_project_name") or f"Imported - {source_name}")
    target_product = _safe_text(project_summary.get("target_product"), source_name)
    description = (
        "Imported as a new documentation-only project. This import does not certify experimental readiness, "
        "does not predict yield, does not optimize pathways, and does not provide wet-lab protocols. "
        + _safe_text(project_summary.get("description"))
    ).strip()

    warnings: list[str] = [_LIMITED_ROLLBACK_WARNING]
    errors: list[str] = []
    try:
        ok, message, project_id = create_pathway_project(
            name=imported_name,
            target_product=target_product,
            host=_safe_text(project_summary.get("host_chassis")),
            description=description,
            status="draft",
        )
    except Exception as exc:
        ok, message, project_id = False, f"Project creation failure: {exc}", None
    if not ok or project_id is None:
        result["execution_status"] = "failed"
        result["message"] = message
        result["validation_report"] = validation_report
        result["dry_run_plan"] = dry_run_plan
        result["warnings"] = warnings
        result["errors"] = [message or "Project creation failed before database writes."]
        return result

    result["created_project_id"] = int(project_id)
    result["created_counts"]["project"] = 1
    result["database_writes_performed"] = True
    result["id_remapping_summary"]["project_id"] = {"source_id": manifest.get("project_id"), "new_id": int(project_id)}

    step_count, step_remap = _create_steps(int(project_id), package.get("pathway_steps"), warnings)
    artifact_count, artifact_remap = _create_artifact_summaries(int(project_id), package.get("linked_tool_artifacts"), warnings)
    test_summary_count = _count_test_record_summaries(package.get("test_records_summary"))

    result["created_counts"]["pathway_steps"] = step_count
    result["created_counts"]["linked_tool_artifact_summaries"] = artifact_count
    result["created_counts"]["test_record_summaries"] = test_summary_count
    result["id_remapping_summary"]["pathway_step_ids"] = step_remap
    result["id_remapping_summary"]["linked_tool_artifact_ids"] = artifact_remap

    audit_payload = {
        "source_project_name": source_name,
        "source_project_id": manifest.get("project_id"),
        "package_fingerprint": dry_run_plan.get("package_fingerprint") or validation_report.get("package_fingerprint"),
        "imported_project_name": imported_name,
        "created_counts": result["created_counts"],
        "id_remapping_summary": result["id_remapping_summary"],
        "boundary_statement": IMPORT_SERVICE_BOUNDARY_STATEMENT,
        "linked_expression_designs_summary": package.get("linked_expression_designs"),
        "test_records_summary": package.get("test_records_summary"),
        "linked_tool_artifacts_summary_only": package.get("linked_tool_artifacts"),
        "documentation_report": package.get("documentation_report"),
        "readme_boundary": package.get("readme_boundary"),
        "raw_payload_restored": False,
        "active_expression_designs_restored": False,
        "readiness_or_evidence_boosted": False,
    }
    result["created_counts"]["documentation_snapshots"] = _create_audit_snapshot(int(project_id), audit_payload, warnings)
    failure_warnings = [warning for warning in warnings if "failure" in warning.lower() or "was not imported" in warning.lower() or "was not created" in warning.lower()]
    if failure_warnings:
        errors = failure_warnings
        result["executed"] = False
        result["execution_status"] = "partial_failure"
        result["message"] = "Import as new documentation-only project encountered partial failure; created counts reflect only successful writes."
    else:
        result["executed"] = True
        result["execution_status"] = "completed"
        result["message"] = "Import as new documentation-only project completed."
    result["read_only"] = False
    result["source_project_name"] = source_name
    result["imported_project_name"] = imported_name
    result["warnings"] = warnings
    result["errors"] = errors
    result["validation_report"] = validation_report
    result["dry_run_plan"] = dry_run_plan
    return result
