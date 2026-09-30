from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from services.formal_cds_workflow import analyze_formal_cds, gene_information_from_values
from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def _app_function(name: str, namespace: dict[str, Any]) -> Any:
    namespace.setdefault("_t", _zh_t)
    namespace.setdefault("_ui", lambda value: value)
    namespace.setdefault("_CDS_INPUT_MODE_VALUES", ("粘贴核酸序列", "上传单条核酸 FASTA"))
    tree = ast.parse(_source())
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace[name]


class _Context:
    def __enter__(self) -> "_Context":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False


class _Upload:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self._content = content.encode("utf-8")

    def getvalue(self) -> bytes:
        return self._content


class _Streamlit:
    def __init__(
        self,
        *,
        raw: str,
        gene_name: str = "TEST_CDS",
        mode: str = "粘贴核酸序列",
        upload: _Upload | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        self.raw = raw
        self.gene_name = gene_name
        self.mode = mode
        self.upload = upload
        self.session_state = state if state is not None else {}
        self.captions: list[str] = []
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.rerun_calls = 0

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def markdown(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def columns(self, spec: int | list[Any] | tuple[Any, ...]) -> list[_Context]:
        count = spec if isinstance(spec, int) else len(spec)
        return [_Context() for _index in range(count)]

    def text_input(self, _label: str, value: str = "", key: str | None = None, **_kwargs: Any) -> str:
        if key == "formal_step2_gene_name":
            return self.gene_name
        if key in self.session_state:
            return str(self.session_state[key])
        return value

    def selectbox(self, _label: str, options: Any, index: int = 0, key: str | None = None, **_kwargs: Any) -> Any:
        values = list(options)
        if key in self.session_state and self.session_state[key] in values:
            return self.session_state[key]
        return values[index]

    def checkbox(self, _label: str, value: bool = False, key: str | None = None, **_kwargs: Any) -> bool:
        return bool(self.session_state.get(key, value))

    def text_area(self, _label: str, value: str = "", key: str | None = None, **_kwargs: Any) -> str:
        if key == "formal_step2_cds_text":
            return self.raw
        return str(self.session_state.get(key, value))

    def segmented_control(self, *_args: Any, **_kwargs: Any) -> str:
        return self.mode

    def file_uploader(self, *_args: Any, **_kwargs: Any) -> _Upload | None:
        return self.upload

    def expander(self, *_args: Any, **_kwargs: Any) -> _Context:
        return _Context()

    def caption(self, message: Any, **_kwargs: Any) -> None:
        self.captions.append(str(message))

    def error(self, message: Any, **_kwargs: Any) -> None:
        self.errors.append(str(message))

    def info(self, message: Any, **_kwargs: Any) -> None:
        self.infos.append(str(message))

    def warning(self, message: Any, **_kwargs: Any) -> None:
        self.warnings.append(str(message))

    def dataframe(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def code(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def rerun(self) -> None:
        self.rerun_calls += 1


class _DesignSession:
    def __init__(self) -> None:
        self.step = 2
        self.original_seq = ""
        self.gene_name = ""
        self.clear_calls = 0

    def clear_step3_outputs(self) -> None:
        self.clear_calls += 1


class _Controller:
    def __init__(self) -> None:
        self.save_calls = 0

    def save(self, _ds: _DesignSession) -> None:
        self.save_calls += 1


def _ui_signature(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _saved_analysis(raw: str = "ATGGCTTAA") -> dict[str, Any]:
    return analyze_formal_cds(
        raw,
        source_kind="paste",
        gene_information=gene_information_from_values(
            gene_name="TEST_CDS",
            source_type="用户自有序列",
            modification_status="未修改的来源序列",
        ),
    )


def _render(
    *,
    raw: str,
    gene_name: str = "TEST_CDS",
    mode: str = "粘贴核酸序列",
    upload: _Upload | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[_Streamlit, _DesignSession, _Controller, list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    streamlit = _Streamlit(raw=raw, gene_name=gene_name, mode=mode, upload=upload, state=state)
    design_session = _DesignSession()
    controller = _Controller()
    navigation_calls: list[dict[str, Any]] = []
    execution_calls: list[dict[str, Any]] = []
    invalidations: list[str] = []

    apply_analysis = _app_function(
        "_apply_formal_cds_analysis",
        {
            "Any": Any,
            "st": streamlit,
            "_controller": lambda: controller,
            "_invalidate_formal_snapshots": lambda: invalidations.append("invalidate"),
        },
    )

    def execute_action(**kwargs: Any) -> tuple[bool, Any, bool]:
        execution_calls.append(dict(kwargs))
        return True, kwargs["action"](), True

    render_step2 = _app_function(
        "_render_step_2_cds",
        {
            "Any": Any,
            "st": streamlit,
            "_is_dual_tu_project": lambda: False,
            "_render_step_navigation": lambda **kwargs: navigation_calls.append(dict(kwargs)),
            "_formal_ui_signature": _ui_signature,
            "_execute_formal_action": execute_action,
            "_apply_formal_cds_analysis": apply_analysis,
            "_controller": lambda: controller,
        },
    )
    render_step2(design_session)
    return streamlit, design_session, controller, navigation_calls, execution_calls, invalidations


def test_step2_has_one_footer_submit_action_and_preserves_existing_keys() -> None:
    step_two = _function_source("_render_step_2_cds")
    tree = ast.parse(step_two)
    direct_buttons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "button"
    ]

    assert direct_buttons == []
    assert "分析序列" not in step_two
    assert "重新分析" not in step_two
    assert step_two.count("_render_step_navigation(") == 1
    assert "next_label=_t('v1.expression.confirm_cds_continue')" in step_two
    assert 'action_id="step2_analyze_continue"' in step_two
    for key in (
        "formal_step2_gene_name",
        "formal_step2_source_type",
        "formal_step2_source_reference",
        "formal_step2_gene_symbol",
        "formal_step2_source_species",
        "formal_step2_modification_status",
        "formal_step2_modification_note",
        "formal_step2_partial_cds",
        "formal_step2_note",
        "formal_step2_mode",
        "formal_step2_upload",
        "formal_step2_cds_text",
    ):
        assert f'key="{key}"' in step_two


def test_valid_preview_is_visible_and_has_no_formal_side_effects() -> None:
    state = {
        "formal_cds_input": _saved_analysis(),
        "formal_cassette_result": {"old": True},
        "mvp_vector_result": {"old": True},
    }
    before = deepcopy(state)

    streamlit, ds, controller, navigation, executions, invalidations = _render(
        raw="ATGGCCGCTTAA",
        state=state,
    )

    assert any("12 bp" in caption and "预览尚未保存" in caption for caption in streamlit.captions)
    assert navigation[0]["next_enabled"] is True
    assert navigation[0]["next_label"] == "确认 CDS 并继续"
    assert state == before
    assert controller.save_calls == 0
    assert ds.step == 2
    assert ds.clear_calls == 0
    assert executions == []
    assert invalidations == []
    assert streamlit.rerun_calls == 0


def test_empty_or_blocking_preview_disables_submit_and_keeps_errors_local() -> None:
    empty = _render(raw="")
    invalid = _render(raw="ATGBCTAA")

    assert empty[0].infos == ["请输入或上传 CDS 序列以查看分析预览。"]
    assert empty[3][0]["next_enabled"] is False
    assert invalid[3][0]["next_enabled"] is False
    assert any("非法字符" in message for message in invalid[0].errors)
    assert invalid[4] == []
    assert invalid[5] == []


def test_submit_reanalyzes_saves_and_advances_through_existing_action_identity() -> None:
    streamlit, ds, controller, navigation, executions, invalidations = _render(
        raw="ATGGCCGCTTAA"
    )

    navigation[0]["next_action"]()

    assert executions[0]["action_id"] == "step2_analyze_continue"
    assert streamlit.session_state["formal_cds_input"]["normalized_cds"] == "ATGGCCGCTTAA"
    assert ds.original_seq == "ATGGCCGCTTAA"
    assert ds.gene_name == "TEST_CDS"
    assert ds.step == 3
    assert controller.save_calls == 2
    assert invalidations == []
    assert streamlit.rerun_calls == 1


def test_modified_cds_invalidates_only_on_submit_and_only_once() -> None:
    state = {
        "formal_cds_input": _saved_analysis(),
        "formal_cassette_result": {"old": True},
        "mvp_vector_result": {"old": True},
    }
    streamlit, ds, _controller, navigation, _executions, invalidations = _render(
        raw="ATGGCCGCTTAA",
        state=state,
    )

    assert invalidations == []
    assert state["formal_cassette_result"] == {"old": True}
    assert state["mvp_vector_result"] == {"old": True}

    navigation[0]["next_action"]()

    assert invalidations == ["invalidate"]
    assert ds.clear_calls == 1
    assert streamlit.session_state["formal_cds_input"]["normalized_cds"] == "ATGGCCGCTTAA"


def test_unchanged_saved_cds_continues_without_downstream_invalidation() -> None:
    saved = _saved_analysis()
    state = {
        "formal_cds_input": deepcopy(saved),
        "formal_cassette_result": {"current": True},
        "mvp_vector_result": {"current": True},
    }
    streamlit, ds, _controller, navigation, _executions, invalidations = _render(
        raw=str(saved["original_text"]),
        state=state,
    )

    assert any("与已保存 CDS 一致" in caption for caption in streamlit.captions)
    navigation[0]["next_action"]()

    assert invalidations == []
    assert ds.clear_calls == 0
    assert state["formal_cassette_result"] == {"current": True}
    assert state["mvp_vector_result"] == {"current": True}
    assert ds.step == 3


def test_uploaded_single_fasta_uses_the_same_automatic_preview_contract() -> None:
    upload = _Upload("test-cds.fasta", ">TEST_CDS\nATGGCTTAA\n")
    streamlit, _ds, controller, navigation, executions, invalidations = _render(
        raw="",
        mode="上传单条核酸 FASTA",
        upload=upload,
    )

    assert any(
        "9 bp" in caption and _zh_t("v1.expression.no_blocking_items") in caption
        for caption in streamlit.captions
    )
    assert navigation[0]["next_enabled"] is True
    assert controller.save_calls == 0
    assert executions == []
    assert invalidations == []


def test_step2_width_mono_and_no_new_page_or_route_contract() -> None:
    source = _source()
    step_two = _function_source("_render_step_2_cds")

    assert ".st-key-formal_step2_cds_text {" in source
    assert "max-width: 960px;" in source
    assert ".st-key-formal_step2_cds_text textarea" in source
    assert "font-family: var(--font-mono) !important;" in source
    assert "min-height: 220px;" in source
    assert "height=230" in step_two
    assert "PAGE_PROJECT_HOME =" in source
    assert "PAGE_DESIGN_WORKSPACE =" in source
    assert "PAGE_RESULTS_EXPORT =" in source
    assert "PAGE_PLANT_LIBRARY =" in source
