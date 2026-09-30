# -*- coding: utf-8 -*-
"""V2.3-R2 read-only local parts catalog UI tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
from views import PartsRegistryBrowse as view
import views.tool_typography as tool_typography


def _fake_record(*, sequence: str | None = None, part_type: str = "Promoter", display_name: str = "Local catalog promoter", curation_status: str = "metadata reviewed", human_review_status: str = "human review documented") -> dict:
    version = {
        "version_label": "v1-local",
        "sequence": sequence,
        "sequence_hash": "abc123" if sequence else None,
        "sequence_hash_algorithm": "sha256" if sequence else None,
    }
    return {
        "local_id": f"{display_name.lower().replace(' ', '-')}",
        "part_type": part_type,
        "display_name": display_name,
        "version_label": "v1-local",
        "sequence_metadata": "Sequence metadata present" if sequence else "No sequence metadata recorded",
        "source_note_count": 2,
        "linkage_record_count": 0,
        "curation_status": curation_status,
        "human_review_status": human_review_status,
        "part": {},
        "versions": [version],
        "sources": [
            {"source_name": "Local notebook", "provenance_note": "source note one"},
            {"source_name": "Local spreadsheet", "provenance_note": "source note two"},
        ],
        "annotations": [{"annotation_type": "metadata completeness", "annotation_text": "Check source note."}],
        "review_statuses": [
            {
                "curation_status": curation_status,
                "human_review_status": human_review_status,
                "review_note": "Documentation review only.",
            }
        ],
        "linkage_records": [],
    }


def _render_with_records(
    monkeypatch,
    records,
    *,
    show_admin: bool = False,
    search_query: str = "",
    part_type: str = view.PART_TYPE_ALL_LABEL,
    curation_status: str = view.CURATION_STATUS_ALL_LABEL,
):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    monkeypatch.setattr(view, "build_parts_browse_records", lambda: records)
    fake_st.text_input_values["parts_registry_search_query"] = search_query
    fake_st.selectbox_values["parts_registry_part_type_filter"] = part_type
    fake_st.selectbox_values["parts_registry_curation_status_filter"] = curation_status
    view.render_panel(show_admin=show_admin)
    return fake_st


def test_repository_empty_state_ui_uses_documentation_only_copy(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [], show_admin=False)

    combined = "\n".join(fake_st.info_messages + fake_st.caption_messages + fake_st.subheaders)

    assert "No local catalog records are present." in combined
    assert "documentation-only" in combined
    assert "provenance context" in combined
    assert "persistent records are currently 0" in combined.lower()
    assert "failed validation" not in combined.lower()


def test_part_list_rendering_shows_core_browse_columns(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    table = fake_st.dataframes[0]

    assert list(table.columns) == [
        "Part type",
        "Display name",
        "Current/version label",
        "Sequence metadata",
        "Source notes",
        "Traceability links",
        "Curation status",
        "Human review",
    ]
    assert table.iloc[0]["Part type"] == "Promoter"
    assert table.iloc[0]["Display name"] == "Local catalog promoter"
    assert table.iloc[0]["Current/version label"] == "v1-local"
    assert [call["label"] for call in fake_st.selectbox_calls] == ["Part type", "Curation status"]
    assert [call["label"] for call in fake_st.text_input_calls] == ["Search local catalog"]


def test_search_and_filters_narrow_rows(monkeypatch):
    records = [
        _fake_record(sequence="ATGC", display_name="Local catalog promoter", curation_status="metadata reviewed"),
        _fake_record(
            sequence=None,
            part_type="Terminator",
            display_name="Local catalog terminator",
            curation_status="provenance review needed",
            human_review_status="human review needed",
        ),
    ]
    fake_st = _render_with_records(
        monkeypatch,
        records,
        show_admin=False,
        search_query="terminator",
        part_type="Terminator",
        curation_status="provenance review needed",
    )

    table = fake_st.dataframes[0]
    captions = "\n".join(fake_st.caption_messages)

    assert len(table) == 1
    assert table.iloc[0]["Display name"] == "Local catalog terminator"
    assert "Showing 1 of 2 saved registry rows after local browse filters." in captions
    assert "Showing 1 of 2 saved registry rows." in captions


def test_part_type_filter_can_isolate_promoter_rows(monkeypatch):
    records = [
        _fake_record(sequence="ATGC", display_name="Promoter alpha", part_type="Promoter"),
        _fake_record(sequence="ATGC", display_name="Terminator beta", part_type="Terminator"),
    ]
    fake_st = _render_with_records(
        monkeypatch,
        records,
        show_admin=False,
        part_type="Promoter",
    )

    table = fake_st.dataframes[0]

    assert len(table) == 1
    assert table.iloc[0]["Part type"] == "Promoter"
    assert table.iloc[0]["Display name"] == "Promoter alpha"


def test_no_matching_filters_show_clear_empty_state(monkeypatch):
    fake_st = _render_with_records(
        monkeypatch,
        [_fake_record(sequence="ATGC"), _fake_record(sequence=None, part_type="Terminator", display_name="Local catalog terminator")],
        show_admin=False,
        search_query="no-match",
    )

    assert fake_st.info_messages[-1] == "No saved registry rows match the current local catalog search and filter settings."
    assert not fake_st.dataframes


def test_sequence_present_metadata_label(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    table = fake_st.dataframes[0]

    assert table.iloc[0]["Sequence metadata"] == "Sequence metadata present"


def test_no_sequence_metadata_label(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence=None)], show_admin=False)

    table = fake_st.dataframes[0]

    assert table.iloc[0]["Sequence metadata"] == "No sequence metadata recorded"


def test_provenance_source_count_rendering(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    table = fake_st.dataframes[0]
    markdown = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)

    assert table.iloc[0]["Source notes"] == 2
    assert "**Source notes:** 2" in markdown


def test_registry_summary_cards_and_status_copy(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    combined = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])

    assert "Saved registry rows" in combined
    assert "Part type groups" in combined
    assert "Version rows" in combined
    assert "Saved registry rows stay separate from bundled catalog rows" in combined
    assert "Saved registry table rows" in combined
    assert "Showing 1 of 1 saved registry rows." in combined
    assert "Showing 1 of 1 saved registry rows after local browse filters." in combined


def test_empty_linkage_display_is_read_only_documentation_traceability(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    table = fake_st.dataframes[0]
    combined = "\n".join(
        fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    assert table.iloc[0]["Traceability links"] == 0
    assert "**Documentation traceability**" in combined
    assert "Read-only documentation traceability" in combined
    assert "No documentation records in this section." in combined


def test_linkage_display_renders_snapshot_label_and_review_status(monkeypatch):
    record = _fake_record(sequence="ATGC")
    record["linkage_record_count"] = 1
    record["linkage_records"] = [
        {
            "Target type": "pathway_project",
            "Target label snapshot": "Pathway documentation project alpha",
            "Link note": "Human review context for linked documentation record.",
            "Review status": "traceability review needed",
            "Part version context": "v1-local",
            "Created at": "2026-06-12T09:20:00",
            "Updated at": "2026-06-12T09:20:00",
        }
    ]

    fake_st = _render_with_records(monkeypatch, [record], show_admin=False)

    table = fake_st.dataframes[0]
    linkage_table = fake_st.dataframes[-1]

    assert table.iloc[0]["Traceability links"] == 1
    assert linkage_table.iloc[0]["Target label snapshot"] == "Pathway documentation project alpha"
    assert linkage_table.iloc[0]["Review status"] == "traceability review needed"
    assert linkage_table.iloc[0]["Part version context"] == "v1-local"


def test_linkage_display_has_no_edit_create_delete_controls(monkeypatch):
    record = _fake_record(sequence="ATGC")
    record["linkage_record_count"] = 1
    record["linkage_records"] = [
        {
            "Target type": "documentation_snapshot",
            "Target label snapshot": "Documentation snapshot alpha",
            "Link note": "Linked documentation record.",
            "Review status": "traceability reviewed",
            "Part version context": "Part-level link",
            "Created at": "2026-06-12T09:20:00",
            "Updated at": "2026-06-12T09:20:00",
        }
    ]

    fake_st = _render_with_records(monkeypatch, [record], show_admin=False)

    control_labels = [call["label"].lower() for call in fake_st.button_calls]
    markdown = "\n".join(str(call["body"]).lower() for call in fake_st.markdown_calls)

    assert control_labels == []
    assert "create link" not in markdown
    assert "edit link" not in markdown
    assert "delete link" not in markdown


def test_review_and_curation_status_copy(monkeypatch):
    fake_st = _render_with_records(monkeypatch, [_fake_record(sequence="ATGC")], show_admin=False)

    table = fake_st.dataframes[0]
    markdown = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)

    assert table.iloc[0]["Curation status"] == "metadata reviewed"
    assert table.iloc[0]["Human review"] == "human review documented"
    assert "**Curation status:** metadata reviewed" in markdown
    assert "**Human review:** human review documented" in markdown


def test_parts_registry_browse_copy_denylist():
    combined = "\n".join(
        [
            view.EMPTY_STATE_COPY,
            view.BOUNDARY_COPY,
            view.LINKAGE_SECTION_COPY,
        ]
    ).lower()
    forbidden = [
        "recommend" + "ed",
        "approv" + "ed",
        "valid" + "ated",
        "optim" + "al",
        "safe for " + "use",
        "compat" + "ible",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "experimentally " + "confirmed",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
