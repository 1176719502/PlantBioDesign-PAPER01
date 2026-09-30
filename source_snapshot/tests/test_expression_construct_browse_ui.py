# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from core.session_keys import SK
from tests.helpers.fake_streamlit import FakeStreamlit
from services import expression_construct_presenter as presenter
import views.ExpressionConstructs as view
import views.tool_typography as tool_typography


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
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
        + [call["label"] for call in fake_st.selectbox_calls]
    )


def _frame_with_columns(fake_st: FakeStreamlit, columns: list[str]):
    for frame in fake_st.dataframes:
        if list(frame.columns) == columns:
            return frame
    raise AssertionError(f"No dataframe captured with columns: {columns}")


def _frames_with_columns(fake_st: FakeStreamlit, columns: list[str]):
    return [frame for frame in fake_st.dataframes if list(frame.columns) == columns]


def _cassette_slot_preview_frame(fake_st: FakeStreamlit):
    frames = _frames_with_columns(fake_st, view.CASSETTE_SLOT_PREVIEW_COLUMNS)
    if not frames:
        raise AssertionError("No cassette slot preview frames captured")
    return pd.concat(frames, ignore_index=True)


def _sample_view_model() -> dict[str, object]:
    return {
        "summary_counts": {
            "construct_profile_count": 2,
            "cassette_count": 2,
            "cassette_part_count": 3,
            "gene_link_count": 2,
            "pathway_step_link_count": 2,
            "project_link_count": 1,
            "review_gap_count": 1,
        },
        "construct_profile_rows": [
            {
                "construct_id": "construct-001",
                "construct_label": "Carotenoid documentation construct",
                "construct_type": "multi-cassette plasmid record",
                "host_context_note": "Host context tracked as documentation only.",
                "source_reference": "Notebook-EC-12",
                "provenance_note": "Source notes collected for traceability review.",
                "review_status": "documentation review pending",
                "documentation_scope_note": "Documentation-only construct record.",
            },
            {
                "construct_id": "construct-002",
                "construct_label": "Empty documentation construct",
                "construct_type": "reference construct record",
                "host_context_note": "",
                "source_reference": "",
                "provenance_note": "",
                "review_status": "",
                "documentation_scope_note": "",
            },
        ],
        "cassette_rows": [
            {
                "cassette_id": "cassette-001",
                "construct_id": "construct-001",
                "cassette_label": "Cassette A",
                "cassette_role": "expression cassette",
                "cassette_order": 1,
                "promoter_label": "P-Doc-A",
                "gene_label": "crtI",
                "terminator_label": "T-Doc-A",
                "source_reference": "Notebook-1",
                "provenance_note": "Traceability note 1",
            },
            {
                "cassette_id": "cassette-002",
                "construct_id": "construct-001",
                "cassette_label": "Cassette B",
                "cassette_role": "expression cassette",
                "cassette_order": 2,
                "promoter_label": "P-Doc-B",
                "gene_label": "crtB",
                "terminator_label": "T-Doc-B",
                "source_reference": "",
                "provenance_note": "",
            },
        ],
        "cassette_part_rows": [
            {
                "cassette_id": "cassette-001",
                "cassette_label": "Cassette A",
                "part_order": 1,
                "part_role": "promoter",
                "part_label": "P-Doc-A",
                "part_reference": "part-ref-1",
                "source_reference": "source-1",
                "source_catalog": "Plant Promoter Catalog",
                "source_record_id": "plant-promoter-001",
                "source_record_label": "Maize promoter source record",
                "evidence_context_note": "monocot | Zea mays (maize) | root | literature-reported | Fixture source",
                "provenance_note": "note-1",
            },
            {
                "cassette_id": "cassette-001",
                "cassette_label": "Cassette A",
                "part_order": 2,
                "part_role": "cds",
                "part_label": "",
                "part_reference": "part-ref-2",
                "source_reference": "",
                "provenance_note": "",
            },
        ],
        "linked_gene_rows": [
            {
                "construct_id": "construct-001",
                "gene_label": "crtI",
                "gene_reference": "crtI-ref",
                "source_reference": "Pathway notebook",
                "provenance_note": "Linked from project notes.",
            },
            {
                "construct_id": "construct-001",
                "gene_label": "",
                "gene_reference": "",
                "source_reference": "",
                "provenance_note": "",
            },
        ],
        "linked_pathway_step_rows": [
            {
                "construct_id": "construct-001",
                "pathway_step_id": "step-1",
                "pathway_step_label": "Precursor supply",
                "source_reference": "Project map",
                "provenance_note": "Linked from pathway review notes.",
            },
            {
                "construct_id": "construct-001",
                "pathway_step_id": "step-2",
                "pathway_step_label": "",
                "source_reference": "",
                "provenance_note": "",
            },
        ],
        "project_link_rows": [
            {
                "id": 1,
                "project_id": "23",
                "construct_id": "construct-001",
                "construct_label": "Carotenoid documentation construct",
                "link_label": "Project documentation link",
                "link_note": "Project-level construct context.",
                "source_context": "Manual project link",
                "curation_status": "documentation review pending",
                "review_note": "Review note for project linkage.",
            }
        ],
        "construct_component_rows": [
            {
                "component_label": "P-Doc-A",
                "component_category": "promoter",
                "component_reference_label": "Maize promoter source record",
                "sequence_availability_status": presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
                "review_metadata_status": presenter.COMPONENT_METADATA_RECORDED_STATUS,
                "review_note": "note-1",
                "cassette_label": "Cassette A",
            },
            {
                "component_label": presenter.NO_PART_LABEL,
                "component_category": "coding sequence",
                "component_reference_label": "part-ref-2",
                "sequence_availability_status": presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
                "review_metadata_status": presenter.COMPONENT_METADATA_GAP_STATUS,
                "review_note": presenter.NO_PROVENANCE_LABEL,
                "cassette_label": "Cassette A",
            },
        ],
        "construct_component_review_summary": {
            "total_component_rows": 2,
            "rows_with_source_reference_context": 2,
            "rows_missing_source_reference_context": 0,
            "rows_with_sequence_availability_note": 2,
            "rows_with_conservation_review_context": 0,
            "rows_needing_conservation_follow_up": 0,
            "rows_with_review_metadata_status": 2,
            "rows_with_review_note": 1,
            "rows_needing_manual_follow_up": 1,
        },
        "construct_component_gap_queue": [
            {
                "Construct label": "Carotenoid documentation construct",
                "Cassette label": "Cassette A",
                "Component label": presenter.NO_PART_LABEL,
                "Component category": "coding sequence",
                "Issue type": "Missing provenance context",
                "Issue detail": "No provenance or review note is recorded for this component row.",
                "Manual follow-up note": "Add a manual provenance or review note for documentation traceability.",
            }
        ],
        "step2_component_context_readback": {
            "title": presenter.STEP2_CONTEXT_READBACK_TITLE,
            "subtitle": presenter.STEP2_CONTEXT_READBACK_COPY,
            "rows": [],
            "summary": {
                "total_rows": 0,
                "rows_with_recorded_assets": 0,
                "manual_follow_up_rows": 0,
            },
            "empty_state": presenter.STEP2_CONTEXT_EMPTY_STATE,
            "documentation_boundary_note": presenter.STEP2_CONTEXT_BOUNDARY_NOTE,
        },
        "review_gap_rows": [
            {"Gap type": "construct provenance", "Label": "Carotenoid documentation construct", "Review gap note": "Construct profile is missing source reference or provenance note."},
        ],
        "boundary_copy": presenter.BOUNDARY_COPY,
    }


