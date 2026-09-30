# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_documentation_package_exporter import (
    LEGACY_PACKAGE_VERSION,
    PACKAGE_VERSION,
    PACKAGE_SCHEMA_VERSION,
    build_project_documentation_export_package,
)
from services.project_documentation_package_importer import (
    build_manifest_review_summary,
    build_import_dry_run,
    detect_import_conflicts,
    import_project_documentation_package_as_new_records,
    import_package_create_as_new,
    summarize_import_plan,
    validate_project_documentation_package,
)
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _use_temp_db(monkeypatch, name: str = "project_documentation_import.db"):
    db_path = repo_local_sqlite_db_path(".pytest_tmp_r82_project_documentation_package_dbs", name)
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    return db_path


def _seed_exportable_records() -> dict:
    profile = repo.create_construct_profile(
        construct_id="construct-source",
        construct_label="Portable source construct",
        construct_type="documentation-only construct draft",
        source_reference="Construct notebook",
        provenance_note="Construct provenance note.",
        review_status="documentation review pending",
    )
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-source",
        cassette_label="Portable cassette",
        cassette_order=1,
        promoter_label="Promoter",
        gene_label="crtB",
        terminator_label="Terminator",
        source_reference="Cassette notebook",
        provenance_note="Cassette provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Portable promoter",
        source_reference="Promoter source",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-001",
        source_record_label="Maize promoter source record",
        evidence_context_note="source context note",
        provenance_note="Promoter provenance note.",
    )
    repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="crtB",
        gene_reference="crtB-ref",
        source_reference="Gene notebook",
        provenance_note="Gene provenance note.",
    )
    repo.add_construct_pathway_step_link(
        profile["construct_id"],
        pathway_step_id="step-source",
        pathway_step_label="Portable pathway step",
        source_reference="Pathway notebook",
        provenance_note="Pathway provenance note.",
    )
    repo.create_construct_project_link(
        project_id="project-source",
        construct_id=profile["construct_id"],
        link_label="Portable project link",
        link_note="Project documentation link.",
        source_context="Pathway Workspace",
        curation_status="documentation review pending",
        review_note="Review note.",
    )
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "project-source",
            "asset_id": "plant-promoter-source",
            "asset_display_name": "Portable plant promoter profile",
            "asset_type": "plant_promoter_profile",
            "asset_version": "catalog-v1",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-source",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "source_labels": "Fixture source: ROOT-101",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 2,
            },
            "asset_snapshot": {
                "asset_type": "plant_promoter_profile",
                "asset_id": "plant-promoter-source",
                "asset_label": "Portable plant promoter profile",
                "asset_version": "catalog-v1",
                "source_label": "Fixture source: ROOT-101",
                "documentation_status": "source review needed",
                "species": "Zea mays (maize)",
                "clade": "monocot",
                "aliases": [],
                "tissue_contexts": ["root"],
                "motif_labels": [],
                "limitation_note": "Pinned documentation snapshot for import.",
            },
            "human_review_required": True,
        }
    )
    return profile


def _package(monkeypatch) -> dict:
    _use_temp_db(monkeypatch)
    _seed_exportable_records()
    package = build_project_documentation_export_package(project_id="project-source")
    return package


