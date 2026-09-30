from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from services.plant_design_review_package_snapshot import build_plant_design_review_package_snapshot
from services.plant_ai_handoff_preview_presenter import build_rice_albumin_handoff_preview_payload
from services.plant_ai_user_input_mock_preview import (
    DEFAULT_USER_INPUT_MOCK_REQUEST,
    build_user_input_mock_preview_payload,
)
from services.plant_construct_slot_plan_presenter import present_construct_slot_plan_readback
from services.plant_construct_slot_plan_readback_builder import build_plant_construct_slot_plan_readback
from services.plant_evidence_package_flow_presenter import present_evidence_package_flow_readback
from services.plant_evidence_package_flow_readback import build_plant_evidence_package_flow_readback
from services.plant_review_framework_summary import build_plant_review_framework_summary
from services.plant_review_module_card_presenter import present_plant_review_module_cards
from services.plant_route_template_presenter import present_plant_route_templates
from services.plant_walkthrough_chain_runner import run_plant_walkthrough_chain_by_fixture_id
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_section_heading,
    render_tool_header,
    render_tool_intro,
)


PAGE_TITLE = "Plant Design Workspace"
PAGE_SUBTITLE = (
    "Documentation-only plant design review workspace. Drafts require manual review and do not "
    "represent experimental validation."
)
BOUNDARY_NOTICE = (
    "Documentation-only readback shell for plant route review. It displays candidate match, "
    "source/evidence readback, gap queue, package snapshot, and Markdown preview data for manual "
    "review only; it is not experiment evidence and does not choose components, generate "
    "sequences, mutate packages, write files, write databases, or judge downstream use."
)
EMPTY_STATE_COPY = (
    "No plant walkthrough fixture output is available for this read-only workspace shell. "
    "The page remains documentation-only and manual-review framed."
)

WORKSPACE_FIXTURE_IDS: tuple[str, ...] = (
    "rice_albumin_expression_review",
    "n_benthamiana_expression_context_review",
    "generic_plant_expression_missing_fields",
)

SECTION_LABELS: tuple[str, ...] = (
    "Plant route review chain overview",
    "AI-guided Plant Design Handoff Preview",
    "User-input Plant Design Mock Preview",
    "Framework coverage summary",
    "Route template registry readback",
    "Module card registry readback",
    "Example walkthrough readback",
    "Route draft summary",
    "Construct slot plan readback",
    "Dedicated slot plan presenter readback",
    "Evidence package flow readback",
    "Component candidate readback",
    "Gap / manual review queue",
    "Package snapshot summary",
    "Markdown readback preview",
    "Boundary notice",
    "Empty state",
)

OVERVIEW_COLUMNS = [
    "Fixture",
    "Chain status",
    "Route",
    "Package status",
    "Candidate rows",
    "Gap items",
    "Manual review items",
    "Markdown readback",
]
FRAMEWORK_COLUMNS = ["Layer", "Status", "Builder", "Presenter", "UI mount"]
ROUTE_TEMPLATE_COLUMNS = ["Route", "Plant context", "Route type", "Required modules", "Package sections"]
MODULE_CARD_COLUMNS = ["Module", "Display name", "Route type", "Required slots", "Evidence fields", "Package section"]
ROUTE_COLUMNS = ["Field", "Readback"]
SLOT_COLUMNS = ["Slot", "Slot type", "Status", "Value", "Manual review"]
SLOT_PRESENTER_COLUMNS = ["Slot", "Module", "Required", "Evidence status", "Manual review"]
EVIDENCE_FLOW_COLUMNS = ["Flow row", "Readback", "Status", "Manual review"]
CANDIDATE_COLUMNS = ["Slot type", "Candidate match", "Source/evidence readback", "Review status"]
GAP_COLUMNS = ["Gap", "Source section", "Field", "Status", "Manual review required"]
PACKAGE_COLUMNS = ["Field", "Readback"]
MARKDOWN_PREVIEW_CHAR_LIMIT = 1600

