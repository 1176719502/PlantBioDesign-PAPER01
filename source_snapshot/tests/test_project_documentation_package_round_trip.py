# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_presenter as presenter
from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_documentation_package_exporter import (
    PACKAGE_SCHEMA_VERSION,
    build_project_documentation_export_package,
)
from services.project_documentation_package_importer import (
    build_import_dry_run,
    import_package_create_as_new,
    validate_project_documentation_package,
)
from services.project_review_report_service import build_project_review_report
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _use_temp_db(monkeypatch, name: str) -> None:
    db_path = repo_local_sqlite_db_path(".pytest_tmp_r82_project_documentation_package_dbs", name)
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))


def _seed_round_trip_source_records() -> dict[str, str]:
    profile = repo.create_construct_profile(
        construct_id="construct-r27-source",
        construct_label="R27 portable construct",
        construct_type="documentation-only construct draft",
        plasmid_backbone="pR27-Doc",
        host_context_note="Host context retained for documentation-only review.",
        source_reference="Construct source notebook",
        provenance_note="Construct provenance note.",
        review_status="documentation review pending",
        documentation_scope_note="Round-trip QA construct scope note.",
    )
    cassette_a = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-r27-a",
        cassette_label="Cassette Alpha",
        cassette_role="expression cassette record",
        cassette_order=1,
        promoter_label="Promoter Alpha",
        gene_label="crtB",
        terminator_label="Terminator Alpha",
        source_reference="Cassette A notebook",
        provenance_note="Cassette A provenance note.",
    )
    cassette_b = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-r27-b",
        cassette_label="Cassette Beta",
        cassette_role="support cassette record",
        cassette_order=2,
        promoter_label="Promoter Beta",
        gene_label="crtI",
        terminator_label="Terminator Beta",
        source_reference="Cassette B notebook",
        provenance_note="Cassette B provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette_a["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Promoter Alpha row",
        part_reference="promoter-alpha-ref",
        source_reference="Promoter Alpha notebook",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-r27-alpha",
        source_record_label="Promoter Alpha source record",
        evidence_context_note="Alpha promoter evidence context retained for review.",
        provenance_note="Promoter Alpha provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette_a["cassette_id"],
        part_order=2,
        part_role="cds",
        part_label="crtB CDS row",
        part_reference="crtB-ref",
        source_reference="crtB source notebook",
        provenance_note="crtB provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette_b["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Promoter Beta row",
        part_reference="promoter-beta-ref",
        source_reference="Promoter Beta notebook",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-r27-beta",
        source_record_label="Promoter Beta source record",
        evidence_context_note="Beta promoter evidence context retained for review.",
        provenance_note="Promoter Beta provenance note.",
    )
    repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="crtB",
        gene_reference="crtB-gene-reference",
        source_reference="Gene linkage notebook",
        provenance_note="Gene linkage provenance note.",
    )
    repo.add_construct_pathway_step_link(
        profile["construct_id"],
        pathway_step_id="step-r27-1",
        pathway_step_label="Pathway step Alpha",
        source_reference="Pathway step notebook",
        provenance_note="Pathway step provenance note.",
    )
    project_link = repo.create_construct_project_link(
        project_id="project-r27",
        construct_id=profile["construct_id"],
        link_label="Primary project construct link",
        link_note="Primary project linkage note.",
        source_context="Pathway Workspace round-trip QA context",
        curation_status="documentation review pending",
        review_note="Primary review note retained for round-trip QA.",
    )
    repo.update_construct_project_link(
        project_link["id"],
        review_note="Updated review note retained for round-trip QA.",
    )
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "project-r27",
            "asset_id": "plant-promoter-r27-reference",
            "asset_display_name": "R27 persisted promoter profile",
            "asset_type": "plant_promoter_profile",
            "asset_version": "catalog-v1",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-r27-reference",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "source_labels": "Fixture source: R27",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 2,
            },
            "human_review_required": True,
        }
    )
    return {
        "construct_id": profile["construct_id"],
        "project_id": "project-r27",
    }


def _row_map(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row.get(key)): row for row in rows}


