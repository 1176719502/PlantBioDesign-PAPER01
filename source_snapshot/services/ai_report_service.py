"""Guarded AI-assisted drafts over a deterministic FormalReportSnapshot."""
from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.ai_provider import AIReportProvider, DisabledAIReportProvider, ProviderResponse, configured_ai_report_provider
from services.formal_report_snapshot import FormalReportSnapshotError, validate_formal_report_snapshot


REPORT_SCHEMA_VERSION = "ai-final-report-v1"
PROVIDER_PROJECTION_SCHEMA_VERSION = "ai-report-provider-projection-v1"
STATUS_AI_ASSISTED_DRAFT = "ai_assisted_draft"
STATUS_UNAVAILABLE = "unavailable"
STATUS_REJECTED = "rejected"
_SECTION_FIELDS = (
    "executive_summary",
    "design_interpretation",
    "validation_interpretation",
    "manual_review_points",
    "limitations",
    "delivery_summary",
)
_ITEM_REQUIRED_FIELDS = frozenset({"interpretation_code", "semantic_fact_tokens"})
_ITEM_ALLOWED_FIELDS = _ITEM_REQUIRED_FIELDS | {"display_order"}
_FACT_REF_SEGMENT_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_]*)(?:\[(?P<index>\d+)\])?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_FRESHNESS_VALUES = frozenset({"current", "stale", "unknown"})
_MAX_PROVIDER_COUNT = 1_000_000
_INTERPRETATION_CODES = frozenset(
    {
        "DESIGN_SUMMARY_AVAILABLE",
        "CANONICAL_CONSTRUCT_PRESENT",
        "CANONICAL_CONSTRUCT_ABSENT",
        "NO_BLOCKERS_REPORTED",
        "WARNINGS_REQUIRE_REVIEW",
        "BLOCKERS_REQUIRE_REVIEW",
        "MANUAL_REVIEW_REQUIRED",
        "DELIVERY_ARTIFACTS_AVAILABLE",
        "DELIVERY_ARTIFACTS_INCOMPLETE",
        "RECORD_REVIEW_REQUIRED",
        "DOCUMENTATION_ONLY",
    }
)
_RENDERED_CODE_TEXT = {
    "DESIGN_SUMMARY_AVAILABLE": "Design summary facts are available for manual review.",
    "CANONICAL_CONSTRUCT_PRESENT": "A canonical construct is recorded.",
    "CANONICAL_CONSTRUCT_ABSENT": "No canonical construct is recorded.",
    "NO_BLOCKERS_REPORTED": "No blockers are recorded in the referenced validation facts.",
    "WARNINGS_REQUIRE_REVIEW": "Recorded warnings require manual review.",
    "BLOCKERS_REQUIRE_REVIEW": "Recorded blockers require manual review.",
    "MANUAL_REVIEW_REQUIRED": "Manual review remains required.",
    "DELIVERY_ARTIFACTS_AVAILABLE": "Referenced delivery artifacts are available.",
    "DELIVERY_ARTIFACTS_INCOMPLETE": "Referenced delivery artifacts are incomplete.",
    "RECORD_REVIEW_REQUIRED": "Referenced record facts require manual review.",
    "DOCUMENTATION_ONLY": "This is a documentation-only record.",
}


class AIReportDraftError(ValueError):
    """A provider draft cannot be safely connected to its snapshot."""


class ProviderReportProjectionError(AIReportDraftError):
    """A local snapshot cannot be safely represented for a provider."""


@dataclass(frozen=True)
class _BoundProviderFact:
    token: str
    kind: str
    value: bool | int


@dataclass(frozen=True)
class _InterpretationContract:
    semantics: frozenset[str]
    predicate: Any