def _sample_promoter_view_model() -> dict[str, object]:
    return {
        "summary_counts": {
            "profile_count": 1,
            "tissue_evidence_count": 1,
            "motif_annotation_count": 0,
            "rows_needing_review_count": 0,
            "source_database_count": 1,
        },
        "profile_rows": [
            {
                "part_id": "plant-promoter-001",
                "display_name": "Maize promoter source record",
            }
        ],
        "evidence_rows": [
            {
                "part_id": "plant-promoter-001",
                "promoter_label": "Maize promoter source record",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
                "tissue_context": "root",
                "evidence_type": "literature-reported",
                "source_database": "Fixture source",
                "curation_status": "source review needed",
                "review_note": "Review note for documentation context.",
            }
        ],
    }


def test_page_renders_boundary_copy_filters_and_tables(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)

    assert "Expression Constructs" in rendered
    assert "documentation-only construct workspace for local draft records" in rendered.lower()
    assert "does not recommend, score, rank, optimize, validate, or predict construct behavior" in rendered
    assert "Create Construct Draft" in rendered
    assert "Edit Construct Metadata" in rendered
    assert "Add Expression Cassette" in rendered
    assert "Add Cassette Part Row" in rendered
    assert "Add Gene Link" in rendered
    assert "Add Pathway Step Link" in rendered
    assert "Add Project Link" in rendered
    assert "Current Construct Preview" in rendered
    assert "Construct component readback" in rendered
    assert "source/reference context, sequence-availability notes, and review gaps" in rendered
    assert "Use the Source/reference context and Record review status columns" in rendered
    assert "Read-only cassette slot preview" in rendered
    assert "existing record readback" in rendered
    assert "source/provenance gaps and manual follow-up stay visible" in rendered
    assert "without changing saved records, package output, sequence assembly, component choice, or workflow behavior" in rendered
    assert "Target and source context" in rendered
    assert "Expression cassette elements" in rendered
    assert "Vector and selection context" in rendered
    assert "Review checks and follow-up" in rendered
    assert "Review the recorded target, source/provenance, and host context" in rendered
    assert "Read-only element readback from existing records" in rendered
    assert "component source/provenance context without part ranking or selection advice" in rendered
    assert "not assessed checks and documentation gaps visible for human review" in rendered
    assert "Step 2 recorded Component Library context" in rendered
    assert "read-only review context from the current expression wizard step 2 component library context presenter" in rendered.lower()
    assert "No Step 2 Component Library context is available for this construct yet" in rendered
    assert "Component documentation follow-up" in rendered
    assert "This cue appears when existing component documentation follow-up rows need easier review on the source page" in rendered
    assert "documentation follow-up type, manual review detail, and manual documentation review note" in rendered
    assert "All follow-up rows" in rendered
    assert "Next documentation step: use the queue below to add or update source/reference" in rendered
    assert "No role-label or duplicate-label documentation follow-up rows are visible" in rendered
    assert "Construct review summary" in rendered
    assert "Component rows reviewed" in rendered
    assert "Source/reference context" in rendered
    assert "Missing source/reference context" in rendered
    assert "Sequence availability note" in rendered
    assert "Record review status" in rendered
    assert "Documentation follow-up" in rendered
    assert "Manual follow-up queue" in rendered
    assert "The Documentation follow-up type column names the review need" in rendered
    assert "human documentation review" in rendered
    assert "Review gaps keep missing source, provenance, source-record, link, and review-note context visible" in rendered
    assert [call["label"] for call in fake_st.selectbox_calls] == [
        "Target type",
        "Host category",
        "Cassette id or selected cassette",
        "Part role",
        "Component Library promoter asset source record",
        "Current construct draft",
        "Construct type",
        "Curation status",
        "Cassette label",
        "Pathway step reference",
    ]
    assert len(fake_st.dataframes) >= 10
    construct_frame = _frame_with_columns(fake_st, view.TABLE_COLUMNS)
    cassette_frame = _frame_with_columns(fake_st, view.CASSETTE_COLUMNS)
    part_frame = _frame_with_columns(fake_st, view.PART_COLUMNS)
    component_frame = _frame_with_columns(fake_st, view.COMPONENT_COLUMNS)
    slot_preview_frame = _cassette_slot_preview_frame(fake_st)
    gap_queue_frame = _frame_with_columns(fake_st, view.COMPONENT_GAP_QUEUE_DISPLAY_COLUMNS)
    gene_frame = _frame_with_columns(fake_st, view.GENE_COLUMNS)
    pathway_frame = _frame_with_columns(fake_st, view.PATHWAY_COLUMNS)
    project_link_frame = _frame_with_columns(fake_st, view.PROJECT_LINK_COLUMNS)
    review_gap_frame = _frame_with_columns(fake_st, view.GAP_COLUMNS)

    assert construct_frame.iloc[0]["Construct label"] == "Carotenoid documentation construct"
    assert cassette_frame.iloc[0]["Cassette label"] == "Cassette A"
    assert part_frame.iloc[0]["Part label"] == "P-Doc-A"
    assert component_frame.iloc[1]["Record review status"] == presenter.COMPONENT_METADATA_GAP_STATUS
    assert component_frame.iloc[1]["Review note"] == presenter.NO_PROVENANCE_LABEL
    assert slot_preview_frame["Slot"].tolist()[:4] == [
        "Target Gene / CDS / Protein",
        "Sequence Source / Provenance",
        "Expression Host",
        "Promoter",
    ]
    assert "CDS / Insert" in slot_preview_frame["Slot"].tolist()
    assert "Vector / Backbone" in slot_preview_frame["Slot"].tolist()
    assert "Gap / Follow-up Review" in slot_preview_frame["Slot"].tolist()
    assert slot_preview_frame[slot_preview_frame["Slot"] == "Promoter"].iloc[0]["Recorded value"] == "P-Doc-A"
    assert (
        slot_preview_frame[slot_preview_frame["Slot"] == "Expression Host"].iloc[0]["Review status"]
        == "documentation review pending"
    )
    assert gap_queue_frame.iloc[0]["Documentation follow-up type"] == "Missing provenance context"
    assert gap_queue_frame.iloc[0]["Manual review detail"] == "No provenance or review note is recorded for this component row."
    assert gap_queue_frame.iloc[0]["Manual documentation review note"] == (
        "Add a manual provenance or review note for documentation traceability."
    )
    assert gene_frame.iloc[0]["Gene label"] == "crtI"
    assert pathway_frame.iloc[0]["Step label"] == "Precursor supply"
    assert project_link_frame.iloc[0]["Project id"] == "23"
    assert review_gap_frame.iloc[0]["Gap type"] == "construct provenance"


