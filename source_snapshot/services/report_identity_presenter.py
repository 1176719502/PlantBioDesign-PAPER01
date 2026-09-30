from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
    normalize_generated_output_text,
)


REPORT_IDENTITY_CHECKSUM_ALGORITHM = "MD5"
REPORT_IDENTITY_BOUNDARY_NOTE = (
    "This report identity block is documentation-only. The MD5 checksum and QR payload are for matching the same "
    "generated report or package preview during human review; they are not a security signature, certification, "
    "experiment validation, or downstream-use judgment."
)
REPORT_IDENTITY_QR_DEPENDENCY_NOTE = (
    "Payload-only QR preview is used; no QR image is rendered and no new QR/image dependency is required."
)
REPORT_IDENTITY_QR_INTENDED_USE = (
    "Use the payload text to compare the same report/package identity during documentation review."
)
REPORT_IDENTITY_QR_PAYLOAD_HEADER = "BioDesign Studio report QR verification payload"

REPORT_VISUAL_WORKFLOW_STEPS = [
    "Target intent",
    "Expression system candidate",
    "Construct/component records",
    "Evidence/provenance review",
    "Codon/conservation status",
    "Review gaps",
    "Handoff package",
]


def _text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    clean = normalize_generated_output_text(value).strip() if value is not None else ""
    return clean or fallback


def _safe_payload_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    text = " ".join(_text(value, fallback).replace("\r", "\n").split())
    compact = re.sub(r"[^A-Za-z]", "", text)
    looks_like_sequence = len(compact) >= 24 and len(compact) >= max(1, int(len(text) * 0.8))
    if looks_like_sequence and (
        set(compact.upper()) <= set("ACGTUN")
        or set(compact.upper()) <= set("ACDEFGHIKLMNPQRSTVWY")
    ):
        return "WITHHELD_FOR_REPORT_IDENTITY_BOUNDARY"
    if re.search(r"[A-Za-z]:\\|/(?:home|users|var|etc|tmp)/", text, flags=re.IGNORECASE):
        return "WITHHELD_FOR_REPORT_IDENTITY_BOUNDARY"
    if re.search(r"\b(api[_ -]?key|credential|password|token|private)\b", text, flags=re.IGNORECASE):
        return "WITHHELD_FOR_REPORT_IDENTITY_BOUNDARY"
    return text[:160]


def _markdown_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return _text(value, fallback).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _checksum(data: Mapping[str, Any]) -> str:
    return hashlib.md5(_canonical_json(data).encode("utf-8")).hexdigest()


