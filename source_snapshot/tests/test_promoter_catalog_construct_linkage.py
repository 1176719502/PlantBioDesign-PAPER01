# -*- coding: utf-8 -*-
"""V2.6-R20 promoter catalog to construct cassette linkage tests."""
from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_presenter as construct_presenter
from services import expression_construct_repository as construct_repo
from services import parts_registry_repository as parts_repo
from views import ExpressionConstructs as construct_view


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "promoter_catalog_construct_linkage.db"
    monkeypatch.setattr(construct_repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(parts_repo, "DB_PATH", str(db_path))
    return db_path


def _seed_promoter_catalog_record(db_path) -> None:
    parts_repo.init_parts_registry_tables()
    conn = sqlite3.connect(str(db_path))
    try:
        timestamp = "2026-06-16T09:00:00"
        conn.execute(
            """
            INSERT INTO parts
                (local_id, part_type, display_name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "plant-promoter-001",
                "Promoter",
                "Maize promoter source record",
                "Documentation-only plant promoter catalog record.",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO plant_promoter_profiles
                (part_id, plant_clade, species_scientific_name, species_common_name,
                 taxonomy_id, cultivar_or_ecotype, native_gene_or_locus,
                 promoter_type, sequence_availability, sequence_scope_note,
                 tss_reference_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "plant-promoter-001",
                "monocot",
                "Zea mays",
                "maize",
                "4577",
                "",
                "Fixture locus",
                "source-recorded promoter context",
                "sequence metadata recorded",
                "Sequence scope kept as documentation context.",
                "TSS note for source review.",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO plant_promoter_tissue_evidence
                (part_id, tissue_context, plant_ontology_id, development_stage,
                 expression_context_label, evidence_type, evidence_summary,
                 source_database, source_accession, publication_reference,
                 curation_status, review_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "plant-promoter-001",
                "root",
                "PO:0009005",
                "seedling",
                "root evidence context",
                "literature-reported",
                "Evidence summary retained for documentation review.",
                "Fixture source",
                "FIXTURE-001",
                "Fixture publication",
                "source review needed",
                "Review note for documentation context.",
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_promoter_catalog_record_can_be_linked_to_cassette_part_row(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    _seed_promoter_catalog_record(db_path)

    options = construct_view._promoter_source_options()
    assert options == [
        {
            "record_id": "plant-promoter-001",
            "record_label": "Maize promoter source record",
            "select_label": "Maize promoter source record / plant-promoter-001",
            "context_note": (
                "monocot | Zea mays (maize) | root | literature-reported | "
                "Fixture source | source review needed | Review note for documentation context."
            ),
        }
    ]

    profile = construct_repo.create_construct_profile(construct_label="Linked promoter construct")
    cassette = construct_repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette A")
    part = construct_repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Manual promoter label",
        source_catalog=construct_presenter.PLANT_PROMOTER_CATALOG_LABEL,
        source_record_id=options[0]["record_id"],
        source_record_label=options[0]["record_label"],
        evidence_context_note=options[0]["context_note"],
        source_reference="Manual source note",
        provenance_note="Linked for documentation review.",
    )

    readback = construct_repo.list_construct_cassette_parts(cassette["cassette_id"])[0]
    view_model = construct_presenter.build_expression_construct_presenter(profile["construct_id"])

    assert part["part_label"] == "Manual promoter label"
    assert readback["source_record_id"] == "plant-promoter-001"
    assert view_model["cassette_part_rows"][0]["source_record_label"] == "Maize promoter source record"
    assert "Fixture source" in view_model["cassette_part_rows"][0]["evidence_context_note"]
    assert "promoter source context" not in [
        row["Gap type"] for row in view_model["review_gap_rows"]
    ]


def test_missing_promoter_catalog_reference_is_safe(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    profile = construct_repo.create_construct_profile(construct_label="Manual promoter construct")
    cassette = construct_repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette A")
    construct_repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Manual promoter label",
        source_reference="Manual source note",
        provenance_note="Manual review note.",
    )

    view_model = construct_presenter.build_expression_construct_presenter(profile["construct_id"])

    assert view_model["cassette_part_rows"][0]["source_record_label"] == construct_presenter.NO_SOURCE_RECORD_LABEL
    assert "promoter source context" in [
        row["Gap type"] for row in view_model["review_gap_rows"]
    ]
