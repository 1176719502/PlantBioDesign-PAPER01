from __future__ import annotations

from pathlib import Path

from core.i18n import translate
import scripts.acceptance.run_formal_multi_tu_blank_acceptance as acceptance_script
from scripts.acceptance.run_formal_multi_tu_blank_acceptance import (
    _canonical_export_evidence,
)
from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_project_draft_repository import SqlitePlantProjectDraftRepository
from tests.test_gate2_formal_multi_tu_workflow import _generate_three_tu
from tests.test_multi_tu_completed_editor_reopen import _bind_completed_state
from tests.test_mvp9_multi_tu_persistence import _initialize_project_history_database


def test_launcher_captures_active_production_database_before_acceptance_isolation() -> None:
    source = Path(acceptance_script.__file__).read_text(encoding="utf-8")
    main_source = source[source.index("def main()") :]
    snapshot_index = main_source.index("snapshot_active_production_database()")
    browser_index = main_source.index("playwright.chromium.launch(")
    configure_index = main_source.index("configure_acceptance_fixture_context(")
    start_index = main_source.index("_start_server_with_authority(")

    assert snapshot_index < browser_index < configure_index < start_index
    assert 'os.environ["BIODESIGN_DB_PATH"] =' not in main_source
    assert (
        "pre_acceptance_production_database_path=pre_acceptance_production_database"
        in main_source
    )
    assert "clear_acceptance_fixture_context()" in main_source
    assert main_source.index("refresh_acceptance_fixture_authority()") > start_index


def test_acceptance_evidence_checks_three_tu_order_orientation_ids_coordinates_and_exports(
    tmp_path: Path,
) -> None:
    complete_plasmid_fixture = _generate_three_tu()
    result = generate_multi_tu_combined_construct(
        project_id="baseline01a-multi-tu-assembly-evidence",
        project_name=complete_plasmid_fixture["project_name"],
        expression_units=complete_plasmid_fixture["original_input"]["expression_units"],
    )
    result["project_type"] = "dual_tu"
    result = _bind_completed_state(result)
    result["formal_project_context"]["current_step"] = 6
    formal_state = result["formal_project_context"]["formal_state"]
    formal_state["formal_multi_tu_step4_confirmation_signature"] = "step4-confirmed"
    formal_state["formal_multi_tu_step5_confirmation_signature"] = "step5-confirmed"
    expected_names = [unit["display_name"] for unit in result["expression_units"]]
    expected_orientations = [unit["orientation"] for unit in result["expression_units"]]

    database_path = tmp_path / "biodesign_unified.db"
    _initialize_project_history_database(database_path)
    repository = SqlitePlantProjectDraftRepository(database_path)
    save_mvp_multi_tu_design(result, repository=repository)
    fasta_path = tmp_path / "complete.fasta"
    genbank_path = tmp_path / "complete.gb"
    fasta_path.write_text(
        result["exports"]["combined_construct_fasta"]["data"], encoding="utf-8"
    )
    genbank_path.write_text(
        result["exports"]["combined_construct_genbank"]["data"], encoding="utf-8"
    )

    evidence = _canonical_export_evidence(
        fasta_path,
        genbank_path,
        repository=repository,
        expected_project_name=result["project_name"],
        expected_display_order=expected_names,
        expected_orientations=expected_orientations,
    )

    assert len(evidence["unit_ids"]) == 3
    assert len(set(evidence["unit_ids"])) == 3
    assert evidence["display_order"] == expected_names
    assert evidence["fasta_matches_canonical"] is True
    assert evidence["genbank_matches_canonical"] is True
    assert evidence["validation_blocking_count"] == 0
    assert evidence["completed_editor_record"] is True
    assert evidence["restored_step"] == 6
    assert evidence["step4_confirmation_persisted"] is True
    assert evidence["step5_confirmation_persisted"] is True
    assert [row["strand"] for row in evidence["unit_ranges"]] == [1, 1, -1]


def test_runner_confirms_step5_then_saves_only_after_reaching_step6() -> None:
    source = Path(acceptance_script.__file__).read_text(encoding="utf-8")
    build = source.split("def _build_blank_multi_tu", 1)[1].split(
        "def _download_pair", 1
    )[0]

    app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "v1.expression.confirm_and_view_results" in app_source
    assert "v1.expression.save_and_view_results" not in app_source
    assert translate("v1.expression.confirm_and_view_results", language="en") == (
        "Confirm and view results"
    )
    assert translate("v1.expression.confirm_and_view_results", language="zh-CN") == (
        "确认并查看结果"
    )
    assert "保存与查看结果" not in build
    assert "Save and view results" not in build
    assert "Confirm and view results" not in build
    assert "确认并查看结果" in build
    assert build.index('"第六步：结果与导出"') < build.index('"保存项目"')


def test_runner_uses_reachable_legacy_and_valid_locale_scenarios() -> None:
    source = Path(acceptance_script.__file__).read_text(encoding="utf-8")
    assert "Project Center" in source
    assert "_seed_legacy_multi_tu_record" in source
    assert "5-prime region required" in source
    assert "A legacy three-role record was loaded." in source
    assert "需补充 5′ 区域" in source
    assert "已读取旧版三角色记录" in source
    assert "Confirm and view results" in source
    assert "确认并查看结果" in source
    assert "_switch_locale(page, \"EN\", \"Step 5: Canonical Assembly Check\")" in source
    assert "_switch_locale(page, \"中文\", \"第五步：Canonical assembly 校验\")" in source
    assert "_assert_no_chinese_leakage(page)" in source


def test_multi_tu_step6_does_not_render_python_source_as_user_content() -> None:
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    step6 = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_persisted_result_downloads", 1
    )[0]
    assert '"""\n        st.dataframe(' not in step6
    assert "st.dataframe(" in step6


def test_legacy_multi_tu_display_labels_are_locale_driven() -> None:
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    results = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_persisted_result_downloads", 1
    )[0]
    assert '_t("v1.common.reverse")' in results
    assert '_t("v1.common.forward")' in results
    assert '"circular": "v1.common.circular"' in source
    assert '"linear": "v1.common.linear"' in source
    assert '"方向": "反向"' not in results
    assert '"方向": "正向"' not in results

    editor = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _structure_overview_html", 1
    )[0]
    overview = source.split("def _render_dual_tu_structure", 1)[1].split(
        "def _render_pcambia1300_workflow_block", 1
    )[0]
    generation = source.split("def _render_dual_tu_step_4", 1)[1].split(
        "def _render_step_4", 1
    )[0]
    for reachable_surface in (editor, overview, generation):
        assert "_t(\"v1.common.reverse\")" in reachable_surface or "_t('v1.common.reverse')" in reachable_surface
        assert "_t(\"v1.common.forward\")" in reachable_surface or "_t('v1.common.forward')" in reachable_surface
        assert "反向（reverse）" not in reachable_surface
        assert "正向（forward）" not in reachable_surface
