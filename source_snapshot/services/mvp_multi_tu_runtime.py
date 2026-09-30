"""Ordered multi-transcription-unit runtime built on the canonical construct model."""
from __future__ import annotations

import copy
import hashlib
import json
from io import StringIO
from typing import Any

from Bio import SeqIO

from core.pcambia1300_exact_insertion_contract import is_pcambia1300_record
from services.canonical_construct_runtime import (
    MULTI_TU_PROJECT_TYPE,
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    blank_runtime,
    create_component,
    create_insertion_site,
    create_sequence_asset,
    ensure_runtime,
    export_active_complete_plasmid,
    export_active_construct,
    generate_active_complete_plasmid,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_insertion_site,
    upsert_sequence_asset,
)
from services.acceptance_fixture_identity import fixture_identity_enabled, runtime_identity
from services.mvp_cds_input import analyze_cds_input
from services.plant_component_workflow_registry import (
    PlantComponentRegistryError,
    normalize_component_selection,
    selection_qualifiers,
)


MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION = "v2.7-mvp9-dual-transcription-unit-runtime"
MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION = "1.0.0"
MULTI_TU_EXPRESSION_ASSEMBLY = "MULTI_TU_EXPRESSION_ASSEMBLY"
FIVE_PRIME_ABSENCE_STATE = "explicit_none"
APPROVED_COMPLETE_VECTOR = "APPROVED_COMPLETE_VECTOR"
GENERIC_MULTI_TU_WORKFLOW = "generic_multi_tu"
ASSEMBLY_CAPABILITY_LIMITS = {
    "complete_vector": "not_available_without_an_approved_vector_contract",
    "professional_review_package": "not_available_in_current_version",
    "wet_lab_readiness": "not_assessed",
}
VALID_ORIENTATIONS = {"forward", "reverse"}
UNIT_ROLE_SPECS = (
    ("promoter", "promoter", True),
    ("five_prime_region", "five_prime_utr", True),
    ("targeting_sequence", "signal_targeting_coding_sequence", False),
    ("cds", "cds", True),
    ("linker", "linker", False),
    ("fusion_tag", "c_terminal_tag", False),
    ("3_prime_regulatory_region", "terminator", True),
)
UNIT_ROLES = tuple(item[0] for item in UNIT_ROLE_SPECS)
REQUIRED_UNIT_ROLES = frozenset(item[0] for item in UNIT_ROLE_SPECS if item[2])
LEGACY_UNIT_ROLE_SPECS = tuple(
    item for item in UNIT_ROLE_SPECS if item[0] != "five_prime_region"
)
STRICT_DNA_ALPHABET = frozenset("ATCG")