WORKSPACE_READABILITY_CSS = """
<style>
.pdw-readback-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.62rem;margin:.45rem 0 1rem 0}
.pdw-readback-card{border:1px solid #e2e8f0;border-radius:8px;background:#ffffff;padding:.72rem .78rem;min-width:0}
.pdw-readback-title{font-size:.8rem;font-weight:800;color:#334155;line-height:1.35;margin-bottom:.48rem;overflow-wrap:anywhere}
.pdw-readback-field{font-size:.7rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#64748b;line-height:1.25;margin-top:.42rem}
.pdw-readback-value{font-size:.88rem;line-height:1.45;color:#0f172a;overflow-wrap:anywhere;word-break:break-word}
.pdw-key-row{display:grid;grid-template-columns:minmax(110px, .42fr) minmax(0, 1fr);gap:.6rem;align-items:start;border-bottom:1px solid #eef2f7;padding:.52rem 0}
.pdw-key-row:last-child{border-bottom:0}
.pdw-markdown-preview{max-height:28rem;overflow:auto;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:.85rem .95rem;margin:.35rem 0 .5rem 0}
.pdw-markdown-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font-size:.84rem;line-height:1.48;color:#0f172a}
@media (max-width: 760px){
  section.main .block-container{padding-left:.85rem;padding-right:.85rem}
  .pdw-readback-grid{grid-template-columns:1fr;gap:.55rem}
  .pdw-key-row{grid-template-columns:1fr;gap:.18rem}
  .pdw-readback-card{padding:.66rem .7rem}
  .pdw-markdown-preview{max-height:20rem;padding:.72rem .78rem}
}
</style>
"""


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else "not recorded"


def _fixture_outputs() -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for fixture_id in WORKSPACE_FIXTURE_IDS:
        output = run_plant_walkthrough_chain_by_fixture_id(fixture_id)
        if isinstance(output, Mapping):
            outputs.append(dict(output))
    return outputs


