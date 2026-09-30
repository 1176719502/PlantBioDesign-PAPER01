from __future__ import annotations

from pathlib import Path

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]


def test_formal_option_mappings_have_bilingual_display_values_and_stable_values() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"standard_plant_expression_vector": "v1.expression.standard_plant_expression_vector"' in source
    assert '"metabolic_pathway_multi_tu_vector": "v1.expression.metabolic_pathway_multi_tu_vector"' in source
    assert '"公共数据库记录": "v1.expression.public_database_record"' in source
    assert '"未修改的来源序列": "v1.expression.unmodified_source_sequence"' in source
    assert '"terminator": "v1.expression.transcription_terminator"' in source
    assert '"靶向序列": "v1.expression.targeting_sequence"' in source

    assert translate("v1.expression.standard_plant_expression_vector", language="en") == "Standard plant expression vector"
    assert translate("v1.expression.standard_plant_expression_vector", language="zh-CN") == "常规植物表达载体"
    assert translate("v1.expression.public_database_record", language="en") == "Public database record"
    assert translate("v1.expression.public_database_record", language="zh-CN") == "公共数据库记录"
    assert translate("v1.expression.not_configured", language="en") == "Not configured"
    assert translate("v1.expression.not_configured", language="zh-CN") == "未配置"


def test_component_library_type_filter_uses_display_mapping_without_replacing_filter_values() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "_TYPE_FILTER_VALUES" in source
    assert "_COMPONENT_LIBRARY_TYPE_FILTER_VALUES" in source
    assert "format_func=lambda value: _localized_value(value" in source
    assert 'if type_filter != "all" and row.get("component_type") != type_filter' in source
    assert '"formal_selectable"' in source


def test_component_library_filter_values_are_locale_independent() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"formal_library_workflow"' in source
    assert '"formal_library_type_radio_v2"' in source
    assert '"all": "v1.component_library.all_records"' in source
    assert '"all": "v1.component_library.all"' in source


def test_option_mapping_labels_are_not_locale_mutations_of_canonical_values() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'key="formal_step1_design_scenario"' in source
    assert 'key="formal_step1_project_type"' in source
    assert 'format_func=lambda value: _t(scenario_labels[value])' in source
    assert 'format_func=lambda value: _t(mode_labels[value])' in source
    assert 'format_func=lambda value: _localized_value(value, _SOURCE_TYPE_LABELS)' in source
