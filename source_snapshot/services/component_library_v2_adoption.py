"""Controlled Component Library V2 adoption projection.

This module is intentionally additive: the frozen V1 Registry and its 156
legacy identities remain the source of historical provenance.  V2 rows are a
deterministic projection of the reviewed R2 JSON package and never mutate the
V1 files or introduce a new admission mode.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


V2_DATA_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "component_library_v2_qualified_core_r2"
)
CORE_PATH = V2_DATA_DIR / "V2_QUALIFIED_CORE_R2_CANONICAL_SET.json"
DIRECT_PATH = V2_DATA_DIR / "V2_QUALIFIED_DIRECT_USE_R2.json"
ASSISTED_PATH = V2_DATA_DIR / "V2_QUALIFIED_USER_ASSISTED_R2.json"
MIGRATION_PATH = V2_DATA_DIR / "V2_LEGACY_MIGRATION_R2.json"
BLOCKED_PATH = V2_DATA_DIR / "V2_BLOCKED_RECORDS_R2.json"

V2_BLOCKED_IDS = frozenset({"V2-CMP-003", "V2-CMP-126"})
V2_CORE_COUNT = 41
V2_DIRECT_USE_COUNT = 17
V2_ASSISTED_COUNT = 24
V2_REFERENCE_COUNT = 95
V2_RETIRED_COUNT = 35
V2_CANONICAL_TOTAL = 171
V2_LEGACY_MAPPING_COUNT = 156
V2_REGISTRY_VERSION = "component-library-v2-controlled-adoption-r1"
V2_CORE_SOURCE_TYPE = "V2_CORE"
V2_DIRECT_SELECTION_CONTRACT = "component-library-v2-direct-use-selection-r1"
V2_ASSISTED_RESOLUTION_SCHEMA = "component-library-v2-project-resolution-r1"


class V2AdoptionError(ValueError):
    """Raised when the frozen V2 adoption package is inconsistent."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V2AdoptionError(f"Cannot read V2 adoption data: {path.name}") from exc
    if not isinstance(value, dict):
        raise V2AdoptionError(f"V2 adoption document must be an object: {path.name}")
    return value


def _records(path: Path) -> list[dict[str, Any]]:
    rows = _load(path).get("records")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise V2AdoptionError(f"V2 adoption records are incomplete: {path.name}")
    return [dict(row) for row in rows]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.upper().encode("ascii")).hexdigest()


def load_v2_package() -> dict[str, list[dict[str, Any]]]:
    """Load and validate the immutable R2 package, without exposing mutation."""
    core = _records(CORE_PATH)
    direct = _records(DIRECT_PATH)
    assisted = _records(ASSISTED_PATH)
    migration = _records(MIGRATION_PATH)
    blocked = _load(BLOCKED_PATH)
    blocked_ids = {
        _text(row.get("canonical_v2_component_id"))
        for row in blocked.get("records", [])
        if isinstance(row, Mapping)
    }
    blocked_ids.update(V2_BLOCKED_IDS)
    if len(core) != V2_CORE_COUNT or len(direct) != V2_DIRECT_USE_COUNT or len(assisted) != V2_ASSISTED_COUNT:
        raise V2AdoptionError("V2 Core/direct/assisted cardinality is invalid.")
    if len(migration) != V2_LEGACY_MAPPING_COUNT:
        raise V2AdoptionError("V2 legacy mapping cardinality is invalid.")
    core_ids = {_text(row.get("canonical_v2_component_id")) for row in core}
    direct_ids = {_text(row.get("canonical_v2_component_id")) for row in direct}
    assisted_ids = {_text(row.get("canonical_v2_component_id")) for row in assisted}
    if len(core_ids) != V2_CORE_COUNT or direct_ids | assisted_ids != core_ids or direct_ids & assisted_ids:
        raise V2AdoptionError("V2 Core ID sets do not reconcile.")
    if core_ids & blocked_ids or direct_ids & blocked_ids or assisted_ids & blocked_ids:
        raise V2AdoptionError("Blocked V2 IDs cannot enter the adoptable Core.")
    for row in direct:
        sequence = _text(row.get("sequence"))
        digest = _text(row.get("sequence_sha256"))
        source_digest = _text(row.get("source_artifact_sha256"))
        required = (
            "canonical_v2_component_id", "source_artifact", "exact_boundary",
            "orientation", "attribution_requirement", "license_rights_source",
            "rights_state", "independent_review_status",
        )
        if (
            not sequence
            or set(sequence) - set("ACGT")
            or int(row.get("length") or 0) != len(sequence)
            or len(digest) != 64
            or set(digest.casefold()) - set("0123456789abcdef")
            or _sha256(sequence) != digest
            or len(source_digest) != 64
            or set(source_digest.casefold()) - set("0123456789abcdef")
            or any(not _text(row.get(field)) for field in required)
            or row.get("asset_integrity_reference_complete") is not True
        ):
            raise V2AdoptionError(
                f"V2 DIRECT_USE asset is incomplete: {_text(row.get('canonical_v2_component_id'))}."
            )
    for row in assisted:
        compatibility = row.get("product_closure_resolution_compatibility")
        if (
            row.get("bundled_authoritative_sequence") is not False
            or not _text(row.get("expected_user_supplied_input"))
            or not isinstance(row.get("required_validation_contract"), list)
            or not isinstance(compatibility, Mapping)
            or compatibility.get("compatible") is not True
            or _text(compatibility.get("mechanism")) != "USER_SEQUENCE_ASSISTED"
        ):
            raise V2AdoptionError(
                f"V2 USER_SEQUENCE_ASSISTED record is incomplete: {_text(row.get('canonical_v2_component_id'))}."
            )
    legacy_ids = [_text(row.get("legacy_component_id")) for row in migration]
    canonical_tiers: dict[str, set[str]] = {}
    for row in migration:
        canonical_tiers.setdefault(_text(row.get("canonical_v2_component_id")), set()).add(
            _text(row.get("library_tier"))
        )
    if (
        len(set(legacy_ids)) != V2_LEGACY_MAPPING_COUNT
        or any(not value for value in legacy_ids)
        or any(row.get("migration_mapping_valid") is not True for row in migration)
    ):
        raise V2AdoptionError("V2 legacy mappings are incomplete or ambiguous.")
    if "" in canonical_tiers or any(len(tiers) != 1 for tiers in canonical_tiers.values()):
        raise V2AdoptionError("V2 canonical migration targets are incomplete or ambiguous.")
    tier_counts = {
        tier: sum(tiers == {tier} for tiers in canonical_tiers.values())
        for tier in ("CORE", "REFERENCE", "RETIRED")
    }
    if tier_counts != {"CORE": 21, "REFERENCE": V2_REFERENCE_COUNT, "RETIRED": V2_RETIRED_COUNT}:
        raise V2AdoptionError("V2 migration tiers are incomplete.")
    return {"core": core, "direct": direct, "assisted": assisted, "migration": migration}


