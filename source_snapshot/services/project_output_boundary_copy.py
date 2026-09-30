from __future__ import annotations

PROJECT_OUTPUT_SCOPE_NOTE = (
    "This is a local, read-only, documentation-only Project Outputs review surface for manual review."
)
PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE = (
    "It is not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment."
)
PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE = (
    "It does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state."
)
PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE = (
    "It does not change project data, package data, saved records, database state, or import/export schema."
)


def project_output_boundary_notes(*, include_no_data_change: bool = False) -> list[str]:
    notes = [
        PROJECT_OUTPUT_SCOPE_NOTE,
        PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
        PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    ]
    if include_no_data_change:
        notes.append(PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE)
    return notes
