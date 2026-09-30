from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services import wizard_catalog_linkage_presenter as presenter


def _record(asset_id: str, asset_type: str, display_name: str, aliases=None, tags=None) -> dict:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "aliases": aliases or [],
        "short_description": "Metadata-only catalog record.",
        "organism_or_source_context": "source context placeholder",
        "sequence_available": False,
        "sequence_hash": "",
        "sequence_hash_algorithm": "",
        "source_notes": "Source review note.",
        "provenance_status": "source review needed",
        "version_context": "test seed",
        "review_status": "human review needed",
        "human_review_notes": "Review note.",
        "tags": tags or [],
        "documentation_boundary_note": "Documentation-only record.",
    }


def _session() -> DesignSession:
    return DesignSession(
        gene_name="demo_gene",
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        elements={
            "promoter_name": "T7 promoter",
            "rbs_name": "B0034 RBS",
            "terminator_name": "rrnB terminator",
        },
    )


def test_wizard_selections_map_to_catalog_asset_types():
    selections = presenter.wizard_catalog_reference_selections(_session())

    by_key = {row["selection_key"]: row for row in selections}
    assert by_key["host"]["asset_type"] == "host_chassis_context_note"
    assert by_key["promoter"]["asset_type"] == "promoter"
    assert by_key["rbs_or_kozak"]["asset_type"] == "rbs_5utr"
    assert by_key["terminator"]["asset_type"] == "terminator"
    assert by_key["tag"]["asset_type"] == "tag"
    assert by_key["cds_target"]["asset_type"] == "cds_target"


def test_no_tag_is_not_linked_as_a_candidate_selection():
    ds = _session()
    ds.tag = "No tag"

    selections = presenter.wizard_catalog_reference_selections(ds)

    assert "tag" not in {row["selection_key"] for row in selections}


def test_build_candidates_matches_display_alias_tags_and_asset_type_without_scoring():
    records = [
        _record("asset-host", "host_chassis_context_note", "E.coli host context note", aliases=["BL21"]),
        _record("asset-prom", "promoter", "T7 promoter documentation record", aliases=["t7 promoter"]),
        _record("asset-rbs", "rbs_5utr", "Translation initiation documentation record", tags=["B0034 RBS"]),
        _record("asset-term", "terminator", "rrnB terminator source note"),
        _record("asset-tag", "tag", "His6 tag context note", aliases=["His6-tag"]),
        _record("asset-cds", "cds_target", "CDS target documentation note", tags=["demo_gene"]),
    ]

    candidates = presenter.build_wizard_catalog_reference_candidates(_session(), records)

    assert {row["asset_id"] for row in candidates} == {
        "asset-host",
        "asset-prom",
        "asset-rbs",
        "asset-term",
        "asset-tag",
        "asset-cds",
    }
    assert all(row["human_review_required"] is True for row in candidates)
    assert all("score" not in row for row in candidates)
    assert all("rank" not in row for row in candidates)


def test_candidate_to_project_link_uses_safe_role_and_review_snapshots():
    candidate = presenter.build_wizard_catalog_reference_candidates(
        _session(),
        [_record("asset-prom", "promoter", "T7 promoter documentation record", aliases=["t7 promoter"])],
    )[0]

    link = presenter.build_wizard_catalog_project_link(
        project_id=5,
        candidate=candidate,
        linked_at="session",
    )

    assert link["project_id"] == "5"
    assert link["asset_id"] == "asset-prom"
    assert link["linkage_role"] == "design_record_context"
    assert link["human_review_required"] is True
    assert link["documentation_note"] == "Documentation-only Wizard reference for promoter context."
    assert link["source_context_snapshot"]["wizard_field"] == "promoter"
    assert link["review_status_snapshot"]["review_status"] == "human review needed"


def test_append_wizard_links_reports_duplicates():
    candidate = presenter.build_wizard_catalog_reference_candidates(
        _session(),
        [_record("asset-prom", "promoter", "T7 promoter documentation record", aliases=["t7 promoter"])],
    )[0]

    links, added, duplicates = presenter.append_wizard_catalog_project_links(
        [],
        project_id=5,
        candidates=[candidate],
        linked_at="session",
    )
    links, added_again, duplicates_again = presenter.append_wizard_catalog_project_links(
        links,
        project_id=5,
        candidates=[candidate],
        linked_at="session",
    )

    assert added == 1
    assert duplicates == 0
    assert added_again == 0
    assert duplicates_again == 1
    assert len(links) == 1


def test_presenter_copy_uses_documentation_boundary():
    copy_blob = "\n".join(
        [
            presenter.CATALOG_REFERENCE_BOUNDARY_COPY,
            presenter.CATALOG_REFERENCE_EMPTY_COPY,
            "\n".join(presenter.WIZARD_SELECTION_LINKAGE_ROLES.values()),
        ]
    ).lower()

    assert "documentation context only" in copy_blob
    assert "human review is required" in copy_blob
    for phrase in [
        "best",
        "ranking",
        "score",
        "optimization",
        "prediction",
        "experiment" + "-ready",
        "production" + "-ready",
    ]:
        assert phrase not in copy_blob
