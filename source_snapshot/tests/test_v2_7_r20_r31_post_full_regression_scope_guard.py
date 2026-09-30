from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path

from tests.component_library_v2_scope import audit_candidate_scope


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "docs" / "qa"
CURRENT_TASK = ROOT / "CURRENT_TASK.md"

FULL_REGRESSION_NOTE = QA_DIR / "V2_7_R20_R10_R19_CHECKPOINT_FULL_REGRESSION.md"

FORMAL_BASE = "29a367e01d4a570f00c1417a69bd18b19e983a9d"
REVIEWED_CANDIDATE_BASE = "d4774d2a7f900053c5fd2bd3cc5585a606aa4256"
REVIEWED_SOURCE_REFS = (
    "80cd1807331eb17da1ee450d8f4bb5b0ba34359d",
    "17a115b5d8e4a2c2cfb2817ef604e55ee0f79661",
)

R2_FIX_PATHS = {
    "CURRENT_TASK.md",
    "app.py",
    "locales/en.py",
    "locales/zh_cn.py",
    "docs/qa/V1_PERSIST_I18N_BROWSER_REVIEW_FIX_R2_20260924.md",
    "tests/test_formal_multi_tu_blank_acceptance.py",
    "tests/test_option_display_mapping_i18n.py",
    "tests/test_ui03b_plant_component_library_alignment.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
}

R3_FIX_PATHS = {
    "app.py",
    "locales/en.py",
    "locales/zh_cn.py",
    "docs/qa/V1_MT_STEP6_I18N_FIX_R3_20260924.md",
    "tests/test_multi_tu_five_prime_region.py",
    "tests/test_i18n_r5c_sol_corrections.py",
}

PATHWAY_STATE_MACHINE_FIX_R2_PATHS = {
    "CURRENT_TASK.md",
    "services/gate3_pathway_mapping.py",
    "scripts/acceptance/run_formal_pathway_blank_acceptance.py",
    "tests/test_gate3_pathway_mapping.py",
    "tests/test_formal_pathway_blank_acceptance.py",
    "docs/qa/V1_PATHWAY_STATE_MACHINE_FIX_R2_20260924.md",
}

COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_PATHS = {
    "locales/en.py",
    "locales/zh_cn.py",
    "services/agent_product_adapter.py",
    "scripts/generate_component_library_v2_step3_routability.py",
    "tests/test_component_library_v2_step3_routability.py",
    "docs/qa/V1_COMPONENT_LIBRARY_V2_STEP3_ROUTABILITY_20260928.json",
    "docs/qa/V1_COMPONENT_LIBRARY_V2_STEP3_ROUTABILITY_20260928.md",
    "CURRENT_TASK.md",
    "app.py",
    "services/component_library_v2_adoption.py",
    "services/registry_catalog_ui.py",
    "services/plant_component_workflow_registry.py",
    "services/mvp_multi_tu_runtime.py",
    "services/mvp_multi_tu_persistence.py",
    "scripts/generate_component_library_v2_product_adoption_r1.py",
    "tests/test_component_library_v2_product_adoption_r1.py",
    "tests/test_formal_hsa_ui_regression.py",
    "tests/test_v1_reviewed_component_catalog_integration.py",
    "tests/test_page_consistency_contract.py",
    "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
    "docs/qa/V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_20260927.md",
    "docs/qa/V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_MAPPING_20260927.json",
}

# These are the reconciliation-only paths authorized by the current R1 task
# in addition to the exact reviewed source unions above.
RECONCILIATION_ONLY_PATHS = {
    "docs/qa/V1_PERSIST_I18N_RECONCILIATION_R1_20260923.md",
    "tests/test_durable_save_session_state_r3.py",
    "tests/test_formal_hsa_ui_regression.py",
    "tests/test_formal_project_definition_lifecycle.py",
    "tests/test_formal_single_gene_reopen_state.py",
    "tests/test_formal_single_gene_runtime.py",
    "tests/test_formal_step2_cds_input.py",
    "tests/test_formal_step4_border_resolution.py",
    "tests/test_formal_wizard_action_state.py",
    "tests/test_formal_wizard_renderer_behavior.py",
    "tests/test_professional_review_delivery_package.py",
    "tests/test_gate2_formal_dual_tu_workflow.py",
    "tests/test_gate2_formal_multi_tu_workflow.py",
    "tests/test_gate3_pathway_mapping.py",
    "tests/test_host01b_step1_registry_integration.py",
    "tests/test_mt01_formal_runtime_integration.py",
    "tests/test_mt02_formal_runtime_integration.py",
    "tests/test_multi_tu_five_prime_region.py",
    "tests/test_pbi121_replacement_strategy.py",
    "tests/test_phase2d_batch2_save_semantics.py",
    "tests/test_publication_map_product_wiring.py",
    "tests/test_sequence_transforms_tools02a.py",
    "tests/test_single_gene_project_home_cold_start.py",
    "tests/test_step2_auto_cds_analysis.py",
    "tests/test_step3_three_prime_role_authority.py",
    "tests/test_ui03b_plant_component_library_alignment.py",
    "tests/test_ui04a_step6_inline_results_export.py",
    "tests/test_ui03a_step3_progressive_disclosure.py",
    "tests/test_v1_ai_candidate_route_formal_wiring.py",
}

