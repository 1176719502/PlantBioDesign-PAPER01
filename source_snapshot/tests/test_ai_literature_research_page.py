from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.AILiteratureResearch as ai_literature_research


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(ai_literature_research, "st", fake_st)
    return fake_st


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
        + [call["label"] for call in fake_st.text_input_calls]
    )


def test_page_renders_empty_input_without_external_api_keys(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    ai_literature_research.render()
    rendered = _rendered_text(fake_st)

    assert "AI Literature Research" in rendered
    assert "Local deterministic stub" in rendered
    assert "No external AI services" in rendered
    assert "Enter a research target" in rendered
    assert "documentation-only" in rendered
    assert fake_st.text_input_calls


def test_page_renders_albumin_brief(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.text_input_values["ai_literature_research_target"] = "albumin"

    ai_literature_research.render()
    rendered = _rendered_text(fake_st)

    assert "Draft research brief generated for human review" in rendered
    assert "## Research target" in rendered
    assert "## Literature context summary" in rendered
    assert "## Key terms / search keywords" in rendered
    assert "## Source notes placeholder" in rendered
    assert "## Documented biology background" in rendered
    assert "## Uncertainty / human review notes" in rendered
    assert "## Follow-up review questions" in rendered
    assert "## Boundary note: documentation-only, not experimental guidance" in rendered
    assert "No external source lookup was performed" in rendered


def test_page_failure_state_is_bounded(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.text_input_values["ai_literature_research_target"] = "albumin"

    def _raise(_target: str):
        raise RuntimeError("stub source lookup disabled")

    monkeypatch.setattr(ai_literature_research, "generate_literature_research_brief", _raise)

    ai_literature_research.render()
    rendered = _rendered_text(fake_st)

    assert "Literature research source lookup unavailable" in rendered
    assert "stub source lookup disabled" in rendered
    assert "documentation-only" in rendered
