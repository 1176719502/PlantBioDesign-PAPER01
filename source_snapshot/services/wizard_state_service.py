from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from core.session_keys import SK


_STEP2_WIDGET_KEYS = (
    "wf_p2_host",
    "wf_p2_tag",
    "wf_p2_prom",
    "wf_p2_rbs",
    "wf_p2_term",
    "wf_p2_prom_db",
    "wf_p2_rbs_db",
    "wf_p2_term_db",
)


_SYNC_MARKER_KEYS = (
    "_wf_p1_loaded_sync",
    "_wf_p2_loaded_sync",
)


def get_wizard_widget_keys() -> tuple[str, ...]:
    """Return known Expression Wizard widget/cache keys that are safe to reset."""
    return (
        "wf_p1_name",
        "wf_p1_seq",
        "wf_p1_mode",
        *_STEP2_WIDGET_KEYS,
        "wf_p2_use_parts_candidate",
        "wf_p2_dismiss_parts_candidate",
        "wf_back_2",
        "wf_back_3",
        "wf_back_4",
        "wf_back_5",
        "wf_back_6",
        "wf_next_3",
        "wf_next_4",
        "wf_next_5",
        "wf_restart",
        *_SYNC_MARKER_KEYS,
    )


def get_wizard_transient_keys() -> tuple[str, ...]:
    """Return wizard-scoped transient task/cache/bridge keys."""
    return (
        "primer_task_id",
        "primer_task_status",
        "primer_task_result",
        "primer_task_error",
        "primer_task_poll_enabled",
        "primer_task_last_polled_at",
        "primer_task_poll_count",
        "primer_task_progress",
        "primer_task_detail",
        SK.PRIMER_TASK_CONTEXT_SIGNATURE,
        "validation_task_id",
        "validation_task_status",
        "validation_task_result",
        "validation_task_error",
        "validation_task_poll_enabled",
        "validation_task_last_polled_at",
        "validation_task_poll_count",
        "validation_task_progress",
        "validation_task_detail",
        SK.VALIDATION_TASK_CONTEXT_SIGNATURE,
        "wf_plasmid_png",
        "wf_plasmid_fig",
        SK.CODON_STEP3_CANDIDATE_BRIDGE,
        SK.CODON_STEP3_SELECTED_CANDIDATE,
        SK.PARTS_STEP2_CANDIDATE_BRIDGE,
        SK.PARTS_STEP2_SELECTED_CANDIDATE,
        "pathway_link_warning",
        "pathway_project_link_warning",
        "saved_design_pathway_link_warning",
        "wf_pathway_link_warning",
    )


def _pop_known_keys(session_state: MutableMapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    cleared: list[str] = []
    for key in keys:
        if key in session_state:
            session_state.pop(key, None)
            cleared.append(key)
    return cleared


def reset_wizard_transient_state(session_state: MutableMapping[str, Any]) -> dict[str, list[str]]:
    """Clear stale wizard task/cache/bridge state while preserving unrelated state."""
    cleared = _pop_known_keys(session_state, get_wizard_transient_keys())
    return {
        "cleared_keys": cleared,
        "preserved_keys": sorted(k for k in session_state.keys() if k not in cleared),
    }


def hydrate_wizard_widgets_from_design_session(session_state: MutableMapping[str, Any], ds: Any) -> dict[str, list[str]]:
    """Hydrate known wizard widgets from the canonical DesignSession fields."""
    hydrated: list[str] = []

    gene_name = getattr(ds, "gene_name", "") or ""
    original_seq = getattr(ds, "original_seq", "") or ""
    values = {
        "wf_p1_name": gene_name,
        "wf_p1_seq": original_seq,
        "_wf_p1_loaded_sync": (gene_name, original_seq),
    }

    for key, value in values.items():
        session_state[key] = value
        hydrated.append(key)

    elements = getattr(ds, "elements", None)
    elements = elements if isinstance(elements, dict) else {}
    step2_signature = (
        getattr(ds, "host", "") or "",
        getattr(ds, "tag", "") or "",
        elements.get("promoter_name", "") or "",
        elements.get("promoter_seq", "") or "",
        elements.get("rbs_name", "") or "",
        elements.get("rbs_seq", "") or "",
        elements.get("terminator_name", "") or "",
        elements.get("terminator_seq", "") or "",
    )
    session_state["_wf_p2_loaded_sync"] = step2_signature
    hydrated.append("_wf_p2_loaded_sync")

    return {
        "hydrated_keys": hydrated,
        "preserved_keys": sorted(k for k in session_state.keys() if k not in hydrated),
    }


def reset_wizard_for_new_design(session_state: MutableMapping[str, Any]) -> dict[str, list[str]]:
    """Clear wizard widget and transient state for a new design without touching other pages."""
    transient = reset_wizard_transient_state(session_state)
    widget_cleared = _pop_known_keys(session_state, get_wizard_widget_keys())
    cleared = [*transient["cleared_keys"], *widget_cleared]
    return {
        "cleared_keys": cleared,
        "preserved_keys": sorted(k for k in session_state.keys() if k not in cleared),
    }


def prepare_loaded_design_session(session_state: MutableMapping[str, Any], ds: Any) -> dict[str, Any]:
    """Prepare session state after loading a saved DesignSession into the wizard."""
    reset_summary = reset_wizard_transient_state(session_state)
    hydrate_summary = hydrate_wizard_widgets_from_design_session(session_state, ds)
    return {
        "cleared_keys": reset_summary["cleared_keys"],
        "hydrated_keys": hydrate_summary["hydrated_keys"],
        "preserved_keys": sorted(
            k for k in session_state.keys()
            if k not in set(reset_summary["cleared_keys"] + hydrate_summary["hydrated_keys"])
        ),
        "sync_global_context": True,
    }


def sync_global_context_from_design_session(session_state: MutableMapping[str, Any], ds: Any, *, active_name: str | None = None) -> dict[str, list[str]]:
    """Synchronize global active context keys from a DesignSession."""
    frame = getattr(ds, "frame", None)
    frame = frame if isinstance(frame, dict) else {}
    resolved_sequence = frame.get("final_sequence") or getattr(ds, "optimized_seq", "") or getattr(ds, "original_seq", "") or ""
    name = active_name or getattr(ds, "gene_name", "") or "Untitled Project"
    features = frame.get("features", []) if isinstance(frame.get("features", []), list) else []

    values = {
        SK.ACTIVE_HOST: getattr(ds, "host", "") or "",
        SK.ACTIVE_SEQ: resolved_sequence,
        SK.ACTIVE_FEATURES: features,
        SK.ACTIVE_NAME: name,
        SK.SEQ_ORIGINAL: getattr(ds, "original_seq", "") or "",
        SK.PROJECT_NAME: name,
    }
    if resolved_sequence:
        values.update({
            SK.SEQ: resolved_sequence,
            SK.SEQ_DESIGN: resolved_sequence,
            SK.SEQ_CURRENT: resolved_sequence,
        })
    if frame.get("final_sequence"):
        values[SK.SEQ_ASSEMBLED] = frame.get("final_sequence")
        values[SK.SEQ_FINAL] = frame.get("final_sequence")
        values[SK.FEATURES] = features

    for key, value in values.items():
        session_state[key] = value
    return {"synced_keys": sorted(values.keys())}
