from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_linked_design_view_model import (
    build_linked_design_evidence_rows,
    build_pathway_steps_table_rows,
    expression_link_counts_by_step,
    expression_links_by_step,
    safe_step_id,
)


def test_build_pathway_steps_table_rows_normal_fields_and_linked_count():
    steps = [
        {
            "id": 11,
            "step_order": 2,
            "step_name": "Convert substrate",
            "reaction_name": "Conversion reaction",
            "substrate": "Substrate A",
            "product": "Product B",
            "enzyme_name": "Enzyme C",
            "gene_name": "geneD",
            "gene_sequence": "ATGCGA",
        }
    ]

    rows = build_pathway_steps_table_rows(steps, {11: 3})

    assert rows == [
        {
            "Order": 2,
            "Step": "Convert substrate",
            "Reaction": "Conversion reaction",
            "Substrate": "Substrate A",
            "Product": "Product B",
            "Enzyme": "Enzyme C",
            "Gene": "geneD",
            "Sequence Length": 6,
            "Linked designs": 3,
        }
    ]


def test_build_pathway_steps_table_rows_uses_string_numeric_step_id_for_linked_count():
    rows = build_pathway_steps_table_rows(
        [{"id": "12", "step_order": 1, "step_name": "String id step"}],
        {12: 2},
    )

    assert rows[0]["Linked designs"] == 2


def test_build_pathway_steps_table_rows_bad_none_step_id_does_not_raise():
    steps = [
        {"id": None, "step_order": 1, "step_name": "Missing id"},
        {"id": "bad", "step_order": 2, "step_name": "Bad id"},
        {"id": 0, "step_order": 3, "step_name": "Zero id"},
        {"id": -1, "step_order": 4, "step_name": "Negative id"},
        None,
    ]

    rows = build_pathway_steps_table_rows(steps, {0: 99, 1: 1})

    assert [row["Step"] for row in rows] == ["Missing id", "Bad id", "Zero id", "Negative id"]
    assert [row["Linked designs"] for row in rows] == [99, 99, 99, 99]


def test_build_pathway_steps_table_rows_missing_optional_fields_fallback():
    rows = build_pathway_steps_table_rows([{"id": 13, "step_order": 5}], {})

    assert rows == [
        {
            "Order": 5,
            "Step": "Step 5",
            "Reaction": "",
            "Substrate": "",
            "Product": "",
            "Enzyme": "",
            "Gene": "",
            "Sequence Length": 0,
            "Linked designs": 0,
        }
    ]


def test_build_pathway_steps_table_rows_does_not_prefer_step_title():
    rows = build_pathway_steps_table_rows(
        [{"id": 14, "step_order": 6, "step_title": "Title fallback", "step_name": "Step name"}],
        {},
    )

    assert rows[0]["Step"] == "Step name"


def test_build_pathway_steps_table_rows_uses_name_before_order_fallback():
    rows = build_pathway_steps_table_rows(
        [{"id": 19, "step_order": 7, "step_title": "Title fallback", "name": "Legacy name"}],
        {},
    )

    assert rows[0]["Step"] == "Legacy name"


def test_build_pathway_steps_table_rows_missing_order_matches_previous_ui():
    rows = build_pathway_steps_table_rows([{"id": 20, "step_title": "Title fallback"}], {})

    assert rows[0]["Step"] == "Step None"


def test_build_pathway_steps_table_rows_sequence_length_calculation():
    rows = build_pathway_steps_table_rows(
        [
            {"id": 15, "step_order": 1, "gene_sequence": "ATGC"},
            {"id": 16, "step_order": 2, "gene_sequence": None},
            {"id": 17, "step_order": 3, "gene_sequence": 12345},
        ],
        {},
    )

    assert [row["Sequence Length"] for row in rows] == [4, 0, 5]


def test_build_pathway_steps_table_rows_does_not_mutate_input_steps():
    steps = [
        {
            "id": "18",
            "step_order": 1,
            "step_name": "Immutable step",
            "gene_sequence": "ATGC",
            "metadata": {"nested": "value"},
        }
    ]
    original_steps = copy.deepcopy(steps)

    rows = build_pathway_steps_table_rows(steps, {18: 1})
    rows[0]["Step"] = "Changed row"

    assert steps == original_steps


def test_groups_string_and_int_step_id_correctly():
    expression_links = [
        {"id": 1, "step_id": 7, "design_name": "Int step link"},
        {"id": 2, "step_id": "7", "design_name": "String step link"},
        {"id": 3, "step_id": "8", "design_name": "Other step link"},
    ]

    grouped = expression_links_by_step(expression_links)
    counts = expression_link_counts_by_step(expression_links)

    assert set(grouped) == {7, 8}
    assert [link["design_name"] for link in grouped[7]] == ["Int step link", "String step link"]
    assert counts == {7: 2, 8: 1}


