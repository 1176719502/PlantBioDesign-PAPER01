from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


DEFAULT_TITLE = "Expression Vector Design Package Preview"
NOT_PROVIDED = "Not provided"


def _text(value: Any, fallback: str = NOT_PROVIDED) -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _cell(value: Any, fallback: str = NOT_PROVIDED) -> str:
    text = _text(value, fallback)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    rendered_rows = [list(row) for row in rows]
    lines = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    if rendered_rows:
        lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rendered_rows)
    else:
        lines.append("| " + " | ".join(["Not provided", *[""] * (len(headers) - 1)]) + " |")
    return "\n".join(lines)


def _field_table(rows: Iterable[tuple[str, Any]]) -> str:
    return _table(["Field", "Value"], rows)


def _section_summary_table(summary: Mapping[str, Any], value_label: str, value_key: str) -> str:
    return _field_table(
        [
            (value_label, summary.get(value_key, "Missing")),
            ("Source / provenance", summary.get("source_or_provenance", "Needs source")),
            ("Review status", summary.get("review_status", "Needs review")),
            ("Gap / manual follow-up", summary.get("gap_or_follow_up", "Needs review")),
            ("Notes", summary.get("notes", NOT_PROVIDED)),
        ]
    )


def _cassette_slot_rows_table(rows: Iterable[Mapping[str, Any]]) -> str:
    return _table(
        ["Slot", "Group", "Recorded value", "Source / provenance", "Review status", "Gap / follow-up"],
        (
            [
                row.get("slot_label", row.get("slot_key", "Missing")),
                row.get("slot_group", NOT_PROVIDED),
                row.get("recorded_value", "Missing"),
                row.get("source_or_provenance", "Needs source"),
                row.get("review_status", "Needs review"),
                row.get("gap_or_follow_up", "Needs review"),
            ]
            for row in rows
        ),
    )


def _sequence_checks_table(rows: Iterable[Mapping[str, Any]]) -> str:
    return _table(
        ["Check", "Recorded value", "Review status", "Gap / follow-up", "Notes"],
        (
            [
                row.get("check_name", "Sequence Basic Checks"),
                row.get("recorded_value", "Missing"),
                row.get("review_status", "Needs review"),
                row.get("gap_or_follow_up", "Needs review"),
                row.get("notes", NOT_PROVIDED),
            ]
            for row in rows
        ),
    )


def _provenance_table(rows: Iterable[Mapping[str, Any]]) -> str:
    return _table(
        ["Section", "Source / provenance", "Review status", "Gap / follow-up"],
        (
            [
                row.get("section", "Missing"),
                row.get("source_or_provenance", "Needs source"),
                row.get("review_status", "Needs review"),
                row.get("gap_or_follow_up", "Needs review"),
            ]
            for row in rows
        ),
    )


def _gap_table(rows: Iterable[Mapping[str, Any]]) -> str:
    return _table(
        ["Section", "Review status", "Recorded value", "Manual follow-up", "Notes"],
        (
            [
                row.get("section", "Missing"),
                row.get("review_status", "Needs review"),
                row.get("recorded_value", "Missing"),
                row.get("manual_follow_up", row.get("gap_or_follow_up", "Needs review")),
                row.get("notes", NOT_PROVIDED),
            ]
            for row in rows
        ),
    )


def _limitations_list(limitations: Iterable[Any]) -> str:
    clean_limitations = [_text(item) for item in limitations if _text(item, "")]
    if not clean_limitations:
        clean_limitations = [
            "Documentation-only readback for human review.",
            "No final vector sequence, protocol, biological recommendation, outcome forecast, or downstream-use judgment is included.",
        ]
    return "\n".join(f"- {_text(item)}" for item in clean_limitations)