_SEMANTIC_CONTRACTS = {
    "DESIGN_SUMMARY_AVAILABLE": _InterpretationContract(frozenset({"DESIGN_SUMMARY_FLAG"}), bool),
    "CANONICAL_CONSTRUCT_PRESENT": _InterpretationContract(frozenset({"CANONICAL_PRESENT"}), lambda value: value is True),
    "CANONICAL_CONSTRUCT_ABSENT": _InterpretationContract(frozenset({"CANONICAL_PRESENT"}), lambda value: value is False),
    "NO_BLOCKERS_REPORTED": _InterpretationContract(frozenset({"VAL_BLOCKING_COUNT"}), lambda value: _is_count(value) and value == 0),
    "WARNINGS_REQUIRE_REVIEW": _InterpretationContract(frozenset({"VAL_WARNING_COUNT"}), lambda value: _is_count(value) and value > 0),
    "BLOCKERS_REQUIRE_REVIEW": _InterpretationContract(frozenset({"VAL_BLOCKING_COUNT"}), lambda value: _is_count(value) and value > 0),
    "MANUAL_REVIEW_REQUIRED": _InterpretationContract(frozenset({"MANUAL_REVIEW_FLAG"}), lambda value: value is True),
    "DELIVERY_ARTIFACTS_AVAILABLE": _InterpretationContract(frozenset({"DELIVERY_AVAILABLE"}), lambda value: value is True),
    "DELIVERY_ARTIFACTS_INCOMPLETE": _InterpretationContract(frozenset({"DELIVERY_AVAILABLE"}), lambda value: value is False),
    "DOCUMENTATION_ONLY": _InterpretationContract(frozenset({"DOC_ONLY_FLAG"}), lambda value: value is True),
}


def _text(value: Any) -> str:
    return " ".join(str("" if value is None else value).replace("\x00", "").split())


def approved_fact_refs(snapshot: Mapping[str, Any]) -> set[str]:
    """Return provider-visible opaque semantic tokens (legacy public name)."""
    return {fact["token"] for fact in build_provider_report_projection(snapshot)["facts"]}


def _empty_report(snapshot_id: str, *, status: str, reason: str, provider_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "status": status,
        **{field: [] for field in _SECTION_FIELDS},
        "rendered_sections": {field: [] for field in _SECTION_FIELDS},
        "provider_metadata": {"provider": "disabled", "reason": reason, **dict(provider_metadata or {})},
    }


def _parse_content(content: Any) -> dict[str, Any]:
    if isinstance(content, Mapping):
        return dict(content)
    if not isinstance(content, str):
        raise AIReportDraftError("Provider returned no structured report content.")
    try:
        loaded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIReportDraftError("Provider returned malformed JSON.") from exc
    if not isinstance(loaded, Mapping):
        raise AIReportDraftError("Provider JSON must be an object.")
    return dict(loaded)


def _resolve_fact(snapshot: Mapping[str, Any], fact_ref: str) -> Any:
    """Resolve one approved, scalar fact reference without accepting object paths."""
    value: Any = snapshot
    for segment in fact_ref.split("."):
        match = _FACT_REF_SEGMENT_RE.fullmatch(segment)
        if not match or not isinstance(value, Mapping) or match.group("key") not in value:
            raise AIReportDraftError("Draft contains an ambiguous or unknown fact reference.")
        value = value[match.group("key")]
        if match.group("index") is not None:
            index = int(match.group("index"))
            if not isinstance(value, Sequence) or isinstance(value, str) or index >= len(value):
                raise AIReportDraftError("Draft contains an ambiguous or unknown fact reference.")
            value = value[index]
    if isinstance(value, Mapping) or (isinstance(value, Sequence) and not isinstance(value, str)):
        raise AIReportDraftError("Draft fact references must resolve to scalar values.")
    return value


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_PROVIDER_COUNT


def _add_bound_fact(
    facts: list[_BoundProviderFact],
    snapshot: Mapping[str, Any],
    ref: str,
    token: str,
    *,
    kind: str,
    value: bool | int,
) -> None:
    local_value = _resolve_fact(snapshot, ref)
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ProviderReportProjectionError(f"Provider fact '{ref}' must be a boolean.")
        if token in {"CANONICAL_PRESENT", "MANUAL_REVIEW_FLAG", "DOC_ONLY_FLAG", "DELIVERY_AVAILABLE"} and not isinstance(local_value, bool):
            raise ProviderReportProjectionError(f"Provider fact '{ref}' must resolve to a local boolean.")
    elif kind == "integer":
        if not _is_count(local_value) or not _is_count(value):
            raise ProviderReportProjectionError(f"Provider fact '{ref}' must be a bounded non-negative integer.")
    else:
        raise ProviderReportProjectionError("Provider projection contains an unsupported fact kind.")
    facts.append(_BoundProviderFact(token=token, kind=kind, value=value))


