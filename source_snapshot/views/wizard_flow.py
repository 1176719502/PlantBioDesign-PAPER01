# -*- coding: utf-8 -*-
"""
views/wizard_flow.py  --  Expression Design Wizard dispatcher.

This file is now a THIN DISPATCHER only.  All wizard logic lives in
views/wizard_steps/.

  Step logic     -> views/wizard_steps/stepN_*.py
  Shared helpers -> views/wizard_steps/_shared.py
  Step registry  -> views/wizard_steps/__init__.py

Backward-compatible re-exports
------------------------------
_check_dna_input and _clean_seq are re-exported here so that
tests/test_regression.py can continue to import them from this
module without modification.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Backward-compatible shims for test_regression.py
# ---------------------------------------------------------------------------
from views.wizard_steps._shared import _check_dna_input  # noqa: F401
from views.wizard_steps._shared import _clean_seq        # noqa: F401


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render(change_page=None) -> None:
    """Public entry point called by ExpressionWizard.py and app.py."""
    from core.design_session import SessionController
    from views.wizard_steps._shared import _wizard_identity_banner, _step_indicator, _nav_bar, render_plant_mvp_context
    from views.wizard_steps import PAGE_FUNCS

    ctrl = SessionController()
    _wizard_identity_banner(ctrl.step)
    _step_indicator(ctrl.step, ctrl)
    render_plant_mvp_context(ctrl.step)
    PAGE_FUNCS.get(ctrl.step, PAGE_FUNCS[1])(ctrl)
    _nav_bar(ctrl)
