# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_promoter_catalog_seed_loader as loader
from tests.helpers.sqlite_test_utils import external_test_scratch_dir


ROOT = Path(__file__).resolve().parents[1]
SCRATCH_DIR = external_test_scratch_dir(".pytest_tmp_r89_plant_promoter_seed_loader_files")


def _write_seed(filename: str, payload: dict) -> Path:
    path = SCRATCH_DIR / filename
    if path.exists():
        path.unlink()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_seed_file_loads_deterministically() -> None:
    path = _write_seed(
        "valid_seed.json",
        {
            "seed_name": "Fixture seed",
            "seed_version": "1",
            "seed_scope": "doc context",
            "documentation_boundary_note": "Boundary note.",
            "records": [
                {
                    "promoter_id": "seed-001",
                    "promoter_name": "Seed promoter A",
                    "aliases": ["A1"],
                    "species": {"scientific_name": "Zea mays", "common_name": "maize"},
                    "clade": "monocot",
                    "tissue_contexts": [
                        {
                            "tissue_context": "root",
                            "evidence_label": "note",
                            "source_label": "Source A",
                            "review_status": "source review needed",
                        }
                    ],
                    "evidence_labels": ["note"],
                    "motif_annotations": [{"motif_name": "Motif A", "motif_source": "Source A"}],
                    "source_labels": ["Source A"],
                    "review_status": "source review needed",
                    "documentation_status": "local curated sample context",
                    "limitation_notes": ["Use as documentation context only."],
                }
            ],
        },
    )

    catalog = loader.load_seed_catalog(path)

    assert catalog["metadata"]["seed_name"] == "Fixture seed"
    assert catalog["profiles"][0]["part_id"] == "seed-001"
    profile_names = [row["display_name"] for row in loader.list_seed_profiles(path)]
    assert profile_names == ["Seed promoter A"]
    assert loader.get_seed_profile_by_part_id("seed-001", path)["display_name"] == "Seed promoter A"
    assert loader.list_seed_tissue_evidence("seed-001", path)[0]["tissue_context"] == "root"
    assert loader.list_seed_motif_annotations("seed-001", path)[0]["motif_name"] == "Motif A"


def test_missing_optional_fields_handled_safely() -> None:
    path = _write_seed(
        "missing_optional_seed.json",
        {
            "records": [
                {
                    "promoter_id": "seed-002",
                    "promoter_name": "Seed promoter B",
                    "species": {"scientific_name": "Arabidopsis thaliana"},
                    "clade": "dicot",
                    "tissue_contexts": [],
                    "evidence_labels": [],
                    "motif_annotations": [],
                    "source_labels": [],
                    "review_status": "source review needed",
                    "documentation_status": "local curated sample context",
                    "limitation_notes": [],
                }
            ]
        },
    )

    catalog = loader.load_seed_catalog(path)

    assert catalog["profiles"][0]["species_scientific_name"] == "Arabidopsis thaliana"
    assert catalog["tissue_evidence_by_part_id"]["seed-002"] == []
    assert catalog["motif_annotations_by_part_id"]["seed-002"] == []


def test_missing_required_fields_are_rejected() -> None:
    path = _write_seed(
        "missing_required_seed.json",
        {"records": [{"promoter_name": "Broken seed", "species": {}, "clade": "monocot"}]},
    )

    try:
        loader.load_seed_catalog(path)
    except loader.PlantPromoterCatalogSeedError as exc:
        assert "missing required field" in str(exc)
    else:
        raise AssertionError("Expected seed loader error")


def test_duplicate_promoter_ids_are_rejected() -> None:
    path = _write_seed(
        "duplicate_ids_seed.json",
        {
            "records": [
                {
                    "promoter_id": "dup-1",
                    "promoter_name": "Seed A",
                    "species": {"scientific_name": "Zea mays"},
                    "clade": "monocot",
                    "tissue_contexts": [],
                    "evidence_labels": [],
                    "motif_annotations": [],
                    "source_labels": [],
                    "review_status": "source review needed",
                    "documentation_status": "local curated sample context",
                    "limitation_notes": [],
                },
                {
                    "promoter_id": "dup-1",
                    "promoter_name": "Seed B",
                    "species": {"scientific_name": "Zea mays"},
                    "clade": "monocot",
                    "tissue_contexts": [],
                    "evidence_labels": [],
                    "motif_annotations": [],
                    "source_labels": [],
                    "review_status": "source review needed",
                    "documentation_status": "local curated sample context",
                    "limitation_notes": [],
                },
            ]
        },
    )

    try:
        loader.load_seed_catalog(path)
    except loader.PlantPromoterCatalogSeedError as exc:
        assert "duplicate promoter_id" in str(exc)
    else:
        raise AssertionError("Expected duplicate promoter id error")


def test_unknown_fields_do_not_crash_loader() -> None:
    path = _write_seed(
        "unknown_fields_seed.json",
        {
            "records": [
                {
                    "promoter_id": "seed-003",
                    "promoter_name": "Seed promoter C",
                    "species": {"scientific_name": "Oryza sativa", "extra": "ignore"},
                    "clade": "monocot",
                    "tissue_contexts": [],
                    "evidence_labels": [],
                    "motif_annotations": [],
                    "source_labels": [],
                    "review_status": "source review needed",
                    "documentation_status": "local curated sample context",
                    "limitation_notes": [],
                    "unknown_field": "ignore",
                }
            ]
        },
    )

    catalog = loader.load_seed_catalog(path)

    assert catalog["profiles"][0]["part_id"] == "seed-003"


def test_r58_nicotiana_demo_promoter_records_load_from_bundled_seed() -> None:
    catalog = loader.load_seed_catalog()
    part_ids = {row["part_id"] for row in catalog["profiles"]}

    expected = {
        "plant-promoter-seed-004",
        "plant-promoter-seed-005",
        "plant-promoter-seed-006",
        "plant-promoter-seed-007",
        "plant-promoter-seed-008",
    }
    assert expected.issubset(part_ids)

    rbcs = loader.get_seed_profile_by_part_id("plant-promoter-seed-006")
    assert rbcs["display_name"] == "RBCS promoter context"
    assert rbcs["species_scientific_name"] == "Nicotiana benthamiana"
    assert "documentation-level" in rbcs["description"].lower()

    tissue_rows = loader.list_seed_tissue_evidence("plant-promoter-seed-006")
    assert len(tissue_rows) == 1
    assert tissue_rows[0]["tissue_context"] == "green tissue"
    assert "promoter_not_recommended" in tissue_rows[0]["review_note"]
