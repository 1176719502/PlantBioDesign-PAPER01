# -*- coding: utf-8 -*-
"""Regression tests for Data registry sequence search modes."""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from views.Data import (
    _apply_filters,
    _build_browsing_scope,
    _did_registry_view_change,
    _paginate_dataframe,
    _paging_summary,
    _resolve_page_for_scope,
    _resolve_selected_part_id_for_visible_page,
    _resolve_selected_row_in_scope,
)



def test_sequence_search_defaults_to_preview_matching() -> None:
    """Default sequence search should use Sequence Preview only."""
    long_seq = "A" * 45 + "TTGGCCAA"
    df = pd.DataFrame(
        [
            {
                "Name": "LongPart",
                "Type": "CDS",
                "Description": "",
                "Function Summary": "",
                "Sequence": long_seq,
                "Sequence Preview": long_seq[:45] + "...",
            }
        ]
    )

    out = _apply_filters(df, "TTGGCCAA", type_filter=[])

    assert out.empty



def test_sequence_search_can_match_full_sequence_when_enabled() -> None:
    """Full sequence option should match beyond the preview window."""
    long_seq = "A" * 45 + "TTGGCCAA"
    df = pd.DataFrame(
        [
            {
                "Name": "LongPart",
                "Type": "CDS",
                "Description": "",
                "Function Summary": "",
                "Sequence": long_seq,
                "Sequence Preview": long_seq[:45] + "...",
            }
        ]
    )

    out = _apply_filters(
        df,
        "TTGGCCAA",
        type_filter=[],
        full_sequence_search=True,
    )

    assert len(out) == 1
    assert out.iloc[0]["Name"] == "LongPart"


def test_paginate_dataframe_returns_expected_slice_and_bounds() -> None:
    """Pagination helper should slice rows and clamp out-of-range pages."""
    df = pd.DataFrame({"Name": [f"Part{i}" for i in range(1, 31)]})

    page_df, current_page, total_pages, total_rows = _paginate_dataframe(df, page=5, page_size=10)

    assert current_page == 3
    assert total_pages == 3
    assert total_rows == 30
    assert page_df["Name"].tolist() == [f"Part{i}" for i in range(21, 31)]


def test_paging_summary_reports_visible_window() -> None:
    """Paging summary should report the visible row range."""
    assert _paging_summary(page=2, page_size=25, total_rows=80) == "Showing rows 26-50 of 80"
    assert _paging_summary(page=1, page_size=25, total_rows=0) == "Showing 0 of 0 rows"



def test_page_resets_when_search_filter_or_page_size_changes() -> None:
    """Browsing scope changes should reset the registry view back to page 1."""
    previous_scope = _build_browsing_scope("promoter", ["CDS", "Promoter"], False, 25)

    assert _resolve_page_for_scope(
        current_page=4,
        previous_scope=previous_scope,
        current_scope=_build_browsing_scope("promoter", ["Promoter", "CDS"], False, 25),
    ) == 4
    assert _resolve_page_for_scope(
        current_page=4,
        previous_scope=previous_scope,
        current_scope=_build_browsing_scope("terminator", ["Promoter", "CDS"], False, 25),
    ) == 1
    assert _resolve_page_for_scope(
        current_page=4,
        previous_scope=previous_scope,
        current_scope=_build_browsing_scope("promoter", ["Promoter"], False, 25),
    ) == 1
    assert _resolve_page_for_scope(
        current_page=4,
        previous_scope=previous_scope,
        current_scope=_build_browsing_scope("promoter", ["Promoter", "CDS"], True, 25),
    ) == 1
    assert _resolve_page_for_scope(
        current_page=4,
        previous_scope=previous_scope,
        current_scope=_build_browsing_scope("promoter", ["Promoter", "CDS"], False, 50),
    ) == 1



def test_registry_view_change_detects_scope_and_page_transitions() -> None:
    """Selection cleanup should only react when the visible registry page changes."""
    scope = _build_browsing_scope("promoter", ["Promoter"], False, 25)

    assert _did_registry_view_change(scope, scope, previous_page=2, current_page=2) is False
    assert _did_registry_view_change(scope, scope, previous_page=2, current_page=3) is True
    assert _did_registry_view_change(
        scope,
        _build_browsing_scope("terminator", ["Promoter"], False, 25),
        previous_page=2,
        current_page=1,
    ) is True



def test_selected_row_clears_when_filtered_row_is_not_in_current_page_scope() -> None:
    """Detail selection should clear when the part is outside the active paged result set."""
    df = pd.DataFrame(
        [
            {"ID": 1, "Name": "Part1"},
            {"ID": 2, "Name": "Part2"},
            {"ID": 3, "Name": "Part3"},
        ]
    )

    page_df, _, _, _ = _paginate_dataframe(df, page=1, page_size=2)

    assert _resolve_selected_row_in_scope(page_df, selected_part_id=2)["Name"] == "Part2"
    assert _resolve_selected_row_in_scope(page_df, selected_part_id=3) is None
    assert _resolve_selected_row_in_scope(page_df, selected_part_id=None) is None



def test_selected_part_id_is_preserved_when_view_is_unchanged() -> None:
    """A rerun without filter or page movement should keep the current detail selection."""
    page_df = pd.DataFrame(
        [
            {"ID": 1, "Name": "Part1"},
            {"ID": 2, "Name": "Part2"},
        ]
    )

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=page_df,
        selected_part_id=2,
        selected_rows=[],
        apply_event_selection=False,
    )

    assert selected_part_id == 2



def test_selected_part_id_clears_when_new_visible_page_excludes_selection() -> None:
    """Changing the visible result set should clear an off-scope stored selection."""
    page_df = pd.DataFrame(
        [
            {"ID": 1, "Name": "Part1"},
            {"ID": 2, "Name": "Part2"},
        ]
    )

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=page_df,
        selected_part_id=3,
        selected_rows=[],
        apply_event_selection=False,
    )

    assert selected_part_id is None



def test_selected_part_id_updates_from_current_event_selection() -> None:
    """A new visible row click should still bind the detail panel to that part."""
    page_df = pd.DataFrame(
        [
            {"ID": 10, "Name": "Part10"},
            {"ID": 11, "Name": "Part11"},
        ]
    )

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=page_df,
        selected_part_id=10,
        selected_rows=[1],
        apply_event_selection=True,
    )

    assert selected_part_id == 11



def test_selected_part_id_does_not_rebind_stale_row_index_after_page_change() -> None:
    """A stale frontend row index should not select a different part after pagination moves."""
    original_page_df = pd.DataFrame(
        [
            {"ID": 10, "Name": "Part10"},
            {"ID": 11, "Name": "Part11"},
        ]
    )
    next_page_df = pd.DataFrame(
        [
            {"ID": 20, "Name": "Part20"},
            {"ID": 21, "Name": "Part21"},
        ]
    )

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=original_page_df,
        selected_part_id=11,
        selected_rows=[1],
        apply_event_selection=True,
    )
    assert selected_part_id == 11

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=next_page_df,
        selected_part_id=selected_part_id,
        selected_rows=[1],
        apply_event_selection=False,
    )

    assert selected_part_id is None

