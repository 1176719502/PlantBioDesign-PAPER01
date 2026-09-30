from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from core.design_session import DesignSession

PATHWAY_WIZARD_CONTEXT_KEY = "pathway_wizard_context"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_gene_sequence(sequence: Any) -> str:
    """Normalize a pathway step gene sequence for Expression Wizard Step 1."""
    return "".join(str(sequence or "").split()).upper()


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _sequence_hash(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest() if sequence else ""


def can_launch_expression_design(step: dict[str, Any] | None) -> bool:
    """Return True when a pathway step has the minimum inputs for Wizard launch."""
    if not isinstance(step, dict):
        return False
    return bool(_clean_text(step.get("gene_name")) and normalize_gene_sequence(step.get("gene_sequence")))


def build_pathway_wizard_context(project: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """Build the small launch context stored outside DesignSession."""
    sequence = normalize_gene_sequence(step.get("gene_sequence"))
    return {
        "source": "pathway_workspace",
        "project_id": _safe_int(project.get("id")),
        "project_name": _clean_text(project.get("name")),
        "step_id": _safe_int(step.get("id")),
        "step_order": _safe_int(step.get("step_order")),
        "step_name": _clean_text(step.get("step_name")),
        "reaction_name": _clean_text(step.get("reaction_name")),
        "gene_name": _clean_text(step.get("gene_name")),
        "gene_sequence_hash": _sequence_hash(sequence),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "status": "active",
    }


def create_design_session_from_pathway_step(step: dict[str, Any]) -> DesignSession:
    """Create a fresh Step 1 Expression Wizard session from a pathway step."""
    return DesignSession(
        step=1,
        gene_name=_clean_text(step.get("gene_name")),
        original_seq=normalize_gene_sequence(step.get("gene_sequence")),
    )


def set_pathway_wizard_context(context: dict[str, Any]) -> None:
    import streamlit as st

    st.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = dict(context or {})


def get_pathway_wizard_context() -> dict[str, Any]:
    import streamlit as st

    context = st.session_state.get(PATHWAY_WIZARD_CONTEXT_KEY)
    return context if isinstance(context, dict) else {}


def clear_pathway_wizard_context() -> None:
    import streamlit as st

    st.session_state.pop(PATHWAY_WIZARD_CONTEXT_KEY, None)


def clear_pathway_context_for_independent_wizard_entry() -> None:
    """Clear pathway launch context before entering the Wizard from non-pathway flows."""
    clear_pathway_wizard_context()


def has_active_pathway_wizard_context() -> bool:
    context = get_pathway_wizard_context()
    return context.get("source") == "pathway_workspace" and context.get("status") == "active"


def _resolve_element_name(ds: DesignSession, part_type: str, name_key: str) -> str:
    elements = ds.elements if isinstance(ds.elements, dict) else {}
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    name = elements.get(name_key) or frame.get(name_key)
    if name:
        return _clean_text(name)

    parts = frame.get("parts") if isinstance(frame.get("parts"), list) else []
    part_type_norm = part_type.lower()
    for part in parts:
        if not isinstance(part, dict):
            continue
        current_type = str(part.get("type") or "").lower()
        if current_type == part_type_norm or (part_type_norm == "rbs" and current_type == "kozak"):
            return _clean_text(part.get("name"))
    return ""


def _hash_text(value: Any) -> str:
    text = str(value or "").strip().upper()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def _primer_risk_status(primers: list[dict[str, Any]]) -> str:
    grades = [str(primer.get("Quality Grade") or "").strip() for primer in primers if isinstance(primer, dict)]
    if any(grade == "Not Recommended" for grade in grades):
        return "not_recommended"
    if any(grade and grade != "Recommended" for grade in grades):
        return "review_required"
    if grades:
        return "recommended"
    return "not_available"


def build_pathway_design_snapshot(
    ds: DesignSession,
    *,
    saved_design_name: str,
    validation_state: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    final_sequence = str(frame.get("final_sequence") or getattr(ds, "final_sequence", "") or "")
    optimized_seq = str(ds.optimized_seq or "")
    return {
        "schema": "pathway_expression_design_snapshot_v1",
        "saved_design_name": _clean_text(saved_design_name),
        "gene_name": _clean_text(ds.gene_name),
        "host": _clean_text(ds.host),
        "selected_elements": {
            "promoter_name": _resolve_element_name(ds, "promoter", "promoter_name"),
            "rbs_or_kozak_name": _resolve_element_name(ds, "rbs", "rbs_name"),
            "terminator_name": _resolve_element_name(ds, "terminator", "terminator_name"),
            "tag": _clean_text(ds.tag),
        },
        "optimized_seq_length_bp": len(optimized_seq),
        "optimized_seq_hash": _hash_text(optimized_seq),
        "expression_frame_length_bp": len(final_sequence) or _safe_int(frame.get("total_length")),
        "expression_frame_hash": _hash_text(final_sequence),
        "primer_count": len(ds.primers or []),
        "validation_status": (validation_state or {}).get("status", "not_available"),
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
        "linked_is_experimental_ready": False,
    }


def build_pathway_validation_summary(
    ds: DesignSession,
    *,
    validation_state: dict[str, Any] | None = None,
    export_recommendation: dict[str, Any] | None = None,
    documentation_only_export: bool = False,
) -> dict[str, Any]:
    state = validation_state or {}
    recommendation = export_recommendation or {}
    issues = [issue for issue in (ds.validation_results or []) if isinstance(issue, dict)]
    blocking_issues = [issue for issue in issues if issue.get("severity") == "critical"]
    validation_warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    export_status = str(recommendation.get("recommendation") or "Not Recommended for Experimental Use")
    not_recommended = export_status == "Not Recommended for Experimental Use"
    return {
        "schema": "pathway_expression_validation_summary_v1",
        "validation_status": state.get("status", "not_available"),
        "validation_is_complete": bool(state.get("is_complete")),
        "validation_is_stale": bool(state.get("is_stale")),
        "validation_warnings": validation_warnings,
        "blocking_issues": blocking_issues,
        "warning_count": int(state.get("warning_count") or len(validation_warnings)),
        "critical_count": int(state.get("critical_count") or len(blocking_issues)),
        "primer_risk_status": _primer_risk_status(ds.primers or []),
        "primer_high_risk_count": int(recommendation.get("primer_high_risk_count") or 0),
        "primer_review_count": int(recommendation.get("primer_review_count") or 0),
        "primer_action_required_count": int(recommendation.get("primer_action_required_count") or 0),
        "affected_fragments": recommendation.get("affected_fragments") or [],
        "export_recommendation": export_status,
        "export_conclusion": recommendation.get("conclusion", ""),
        "recommended_action": recommendation.get("action", ""),
        "documentation_only": bool(documentation_only_export or not_recommended or export_status != "Documentation Export Available"),
        "not_recommended_for_experimental_use": bool(not_recommended),
        "linked_is_experimental_ready": False,
    }


def link_saved_design_to_active_pathway_context(
    ds: DesignSession,
    *,
    saved_design_name: str,
    validation_state: dict[str, Any] | None = None,
    export_recommendation: dict[str, Any] | None = None,
    documentation_only_export: bool = False,
) -> tuple[bool, str, bool]:
    context = get_pathway_wizard_context()
    if not (
        context.get("source") == "pathway_workspace"
        and context.get("status") == "active"
        and _safe_int(context.get("project_id")) > 0
        and _safe_int(context.get("step_id")) > 0
    ):
        return True, "No active pathway context; no pathway link was created.", False

    from services.pathway_repository import link_expression_design_to_step, safe_json_dumps

    created_at = datetime.now().isoformat(timespec="seconds")
    snapshot = build_pathway_design_snapshot(
        ds,
        saved_design_name=saved_design_name,
        validation_state=validation_state,
        created_at=created_at,
    )
    snapshot["pathway_context"] = {
        "project_id": _safe_int(context.get("project_id")),
        "project_name": _clean_text(context.get("project_name")),
        "step_id": _safe_int(context.get("step_id")),
        "step_order": _safe_int(context.get("step_order")),
        "step_name": _clean_text(context.get("step_name")),
        "reaction_name": _clean_text(context.get("reaction_name")),
        "gene_sequence_hash": _clean_text(context.get("gene_sequence_hash")),
        "started_at": _clean_text(context.get("started_at")),
    }
    validation_summary = build_pathway_validation_summary(
        ds,
        validation_state=validation_state,
        export_recommendation=export_recommendation,
        documentation_only_export=documentation_only_export,
    )
    ok, message, _link_id = link_expression_design_to_step(
        project_id=context.get("project_id"),
        step_id=context.get("step_id"),
        design_name=saved_design_name,
        design_snapshot_json=safe_json_dumps(snapshot),
        validation_summary_json=safe_json_dumps(validation_summary),
        design_source="expression_wizard",
    )
    if ok:
        context["status"] = "linked"
        context["linked_design_name"] = _clean_text(saved_design_name)
        context["linked_at"] = created_at
        set_pathway_wizard_context(context)
    return ok, message, True
