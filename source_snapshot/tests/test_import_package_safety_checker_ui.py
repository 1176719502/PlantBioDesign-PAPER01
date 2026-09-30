from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ROOT_PATH = Path(ROOT)
PATHWAY_WORKSPACE = ROOT_PATH / "views" / "PathwayWorkspace.py"
SAFETY_CHECKER = ROOT_PATH / "services" / "project_import_package_safety_checker.py"
IMPORT_SAFETY_SECTION = ROOT_PATH / "views" / "pathway_workspace_sections" / "import_safety_section.py"
IMPORT_PREVIEW_SECTION = ROOT_PATH / "views" / "pathway_workspace_sections" / "import_preview_section.py"


def _source() -> str:
    return "\n".join(
        [
            PATHWAY_WORKSPACE.read_text(encoding="utf-8"),
            IMPORT_SAFETY_SECTION.read_text(encoding="utf-8"),
            SAFETY_CHECKER.read_text(encoding="utf-8"),
        ]
    )


def test_import_package_safety_checker_ui_copy_present() -> None:
    source = _source()

    for expected in [
        "Import Package Safety Check Report",
        "This is a read-only safety check.",
        "This report does not import or modify any project.",
        "No database writes are performed.",
        "Blocked / NO-GO safety states stop the separate gated create-as-new action.",
        "This report never creates a project.",
        "Safe for read-only review.",
        "Review warnings before future import planning.",
        "Package is blocked for future execution planning until issues are resolved.",
        "This check could not be evaluated from the available package metadata.",
        "This report does not certify experimental readiness.",
        "This report does not predict yield.",
        "This report does not optimize pathways.",
        "This report does not provide wet-lab protocols.",
    ]:
        assert expected in source


def test_import_safety_locked_no_execution_controls_or_calls() -> None:
    preview_source = "\n".join(
        [
            IMPORT_PREVIEW_SECTION.read_text(encoding="utf-8"),
            IMPORT_SAFETY_SECTION.read_text(encoding="utf-8"),
        ]
    )

    forbidden = [
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]

    assert not [term for term in forbidden if term in preview_source]
