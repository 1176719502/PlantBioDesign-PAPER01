# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_repository as repo
from services import plant_promoter_catalog_workspace_presenter as presenter
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


NOW = "2026-06-17T09:00:00"


def _use_temp_db(monkeypatch) -> Path:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r89_plant_promoter_workspace_dbs",
        "plant_promoter_workspace.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _insert_part(conn: sqlite3.Connection, part_id: str, display_name: str) -> None:
    conn.execute(
        """
        INSERT INTO parts
            (local_id, part_type, display_name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            part_id,
            "Promoter",
            display_name,
            "Documentation-only plant promoter profile record.",
            NOW,
            NOW,
        ),
    )


def _insert_profile(conn: sqlite3.Connection, part_id: str, display_name: str) -> None:
    _insert_part(conn, part_id, display_name)
    conn.execute(
        """
        INSERT INTO plant_promoter_profiles
            (
                part_id, plant_clade, species_scientific_name, species_common_name,
                taxonomy_id, cultivar_or_ecotype, native_gene_or_locus,
                promoter_type, sequence_availability, sequence_scope_note,
                tss_reference_note, created_at, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            part_id,
            "monocot",
            "Zea mays",
            "maize",
            "4577",
            "B73 context",
            "Zm fixture locus",
            "source-recorded promoter context",
            "metadata-only sequence context",
            "Sequence scope is recorded for documentation review.",
            "TSS note is source context.",
            NOW,
            NOW,
        ),
    )


def _insert_evidence(conn: sqlite3.Connection, part_id: str, tissue: str, accession: str) -> None:
    conn.execute(
        """
        INSERT INTO plant_promoter_tissue_evidence
            (
                part_id, tissue_context, plant_ontology_id, development_stage,
                expression_context_label, evidence_type, evidence_summary,
                source_database, source_accession, publication_reference,
                curation_status, review_note, created_at, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            part_id,
            tissue,
            "PO:fixture",
            "source-recorded stage",
            f"{tissue} context",
            "literature-reported",
            f"{tissue} evidence captured as documentation context.",
            "Fixture source",
            accession,
            "Fixture publication reference",
            "source review needed",
            "Review source metadata before citation.",
            NOW,
            NOW,
        ),
    )


def _insert_motif(conn: sqlite3.Connection, part_id: str) -> None:
    conn.execute(
        """
        INSERT INTO plant_promoter_motif_annotations
            (
                part_id, motif_name, motif_source, motif_accession,
                motif_sequence_or_consensus, motif_position_note,
                associated_function_note, evidence_note, created_at, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            part_id,
            "Fixture motif",
            "Fixture motif source",
            "MOTIF-001",
            "NNNN",
            "Source-recorded position context.",
            "Function note is documentation context.",
            "Motif evidence note for source review.",
            NOW,
            NOW,
        ),
    )


def _seed(monkeypatch) -> None:
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    conn = sqlite3.connect(str(db_path))
    try:
        _insert_profile(conn, "plant-promoter-101", "Maize promoter profile")
        _insert_evidence(conn, "plant-promoter-101", "root", "ROOT-101")
        _insert_evidence(conn, "plant-promoter-101", "leaf", "LEAF-101")
        _insert_motif(conn, "plant-promoter-101")
        conn.commit()
    finally:
        conn.close()


def test_empty_catalog_state_returns_defensive_messages(monkeypatch) -> None:
    _use_temp_db(monkeypatch)

    options = presenter.build_catalog_reference_options()
    detail = presenter.build_profile_detail_view_model("plant-promoter-seed-001")

    assert options
    assert detail["status"] == "available"
    assert detail["profile_summary"]["catalog_record_source"] == "local curated sample records"
    assert detail["evidence_rows"]
    assert detail["motif_annotation_rows"]


