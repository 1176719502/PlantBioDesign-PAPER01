"""Deterministic Step 6 projection of the canonical formal report contract.

The canonical report contract is the only source of report facts. This module
only projects that contract into visible and downloadable delivery content; it
never rereads or rebuilds biological results.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.formal_report_snapshot import validate_formal_report_snapshot
from services.formal_results_report_contract import (
    REPORT_CONTRACT_SCHEMA_VERSION,
    validate_report_artifact_manifest,
)


REPORT_VERSION = "1.0"
STATUS_AVAILABLE = "documentation_delivery_available"
STATUS_REVIEW_REQUIRED = "documentation_delivery_review_required"
STATUS_BLOCKED = "documentation_delivery_blocked"
SUPPORTED_STATUSES = frozenset({STATUS_AVAILABLE, STATUS_REVIEW_REQUIRED, STATUS_BLOCKED})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATUS_DETAILS = {
    STATUS_AVAILABLE: (
        "Documentation delivery record available",
        "The canonical report contract records no blockers or warnings.",
    ),
    STATUS_REVIEW_REQUIRED: (
        "Documentation delivery available with review required",
        "Warning-level review signals remain open; manual review is required.",
    ),
    STATUS_BLOCKED: (
        "Documentation delivery blocked",
        "Resolve the recorded review blockers before using delivery actions.",
    ),
}
_DELIVERY_EVIDENCE_FIELDS = frozenset(
    {
        "report_version",
        "schema_version",
        "workflow_type",
        "status",
        "status_label",
        "status_note",
        "delivery_record_available",
        "blocking_reasons",
        "blocking_count",
        "warning_count",
        "artifacts",
        "report_snapshot_id",
        "artifact_manifest_id",
        "canonical_sha256",
    }
)


@dataclass(frozen=True)
class FormalReportDeliveryDecision:
    """Verified delivery decision derived from identity-bound report evidence."""

    eligible: bool
    status: str
    markdown: str
    data: bytes
    content_sha256: str
    blocking_reasons: tuple[str, ...]
    blocking_count: int
    warning_count: int
    artifacts: tuple[Mapping[str, Any], ...]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def persisted_multi_tu_report_eligible(
    result: Any,
    *,
    result_preview_mode: bool,
) -> bool:
    """Allow persisted report delivery only from explicit durable review evidence."""
    if not result_preview_mode or not isinstance(result, Mapping):
        return False
    if str(result.get("result_kind") or "") != "MULTI_TU_EXPRESSION_ASSEMBLY":
        return False

    context = _mapping(result.get("formal_project_context"))
    if context.get("construct_review_status") != "current":
        return False

    combined = _mapping(result.get("combined_construct"))
    formal_validation = _mapping(combined.get("formal_validation"))
    return formal_validation.get("status") in {
        "formal_ready",
        "four_role_review_required",
    }


def _text(value: Any, fallback: str = "--") -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text or fallback


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _delivery_evidence_identity(value: Mapping[str, Any]) -> str:
    try:
        payload = _canonical_json(value).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Formal report delivery evidence is malformed.") from exc
    return f"sha256:{_sha256(payload)}"


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Formal report {field} must be a non-negative integer.")
    return value


def _follow_up_lines(status: str, warning_count: int, blockers: Sequence[str]) -> list[str]:
    if status == STATUS_BLOCKED:
        return [f"- {blocker}" for blocker in blockers]
    if status == STATUS_REVIEW_REQUIRED and warning_count:
        return ["- Manual review remains required for warning-level signals."]
    return ["- No additional canonical review blockers are recorded in this snapshot."]


def validate_formal_report_delivery(
    report: Mapping[str, Any],
) -> FormalReportDeliveryDecision:
    """Validate one formal-report projection and derive delivery eligibility."""
    if not isinstance(report, Mapping):
        raise ValueError("Formal report projection must be a mapping.")
    if report.get("version") != REPORT_VERSION:
        raise ValueError("Unsupported formal report version.")
    if report.get("schema_version") != REPORT_CONTRACT_SCHEMA_VERSION:
        raise ValueError("Unsupported formal report schema version.")

    status = report.get("status")
    if not isinstance(status, str) or status not in SUPPORTED_STATUSES:
        raise ValueError("Unsupported formal report delivery status.")
    markdown = report.get("markdown")
    data = report.get("data")
    digest = report.get("sha256")
    if not isinstance(markdown, str) or not markdown:
        raise ValueError("Formal report content is unavailable.")
    if not isinstance(data, bytes) or data != markdown.encode("utf-8"):
        raise ValueError("Formal report content identity does not match its Markdown bytes.")
    actual_digest = _sha256(data)
    if (
        not isinstance(digest, str)
        or not _SHA256_RE.fullmatch(digest)
        or digest != actual_digest
        or report.get("content_identity") != f"sha256:{actual_digest}"
    ):
        raise ValueError("Formal report content identity does not match its bytes.")

    raw_evidence = report.get("delivery_evidence")
    if not isinstance(raw_evidence, Mapping):
        raise ValueError("Formal report delivery evidence is unavailable.")
    evidence = dict(raw_evidence)
    if set(evidence) != _DELIVERY_EVIDENCE_FIELDS:
        raise ValueError("Formal report delivery evidence schema is malformed.")
    evidence_identity = _delivery_evidence_identity(evidence)
    if report.get("delivery_evidence_identity") != evidence_identity:
        raise ValueError("Formal report delivery evidence identity does not match its facts.")
    if markdown.splitlines().count(f"Delivery evidence identity: {evidence_identity}") != 1:
        raise ValueError("Formal report content does not bind its delivery evidence identity.")

    bound_fields = (
        "workflow_type",
        "status",
        "status_label",
        "status_note",
        "delivery_record_available",
        "blocking_reasons",
        "blocking_count",
        "warning_count",
        "artifacts",
        "report_snapshot_id",
        "artifact_manifest_id",
        "canonical_sha256",
    )
    if evidence.get("report_version") != REPORT_VERSION:
        raise ValueError("Formal report delivery evidence has an unsupported report version.")
    if evidence.get("schema_version") != REPORT_CONTRACT_SCHEMA_VERSION:
        raise ValueError("Formal report delivery evidence has an unsupported schema version.")
    for field in bound_fields:
        if report.get(field) != evidence.get(field):
            raise ValueError(f"Formal report {field} contradicts identity-bound evidence.")

    workflow_type = evidence.get("workflow_type")
    if workflow_type not in {"single_gene", "multi_tu"}:
        raise ValueError("Unsupported formal report workflow type.")
    status_label, status_note = _STATUS_DETAILS[status]
    if evidence.get("status") != status:
        raise ValueError("Formal report status contradicts identity-bound evidence.")
    if evidence.get("status_label") != status_label or evidence.get("status_note") != status_note:
        raise ValueError("Formal report delivery reasons contradict its status.")

    blocking_count = _nonnegative_integer(evidence.get("blocking_count"), "blocking_count")
    warning_count = _nonnegative_integer(evidence.get("warning_count"), "warning_count")
    raw_blockers = evidence.get("blocking_reasons")
    if not isinstance(raw_blockers, list) or any(
        not isinstance(item, str) or not item or item != item.strip() for item in raw_blockers
    ):
        raise ValueError("Formal report blocking reasons are malformed.")
    blockers = list(raw_blockers)
    if len(set(blockers)) != len(blockers):
        raise ValueError("Formal report blocking reasons contain duplicates.")

    canonical_reason_prefix = "The canonical review record contains "
    canonical_reasons = [item for item in blockers if item.startswith(canonical_reason_prefix)]
    expected_canonical_reason = (
        f"The canonical review record contains {blocking_count} blocking item(s)."
    )
    if blocking_count and canonical_reasons != [expected_canonical_reason]:
        raise ValueError("Formal report blocker count contradicts its blocker list.")
    if not blocking_count and canonical_reasons:
        raise ValueError("Formal report blocker list contradicts its blocker count.")

    raw_artifacts = evidence.get("artifacts")
    if not isinstance(raw_artifacts, list) or any(
        not isinstance(item, Mapping) for item in raw_artifacts
    ):
        raise ValueError("Formal report artifact evidence is malformed.")
    artifacts = [dict(item) for item in raw_artifacts]
    if [item.get("artifact_id") for item in artifacts] != [
        "fasta",
        "genbank",
        "plasmid_map",
    ]:
        raise ValueError("Formal report artifact evidence is incomplete or unordered.")
    for item in artifacts:
        if not isinstance(item.get("required"), bool) or not isinstance(item.get("available"), bool):
            raise ValueError("Formal report artifact availability is malformed.")
    unavailable = [
        str(item.get("label"))
        for item in artifacts
        if item.get("required") and not item.get("available")
    ]
    unavailable_prefix = "Missing canonical report artifact(s): "
    unavailable_reasons = [item for item in blockers if item.startswith(unavailable_prefix)]
    expected_unavailable_reason = unavailable_prefix + ", ".join(unavailable) + "."
    if unavailable and unavailable_reasons != [expected_unavailable_reason]:
        raise ValueError("Formal report artifact blockers contradict artifact availability.")
    if not unavailable and unavailable_reasons:
        raise ValueError("Formal report artifact blockers contradict artifact availability.")

    if status == STATUS_BLOCKED:
        if not blockers:
            raise ValueError("Blocked formal report has no identity-bound blocking evidence.")
        eligible = False
    elif blockers or blocking_count:
        raise ValueError("Deliverable formal report contains contradictory blocking evidence.")
    elif status == STATUS_REVIEW_REQUIRED:
        if warning_count < 1:
            raise ValueError("Review-required formal report has no warning evidence.")
        eligible = True
    else:
        if warning_count:
            raise ValueError("Ready formal report contains contradictory warning evidence.")
        eligible = True

    availability = evidence.get("delivery_record_available")
    if not isinstance(availability, bool) or availability is not eligible:
        raise ValueError("Formal report availability flag contradicts verified delivery evidence.")
    for field, value in (
        ("report_snapshot_id", evidence.get("report_snapshot_id")),
        ("artifact_manifest_id", evidence.get("artifact_manifest_id")),
        ("canonical_sha256", evidence.get("canonical_sha256")),
    ):
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError(f"Formal report {field} is malformed.")

    required_lines = (
        f"Report version: {REPORT_VERSION}",
        f"Canonical contract schema: {REPORT_CONTRACT_SCHEMA_VERSION}",
        f"ReportSnapshot ID: {evidence['report_snapshot_id']}",
        f"Artifact manifest ID: {evidence['artifact_manifest_id']}",
        f"Status: {status_label}",
        f"Note: {status_note}",
        f"Canonical SHA-256: {evidence['canonical_sha256']}",
        f"Blocking items: {blocking_count}",
        f"Warning items: {warning_count}",
    )
    markdown_lines = markdown.splitlines()
    if any(markdown_lines.count(line) != 1 for line in required_lines):
        raise ValueError("Formal report content contradicts identity-bound delivery evidence.")
    expected_follow_up = "\n".join(
        ["## Review Follow-up", "", *_follow_up_lines(status, warning_count, blockers), "", "## Boundary"]
    )
    if expected_follow_up not in markdown:
        raise ValueError("Formal report follow-up reasons contradict delivery evidence.")

    return FormalReportDeliveryDecision(
        eligible=eligible,
        status=status,
        markdown=markdown,
        data=data,
        content_sha256=actual_digest,
        blocking_reasons=tuple(blockers),
        blocking_count=blocking_count,
        warning_count=warning_count,
        artifacts=tuple(artifacts),
    )


def render_formal_report_markdown(report: Mapping[str, Any]) -> bytes:
    """Return Markdown bytes only when verified formal evidence permits delivery."""
    decision = validate_formal_report_delivery(report)
    if not decision.eligible:
        raise ValueError("Formal report delivery is blocked.")
    return decision.data


def _safe_file_stem(value: Any) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", _text(value, "BioDesign_Project"))
    return re.sub(r"_+", "_", stem).strip(" ._-") or "BioDesign_Project"


def _delivery_artifacts(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        _text(_mapping(item).get("artifact_id"), ""): _mapping(item)
        for item in list(snapshot.get("delivery_artifacts") or [])
    }
    rows: list[dict[str, Any]] = []
    for artifact_id, label, required in (
        ("fasta", "Canonical FASTA", True),
        ("genbank", "Canonical GenBank", True),
        ("plasmid_map", "Canonical plasmid map", False),
    ):
        item = by_id.get(artifact_id, {})
        available = item.get("status") == "available"
        rows.append(
            {
                "artifact_id": artifact_id,
                "label": label,
                "required": required,
                "file_name": _text(item.get("file_name"), f"canonical.{artifact_id}"),
                "available": available,
                "size_bytes": _integer(item.get("size_bytes")) if available else 0,
                "sha256": _text(item.get("sha256")) if available else "--",
                "canonical_sha256": _text(item.get("canonical_sha256")) if available else "--",
                "unavailable_reason": "" if available else _text(item.get("reason"), "not_available"),
            }
        )
    return rows


def project_final_review_report(
    report_contract: Mapping[str, Any],
    *,
    delivery_policy_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Project one validated canonical contract into the Step 6 report shape."""
    contract = _mapping(report_contract)
    if _text(contract.get("schema_version"), "") != REPORT_CONTRACT_SCHEMA_VERSION:
        raise ValueError("Unsupported formal results report contract schema.")
    snapshot = validate_formal_report_snapshot(_mapping(contract.get("report_snapshot")))
    manifest = validate_report_artifact_manifest(
        _mapping(contract.get("artifact_manifest")), snapshot
    )

    validation = _mapping(snapshot.get("validation_summary"))
    construct = _mapping(snapshot.get("construct_summary"))
    freshness = _mapping(snapshot.get("freshness"))
    project = _mapping(snapshot.get("project"))
    canonical = _mapping(manifest.get("canonical_sequence_identity"))
    workflow_type = _text(snapshot.get("workflow_type"), "")
    artifacts = _delivery_artifacts(snapshot)
    blocking_count = _integer(validation.get("blocking_count"))
    warning_count = _integer(validation.get("warning_count"))

    blockers: list[str] = []
    if _text(freshness.get("state"), "") != "current":
        blockers.append("The canonical report snapshot is not current.")
    if blocking_count:
        blockers.append(f"The canonical review record contains {blocking_count} blocking item(s).")
    unavailable = [
        row["label"] for row in artifacts if row["required"] and not row["available"]
    ]
    if unavailable:
        blockers.append("Missing canonical report artifact(s): " + ", ".join(unavailable) + ".")
    for value in delivery_policy_blockers:
        blocker = _text(value, "")
        if blocker and blocker not in blockers:
            blockers.append(blocker)

    if blockers:
        status = STATUS_BLOCKED
        delivery_record_available = False
    elif warning_count:
        status = STATUS_REVIEW_REQUIRED
        delivery_record_available = True
    else:
        status = STATUS_AVAILABLE
        delivery_record_available = True
    status_label, status_note = _STATUS_DETAILS[status]

    project_name = _text(project.get("name"), "Plant expression vector project")
    title_type = "Multi-TU" if workflow_type == "multi_tu" else "Single-Gene"
    route_data = _mapping(snapshot.get("route_specific_data"))
    step_outputs = _mapping(route_data.get("step_outputs"))
    step_3 = _mapping(_mapping(step_outputs.get("step_3")).get("facts"))
    step_4 = _mapping(_mapping(step_outputs.get("step_4")).get("facts"))
    component_summary = _mapping(snapshot.get("component_summary"))
    components = [
        _mapping(item) for item in list(component_summary.get("components") or [])
    ]
    provenance = _mapping(snapshot.get("provenance_summary"))
    complete_plasmid = _mapping(construct.get("complete_plasmid"))
    boundary = _mapping(snapshot.get("boundary"))
    report_snapshot_id = _text(snapshot.get("snapshot_id"))
    artifact_manifest_id = _text(manifest.get("manifest_id"))
    canonical_sha256 = _text(canonical.get("sha256"))
    does_not_establish = [
        _text(item, "")
        for item in list(boundary.get("does_not_establish") or [])
        if _text(item, "")
    ]
    delivery_evidence = {
        "report_version": REPORT_VERSION,
        "schema_version": REPORT_CONTRACT_SCHEMA_VERSION,
        "workflow_type": workflow_type,
        "status": status,
        "status_label": status_label,
        "status_note": status_note,
        "delivery_record_available": delivery_record_available,
        "blocking_reasons": list(blockers),
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "artifacts": [dict(item) for item in artifacts],
        "report_snapshot_id": report_snapshot_id,
        "artifact_manifest_id": artifact_manifest_id,
        "canonical_sha256": canonical_sha256,
    }
    delivery_evidence_identity = _delivery_evidence_identity(delivery_evidence)

    step_1 = _mapping(_mapping(step_outputs.get('step_1')).get('facts'))
    step_2 = _mapping(_mapping(step_outputs.get('step_2')).get('facts'))
    context = _mapping(step_1.get('project_context'))
    has_backbone = complete_plasmid.get('status') == 'available'
    backbone_refs = [item for item in _mapping(snapshot.get('provenance_summary')).get('source_records', []) if _mapping(item).get('role') == 'backbone']
    features = list(_mapping(snapshot.get('feature_summary')).get('features') or [])
    lines = [
        f"# {title_type} Final Review and Delivery Record",
        "",
        '## Project and Design Summary', '',
        f'Project: {project_name}',
        f"Design scenario: {_text(context.get('design_scenario'), title_type)}",
        '',
        '## Host and Target', '',
        f"Host: {_text(_mapping(_mapping(snapshot.get('host')).get('facts')).get('host_key'), 'Not recorded')}",
        f"Target: {_text(_mapping(_mapping(snapshot.get('design_goal')).get('facts')).get('expression_target'), 'Not recorded')}", '',
        '## Transcription Units and Pathway', '',
        f"Transcription unit count: {_integer(step_3.get('transcription_unit_count'))}",
    ]
    for unit in step_2.get('transcription_units', []):
        lines.append(f"- TU{_integer(unit.get('order'))}: {_text(unit.get('orientation'))}")
    lines.extend(['', '## Backbone', '',
        ('Complete plasmid includes a backbone; its source record is listed in provenance.' if has_backbone else 'Not applicable / no backbone included'),
        '', '## Insertion and Replacement', '',
        (f"Original {step_4.get('mode')} interval (1-based inclusive): {_integer(step_4.get('start_coordinate'))}..{_integer(step_4.get('end_coordinate'))}" if has_backbone else 'Not applicable / no backbone included'),
        f"Inserted expression region length: {_integer(construct.get('cassette_length_bp'))} bp" if has_backbone else 'Expression assembly only.',
        '', '## Component Provenance and Evidence', '',
    ])
    for component in components:
        lines.append(f"- {_text(component.get('name'))} | {_text(component.get('role'))} | source: {_text(component.get('source'))} | reference: {_text(component.get('accession'))}")
    lines.extend(['', '## Map and Feature Summary', '',
        f"Topology: {_text(canonical.get('topology'))}",
        f"Recorded features: {len(features)}", '',
    ])
    for feature in features:
        lines.append(f"- {_text(feature.get('name'))}: {_integer(feature.get('start'))}..{_integer(feature.get('end'))} (1-based inclusive), strand {_integer(feature.get('strand'))}")
    lines.extend(['', '## Review Notes', '',
        f'Warning findings recorded: {warning_count}',
        *_follow_up_lines(status, warning_count, blockers),
        '', '## Technical Identities, Hashes and Manifest', '',
        f"Report version: {REPORT_VERSION}",
        f"Canonical contract schema: {_text(contract.get('schema_version'))}",
        f"ReportSnapshot ID: {report_snapshot_id}",
        f"Artifact manifest ID: {artifact_manifest_id}",
        f"Delivery evidence identity: {delivery_evidence_identity}",
        f"Project: {project_name}",
        f"Project ID: {_text(project.get('project_id'))}",
        f"Workflow type: {workflow_type}",
        "",
        "## Review Status",
        "",
        f"Status: {status_label}",
        f"Note: {status_note}",
        "",
        "## Canonical Sequence Record",
        "",
        f"Canonical length: {_integer(canonical.get('length_bp'))} bp",
        f"Canonical topology: {_text(canonical.get('topology'))}",
        f"Canonical SHA-256: {canonical_sha256}",
        f"Canonical input signature: {_text(canonical.get('input_signature'))}",
        f"Expression cassette length: {_integer(construct.get('cassette_length_bp'))} bp",
        f"Expression cassette SHA-256: {_text(construct.get('cassette_sha256'))}",
    ])
    if workflow_type == "multi_tu":
        lines.append(f"Transcription unit count: {_integer(step_3.get('transcription_unit_count'))}")
    lines.extend(
        [
            f"Complete plasmid status: {_text(complete_plasmid.get('status'), 'unavailable')}",
            "",
            "## Component Identity and Provenance",
            "",
        ]
    )
    assisted_by_component = {
        _text(item.get('component_id')): _mapping(item.get('assisted_provenance'))
        for item in _mapping(component_summary.get('authority')).get('records', [])
        if isinstance(item, Mapping) and item.get('assisted_provenance')
    }
    for component in components:
        lines.append(
            "- "
            f"{_integer(component.get('order'))}. {_text(component.get('name'))} | "
            f"role={_text(component.get('role'))} | "
            f"component_id={_text(component.get('component_id'))} | "
            f"source={_text(component.get('source'))} | "
            f"reference={_text(component.get('accession'))} | "
            f"length={_integer(component.get('length_bp'))} bp"
        )
        assisted = assisted_by_component.get(_text(component.get('component_id')), {})
        if assisted:
            for label, field in (
                ('V2 canonical ID', 'catalog_component_id'),
                ('Catalog identity', 'catalog_name'),
                ('Source accession', 'source_accession'),
                ('Original route', 'original_route'),
                ('Sequence authority', 'authority'),
                ('User sequence source / file label', 'source_label'),
                ('Reviewed source boundary', 'reviewed_source_boundary'),
                ('Sequence SHA-256', 'sequence_sha256'),
                ('Project binding', 'project_id'),
                ('Project resolution ID', 'resolution_id'),
                ('Confirmation mode', 'confirmation_mode'),
            ):
                if assisted.get(field):
                    lines.append(f"  - {label}: {_text(assisted[field])}")
            for field in ('accession_verified', 'boundary_verified_by_software'):
                value = assisted.get(field)
                displayed = str(value).lower() if isinstance(value, bool) else 'not_recorded'
                lines.append(f"  - {field}={displayed}")
            lines.append(
                '  - USER_PROVIDED sequence; the accession and source boundary are recorded provenance, '
                'not independent software verification. SHA-256 identifies supplied bytes, not source identity.'
            )
    if not components:
        lines.append("- No canonical component records are available.")
    lines.extend(
        [
            f"Provenance identity: {_text(provenance.get('identity'))}",
            "",
            "## Vector Strategy",
            "",
            f"Workflow ID: {_text(step_4.get('workflow_id'))}",
            f"Mode: {_text(step_4.get('mode'))}",
            (f"Coordinates (1-based inclusive): {_integer(step_4.get('start_coordinate'))}..{_integer(step_4.get('end_coordinate'))}" if has_backbone else 'Coordinates: Not applicable / no backbone included'),
            f"Orientation: {_text(step_4.get('orientation'))}",
            "",
            "## Review Counts",
            "",
            f"Blocking items: {blocking_count}",
            f"Warning items: {warning_count}",
            "",
            "## Canonical Delivery Artifacts",
            "",
        ]
    )
    for artifact in artifacts:
        availability = "available" if artifact["available"] else "unavailable"
        lines.extend(
            [
                f"- {artifact['label']}: {availability}",
                f"  File: {artifact['file_name']}",
                f"  Bytes: {artifact['size_bytes']}",
                f"  SHA-256: {artifact['sha256']}",
                f"  Canonical SHA-256: {artifact['canonical_sha256']}",
            ]
        )
        if not artifact["available"]:
            lines.append(f"  Reason: {artifact['unavailable_reason']}")
    lines.extend(["", "## Review Follow-up", ""])
    lines.extend(_follow_up_lines(status, warning_count, blockers))
    lines.extend(["", "## Boundary", ""])
    if does_not_establish:
        lines.append(
            "This documentation-only design review record does not establish "
            + ", ".join(does_not_establish)
            + "."
        )
    else:
        lines.append("This is a documentation-only design review record for professional review.")
    lines.append("")

    markdown = "\n".join(lines)
    data = markdown.encode("utf-8")
    content_sha256 = _sha256(data)
    file_stem = _safe_file_stem(project_name)
    return {
        "version": REPORT_VERSION,
        "schema_version": REPORT_CONTRACT_SCHEMA_VERSION,
        "workflow_type": workflow_type,
        "status": status,
        "status_label": status_label,
        "status_note": status_note,
        "delivery_record_available": delivery_record_available,
        "blocking_reasons": blockers,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "artifacts": artifacts,
        "report_snapshot_id": report_snapshot_id,
        "artifact_manifest_id": artifact_manifest_id,
        "canonical_sha256": canonical_sha256,
        "delivery_evidence": delivery_evidence,
        "delivery_evidence_identity": delivery_evidence_identity,
        "markdown": markdown,
        "data": data,
        "sha256": content_sha256,
        "content_identity": f"sha256:{content_sha256}",
        "file_name": f"{file_stem}_final_review.md",
        "pdf_file_name": f"{file_stem}_final_review.pdf",
    }


def build_final_review_report(
    project_record: Mapping[str, Any],
    *,
    delivery_policy_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the canonical contract once and return its deterministic projection."""
    from services.formal_results_report_contract import build_formal_results_report_contract

    return project_final_review_report(
        build_formal_results_report_contract(project_record),
        delivery_policy_blockers=delivery_policy_blockers,
    )
