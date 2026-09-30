from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services import project_quality_dashboard_service
from services import project_review_report_service
from services.expression_wizard_catalog_picker_presenter import (
    DEFAULT_WIZARD_REFERENCE_NOTE,
    WIZARD_REFERENCE_ROLE,
    add_expression_wizard_catalog_context_link,
    build_expression_wizard_catalog_link_payload,
    build_expression_wizard_catalog_picker_view_model,
    build_expression_wizard_catalog_traceability_summary,
)
from services.project_documentation_package_exporter import build_project_documentation_export_package


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_wizard_catalog_picker.db"
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    return db_path


def _record(
    asset_id: str,
    asset_type: str,
    display_name: str,
    *,
    context: str = "source context placeholder",
) -> dict:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "aliases": [],
        "short_description": "Metadata-only local catalog record.",
        "organism_or_source_context": context,
        "sequence_available": False,
        "sequence_hash": "",
        "sequence_hash_algorithm": "",
        "source_notes": "Source review note.",
        "provenance_status": "source review needed",
        "version_context": "test seed",
        "review_status": "human review needed",
        "human_review_notes": "Human review note.",
        "tags": [],
        "documentation_boundary_note": "Documentation-only record.",
    }


def test_picker_view_model_no_project_context_empty_state():
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={},
        local_asset_records=[_record("asset-1", "promoter", "Alpha promoter")],
    )

    assert view_model["status"] == "no_project_context"
    assert view_model["project_id"] == ""
    assert view_model["options"] == []
    assert "No project context is linked" in view_model["message"]


def test_seed_backed_plant_promoter_options_visible():
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={"source": "pathway_workspace", "project_id": 5},
        local_asset_records=[],
    )

    promoter_options = view_model["plant_promoter_options"]
    assert promoter_options
    assert any(row["asset_id"] == "plant-promoter-seed-001" for row in promoter_options)
    assert "Component Library promoter asset records" in view_model["seed_context_copy"]
    assert "local curated sample context" in view_model["seed_context_copy"]
    assert all(row["asset_type"] == "plant_promoter_profile" for row in promoter_options)
    assert all(
        "Component Library promoter asset metadata" in row["limitation_note"]
        for row in promoter_options
    )
    assert all(row["source_label"] == "Plant Promoter Catalog" for row in promoter_options)


def test_picker_options_use_deterministic_ordering():
    records = [
        _record("asset-b", "terminator", "Beta terminator"),
        _record("asset-a2", "promoter", "Alpha promoter"),
        _record("asset-a1", "promoter", "Alpha promoter"),
    ]

    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={"source": "pathway_workspace", "project_id": 5},
        local_asset_records=records,
    )
    local_rows = view_model["available_catalog_assets"]

    assert [(row["asset_type"], row["display_label"], row["asset_id"]) for row in local_rows] == [
        ("promoter", "Alpha promoter", "asset-a1"),
        ("promoter", "Alpha promoter", "asset-a2"),
        ("terminator", "Beta terminator", "asset-b"),
    ]


def test_link_payload_includes_documentation_metadata_for_local_asset():
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={"source": "pathway_workspace", "project_id": 5},
        local_asset_records=[_record("asset-prom", "promoter", "Local promoter context")],
    )
    option = view_model["available_catalog_assets"][0]

    link = build_expression_wizard_catalog_link_payload(
        project_id=5,
        option=option,
        documentation_note=DEFAULT_WIZARD_REFERENCE_NOTE,
        linked_at="session",
    )

    assert link["project_id"] == "5"
    assert link["asset_id"] == "asset-prom"
    assert link["asset_type"] == "promoter"
    assert link["linkage_role"] == WIZARD_REFERENCE_ROLE
    assert link["documentation_note"] == DEFAULT_WIZARD_REFERENCE_NOTE
    assert link["source_context_snapshot"]["catalog"] == "Local Design Asset Catalog"
    assert link["source_context_snapshot"]["wizard_context"] == "Expression Wizard design record"
    assert link["source_context_snapshot"]["reference_origin"] == "Expression Wizard catalog context"
    assert link["source_context_snapshot"]["project_documentation_context"] == "Expression Wizard Step 6 catalog context"
    assert link["review_status_snapshot"]["curation_statuses"] == "human review needed"
    assert link["asset_snapshot"]["asset_label"] == "Local promoter context"
    assert link["asset_snapshot"]["source_label"] == "source review needed"
    assert link["human_review_required"] is True


