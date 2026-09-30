from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from core.i18n import translate
from services.dna_sequence_analysis import (
    DnaSequenceAnalysisResult,
    SequenceTopology,
    analyze_dna_sequence,
)
from views import SequenceToolbox as toolbox


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "views" / "SequenceToolbox.py"
APP = ROOT / "app.py"
MANIFEST = ROOT / "packaging" / "resource_manifest.json"
PAGE_TEST_SCRIPT = r"""
import json
import sys
from streamlit.testing.v1 import AppTest
from views import SequenceToolbox as toolbox

raw_sequence, topology, action = sys.argv[1:4]
page = AppTest.from_string(
    "from views.SequenceToolbox import render\nrender()"
).run(timeout=10)
if action != "initial":
    page.text_area(key=toolbox.SEQUENCE_INPUT_KEY).input(raw_sequence).run()
    page.selectbox(key=toolbox.TOPOLOGY_KEY).select(topology).run()
    if not page.button(key="sequence_toolbox_analyze").disabled:
        page.button(key="sequence_toolbox_analyze").click().run()
if action == "stale":
    page.text_area(key=toolbox.SEQUENCE_INPUT_KEY).input("ATGN").run()
elif action == "clear":
    page.session_state["canonical_sequence"] = "UNCHANGED"
    page.button(key="sequence_toolbox_clear").click().run()
elif action == "transform_change":
    page.text_area(key="sequence_toolbox_transform_input").input("AUGC").run()
elif action == "translation_change":
    page.text_area(key="sequence_toolbox_translation_input").input("ATGAAATAA").run()
    page.button(key="sequence_toolbox_translate").click().run()
elif action == "transform_valid":
    page.text_area(key="sequence_toolbox_transform_input").input("ATGC").run()
elif action == "translation_valid":
    page.text_area(key="sequence_toolbox_translation_input").input("ATGC").run()
elif action == "orf_empty":
    page.text_area(key="sequence_toolbox_translation_input").input("ATG").run()
elif action == "transform_example":
    page.button(key="sequence_toolbox_transform_example").click().run()
elif action == "translation_example":
    page.button(key="sequence_toolbox_translation_example").click().run()
elif action == "clear_top_input":
    page.text_area(key=toolbox.SEQUENCE_INPUT_KEY).input("").run()
elif action == "clear_transform_input":
    page.text_area(key="sequence_toolbox_transform_input").input("ATGC").run()
    page.button(key="sequence_toolbox_transform").click().run()
    page.text_area(key="sequence_toolbox_transform_input").input("").run()
elif action == "clear_translation_input":
    page.text_area(key="sequence_toolbox_translation_input").input("ATGAAATAA").run()
    page.button(key="sequence_toolbox_translate").click().run()
    page.text_area(key="sequence_toolbox_translation_input").input("").run()

payload = {
    "exceptions": [str(item.value) for item in page.exception],
    "titles": [item.value for item in page.title],
    "text_area": page.text_area(key=toolbox.SEQUENCE_INPUT_KEY).value,
    "topology": page.selectbox(key=toolbox.TOPOLOGY_KEY).value,
    "buttons": [item.label for item in page.button],
    "metrics": {item.label: item.value for item in page.metric},
    "metric_labels": [item.label for item in page.metric],
    "code": [item.value for item in page.code],
    "success": [item.value for item in page.success],
    "warning": [item.value for item in page.warning],
    "error": [item.value for item in page.error],
    "info": [item.value for item in page.info],
    "markdown": [item.value for item in page.markdown],
    "caption": [item.value for item in page.caption],
    "analysis_disabled": page.button(key="sequence_toolbox_analyze").disabled,
    "transform_disabled": page.button(key="sequence_toolbox_transform").disabled,
    "translation_disabled": page.button(key="sequence_toolbox_translate").disabled,
    "transform_input": page.text_area(key="sequence_toolbox_transform_input").value,
    "translation_input": page.text_area(key="sequence_toolbox_translation_input").value,
    "has_analysis_result": toolbox.RESULT_KEY in page.session_state,
    "has_transform_result": toolbox.TRANSFORM_RESULT_KEY in page.session_state,
    "has_translation_result": toolbox.TRANSLATION_RESULT_KEY in page.session_state,
    "canonical_sequence": page.session_state["canonical_sequence"]
        if "canonical_sequence" in page.session_state else None,
}
print("TOOLBOX_RESULT=" + json.dumps(payload, ensure_ascii=False))
"""


