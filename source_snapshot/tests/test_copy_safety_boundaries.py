from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from views.Homepage import (  # noqa: E402
    WORKFLOW_GUIDE_BOUNDARY_COPY,
    WORKFLOW_GUIDE_RELATIONSHIP_COPY,
    WORKFLOW_GUIDE_STEPS,
)
from views.PathwayWorkspace import (  # noqa: E402
    IMPORT_PREVIEW_DISCOVERY_COPY,
    PROJECT_OUTPUTS_CONTENTS_GUIDE_COPY,
    PROJECT_OUTPUTS_GUIDE_COPY,
)
from services.project_quality_dashboard_service import build_project_quality_dashboard  # noqa: E402

FORBIDDEN_USER_VISIBLE_PHRASES = [
    "successful import",
    "project imported",
    "ready for execution",
    "experiment-ready",
    "production-ready",
    "validated construct",
    "optimized pathway",
    "yield prediction",
    "lab-ready",
    "wet-lab ready",
    "proven construct",
    "validated pathway",
]

FORBIDDEN_HIGH_RISK_UI_TERMS = [
    "Validation Issues",
    "Validation status",
    "Run validation",
    "Current review status",
    "Vector Suggestion",
    "Valid package",
    "System Online",
    "ready to write",
]

REQUIRED_TERMINOLOGY_CLEANUP_COPY = [
    "Local workspace available",
    "Vector review option",
    "Review Issues",
    "Run documentation checks first.",
    "Review Checks",
    "Output",
    "available to write",
]

FORBIDDEN_TERMINOLOGY_REPLACEMENTS = {
    "successful import": "package preview created",
    "project imported": "project record prepared",
    "ready for execution": "available for documentation review",
    "experiment-ready": "documentation-only review state",
    "production-ready": "documentation-only review state",
    "validated construct": "reviewed design record",
    "optimized pathway": "documented pathway",
    "yield prediction": "documentation summary",
    "recommended construct": "reviewed design record",
    "wet-lab ready": "available for documentation review",
}

REQUIRED_SAFE_TERMS = [
    "documentation-only",
    "local project workspace",
    "design record",
    "documentation snapshot",
    "import preview",
    "export package",
    "duplicate guard",
    "traceability",
]

USER_VISIBLE_COPY_PATHS = [
    Path(ROOT) / "views" / "Homepage.py",
    Path(ROOT) / "views" / "PathwayWorkspace.py",
    Path(ROOT) / "locales" / "en.py",
    Path(ROOT) / "views" / "pathway_workspace_sections" / "project_report_download_section.py",
    Path(ROOT) / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py",
    Path(ROOT) / "services" / "project_review_handoff_center_service.py",
    Path(ROOT) / "services" / "project_handoff_package_preview_service.py",
]

TERMINOLOGY_GUARD_ROOTS = [
    Path(ROOT) / "views",
    Path(ROOT) / "locales" / "en.py",
]

TERMINOLOGY_GUARD_EXCLUDED_PARTS = {
    ".venv",
    "__pycache__",
    ".pytest_tmp",
    ".pytest_cache",
    "archive",
    "release_notes",
    "releases",
}

NEGATIVE_CONTEXT_RE = re.compile(
    r"\b("
    r"no|not|never|without|avoid|forbid(?:den)?|denylist|"
    r"does not|do not|must not|should not|cannot|"
    r"not a|not an|not treated|not treat|not imply|not approve|"
    r"does not imply|does not approve|does not certify|does not predict|does not optimize"
    r")\b"
)


def _workflow_guide_text() -> str:
    parts = [WORKFLOW_GUIDE_BOUNDARY_COPY, *WORKFLOW_GUIDE_RELATIONSHIP_COPY]
    for step in WORKFLOW_GUIDE_STEPS:
        parts.extend([step["title"], step["description"], step["button"], step["page_key"]])
    return "\n".join(parts)


def _visible_copy_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in USER_VISIBLE_COPY_PATHS)


def _terminology_guard_files() -> list[Path]:
    files: list[Path] = []
    for root in TERMINOLOGY_GUARD_ROOTS:
        if root.is_file():
            candidates = [root]
        else:
            candidates = [
                path
                for path in root.rglob("*")
                if path.suffix.lower() in {".py", ".md"} and path.is_file()
            ]
        for path in candidates:
            relative_parts = path.relative_to(ROOT).parts
            if any(part in TERMINOLOGY_GUARD_EXCLUDED_PARTS for part in relative_parts):
                continue
            if path.name.startswith("release_notes"):
                continue
            files.append(path)
    return sorted(set(files))


def _is_allowed_terminology_context(line: str) -> bool:
    normalized = line.lower()
    return bool(NEGATIVE_CONTEXT_RE.search(normalized))


def _terminology_guard_hits() -> list[str]:
    hits: list[str] = []
    for path in _terminology_guard_files():
        relative = path.relative_to(ROOT)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            normalized = line.lower()
            if _is_allowed_terminology_context(normalized):
                continue
            for phrase, replacement in FORBIDDEN_TERMINOLOGY_REPLACEMENTS.items():
                if phrase in normalized:
                    hits.append(
                        f"{relative}:{line_number}: '{phrase}' -> consider '{replacement}'"
                    )
    return hits


