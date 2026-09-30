from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs" / "project_import_mvp_implementation_plan.md"


def _plan_text() -> str:
    assert PLAN_PATH.exists(), "Project import MVP implementation plan document is missing."
    return PLAN_PATH.read_text(encoding="utf-8").lower()


def test_project_import_mvp_plan_declares_scope_and_safety_boundaries():
    text = _plan_text()

    required_phrases = [
        "import as new project only",
        "no overwrite",
        "no merge",
        "documentation-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "computational previews",
        "review records only",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_project_import_mvp_plan_requires_id_remapping_and_no_raw_payload_restore():
    text = _plan_text()

    required_phrases = [
        "project_id remapping",
        "pathway_step_id remapping",
        "linked_tool_artifact_id remapping",
        "test_record_id remapping",
        "raw payload restoration",
        "out of scope",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_project_import_mvp_plan_documents_schema_and_future_test_requirements():
    text = _plan_text()

    required_phrases = [
        "mvp should avoid schema migration if possible",
        "database write calls limited to approved repository apis",
        "transaction rollback on error",
        "completeness / evidence matrix / review signals not falsely boosted",
    ]

    for phrase in required_phrases:
        assert phrase in text