def _bound_provider_facts(snapshot: Mapping[str, Any]) -> list[_BoundProviderFact]:
    """Build the finite fact registry without forwarding any snapshot branch."""
    facts: list[_BoundProviderFact] = []
    for ref, token in (
        ("construct_summary.canonical_construct_present", "CANONICAL_PRESENT"),
        ("boundary.manual_review_required", "MANUAL_REVIEW_FLAG"),
        ("boundary.documentation_only", "DOC_ONLY_FLAG"),
    ):
        try:
            value = _resolve_fact(snapshot, ref)
        except AIReportDraftError:
            continue
        _add_bound_fact(facts, snapshot, ref, token, kind="boolean", value=value)
    for ref, token in (
        ("validation_summary.blocking_count", "VAL_BLOCKING_COUNT"),
        ("validation_summary.warning_count", "VAL_WARNING_COUNT"),
    ):
        try:
            value = _resolve_fact(snapshot, ref)
        except AIReportDraftError:
            continue
        _add_bound_fact(facts, snapshot, ref, token, kind="integer", value=value)
    try:
        design_summary = _resolve_fact(snapshot, "design_goal.summary")
    except AIReportDraftError:
        design_summary = None
    if isinstance(design_summary, str) and bool(design_summary):
        _add_bound_fact(
            facts,
            snapshot,
            "design_goal.summary",
            "DESIGN_SUMMARY_FLAG",
            kind="boolean",
            value=True,
        )
    for artifact in snapshot.get("delivery_artifacts", []):
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("available"), bool):
            continue
        ref = f"delivery_artifacts[{snapshot['delivery_artifacts'].index(artifact)}].available"
        _add_bound_fact(facts, snapshot, ref, "DELIVERY_AVAILABLE", kind="boolean", value=artifact["available"])
        break
    return facts


def build_provider_report_projection(snapshot: Mapping[str, Any], *, provider_request_id: str | None = None) -> dict[str, Any]:
    """Create the only typed, explicitly constructed payload a provider may see."""
    data = validate_formal_report_snapshot(snapshot)
    freshness = data["freshness"].get("state", "unknown")
    if not isinstance(freshness, str) or freshness not in _FRESHNESS_VALUES:
        raise ProviderReportProjectionError("Provider projection requires an allow-listed freshness state.")
    facts = _bound_provider_facts(data)
    canonical_present = next(
        (fact.value for fact in facts if fact.token == "CANONICAL_PRESENT"),
        None,
    )
    if not isinstance(canonical_present, bool):
        raise ProviderReportProjectionError("Provider projection requires an explicit canonical construct boolean.")
    projection = {
        "schema_version": PROVIDER_PROJECTION_SCHEMA_VERSION,
        "snapshot_id": data["snapshot_id"],
        "provider_request_id": provider_request_id or secrets.token_urlsafe(24),
        "workflow_type": data["workflow_type"],
        "freshness": freshness,
        "canonical_construct_present": canonical_present,
        "facts": [
            {"token": fact.token, "kind": fact.kind, "value": fact.value}
            for fact in facts
        ],
        "allowed_interpretation_codes": sorted(_INTERPRETATION_CODES),
    }
    _validate_provider_projection(projection)
    return projection


def _validate_provider_projection(projection: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "snapshot_id", "provider_request_id", "workflow_type", "freshness", "canonical_construct_present", "facts", "allowed_interpretation_codes",
    }
    if set(projection) != required:
        raise ProviderReportProjectionError("Provider projection schema mismatch.")
    if projection["schema_version"] != PROVIDER_PROJECTION_SCHEMA_VERSION:
        raise ProviderReportProjectionError("Provider projection schema version is unsupported.")
    if not isinstance(projection["snapshot_id"], str) or not _SHA256_RE.fullmatch(projection["snapshot_id"]):
        raise ProviderReportProjectionError("Provider projection snapshot ID is invalid.")
    if not isinstance(projection["provider_request_id"], str) or not projection["provider_request_id"]:
        raise ProviderReportProjectionError("Provider projection request ID is invalid.")
    if projection["workflow_type"] not in {"single_gene", "multi_tu", "pathway"}:
        raise ProviderReportProjectionError("Provider projection workflow type is invalid.")
    if projection["freshness"] not in _FRESHNESS_VALUES or not isinstance(projection["canonical_construct_present"], bool):
        raise ProviderReportProjectionError("Provider projection contains an invalid enum or boolean.")
    if projection["allowed_interpretation_codes"] != sorted(_INTERPRETATION_CODES):
        raise ProviderReportProjectionError("Provider projection interpretation codes are invalid.")
    if not isinstance(projection["facts"], list):
        raise ProviderReportProjectionError("Provider projection facts must be a list.")
    seen_tokens: set[str] = set()
    for fact in projection["facts"]:
        if not isinstance(fact, Mapping) or set(fact) != {"token", "kind", "value"}:
            raise ProviderReportProjectionError("Provider projection fact schema mismatch.")
        if not isinstance(fact["token"], str) or fact["token"] in seen_tokens:
            raise ProviderReportProjectionError("Provider projection contains an invalid semantic token.")
        seen_tokens.add(fact["token"])
        if fact["kind"] == "boolean" and not isinstance(fact["value"], bool):
            raise ProviderReportProjectionError("Provider projection contains an invalid boolean fact.")
        elif fact["kind"] == "integer" and not _is_count(fact["value"]):
            raise ProviderReportProjectionError("Provider projection contains an invalid integer fact.")
        elif fact["kind"] not in {"boolean", "integer"}:
            raise ProviderReportProjectionError("Provider projection contains an unsupported fact kind.")