def test_round_trip_preserves_core_counts_and_fields(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_source.db")
    seed = _seed_round_trip_source_records()
    exported = build_project_documentation_export_package(
        project={"id": seed["project_id"], "name": "R27 Round Trip Project"},
        project_id=seed["project_id"],
        report_reference={"source_area": "round-trip-test"},
    )

    validation = validate_project_documentation_package(exported)
    dry_run = build_import_dry_run(exported, target_project_id="project-r27-imported")

    assert validation["is_valid"] is True
    assert dry_run["is_valid"] is True
    assert dry_run["plan"]["would_create"] == {
        "construct_profiles": 1,
        "expression_cassettes": 2,
        "cassette_parts": 3,
        "promoter_source_link_rows": 2,
        "linked_genes": 1,
        "linked_pathway_steps": 1,
        "project_construct_links": 1,
        "project_catalog_asset_links": 1,
    }

    _use_temp_db(monkeypatch, "project_documentation_round_trip_imported.db")
    result = import_package_create_as_new(exported, target_project_id="project-r27-imported", confirm=True)
    assert result["created"] is True
    assert result["errors"] == []
    assert result["created_counts"] == {
        "construct_profiles": 1,
        "expression_cassettes": 2,
        "cassette_parts": 3,
        "linked_genes": 1,
        "linked_pathway_steps": 1,
        "project_construct_links": 1,
        "project_catalog_asset_links": 1,
        "project_catalog_asset_link_duplicates": 0,
        "project_catalog_asset_link_skipped": 0,
    }

    re_exported = build_project_documentation_export_package(
        project={"id": "project-r27-imported", "name": "Imported Round Trip Project"},
        project_id="project-r27-imported",
        report_reference={"source_area": "round-trip-test-re-export"},
    )

    assert re_exported["package_metadata"]["counts"] == {
        "construct_profile_count": 1,
        "cassette_count": 2,
        "cassette_part_count": 3,
        "promoter_source_link_row_count": 2,
        "linked_gene_count": 1,
        "linked_pathway_step_count": 1,
        "project_construct_link_count": 1,
        "project_catalog_asset_link_count": 1,
        "linked_plant_promoter_count": 1,
        "catalog_reference_missing_metadata_count": 2,
        "expression_wizard_catalog_reference_count": 0,
        "expression_wizard_plant_promoter_reference_count": 0,
        "expression_wizard_catalog_missing_metadata_count": 0,
        "catalog_links_with_pinned_snapshots_count": 0,
        "catalog_links_missing_snapshots_count": 1,
        "catalog_links_malformed_snapshot_warning_count": 0,
        "review_gap_count": 0,
    }
    assert exported["manifest"]["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert exported["integrity_summary"]["package_id"].startswith("bdspkg-")
    assert re_exported["manifest"]["record_counts"]["promoter_source_link_row_count"] == 2
    assert re_exported["project_catalog_asset_links"][0]["asset_id"] == "plant-promoter-r27-reference"
    assert re_exported["project_catalog_asset_links"][0]["compact_metadata"]["source_context_snapshot"]["species"] == "Zea mays (maize)"
    assert re_exported["project_catalog_asset_links"][0]["snapshot_state"] == "live metadata fallback"

    source_profiles = exported["construct_profiles"]
    imported_profiles = re_exported["construct_profiles"]
    assert len(source_profiles) == len(imported_profiles) == 1
    assert imported_profiles[0]["construct_label"] == source_profiles[0]["construct_label"]
    assert imported_profiles[0]["construct_type"] == source_profiles[0]["construct_type"]
    assert imported_profiles[0]["plasmid_backbone"] == source_profiles[0]["plasmid_backbone"]
    assert imported_profiles[0]["source_reference"] == source_profiles[0]["source_reference"]
    assert imported_profiles[0]["provenance_note"] == source_profiles[0]["provenance_note"]
    assert imported_profiles[0]["review_status"] == source_profiles[0]["review_status"]
    assert imported_profiles[0]["documentation_scope_note"] == source_profiles[0]["documentation_scope_note"]

    exported_cassettes = _row_map(exported["expression_cassettes"], "cassette_label")
    re_exported_cassettes = _row_map(re_exported["expression_cassettes"], "cassette_label")
    assert list(row["cassette_label"] for row in re_exported["expression_cassettes"]) == [
        "Cassette Alpha",
        "Cassette Beta",
    ]
    for cassette_label in ("Cassette Alpha", "Cassette Beta"):
        assert re_exported_cassettes[cassette_label]["cassette_order"] == exported_cassettes[cassette_label]["cassette_order"]
        assert re_exported_cassettes[cassette_label]["cassette_role"] == exported_cassettes[cassette_label]["cassette_role"]
        assert re_exported_cassettes[cassette_label]["source_reference"] == exported_cassettes[cassette_label]["source_reference"]
        assert re_exported_cassettes[cassette_label]["provenance_note"] == exported_cassettes[cassette_label]["provenance_note"]

    exported_parts = _row_map(exported["cassette_parts"], "part_label")
    re_exported_parts = _row_map(re_exported["cassette_parts"], "part_label")
    assert [row["part_label"] for row in re_exported["cassette_parts"]] == [
        "Promoter Alpha row",
        "crtB CDS row",
        "Promoter Beta row",
    ]
    for label in ("Promoter Alpha row", "crtB CDS row", "Promoter Beta row"):
        assert re_exported_parts[label]["part_order"] == exported_parts[label]["part_order"]
        assert re_exported_parts[label]["part_role"] == exported_parts[label]["part_role"]
        assert re_exported_parts[label]["source_reference"] == exported_parts[label]["source_reference"]
        assert re_exported_parts[label]["provenance_note"] == exported_parts[label]["provenance_note"]
    assert re_exported_parts["Promoter Alpha row"]["source_catalog"] == "Plant Promoter Catalog"
    assert re_exported_parts["Promoter Alpha row"]["source_record_id"] == "plant-promoter-r27-alpha"
    assert re_exported_parts["Promoter Alpha row"]["source_record_label"] == "Promoter Alpha source record"
    assert "evidence context retained" in re_exported_parts["Promoter Alpha row"]["evidence_context_note"]
    assert re_exported_parts["Promoter Beta row"]["source_record_id"] == "plant-promoter-r27-beta"

    assert re_exported["linked_genes"][0]["gene_label"] == exported["linked_genes"][0]["gene_label"]
    assert re_exported["linked_genes"][0]["gene_reference"] == exported["linked_genes"][0]["gene_reference"]
    assert re_exported["linked_pathway_steps"][0]["pathway_step_id"] == exported["linked_pathway_steps"][0]["pathway_step_id"]
    assert re_exported["linked_pathway_steps"][0]["pathway_step_label"] == exported["linked_pathway_steps"][0]["pathway_step_label"]
    assert re_exported["project_construct_links"][0]["link_label"] == exported["project_construct_links"][0]["link_label"]
    assert re_exported["project_construct_links"][0]["link_note"] == exported["project_construct_links"][0]["link_note"]
    assert re_exported["project_construct_links"][0]["source_context"] == exported["project_construct_links"][0]["source_context"]
    assert re_exported["project_construct_links"][0]["review_note"] == exported["project_construct_links"][0]["review_note"]


def test_round_trip_imported_records_remain_readable_to_presenter_and_report(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_readability_source.db")
    seed = _seed_round_trip_source_records()
    package = build_project_documentation_export_package(project_id=seed["project_id"])

    _use_temp_db(monkeypatch, "project_documentation_round_trip_readability_imported.db")
    result = import_package_create_as_new(package, target_project_id="project-r27-report", confirm=True)
    local_construct_id = result["construct_id_map"]["construct-r27-source"]

    view = presenter.build_expression_construct_presenter(local_construct_id, project_id="project-r27-report")
    report = build_project_review_report(
        {
            "id": "project-r27-report",
            "name": "R27 report readability",
            "pathway_steps": [{"id": "step-r27-1", "step_name": "Pathway step Alpha"}],
        }
    )

    assert view["summary_counts"] == {
        "construct_profile_count": 1,
        "cassette_count": 2,
        "cassette_part_count": 3,
        "gene_link_count": 1,
        "pathway_step_link_count": 1,
        "project_link_count": 1,
        "review_gap_count": 0,
    }
    assert [row["cassette_label"] for row in view["cassette_rows"]] == ["Cassette Alpha", "Cassette Beta"]
    assert [row["part_order"] for row in view["cassette_part_rows"]] == [1, 2, 1]
    assert view["cassette_part_rows"][0]["source_record_label"] == "Promoter Alpha source record"
    assert view["project_link_rows"][0]["review_note"] == "Updated review note retained for round-trip QA."

    construct_section = report["expression_construct_documentation"]
    assert construct_section["status"] == "AVAILABLE"
    assert construct_section["project_scoped_filtering"] == "project-level construct links"
    assert construct_section["summary_counts"]["construct_profile_count"] == 1
    assert construct_section["summary_counts"]["cassette_part_count"] == 3
    assert construct_section["summary_counts"]["project_link_count"] == 1
    assert "R27 portable construct" in report["markdown"]
    assert "Promoter Alpha source record" in report["markdown"]
    assert "Updated review note retained for round-trip QA." in report["markdown"]


def test_round_trip_handles_missing_optional_and_unknown_extra_fields_without_breaking_import(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_optional_source.db")
    seed = _seed_round_trip_source_records()
    package = build_project_documentation_export_package(project_id=seed["project_id"])
    package["project_metadata"].pop("project_name", None)
    package["construct_profiles"][0]["future_extra_construct_note"] = "ignored"
    package["cassette_parts"][0]["future_extra_part_note"] = "ignored"

    dry_run = build_import_dry_run(package, target_project_id="project-r27-optional")

    assert dry_run["is_valid"] is True
    assert "project_metadata.project_name" in dry_run["plan"]["missing_optional_fields"]
    assert "construct_profiles[0].future_extra_construct_note" in dry_run["plan"]["unknown_extra_fields"]
    assert "cassette_parts[0].future_extra_part_note" in dry_run["plan"]["unknown_extra_fields"]

    _use_temp_db(monkeypatch, "project_documentation_round_trip_optional_imported.db")
    result = import_package_create_as_new(package, target_project_id="project-r27-optional", confirm=True)
    re_exported = build_project_documentation_export_package(project_id="project-r27-optional")

    assert result["created"] is True
    assert re_exported["package_metadata"]["counts"]["construct_profile_count"] == 1
    assert re_exported["package_metadata"]["counts"]["promoter_source_link_row_count"] == 2
    assert re_exported["project_metadata"]["project_id"] == "project-r27-optional"


def test_round_trip_preserves_linked_catalog_reference_fields_when_legacy_package_rows_are_imported(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_catalog_legacy_source.db")
    seed = _seed_round_trip_source_records()
    package = build_project_documentation_export_package(project_id=seed["project_id"])
    row = package["project_catalog_asset_links"][0]
    row.pop("compact_metadata", None)
    row["asset_snapshot"] = {}

    _use_temp_db(monkeypatch, "project_documentation_round_trip_catalog_legacy_imported.db")
    result = import_package_create_as_new(package, target_project_id="project-r27-legacy", confirm=True)
    re_exported = build_project_documentation_export_package(project_id="project-r27-legacy")
    imported_row = re_exported["project_catalog_asset_links"][0]

    assert result["created"] is True
    assert imported_row["record_identifier"] == "plant-promoter-r27-reference"
    assert imported_row["catalog_label"] == "Plant Promoter Catalog"
    assert imported_row["catalog_name_source"] == "Plant Promoter Catalog / Fixture source: R27"
    assert imported_row["catalog_source_status"] == "Plant Promoter Catalog / Fixture source: R27 / source review needed"
    assert imported_row["reference_origin"] == "Project documentation reference"
    assert imported_row["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert imported_row["documentation_note"] == "Documentation-only Plant Promoter Catalog reference for project traceability."
    assert imported_row["linked_persisted_status"] == "Persisted linked catalog reference"
    assert imported_row["snapshot_state"] == "live metadata fallback"


def test_round_trip_legacy_missing_catalog_fields_re_export_with_safe_defaults(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_catalog_defaults_source.db")
    seed = _seed_round_trip_source_records()
    package = build_project_documentation_export_package(project_id=seed["project_id"])
    row = package["project_catalog_asset_links"][0]
    row.pop("compact_metadata", None)
    row["asset_snapshot"] = {}
    row["source_label"] = "Source status not recorded"
    row["documentation_status"] = "Not recorded"
    row["project_documentation_context"] = "Documentation context not provided"

    _use_temp_db(monkeypatch, "project_documentation_round_trip_catalog_defaults_imported.db")
    result = import_package_create_as_new(package, target_project_id="project-r27-defaults", confirm=True)
    re_exported = build_project_documentation_export_package(project_id="project-r27-defaults")
    imported_row = re_exported["project_catalog_asset_links"][0]

    assert result["created"] is True
    assert imported_row["catalog_name_source"] == "Plant Promoter Catalog / Source status not recorded"
    assert imported_row["catalog_source_status"] == "Plant Promoter Catalog / Source status not recorded / Not recorded"
    assert imported_row["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert imported_row["linked_persisted_status"] == "Persisted linked catalog reference"


def test_round_trip_export_dedupes_construct_rows_when_project_has_multiple_links(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_dedupe.db")
    seed = _seed_round_trip_source_records()
    repo.create_construct_project_link(
        project_id=seed["project_id"],
        construct_id=seed["construct_id"],
        link_label="Secondary project construct link",
        link_note="Secondary project linkage note.",
        source_context="Secondary round-trip QA context",
        curation_status="documentation review pending",
        review_note="Secondary review note.",
    )

    package = build_project_documentation_export_package(project_id=seed["project_id"])

    assert package["package_metadata"]["counts"]["construct_profile_count"] == 1
    assert package["package_metadata"]["counts"]["cassette_count"] == 2
    assert package["package_metadata"]["counts"]["cassette_part_count"] == 3
    assert len(package["construct_profiles"]) == 1
    assert len(package["project_construct_links"]) == 2


def test_round_trip_copy_avoids_unsafe_product_claims(monkeypatch):
    _use_temp_db(monkeypatch, "project_documentation_round_trip_copy.db")
    seed = _seed_round_trip_source_records()
    package = build_project_documentation_export_package(project_id=seed["project_id"])
    dry_run = build_import_dry_run(package, target_project_id="project-r27-copy")
    combined = str(package).lower() + str(dry_run).lower()
    forbidden = [
        "best promoter",
        "recommended",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
        "validated construct",
        "optimized pathway",
        "successful import",
        "project imported",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert "documentation-only" in combined