def _component_type(role: str) -> str:
    return {
        "promoter": "promoter",
        "enhancer_regulatory_element": "promoter",
        "terminator_3prime_regulatory_region": "three_prime_regulatory_region",
        "5_utr_regulatory": "five_prime_utr",
        "reporter": "cds",
        "selectable_marker": "cds",
        "cds_enzyme_functional": "cds",
    }.get(role, "")


def _core_overlay(core: Mapping[str, Any], asset: Mapping[str, Any] | None, mode: str) -> dict[str, Any]:
    role = _text(core.get("role"))
    asset_reference = core.get("sequence_asset_reference")
    asset_reference = dict(asset_reference) if isinstance(asset_reference, Mapping) else {}
    sequence = _text((asset or {}).get("sequence")) if mode == "DIRECT_USE" else ""
    length = int((asset or {}).get("length") or asset_reference.get("length") or 0)
    digest = _text((asset or {}).get("sequence_sha256")) or _text(asset_reference.get("sequence_sha256"))
    return {
        "id": _text(core.get("canonical_v2_component_id")),
        "catalog_record_id": _text(core.get("canonical_v2_component_id")),
        "canonical_v2_component_id": _text(core.get("canonical_v2_component_id")),
        "record_authority": "v2_canonical_core",
        "name": _text(core.get("canonical_name")),
        "display_name": _text(core.get("canonical_name")),
        "aliases": list(core.get("aliases") or []),
        "role": role,
        "component_role": role,
        "component_type": _component_type(role),
        "type": _component_type(role),
        "sequence": sequence,
        "length": length,
        "sequence_sha256": digest,
        "accession": _text(core.get("accession_or_source_record")),
        "source": _text(core.get("source_record")),
        "source_record": _text(core.get("source_record")),
        "source_organism": _text(core.get("source_organism")),
        "organism_source_context": _text(core.get("source_organism")),
        "host_context": "",
        "target_host_species": [],
        "host_applicability": copy.deepcopy(core.get("host_applicability") or {}),
        "evidence_tier": _text(core.get("evidence_maturity")),
        "primary_reference": _text(core.get("primary_citation") or core.get("citation")),
        "doi": _text(core.get("doi")),
        "pmid": _text(core.get("pmid")),
        "source_coordinates": _text((asset or {}).get("exact_boundary")),
        "source_url_reference": _text((asset or {}).get("source_artifact")),
        "provenance_origin": _text(core.get("evidence_origin")),
        "redistribution_status": _text((asset or {}).get("license_rights_source")),
        "library_tier": "CORE",
        "participation_mode": mode,
        "admission_mode": mode,
        "formal_selectable": mode == "DIRECT_USE",
        "catalog_governance_state": ("bundled", "local_verified", "eligible") if mode == "DIRECT_USE" else ("reference_only", "unavailable", "requires_sequence"),
        "distribution_mode": "bundled" if mode == "DIRECT_USE" else "reference_only",
        "sequence_availability": "local_verified" if mode == "DIRECT_USE" else "unavailable",
        "workflow_admission_status": "eligible" if mode == "DIRECT_USE" else "requires_sequence",
        "workflow_compatibility": ["generic_multi_tu"],
        "canonical_record": True,
        "legacy_component_ids": list(core.get("legacy_component_ids") or core.get("legacy_ids") or []),
        "evidence_paths": list(core.get("evidence_paths") or []),
        "expected_user_supplied_input": (asset or {}).get("expected_user_supplied_input"),
        "required_validation_contract": list((asset or {}).get("required_validation_contract") or []),
        "recorded_boundary_context": copy.deepcopy(
            (asset or {}).get("recorded_boundary_context")
        ),
        "product_closure_resolution_compatibility": copy.deepcopy(
            (asset or {}).get("product_closure_resolution_compatibility") or {}
        ),
        "v2_evidence_caveat": _text(core.get("evidence_caveat")),
        "v2_source_citation": copy.deepcopy(core.get("source_citation") or {}),
        "v2_asset": copy.deepcopy(asset or {}),
        "v2_assisted_contract": (
            copy.deepcopy(asset or {}) if mode == "USER_SEQUENCE_ASSISTED" else {}
        ),
    }


