# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import builtins
from pathlib import Path

from services import candidate_evidence_review_matrix as matrix
from services import candidate_evidence_review_snapshot_formatter as snapshot_formatter


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("valid", "ated ", "con", "struct"),
    _term("optimized ", "pathway"),
    _term("yield ", "pre", "diction"),
    _term("recom", "mended"),
    _term("best"),
    _term("top ", "candidate"),
    _term("rank", "ing"),
    _term("scor", "ing"),
    _term("optim", "ization"),
    _term("pre", "diction"),
    _term("vali", "dated"),
    _term("experimentally ", "confirmed"),
    _term("ready ", "for synthesis"),
    _term("ready ", "for wet lab"),
    _term("host ", "compatibility"),
)


def _complete_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "candidate_label": "Maize promoter source context",
        "source_category": "Plant Promoter Catalog",
        "source_identifier": "PP-TRACE-001",
        "source_hash": "sha256:abc123",
        "review_status": "source review recorded",
    }
    record.update(overrides)
    return record


def test_empty_input_returns_safe_empty_state() -> None:
    view = matrix.build_candidate_evidence_review_matrix([])

    assert view["rows"] == []
    assert view["summary"]["candidate_count"] == 0
    assert view["summary"]["documentation_complete_count"] == 0
    assert view["empty_state_message"]
    assert "documentation-only" in view["boundary_note"].lower()


def test_complete_metadata_returns_documentation_complete_status() -> None:
    view = matrix.build_candidate_evidence_review_matrix([_complete_record()])

    assert view["summary"]["candidate_count"] == 1
    assert view["summary"]["documentation_complete_count"] == 1
    assert view["summary"]["metadata_incomplete_count"] == 0

    row = view["rows"][0]
    assert row["candidate_label"] == "Maize promoter source context"
    assert row["provenance_status"] == "source trace recorded"
    assert row["metadata_status"] == "documentation-complete"
    assert row["record_review_status"] == "documentation-complete"
    assert row["review_focus"] == "manual follow-up review"
    assert row["gap_label"] == "No required documentation fields missing"
    assert row["missing_fields"] == []
    assert row["next_manual_action"] == matrix.COMPLETE_METADATA_ACTION


def test_missing_source_identifier_hash_and_review_metadata_produces_missing_fields() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        [
            {
                "candidate_label": "Partial candidate source context",
            }
        ]
    )

    row = view["rows"][0]
    assert row["metadata_status"] == "metadata-incomplete"
    assert row["record_review_status"] == "metadata-incomplete"
    assert row["provenance_status"] == "source trace missing"
    assert row["review_focus"] == "source/provenance and record review"
    assert row["gap_label"] == "source/provenance and record review"
    assert row["missing_fields"] == [
        "source_category",
        "source_identifier",
        "source_hash",
        "review_status",
    ]
    assert row["next_manual_action"] == matrix.MISSING_METADATA_ACTION
    assert view["summary"]["metadata_incomplete_count"] == 1
    assert view["summary"]["source_trace_missing_count"] == 1


def test_missing_review_status_only_points_to_evidence_record_review() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        [
            _complete_record(review_status=""),
        ]
    )

    row = view["rows"][0]
    assert row["missing_fields"] == ["review_status"]
    assert row["review_focus"] == "evidence-record review"
    assert row["gap_label"] == "evidence-record review"
    assert row["next_manual_action"] == matrix.MISSING_METADATA_ACTION


