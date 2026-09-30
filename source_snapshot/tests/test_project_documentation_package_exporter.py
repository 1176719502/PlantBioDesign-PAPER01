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
    CSV_DEFERRED_NOTE,
    DOCUMENTATION_ONLY_BOUNDARY,
    PACKAGE_VERSION,
    PACKAGE_FORMAT,
    PACKAGE_SCHEMA_VERSION,
    build_project_documentation_export_package,
)
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _use_temp_db(monkeypatch):
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_export.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    return db_path


def _seed_project_construct() -> dict:
    profile = repo.create_construct_profile(
        construct_id="construct-r24",
        construct_label="R24 portable construct",
        construct_type="documentation-only construct draft",
        plasmid_backbone="pR24-Doc",
        host_context_note="Host context recorded for documentation review.",
        source_reference="Construct notebook",
        provenance_note="Construct provenance note.",
        review_status="documentation review pending",
        documentation_scope_note="Metadata package export scope.",
    )
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-r24-a",
        cassette_label="Cassette A",
        cassette_role="expression cassette record",
        cassette_order=1,
        promoter_label="Catalog promoter",
        gene_label="crtI",
        terminator_label="Doc terminator",
        source_reference="Cassette notebook",
        provenance_note="Cassette provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Catalog promoter row",
        part_reference="promoter-ref",
        source_reference="Promoter notebook",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-001",
        source_record_label="Maize promoter source record",
        evidence_context_note="local provenance context only",
        provenance_note="Promoter provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=2,
        part_role="cds",
        part_label="crtI CDS",
        part_reference="crtI-ref",
        source_reference="Gene notebook",
        provenance_note="CDS provenance note.",
    )
    repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="crtI",
        gene_reference="crtI-local-ref",
        source_reference="Gene notebook",
        provenance_note="Gene provenance note.",
    )
    repo.add_construct_pathway_step_link(
        profile["construct_id"],
        pathway_step_id="step-r24-1",
        pathway_step_label="Recorded pathway step",
        source_reference="Pathway notes",
        provenance_note="Pathway link provenance note.",
    )
    repo.create_construct_project_link(
        project_id="project-r24",
        construct_id=profile["construct_id"],
        link_label="R24 project construct link",
        link_note="Connects construct documentation to the project record.",
        source_context="Pathway Workspace manual context",
        curation_status="documentation review pending",
        review_note="Review package before local use.",
    )
    return profile


def _add_catalog_reference(
    *,
    project_id: str = "project-r24",
    asset_id: str = "plant-promoter-r36",
    label: str = "R36 plant promoter profile",
    role: str = "source_review_context",
) -> dict:
    added, _message, stored = project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_display_name": label,
            "asset_type": "plant_promoter_profile",
            "asset_version": "catalog-v1",
            "linkage_role": role,
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": asset_id,
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
                "asset_id": asset_id,
                "asset_label": label,
                "asset_version": "catalog-v1",
                "source_label": "Fixture source: ROOT-101",
                "documentation_status": "source review needed",
                "species": "Zea mays (maize)",
                "clade": "monocot",
                "aliases": [],
                "tissue_contexts": ["root"],
                "motif_labels": [],
                "limitation_note": "Pinned documentation snapshot for package export.",
            },
            "human_review_required": True,
        }
    )
    assert added is True
    return stored