def _page_result(
    raw_sequence: str = "",
    topology: str = SequenceTopology.UNKNOWN.value,
    action: str = "initial",
) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", PAGE_TEST_SCRIPT, raw_sequence, topology, action],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    marker = "TOOLBOX_RESULT="
    line = next(
        (line for line in completed.stdout.splitlines() if line.startswith(marker)),
        None,
    )
    assert line is not None, completed.stdout
    return json.loads(line.removeprefix(marker))


def _analyze(
    raw_sequence: str,
    topology: str = SequenceTopology.UNKNOWN.value,
) -> dict[str, object]:
    result = _page_result(raw_sequence, topology, "analyze")
    assert result["exceptions"] == []
    return result


def test_page_initial_render_is_stable_and_waits_for_user_action() -> None:
    page = _page_result()

    assert page["exceptions"] == []
    assert page["titles"] == [translate("v1.common.sequence_tools", language="en")]
    assert translate("v1.sequence_tools.basic_dna_sequence_analysis_conversion", language="en") in page["caption"]
    assert page["text_area"] == ""
    assert page["topology"] == "unknown"
    assert translate("v1.sequence_tools.analyze_sequence", language="en") in page["buttons"]
    assert translate("v1.common.clear_all", language="en") in page["buttons"]
    assert translate("v1.sequence_tools.convert_sequence", language="en") in page["buttons"]
    assert translate("v1.sequence_tools.translate_selected_reading_frame", language="en") in page["buttons"]
    assert page["analysis_disabled"] is True
    assert page["transform_disabled"] is True
    assert page["translation_disabled"] is True
    assert page["transform_input"] == ""
    assert page["translation_input"] == ""
    assert page["buttons"].count(translate("v1.common.load_example", language="en")) == 2
    assert translate("v1.sequence_tools.empty_input_awaiting_valid_dna_input_before", language="en") in page["info"]
    assert page["metrics"] == {}
    assert page["error"] == []


@pytest.mark.parametrize("topology", tuple(SequenceTopology))
def test_adapter_passes_raw_input_and_topology_unchanged_to_formal_service(
    topology: SequenceTopology,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | SequenceTopology]] = []

    def spy(
        raw_sequence: str,
        topology: str | SequenceTopology = SequenceTopology.UNKNOWN,
    ) -> DnaSequenceAnalysisResult:
        calls.append((raw_sequence, topology))
        return analyze_dna_sequence(raw_sequence, topology=topology)

    monkeypatch.setattr(toolbox, "analyze_dna_sequence", spy)
    raw_sequence = " aT\nN\t! "

    result = toolbox.run_sequence_analysis(raw_sequence, topology)

    assert calls == [(raw_sequence, topology)]
    assert result.raw_sequence == raw_sequence
    assert result.normalized_sequence == "ATN!"


def test_acgt_analysis_displays_service_result_fields() -> None:
    page = _analyze("at gc")
    metrics = page["metrics"]

    assert metrics == {
        translate("v1.sequence_tools.analysis_validity", language="en"): translate("runtime.valid", language="en"),
        translate("v1.sequence_tools.construct_ready", language="en"): translate("runtime.yes", language="en"),
        translate("v1.common.topology", language="en"): translate("runtime.unknown", language="en"),
        translate("v1.sequence_tools.standardized_text_length", language="en"): "4",
        translate("v1.sequence_tools.number_valid_bases", language="en"): "4",
        translate("v1.sequence_tools.dna_sequence_length", language="en"): "4",
        translate("v1.sequence_tools.number_non_ambiguous_bases", language="en"): "4",
        translate("v1.sequence_tools.number_ambiguous_bases", language="en"): "0",
        translate("v1.sequence_tools.gc_count", language="en"): "2",
        translate("v1.sequence_tools.gc_percentage", language="en"): "50.00%",
    }
    assert page["code"] == ["ATGC", "GCAT"]
    assert any("construct-ready" in value.casefold() for value in page["success"])
    assert page["error"] == []