def test_filter_options_and_profile_detail_readback(monkeypatch) -> None:
    _seed(monkeypatch)

    options = presenter.build_catalog_reference_options(plant_clade="monocot", tissue_context="root")
    detail = presenter.build_profile_detail_view_model("plant-promoter-101")

    assert options == [
        {
            "part_id": "plant-promoter-101",
            "select_label": "Maize promoter profile / plant-promoter-101",
            "promoter_label": "Maize promoter profile",
            "plant_clade": "monocot",
            "species_label": "Zea mays (maize)",
            "tissue_context_count": 2,
            "evidence_row_count": 2,
            "motif_annotation_count": 1,
            "missing_metadata_count": 0,
        }
    ]
    assert detail["profile_summary"]["alias"] == "Zm fixture locus"
    assert detail["profile_summary"]["species_label"] == "Zea mays (maize)"
    assert detail["missing_metadata_count"] == 0


def test_seed_backed_detail_view_is_available_when_db_empty(monkeypatch) -> None:
    _use_temp_db(monkeypatch)

    detail = presenter.build_profile_detail_view_model("plant-promoter-seed-002")

    assert detail["status"] == "available"
    assert detail["profile_summary"]["promoter_label"] == "Arabidopsis ACT2 promoter source context"
    assert detail["profile_summary"]["catalog_record_source"] == "local curated sample records"


def test_tissue_evidence_motif_and_source_review_rows(monkeypatch) -> None:
    _seed(monkeypatch)

    detail = presenter.build_profile_detail_view_model("plant-promoter-101")

    evidence_rows = detail["evidence_rows"]
    motif_rows = detail["motif_annotation_rows"]
    source_rows = detail["source_review_metadata_rows"]

    assert [row["tissue_context"] for row in evidence_rows] == ["leaf", "root"]
    assert evidence_rows[0]["source_label"] == "Fixture source: LEAF-101"
    assert motif_rows[0]["motif_name"] == "Fixture motif"
    assert motif_rows[0]["motif_source"] == "Fixture motif source"
    assert {"metadata_group": "Source labels", "metadata_value": "Fixture source: LEAF-101; Fixture source: ROOT-101"} in source_rows
    assert {"metadata_group": "Missing metadata count", "metadata_value": "0"} in source_rows


def test_project_link_and_compact_summary_are_documentation_level(monkeypatch) -> None:
    _seed(monkeypatch)

    link = presenter.build_promoter_catalog_project_link(
        project_id=7,
        part_id="plant-promoter-101",
        linkage_role="source_review_context",
    )
    summary = presenter.summarize_linked_plant_promoter_references([link])

    assert link["asset_type"] == presenter.PLANT_PROMOTER_PROFILE_ASSET_TYPE
    assert link["source_context_snapshot"]["catalog"] == "Plant Promoter Catalog"
    assert "Component Library promoter asset" in presenter.DEFAULT_REFERENCE_NOTE
    assert "Component Library promoter asset" in presenter.CATALOG_REFERENCE_BOUNDARY_NOTE
    assert "Component Library promoter assets" in presenter.CATALOG_REFERENCE_LIMITATION_NOTE
    assert link["source_context_snapshot"]["species"] == "Zea mays (maize)"
    assert summary["linked_promoter_count"] == 1
    assert summary["missing_metadata_count"] == 0
    assert summary["references"][0]["asset_display_name"] == "Maize promoter profile"


def test_workspace_presenter_forbidden_claim_terms_absent(monkeypatch) -> None:
    _seed(monkeypatch)
    link = presenter.build_promoter_catalog_project_link(project_id=7, part_id="plant-promoter-101")
    text = str(
        {
            "detail": presenter.build_profile_detail_view_model("plant-promoter-101"),
            "options": presenter.build_catalog_reference_options(),
            "summary": presenter.summarize_linked_plant_promoter_references([link]),
        }
    ).lower()
    forbidden = [
        "recommend" + "ed",
        "best",
        "optimal",
        "valid" + "ated",
        "approv" + "ed",
        "safe for " + "use",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "experimentally " + "confirmed",
        "host " + "compatible",
        "predic" + "tion",
        "optimiza" + "tion",
        "rank" + "ing",
        "scor" + "ing",
    ]

    assert [phrase for phrase in forbidden if phrase in text] == []
