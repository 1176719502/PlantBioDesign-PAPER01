import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from core.i18n import t as _t
from views.Dashboard import (
    _build_result_count_text,
    _clear_saved_design_filters,
    _default_saved_design_filters,
    _display_project,
    _filter_and_sort_projects,
    _matches_search,
)


SAMPLE_PROJECTS = [
    {
        "Name": "Alpha Design",
        "Gene": "GFP",
        "Host": "E.coli BL21(DE3)",
        "Type": "Expression Design",
        "Saved": "2026-01-03 11:00",
        "Length (bp)": 1200,
        "GC%": "51.0%",
        "_gene": "GFP",
        "_host": "E.coli BL21(DE3)",
    },
    {
        "Name": "Beta Vector",
        "Gene": "RFP",
        "Host": "S. cerevisiae",
        "Type": "Vector",
        "Saved": "2026-01-01 09:00",
        "Length (bp)": 5400,
        "GC%": "48.0%",
        "_gene": "RFP",
        "_host": "S. cerevisiae",
    },
    {
        "Name": "Gamma Sequence",
        "Gene": "LacZ",
        "Host": "B. subtilis",
        "Type": "Sequence",
        "Saved": "2026-01-02 10:00",
        "Length (bp)": 900,
        "GC%": "44.0%",
        "_gene": "LacZ",
        "_host": "B. subtilis",
    },
]


def test_default_saved_design_filters_match_expected_defaults():
    assert _default_saved_design_filters() == {
        "pw_search_query": "",
        "pw_type_filter": "All",
        "pw_sort_order": "Newest first",
    }


def test_dashboard_clarification_copy_defines_snapshot_not_readiness():
    saved_copy = _t("dashboard.saved_snapshot_clarification")
    load_copy = _t("dashboard.load_snapshot_clarification")
    empty_copy = _t("dashboard.empty_body")
    preview_copy = _t("dashboard.preview.status_clarification")
    bottom_help = _t("dashboard.bottom_help")

    assert _t("dashboard.title") == "Saved Designs"
    assert "Project Workspace" not in _t("dashboard.title")
    assert "saved design records and saved design snapshots" in _t("dashboard.subtitle")
    assert "Project Workspace" not in _t("dashboard.subtitle")
    assert "Saved Designs summaries are entry points" in saved_copy
    assert "Saved design records are local documentation records" in saved_copy
    assert "Expression Wizard design record subflow" in saved_copy
    assert "Saved design = wizard snapshot" in saved_copy
    assert "Pathway project = documentation workspace" in saved_copy
    assert "not active projects, review approval, or readiness approval" in saved_copy
    assert "experiment-ready" not in saved_copy
    assert "Saved design ID identifies a saved design record for loading and traceability." in load_copy
    assert "Save a design record in Step 6" in empty_copy
    assert "local documentation records only" in empty_copy
    assert "Expression Wizard design record subflow" in load_copy
    assert "without creating or selecting a linked Pathway Project context" in load_copy
    assert "Use Pathway Projects when linked records should support documentation traceability" in load_copy
    assert "Loading a saved design restores wizard inputs and outputs" not in load_copy
    assert "local documentation record, not experimental validation or readiness approval" in preview_copy
    assert "documentation traceability" in bottom_help
    assert "Documentation artifacts and saved design records are review records only" in bottom_help
    assert _t("dashboard.ready") == "Local workspace available"
    assert "Ready" not in _t("dashboard.ready")



    st.session_state.clear()
    st.session_state["pw_search_query"] = "gfp"
    st.session_state["pw_type_filter"] = "Vector"
    st.session_state["pw_sort_order"] = "Oldest first"
    st.session_state["pw_project_select"] = "Alpha Design"
    st.session_state["pw_confirm_delete"] = "Beta Vector"
    st.session_state["wizard_step"] = 4

    _clear_saved_design_filters()

    assert st.session_state["pw_search_query"] == ""
    assert st.session_state["pw_type_filter"] == "All"
    assert st.session_state["pw_sort_order"] == "Newest first"
    assert st.session_state["pw_project_select"] == "Alpha Design"
    assert st.session_state["pw_confirm_delete"] == "Beta Vector"
    assert st.session_state["wizard_step"] == 4



def test_build_result_count_text_formats_full_visible_count():
    assert _build_result_count_text(24, 24) == "Showing 24 of 24 designs"



def test_build_result_count_text_formats_partial_visible_count():
    assert _build_result_count_text(7, 24) == "Showing 7 of 24 designs"



def test_build_result_count_text_formats_zero_visible_count():
    assert _build_result_count_text(0, 24) == "Showing 0 of 24 designs"


def test_dashboard_saved_at_display_uses_consistent_minute_format():
    source = {
        "Name": "Alpha Design",
        "Saved": "2026-04-08T12:00:45",
    }

    displayed = _display_project(source)

    assert displayed["Saved"] == "2026-04-08 12:00"
    assert source["Saved"] == "2026-04-08T12:00:45"



def test_clear_filters_equivalent_to_default_filter_and_sort():
    defaults = _default_saved_design_filters()
    projects_after_clear = _filter_and_sort_projects(
        SAMPLE_PROJECTS,
        defaults["pw_search_query"],
        defaults["pw_type_filter"],
        defaults["pw_sort_order"],
    )
    explicit_default_projects = _filter_and_sort_projects(
        SAMPLE_PROJECTS,
        "",
        "All",
        "Newest first",
    )

    assert projects_after_clear == explicit_default_projects



def test_matches_search_checks_name_gene_and_host():
    assert _matches_search(SAMPLE_PROJECTS[0], "alpha") is True
    assert _matches_search(SAMPLE_PROJECTS[0], "gfp") is True
    assert _matches_search(SAMPLE_PROJECTS[0], "bl21") is True
    assert _matches_search(SAMPLE_PROJECTS[0], "yeast") is False



def test_filter_and_sort_projects_applies_type_and_newest_first():
    rows = _filter_and_sort_projects(
        SAMPLE_PROJECTS,
        search_query="",
        type_filter="Sequence",
        sort_order="Newest first",
    )

    assert [row["Name"] for row in rows] == ["Gamma Sequence"]



def test_filter_and_sort_projects_applies_search_and_oldest_first():
    rows = _filter_and_sort_projects(
        SAMPLE_PROJECTS,
        search_query="design",
        type_filter="All",
        sort_order="Oldest first",
    )

    assert [row["Name"] for row in rows] == ["Alpha Design"]



def test_filter_and_sort_projects_sorts_all_rows_by_saved_time():
    newest = _filter_and_sort_projects(SAMPLE_PROJECTS, "", "All", "Newest first")
    oldest = _filter_and_sort_projects(SAMPLE_PROJECTS, "", "All", "Oldest first")

    assert [row["Name"] for row in newest] == ["Alpha Design", "Gamma Sequence", "Beta Vector"]
    assert [row["Name"] for row in oldest] == ["Beta Vector", "Gamma Sequence", "Alpha Design"]