def test_iupac_ambiguity_displays_dual_gc_and_warnings() -> None:
    page = _analyze("ACGTN", topology="linear")
    metrics = page["metrics"]

    assert metrics[translate("v1.sequence_tools.construct_ready", language="en")] == translate("runtime.no", language="en")
    assert metrics[translate("v1.common.topology", language="en")] == translate("runtime.linear", language="en")
    assert metrics[translate("v1.sequence_tools.number_ambiguous_bases", language="en")] == "1"
    assert metrics[translate("v1.sequence_tools.gc_over_full_iupac_compliant_length", language="en")] == "40.00%"
    assert metrics[translate("v1.sequence_tools.gc_c_g_t_non_ambiguous_bases", language="en")] == "50.00%"
    assert page["code"] == ["ACGTN", "NACGT"]
    warnings = page["warning"]
    assert any(translate("v1.sequence_tools.ambiguous_bases_cause_differences_gc_interpretation_review", language="en") in value for value in warnings)
    assert any("AMBIGUOUS_BASES_PRESENT" in value for value in warnings)
    assert any("NOT_CONSTRUCT_READY" in value for value in warnings)


def test_all_ambiguous_sequence_does_not_show_false_unambiguous_gc() -> None:
    page = _analyze("NN", topology="circular")
    metrics = page["metrics"]

    assert metrics[translate("v1.common.topology", language="en")] == translate("runtime.circular", language="en")
    assert metrics[translate("v1.sequence_tools.gc_over_full_iupac_compliant_length", language="en")] == "0.00%"
    assert metrics[translate("v1.sequence_tools.gc_c_g_t_non_ambiguous_bases", language="en")] == translate("runtime.not_computable", language="en")


@pytest.mark.parametrize("raw_sequence", ("AUGC", "AT! 1"))
def test_invalid_top_level_input_is_not_submitted_for_analysis(raw_sequence: str) -> None:
    page = _page_result(raw_sequence, action="analyze")

    assert page["analysis_disabled"] is True
    assert page["has_analysis_result"] is False
    assert page["metrics"] == {}
    assert translate("v1.sequence_tools.invalid_input_dna_analysis_construct_generation_cannot", language="en") in page["info"]


def test_empty_submission_reports_empty_state_without_fake_gc() -> None:
    page = _page_result(" \n\t", action="analyze")

    assert page["analysis_disabled"] is True
    assert page["has_analysis_result"] is False
    assert page["metrics"] == {}
    assert translate("v1.sequence_tools.empty_input_awaiting_valid_dna_input_before", language="en") in page["info"]
    assert page["code"] == []


def test_changed_input_marks_existing_result_stale_until_reanalysis() -> None:
    page = _page_result("ATGC", action="stale")

    assert page["exceptions"] == []
    assert page["metrics"] == {}
    assert any(translate("v1.sequence_tools.input_topology_changed_re_analyze_update_results", language="en") in value for value in page["info"])


@pytest.mark.parametrize("action", ("transform_change", "translation_change"))
def test_tool_inputs_do_not_mark_top_level_analysis_stale(action: str) -> None:
    page = _page_result("ATGC", action=action)

    assert page["exceptions"] == []
    assert page["metrics"]
    assert not any("请重新分析" in value for value in page["info"])
    assert page["analysis_disabled"] is False
    assert page["has_analysis_result"] is True


@pytest.mark.parametrize(
    ("action", "disabled_key"),
    (("transform_valid", "transform_disabled"), ("translation_valid", "translation_disabled")),
)
def test_valid_tool_inputs_enable_their_primary_action(action: str, disabled_key: str) -> None:
    page = _page_result(action=action)

    assert page[disabled_key] is False


