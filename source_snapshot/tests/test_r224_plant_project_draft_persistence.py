# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_expression_workspace_prototype_presenter import (
    build_plant_expression_workspace_prototype_presenter,
)
from services.canonical_construct_runtime import (
    create_component,
    create_sequence_asset,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_sequence_asset,
)
from services.plant_project_draft_controller import (
    ACTIVE_PLANT_PROJECT_DRAFT_KEY,
    ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY,
    PlantProjectDraftController,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import (
    PLANT_PROJECT_DRAFT_SCHEMA_VERSION,
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    UnsupportedPlantProjectDraftSchemaError,
    build_plant_project_draft_completeness,
    update_plant_project_draft,
)
from views import Plant_Expression_Workspace as expression_page
from views.pathway_workspace_sections import plant_review_workflow_section as section


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_OUTPUT_FRAGMENTS = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("lab", "-ready"),
    _term("proven ", "construct"),
    _term("validated ", "pathway"),
)


def _repo(tmp_path: Path) -> PlantProjectDraftRepository:
    return PlantProjectDraftRepository(tmp_path / "plant_drafts")


def _filled_draft(name: str = "Duplicate display name") -> PlantDesignProjectDraft:
    draft = PlantDesignProjectDraft.blank(project_name=name)
    return update_plant_project_draft(
        draft,
        plant_design_goal="Document a synthetic placeholder plant protein expression review goal.",
        host_context="Synthetic placeholder host plant context.",
        expression_context="Synthetic placeholder expression context.",
        construct_slot_updates={
            "target_protein": {
                "component_name": "placeholder protein note",
                "source_reference": "user source note",
            },
            "target_gene_or_cds": {
                "component_name": "placeholder CDS note",
                "evidence_reference": "EV-placeholder",
            },
            "host_plant": {"component_name": "placeholder host context"},
            "expression_context": {"component_name": "placeholder expression context"},
            "promoter_or_regulatory_element": {"component_name": "placeholder promoter note"},
            "terminator": {"component_name": "placeholder terminator note"},
            "marker_or_reporter": {"component_name": "placeholder marker note"},
            "vector_or_backbone": {"component_name": "placeholder backbone note"},
        },
        evidence_references=[
            {
                "evidence_id": "EV-placeholder",
                "label": "User evidence placeholder",
                "reference_text": "Manual user-entered provenance note.",
                "record_origin": "user",
            }
        ],
    )


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


def test_blank_draft_has_stable_identity_schema_timestamps_and_required_structure() -> None:
    draft = PlantDesignProjectDraft.blank()
    reloaded = PlantDesignProjectDraft.from_dict(draft.to_dict())

    assert reloaded.project_id == draft.project_id
    assert reloaded.project_name == ""
    assert reloaded.schema_version == PLANT_PROJECT_DRAFT_SCHEMA_VERSION
    assert reloaded.created_at.endswith("Z")
    assert reloaded.updated_at.endswith("Z")
    assert len(reloaded.construct_slots) >= 8
    assert reloaded.evidence_references == []
    assert reloaded.manual_review_state["review_state"] == "review-required"
    assert reloaded.record_origin == "user"


def test_schema_rejects_invalid_payloads_and_unknown_future_versions() -> None:
    with pytest.raises(PlantProjectDraftError):
        PlantDesignProjectDraft.from_dict({"schema_version": PLANT_PROJECT_DRAFT_SCHEMA_VERSION})

    payload = PlantDesignProjectDraft.blank(project_name="Future schema").to_dict()
    payload["schema_version"] = "v99.future"
    with pytest.raises(UnsupportedPlantProjectDraftSchemaError):
        PlantDesignProjectDraft.from_dict(payload)

    payload = PlantDesignProjectDraft.blank(project_name="Example source").to_dict()
    payload["record_origin"] = "example"
    with pytest.raises(PlantProjectDraftError):
        PlantDesignProjectDraft.from_dict(payload)


