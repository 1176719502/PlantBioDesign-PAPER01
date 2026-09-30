from __future__ import annotations

import ast
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from services.formal_cds_workflow import analyze_formal_cds
from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


class _WidgetColumn:
    def __init__(self, metrics: list[tuple[str, str]]) -> None:
        self._metrics = metrics

    def __enter__(self) -> "_WidgetColumn":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def metric(self, label: str, value: str) -> None:
        self._metrics.append((label, value))


class _UploadedFile:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self._data = text.encode("utf-8")

    def getvalue(self) -> bytes:
        return self._data


class _StreamlitStep2:
    def __init__(self, *, mode: str, raw: str, uploaded: _UploadedFile | None = None) -> None:
        self.mode = mode
        self.raw = raw
        self.uploaded = uploaded
        self.session_state: dict[str, Any] = {}
        self.callbacks: list[Any] = []
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.metrics: list[tuple[str, str]] = []

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def markdown(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def segmented_control(self, *_args: Any, **kwargs: Any) -> str:
        self.callbacks.append(kwargs.get("on_change"))
        return self.mode

    def text_input(self, *_args: Any, **kwargs: Any) -> str:
        self.callbacks.append(kwargs.get("on_change"))
        return ""

    def file_uploader(self, *_args: Any, **kwargs: Any) -> _UploadedFile | None:
        self.callbacks.append(kwargs.get("on_change"))
        return self.uploaded

    def text_area(self, *_args: Any, **kwargs: Any) -> str:
        self.callbacks.append(kwargs.get("on_change"))
        return self.raw

    def checkbox(self, *_args: Any, **kwargs: Any) -> bool:
        self.callbacks.append(kwargs.get("on_change"))
        return False

    def columns(self, count: int) -> list[_WidgetColumn]:
        return [_WidgetColumn(self.metrics) for _ in range(count)]

    def selectbox(self, _label: str, options: Any, **kwargs: Any) -> Any:
        self.callbacks.append(kwargs.get("on_change"))
        return list(options)[0]

    def dataframe(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def expander(self, *_args: Any, **_kwargs: Any) -> "_StreamlitStep2":
        return self

    def __enter__(self) -> "_StreamlitStep2":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def caption(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def code(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def success(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def button(self, *_args: Any, **_kwargs: Any) -> bool:
        return False


class _DesignSession:
    original_seq = ""
    gene_name = ""


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    namespace.setdefault("_t", _zh_t)
    namespace.setdefault("_ui", lambda value: value)
    namespace.setdefault("_CDS_INPUT_MODE_VALUES", ("粘贴核酸序列", "上传单条核酸 FASTA"))
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _render_step2(*, mode: str, raw: str, uploaded: _UploadedFile | None = None) -> tuple[_StreamlitStep2, list[dict[str, Any]]]:
    streamlit = _StreamlitStep2(mode=mode, raw=raw, uploaded=uploaded)
    captured: list[dict[str, Any]] = []
    namespace: dict[str, Any] = {
        "Any": Any,
        "st": streamlit,
        "_invalidate_formal_snapshots": lambda: None,
        "_clear_complete_plasmid_state": lambda: None,
        "_controller": lambda: None,
        "_render_step_navigation": lambda **_kwargs: None,
    }
    render_step2 = _app_functions("_render_step_2_cds", namespace=namespace)["_render_step_2_cds"]
    original_analyze = analyze_formal_cds

    def capture_analysis(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_analyze(*args, **kwargs)
        captured.append(result)
        return result

    with patch("services.formal_cds_workflow.analyze_formal_cds", side_effect=capture_analysis):
        render_step2(_DesignSession())
    return streamlit, captured


def _rule_ids(result: dict[str, Any]) -> set[str]:
    return {str(item["rule_id"]) for item in result["findings"]}


def test_formal_step2_empty_paste_renders_without_nameerror() -> None:
    streamlit, captured = _render_step2(mode="粘贴序列", raw="")

    assert not streamlit.errors
    assert streamlit.infos == ["请输入或上传 CDS 序列以查看分析预览。"]
    assert captured[0]["blocking"]
    assert "empty_cds" in _rule_ids(captured[0])


def test_formal_step2_paste_and_upload_use_the_same_cds_analysis() -> None:
    dna = "atg gct\ntaa"
    fasta = ">single-record\nATGGCTTAA\n"

    _, pasted_dna = _render_step2(mode="粘贴序列", raw=dna)
    _, pasted_fasta = _render_step2(mode="粘贴序列", raw=fasta)
    _, uploaded_fasta = _render_step2(
        mode="上传单条核酸 FASTA",
        raw="",
        uploaded=_UploadedFile("single-record.fasta", fasta),
    )

    assert pasted_dna[0]["normalized_cds"] == "ATGGCTTAA"
    assert pasted_fasta[0]["normalized_cds"] == uploaded_fasta[0]["normalized_cds"]
    assert pasted_fasta[0]["source_format"] == uploaded_fasta[0]["source_format"] == "fasta"
    assert not any(result["blocking"] for result in (pasted_dna[0], pasted_fasta[0], uploaded_fasta[0]))


def test_formal_step2_blocks_multiple_fasta_records_and_invalid_characters() -> None:
    _, multi_record = _render_step2(mode="粘贴序列", raw=">first\nATGGCTTAA\n>second\nATGGCTTAA\n")
    _, invalid = _render_step2(mode="粘贴序列", raw="ATGBCTAA")

    assert multi_record[0]["blocking"]
    assert "multiple_fasta_records" in _rule_ids(multi_record[0])
    assert invalid[0]["blocking"]
    assert "invalid_dna_character" in _rule_ids(invalid[0])


def test_formal_component_input_change_clears_old_cassette_and_plasmid_results() -> None:
    streamlit = _StreamlitStep2(mode="粘贴序列", raw="")
    streamlit.session_state.update(
        {
            "mvp_vector_result": {"old": True},
            "mvp_current_input_signature": "old-inputs",
            "formal_cassette_result": {"old": True},
            "formal_cassette_exports": {"old": True},
        }
    )
    functions = _app_functions(
        "_clear_complete_plasmid_state",
        "_invalidate_formal_snapshots",
        namespace={"Any": Any, "st": streamlit},
    )

    functions["_invalidate_formal_snapshots"]()

    assert "mvp_vector_result" not in streamlit.session_state
    assert "formal_cassette_result" not in streamlit.session_state
    assert "formal_cassette_exports" not in streamlit.session_state
    assert streamlit.session_state["mvp_inputs_stale"] is True


def test_formal_backbone_change_only_clears_complete_plasmid_state() -> None:
    streamlit = _StreamlitStep2(mode="粘贴序列", raw="")
    streamlit.session_state.update(
        {
            "mvp_vector_result": {"old": True},
            "mvp_current_input_signature": "old-construct",
            "mvp_inputs_stale": False,
            "formal_cassette_result": {"current": True},
            "formal_cassette_exports": {"current": True},
            "formal_cassette_input_signature": "current-cassette",
        }
    )
    functions = _app_functions(
        "_invalidate_complete_plasmid_snapshot",
        namespace={"Any": Any, "st": streamlit},
    )

    functions["_invalidate_complete_plasmid_snapshot"]()

    assert "mvp_vector_result" not in streamlit.session_state
    assert "mvp_current_input_signature" not in streamlit.session_state
    assert "mvp_inputs_stale" not in streamlit.session_state
    assert streamlit.session_state["formal_cassette_result"] == {"current": True}
    assert streamlit.session_state["formal_cassette_exports"] == {"current": True}
    assert streamlit.session_state["formal_cassette_input_signature"] == "current-cassette"


def test_formal_step_navigation_does_not_invalidate_snapshots() -> None:
    streamlit = _StreamlitStep2(mode="粘贴序列", raw="")
    insertion = {
        "t_dna_operation_validation": {
            "allowed": True,
            "status": "pcambia1300_exact_insertion_applied",
        }
    }
    streamlit.session_state.update(
        {
            "mvp_vector_result": {"current": True},
            "formal_cassette_result": {
                "current": True,
                "runtime": {"sequence_length": 4},
                "input_signature": "cassette",
            },
            "formal_cassette_exports": {"current": True},
            "formal_project_definition": {"project_name": "P", "plant_host": "Rice"},
            "formal_cds_input": {"normalized_cds": "ATG"},
            "formal_cassette_input_signature": "cassette",
            "formal_step3_order_confirmation_recorded": True,
            "formal_backbone_record": {
                "normalized_sequence": "AAAA",
                "normalized_sequence_sha256": "backbone-sha",
            },
            "formal_insertion_settings": insertion,
        }
    )
    signature_payload = {
        "cassette": "cassette",
        "backbone": "backbone-sha",
        "insertion": insertion,
    }
    streamlit.session_state["formal_ui_step4_confirmation_signature"] = json.dumps(
        signature_payload,
        sort_keys=True,
        default=str,
    )
    saved_steps: list[int] = []

    class _Session:
        step = 4

    class _Controller:
        def get(self) -> _Session:
            return _Session()

        def save(self, session: _Session) -> None:
            saved_steps.append(session.step)

    streamlit.rerun = lambda: None
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "st": streamlit,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "multi_tu",
        "_controller": lambda: _Controller(),
        "_host_supports_project_type": lambda host, _project_type: bool(host),
        "_formal_project_type": lambda: "single_gene",
        "_is_pathway_multi_tu_project": lambda: False,
        "_is_generic_multi_tu_workflow": lambda: False,
        "_is_multi_tu_expression_assembly": lambda _result: False,
        "_formal_ui_signature": lambda value: json.dumps(value, sort_keys=True, default=str),
    }
    functions = _app_functions(
        "_set_formal_step",
        "_formal_step_statuses",
        "_formal_step4_strategy_signature",
        "_normalize_formal_current_step",
        "_formal_step_contract",
        namespace=namespace,
    )
    expected_statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]
    assert functions["_formal_step_statuses"]()[3]["done"] is False

    streamlit.session_state.update(
        formal_step4_strategy_confirmed=True,
        formal_step4_strategy_signature=functions["_formal_step4_strategy_signature"](),
    )
    assert functions["_formal_step_statuses"]() == expected_statuses

    contract_calls: list[list[dict[str, Any]]] = []
    real_contract_builder = functions["_formal_step_contract"]

    def tracked_contract_builder(
        current_step: int,
        *,
        statuses: list[dict[str, bool]] | None = None,
    ) -> list[dict[str, Any]]:
        contract = real_contract_builder(current_step, statuses=statuses)
        contract_calls.append(contract)
        return contract

    namespace["_formal_step_contract"] = tracked_contract_builder

    functions["_set_formal_step"](5)

    assert saved_steps == [5]
    assert streamlit.session_state["mvp_vector_result"] == {"current": True}
    assert streamlit.session_state["formal_cassette_result"] == {
        "current": True,
        "runtime": {"sequence_length": 4},
        "input_signature": "cassette",
    }
    assert streamlit.session_state["formal_cassette_exports"] == {"current": True}
    assert streamlit.session_state["formal_step_preview"] is True
    assert len(contract_calls) == 1
    assert contract_calls[0][4]["state"] == "AVAILABLE"
    assert [key for key in streamlit.session_state if "preview" in key] == ["formal_step_preview"]
