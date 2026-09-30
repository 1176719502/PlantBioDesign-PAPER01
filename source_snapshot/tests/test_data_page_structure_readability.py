from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.Data as view
import views.tool_typography as tool_typography


def _sample_local_design_catalog() -> dict[str, object]:
    return {
        "metadata": {"seed_name": "Fixture local design asset seed", "seed_version": "v2.6-r170"},
        "records": [
            {
                "asset_id": "asset-001",
                "asset_type": "promoter",
                "display_name": "Promoter asset",
                "aliases": [],
                "short_description": "Documentation-only record.",
                "organism_or_source_context": "local source context",
                "sequence_available": False,
                "sequence_hash": "",
                "sequence_hash_algorithm": "",
                "source_notes": "Local source note.",
                "provenance_status": "source review needed",
                "version_context": "seed v2.6-r170",
                "review_status": "human review needed",
                "human_review_notes": "Documentation review needed.",
                "tags": ["promoter"],
                "documentation_boundary_note": "Documentation-only record.",
            }
        ],
    }


def _sample_parts_df():
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "ID": 1,
                "Name": "Part1",
                "Type": "Promoter",
                "Organism": "Universal",
                "Function Summary": "",
                "Length (bp)": 10,
                "GC Content (%)": 50.0,
                "Description": "",
                "Sequence Preview": "ATGC",
                "Created At": "2026-06-25",
                "Sequence": "ATGC",
            }
        ]
    )


