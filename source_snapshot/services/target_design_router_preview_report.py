from __future__ import annotations

from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
)


REPORT_HEADINGS = [
    "# Target Design Preview",
    "## Boundary",
    "## Target Summary",
    "## Design Route",
    "## Construct Draft",
    "## Gene Slots",
    "## Cassette Slots",
    "## Required Parts",
    "## Missing Fields",
    "## Source Requirements",
    "## Review Notes",
    "## Support Status",
]

DEFAULT_BOUNDARY_NOTE = (
    "Documentation-only construct draft preview for manual design review. "
    "Not experimental validation and not a downstream use judgment."
)

EMPTY_SECTION_COPY = "No entries recorded in this preview section."
EMPTY_GENE_SLOTS_COPY = (
    "No gene slots are available because target clarification is required before any gene or pathway identity is drafted."
)
EMPTY_CASSETTE_SLOTS_COPY = (
    "No cassette slots are available until the route is clarified; sugarcane healthy sugar and unknown targets remain "
    "target-clarification previews."
)
EMPTY_REQUIRED_PARTS_COPY = (
    "No required parts are available until a route is clarified; this empty section is not a complete design."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value:
        return [value]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _escape_cell(value: Any) -> str:
    return _text(value, "Not recorded").replace("|", "\\|").replace("\n", "<br>")


def _bullet(label: str, value: Any, fallback: str = "Not recorded") -> str:
    return f"- {label}: {_text(value, fallback)}"


def _bullet_list(values: list[Any], *, empty_copy: str = EMPTY_SECTION_COPY) -> list[str]:
    rows = [_text(value) for value in values if _text(value)]
    if not rows:
        return [empty_copy]
    return [f"- {value}" for value in rows]


def _markdown_table(rows: list[dict[str, Any]], columns: list[str], *, empty_copy: str = EMPTY_SECTION_COPY) -> list[str]:
    clean_rows = [row for row in rows if isinstance(row, dict)]
    if not clean_rows:
        return [empty_copy]
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_escape_cell(row.get(column)) for column in columns) + " |"
        for row in clean_rows
    ]
    return [header, divider, *body]


def _section(title: str, lines: list[str]) -> list[str]:
    return [title, "", *lines, ""]


def _target_summary_lines(preview: dict[str, Any]) -> list[str]:
    summary = _as_dict(preview.get("target_summary"))
    aliases = " | ".join(_text(alias) for alias in _as_list(summary.get("aliases")) if _text(alias))
    return [
        _bullet("target_label", summary.get("target_label"), "Unresolved target"),
        _bullet("target_class", summary.get("target_class"), "unresolved_target"),
        _bullet("aliases", aliases),
        _bullet("notes", summary.get("notes")),
    ]


def _design_route_lines(preview: dict[str, Any]) -> list[str]:
    summary = _as_dict(preview.get("design_route_summary"))
    return [
        _bullet("design_route", summary.get("design_route"), "needs_target_clarification"),
        _bullet("route_label", summary.get("route_label"), "route preview"),
        _bullet("review_status", summary.get("review_status"), "needs review"),
        _bullet("support_status", summary.get("support_status"), _text(preview.get("support_status"), "unresolved")),
    ]


def _construct_template_lines(preview: dict[str, Any]) -> list[str]:
    summary = _as_dict(preview.get("construct_template_summary"))
    structure = " | ".join(_text(item) for item in _as_list(summary.get("structure")) if _text(item))
    return [
        _bullet("template_id", summary.get("template_id"), "needs_target_clarification"),
        _bullet("template_label", summary.get("template_label"), "Target clarification draft"),
        _bullet("description", summary.get("description"), "No construct draft is created until review fields are clarified."),
        _bullet("structure", structure),
    ]


def format_target_design_preview_markdown(preview: dict[str, Any]) -> str:
    """Return deterministic documentation-safe Markdown for a target design preview."""
    if not isinstance(preview, dict):
        raise TypeError("preview must be a dictionary")

    preview = normalize_generated_output_claims(preview)
    boundary_note = _text(preview.get("boundary_note"), DEFAULT_BOUNDARY_NOTE)
    lines: list[str] = ["# Target Design Preview", ""]
    lines.extend(_section("## Boundary", [boundary_note]))
    lines.extend(_section("## Target Summary", _target_summary_lines(preview)))
    lines.extend(_section("## Design Route", _design_route_lines(preview)))
    lines.extend(_section("## Construct Draft", _construct_template_lines(preview)))
    lines.extend(
        _section(
            "## Gene Slots",
            _markdown_table(
                _as_list(preview.get("gene_slots_table")),
                ["slot", "gene_label", "slot_role", "source_requirement", "review_status"],
                empty_copy=EMPTY_GENE_SLOTS_COPY,
            ),
        )
    )
    lines.extend(
        _section(
            "## Cassette Slots",
            _markdown_table(
                _as_list(preview.get("cassette_slots_table")),
                [
                    "cassette_slot",
                    "cassette",
                    "part_slot",
                    "slot_role",
                    "slot_label",
                    "source_status",
                    "review_status",
                ],
                empty_copy=EMPTY_CASSETTE_SLOTS_COPY,
            ),
        )
    )
    lines.extend(
        _section(
            "## Required Parts",
            _markdown_table(
                _as_list(preview.get("required_parts_table")),
                ["item", "status", "review_action"],
                empty_copy=EMPTY_REQUIRED_PARTS_COPY,
            ),
        )
    )
    lines.extend(
        _section(
            "## Missing Fields",
            _markdown_table(
                _as_list(preview.get("missing_fields_table")),
                ["field", "status", "review_action"],
            ),
        )
    )
    lines.extend(
        _section(
            "## Source Requirements",
            _markdown_table(
                _as_list(preview.get("source_requirements_table")),
                ["source_requirement", "status", "review_action"],
            ),
        )
    )
    lines.extend(_section("## Review Notes", _bullet_list(_as_list(preview.get("review_notes")))))
    lines.extend(
        _section(
            "## Support Status",
            [
                _bullet("support_status", preview.get("support_status"), "unresolved"),
                _bullet("readiness_label", preview.get("readiness_label"), "Draft only"),
            ],
        )
    )
    markdown = "\n".join(lines).rstrip() + "\n"
    assert_no_misleading_generated_claims(markdown, context="target preview report")
    return markdown
