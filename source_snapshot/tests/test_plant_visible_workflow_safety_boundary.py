# -*- coding: utf-8 -*-
from __future__ import annotations

from tests.helpers.fake_streamlit import FakeStreamlit
from tests.test_rice_albumin_workspace_visible_workflow import (
    _rendered_text,
    _rice_albumin_project,
    _rice_albumin_steps,
    _rice_albumin_test_records,
)
from views.pathway_workspace_sections import plant_review_handoff_preview_section as handoff_section
from views.pathway_workspace_sections import plant_review_workflow_section as section


def _term(*parts: str) -> str:
    return "".join(parts)


UNSAFE_VISIBLE_TERMS = (
    _term("optim", "ized"),
    _term("valid", "ated"),
    _term("best"),
    _term("recommend", "ed"),
    _term("ready ", "to build"),
    _term("experiment", "-ready"),
    _term("wet-lab ", "ready"),
    _term("high ", "yield"),
    _term("successful ", "production"),
    _term("proto", "col"),
)


def _allowed_boundary_line(line: str) -> bool:
    allowed_markers = (
        "blocked output",
        "boundary",
        "without",
        "does not",
        "do not",
        "no ",
        "not ",
        "documentation-only",
        "manual review",
        "manual-review",
        "judgment",
        "claim",
    )
    return any(marker in line for marker in allowed_markers)


def test_visible_plant_review_workflow_keeps_unsafe_terms_in_boundary_context(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(handoff_section, "st", fake_st)

    workflow = section.render_plant_review_workflow_section(
        project=_rice_albumin_project(),
        steps=_rice_albumin_steps(),
        expression_links=[],
        test_records=_rice_albumin_test_records(),
        review_signals=[],
    )
    rendered = _rendered_text(fake_st).casefold()

    assert workflow["manual_review_required"] is True
    assert workflow["blocked"] is False
    assert "documentation-only" in rendered
    assert "read-only" in rendered

    unsafe_lines = [
        line
        for line in rendered.splitlines()
        if any(term in line for term in UNSAFE_VISIBLE_TERMS) and not _allowed_boundary_line(line)
    ]
    assert unsafe_lines == []


def test_visible_plant_review_workflow_source_does_not_add_write_or_export_controls() -> None:
    source = section.__file__
    handoff_source = handoff_section.__file__

    for path in (source, handoff_source):
        text = open(path, encoding="utf-8").read().casefold()
        assert "download_button" not in text
        assert "file_uploader" not in text
        assert ".button(" not in text
        assert "add_project" not in text
        assert "update_project" not in text
        assert "delete_project" not in text