def test_repository_saves_loads_updates_and_lists_duplicate_names_without_overwrite(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.save(_filled_draft("Duplicate display name"))
    second = repo.save(_filled_draft("Duplicate display name"))

    assert first.project_id != second.project_id
    assert len(repo.list_summaries()) == 2

    loaded_first = repo.load(first.project_id)
    updated_first = update_plant_project_draft(
        loaded_first,
        plant_design_goal="Edited placeholder plant goal after restart.",
        updated_at="2099-01-01T00:00:00Z",
    )
    saved_first = repo.save(updated_first)
    reloaded_first = repo.load(first.project_id)

    assert reloaded_first.project_id == first.project_id
    assert reloaded_first.created_at == first.created_at
    assert reloaded_first.updated_at != first.updated_at
    assert reloaded_first.plant_design_goal == "Edited placeholder plant goal after restart."
    assert repo.load(second.project_id).plant_design_goal != reloaded_first.plant_design_goal
    assert saved_first.project_id == first.project_id


def test_repository_roundtrips_canonical_construct_runtime_payload(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    draft = _filled_draft("R227 runtime persistence")
    runtime = {"project_id": draft.project_id}
    promoter_asset = create_sequence_asset(
        project_id=draft.project_id,
        display_name="Promoter",
        raw_text="TTGACATATAAAGG",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    cds_asset = create_sequence_asset(
        project_id=draft.project_id,
        display_name="CDS",
        raw_text="ATGGCTGAACTGTAA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    terminator_asset = create_sequence_asset(
        project_id=draft.project_id,
        display_name="Terminator",
        raw_text="GCGTTTTTTGCG",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, promoter_asset)
    runtime = upsert_sequence_asset(runtime, cds_asset)
    runtime = upsert_sequence_asset(runtime, terminator_asset)
    promoter_component = create_component(
        project_id=draft.project_id,
        component_type="promoter",
        display_name="Promoter",
        sequence_asset_id=promoter_asset["asset_id"],
    )
    cds_component = create_component(
        project_id=draft.project_id,
        component_type="cds",
        display_name="CDS",
        sequence_asset_id=cds_asset["asset_id"],
    )
    terminator_component = create_component(
        project_id=draft.project_id,
        component_type="terminator",
        display_name="Terminator",
        sequence_asset_id=terminator_asset["asset_id"],
    )
    runtime = upsert_component(runtime, promoter_component)
    runtime = upsert_component(runtime, cds_component)
    runtime = upsert_component(runtime, terminator_component)
    runtime = set_active_component_order(
        runtime,
        [promoter_component["component_id"], cds_component["component_id"], terminator_component["component_id"]],
    )
    runtime = generate_active_construct(runtime)

    saved = repo.save(update_plant_project_draft(draft, canonical_construct_runtime=runtime))
    reloaded = repo.load(saved.project_id)

    assert reloaded.canonical_construct_runtime["sequence_assets"]
    assert reloaded.canonical_construct_runtime["components"]
    assert reloaded.canonical_construct_runtime["transcription_units"][0]["generated_nucleotide_sequence"] == (
        "TTGACATATAAAGGATGGCTGAACTGTAAGCGTTTTTTGCG"
    )


def test_repository_malformed_and_failed_save_fail_safely(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    draft = _filled_draft("Safe write check")
    saved = repo.save(draft)
    original_payload = repo.load(saved.project_id).to_dict()
    (repo.storage_dir / "malformed.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(PlantProjectDraftError):
        repo.load("malformed")

    def _broken_write(_target: Path, _payload: dict[str, Any]) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(repo, "_atomic_write_json", _broken_write)
    changed = update_plant_project_draft(saved, project_name="Name that should not be written")
    with pytest.raises(OSError):
        repo.save(changed)

    clean_repo = _repo(tmp_path)
    assert clean_repo.load(saved.project_id).to_dict() == original_payload


def test_controller_create_save_restart_reopen_continue_editing_and_completeness(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    session_state: dict[str, Any] = {}
    controller = PlantProjectDraftController(session_state=session_state, repository=repo)
    created = controller.create_blank()
    assert created.ok is True
    project_id = created.draft.project_id

    update_result = controller.update_active(
        project_name="R224 local draft",
        plant_design_goal="Document a placeholder plant design goal.",
        host_context="Placeholder host context.",
        expression_context="Placeholder expression context.",
        construct_slot_updates={
            "target_protein": {"component_name": "placeholder protein"},
            "target_gene_or_cds": {"component_name": "placeholder CDS", "evidence_reference": "EV-1"},
        },
        evidence_references=[
            {
                "evidence_id": "EV-1",
                "label": "User evidence",
                "reference_text": "Manual placeholder source note.",
                "record_origin": "user",
            }
        ],
    )
    assert update_result.ok is True
    assert controller.save_active().ok is True

    new_session = {ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY: project_id}
    reopened_controller = PlantProjectDraftController(session_state=new_session, repository=repo)
    reopened = reopened_controller.active_draft()
    assert reopened is not None
    assert reopened.project_id == project_id
    assert reopened.plant_design_goal == "Document a placeholder plant design goal."

    reopened_controller.update_active(plant_design_goal="Continue editing the same placeholder plant design goal.")
    reopened_controller.save_active()
    assert repo.load(project_id).plant_design_goal == "Continue editing the same placeholder plant design goal."

    completeness = reopened_controller.active_completeness()
    assert completeness["completeness_state"] == "incomplete"
    assert "promoter_or_regulatory_element" in completeness["missing_construct_slots"]
    assert "target_protein" in completeness["component_evidence_gaps"]


def test_r223_presenter_consumes_persisted_user_draft_without_fixture_leakage() -> None:
    presenter = build_plant_expression_workspace_prototype_presenter(
        project_draft=_filled_draft("User draft workspace").to_dict(),
        use_default_fixture=False,
    )
    rendered = repr(presenter)

    assert presenter["page_badge"] == "User draft"
    assert presenter["workspace_summary"]["project_name"] == "User draft workspace"
    assert presenter["workspace_summary"]["record_origin"] == "user"
    assert "placeholder protein note" in rendered
    assert "Rice albumin expression review" not in rendered
    assert presenter["empty_state"]["is_empty"] is False


def test_plant_expression_workspace_defaults_to_current_user_draft_and_labels_example_mode(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    draft = _filled_draft("Expression workspace active draft")
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

    assert returned["workspace_summary"]["project_name"] == "Expression workspace active draft"
    assert fake_st.radio_calls[0]["options"] == ["Current user draft", "Example read-only demonstration"]
    assert "Example / Demonstration / Read-only / Not user data." not in rendered

    fake_example = FakeStreamlit()
    fake_example.radio_values["r224_plant_expression_workspace_source_mode"] = "Example read-only demonstration"
    monkeypatch.setattr(expression_page, "st", fake_example)
    returned_example = expression_page.render()
    rendered_example = _rendered_text(fake_example)

    assert returned_example["workspace_summary"]["record_origin"] == "example"
    assert "Example / Demonstration / Read-only / Not user data." in rendered_example


def test_plant_expression_workspace_current_mode_mounts_canonical_runtime_controls(monkeypatch) -> None:
    base_draft = _filled_draft("Runtime workspace draft")
    runtime = {"project_id": base_draft.project_id}
    promoter_asset = create_sequence_asset(
        project_id=base_draft.project_id,
        display_name="Promoter",
        raw_text="TTGACATATAAAGG",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    cds_asset = create_sequence_asset(
        project_id=base_draft.project_id,
        display_name="CDS",
        raw_text="ATGGCTGAACTGTAA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    terminator_asset = create_sequence_asset(
        project_id=base_draft.project_id,
        display_name="Terminator",
        raw_text="GCGTTTTTTGCG",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, promoter_asset)
    runtime = upsert_sequence_asset(runtime, cds_asset)
    runtime = upsert_sequence_asset(runtime, terminator_asset)
    promoter_component = create_component(
        project_id=base_draft.project_id,
        component_type="promoter",
        display_name="Promoter",
        sequence_asset_id=promoter_asset["asset_id"],
    )
    cds_component = create_component(
        project_id=base_draft.project_id,
        component_type="cds",
        display_name="CDS",
        sequence_asset_id=cds_asset["asset_id"],
    )
    terminator_component = create_component(
        project_id=base_draft.project_id,
        component_type="terminator",
        display_name="Terminator",
        sequence_asset_id=terminator_asset["asset_id"],
    )
    runtime = upsert_component(runtime, promoter_component)
    runtime = upsert_component(runtime, cds_component)
    runtime = upsert_component(runtime, terminator_component)
    runtime = set_active_component_order(
        runtime,
        [promoter_component["component_id"], cds_component["component_id"], terminator_component["component_id"]],
    )
    runtime = generate_active_construct(runtime)
    draft = update_plant_project_draft(
        base_draft,
        canonical_construct_runtime=runtime,
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

    assert "runtime_state" in returned
    assert returned["runtime_state"]["sequence_checksum"] == "7babd54d5f11513c180a356232a516966d63f9f4245bf57213c548f8ad890bfe"
    assert any(call["label"] == "Add or update SequenceAsset" for call in fake_st.button_calls)
    assert any(call["label"] == "Add or update Component" for call in fake_st.button_calls)
    assert any(call["label"] == "Generate canonical construct" for call in fake_st.button_calls)
    assert any(call["label"] == "Export canonical FASTA (.fasta)" for call in fake_st.download_button_calls)
    assert any(call["label"] == "Export canonical GenBank (.gb)" for call in fake_st.download_button_calls)


def test_persistence_panel_mounts_create_open_save_editor_and_syncs_r223_session(monkeypatch, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    fake_st = FakeStreamlit()
    fake_st.button_values[f"{section.R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_new"] = True
    monkeypatch.setattr(section, "st", fake_st)

    result = section.render_plant_project_draft_persistence_panel(repository=repo)
    rendered = _rendered_text(fake_st)

    assert result["active_draft"]["project_id"].startswith("plant-draft-")
    assert section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY in fake_st.session_state
    assert "Create blank plant project draft" in [call["label"] for call in fake_st.button_calls]
    assert "Save plant project draft" in [call["label"] for call in fake_st.button_calls]
    assert "Project ID:" in rendered
    assert "documentation-only user data" in rendered


def test_r224_copy_avoids_unsafe_claims() -> None:
    files = (
        ROOT / "services" / "plant_project_draft_schema.py",
        ROOT / "services" / "plant_project_draft_repository.py",
        ROOT / "services" / "plant_project_draft_controller.py",
        ROOT / "services" / "plant_project_draft_r223_adapter.py",
        ROOT / "services" / "plant_expression_workspace_prototype_presenter.py",
        ROOT / "views" / "Plant_Expression_Workspace.py",
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
        ROOT / "tests" / "test_r224_plant_project_draft_persistence.py",
    )
    changed_text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    payload_text = json.dumps(_filled_draft("Copy scan").to_dict(), ensure_ascii=False)
    lowered = f"{changed_text}\n{payload_text}".casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "manual review" in lowered
