"""Archived AutoPipeline view.

This module is intentionally kept as a safe placeholder. The automated
pipeline workflow is outside the stabilized MVP and is not exposed in the
current application navigation.
"""
from __future__ import annotations

import streamlit as st


def render(*_args, **_kwargs) -> None:
    """Render an archived notice without enabling AutoPipeline behavior."""
    st.title("AutoPipeline Archived")
    st.info(
        "The AutoPipeline workspace is currently archived and hidden from the "
        "active BioDesign Studio workflow. Use the Expression Wizard for the "
        "stabilized single-gene expression design process."
    )