def build_v2_canonical_inventory(*, include_legacy_ids: bool = True) -> list[dict[str, Any]]:
    """Return exactly 171 deterministic canonical rows for the adopted UI."""
    package = load_v2_package()
    core_by_id = {_text(row.get("canonical_v2_component_id")): row for row in package["core"]}
    direct_by_id = {_text(row.get("canonical_v2_component_id")): row for row in package["direct"]}
    assisted_by_id = {
        _text(row.get("canonical_v2_component_id")): row
        for row in package["assisted"]
    }
    from services.plant_component_workflow_registry import catalog_library_view_records

    legacy_rows = {_text(row.get("catalog_record_id")): dict(row) for row in catalog_library_view_records()}
    migration_by_id: dict[str, list[dict[str, Any]]] = {}
    for mapping in package["migration"]:
        migration_by_id.setdefault(_text(mapping.get("canonical_v2_component_id")), []).append(mapping)
    rows: list[dict[str, Any]] = []
    for canonical_id, mappings in migration_by_id.items():
        mapped_legacy_rows = [
            legacy_rows.get(_text(mapping.get("legacy_component_id")), {})
            for mapping in mappings
        ]
        current_formal = next(
            (
                legacy
                for legacy in mapped_legacy_rows
                if bool(legacy.get("formal_selectable"))
                and _text(legacy.get("registry_component_id"))
            ),
            {},
        )
        if canonical_id in core_by_id:
            mode = "DIRECT_USE" if canonical_id in direct_by_id else "USER_SEQUENCE_ASSISTED"
            row = _core_overlay(
                core_by_id[canonical_id],
                direct_by_id.get(canonical_id) or assisted_by_id.get(canonical_id),
                mode,
            )
            row.update(
                {
                    "current_product_identity": _text(
                        current_formal.get("registry_component_id")
                    ),
                    "current_product_state": (
                        "FORMAL_REGISTRY_ADMITTED"
                        if current_formal
                        else "V2_QUALIFIED_NOT_FORMALLY_ADMITTED"
                        if mode == "DIRECT_USE"
                        else "PROJECT_SCOPED_USER_SEQUENCE_REQUIRED"
                    ),
                    "current_selector_visibility": bool(current_formal),
                    "current_agent_visibility": True,
                    "required_target_state": (
                        "PRESERVE_CURRENT_REGISTRY_ADMISSION"
                        if current_formal
                        else "REQUIRE_CURRENT_HOST_AND_ROLE_ADMISSION"
                        if mode == "DIRECT_USE"
                        else "PROJECT_SCOPED_USER_SEQUENCE_ASSISTED"
                    ),
                }
            )
            if mode == "DIRECT_USE":
                row["v2_direct_use_qualified"] = True
                row["formal_selectable"] = bool(current_formal)
                row["registry_component_id"] = _text(
                    current_formal.get("registry_component_id")
                )
                row["registry_version"] = _text(current_formal.get("registry_version"))
                if current_formal:
                    if _text(current_formal.get("sequence")) != _text(row.get("sequence")):
                        raise V2AdoptionError(
                            f"V2/current Registry sequence conflict: {canonical_id}."
                        )
                    row["catalog_governance_state"] = current_formal.get(
                        "catalog_governance_state"
                    )
                    row["distribution_mode"] = _text(
                        current_formal.get("distribution_mode")
                    )
                    row["sequence_availability"] = _text(
                        current_formal.get("sequence_availability")
                    )
                    row["workflow_admission_status"] = _text(
                        current_formal.get("workflow_admission_status")
                    )
                    row["target_host_species"] = list(
                        current_formal.get("target_host_species") or []
                    )
                    row["host_context"] = _text(current_formal.get("host_context"))
                    row["host_applicability_scope"] = list(
                        current_formal.get("host_applicability_scope") or []
                    )
                    row["adoption_blockers"] = []
                else:
                    row["catalog_governance_state"] = (
                        "bundled",
                        "local_verified",
                        "blocked",
                    )
                    row["workflow_admission_status"] = "blocked"
                    row["adoption_blockers"] = [
                        "current_registry_identity_not_admitted",
                        "current_host_applicability_not_proven",
                        "formal_role_or_workflow_admission_not_proven",
                    ]
            else:
                row["formal_selectable"] = False
                row["adoption_blockers"] = [
                    "authoritative_sequence_not_bundled",
                    "project_scoped_user_sequence_and_confirmation_required",
                ]
        else:
            first = mappings[0]
            legacy = legacy_rows.get(_text(first.get("legacy_component_id")), {})
            tier = _text(first.get("library_tier"))
            row = dict(legacy)
            row.update({
                "id": canonical_id,
                "catalog_record_id": canonical_id,
                "canonical_v2_component_id": canonical_id,
                "record_authority": "v2_retired" if tier == "RETIRED" else "v2_reference",
                "library_tier": tier,
                "participation_mode": "REFERENCE_ONLY",
                "admission_mode": "REFERENCE_ONLY",
                "formal_selectable": False,
                "canonical_record": True,
                "legacy_component_ids": [_text(item.get("legacy_component_id")) for item in mappings],
                "migration_status": "migration-resolvable",
                "retirement_reason": _text(first.get("retirement_reason")),
                "catalog_governance_state": ("deferred", "unavailable", "blocked") if tier == "RETIRED" else ("reference_only", "unavailable", "requires_sequence"),
                "current_product_identity": _text(first.get("legacy_component_id")),
                "current_product_state": "RETIRED_EXCLUDED" if tier == "RETIRED" else "REFERENCE_ONLY",
                "current_selector_visibility": False,
                "current_agent_visibility": tier == "REFERENCE",
                "required_target_state": "REMAIN_EXCLUDED" if tier == "RETIRED" else "REFERENCE_AGENT_ONLY",
                "adoption_blockers": [
                    "retired_from_new_designs" if tier == "RETIRED" else "reference_only_no_formal_sequence_authority"
                ],
            })
            if tier == "RETIRED":
                row["sequence"] = ""
                row["length"] = int(legacy.get("length") or 0)
        if include_legacy_ids:
            row["legacy_component_ids"] = sorted(set(row.get("legacy_component_ids") or []) | {_text(item.get("legacy_component_id")) for item in mappings})
        rows.append(row)
    for canonical_id, core in core_by_id.items():
        if canonical_id in migration_by_id:
            continue
        mode = "DIRECT_USE" if canonical_id in direct_by_id else "USER_SEQUENCE_ASSISTED"
        row = _core_overlay(
                core,
                direct_by_id.get(canonical_id) or assisted_by_id.get(canonical_id),
                mode,
            )
        row.update(
            {
                "formal_selectable": False,
                "current_product_identity": "",
                "current_product_state": (
                    "V2_QUALIFIED_NOT_FORMALLY_ADMITTED"
                    if mode == "DIRECT_USE"
                    else "PROJECT_SCOPED_USER_SEQUENCE_REQUIRED"
                ),
                "current_selector_visibility": False,
                "current_agent_visibility": True,
                "required_target_state": (
                    "REQUIRE_CURRENT_HOST_AND_ROLE_ADMISSION"
                    if mode == "DIRECT_USE"
                    else "PROJECT_SCOPED_USER_SEQUENCE_ASSISTED"
                ),
                "adoption_blockers": (
                    [
                        "current_registry_identity_not_admitted",
                        "current_host_applicability_not_proven",
                        "formal_role_or_workflow_admission_not_proven",
                    ]
                    if mode == "DIRECT_USE"
                    else [
                        "authoritative_sequence_not_bundled",
                        "project_scoped_user_sequence_and_confirmation_required",
                    ]
                ),
            }
        )
        if mode == "DIRECT_USE":
            row["v2_direct_use_qualified"] = True
            row["catalog_governance_state"] = (
                "bundled",
                "local_verified",
                "blocked",
            )
            row["workflow_admission_status"] = "blocked"
        rows.append(row)
    if len(rows) != V2_CANONICAL_TOTAL:
        raise V2AdoptionError(f"Expected {V2_CANONICAL_TOTAL} canonical rows, got {len(rows)}.")
    counts = {"CORE": 0, "REFERENCE": 0, "RETIRED": 0}
    for row in rows:
        tier = _text(row.get("library_tier"))
        if tier == "CORE":
            counts[tier] += 1
        elif tier in counts:
            counts[tier] += 1
    if counts != {"CORE": 41, "REFERENCE": 95, "RETIRED": 35}:
        raise V2AdoptionError(f"V2 canonical tier counts are invalid: {counts}")
    blocked_rows = [row for row in rows if _text(row.get("canonical_v2_component_id")) in V2_BLOCKED_IDS]
    if len(blocked_rows) != 2 or any(
        _text(row.get("library_tier")) != "REFERENCE"
        or _text(row.get("admission_mode")) != "REFERENCE_ONLY"
        or bool(row.get("formal_selectable"))
        for row in blocked_rows
    ):
        raise V2AdoptionError("Blocked IDs must remain non-adoptable Reference records.")
    formally_admitted = [row for row in rows if bool(row.get("formal_selectable"))]
    if {
        _text(row.get("canonical_v2_component_id")) for row in formally_admitted
    } - {"V2-CMP-138", "V2-CMP-144"}:
        raise V2AdoptionError(
            "Unexpected V2 identity entered current Formal admission."
        )
    return copy.deepcopy(sorted(rows, key=lambda row: _text(row.get("canonical_v2_component_id"))))


