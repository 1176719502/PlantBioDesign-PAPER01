from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_quality_dashboard_service import build_project_quality_dashboard
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def test_minimal_project_generates_dashboard_with_expected_gaps() -> None:
    dashboard = build_project_quality_dashboard({"id": 1, "name": "Minimal"})

    assert dashboard["dashboard_title"] == "Project Quality Dashboard"
    assert dashboard["overall_documentation_status"] in {"NEEDS_DOCUMENTATION", "NEEDS_REVIEW"}
    gap_ids = {gap["gap_id"] for gap in dashboard["review_gaps"]}
    assert "no_pathway_steps_documented" in gap_ids
    assert "no_linked_documentation_artifacts" in gap_ids
    assert "no_saved_design_snapshot_linked" in gap_ids
    assert "no_import_safety_check_report_attached" in gap_ids


def test_project_with_steps_and_artifacts_updates_counts_and_gaps() -> None:
    dashboard = build_project_quality_dashboard(
        {
            "id": 2,
            "name": "Documented",
            "pathway_steps": [
                {"step_name": "Step A", "organism": "Host", "enzyme": "Enz", "gene": "geneA"},
                {"step_name": "Step B", "organism": "Host", "enzyme": "Enz", "gene": "geneB"},
            ],
        },
        linked_artifacts=[{"artifact_type": "note", "source": "Library", "title": "Trace note"}],
    )

    assert dashboard["metrics"]["pathway_steps_count"] == 2
    assert dashboard["metrics"]["linked_artifacts_count"] == 1
    gap_ids = {gap["gap_id"] for gap in dashboard["review_gaps"]}
    assert "no_pathway_steps_documented" not in gap_ids
    assert "no_linked_documentation_artifacts" not in gap_ids


def test_quality_dashboard_includes_host_chassis_context_summary() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 210, "name": "Host summary project", "host": "Pichia pastoris"},
        linked_catalog_assets=[
            {
                "project_id": 210,
                "asset_id": "host-note-210",
                "asset_display_name": "Plant context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {
                    "host_context": "Nicotiana benthamiana documentation context",
                },
            }
        ],
    )

    host_summary = dashboard["host_chassis_context_status"]
    assert dashboard["metrics"]["host_context_record_count"] == 2
    assert host_summary["project_context"] == "yeast"
    assert host_summary["plant_is_supported_example_only"] is True
    assert host_summary["contexts_present"] == ["yeast", "plant"]
    assert "generic / unspecified" in host_summary["supported_contexts"]


def test_quality_dashboard_relabels_unsafe_host_compatibility_runtime_copy() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 211, "name": "Host wording project", "host": "Host compatibility notes"},
        linked_catalog_assets=[
            {
                "project_id": 211,
                "asset_id": "host-note-211",
                "asset_display_name": "Host compatibility context note",
                "asset_type": "host_chassis_context_note",
                "documentation_note": "Avoid treating this as host compatibility.",
                "source_context_snapshot": {
                    "host_context": "Host compatibility source note",
                    "project_documentation_context": "Host compatibility readback",
                    "source_review_status": "Host compatibility review pending",
                },
                "review_status_snapshot": {
                    "review_status": "Host compatibility reviewed as documentation context only",
                },
            }
        ],
    )

    text = str(dashboard).lower()
    assert "host compatibility" not in text
    assert "host context" in text
    assert "documentation context note" in text


def test_quality_dashboard_relabels_host_context_copy_from_catalog_aggregates() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 212, "name": "Catalog aggregate wording project"},
        linked_catalog_assets=[
            {
                "project_id": 212,
                "asset_id": "catalog-host-aggregate-212",
                "asset_display_name": "Host compatibility source summary",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "design_record_context",
                "documentation_note": "Compatible host note copied from upstream records.",
                "source_context_snapshot": {
                    "catalog": "Local Design Asset Catalog",
                    "reference_origin": "Expression Wizard catalog context",
                    "project_documentation_context": "Compatibility proof readback",
                    "source_labels": "Recommended host source label",
                },
                "review_status_snapshot": {
                    "curation_statuses": "Host readiness review pending",
                    "review_status": "Validated host note",
                    "missing_metadata_count": 1,
                },
                "asset_snapshot": {
                    "asset_label": "Ready host catalog label",
                    "source_label": "Compatible host source",
                    "documentation_status": "Recommended host review",
                    "limitation_note": "Host compatibility limitation note",
                },
            }
        ],
    )

    text = str(dashboard).lower()
    for unsafe in [
        "host compatibility",
        "compatible host",
        "compatibility proof",
        "host readiness",
        "ready host",
        "validated host",
        "recommended host",
    ]:
        assert unsafe not in text
    assert "host/context documentation" in text
    assert "host context record" in text


def test_quality_dashboard_shared_boundary_normalizes_nested_keys() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 214, "name": "Nested generated key project"},
        linked_catalog_assets=[
            {
                "project_id": 214,
                "asset_id": "nested-host-key",
                "asset_display_name": "Nested host key note",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "project_documentation_context": "Host compatibility nested readback",
                },
                "asset_snapshot": {
                    "host compatibility": {
                        "compatible host": "Compatibility proof nested value",
                    }
                },
            }
        ],
    )

    text = str(dashboard).lower()
    assert "host compatibility" not in text
    assert "compatible host" not in text
    assert "compatibility proof" not in text
    assert "documentation" in text


def test_quality_dashboard_guard_still_rejects_non_host_misleading_claim() -> None:
    try:
        build_project_quality_dashboard(
            {"id": 213, "name": "Unsafe dashboard project"},
            linked_artifacts=[
                {
                    "artifact_type": "review note",
                    "source": "Manual note",
                    "title": "Validated construct claim",
                }
            ],
        )
    except ValueError as exc:
        assert "Misleading dashboard claim detected: validated construct" in str(exc)
    else:
        raise AssertionError("Expected dashboard misleading-claim guard to reject unsafe copy.")


def test_linked_plant_promoter_catalog_references_are_summarized() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 12, "name": "Plant promoter dashboard"},
        linked_catalog_assets=[
            {
                "project_id": 12,
                "asset_id": "plant-promoter-101",
                "asset_display_name": "Maize promoter profile",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-101",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "Fixture source: ROOT-101",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 2,
                },
                "linked_at": "2026-06-17T09:00:00Z",
                "human_review_required": True,
            }
        ],
    )

    assert dashboard["metrics"]["linked_catalog_assets_count"] == 1
    assert dashboard["metrics"]["linked_plant_promoter_profile_count"] == 1
    assert dashboard["metrics"]["plant_promoter_missing_metadata_count"] == 2
    promoter_summary = dashboard["linked_catalog_assets_status"]["plant_promoter_reference_summary"]
    assert promoter_summary["references"][0]["asset_display_name"] == "Maize promoter profile"


def test_linked_catalog_metadata_gaps_are_promoted_to_review_gaps() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 112, "name": "Metadata gap dashboard"},
        linked_catalog_assets=[
            {
                "project_id": 112,
                "asset_id": "plant-promoter-gap-112",
                "asset_display_name": "Gap-heavy promoter profile",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-gap-112",
                },
                "review_status_snapshot": {
                    "missing_metadata_count": 2,
                },
                "human_review_required": True,
            }
        ],
    )

    gap_ids = {gap["gap_id"] for gap in dashboard["review_gaps"]}
    assert "linked_catalog_reference_metadata_review_needed" in gap_ids
    assert dashboard["metrics"]["missing_source_or_review_metadata_count"] == 2
    checklist_by_id = {item["item_id"]: item for item in dashboard["documentation_completeness"]}
    assert checklist_by_id["linked_catalog_reference_metadata_reviewed"]["status"] == "NEEDS_REVIEW"
    gap_text = "\n".join(gap["summary"] + " " + gap["user_guidance"] for gap in dashboard["review_gaps"]).lower()
    checklist_text = str(checklist_by_id["linked_catalog_reference_metadata_reviewed"]).lower()
    guidance_text = "\n".join(dashboard["next_actions"]).lower()
    assert "source/provenance or manual review follow-up" in gap_text
    assert "existing review surfaces" in gap_text
    assert "source/provenance or manual review gaps" in checklist_text
    assert "source/provenance gaps and manual review status" in guidance_text


def test_persisted_catalog_references_are_picked_up_in_summary(monkeypatch) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r147_project_quality_dashboard_service_dbs",
        "quality_dashboard_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "12",
            "asset_id": "plant-promoter-101",
            "asset_display_name": "Persisted maize promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-101",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 1,
            },
            "human_review_required": True,
        }
    )

    dashboard = build_project_quality_dashboard({"id": 12, "name": "Plant promoter dashboard"})

    assert dashboard["metrics"]["linked_catalog_assets_count"] == 1
    assert dashboard["metrics"]["linked_plant_promoter_profile_count"] == 1
    assert dashboard["metrics"]["missing_source_or_review_metadata_count"] == 1


def test_quality_dashboard_reads_imported_catalog_references(monkeypatch) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r147_project_quality_dashboard_service_dbs",
        "quality_dashboard_imported_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "22",
            "asset_id": "plant-promoter-202",
            "asset_display_name": "Imported promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-202",
                "plant_clade": "dicot",
                "species": "Arabidopsis thaliana",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 1,
            },
            "human_review_required": True,
        }
    )

    dashboard = build_project_quality_dashboard({"id": 22, "name": "Imported promoter dashboard"})

    assert dashboard["metrics"]["linked_catalog_reference_count"] == 1
    assert dashboard["metrics"]["linked_plant_promoter_reference_count"] == 1
    assert dashboard["metrics"]["missing_source_or_review_metadata_count"] == 1
    assert dashboard["linked_catalog_assets_status"]["plant_promoter_reference_summary"]["references"][0]["asset_display_name"] == "Imported promoter profile"


def test_quality_dashboard_summarizes_wizard_origin_catalog_references(monkeypatch) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r147_project_quality_dashboard_service_dbs",
        "quality_dashboard_wizard_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "32",
            "asset_id": "plant-promoter-302",
            "asset_display_name": "Wizard-origin promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "design_record_context",
            "documentation_note": "Documentation-only Expression Wizard catalog context reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-302",
                "plant_clade": "dicot",
                "species": "Arabidopsis thaliana",
                "reference_origin": "Expression Wizard catalog context",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 3,
            },
            "human_review_required": True,
        }
    )

    dashboard = build_project_quality_dashboard({"id": 32, "name": "Wizard origin dashboard"})

    assert dashboard["metrics"]["expression_wizard_catalog_reference_count"] == 1
    assert dashboard["metrics"]["expression_wizard_plant_promoter_reference_count"] == 1
    assert dashboard["metrics"]["expression_wizard_catalog_missing_metadata_count"] == 3
    traceability = dashboard["linked_catalog_assets_status"]["expression_wizard_catalog_traceability"]
    assert traceability["traceability_rows"][0]["reference_origin"] == "Expression Wizard catalog context"


def test_seed_backed_linked_plant_promoter_reference_summary_is_visible() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 13, "name": "Seed backed dashboard"},
        linked_catalog_assets=[
            {
                "project_id": 13,
                "asset_id": "plant-promoter-seed-001",
                "asset_display_name": "Maize ubiquitin promoter source context",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-seed-001",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "Literature source placeholder: ZMU-ROOT",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "linked_at": "2026-06-17T09:00:00Z",
                "human_review_required": True,
            }
        ],
    )

    promoter_summary = dashboard["linked_catalog_assets_status"]["plant_promoter_reference_summary"]
    assert promoter_summary["linked_promoter_count"] == 1
    assert promoter_summary["references"][0]["asset_display_name"] == "Maize ubiquitin promoter source context"


def test_saved_design_snapshot_available_and_not_available_cases() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 3, "name": "Saved"},
        saved_designs=[
            {
                "design_id": "design-1",
                "display_name": "Snapshot One",
                "source_saved_design_id": "saved-1",
                "saved_design_version": "v1",
                "identity_source": "linked_artifact",
            }
        ],
    )

    saved = dashboard["saved_design_snapshot_status"]
    assert saved["design_id"] == "design-1"
    assert saved["display_name"] == "Snapshot One"
    assert saved["source_saved_design_id"] == "saved-1"

    missing = build_project_quality_dashboard({"id": 4, "name": "No saved"})
    assert missing["saved_design_snapshot_status"]["status"] == "NOT_AVAILABLE"


def test_export_and_import_safety_status_are_summarized_with_read_only_boundary() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 5, "name": "Package"},
        export_summary={"status": "AVAILABLE", "contents_preview_status": "AVAILABLE"},
        import_safety_summary={
            "overall_status": "WARNING",
            "blocking_issues": ["Issue A"],
            "warnings": ["Warning A", "Warning B"],
            "check_items": [{"status": "NOT_EVALUATED"}, {"status": "PASS"}],
        },
    )

    assert dashboard["export_package_status"]["status"] == "AVAILABLE"
    safety = dashboard["import_safety_status"]
    assert safety["overall_status"] == "WARNING"
    assert safety["blocking_issue_count"] == 1
    assert safety["warning_count"] == 2
    assert safety["not_evaluated_count"] == 1
    text = str(safety)
    assert "Import package safety checks are read-only." in text
    assert "They do not import or modify any project." in text
    assert "No database writes are performed." in text


def test_package_exchange_review_trail_exposes_manifest_context() -> None:
    dashboard = build_project_quality_dashboard(
        {"id": 10, "name": "Package trail"},
        export_summary={
            "status": "AVAILABLE",
            "package_contents_preview_status": "AVAILABLE",
            "documentation_only_package_note": "Export packages are documentation-only project packages.",
        },
        import_safety_summary={
            "status": "AVAILABLE",
            "overall_status": "NEEDS_REVIEW",
            "manifest_summary": {
                "is_manifest_present": True,
                "package_schema_version": "2.6-r28",
                "included_sections": ["project_metadata", "construct_profiles"],
                "record_counts": {"construct_profile_count": 2, "review_gap_count": 1},
                "documentation_boundary": "Manifest review is documentation context.",
                "review_notes": ["Manifest review needs follow-up."],
            },
        },
    )

    trail = dashboard["package_exchange_review_trail"]
    manifest = trail["manifest_review"]
    assert trail["status"] == "AVAILABLE"
    assert manifest["is_manifest_present"] is True
    assert manifest["included_section_count"] == 2
    assert manifest["record_counts"]["record_count_total"] == 3
    assert "Create or review project documentation." in trail["package_workflow_context"]
    assert "Export a documentation package with manifest metadata." in trail["demo_workflow_context"]
    assert "Review the package in Import Manifest Review before local documentation use." in trail["demo_workflow_context"]
    assert "Create a new project copy only through explicit create-as-new confirmation." in trail["demo_workflow_context"]
    assert "Review the package exchange review trail in the Project Review Report and Project Quality Dashboard." in trail["demo_workflow_context"]
    assert "Manifest review needs follow-up." in str(trail)


def test_documentation_completeness_checklist_contains_required_items_and_statuses() -> None:
    dashboard = build_project_quality_dashboard({"id": 6, "name": "Checklist"})
    checklist = dashboard["documentation_completeness"]
    labels = {item["label"] for item in checklist}
    statuses = {item["status"] for item in checklist}

    assert "Project identity documented" in labels
    assert "Pathway steps documented" in labels
    assert "Linked documentation artifacts attached" in labels
    assert "Saved design snapshot linked or traceable" in labels
    assert "Export package status available" in labels
    assert "Import package safety check available" in labels
    assert "Review notes available" in labels
    assert "Boundary notes visible" in labels
    assert statuses <= {"COMPLETE", "MISSING", "NOT_AVAILABLE", "NEEDS_REVIEW"}
    assert "experimental readiness score" not in str(dashboard).lower()


def test_next_actions_are_safe_documentation_actions_only() -> None:
    dashboard = build_project_quality_dashboard({"id": 7, "name": "Actions"})
    text = "\n".join(dashboard["next_actions"]).lower()

    assert "add pathway documentation steps" in text
    assert "link documentation artifacts for traceability" in text
    assert "save or link a wizard design snapshot when needed" in text
    assert "generate a project review report" in text
    assert "export a documentation-only project package" in text
    assert "run import package safety check on an exported package for read-only review" in text
    forbidden = ["run experiment", "validate construct", "optimize pathway", "execute import", "wet-lab protocol"]
    for phrase in forbidden:
        assert phrase not in text


def test_boundary_copy_is_present() -> None:
    text = str(build_project_quality_dashboard({"id": 8, "name": "Boundary"}))

    assert "documentation completeness only" in text
    assert "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment" in text
    assert "does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state" in text
    assert "does not forecast yield" in text
    assert "does not tune pathways" in text
    assert "does not provide wet-lab instructions" in text
    assert "Import Preview remains read-only" in text
    assert "Blocked / NO-GO import states apply only to the gated create-as-new action" in text


def test_no_misleading_claims_in_service_output() -> None:
    text = str(build_project_quality_dashboard({"id": 9, "name": "Claims"})).lower()

    forbidden = [
        "validation success",
        "successful cloning",
        "successful pcr",
        "successful expression",
        "valid" + "ated construct",
        "ready for experiment",
        "experiment-ready",
        "production-ready",
        "yield " + "prediction",
        "optimized pathway",
        "evidence score",
        "readiness score",
        "successful import",
        "valid" + "ated import",
    ]
    for phrase in forbidden:
        assert phrase not in text
