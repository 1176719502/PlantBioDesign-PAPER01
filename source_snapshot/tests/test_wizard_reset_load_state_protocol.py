# -*- coding: utf-8 -*-
from pathlib import Path

from core.design_session import DesignSession
from core.session_keys import SK
from services.wizard_state_service import (
    hydrate_wizard_widgets_from_design_session,
    prepare_loaded_design_session,
    reset_wizard_for_new_design,
    reset_wizard_transient_state,
)

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "views" / "Dashboard.py"
DESIGN_SESSION = ROOT / "core" / "design_session.py"
STEP1 = ROOT / "views" / "wizard_steps" / "step1_gene_input.py"
SERVICE = ROOT / "services" / "wizard_state_service.py"
MODIFIED_FILES = [DASHBOARD, DESIGN_SESSION, STEP1, SERVICE]


def _dirty_session_state() -> dict:
    return {
        "primer_task_id": "p-1",
        "primer_task_status": "finished",
        "primer_task_result": {"results": []},
        "primer_task_error": "old",
        "primer_task_poll_count": 4,
        SK.PRIMER_TASK_CONTEXT_SIGNATURE: "old-primer-context",
        "validation_task_id": "v-1",
        "validation_task_status": "finished",
        "validation_task_result": {"issues": []},
        "validation_task_error": "old",
        "validation_task_poll_count": 3,
        SK.VALIDATION_TASK_CONTEXT_SIGNATURE: "old-validation-context",
        "wf_plasmid_png": b"png",
        "wf_plasmid_fig": object(),
        SK.CODON_STEP3_CANDIDATE_BRIDGE: {"candidate": 1},
        SK.CODON_STEP3_SELECTED_CANDIDATE: {"candidate": 1},
        SK.PARTS_STEP2_CANDIDATE_BRIDGE: {"candidate": 2},
        SK.PARTS_STEP2_SELECTED_CANDIDATE: {"candidate": 2},
        "pathway_link_warning": "stale",
        "unrelated_tool_state": "keep",
    }


def test_reset_wizard_transient_state_clears_tasks_cache_bridge_and_preserves_unrelated():
    state = _dirty_session_state()

    summary = reset_wizard_transient_state(state)

    for key in (
        "primer_task_id",
        "primer_task_status",
        "primer_task_result",
        "primer_task_error",
        "primer_task_poll_count",
        SK.PRIMER_TASK_CONTEXT_SIGNATURE,
        "validation_task_id",
        "validation_task_status",
        "validation_task_result",
        "validation_task_error",
        "validation_task_poll_count",
        SK.VALIDATION_TASK_CONTEXT_SIGNATURE,
        "wf_plasmid_png",
        "wf_plasmid_fig",
        SK.CODON_STEP3_CANDIDATE_BRIDGE,
        SK.CODON_STEP3_SELECTED_CANDIDATE,
        SK.PARTS_STEP2_CANDIDATE_BRIDGE,
        SK.PARTS_STEP2_SELECTED_CANDIDATE,
        "pathway_link_warning",
    ):
        assert key not in state
        assert key in summary["cleared_keys"]
    assert state["unrelated_tool_state"] == "keep"


def test_hydrate_wizard_widgets_from_design_session_step1_fields_and_preserves_unrelated():
    state = {"unrelated_tool_state": "keep"}
    ds = DesignSession(gene_name="LoadedGene", original_seq="ATGAAATAA")

    summary = hydrate_wizard_widgets_from_design_session(state, ds)

    assert state["wf_p1_name"] == "LoadedGene"
    assert state["wf_p1_seq"] == "ATGAAATAA"
    assert state["_wf_p1_loaded_sync"] == ("LoadedGene", "ATGAAATAA")
    assert "wf_p1_name" in summary["hydrated_keys"]
    assert "wf_p1_seq" in summary["hydrated_keys"]
    assert state["unrelated_tool_state"] == "keep"


def test_hydrate_wizard_widgets_from_design_session_missing_fields_do_not_raise():
    state = {"unrelated_tool_state": "keep"}

    summary = hydrate_wizard_widgets_from_design_session(state, object())

    assert state["wf_p1_name"] == ""
    assert state["wf_p1_seq"] == ""
    assert summary["hydrated_keys"]
    assert state["unrelated_tool_state"] == "keep"


def test_reset_wizard_for_new_design_clears_widgets_and_transient_not_unrelated():
    state = _dirty_session_state()
    state.update({
        "wf_p1_name": "Old",
        "wf_p1_seq": "ATGOLDTAA",
        "wf_p2_host": "OldHost",
        "saved_design_filter": "keep",
    })

    summary = reset_wizard_for_new_design(state)

    for key in ("wf_p1_name", "wf_p1_seq", "wf_p2_host", "primer_task_id", "validation_task_id"):
        assert key not in state
        assert key in summary["cleared_keys"]
    assert state["unrelated_tool_state"] == "keep"
    assert state["saved_design_filter"] == "keep"


def test_prepare_loaded_design_session_hydrates_and_clears_stale_transient_state():
    state = _dirty_session_state()
    state["wf_p1_name"] = "OldGene"
    state["wf_p1_seq"] = "ATGOLDTAA"
    ds = DesignSession(gene_name="LoadedGene", original_seq="ATGCCCCCTAA")

    summary = prepare_loaded_design_session(state, ds)

    assert state["wf_p1_name"] == "LoadedGene"
    assert state["wf_p1_seq"] == "ATGCCCCCTAA"
    assert "primer_task_result" not in state
    assert "validation_task_result" not in state
    assert SK.PRIMER_TASK_CONTEXT_SIGNATURE not in state
    assert SK.VALIDATION_TASK_CONTEXT_SIGNATURE not in state
    assert "cleared_keys" in summary
    assert "hydrated_keys" in summary
    assert "primer_task_result" in summary["cleared_keys"]
    assert "wf_p1_name" in summary["hydrated_keys"]


def test_static_integration_paths_use_shared_helpers_and_no_disallowed_execution_flags():
    dashboard_text = DASHBOARD.read_text(encoding="utf-8")
    design_session_text = DESIGN_SESSION.read_text(encoding="utf-8")
    step1_text = STEP1.read_text(encoding="utf-8")
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in MODIFIED_FILES)

    assert "prepare_loaded_design_session(st.session_state, result)" in dashboard_text
    assert "sync_global_context_from_design_session(st.session_state, result" in dashboard_text
    assert "reset_wizard_for_new_design(st.session_state)" in dashboard_text
    assert "reset_wizard_for_new_design(st.session_state)" in design_session_text
    assert "hydrate_wizard_widgets_from_design_session(st.session_state, ds)" in step1_text
    assert "st.session_state[\"wf_p1_name\"] = ds.gene_name" not in step1_text
    assert "enable_database_write=True" not in all_text
    assert "execute_project_import_as_new_project" not in all_text


def test_no_misleading_copy_in_modified_files():
    forbidden = [
        "validation success",
        "successful cloning",
        "successful PCR",
        "successful expression",
        "ready for experiment",
        "experiment-ready",
        "production-ready",
        "yield prediction",
        "optimized pathway",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in MODIFIED_FILES)
    for phrase in forbidden:
        assert phrase not in combined
