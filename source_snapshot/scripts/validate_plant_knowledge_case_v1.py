"""Validate the read-only Plant Knowledge Layer v1 reporter case manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "plant_knowledge_cases_v1" / "reporter_expression_construct_case.json"
REGISTRY_PATH = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
KNOWLEDGE_PATH = ROOT / "data" / "plant_knowledge_layer_v1" / "evidence_curation_v1.json"
EXPECTED_COMPONENTS = {
    "promoter": "PCLV1-PRO-35S-835",
    "reporter_cds": "PCLV1-CDS-GUSA",
    "vector_source": "PCLV1-VEC-PBIN19",
}
FORBIDDEN_POSITIVE_TERMS = (
    "improved expression",
    "biological performance",
    "expression success",
    "experimental validation",
    "wet-lab readiness",
    "automatic recommendation",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_keys(value: Any, key: str) -> list[Any]:
    if isinstance(value, dict):
        return [child for name, child in value.items() if name == key] + [
            nested for child in value.values() for nested in _walk_keys(child, key)
        ]
    if isinstance(value, list):
        return [nested for child in value for nested in _walk_keys(child, key)]
    return []


def _claim_scan_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(
            _claim_scan_text(child)
            for key, child in value.items()
            if key != "blocked_claims"
        )
    if isinstance(value, list):
        return " ".join(_claim_scan_text(child) for child in value)
    return str(value or "")


def validate() -> list[str]:
    errors: list[str] = []
    try:
        case = _load(CASE_PATH)
        registry = _load(REGISTRY_PATH)
        knowledge = _load(KNOWLEDGE_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"input read failed: {exc}"]

    if case.get("schema_version") != "plant-knowledge-case-walkthrough-v1":
        errors.append("case schema_version is invalid")
    if case.get("scope") != "documentation_only_read_only_case":
        errors.append("case scope must remain documentation-only/read-only")
    if case.get("registry_source") != "data/plant_component_registry_v1/registry.batch1.json":
        errors.append("case Registry source is not authoritative")
    if case.get("knowledge_layer_source") != "data/plant_knowledge_layer_v1/evidence_curation_v1.json":
        errors.append("case Knowledge Layer source is not authoritative")
    if _walk_keys(case, "sequence"):
        errors.append("case manifest must not contain sequence data")

    registry_by_id = {row.get("component_id"): row for row in registry.get("records", [])}
    knowledge_by_component = {row.get("component_id"): row for row in knowledge.get("records", [])}
    components = case.get("selected_components")
    if not isinstance(components, list) or len(components) != len(EXPECTED_COMPONENTS):
        errors.append("case must contain exactly three selected component links")
        return errors

    seen_slots: set[str] = set()
    for index, link in enumerate(components):
        prefix = f"selected_components[{index}]"
        if not isinstance(link, dict):
            errors.append(f"{prefix} must be an object")
            continue
        slot = str(link.get("slot") or "").strip()
        component_id = str(link.get("registry_component_id") or "").strip()
        evidence_id = str(link.get("knowledge_layer_evidence_object_id") or "").strip()
        seen_slots.add(slot)
        if EXPECTED_COMPONENTS.get(slot) != component_id:
            errors.append(f"{prefix} has an unexpected slot/component mapping")
        registry_record = registry_by_id.get(component_id)
        evidence_record = knowledge_by_component.get(component_id)
        if registry_record is None:
            errors.append(f"{prefix} Registry component is missing: {component_id}")
            continue
        if evidence_record is None:
            errors.append(f"{prefix} Knowledge Layer record is missing: {component_id}")
            continue
        if evidence_record.get("evidence_object_id") != evidence_id:
            errors.append(f"{prefix} evidence object does not match component")
        reference = evidence_record.get("registry_reference") or {}
        for field in ("component_id", "accession_version", "sequence_length", "sequence_sha256", "source_record", "source_record_sha256"):
            expected = component_id if field == "component_id" else registry_record.get(field)
            if reference.get(field) != expected:
                errors.append(f"{prefix} Knowledge Layer {field} does not match Registry")
        source_path = ROOT / str(registry_record.get("source_record") or "")
        if not source_path.is_file():
            errors.append(f"{prefix} source record is missing")
        elif _sha256_file(source_path) != registry_record.get("source_record_sha256"):
            errors.append(f"{prefix} source record hash does not match Registry")
        claim_ids = {claim.get("claim_id") for claim in evidence_record.get("evidence_claims", [])}
        linked_claim_ids = set(link.get("evidence_claim_ids") or [])
        if linked_claim_ids != claim_ids:
            errors.append(f"{prefix} claim linkage does not match the evidence object")
        claim_types = {claim.get("claim_type") for claim in evidence_record.get("evidence_claims", [])}
        if not {"IDENTITY", "BOUNDARY", "FUNCTION"}.issubset(claim_types):
            errors.append(f"{prefix} evidence claims lack identity/boundary/function coverage")
        if not evidence_record.get("engineering_context_notes"):
            errors.append(f"{prefix} lacks engineering context")
        if link.get("engineering_context_reference") != "knowledge_layer.engineering_context_notes":
            errors.append(f"{prefix} engineering context reference is invalid")
        if not str(link.get("selection_rationale") or "").strip():
            errors.append(f"{prefix} selection rationale is missing")
        review = evidence_record.get("review") or {}
        if review.get("record_status") != "DRAFT" or review.get("human_review_status") != "PENDING_HUMAN_REVIEW":
            errors.append(f"{prefix} review state must remain draft/pending human review")

    if seen_slots != set(EXPECTED_COMPONENTS):
        errors.append("case slots are incomplete or duplicated")
    text = _claim_scan_text(case).casefold()
    for term in FORBIDDEN_POSITIVE_TERMS:
        if term.casefold() in text:
            errors.append(f"case manifest contains blocked claim text: {term}")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("Plant Knowledge Layer v1 case validation failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        raise SystemExit(1)
    print("Plant Knowledge Layer v1 reporter case validation passed: 3 Registry-to-Knowledge links.")
