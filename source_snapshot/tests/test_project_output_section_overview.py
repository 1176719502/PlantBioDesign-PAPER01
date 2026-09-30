from __future__ import annotations

from services.project_output_section_overview import (
    build_project_output_sections_overview,
    format_project_output_sections_overview_markdown,
)


def test_project_output_sections_overview_is_compact_read_only_map() -> None:
    overview = build_project_output_sections_overview(
        report={
            "markdown": "# Project Review Report\n\n## Report summary",
            "missing_fields": [{"gap_id": "review_note"}],
        },
        detailed_report_draft={
            "status": "AVAILABLE",
            "markdown": "# Detailed Documentation Report Draft\n\n## Project summary\n\n## Known limitations",
            "component_library_followup_queue_report_readback": {
                "status": "AVAILABLE",
                "summary": {"queue_item_count": 2},
            },
        },
        handoff_preview={
            "status": "AVAILABLE",
            "review_sheet_sections": [{"key": "handoff_summary"}],
            "traceability_matrix_rows": [{"source_surface": "Project Review Report"}],
            "expression_construct_review_action_panel": {
                "status": "AVAILABLE",
                "summary": {"row_count": 4},
            },
        },
        dashboard={
            "overall_documentation_status": "REVIEW_NEEDED",
            "metrics": {"review_gap_count": 3},
        },
    )

    assert overview["title"] == "Output sections overview"
    assert overview["status"] == "AVAILABLE"
    assert overview["section_count"] == 7
    assert overview["available_section_count"] == 7
    assert [row["section_name"] for row in overview["rows"]] == [
        "Project Review Report",
        "Detailed Documentation Draft / markdown preview",
        "Handoff Review / package preview",
        "Quality Dashboard package preview",
        "Expression Construct Review summary/action panel",
        "Component Library follow-up queue report/readback",
        "Project handoff traceability matrix",
    ]
    assert overview["rows"][0]["count"] == 1
    assert overview["rows"][1]["count"] == 2
    assert overview["rows"][3]["count"] == 3
    assert overview["rows"][4]["count"] == 4
    assert overview["rows"][5]["count"] == 2
    assert overview["rows"][6]["count"] == 1
    assert "Read-only section map" in overview["boundary_notes"][0]


def test_project_output_sections_overview_markdown_has_no_long_boundary_wall() -> None:
    overview = build_project_output_sections_overview(
        handoff_preview={
            "status": "AVAILABLE",
            "review_sheet_sections": [{"key": "handoff_summary"}],
        }
    )
    markdown = format_project_output_sections_overview_markdown(overview)

    assert "## Output sections overview" in markdown
    assert "| Section | Status | Count | Inspect next |" in markdown
    assert "Project Review Report" in markdown
    assert "Handoff Review / package preview" in markdown
    assert "Read-only section map" in markdown
    assert "validated construct" not in markdown.lower()
    assert "optimized pathway" not in markdown.lower()
    assert "yield prediction" not in markdown.lower()
    assert "ready for execution" not in markdown.lower()
