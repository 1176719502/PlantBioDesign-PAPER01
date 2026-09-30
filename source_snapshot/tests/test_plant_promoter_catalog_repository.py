# -*- coding: utf-8 -*-
"""V2.6-R14 read-only plant promoter catalog foundation tests."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_repository as repo
from services import plant_promoter_catalog_presenter as presenter
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


NOW = "2026-06-16T10:00:00"


def _plant_promoter_catalog_db_path(filename: str) -> Path:
    return repo_local_sqlite_db_path(".pytest_tmp_r81_plant_promoter_catalog_dbs", filename)


def _use_temp_db(monkeypatch) -> Path:
    db_path = _plant_promoter_catalog_db_path("plant_promoter_catalog.db")
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
            "Documentation-only plant promoter catalog record for source review.",
            NOW,
            NOW,
        ),
    )


def _insert_profile(
    conn: sqlite3.Connection,
    *,
    part_id: str,
    plant_clade: str,
    scientific_name: str,
    common_name: str,
    promoter_type: str = "source-recorded promoter context",
) -> None:
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
            plant_clade,
            scientific_name,
            common_name,
            "",
            "source-recorded context",
            "source-recorded locus",
            promoter_type,
            "metadata-only sequence context",
            "Sequence scope is a curated note for documentation review.",
            "TSS reference is recorded as source context.",
            NOW,
            NOW,
        ),
    )


def _insert_tissue_evidence(
    conn: sqlite3.Connection,
    *,
    part_id: str,
    tissue_context: str,
    source_accession: str,
    evidence_type: str = "literature-reported",
    source_database: str = "Fixture source",
    curation_status: str = "source review needed",
) -> None:
    review_note = (
        "Source context reviewed for documentation."
        if curation_status == "metadata reviewed"
        else "Needs review before use in project documentation."
    )
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
            tissue_context,
            "PO:test-context",
            "source-recorded stage",
            f"{tissue_context} evidence context",
            evidence_type,
            f"{tissue_context} tissue-context evidence captured for documentation review.",
            source_database,
            source_accession,
            "Fixture publication reference",
            curation_status,
            review_note,
            NOW,
            NOW,
        ),
    )


def _insert_motif(conn: sqlite3.Connection, *, part_id: str, motif_name: str) -> None:
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
            motif_name,
            "Fixture motif source",
            "MOTIF-FIXTURE",
            "NNNN",
            "Position is source-recorded context only.",
            "Function note is documentation context only.",
            "Motif evidence note needs source review.",
            NOW,
            NOW,
        ),
    )


def _seed_profiles(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn, "plant-promoter-001", "Maize promoter source record")
        _insert_profile(
            conn,
            part_id="plant-promoter-001",
            plant_clade="monocot",
            scientific_name="Zea mays",
            common_name="maize",
        )
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-001",
            tissue_context="root",
            source_accession="ROOT-001",
            curation_status="source review needed",
        )
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-001",
            tissue_context="stem",
            source_accession="STEM-001",
            curation_status="metadata reviewed",
        )
        _insert_motif(conn, part_id="plant-promoter-001", motif_name="Fixture motif A")

        _insert_part(conn, "plant-promoter-002", "Arabidopsis promoter source record")
        _insert_profile(
            conn,
            part_id="plant-promoter-002",
            plant_clade="dicot",
            scientific_name="Arabidopsis thaliana",
            common_name="thale cress",
        )
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-002",
            tissue_context="leaf",
            source_accession="LEAF-001",
            curation_status="source review needed",
        )
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-002",
            tissue_context="callus",
            source_accession="CALLUS-001",
            curation_status="follow-up documentation needed",
        )
        conn.commit()
    finally:
        conn.close()


def test_schema_creation_adds_plant_promoter_tables(monkeypatch):
    db_path = _use_temp_db(monkeypatch)

    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "plant_promoter_profiles",
        "plant_promoter_tissue_evidence",
        "plant_promoter_motif_annotations",
    }.issubset(tables)


def test_startup_creates_plant_promoter_tables(monkeypatch):
    from core import database as db
    from core import seed_database as sd
    from core import unified_database as ud

    db_path = _plant_promoter_catalog_db_path("startup_plant_promoter_catalog.db")
    monkeypatch.setattr(ud, "DB_PATH", str(db_path))
    monkeypatch.setattr(sd, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))

    ud.initialize_database_on_startup()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "plant_promoter_profiles" in tables
    assert "plant_promoter_tissue_evidence" in tables
    assert "plant_promoter_motif_annotations" in tables


def test_empty_read_paths_return_defensive_defaults(monkeypatch):
    _use_temp_db(monkeypatch)

    view_model = presenter.build_plant_promoter_catalog_view_model()
    assert view_model["summary_counts"]["profile_count"] > 0
    assert view_model["catalog_source"] == "local curated sample records"
    assert view_model["seed_metadata"]["seed_name"] == "V2.6 R34 Plant Promoter Catalog curated sample records"
    assert view_model["profile_rows"]


def test_listing_and_profile_readback(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    profiles = repo.list_plant_promoter_profiles()
    profile = repo.get_plant_promoter_profile_by_part_id("plant-promoter-001")

    assert [row["part_id"] for row in profiles] == [
        "plant-promoter-002",
        "plant-promoter-001",
    ]
    assert profile["display_name"] == "Maize promoter source record"
    assert profile["plant_clade"] == "monocot"
    assert profile["species_scientific_name"] == "Zea mays"


def test_clade_species_and_tissue_filters(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    monocot = repo.list_plant_promoter_profiles_by_clade("monocot")
    dicot = repo.list_plant_promoter_profiles_by_clade("DICOT")
    species = repo.list_plant_promoter_profiles_by_species("arabidopsis")

    assert [row["part_id"] for row in monocot] == ["plant-promoter-001"]
    assert [row["part_id"] for row in dicot] == ["plant-promoter-002"]
    assert [row["part_id"] for row in species] == ["plant-promoter-002"]

    for tissue in ("root", "stem", "leaf", "callus"):
        rows = repo.list_plant_promoter_profiles_by_tissue_context(tissue)
        assert len(rows) == 1
        assert repo.list_plant_promoter_tissue_evidence(
            rows[0]["part_id"],
            tissue_context=tissue,
        )[0]["tissue_context"] == tissue


def test_unknown_tissue_context_returns_empty_rows(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    assert repo.list_plant_promoter_profiles_by_tissue_context("seedling") == []
    assert repo.list_plant_promoter_tissue_evidence(
        "plant-promoter-001",
        tissue_context="seedling",
    ) == []


def test_motif_annotation_readback(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    motifs = repo.list_plant_promoter_motif_annotations("plant-promoter-001")

    assert len(motifs) == 1
    assert motifs[0]["motif_name"] == "Fixture motif A"
    assert motifs[0]["motif_sequence_or_consensus"] == "NNNN"
    assert "source review" in motifs[0]["evidence_note"]


def test_presenter_summary_behavior(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    view_model = presenter.build_plant_promoter_catalog_view_model()

    assert view_model["summary_counts"] == {
        "profile_count": 2,
        "tissue_evidence_count": 4,
        "motif_annotation_count": 1,
        "rows_needing_review_count": 3,
        "source_database_count": 1,
        "linked_catalog_reference_count": 1,
    }
    assert view_model["available_plant_clades"] == ["dicot", "monocot"]
    assert "Arabidopsis thaliana (thale cress)" in view_model["available_species"]
    assert view_model["tissue_context_evidence_summary"] == {
        "callus": 1,
        "leaf": 1,
        "root": 1,
        "stem": 1,
    }
    assert view_model["source_evidence_labels"] == [
        "Fixture source: CALLUS-001",
        "Fixture source: LEAF-001",
        "Fixture source: ROOT-001",
        "Fixture source: STEM-001",
    ]
    assert len(view_model["evidence_rows"]) == 4
    assert len(view_model["context_readback_rows"]) == 4
    assert len(view_model["motif_preview_rows"]) == 1
    assert view_model["boundary_note"] == "Read-only catalog context for documentation and source review."
    assert "Documentation-only context readback" in view_model["documentation_only_context_note"]
    assert view_model["catalog_status_label"] == "persistent records"
    assert view_model["documentation_status_label"] == "documentation-only reference records"
    first_readback = view_model["context_readback_rows"][0]
    assert "source context:" in first_readback["source_review_metadata"]
    assert "review metadata:" in first_readback["source_review_metadata"]
    assert "manual review note:" in first_readback["source_review_metadata"]
    assert first_readback["documentation_boundary"] == presenter.READBACK_BOUNDARY_NOTE


def test_presenter_uses_seed_fallback_when_catalog_empty(monkeypatch):
    _use_temp_db(monkeypatch)

    view_model = presenter.build_plant_promoter_catalog_view_model()

    assert view_model["catalog_source"] == "local curated sample records"
    assert view_model["summary_counts"]["profile_count"] == len(view_model["profile_rows"])
    assert view_model["profile_rows"][0]["catalog_record_source"] == "local curated sample records"
    assert view_model["seed_metadata"]["seed_version"] == "v2.6-r58"
    assert view_model["persistent_profile_count"] == 0
    assert view_model["seed_profile_count"] == len(view_model["profile_rows"])
    assert view_model["linked_catalog_reference_labels"]


def test_presenter_supports_evidence_type_and_curation_filters(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    _seed_profiles(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-002",
            tissue_context="flower",
            source_accession="FLOWER-001",
            evidence_type="atlas-curated",
            curation_status="metadata reviewed",
        )
        conn.commit()
    finally:
        conn.close()

    view_model = presenter.build_plant_promoter_catalog_view_model(
        plant_clade="dicot",
        evidence_type="atlas-curated",
        curation_status="metadata reviewed",
    )

    assert view_model["summary_counts"] == {
        "profile_count": 1,
        "tissue_evidence_count": 1,
        "motif_annotation_count": 0,
        "rows_needing_review_count": 0,
        "source_database_count": 1,
        "linked_catalog_reference_count": 1,
    }
    assert view_model["evidence_rows"] == [
        {
            "part_id": "plant-promoter-002",
            "display_name": "Arabidopsis promoter source record",
            "promoter_label": "Arabidopsis promoter source record",
            "plant_clade": "dicot",
            "species_label": "Arabidopsis thaliana (thale cress)",
            "tissue_context": "flower",
            "evidence_type": "atlas-curated",
            "source_database": "Fixture source",
            "curation_status": "metadata reviewed",
            "review_note": "Source context reviewed for documentation.",
        }
    ]


def test_presenter_uses_fallback_labels_for_missing_tissue_and_source(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn, "plant-promoter-003", "Unknown context promoter")
        _insert_profile(
            conn,
            part_id="plant-promoter-003",
            plant_clade="other / not specified",
            scientific_name="",
            common_name="",
        )
        _insert_tissue_evidence(
            conn,
            part_id="plant-promoter-003",
            tissue_context="",
            source_accession="",
            evidence_type="",
            source_database="",
            curation_status="",
        )
        conn.commit()
    finally:
        conn.close()

    view_model = presenter.build_plant_promoter_catalog_view_model()

    assert view_model["evidence_rows"] == [
        {
            "part_id": "plant-promoter-003",
            "display_name": "Unknown context promoter",
            "promoter_label": "Unknown context promoter",
            "plant_clade": "other / not specified",
            "species_label": presenter.NO_SPECIES_LABEL,
            "tissue_context": presenter.NO_TISSUE_LABEL,
            "evidence_type": presenter.NO_EVIDENCE_TYPE_LABEL,
            "source_database": presenter.NO_SOURCE_LABEL,
            "curation_status": presenter.NO_CURATION_STATUS_LABEL,
            "review_note": "Needs review before use in project documentation.",
        }
    ]
    assert view_model["context_readback_rows"] == [
        {
            "part_id": "plant-promoter-003",
            "promoter_label": "Unknown context promoter",
            "catalog_context": "Unknown context promoter",
            "species_or_clade_context": "other / not specified",
            "tissue_evidence_context": f"{presenter.NO_TISSUE_LABEL}; {presenter.NO_EVIDENCE_TYPE_LABEL}",
            "source_review_metadata": (
                f"source context: {presenter.NO_SOURCE_LABEL}; "
                f"review metadata: {presenter.NO_CURATION_STATUS_LABEL}; "
                f"manual review note: Needs review before use in project documentation."
            ),
            "metadata_gap": "species context metadata gap; tissue evidence context metadata gap; source context metadata gap; review metadata gap",
            "documentation_boundary": presenter.READBACK_BOUNDARY_NOTE,
        }
    ]


def test_presenter_marks_missing_review_note_as_metadata_gap(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn, "plant-promoter-004", "Sparse review note promoter")
        _insert_profile(
            conn,
            part_id="plant-promoter-004",
            plant_clade="monocot",
            scientific_name="Oryza sativa",
            common_name="rice",
        )
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
                "plant-promoter-004",
                "leaf",
                "",
                "",
                "",
                "literature-reported",
                "",
                "Fixture source",
                "LEAF-004",
                "",
                "metadata reviewed",
                "",
                NOW,
                NOW,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    view_model = presenter.build_plant_promoter_catalog_view_model()
    readback = view_model["context_readback_rows"][0]

    assert "manual review note metadata gap" in readback["metadata_gap"]
    assert "manual review note: No manual review note recorded" in readback["source_review_metadata"]
    assert "recommended promoter" not in readback["documentation_boundary"].lower()
    assert "optimized promoter" not in readback["documentation_boundary"].lower()
    assert "validated promoter" not in readback["documentation_boundary"].lower()


def test_new_copy_avoids_risky_product_claims():
    combined = "\n".join(
        [
            presenter.NO_CLADE_LABEL,
            presenter.NO_SPECIES_LABEL,
            presenter.NO_TISSUE_LABEL,
            presenter.NO_SOURCE_LABEL,
            presenter.build_plant_promoter_catalog_view_model()["boundary_note"],
        ]
    ).lower()
    forbidden = [
        "recommend" + "ed",
        "best " + "promoter",
        "valid" + "ated",
        "optim" + "ized",
        "scor" + "ing",
        "rank" + "ing",
        "host " + "compatibility",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "transformation " + "protocol",
        "experimentally " + "confirmed",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
