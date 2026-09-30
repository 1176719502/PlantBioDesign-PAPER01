from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "docs" / "qa"

R34 = QA_DIR / "V2_7_R34_PRE_0900_FINAL_COMMAND_DRY_RUN.md"
R35 = QA_DIR / "V2_7_R35_0900_COMPLETION_CRITERIA_GUARD.md"
R36 = QA_DIR / "V2_7_R36_0900_TIMED_READINESS_AUDIT_TEMPLATE.md"
R37 = QA_DIR / "V2_7_R37_0900_STOP_CONDITION_DECISION_GUARD.md"
R38 = QA_DIR / "V2_7_R38_PRE_0900_COMPLETION_CLAIM_GUARD.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_r38_near_final_notes_keep_pre_0900_nonfinal_boundary() -> None:
    expected_by_note = {
        R34: [
            "This is not the final 09:00 checkpoint",
            "pre-09:00 dry run, not final checkpoint completion",
        ],
        R35: [
            "at or after 2026-07-04 09:00 Asia/Shanghai",
            "R34 dry-run evidence is useful but not enough",
        ],
        R36: [
            "This template is not final evidence",
            "PENDING_FINAL_AUDIT",
        ],
        R37: [
            "only after the final timed readiness audit runs at or after 2026-07-04 09:00 Asia/Shanghai",
            "If final evidence is missing or indirect, do not mark the active goal complete",
        ],
        R38: [
            "R38 does not mark the active goal complete",
            "goal completion before the required timed evidence exists",
        ],
    }

    missing: list[str] = []
    for note, expected_phrases in expected_by_note.items():
        source = _read(note)
        for phrase in expected_phrases:
            if phrase not in source:
                missing.append(f"{note.name}: {phrase}")

    assert missing == []


def test_r38_completion_claim_guard_names_required_gate_documents() -> None:
    source = _read(R38)

    for expected in [
        "R34 is a dry run",
        "R35 defines completion criteria",
        "R36 provides a final timed audit template",
        "R37 defines stop-condition decisions",
        "final timed readiness audit runs at or after 09:00",
    ]:
        assert expected in source


def test_r38_completion_claim_guard_preserves_no_commit_and_copy_boundary() -> None:
    source = _read(R38).lower()

    assert "no staging, commit, or tag was performed" in source
    assert "documentation-only" in source
    assert "review-framed" in source

    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
        "lab" + "-ready",
        "wet-lab" + " ready",
        "proven" + " construct",
        "validated" + " pathway",
    ]
    assert [phrase for phrase in forbidden if phrase in source] == []
