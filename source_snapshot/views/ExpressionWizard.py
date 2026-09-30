# views/ExpressionWizard.py
"""
Expression Wizard — thin router shell.

This file used to contain a full 1,160-line duplicate of the 6-step wizard
implemented in views/wizard_flow.py (also 1,125 lines).  Both files rendered
identical functionality, causing:
  - Double maintenance burden (bug fixes had to be applied twice)
  - Divergence between the two implementations over time
  - Unnecessary import overhead (~2 MB of code loaded twice)

Fix (2026-03-18)
-----------------
This file is now a thin shell that simply delegates to wizard_flow.render().
All wizard logic lives exclusively in views/wizard_flow.py.

If you need to add a feature to the Expression Wizard, edit wizard_flow.py.
"""
from __future__ import annotations

import streamlit as st


def render(change_page=None) -> None:  # noqa: D401
    """Entry point called by app.py router -- delegates to wizard_flow."""
    try:
        from views.wizard_flow import render as _wf_render
        _wf_render(change_page)
    except ImportError as exc:
        st.error("Expression Wizard is unavailable in this environment.")
        st.caption(
            "The design-record workflow could not be loaded. Existing saved design records remain documentation-only "
            "local records; no validation, export, or primer status has been changed."
        )
        with st.expander("Technical load detail", expanded=False):
            st.code(str(exc), language="text")
    except Exception as exc:
        st.error("Expression Wizard could not render this design-record view.")
        st.caption(
            "No design state, validation status, primer status, or export package was changed. "
            "Review the technical detail only if you need to troubleshoot the local app."
        )
        import traceback
        with st.expander("Technical render detail", expanded=False):
            st.code(traceback.format_exc(), language="text")
