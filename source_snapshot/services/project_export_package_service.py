from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

from services.pathway_completeness_service import build_dbt_step_evidence_matrix_rows, summarize_review_signals
from services.pathway_report_service import BOUNDARY_STATEMENT, PathwayReportConfig, generate_pathway_markdown_report
from services.tool_artifact_service import readable_payload_summary

PACKAGE_VERSION = "1.0"
APP_CONTEXT = "Pathway Workspace Project Export Package"
README_BOUNDARY_TEXT = """This export package is documentation-only.
It does not certify experimental readiness.
It does not predict yield.
It does not optimize pathways.
It does not provide wet-lab instructions.
This package does not provide wet-lab protocols.
Linked artifacts are computational previews / review records only.

This package is for review, traceability, read-only validation, and archival use only. Keep it as a review/archive artifact. It is not an import package, not a wet-lab handoff package, not a validated pathway record, not production readiness evidence, and not evidence of successful cloning, PCR, gel, expression, or biological performance.
"""
INCLUDED_FILES = [
    "manifest.json",
    "project_summary.json",
    "pathway_steps.json",
    "test_records_summary.json",
    "linked_expression_designs.json",
    "linked_tool_artifacts.json",
    "documentation_report.md",
    "README_BOUNDARY.txt",
]
PROJECT_EXPORT_CONTENTS_PREVIEW_BOUNDARY = (
    "This package is documentation-only and intended for review and traceability only. "
    "It does not certify experimental readiness, does not predict yield, does not optimize pathways, "
    "and does not provide wet-lab instructions."
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_filename_part(value: Any, fallback: str = "pathway_project") -> str:
    text = _safe_text(value).lower()
    safe = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return safe or fallback


def build_project_export_filename(project: dict[str, Any] | None, exported_at: str | None = None) -> str:
    safe_project_name = _safe_filename_part((project or {}).get("name") or (project or {}).get("target_product"))
    timestamp = (exported_at or _now_iso()).replace("-", "").replace(":", "").replace("T", "_")[:15]
    return f"pathway_project_export_{safe_project_name}_{timestamp}.zip"


def build_project_export_manifest(
    project: dict[str, Any] | None,
    *,
    exported_at: str | None = None,
    included_sections: list[str] | None = None,
) -> dict[str, Any]:
    safe_project = project if isinstance(project, dict) else {}
    return {
        "package_version": PACKAGE_VERSION,
        "exported_at": exported_at or _now_iso(),
        "app_context": APP_CONTEXT,
        "project_id": safe_project.get("id"),
        "project_name": safe_project.get("name") or safe_project.get("target_product") or "",
        "boundary_statement": BOUNDARY_STATEMENT,
        "included_sections": included_sections or list(INCLUDED_FILES),
    }


def build_project_export_contents_preview(
    linked_tool_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_artifacts = [artifact for artifact in (linked_tool_artifacts or []) if isinstance(artifact, dict)]
    return {
        "sections": [
            "Project summary",
            "Pathway steps",
            "Test records summary",
            "Linked expression designs",
            f"Linked tool artifacts: {len(safe_artifacts)}",
            "Documentation report",
            "Boundary README",
        ],
        "linked_tool_artifacts_count": len(safe_artifacts),
        "boundary_summary": PROJECT_EXPORT_CONTENTS_PREVIEW_BOUNDARY,
    }


def _review_signal_counts_for_step(step_id: Any, review_signals: list[dict[str, Any]] | None) -> int:
    try:
        resolved_step_id = int(step_id or 0)
    except (TypeError, ValueError):
        resolved_step_id = 0
    count = 0
    for signal in review_signals or []:
        if not isinstance(signal, dict):
            continue
        try:
            signal_step_id = int(signal.get("related_step_id") or 0)
        except (TypeError, ValueError):
            signal_step_id = 0
        if signal_step_id == resolved_step_id:
            count += 1
    return count


def _project_summary(
    project: dict[str, Any],
    completeness_result: dict[str, Any] | None,
    review_signals: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    completeness = completeness_result if isinstance(completeness_result, dict) else {}
    return {
        "project_name": project.get("name") or "",
        "target_product": project.get("target_product") or "",
        "host_chassis": project.get("host") or project.get("chassis") or "",
        "status": project.get("status") or "",
        "description": project.get("description") or "",
        "completeness_score": completeness.get("score"),
        "documentation_status": completeness.get("status"),
        "review_signal_summary": summarize_review_signals(review_signals),
        "boundary_statement": "Documentation-only summary; completeness score means documentation coverage only and does not certify experimental readiness.",
    }


def _pathway_steps(
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
    test_records: list[dict[str, Any]] | None,
    review_signals: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows = build_dbt_step_evidence_matrix_rows({}, steps, expression_links, test_records, review_signals)
    safe_steps = [step for step in (steps or []) if isinstance(step, dict)]
    return [
        {
            **row,
            "step_id": safe_steps[index].get("id") if index < len(safe_steps) else None,
            "recorded_pathway_step": safe_steps[index] if index < len(safe_steps) else {},
            "review_signal_count": _review_signal_counts_for_step(safe_steps[index].get("id") if index < len(safe_steps) else None, review_signals),
            "boundary_statement": "Recorded pathway step documentation only; this does not validate, optimize, or certify the step.",
        }
        for index, row in enumerate(rows)
    ]


def _test_records_summary(test_records: list[dict[str, Any]] | None) -> dict[str, Any]:
    records = [record for record in (test_records or []) if isinstance(record, dict)]
    project_records = [record for record in records if record.get("step_id") in (None, "")]
    step_records = [record for record in records if record.get("step_id") not in (None, "")]
    return {
        "documentation_only_framing": "Test records are user-entered observations for documentation and traceability only; do not treat tests as readiness certification.",
        "project_level_test_records_summary": {"count": len(project_records), "records": project_records},
        "step_associated_test_records_summary": {"count": len(step_records), "records": step_records},
        "boundary_statement": "Test Records do not certify experimental readiness, successful cloning/PCR/gel/expression, yield, optimization, or validation.",
    }


def _linked_expression_designs(expression_links: list[dict[str, Any]] | None) -> dict[str, Any]:
    links = []
    for link in expression_links or []:
        if not isinstance(link, dict):
            continue
        links.append(
            {
                "id": link.get("id"),
                "step_id": link.get("step_id"),
                "design_id": link.get("design_id"),
                "design_name": link.get("design_name") or link.get("name") or "",
                "primer_risk_status": link.get("primer_risk_status") or link.get("primer_risk") or link.get("risk_status") or "",
                "boundary_statement": "Linked Expression Wizard designs are traceability references only and remain governed by Wizard validation and primer-risk semantics.",
            }
        )
    return {"documentation_only_boundary": "Linked expression designs are references only; this package does not reinterpret readiness or primer risk.", "linked_expression_designs": links}


def _linked_tool_artifacts(tool_artifacts: list[dict[str, Any]] | None) -> dict[str, Any]:
    artifacts = []
    for artifact in tool_artifacts or []:
        if not isinstance(artifact, dict):
            continue
        artifacts.append(
            {
                "created_at": artifact.get("created_at"),
                "artifact_type": artifact.get("artifact_type"),
                "source_module": artifact.get("source_module"),
                "title": artifact.get("title"),
                "summary": artifact.get("summary"),
                "boundary_label": artifact.get("boundary_label"),
                "readable_payload_summary": [
                    {"label": label, "value": value}
                    for label, value in readable_payload_summary(artifact.get("payload_json"))
                ],
                "project_id": artifact.get("project_id"),
            }
        )
    return {"documentation_only_boundary": "Linked artifacts are computational previews / review records only. Raw payloads are not included by default.", "linked_tool_artifacts": artifacts}


def build_project_export_payload(
    *,
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
    test_records: list[dict[str, Any]] | None,
    completeness_result: dict[str, Any] | None,
    review_signals: list[dict[str, Any]] | None,
    linked_tool_artifacts: list[dict[str, Any]] | None = None,
    documentation_report: str | None = None,
    exported_at: str | None = None,
) -> dict[str, Any]:
    safe_project = project if isinstance(project, dict) else {}
    manifest = build_project_export_manifest(safe_project, exported_at=exported_at)
    report = documentation_report
    if report is None:
        report = generate_pathway_markdown_report(
            safe_project,
            steps or [],
            expression_links or [],
            test_records or [],
            completeness_result or {},
            review_signals or [],
            generated_at=None,
            config=PathwayReportConfig(),
        )
    return {
        "manifest": manifest,
        "project_summary": _project_summary(safe_project, completeness_result, review_signals),
        "pathway_steps": _pathway_steps(steps, expression_links, test_records, review_signals),
        "test_records_summary": _test_records_summary(test_records),
        "linked_expression_designs": _linked_expression_designs(expression_links),
        "linked_tool_artifacts": _linked_tool_artifacts(linked_tool_artifacts),
        "documentation_report": report,
        "readme_boundary": README_BOUNDARY_TEXT,
    }


def build_project_export_zip(payload: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(payload.get("manifest", {}), ensure_ascii=False, indent=2, default=str))
        archive.writestr("project_summary.json", json.dumps(payload.get("project_summary", {}), ensure_ascii=False, indent=2, default=str))
        archive.writestr("pathway_steps.json", json.dumps(payload.get("pathway_steps", []), ensure_ascii=False, indent=2, default=str))
        archive.writestr("test_records_summary.json", json.dumps(payload.get("test_records_summary", {}), ensure_ascii=False, indent=2, default=str))
        archive.writestr("linked_expression_designs.json", json.dumps(payload.get("linked_expression_designs", {}), ensure_ascii=False, indent=2, default=str))
        archive.writestr("linked_tool_artifacts.json", json.dumps(payload.get("linked_tool_artifacts", {}), ensure_ascii=False, indent=2, default=str))
        archive.writestr("documentation_report.md", str(payload.get("documentation_report") or ""))
        archive.writestr("README_BOUNDARY.txt", str(payload.get("readme_boundary") or README_BOUNDARY_TEXT))
    return buffer.getvalue()
