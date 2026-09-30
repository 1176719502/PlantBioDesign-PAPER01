"""Authoritative workflow and operation gate for plant vector assets."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from core.pbi121_replacement_contract import (
    Pbi121ReplacementContractError,
    validate_pbi121_backbone_record_for_replacement,
)
from core.vector_asset_contracts_v1 import classify_vector_asset


WORKFLOW_ALIASES = {
    "rice_alb_single_gene": "single_gene_rice_alb",
    "single_gene_rice_alb": "single_gene_rice_alb",
    "formal_single_gene": "single_gene",
    "single_gene": "single_gene",
    "generic_multi_tu": "generic_multi_tu",
    "gate3_pathway": "gate3_pathway",
    "gate3": "betalain_gate3",
    "gate3_betalain_three_tu": "betalain_gate3",
    "betalain_gate3": "betalain_gate3",
}
ASSET_KIND_LABELS = {
    "exact_insertion_source": "单基因精确插入载体来源",
    "tDNA_replacement_source": "Gate 3 精确替换载体来源",
    "reference_vector": "完整参考载体，不可直接设计",
    "hold_unverified_asset": "待验证本地示例，来源未验证",
    "unverified_uploaded_vector": "未验证上传载体，只读",
}


class VectorAssetAdmissionError(ValueError):
    """Raised when a formal workflow requests an unapproved vector operation."""


def normalize_workflow_id(value: Any) -> str:
    workflow = str(value or "").strip()
    return WORKFLOW_ALIASES.get(workflow, workflow)


def annotate_vector_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Attach a derived snapshot for display; authorization always recalculates it."""
    annotated = copy.deepcopy(dict(record))
    identity = classify_vector_asset(annotated)
    annotated["vector_asset_identity"] = identity
    annotated["asset_id"] = identity.get("asset_id")
    annotated["asset_kind"] = identity.get("asset_kind")
    annotated["operation_kind"] = identity.get("operation_kind")
    annotated["vector_asset_display_label"] = ASSET_KIND_LABELS.get(
        str(identity.get("asset_kind") or ""), "未验证上传载体，只读"
    )
    return annotated


def _blocked(identity: Mapping[str, Any], workflow_id: str, reason: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "status": "vector_asset_contract_blocked",
        "workflow_id": workflow_id,
        "identity": copy.deepcopy(dict(identity)),
        "contract": copy.deepcopy(dict(identity.get("contract") or {})),
        "canonical_settings": {},
        "reason": reason,
    }


def assess_vector_workflow(record: Mapping[str, Any], *, workflow_id: str) -> dict[str, Any]:
    identity = classify_vector_asset(record)
    workflow = normalize_workflow_id(workflow_id)
    if identity.get("identity_status") != "EXACT_KNOWN_ASSET":
        return _blocked(
            identity,
            workflow,
            str(identity.get("reason") or "The uploaded vector has no reviewed operation contract."),
        )
    contract = dict(identity.get("contract") or {})
    if bool(identity.get("rotation_equivalent")):
        return _blocked(
            identity,
            workflow,
            "The circular sequence is rotation-equivalent to a known asset, but its coordinate origin differs from the reviewed operation contract. It remains read-only until origin normalization is implemented.",
        )
    if not bool(contract.get("direct_design_allowed")) or not bool(contract.get("canonical_modification_allowed")):
        return _blocked(identity, workflow, str(contract.get("warning_text") or "Direct design is not allowed."))
    if workflow not in set(contract.get("supported_workflows") or []):
        return _blocked(
            identity,
            workflow,
            f"{contract.get('display_name')} is not admitted to the {workflow or 'unspecified'} workflow.",
        )
    if (
        str(contract.get("asset_id") or "") == "pbi121_af485783_1"
        and (workflow == "gate3_pathway" or bool(record.get("original_text")))
    ):
        try:
            validate_pbi121_backbone_record_for_replacement(dict(record))
        except Pbi121ReplacementContractError as exc:
            return _blocked(identity, workflow, str(exc))
    operation_kind = str(contract.get("operation_kind") or "none")
    if operation_kind == "exact_insertion":
        cut_index = int((contract.get("internal_coordinate_contract") or {}).get("cut_index"))
        canonical_settings = {
            "mode": "insertion",
            "start_coordinate": cut_index,
            "end_coordinate": cut_index + 1,
            "expected_removed_sequence": "",
            "insertion_orientation": "forward",
        }
    elif operation_kind == "exact_replacement":
        external_region = dict(contract.get("external_coordinate_contract") or {})
        canonical_settings = {
            "mode": "replacement",
            "start_coordinate": int(external_region["start"]),
            "end_coordinate": int(external_region["end"]),
            "insertion_orientation": "forward",
        }
    else:
        return _blocked(identity, workflow, "The vector asset contract does not define a design operation.")
    return {
        "allowed": True,
        "status": "vector_asset_contract_admitted",
        "workflow_id": workflow,
        "identity": copy.deepcopy(identity),
        "contract": contract,
        "canonical_settings": canonical_settings,
        "reason": "The reviewed vector asset contract admits this workflow.",
    }


def validate_vector_operation(
    record: Mapping[str, Any],
    *,
    workflow_id: str,
    insertion_settings: Mapping[str, Any],
) -> dict[str, Any]:
    assessment = assess_vector_workflow(record, workflow_id=workflow_id)
    if not assessment["allowed"]:
        return assessment
    expected = dict(assessment["canonical_settings"])
    requested = {
        "mode": str(insertion_settings.get("mode") or ""),
        "start_coordinate": int(insertion_settings.get("start_coordinate") or 0),
        "end_coordinate": int(insertion_settings.get("end_coordinate") or 0),
        "insertion_orientation": str(insertion_settings.get("insertion_orientation") or "forward"),
    }
    comparable_expected = {key: expected[key] for key in requested}
    if requested != comparable_expected:
        return _blocked(
            assessment["identity"],
            assessment["workflow_id"],
            "User, session-state, and project-JSON coordinates cannot override the reviewed vector asset contract.",
        )
    assessment["status"] = "vector_asset_exact_operation_admitted"
    assessment["reason"] = "The requested operation exactly matches the reviewed vector asset contract."
    return assessment


def require_vector_operation(
    record: Mapping[str, Any],
    *,
    workflow_id: str,
    insertion_settings: Mapping[str, Any],
) -> dict[str, Any]:
    assessment = validate_vector_operation(
        record,
        workflow_id=workflow_id,
        insertion_settings=insertion_settings,
    )
    if not assessment["allowed"]:
        raise VectorAssetAdmissionError(str(assessment["reason"]))
    return assessment


def assess_legacy_project_vector(
    record: Mapping[str, Any],
    *,
    workflow_id: str,
    insertion_settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep saved bytes readable while preventing unsafe completion or regeneration."""
    assessment = validate_vector_operation(
        record,
        workflow_id=workflow_id,
        insertion_settings=insertion_settings,
    )
    return {
        **assessment,
        "legacy_project_read_only": not bool(assessment["allowed"]),
        "completed_design_allowed": bool(assessment["allowed"]),
        "modified_vector_export_allowed": bool(assessment["allowed"]),
    }