def test_ignores_bad_none_and_non_positive_link_step_id():
    expression_links = [
        {"step_id": None, "design_name": "Missing"},
        {"step_id": "bad", "design_name": "Bad"},
        {"step_id": 0, "design_name": "Zero"},
        {"step_id": "-1", "design_name": "Negative"},
        {"step_id": 2, "design_name": "Kept"},
        "not a dict",
    ]

    assert expression_links_by_step(expression_links) == {2: [{"step_id": 2, "design_name": "Kept"}]}
    assert expression_link_counts_by_step(expression_links) == {2: 1}


def test_returns_count_zero_for_unlinked_steps():
    steps = [
        {"id": 1, "step_order": 1, "step_name": "Linked step"},
        {"id": 2, "step_order": 2, "step_name": "Unlinked step"},
    ]
    expression_links = [{"step_id": "1", "design_name": "Linked design"}]

    rows = build_linked_design_evidence_rows(steps, expression_links)

    assert rows[0]["linked_design_count"] == 1
    assert rows[1]["linked_design_count"] == 0
    assert rows[1]["linked_design_rows"] == []


def test_display_name_fallback_when_design_name_title_and_name_missing():
    steps = [{"id": 3, "step_order": 1, "step_name": "Evidence step"}]
    expression_links = [
        {"step_id": 3, "design_title": "Design title"},
        {"step_id": 3, "snapshot_title": "Snapshot title"},
        {"step_id": 3, "name": "Name fallback"},
        {"step_id": 3, "title": "Title fallback"},
        {"step_id": 3, "design_id": 42},
        {"step_id": 3},
    ]

    linked_rows = build_linked_design_evidence_rows(steps, expression_links)[0]["linked_design_rows"]

    assert [row["linked_design_name"] for row in linked_rows] == [
        "Design title",
        "Snapshot title",
        "Name fallback",
        "Title fallback",
        "Linked design 42",
        "Linked design",
    ]


def test_timestamp_fallback_when_linked_saved_created_and_updated_fields_vary():
    steps = [{"id": 4, "step_order": 1, "step_name": "Timestamp step"}]
    expression_links = [
        {"step_id": 4, "linked_at": "2026-06-01T10:00:00"},
        {"step_id": 4, "saved_at": "2026-06-01T11:00:00"},
        {"step_id": 4, "created_at": "2026-06-01T12:00:00"},
        {"step_id": 4, "updated_at": "2026-06-01T13:00:00"},
        {"step_id": 4},
    ]

    linked_rows = build_linked_design_evidence_rows(steps, expression_links)[0]["linked_design_rows"]

    assert [row["linked_timestamp"] for row in linked_rows] == [
        "2026-06-01T10:00:00",
        "2026-06-01T11:00:00",
        "2026-06-01T12:00:00",
        "2026-06-01T13:00:00",
        "Not recorded",
    ]


def test_source_context_fallback_when_source_and_context_fields_vary():
    steps = [{"id": 5, "step_order": 1, "step_name": "Source step"}]
    expression_links = [
        {"step_id": 5, "design_source": "expression_wizard"},
        {"step_id": 5, "source": "saved_design"},
        {"step_id": 5, "linked_source": "pathway_workspace"},
        {"step_id": 5, "context": "active pathway context"},
        {"step_id": 5, "source_context": "stored context"},
        {"step_id": 5},
    ]

    linked_rows = build_linked_design_evidence_rows(steps, expression_links)[0]["linked_design_rows"]

    assert [row["source_context"] for row in linked_rows] == [
        "expression_wizard",
        "saved_design",
        "pathway_workspace",
        "active pathway context",
        "stored context",
        "Not recorded",
    ]


def test_bad_none_step_id_does_not_raise():
    steps = [
        {"id": None, "step_order": 1, "step_name": "Missing id"},
        {"id": "bad", "step_order": 2, "step_title": "Bad id title"},
        {"id": 0, "step_order": 3},
        {"id": -4, "step_order": 4, "step_name": "Negative id"},
        None,
    ]

    rows = build_linked_design_evidence_rows(steps, [{"step_id": 1, "design_name": "Unmatched"}])

    assert safe_step_id(None) == 0
    assert safe_step_id("bad") == 0
    assert safe_step_id(0) == 0
    assert safe_step_id(-4) == 0
    assert [row["step_id"] for row in rows] == [0, 0, 0, 0]
    assert [row["linked_design_count"] for row in rows] == [0, 0, 0, 0]
    assert rows[1]["step_title"] == "Bad id title"
    assert rows[2]["step_title"] == "Step 3"


def test_does_not_mutate_input_steps_or_expression_links():
    steps = [{"id": "6", "step_order": 1, "step_name": "Immutable step"}]
    expression_links = [{"step_id": "6", "design_name": "Immutable design", "metadata": {"key": "value"}}]
    original_steps = copy.deepcopy(steps)
    original_expression_links = copy.deepcopy(expression_links)

    rows = build_linked_design_evidence_rows(steps, expression_links)
    grouped = expression_links_by_step(expression_links)
    grouped[6][0]["design_name"] = "Changed copy"

    assert rows[0]["linked_design_rows"][0]["linked_design_name"] == "Immutable design"
    assert steps == original_steps
    assert expression_links == original_expression_links
