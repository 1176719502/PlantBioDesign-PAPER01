# -*- coding: utf-8 -*-
"""V2.4-R4 local parts catalog manual entry UI tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
from views import PartsRegistryBrowse as view


def _record() -> dict:
    return {
        "local_id": "part-local-001",
        "part_type": "Promoter",
        "display_name": "Local catalog promoter",
        "version_label": "v1-local",
        "sequence_metadata": "No sequence metadata recorded",
        "source_note_count": 0,
        "linkage_record_count": 0,
        "curation_status": "metadata incomplete",
        "human_review_status": "human review needed",
        "part": {},
        "versions": [],
        "sources": [],
        "annotations": [],
        "review_statuses": [],
        "linkage_records": [],
    }


def _render(monkeypatch, records=None) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(view, "build_parts_browse_records", lambda: records if records is not None else [_record()])
    monkeypatch.setattr(view.repo, "list_versions_for_part", lambda local_id: [{"id": 7, "version_label": "v1-local"}])
    view.render_admin_section(records if records is not None else [_record()])
    return fake_st


def _capture(monkeypatch, service_name: str, result: dict | None = None) -> list[dict]:
    calls: list[dict] = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return result or {"ok": True, "record": {"id": 1}, "error": ""}

    monkeypatch.setattr(view.write_service, service_name, fake_call)
    return calls


def test_render_admin_section(monkeypatch):
    fake_st = _render(monkeypatch)

    combined = "\n".join(fake_st.subheaders + fake_st.caption_messages)

    assert "Local parts catalog manual entry" in combined
    assert "documentation-only local catalog records" in combined
    assert "Add local catalog documentation records" in [call["label"] for call in fake_st.expander_calls]


def test_create_local_part_form_calls_write_service(monkeypatch):
    calls = _capture(monkeypatch, "create_local_part")
    fake_st = FakeStreamlit()
    fake_st.text_input_values.update(
        {
            "parts_catalog_create_local_id": "part-local-002",
            "parts_catalog_create_display_name": "Local terminator documentation record",
        }
    )
    fake_st.text_area_values["parts_catalog_create_description"] = "Metadata record for local review."
    fake_st.selectbox_values["parts_catalog_create_part_type"] = "Terminator"
    fake_st.form_submit_values["parts_catalog_create_submit"] = True
    monkeypatch.setattr(view, "st", fake_st)

    view.render_admin_section([])

    assert calls == [
        {
            "local_id": "part-local-002",
            "part_type": "Terminator",
            "display_name": "Local terminator documentation record",
            "description": "Metadata record for local review.",
        }
    ]
    assert fake_st.success_messages == ["Local catalog documentation record saved."]


def test_add_version_form(monkeypatch):
    calls = _capture(monkeypatch, "add_part_version")
    fake_st = _render(monkeypatch)
    fake_st.text_input_values.update(
        {
            "parts_catalog_version_label": "v2-local",
            "parts_catalog_version_hash": "abc123",
            "parts_catalog_version_hash_algorithm": "sha256",
        }
    )
    fake_st.text_area_values.update(
        {
            "parts_catalog_version_sequence": "ATGC",
            "parts_catalog_version_note": "Sequence metadata record.",
        }
    )
    fake_st.form_submit_values["parts_catalog_version_submit"] = True
    view.render_admin_section([_record()])

    assert calls[-1] == {
        "part_local_id": "part-local-001",
        "version_label": "v2-local",
        "sequence": "ATGC",
        "sequence_hash": "abc123",
        "sequence_hash_algorithm": "sha256",
        "version_note": "Sequence metadata record.",
    }


def test_add_source_provenance_form(monkeypatch):
    calls = _capture(monkeypatch, "add_part_source")
    fake_st = _render(monkeypatch)
    fake_st.selectbox_values["parts_catalog_source_version"] = "7"
    fake_st.text_input_values.update(
        {
            "parts_catalog_source_name": "Local notebook",
            "parts_catalog_source_reference": "NB-2026-06-12",
        }
    )
    fake_st.text_area_values.update(
        {
            "parts_catalog_source_context": "Local source context.",
            "parts_catalog_source_note": "Provenance note.",
        }
    )
    fake_st.form_submit_values["parts_catalog_source_submit"] = True
    view.render_admin_section([_record()])

    assert calls[-1]["part_local_id"] == "part-local-001"
    assert calls[-1]["part_version_id"] == 7
    assert calls[-1]["source_name"] == "Local notebook"
    assert calls[-1]["provenance_note"] == "Provenance note."


def test_add_annotation_form(monkeypatch):
    calls = _capture(monkeypatch, "add_part_annotation")
    fake_st = _render(monkeypatch)
    fake_st.selectbox_values["parts_catalog_annotation_version"] = "7"
    fake_st.text_input_values["parts_catalog_annotation_type"] = "metadata completeness"
    fake_st.text_area_values["parts_catalog_annotation_text"] = "Check source note."
    fake_st.form_submit_values["parts_catalog_annotation_submit"] = True
    view.render_admin_section([_record()])

    assert calls[-1] == {
        "part_local_id": "part-local-001",
        "part_version_id": 7,
        "annotation_type": "metadata completeness",
        "annotation_text": "Check source note.",
    }


def test_add_review_status_form(monkeypatch):
    calls = _capture(monkeypatch, "add_part_review_status")
    fake_st = _render(monkeypatch)
    fake_st.selectbox_values.update(
        {
            "parts_catalog_review_version": "7",
            "parts_catalog_curation_status": "metadata reviewed",
            "parts_catalog_human_review_status": "human review documented",
        }
    )
    fake_st.text_area_values["parts_catalog_review_note"] = "Documentation review note."
    fake_st.text_input_values.update(
        {
            "parts_catalog_reviewer": "AB",
            "parts_catalog_reviewed_at": "2026-06-12T10:00:00",
        }
    )
    fake_st.form_submit_values["parts_catalog_review_submit"] = True
    view.render_admin_section([_record()])

    assert calls[-1]["curation_status"] == "metadata reviewed"
    assert calls[-1]["human_review_status"] == "human review documented"
    assert calls[-1]["reviewer_name_or_initials"] == "AB"


def test_add_link_form(monkeypatch):
    calls = _capture(monkeypatch, "add_part_link")
    fake_st = _render(monkeypatch)
    fake_st.selectbox_values.update(
        {
            "parts_catalog_link_version": "7",
            "parts_catalog_link_target_type": "pathway_project",
            "parts_catalog_link_review_status": "traceability reviewed",
        }
    )
    fake_st.text_input_values.update(
        {
            "parts_catalog_link_target_id": "pathway-project-001",
            "parts_catalog_link_target_label": "Pathway documentation project",
        }
    )
    fake_st.text_area_values["parts_catalog_link_note"] = "Traceability note."
    fake_st.form_submit_values["parts_catalog_link_submit"] = True
    view.render_admin_section([_record()])

    assert calls[-1] == {
        "part_local_id": "part-local-001",
        "part_version_id": 7,
        "target_type": "pathway_project",
        "target_id": "pathway-project-001",
        "target_label": "Pathway documentation project",
        "link_note": "Traceability note.",
        "review_status": "traceability reviewed",
    }


def test_validation_error_display(monkeypatch):
    _capture(monkeypatch, "create_local_part", {"ok": False, "record": {}, "error": "local_id is required."})
    fake_st = FakeStreamlit()
    fake_st.form_submit_values["parts_catalog_create_submit"] = True
    monkeypatch.setattr(view, "st", fake_st)

    view.render_admin_section([])

    assert fake_st.error_messages == ["local_id is required."]


def test_no_forbidden_copy_terms():
    combined = "\n".join(
        [
            view.EMPTY_STATE_COPY,
            view.BOUNDARY_COPY,
            view.LINKAGE_SECTION_COPY,
            view.ADMIN_BOUNDARY_COPY,
        ]
    ).lower()
    forbidden = [
        "successful " + "import",
        "project " + "imported",
        "ready for " + "execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "wet-lab " + "ready",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_no_delete_import_export_recommendation_controls(monkeypatch):
    fake_st = _render(monkeypatch)
    labels = "\n".join(
        [call["label"] for call in fake_st.form_submit_button_calls]
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
    ).lower()
    forbidden = [
        "delete",
        "remove",
        "import",
        "export",
        "recommend",
        "compatibility",
        "performance",
        "readiness",
    ]

    assert [term for term in forbidden if term in labels] == []
