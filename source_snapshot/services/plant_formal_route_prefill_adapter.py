"""Pure adapter from a confirmed advisory route to formal prefill drafts.

The adapter is intentionally session-agnostic. It validates and binds the
current user inputs, then returns plain prefill data for a later UI wiring
batch. It never writes project state or grants formal workflow authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import hmac
import json
from typing import Any

from services.formal_cds_workflow import analyze_formal_cds
from services.plant_component_candidate_matcher import match_plant_component_candidates
from services.plant_host_registry import SINGLE_GENE_COMPLETE_VECTOR, list_hosts
from services.plant_simple_wizard_intent_intake_presenter import (
    build_simple_plant_wizard_intent_intake_presenter,
)
from services.plant_simple_wizard_route_confirmation_presenter import (
    build_simple_plant_wizard_route_confirmation_presenter,
)
from services.plant_user_intent_route_draft_builder import (
    build_plant_expression_route_draft,
)


ADAPTER_SCHEMA_VERSION = "plant-formal-route-prefill-adapter.v1"
INPUT_SIGNATURE_VERSION = "plant-formal-route-prefill-input.v1"
READY_STATUS = "formal_prefill_draft_ready"
FAIL_CLOSED_STATUS = "formal_prefill_fail_closed"
DEFAULT_USER_PROVIDED_CDS_DISPLAY_NAME = "用户提供的 CDS"

_FORMAL_PROJECT_TYPE = "single_gene"
_FORMAL_DESIGN_SCENARIO = "standard_plant_expression_vector"

ROUTE_CROSSWALK: dict[str, dict[str, Any]] = {
    "plant_protein_expression_review": {
        "formal_project_type": _FORMAL_PROJECT_TYPE,
        "formal_design_scenario": _FORMAL_DESIGN_SCENARIO,
        "single_gene_supported": True,
    },
    "plant_metabolic_pathway_review": {
        "formal_project_type": "multi_tu",
        "formal_design_scenario": "metabolic_pathway_multi_tu_vector",
        "single_gene_supported": False,
    },
    "plant_multigene_construct_review": {
        "formal_project_type": "multi_tu",
        "formal_design_scenario": "multi_tu",
        "single_gene_supported": False,
    },
    "plant_regulatory_module_review": {
        "formal_project_type": "regulatory_module",
        "formal_design_scenario": "regulatory_module",
        "single_gene_supported": False,
    },
}

_GENE_INFORMATION_FIELDS = (
    "gene_name",
    "gene_symbol",
    "source_species",
    "source_type",
    "source_reference",
    "modification_status",
    "modification_note",
    "is_partial_cds",
    "note",
)
_DISPLAY_NAME_FIELDS = (
    "gene_name",
    "gene_symbol",
    "display_name",
    "record_name",
    "name",
)


class PlantFormalRoutePrefillInputError(ValueError):
    """Raised only by the standalone signature helper for invalid inputs."""

    def __init__(self, message: str, *, reason_code: str = "") -> None:
        super().__init__(message)
        self.reason_code = str(reason_code or "").strip()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _plain_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return str(value)


def _storage_value(host_record: Mapping[str, Any]) -> str:
    aliases = list(host_record.get("aliases") or [])
    suffix = _text(aliases[0] if aliases else host_record.get("scientific_name"))
    return f"{_text(host_record.get('common_name'))} ({suffix})"


def _host_search_values(host_record: Mapping[str, Any]) -> set[str]:
    values = {
        _text(host_record.get("host_id")),
        _text(host_record.get("common_name")),
        _text(host_record.get("scientific_name")),
        _storage_value(host_record),
        *(_text(alias) for alias in host_record.get("aliases") or []),
    }
    return {value.casefold() for value in values if value}


def _supported_host_record(plant_host: Any) -> dict[str, Any] | None:
    requested = _text(plant_host).casefold()
    if not requested:
        return None
    for record in list_hosts():
        if requested not in _host_search_values(record):
            continue
        if SINGLE_GENE_COMPLETE_VECTOR not in record.get("workflow_levels", []):
            return None
        return record
    return None


def _source_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return _plain_value(dict(value or {}))


def _gene_information(source_metadata: Mapping[str, Any]) -> dict[str, Any]:
    nested = source_metadata.get("gene_information")
    sources = [source_metadata]
    if isinstance(nested, Mapping):
        sources.insert(0, nested)
    values: dict[str, Any] = {}
    for field in _GENE_INFORMATION_FIELDS:
        for source in sources:
            if field in source:
                values[field] = source[field]
                break
    values.setdefault("gene_name", "")
    return values


def _first_supplied_text(source_metadata: Mapping[str, Any], fields: Sequence[str]) -> str:
    nested = source_metadata.get("gene_information")
    sources = [nested, source_metadata] if isinstance(nested, Mapping) else [source_metadata]
    for source in sources:
        for field in fields:
            value = _text(source.get(field))
            if value:
                return value
    return ""


def _signature_from_normalized(
    *,
    goal_text: str,
    formal_host_value: str,
    normalized_cds: str,
    source_metadata: Mapping[str, Any],
) -> str:
    payload = {
        "signature_version": INPUT_SIGNATURE_VERSION,
        "goal_text": _text(goal_text),
        "formal_host_value": formal_host_value,
        "normalized_cds": normalized_cds,
        "supplied_source_metadata": _plain_value(source_metadata),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def plant_formal_route_prefill_input_signature(
    *,
    goal_text: str,
    plant_host: str,
    user_provided_cds: str,
    source_metadata: Mapping[str, Any] | None = None,
) -> str:
    """Return the deterministic signature for one valid formal-prefill input set."""
    if not isinstance(source_metadata, (Mapping, type(None))):
        raise PlantFormalRoutePrefillInputError(
            "source_metadata must be a mapping when supplied",
            reason_code="invalid_source_metadata",
        )
    host_record = _supported_host_record(plant_host)
    if host_record is None:
        raise PlantFormalRoutePrefillInputError(
            "plant_host is not supported by the single-gene formal workflow",
            reason_code="unsupported_formal_plant_host",
        )
    if not isinstance(user_provided_cds, str):
        raise PlantFormalRoutePrefillInputError(
            "user_provided_cds must be text",
            reason_code="invalid_cds",
        )
    analysis = analyze_formal_cds(
        user_provided_cds,
        source_kind="user_provided",
        gene_information=_gene_information(_source_metadata(source_metadata)),
    )
    if analysis.get("blocking") or not _text(analysis.get("normalized_cds")):
        raise PlantFormalRoutePrefillInputError(
            "user_provided_cds is invalid",
            reason_code="invalid_cds",
        )
    return _signature_from_normalized(
        goal_text=goal_text,
        formal_host_value=_storage_value(host_record),
        normalized_cds=_text(analysis.get("normalized_cds")),
        source_metadata=_source_metadata(source_metadata),
    )


def _fail_closed(reason: str) -> dict[str, Any]:
    return {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_status": FAIL_CLOSED_STATUS,
        "fail_closed": True,
        "fail_closed_reason": reason,
        "prefill": None,
        "advisory_only": True,
        "formal_authority": False,
        "persist": False,
    }


def _selected_candidate(
    intent_payload: Mapping[str, Any], selected_route_id: str
) -> dict[str, Any] | None:
    for candidate in intent_payload.get("route_candidates") or []:
        if isinstance(candidate, Mapping) and _text(candidate.get("route_id")) == selected_route_id:
            return deepcopy(dict(candidate))
    return None


def _gene_display_name(
    *,
    source_metadata: Mapping[str, Any],
    cds_analysis: Mapping[str, Any],
    route_draft: Mapping[str, Any],
) -> str:
    supplied = _first_supplied_text(source_metadata, _DISPLAY_NAME_FIELDS)
    if supplied:
        return supplied
    fasta_name = _text(cds_analysis.get("record_name"))
    if fasta_name:
        return fasta_name
    # A free-text goal is route evidence, not proof of the target identity.
    return DEFAULT_USER_PROVIDED_CDS_DISPLAY_NAME


def build_plant_formal_route_prefill_adapter(
    *,
    goal_text: str,
    plant_host: str,
    user_provided_cds: str,
    source_metadata: Mapping[str, Any] | None = None,
    user_selected_route_id: str | None,
    human_confirmed: bool,
    input_signature: str | None,
) -> dict[str, Any]:
    """Build a fail-closed, advisory-only formal prefill payload."""
    selected_route_id = _text(user_selected_route_id)
    if not selected_route_id:
        return _fail_closed("explicit_user_route_selection_required")
    if human_confirmed is not True:
        return _fail_closed("human_confirmation_required")

    crosswalk = ROUTE_CROSSWALK.get(selected_route_id)
    if crosswalk is None:
        return _fail_closed("unknown_route_crosswalk")
    if crosswalk.get("single_gene_supported") is not True:
        return _fail_closed("non_single_gene_route_not_supported_in_v1")
    if not _text(goal_text):
        return _fail_closed("goal_text_required")
    if not isinstance(source_metadata, (Mapping, type(None))):
        return _fail_closed("invalid_source_metadata")

    host_record = _supported_host_record(plant_host)
    if host_record is None:
        return _fail_closed("unsupported_formal_plant_host")
    if not isinstance(user_provided_cds, str):
        return _fail_closed("invalid_cds")

    supplied_source_metadata = _source_metadata(source_metadata)
    source_kind = _first_supplied_text(supplied_source_metadata, ("source_kind",)) or "user_provided"
    source_name = _first_supplied_text(
        supplied_source_metadata,
        ("source_name", "source_file_name", "filename"),
    )
    cds_analysis = analyze_formal_cds(
        user_provided_cds,
        source_kind=source_kind,
        source_name=source_name,
        gene_information=_gene_information(supplied_source_metadata),
    )
    normalized_cds = _text(cds_analysis.get("normalized_cds"))
    if cds_analysis.get("blocking") or not normalized_cds:
        return _fail_closed("invalid_cds")

    formal_host_value = _storage_value(host_record)
    computed_signature = _signature_from_normalized(
        goal_text=goal_text,
        formal_host_value=formal_host_value,
        normalized_cds=normalized_cds,
        source_metadata=supplied_source_metadata,
    )
    if not _text(input_signature):
        return _fail_closed("input_signature_required")
    if not hmac.compare_digest(_text(input_signature), computed_signature):
        return _fail_closed("input_signature_mismatch")

    intent_payload = build_simple_plant_wizard_intent_intake_presenter(
        user_goal_text=_text(goal_text),
        available_materials=["target_gene_or_cds", "host_plant"],
    )
    selected_candidate = _selected_candidate(intent_payload, selected_route_id)
    if selected_candidate is None:
        return _fail_closed("selected_route_not_in_current_candidates")
    confirmation = build_simple_plant_wizard_route_confirmation_presenter(
        intent_payload=dict(intent_payload),
        selected_route_id=selected_route_id,
    )
    confirmed_route = confirmation.get("recommended_route") or {}
    if (
        confirmation.get("decision_state") != "ready_for_user_confirmation"
        or _text(confirmed_route.get("route_id")) != selected_route_id
    ):
        return _fail_closed("route_confirmation_contract_not_satisfied")

    route_input = {
        "intent_text": _text(goal_text),
        "plant_host": _text(host_record.get("scientific_name")),
        "plant_context": _text(goal_text),
    }
    supplied_gene_name = _first_supplied_text(supplied_source_metadata, _DISPLAY_NAME_FIELDS)
    if supplied_gene_name:
        route_input["target_name"] = supplied_gene_name
    supplied_source_reference = _first_supplied_text(
        supplied_source_metadata,
        ("source_reference", "source_name", "source_file_name"),
    )
    if supplied_source_reference:
        route_input["known_cds_source"] = supplied_source_reference

    service_route_draft = build_plant_expression_route_draft(route_input)
    component_match_result = match_plant_component_candidates(
        service_route_draft,
        {},
        [],
        {"query": _text(goal_text)},
    )
    component_candidate_review = {
        "matcher_status": _text(component_match_result.get("matcher_status")),
        "active_component_candidate_selection": component_match_result.get(
            "active_component_candidate_selection"
        )
        is True,
        "candidate_component_matches_present": component_match_result.get(
            "candidate_component_matches_present"
        )
        is True,
        "candidate_component_count": int(
            (component_match_result.get("summary") or {}).get("candidate_component_count") or 0
        ),
        "manual_review_required": component_match_result.get("manual_review_required") is True,
    }
    display_name = _gene_display_name(
        source_metadata=supplied_source_metadata,
        cds_analysis=cds_analysis,
        route_draft=service_route_draft,
    )
    reasons = [
        _text(reason)
        for reason in selected_candidate.get("match_reasons_zh") or []
        if _text(reason)
    ]

    project_expression_target_draft = {
        "project_name_draft": _text(goal_text),
        "expression_goal": _text(goal_text),
        "plant_host": formal_host_value,
        "gene_cds_display_name": display_name,
        "project_type": crosswalk["formal_project_type"],
        "design_scenario": crosswalk["formal_design_scenario"],
    }
    prefill = {
        "project_expression_target_draft": project_expression_target_draft,
        "formal_host_value": formal_host_value,
        "formal_host_id": _text(host_record.get("host_id")),
        "gene_cds_display_name": display_name,
        "raw_cds": user_provided_cds,
        "normalized_cds": normalized_cds,
        "supplied_source_metadata": supplied_source_metadata,
        "selected_advisory_route_id": selected_route_id,
        "selected_advisory_route_reasons": reasons,
        "component_candidate_review": component_candidate_review,
    }

    return {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_status": READY_STATUS,
        "fail_closed": False,
        "input_signature": computed_signature,
        "prefill": prefill,
        **prefill,
        "advisory_only": True,
        "formal_authority": False,
        "persist": False,
    }


# Compact aliases keep the core callable discoverable for the later UI wiring batch.
build_plant_formal_route_prefill = build_plant_formal_route_prefill_adapter
build_plant_formal_route_prefill_input_signature = plant_formal_route_prefill_input_signature