def test_duplicate_link_guard_returns_existing_reference(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    records = [_record("asset-prom", "promoter", "Local promoter context")]
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={"source": "pathway_workspace", "project_id": 5},
        local_asset_records=records,
    )
    option_id = view_model["available_catalog_assets"][0]["option_id"]

    first = add_expression_wizard_catalog_context_link(
        project_context={"source": "pathway_workspace", "project_id": 5},
        option_id=option_id,
        local_asset_records=records,
    )
    second = add_expression_wizard_catalog_context_link(
        project_context={"source": "pathway_workspace", "project_id": 5},
        option_id=option_id,
        local_asset_records=records,
    )

    assert first["added"] is True
    assert second["added"] is False
    assert second["duplicate"] is True
    assert second["link"]["link_id"] == first["link"]["link_id"]
    assert len(project_catalog_link_repo.list_project_catalog_asset_links("5")) == 1


def test_wizard_created_link_appears_in_persisted_repository(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    result = add_expression_wizard_catalog_context_link(
        project_context={"source": "pathway_workspace", "project_id": 5},
        option_id="plant::plant_promoter_profile::plant-promoter-seed-001",
        local_asset_records=[],
    )

    persisted = project_catalog_link_repo.list_project_catalog_asset_links("5")

    assert result["added"] is True
    assert len(persisted) == 1
    assert persisted[0]["asset_id"] == "plant-promoter-seed-001"
    assert persisted[0]["asset_type"] == "plant_promoter_profile"
    assert persisted[0]["linkage_role"] == WIZARD_REFERENCE_ROLE
    assert persisted[0]["source_context_snapshot"]["catalog"] == "Plant Promoter Catalog"
    assert persisted[0]["source_context_snapshot"]["reference_origin"] == "Expression Wizard catalog context"
    assert persisted[0]["source_context_snapshot"]["project_documentation_context"] == "Expression Wizard Step 6 catalog context"
    assert persisted[0]["asset_snapshot"]["asset_label"] == "Maize ubiquitin promoter source context"
    assert persisted[0]["asset_snapshot"]["species"] == "Zea mays (maize)"


def test_traceability_summary_dedupes_orders_and_handles_missing_metadata():
    links = [
        {
            "project_id": "p-1",
            "asset_id": "asset-b",
            "asset_display_name": "Beta context",
            "asset_type": "promoter",
            "linkage_role": WIZARD_REFERENCE_ROLE,
            "documentation_note": DEFAULT_WIZARD_REFERENCE_NOTE,
            "source_context_snapshot": {"catalog": "Local Design Asset Catalog"},
            "review_status_snapshot": {"human_review_status": "human review needed"},
            "human_review_required": True,
        },
        {
            "project_id": "p-1",
            "asset_id": "asset-a",
            "asset_display_name": "Alpha context",
            "asset_type": "plant_promoter_profile",
            "linkage_role": WIZARD_REFERENCE_ROLE,
            "documentation_note": DEFAULT_WIZARD_REFERENCE_NOTE,
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "source_labels": "Fixture source: ROOT-101",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 2,
            },
            "asset_snapshot": {
                "asset_type": "plant_promoter_profile",
                "asset_id": "asset-a",
                "asset_label": "Pinned Alpha context",
                "asset_version": "pinned-v1",
                "source_label": "Pinned fixture source",
                "documentation_status": "pinned source review needed",
                "species": "Pinned species",
                "clade": "Pinned clade",
                "aliases": [],
                "tissue_contexts": [],
                "motif_labels": [],
                "limitation_note": "Pinned documentation snapshot.",
            },
            "human_review_required": True,
        },
        {
            "project_id": "p-1",
            "asset_id": "asset-a",
            "asset_display_name": "Alpha context",
            "asset_type": "plant_promoter_profile",
            "linkage_role": WIZARD_REFERENCE_ROLE,
            "documentation_note": DEFAULT_WIZARD_REFERENCE_NOTE,
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "source_labels": "Fixture source: ROOT-101",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 2,
            },
            "human_review_required": True,
        },
        {
            "project_id": "p-1",
            "asset_id": "asset-z",
            "asset_display_name": "Non-wizard context",
            "asset_type": "promoter",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only reference.",
            "source_context_snapshot": {},
            "review_status_snapshot": {},
            "human_review_required": True,
        },
    ]

    summary = build_expression_wizard_catalog_traceability_summary(links, project_id="p-1")

    assert summary["reference_count"] == 2
    assert summary["plant_promoter_reference_count"] == 1
    assert summary["missing_metadata_count"] == 3
    assert [(row["asset_label"], row["asset_id"]) for row in summary["traceability_rows"]] == [
        ("Pinned Alpha context", "asset-a"),
        ("Beta context", "asset-b"),
    ]
    assert summary["traceability_rows"][0]["source_label"] == "Pinned fixture source"
    assert summary["traceability_rows"][0]["record_identifier"] == "asset-a"
    assert "Plant Promoter Catalog / Pinned fixture source / pinned source review needed" == summary["traceability_rows"][0]["catalog_source_status"]
    assert summary["traceability_rows"][0]["snapshot_status"] == "pinned documentation snapshot"
    assert summary["traceability_rows"][0]["reference_origin"] == "Expression Wizard catalog context"
    assert summary["traceability_rows"][0]["reference_note"] == DEFAULT_WIZARD_REFERENCE_NOTE
    assert summary["traceability_rows"][0]["linked_project_id"] == "p-1"