def test_cassette_slot_preview_groups_rows_for_read_only_review(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(
        view.repo,
        "list_construct_profiles",
        lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}],
    )
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)
    slot_frames = _frames_with_columns(fake_st, view.CASSETTE_SLOT_PREVIEW_COLUMNS)

    assert [title for title, _keys, _help in view.CASSETTE_SLOT_PREVIEW_GROUPS] == [
        "Target and source context",
        "Expression cassette elements",
        "Vector and selection context",
        "Review checks and follow-up",
    ]
    assert len(slot_frames) == 4
    assert slot_frames[0]["Slot"].tolist() == [
        "Target Gene / CDS / Protein",
        "Sequence Source / Provenance",
        "Expression Host",
    ]
    assert slot_frames[1]["Slot"].tolist() == [
        "Promoter",
        "RBS / Kozak / 5' UTR",
        "Signal Peptide / Secretion Leader",
        "CDS / Insert",
        "Fusion Tag",
        "Linker",
        "Terminator / PolyA",
    ]
    assert slot_frames[2]["Slot"].tolist() == [
        "Selectable Marker / Reporter",
        "Vector / Backbone",
        "Component Source",
    ]
    assert slot_frames[3]["Slot"].tolist() == [
        "Sequence Basic Checks",
        "Gap / Follow-up Review",
    ]
    assert "Read-only cassette slot preview" in rendered
    assert "Documentation-only slot readback" in rendered
    assert "Manual follow-up" in rendered
    assert "documentation gap" in rendered.lower()