def v2_adoption_summary(rows: list[Mapping[str, Any]] | None = None) -> dict[str, int]:
    rows = build_v2_canonical_inventory() if rows is None else rows
    return {
        "canonical_total": len(rows),
        "core": sum(_text(r.get("library_tier")) == "CORE" for r in rows),
        "direct_use": sum(_text(r.get("admission_mode")) == "DIRECT_USE" for r in rows),
        "user_sequence_assisted": sum(_text(r.get("admission_mode")) == "USER_SEQUENCE_ASSISTED" for r in rows),
        "reference": sum(_text(r.get("library_tier")) == "REFERENCE" for r in rows),
        "retired": sum(_text(r.get("library_tier")) == "RETIRED" for r in rows),
        "legacy_mappings": V2_LEGACY_MAPPING_COUNT,
    }


def validate_v2_user_sequence(row: Mapping[str, Any], sequence: str) -> dict[str, Any]:
    """Validate an assisted sequence against the frozen V2 identity contract."""
    from services.mvp_sequence_input import analyze_dna_component_input

    try:
        analyzed = analyze_dna_component_input(
            sequence,
            project_id="v2-assisted-sequence-validation",
            component_type=_text(row.get("component_type")) or "component",
            display_name=_text(row.get("name")) or "V2 assisted component",
            source_kind="paste",
            source_name="user-provided sequence",
        )
        normalized = _text(analyzed.get("normalized_sequence"))
    except ValueError:
        normalized = ""
    checks = {
        "sequence_supplied": bool(normalized),
        "strict_dna_alphabet": bool(normalized) and not (set(normalized) - set("ACGT")),
    }
    return {"component_id": _text(row.get("canonical_v2_component_id")), "participation_mode": "USER_SEQUENCE_ASSISTED", "checks": checks, "sequence_validation_passed": all(checks.values()), "accepted": False}


