from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
    normalize_generated_output_text,
)
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
)
from services.project_output_section_overview import (
    build_project_output_sections_overview,
    format_project_output_sections_overview_markdown,
)
from services.documentation_review_label_helper import format_review_next_label, review_next_body
from services.expression_construct_review_action_panel_presenter import (
    PANEL_BOUNDARY_NOTE,
    build_expression_construct_review_action_panel,
)
from services.placeholder_review_value import clean_review_value


PREVIEW_TITLE = "Project handoff package preview"
PREVIEW_SUBTITLE = (
    "Read-only preview for human handoff review; no export package is created here."
)
PREVIEW_BOUNDARY_NOTES = [
    PROJECT_OUTPUT_SCOPE_NOTE,
    "This is a package preview only for human handoff review.",
    "No export package is created here.",
    "Review source records before handoff.",
    "Review provenance notes before handoff.",
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE,
]
SNAPSHOT_REVIEW_CARD_TITLE = "Handoff snapshot review card"
SNAPSHOT_CHECKSUM_ALGORITHM = "MD5"
SNAPSHOT_BOUNDARY_NOTE = (
    "Documentation preview only; no export package is created here. "
    "The MD5 code is for preview matching only, not a security signature or certification."
)
REVIEW_SHEET_TITLE = "Project handoff review sheet"
REVIEW_SHEET_BOUNDARY_NOTE = (
    "Read-only review sheet copy view for documentation handoff review; "
    "no export package is created here and no file is generated here."
)
TRACEABILITY_MATRIX_TITLE = "Project handoff traceability matrix"
TRACEABILITY_MATRIX_BOUNDARY_NOTE = (
    "Read-only traceability matrix for documentation source review; "
    "no project data, package data, or saved records are changed here."
)
QR_VERIFICATION_TITLE = "Handoff QR verification preview"
QR_VERIFICATION_BOUNDARY_NOTE = (
    "Read-only QR verification payload for matching the same preview identity during human review. "
    "No export package is created here. No file or download is created here. "
    "The MD5 code is for preview matching only, not a security signature or certification."
)
QR_VERIFICATION_DEPENDENCY_DECISION = (
    "Payload-only fallback is used because the default dependency manifest does not include a QR rendering library."
)
QR_VERIFICATION_INTENDED_USE = (
    "Use this preview identity to match the same handoff snapshot during human review."
)
QR_VERIFICATION_PAYLOAD_HEADER = "BioDesign Studio handoff QR verification payload"
HANDOFF_WORKSPACE_TITLE = "Project handoff review workspace"
HANDOFF_WORKSPACE_BOUNDARY_NOTE = (
    "This workspace organizes local, read-only, documentation-only review surfaces for manual review. "
    "It does not create files, packages, exports, biology-use recommendations, validation claims, "
    "optimization claims, or wet-lab use judgments."
)
EXPRESSION_REVIEW_ACTION_PANEL_TITLE = "Expression construct review action panel"
EXPRESSION_REVIEW_ACTION_PANEL_NOTE = (
    "Compact read-only handoff readback reused from the Expression Construct Review action panel."
)
EXPRESSION_REVIEW_ACTION_PANEL_BOUNDARY_NOTE = (
    "This handoff readback reuses documentation follow-up cues only; it is not a biology-use "
    "recommendation, validation claim, optimization claim, or wet-lab use judgment."
)