def _validate_interpretation_code(
    code: str,
    tokens: Sequence[str],
    snapshot: Mapping[str, Any],
    bound_facts: Mapping[str, _BoundProviderFact],
) -> None:
    """Bind a provider code to one exact local ref and its named semantic."""
    contract = _SEMANTIC_CONTRACTS[code]
    if len(tokens) != 1:
        raise AIReportDraftError(f"Interpretation code '{code}' requires exactly one semantic token.")
    bound_fact = bound_facts.get(tokens[0])
    if bound_fact is None or bound_fact.token not in contract.semantics:
        raise AIReportDraftError(f"Interpretation code '{code}' is not bound to its permitted semantic token.")
    local_value = bound_fact.value
    if not contract.predicate(local_value):
        raise AIReportDraftError(f"Interpretation code '{code}' predicate does not match the local snapshot fact.")


def _normalized_item(
    item: Any,
    snapshot: Mapping[str, Any],
    bound_facts: Mapping[str, _BoundProviderFact],
) -> dict[str, Any]:
    if not isinstance(item, Mapping) or set(item) - _ITEM_ALLOWED_FIELDS or _ITEM_REQUIRED_FIELDS - set(item):
        raise AIReportDraftError("Draft interpretation items must contain only interpretation_code, semantic_fact_tokens, and display_order.")
    code = item.get("interpretation_code")
    if not isinstance(code, str) or code not in _INTERPRETATION_CODES:
        raise AIReportDraftError("Draft contains an unknown interpretation code.")
    tokens = item.get("semantic_fact_tokens")
    if not isinstance(tokens, list) or not tokens or not all(isinstance(token, str) for token in tokens) or len(set(tokens)) != len(tokens):
        raise AIReportDraftError("Each interpretation item must cite unique semantic tokens.")
    if not set(tokens).issubset(bound_facts):
        raise AIReportDraftError("Draft references unknown semantic tokens.")
    _validate_interpretation_code(code, tokens, snapshot, bound_facts)
    normalized: dict[str, Any] = {"interpretation_code": code, "semantic_fact_tokens": list(tokens)}
    if "display_order" in item:
        display_order = item["display_order"]
        if not isinstance(display_order, int) or isinstance(display_order, bool) or display_order < 0:
            raise AIReportDraftError("display_order must be a non-negative integer.")
        normalized["display_order"] = display_order
    return normalized


def _render_interpretation(item: Mapping[str, Any], bound_facts: Mapping[str, _BoundProviderFact]) -> str:
    facts = []
    for token in item["semantic_fact_tokens"]:
        value = bound_facts[token].value
        facts.append(f"{token}: {str(value).lower() if isinstance(value, bool) else _text(value)}")
    return f"{_RENDERED_CODE_TEXT[item['interpretation_code']]} Referenced facts: {'; '.join(facts)}."