class MvpMultiTuRuntimeError(ValueError):
    """Raised when a multi-transcription-unit request is structurally invalid."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sha256_sequence(sequence: str) -> str:
    return hashlib.sha256(sequence.upper().encode("ascii")).hexdigest()


def _input_signature(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _raw_sequence(component_input: dict[str, Any]) -> str:
    return str(
        component_input.get("raw_text")
        or component_input.get("sequence")
        or component_input.get("original_text")
        or ""
    )


def _is_explicit_five_prime_absence(component_input: Any) -> bool:
    value = _mapping(component_input)
    state = _text(value.get("absence_state")).casefold()
    return state in {FIVE_PRIME_ABSENCE_STATE, "none"}


def _normalized_five_prime_absence(component_input: Any) -> dict[str, Any]:
    return {
        "absence_state": FIVE_PRIME_ABSENCE_STATE,
        "display_name": _text(_mapping(component_input).get("display_name"))
        or "不使用独立 5′ region",
        "raw_text": "",
        "source_type": "EXPLICIT_ABSENCE",
        "source_format": "none",
        "source_name": "",
        "source_description": "Explicitly absent; no independent 5′ region / 5′ UTR.",
        "provenance_reference": "",
        "provenance_state": "explicit_absence",
    }


def _unit_component_input(unit: dict[str, Any], role: str) -> dict[str, Any]:
    aliases = {
        "3_prime_regulatory_region": ("3_prime_regulatory_region", "terminator"),
        "targeting_sequence": ("targeting_sequence", "targeting"),
        "fusion_tag": ("fusion_tag", "c_terminal_tag", "tag"),
    }
    for key in aliases.get(role, (role,)):
        value = unit.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _unit_role_specs(unit: dict[str, Any]) -> tuple[tuple[str, str, bool], ...]:
    """Keep persisted three-role units readable without upgrading their contents."""
    five_prime = _unit_component_input(unit, "five_prime_region")
    if _is_explicit_five_prime_absence(five_prime):
        return tuple(
            (role, component_type, False if role == "five_prime_region" else required)
            for role, component_type, required in UNIT_ROLE_SPECS
        )
    if "five_prime_region" in unit:
        # A present-but-empty editor field is unconfigured and must block
        # generation; only omitted legacy records use the compatibility path.
        return UNIT_ROLE_SPECS
    if not _raw_sequence(five_prime).strip() and not _text(five_prime.get("component_id")):
        return LEGACY_UNIT_ROLE_SPECS
    return UNIT_ROLE_SPECS


def _unit_roles(unit: dict[str, Any]) -> tuple[str, ...]:
    return tuple(item[0] for item in _unit_role_specs(unit))


def _required_unit_roles(unit: dict[str, Any]) -> frozenset[str]:
    return frozenset(item[0] for item in _unit_role_specs(unit) if item[2])


def _formal_validation(expression_units: list[dict[str, Any]]) -> dict[str, Any]:
    missing_units = [
        _text(unit.get("unit_id"))
        for unit in expression_units
        if not (
            _raw_sequence(_unit_component_input(unit, "five_prime_region")).strip()
            or _text(
                _mapping(
                    _unit_component_input(unit, "five_prime_region").get("component_reference")
                ).get("selected_sequence")
            )
            or _is_explicit_five_prime_absence(
                _unit_component_input(unit, "five_prime_region")
            )
        )
    ]
    if missing_units:
        return {
            "status": "legacy_incomplete",
            "formal_ready": False,
            "findings": [
                {
                    "code": "MISSING_FIVE_PRIME_REGION",
                    "blocking": True,
                    "unit_ids": missing_units,
                }
            ],
        }
    selections = [
        _mapping(_mapping(unit.get(role)).get("component_reference"))
        for unit in expression_units
        for role in _unit_roles(unit)
        if role in _required_unit_roles(unit)
    ]
    formal_ready = bool(selections) and all(
        _text(selection.get("source_type")) == "REGISTRY"
        and bool(selection.get("formal_selection_confirmed"))
        for selection in selections
    )
    return {
        "status": "formal_ready" if formal_ready else "four_role_review_required",
        "formal_ready": formal_ready,
        "findings": [] if formal_ready else [
            {"code": "FORMAL_SELECTION_REVIEW_REQUIRED", "blocking": True, "unit_ids": []}
        ],
    }


def _validate_expression_units(expression_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not expression_units:
        raise MvpMultiTuRuntimeError("multi_tu requires at least one expression unit.")
    fixture_mode = fixture_identity_enabled()
    units = [copy.deepcopy(unit) for unit in expression_units]
    unit_ids = [_text(unit.get("unit_id")) for unit in units]
    if any(not unit_id for unit_id in unit_ids):
        raise MvpMultiTuRuntimeError("Each expression unit requires a non-empty unit_id.")
    if len(set(unit_ids)) != len(unit_ids):
        raise MvpMultiTuRuntimeError("Expression-unit unit_id values must be distinct.")
    orders = [int(unit.get("order", 0) or 0) for unit in units]
    expected_orders = list(range(1, len(units) + 1))
    if sorted(orders) != expected_orders or len(set(orders)) != len(units):
        raise MvpMultiTuRuntimeError(
            "Expression-unit order must contain every position from 1 through the unit count exactly once."
        )

    for unit in units:
        unit_id = _text(unit.get("unit_id"))
        orientation = _text(unit.get("orientation")).lower()
        if orientation not in VALID_ORIENTATIONS:
            raise MvpMultiTuRuntimeError(
                f"Expression unit '{unit_id}' orientation must be forward or reverse."
            )
        unit["unit_id"] = unit_id
        unit["display_name"] = _text(unit.get("display_name") or unit.get("unit_name")) or unit_id
        unit["unit_name"] = unit["display_name"]
        unit["orientation"] = orientation
        unit["order"] = int(unit.get("order"))
        unit["validation_state"] = _text(unit.get("validation_state")) or "current"
        unit["provenance_state"] = _text(unit.get("provenance_state")) or "review_required"
        if fixture_mode:
            unit["unit_id"] = runtime_identity(
                "tu",
                stable_key=f"order={unit['order']}|display={unit['display_name']}|orientation={orientation}",
            )
        for role, _component_type, required in _unit_role_specs(unit):
            component_input = _unit_component_input(unit, role)
            raw_text = _raw_sequence(component_input)
            if role == "five_prime_region" and _is_explicit_five_prime_absence(component_input):
                if raw_text.strip():
                    raise MvpMultiTuRuntimeError(
                        f"Expression unit '{unit_id}' explicit NONE five_prime_region cannot contain sequence data."
                    )
                unit[role] = _normalized_five_prime_absence(component_input)
                continue
            if required and not raw_text.strip():
                raise MvpMultiTuRuntimeError(
                    f"Expression unit '{unit_id}' requires a non-empty {role} sequence."
                )
            if not raw_text.strip():
                unit[role] = {}
                continue
            if role == "cds":
                cds_input = analyze_cds_input(
                    raw_text,
                    source_kind=_text(component_input.get("source_type") or component_input.get("source_kind"))
                    or "user_pasted",
                    source_name=_text(component_input.get("source_name")),
                )
                blocking_rules = [
                    _text(finding.get("rule_id"))
                    for finding in list(cds_input.get("findings") or [])
                    if bool(finding.get("blocking"))
                ]
                if blocking_rules:
                    raise MvpMultiTuRuntimeError(
                        f"Expression unit '{unit_id}' CDS failed validation: {', '.join(blocking_rules)}."
                    )
                component_input["cds_analysis"] = cds_input
            component_input["raw_text"] = raw_text
            unit[role] = component_input
    return units


def _create_unit_records(
    runtime: dict[str, Any],
    *,
    project_id: str,
    unit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    unit_record = {
        "unit_id": unit["unit_id"],
        "unit_name": unit["unit_name"],
        "display_name": unit["display_name"],
        "orientation": unit["orientation"],
        "order": unit["order"],
        "validation_state": unit["validation_state"],
        "provenance_state": unit["provenance_state"],
    }
    normalized_input = {
        "unit_id": unit["unit_id"],
        "unit_name": unit["unit_name"],
        "display_name": unit["display_name"],
        "orientation": unit["orientation"],
        "order": unit["order"],
        "validation_state": unit["validation_state"],
        "provenance_state": unit["provenance_state"],
    }
    for role, component_type, _required in _unit_role_specs(unit):
        source = _mapping(unit.get(role))
        raw_text = _raw_sequence(source)
        if role == "five_prime_region" and _is_explicit_five_prime_absence(source):
            absence = _normalized_five_prime_absence(source)
            unit_record[role] = copy.deepcopy(absence)
            normalized_input[role] = copy.deepcopy(absence)
            continue
        if not raw_text.strip():
            continue
        source_format = _text(source.get("source_format")) or (
            "fasta" if raw_text.lstrip().startswith(">") else "plain"
        )
        display_name = _text(source.get("display_name")) or f"{unit['unit_name']} {role}"
        try:
            asset_id = (
                runtime_identity(
                    "seqasset",
                    stable_key=f"{unit['unit_id']}|role={role}|sequence={raw_text}",
                )
                if fixture_identity_enabled()
                else None
            )
            asset = create_sequence_asset(
                project_id=project_id,
                display_name=display_name,
                raw_text=raw_text,
                molecule_type="dna",
                source_type=_text(source.get("source_type") or source.get("source_kind")) or "paste",
                source_format=source_format,
                source_name=_text(source.get("source_name")),
                source_description=_text(source.get("source_description")),
                provenance_reference=_text(source.get("provenance_reference")),
                asset_role="construct_component",
                asset_id=asset_id,
            )
        except CanonicalConstructRuntimeError as exc:
            raise MvpMultiTuRuntimeError(str(exc)) from exc
        invalid = sorted(
            set(_text(asset.get("nucleotide_sequence")).upper()) - set(STRICT_DNA_ALPHABET)
        )
        if invalid:
            raise MvpMultiTuRuntimeError(
                f"Expression unit '{unit['unit_id']}' {role} contains invalid DNA character(s): {', '.join(invalid)}."
            )
        runtime = upsert_sequence_asset(runtime, asset)
        component_reference: dict[str, Any] = {}
        if role in REQUIRED_UNIT_ROLES:
            try:
                selection_source = copy.deepcopy(source)
                selection_source["_runtime_project_id"] = project_id
                component_reference = normalize_component_selection(
                    selection_source,
                    role=role,
                    sequence=_text(asset.get("nucleotide_sequence")),
                    workflow_id=GENERIC_MULTI_TU_WORKFLOW,
                )
            except PlantComponentRegistryError as exc:
                raise MvpMultiTuRuntimeError(
                    f"Expression unit '{unit['unit_id']}' {role} selection is not admissible: {exc}"
                ) from exc
        component = create_component(
            project_id=project_id,
            component_type=component_type,
            display_name=display_name,
            sequence_asset_id=asset["asset_id"],
            orientation=unit["orientation"],
            provenance_reference=_text(source.get("provenance_reference")),
            component_id=(
                runtime_identity(
                    "component",
                    stable_key=f"{unit['unit_id']}|role={role}|asset={asset['asset_id']}|orientation={unit['orientation']}",
                )
                if fixture_identity_enabled()
                else None
            ),
        )
        runtime = upsert_component(runtime, component)
        unit_record[role] = {
            "component_id": component["component_id"],
            "sequence_asset_id": asset["asset_id"],
            "component_reference": copy.deepcopy(component_reference),
        }
        normalized_input[role] = {
            "display_name": display_name,
            "raw_text": raw_text,
            "source_type": _text(source.get("source_type") or source.get("source_kind")) or "paste",
            "source_format": source_format,
            "source_name": _text(source.get("source_name")),
            "source_description": _text(source.get("source_description")),
            "provenance_reference": _text(source.get("provenance_reference")),
            "component_reference": copy.deepcopy(component_reference),
        }
        if role == "cds":
            normalized_input[role]["cds_analysis"] = copy.deepcopy(source.get("cds_analysis") or {})
    signature_payload = {
        key: copy.deepcopy(value)
        for key, value in normalized_input.items()
        if key != "order"
    }
    unit_signature = _input_signature(signature_payload)
    unit_record["input_signature"] = unit_signature
    unit_record["input_signature_payload"] = signature_payload
    normalized_input["input_signature"] = unit_signature
    return runtime, {"runtime_record": unit_record, "input_record": normalized_input}


def _flatten_component_order(expression_units: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for unit in sorted(expression_units, key=lambda item: int(item.get("order", 0) or 0)):
        roles = _unit_roles(unit)
        if _text(unit.get("orientation")) != "forward":
            roles = tuple(reversed(roles))
        for role in roles:
            ref = _mapping(unit.get(role))
            component_id = _text(ref.get("component_id"))
            if not component_id:
                if role in _required_unit_roles(unit):
                    raise MvpMultiTuRuntimeError(
                        f"Expression unit '{_text(unit.get('unit_id'))}' is missing its {role} component reference."
                    )
                continue
            ordered.append(component_id)
    return ordered


def _require_multi_tu_runtime(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    runtime = ensure_runtime(_text((runtime_payload or {}).get("project_id")), runtime_payload)
    if _text(runtime.get("project_type")) != MULTI_TU_PROJECT_TYPE:
        raise MvpMultiTuRuntimeError("The runtime is not a multi_tu project.")
    if not list(runtime.get("expression_units") or []):
        raise MvpMultiTuRuntimeError("The multi_tu runtime does not contain an expression unit.")
    return runtime


def _combined_construct_snapshot(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    runtime = _require_multi_tu_runtime(runtime_payload)
    construct = active_construct_snapshot(runtime)
    validated_runtime = construct["runtime"]
    combined_sequence = _text(construct.get("sequence"))
    feature_rows = list(construct.get("feature_rows") or [])
    unit_ranges = {
        _text(row.get("unit_id")): row
        for row in feature_rows
        if _text(row.get("component_type")) == "transcription_unit"
    }
    component_rows = [
        row for row in feature_rows if _text(row.get("component_type")) != "transcription_unit"
    ]
    unit_results: list[dict[str, Any]] = []
    for unit in sorted(list(validated_runtime.get("expression_units") or []), key=lambda item: int(item.get("order", 0) or 0)):
        unit_id = _text(unit.get("unit_id"))
        unit_range = dict(unit_ranges.get(unit_id) or {})
        start = int(unit_range.get("start", 0) or 0)
        end = int(unit_range.get("end", 0) or 0)
        unit_sequence = combined_sequence[start - 1 : end] if start >= 1 and end >= start else ""
        input_payload = _mapping(unit.get("input_signature_payload"))
        component_references = {
            role: copy.deepcopy(
                _mapping(_mapping(input_payload.get(role)).get("component_reference"))
            )
            for role in _unit_roles(unit)
            if role in _required_unit_roles(unit)
        }
        unit_components = []
        for raw_row in component_rows:
            if _text(raw_row.get("unit_id")) != unit_id:
                continue
            row = copy.deepcopy(raw_row)
            biological_role = _text(row.get("biological_role"))
            if biological_role in component_references:
                row["component_reference"] = copy.deepcopy(
                    component_references[biological_role]
                )
            unit_components.append(row)
        unit_results.append(
            {
                "unit_id": unit_id,
                "unit_name": _text(unit.get("unit_name")),
                "display_name": _text(unit.get("display_name") or unit.get("unit_name")),
                "orientation": _text(unit.get("orientation")),
                "order": int(unit.get("order", 0) or 0),
                "dna": unit_sequence,
                "length": len(unit_sequence),
                "sequence_sha256": _sha256_sequence(unit_sequence) if unit_sequence else "",
                "input_signature": _text(unit.get("input_signature")),
                "range": {
                    "start": start,
                    "end": end,
                    "strand": int(unit_range.get("strand", 1) or 1),
                },
                "components": unit_components,
                "component_references": component_references,
                "cassette_sequence": unit_sequence,
                "cassette_length": len(unit_sequence),
                "validation_state": _text(unit.get("validation_state")) or "current",
                "provenance_state": _text(unit.get("provenance_state")) or "review_required",
            }
        )

    return {
        "project_type": MULTI_TU_PROJECT_TYPE,
        "runtime": validated_runtime,
        "expression_units": unit_results,
        "unit_order": [unit["unit_id"] for unit in unit_results],
        "combined_construct": {
            "dna": combined_sequence,
            "total_length": len(combined_sequence),
            "sequence_sha256": _text(construct.get("sequence_checksum")),
            "component_coordinates": [
                copy.deepcopy(row)
                for unit in unit_results
                for row in list(unit.get("components") or [])
            ],
            "unit_ranges": [dict(unit_ranges[unit["unit_id"]]) for unit in unit_results],
            "input_signature": _text(
                validated_runtime["transcription_units"][0].get("input_signature")
            ),
            "validation_status": _text(construct.get("construct_status")),
            "validation_findings": list(construct.get("validation_findings") or []),
            "validation_summary": dict(construct.get("validation_summary") or {}),
            "formal_validation": _formal_validation(
                list(validated_runtime.get("expression_units") or [])
            ),
        },
    }


def multi_tu_snapshot(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    combined = _combined_construct_snapshot(runtime_payload)
    complete = active_complete_plasmid_snapshot(combined["runtime"])
    return {
        **combined,
        "runtime": complete["runtime"],
        "complete_plasmid": {
            "dna": _text(complete.get("sequence")),
            "total_length": int(complete.get("sequence_length", 0) or 0),
            "sequence_sha256": _text(complete.get("sequence_checksum")),
            "cassette_coordinates": dict(complete.get("cassette_coordinates") or {}),
            "feature_coordinates": list(complete.get("feature_rows") or []),
            "input_signature": _text(
                complete["runtime"]["complete_plasmid_constructs"][0].get("input_signature")
            ),
            "validation_status": _text(complete.get("construct_status")),
            "validation_findings": list(complete.get("validation_findings") or []),
            "validation_summary": dict(complete.get("validation_summary") or {}),
        },
    }


def multi_tu_assembly_snapshot(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return the current canonical multi-TU assembly without requiring a vector."""
    return _combined_construct_snapshot(runtime_payload)


