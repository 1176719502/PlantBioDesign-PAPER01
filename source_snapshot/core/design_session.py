# -*- coding: utf-8 -*-
"""
core/design_session.py
~~~~~~~~~~~~~~~~~~~~~~
Centralised data hub for the Expression Wizard 6-step pipeline.

DesignSession
-------------
  Immutable-style dataclass that holds every artefact produced by the wizard.
  All fields have safe defaults so callers can inspect partial state at any
  step without AttributeError.

SessionController
-----------------
  Thin adapter that reads / writes DesignSession instances into
  st.session_state under a single key ('design_session'), providing:
    • get()        — retrieve current session (creates blank if missing)
    • save()       — persist a DesignSession back to session state
    • reset()      — wipe the session and restart from step 1
    • step         — property: current wizard step (1-6)
    • advance()    — move to next step
    • retreat()    — move to previous step
    • can_advance  — True only when the current step's output is valid

Step gate rules (can_advance)
-----------------------------
  Step 1 → 2  : original_seq must be ≥ 30 bp
  Step 2 → 3  : host must be non-empty string
  Step 3 → 4  : frame_ok must be True (build_expression_frame succeeded)
  Step 4 → 5  : primers list must be non-empty
  Step 5 → 6  : validation_results list must be non-empty
  Step 6      : always True (export step, no further steps)

No Streamlit imports at module level — only inside SessionController methods
so this module can be unit-tested without a running Streamlit server.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.session_keys import SK
from services.sequence_inspector import WIZARD_MINIMUM_SEQUENCE_LENGTH


def _sha256_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# DesignSession
# ---------------------------------------------------------------------------

@dataclass
class DesignSession:
    """Single source of truth for one wizard run.

    Fields
    ------
    step : int
        Current wizard page index (1-6).
    gene_name : str
        User-supplied gene / construct name.
    original_seq : str
        Raw CDS sequence submitted in Step 1 (uppercase, no whitespace).
    optimized_seq : str
        Codon-optimised CDS produced in Step 3.  Empty until Step 3 runs.
    host : str
        Expression host selected in Step 2 (e.g. 'E.coli BL21(DE3)').
    tag : str
        Protein tag selected in Step 2 (e.g. 'His6-tag (C-term)').
    elements : Dict[str, Any]
        Regulatory element selections from Step 2.  Keys:
          promoter_name, promoter_seq,
          rbs_name, rbs_seq,
          terminator_name, terminator_seq.
    frame : Dict[str, Any]
        Full expression frame dict returned by build_expression_frame().
        Non-empty after Step 3 succeeds.
    primers : List[Dict[str, Any]]
        Primer list returned by AssemblyPlanner.plan_gibson_assembly().
        Populated in Step 4.
    validation_results : List[Dict[str, Any]]
        Issue dicts returned by validate_frame().  Populated in Step 5.
    cloning_method : str
        Cloning strategy selected in Step 4.
    codon_report : Dict[str, Any]
        DeepCodonOptimizer result dict.  Empty dict if optimisation skipped.
    primer_context_host : str
        The host string that was active when the current primers were designed.
        Used by Step 4 to detect upstream host changes and invalidate stale primers.
    primer_context_seq_hash : str
        SHA-256 hash of the sequence that was active when the current primers
        were designed.  Used by Step 4 to detect upstream sequence changes.
    """

    step: int = 1

    # Step 1 outputs
    gene_name: str = ""
    original_seq: str = ""

    # Step 2 outputs
    host: str = ""
    tag: str = ""
    elements: Dict[str, Any] = field(default_factory=dict)

    # Step 3 outputs
    optimized_seq: str = ""
    frame: Dict[str, Any] = field(default_factory=dict)
    codon_report: Dict[str, Any] = field(default_factory=dict)
    frame_context_signature: str = ""

    # Step 4 outputs
    cloning_method: str = ""
    primers: List[Dict[str, Any]] = field(default_factory=list)
    primer_context_host: str = ""
    primer_context_seq_hash: str = ""
    primer_context_signature: str = ""
    step4_plan_summary: Dict[str, Any] = field(default_factory=dict)
    primer_design_status: str = ""
    primer_backend_available: Optional[bool] = None
    active_primer_pair: Optional[Dict[str, Any]] = None

    # Step 5 outputs
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    validation_context_signature: str = ""

    # Saved design snapshot identity; distinct from pathway project identity.
    source_saved_design_id: str = ""
    saved_design_metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers

    @property
    def final_sequence(self) -> str:
        """Convenience: assembled expression frame sequence, or empty string."""
        return self.frame.get("final_sequence", "")

    @property
    def frame_ok(self) -> bool:
        """True if a successfully built expression frame is present."""
        return bool(self.frame.get("success"))

    def current_frame_context_signature(self) -> str:
        """Stable signature for Step 3 inputs that define the expression frame."""
        elements = self.elements if isinstance(self.elements, dict) else {}
        payload = {
            "gene_name": str(self.gene_name or "").strip(),
            "original_seq": str(self.original_seq or "").strip().upper(),
            "host": str(self.host or "").strip(),
            "tag": str(self.tag or "").strip(),
            "elements": {
                "promoter_name": str(elements.get("promoter_name") or "").strip(),
                "promoter_seq": str(elements.get("promoter_seq") or "").strip().upper(),
                "rbs_name": str(elements.get("rbs_name") or "").strip(),
                "rbs_seq": str(elements.get("rbs_seq") or "").strip().upper(),
                "terminator_name": str(elements.get("terminator_name") or "").strip(),
                "terminator_seq": str(elements.get("terminator_seq") or "").strip().upper(),
            },
        }
        return _sha256_json(payload)

    def current_primer_context_signature(self) -> str:
        """Stable signature for Step 4 inputs that define primer-design validity."""
        payload = {
            "frame_context_signature": self.current_frame_context_signature(),
            "frame_success": bool(self.frame.get("success")) if isinstance(self.frame, dict) else False,
            "final_sequence": str(self.final_sequence or self.optimized_seq or self.original_seq or "").strip().upper(),
            "cloning_method": str(self.cloning_method or "Gibson Assembly").strip(),
        }
        return _sha256_json(payload)

    def current_validation_context_signature(self) -> str:
        """Stable signature for Step 5 inputs that define validation validity."""
        normalized_primers = []
        for primer in (self.primers or []):
            if not isinstance(primer, dict):
                continue
            normalized_primers.append(
                {
                    "fragment": str(primer.get("Fragment Name") or primer.get("name") or "").strip(),
                    "forward": str(primer.get("Forward Primer (5'->3')") or primer.get("sequence") or "").strip().upper(),
                    "reverse": str(primer.get("Reverse Primer (5'->3')") or "").strip().upper(),
                    "quality_grade": str(primer.get("Quality Grade") or "").strip(),
                }
            )
        payload = {
            "primer_context_signature": self.current_primer_context_signature(),
            "primer_design_status": str(self.primer_design_status or "").strip(),
            "primer_backend_available": self.primer_backend_available,
            "primers": normalized_primers,
        }
        return _sha256_json(payload)

    def frame_is_stale(self) -> bool:
        if not self.frame_ok:
            return False
        if not self.frame_context_signature:
            return False
        return self.frame_context_signature != self.current_frame_context_signature()

    def primers_are_stale(self) -> bool:
        if not self.primers and not self.step4_plan_summary and not self.primer_design_status:
            return False
        current_signature = self.current_primer_context_signature()
        if self.primer_context_signature:
            return self.primer_context_signature != current_signature

        current_host = str(self.host or "").strip()
        current_seq = str(self.final_sequence or self.optimized_seq or self.original_seq or "").strip().upper()
        current_seq_hash = hashlib.sha256(current_seq.encode("utf-8")).hexdigest() if current_seq else ""
        if not self.primer_context_host and not self.primer_context_seq_hash:
            return False
        return (
            not self.primer_context_host
            or not self.primer_context_seq_hash
            or self.primer_context_host != current_host
            or self.primer_context_seq_hash != current_seq_hash
        )

    def validation_is_stale(self) -> bool:
        has_completed_validation = bool(self.validation_results) or bool(self.validation_context_signature)
        if not has_completed_validation:
            return False
        if not self.validation_context_signature:
            return False
        return self.validation_context_signature != self.current_validation_context_signature()

    def clear_step5_outputs(self) -> None:
        self.validation_results = []
        self.validation_context_signature = ""

    def clear_step4_outputs(self) -> None:
        self.cloning_method = ""
        self.primers = []
        self.primer_context_host = ""
        self.primer_context_seq_hash = ""
        self.primer_context_signature = ""
        self.step4_plan_summary = {}
        self.primer_design_status = ""
        self.primer_backend_available = None
        self.active_primer_pair = None
        self.clear_step5_outputs()

    def clear_step3_outputs(self) -> None:
        self.optimized_seq = ""
        self.frame = {}
        self.codon_report = {}
        self.frame_context_signature = ""
        self.clear_step4_outputs()

    def invalidate_stale_workflow_outputs(self) -> Dict[str, bool]:
        """Clear stale Step 3/4/5 outputs and return what was invalidated."""
        stale = {
            "frame_stale": self.frame_is_stale(),
            "primer_stale": False,
            "validation_stale": False,
        }

        if stale["frame_stale"]:
            stale["primer_stale"] = bool(self.primers or self.step4_plan_summary)
            stale["validation_stale"] = bool(self.validation_results)
            self.clear_step3_outputs()
            return stale

        stale["primer_stale"] = self.primers_are_stale()
        if stale["primer_stale"]:
            stale["validation_stale"] = bool(self.validation_results)
            self.clear_step4_outputs()
            return stale

        stale["validation_stale"] = self.validation_is_stale()
        if stale["validation_stale"]:
            self.clear_step5_outputs()

        return stale

    def summary(self) -> Dict[str, Any]:
        """Return a lightweight dict suitable for display / export."""
        return {
            "gene_name":        self.gene_name,
            "host":             self.host,
            "tag":              self.tag,
            "original_seq_len": len(self.original_seq),
            "optimized_seq_len":len(self.optimized_seq),
            "frame_length_bp":  self.frame.get("total_length", 0),
            "gc_content":       self.frame.get("gc_content", 0.0),
            "n_primers":        len(self.primers),
            "n_issues":         len(self.validation_results),
            "cloning_method":   self.cloning_method,
            "vector_suggestion":self.frame.get("vector_suggestion", ""),
        }


# ---------------------------------------------------------------------------
# SessionController
# ---------------------------------------------------------------------------

_SESSION_KEY = "design_session"


class SessionController:
    """Adapter between DesignSession and Streamlit session_state.

    Usage (inside a Streamlit page)
    --------------------------------
    >>> ctrl = SessionController()
    >>> ds = ctrl.get()          # DesignSession (creates blank if first call)
    >>> ds.original_seq = "ATG..."
    >>> ctrl.save(ds)
    >>> ctrl.advance()           # moves to next step and calls st.rerun()
    """

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def get(self) -> DesignSession:
        """Return the current DesignSession, creating a blank one if absent."""
        import streamlit as st
        obj = st.session_state.get(_SESSION_KEY)
        if not isinstance(obj, DesignSession):
            obj = DesignSession()
            st.session_state[_SESSION_KEY] = obj
        return obj

    def save(self, ds: DesignSession) -> None:
        """Store *ds* in the current Streamlit session only."""
        import streamlit as st
        st.session_state[_SESSION_KEY] = ds

    def reset(self) -> None:
        """Wipe the session and restart the wizard from step 1."""
        import streamlit as st
        from services.wizard_state_service import reset_wizard_for_new_design

        st.session_state[_SESSION_KEY] = DesignSession()
        reset_wizard_for_new_design(st.session_state)
        self.clear_global_context()
        st.session_state[SK.SELECTED_PAGE] = "Expression Wizard"
        st.rerun()

    def clear_global_context(self) -> None:
        """Clear the shared project context and cross-page sequence aliases."""
        SK.clear(
            SK.ACTIVE_HOST,
            SK.ACTIVE_SEQ,
            SK.ACTIVE_NAME,
            SK.ACTIVE_FEATURES,
            SK.DASHBOARD_PROJECT,
            SK.SEQ,
            SK.FEATURES,
            SK.PROJECT_NAME,
            SK.SEQ_DESIGN,
            SK.SEQ_CURRENT,
            SK.SEQ_ASSEMBLED,
            SK.SEQ_ORIGINAL,
            SK.SEQ_FINAL,
            SK.CHASSIS,
            SK.RESEARCHER_NAME,
            SK.ASSEMBLY_METHOD,
            SK.ASSEMBLY_RESULT,
            SK.PROTEIN_SEQ,
            SK.TRANSLATED_PROTEIN,
            SK.PDB_ID,
            SK.FBA_RESULT,
            SK.AI9_RESULT,
            SK.CHAT_HISTORY,
        )

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------

    @property
    def step(self) -> int:
        """Current wizard step (1-6)."""
        return self.get().step

    def advance(self) -> None:
        """Move to the next step and rerun (only if gate passes)."""
        import streamlit as st
        ds = self.get()
        if self.can_advance and ds.step < 6:
            ds.step += 1
            self.save(ds)
            st.rerun()

    def retreat(self) -> None:
        """Move to the previous step and rerun."""
        import streamlit as st
        ds = self.get()
        if ds.step > 1:
            ds.step -= 1
            self.save(ds)
            st.rerun()

    def jump(self, target: int) -> None:
        """Jump to a specific step (1-6) without gate check and rerun."""
        import streamlit as st
        ds = self.get()
        ds.step = max(1, min(6, target))
        self.save(ds)
        st.rerun()

    # ------------------------------------------------------------------
    # Gate logic  ("Next" button enabled only when this is True)
    # ------------------------------------------------------------------

    @property
    def can_advance(self) -> bool:
        """Return True when the current step's output satisfies its gate rule."""
        ds = self.get()
        s  = ds.step
        if s == 1:
            return len(ds.original_seq) >= WIZARD_MINIMUM_SEQUENCE_LENGTH
        if s == 2:
            return bool(ds.host)
        if s == 3:
            # frame_ok is True only when build_expression_frame() succeeded this
            # session for the current host/tag. Relying on optimized_seq alone
            # would allow stale data from a previous host selection to pass.
            return ds.frame_ok and not ds.frame_is_stale()
        if s == 4:
            if ds.primers:
                return not ds.primers_are_stale()
            return (
                ds.frame_ok
                and not ds.frame_is_stale()
                and str(ds.primer_design_status or "").strip().lower() == "unavailable"
                and ds.primer_backend_available is False
                and ds.active_primer_pair is None
                and not ds.primers_are_stale()
            )
        if s == 5:
            # Validation must have completed for the current frame + primers and
            # contain no critical issues. A completed clean run can have zero
            # issue rows, so the current validation context signature is also
            # accepted as evidence that Step 5 has run.
            has_completed_validation = bool(ds.validation_results) or bool(ds.validation_context_signature)
            if not has_completed_validation or ds.validation_is_stale():
                return False
            criticals = [i for i in ds.validation_results if i.get("severity") == "critical"]
            return len(criticals) == 0
        # Step 6 — export, no further steps
        return True

    # ------------------------------------------------------------------
    # Cross-page sync helpers
    # ------------------------------------------------------------------

    def sync_to_global_state(self) -> None:
        """Write the active design into the canonical global context keys.

        SK.ACTIVE_SEQ, SK.ACTIVE_FEATURES, SK.ACTIVE_HOST, and SK.ACTIVE_NAME
        are the single cross-page slots read by downstream pages.
        """
        import streamlit as st
        ds = self.get()
        if ds.frame_ok:
            seq = ds.final_sequence
            st.session_state[SK.ACTIVE_SEQ] = seq
            st.session_state[SK.ACTIVE_FEATURES] = ds.frame.get("features", [])
            st.session_state[SK.ACTIVE_HOST] = ds.host or ""
            st.session_state[SK.ACTIVE_NAME] = ds.gene_name or "Untitled Project"
            st.session_state[SK.SEQ] = seq
            st.session_state[SK.SEQ_DESIGN] = seq
            st.session_state[SK.SEQ_CURRENT] = seq
            st.session_state[SK.SEQ_ASSEMBLED] = seq
            st.session_state[SK.SEQ_ORIGINAL] = ds.original_seq or ""
            st.session_state[SK.SEQ_FINAL] = seq
            st.session_state[SK.PROJECT_NAME] = ds.gene_name or "Untitled Project"
            st.session_state[SK.SEQ] = seq
            st.session_state[SK.FEATURES] = ds.frame.get("features", [])
            st.session_state[SK.PROJECT_NAME] = ds.gene_name or "Untitled Project"
