# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_presenter as presenter
from services import expression_construct_repository as repo


def test_presenter_reflects_created_draft_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_construct_editable.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))

    profile = repo.create_construct_profile(construct_label="Editable draft")
    cassette = repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette A")
    repo.add_construct_cassette_part(cassette["cassette_id"], part_label="Part A")
    repo.add_construct_gene_link(profile["construct_id"], gene_label="crtI")
    repo.add_construct_pathway_step_link(profile["construct_id"], pathway_step_id="step-1", pathway_step_label="Step A")

    view_model = presenter.build_expression_construct_presenter(profile["construct_id"])

    assert view_model["construct_profile_rows"][0]["construct_label"] == "Editable draft"
    assert view_model["cassette_rows"][0]["cassette_label"] == "Cassette A"
    assert view_model["cassette_part_rows"][0]["part_label"] == "Part A"
    assert view_model["linked_gene_rows"][0]["gene_label"] == "crtI"
    assert view_model["linked_pathway_step_rows"][0]["pathway_step_label"] == "Step A"


def test_empty_states_remain_safe_when_database_is_empty(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_construct_empty.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))

    view_model = presenter.build_expression_construct_presenter("")

    assert view_model["summary_counts"]["construct_profile_count"] == 0
    assert view_model["summary_counts"]["project_link_count"] == 0
    assert "construct draft" in view_model["empty_states"]["constructs"].lower()
