# -*- coding: utf-8 -*-
"""V2.3-R5 read-only parts linkage display presenter tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_browse_presenter as presenter


def _part() -> dict:
    return {
        "local_id": "part-local-001",
        "part_type": "Promoter",
        "display_name": "Local promoter documentation record",
        "description": "Local catalog metadata record for provenance review.",
        "created_at": "2026-06-12T09:00:00",
        "updated_at": "2026-06-12T09:00:00",
    }


def _version(version_id: int = 7) -> dict:
    return {
        "id": version_id,
        "part_local_id": "part-local-001",
        "version_label": "metadata-only-v1",
        "sequence": None,
        "sequence_hash": None,
        "sequence_hash_algorithm": None,
        "version_note": "Version record preserves metadata without sequence.",
        "created_at": "2026-06-12T09:10:00",
        "updated_at": "2026-06-12T09:10:00",
    }


def _link(*, version_id: int | None = None) -> dict:
    return {
        "id": 11,
        "part_local_id": "part-local-001",
        "part_version_id": version_id,
        "target_type": "pathway_project",
        "target_id": "pathway-project-001",
        "target_label": "Pathway documentation project alpha",
        "link_note": "Human review context for linked documentation record.",
        "review_status": "traceability review needed",
        "created_at": "2026-06-12T09:20:00",
        "updated_at": "2026-06-12T09:30:00",
    }


def _patch_repo(monkeypatch, *, versions=None, links=None):
    monkeypatch.setattr(presenter.repo, "list_versions_for_part", lambda local_id: versions or [])
    monkeypatch.setattr(presenter.repo, "list_source_records", lambda local_id: [])
    monkeypatch.setattr(presenter.repo, "list_annotations", lambda local_id: [])
    monkeypatch.setattr(presenter.repo, "list_review_status_records", lambda local_id: [])
    monkeypatch.setattr(presenter.repo, "list_links_for_part", lambda local_id: links or [])


def test_part_with_no_linkage_builds_empty_display(monkeypatch):
    _patch_repo(monkeypatch, versions=[_version()], links=[])

    record = presenter.build_part_browse_record(_part())

    assert record["linkage_record_count"] == 0
    assert record["linkage_records"] == []


def test_part_with_one_linkage_builds_display_row(monkeypatch):
    _patch_repo(monkeypatch, versions=[_version()], links=[_link()])

    record = presenter.build_part_browse_record(_part())
    link_row = record["linkage_records"][0]

    assert record["linkage_record_count"] == 1
    assert link_row["Target type"] == "pathway_project"
    assert link_row["Target label snapshot"] == "Pathway documentation project alpha"
    assert link_row["Link note"] == "Human review context for linked documentation record."
    assert link_row["Review status"] == "traceability review needed"
    assert link_row["Part version context"] == "Part-level link"
    assert link_row["Created at"] == "2026-06-12T09:20:00"
    assert link_row["Updated at"] == "2026-06-12T09:30:00"


def test_version_specific_linkage_uses_version_label_context(monkeypatch):
    _patch_repo(monkeypatch, versions=[_version(7)], links=[_link(version_id=7)])

    record = presenter.build_part_browse_record(_part())

    assert record["linkage_records"][0]["Part version context"] == "metadata-only-v1"


def test_version_specific_linkage_falls_back_to_version_id_when_label_missing():
    rows = presenter.build_linkage_display_records(
        [_link(version_id=99)],
        [_version(7)],
    )

    assert rows[0]["Part version context"] == "Version id 99"


def test_linkage_table_rows_include_traceability_count(monkeypatch):
    _patch_repo(monkeypatch, versions=[_version()], links=[_link()])

    record = presenter.build_part_browse_record(_part())
    rows = presenter.table_rows([record])

    assert rows[0]["Traceability links"] == 1


def test_linkage_display_terms_stay_documentation_traceability_only():
    combined = "\n".join(
        [
            presenter.NO_LINKAGE_LABEL,
            presenter.NO_LINK_VERSION_LABEL,
            *presenter.build_linkage_display_records([_link(version_id=7)], [_version(7)])[0].values(),
        ]
    ).lower()
    forbidden = [
        "recommend" + "ed",
        "approv" + "ed",
        "valid" + "ated",
        "optim" + "al",
        "safe for " + "use",
        "compat" + "ible",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "experimentally " + "confirmed",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