def test_tool_sections_do_not_include_the_top_level_analysis_prompt() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "输入序列并选择拓扑后，点击“分析序列”查看结果。" not in source


@pytest.mark.parametrize(
    ("action", "input_key"),
    (("transform_example", "transform_input"), ("translation_example", "translation_input")),
)
def test_examples_are_loaded_only_after_explicit_user_action(action: str, input_key: str) -> None:
    page = _page_result(action=action)

    assert page[input_key] != ""


@pytest.mark.parametrize(
    ("action", "result_key", "disabled_key"),
    (
        ("clear_top_input", "has_analysis_result", "analysis_disabled"),
        ("clear_transform_input", "has_transform_result", "transform_disabled"),
        ("clear_translation_input", "has_translation_result", "translation_disabled"),
    ),
)
def test_clearing_an_input_invalidates_its_result_and_disables_its_action(
    action: str,
    result_key: str,
    disabled_key: str,
) -> None:
    page = _page_result("ATGC", action=action)

    assert page[result_key] is False
    assert page[disabled_key] is True


def test_translation_metadata_is_separate_and_localized() -> None:
    page = _page_result("ATGC", action="translation_change")

    assert translate("v1.sequence_tools.strand_orientation", language="en", value=translate("v1.sequence_tools.forward_strand", language="en")) in page["markdown"]
    assert translate("v1.sequence_tools.reading_frame", language="en", value=1) in page["markdown"]
    assert translate("v1.sequence_tools.amino_acid_sequence", language="en") in page["markdown"]
    assert "MK*" in page["code"]


def test_empty_orf_uses_localized_message_without_empty_table_row() -> None:
    page = _page_result("ATGC", action="orf_empty")
    rendered = "\n".join(
        [*page["info"], *page["markdown"], *page["code"]]
    ).lower()

    assert translate("v1.sequence_tools.no_orf_matching_rules_detected", language="en").lower() in rendered
    assert "empty" not in rendered
    assert any("1-based closed intervals" in value for value in page["caption"])


def test_clear_resets_only_toolbox_state() -> None:
    page = _page_result("ATGC", topology="circular", action="clear")

    assert page["exceptions"] == []
    assert page["text_area"] == ""
    assert page["topology"] == "unknown"
    assert page["canonical_sequence"] == "UNCHANGED"
    assert page["metrics"] == {}


def test_page_module_has_no_second_sequence_algorithm_or_side_effect_dependency() -> None:
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "services.dna_sequence_analysis" in imported_modules
    assert not imported_modules.intersection(
        {
            "core.database",
            "core.unified_database",
                "requests",
                "urllib",
                "utils.sequence_utils",
            }
        )
    assert not called_names.intersection({"open", "write", "write_text", "connect"})
    assert "maketrans" not in source
    assert ".translate(" not in source
    assert ".count(" not in source
    assert "frozenset" not in source


def test_formal_navigation_and_runtime_manifest_include_toolbox_only() -> None:
    app_source = APP.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runtime_modules = set(manifest["runtime_python_modules"])

    assert 'PAGE_SEQUENCE_TOOLBOX = "Sequence Toolbox"' in app_source
    assert '_NAV_LABEL_KEYS' in app_source
    assert 'PAGE_SEQUENCE_TOOLBOX: "v1.common.sequence_tools"' in app_source
    assert "render_sequence_toolbox()" in app_source
    assert "views/SequenceToolbox.py" in runtime_modules
    assert "services/dna_sequence_analysis.py" in runtime_modules
    assert "views/SequenceTools.py" not in runtime_modules
    assert "knowledge page" not in app_source.lower()
    assert "report center" not in app_source.lower()


def test_direct_analysis_has_no_file_side_effects(external_tmp_path: Path) -> None:
    before = tuple(external_tmp_path.iterdir())

    result = toolbox.run_sequence_analysis("ACGTN", SequenceTopology.CIRCULAR)

    assert result.topology is SequenceTopology.CIRCULAR
    assert tuple(external_tmp_path.iterdir()) == before