def test_data_render_orders_core_browse_and_collapsed_review_sections(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    monkeypatch.setattr(view, "_load_parts", lambda filter_type=None: _sample_parts_df())
    monkeypatch.setattr(view, "load_local_design_asset_seed_catalog", lambda: _sample_local_design_catalog())
    monkeypatch.setattr(
        view,
        "build_component_library_asset_readback_presenter",
        lambda **kwargs: {
            "rows": [{"Asset label": "A"}],
            "documentation_boundary_note": "Documentation-only Component Library asset readback.",
            "empty_state": "No Component Library asset metadata is available for generic readback.",
            "summary": {
                "total_asset_rows": 1,
                "asset_type_count": 1,
                "rows_with_source_provenance_identity": 1,
                "rows_with_evidence_review_metadata": 1,
            },
            "source_identity_note": "Stored route, source, provenance, package, and saved-record identifiers are preserved.",
            "columns": ["Asset label"],
        },
    )
    monkeypatch.setattr(
        view,
        "build_component_library_contract_crosswalk_presenter",
        lambda records: {
            "summary": {
                "total_components": 1,
                "components_with_source_provenance_context": 1,
                "components_with_evidence_reference_context": 1,
                "components_with_missing_fields": 0,
            },
            "components": [
                {
                    "component_summary": {
                        "component_id": "asset-001",
                        "component_type": "promoter",
                        "component_label": "Promoter asset",
                    },
                    "source_provenance_display_status": "Source/provenance context recorded",
                    "evidence_reference_display_status": "Evidence/reference context recorded",
                    "missing_fields": [],
                    "follow_up_notes": ["Review recorded source/provenance context before documentation reuse."],
                    "required_fields": [
                        {
                            "contract_field": "component_id",
                            "requirement": "required",
                            "display_value": "asset-001",
                            "recorded": True,
                            "display_treatment": "contract field",
                        }
                    ],
                    "optional_fields": [
                        {
                            "contract_field": "source_label",
                            "requirement": "optional",
                            "display_value": "Local Design Asset Catalog",
                            "recorded": True,
                            "display_treatment": "display-only",
                        }
                    ],
                }
            ],
            "field_groups": {
                "required": ["component_id", "component_type", "component_label", "documentation_boundary_note"],
                "optional": ["source_label", "evidence_summary"],
                "deferred": ["created_at"],
                "out_of_scope": ["automatic component choice"],
            },
            "boundary_notes": [
                "Documentation-only Component Library component record.",
                "Review fields are documentation review state only.",
            ],
            "empty_state": "No Component Library component or asset-like records are available for contract crosswalk readback.",
        },
    )
    monkeypatch.setattr(
        view,
        "build_component_library_followup_queue_presenter",
        lambda records: {
            "intro": "Read-only source/provenance follow-up rows.",
            "boundary_note": "Documentation-only follow-up queue.",
            "rows": [
                {
                    "Component label": "Promoter asset",
                    "Component ID": "asset-001",
                    "Component type": "promoter",
                    "Follow-up type": "Needs manual review",
                    "Follow-up detail": "Confirm source citation before citing this design record.",
                    "Manual review": "Needs manual review",
                    "Boundary note": "Documentation-only follow-up queue.",
                }
            ],
            "columns": [
                "Component label",
                "Component ID",
                "Component type",
                "Follow-up type",
                "Follow-up detail",
                "Manual review",
                "Boundary note",
            ],
            "filter_options": {
                "followup_types": ["Needs manual review"],
                "component_types": ["promoter"],
            },
            "filter_empty_state": (
                "No follow-up rows match the current read-only filters. "
                "Adjust the filters to review other existing rows."
            ),
            "summary": {
                "total_followup_rows": 1,
                "components_with_followup": 1,
                "records_with_followup": 1,
                "followup_type_counts": {"Needs manual review": 1},
                "component_type_counts": {"promoter": 1},
                "missing_source_provenance_count": 0,
                "missing_evidence_reference_count": 0,
                "needs_manual_review_count": 1,
                "deferred_field_count": 0,
                "boundary_note_count": 0,
                "summary_rows": [
                    {"Summary group": "Follow-up type", "Group value": "Needs manual review", "Rows": 1},
                    {"Summary group": "Component type", "Group value": "promoter", "Rows": 1},
                ],
            },
            "empty_state": "No Component Library source/provenance follow-up rows are currently flagged.",
        },
    )
    monkeypatch.setattr(view, "_render_documentation_artifact_library", lambda: fake_st.subheaders.append("Saved Documentation Artifacts"))
    monkeypatch.setattr(view, "_render_component_library_slot_browse", lambda records: fake_st.subheaders.append("Component records by plant expression construct context"))
    monkeypatch.setattr(view, "_render_local_design_asset_catalog", lambda: fake_st.subheaders.append("Local Design Asset Catalog"))
    monkeypatch.setattr(view, "render_read_only_parts_catalog", lambda *, show_admin=True: fake_st.subheaders.append(f"Parts Registry show_admin={show_admin}"))
    monkeypatch.setattr(view, "render_plant_promoter_catalog", lambda: fake_st.subheaders.append("Promoter Assets - Plant Domain"))
    monkeypatch.setattr(view, "_render_part_table", lambda *args, **kwargs: None)

    view.render()

    subheaders = fake_st.subheaders
    assert "Component records by plant expression construct context" in subheaders
    assert subheaders.index("Component records by plant expression construct context") < subheaders.index("Core component browsing")
    assert subheaders.index("Core component browsing") < subheaders.index("Parts Registry show_admin=False")
    assert subheaders.index("Parts Registry show_admin=False") < subheaders.index("Local Design Asset Catalog")
    assert subheaders.index("Local Design Asset Catalog") < subheaders.index("Review / source follow-up")
    assert subheaders.index("Review / source follow-up") < subheaders.index("Promoter Assets - Plant Domain")
    expander_labels = [call["label"] for call in fake_st.expander_calls]
    assert "Plant component source/provenance review details" in expander_labels
    assert "Manual follow-up guidance" in expander_labels
    assert "Plant promoter asset context" in expander_labels
    assert "Computed Component Library readback rows" in expander_labels
    assert "Saved documentation artifacts" in expander_labels
    assert "Registry admin and write controls" in expander_labels
    assert "Parts Registry boundary" in expander_labels
    assert "Legacy registry type counts" in expander_labels
    assert "Component contract crosswalk readback" in subheaders
    assert "Source/provenance follow-up queue" in subheaders
    default_collapsed = {
        "Plant promoter asset context",
        "Plant component source/provenance review details",
        "Manual follow-up guidance",
        "Computed Component Library readback rows",
        "Saved documentation artifacts",
        "Registry admin and write controls",
        "Parts Registry boundary",
        "Legacy registry type counts",
    }
    expanded_by_label = {
        call["label"]: call.get("expanded")
        for call in fake_st.expander_calls
        if call["label"] in default_collapsed
    }
    assert expanded_by_label == {label: False for label in default_collapsed}
    assert "Promoter" in fake_st.tab_labels
    page_text = "\n".join(
        fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )
    assert "Plant component/source/provenance review" in page_text
    assert "Plant recombinant protein / molecular farming" in page_text
    assert "Contract crosswalk readback reuses existing Component Library records" in page_text
    assert "Component summary:** Promoter asset (promoter)" in page_text
    assert "Source/provenance: Source/provenance context recorded" in page_text
    assert "Evidence/reference: Evidence/reference context recorded" in page_text
    assert "Follow-up summary grouping" in page_text
    assert "Read-only queue filters" in page_text
    assert "Filtered follow-up rows: 1 of 1" in page_text
    assert "Detailed read-only queue rows preserve the existing R359 follow-up table." in page_text
    assert "Find components by workflow slot" in page_text
    assert "Available workflow slot groups" in page_text
    assert "First-screen filters" in page_text
    assert "Filtered record cards" in page_text
    selectbox_labels = [call["label"] for call in fake_st.selectbox_calls]
    assert "Slot" in selectbox_labels
    assert "Source/provenance" in selectbox_labels
    assert "Follow-up" in selectbox_labels
    multiselect_labels = [call["label"] for call in fake_st.multiselect_calls]
    assert "Follow-up type" in multiselect_labels
    assert "Component type" in multiselect_labels
    assert any(
        call["key"] == "component_library_followup_type_filter"
        and call["options"] == ["Needs manual review"]
        and call["default"] == []
        for call in fake_st.multiselect_calls
    )
    assert any(
        call["key"] == "component_library_followup_component_type_filter"
        and call["options"] == ["promoter"]
        and call["default"] == []
        for call in fake_st.multiselect_calls
    )
    assert fake_st.dataframes
    assert "Slot" in fake_st.dataframes[0].columns
    assert "Component label" in fake_st.dataframes[0].columns
    assert "Promoter asset" in set(fake_st.dataframes[0]["Component label"])
    assert any("Plant component category" in frame.columns for frame in fake_st.dataframes)
    assert any(
        "Plant promoter context" in set(frame["Plant component category"])
        for frame in fake_st.dataframes
        if "Plant component category" in frame.columns
    )
    assert any("Field group" in frame.columns for frame in fake_st.dataframes)
    assert any("Contract field" in frame.columns for frame in fake_st.dataframes)
    assert any("Summary group" in frame.columns for frame in fake_st.dataframes)
    assert any("Follow-up type" in set(frame.get("Summary group", [])) for frame in fake_st.dataframes if "Summary group" in frame.columns)
    for phrase in (
        " ".join(("successful", "import")),
        " ".join(("project", "imported")),
        " ".join(("ready", "for", "execution")),
        "-".join(("experiment", "ready")),
        "-".join(("production", "ready")),
        " ".join(("validated", "construct")),
        " ".join(("optimized", "pathway")),
        " ".join(("yield", "prediction")),
        "-".join(("build", "ready")),
        " ".join(("wet-lab", "ready")),
    ):
        assert phrase not in page_text.casefold()


def test_local_design_asset_selected_detail_is_default_collapsed(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    monkeypatch.setattr(view, "load_local_design_asset_seed_catalog", lambda: _sample_local_design_catalog())

    view._render_local_design_asset_catalog()

    assert fake_st.dataframes
    assert any(
        call["label"] == "Documentation-only candidate record for review"
        for call in fake_st.selectbox_calls
    )
    expanded_by_label = {
        call["label"]: call.get("expanded")
        for call in fake_st.expander_calls
    }
    assert expanded_by_label["Selected asset documentation details"] is False
    assert "documentation-only source/provenance review context for the selected row" in "\n".join(
        fake_st.caption_messages
    )


def test_component_library_slot_browse_renders_filter_and_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    view._render_component_library_slot_browse([])

    assert "Component records by plant expression construct context" in fake_st.subheaders
    assert any(
        call["label"] == "What do these terms mean?" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    empty_glossary_text = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])
    assert "Expression vector slot" in empty_glossary_text
    assert "a place in the planned expression vector record" in empty_glossary_text
    assert "Component record" in empty_glossary_text
    assert "Source/provenance" in empty_glossary_text
    assert "Manual follow-up" in empty_glossary_text
    assert "CDS / Insert" in empty_glossary_text
    assert "Vector / Backbone" in empty_glossary_text
    assert "Terminator / PolyA" in empty_glossary_text
    assert "does not select components or validate the design" in empty_glossary_text
    assert any("No component records are available yet" in message for message in fake_st.info_messages)
    assert any("No slot detail is shown until existing Component Library records are available" in message for message in fake_st.caption_messages)

    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    view._render_component_library_slot_browse(_sample_local_design_catalog()["records"])

    assert any(
        call["label"] == "Plant expression construct context filter"
        for call in fake_st.selectbox_calls
    )
    assert any(
        call["label"] == "What do these terms mean?" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    assert fake_st.dataframes
    rendered_frame = fake_st.dataframes[-1]
    assert "Source/provenance status" in rendered_frame.columns
    assert "Manual follow-up" in rendered_frame.columns
    assert any(
        call["label"] == "Compact slot details for narrow screens" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    assert any(
        call["label"] == "Advanced component evidence readback" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    compact_text = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "**Plant promoter context**" in compact_text
    assert "Records: 1 | Promoter asset" in compact_text
    assert "Source/provenance: Source/provenance missing - manual follow-up needed." in compact_text
    assert "Manual follow-up: Manual follow-up needed." in compact_text
    compact_captions = "\n".join(fake_st.caption_messages)
    assert "Compact readback repeats the table's key review fields for narrow screens" in compact_captions
    glossary_and_compact_text = f"{compact_text}\n{compact_captions}".casefold()
    assert "this section helps you review records and missing source information" in glossary_and_compact_text
    assert "does not select components or validate the design" in glossary_and_compact_text
    for phrase in (
        "best promoter",
        "best host",
        "best vector",
        "optimized sequence",
        " ".join(("validated", "construct")),
        "ready-to-clone",
        "-".join(("build", "ready")),
        " ".join(("yield", "prediction")),
        "wet-lab protocol",
    ):
        assert phrase not in glossary_and_compact_text


def test_component_contract_crosswalk_readback_preserves_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    view._render_component_library_contract_crosswalk_readback([])

    assert "Component contract crosswalk readback" in fake_st.subheaders
    assert any(
        "No Component Library component or asset-like records are available for contract crosswalk readback" in message
        for message in fake_st.info_messages
    )
    rendered_text = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])
    assert "read-only review context" in rendered_text.casefold()
    assert "does not create or persist component records" in rendered_text.casefold()


def test_component_library_followup_queue_filters_detail_rows_without_changing_summary(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.multiselect_values["component_library_followup_type_filter"] = ["Boundary note"]
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    monkeypatch.setattr(
        view,
        "build_component_library_followup_queue_presenter",
        lambda records: {
            "intro": "Read-only source/provenance follow-up rows.",
            "boundary_note": "Documentation-only follow-up queue.",
            "rows": [
                {
                    "Component label": "Promoter asset",
                    "Component ID": "asset-001",
                    "Component type": "promoter",
                    "Follow-up type": "Needs manual review",
                    "Follow-up detail": "Confirm source citation before citing this design record.",
                    "Manual review": "Needs manual review",
                    "Boundary note": "Documentation-only follow-up queue.",
                },
                {
                    "Component label": "Promoter asset",
                    "Component ID": "asset-001",
                    "Component type": "promoter",
                    "Follow-up type": "Boundary note",
                    "Follow-up detail": "Documentation-only Component Library component record.",
                    "Manual review": "Needs manual review",
                    "Boundary note": "Documentation-only follow-up queue.",
                },
            ],
            "columns": [
                "Component label",
                "Component ID",
                "Component type",
                "Follow-up type",
                "Follow-up detail",
                "Manual review",
                "Boundary note",
            ],
            "filter_options": {
                "followup_types": ["Boundary note", "Needs manual review"],
                "component_types": ["promoter"],
            },
            "filter_empty_state": (
                "No follow-up rows match the current read-only filters. "
                "Adjust the filters to review other existing rows."
            ),
            "summary": {
                "total_followup_rows": 2,
                "components_with_followup": 1,
                "records_with_followup": 1,
                "missing_source_provenance_count": 0,
                "missing_evidence_reference_count": 0,
                "needs_manual_review_count": 1,
                "deferred_field_count": 0,
                "boundary_note_count": 1,
                "summary_rows": [
                    {"Summary group": "Follow-up type", "Group value": "Boundary note", "Rows": 1},
                    {"Summary group": "Follow-up type", "Group value": "Needs manual review", "Rows": 1},
                ],
            },
            "empty_state": "No Component Library source/provenance follow-up rows are currently flagged.",
        },
    )

    view._render_component_library_followup_queue([])

    assert any("Filtered follow-up rows: 1 of 2" in message for message in fake_st.caption_messages)
    assert any(
        "Follow-up type" in frame.columns and set(frame["Follow-up type"]) == {"Boundary note"}
        for frame in fake_st.dataframes
    )
    assert any(
        "Summary group" in frame.columns and set(frame["Group value"]) == {"Boundary note", "Needs manual review"}
        for frame in fake_st.dataframes
    )


def test_component_library_followup_queue_shows_safe_filtered_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.multiselect_values["component_library_followup_component_type_filter"] = ["terminator"]
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    monkeypatch.setattr(
        view,
        "build_component_library_followup_queue_presenter",
        lambda records: {
            "intro": "Read-only source/provenance follow-up rows.",
            "boundary_note": "Documentation-only follow-up queue.",
            "rows": [
                {
                    "Component label": "Promoter asset",
                    "Component ID": "asset-001",
                    "Component type": "promoter",
                    "Follow-up type": "Needs manual review",
                    "Follow-up detail": "Confirm source citation before citing this design record.",
                    "Manual review": "Needs manual review",
                    "Boundary note": "Documentation-only follow-up queue.",
                }
            ],
            "columns": [
                "Component label",
                "Component ID",
                "Component type",
                "Follow-up type",
                "Follow-up detail",
                "Manual review",
                "Boundary note",
            ],
            "filter_options": {
                "followup_types": ["Needs manual review"],
                "component_types": ["promoter", "terminator"],
            },
            "filter_empty_state": (
                "No follow-up rows match the current read-only filters. "
                "Adjust the filters to review other existing rows."
            ),
            "summary": {
                "total_followup_rows": 1,
                "components_with_followup": 1,
                "records_with_followup": 1,
                "missing_source_provenance_count": 0,
                "missing_evidence_reference_count": 0,
                "needs_manual_review_count": 1,
                "deferred_field_count": 0,
                "boundary_note_count": 0,
                "summary_rows": [
                    {"Summary group": "Follow-up type", "Group value": "Needs manual review", "Rows": 1},
                ],
            },
            "empty_state": "No Component Library source/provenance follow-up rows are currently flagged.",
        },
    )

    view._render_component_library_followup_queue([])

    assert any("Filtered follow-up rows: 0 of 1" in message for message in fake_st.caption_messages)
    assert any(
        "No follow-up rows match the current read-only filters" in message
        for message in fake_st.info_messages
    )
    assert not any(
        "Follow-up type" in frame.columns and set(frame["Follow-up type"]) == {"Needs manual review"}
        for frame in fake_st.dataframes
    )
