from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_DOC = ROOT / "docs" / "archive" / "historical-root" / "main_workflow_manual_ui_smoke_checklist_v1_15_1.md"
TEST_FILE = ROOT / "tests" / "test_main_workflow_manual_ui_smoke_checklist_v1_15_1.py"


def _checklist_text() -> str:
    return CHECKLIST_DOC.read_text(encoding="utf-8")


def test_v1_15_1_main_workflow_manual_ui_smoke_checklist_exists() -> None:
    assert CHECKLIST_DOC.exists()


def test_v1_15_1_required_sections_exist() -> None:
    text = _checklist_text()
    required_sections = [
        "Executive summary",
        "Test environment",
        "Manual test data",
        "Expression Wizard smoke path",
        "Wizard reset/load state smoke path",
        "Dashboard / Saved Design smoke path",
        "Pathway Projects / Pathway Workspace smoke path",
        "Saved Documentation Artifacts smoke path",
        "Export package smoke path",
        "Import Package Preview / Safety Check smoke path",
        "Negative safety checks",
        "Pass / fail criteria",
        "Release gate usage",
        "Recommended future automation",
    ]
    for section in required_sections:
        assert section in text


def test_v1_15_1_main_workflow_steps_are_covered() -> None:
    text = _checklist_text()
    required_steps = [
        "Step 1 Gene Input",
        "Step 2 Host / Elements",
        "Step 3 Expression Frame / Codon Usage Preview",
        "Step 4 Primer / Cloning Preview",
        "Step 5 Review / Validation Preview",
        "Step 6 Export / Save",
    ]
    for step in required_steps:
        assert step in text


def test_v1_15_1_v1_14_stability_fixes_are_covered() -> None:
    text = _checklist_text()
    required_phrases = [
        "stale primer result guard",
        "stale review result guard",
        "Start new design clears primer task state",
        "Start new design clears validation task state",
        "Load saved design hydrates wf_p1_name and wf_p1_seq",
        "saved design ID",
        "internal load key",
        "Import Package Safety Check Report",
        "NOT_EVALUATED checks are honest and do not fake pass",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_1_safety_boundary_is_covered() -> None:
    text = _checklist_text()
    required_phrases = [
        "documentation-only",
        "computational preview only",
        "review records only",
        "read-only safety check",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "real import execution remains disabled / NO-GO",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_1_negative_safety_denylist_is_covered() -> None:
    text = _checklist_text()
    denied_claims = [
        "successful cloning",
        "successful PCR",
        "successful expression",
        "validation success",
        "validated construct",
        "ready for experiment",
        "experiment-ready",
        "production-ready",
        "yield prediction",
        "optimized pathway",
        "successful import",
        "validated import",
    ]
    for claim in denied_claims:
        assert claim in text


def test_v1_15_1_pass_fail_criteria_are_covered() -> None:
    text = _checklist_text()
    required_phrases = [
        "Any FAIL blocks stable tag",
        "full pytest passes",
        "import preview writes database or creates project",
        "delete removes wrong saved design",
        "saved design loads wrong sequence/name",
        "Import Project / Execute Import button appears",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_1_changes_do_not_enable_import_execution() -> None:
    combined_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CHECKLIST_DOC, TEST_FILE)
    )
    forbidden_phrases = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined_text
