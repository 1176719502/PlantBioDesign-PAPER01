# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_presenter as presenter
from services import expression_construct_repository as repo
from services.project_review_report_service import build_project_review_report


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_construct_project_linkage.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _seed_construct(label: str = "Project linked construct", construct_id: str | None = "construct-project") -> dict:
    profile = repo.create_construct_profile(
        construct_id=construct_id,
        construct_label=label,
        construct_type="documentation-only construct draft",
        source_reference="Construct notebook",
        provenance_note="Construct provenance note.",
        review_status="documentation review pending",
    )
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id=f"cassette-{profile['construct_id']}",
        cassette_label=f"{label} cassette",
        cassette_order=1,
        source_reference="Cassette notebook",
        provenance_note="Cassette provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label=f"{label} promoter",
        source_reference="Promoter notebook",
        provenance_note="Promoter provenance note.",
    )
    return profile


def test_schema_startup_includes_project_link_table(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)

    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()

    assert "expression_construct_project_links" in tables


def test_create_update_and_list_project_construct_links(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = _seed_construct()

    link = repo.create_construct_project_link(
        project_id=23,
        construct_id=profile["construct_id"],
        link_label="R23 project construct link",
        link_note="Connects this construct record to project 23 for documentation review.",
        source_context="manual R23 link",
        curation_status="documentation review pending",
        review_note="Review construct provenance with project notes.",
    )
    updated = repo.update_construct_project_link(
        link["id"],
        link_label="Updated R23 project construct link",
        review_note="Updated project-link review note.",
    )

    by_project = repo.list_construct_project_links(project_id=23)
    by_construct = repo.list_construct_project_links(construct_id=profile["construct_id"])
    profiles_for_project = repo.list_construct_profiles_for_project(23)

    assert link["project_id"] == "23"
    assert link["construct_id"] == profile["construct_id"]
    assert updated["link_label"] == "Updated R23 project construct link"
    assert updated["review_note"] == "Updated project-link review note."
    assert [row["id"] for row in by_project] == [link["id"]]
    assert [row["id"] for row in by_construct] == [link["id"]]
    assert profiles_for_project[0]["construct_id"] == profile["construct_id"]
    assert profiles_for_project[0]["project_link_label"] == "Updated R23 project construct link"


def test_project_link_methods_handle_missing_ids_safely(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _seed_construct()

    assert repo.create_construct_project_link(project_id="", construct_id="construct-project") == {}
    assert repo.create_construct_project_link(project_id=23, construct_id="missing") == {}
    assert repo.update_construct_project_link(999999, link_label="Missing") == {}
    assert repo.get_construct_project_link("") == {}
    assert repo.list_construct_project_links() == []
    assert repo.list_construct_project_links(project_id="") == []
    assert repo.list_construct_project_links(construct_id="") == []
    assert repo.list_construct_profiles_for_project("") == []


def test_presenter_counts_and_rows_include_project_links(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = _seed_construct()
    repo.create_construct_project_link(
        project_id="project-r23",
        construct_id=profile["construct_id"],
        link_label="Project R23 link",
        link_note="Documentation link note.",
        source_context="Pathway Workspace manual reference",
        curation_status="documentation review pending",
        review_note="Review note.",
    )

    view_model = presenter.build_expression_construct_presenter(profile["construct_id"])

    assert view_model["summary_counts"]["project_link_count"] == 1
    assert view_model["project_link_rows"][0]["project_id"] == "project-r23"
    assert view_model["project_link_rows"][0]["link_label"] == "Project R23 link"


def test_report_uses_explicit_project_links_before_pathway_step_fallback(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    linked = _seed_construct("Explicit project construct", "construct-explicit")
    fallback = _seed_construct("Fallback step construct", "construct-fallback")
    repo.create_construct_project_link(
        project_id=23,
        construct_id=linked["construct_id"],
        link_label="Explicit project link",
        link_note="Project-level documentation link.",
    )
    repo.create_construct_project_link(
        project_id=99,
        construct_id=linked["construct_id"],
        link_label="Other project link",
        link_note="Separate project documentation link.",
    )
    repo.add_construct_pathway_step_link(
        fallback["construct_id"],
        pathway_step_id="step-1",
        pathway_step_label="Fallback pathway step",
    )

    report = build_project_review_report(
        {
            "id": 23,
            "name": "R23 explicit project",
            "pathway_steps": [{"id": "step-1", "step_name": "Fallback pathway step"}],
        }
    )
    section = report["expression_construct_documentation"]

    assert section["project_scoped_filtering"] == "project-level construct links"
    assert section["summary_counts"]["construct_profile_count"] == 1
    assert section["summary_counts"]["project_link_count"] == 1
    assert "Explicit project construct" in report["markdown"]
    assert "Other project link" not in report["markdown"]
    assert "Fallback step construct" not in report["markdown"]


def test_report_falls_back_to_pathway_step_links_without_explicit_project_links(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _seed_construct("Fallback linked construct", "construct-fallback")
    repo.add_construct_pathway_step_link(
        "construct-fallback",
        pathway_step_id="step-1",
        pathway_step_label="Fallback pathway step",
    )

    report = build_project_review_report(
        {
            "id": 24,
            "name": "R23 fallback project",
            "pathway_steps": [{"id": "step-1", "step_name": "Fallback pathway step"}],
        }
    )
    section = report["expression_construct_documentation"]

    assert section["project_scoped_filtering"] == "pathway_step_id links"
    assert section["summary_counts"]["construct_profile_count"] == 1
    assert "Fallback linked construct" in report["markdown"]


def test_project_link_copy_avoids_unsafe_claims():
    combined = "\n".join(
        [
            repo.EXPRESSION_CONSTRUCT_PROJECT_LINKS_TABLE_SQL,
            presenter.NO_PROJECT_LINK_LABEL,
            presenter.NO_PROJECT_LINK_NOTE_LABEL,
            presenter.build_expression_construct_presenter("")["empty_states"]["project_links"],
        ]
    ).lower()
    forbidden = [
        "best promoter",
        "scoring",
        "ranking",
        "optimized",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