def test_workflow_guide_copy_keeps_documentation_only_boundary_terms() -> None:
    guide_text = _workflow_guide_text().lower()

    for required in REQUIRED_SAFE_TERMS:
        assert required in guide_text


def test_workflow_guide_copy_keeps_main_entry_discoverability_terms() -> None:
    guide_text = _workflow_guide_text()

    for phrase in [
        "Start here: Expression Wizard is the primary single-gene / single-protein expression vector design preparation path",
        "Use Component Library as a supporting source/provenance library",
        "Use Pathway Projects and Pathway Workspace when the expression vector record needs project grouping",
        "Project Outputs is the place for documentation snapshots, reports, documentation-only export package review, and import preview review",
    ]:
        assert phrase in guide_text


def test_workflow_guide_copy_does_not_use_forbidden_claims() -> None:
    guide_text = _workflow_guide_text().lower()

    for forbidden in FORBIDDEN_USER_VISIBLE_PHRASES:
        assert forbidden not in guide_text


def test_homepage_and_locale_copy_do_not_use_forbidden_claims() -> None:
    visible_copy = _visible_copy_text().lower()

    for forbidden in FORBIDDEN_USER_VISIBLE_PHRASES:
        assert forbidden not in visible_copy


def test_main_user_visible_copy_uses_review_framed_terminology() -> None:
    visible_copy = _visible_copy_text()

    for forbidden in FORBIDDEN_HIGH_RISK_UI_TERMS:
        assert forbidden not in visible_copy

    for required in REQUIRED_TERMINOLOGY_CLEANUP_COPY:
        assert required in visible_copy


def test_terminology_guard_blocks_positive_high_risk_user_visible_copy() -> None:
    hits = _terminology_guard_hits()

    assert not hits, "Forbidden terminology claims found:\n" + "\n".join(hits)


def test_workflow_guide_distinguishes_design_and_documentation_snapshots() -> None:
    guide_text = _workflow_guide_text()

    assert "Design Snapshot != Documentation Snapshot" in guide_text
    assert "design snapshot stores Expression Wizard design state" in guide_text
    assert "documentation snapshot stores Pathway Workspace project documentation state" in guide_text


def test_pathway_workspace_next_steps_copy_keeps_documentation_only_boundary() -> None:
    workspace_source = (Path(ROOT) / "views" / "PathwayWorkspace.py").read_text(encoding="utf-8")
    project_outputs_source = (Path(ROOT) / "views" / "pathway_workspace_sections" / "project_outputs_section.py").read_text(
        encoding="utf-8"
    )
    report_download_source = (
        Path(ROOT) / "views" / "pathway_workspace_sections" / "project_report_download_section.py"
    ).read_text(encoding="utf-8")
    checked_copy = "\n".join(
        [
            workspace_source,
            project_outputs_source,
            report_download_source,
            PROJECT_OUTPUTS_GUIDE_COPY,
            IMPORT_PREVIEW_DISCOVERY_COPY,
            PROJECT_OUTPUTS_CONTENTS_GUIDE_COPY,
        ]
    )
    normalized_checked_copy = " ".join(checked_copy.split())

    for phrase in [
        "Next documentation steps",
        "Add or review pathway steps",
        "Open / review linked Expression Wizard design records",
        "Save documentation snapshot",
        "Review import package",
        "Project Outputs is the review and traceability area",
        "Pathway Workspace > Project Outputs > Import Preview",
        "documentation-only package inspection for validation and dry-run planning",
        "preview does not create a project, overwrite, or merge existing projects",
        "A separate gated import-as-new action may create a local documentation-only project after validation, safety review, dry-run planning, and explicit confirmation",
        "They point to existing workspace",
        "tabs and outputs",
        "do not change project schemas, import/export behavior, or readiness semantics",
        "documentation-only",
    ]:
        assert phrase in normalized_checked_copy

    normalized = checked_copy.lower()
    for forbidden in FORBIDDEN_USER_VISIBLE_PHRASES:
        assert forbidden not in normalized


def test_dashboard_output_relabels_host_context_claim_copy() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 186, "name": "Copy guard dashboard", "host": "host " + "compatibility"},
        linked_catalog_assets=[
            {
                "asset_id": "copy-guard-host-context",
                "asset_display_name": "compatible " + "host record",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "reference_origin": "Expression Wizard catalog context",
                    "project_documentation_context": "compatibility " + "proof",
                },
                "review_status_snapshot": {
                    "curation_statuses": "host " + "readiness",
                    "missing_metadata_count": 1,
                },
                "asset_snapshot": {
                    "asset_label": "ready " + "host",
                    "source_label": "validated " + "host",
                    "documentation_status": "recommended " + "host",
                },
            }
        ],
    )

    rendered = str(dashboard).lower()
    for unsafe in [
        "host " + "compatibility",
        "compatible " + "host",
        "compatibility " + "proof",
        "host " + "readiness",
        "ready " + "host",
        "validated " + "host",
        "recommended " + "host",
    ]:
        assert unsafe not in rendered
    assert "host context documentation" in rendered