def test_export_package_includes_metadata_and_documentation_boundary(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()

    package = build_project_documentation_export_package(
        project={"id": "project-r24", "name": "R24 project", "target_product": "Demo product"},
        exported_at="2026-06-16T10:00:00+00:00",
    )

    metadata = package["package_metadata"]
    manifest = package["manifest"]
    assert metadata["package_kind"] == "BioDesign Studio project documentation package"
    assert metadata["package_version"] == PACKAGE_VERSION
    assert metadata["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert metadata["exported_at"] == "2026-06-16T10:00:00+00:00"
    assert metadata["documentation_only_boundary"] == DOCUMENTATION_ONLY_BOUNDARY
    assert manifest["package_format"] == PACKAGE_FORMAT
    assert manifest["package_schema_version"] == PACKAGE_SCHEMA_VERSION
    assert manifest["exported_at"] == "2026-06-16T10:00:00+00:00"
    assert manifest["exported_by_app"] == "BioDesign Studio"
    assert manifest["export_scope"]["selection_mode"] == "project_scoped"
    assert manifest["export_scope"]["project_id"] == "project-r24"
    assert manifest["included_sections"]
    assert "project_catalog_asset_links" in manifest["included_sections"]
    assert manifest["compatibility_notes"]
    assert manifest["documentation_boundary"] == DOCUMENTATION_ONLY_BOUNDARY
    assert manifest["limitations"][2] == CSV_DEFERRED_NOTE
    assert "documentation-only" in package["documentation_only_boundary"]
    assert package["known_limitations"][2] == CSV_DEFERRED_NOTE
    assert package["integrity_summary"]["package_id"].startswith("bdspkg-")
    assert "Lightweight package comparison summary only." in package["integrity_summary"]["integrity_note"]
    assert set(package.keys()) == {
        "manifest",
        "package_metadata",
        "project_metadata",
        "project_construct_links",
        "project_catalog_asset_links",
        "construct_profiles",
        "expression_cassettes",
        "cassette_parts",
        "linked_genes",
        "linked_pathway_steps",
        "review_gaps",
        "report_references",
        "documentation_only_boundary",
        "known_limitations",
        "integrity_summary",
    }
    assert "host_chassis_context_summary" not in package
    assert "host_chassis_context" not in package
    assert "host_chassis" not in package
    assert "construct_component_rows" not in package
    assert "construct_component_rows" not in package["manifest"]
    assert "chassis" not in package["manifest"]
    assert "host_chassis" not in package["manifest"]
    assert "host_chassis_context_summary" not in package["manifest"]


def test_export_package_includes_construct_project_cassette_part_and_link_rows(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()

    package = build_project_documentation_export_package(project_id="project-r24")

    counts = package["package_metadata"]["counts"]
    assert counts["construct_profile_count"] == 1
    assert counts["cassette_count"] == 1
    assert counts["cassette_part_count"] == 2
    assert counts["promoter_source_link_row_count"] == 1
    assert counts["linked_gene_count"] == 1
    assert counts["linked_pathway_step_count"] == 1
    assert counts["project_construct_link_count"] == 1
    assert package["construct_profiles"][0]["construct_id"] == "construct-r24"
    assert package["project_construct_links"][0]["project_id"] == "project-r24"
    assert package["expression_cassettes"][0]["cassette_id"] == "cassette-r24-a"
    assert package["linked_genes"][0]["gene_label"] == "crtI"
    assert package["linked_pathway_steps"][0]["pathway_step_id"] == "step-r24-1"


def test_export_package_includes_promoter_source_link_fields(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()

    package = build_project_documentation_export_package(project_id="project-r24")
    promoter = next(row for row in package["cassette_parts"] if row["part_role"] == "promoter")

    assert promoter["source_catalog"] == "Plant Promoter Catalog"
    assert promoter["source_record_id"] == "plant-promoter-001"
    assert promoter["source_record_label"] == "Maize promoter source record"
    assert promoter["evidence_context_note"] == "local provenance context only"


def test_export_package_handles_no_construct_data(monkeypatch):
    _use_temp_db(monkeypatch)

    package = build_project_documentation_export_package(project={"id": "empty-project", "name": "Empty"})

    assert package["project_metadata"]["project_id"] == "empty-project"
    assert package["construct_profiles"] == []
    assert package["expression_cassettes"] == []
    assert package["cassette_parts"] == []
    assert package["package_metadata"]["counts"]["construct_profile_count"] == 0
    assert package["manifest"]["record_counts"]["promoter_source_link_row_count"] == 0
    assert package["project_catalog_asset_links"] == []
    assert package["manifest"]["record_counts"]["project_catalog_asset_link_count"] == 0


def test_export_package_handles_manual_promoter_without_catalog_links(monkeypatch):
    _use_temp_db(monkeypatch)
    profile = repo.create_construct_profile(construct_id="construct-manual", construct_label="Manual promoter construct")
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-manual",
        cassette_label="Manual cassette",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Manual promoter row",
    )

    package = build_project_documentation_export_package(construct_ids=[profile["construct_id"]])
    promoter = package["cassette_parts"][0]

    assert promoter["part_label"] == "Manual promoter row"
    assert promoter["source_catalog"] == ""
    assert promoter["source_record_id"] == ""
    assert promoter["source_record_label"] == ""
    assert promoter["evidence_context_note"] == ""


def test_export_package_copy_avoids_unsafe_product_claims(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()

    combined = str(build_project_documentation_export_package(project_id="project-r24")).lower()
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


def test_export_package_dedupes_construct_rows_when_project_has_multiple_links(monkeypatch):
    _use_temp_db(monkeypatch)
    profile = _seed_project_construct()
    repo.create_construct_project_link(
        project_id="project-r24",
        construct_id=profile["construct_id"],
        link_label="R24 project construct link secondary",
        link_note="Second link for the same construct.",
        source_context="Additional documentation context",
        curation_status="documentation review pending",
        review_note="Secondary review note.",
    )

    package = build_project_documentation_export_package(project_id="project-r24")

    counts = package["package_metadata"]["counts"]
    assert counts["construct_profile_count"] == 1
    assert counts["cassette_count"] == 1
    assert counts["cassette_part_count"] == 2
    assert counts["project_construct_link_count"] == 2
    assert len(package["construct_profiles"]) == 1
    assert [row["link_label"] for row in package["project_construct_links"]] == [
        "R24 project construct link",
        "R24 project construct link secondary",
    ]


def test_export_package_manifest_integrity_summary_is_deterministic_for_same_rows(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()

    package_one = build_project_documentation_export_package(
        project_id="project-r24",
        exported_at="2026-06-16T10:00:00+00:00",
    )
    package_two = build_project_documentation_export_package(
        project_id="project-r24",
        exported_at="2026-06-16T10:00:00+00:00",
    )

    assert package_one["manifest"]["record_counts"] == package_two["manifest"]["record_counts"]
    assert package_one["integrity_summary"]["package_id"] == package_two["integrity_summary"]["package_id"]


def test_export_package_includes_persisted_catalog_reference_links(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()
    _add_catalog_reference()

    package = build_project_documentation_export_package(project_id="project-r24")

    assert package["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1
    assert package["manifest"]["record_counts"]["linked_plant_promoter_count"] == 1
    assert package["manifest"]["record_counts"]["catalog_reference_missing_metadata_count"] == 2
    assert package["manifest"]["record_counts"]["catalog_links_with_pinned_snapshots_count"] == 1
    assert package["manifest"]["record_counts"]["catalog_links_missing_snapshots_count"] == 0
    assert package["manifest"]["record_counts"]["expression_wizard_catalog_reference_count"] == 0
    row = package["project_catalog_asset_links"][0]
    assert row["asset_id"] == "plant-promoter-r36"
    assert row["asset_label"] == "R36 plant promoter profile"
    assert row["asset_version"] == "catalog-v1"
    assert row["source_label"] == "Fixture source: ROOT-101"
    assert row["documentation_status"] == "source review needed"
    assert row["record_identifier"] == "plant-promoter-r36"
    assert row["catalog_label"] == "Plant Promoter Catalog"
    assert row["catalog_name_source"] == "Plant Promoter Catalog / Fixture source: ROOT-101"
    assert row["catalog_source_status"] == "Plant Promoter Catalog / Fixture source: ROOT-101 / source review needed"
    assert row["reference_origin"] == "Project documentation reference"
    assert row["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert row["documentation_note"] == "Documentation-only Plant Promoter Catalog reference for project traceability."
    assert row["linked_reference_label"] == "Linked catalog reference"
    assert row["linked_persisted_status"] == "Persisted linked catalog reference"
    assert row["snapshot_state"] == "pinned snapshot"
    assert "source_context_readback" not in row
    assert "review_needed_context" not in row
    assert "metadata_gap_context" not in row
    assert "catalog_reference_context" not in row
    assert row["asset_snapshot"]["asset_label"] == "R36 plant promoter profile"
    assert row["asset_snapshot"]["species"] == "Zea mays (maize)"
    assert row["snapshot_schema_version"] == "2.6-r39-catalog-reference-snapshot"
    assert row["compact_metadata"]["source_context_snapshot"]["species"] == "Zea mays (maize)"
    assert row["compact_metadata"]["review_status_snapshot"]["missing_metadata_count"] == 2
    assert row["compact_metadata"]["asset_snapshot"]["source_label"] == "Fixture source: ROOT-101"


def test_export_package_summarizes_wizard_origin_catalog_references(monkeypatch):
    _use_temp_db(monkeypatch)
    _add_catalog_reference(role="design_record_context")

    package = build_project_documentation_export_package(project_id="project-r24")
    counts = package["package_metadata"]["counts"]

    assert counts["project_catalog_asset_link_count"] == 1
    assert counts["linked_plant_promoter_count"] == 1
    assert counts["catalog_reference_missing_metadata_count"] == 2
    assert counts["expression_wizard_catalog_reference_count"] == 1
    assert counts["expression_wizard_plant_promoter_reference_count"] == 1
    assert counts["expression_wizard_catalog_missing_metadata_count"] == 2


def test_export_package_catalog_reference_ordering_is_deterministic(monkeypatch):
    _use_temp_db(monkeypatch)
    _add_catalog_reference(asset_id="asset-b", label="Beta profile")
    _add_catalog_reference(asset_id="asset-a2", label="Alpha profile", role="report_context")
    _add_catalog_reference(asset_id="asset-a1", label="Alpha profile", role="project_reference")

    package = build_project_documentation_export_package(project_id="project-r24")

    assert [
        (row["asset_label"], row["asset_id"], row["linkage_role"])
        for row in package["project_catalog_asset_links"]
    ] == [
        ("Alpha profile", "asset-a1", "project_reference"),
        ("Alpha profile", "asset-a2", "report_context"),
        ("Beta profile", "asset-b", "source_review_context"),
    ]


def test_export_package_catalog_reference_fallback_fields_are_clear(monkeypatch):
    _use_temp_db(monkeypatch)
    added, _message, _stored = project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "project-r24",
            "asset_id": "asset-fallback",
            "asset_display_name": "Fallback reference",
            "asset_type": "other_reference",
            "linkage_role": "report_context",
            "documentation_note": "",
            "source_context_snapshot": {},
            "review_status_snapshot": {},
            "human_review_required": True,
        }
    )
    assert added is True

    package = build_project_documentation_export_package(project_id="project-r24")
    row = package["project_catalog_asset_links"][0]

    assert row["record_identifier"] == "asset-fallback"
    assert row["catalog_name_source"] == "Local Design Asset Catalog / Source status not recorded"
    assert row["catalog_source_status"] == "Local Design Asset Catalog / Source status not recorded / Not recorded"
    assert row["reference_origin"] == "Project documentation reference"
    assert row["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert row["documentation_note"] == "Documentation-only reference for project traceability."


def test_export_package_preserves_persisted_catalog_reference_fields_after_import(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()
    _add_catalog_reference()

    package = build_project_documentation_export_package(project_id="project-r24")
    row = package["project_catalog_asset_links"][0]

    assert row["record_identifier"] == "plant-promoter-r36"
    assert row["catalog_label"] == "Plant Promoter Catalog"
    assert row["catalog_name_source"] == "Plant Promoter Catalog / Fixture source: ROOT-101"
    assert row["catalog_source_status"] == "Plant Promoter Catalog / Fixture source: ROOT-101 / source review needed"
    assert row["reference_origin"] == "Project documentation reference"
    assert row["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert row["documentation_note"] == "Documentation-only Plant Promoter Catalog reference for project traceability."
    assert row["linked_reference_label"] == "Linked catalog reference"
    assert row["linked_persisted_status"] == "Persisted linked catalog reference"
    assert row["snapshot_state"] == "pinned snapshot"


def test_export_package_omits_staged_only_catalog_reference_rows(monkeypatch):
    _use_temp_db(monkeypatch)
    _seed_project_construct()
    added, _message, _stored = project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "project-r24",
            "asset_id": "asset-staged-only",
            "asset_display_name": "Staged only reference",
            "asset_type": "other_reference",
            "linkage_role": "project_reference",
            "documentation_note": "Staged basket reference.",
            "source_context_snapshot": {
                "project_documentation_context": "Staged basket context",
                "reference_origin": "Staged basket",
            },
            "review_status_snapshot": {},
            "human_review_required": True,
        }
    )
    assert added is True

    package = build_project_documentation_export_package(project_id="project-r24")

    assert package["project_catalog_asset_links"] == []
