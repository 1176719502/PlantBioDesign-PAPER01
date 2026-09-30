from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.pathway_traceability_view_model import (
    build_project_outputs_traceability_summary_state,
    build_traceability_graph_lite_display_state,
    build_traceability_graph_lite,
)


def render_traceability_graph_lite_section(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    *,
    lineage_copy: str,
    boundary_copy: str,
    status_helper_copy: str,
    empty_state_copy: str,
) -> None:
    st.subheader("Traceability Graph Lite")
    st.caption(lineage_copy)
    st.caption(boundary_copy)
    st.caption(status_helper_copy)

    graph = build_traceability_graph_lite(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots=snapshots,
    )
    display_state = build_traceability_graph_lite_display_state(graph)
    summary_state = display_state["summary"]
    table_state = display_state["table"]

    with st.container(border=True):
        columns = st.columns(4, gap="small")
        for column, (label, value) in zip(columns, summary_state["metric_items"]):
            with column:
                st.markdown(f"**{label}**")
                st.markdown(value)

    if table_state["has_rows"]:
        st.dataframe(pd.DataFrame(table_state["rows"]), width="stretch", hide_index=True)
    else:
        st.info(empty_state_copy)


def render_project_outputs_traceability_summary(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    snapshots: list[dict[str, Any]] | None,
    *,
    status_helper_copy: str,
) -> None:
    graph = build_traceability_graph_lite(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots=snapshots,
    )
    summary_state = build_project_outputs_traceability_summary_state(graph)

    st.caption(summary_state["boundary_caption"])
    st.caption(status_helper_copy)
    with st.container(border=True):
        columns = st.columns(4, gap="small")
        for column, (label, value) in zip(columns, summary_state["metric_items"]):
            with column:
                st.markdown(f"**{label}**")
                st.markdown(value)