def v2_assisted_admission_decision(component_id: str) -> dict[str, Any]:
    """Project one V2 assisted identity into the shared admission contract."""
    current = v2_canonical_record(component_id)
    if _text(current.get("admission_mode")) != "USER_SEQUENCE_ASSISTED":
        raise V2AdoptionError("Only V2 USER_SEQUENCE_ASSISTED records use project resolution.")
    contract = copy.deepcopy(current.get("v2_assisted_contract") or {})
    boundary = copy.deepcopy(contract.get("recorded_boundary_context"))
    source_provenance = {
        "display_accession": _text(current.get("accession")),
        "accession": _text(current.get("accession")),
        "source_database": _text(current.get("source")),
        "source_record": _text(current.get("source_record")),
        "source_coordinates": boundary,
        "source_url_reference": _text(current.get("source_url_reference")),
        "evidence_publication_reference": _text(current.get("primary_reference")),
        "reviewed_source_commit": "2a63df090c3b57a801a11de228e9d816ade17dad",
        "legacy_component_ids": list(current.get("legacy_component_ids") or []),
    }
    return {
        "component_id": _text(current.get("canonical_v2_component_id")),
        "display_name": _text(current.get("name")),
        "component_type": _text(current.get("component_type")),
        "component_role": _text(current.get("role")),
        "participation_mode": "USER_SEQUENCE_ASSISTED",
        "sequence_length": None,
        "sequence_sha256": "",
        "sequence_identity_mode": "FREEZE_USER_SEQUENCE",
        "source_provenance": source_provenance,
        "boundary_definition": boundary,
        "orientation_semantics": copy.deepcopy(boundary),
        "rights_classification": "USER_SEQUENCE_REQUIRED",
        "current_formal_selectable": False,
        "current_admission_fields": {
            "library_tier": "CORE",
            "admission_mode": "USER_SEQUENCE_ASSISTED",
            "formal_selectable": False,
        },
        "known_validation_state": {
            "independent_review_status": _text(
                contract.get("independent_review_status")
            )
        },
        "host_applicability": {
            "organism_source_context": _text(current.get("source_organism")),
            "claim_boundary": "source context only; plant-use applicability is not inferred",
        },
        "rights_redistribution_evidence": _text(
            contract.get("rights_redistribution_evidence")
        ),
        "duplicate_or_alias_relationships": {},
        "reason_codes": list(current.get("required_validation_contract") or []),
        "aliases": list(current.get("aliases") or []),
        "component_identity_source": V2_CORE_SOURCE_TYPE,
        "user_sequence_source_required": True,
        "required_validation_contract": list(
            current.get("required_validation_contract") or []
        ),
    }


def v2_component_admission_decision(component_id: str) -> dict[str, Any]:
    """Return the shared admission shape for either adopted V2 mode."""
    current = v2_canonical_record(component_id)
    if _text(current.get("admission_mode")) == "USER_SEQUENCE_ASSISTED":
        return v2_assisted_admission_decision(component_id)
    if _text(current.get("admission_mode")) == "DIRECT_USE":
        return {
            "component_id": _text(current.get("canonical_v2_component_id")),
            "display_name": _text(current.get("name")),
            "component_type": _text(current.get("component_type")),
            "component_role": _text(current.get("role")),
            "participation_mode": "DIRECT_USE",
            "sequence_length": int(current.get("length") or 0),
            "sequence_sha256": _text(current.get("sequence_sha256")),
            "sequence_identity_mode": "CATALOG_SEQUENCE",
            "source_provenance": {
                "display_accession": _text(current.get("accession")),
                "accession": _text(current.get("accession")),
                "source_database": _text(current.get("source")),
                "source_record": _text(current.get("source_record")),
            },
            "rights_classification": "RIGHTS_CLEAR_FOR_CURRENT_USE",
            "current_formal_selectable": bool(current.get("formal_selectable")),
            "current_admission_fields": {
                "library_tier": "CORE",
                "admission_mode": "DIRECT_USE",
                "formal_selectable": bool(current.get("formal_selectable")),
            },
            "known_validation_state": {},
            "host_applicability": copy.deepcopy(current.get("host_applicability") or {}),
            "rights_redistribution_evidence": _text(
                current.get("redistribution_status")
            ),
            "duplicate_or_alias_relationships": {},
            "reason_codes": list(current.get("adoption_blockers") or []),
            "aliases": list(current.get("aliases") or []),
            "component_identity_source": V2_CORE_SOURCE_TYPE,
            "user_sequence_source_required": False,
        }
    raise V2AdoptionError("V2 component is not formally adoptable.")


