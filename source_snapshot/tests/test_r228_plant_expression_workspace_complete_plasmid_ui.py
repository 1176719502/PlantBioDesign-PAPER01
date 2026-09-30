from __future__ import annotations

import sys
from pathlib import Path

from services.canonical_construct_runtime import (
    create_component,
    create_insertion_site,
    create_sequence_asset,
    generate_active_complete_plasmid,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_insertion_site,
    upsert_sequence_asset,
)
from services.plant_project_draft_controller import (
    ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY,
    ACTIVE_PLANT_PROJECT_DRAFT_KEY,
)
from services.plant_project_draft_schema import PlantDesignProjectDraft, update_plant_project_draft
from tests.helpers.fake_streamlit import FakeStreamlit
from views import Plant_Expression_Workspace as expression_page


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _complete_runtime(project_id: str = "plant-draft-r228-ui") -> dict:
    runtime = {"project_id": project_id}
    ordered_ids: list[str] = []
    for component_type, display_name, sequence in (
        ("promoter", "SYNTH_PROMOTER_ALPHA", "TTGACATATAAAGG"),
        ("cds", "SYNTH_CDS_ALPHA", "ATGGCTGAACTGTAA"),
        ("terminator", "SYNTH_TERMINATOR_ALPHA", "GCGTTTTTTGCG"),
    ):
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=display_name,
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
            asset_role="construct_component",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id=project_id,
            component_type=component_type,
            display_name=display_name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        ordered_ids.append(component["component_id"])
    runtime = set_active_component_order(runtime, ordered_ids)
    runtime = generate_active_construct(runtime)

    backbone_text = """LOCUS       SYNTHBONE                 32 bp    DNA     circular UNK 01-JAN-1980
DEFINITION  Synthetic backbone.
ACCESSION   SYNTHBONE
VERSION     SYNTHBONE
KEYWORDS    .
SOURCE      synthetic DNA construct
  ORGANISM  synthetic DNA construct
            other sequences; artificial sequences.
FEATURES             Location/Qualifiers
     rep_origin      1..4
                     /label="ORI_LEFT"
     misc_feature    9..12
                     /label="UPSTREAM_MARKER"
     misc_feature    25..28
                     /label="TAIL_TAG"
ORIGIN
        1 aaaaccccgg ggttttaaaa ccccggggtt tt
//
"""
    backbone = create_sequence_asset(
        project_id=project_id,
        display_name="SYNTH_BACKBONE_ALPHA",
        raw_text=backbone_text,
        molecule_type="dna",
        source_type="upload",
        source_format="genbank",
        asset_role="backbone",
    )
    runtime = upsert_sequence_asset(runtime, backbone)
    site = create_insertion_site(
        project_id=project_id,
        backbone_asset_id=backbone["asset_id"],
        start_coordinate=16,
        end_coordinate=17,
        mode="insertion",
        user_confirmation=True,
    )
    runtime = upsert_insertion_site(runtime, site)
    return generate_active_complete_plasmid(runtime)


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.info_messages
        + fake_st.success_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )


def test_workspace_mounts_backbone_complete_plasmid_controls_and_downloads(monkeypatch) -> None:
    draft = update_plant_project_draft(
        PlantDesignProjectDraft.blank(project_name="R228 UI draft"),
        project_name="R228 UI draft",
        plant_design_goal="Document backbone insertion into a complete plasmid.",
        host_context="Synthetic plant host",
        expression_context="Synthetic expression context",
        canonical_construct_runtime=_complete_runtime(),
    )
    fake_st = FakeStreamlit()
    fake_st.session_state[ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY] = draft.project_id
    fake_st.session_state[ACTIVE_PLANT_PROJECT_DRAFT_KEY] = draft.to_dict()
    monkeypatch.setattr(expression_page, "st", fake_st)
    monkeypatch.setattr(
        expression_page,
        "render_plant_project_draft_persistence_panel",
        lambda: {"active_draft": draft.to_dict(), "persistence_state": "saved"},
    )

    returned = expression_page.render()
    rendered = _rendered_text(fake_st)
    labels = [call["label"] for call in fake_st.download_button_calls]

    assert "complete_plasmid_state" in returned
    assert returned["complete_plasmid_state"]["topology"] == "circular"
    assert any(call["label"] == "Import or update backbone" for call in fake_st.button_calls)
    assert any(call["label"] == "Record insertion site" for call in fake_st.button_calls)
    assert any(call["label"] == "Generate complete plasmid" for call in fake_st.button_calls)
    assert "Export complete plasmid FASTA (.fasta)" in labels
    assert "Export complete plasmid GenBank (.gb)" in labels
    assert "Backbone intake" in rendered
    assert "Complete plasmid output" in rendered