def format_expression_vector_design_package_preview_markdown(preview: Mapping[str, Any] | None) -> str:
    """Format an R269 Expression Vector Design Package preview dictionary as Markdown.

    This is a read-only readback formatter. It does not export packages, generate
    vector sequences, choose components, provide procedure steps, or change data.
    """
    preview_data = _mapping(preview)
    identity = _mapping(preview_data.get("package_identity"))
    target = _mapping(preview_data.get("target_summary"))
    host = _mapping(preview_data.get("host_summary"))
    vector = _mapping(preview_data.get("vector_backbone_summary"))
    presenter = _mapping(preview_data.get("cassette_slot_rows_presenter"))
    presenter_summary = _mapping(presenter.get("summary"))
    cassette_rows = _list_of_mappings(preview_data.get("cassette_slot_rows"))
    sequence_rows = _list_of_mappings(preview_data.get("sequence_basic_checks"))
    provenance_rows = _list_of_mappings(preview_data.get("provenance_summary"))
    gap_rows = _list_of_mappings(preview_data.get("gap_follow_up_summary"))
    limitations = preview_data.get("package_limitations")

    package_title = _text(identity.get("package_title"), DEFAULT_TITLE)
    lines = [
        f"# {_cell(package_title)}",
        "",
        "## Package Identity",
        _field_table(
            [
                ("Package type", identity.get("package_type", DEFAULT_TITLE)),
                ("Package title", package_title),
                ("Package status", identity.get("package_status", "Needs review")),
                ("Source commit or version", identity.get("source_commit_or_version", NOT_PROVIDED)),
                ("Package ID", identity.get("package_id", NOT_PROVIDED)),
                ("Checksum algorithm", identity.get("checksum_algorithm", NOT_PROVIDED)),
                ("MD5", identity.get("md5", NOT_PROVIDED)),
                ("Identity boundary note", identity.get("identity_boundary_note", "Documentation-only identity readback for human review.")),
            ]
        ),
        "",
        "## Target Gene / CDS / Protein",
        _table(
            ["Field", "Value"],
            [
                ("Target name", target.get("target_name", "Missing")),
                ("CDS / protein value", target.get("cds_or_protein_value", "Missing")),
                ("Source / provenance", target.get("source_or_provenance", "Needs source")),
                ("Review status", target.get("review_status", "Needs review")),
                ("Gap / manual follow-up", target.get("gap_or_follow_up", "Needs review")),
                ("Notes", target.get("notes", NOT_PROVIDED)),
            ],
        ),
        "",
        "## Host / Expression System",
        _section_summary_table(host, "Host / expression system", "host_or_system"),
        "",
        "## Expression Cassette Slot Review",
        _field_table(
            [
                ("Presenter title", presenter.get("title", "Expression cassette slot rows")),
                ("Total slot rows", presenter_summary.get("total_slot_rows", len(cassette_rows))),
                ("Documented rows", presenter_summary.get("documented_rows", NOT_PROVIDED)),
                ("Manual follow-up rows", presenter_summary.get("manual_follow_up_rows", NOT_PROVIDED)),
                ("Optional not-provided rows", presenter_summary.get("optional_not_provided_rows", NOT_PROVIDED)),
                ("Documentation boundary note", presenter.get("documentation_boundary_note", "Documentation-only readback for human review.")),
            ]
        ),
        "",
        _cassette_slot_rows_table(cassette_rows),
        "",
        "## Vector / Backbone",
        _field_table(
            [
                ("Vector / backbone name", vector.get("vector_or_backbone_name", "Missing")),
                ("Source / provenance", vector.get("source_or_provenance", "Needs source")),
                ("Sequence availability", vector.get("sequence_availability", "Not provided")),
                ("Review status", vector.get("review_status", "Needs review")),
                ("Gap / manual follow-up", vector.get("gap_or_follow_up", "Needs review")),
                ("Notes", vector.get("notes", NOT_PROVIDED)),
            ]
        ),
        "",
        "## Sequence Basic Checks",
        _sequence_checks_table(sequence_rows),
        "",
        "## Source / Provenance Summary",
        _provenance_table(provenance_rows),
        "",
        "## Gap / Manual Follow-up Review",
        _gap_table(gap_rows),
        "",
        "## Package Limitations",
        _limitations_list(limitations if isinstance(limitations, Iterable) and not isinstance(limitations, (str, bytes, Mapping)) else []),
        "",
    ]
    return "\n".join(lines)