def build_report_visual_narrative(
    *,
    stage: str = "",
    recorded_context: str = "",
    manual_follow_up: str = "",
    workflow_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Build lightweight text/Markdown narrative for report readability."""
    steps = [_text(step) for step in (workflow_steps or REPORT_VISUAL_WORKFLOW_STEPS)]
    narrative = {
        "title": "Report visual narrative",
        "workflow_diagram_text": " -> ".join(steps),
        "section_summary_cards": [
            {
                "label": "Report purpose",
                "summary": "Summarize local design records, provenance context, review gaps, and handoff context for human documentation review.",
            },
            {
                "label": "Current documentation/review stage",
                "summary": _text(stage, "Documentation review stage not recorded."),
            },
            {
                "label": "Recorded context",
                "summary": _text(recorded_context, "Recorded project/design context is summarized from supplied local records."),
            },
            {
                "label": "Manual/company follow-up",
                "summary": _text(manual_follow_up, "Human reviewer or company review should resolve missing source/provenance and handoff questions."),
            },
        ],
        "interpretation_note": (
            "The workflow diagram is a reading guide for the generated report. It does not add analysis, scoring, "
            "selection advice, automated design-improvement guidance, or replace expert/company review."
        ),
    }
    narrative = normalize_generated_output_claims(narrative)
    assert_no_misleading_generated_claims(narrative, context="report visual narrative")
    return narrative


def format_report_visual_narrative_markdown(narrative: Mapping[str, Any]) -> str:
    cards = [dict(card) for card in narrative.get("section_summary_cards") or [] if isinstance(card, Mapping)]
    lines = [
        "## Report visual narrative",
        _markdown_value(narrative.get("interpretation_note")),
        "",
        "### Workflow diagram",
        f"`{_markdown_value(narrative.get('workflow_diagram_text'))}`",
        "",
        "### Section summary cards",
        "| Card | Summary |",
        "| --- | --- |",
    ]
    for card in cards:
        lines.append(f"| {_markdown_value(card.get('label'))} | {_markdown_value(card.get('summary'))} |")
    return "\n".join(lines)


def build_report_identity_block(
    *,
    report_title: str,
    project_or_case_name: str = "",
    generated_at: str = "",
    report_version: str = "",
    software_version: str = "BioDesign Studio",
    git_reference: str = "",
    report_or_package_id: str = "",
    purpose: str = "",
    review_stage: str = "",
    recorded_context: str = "",
    manual_follow_up: str = "",
    qr_payload_header: str = REPORT_IDENTITY_QR_PAYLOAD_HEADER,
) -> dict[str, Any]:
    """Build a deterministic text identity block for generated reports/package previews."""
    source = {
        "report_title": _safe_payload_value(report_title),
        "project_or_case_name": _safe_payload_value(project_or_case_name),
        "generated_at": _safe_payload_value(generated_at),
        "report_version": _safe_payload_value(report_version),
        "software_version": _safe_payload_value(software_version, "BioDesign Studio"),
        "git_reference": _safe_payload_value(git_reference),
        "purpose": _safe_payload_value(purpose, "Documentation review, provenance review, and handoff communication."),
        "review_stage": _safe_payload_value(review_stage, "Documentation review stage not recorded."),
        "recorded_context": _safe_payload_value(recorded_context, "Local records summarized for documentation review."),
        "manual_follow_up": _safe_payload_value(manual_follow_up, "Human/company review remains required for missing context and final decisions."),
    }
    preliminary_checksum = _checksum(source)
    report_id = _safe_payload_value(report_or_package_id, f"md5:{preliminary_checksum[:12]}")
    source = {**source, "report_or_package_id": report_id}
    checksum = _checksum(source)
    payload = {
        "payload_title": _safe_payload_value(qr_payload_header, REPORT_IDENTITY_QR_PAYLOAD_HEADER),
        **source,
        "checksum_algorithm": REPORT_IDENTITY_CHECKSUM_ALGORITHM,
        "md5_checksum": checksum,
        "boundary_note": REPORT_IDENTITY_BOUNDARY_NOTE,
    }
    payload_text = "\n".join(
        [
            payload["payload_title"],
            f"Report title: {payload['report_title']}",
            f"Project/case name: {payload['project_or_case_name']}",
            f"Generated at: {payload['generated_at']}",
            f"Report version: {payload['report_version']}",
            f"Software version: {payload['software_version']}",
            f"Git commit/tag: {payload['git_reference']}",
            f"Report/package ID: {payload['report_or_package_id']}",
            f"Checksum algorithm: {payload['checksum_algorithm']}",
            f"MD5 checksum: {payload['md5_checksum']}",
            f"Purpose: {payload['purpose']}",
            f"Review stage: {payload['review_stage']}",
            f"Recorded context: {payload['recorded_context']}",
            f"Manual/company follow-up: {payload['manual_follow_up']}",
            f"Boundary: {payload['boundary_note']}",
            f"QR dependency note: {REPORT_IDENTITY_QR_DEPENDENCY_NOTE}",
        ]
    )
    block = {
        "title": "Report identity and QR verification preview",
        "report_title": payload["report_title"],
        "project_or_case_name": payload["project_or_case_name"],
        "generated_at": payload["generated_at"],
        "report_version": payload["report_version"],
        "software_version": payload["software_version"],
        "git_reference": payload["git_reference"],
        "report_or_package_id": payload["report_or_package_id"],
        "checksum_algorithm": REPORT_IDENTITY_CHECKSUM_ALGORITHM,
        "md5_checksum": checksum,
        "qr_payload": payload,
        "qr_payload_text": payload_text,
        "qr_payload_status": "PAYLOAD_ONLY",
        "qr_dependency_note": REPORT_IDENTITY_QR_DEPENDENCY_NOTE,
        "qr_intended_use": REPORT_IDENTITY_QR_INTENDED_USE,
        "boundary_note": REPORT_IDENTITY_BOUNDARY_NOTE,
    }
    block = normalize_generated_output_claims(block)
    assert_no_misleading_generated_claims(block, context="report identity")
    return block


def format_report_identity_markdown(identity: Mapping[str, Any]) -> str:
    payload = identity.get("qr_payload") if isinstance(identity.get("qr_payload"), Mapping) else {}
    lines = [
        "## Report identity and QR verification preview",
        f"- Report title: {_markdown_value(identity.get('report_title'))}",
        f"- Project/case name: {_markdown_value(identity.get('project_or_case_name'))}",
        f"- Generated at: {_markdown_value(identity.get('generated_at'))}",
        f"- Report version: {_markdown_value(identity.get('report_version'))}",
        f"- Software version: {_markdown_value(identity.get('software_version'))}",
        f"- Git commit/tag: {_markdown_value(identity.get('git_reference'))}",
        f"- Report/package ID: {_markdown_value(identity.get('report_or_package_id'))}",
        f"- Checksum algorithm: {_markdown_value(identity.get('checksum_algorithm'))}",
        f"- MD5 checksum: {_markdown_value(identity.get('md5_checksum'))}",
        f"- QR payload status: {_markdown_value(identity.get('qr_payload_status'))}",
        f"- QR interpretation: {_markdown_value(identity.get('qr_intended_use'))}",
        f"- QR dependency note: {_markdown_value(identity.get('qr_dependency_note'))}",
        f"- Documentation-only boundary: {_markdown_value(identity.get('boundary_note'))}",
        "",
        "```text",
        _text(identity.get("qr_payload_text")),
        "```",
    ]
    if payload:
        lines.extend(
            [
                "",
                "### QR payload fields",
                f"- Purpose: {_markdown_value(payload.get('purpose'))}",
                f"- Review stage: {_markdown_value(payload.get('review_stage'))}",
                f"- Recorded context: {_markdown_value(payload.get('recorded_context'))}",
                f"- Manual/company follow-up: {_markdown_value(payload.get('manual_follow_up'))}",
            ]
        )
    return "\n".join(lines)
