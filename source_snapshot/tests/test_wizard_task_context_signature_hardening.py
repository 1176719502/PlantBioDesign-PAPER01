# -*- coding: utf-8 -*-
from pathlib import Path

from services.wizard_task_context_guard import (
    build_stale_primer_task_message,
    build_stale_validation_task_message,
    should_apply_task_result,
)

ROOT = Path(__file__).resolve().parents[1]
STEP4 = ROOT / "views" / "wizard_steps" / "step4_cloning_primers.py"
STEP5 = ROOT / "views" / "wizard_steps" / "step5_validation.py"
SESSION_KEYS = ROOT / "core" / "session_keys.py"
GUARD = ROOT / "services" / "wizard_task_context_guard.py"
MODIFIED_FILES = [STEP4, STEP5, SESSION_KEYS, GUARD]


def test_task_context_guard_matching_signature_applies():
    assert should_apply_task_result("abc", "abc") is True


def test_task_context_guard_mismatched_signature_does_not_apply():
    assert should_apply_task_result("old", "new") is False


def test_task_context_guard_missing_task_signature_does_not_apply():
    assert should_apply_task_result("", "current") is False
    assert should_apply_task_result(None, "current") is False


def test_task_context_guard_missing_current_signature_does_not_apply():
    assert should_apply_task_result("task", "") is False
    assert should_apply_task_result("task", None) is False


def test_stale_task_messages_exist_and_are_safety_scoped():
    primer = build_stale_primer_task_message()
    validation = build_stale_validation_task_message()
    assert "This primer task result was ignored because the design context changed." in primer
    assert "Re-run the primer preview for the current design context." in primer
    assert "This review task result was ignored because the design context changed." in validation
    assert "Re-run the review preview for the current design context." in validation
    assert "computational preview only" in primer
    assert "does not certify experimental readiness" in primer
    assert "computational preview only" in validation
    assert "does not certify experimental readiness" in validation


def test_step4_static_primer_context_signature_guard_before_write():
    text = STEP4.read_text(encoding="utf-8")
    assert "PRIMER_TASK_CONTEXT_SIGNATURE" in text or "primer_task_context_signature" in text
    assert "current_primer_context_signature()" in text
    assert "should_apply_task_result(task_signature, current_signature)" in text
    assert text.index("should_apply_task_result(task_signature, current_signature)") < text.index("ds.primers = _primer_rows_from_structured_results")
    assert "This primer task result was ignored because the design context changed." in text or "build_stale_primer_task_message" in text
    assert "Re-run the primer preview for the current design context." in text or "build_stale_primer_task_message" in text


def test_step5_static_validation_context_signature_guard_before_write():
    text = STEP5.read_text(encoding="utf-8")
    assert "VALIDATION_TASK_CONTEXT_SIGNATURE" in text or "validation_task_context_signature" in text
    assert "current_validation_context_signature()" in text
    assert "should_apply_task_result(task_signature, current_signature)" in text
    assert text.index("should_apply_task_result(task_signature, current_signature)") < text.index("ds.validation_results = merged_issues")
    assert "This review task result was ignored because the design context changed." in text or "build_stale_validation_task_message" in text
    assert "Re-run the review preview for the current design context." in text or "build_stale_validation_task_message" in text


def test_no_misleading_copy_in_modified_files():
    forbidden = [
        "successful cloning",
        "successful PCR",
        "successful expression",
        "validated construct",
        "validation success",
        "ready for experiment",
        "experiment-ready",
        "production-ready",
        "yield prediction",
        "optimized pathway",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in MODIFIED_FILES).lower()
    for phrase in forbidden:
        assert phrase.lower() not in combined


def test_import_safety_unaffected_by_modified_files():
    forbidden = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in MODIFIED_FILES)
    for phrase in forbidden:
        assert phrase not in combined
