from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGED_COPY_FILES = [
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "views" / "pathway_workspace_sections" / "export_package_section.py",
    ROOT / "services" / "project_export_package_service.py",
]


def _changed_copy() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_COPY_FILES)


def test_export_user_flow_copy_present() -> None:
    copy = _changed_copy()

    required = [
        "Project Export Package",
        "Documentation-only package summary for review, traceability, and local archive use.",
        "This package is for review, traceability, read-only validation, and archival use only.",
        "Next action: review package contents, download the package, then use Import Preview for read-only structure and field checks.",
        "this export does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab instructions.",
    ]

    for phrase in required:
        assert phrase in copy


def test_package_contents_guidance_present() -> None:
    copy = _changed_copy()

    required = [
        "Package contents preview",
        "Includes project summary, pathway steps, review notes, documentation snapshots, linked documentation artifacts, and manifest metadata when available.",
        "Package contents are documentation records only.",
        "Raw payload previews are for traceability only.",
    ]

    for phrase in required:
        assert phrase in copy


def test_post_download_next_steps_present() -> None:
    copy = _changed_copy()

    required = [
        "Download the documentation package.",
        "Keep the package as a review/archive artifact.",
        "Use Project Import Package Preview for read-only package structure checks.",
        "Keep review decisions separate from readiness or execution claims.",
        "Blocked / NO-GO states apply only to the gated create-as-new action",
    ]

    for phrase in required:
        assert phrase in copy


def test_import_preview_relationship_copy_present() -> None:
    copy = _changed_copy()

    required = [
        "read-only preview",
        "no database writes",
        "This preview does not import or modify any project.",
        "It validates package structure and shows a dry-run import plan.",
        "A separate gated import-as-new action may create a local documentation-only project only after validation, safety review, dry-run planning, and explicit confirmation.",
        "Blocked / NO-GO safety states stop the separate gated create-as-new action.",
    ]

    for phrase in required:
        assert phrase in copy


def test_safety_boundary_copy_present() -> None:
    copy = _changed_copy()

    required = [
        "documentation-only",
        "no overwrite",
        "no merge",
        "no raw payload_json restoration",
        "computational previews",
        "review records only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
    ]

    for phrase in required:
        assert phrase in copy


def test_forbidden_misleading_copy_absent_in_changed_files() -> None:
    copy = _changed_copy().lower()

    forbidden = [
        "experiment-ready package",
        "production-ready package",
        "validated import",
        "successful import",
        "import now",
        "ready to import",
        "ready for execution",
        "wet-lab protocol generated",
        "yield prediction result",
        "optimized pathway package",
        "validated pathway package",
    ]

    for phrase in forbidden:
        assert phrase not in copy


def test_import_safety_still_gated_in_ui_and_changed_files() -> None:
    copy = _changed_copy()

    required = [
        "read-only preview",
        "No database writes are performed by preview and safety checks.",
        "Create New Documentation Project",
        "final confirmation",
        "Documentation project creation requires all explicit gates.",
        "documentation-only",
        "does not certify experimental readiness",
    ]
    forbidden = [
        "execute_project_import_as_new_project",
        "enable_database_write=True",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]

    for phrase in required:
        assert phrase in copy
    for phrase in forbidden:
        assert phrase not in copy