def _validated_draft(
    content: Any,
    snapshot: Mapping[str, Any],
    metadata: Mapping[str, Any],
    bound_facts: Mapping[str, _BoundProviderFact],
) -> dict[str, Any]:
    draft = _parse_content(content)
    required = {"schema_version", "snapshot_id", "provider_request_id", "status", *_SECTION_FIELDS}
    if set(draft) - required:
        raise AIReportDraftError("Draft contains unsupported fields.")
    missing = required - set(draft)
    if missing:
        raise AIReportDraftError(f"Draft is missing required fields: {sorted(missing)}.")
    if _text(draft["schema_version"]) != REPORT_SCHEMA_VERSION:
        raise AIReportDraftError("Draft schema version does not match.")
    if _text(draft["snapshot_id"]) != _text(snapshot["snapshot_id"]):
        raise AIReportDraftError("Draft snapshot ID does not match.")
    if _text(draft["provider_request_id"]) != _text(metadata.get("provider_request_id")):
        raise AIReportDraftError("Draft request ID does not match.")
    if _text(draft["status"]) != STATUS_AI_ASSISTED_DRAFT:
        raise AIReportDraftError("Draft status must identify an AI-assisted draft.")
    sections: dict[str, list[dict[str, Any]]] = {}
    rendered_sections: dict[str, list[str]] = {}
    for field in _SECTION_FIELDS:
        raw_items = draft[field]
        if not isinstance(raw_items, list):
            raise AIReportDraftError(f"Draft section '{field}' must be a list of structured interpretation items.")
        items = [_normalized_item(item, snapshot, bound_facts) for item in raw_items]
        ordered_items = [
            item
            for _, item in sorted(
                enumerate(items),
                key=lambda entry: (entry[1].get("display_order", entry[0]), entry[0]),
            )
        ]
        sections[field] = ordered_items
        rendered_sections[field] = [_render_interpretation(item, bound_facts) for item in ordered_items]
    if not isinstance(metadata, Mapping):
        raise AIReportDraftError("Provider metadata must be a mapping.")
    provider_metadata = {
        key: _text(metadata[key])
        for key in ("provider", "model", "provider_request_id")
        if key in metadata
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "snapshot_id": snapshot["snapshot_id"],
        "status": STATUS_AI_ASSISTED_DRAFT,
        **sections,
        "rendered_sections": rendered_sections,
        "provider_metadata": provider_metadata,
    }


def build_ai_report_draft(
    snapshot: Mapping[str, Any],
    *,
    provider: AIReportProvider | None = None,
    deterministic_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an optional draft; all provider failures degrade to a stable fallback.

    ``deterministic_report`` is accepted solely so callers can assert it is not
    changed.  It is intentionally not sent to a provider or returned here.
    """
    del deterministic_report
    try:
        normalized_snapshot = validate_formal_report_snapshot(snapshot)
    except FormalReportSnapshotError:
        supplied_id = snapshot.get("snapshot_id") if isinstance(snapshot, Mapping) else ""
        safe_id = supplied_id if isinstance(supplied_id, str) and _SHA256_RE.fullmatch(supplied_id) else ""
        return _empty_report(safe_id, status=STATUS_REJECTED, reason="snapshot_sanitization_failed")
    try:
        provider_request_id = secrets.token_urlsafe(24)
        projection = build_provider_report_projection(normalized_snapshot, provider_request_id=provider_request_id)
    except (FormalReportSnapshotError, ProviderReportProjectionError, AttributeError, TypeError, KeyError, IndexError):
        return _empty_report(normalized_snapshot["snapshot_id"], status=STATUS_REJECTED, reason="provider_projection_failed")
    bound_facts = {
        fact.token: fact
        for fact in _bound_provider_facts(normalized_snapshot)
    }
    selected = provider or configured_ai_report_provider()
    request_payload = {"projection": projection}
    try:
        response = selected.generate_report_draft(request_payload)
        if isinstance(response, Mapping):
            response = ProviderResponse(content=dict(response), metadata={"provider": "custom"})
        if not isinstance(response, ProviderResponse):
            raise AIReportDraftError("Provider must return ProviderResponse or a mapping.")
        metadata = {**dict(response.metadata), "provider_request_id": provider_request_id}
        return _validated_draft(response.content, normalized_snapshot, metadata, bound_facts)
    except AIReportDraftError as exc:
        return _empty_report(normalized_snapshot["snapshot_id"], status=STATUS_REJECTED, reason=_text(exc))
    except Exception:
        reason = "provider_disabled" if isinstance(selected, DisabledAIReportProvider) else "provider_unavailable"
        provider_name = "disabled" if isinstance(selected, DisabledAIReportProvider) else selected.__class__.__name__
        return _empty_report(
            normalized_snapshot["snapshot_id"],
            status=STATUS_UNAVAILABLE,
            reason=reason,
            provider_metadata={"provider": provider_name},
        )