def test_page_displays_step2_component_context_readback_without_saved_state_change(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    ds = DesignSession(
        step=2,
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        elements={"promoter_name": "T7 Promoter"},
        frame={"existing": True},
        optimized_seq="ATGGCC",
        primers=[{"name": "p1"}],
        validation_results=[{"status": "old"}],
    )
    original = (
        ds.host,
        ds.tag,
        dict(ds.elements),
        dict(ds.frame),
        ds.optimized_seq,
        list(ds.primers),
        list(ds.validation_results),
    )
    captured_context: dict[str, object] = {}

    def _fake_presenter(**kwargs):
        model = _sample_view_model()
        if "step2_component_context" in kwargs:
            captured_context.update(kwargs["step2_component_context"])
            model["step2_component_context_readback"] = kwargs["step2_component_context"]
        return model

    fake_st.session_state[SK.DESIGN_SESSION] = ds
    monkeypatch.setattr(
        view,
        "_current_step2_component_context_readback",
        lambda: presenter.build_step2_component_context_readback(
            host=ds.host,
            tag=ds.tag,
            rules={
                "kingdom": "prokaryote",
                "promoter": "T7 Promoter",
                "rbs": "Shine-Dalgarno B0034",
                "terminator": "rrnB T1 Terminator",
                "vector_suggestion": "pET documentation context",
            },
            elements=ds.elements,
            records=[
                {
                    "asset_id": "asset-prom",
                    "asset_type": "promoter",
                    "display_name": "T7 promoter source note",
                    "aliases": ["T7 Promoter"],
                    "short_description": "Metadata-only promoter context record.",
                    "organism_or_source_context": "recorded context for documentation review",
                    "sequence_available": True,
                    "source_notes": "Source/provenance review note.",
                    "provenance_status": "source review needed",
                    "version_context": "test seed",
                    "review_status": "record review pending",
                    "tags": [],
                }
            ],
        ),
    )
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", _fake_presenter)
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)
    step2_frame = fake_st.dataframes[-6]

    assert captured_context["title"] == presenter.STEP2_CONTEXT_READBACK_TITLE
    assert "Step 2 recorded Component Library context" in rendered
    assert "source/provenance review" in rendered
    assert "record review status" in rendered
    assert "manual follow-up" in rendered
    assert list(step2_frame.columns) == view.STEP2_COMPONENT_CONTEXT_COLUMNS
    assert "promoter" in step2_frame["Step 2 context category"].tolist()
    promoter_row = step2_frame[step2_frame["Step 2 context category"] == "promoter"].iloc[0]
    assert promoter_row["Step 2 recorded value"] == "T7 Promoter"
    assert promoter_row["Component Library asset"] == "T7 promoter source note / asset-prom"
    assert (ds.host, ds.tag, dict(ds.elements), dict(ds.frame), ds.optimized_seq, list(ds.primers), list(ds.validation_results)) == original