_SURFACE_LABELS = {
    "construct_component_documentation": "construct/component documentation summary",
    "evidence_follow_up": "evidence follow-up summary",
    "promoter_source_review_gaps": "Component Library promoter asset source/review gap summary",
    "host_context_documentation": "host/context documentation summary",
    "project_review_report": "project review report summary",
}
_TRACEABILITY_SURFACE_LABELS = {
    "construct_component_documentation": "Expression Constructs",
    "evidence_follow_up": "Candidate Evidence Review",
    "promoter_source_review_gaps": "Component Library promoter asset source/review",
    "host_context_documentation": "Host/context documentation",
    "project_review_report": "Project Review Report",
    "handoff_review_sheet": "Handoff Review Sheet",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _review_text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return clean_review_value(value, fallback)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _markdown_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return _text(value, fallback).replace("|", "\\|").replace("\n", "<br>")


def _plain_text_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return " ".join(_text(value, fallback).replace("\r", "\n").split())


def _safe_qr_payload_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    text = _plain_text_value(_review_text(value, fallback), fallback)
    compact = re.sub(r"[^A-Za-z]", "", text)
    looks_like_sequence = len(compact) >= 24 and len(compact) >= max(1, int(len(text) * 0.8))
    if looks_like_sequence and (
        set(compact.upper()) <= set("ACGTUN")
        or set(compact.upper()) <= set("ACDEFGHIKLMNPQRSTVWY")
    ):
        return "WITHHELD_FOR_PREVIEW_METADATA_BOUNDARY"
    if re.search(r"[A-Za-z]:\\|/(?:home|users|var|etc|tmp)/", text, flags=re.IGNORECASE):
        return "WITHHELD_FOR_PREVIEW_METADATA_BOUNDARY"
    if re.search(r"\b(api[_ -]?key|credential|password|token|private)\b", text, flags=re.IGNORECASE):
        return "WITHHELD_FOR_PREVIEW_METADATA_BOUNDARY"
    return text[:120]


def _canonical_traceability_surface(value: Any) -> str:
    text = _text(value, "").casefold()
    if "expression construct" in text or "construct/component" in text:
        return _TRACEABILITY_SURFACE_LABELS["construct_component_documentation"]
    if "candidate evidence" in text or "evidence follow-up" in text:
        return _TRACEABILITY_SURFACE_LABELS["evidence_follow_up"]
    if "promoter" in text or "source/review" in text:
        return _TRACEABILITY_SURFACE_LABELS["promoter_source_review_gaps"]
    if "host" in text or "chassis" in text or "context documentation" in text:
        return _TRACEABILITY_SURFACE_LABELS["host_context_documentation"]
    if "review report" in text or "report markdown" in text:
        return _TRACEABILITY_SURFACE_LABELS["project_review_report"]
    if "review sheet" in text:
        return _TRACEABILITY_SURFACE_LABELS["handoff_review_sheet"]
    return _text(value, "Documentation source")


def _context_from_follow_up_row(row: Mapping[str, Any]) -> tuple[str, str, str]:
    issue = _text(row.get("issue_type"), "Documentation follow-up")
    note = _text(row.get("manual_follow_up_note"), "Review documentation context manually.")
    combined = f"{issue} {note} {_text(row.get('source_surface'))}".casefold()

    documentation_context = f"Manual documentation follow-up: {issue}"
    if "source" in combined or "reference" in combined:
        source_reference_context = "Source/reference context needs manual documentation follow-up."
    else:
        source_reference_context = "No source/reference context surfaced in this handoff row."

    if "provenance" in combined or "review" in combined:
        provenance_review_context = "Provenance/review context needs manual documentation follow-up."
    else:
        provenance_review_context = "No provenance/review context surfaced in this handoff row."
    return documentation_context, source_reference_context, provenance_review_context


def _traceability_row(
    *,
    source_surface: str,
    item_label: str,
    documentation_context: str,
    source_reference_context: str,
    provenance_review_context: str,
    manual_follow_up_status: str,
    where_to_review_next: str,
    included_in_review_sheet: str,
) -> dict[str, str]:
    return {
        "source_surface": source_surface,
        "item_label": item_label,
        "documentation_context": documentation_context,
        "source_reference_context": source_reference_context,
        "provenance_review_context": provenance_review_context,
        "manual_follow_up_status": manual_follow_up_status,
        "where_to_review_next": where_to_review_next,
        "included_in_review_sheet": included_in_review_sheet,
    }


def _normalize_preview_content(content: str) -> str:
    lines = str(content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _preview_section_count(markdown: str) -> int:
    return sum(1 for line in _normalize_preview_content(markdown).split("\n") if line.startswith(("## ", "### ")))


def _surface_item(key: str, label: str, count: int, note: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "manual_follow_up_count": count,
        "status": "Documentation follow-up visible" if count else "No visible follow-up",
        "note": note,
    }


def _build_included_documentation_preview(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    expression_count = _int(summary.get("expression_construct_documentation_follow_up_count"))
    candidate_count = _int(summary.get("candidate_evidence_follow_up_count"))
    promoter_count = _int(summary.get("promoter_source_review_follow_up_count"))
    host_count = _int(summary.get("host_context_documentation_follow_up_count"))
    report_available = bool(summary.get("report_markdown_available"))

    return [
        _surface_item(
            "construct_component_documentation",
            _SURFACE_LABELS["construct_component_documentation"],
            expression_count,
            "Construct and component documentation context is summarized for human review.",
        ),
        _surface_item(
            "evidence_follow_up",
            _SURFACE_LABELS["evidence_follow_up"],
            candidate_count,
            "Candidate evidence documentation follow-up is summarized for human review.",
        ),
        _surface_item(
            "promoter_source_review_gaps",
            _SURFACE_LABELS["promoter_source_review_gaps"],
            promoter_count,
            "Component Library promoter asset source metadata and review gaps are summarized for human review.",
        ),
        _surface_item(
            "host_context_documentation",
            _SURFACE_LABELS["host_context_documentation"],
            host_count,
            "Host/context documentation state is summarized for human review.",
        ),
        {
            "key": "project_review_report",
            "label": _SURFACE_LABELS["project_review_report"],
            "manual_follow_up_count": 0,
            "status": "Markdown available" if report_available else "Markdown not supplied",
            "note": (
                "Project Review Report Markdown is included as a read-only summary for human review."
                if report_available
                else "Project Review Report Markdown was not supplied to this preview."
            ),
        },
    ]


def _build_expression_construct_review_action_panel_readback(
    construct_review_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = _mapping(construct_review_payload)
    if "rows" in payload and "summary" in payload and "construct_component_review_summary" not in payload:
        payload = {
            "construct_component_review_summary": payload.get("summary") or {},
            "construct_component_gap_queue": payload.get("rows") or [],
            "review_gap_rows": payload.get("rows") or [],
            "summary_counts": {
                "review_gap_count": len(_rows(payload.get("rows"))),
            },
            "boundary_notes": payload.get("boundary_notes") or [],
            "message": payload.get("empty_state_message") or "",
        }

    panel = build_expression_construct_review_action_panel(payload)
    rows = [
        {
            "label": _review_text(row.get("label")),
            "status": _review_text(row.get("status")),
            "count": _int(row.get("count")),
            "review_action": _review_text(row.get("review_action")),
            "boundary_note": _review_text(row.get("boundary_note"), PANEL_BOUNDARY_NOTE),
        }
        for row in _rows(panel.get("rows"))
    ]
    action_summary_rows = [
        {
            "label": row["label"],
            "summary": (
                f"{row['status']}; count {row['count']}; "
                f"{row['review_action']}; boundary: {row['boundary_note']}"
            ),
            "traceability_context": (
                f"{row['label']}: {row['status']}; count {row['count']}; "
                f"{row['review_action']}"
            ),
        }
        for row in rows
    ]
    return normalize_generated_output_claims(
        {
            "title": EXPRESSION_REVIEW_ACTION_PANEL_TITLE,
            "status": _text(panel.get("status"), "NOT_AVAILABLE"),
            "review_summary_status": _review_text(panel.get("review_summary_status")),
            "note": EXPRESSION_REVIEW_ACTION_PANEL_NOTE,
            "source_presenter": (
                "services.expression_construct_review_action_panel_presenter."
                "build_expression_construct_review_action_panel"
            ),
            "rows": rows,
            "summary": {
                "row_count": len(rows),
                "manual_follow_up_count": _int(_mapping(panel.get("summary")).get("manual_follow_up_count")),
                "missing_documentation_count": _int(
                    _mapping(panel.get("summary")).get("missing_documentation_count")
                ),
                "source_provenance_follow_up_count": _int(
                    _mapping(panel.get("summary")).get("source_provenance_follow_up_count")
                ),
            },
            "action_summary": {
                "title": "Action summary",
                "row_count": len(action_summary_rows),
                "readback_note": (
                    "Consolidated readback for package preview, review sheet, and traceability review."
                ),
                "rows": action_summary_rows,
            },
            "boundary_note": EXPRESSION_REVIEW_ACTION_PANEL_BOUNDARY_NOTE,
        }
    )


def _format_expression_construct_review_action_summary_markdown(
    panel: Mapping[str, Any],
) -> str:
    action_summary = _mapping(panel.get("action_summary"))
    rows = _rows(action_summary.get("rows"))
    if not rows:
        return ""
    lines = [
        f"- {_markdown_value(action_summary.get('title'), 'Action summary')}: "
        f"{_int(action_summary.get('row_count'))} review-framed row(s).",
        f"- Readback note: {_markdown_value(action_summary.get('readback_note'))}",
    ]
    for row in rows:
        lines.append(
            f"  - {_markdown_value(row.get('label'))}: {_markdown_value(row.get('summary'))}"
        )
    return "\n".join(lines)


def _format_expression_construct_review_action_summary_plain_text(
    panel: Mapping[str, Any],
) -> list[str]:
    action_summary = _mapping(panel.get("action_summary"))
    rows = _rows(action_summary.get("rows"))
    if not rows:
        return []
    lines = [
        f"{_plain_text_value(action_summary.get('title'), 'Action summary')}: "
        f"{_int(action_summary.get('row_count'))} review-framed row(s).",
        f"Readback note: {_plain_text_value(action_summary.get('readback_note'))}",
    ]
    for row in rows:
        lines.append(
            f"- {_plain_text_value(row.get('label'))}: {_plain_text_value(row.get('summary'))}"
        )
    return lines


def _format_expression_construct_review_action_panel_markdown(preview: Mapping[str, Any]) -> str:
    panel = _mapping(preview.get("expression_construct_review_action_panel"))
    if not panel:
        return ""
    lines = [
        f"### {_markdown_value(panel.get('title'), EXPRESSION_REVIEW_ACTION_PANEL_TITLE)}",
        f"- Status: {_markdown_value(panel.get('status'))}",
        f"- Review summary status: {_markdown_value(panel.get('review_summary_status'))}",
        f"- Note: {_markdown_value(panel.get('note'), EXPRESSION_REVIEW_ACTION_PANEL_NOTE)}",
        f"- Boundary: {_markdown_value(panel.get('boundary_note'), EXPRESSION_REVIEW_ACTION_PANEL_BOUNDARY_NOTE)}",
    ]
    action_summary = _format_expression_construct_review_action_summary_markdown(panel)
    if action_summary:
        lines += ["", action_summary]
    rows = _rows(panel.get("rows"))
    if rows:
        lines += [
            "| Action row | Status | Count | Review action | Boundary |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_value(row.get(key))
                    for key in ("label", "status", "count", "review_action", "boundary_note")
                )
                + " |"
            )
    else:
        lines.append("- No expression construct review action rows are visible in this preview.")
    return "\n".join(lines)


def _build_snapshot_review_card(preview: Mapping[str, Any], normalized_content: str) -> dict[str, Any]:
    cover = _mapping(preview.get("handoff_cover_summary"))
    surfaces = [_text(surface) for surface in cover.get("documentation_surfaces_included") or []]
    checksum = hashlib.md5(normalized_content.encode("utf-8")).hexdigest()
    return {
        "title": SNAPSHOT_REVIEW_CARD_TITLE,
        "snapshot_title": _text(preview.get("title"), PREVIEW_TITLE),
        "snapshot_checksum": checksum,
        "snapshot_id": f"{SNAPSHOT_CHECKSUM_ALGORITHM.lower()}:{checksum}",
        "snapshot_checksum_algorithm": SNAPSHOT_CHECKSUM_ALGORITHM,
        "snapshot_included_surface_count": len(surfaces),
        "snapshot_included_surfaces": surfaces,
        "snapshot_manual_follow_up_count": _int(cover.get("total_manual_follow_up_items")),
        "snapshot_section_count": _preview_section_count(normalized_content),
        "snapshot_content_length": len(normalized_content),
        "boundary_note": SNAPSHOT_BOUNDARY_NOTE,
    }


def _format_qr_verification_payload_text(payload: Mapping[str, Any]) -> str:
    lines = [
        QR_VERIFICATION_PAYLOAD_HEADER,
        f"Snapshot title: {_safe_qr_payload_value(payload.get('snapshot_title'))}",
        f"Project label: {_safe_qr_payload_value(payload.get('project_label'))}",
        f"Snapshot ID: {_safe_qr_payload_value(payload.get('snapshot_id'))}",
        f"Checksum algorithm: {_safe_qr_payload_value(payload.get('checksum_algorithm'))}",
        f"MD5 preview checksum: {_safe_qr_payload_value(payload.get('snapshot_checksum'))}",
        f"Included surfaces count: {_int(payload.get('included_surfaces_count'))}",
        f"Manual follow-up count: {_int(payload.get('manual_follow_up_count'))}",
        f"Boundary: {_safe_qr_payload_value(payload.get('boundary_note'), QR_VERIFICATION_BOUNDARY_NOTE)}",
        "Boundary: No export package is created here.",
        "Boundary: No file or download is created here.",
        "Boundary: MD5 code for preview matching only, not a security signature or certification.",
    ]
    return "\n".join(lines)


def _format_qr_verification_payload_markdown(preview: Mapping[str, Any]) -> str:
    payload = _mapping(preview.get("qr_verification_payload"))
    lines = [
        f"### {QR_VERIFICATION_TITLE}",
        f"- {_markdown_value(preview.get('qr_verification_intended_use'), QR_VERIFICATION_INTENDED_USE)}",
        f"- {_markdown_value(preview.get('qr_verification_dependency_decision'), QR_VERIFICATION_DEPENDENCY_DECISION)}",
        f"- {_markdown_value(preview.get('qr_verification_boundary_note'), QR_VERIFICATION_BOUNDARY_NOTE)}",
        f"- Snapshot ID: {_markdown_value(payload.get('snapshot_id'))}",
        f"- Checksum algorithm: {_markdown_value(payload.get('checksum_algorithm'))}",
        f"- MD5 preview checksum: {_markdown_value(payload.get('snapshot_checksum'))}",
        f"- Included surfaces count: {_int(payload.get('included_surfaces_count'))}",
        f"- Manual follow-up count: {_int(payload.get('manual_follow_up_count'))}",
        "",
        "```text",
        _text(preview.get("qr_verification_payload_text")),
        "```",
    ]
    return "\n".join(lines)


def _build_qr_verification_preview(
    preview: Mapping[str, Any],
    review_card: Mapping[str, Any],
) -> dict[str, Any]:
    cover = _mapping(preview.get("handoff_cover_summary"))
    payload = {
        "payload_title": QR_VERIFICATION_PAYLOAD_HEADER,
        "snapshot_title": _safe_qr_payload_value(review_card.get("snapshot_title"), PREVIEW_TITLE),
        "project_label": _safe_qr_payload_value(cover.get("project_label"), "Active pathway documentation project"),
        "snapshot_id": _safe_qr_payload_value(review_card.get("snapshot_id")),
        "checksum_algorithm": _safe_qr_payload_value(review_card.get("snapshot_checksum_algorithm"), SNAPSHOT_CHECKSUM_ALGORITHM),
        "snapshot_checksum": _safe_qr_payload_value(review_card.get("snapshot_checksum")),
        "included_surfaces_count": _int(review_card.get("snapshot_included_surface_count")),
        "manual_follow_up_count": _int(review_card.get("snapshot_manual_follow_up_count")),
        "boundary_note": QR_VERIFICATION_BOUNDARY_NOTE,
    }
    payload_text = _format_qr_verification_payload_text(payload)
    return {
        "qr_verification_title": QR_VERIFICATION_TITLE,
        "qr_verification_payload": payload,
        "qr_verification_payload_text": payload_text,
        "qr_verification_boundary_note": QR_VERIFICATION_BOUNDARY_NOTE,
        "qr_verification_dependency_decision": QR_VERIFICATION_DEPENDENCY_DECISION,
        "qr_verification_intended_use": QR_VERIFICATION_INTENDED_USE,
    }


def _build_traceability_matrix_rows(preview: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    review_sheet_sections = {
        _text(section.get("key"))
        for section in _rows(preview.get("review_sheet_sections"))
    }

    for item in _rows(preview.get("included_documentation_preview")):
        label = _text(item.get("label"), "Documentation surface")
        source_surface = _canonical_traceability_surface(label)
        count = _int(item.get("manual_follow_up_count"))
        status = "Manual documentation follow-up visible" if count else _review_text(item.get("status"), "No visible follow-up")
        item_note = _review_text(item.get("note"), "Documentation surface available for review.")
        source_context = (
            "Source/reference context included in this documentation surface summary."
            if "source" in label.casefold() or source_surface in {
                _TRACEABILITY_SURFACE_LABELS["construct_component_documentation"],
                _TRACEABILITY_SURFACE_LABELS["promoter_source_review_gaps"],
            }
            else "Source/reference context not surfaced by this summary row."
        )
        provenance_context = (
            "Provenance/review context included in this documentation surface summary."
            if "review" in label.casefold() or source_surface in {
                _TRACEABILITY_SURFACE_LABELS["evidence_follow_up"],
                _TRACEABILITY_SURFACE_LABELS["promoter_source_review_gaps"],
                _TRACEABILITY_SURFACE_LABELS["project_review_report"],
            }
            else "Provenance/review context not surfaced by this summary row."
        )
        rows.append(
            _traceability_row(
                source_surface=source_surface,
                item_label=label,
                documentation_context=item_note,
                source_reference_context=source_context,
                provenance_review_context=provenance_context,
                manual_follow_up_status=status,
                where_to_review_next=format_review_next_label(source_surface),
                included_in_review_sheet="Yes - included in review sheet handoff summary",
            )
        )

    for row in _rows(preview.get("manual_follow_up_queue")):
        documentation_context, source_context, provenance_context = _context_from_follow_up_row(row)
        rows.append(
            _traceability_row(
                source_surface=_canonical_traceability_surface(row.get("source_surface")),
                item_label=_text(row.get("item_label"), "Documentation review item"),
                documentation_context=documentation_context,
                source_reference_context=source_context,
                provenance_review_context=provenance_context,
                manual_follow_up_status=_review_text(
                    row.get("manual_follow_up_note"),
                    "Manual documentation follow-up is visible for this item.",
                ),
                where_to_review_next=format_review_next_label(
                    row.get("where_to_review_next"),
                    "Project review handoff center",
                ),
                included_in_review_sheet="Yes - included in review sheet manual follow-up queue",
            )
        )

    for section in _rows(preview.get("review_sheet_sections")):
        rows.append(
            _traceability_row(
                source_surface=_TRACEABILITY_SURFACE_LABELS["handoff_review_sheet"],
                item_label=_text(section.get("label"), "Review sheet section"),
                documentation_context=_text(section.get("description"), "Review sheet section available for copy view."),
                source_reference_context="Source/reference context follows the source sections included in this review sheet.",
                provenance_review_context="Provenance/review context follows the source sections included in this review sheet.",
                manual_follow_up_status="Included for read-only documentation handoff review.",
                where_to_review_next=format_review_next_label("Project handoff review sheet"),
                included_in_review_sheet=(
                    "Yes - included in review sheet"
                    if _text(section.get("key")) in review_sheet_sections
                    else "No"
                ),
            )
        )

    panel = _mapping(preview.get("expression_construct_review_action_panel"))
    for row in _rows(panel.get("rows")):
        action_summary_row = next(
            (
                summary_row
                for summary_row in _rows(_mapping(panel.get("action_summary")).get("rows"))
                if _text(summary_row.get("label")) == _text(row.get("label"))
            ),
            {},
        )
        rows.append(
            _traceability_row(
                source_surface="Expression Constructs",
                item_label=_text(row.get("label"), "Expression construct review action"),
                documentation_context=_review_text(
                    action_summary_row.get("traceability_context") or row.get("review_action"),
                    "Expression construct review action panel row available for documentation review.",
                ),
                source_reference_context="Source/reference context follows the reused expression construct action panel.",
                provenance_review_context="Provenance/review context follows the reused expression construct action panel.",
                manual_follow_up_status=_review_text(row.get("status"), "Read-only documentation review cue"),
                where_to_review_next=format_review_next_label("Expression Constructs"),
                included_in_review_sheet="Yes - included in review sheet expression construct action panel",
            )
        )

    if not rows:
        rows.append(
            _traceability_row(
                source_surface="Documentation source",
                item_label="No visible handoff items",
                documentation_context="No handoff traceability rows are visible from the supplied review queues.",
                source_reference_context="Manual documentation follow-up is needed if source/reference context should be recorded.",
                provenance_review_context="Manual documentation follow-up is needed if provenance/review context should be recorded.",
                manual_follow_up_status="No visible follow-up",
                where_to_review_next=format_review_next_label("Project review handoff center"),
                included_in_review_sheet="No",
            )
        )
    return rows


def _build_traceability_matrix_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_source_surface: dict[str, int] = {}
    by_manual_follow_up_status: dict[str, int] = {}
    included_count = 0
    source_reference_follow_up_count = 0
    provenance_review_follow_up_count = 0

    for row in rows:
        source_surface = _text(row.get("source_surface"), "Documentation source")
        status = _text(row.get("manual_follow_up_status"), "NOT_AVAILABLE")
        by_source_surface[source_surface] = by_source_surface.get(source_surface, 0) + 1
        by_manual_follow_up_status[status] = by_manual_follow_up_status.get(status, 0) + 1
        if _text(row.get("included_in_review_sheet"), "No").casefold().startswith("yes"):
            included_count += 1
        if "follow-up" in _text(row.get("source_reference_context")).casefold():
            source_reference_follow_up_count += 1
        if "follow-up" in _text(row.get("provenance_review_context")).casefold():
            provenance_review_follow_up_count += 1

    return {
        "row_count": len(rows),
        "included_in_review_sheet_count": included_count,
        "source_reference_context_follow_up_count": source_reference_follow_up_count,
        "provenance_review_context_follow_up_count": provenance_review_follow_up_count,
        "by_source_surface": by_source_surface,
        "by_manual_follow_up_status": by_manual_follow_up_status,
        "boundary_note": TRACEABILITY_MATRIX_BOUNDARY_NOTE,
    }


def _handoff_workspace_row(
    *,
    workspace_area: str,
    current_status: str,
    key_count_or_identity: str,
    review_surface: str,
    where_to_inspect_next: str,
    boundary_note: str,
) -> dict[str, str]:
    return {
        "workspace_area": workspace_area,
        "current_status": current_status,
        "key_count_or_identity": key_count_or_identity,
        "review_surface": review_surface,
        "where_to_inspect_next": where_to_inspect_next,
        "boundary_note": boundary_note,
    }


def handoff_workspace_nav_rows(preview: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return deterministic read-only navigation rows for the handoff review workspace."""
    preview = normalize_generated_output_claims(preview)
    cover = _mapping(preview.get("handoff_cover_summary"))
    card = _mapping(preview.get("snapshot_review_card"))
    payload = _mapping(preview.get("qr_verification_payload"))
    traceability_summary = _mapping(preview.get("traceability_matrix_summary"))
    included_surfaces = cover.get("documentation_surfaces_included") or []
    manual_follow_up_count = _int(cover.get("total_manual_follow_up_items"))
    review_sheet_markdown_status = "Markdown copy view available" if _text(preview.get("review_sheet_markdown"), "") else "Markdown copy view not available"
    review_sheet_plain_text_status = "Plain-text copy view available" if _text(preview.get("review_sheet_plain_text"), "") else "Plain-text copy view not available"
    qr_status = "QR payload preview available" if payload else "QR payload preview not available"
    report_row = next(
        (
            row
            for row in _rows(preview.get("included_documentation_preview"))
            if _text(row.get("key")) == "project_review_report"
        ),
        {},
    )

    return normalize_generated_output_claims([
        _handoff_workspace_row(
            workspace_area="Handoff Center",
            current_status=_project_review_status(cover),
            key_count_or_identity=f"{manual_follow_up_count} manual follow-up item(s)",
            review_surface="Project review handoff center",
            where_to_inspect_next="Follow-up queue overview and handoff checklist",
            boundary_note="Read-only project-level handoff summary; no file or download is created here.",
        ),
        _handoff_workspace_row(
            workspace_area="Package Preview",
            current_status=_text(preview.get("status"), "NOT_AVAILABLE"),
            key_count_or_identity=f"{len(included_surfaces)} included documentation surface(s)",
            review_surface="Project handoff package preview",
            where_to_inspect_next="Included documentation preview and Markdown handoff preview",
            boundary_note="Preview-only package preview; no export package is created here.",
        ),
        _handoff_workspace_row(
            workspace_area="Snapshot / MD5 / QR Payload",
            current_status=qr_status,
            key_count_or_identity=(
                f"MD5 {card.get('snapshot_checksum') or payload.get('snapshot_checksum') or 'NOT_AVAILABLE'}; "
                f"snapshot {card.get('snapshot_id') or payload.get('snapshot_id') or 'NOT_AVAILABLE'}"
            ),
            review_surface="Handoff snapshot review card and Handoff QR verification preview",
            where_to_inspect_next="Snapshot included surfaces and QR verification payload",
            boundary_note="MD5/QR payload for preview matching only; not a security signature or certification.",
        ),
        _handoff_workspace_row(
            workspace_area="Review Sheet Copy View",
            current_status=f"{review_sheet_markdown_status}; {review_sheet_plain_text_status}",
            key_count_or_identity=f"{len(_rows(preview.get('review_sheet_sections')))} review sheet section(s)",
            review_surface="Project handoff review sheet",
            where_to_inspect_next="Markdown copy view and Plain-text copy view",
            boundary_note="Copy-only review sheet; no export package, file, or download is created here.",
        ),
        _handoff_workspace_row(
            workspace_area="Traceability Matrix",
            current_status="Read-only traceability matrix available",
            key_count_or_identity=f"{_int(traceability_summary.get('row_count'))} matrix row(s)",
            review_surface="Project handoff traceability matrix",
            where_to_inspect_next="Source surface, manual follow-up status, and where-to-review-next coverage",
            boundary_note="Read-only traceability review; no project data, package data, or saved records are changed here.",
        ),
        _handoff_workspace_row(
            workspace_area="Project Review Report Markdown",
            current_status=_text(report_row.get("status"), "Markdown not supplied"),
            key_count_or_identity=(
                "Documentation handoff summary available"
                if _text(report_row.get("status"), "").casefold() == "markdown available"
                else "Documentation handoff summary not supplied"
            ),
            review_surface="Project Review Report Markdown",
            where_to_inspect_next="Project review report summary and Markdown handoff preview",
            boundary_note="Report remains read-only documentation output; no biological recommendation claim is made.",
        ),
    ])


def handoff_workspace_summary(preview: Mapping[str, Any]) -> dict[str, Any]:
    preview = normalize_generated_output_claims(preview)
    rows = handoff_workspace_nav_rows(preview)
    cover = _mapping(preview.get("handoff_cover_summary"))
    traceability_summary = _mapping(preview.get("traceability_matrix_summary"))
    return normalize_generated_output_claims({
        "title": HANDOFF_WORKSPACE_TITLE,
        "status": _text(preview.get("status"), "NOT_AVAILABLE"),
        "workspace_area_count": len(rows),
        "total_manual_follow_up_items": _int(cover.get("total_manual_follow_up_items")),
        "included_documentation_surface_count": len(cover.get("documentation_surfaces_included") or []),
        "traceability_matrix_row_count": _int(traceability_summary.get("row_count")),
        "snapshot_checksum": _text(preview.get("snapshot_checksum")),
        "qr_payload_status": "AVAILABLE" if _mapping(preview.get("qr_verification_payload")) else "NOT_AVAILABLE",
        "boundary_note": HANDOFF_WORKSPACE_BOUNDARY_NOTE,
    })


def handoff_workspace_markdown(preview: Mapping[str, Any]) -> str:
    preview = normalize_generated_output_claims(preview)
    summary = handoff_workspace_summary(preview)
    rows = handoff_workspace_nav_rows(preview)
    lines = [
        f"## {HANDOFF_WORKSPACE_TITLE}",
        f"- Status: {_markdown_value(summary.get('status'))}",
        f"- Workspace areas: {_int(summary.get('workspace_area_count'))}",
        f"- Total manual follow-up items: {_int(summary.get('total_manual_follow_up_items'))}",
        f"- Included documentation surfaces: {_int(summary.get('included_documentation_surface_count'))}",
        f"- Traceability matrix rows: {_int(summary.get('traceability_matrix_row_count'))}",
        f"- Snapshot checksum: {_markdown_value(summary.get('snapshot_checksum'))}",
        f"- QR payload status: {_markdown_value(summary.get('qr_payload_status'))}",
        f"- Boundary: {_markdown_value(summary.get('boundary_note'), HANDOFF_WORKSPACE_BOUNDARY_NOTE)}",
        "",
        "| Workspace area | Current status | Key count or identity | Review surface | Where to inspect next | Boundary note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _markdown_value(row.get(key))
                for key in (
                    "workspace_area",
                    "current_status",
                    "key_count_or_identity",
                    "review_surface",
                    "where_to_inspect_next",
                    "boundary_note",
                )
            )
            + " |"
        )
    return "\n".join(lines)


def format_project_handoff_traceability_matrix_markdown(preview: Mapping[str, Any]) -> str:
    summary = _mapping(preview.get("traceability_matrix_summary"))
    rows = _rows(preview.get("traceability_matrix_rows"))
    lines = [
        f"### {TRACEABILITY_MATRIX_TITLE}",
        f"- {_markdown_value(summary.get('boundary_note'), TRACEABILITY_MATRIX_BOUNDARY_NOTE)}",
        f"- Matrix rows: {_int(summary.get('row_count'))}",
        f"- Included in review sheet: {_int(summary.get('included_in_review_sheet_count'))}",
        f"- Source/reference context follow-up: {_int(summary.get('source_reference_context_follow_up_count'))}",
        f"- Provenance/review context follow-up: {_int(summary.get('provenance_review_context_follow_up_count'))}",
        "",
        "| Source surface | Item label | Documentation context | Source/reference context | Provenance/review context | Manual follow-up status | Review next | Included in review sheet |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _markdown_value(row.get(key))
                for key in (
                    "source_surface",
                    "item_label",
                    "documentation_context",
                    "source_reference_context",
                    "provenance_review_context",
                    "manual_follow_up_status",
                    "where_to_review_next",
                    "included_in_review_sheet",
                )
            )
            + " |"
        )
    return "\n".join(lines)


def format_project_handoff_traceability_matrix_plain_text(preview: Mapping[str, Any]) -> str:
    summary = _mapping(preview.get("traceability_matrix_summary"))
    rows = _rows(preview.get("traceability_matrix_rows"))
    lines = [
        TRACEABILITY_MATRIX_TITLE,
        _plain_text_value(summary.get("boundary_note"), TRACEABILITY_MATRIX_BOUNDARY_NOTE),
        f"Matrix rows: {_int(summary.get('row_count'))}",
        f"Included in review sheet: {_int(summary.get('included_in_review_sheet_count'))}",
        f"Source/reference context follow-up: {_int(summary.get('source_reference_context_follow_up_count'))}",
        f"Provenance/review context follow-up: {_int(summary.get('provenance_review_context_follow_up_count'))}",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{index}. Source surface: {_plain_text_value(row.get('source_surface'))}",
                f"   Item label: {_plain_text_value(row.get('item_label'))}",
                f"   Documentation context: {_plain_text_value(row.get('documentation_context'))}",
                f"   Source/reference context: {_plain_text_value(row.get('source_reference_context'))}",
                f"   Provenance/review context: {_plain_text_value(row.get('provenance_review_context'))}",
                f"   Manual follow-up status: {_plain_text_value(row.get('manual_follow_up_status'))}",
                f"   Review next: {_plain_text_value(review_next_body(row.get('where_to_review_next')))}",
                f"   Included in review sheet: {_plain_text_value(row.get('included_in_review_sheet'))}",
            ]
        )
    return "\n".join(lines)


def _project_review_status(cover: Mapping[str, Any]) -> str:
    follow_up_count = _int(cover.get("total_manual_follow_up_items"))
    if follow_up_count:
        return (
            f"Documentation review has {follow_up_count} visible manual follow-up item(s) "
            "for human review before handoff."
        )
    return "Documentation review has no visible manual follow-up items in this preview."


def _review_sheet_sections() -> list[dict[str, str]]:
    return [
        {
            "key": "snapshot_review_card",
            "label": "Snapshot review card",
            "description": "Snapshot title, MD5 preview checksum, included surfaces, follow-up count, and preview size.",
        },
        {
            "key": "handoff_summary",
            "label": "Handoff summary",
            "description": "Documentation surfaces, manual follow-up count, and documentation review status.",
        },
        {
            "key": "handoff_checklist",
            "label": "Handoff checklist",
            "description": "Read-only checklist for source, provenance, evidence, promoter, host, and report review context.",
        },
        {
            "key": "manual_follow_up_queue",
            "label": "Manual follow-up queue",
            "description": "Source surface, item label, issue type, manual follow-up note, and next review surface.",
        },
        {
            "key": "expression_construct_review_action_panel",
            "label": EXPRESSION_REVIEW_ACTION_PANEL_TITLE,
            "description": (
                "Read-only Expression Construct Review action panel rows reused for handoff review."
            ),
        },
        {
            "key": "traceability_matrix",
            "label": "Project handoff traceability matrix",
            "description": "Source-to-follow-up mapping with documentation, source/reference, provenance/review, next-review, and review-sheet context.",
        },
        {
            "key": "qr_verification_preview",
            "label": "Handoff QR verification preview",
            "description": "Read-only QR verification payload for matching the same preview identity during human review.",
        },
        {
            "key": "markdown_copy_view",
            "label": "Markdown copy view",
            "description": "Read-only Markdown block for copying into a message, document, or review note.",
        },
        {
            "key": "plain_text_copy_view",
            "label": "Plain-text copy view",
            "description": "Read-only plain-text block for chat, email, or meeting notes.",
        },
    ]


def format_project_handoff_review_sheet_markdown(preview: Mapping[str, Any]) -> str:
    cover = _mapping(preview.get("handoff_cover_summary"))
    card = _mapping(preview.get("snapshot_review_card"))
    lines = [
        f"## {REVIEW_SHEET_TITLE}",
        "- Read-only review sheet copy view for documentation handoff review.",
        "- No export package is created here.",
        "- No file is generated here.",
        "- MD5 code for preview matching only, not a security signature or certification.",
        "",
        "### Snapshot review card",
        f"- Snapshot title: {_markdown_value(card.get('snapshot_title'))}",
        f"- MD5 preview checksum: {_markdown_value(card.get('snapshot_checksum'))}",
        f"- Snapshot ID: {_markdown_value(card.get('snapshot_id'))}",
        f"- Included surfaces count: {_int(card.get('snapshot_included_surface_count'))}",
        "- Included surfaces: "
        + ", ".join(_markdown_value(surface) for surface in card.get("snapshot_included_surfaces") or []),
        f"- Manual follow-up count: {_int(card.get('snapshot_manual_follow_up_count'))}",
        f"- Section count: {_int(card.get('snapshot_section_count'))}",
        f"- Content length: {_int(card.get('snapshot_content_length'))}",
        f"- Preview-only boundary note: {_markdown_value(card.get('boundary_note'), SNAPSHOT_BOUNDARY_NOTE)}",
        "",
        "### Handoff summary",
        f"- Project label: {_markdown_value(cover.get('project_label'))}",
        "- Documentation surfaces included: "
        + ", ".join(_markdown_value(surface) for surface in cover.get("documentation_surfaces_included") or []),
        f"- Current manual follow-up item count: {_int(cover.get('total_manual_follow_up_items'))}",
        f"- Documentation review status: {_markdown_value(_project_review_status(cover))}",
        "",
        "### Handoff checklist",
    ]
    for item in _rows(preview.get("handoff_checklist")):
        lines.append(
            f"- {_markdown_value(item.get('label'))}: {_markdown_value(item.get('status'))} - "
            f"{_markdown_value(item.get('note'))}"
        )

    lines += ["", "### Manual follow-up queue"]
    queue_rows = _rows(preview.get("manual_follow_up_queue"))
    if queue_rows:
        lines += [
            "| Source surface | Item label | Issue type | Manual follow-up note | Review next |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in queue_rows:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_value(row.get(key))
                    for key in (
                        "source_surface",
                        "item_label",
                        "issue_type",
                        "manual_follow_up_note",
                        "where_to_review_next",
                    )
                )
                + " |"
            )
    else:
        lines.append("- No manual follow-up items are visible from the supplied review queues.")

    panel_markdown = _format_expression_construct_review_action_panel_markdown(preview)
    if panel_markdown:
        lines += ["", panel_markdown]

    traceability_markdown = _text(preview.get("traceability_matrix_markdown"), "")
    if traceability_markdown:
        lines += ["", traceability_markdown]

    qr_payload_markdown = _text(preview.get("qr_verification_payload_markdown"), "")
    if qr_payload_markdown:
        lines += ["", qr_payload_markdown]

    lines += [
        "",
        "### Copy view boundary",
        f"- {_markdown_value(preview.get('review_sheet_boundary_note'), REVIEW_SHEET_BOUNDARY_NOTE)}",
        "- This copy view does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state.",
    ]
    return "\n".join(lines)


def format_project_handoff_review_sheet_plain_text(preview: Mapping[str, Any]) -> str:
    cover = _mapping(preview.get("handoff_cover_summary"))
    card = _mapping(preview.get("snapshot_review_card"))
    lines = [
        REVIEW_SHEET_TITLE,
        "Read-only review sheet copy view for documentation handoff review.",
        "No export package is created here.",
        "No file is generated here.",
        "MD5 code for preview matching only, not a security signature or certification.",
        "",
        "Snapshot review card",
        f"Snapshot title: {_plain_text_value(card.get('snapshot_title'))}",
        f"MD5 preview checksum: {_plain_text_value(card.get('snapshot_checksum'))}",
        f"Snapshot ID: {_plain_text_value(card.get('snapshot_id'))}",
        f"Included surfaces count: {_int(card.get('snapshot_included_surface_count'))}",
        "Included surfaces: "
        + ", ".join(_plain_text_value(surface) for surface in card.get("snapshot_included_surfaces") or []),
        f"Manual follow-up count: {_int(card.get('snapshot_manual_follow_up_count'))}",
        f"Section count: {_int(card.get('snapshot_section_count'))}",
        f"Content length: {_int(card.get('snapshot_content_length'))}",
        f"Preview-only boundary note: {_plain_text_value(card.get('boundary_note'), SNAPSHOT_BOUNDARY_NOTE)}",
        "",
        "Handoff summary",
        f"Project label: {_plain_text_value(cover.get('project_label'))}",
        "Documentation surfaces included: "
        + ", ".join(_plain_text_value(surface) for surface in cover.get("documentation_surfaces_included") or []),
        f"Current manual follow-up item count: {_int(cover.get('total_manual_follow_up_items'))}",
        f"Documentation review status: {_plain_text_value(_project_review_status(cover))}",
        "",
        "Handoff checklist",
    ]
    for item in _rows(preview.get("handoff_checklist")):
        lines.append(
            f"- {_plain_text_value(item.get('label'))}: {_plain_text_value(item.get('status'))} - "
            f"{_plain_text_value(item.get('note'))}"
        )

    lines += ["", "Manual follow-up queue"]
    queue_rows = _rows(preview.get("manual_follow_up_queue"))
    if queue_rows:
        for index, row in enumerate(queue_rows, start=1):
            lines.extend(
                [
                    f"{index}. Source surface: {_plain_text_value(row.get('source_surface'))}",
                    f"   Item label: {_plain_text_value(row.get('item_label'))}",
                    f"   Issue type: {_plain_text_value(row.get('issue_type'))}",
                    f"   Manual follow-up note: {_plain_text_value(row.get('manual_follow_up_note'))}",
                    f"   Review next: {_plain_text_value(review_next_body(row.get('where_to_review_next')))}",
                ]
            )
    else:
        lines.append("No manual follow-up items are visible from the supplied review queues.")

    panel = _mapping(preview.get("expression_construct_review_action_panel"))
    panel_rows = _rows(panel.get("rows"))
    if panel:
        lines += [
            "",
            _plain_text_value(panel.get("title"), EXPRESSION_REVIEW_ACTION_PANEL_TITLE),
            f"Status: {_plain_text_value(panel.get('status'))}",
            f"Review summary status: {_plain_text_value(panel.get('review_summary_status'))}",
            _plain_text_value(panel.get("note"), EXPRESSION_REVIEW_ACTION_PANEL_NOTE),
            _plain_text_value(panel.get("boundary_note"), EXPRESSION_REVIEW_ACTION_PANEL_BOUNDARY_NOTE),
        ]
        summary_lines = _format_expression_construct_review_action_summary_plain_text(panel)
        if summary_lines:
            lines.extend(["", *summary_lines])
        for index, row in enumerate(panel_rows, start=1):
            lines.extend(
                [
                    f"{index}. Action row: {_plain_text_value(row.get('label'))}",
                    f"   Status: {_plain_text_value(row.get('status'))}",
                    f"   Count: {_int(row.get('count'))}",
                    f"   Review action: {_plain_text_value(row.get('review_action'))}",
                ]
            )

    traceability_plain_text = _text(preview.get("traceability_matrix_plain_text"), "")
    if traceability_plain_text:
        lines += ["", traceability_plain_text]

    qr_payload_text = _text(preview.get("qr_verification_payload_text"), "")
    if qr_payload_text:
        lines += ["", QR_VERIFICATION_TITLE, qr_payload_text]

    lines += [
        "",
        "Copy view boundary",
        _plain_text_value(preview.get("review_sheet_boundary_note"), REVIEW_SHEET_BOUNDARY_NOTE),
        "This copy view does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state.",
    ]
    return "\n".join(lines)


def format_project_handoff_package_preview_markdown(preview: Mapping[str, Any]) -> str:
    cover = _mapping(preview.get("handoff_cover_summary"))
    lines = [
        "## Project handoff package preview",
        "- Read-only preview for human handoff review.",
        "- No export package is created here.",
        f"- Project label: {_markdown_value(cover.get('project_label'))}",
        f"- Total manual follow-up items: {_int(cover.get('total_manual_follow_up_items'))}",
        "- Documentation surfaces included: "
        + ", ".join(_markdown_value(surface) for surface in cover.get("documentation_surfaces_included") or []),
        "",
        "### Included documentation preview",
    ]
    overview_markdown = format_project_output_sections_overview_markdown(
        preview.get("output_sections_overview")
    )
    if overview_markdown:
        lines += ["", overview_markdown]

    review_card = _mapping(preview.get("snapshot_review_card"))
    if review_card:
        lines += [
            "",
            f"### {_markdown_value(review_card.get('title'), SNAPSHOT_REVIEW_CARD_TITLE)}",
            f"- Snapshot title: {_markdown_value(review_card.get('snapshot_title'))}",
            f"- Snapshot ID: {_markdown_value(review_card.get('snapshot_id'))}",
            f"- Preview checksum: {_markdown_value(review_card.get('snapshot_checksum'))}",
            f"- Checksum algorithm: {_markdown_value(review_card.get('snapshot_checksum_algorithm'))}",
            f"- Included documentation surfaces count: {_int(review_card.get('snapshot_included_surface_count'))}",
            "- Included documentation surfaces: "
            + ", ".join(_markdown_value(surface) for surface in review_card.get("snapshot_included_surfaces") or []),
            f"- Manual follow-up item count: {_int(review_card.get('snapshot_manual_follow_up_count'))}",
            f"- Preview section count: {_int(review_card.get('snapshot_section_count'))}",
            f"- Preview content length: {_int(review_card.get('snapshot_content_length'))}",
            f"- Boundary note: {_markdown_value(review_card.get('boundary_note'), SNAPSHOT_BOUNDARY_NOTE)}",
        ]

    for item in _rows(preview.get("included_documentation_preview")):
        lines.append(
            f"- {_markdown_value(item.get('label'))}: {_markdown_value(item.get('status'))}; "
            f"manual follow-up {_int(item.get('manual_follow_up_count'))}. "
            f"{_markdown_value(item.get('note'))}"
        )

    lines += ["", "### Handoff checklist"]
    for item in _rows(preview.get("handoff_checklist")):
        lines.append(
            f"- {_markdown_value(item.get('label'))}: {_markdown_value(item.get('status'))} - "
            f"{_markdown_value(item.get('note'))}"
        )

    lines += ["", "### Manual follow-up queue"]
    queue_rows = _rows(preview.get("manual_follow_up_queue"))
    if queue_rows:
        lines += [
            "| Source surface | Item label | Issue type | Manual follow-up note | Review next |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in queue_rows:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_value(row.get(key))
                    for key in (
                        "source_surface",
                        "item_label",
                        "issue_type",
                        "manual_follow_up_note",
                        "where_to_review_next",
                    )
                )
                + " |"
            )
    else:
        lines.append("- No manual follow-up items are visible from the supplied review queues.")

    panel_markdown = _format_expression_construct_review_action_panel_markdown(preview)
    if panel_markdown:
        lines += ["", panel_markdown]

    traceability_markdown = _text(preview.get("traceability_matrix_markdown"), "")
    if traceability_markdown:
        lines += ["", traceability_markdown]

    qr_payload_markdown = _text(preview.get("qr_verification_payload_markdown"), "")
    if qr_payload_markdown:
        lines += ["", qr_payload_markdown]

    lines += ["", "### Boundary notes"]
    for note in preview.get("boundary_notes") or []:
        lines.append(f"- {_markdown_value(note)}")

    return "\n".join(lines)


def build_project_handoff_package_preview(
    handoff_center: Mapping[str, Any] | None,
    *,
    project_label: str | None = None,
    construct_review_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only handoff package preview from R177 handoff output."""
    handoff = normalize_generated_output_claims(_mapping(handoff_center))
    clean_project_label = normalize_generated_output_text(project_label) if project_label is not None else None
    summary = _mapping(handoff.get("summary"))
    included_documentation_preview = _build_included_documentation_preview(summary)
    surfaces = [item["label"] for item in included_documentation_preview]
    manual_follow_up_queue = _rows(handoff.get("follow_up_rows"))
    expression_construct_review_action_panel = _build_expression_construct_review_action_panel_readback(
        construct_review_payload or handoff.get("expression_construct_queue") or {}
    )

    preview = {
        "title": PREVIEW_TITLE,
        "subtitle": PREVIEW_SUBTITLE,
        "status": "AVAILABLE" if handoff else "NOT_AVAILABLE",
        "handoff_cover_summary": {
            "project_label": _review_text(clean_project_label, "Active pathway documentation project"),
            "total_manual_follow_up_items": _int(summary.get("total_follow_up_items")),
            "documentation_surfaces_included": surfaces,
        },
        "included_documentation_preview": included_documentation_preview,
        "expression_construct_review_action_panel": expression_construct_review_action_panel,
        "handoff_checklist": _rows(handoff.get("checklist")),
        "manual_follow_up_queue": manual_follow_up_queue,
        "boundary_notes": PREVIEW_BOUNDARY_NOTES[:],
        "review_sheet_boundary_note": REVIEW_SHEET_BOUNDARY_NOTE,
        "review_sheet_sections": _review_sheet_sections(),
    }
    traceability_rows = _build_traceability_matrix_rows(preview)
    preview["traceability_matrix_rows"] = traceability_rows
    preview["traceability_matrix_summary"] = _build_traceability_matrix_summary(traceability_rows)
    preview["traceability_matrix_markdown"] = format_project_handoff_traceability_matrix_markdown(preview)
    preview["traceability_matrix_plain_text"] = format_project_handoff_traceability_matrix_plain_text(preview)
    base_markdown = format_project_handoff_package_preview_markdown(preview)
    normalized_content = _normalize_preview_content(base_markdown)
    review_card = _build_snapshot_review_card(preview, normalized_content)
    preview.update(
        {
            "snapshot_title": review_card["snapshot_title"],
            "snapshot_checksum": review_card["snapshot_checksum"],
            "snapshot_id": review_card["snapshot_id"],
            "snapshot_checksum_algorithm": review_card["snapshot_checksum_algorithm"],
            "snapshot_section_count": review_card["snapshot_section_count"],
            "snapshot_content_length": review_card["snapshot_content_length"],
            "snapshot_included_surface_count": review_card["snapshot_included_surface_count"],
            "snapshot_review_card": review_card,
        }
    )
    preview.update(_build_qr_verification_preview(preview, review_card))
    preview["qr_verification_payload_markdown"] = _format_qr_verification_payload_markdown(preview)
    preview["output_sections_overview"] = build_project_output_sections_overview(
        handoff_preview=preview
    )
    preview["markdown_handoff_preview"] = format_project_handoff_package_preview_markdown(preview)
    preview["review_sheet_markdown"] = format_project_handoff_review_sheet_markdown(preview)
    preview["review_sheet_plain_text"] = format_project_handoff_review_sheet_plain_text(preview)
    preview["handoff_workspace_nav_rows"] = handoff_workspace_nav_rows(preview)
    preview["handoff_workspace_summary"] = handoff_workspace_summary(preview)
    preview["handoff_workspace_markdown"] = handoff_workspace_markdown(preview)
    preview = normalize_generated_output_claims(preview)
    assert_no_misleading_generated_claims(preview, context="handoff preview")
    return preview