def _chain_summary(output: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(output.get("chain_summary"))


def _route_draft(output: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(output.get("route_draft"))


def _package_snapshot(output: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(output.get("package_snapshot"))


def _markdown_readback(output: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(output.get("markdown_readback"))


def _overview_frame(outputs: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for output in outputs:
        summary = _chain_summary(output)
        route = _route_draft(output)
        package = _package_snapshot(output)
        markdown = _markdown_readback(output)
        rows.append(
            {
                "Fixture": _text(output.get("fixture_id"), "fixture"),
                "Chain status": _text(summary.get("chain_status"), "not recorded"),
                "Route": _text(route.get("route_id"), "not recorded"),
                "Package status": _text(package.get("package_status"), "not recorded"),
                "Candidate rows": int(summary.get("candidate_rows") or 0),
                "Gap items": int(summary.get("gap_queue_items") or 0),
                "Manual review items": int(summary.get("manual_review_items") or 0),
                "Markdown readback": "available" if _text(markdown.get("markdown_text")) else "not recorded",
            }
        )
    return pd.DataFrame(rows, columns=OVERVIEW_COLUMNS)


def _framework_summary_model() -> dict[str, Any]:
    return build_plant_review_framework_summary()


def _framework_summary_frame(summary: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in _sequence(summary.get("layer_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Layer": _text(item.get("layer_label"), "not recorded"),
                "Status": _text(item.get("status"), "manual review required"),
                "Builder": _text(item.get("builder"), "not recorded"),
                "Presenter": _text(item.get("presenter"), "not recorded"),
                "UI mount": _text(item.get("ui_mount"), "not recorded"),
            }
        )
    return pd.DataFrame(rows, columns=FRAMEWORK_COLUMNS)


def _route_template_registry_frame() -> pd.DataFrame:
    presenter = present_plant_route_templates()
    rows: list[dict[str, Any]] = []
    for row in _sequence(presenter.get("template_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Route": _text(item.get("route_id"), "not recorded"),
                "Plant context": _text(item.get("plant_context"), "not recorded"),
                "Route type": _text(item.get("route_type"), "not recorded"),
                "Required modules": str(item.get("required_module_count", 0)),
                "Package sections": str(item.get("package_section_count", 0)),
            }
        )
    return pd.DataFrame(rows, columns=ROUTE_TEMPLATE_COLUMNS)


def _module_card_registry_frame() -> pd.DataFrame:
    presenter = present_plant_review_module_cards()
    rows: list[dict[str, Any]] = []
    for row in _sequence(presenter.get("module_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Module": _text(item.get("module_id"), "not recorded"),
                "Display name": _text(item.get("display_name"), "not recorded"),
                "Route type": _text(item.get("route_type"), "not recorded"),
                "Required slots": str(item.get("required_slot_count", 0)),
                "Evidence fields": str(item.get("evidence_field_count", 0)),
                "Package section": _text(item.get("package_section"), "not recorded"),
            }
        )
    return pd.DataFrame(rows, columns=MODULE_CARD_COLUMNS)


def _route_summary_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    route = _route_draft(output)
    plant_context = _mapping(route.get("plant_context"))
    target_summary = _mapping(route.get("target_summary"))
    rows = [
        {"Field": "Fixture", "Readback": _text(output.get("fixture_id"), "not recorded")},
        {"Field": "Route id", "Readback": _text(route.get("route_id"), "not recorded")},
        {"Field": "Route name", "Readback": _text(route.get("route_name"), "not recorded")},
        {"Field": "Draft status", "Readback": _text(route.get("draft_status"), "manual review required")},
        {"Field": "Plant context", "Readback": _text(plant_context.get("plant_context"), "not recorded")},
        {"Field": "Scope status", "Readback": _text(plant_context.get("scope_status"), "manual review required")},
        {"Field": "Target", "Readback": _text(target_summary.get("target_name"), "not recorded")},
    ]
    return pd.DataFrame(rows, columns=ROUTE_COLUMNS)


def _slot_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    package = _package_snapshot(output)
    slot_section = _mapping(package.get("construct_slot_plan_section"))
    rows: list[dict[str, Any]] = []
    for row in _sequence(slot_section.get("construct_slot_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Slot": _text(item.get("slot_name"), "not recorded"),
                "Slot type": _text(item.get("slot_type"), "not recorded"),
                "Status": _text(item.get("status"), "manual review required"),
                "Value": _text(item.get("value"), "not recorded"),
                "Manual review": "manual review required",
            }
        )
    return pd.DataFrame(rows, columns=SLOT_COLUMNS)


def _slot_plan_presenter_payload(output: Mapping[str, Any]) -> dict[str, Any]:
    route = _route_draft(output)
    if not route:
        return present_construct_slot_plan_readback({})
    readback = build_plant_construct_slot_plan_readback(
        route.get("selected_template") if isinstance(route.get("selected_template"), Mapping) else route,
        route.get("required_modules") if isinstance(route.get("required_modules"), Sequence) else [],
    )
    return present_construct_slot_plan_readback(readback)


def _slot_presenter_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    presenter = _slot_plan_presenter_payload(output)
    rows: list[dict[str, Any]] = []
    for row in _sequence(presenter.get("slot_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Slot": _text(item.get("slot_id"), "not recorded"),
                "Module": _text(item.get("module_label"), "not recorded"),
                "Required": _text(item.get("required_or_optional"), "manual review"),
                "Evidence status": _text(item.get("current_evidence_status"), "manual review required"),
                "Manual review": _text(item.get("manual_review_state"), "manual review required"),
            }
        )
    return pd.DataFrame(rows, columns=SLOT_PRESENTER_COLUMNS)


def _evidence_flow_presenter_payload(output: Mapping[str, Any]) -> dict[str, Any]:
    package = _package_snapshot(output)
    gap_queue = _mapping(output.get("gap_queue_payload"))
    slot_plan = _slot_plan_presenter_payload(output)
    flow_readback = build_plant_evidence_package_flow_readback(
        {
            "route_template_id": _mapping(slot_plan.get("summary_card")).get("route_template_id"),
            "canonical_route_template_id": _mapping(slot_plan.get("summary_card")).get("canonical_route_template_id"),
            "slot_rows": [
                {
                    "slot_id": row.get("slot_id"),
                    "module_id": row.get("module_id"),
                    "module_label": row.get("module_label"),
                    "expected_evidence_type": row.get("expected_evidence_type"),
                    "current_evidence_status": row.get("current_evidence_status"),
                    "manual_review_state": row.get("manual_review_state"),
                    "gap_reason": row.get("gap_reason"),
                }
                for row in _sequence(slot_plan.get("slot_rows"))
                if isinstance(row, Mapping)
            ],
        },
        gap_queue,
        package,
    )
    return present_evidence_package_flow_readback(flow_readback)


def _evidence_flow_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    presenter = _evidence_flow_presenter_payload(output)
    summary = _mapping(presenter.get("summary_card"))
    handoff = _mapping(presenter.get("handoff_card"))
    rows = [
        {
            "Flow row": "Evidence records",
            "Readback": str(summary.get("evidence_record_count", 0)),
            "Status": _text(summary.get("flow_status"), "manual review required"),
            "Manual review": _yes_no(summary.get("manual_review_required")),
        },
        {
            "Flow row": "Gap review items",
            "Readback": str(summary.get("gap_review_item_count", 0)),
            "Status": "manual review queue",
            "Manual review": _yes_no(summary.get("manual_review_required")),
        },
        {
            "Flow row": "Package sections",
            "Readback": str(summary.get("package_section_count", 0)),
            "Status": "documentation snapshot",
            "Manual review": _yes_no(summary.get("manual_review_required")),
        },
        {
            "Flow row": "Handoff summary",
            "Readback": _text(handoff.get("package_id"), "not recorded"),
            "Status": _text(handoff.get("handoff_status"), "manual review required"),
            "Manual review": _yes_no(handoff.get("manual_review_required")),
        },
    ]
    return pd.DataFrame(rows, columns=EVIDENCE_FLOW_COLUMNS)


def _candidate_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    package = _package_snapshot(output)
    candidate_section = _mapping(package.get("component_candidate_section"))
    rows: list[dict[str, Any]] = []
    for row in _sequence(candidate_section.get("slot_candidate_rows")):
        item = _mapping(row)
        if not item:
            continue
        source_bits = [
            _text(item.get("source_id")),
            _text(item.get("evidence_status")),
        ]
        rows.append(
            {
                "Slot type": _text(item.get("slot_type"), "not recorded"),
                "Candidate match": _text(item.get("component_name"), _text(item.get("component_id"), "not recorded")),
                "Source/evidence readback": " | ".join(bit for bit in source_bits if bit) or "not recorded",
                "Review status": _text(item.get("review_status"), "manual review required"),
            }
        )
    for row in _sequence(candidate_section.get("unmatched_slot_rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Slot type": _text(item.get("slot_type"), "not recorded"),
                "Candidate match": "No candidate match recorded",
                "Source/evidence readback": _text(item.get("note"), "manual review required"),
                "Review status": _text(item.get("candidate_status"), "manual review required"),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def _gap_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    package = _package_snapshot(output)
    gap_section = _mapping(package.get("gap_queue_section"))
    rows: list[dict[str, Any]] = []
    for row in _sequence(gap_section.get("queue_items")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Gap": _text(item.get("gap_type"), _text(item.get("gap_id"), "not recorded")),
                "Source section": _text(item.get("source_section"), "not recorded"),
                "Field": _text(item.get("field_name"), "not recorded"),
                "Status": _text(item.get("status"), "manual review required"),
                "Manual review required": "yes",
            }
        )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def _package_frame(output: Mapping[str, Any]) -> pd.DataFrame:
    package = _package_snapshot(output)
    rows = [
        {"Field": "Package id", "Readback": _text(package.get("package_id"), "not recorded")},
        {"Field": "Package title", "Readback": _text(package.get("package_title"), "not recorded")},
        {"Field": "Package status", "Readback": _text(package.get("package_status"), "not recorded")},
        {"Field": "Package scope", "Readback": _text(package.get("package_scope"), "not recorded")},
        {"Field": "Identity MD5", "Readback": _text(package.get("identity_md5"), "not recorded")},
        {"Field": "Package warnings", "Readback": str(len(_sequence(package.get("package_warnings"))))},
    ]
    return pd.DataFrame(rows, columns=PACKAGE_COLUMNS)


def _empty_markdown_preview() -> str:
    empty_snapshot = build_plant_design_review_package_snapshot()
    markdown = _mapping(empty_snapshot.get("empty_state"))
    return _text(markdown.get("message"), EMPTY_STATE_COPY)


def _bounded_markdown_preview(markdown_text: str) -> str:
    clean = _text(markdown_text, EMPTY_STATE_COPY)
    if len(clean) <= MARKDOWN_PREVIEW_CHAR_LIMIT:
        return clean
    trimmed = clean[:MARKDOWN_PREVIEW_CHAR_LIMIT].rstrip()
    return (
        f"{trimmed}\n\n"
        "[Preview shortened for readability. Documentation-only fixture readback continues beyond this bounded preview.]"
    )


def build_plant_design_workspace_shell_model(
    chain_outputs: Sequence[Mapping[str, Any]] | None = None,
    user_mock_request: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only shell model from R389-R392 fixture chain outputs."""
    outputs = [dict(output) for output in (chain_outputs if chain_outputs is not None else _fixture_outputs()) if isinstance(output, Mapping)]
    active_output = outputs[0] if outputs else {}
    markdown = _markdown_readback(active_output)
    is_empty = not outputs
    markdown_text = _text(markdown.get("markdown_text")) or _empty_markdown_preview()
    framework_summary = _framework_summary_model()
    model = {
        "page_title": PAGE_TITLE,
        "subtitle": PAGE_SUBTITLE,
        "boundary_notice": BOUNDARY_NOTICE,
        "section_labels": list(SECTION_LABELS),
        "fixture_ids": [str(fixture_id) for fixture_id in WORKSPACE_FIXTURE_IDS],
        "read_only": True,
        "ai_handoff_preview": build_rice_albumin_handoff_preview_payload(),
        "user_input_mock_preview": build_user_input_mock_preview_payload(user_mock_request or DEFAULT_USER_INPUT_MOCK_REQUEST),
        "empty_state": {
            "is_empty": is_empty,
            "message": EMPTY_STATE_COPY if is_empty else "",
            "manual_review_required": True,
        },
        "overview": _overview_frame(outputs),
        "framework_summary": framework_summary,
        "framework_summary_rows": _framework_summary_frame(framework_summary),
        "route_template_registry": _route_template_registry_frame(),
        "module_card_registry": _module_card_registry_frame(),
        "active_fixture_id": _text(active_output.get("fixture_id"), "no_fixture_output"),
        "route_summary": _route_summary_frame(active_output),
        "construct_slot_plan": _slot_frame(active_output),
        "dedicated_slot_plan_presenter": _slot_presenter_frame(active_output),
        "evidence_package_flow": _evidence_flow_frame(active_output),
        "component_candidate_readback": _candidate_frame(active_output),
        "gap_manual_review_queue": _gap_frame(active_output),
        "package_snapshot_summary": _package_frame(active_output),
        "markdown_readback_preview": _bounded_markdown_preview(markdown_text),
        "markdown_readback_full_length": len(markdown_text),
        "markdown_readback_preview_limit": MARKDOWN_PREVIEW_CHAR_LIMIT,
    }
    return model


def _inject_workspace_readability_css() -> None:
    st.markdown(WORKSPACE_READABILITY_CSS, unsafe_allow_html=True)


def _render_static_readback(frame: pd.DataFrame, empty_copy: str, title_column: str | None = None) -> None:
    if frame.empty:
        st.caption(empty_copy)
        return
    rows: list[str] = []
    for record in frame.to_dict(orient="records"):
        title = _text(record.get(title_column), "Readback row") if title_column else "Readback row"
        fields = []
        for column in frame.columns:
            if title_column and column == title_column:
                continue
            value = _text(record.get(column), "not recorded")
            fields.append(
                "<div class='pdw-readback-field'>"
                f"{html.escape(str(column))}"
                "</div>"
                "<div class='pdw-readback-value'>"
                f"{html.escape(value)}"
                "</div>"
            )
        rows.append(
            "<div class='pdw-readback-card'>"
            f"<div class='pdw-readback-title'>{html.escape(title)}</div>"
            f"{''.join(fields)}"
            "</div>"
        )
    st.markdown("<div class='pdw-readback-grid'>" + "".join(rows) + "</div>", unsafe_allow_html=True)


def _render_key_value_readback(frame: pd.DataFrame, empty_copy: str) -> None:
    if frame.empty:
        st.caption(empty_copy)
        return
    rows = []
    for record in frame.to_dict(orient="records"):
        field = _text(record.get("Field"), "Field")
        value = _text(record.get("Readback"), "not recorded")
        rows.append(
            "<div class='pdw-key-row'>"
            f"<div class='pdw-readback-field'>{html.escape(field)}</div>"
            f"<div class='pdw-readback-value'>{html.escape(value)}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='pdw-readback-card'>" + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def _render_markdown_preview(preview_text: str, full_length: int) -> None:
    st.caption(
        "Documentation-only bounded preview for manual review context. "
        f"Showing up to {MARKDOWN_PREVIEW_CHAR_LIMIT} characters from fixture readback; source length: {full_length} characters."
    )
    with st.expander("Show bounded Markdown preview", expanded=False):
        st.markdown(
            "<div class='pdw-markdown-preview'><pre>"
            f"{html.escape(preview_text)}"
            "</pre></div>",
            unsafe_allow_html=True,
        )


def _frame(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows if isinstance(row, Mapping)], columns=list(columns))


def _render_ai_handoff_preview(payload: Mapping[str, Any]) -> None:
    render_tool_intro(
        _text(payload.get("title"), "AI-guided Plant Design Handoff Preview"),
        _text(
            payload.get("subtitle"),
            "Fixed rice albumin-like read-only mock preview - deterministic fixture - manual review required",
        ),
    )
    render_boundary_note(_text(payload.get("boundary_note"), "Read-only handoff preview for manual review."))

    badges = []
    for badge in _sequence(payload.get("status_badges")):
        item = _mapping(badge)
        if item:
            badges.append((_text(item.get("label"), "Status"), _text(item.get("value"), "not recorded"), None))
    render_compact_summary_cards(badges)

    if _mapping(payload.get("empty_state")).get("is_empty"):
        st.info(_text(_mapping(payload.get("empty_state")).get("message"), "Handoff preview is unavailable."))
        return

    render_section_heading("Request & scope")
    _render_key_value_readback(
        _frame(_sequence(payload.get("request_scope_rows")), ["Field", "Readback"]),
        "No request or scope rows are available.",
    )

    render_section_heading("Allowed outputs")
    _render_static_readback(
        _frame(_sequence(payload.get("allowed_output_rows")), ["Output", "Preview boundary"]),
        "No allowed outputs are available.",
        title_column="Output",
    )

    render_section_heading("Blocked outputs")
    _render_static_readback(
        _frame(_sequence(payload.get("blocked_output_rows")), ["Output", "Preview boundary"]),
        "No blocked outputs are recorded.",
        title_column="Output",
    )

    render_section_heading("Parsed design intent")
    _render_key_value_readback(
        _frame(_sequence(payload.get("design_intent_rows")), ["Field", "Readback"]),
        "No parsed design intent rows are available.",
    )

    render_section_heading("Plant design context")
    _render_key_value_readback(
        _frame(_sequence(payload.get("plant_context_rows")), ["Field", "Readback"]),
        "No plant design context rows are available.",
    )

    render_section_heading("Missing information")
    _render_static_readback(
        _frame(_sequence(payload.get("missing_information_rows")), ["Missing information", "Why this is still open"]),
        "No missing information rows are available.",
        title_column="Missing information",
    )

    render_section_heading("Evidence and component placeholders")
    _render_static_readback(
        _frame(
            _sequence(payload.get("evidence_placeholder_rows")),
            ["Evidence id", "Title", "Source type", "Source status", "Review status"],
        ),
        "No evidence placeholder rows are available.",
        title_column="Title",
    )
    _render_static_readback(
        _frame(
            _sequence(payload.get("component_placeholder_rows")),
            ["Component id", "Label", "Component type", "Source species", "Sequence/documentation status", "Manual notes"],
        ),
        "No component placeholder rows are available.",
        title_column="Label",
    )

    render_section_heading("Component candidate / placeholder slots")
    _render_static_readback(
        _frame(
            _sequence(payload.get("component_candidate_rows")),
            ["Slot id", "Slot type", "Label", "Draft status", "Selected component", "Candidate placeholders", "Manual review"],
        ),
        "No component candidate rows are available.",
        title_column="Label",
    )

    render_section_heading("Construct draft slot scaffold")
    _render_static_readback(
        _frame(
            _sequence(payload.get("construct_slot_rows")),
            ["Draft id", "Slot id", "Slot type", "Missing reason", "Manual review"],
        ),
        "No construct draft slot rows are available.",
        title_column="Slot id",
    )

    render_section_heading("Review gaps and missing information")
    _render_static_readback(
        _frame(_sequence(payload.get("review_gap_rows")), ["Review item", "Type", "Severity", "Message", "Review status"]),
        "No review gap rows are available.",
        title_column="Review item",
    )
    _render_static_readback(
        _frame(_sequence(payload.get("manual_checklist_rows")), ["Review item", "Type", "Severity", "Message", "Review status"]),
        "No manual checklist rows are available.",
        title_column="Review item",
    )

    render_section_heading("Company handoff draft sections")
    _render_static_readback(
        _frame(_sequence(payload.get("handoff_section_rows")), ["Section id", "Title", "Summary", "Rows", "Manual review"]),
        "No company handoff draft sections are available.",
        title_column="Title",
    )

    render_section_heading("Boundary statements")
    _render_static_readback(
        _frame(_sequence(payload.get("boundary_statement_rows")), ["Boundary statement"]),
        "No boundary statements are available.",
        title_column="Boundary statement",
    )

    render_section_heading("Manual review status")
    _render_key_value_readback(
        _frame(_sequence(payload.get("manual_review_status_rows")), ["Field", "Readback"]),
        "No manual review status rows are available.",
    )


def _render_user_input_mock_preview(payload: Mapping[str, Any]) -> None:
    render_tool_intro(
        _text(payload.get("title"), "User-input Plant Design Mock Preview"),
        _text(payload.get("subtitle"), "Deterministic, unsaved mock preview from the current text input"),
    )
    render_boundary_note(_text(payload.get("boundary_note"), "Read-only mock preview for manual review."))

    badges = []
    for badge in _sequence(payload.get("status_badges")):
        item = _mapping(badge)
        if item:
            badges.append((_text(item.get("label"), "Status"), _text(item.get("value"), "not recorded"), None))
    render_compact_summary_cards(badges)

    render_section_heading("Input scope route")
    _render_key_value_readback(
        _frame(_sequence(payload.get("request_scope_rows")), ["Field", "Readback"]),
        "No input route rows are available.",
    )

    if _sequence(payload.get("route_out_rows")):
        render_section_heading("Non-plant route")
        _render_key_value_readback(
            _frame(_sequence(payload.get("route_out_rows")), ["Field", "Readback"]),
            "No non-plant route rows are available.",
        )

    if _sequence(payload.get("blocked_notice_rows")):
        render_section_heading("Blocked input notice")
        _render_key_value_readback(
            _frame(_sequence(payload.get("blocked_notice_rows")), ["Field", "Readback"]),
            "No blocked input notice rows are available.",
        )

    render_section_heading("Allowed mock outputs")
    _render_static_readback(
        _frame(_sequence(payload.get("allowed_output_rows")), ["Output", "Preview boundary"]),
        "No allowed mock outputs are available.",
        title_column="Output",
    )

    render_section_heading("Blocked mock outputs")
    _render_static_readback(
        _frame(_sequence(payload.get("blocked_output_rows")), ["Output", "Preview boundary"]),
        "No blocked mock outputs are available.",
        title_column="Output",
    )

    if _sequence(payload.get("parsed_intent_rows")):
        render_section_heading("Parsed mock preview")
        _render_key_value_readback(
            _frame(_sequence(payload.get("parsed_intent_rows")), ["Field", "Readback"]),
            "No parsed mock preview rows are available.",
        )

    if _sequence(payload.get("missing_information_rows")):
        render_section_heading("Mock missing information")
        _render_static_readback(
            _frame(_sequence(payload.get("missing_information_rows")), ["Missing information", "Why this is still open"]),
            "No mock missing information rows are available.",
            title_column="Missing information",
        )

    if _sequence(payload.get("review_gap_rows")):
        render_section_heading("Mock review gaps")
        _render_static_readback(
            _frame(_sequence(payload.get("review_gap_rows")), ["Review item", "Reason", "Status"]),
            "No mock review gap rows are available.",
            title_column="Review item",
        )

    render_section_heading("Mock boundary statements")
    _render_static_readback(
        _frame(_sequence(payload.get("boundary_statement_rows")), ["Boundary statement"]),
        "No mock boundary statements are available.",
        title_column="Boundary statement",
    )


def render(_change_page=None) -> dict[str, Any]:
    """Render the R395 read-only Plant Design Workspace shell."""
    model = build_plant_design_workspace_shell_model()
    inject_tool_typography_css()
    _inject_workspace_readability_css()
    render_tool_header(model["page_title"], model["subtitle"])
    render_boundary_note(model["boundary_notice"])
    render_help_text(
        "Fixed sample readback uses rice albumin, N. benthamiana, and missing-fields fixtures only. "
        "Rows are displayed as supplied by the existing plant review chain."
    )

    render_section_heading("Plant route review chain overview")
    render_compact_summary_cards(
        [
            ("Fixture outputs", str(len(model["overview"])), None),
            ("Read-only", _yes_no(model["read_only"]), None),
            ("Manual review", "required", None),
            ("Sample focus", model["active_fixture_id"], None),
        ]
    )
    _render_static_readback(model["overview"], "No plant route review chain output is available.", title_column="Fixture")

    render_section_heading("AI-guided Plant Design Handoff Preview")
    _render_ai_handoff_preview(model["ai_handoff_preview"])

    render_section_heading("User-input Plant Design Mock Preview")
    user_mock_request = st.text_area(
        "Plant design request mock input (deterministic preview only; not saved)",
        value=DEFAULT_USER_INPUT_MOCK_REQUEST,
        height=110,
        help=(
            "Try a rice albumin-like company handoff request, a blocked operational request, "
            "a non-plant request, or a mixed safe-plus-blocked request."
        ),
    )
    model["user_input_mock_preview"] = build_user_input_mock_preview_payload(user_mock_request)
    _render_user_input_mock_preview(model["user_input_mock_preview"])

    render_section_heading("Framework coverage summary")
    coverage = model["framework_summary"]["coverage_summary"]
    render_compact_summary_cards(
        [
            ("Framework layers", str(coverage["layer_count"]), None),
            ("Presenter layers", str(coverage["presenter_layer_count"]), None),
            ("Workspace mounts", str(coverage["workspace_mount_count"]), None),
            ("Manual review", "required", None),
        ]
    )
    _render_static_readback(
        model["framework_summary_rows"],
        "No framework coverage rows are available.",
        title_column="Layer",
    )

    render_section_heading("Route template registry readback")
    _render_static_readback(
        model["route_template_registry"],
        "No route template registry rows are available.",
        title_column="Route",
    )

    render_section_heading("Module card registry readback")
    _render_static_readback(
        model["module_card_registry"],
        "No module card registry rows are available.",
        title_column="Module",
    )

    render_tool_intro(
        "Example walkthrough readback",
        "Fixed sample readback from the rice albumin fixture is shown first; the overview table also lists "
        "N. benthamiana and missing-fields fixture outputs for manual review context.",
    )

    render_section_heading("Route draft summary")
    _render_key_value_readback(model["route_summary"], "No route draft summary is available.")

    render_section_heading("Construct slot plan readback")
    _render_static_readback(model["construct_slot_plan"], "No construct slot plan rows are available.", title_column="Slot")

    render_section_heading("Dedicated slot plan presenter readback")
    _render_static_readback(
        model["dedicated_slot_plan_presenter"],
        "No dedicated slot plan presenter rows are available.",
        title_column="Slot",
    )

    render_section_heading("Evidence package flow readback")
    _render_static_readback(
        model["evidence_package_flow"],
        "No evidence package flow rows are available.",
        title_column="Flow row",
    )

    render_section_heading("Component candidate readback")
    _render_static_readback(
        model["component_candidate_readback"],
        "No component candidate readback rows are available.",
        title_column="Slot type",
    )

    render_section_heading("Gap / manual review queue")
    _render_static_readback(model["gap_manual_review_queue"], "No gap queue rows are available.", title_column="Gap")

    render_section_heading("Package snapshot summary")
    _render_key_value_readback(model["package_snapshot_summary"], "No package snapshot summary is available.")

    render_section_heading("Markdown readback preview")
    _render_markdown_preview(
        model["markdown_readback_preview"],
        int(model["markdown_readback_full_length"]),
    )

    render_section_heading("Boundary notice")
    st.info(model["boundary_notice"])

    render_section_heading("Empty state")
    if model["empty_state"]["is_empty"]:
        st.info(model["empty_state"]["message"])
    else:
        st.caption("Empty state remains available when fixture chain output is absent.")

    return model