def _unit_fasta_exports(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from components.export_manager import generate_fasta_string

    return {
        unit["unit_id"]: {
            "label": f"Export {unit['display_name'] or unit['unit_id']} canonical FASTA (.fasta)",
            "file_name": f"{unit['unit_id']}_{unit['sequence_sha256'][:16]}.fasta",
            "mime": "text/plain",
            "data": generate_fasta_string(
                unit["dna"],
                f"{unit['unit_id']}|order={unit['order']}|orientation={unit['orientation']}|len={unit['length']}|sha256={unit['sequence_sha256']}",
            ),
        }
        for unit in snapshot["expression_units"]
    }


def _assembly_genbank(data: str, *, project_name: str, unit_count: int) -> str:
    from components.export_manager import write_genbank_record

    record = next(SeqIO.parse(StringIO(data), "genbank"))
    record.description = (
        f"{project_name} Multi-TU expression assembly; linear canonical sequence without an approved vector background"
    )
    record.annotations["topology"] = "linear"
    record.annotations["comment"] = (
        f"result_kind={MULTI_TU_EXPRESSION_ASSEMBLY}; "
        f"workflow={GENERIC_MULTI_TU_WORKFLOW}; tu_count={unit_count}; contains_vector=false"
    )
    output = StringIO()
    write_genbank_record(record, output)
    return output.getvalue()


def _component_reference_summary(snapshot: dict[str, Any]) -> str:
    references: list[str] = []
    for unit in snapshot["expression_units"]:
        component_references = _mapping(unit.get("component_references"))
        for role in UNIT_ROLES:
            reference = _mapping(component_references.get(role))
            if not reference:
                continue
            component_id = _text(reference.get("registry_component_id"))
            references.append(component_id or f"USER_PROVIDED:{role}")
    return ",".join(references)


def _traceable_assembly_genbank(data: str, *, snapshot: dict[str, Any]) -> str:
    from components.export_manager import write_genbank_record

    record = next(SeqIO.parse(StringIO(data), "genbank"))
    references = {
        (_text(unit.get("unit_id")), role): reference
        for unit in snapshot["expression_units"]
        for role in UNIT_ROLES
        if (reference := _mapping(_mapping(unit.get("component_references")).get(role)))
    }
    for feature in record.features:
        unit_id = _text((feature.qualifiers.get("unit_id") or [""])[0])
        role = _text((feature.qualifiers.get("biological_role") or [""])[0])
        reference = references.get((unit_id, role), {})
        if not reference:
            continue
        feature.qualifiers.update(selection_qualifiers(reference))
    output = StringIO()
    write_genbank_record(record, output)
    return output.getvalue()


def export_multi_tu_assembly_outputs(
    runtime_payload: dict[str, Any] | None,
    *,
    project_name: str,
) -> dict[str, Any]:
    """Export only the canonical linear assembly and its expression units."""
    runtime = _require_multi_tu_runtime(runtime_payload)
    canonical = export_active_construct(runtime, project_name=project_name)
    snapshot = _combined_construct_snapshot(runtime)
    from components.export_manager import generate_fasta_string

    combined = snapshot["combined_construct"]
    unit_count = len(snapshot["expression_units"])
    header = (
        f"{project_name}|workflow=Multi-TU|tu_count={unit_count}|"
        f"result_kind={MULTI_TU_EXPRESSION_ASSEMBLY}|contains_vector=false|"
        f"len={combined['total_length']}|sha256={combined['sequence_sha256']}|"
        f"components={_component_reference_summary(snapshot)}"
    )
    fasta = {
        **canonical["fasta"],
        "label": "Export Multi-TU canonical assembly FASTA (.fasta)",
        "data": generate_fasta_string(combined["dna"], header),
    }
    genbank = {
        **canonical["genbank"],
        "label": "Export Multi-TU canonical assembly GenBank (.gb)",
        "data": _assembly_genbank(
            _traceable_assembly_genbank(
                canonical["genbank"]["data"],
                snapshot=snapshot,
            ),
            project_name=project_name,
            unit_count=unit_count,
        ),
    }
    return {
        "unit_fastas": _unit_fasta_exports(snapshot),
        "combined_construct_fasta": fasta,
        "combined_construct_genbank": genbank,
        "metadata": {
            "result_kind": MULTI_TU_EXPRESSION_ASSEMBLY,
            "contains_vector": False,
            "combined_construct": canonical["metadata"],
        },
    }


def project_assisted_assembly_outputs(result: dict[str, Any]) -> dict[str, Any]:
    """Refresh current assisted GenBank provenance without changing saved state.

    Old in-memory results may carry pre-fix export bytes. Re-export only their
    current canonical GenBank at the active Step 6 output boundary; historical
    saved-artifact downloads and canonical input/revision identities are intact.
    """
    from services.component_output_provenance import runtime_assisted_component_provenance

    runtime = _mapping(result.get('runtime'))
    exports = _mapping(result.get('exports'))
    if not exports.get('combined_construct_genbank') or not runtime_assisted_component_provenance(runtime):
        return result
    current = export_multi_tu_assembly_outputs(runtime, project_name=_text(result.get('project_name')))
    return {**result, 'exports': {**exports, 'combined_construct_genbank': current['combined_construct_genbank']}}


def export_multi_tu_outputs(
    runtime_payload: dict[str, Any] | None,
    *,
    project_name: str,
) -> dict[str, Any]:
    runtime = _require_multi_tu_runtime(runtime_payload)
    combined = export_active_construct(runtime, project_name=project_name)
    complete = export_active_complete_plasmid(runtime, project_name=project_name)
    snapshot = _combined_construct_snapshot(runtime)
    return {
        "unit_fastas": _unit_fasta_exports(snapshot),
        "combined_construct_fasta": combined["fasta"],
        "complete_plasmid_fasta": complete["fasta"],
        "complete_plasmid_genbank": complete["genbank"],
        "metadata": {
            "combined_construct": combined["metadata"],
            "complete_plasmid": complete["metadata"],
        },
    }


def generate_multi_tu_combined_construct(
    *,
    project_id: str,
    project_name: str,
    expression_units: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate the current ordered multi-unit construct without composing a plasmid."""
    resolved_project_id = _text(project_id)
    resolved_project_name = _text(project_name)
    if not resolved_project_id or not resolved_project_name:
        raise MvpMultiTuRuntimeError("project_id and project_name are required.")
    units = _validate_expression_units(expression_units)

    fixture_mode = fixture_identity_enabled()
    runtime = blank_runtime(resolved_project_id)
    if fixture_mode:
        deterministic_ids = {
            "tu": runtime_identity("tu", stable_key="multi-tu|active-transcription-unit"),
            "construct": runtime_identity("construct", stable_key="multi-tu|active-construct"),
            "insertion": runtime_identity("insertion", stable_key="multi-tu|active-insertion-site"),
            "plasmid": runtime_identity("plasmid", stable_key="multi-tu|active-complete-plasmid"),
        }
        runtime["transcription_units"][0]["tu_id"] = deterministic_ids["tu"]
        runtime["constructs"][0]["construct_id"] = deterministic_ids["construct"]
        runtime["constructs"][0]["transcription_unit_id"] = deterministic_ids["tu"]
        runtime["constructs"][0]["persistence_identity"] = deterministic_ids["construct"]
        runtime["insertion_sites"][0]["site_id"] = deterministic_ids["insertion"]
        runtime["complete_plasmid_constructs"][0]["plasmid_id"] = deterministic_ids["plasmid"]
        runtime["complete_plasmid_constructs"][0]["transcription_unit_id"] = deterministic_ids["tu"]
        runtime["complete_plasmid_constructs"][0]["insertion_site_id"] = deterministic_ids["insertion"]
        runtime["complete_plasmid_constructs"][0]["persistence_identity"] = deterministic_ids["plasmid"]
        runtime["active_transcription_unit_id"] = deterministic_ids["tu"]
        runtime["active_construct_id"] = deterministic_ids["construct"]
        runtime["active_insertion_site_id"] = deterministic_ids["insertion"]
        runtime["active_complete_plasmid_id"] = deterministic_ids["plasmid"]
    runtime["project_type"] = MULTI_TU_PROJECT_TYPE
    runtime["multi_tu_schema_version"] = MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION
    runtime_units: list[dict[str, Any]] = []
    input_units: list[dict[str, Any]] = []
    for unit in units:
        runtime, records = _create_unit_records(runtime, project_id=resolved_project_id, unit=unit)
        runtime_units.append(records["runtime_record"])
        input_units.append(records["input_record"])
    runtime["expression_units"] = runtime_units
    for unit in units:
        runtime = set_multi_tu_unit_orientation(
            runtime,
            unit_id=unit["unit_id"],
            orientation=unit["orientation"],
        )
    runtime = set_multi_tu_unit_order(
        runtime,
        [unit["unit_id"] for unit in sorted(units, key=lambda item: item["order"])],
    )
    runtime = generate_active_construct(runtime)

    snapshot = _combined_construct_snapshot(runtime)
    if snapshot["combined_construct"]["validation_status"] != "current":
        raise MvpMultiTuRuntimeError("The combined multi-TU construct has blocking validation findings.")
    result = {
        "schema_version": MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION,
        "project_schema_version": MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION,
        "project_type": MULTI_TU_PROJECT_TYPE,
        "workflow_kind": GENERIC_MULTI_TU_WORKFLOW,
        "result_kind": MULTI_TU_EXPRESSION_ASSEMBLY,
        "contains_vector": False,
        "capability_limits": copy.deepcopy(ASSEMBLY_CAPABILITY_LIMITS),
        "current_step_state": 4,
        "project_id": resolved_project_id,
        "project_name": resolved_project_name,
        "original_input": {"expression_units": input_units},
        "expression_units": snapshot["expression_units"],
        "unit_input_signatures": {
            unit["unit_id"]: unit["input_signature"]
            for unit in snapshot["expression_units"]
        },
        "unit_order": snapshot["unit_order"],
        "combined_construct": snapshot["combined_construct"],
        "formal_validation": copy.deepcopy(snapshot["combined_construct"]["formal_validation"]),
        "input_signature": snapshot["combined_construct"]["input_signature"],
        "runtime": snapshot["runtime"],
    }
    result["exports"] = export_multi_tu_assembly_outputs(
        result["runtime"],
        project_name=resolved_project_name,
    )
    return result


def generate_multi_tu_complete_plasmid(
    combined_result: dict[str, Any],
    *,
    backbone: dict[str, Any],
    insertion_settings: dict[str, Any],
) -> dict[str, Any]:
    """Compose a generated multi-unit construct into the requested backbone."""
    if _text(combined_result.get("project_type")) != MULTI_TU_PROJECT_TYPE:
        raise MvpMultiTuRuntimeError("The combined result is not a multi_tu project.")
    resolved_project_id = _text(combined_result.get("project_id"))
    resolved_project_name = _text(combined_result.get("project_name"))
    runtime = _require_multi_tu_runtime(_mapping(combined_result.get("runtime")))

    backbone_input = _mapping(backbone)
    if is_pcambia1300_record(backbone_input):
        raise MvpMultiTuRuntimeError(
            "pCAMBIA-1300 / AF234296.1 is blocked for Multi-TU use because multi-TU capacity, orientation, and promoter-interference acceptance is not complete."
        )
    backbone_raw_text = _raw_sequence(backbone_input)
    if not backbone_raw_text.strip():
        raise MvpMultiTuRuntimeError("A non-empty circular backbone input is required.")
    try:
        backbone_asset = create_sequence_asset(
            project_id=resolved_project_id,
            display_name=_text(backbone_input.get("display_name")) or "Multi-TU backbone",
            raw_text=backbone_raw_text,
            molecule_type="dna",
            source_type=_text(backbone_input.get("source_type") or backbone_input.get("source_kind")) or "upload",
            source_format=_text(backbone_input.get("source_format")) or "genbank",
            source_name=_text(backbone_input.get("source_name")),
            source_description=_text(backbone_input.get("source_description")),
            provenance_reference=_text(backbone_input.get("provenance_reference")),
            topology=_text(backbone_input.get("topology")),
            asset_role="backbone",
        )
    except CanonicalConstructRuntimeError as exc:
        raise MvpMultiTuRuntimeError(str(exc)) from exc
    runtime = upsert_sequence_asset(runtime, backbone_asset)

    site_input = _mapping(insertion_settings)
    try:
        insertion_site = create_insertion_site(
            project_id=resolved_project_id,
            backbone_asset_id=backbone_asset["asset_id"],
            start_coordinate=int(site_input.get("start_coordinate", 0) or 0),
            end_coordinate=int(site_input.get("end_coordinate", 0) or 0),
            mode=_text(site_input.get("mode")),
            expected_removed_sequence=_text(site_input.get("expected_removed_sequence")),
            insertion_orientation=_text(site_input.get("insertion_orientation")) or "forward",
            user_confirmation=bool(site_input.get("user_confirmation", True)),
            topology_confirmation=bool(site_input.get("topology_confirmation", False)),
        )
    except (CanonicalConstructRuntimeError, TypeError, ValueError) as exc:
        raise MvpMultiTuRuntimeError(str(exc)) from exc
    runtime = upsert_insertion_site(runtime, insertion_site)
    runtime = generate_active_complete_plasmid(runtime)

    snapshot = multi_tu_snapshot(runtime)
    if snapshot["complete_plasmid"]["validation_status"] != "current":
        rules = [
            _text(item.get("rule_id"))
            for item in snapshot["complete_plasmid"]["validation_findings"]
            if bool(item.get("blocking"))
        ]
        raise MvpMultiTuRuntimeError(
            "The complete multi-TU plasmid has blocking validation findings"
            + (f": {', '.join(rules)}." if rules else ".")
        )
    exports = export_multi_tu_outputs(snapshot["runtime"], project_name=resolved_project_name)
    original_input = copy.deepcopy(_mapping(combined_result.get("original_input")))
    original_input["backbone"] = copy.deepcopy(backbone_input)
    original_input["insertion_settings"] = copy.deepcopy(site_input)
    return {
        "schema_version": MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION,
        "project_schema_version": MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION,
        "project_type": MULTI_TU_PROJECT_TYPE,
        "project_id": resolved_project_id,
        "project_name": resolved_project_name,
        "original_input": original_input,
        "expression_units": snapshot["expression_units"],
        "unit_input_signatures": {
            unit["unit_id"]: unit["input_signature"]
            for unit in snapshot["expression_units"]
        },
        "unit_order": snapshot["unit_order"],
        "combined_construct": snapshot["combined_construct"],
        "complete_plasmid": snapshot["complete_plasmid"],
        "input_signature": snapshot["complete_plasmid"]["input_signature"],
        "runtime": snapshot["runtime"],
        "exports": exports,
    }


def generate_admitted_multi_tu_complete_plasmid(
    combined_result: dict[str, Any],
    *,
    backbone: dict[str, Any],
    insertion_settings: dict[str, Any],
    workflow_id: str,
) -> dict[str, Any]:
    """Generate a formal multi-TU plasmid only after contract admission."""
    from services.vector_asset_admission import require_vector_operation

    require_vector_operation(
        backbone,
        workflow_id=workflow_id,
        insertion_settings=insertion_settings,
    )
    return generate_multi_tu_complete_plasmid(
        combined_result,
        backbone=backbone,
        insertion_settings=insertion_settings,
    )


def generate_multi_tu_construct(
    *,
    project_id: str,
    project_name: str,
    expression_units: list[dict[str, Any]],
    backbone: dict[str, Any],
    insertion_settings: dict[str, Any],
) -> dict[str, Any]:
    """Generate both multi-TU stages through the formal two-stage wrappers."""
    combined = generate_multi_tu_combined_construct(
        project_id=project_id,
        project_name=project_name,
        expression_units=expression_units,
    )
    return generate_multi_tu_complete_plasmid(
        combined,
        backbone=backbone,
        insertion_settings=insertion_settings,
    )


def set_multi_tu_unit_order(
    runtime_payload: dict[str, Any] | None,
    unit_order: list[str],
) -> dict[str, Any]:
    runtime = _require_multi_tu_runtime(runtime_payload)
    requested = [_text(unit_id) for unit_id in unit_order]
    existing = {_text(unit.get("unit_id")) for unit in list(runtime.get("expression_units") or [])}
    if len(requested) != len(existing) or len(set(requested)) != len(existing) or set(requested) != existing:
        raise MvpMultiTuRuntimeError("unit_order must contain every expression-unit id exactly once.")
    for unit in list(runtime.get("expression_units") or []):
        unit["order"] = requested.index(_text(unit.get("unit_id"))) + 1
    return set_active_component_order(runtime, _flatten_component_order(runtime["expression_units"]))


def set_multi_tu_unit_orientation(
    runtime_payload: dict[str, Any] | None,
    *,
    unit_id: str,
    orientation: str,
) -> dict[str, Any]:
    runtime = _require_multi_tu_runtime(runtime_payload)
    resolved_orientation = _text(orientation).lower()
    if resolved_orientation not in VALID_ORIENTATIONS:
        raise MvpMultiTuRuntimeError("orientation must be forward or reverse.")
    target = next(
        (unit for unit in list(runtime.get("expression_units") or []) if _text(unit.get("unit_id")) == _text(unit_id)),
        None,
    )
    if target is None:
        raise MvpMultiTuRuntimeError("The requested expression unit does not exist.")
    target["orientation"] = resolved_orientation
    signature_payload = copy.deepcopy(_mapping(target.get("input_signature_payload")))
    signature_payload["orientation"] = resolved_orientation
    target["input_signature_payload"] = signature_payload
    target["input_signature"] = _input_signature(signature_payload)
    component_index = {
        _text(component.get("component_id")): component
        for component in list(runtime.get("components") or [])
    }
    for role in _unit_roles(target):
        component_id = _text(_mapping(target.get(role)).get("component_id"))
        if not component_id and role not in _required_unit_roles(target):
            continue
        component = copy.deepcopy(component_index.get(component_id) or {})
        if not component:
            raise MvpMultiTuRuntimeError(f"The expression unit is missing its {role} component.")
        component["orientation"] = resolved_orientation
        runtime = upsert_component(runtime, component)
    runtime["expression_units"] = [
        copy.deepcopy(target) if _text(unit.get("unit_id")) == _text(unit_id) else unit
        for unit in list(runtime.get("expression_units") or [])
    ]
    return set_active_component_order(runtime, _flatten_component_order(runtime["expression_units"]))