def _selection_digest(selection: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(selection))
    payload.pop("snapshot_sha256", None)
    payload.pop("registry_comparison", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def v2_canonical_record(component_id: str) -> dict[str, Any]:
    requested = _text(component_id)
    for row in build_v2_canonical_inventory():
        if requested == _text(row.get("canonical_v2_component_id")) or requested in list(row.get("legacy_component_ids") or []):
            return row
    raise V2AdoptionError(f"V2 component identity does not exist: {requested or '<empty>'}.")


def build_v2_direct_selection(
    row: Mapping[str, Any],
    *,
    role: str,
    workflow_id: str = "generic_multi_tu",
    requested_host: str = "",
) -> dict[str, Any]:
    """Build the existing immutable selection shape for a V2 DIRECT_USE row."""
    canonical_id = _text(row.get("canonical_v2_component_id"))
    current = v2_canonical_record(canonical_id)
    if _text(current.get("admission_mode")) != "DIRECT_USE":
        raise V2AdoptionError("Only V2 DIRECT_USE records may create a direct selection.")
    if not bool(current.get("formal_selectable")) and canonical_id not in {
        "V2-CMP-138",
        "V2-CMP-144",
    }:
        raise V2AdoptionError(
            "V2 DIRECT_USE asset is qualified but lacks current Registry/host admission."
        )
    sequence = _text(current.get("sequence")).upper()
    if not sequence or set(sequence) - set("ACGT") or _sha256(sequence) != _text(current.get("sequence_sha256")):
        raise V2AdoptionError("V2 DIRECT_USE sequence identity is invalid.")
    resolved_host = _text(requested_host)
    if _text(workflow_id) != "generic_multi_tu" and not resolved_host:
        raise V2AdoptionError(
            "V2 DIRECT_USE selection is blocked: host-specific workflow requires a requested host."
        )
    host_applicability = copy.deepcopy(current.get("host_applicability") or {})
    if resolved_host:
        from services.plant_component_workflow_registry import (
            HOST_APPLICABILITY_ADMITTED,
            HOST_APPLICABILITY_NOT_PROVEN,
            HOST_APPLICABILITY_WRONG_HOST,
            host_applicability_gate,
        )

        host_status = host_applicability_gate(current, resolved_host)
        if host_status != HOST_APPLICABILITY_ADMITTED:
            reason = (
                "host applicability is not reviewed for the requested host"
                if host_status == HOST_APPLICABILITY_NOT_PROVEN
                else "host applicability does not include the requested host"
                if host_status == HOST_APPLICABILITY_WRONG_HOST
                else "host applicability is not admitted"
            )
            raise V2AdoptionError(f"V2 DIRECT_USE selection is blocked: {reason}.")
    selection = {
        "snapshot_schema_version": "plant-component-selection-snapshot-v1",
        "registry_version": V2_REGISTRY_VERSION,
        "source_type": V2_CORE_SOURCE_TYPE,
        "selection_source": V2_CORE_SOURCE_TYPE,
        "workflow_context": _text(workflow_id),
        "tu_role": _text(role),
        "registry_component_id": "",
        "catalog_component_id": canonical_id,
        "component_type": _text(current.get("component_type")),
        "display_name": _text(current.get("name")),
        "accession_version": _text(current.get("accession")),
        "selected_sequence": sequence,
        "selected_length": len(sequence),
        "sequence_sha256": _text(current.get("sequence_sha256")),
        "evidence_tier": _text(current.get("evidence_tier")),
        "source_organism": _text(current.get("source_organism")),
        "target_host_species": [],
        "component_snapshot": {
            "component_id": canonical_id,
            "component_type": _text(current.get("component_type")),
            "display_name": _text(current.get("name")),
            "sequence": sequence,
            "sequence_length": len(sequence),
            "sequence_sha256": _text(current.get("sequence_sha256")),
            "source_record": _text(current.get("source_record")),
            "source_organism": _text(current.get("source_organism")),
            "source_citation": copy.deepcopy(current.get("v2_source_citation") or {}),
            "asset": copy.deepcopy(current.get("v2_asset") or {}),
            "legacy_component_ids": list(current.get("legacy_component_ids") or []),
        },
        "workflow_compatibility": [_text(workflow_id)],
        "formal_selection_confirmed": False,
        "admission_mode": "DIRECT_USE",
        "governance_status": "DIRECT_USE",
        "distribution_mode": "bundled",
        "sequence_availability": "local_verified",
        "workflow_admission_status": "eligible",
        "v2_selection_contract": V2_DIRECT_SELECTION_CONTRACT,
        "limitation": "Qualified sequence identity and provenance do not establish biological performance or experimental readiness.",
    }
    if resolved_host:
        selection.update(
            {
                "target_host_species": list(host_applicability.get("scope") or []),
                "requested_host": resolved_host,
                "host_applicability_at_selection": host_applicability,
            }
        )
    selection["snapshot_sha256"] = _selection_digest(selection)
    return selection


def validate_v2_direct_selection(
    selection: Mapping[str, Any],
    *,
    role: str,
    sequence: str,
    requested_host: str = "",
) -> dict[str, Any]:
    snapshot = copy.deepcopy(dict(selection))
    if _text(snapshot.get("source_type")) != V2_CORE_SOURCE_TYPE or _text(snapshot.get("selection_source")) != V2_CORE_SOURCE_TYPE:
        raise V2AdoptionError("V2 direct selection authority is invalid.")
    if _text(snapshot.get("v2_selection_contract")) != V2_DIRECT_SELECTION_CONTRACT:
        raise V2AdoptionError("V2 direct selection contract is unsupported.")
    if _text(snapshot.get("snapshot_sha256")) != _selection_digest(snapshot):
        raise V2AdoptionError("V2 direct selection checksum does not match.")
    if _text(snapshot.get("tu_role")) != _text(role):
        raise V2AdoptionError("V2 direct selection role does not match.")
    resolved_host = _text(requested_host) or _text(snapshot.get("requested_host"))
    current = build_v2_direct_selection(
        v2_canonical_record(_text(snapshot.get("catalog_component_id"))),
        role=role,
        workflow_id=_text(snapshot.get("workflow_context")),
        requested_host=resolved_host,
    )
    normalized = _text(sequence).upper()
    if normalized != _text(current.get("selected_sequence")) or snapshot != current:
        raise V2AdoptionError("V2 direct selection does not match the frozen canonical record.")
    if resolved_host and _text(snapshot.get("requested_host")) != resolved_host:
        raise V2AdoptionError("V2 direct selection host does not match the current project host.")
    return snapshot


def build_v2_direct_component(
    row: Mapping[str, Any], *, role: str, requested_host: str = ""
) -> dict[str, Any]:
    selection = build_v2_direct_selection(row, role=role, requested_host=requested_host)
    current = v2_canonical_record(_text(row.get("canonical_v2_component_id")))
    return {
        "role": role,
        "display_name": _text(current.get("name")),
        "raw_text": _text(current.get("sequence")),
        "source_type": V2_CORE_SOURCE_TYPE,
        "source_format": "plain",
        "source_name": _text(current.get("accession")) or V2_REGISTRY_VERSION,
        "provenance_reference": _text(current.get("source_record")),
        "component_identity_source": V2_CORE_SOURCE_TYPE,
        "sequence_source": "V2_CORE_DIRECT",
        "component_reference": selection,
    }


def v2_assisted_confirmation_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    """Expose explicit reviewed intervals, never infer coordinates from a name.

    Length is arithmetic over recorded inclusive coordinates. Neither it nor
    the frozen user checksum verifies the submitted DNA against an accession.
    """
    contract = dict(row.get("v2_assisted_contract") or {})
    boundary = contract.get("recorded_boundary_context")
    reviewed = contract.get("independent_review_status") == "USER_SEQUENCE_ASSISTED_CONFIRMED"
    intervals: set[tuple[int, int, str]] = set()
    if reviewed and isinstance(boundary, Mapping) and not boundary.get("crosses_origin"):
        start, end = boundary.get("start_one_based"), boundary.get("end_one_based_inclusive")
        strand = boundary.get("strand")
        if isinstance(start, int) and isinstance(end, int) and strand in {"+", "-"}:
            intervals.add((start, end, strand))
    elif reviewed and isinstance(boundary, str):
        matches = [re.match(r"^(\d+)\.\.(\d+) \(([+-])\);", s.strip()) for s in boundary.split(" | ")]
        if all(matches):
            intervals = {(int(m[1]), int(m[2]), m[3]) for m in matches if m}
    interval = next(iter(intervals)) if len(intervals) == 1 else None
    explicit = bool(interval and 0 < interval[0] <= interval[1])
    return {
        "confirmation_mode": "IDENTITY_AND_RECORDED_BOUNDARY" if explicit else "PROJECT_INTENT",
        "has_reviewed_boundary": explicit,
        "recorded_boundary": copy.deepcopy(boundary) if explicit else None,
        "expected_length": interval[1] - interval[0] + 1 if explicit else None,
        "expected_length_basis": "recorded_inclusive_coordinates" if explicit else None,
        "sequence_authority": "USER_PROVIDED",
        "accession_verified": False,
        "boundary_verified_by_software": False,
    }


def resolve_v2_user_sequence_for_project(
    row: Mapping[str, Any], sequence: str, *, project_id: str, repository: Any = None,
    identity_and_boundaries_confirmed: bool = False, explicit_user_confirmation: bool = False,
    project_intent_confirmed: bool = False,
    user_sequence_source: str = "",
    supplied_at: str | None = None,
) -> dict[str, Any]:
    current = v2_canonical_record(_text(row.get("canonical_v2_component_id")))
    if _text(current.get("admission_mode")) != "USER_SEQUENCE_ASSISTED":
        raise V2AdoptionError(
            "Only V2 USER_SEQUENCE_ASSISTED records use project resolution."
        )
    project_key = _text(project_id)
    if not project_key or repository is None:
        raise V2AdoptionError(
            "Project-scoped resolution requires an active persisted project."
        )
    try:
        persisted = repository.load(project_key)
    except Exception as exc:
        raise V2AdoptionError(
            "Project-scoped resolution requires an active persisted project."
        ) from exc
    if _text(getattr(persisted, "project_id", "")) != project_key:
        raise V2AdoptionError("Project-scoped resolution project identity is invalid.")
    validation = validate_v2_user_sequence(current, sequence)
    normalized = ""
    if validation["sequence_validation_passed"]:
        from services.mvp_sequence_input import analyze_dna_component_input

        analyzed = analyze_dna_component_input(
            sequence,
            project_id=project_key,
            component_type=_text(current.get("component_type")) or "component",
            display_name=_text(current.get("name")) or "V2 assisted component",
            source_kind="paste",
            source_name=_text(user_sequence_source) or "user-provided sequence",
        )
        normalized = _text(analyzed.get("normalized_sequence"))
    confirmation = v2_assisted_confirmation_contract(current)
    checks = {
        "sequence_supplied": bool(normalized),
        "strict_dna_alphabet": bool(normalized) and not (set(normalized) - set("ACGT")),
        "user_sequence_source_recorded": bool(_text(user_sequence_source)),
        "explicit_user_confirmation": bool(explicit_user_confirmation),
    }
    if confirmation["has_reviewed_boundary"]:
        checks["identity_and_boundaries_confirmed"] = bool(identity_and_boundaries_confirmed)
        checks["expected_length_match"] = len(normalized) == confirmation["expected_length"]
    else:
        checks["project_intent_confirmed"] = bool(project_intent_confirmed)
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise V2AdoptionError(
            "User sequence cannot be resolved for this project: " + ", ".join(failed)
        )
    timestamp = _text(supplied_at) or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    decision = v2_assisted_admission_decision(
        _text(current.get("canonical_v2_component_id"))
    )
    evidence = {
        "schema_version": V2_ASSISTED_RESOLUTION_SCHEMA,
        "resolution_id": "",
        "project_id": project_key,
        "catalog_component_id": _text(current.get("canonical_v2_component_id")),
        "catalog_name": _text(current.get("name")),
        "role": _text(current.get("role")),
        "catalog_component_type": _text(current.get("component_type")),
        "governance_status": "USER_SEQUENCE_ASSISTED",
        "admission_mode": "USER_SEQUENCE_ASSISTED",
        "component_identity_source": V2_CORE_SOURCE_TYPE,
        "sequence_source": "USER_SUPPLIED_CONFIRMED",
        "source_provenance": copy.deepcopy(decision.get("source_provenance") or {}),
        "recorded_boundary_context": copy.deepcopy(
            current.get("recorded_boundary_context")
        ),
        "user_sequence_source": _text(user_sequence_source),
        "normalized_sequence": normalized,
        "sequence_length": len(normalized),
        "sequence_sha256": _sha256(normalized),
        "supplied_at": timestamp,
        "resolution_mode": "PROJECT_LOCAL_USER_SEQUENCE",
        "required_validation_contract": list(
            current.get("required_validation_contract") or []
        ),
        "checks": checks,
        "confirmation_contract": confirmation,
    }
    digest_payload = {key: value for key, value in evidence.items() if key != "resolution_id"}
    evidence["resolution_id"] = hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return evidence


def validate_v2_project_resolution(resolution: Mapping[str, Any], *, project_id: str, sequence: str, repository: Any = None) -> dict[str, Any]:
    evidence = copy.deepcopy(dict(resolution))
    expected_project_id = _text(project_id)
    if _text(evidence.get("schema_version")) != V2_ASSISTED_RESOLUTION_SCHEMA:
        raise V2AdoptionError("Project-scoped resolution schema is not supported.")
    if _text(evidence.get("project_id")) != expected_project_id:
        raise V2AdoptionError(
            "Project-scoped resolution belongs to another project."
        )
    if repository is not None:
        try:
            persisted = repository.load(expected_project_id)
        except Exception as exc:
            raise V2AdoptionError(
                "Project-scoped resolution requires an active persisted project."
            ) from exc
        if _text(getattr(persisted, "project_id", "")) != expected_project_id:
            raise V2AdoptionError("Project-scoped resolution project identity is invalid.")
    if "confirmation_contract" not in evidence:
        # Existing R1 snapshots remain historical USER_PROVIDED records. Do not
        # silently upgrade their old checkbox into the evidence-aware contract.
        return _validate_legacy_v2_resolution(evidence, sequence)
    expected = resolve_v2_user_sequence_for_project(
        v2_canonical_record(_text(evidence.get("catalog_component_id"))),
        sequence,
        project_id=expected_project_id,
        repository=(repository if repository is not None else _ResolutionRepository(expected_project_id)),
        identity_and_boundaries_confirmed=bool((evidence.get("checks") or {}).get("identity_and_boundaries_confirmed")),
        project_intent_confirmed=bool((evidence.get("checks") or {}).get("project_intent_confirmed")),
        explicit_user_confirmation=bool((evidence.get("checks") or {}).get("explicit_user_confirmation")),
        user_sequence_source=_text(evidence.get("user_sequence_source")),
        supplied_at=_text(evidence.get("supplied_at")),
    )
    if expected != evidence:
        raise V2AdoptionError("Project-scoped resolution evidence has been modified.")
    return evidence


def _validate_legacy_v2_resolution(evidence: dict[str, Any], sequence: str) -> dict[str, Any]:
    from services.mvp_sequence_input import analyze_dna_component_input

    current = v2_canonical_record(_text(evidence.get("catalog_component_id")))
    decision = v2_assisted_admission_decision(_text(current.get("canonical_v2_component_id")))
    source = _text(evidence.get("user_sequence_source"))
    analyzed = analyze_dna_component_input(sequence, project_id=_text(evidence.get("project_id")), component_type=_text(current.get("component_type")), display_name=_text(current.get("name")), source_kind="paste", source_name=source)
    normalized = _text(analyzed.get("normalized_sequence"))
    if not source or not normalized or set(normalized) - set("ACGT") or not _text(evidence.get("supplied_at")):
        raise V2AdoptionError("Historical project resolution is incomplete.")
    expected = {
        "schema_version": V2_ASSISTED_RESOLUTION_SCHEMA, "project_id": evidence["project_id"],
        "catalog_component_id": current["canonical_v2_component_id"], "catalog_name": current["name"],
        "role": current["role"], "catalog_component_type": current["component_type"],
        "governance_status": "USER_SEQUENCE_ASSISTED", "admission_mode": "USER_SEQUENCE_ASSISTED",
        "component_identity_source": V2_CORE_SOURCE_TYPE, "sequence_source": "USER_SUPPLIED_CONFIRMED",
        "source_provenance": decision["source_provenance"], "recorded_boundary_context": current.get("recorded_boundary_context"),
        "user_sequence_source": source, "normalized_sequence": normalized, "sequence_length": len(normalized),
        "sequence_sha256": _sha256(normalized), "supplied_at": evidence["supplied_at"],
        "resolution_mode": "PROJECT_LOCAL_USER_SEQUENCE", "required_validation_contract": list(current.get("required_validation_contract") or []),
        "checks": {"sequence_supplied": True, "strict_dna_alphabet": True, "user_sequence_source_recorded": True, "identity_and_boundaries_confirmed": True, "explicit_user_confirmation": True},
    }
    expected["resolution_id"] = hashlib.sha256(json.dumps(expected, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if expected != evidence:
        raise V2AdoptionError("Historical project resolution evidence has been modified.")
    return evidence


class _ResolutionProject:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id


class _ResolutionRepository:
    """Validation-only adapter; creation still requires the real repository."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def load(self, project_id: str) -> _ResolutionProject:
        if _text(project_id) != self.project_id:
            raise KeyError(project_id)
        return _ResolutionProject(self.project_id)


__all__ = [
    "V2AdoptionError", "V2_ASSISTED_RESOLUTION_SCHEMA", "V2_BLOCKED_IDS",
    "V2_CORE_SOURCE_TYPE", "build_v2_canonical_inventory", "build_v2_direct_component",
    "build_v2_direct_selection", "load_v2_package", "resolve_v2_user_sequence_for_project",
    "validate_v2_direct_selection", "validate_v2_project_resolution", "validate_v2_user_sequence",
    "v2_adoption_summary", "v2_assisted_admission_decision",
    "v2_component_admission_decision", "v2_canonical_record",
]