def test_placeholder_source_and_review_values_are_missing_metadata() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        [
            {
                "candidate_label": "Placeholder source trace",
                "source_category": "Not specified",
                "source_identifier": "Unknown",
                "source_hash": "TBD",
                "review_status": "N/A",
            },
            {
                "candidate_label": "None placeholder source trace",
                "source_category": "None",
                "source_identifier": "",
                "source_hash": "none",
                "review_status": "Unknown",
            },
        ]
    )

    assert view["summary"]["candidate_count"] == 2
    assert view["summary"]["documentation_complete_count"] == 0
    assert view["summary"]["metadata_incomplete_count"] == 2
    assert view["summary"]["source_trace_missing_count"] == 2
    for row in view["rows"]:
        assert row["metadata_status"] == "metadata-incomplete"
        assert row["provenance_status"] == "source trace missing"
        assert row["missing_fields"] == [
            "source_category",
            "source_identifier",
            "source_hash",
            "review_status",
        ]


def test_external_candidate_records_are_not_promoted_to_curated_runtime_seed() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        [
            _complete_record(
                candidate_label="NCBI trace candidate",
                source_category="NCBI Nucleotide / GenBank",
                source_identifier="S51061.1",
                source_review_status="source_candidate_identified",
                curation_status="not_curated_yet",
                not_runtime_seed=True,
            )
        ]
    )

    row = view["rows"][0]
    assert row["metadata_status"] == "documentation-complete"
    assert row["external_candidate"] is True
    assert row["curation_boundary_status"] == matrix.RUNTIME_SEED_BLOCKED_STATUS
    assert row["next_manual_action"] == matrix.EXTERNAL_SOURCE_ACTION
    assert view["summary"]["external_candidate_count"] == 1
    assert view["summary"]["runtime_seed_intake_blocked_count"] == 1


def test_view_model_candidate_rows_are_accepted_without_repository_access() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        {
            "candidate_rows": [
                _complete_record(candidate_label="View model candidate"),
            ]
        }
    )

    assert [row["candidate_label"] for row in view["rows"]] == ["View model candidate"]
    assert view["summary"]["candidate_count"] == 1


def test_no_ordering_metric_or_selection_advice_wording_appears() -> None:
    text = str(
        matrix.build_candidate_evidence_review_matrix(
            [
                _complete_record(candidate_label="Alpha candidate"),
                {
                    "candidate_label": "Partial candidate",
                },
            ]
        )
    ).lower()
    service_text = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "candidate_evidence_review_matrix.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in text
        assert forbidden not in service_text


def test_row_order_is_deterministic_by_label_category_and_identifier() -> None:
    view = matrix.build_candidate_evidence_review_matrix(
        [
            _complete_record(
                candidate_label="Zulu candidate",
                source_category="Catalog B",
                source_identifier="B-002",
            ),
            _complete_record(
                candidate_label="Alpha candidate",
                source_category="Catalog Z",
                source_identifier="Z-001",
            ),
            _complete_record(
                candidate_label="Alpha candidate",
                source_category="Catalog A",
                source_identifier="A-001",
            ),
        ]
    )

    assert [
        (row["candidate_label"], row["source_category"], row["source_identifier"])
        for row in view["rows"]
    ] == [
        ("Alpha candidate", "Catalog A", "A-001"),
        ("Alpha candidate", "Catalog Z", "Z-001"),
        ("Zulu candidate", "Catalog B", "B-002"),
    ]


def test_service_does_not_import_streamlit(monkeypatch) -> None:
    original_import = builtins.__import__

    def _block_streamlit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("candidate evidence review matrix must not import Streamlit")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit_import)

    view = matrix.build_candidate_evidence_review_matrix([_complete_record()])

    assert view["summary"]["candidate_count"] == 1
    importlib.reload(matrix)


def test_empty_matrix_snapshot_is_safe_and_copy_friendly() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        matrix.build_candidate_evidence_review_matrix([])
    )

    assert snapshot.startswith("# Candidate Evidence Review Snapshot")
    assert "Documentation-only evidence review snapshot" in snapshot
    assert "- candidate records: 0" in snapshot
    assert "## Empty state" in snapshot
    assert "manual review planning only" in snapshot
    assert "documentation triage" in snapshot
    assert "does not order candidates" in snapshot
    assert "assign numeric review values" in snapshot