POST_FULL_REGRESSION_NOTES = [
    "V2_7_R21_R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT.md",
    "V2_7_R22_PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD.md",
    "V2_7_R23_R10_R22_QA_CHECKPOINT_INTEGRITY_GUARD.md",
    "V2_7_R24_R10_R23_QA_NOTE_STRUCTURE_GUARD.md",
    "V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md",
    "V2_7_R26_R10_R25_CHECKPOINT_COPY_BOUNDARY_GUARD.md",
    "V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md",
    "V2_7_R28_0900_CHECKPOINT_HANDOFF_GUARD.md",
    "V2_7_R29_R10_R28_QA_NOTE_STRUCTURE_REFRESH.md",
    "V2_7_R30_R10_R29_COMMIT_READINESS_INVENTORY.md",
    "V2_7_R31_R10_R30_LIVE_WORKTREE_INVENTORY_GUARD.md",
    "V2_7_R32_R20_R31_POST_FULL_REGRESSION_SCOPE_GUARD.md",
]

FULL_REGRESSION_COVERED_PRODUCT_PATHS = {
    "services/canonical_construct_runtime.py",
    "services/component_library_v2_adoption.py",
    "services/formal_project_persistence.py",
    "services/formal_single_gene_runtime.py",
    "services/formal_t_dna_review.py",
    "services/mvp_multi_tu_persistence.py",
    "services/mvp_multi_tu_runtime.py",
    "services/mvp_single_gene_persistence.py",
    "services/pathway_outputs_workflow_view_model.py",
    "services/plant_component_workflow_registry.py",
    "services/registry_catalog_ui.py",
    "services/plant_project_draft_repository.py",
    "services/plant_project_draft_schema.py",
    "services/professional_review_delivery_package.py",
    "services/rice_hsa_ncbi_mvp10_case.py",
    "services/crispr_product_workflow.py",
    "services/crispr_workflow_contract.py",
    "views/PathwayWorkspace.py",
    "views/pathway_workspace_sections/__init__.py",
}

EXPECTED_UNTRACKED_SECTION_PATHS = {
    "services/formal_project_persistence.py",
    "services/plant_component_workflow_registry.py",
    "views/CrisprWorkspace.py",
}

PROTECTED_RUNTIME_PATH_MARKERS = [
    "migrations/",
    "services/project_import_service.py",
    "services/project_export_package_service.py",
    "expression_wizard",
    "primer3",
    ".venv",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _status_paths() -> set[str]:
    return {line[3:].replace("\\", "/") for line in _git_lines("status", "--short", "--untracked-files=all")}


def _current_task_allowed_patterns() -> set[str]:
    reviewed = set(_git_lines("diff", "--name-only", FORMAL_BASE, REVIEWED_CANDIDATE_BASE))
    return (
        reviewed
        | R2_FIX_PATHS
        | R3_FIX_PATHS
        | PATHWAY_STATE_MACHINE_FIX_R2_PATHS
        | COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_PATHS
    )


def _current_task_allows(path: str) -> bool:
    return any(fnmatch(path, pattern) for pattern in _current_task_allowed_patterns())


def test_r20_full_regression_note_records_current_baseline_evidence() -> None:
    source = _read(FULL_REGRESSION_NOTE)

    for expected in [
        "2598 passed, 8 skipped, 2 warnings in 584.54s",
        "R10-R19",
        "No commit or tag was created",
        "No database schema changed",
        "No import/export package schema changed",
        "No Expression Wizard core algorithm changed",
    ]:
        assert expected in source


def test_r21_r32_notes_record_no_product_runtime_change_after_full_regression() -> None:
    missing: list[str] = []

    for note_name in POST_FULL_REGRESSION_NOTES:
        source = _read(QA_DIR / note_name)
        if "No product runtime code changed" not in source:
            missing.append(note_name)

    assert missing == []


def test_live_tracked_product_diff_stays_within_full_regression_covered_paths() -> None:
    # R2 audits every path, including components/export_manager.py. Named
    # focused obligations do not claim retrospective full-suite coverage.
    audit = audit_candidate_scope(ROOT)
    assert audit['committed']
    assert all(rule['regressions'] for rule in audit['coverage'].values())


def test_live_untracked_product_files_are_expected_extracted_sections_only() -> None:
    audit_candidate_scope(ROOT)


def test_live_worktree_has_no_protected_runtime_paths_after_full_regression() -> None:
    audit_candidate_scope(ROOT)


def test_reconciliation_scope_rejects_a_synthetic_unexpected_path() -> None:
    assert not _current_task_allows("tests/unexpected_reconciliation_path.py")


def test_r2_scope_rejects_formerly_whitelisted_unrelated_production_path() -> None:
    assert not _current_task_allows("services/pathway_outputs_workflow_view_model.py")


def test_r3_scope_accepts_only_the_bounded_step6_i18n_paths() -> None:
    assert _current_task_allows("docs/qa/V1_MT_STEP6_I18N_FIX_R3_20260924.md")
    assert _current_task_allows("tests/test_multi_tu_five_prime_region.py")
    assert not _current_task_allows("tests/test_mtu_step6_i18n_unrelated.py")