def test_step2_component_context_ui_copy_avoids_claims(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    model = _sample_view_model()
    model["step2_component_context_readback"] = presenter.build_step2_component_context_readback(host="", tag="")
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: model)
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: model["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: model["cassette_rows"])

    view.render()

    combined = _rendered_text(fake_st).lower()
    forbidden = [
        "best host",
        "best promoter",
        "optimized",
        "high-expression",
        "high expression",
        "validated",
        "wet-lab ready",
        "expression improvement",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_empty_state_renders_safe_copy(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [])
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(
        view.presenter,
        "build_expression_construct_presenter",
        lambda **kwargs: {
            "summary_counts": {},
            "construct_profile_rows": [],
            "cassette_rows": [],
            "cassette_part_rows": [],
            "linked_gene_rows": [],
            "linked_pathway_step_rows": [],
            "project_link_rows": [],
            "review_gap_rows": [],
            "draft_defaults": {},
            "empty_states": {},
        },
    )

    view.render()
    rendered = _rendered_text(fake_st)
    slot_preview_frame = _cassette_slot_preview_frame(fake_st)
    source_row = slot_preview_frame[slot_preview_frame["Slot"] == "Sequence Source / Provenance"].iloc[0]
    target_row = slot_preview_frame[slot_preview_frame["Slot"] == "Target Gene / CDS / Protein"].iloc[0]

    assert "No construct drafts are present yet" in rendered
    assert "Read-only cassette slot preview" in rendered
    assert "manual documentation gaps and optional empty slots only" in rendered
    assert source_row["Review status"] == "needs source"
    assert "Manual follow-up" in source_row["Gap / follow-up"]
    assert target_row["Review status"] == "missing"
    assert "record Target Gene / CDS / Protein context" in target_row["Gap / follow-up"]


def test_presenter_output_is_consumed_defensively(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [])
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(
        view.presenter,
        "build_expression_construct_presenter",
        lambda **kwargs: {
            "summary_counts": {"construct_profile_count": "2"},
            "construct_profile_rows": ["bad-row"],
            "cassette_rows": [None, {"cassette_label": "Fallback cassette"}],
            "cassette_part_rows": "not-a-list",
            "linked_gene_rows": None,
            "linked_pathway_step_rows": [],
            "project_link_rows": [],
            "review_gap_rows": [],
            "boundary_copy": presenter.BOUNDARY_COPY,
            "draft_defaults": {},
            "empty_states": {},
        },
    )

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No construct drafts are present yet" in rendered


def test_page_copy_denylist_stays_bounded(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()
    combined = _rendered_text(fake_st).lower()
    forbidden = [
        "best promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "cloning protocol",
        "wet-lab protocol",
        "experimentally confirmed",
        "experimentally validated",
        "expression prediction",
        "yield improvement",
        "yield prediction",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_component_review_action_cue_appears_for_role_and_duplicate_follow_up_rows(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    model = _sample_view_model()
    model["construct_component_gap_queue"] = [
        {
            "Construct label": "Carotenoid documentation construct",
            "Cassette label": "Cassette A",
            "Component label": "Manual component row",
            "Component category": presenter.NO_COMPONENT_CATEGORY_LABEL,
            "Issue type": presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
            "Issue detail": "Component role is missing or recorded as other documented component.",
            "Manual follow-up note": "Manual documentation follow-up: review the component role label.",
        },
        {
            "Construct label": "Carotenoid documentation construct",
            "Cassette label": "Cassette A",
            "Component label": "Shared label",
            "Component category": "multiple documented component categories",
            "Issue type": presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
            "Issue detail": "The same visible component label appears more than once.",
            "Manual follow-up note": "Manual documentation follow-up: review duplicate component labels.",
        },
        {
            "Construct label": "Carotenoid documentation construct",
            "Cassette label": "Cassette A",
            "Component label": "Missing source part",
            "Component category": "terminator",
            "Issue type": "Missing source/reference context",
            "Issue detail": "No source record, component reference, or source note is recorded.",
            "Manual follow-up note": "Add documentation source/reference context.",
        },
    ]
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: model)
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: model["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: model["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)

    assert "Component documentation follow-up" in rendered
    assert "current role-label and duplicate-label documentation rows" in rendered
    assert "The cue does not resolve biological questions or change saved records" in rendered
    assert "Next documentation step: use the queue below to add or update source/reference" in rendered
    assert "Start with rows whose follow-up type mentions missing source/reference context" in rendered
    assert "Use the manual review detail before editing local draft records" in rendered
    assert "Review component role documentation: Manual component row / Cassette A" in rendered
    assert "Review duplicate component label: Shared label / Cassette A" in rendered
    assert "Missing source/reference context: Missing source part" not in rendered
    assert {"label": "Role-label review", "value": "1"} in fake_st.metric_calls or "Role-label review" in rendered
    assert {"label": "Duplicate-label review", "value": "1"} in fake_st.metric_calls or "Duplicate-label review" in rendered


def test_component_review_action_cue_empty_state_stays_safe(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    model = _sample_view_model()
    model["construct_component_gap_queue"] = []
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: model)
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: model["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: model["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)

    assert "Component documentation follow-up" in rendered
    assert "No role-label or duplicate-label documentation follow-up rows are visible" in rendered
    assert "This only describes the current documentation queue; broader manual review may still be needed" in rendered
    assert "No manual documentation follow-up rows are visible for the current construct/cassette filter" in rendered
    assert "Clear filters or review construct metadata" in rendered
    assert "Role-label review" in rendered
    assert "Duplicate-label review" in rendered


def test_component_review_action_cue_copy_stays_documentation_only() -> None:
    combined = "\n".join(
        [
            view.COMPONENT_REVIEW_ACTION_CUE_COPY,
            view.COMPONENT_REVIEW_ACTION_CUE_MANUAL_COPY,
            view.COMPONENT_REVIEW_NEXT_STEP_COPY,
            view.COMPONENT_REVIEW_ACTION_CUE_EMPTY_COPY,
            "\n".join(view.COMPONENT_REVIEW_ACTION_ISSUE_TYPES),
        ]
    ).lower()

    assert "manual action remains" in combined
    assert "documentation" in combined
    assert "documentation follow-up type" in combined
    assert "manual review detail" in combined
    assert "manual documentation review note" in combined
    assert "source/reference" in combined
    assert "does not resolve biological questions or change saved records" in combined
    forbidden = [
        "biological recommendation",
        "compatibility proof",
        "experiment validation",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "wet-lab readiness",
        "ready for " + "execution",
        "experiment-" + "ready",
        "production-" + "ready",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_component_follow_up_queue_display_columns_match_manual_review_cue() -> None:
    frame = view._component_follow_up_queue_frame(
        [
            {
                "Construct label": "Carotenoid documentation construct",
                "Cassette label": "Cassette A",
                "Component label": "Manual component row",
                "Component category": presenter.NO_COMPONENT_CATEGORY_LABEL,
                "Issue type": presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
                "Issue detail": "Component role is missing or recorded as other documented component.",
                "Manual follow-up note": "Manual documentation follow-up: review the component role label.",
            }
        ]
    )

    assert list(frame.columns) == view.COMPONENT_GAP_QUEUE_DISPLAY_COLUMNS
    assert frame.iloc[0]["Documentation follow-up type"] == presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE
    assert frame.iloc[0]["Manual review detail"] == "Component role is missing or recorded as other documented component."
    assert frame.iloc[0]["Manual documentation review note"] == (
        "Manual documentation follow-up: review the component role label."
    )


def test_construct_component_review_summary_treats_placeholder_source_as_missing() -> None:
    component_rows = [
        {
            "Construct label": "Placeholder construct",
            "Cassette label": "Placeholder cassette",
            "Component label": "Placeholder component",
            "Component category": "promoter",
            "sequence_availability_status": "Not specified",
            "review_metadata_status": "N/A",
            "review_note": "TBD",
        }
    ]
    gap_rows = [
        {
            "Construct label": "Placeholder construct",
            "Cassette label": "Placeholder cassette",
            "Component label": "Placeholder component",
            "Component category": "promoter",
            "Issue type": "Missing source/reference context",
        }
    ]

    summary = presenter.build_construct_component_review_summary(component_rows, gap_rows)

    assert summary["rows_with_source_reference_context"] == 0
    assert summary["rows_missing_source_reference_context"] == 1
    assert summary["rows_with_sequence_availability_note"] == 0
    assert summary["rows_with_conservation_review_context"] == 0
    assert summary["rows_needing_conservation_follow_up"] == 0
    assert summary["rows_with_review_metadata_status"] == 0
    assert summary["rows_with_review_note"] == 0
    assert summary["rows_needing_manual_follow_up"] == 1


def test_editable_form_submit_labels_exist(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()

    assert [call["label"] for call in fake_st.form_submit_button_calls] == [
        "Create construct draft",
        "Save construct metadata",
        "Add expression cassette",
        "Add cassette part row",
        "Add gene link",
        "Add pathway step link",
        "Add project link",
    ]


def test_promoter_catalog_empty_state_does_not_block_manual_part_entry(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(
        view.promoter_presenter,
        "build_plant_promoter_catalog_view_model",
        lambda **kwargs: {"profile_rows": [], "evidence_rows": [], "summary_counts": {}},
    )
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No Component Library promoter asset rows are available" in rendered
    assert "Manual promoter rows can be documented without Component Library promoter asset references" in rendered


def test_add_part_form_submits_optional_promoter_catalog_reference(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    captured: dict[str, object] = {}
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    def _capture_part(cassette_id, **kwargs):
        captured["cassette_id"] = cassette_id
        captured.update(kwargs)
        return {"id": 1, **kwargs}

    monkeypatch.setattr(view.repo, "add_construct_cassette_part", _capture_part)
    fake_st.selectbox_values["expression_construct_part_promoter_source"] = (
        "Maize promoter source record / plant-promoter-001"
    )
    fake_st.form_submit_values["expression_construct_add_part_submit"] = True

    view.render()

    assert captured["cassette_id"] == "cassette-001"
    assert captured["source_catalog"] == "Plant Promoter Catalog"
    assert captured["source_record_id"] == "plant-promoter-001"
    assert captured["source_record_label"] == "Maize promoter source record"
    assert "Fixture source" in captured["evidence_context_note"]


def test_add_project_link_form_submits_documentation_reference(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    captured: dict[str, object] = {}
    monkeypatch.setattr(view.presenter, "build_expression_construct_presenter", lambda **kwargs: _sample_view_model())
    monkeypatch.setattr(view.promoter_presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_promoter_view_model())
    monkeypatch.setattr(view.repo, "list_construct_profiles", lambda: [{"construct_id": "construct-001", "construct_label": "Carotenoid documentation construct"}])
    monkeypatch.setattr(view.repo, "get_construct_profile", lambda construct_id: _sample_view_model()["construct_profile_rows"][0])
    monkeypatch.setattr(view.repo, "list_construct_cassettes", lambda construct_id: _sample_view_model()["cassette_rows"])

    def _capture_project_link(**kwargs):
        captured.update(kwargs)
        return {"id": 1, **kwargs}

    monkeypatch.setattr(view.repo, "create_construct_project_link", _capture_project_link)
    fake_st.text_input_values["expression_construct_project_link_project_id"] = "23"
    fake_st.text_input_values["expression_construct_project_link_label"] = "Project 23 construct link"
    fake_st.text_area_values["expression_construct_project_link_note"] = "Documentation linkage note."
    fake_st.form_submit_values["expression_construct_add_project_link_submit"] = True

    view.render()

    assert captured["project_id"] == "23"
    assert captured["construct_id"] == "construct-001"
    assert captured["link_label"] == "Project 23 construct link"
    assert captured["link_note"] == "Documentation linkage note."
    assert "Project-level construct link saved as a documentation reference." in fake_st.success_messages