def test_snapshot_complete_and_missing_metadata_counts_are_reported() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        [
            _complete_record(candidate_label="Complete source trace"),
            {"candidate_label": "Partial source trace", "source_category": "Local notes"},
        ]
    )

    assert "- candidate records: 2" in snapshot
    assert "- record review complete: 1" in snapshot
    assert "- record review gaps: 1" in snapshot
    assert "- source trace recorded: 1" in snapshot
    assert "- source trace incomplete: 1" in snapshot


def test_snapshot_missing_fields_are_grouped_deterministically() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        [
            {"candidate_label": "Zulu partial"},
            {"candidate_label": "Alpha partial"},
        ]
    )

    source_category_index = snapshot.index("- source_category: 2 record(s)")
    source_identifier_index = snapshot.index("- source_identifier: 2 record(s)")
    source_hash_index = snapshot.index("- source_hash: 2 record(s)")
    review_status_index = snapshot.index("- review_status: 2 record(s)")
    assert source_category_index < source_identifier_index < source_hash_index < review_status_index
    assert snapshot.index("  - Alpha partial", source_category_index) < snapshot.index(
        "  - Zulu partial",
        source_category_index,
    )


def test_snapshot_next_manual_curation_actions_appear() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        [
            _complete_record(candidate_label="Complete source trace"),
            {"candidate_label": "Partial source trace"},
        ]
    )

    assert "## Next documentation review actions" in snapshot
    assert matrix.COMPLETE_METADATA_ACTION in snapshot
    assert matrix.MISSING_METADATA_ACTION in snapshot


def test_snapshot_includes_demo_friendly_read_only_triage_notes() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        [_complete_record(candidate_label="Alpha candidate")]
    )

    assert "what is documented, what is missing, and what still needs human follow-up" in snapshot
    assert "review aid for human discussion only" in snapshot
    assert "does not order candidates" in snapshot
    assert "suggest a preferred option" in snapshot
    assert "judge wet-lab use state" in snapshot


def test_snapshot_avoids_unsafe_claim_wording() -> None:
    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(
        [
            _complete_record(candidate_label="Alpha candidate"),
            {"candidate_label": "Partial candidate"},
        ]
    ).lower()
    service_text = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "candidate_evidence_review_snapshot_formatter.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in snapshot
        assert forbidden not in service_text


def test_snapshot_normalizes_generated_boundary_terms_without_changing_matrix_payload() -> None:
    matrix_payload = matrix.build_candidate_evidence_review_matrix(
        [
            {
                "candidate_label": "Host compatibility / compatible host trace",
            }
        ]
    )

    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot(matrix_payload).lower()

    assert "host compatibility" in str(matrix_payload).lower()
    assert "compatible host" in str(matrix_payload).lower()
    assert "host/context documentation" in snapshot
    assert "host context record" in snapshot
    assert "host compatibility" not in snapshot
    assert "compatible host" not in snapshot


def test_snapshot_guard_rejects_non_normalized_unsafe_generated_claim() -> None:
    matrix_payload = matrix.build_candidate_evidence_review_matrix(
        [{"candidate_label": "validated construct"}]
    )

    try:
        snapshot_formatter.format_candidate_evidence_review_snapshot(matrix_payload)
    except ValueError as exc:
        assert "Misleading candidate evidence review snapshot claim detected: validated construct" in str(exc)
    else:
        raise AssertionError("Expected candidate evidence review snapshot guard to reject unsafe generated claim.")


def test_snapshot_formatter_does_not_import_streamlit(monkeypatch) -> None:
    original_import = builtins.__import__

    def _block_streamlit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("candidate evidence review snapshot formatter must not import Streamlit")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit_import)

    snapshot = snapshot_formatter.format_candidate_evidence_review_snapshot([_complete_record()])

    assert "# Candidate Evidence Review Snapshot" in snapshot
    importlib.reload(snapshot_formatter)
