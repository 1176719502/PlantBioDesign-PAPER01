from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from services import pathway_repository as repo

DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION = "1.0"
DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT = (
    "Documentation snapshots are user-created local workspace records for traceability only. They do not approve, "
    "validate, certify, sign, lock, or make the project ready for experimental use. Snapshot contents do not change "
    "Wizard validation, Step 6 export recommendations, primer-risk status, completeness score semantics, Suggestions "
    "semantics, Review Notes semantics, or downstream handoff behavior."
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _report_config_dict(report_config: Any) -> dict[str, Any]:
    if report_config is None:
        return {}
    if isinstance(report_config, dict):
        return dict(report_config)
    if hasattr(report_config, "__dict__"):
        return {
            key: value
            for key, value in vars(report_config).items()
            if not key.startswith("_")
        }
    return {"value": str(report_config)}


def _sequence_length(sequence: Any) -> int:
    text = "".join(str(sequence or "").split())
    return len(text)


def _normalize_step(step: dict[str, Any], include_full_sequences: bool) -> dict[str, Any]:
    normalized = deepcopy(step)
    sequence = normalized.get("gene_sequence")
    if include_full_sequences:
        normalized["gene_sequence"] = _normalize_text(sequence)
        normalized["gene_sequence_included"] = True
    else:
        normalized.pop("gene_sequence", None)
        normalized["gene_sequence_summary"] = {
            "included": False,
            "presence": bool(_normalize_text(sequence)),
            "length_nt": _sequence_length(sequence) if _normalize_text(sequence) else 0,
        }
    return normalized


def build_documentation_snapshot_payload(
    *,
    project_id: int | str | None,
    snapshot_title: str = "",
    snapshot_note: str = "",
    report_config: Any = None,
    suggestions: Any = None,
    review_notes: Any = None,
) -> tuple[bool, str, dict[str, Any]]:
    try:
        resolved_project_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid project id.", {}
    if resolved_project_id <= 0:
        return False, "Invalid project id.", {}

    project = repo.get_pathway_project(resolved_project_id)
    if not project:
        return False, "Pathway project was not found.", {}

    steps = repo.list_pathway_steps(resolved_project_id)
    expression_links = repo.list_expression_design_links(resolved_project_id)
    test_records = repo.list_pathway_test_records(resolved_project_id)
    project_review = _as_mapping(project.get("documentation_review"))
    report_config_dict = _report_config_dict(report_config)
    include_full_sequences = bool(report_config_dict.get("include_full_gene_sequences", False))
    safe_suggestions = _as_records(suggestions)
    safe_review_notes = _as_mapping(review_notes) if review_notes is not None else project_review

    payload = {
        "schema_version": DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_metadata": {
            "snapshot_title": _normalize_text(snapshot_title, "Untitled Documentation Snapshot"),
            "snapshot_note": _normalize_text(snapshot_note),
            "created_at": _now(),
        },
        "boundary_statement": DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT,
        "project": project,
        "pathway_steps": [_normalize_step(step, include_full_sequences) for step in steps],
        "linked_expression_designs": expression_links,
        "test_records": test_records,
        "suggestions": safe_suggestions,
        "review_notes": safe_review_notes,
        "report_configuration": report_config_dict,
        "generated_markdown": {
            "included": False,
            "text": None,
        },
    }
    return True, "Documentation snapshot payload prepared.", payload


def create_documentation_snapshot(
    *,
    project_id: int | str | None,
    snapshot_title: str = "",
    snapshot_note: str = "",
    report_config: Any = None,
    suggestions: Any = None,
    review_notes: Any = None,
    generated_markdown_text: str | None = None,
    include_generated_markdown: bool = False,
) -> tuple[bool, str, int | None]:
    ok, message, payload = build_documentation_snapshot_payload(
        project_id=project_id,
        snapshot_title=snapshot_title,
        snapshot_note=snapshot_note,
        report_config=report_config,
        suggestions=suggestions,
        review_notes=review_notes,
    )
    if not ok:
        return False, message, None

    markdown_text = _normalize_text(generated_markdown_text)
    include_markdown = bool(include_generated_markdown or markdown_text)
    payload["generated_markdown"] = {
        "included": include_markdown,
        "text": markdown_text if include_markdown else None,
    }

    return repo.create_pathway_documentation_snapshot(
        project_id=project_id,
        snapshot_title=payload["snapshot_metadata"]["snapshot_title"],
        snapshot_note=payload["snapshot_metadata"]["snapshot_note"],
        snapshot_payload=payload,
        report_config=report_config,
        generated_markdown_text=markdown_text if include_markdown else None,
        include_generated_markdown=include_markdown,
        schema_version=DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION,
    )


def list_documentation_snapshots(project_id: int | str | None) -> list[dict[str, Any]]:
    return repo.list_pathway_documentation_snapshots(project_id)


def get_documentation_snapshot(snapshot_id: int | str | None) -> dict[str, Any]:
    return repo.get_pathway_documentation_snapshot(snapshot_id)