def test_wizard_created_link_appears_in_package_report_and_quality_summary(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(
        project_review_report_service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )
    add_expression_wizard_catalog_context_link(
        project_context={"source": "pathway_workspace", "project_id": "r37-project"},
        option_id="plant::plant_promoter_profile::plant-promoter-seed-001",
        local_asset_records=[],
    )

    package = build_project_documentation_export_package(project_id="r37-project")
    report = project_review_report_service.build_project_review_report(
        {"id": "r37-project", "name": "R37 project"}
    )
    dashboard = project_quality_dashboard_service.build_project_quality_dashboard(
        {"id": "r37-project", "name": "R37 project"}
    )

    assert package["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1
    assert package["package_metadata"]["counts"]["linked_plant_promoter_count"] == 1
    assert package["package_metadata"]["counts"]["expression_wizard_catalog_reference_count"] == 1
    assert package["package_metadata"]["counts"]["expression_wizard_plant_promoter_reference_count"] == 1
    assert "Maize ubiquitin promoter source context" in report["detailed_documentation_report_draft"]["markdown"]
    assert report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_plant_promoter_count"] == 1
    traceability = report["detailed_documentation_report_draft"]["linked_catalog_assets"]["expression_wizard_catalog_traceability"]
    assert traceability["reference_count"] == 1
    assert "Expression Wizard catalog traceability" in report["detailed_documentation_report_draft"]["markdown"]
    assert dashboard["metrics"]["linked_catalog_reference_count"] == 1
    assert dashboard["metrics"]["linked_plant_promoter_reference_count"] == 1
    assert dashboard["metrics"]["expression_wizard_catalog_reference_count"] == 1


def test_picker_user_visible_copy_avoids_forbidden_claim_terms():
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context={"source": "pathway_workspace", "project_id": 5},
        local_asset_records=[_record("asset-prom", "promoter", "Local promoter context")],
    )
    combined = "\n".join(
        [
            view_model["message"],
            view_model["boundary_copy"],
            view_model["seed_context_copy"],
            *[
                "\n".join(
                    str(row.get(key, ""))
                    for key in (
                        "select_label",
                        "display_label",
                        "species_or_clade",
                        "source_label",
                        "documentation_status",
                        "limitation_note",
                    )
                )
                for row in view_model["options"]
            ],
        ]
    ).lower()

    forbidden = [
        "recommend" + "ed",
        "best",
        "optimal",
        "valid" + "ated",
        "approv" + "ed",
        "safe for use",
        "ready for synthesis",
        "ready for wet lab",
        "experimentally confirmed",
        "host compatible",
        "predict" + "ion",
        "optimiz" + "ation",
        "rank" + "ing",
        "scor" + "ing",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []
