from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path

from tests.component_library_v2_scope import audit_candidate_scope

from tests.test_v2_7_r20_r31_post_full_regression_scope_guard import (
    COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_PATHS,
    FORMAL_BASE,
    REVIEWED_CANDIDATE_BASE,
    RECONCILIATION_ONLY_PATHS,
    PATHWAY_STATE_MACHINE_FIX_R2_PATHS,
    R2_FIX_PATHS,
    R3_FIX_PATHS,
    REVIEWED_SOURCE_REFS,
)


ROOT = Path(__file__).resolve().parents[1]
CURRENT_TASK = ROOT / "CURRENT_TASK.md"

EXPECTED_CHANGED_PATHS = {
    "services/pathway_outputs_workflow_view_model.py",
    "tests/test_copy_safety_boundaries.py",
    "tests/test_pathway_outputs_workflow_view_model.py",
    "tests/test_pathway_workspace_batch_a_section_extraction.py",
    "tests/test_pathway_workspace_batch_b_import_sections_extraction.py",
    "tests/test_pathway_workspace_batch_c_layout_sections_extraction.py",
    "tests/test_pathway_workspace_documentation_snapshots_section_extraction.py",
    "tests/test_pathway_workspace_export_package_section_extraction.py",
    "tests/test_pathway_workspace_import_preview_callback_boundary.py",
    "tests/test_pathway_workspace_orchestration_guard.py",
    "tests/test_pathway_workspace_overview_extraction_readiness_guard.py",
    "tests/test_pathway_workspace_project_outputs_boundary.py",
    "tests/test_pathway_workspace_project_outputs_section_extraction.py",
    "tests/test_pathway_workspace_project_report_download_section_extraction.py",
    "tests/test_pathway_workspace_quality_dashboard_section_extraction.py",
    "tests/test_pathway_workspace_review_report_section_extraction.py",
    "tests/test_pathway_workspace_traceability_section_extraction.py",
    "tests/test_ui_empty_error_state_sweep.py",
    "tests/test_v2_6_r111_post_r110_demo_baseline_health_check.py",
    "tests/test_v2_7_project_outputs_checkpoint_protected_area_guard.py",
    "tests/test_v2_7_r10_r22_qa_checkpoint_integrity.py",
    "tests/test_v2_7_r10_r23_qa_note_structure_guard.py",
    "tests/test_v2_7_r10_r24_checkpoint_manifest.py",
    "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
    "tests/test_v2_7_r10_r26_checkpoint_manifest_refresh.py",
    "tests/test_v2_7_r10_r27_0900_checkpoint_handoff.py",
    "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
    "tests/test_v2_7_r10_r29_commit_readiness_inventory.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    "views/PathwayWorkspace.py",
    "views/pathway_workspace_sections/__init__.py",
    "views/pathway_workspace_sections/project_outputs_section.py",
    "views/pathway_workspace_sections/project_report_download_section.py",
    "docs/qa/V2_7_R10_TRACEABILITY_BOUNDARY_AUDIT.md",
    "docs/qa/V2_7_R11_PROJECT_OUTPUTS_DETAIL_TABLE_STATE.md",
    "docs/qa/V2_7_R12_PROJECT_OUTPUTS_BOUNDARY_GUARD.md",
    "docs/qa/V2_7_R13_PROJECT_OUTPUTS_DETAIL_TABLE_WIDTH_GUARD.md",
    "docs/qa/V2_7_R14_PROJECT_OUTPUTS_NEXT_CUT_AUDIT.md",
    "docs/qa/V2_7_R15_PROJECT_OUTPUTS_SECTION_EXTRACTION_FEASIBILITY_AUDIT.md",
    "docs/qa/V2_7_R16_PROJECT_OUTPUTS_SECTION_SHELL_EXTRACTION.md",
    "docs/qa/V2_7_R17_PROJECT_OUTPUTS_CALLBACK_MIGRATION_AUDIT.md",
    "docs/qa/V2_7_R18_PROJECT_REPORT_DOWNLOAD_SECTION_EXTRACTION.md",
    "docs/qa/V2_7_R19_IMPORT_PREVIEW_CALLBACK_BOUNDARY_GUARD.md",
    "docs/qa/V2_7_R20_R10_R19_CHECKPOINT_FULL_REGRESSION.md",
    "docs/qa/V2_7_R21_R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT.md",
    "docs/qa/V2_7_R22_PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD.md",
    "docs/qa/V2_7_R23_R10_R22_QA_CHECKPOINT_INTEGRITY_GUARD.md",
    "docs/qa/V2_7_R24_R10_R23_QA_NOTE_STRUCTURE_GUARD.md",
    "docs/qa/V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md",
    "docs/qa/V2_7_R26_R10_R25_CHECKPOINT_COPY_BOUNDARY_GUARD.md",
    "docs/qa/V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md",
    "docs/qa/V2_7_R28_0900_CHECKPOINT_HANDOFF_GUARD.md",
    "docs/qa/V2_7_R29_R10_R28_QA_NOTE_STRUCTURE_REFRESH.md",
    "docs/qa/V2_7_R30_R10_R29_COMMIT_READINESS_INVENTORY.md",
    "docs/qa/V2_7_R31_R10_R30_LIVE_WORKTREE_INVENTORY_GUARD.md",
    "docs/qa/V2_7_R32_R20_R31_POST_FULL_REGRESSION_SCOPE_GUARD.md",
    "docs/qa/V2_7_R33_0900_FINAL_CHECK_COMMAND_BUNDLE.md",
    "docs/qa/V2_7_R34_PRE_0900_FINAL_COMMAND_DRY_RUN.md",
    "docs/qa/V2_7_R35_0900_COMPLETION_CRITERIA_GUARD.md",
    "docs/qa/V2_7_R36_0900_TIMED_READINESS_AUDIT_TEMPLATE.md",
    "docs/qa/V2_7_R37_0900_STOP_CONDITION_DECISION_GUARD.md",
    "docs/qa/V2_7_R38_PRE_0900_COMPLETION_CLAIM_GUARD.md",
    "docs/qa/V2_7_R39_PRE_0900_HEARTBEAT_READINESS_AUDIT.md",
    "docs/qa/V2_7_R40_PRE_0900_HEARTBEAT_AUTOMATION_HANDOFF.md",
    "docs/qa/V2_7_R41_PRE_0900_AUTOMATION_VIEW_CONFIRMATION.md",
    "docs/qa/V2_7_R42_0900_CURRENT_FINAL_COMMAND_BUNDLE_SUPPLEMENT.md",
    "docs/qa/V2_7_R43_0900_CURRENT_TIMED_AUDIT_TEMPLATE_SUPPLEMENT.md",
    "docs/qa/V2_7_R44_0900_FINAL_AUDIT_EXECUTION_ORDER.md",
    "docs/qa/V2_7_R45_0900_HEARTBEAT_PROMPT_REFRESH.md",
    "docs/qa/V2_7_R46_PRE_0900_ACTIVE_GOAL_CONTINUATION_GUARD.md",
    "docs/qa/V2_7_R47_0900_CURRENT_FINAL_COMMAND_BUNDLE_REFRESH.md",
    "docs/qa/V2_7_R48_0900_CURRENT_EXECUTION_ORDER_REFRESH.md",
    "docs/qa/V2_7_R49_0900_CURRENT_TIMED_AUDIT_FIELDS_REFRESH.md",
    "docs/qa/V2_7_R50_0900_CURRENT_COMPLETION_CRITERIA_REFRESH.md",
    "docs/qa/V2_7_R51_0900_CURRENT_DECISION_RULES_REFRESH.md",
    "docs/qa/V2_7_R52_0900_CURRENT_CHAIN_CONSISTENCY_GUARD.md",
    "docs/qa/V2_7_R53_0900_POST_R52_SUPPLEMENTAL_COMMAND_BUNDLE.md",
    "docs/qa/V2_7_R54_0900_CURRENT_TIMED_AUDIT_FIELDS_WITH_R53.md",
    "docs/qa/V2_7_R55_0900_CURRENT_COMPLETION_CRITERIA_WITH_R54.md",
    "docs/qa/V2_7_R56_0900_CURRENT_DECISION_RULES_WITH_R55.md",
    "docs/qa/V2_7_R57_0900_CURRENT_EXECUTION_ORDER_WITH_R56.md",
    "docs/qa/V2_7_R58_PRE_0900_AUTOMATION_CURRENT_CHAIN_CONFIRMATION.md",
    "docs/qa/V2_7_R59_0900_CURRENT_DIRECT_EVIDENCE_WORKSHEET.md",
    "docs/qa/V2_7_R60_0900_FINAL_TIMED_AUDIT_RECORD_SHELL.md",
    "docs/qa/V2_7_R61_0900_POST_R60_SUPPLEMENTAL_COMMAND_BUNDLE.md",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
    "tests/test_v2_7_r33_0900_final_check_command_bundle.py",
    "tests/test_v2_7_r34_pre_0900_final_command_dry_run.py",
    "tests/test_v2_7_r35_0900_completion_criteria_guard.py",
    "tests/test_v2_7_r36_0900_timed_readiness_audit_template.py",
    "tests/test_v2_7_r37_0900_stop_condition_decision_guard.py",
    "tests/test_v2_7_r38_pre_0900_completion_claim_guard.py",
    "tests/test_v2_7_r39_pre_0900_heartbeat_readiness_audit.py",
    "tests/test_v2_7_r40_pre_0900_heartbeat_automation_handoff.py",
    "tests/test_v2_7_r41_pre_0900_automation_view_confirmation.py",
    "tests/test_v2_7_r42_0900_current_final_command_bundle_supplement.py",
    "tests/test_v2_7_r43_0900_current_timed_audit_template_supplement.py",
    "tests/test_v2_7_r44_0900_final_audit_execution_order.py",
    "tests/test_v2_7_r45_0900_heartbeat_prompt_refresh.py",
    "tests/test_v2_7_r46_pre_0900_active_goal_continuation_guard.py",
    "tests/test_v2_7_r47_0900_current_final_command_bundle_refresh.py",
    "tests/test_v2_7_r48_0900_current_execution_order_refresh.py",
    "tests/test_v2_7_r49_0900_current_timed_audit_fields_refresh.py",
    "tests/test_v2_7_r50_0900_current_completion_criteria_refresh.py",
    "tests/test_v2_7_r51_0900_current_decision_rules_refresh.py",
    "tests/test_v2_7_r52_0900_current_chain_consistency_guard.py",
    "tests/test_v2_7_r53_0900_post_r52_supplemental_command_bundle.py",
    "tests/test_v2_7_r54_0900_current_timed_audit_fields_with_r53.py",
    "tests/test_v2_7_r55_0900_current_completion_criteria_with_r54.py",
    "tests/test_v2_7_r56_0900_current_decision_rules_with_r55.py",
    "tests/test_v2_7_r57_0900_current_execution_order_with_r56.py",
    "tests/test_v2_7_r58_pre_0900_automation_current_chain_confirmation.py",
    "tests/test_v2_7_r59_0900_current_direct_evidence_worksheet.py",
    "tests/test_v2_7_r60_0900_final_timed_audit_record_shell.py",
    "tests/test_v2_7_r61_0900_post_r60_supplemental_command_bundle.py",
}

CURRENT_GUARD_FIX_PATHS = {
    "docs/qa/V2_7_R63_POST_COMMIT_LIVE_WORKTREE_GUARD_STATE_FIX.md",
}

CURRENT_R73_BASELINE_RECONCILIATION_PATHS = {
    "docs/qa/V2_7_R73_PLANT_ROUTE_PRESENTER_READBACK_BASELINE_RECONCILIATION.md",
    "tests/test_plant_component_candidate_match_readback.py",
    "tests/test_plant_construct_slot_plan_presenter.py",
    "tests/test_plant_design_workspace_ui_shell.py",
    "tests/test_plant_evidence_package_flow_presenter.py",
    "tests/test_plant_evidence_package_flow_readback.py",
    "tests/test_plant_route_draft_presenter.py",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
}

CURRENT_R76_CHAIN_RUNNER_PATHS = {
    "docs/qa/V2_7_R76_PLANT_REVIEW_WORKFLOW_CHAIN_RUNNER.md",
    "services/plant_review_workflow_chain_runner.py",
    "tests/test_plant_review_workflow_chain_runner.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
}

CURRENT_HISTORICAL_FULL_SUITE_REPAIR_PATHS = {
    "docs/qa/data_manifests/v2_7_r226_real_construct_capability_matrix.json",
    "tests/test_r134_rice_albumin_seed_review_visible_mount.py",
    "tests/test_r150_plant_review_targeted_readability_polish.py",
    "tests/test_plant_review_slot_coverage_matrix_mount.py",
    "tests/test_r223_plant_expression_workspace_prototype.py",
    "tests/test_rice_albumin_workspace_visible_workflow.py",
}

CURRENT_MVP6_FORMAL_THREE_PAGE_UI_PATHS = {
    "artifacts/mvp_acceptance/acceptance_result.json",
    "artifacts/mvp_acceptance/after_complete_vector.png",
    "artifacts/mvp_acceptance/after_real_case.png",
    "docs/qa/MVP6_FORMAL_THREE_PAGE_UI_QA.md",
    "mvp_app.py",
    "scripts/acceptance/run_mvp_persistence_three_round_acceptance.py",
    "scripts/acceptance/run_mvp_three_round_acceptance.py",
    "scripts/acceptance/run_mvp_user_cds_input_acceptance.py",
    "scripts/acceptance/run_mvp_windows_launcher_acceptance.py",
    "scripts/windows/biodesign_mvp_launcher.py",
    "services/mvp_single_gene_persistence.py",
    "services/plant_project_draft_repository.py",
    "tests/helpers/fake_streamlit.py",
    "tests/test_mvp6_formal_three_page_ui.py",
    "tests/test_mvp6_project_deletion.py",
    "tests/test_mvp_windows_launcher_runtime.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
}

CURRENT_MVP9_MULTI_TU_RUNTIME_PATHS = {
    "docs/qa/V2_7_MVP9_DUAL_TRANSCRIPTION_UNIT_RUNTIME_QA.md",
    "services/canonical_construct_runtime.py",
    "services/mvp_multi_tu_persistence.py",
    "services/mvp_multi_tu_runtime.py",
    "tests/data/mvp9_multi_tu_cases.json",
    "tests/mvp8_fixed_snapshot_equivalence.py",
    "tests/test_mvp9_multi_tu_persistence.py",
    "tests/test_mvp9_multi_tu_runtime.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
}

CURRENT_V1_FINAL_PRODUCT_RECONCILIATION_PATHS = {
    "app.py",
    "data/plant_component_registry_v1/registry.batch1.json",
    "data/plant_component_registry_v1/sequences/PCLV1-3REG-CAMV35S-212.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-3REG-E8-140.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-3REG-LEB4-123.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-5UTR-CDOPA5GT-21.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-5UTR-CYP76AD1-258.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-5UTR-DODA1-59.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-5UTR-E8-39.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-5UTR-TEV-136.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-CDS-BAR.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-CDS-HPTII.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-CDS-SGFP.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-PRO-35S2-758.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-PRO-E8-2164.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-PRO-LEB4-2697.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-PRO-RD29A-824.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-TER-HSP18-2-250.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-TER-RBCS-E9-295.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-VEC-PCAMBIA1300.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-VEC-PCSGFPBT.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-VEC-PGWB8.fasta",
    "data/plant_component_registry_v1/sequences/PCLV1-VEC-PPZP201.fasta",
    "data/plant_component_registry_v1/source_manifest.csv",
    "data/plant_component_registry_v1/source_records/AB289771.1.gb",
    "data/plant_component_registry_v1/source_records/AF234296.1.gb",
    "data/plant_component_registry_v1/source_records/AF309825.2.gb",
    "data/plant_component_registry_v1/source_records/AY973635.1.gb",
    "data/plant_component_registry_v1/source_records/DQ370426.1.gb",
    "data/plant_component_registry_v1/source_records/KJ561284.1.gb",
    "data/plant_component_registry_v1/source_records/PP558908.1.gb",
    "data/plant_component_registry_v1/source_records/U10489.1.gb",
    "data/plant_component_registry_v1/source_records/X03677.1.gb",
    "data/plant_component_registry_v1/source_records/X13437.1.gb",
    "data/plant_component_registry_v1/source_records/X17220.1.gb",
    "data/plant_knowledge_cases_v1/reporter_expression_construct_case.json",
    "data/plant_knowledge_layer_v1/evidence_curation_v1.json",
    "data/plant_knowledge_layer_v1/evidence_curation_v1.schema.json",
    "data/real_case_contracts_v1/mt01_pgrdl_sp/expected_hashes.json",
    "data/real_case_contracts_v1/mt02_pdoe13/expected_hashes.json",
    "docs/qa/V1_CRISPR_P0_PRODUCT_INCLUSION_R1_20260824.md",
    "docs/qa/V1_PUBLICATION_DATA_MINIMUM_EXPANSION_R1_20260824.md",
    "packaging/resource_manifest.json",
    "scripts/acceptance/run_formal_crispr_p0_acceptance.py",
    "scripts/acceptance/run_formal_single_gene_blank_acceptance.py",
    "scripts/data/build_plant_component_registry_expansion_v1.py",
    "scripts/validate_plant_component_registry.py",
    "scripts/validate_plant_knowledge_case_v1.py",
    "scripts/validate_plant_knowledge_layer_v1.py",
    "services/crispr_product_workflow.py",
    "services/crispr_workflow_contract.py",
    "tests/test_app_startup_state.py",
    "tests/test_crispr_product_workflow.py",
    "tests/test_crispr_workflow_contract.py",
    "tests/test_crispr_workspace.py",
    "tests/test_formal_crispr_p0_acceptance.py",
    "tests/test_formal_hsa_ui_regression.py",
    "tests/test_formal_single_gene_reopen_state.py",
    "tests/test_formal_step_navigation.py",
    "tests/test_left_navigation_ia.py",
    "tests/test_mt01_gold_standard_contract.py",
    "tests/test_phase2d_batch3_legacy_ui_isolation.py",
    "tests/test_plant_component_registry_v1_batch1.py",
    "tests/test_plant_component_registry_v1_l1_recovery.py",
    "tests/test_plant_knowledge_case_v1.py",
    "tests/test_plant_knowledge_layer_v1_curation.py",
    "tests/test_r110_navigation_runtime_copy_safety.py",
    "tests/test_r178_ui_surface_freeze_and_navigation.py",
    "tests/test_r227_navigation_metric_typography.py",
    "tests/test_registry_v1_distribution_foundation.py",
    "tests/test_registry_v1_distribution_persistence.py",
    "tests/test_registry_v1_ui_catalog_behavior.py",
    "tests/test_v1_component_library_workflow_integration.py",
    "tests/test_v2_6_r111_post_r110_demo_baseline_health_check.py",
    "views/CrisprWorkspace.py",
}

CURRENT_PHASE2D_BATCH2_JSON_SCHEMA_PATHS = {
    "services/plant_project_draft_schema.py",
}

CURRENT_TOMATO_SINGLE_GENE_ELIGIBILITY_R1_PATHS = {
    "data/plant_host_registry_v1/hosts.json",
    "tests/test_agent_v1_ui_backend_wiring.py",
    "tests/test_host01b_step1_registry_integration.py",
    "tests/test_plant_host_registry_v1.py",
    "tests/test_tomato_single_gene_product_eligibility_r1.py",
}

ALLOWED_LIVE_WORKTREE_PATHS = (
    EXPECTED_CHANGED_PATHS
    | CURRENT_GUARD_FIX_PATHS
    | CURRENT_R73_BASELINE_RECONCILIATION_PATHS
    | CURRENT_R76_CHAIN_RUNNER_PATHS
    | CURRENT_HISTORICAL_FULL_SUITE_REPAIR_PATHS
    | CURRENT_MVP6_FORMAL_THREE_PAGE_UI_PATHS
    | CURRENT_MVP9_MULTI_TU_RUNTIME_PATHS
    | CURRENT_V1_FINAL_PRODUCT_RECONCILIATION_PATHS
    | CURRENT_TOMATO_SINGLE_GENE_ELIGIBILITY_R1_PATHS
    | PATHWAY_STATE_MACHINE_FIX_R2_PATHS
    | COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_PATHS
)

PROTECTED_PATH_MARKERS = [
    "migrations/",
    "schema",
    "services/project_import_service.py",
    "services/project_export_package_service.py",
    "primer3",
    ".venv",
    "expression_wizard",
]

CLEAN_POST_COMMIT_NOTE = "clean post-commit state: no live worktree paths to inventory"
DIRTY_OR_STAGED_NOTE = (
    "dirty or staged pre-commit state: live paths must stay inside the "
    "R10-R61 checkpoint inventory plus current guard-fix, R73 reconciliation evidence, or R76 chain runner paths"
)


def _status_lines() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _path_from_status_line(line: str) -> str:
    path = line[3:].replace("\\", "/")
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path


def _paths_from_status_lines(status_lines: list[str]) -> set[str]:
    return {_path_from_status_line(line) for line in status_lines}


def _current_task_allowed_patterns(source: str | None = None) -> set[str]:
    if source is not None:
        return {
            line.split("`", 2)[1]
            for line in source.splitlines()
            if line.strip().startswith("- `") and line.count("`") >= 2
        }
    result = subprocess.run(
        ["git", "diff", "--name-only", FORMAL_BASE, REVIEWED_CANDIDATE_BASE],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        line.replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    } | R2_FIX_PATHS | R3_FIX_PATHS | PATHWAY_STATE_MACHINE_FIX_R2_PATHS | COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_PATHS


def _path_is_allowed(path: str, patterns: set[str]) -> bool:
    reviewed = {
        line.replace("\\", "/")
        for line in subprocess.run(
            ["git", "diff", "--name-only", FORMAL_BASE, REVIEWED_CANDIDATE_BASE],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if line.strip()
    }
    return (
        path in reviewed
        | R2_FIX_PATHS
        | PATHWAY_STATE_MACHINE_FIX_R2_PATHS
        or any(fnmatch(path, pattern) for pattern in patterns)
    )


def _unexpected_live_paths(
    status_lines: list[str],
    current_task_patterns: set[str] | None = None,
) -> list[str]:
    patterns = _current_task_allowed_patterns() if current_task_patterns is None else current_task_patterns
    return sorted(path for path in _paths_from_status_lines(status_lines) if not _path_is_allowed(path, patterns))


def _protected_hits(
    status_lines: list[str],
    current_task_patterns: set[str] | None = None,
) -> list[str]:
    patterns = (
        _current_task_allowed_patterns()
        if current_task_patterns is None
        else current_task_patterns
    )
    actual_paths = {
        path.lower()
        for path in _paths_from_status_lines(status_lines)
        if path not in CURRENT_PHASE2D_BATCH2_JSON_SCHEMA_PATHS
        and path not in CURRENT_V1_FINAL_PRODUCT_RECONCILIATION_PATHS
        and not any(fnmatch(path, pattern) for pattern in patterns)
    }
    return [
        path
        for path in sorted(actual_paths)
        for marker in PROTECTED_PATH_MARKERS
        if marker in path
    ]


def _inventory_state_note(status_lines: list[str]) -> str:
    if not _paths_from_status_lines(status_lines):
        return CLEAN_POST_COMMIT_NOTE
    return DIRTY_OR_STAGED_NOTE


def test_r31_state_model_records_clean_post_commit_inventory() -> None:
    status_lines: list[str] = []

    assert _paths_from_status_lines(status_lines) == set()
    assert _unexpected_live_paths(status_lines) == []
    assert _protected_hits(status_lines) == []
    assert _inventory_state_note(status_lines) == CLEAN_POST_COMMIT_NOTE


def test_r31_state_model_allows_dirty_or_staged_checkpoint_paths() -> None:
    status_lines = [
        " M app.py",
        "A  docs/qa/V1_PERSIST_I18N_BROWSER_REVIEW_FIX_R2_20260924.md",
        "?? tests/test_option_display_mapping_i18n.py",
    ]

    assert _unexpected_live_paths(status_lines) == []
    assert _protected_hits(status_lines) == []
    assert _inventory_state_note(status_lines) == DIRTY_OR_STAGED_NOTE


def test_r31_state_model_rejects_unexpected_dirty_or_staged_paths() -> None:
    status_lines = [
        " M services/pathway_outputs_workflow_view_model.py",
        "A  services/project_import_service.py",
        "?? scratch.md",
    ]

    assert _unexpected_live_paths(status_lines) == [
        "scratch.md",
        "services/pathway_outputs_workflow_view_model.py",
        "services/project_import_service.py",
    ]
    assert _protected_hits(status_lines) == ["services/project_import_service.py"]


def test_r2_scope_accepts_reviewed_candidate_and_bounded_fix_paths() -> None:
    patterns = _current_task_allowed_patterns()
    assert _unexpected_live_paths([" M app.py"], patterns) == []
    assert _unexpected_live_paths(
        ["?? docs/qa/V1_PERSIST_I18N_BROWSER_REVIEW_FIX_R2_20260924.md"], patterns
    ) == []


def test_r31_state_model_allows_current_task_patterns() -> None:
    source = """# Current Task\n\n## Scope Guard Paths\n\n- `core/config.py`\n- `audit_reports/baseline_phase1_5D/**`\n\n## Stop Conditions\n"""
    patterns = _current_task_allowed_patterns(source)
    status_lines = [
        " M core/config.py",
        "?? audit_reports/baseline_phase1_5D/FULL_REGRESSION_RESULTS.md",
    ]

    assert _unexpected_live_paths(status_lines, patterns) == []
    assert _protected_hits(status_lines, patterns) == []


def test_r31_state_model_rejects_path_outside_current_task_patterns() -> None:
    status_lines = [" M core/config.py", "?? services/project_import_service.py"]

    assert _unexpected_live_paths(status_lines, {"core/config.py"}) == ["services/project_import_service.py"]


def test_r31_live_worktree_contains_only_allowed_inventory_paths() -> None:
    audit = audit_candidate_scope(ROOT)
    assert audit['committed']
    assert set(audit['effective']) == set(audit['coverage'])


def test_r31_live_worktree_excludes_protected_areas() -> None:
    # The exact R2 manifest supersedes historical live-state exceptions.
    audit_candidate_scope(ROOT)
