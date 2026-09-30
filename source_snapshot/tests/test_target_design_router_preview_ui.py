from __future__ import annotations

import inspect
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.ExpressionConstructs as view
import views.tool_typography as tool_typography


FORBIDDEN_POSITIVE_CLAIMS = [
    "successful " + "import",
    "project " + "imported",
    "ready for " + "execution",
    "experiment" + "-ready",
    "production" + "-ready",
    "validated " + "construct",
    "optimized " + "pathway",
    "yield " + "prediction",
    "recommendation",
    "recommended",
    "optimization",
    "prediction",
    "wet-lab " + "readiness",
    "experimental success",
    "validated " + "design",
    "guaranteed " + "expression",
    "purity",
    "activity",
    "therapeutic " + "success",
]


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _dataframe_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(frame.to_string(index=False) for frame in fake_st.dataframes)


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [str(call["body"]) for call in fake_st.code_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
        + [call["label"] for call in fake_st.text_input_calls]
        + [call["label"] for call in fake_st.expander_calls]
        + fake_st.tab_labels
        + _dataframe_text(fake_st).splitlines()
    )


def _render_preview(monkeypatch, *, target_name: str, target_type: str = "", host_category: str = "", specific_host: str = "", expression_purpose: str = "") -> FakeStreamlit:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.text_input_values["target_design_preview_target_name"] = target_name
    fake_st.selectbox_values["target_design_preview_target_type"] = target_type
    fake_st.selectbox_values["target_design_preview_host_category"] = host_category
    fake_st.text_input_values["target_design_preview_specific_host"] = specific_host
    fake_st.text_input_values["target_design_preview_expression_purpose"] = expression_purpose

    view._render_target_design_preview_panel()
    return fake_st


def test_target_design_preview_panel_renders_boundary_copy(monkeypatch) -> None:
    fake_st = _render_preview(monkeypatch, target_name="GOI", target_type="gene", host_category="plant")
    rendered = _rendered_text(fake_st)

    assert "Target Design Preview" in rendered
    assert "Target Design Route Preview" in rendered
    assert "Target name" in rendered
    assert "Target type" in rendered
    assert "Host category" in rendered
    assert "Specific host" in rendered
    assert "Expression purpose" in rendered
    assert "documentation-only construct draft preview" in rendered.lower()
    assert "manual review" in rendered.lower()
    assert "source confirmation" in rendered.lower()
    assert "does not create records" in rendered.lower()
    assert "not saved as a record" in rendered.lower()
    assert "Scan Target summary first" in rendered
    assert "Boundary note" in rendered
    assert "read-only review aid" in rendered
    assert "source confirmation" in rendered
    assert "manual documentation follow-up" in rendered
    assert "Overview" in rendered
    assert "Draft structure" in rendered
    assert "Review checklist" in rendered


def test_hsa_preview_displays_route_and_slots(monkeypatch) -> None:
    fake_st = _render_preview(
        monkeypatch,
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        expression_purpose="protein expression",
    )
    rendered = _rendered_text(fake_st)

    assert "protein_expression" in rendered
    assert "HSA protein expression construct draft" in rendered
    assert "HSA" in rendered
    assert "HSA cassette draft" in rendered
    assert "Needs source review" in rendered
    assert "manual review label only" in rendered
    assert "documentation-only" in rendered.lower()
    assert "Markdown readback" in rendered
    assert "Target label" in rendered
    assert "Source requirement" in rendered
    assert "Review action" in rendered
    assert "# Target Design Preview" in rendered
    assert len(fake_st.code_calls) == 1
    assert fake_st.code_calls[0]["language"] == "markdown"


def test_artemisinin_preview_displays_gene_and_cassette_slots_without_records(monkeypatch) -> None:
    fake_st = _render_preview(
        monkeypatch,
        target_name="artemisinin precursor",
        target_type="pathway",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
    )
    rendered = _rendered_text(fake_st)

    for gene in ["ADS", "CYP71AV1", "CPR", "ADH1", "DBR2", "ALDH1"]:
        assert gene in rendered
        assert f"{gene} cassette draft" in rendered
    assert "multi_gene_pathway_expression" in rendered
    assert "source required" in rendered
    assert fake_st.form_submit_button_calls == []
    assert fake_st.success_messages == []
    assert fake_st.download_button_calls == []


def test_sugarcane_preview_shows_target_clarification_without_cassette_slots(monkeypatch) -> None:
    fake_st = _render_preview(
        monkeypatch,
        target_name="sugarcane healthy sugar",
        target_type="trait",
        host_category="plant",
        specific_host="sugarcane",
    )
    rendered = _rendered_text(fake_st)
    dataframe_text = _dataframe_text(fake_st)

    assert "trait_or_phenotype" in rendered
    assert "needs_target_clarification" in rendered
    assert "No gene slots are shown because target clarification is required" in rendered
    assert "No cassette slots are available until the route is clarified" in rendered
    assert "remain target-clarification previews" in rendered
    assert "this empty table is not a complete design" in rendered
    assert "sweet protein expression" in rendered
    assert "rare sugar enzyme expression" in rendered
    assert "steviol glycoside pathway" in rendered
    assert "sugar metabolism modification" in rendered
    assert "cassette draft" not in dataframe_text


def test_target_preview_markdown_readback_is_tabbed_and_read_only(monkeypatch) -> None:
    fake_st = _render_preview(monkeypatch, target_name="GOI", target_type="gene", host_category="plant")

    assert ["Overview", "Draft structure", "Review checklist", "Markdown readback"] in fake_st.tab_groups
    assert len(fake_st.code_calls) == 1
    assert fake_st.code_calls[0]["language"] == "markdown"
    assert "# Target Design Preview" in fake_st.code_calls[0]["body"]
    assert "## Boundary" in fake_st.code_calls[0]["body"]
    assert "Read-only Markdown readback for documentation review only" in _rendered_text(fake_st)
    assert "copyable review text" in _rendered_text(fake_st)
    assert "does not change export or package schema" in _rendered_text(fake_st)
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []


def test_target_preview_readability_labels_replace_raw_scan_fields(monkeypatch) -> None:
    fake_st = _render_preview(
        monkeypatch,
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
    )
    dataframe_text = _dataframe_text(fake_st)

    for label in [
        "Target label",
        "Design route",
        "Review status",
        "Template label",
        "Source requirement",
        "Review action",
    ]:
        assert label in dataframe_text

    for raw_label in ["target_label", "source_requirement", "review_action"]:
        assert raw_label not in dataframe_text


def test_target_preview_copy_does_not_include_forbidden_positive_claims(monkeypatch) -> None:
    rendered_samples = [
        _rendered_text(_render_preview(monkeypatch, target_name="GOI", target_type="gene", host_category="plant")),
        _rendered_text(_render_preview(monkeypatch, target_name="HSA", target_type="protein", host_category="plant")),
        _rendered_text(_render_preview(monkeypatch, target_name="artemisinin precursor", target_type="pathway")),
        _rendered_text(_render_preview(monkeypatch, target_name="sugarcane healthy sugar", target_type="trait")),
    ]
    combined = "\n".join(rendered_samples).lower()
    combined = combined.replace("not production, yield, or experimental validation", "")

    assert [phrase for phrase in FORBIDDEN_POSITIVE_CLAIMS if phrase in combined] == []


def test_target_preview_panel_does_not_introduce_database_write_path() -> None:
    source = inspect.getsource(view._render_target_design_preview_panel)

    assert "repo." not in source
    assert "create_construct" not in source
    assert "add_construct" not in source
    assert "update_construct" not in source
    assert "form_submit_button" not in source
    assert "download_button" not in source
