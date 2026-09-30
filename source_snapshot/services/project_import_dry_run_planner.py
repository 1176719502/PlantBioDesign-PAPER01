from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from typing import Any

from services.project_import_package_validator import validate_project_import_package

DRY_RUN_BOUNDARY_STATEMENT = (
    "This dry-run import plan is documentation-only and read-only. It describes a future "
    "Import as New Project plan only; it performs no database writes, no overwrite, and no merge. "
    "It does not certify experimental readiness, does not predict yield, does not optimize pathways, "
    "and does not provide wet-lab protocols. It does not validate cloning, PCR, gel, expression, "
    "folding, function, or pathway performance. Linked artifacts remain computational previews / "
    "review records only. Test records are documentation summaries only."
)


def _base_plan() -> dict[str, Any]:
    return {
        "is_plan_available": False,
        "is_valid_package": False,
        "errors": [],
        "warnings": [],
        "source_project_name": None,
        "source_project_id": None,
        "proposed_project_name": None,
        "package_version": None,
        "package_fingerprint": None,
        "would_create": {},
        "id_remapping_required": {
            "project_id": True,
            "pathway_step_ids": True,
            "linked_tool_artifact_ids": True,
            "test_record_ids": True,
        },
        "import_mode": "import_as_new_project_only",
        "read_only": True,
        "database_writes_performed": False,
        "boundary_statement": DRY_RUN_BOUNDARY_STATEMENT,
    }


def _read_json_file(archive: zipfile.ZipFile, filename: str, fallback: Any) -> Any:
    try:
        return json.loads(archive.read(filename).decode("utf-8"))
    except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fallback


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


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


def _source_project_name(manifest: Any, project_summary: Any, validation_report: dict[str, Any]) -> str:
    if isinstance(manifest, dict) and manifest.get("project_name"):
        return str(manifest.get("project_name"))
    if isinstance(project_summary, dict) and project_summary.get("project_name"):
        return str(project_summary.get("project_name"))
    if validation_report.get("project_name"):
        return str(validation_report.get("project_name"))
    return "Unnamed Project"


def build_project_import_dry_run_plan(zip_bytes: bytes) -> dict[str, Any]:
    """Build a read-only plan for a future Import as New Project operation.

    The planner validates and summarizes package contents only. It does not import,
    create, mutate, merge, overwrite, or persist any project data.
    """
    validation_report = validate_project_import_package(zip_bytes)
    plan = _base_plan()
    plan["is_valid_package"] = bool(validation_report.get("is_valid"))
    plan["errors"] = list(validation_report.get("errors") or [])
    plan["warnings"] = list(validation_report.get("warnings") or [])
    plan["package_version"] = validation_report.get("package_version")
    plan["source_project_name"] = validation_report.get("project_name")
    plan["package_fingerprint"] = hashlib.sha256(zip_bytes).hexdigest()

    if not validation_report.get("is_valid"):
        return plan

    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        manifest = _read_json_file(archive, "manifest.json", {})
        project_summary = _read_json_file(archive, "project_summary.json", {})
        pathway_steps = _read_json_file(archive, "pathway_steps.json", [])
        test_records_summary = _read_json_file(archive, "test_records_summary.json", {})
        linked_expression_designs = _read_json_file(archive, "linked_expression_designs.json", {})
        linked_tool_artifacts = _read_json_file(archive, "linked_tool_artifacts.json", {})

    source_name = _source_project_name(manifest, project_summary, validation_report)
    expression_links = (
        linked_expression_designs.get("linked_expression_designs")
        if isinstance(linked_expression_designs, dict)
        else []
    )
    tool_artifacts = (
        linked_tool_artifacts.get("linked_tool_artifacts")
        if isinstance(linked_tool_artifacts, dict)
        else []
    )

    plan["is_plan_available"] = True
    plan["source_project_name"] = source_name
    plan["source_project_id"] = manifest.get("project_id") if isinstance(manifest, dict) else None
    plan["proposed_project_name"] = f"Imported - {source_name}"
    plan["package_version"] = validation_report.get("package_version") or (
        manifest.get("package_version") if isinstance(manifest, dict) else None
    )
    plan["would_create"] = {
        "project": 1,
        "pathway_steps": _count_list(pathway_steps),
        "test_record_summaries": _count_test_record_summaries(test_records_summary),
        "linked_expression_design_references": _count_list(expression_links),
        "linked_tool_artifact_summaries": _count_list(tool_artifacts),
    }
    return plan