def test_import_validator_accepts_valid_package(monkeypatch):
    package = _package(monkeypatch)

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is True
    assert report["errors"] == []
    assert report["package_version"] == PACKAGE_VERSION
    assert report["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert report["counts"]["construct_profiles"] == 1
    assert report["counts"]["promoter_source_link_rows"] == 1
    assert report["counts"]["project_catalog_asset_links"] == 1
    assert report["counts"]["linked_plant_promoter_catalog_references"] == 1
    assert report["counts"]["catalog_reference_missing_metadata_count"] == 2
    assert report["counts"]["catalog_links_with_pinned_snapshots_count"] == 1
    assert report["counts"]["catalog_links_missing_snapshots_count"] == 0
    assert report["manifest_summary"]["package_format"] == "biodesign-studio-project-documentation-package"
    assert report["manifest_summary"]["exported_by_app"] == "BioDesign Studio"
    assert report["manifest_summary"]["documentation_boundary"]
    assert report["manifest_summary"]["limitations"]
    assert report["manifest_summary"]["review_notes"] == []
    assert report["manifest_summary"]["record_counts"]["promoter_source_link_row_count"] == 1
    assert report["integrity_summary"]["package_id"].startswith("bdspkg-")
    assert "documentation-only" in report["documentation_only_boundary"]
    review = report["catalog_reference_import_review_summary"]
    assert review["total_rows_in_package"] == 1
    assert review["complete_documentation_context_count"] == 1
    assert review["safe_fallback_label_count"] == 0
    assert review["live_metadata_fallback_count"] == 0
    assert review["missing_identifier_or_source_status_count"] == 0
    combined = str(report).lower()
    assert "host_chassis_context_summary" not in combined
    assert "host compatibility proof" not in combined
    assert "host recommendation" not in combined
    assert "construct_component_rows" not in combined


def test_manifest_review_summary_exposes_r28_fields_for_import_review(monkeypatch):
    package = _package(monkeypatch)
    package["manifest"]["source_commit_or_tag"] = "v2.6-r28-project-package-manifest-export-polish"

    summary = build_manifest_review_summary(package)
    dry_run = build_import_dry_run(package, target_project_id="project-target")

    assert summary["is_manifest_present"] is True
    assert summary["package_format"] == "biodesign-studio-project-documentation-package"
    assert summary["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert summary["exported_by_app"] == "BioDesign Studio"
    assert summary["source_commit_or_tag"] == "v2.6-r28-project-package-manifest-export-polish"
    assert summary["export_scope"]["selection_mode"] == "project_scoped"
    assert summary["record_counts"]["construct_profile_count"] == 1
    assert summary["record_counts"]["project_catalog_asset_link_count"] == 1
    assert "project_metadata" in summary["included_sections"]
    assert summary["compatibility_notes"]
    assert "documentation-only" in summary["documentation_boundary"]
    assert summary["limitations"]
    assert summary["review_notes"] == []
    assert dry_run["plan"]["manifest_summary"] == summary


def test_import_validator_handles_missing_optional_fields_and_unknown_extra_fields(monkeypatch):
    package = _package(monkeypatch)
    package["project_metadata"].pop("project_name", None)
    package["construct_profiles"][0].pop("construct_type", None)
    package["construct_profiles"][0]["unexpected_local_note"] = "ignored by importer"
    package["cassette_parts"][0]["extra_column_from_future"] = "ignored"

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is True
    assert report["project_name"] == ""
    assert report["errors"] == []


def test_import_dry_run_reports_counts_conflicts_and_deferred_checks(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_dry_run_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    dry_run = build_import_dry_run(package, target_project_id="project-target")

    assert dry_run["is_valid"] is True
    assert dry_run["plan"]["would_create"]["construct_profiles"] == 1
    assert dry_run["plan"]["would_create"]["cassette_parts"] == 1
    assert dry_run["plan"]["would_create"]["promoter_source_link_rows"] == 1
    assert dry_run["plan"]["would_create"]["project_catalog_asset_links"] == 1
    assert dry_run["plan"]["package_version"] == PACKAGE_VERSION
    assert dry_run["plan"]["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert dry_run["plan"]["destructive_actions_available"] is False
    assert dry_run["conflicts"]["has_conflicts"] is False
    assert isinstance(dry_run["conflicts"]["deferred_checks"], list)


def test_import_conflict_preview_detects_duplicate_label_and_project_link(monkeypatch):
    package = _package(monkeypatch)
    _use_temp_db(monkeypatch)
    repo.create_construct_profile(
        construct_id="existing-construct",
        construct_label="Portable source construct",
    )
    repo.create_construct_profile(
        construct_id="existing-link-construct",
        construct_label="Linked construct",
    )
    repo.create_construct_project_link(
        project_id="project-source",
        construct_id="existing-link-construct",
        link_label="Portable project link",
        link_note="Existing link.",
    )

    conflicts = detect_import_conflicts(package, target_project_id="project-source")

    conflict_types = {entry["conflict_type"] for entry in conflicts["conflicts"]}
    assert "construct_label_exists" in conflict_types
    assert "project_construct_link_exists" in conflict_types


def test_import_plan_reports_missing_optional_fields_and_unknown_fields(monkeypatch):
    package = _package(monkeypatch)
    package["project_metadata"].pop("project_name", None)
    package["construct_profiles"][0]["unexpected_local_note"] = "ignored by importer"
    package["cassette_parts"][0]["extra_column_from_future"] = "ignored"

    plan = summarize_import_plan(package, target_project_id="project-target")

    assert "project_metadata.project_name" in plan["missing_optional_fields"]
    assert "construct_profiles[0].unexpected_local_note" in plan["unknown_extra_fields"]
    assert "cassette_parts[0].extra_column_from_future" in plan["unknown_extra_fields"]


def test_import_validator_rejects_structurally_bad_package():
    report = validate_project_documentation_package({"package_metadata": {"package_version": "2.6-r28"}})

    assert report["is_valid"] is False
    assert any("Unsupported package_kind" in error for error in report["errors"])
    assert any("documentation-only" in error for error in report["errors"])


def test_import_validator_rejects_raw_payload_keys(monkeypatch):
    package = _package(monkeypatch)
    package["construct_profiles"][0]["payload_json"] = {"raw": "not accepted"}

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is False
    assert any("raw or executable payload" in error for error in report["errors"])


def test_import_creates_construct_project_link_and_related_records_as_new_rows(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert result["created"] is True
    assert result["errors"] == []
    assert result["created_counts"] == {
        "construct_profiles": 1,
        "expression_cassettes": 1,
        "cassette_parts": 1,
        "linked_genes": 1,
        "linked_pathway_steps": 1,
        "project_construct_links": 1,
        "project_catalog_asset_links": 1,
        "project_catalog_asset_link_duplicates": 0,
        "project_catalog_asset_link_skipped": 0,
    }
    local_construct_id = result["construct_id_map"]["construct-source"]
    local_cassette_id = result["cassette_id_map"]["cassette-source"]
    assert local_construct_id != "construct-source"
    assert local_cassette_id != "cassette-source"
    assert repo.get_construct_profile(local_construct_id)["construct_label"] == "Portable source construct"
    assert repo.list_construct_cassettes(local_construct_id)[0]["cassette_id"] == local_cassette_id
    assert repo.list_construct_cassette_parts(local_cassette_id)[0]["source_record_id"] == "plant-promoter-001"
    assert repo.list_construct_gene_links(local_construct_id)[0]["gene_label"] == "crtB"
    assert repo.list_construct_pathway_step_links(local_construct_id)[0]["pathway_step_id"] == "step-source"
    assert repo.list_construct_project_links(project_id="project-target")[0]["construct_id"] == local_construct_id
    imported_links = project_catalog_link_repo.list_project_catalog_asset_links("project-target")
    assert len(imported_links) == 1
    assert imported_links[0]["asset_id"] == "plant-promoter-source"
    assert imported_links[0]["source_context_snapshot"]["species"] == "Zea mays (maize)"
    assert imported_links[0]["asset_snapshot"]["asset_label"] == "Portable plant promoter profile"
    assert imported_links[0]["asset_snapshot"]["species"] == "Zea mays (maize)"


def test_create_as_new_requires_explicit_confirmation(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_confirm_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))

    result = import_package_create_as_new(package, target_project_id="project-target", confirm=False)

    assert result["created"] is False
    assert result["confirm_required"] is True
    assert result["errors"]
    assert repo.list_construct_profiles() == []


def test_create_as_new_preserves_source_link_fields_and_does_not_overwrite_rows(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_overwrite_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    existing = repo.create_construct_profile(
        construct_id="existing-construct-row",
        construct_label="Portable source construct",
        source_reference="Existing source reference",
        provenance_note="Existing provenance note.",
    )

    result = import_package_create_as_new(package, target_project_id="project-target", confirm=True)

    assert result["created"] is True
    assert existing["source_reference"] == "Existing source reference"
    created_construct = repo.list_construct_profiles()[0]
    assert created_construct["construct_label"] == "Portable source construct"
    assert repo.list_construct_cassette_parts(result["cassette_id_map"]["cassette-source"])[0]["source_record_id"] == "plant-promoter-001"


def test_import_round_trip_export_counts_match_created_records(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_round_trip_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")
    round_trip = build_project_documentation_export_package(project_id="project-target")

    assert result["created"] is True
    assert round_trip["package_metadata"]["counts"]["construct_profile_count"] == 1
    assert round_trip["package_metadata"]["counts"]["cassette_count"] == 1
    assert round_trip["package_metadata"]["counts"]["cassette_part_count"] == 1
    assert round_trip["package_metadata"]["counts"]["promoter_source_link_row_count"] == 1
    assert round_trip["package_metadata"]["counts"]["linked_gene_count"] == 1
    assert round_trip["package_metadata"]["counts"]["linked_pathway_step_count"] == 1
    assert round_trip["package_metadata"]["counts"]["project_construct_link_count"] == 1
    assert round_trip["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1


def test_import_catalog_reference_links_is_idempotent(monkeypatch):
    package = _package(monkeypatch)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_idempotent.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    first = import_project_documentation_package_as_new_records(package, target_project_id="project-target")
    second = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert first["created_counts"]["project_catalog_asset_links"] == 1
    assert second["created_counts"]["project_catalog_asset_links"] == 0
    assert second["created_counts"]["project_catalog_asset_link_duplicates"] == 1
    assert len(project_catalog_link_repo.list_project_catalog_asset_links("project-target")) == 1


def test_import_catalog_reference_links_missing_optional_metadata_is_handled(monkeypatch):
    package = _package(monkeypatch)
    package["project_catalog_asset_links"][0].pop("compact_metadata", None)
    package["project_catalog_asset_links"][0].pop("source_label", None)
    package["project_catalog_asset_links"][0].pop("documentation_status", None)
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_optional.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert result["created_counts"]["project_catalog_asset_links"] == 1
    imported = project_catalog_link_repo.list_project_catalog_asset_links("project-target")[0]
    assert imported["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert imported["source_context_snapshot"]["catalog"] == "Plant Promoter Catalog"
    assert imported["source_context_snapshot"]["profile_id"] == "plant-promoter-source"
    assert imported["source_context_snapshot"]["reference_origin"] == "Project documentation reference"
    assert imported["review_status_snapshot"] == {}
    assert imported["asset_snapshot"]["asset_label"] == "Portable plant promoter profile"


def test_import_catalog_reference_links_restores_linked_reference_context_from_legacy_fields(monkeypatch):
    package = _package(monkeypatch)
    row = package["project_catalog_asset_links"][0]
    row.pop("compact_metadata", None)
    row["asset_snapshot"] = {}
    row["source_label"] = "Fixture source: ROOT-101"
    row["documentation_status"] = "source review needed"
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_legacy_fields.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert result["created_counts"]["project_catalog_asset_links"] == 1
    imported = project_catalog_link_repo.list_project_catalog_asset_links("project-target")[0]
    assert imported["source_context_snapshot"]["profile_id"] == "plant-promoter-source"
    assert imported["source_context_snapshot"]["catalog"] == "Plant Promoter Catalog"
    assert imported["source_context_snapshot"]["reference_origin"] == "Project documentation reference"
    assert imported["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert imported["source_context_snapshot"]["source_labels"] == "Fixture source: ROOT-101"
    assert imported["review_status_snapshot"]["review_status"] == "source review needed"
    assert imported["asset_snapshot"] == {}
    assert imported["asset_label"] == "Portable plant promoter profile"
    assert imported["source_label"] == "Fixture source: ROOT-101"
    assert imported["documentation_status"] == "source review needed"
    re_exported = build_project_documentation_export_package(project_id="project-target")
    re_exported_row = re_exported["project_catalog_asset_links"][0]
    assert re_exported_row["record_identifier"] == "plant-promoter-source"
    assert re_exported_row["catalog_name_source"] == "Plant Promoter Catalog / Fixture source: ROOT-101"
    assert re_exported_row["catalog_source_status"] == "Plant Promoter Catalog / Fixture source: ROOT-101 / source review needed"
    assert re_exported_row["snapshot_state"] == "live metadata fallback"


def test_import_catalog_reference_links_legacy_default_labels_are_not_persisted_as_literal_values(monkeypatch):
    package = _package(monkeypatch)
    package["project_catalog_asset_links"][0].pop("compact_metadata", None)
    package["project_catalog_asset_links"][0]["asset_snapshot"] = {}
    package["project_catalog_asset_links"][0]["source_label"] = "Source status not recorded"
    package["project_catalog_asset_links"][0]["documentation_status"] = "Not recorded"
    package["project_catalog_asset_links"][0]["project_documentation_context"] = "Documentation context not provided"
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_default_labels.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")
    imported = project_catalog_link_repo.list_project_catalog_asset_links("project-target")[0]
    re_exported = build_project_documentation_export_package(project_id="project-target")

    assert result["created_counts"]["project_catalog_asset_links"] == 1
    assert imported["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert "source_labels" not in imported["source_context_snapshot"]
    assert imported["review_status_snapshot"] == {}
    assert imported["asset_snapshot"] == {}
    assert imported["asset_label"] == "Portable plant promoter profile"
    row = re_exported["project_catalog_asset_links"][0]
    assert row["catalog_name_source"] == "Plant Promoter Catalog / Source status not recorded"
    assert row["catalog_source_status"] == "Plant Promoter Catalog / Source status not recorded / Not recorded"
    assert row["project_documentation_context"] == "Pathway Workspace linked catalog assets"


def test_import_catalog_reference_links_malformed_snapshot_warns_and_falls_back(monkeypatch):
    package = _package(monkeypatch)
    package["project_catalog_asset_links"][0]["asset_snapshot"] = "not-json-object"
    package["project_catalog_asset_links"][0]["compact_metadata"]["asset_snapshot"] = "not-json-object"
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_bad_snapshot.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert result["created_counts"]["project_catalog_asset_links"] == 1
    assert any("malformed snapshot metadata" in warning for warning in result["warnings"])
    imported = project_catalog_link_repo.list_project_catalog_asset_links("project-target")[0]
    assert imported["asset_snapshot"]["asset_label"] == ""


def test_import_preview_summary_counts_and_legacy_fallback_rows(monkeypatch):
    package = _package(monkeypatch)
    row = package["project_catalog_asset_links"][0]
    row.pop("compact_metadata", None)
    row["asset_snapshot"] = {}
    row["source_label"] = "Source status not recorded"
    row["documentation_status"] = "Not recorded"
    row["project_documentation_context"] = "Documentation context not provided"
    report = validate_project_documentation_package(package)
    review = report["catalog_reference_import_review_summary"]

    assert review["total_rows_in_package"] == 1
    assert review["complete_documentation_context_count"] == 0
    assert review["safe_fallback_label_count"] == 1
    assert review["live_metadata_fallback_count"] == 1
    assert review["missing_identifier_or_source_status_count"] == 1
    assert any("legacy package fallback" in message for message in review["integrity_messages"])
    assert any("source status not recorded" in message for message in review["integrity_messages"])
    assert any("documentation context not provided" in message for message in review["integrity_messages"])


def test_import_preview_summary_ignores_staged_basket_only_rows(monkeypatch):
    package = _package(monkeypatch)
    package["project_catalog_asset_links"].append(
        {
            "basket_id": "basket-1",
            "project_id": "project-source",
            "asset_id": "staged-only",
            "asset_type": "other_reference",
            "asset_label": "Staged only row",
            "staged_reference_label": "Staged documentation reference",
            "source_context_snapshot": {"project_documentation_context": "Staged basket context"},
            "documentation_status": "Not recorded",
        }
    )

    report = validate_project_documentation_package(package)
    review = report["catalog_reference_import_review_summary"]

    assert review["staged_rows_excluded_count"] == 1
    assert review["total_rows_in_package"] == 1
    assert report["counts"]["project_catalog_asset_links"] == 2
    assert review["integrity_messages"][0].startswith("1 persisted linked reference row")


def test_import_catalog_reference_links_malformed_rows_are_recorded_safely(monkeypatch):
    package = _package(monkeypatch)
    package["project_catalog_asset_links"].append(
        {
            "project_id": "project-source",
            "asset_type": "plant_promoter_profile",
            "asset_label": "Missing asset id row",
            "future_field": "ignored",
        }
    )
    dry_run = build_import_dry_run(package, target_project_id="project-target")
    new_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_import_catalog_malformed.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(new_db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(new_db_path))

    result = import_project_documentation_package_as_new_records(package, target_project_id="project-target")

    assert dry_run["is_valid"] is True
    assert dry_run["plan"]["would_create"]["project_catalog_asset_links"] == 1
    assert "project_catalog_asset_links[1].future_field" in dry_run["plan"]["unknown_extra_fields"]
    assert result["created_counts"]["project_catalog_asset_links"] == 1
    assert result["created_counts"]["project_catalog_asset_link_skipped"] == 1
    assert any("Skipped catalog reference link row" in warning for warning in result["warnings"])


def test_import_invalid_package_does_not_write_rows(monkeypatch):
    _use_temp_db(monkeypatch)
    invalid = {
        "package_metadata": {"package_kind": "wrong", "package_version": "bad"},
        "construct_profiles": [{"construct_id": "unsafe", "construct_label": "Unsafe"}],
    }

    result = import_project_documentation_package_as_new_records(invalid)

    assert result["created"] is False
    assert result["errors"]
    assert repo.list_construct_profiles() == []


def test_importer_copy_avoids_unsafe_product_claims(monkeypatch):
    package = _package(monkeypatch)
    combined = str(validate_project_documentation_package(package)).lower()
    combined += str(import_project_documentation_package_as_new_records(package, target_project_id="copy-check")).lower()
    forbidden = [
        "best promoter",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
        "successful import",
        "project imported",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert "documentation-only" in combined


def test_import_validator_accepts_legacy_package_without_manifest(monkeypatch):
    package = _package(monkeypatch)
    package.pop("manifest", None)
    package.pop("integrity_summary", None)
    package["package_metadata"]["package_version"] = LEGACY_PACKAGE_VERSION
    package["package_metadata"].pop("package_schema_version", None)

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is True
    assert report["package_version"] == LEGACY_PACKAGE_VERSION
    assert report["package_schema_version"] is None
    assert report["manifest_summary"]["is_manifest_present"] is False
    assert "Older package format" in " ".join(report["manifest_summary"]["review_notes"])
    assert report["manifest_summary"]["record_counts"]["construct_profile_count"] == 1


def test_import_validator_handles_partial_manifest_with_review_notes(monkeypatch):
    package = _package(monkeypatch)
    package["manifest"] = {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "documentation_boundary": package["documentation_only_boundary"],
        "record_counts": "needs review",
    }

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is True
    notes = " ".join(report["manifest_summary"]["review_notes"])
    assert "Package format not provided" in notes
    assert "Exported by app not provided" in notes
    assert "Export scope not provided" in notes
    assert "Compatibility notes not provided" in notes
    assert "record_counts is not an object" in notes
    assert report["manifest_summary"]["record_counts"]["construct_profile_count"] == 1


def test_import_validator_warns_when_manifest_schema_version_is_unsupported(monkeypatch):
    package = _package(monkeypatch)
    package["manifest"]["package_schema_version"] = "9.9-r99"

    report = validate_project_documentation_package(package)

    assert report["is_valid"] is True
    assert "Unsupported package_schema_version" in " ".join(report["warnings"])
