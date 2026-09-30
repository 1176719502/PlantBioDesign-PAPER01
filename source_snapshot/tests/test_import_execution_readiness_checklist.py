from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_DOC = ROOT / "docs" / "import_execution_readiness_checklist.md"


REQUIRED_TERMS = [
    "Current decision: NO-GO",
    "Create New Documentation Project",
    "valid package",
    "dry-run import plan",
    "explicit confirmation checkbox",
    "final warning",
    "documentation-only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no original id restoration",
    "no validator bypass",
    "no dry-run bypass",
    "enable_database_write=False",
    "enable_database_write=True",
    "execute_project_import_as_new_project",
    "UI must not call repository write APIs directly",
    "no execution should happen during preview",
    "audit summary",
    "limited rollback",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
    "full pytest",
]

FORBIDDEN_ACTION_LABELS = [
    "Import Project",
    "Execute Import",
    "Confirm Import",
    "Restore Project",
    "Merge Project",
    "Overwrite Project",
    "Import now",
    "Ready to import",
]


ALLOWED_ACTION_SECTION_PATTERN = re.compile(
    r"## 3\. Allowed future action name(?P<section>.*?)## 4\. Required execution boundary",
    re.DOTALL,
)


def _read_checklist() -> str:
    return CHECKLIST_DOC.read_text(encoding="utf-8")


def test_import_execution_readiness_checklist_doc_exists() -> None:
    assert CHECKLIST_DOC.exists(), "V1.8.8 import execution readiness checklist should exist"


def test_import_execution_readiness_checklist_contains_required_terms() -> None:
    content = _read_checklist()
    normalized = content.lower()

    missing_terms = [term for term in REQUIRED_TERMS if term.lower() not in normalized]

    assert not missing_terms, (
        "Import execution readiness checklist is missing required terms: "
        + ", ".join(missing_terms)
    )


def test_import_execution_readiness_checklist_keeps_forbidden_labels_prohibited() -> None:
    content = _read_checklist()
    section_match = ALLOWED_ACTION_SECTION_PATTERN.search(content)

    assert section_match, "Allowed action section should be present and bounded"

    allowed_action_section = section_match.group("section")
    recommendation_text = allowed_action_section.split("Forbidden / do not use labels:", 1)[0]
    forbidden_text = allowed_action_section.split("Forbidden / do not use labels:", 1)[1]

    assert "Create New Documentation Project" in recommendation_text

    for forbidden_label in FORBIDDEN_ACTION_LABELS:
        assert forbidden_label not in recommendation_text
        assert forbidden_label in forbidden_text

    assert "must not appear as allowed action names" in forbidden_text


def test_import_execution_readiness_checklist_declares_no_go_boundary() -> None:
    content = _read_checklist()

    assert "Current decision: NO-GO for real import execution UI in this build." in content
    assert "Next allowed step: implementation planning only" in content
    assert "separate explicitly approved gated execution branch" in content
