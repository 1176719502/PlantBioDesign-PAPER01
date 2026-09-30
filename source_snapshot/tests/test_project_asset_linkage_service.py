# -*- coding: utf-8 -*-
"""Focused regression tests for project asset linkage records."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import project_asset_linkage_service as linkage_service


def _link(**overrides):
    base = {
        "project_id": "pathway-project-001",
        "asset_id": "asset-001",
        "asset_display_name": "Local promoter documentation record",
        "asset_type": "promoter",
        "linkage_role": "project_reference",
        "documentation_note": "Documentation-only reference for project traceability.",
        "source_context_snapshot": {"source_review_status": "source review needed"},
        "review_status_snapshot": {"human_review_status": "human review needed"},
        "linked_at": "2026-06-15T10:00:00Z",
        "human_review_required": True,
    }
    base.update(overrides)
    return linkage_service.build_project_asset_link(**base)


def test_valid_link_creation():
    link = _link()

    assert link["project_id"] == "pathway-project-001"
    assert link["asset_id"] == "asset-001"
    assert link["linkage_role"] == "project_reference"
    assert link["human_review_required"] is True


def test_missing_required_fields_raise():
    with pytest.raises(ValueError) as excinfo:
        linkage_service.build_project_asset_link(
            project_id="",
            asset_id="asset-001",
            asset_display_name="Local promoter documentation record",
            asset_type="promoter",
            linkage_role="project_reference",
        )

    assert "project_id must not be empty" in str(excinfo.value)


def test_invalid_linkage_role_rejected():
    with pytest.raises(ValueError) as excinfo:
        _link(linkage_role="best_match")

    assert "unrecognized linkage_role" in str(excinfo.value)


def test_human_review_required_defaults_true():
    link = linkage_service.build_project_asset_link(
        project_id="pathway-project-001",
        asset_id="asset-002",
        asset_display_name="Local source note",
        asset_type="literature_source_note",
        linkage_role="source_review_context",
    )

    assert link["human_review_required"] is True


def test_summary_counts_by_asset_type_and_role():
    links = [
        _link(asset_id="asset-001", asset_type="promoter", linkage_role="project_reference"),
        _link(asset_id="asset-002", asset_type="promoter", linkage_role="design_record_context"),
        _link(asset_id="asset-003", asset_type="literature_source_note", linkage_role="report_context"),
    ]

    summary = linkage_service.summarize_project_asset_links(links)

    assert summary["total_links"] == 3
    assert summary["by_asset_type"]["promoter"] == 2
    assert summary["by_asset_type"]["literature_source_note"] == 1
    assert summary["by_linkage_role"]["project_reference"] == 1
    assert summary["by_linkage_role"]["design_record_context"] == 1
    assert summary["by_linkage_role"]["report_context"] == 1


def test_filtering_by_project_id():
    links = [
        _link(project_id="pathway-project-001", asset_id="asset-001"),
        _link(project_id="pathway-project-002", asset_id="asset-002"),
    ]

    filtered = linkage_service.filter_links_by_project(links, "pathway-project-001")

    assert [row["asset_id"] for row in filtered] == ["asset-001"]


def test_append_project_asset_link_adds_new_link_once():
    links = [_link(asset_id="asset-001", linkage_role="project_reference")]

    updated_links, added = linkage_service.append_project_asset_link(
        links,
        _link(asset_id="asset-002", linkage_role="candidate_context"),
    )

    assert added is True
    assert [row["asset_id"] for row in updated_links] == ["asset-001", "asset-002"]


def test_append_project_asset_link_rejects_duplicate_identity():
    links = [_link(asset_id="asset-001", linkage_role="project_reference")]

    updated_links, added = linkage_service.append_project_asset_link(
        links,
        _link(asset_id="asset-001", linkage_role="project_reference", documentation_note="Updated note"),
    )

    assert added is False
    assert updated_links == links


def test_merge_project_asset_links_prefers_latest_duplicate_identity():
    merged = linkage_service.merge_project_asset_links(
        [_link(asset_id="asset-001", linkage_role="project_reference", documentation_note="Initial note")],
        [_link(asset_id="asset-001", linkage_role="project_reference", documentation_note="Updated note")],
        [_link(asset_id="asset-002", linkage_role="candidate_context")],
    )

    assert len(merged) == 2
    assert merged[0]["asset_id"] == "asset-001"
    assert merged[0]["documentation_note"] == "Updated note"
    assert merged[1]["asset_id"] == "asset-002"


def test_report_links_needing_review_uses_human_review_flag_and_snapshot():
    links = [
        _link(asset_id="asset-001", human_review_required=True),
        _link(asset_id="asset-002", human_review_required=False, review_status_snapshot={"status": "review needed"}),
        _link(asset_id="asset-003", human_review_required=False, review_status_snapshot={"status": "complete"}),
    ]

    review_links = linkage_service.report_links_needing_review(links)

    assert {row["asset_id"] for row in review_links} == {"asset-001", "asset-002"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("documentation_note", "This is a recommended and validated asset."),
        ("documentation_note", "Suitable for experimental use."),
        ("documentation_note", "Compatibility confirmed and ready."),
        ("asset_display_name", "Recommended asset"),
    ],
)
def test_forbidden_overclaiming_wording_rejected(field, value):
    payload = {
        "project_id": "pathway-project-001",
        "asset_id": "asset-001",
        "asset_display_name": "Local promoter documentation record",
        "asset_type": "promoter",
        "linkage_role": "project_reference",
        "documentation_note": "Documentation-only reference.",
        "source_context_snapshot": {"source_review_status": "source review needed"},
        "review_status_snapshot": {"human_review_status": "human review needed"},
    }
    payload[field] = value

    with pytest.raises(ValueError) as excinfo:
        linkage_service.build_project_asset_link(**payload)

    assert "forbidden wording" in str(excinfo.value)


def test_snapshot_fields_must_be_dictionaries():
    with pytest.raises(ValueError) as excinfo:
        _link(source_context_snapshot="not a dict")

    assert "snapshot fields must be dictionaries" in str(excinfo.value)


def test_service_terms_stay_documentation_only():
    allowed_roles_blob = "\n".join(linkage_service.ALLOWED_LINKAGE_ROLES).lower()
    forbidden = [
        "recommend" + "ed",
        "recommend" + "ation",
        "suit" + "able",
        "suit" + "ability",
        "compat" + "ible",
        "compat" + "ibility",
        "valid" + "ated",
        "valid" + "ation",
        "read" + "iness",
        "experimental use",
        "experiment-ready",
    ]

    assert [phrase for phrase in forbidden if phrase in allowed_roles_blob] == []
