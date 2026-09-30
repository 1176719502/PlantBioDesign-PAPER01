"""Durable persistence for ordered multi-transcription-unit project records."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO

from services.mvp_multi_tu_runtime import (
    ASSEMBLY_CAPABILITY_LIMITS,
    GENERIC_MULTI_TU_WORKFLOW,
    MULTI_TU_EXPRESSION_ASSEMBLY,
    MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION,
    MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION,
    MvpMultiTuRuntimeError,
    export_multi_tu_assembly_outputs,
    export_multi_tu_outputs,
    multi_tu_assembly_snapshot,
    multi_tu_snapshot,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    PlantProjectDraftSummary,
    SqlitePlantProjectDraftRepository,
    require_active_project,
)
from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    update_plant_project_draft,
)
from services.formal_project_persistence import (
    WORKFLOW_GATE3_PATHWAY,
    WORKFLOW_MULTI_TU,
    mark_formal_project_completed,
)
from services.formal_editor_state_contract import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION,
    RECORD_KIND_FORMAL_EDITOR_COMPLETED,
)
from services.plant_component_workflow_registry import (
    REGISTRY_SOURCE_TYPE,
    PlantComponentRegistryError,
    admit_registry_selection,
    compare_selection_to_current_registry,
    selection_qualifiers,
    validate_saved_selection,
)


MVP_MULTI_TU_PERSISTENCE_KEY = "mvp_multi_tu_persistence"
MVP_MULTI_TU_PERSISTENCE_SCHEMA_VERSION = "v2.7-mvp9-multi-tu-persistence"
MVP_SINGLE_GENE_PERSISTENCE_KEY = "mvp_single_gene_persistence"
PROJECT_TYPE = "multi_tu"
FORMAL_PROJECT_TYPE = "dual_tu"
SUPPORTED_PROJECT_TYPES = frozenset({PROJECT_TYPE, FORMAL_PROJECT_TYPE})
COMPLETE_EXPORT_KEYS = (
    "combined_construct_fasta",
    "complete_plasmid_fasta",
    "complete_plasmid_genbank",
)
ASSEMBLY_EXPORT_KEYS = (
    "combined_construct_fasta",
    "combined_construct_genbank",
)
LEGACY_COMPLETE_VECTOR_RECORD = "LEGACY_COMPLETE_VECTOR_RECORD"
TRACEABLE_COMPONENT_ROLES = (
    "promoter",
    "five_prime_region",
    "cds",
    "3_prime_regulatory_region",
)
ASSEMBLY_NO_VECTOR_STATUS = "not_applicable_without_vector"


def _is_explicit_five_prime_absence(value: Any) -> bool:
    component = _mapping(value)
    return _text(component.get("absence_state")).casefold() in {
        "explicit_none",
        "none",
    }


class MvpMultiTuPersistenceError(ValueError):
    """Raised when an MVP9 saved project cannot be used safely."""


def _default_multi_tu_repository() -> SqlitePlantProjectDraftRepository:
    return SqlitePlantProjectDraftRepository()


def _is_gate3_context(value: dict[str, Any]) -> bool:
    context = _mapping(value.get("formal_project_context"))
    return _text(context.get("design_scenario")) == "metabolic_pathway_multi_tu_vector"


def _formal_vector_workflow_id(context: dict[str, Any]) -> str:
    if _text(context.get("design_scenario")) != "metabolic_pathway_multi_tu_vector":
        return GENERIC_MULTI_TU_WORKFLOW
    if bool(context.get("replacement_strategy_id")):
        return "betalain_gate3"
    return WORKFLOW_GATE3_PATHWAY


def multi_tu_formal_editor_restore_reason(result: dict[str, Any]) -> str:
    """Return an empty reason only for an explicitly resumable editor record."""
    if _text(result.get("project_type")) not in SUPPORTED_PROJECT_TYPES:
        return "unsupported_project_type"
    context = _mapping(result.get("formal_project_context"))
    if _text(context.get("project_type")) not in SUPPORTED_PROJECT_TYPES:
        return "unsupported_project_type"
    if _text(context.get("record_kind")) != RECORD_KIND_FORMAL_EDITOR_COMPLETED:
        return "legacy_record"
    if (
        _text(context.get("formal_editor_state_contract_version"))
        != FORMAL_EDITOR_STATE_CONTRACT_VERSION
    ):
        return "unsupported_version"
    if int(context.get("current_step") or 0) != 6:
        return "state_canonical_mismatch"
    expected_workflow = _formal_vector_workflow_id(context)
    if _text(result.get("workflow_kind")) != expected_workflow:
        return "state_canonical_mismatch"
    scenario = _text(context.get("design_scenario"))
    if scenario not in {"", "standard_plant_expression_vector", "metabolic_pathway_multi_tu_vector"}:
        return "state_canonical_mismatch"

    state = _mapping(context.get("formal_state"))
    required_mappings = (
        "formal_project_definition",
        "formal_backbone_record",
        "formal_insertion_settings",
        "formal_dual_tu_combined_result",
    )
    if not state or any(not _mapping(state.get(key)) for key in required_mappings):
        return "missing_formal_state"
    expected_scenario = scenario or "standard_plant_expression_vector"
    if (
        _text(state.get("formal_project_type")) not in SUPPORTED_PROJECT_TYPES
        or _text(state.get("formal_design_scenario")) != expected_scenario
    ):
        return "state_canonical_mismatch"
    state_units = list(state.get("formal_transcription_units") or [])
    original = _mapping(result.get("original_input"))
    original_units = list(original.get("expression_units") or [])
    if not state_units or [
        _text(_mapping(unit).get("unit_id")) for unit in state_units
    ] != [_text(_mapping(unit).get("unit_id")) for unit in original_units]:
        return "state_canonical_mismatch"
    if expected_workflow == WORKFLOW_GATE3_PATHWAY:
        context_step_ids = [
            _text(_mapping(step).get("step_id"))
            for step in list(context.get("pathway_steps") or [])
        ]
        state_step_ids = [
            _text(_mapping(step).get("step_id"))
            for step in list(state.get("formal_pathway_steps") or [])
        ]
        if not context_step_ids or state_step_ids != context_step_ids:
            return "state_canonical_mismatch"
    definition = _mapping(context.get("project_definition"))
    state_definition = _mapping(state.get("formal_project_definition"))
    if not definition or any(
        _text(state_definition.get(key)) != _text(definition.get(key))
        for key in ("project_name", "plant_host")
    ):
        return "state_canonical_mismatch"
    state_result = _mapping(state.get("formal_dual_tu_combined_result"))
    if (
        _text(state_result.get("project_id")) != _text(result.get("project_id"))
        or _text(state.get("mvp_project_id")) != _text(result.get("project_id"))
        or _text(state.get("mvp_current_input_signature"))
        != _text(result.get("input_signature"))
    ):
        return "state_canonical_mismatch"
    state_insertion = _mapping(state.get("formal_insertion_settings"))
    original_insertion = _mapping(original.get("insertion_settings"))
    if _is_assembly_result(result):
        if (
            _text(result.get("result_kind")) != MULTI_TU_EXPRESSION_ASSEMBLY
            or result.get("contains_vector") is not False
            or _text(result.get("topology")) != "linear"
        ):
            return "state_canonical_mismatch"
        try:
            expected_backbone, expected_insertion = (
                linear_multi_tu_completed_editor_vector_state(result)
            )
        except MvpMultiTuPersistenceError:
            return "state_canonical_mismatch"
        if (
            _mapping(state.get("formal_backbone_record")) != expected_backbone
            or state_insertion != expected_insertion
            or _mapping(original.get("backbone")) != expected_backbone
            or original_insertion != expected_insertion
        ):
            return "state_canonical_mismatch"
    if any(
        state_insertion.get(key) != original_insertion.get(key)
        for key in (
            "mode",
            "start_coordinate",
            "end_coordinate",
            "insertion_orientation",
            "workflow_id",
        )
    ):
        return "state_canonical_mismatch"
    return ""


def _fresh_repository(repository: Any) -> Any:
    if isinstance(repository, SqlitePlantProjectDraftRepository):
        return SqlitePlantProjectDraftRepository(repository.database_path)
    return PlantProjectDraftRepository(repository.storage_dir)


def _text(value: Any) -> str:
    return str(value or "")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _traceable_roles(unit: dict[str, Any]) -> tuple[str, ...]:
    if not _mapping(unit.get("five_prime_region")) or _is_explicit_five_prime_absence(
        unit.get("five_prime_region")
    ):
        return tuple(role for role in TRACEABLE_COMPONENT_ROLES if role != "five_prime_region")
    return TRACEABLE_COMPONENT_ROLES


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _encode_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decode_text(value: str, *, label: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise MvpMultiTuPersistenceError(
            f"Saved {label} bytes are corrupted and cannot be reopened."
        ) from exc


def _is_assembly_result(value: dict[str, Any]) -> bool:
    return (
        _text(value.get("result_kind")) == MULTI_TU_EXPRESSION_ASSEMBLY
        or value.get("contains_vector") is False
    )


def _is_mt01_claim(value: dict[str, Any]) -> bool:
    from services.mt01_formal_runtime import is_mt01_claim

    return is_mt01_claim(value)


def _validate_mt01_claim(value: dict[str, Any]) -> dict[str, Any]:
    from services.mt01_formal_runtime import Mt01RuntimeError, validate_mt01_result

    try:
        return validate_mt01_result(value)
    except Mt01RuntimeError as exc:
        raise MvpMultiTuPersistenceError(str(exc)) from exc


def _is_mt02_claim(value: dict[str, Any]) -> bool:
    from services.mt02_formal_runtime import is_mt02_claim

    return is_mt02_claim(value)


def _validate_mt02_claim(value: dict[str, Any]) -> dict[str, Any]:
    from services.mt02_formal_runtime import Mt02RuntimeError, validate_mt02_result

    try:
        return validate_mt02_result(value)
    except Mt02RuntimeError as exc:
        raise MvpMultiTuPersistenceError(str(exc)) from exc


def _real_case_id(value: dict[str, Any]) -> str:
    provenance_case_id = _text(_mapping(value.get("case_provenance")).get("case_id"))
    snapshot_case_id = _text(_mapping(value.get("case_snapshot")).get("case_id"))
    if provenance_case_id == snapshot_case_id and provenance_case_id in {"MT-01", "MT-02"}:
        return provenance_case_id
    if _is_mt01_claim(value):
        return "MT-01"
    if _is_mt02_claim(value):
        return "MT-02"
    return ""


def _validated_real_case_id(value: dict[str, Any]) -> str:
    case_id = _real_case_id(value)
    if case_id == "MT-01":
        _validate_mt01_claim(value)
    elif case_id == "MT-02":
        _validate_mt02_claim(value)
    return case_id


def _assembly_vector_status() -> dict[str, Any]:
    return {
        "allowed": False,
        "status": ASSEMBLY_NO_VECTOR_STATUS,
        "workflow_id": GENERIC_MULTI_TU_WORKFLOW,
        "identity": {},
        "contract": {},
        "canonical_settings": {},
        "reason": "This Multi-TU expression assembly does not contain a vector background.",
        "legacy_project_read_only": False,
        "completed_design_allowed": False,
        "modified_vector_export_allowed": False,
    }


def linear_multi_tu_completed_editor_vector_state(
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the explicit no-vector state for a canonical linear assembly."""
    if (
        _text(result.get("project_type")) not in SUPPORTED_PROJECT_TYPES
        or _text(result.get("workflow_kind")) != GENERIC_MULTI_TU_WORKFLOW
        or _text(result.get("result_kind")) != MULTI_TU_EXPRESSION_ASSEMBLY
        or result.get("contains_vector") is not False
        or _text(result.get("topology")) not in {"", "linear"}
    ):
        raise MvpMultiTuPersistenceError(
            "Only a canonical linear Multi-TU assembly can bind no-vector editor state."
        )
    common = {
        "status": ASSEMBLY_NO_VECTOR_STATUS,
        "workflow_id": GENERIC_MULTI_TU_WORKFLOW,
        "contains_vector": False,
        "assembly_topology": "linear",
    }
    backbone = {**common, "record_kind": "no_backbone"}
    insertion = {
        **common,
        "record_kind": "no_insertion",
        "mode": "not_applicable",
        "start_coordinate": None,
        "end_coordinate": None,
        "insertion_orientation": "not_applicable",
    }
    return backbone, insertion


def _validated_component_references(
    original_input: dict[str, Any],
    active: dict[str, Any],
    *,
    registry_path: str | Path | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    active_units = {
        _text(unit.get("unit_id")): _mapping(unit)
        for unit in list(active.get("expression_units") or [])
    }
    comparisons: dict[str, dict[str, dict[str, Any]]] = {}
    for raw_unit in list(original_input.get("expression_units") or []):
        unit = _mapping(raw_unit)
        unit_id = _text(unit.get("unit_id"))
        active_unit = active_units.get(unit_id)
        if active_unit is None:
            raise MvpMultiTuPersistenceError(
                "Saved component snapshots do not match the canonical expression units."
            )
        active_references = _mapping(active_unit.get("component_references"))
        comparisons[unit_id] = {}
        for role in _traceable_roles(unit):
            component_input = _mapping(unit.get(role))
            reference = _mapping(component_input.get("component_reference"))
            sequence = _text(reference.get("selected_sequence"))
            try:
                validated = validate_saved_selection(reference, role=role, sequence=sequence)
                if _text(validated.get("source_type")) == REGISTRY_SOURCE_TYPE:
                    validated = admit_registry_selection(
                        validated,
                        role=role,
                        sequence=sequence,
                        workflow_id=_text(validated.get("workflow_context"))
                        or GENERIC_MULTI_TU_WORKFLOW,
                        path=registry_path,
                    )
            except PlantComponentRegistryError as exc:
                raise MvpMultiTuPersistenceError(str(exc)) from exc
            if validated != _mapping(active_references.get(role)):
                raise MvpMultiTuPersistenceError(
                    "Saved component snapshot does not match the canonical runtime reference."
                )
            comparisons[unit_id][role] = compare_selection_to_current_registry(
                validated, path=registry_path
            )
    return comparisons


def _validate_genbank_component_qualifiers(
    record: Any, active: dict[str, Any]
) -> None:
    expected = {
        (_text(unit.get("unit_id")), role): selection_qualifiers(
            _mapping(_mapping(unit.get("component_references")).get(role))
        )
        for unit in list(active.get("expression_units") or [])
        for role in _traceable_roles(_mapping(unit))
    }
    observed: set[tuple[str, str]] = set()
    for feature in record.features:
        unit_id = _text((feature.qualifiers.get("unit_id") or [""])[0])
        role = _text((feature.qualifiers.get("biological_role") or [""])[0])
        qualifiers = expected.get((unit_id, role))
        if not qualifiers:
            continue
        observed.add((unit_id, role))
        mismatched = False
        for key, values in qualifiers.items():
            observed_values = [str(item) for item in feature.qualifiers.get(key, [])]
            if key in {
                "sequence_sha256",
                "resolution_id",
                "user_sequence_sha256",
                "source_record_sha256",
                "feature_sha256",
                "component_contract",
                "citation",
            }:
                if "".join(observed_values).replace(" ", "") != "".join(
                    str(item) for item in values
                ).replace(" ", ""):
                    mismatched = True
            elif observed_values != values:
                mismatched = True
        if mismatched:
            raise MvpMultiTuPersistenceError(
                "Saved Multi-TU GenBank component traceability does not match the component snapshot."
            )
    if observed != set(expected):
        raise MvpMultiTuPersistenceError(
            "Saved Multi-TU GenBank is missing component traceability features."
        )


def _snapshot_payload(
    result: dict[str, Any], *, registry_path: str | Path | None = None
) -> dict[str, Any]:
    project_type = _text(result.get("project_type"))
    if project_type not in SUPPORTED_PROJECT_TYPES:
        raise MvpMultiTuPersistenceError("Only multi_tu or dual_tu results can be saved by multi-TU persistence.")
    runtime = _mapping(result.get("runtime"))
    if _text(runtime.get("project_type")) != PROJECT_TYPE:
        raise MvpMultiTuPersistenceError("The saved runtime is not a multi_tu runtime.")
    if _text(runtime.get("multi_tu_schema_version")) != MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION:
        raise MvpMultiTuPersistenceError("The multi_tu runtime schema version is not supported.")
    original_input = _mapping(result.get("original_input"))
    if not list(original_input.get("expression_units") or []):
        raise MvpMultiTuPersistenceError("The multi_tu result does not contain original expression-unit inputs.")

    assembly_only = _is_assembly_result(result)
    real_case_id = _validated_real_case_id(result)
    real_case_claim = bool(real_case_id)
    try:
        active = (
            multi_tu_assembly_snapshot(runtime)
            if assembly_only
            else multi_tu_snapshot(runtime)
        )
    except MvpMultiTuRuntimeError as exc:
        raise MvpMultiTuPersistenceError(str(exc)) from exc
    if active["combined_construct"]["validation_status"] != "current":
        raise MvpMultiTuPersistenceError("A stale or blocking-invalid combined construct cannot be saved.")
    if not assembly_only and active["complete_plasmid"]["validation_status"] != "current":
        raise MvpMultiTuPersistenceError("A stale or blocking-invalid complete plasmid cannot be saved.")
    registry_comparisons = _validated_component_references(
        original_input, active, registry_path=registry_path
    )

    exports = _mapping(result.get("exports"))
    encoded_exports: dict[str, dict[str, Any]] = {}
    export_keys = ASSEMBLY_EXPORT_KEYS if assembly_only else COMPLETE_EXPORT_KEYS
    for export_key in export_keys:
        export_record = _mapping(exports.get(export_key))
        data = _text(export_record.get("data"))
        if not data:
            raise MvpMultiTuPersistenceError(f"The multi_tu result is missing {export_key} bytes.")
        encoded_exports[export_key] = {
            "label": _text(export_record.get("label")),
            "file_name": _text(export_record.get("file_name")),
            "mime": _text(export_record.get("mime")) or "text/plain",
            "data_b64": _encode_text(data),
            "sha256": _sha256_text(data),
        }
    unit_fastas = _mapping(exports.get("unit_fastas"))
    encoded_unit_fastas: dict[str, dict[str, Any]] = {}
    for unit in active["expression_units"]:
        unit_id = _text(unit.get("unit_id"))
        export_record = _mapping(unit_fastas.get(unit_id))
        data = _text(export_record.get("data"))
        if not data:
            raise MvpMultiTuPersistenceError(f"The multi_tu result is missing canonical FASTA bytes for {unit_id}.")
        encoded_unit_fastas[unit_id] = {
            "label": _text(export_record.get("label")),
            "file_name": _text(export_record.get("file_name")),
            "mime": _text(export_record.get("mime")) or "text/plain",
            "data_b64": _encode_text(data),
            "sha256": _sha256_text(data),
        }
    encoded_exports["unit_fastas"] = encoded_unit_fastas
    encoded_exports["metadata"] = copy.deepcopy(_mapping(exports.get("metadata")))

    try:
        combined_fasta = next(
            SeqIO.parse(StringIO(_text(exports["combined_construct_fasta"].get("data"))), "fasta")
        )
        if assembly_only:
            canonical_genbank = next(
                SeqIO.parse(StringIO(_text(exports["combined_construct_genbank"].get("data"))), "genbank")
            )
        else:
            complete_fasta = next(
                SeqIO.parse(StringIO(_text(exports["complete_plasmid_fasta"].get("data"))), "fasta")
            )
            complete_genbank = next(
                SeqIO.parse(StringIO(_text(exports["complete_plasmid_genbank"].get("data"))), "genbank")
            )
    except Exception as exc:
        raise MvpMultiTuPersistenceError("The multi_tu export bytes cannot be parsed for canonical verification.") from exc
    if str(combined_fasta.seq).upper() != _text(active["combined_construct"].get("dna")):
        raise MvpMultiTuPersistenceError("The multi-TU FASTA does not match the canonical combined sequence.")
    if assembly_only:
        if str(canonical_genbank.seq).upper() != _text(active["combined_construct"].get("dna")):
            raise MvpMultiTuPersistenceError("The multi-TU GenBank does not match the canonical combined sequence.")
        if not real_case_claim:
            _validate_genbank_component_qualifiers(canonical_genbank, active)
    else:
        complete_sequence = _text(active["complete_plasmid"].get("dna"))
        if str(complete_fasta.seq).upper() != complete_sequence:
            raise MvpMultiTuPersistenceError("The complete-plasmid FASTA does not match the canonical sequence.")
        if str(complete_genbank.seq).upper() != complete_sequence:
            raise MvpMultiTuPersistenceError("The complete-plasmid GenBank does not match the canonical sequence.")
    for unit in active["expression_units"]:
        unit_id = _text(unit.get("unit_id"))
        unit_fasta = next(SeqIO.parse(StringIO(_text(unit_fastas[unit_id].get("data"))), "fasta"))
        if str(unit_fasta.seq).upper() != _text(unit.get("dna")):
            raise MvpMultiTuPersistenceError(f"The {unit_id} FASTA does not match its canonical sequence.")

    project_id = _text(result.get("project_id"))
    project_name = _text(result.get("project_name"))
    if not project_id or not project_name:
        raise MvpMultiTuPersistenceError("project_id and project_name are required before saving.")
    snapshot = {
        "persistence_schema_version": MVP_MULTI_TU_PERSISTENCE_SCHEMA_VERSION,
        "project_schema_version": MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION,
        "project_type": project_type,
        "project_id": project_id,
        "project_name": project_name,
        "workflow_kind": (
            _formal_vector_workflow_id(_mapping(result.get("formal_project_context")))
            if _is_gate3_context(result)
            else _text(result.get("workflow_kind")) or GENERIC_MULTI_TU_WORKFLOW
        ),
        "result_kind": (
            MULTI_TU_EXPRESSION_ASSEMBLY
            if assembly_only
            else _text(result.get("result_kind")) or LEGACY_COMPLETE_VECTOR_RECORD
        ),
        "contains_vector": not assembly_only,
        "topology": "linear" if assembly_only else _text(result.get("topology")),
        "capability_limits": copy.deepcopy(
            _mapping(result.get("capability_limits"))
            or (ASSEMBLY_CAPABILITY_LIMITS if assembly_only else {})
        ),
        "current_step_state": int(result.get("current_step_state") or 6),
        "runtime_schema_version": MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION,
        "runtime_sha256": _sha256_text(_canonical_json(runtime)),
        "original_input": copy.deepcopy(original_input),
        "expression_units": copy.deepcopy(active["expression_units"]),
        "unit_input_signatures": {
            unit["unit_id"]: _text(unit.get("input_signature"))
            for unit in active["expression_units"]
        },
        "unit_order": list(active["unit_order"]),
        "combined_construct": copy.deepcopy(active["combined_construct"]),
        "combined_construct_input_signature": _text(active["combined_construct"].get("input_signature")),
        "complete_plasmid": copy.deepcopy(active.get("complete_plasmid") or {}),
        "complete_plasmid_input_signature": _text((active.get("complete_plasmid") or {}).get("input_signature")),
        "input_signature": _text(
            active["combined_construct"].get("input_signature")
            if assembly_only
            else active["complete_plasmid"].get("input_signature")
        ),
        "formal_project_context": copy.deepcopy(_mapping(result.get("formal_project_context"))),
        "registry_comparisons": registry_comparisons,
        "exports": encoded_exports,
    }
    if real_case_claim:
        snapshot.update(
            {
                "case_id": _text(result.get("case_id")),
                "case_verified": bool(result.get("case_verified")),
                "case_provenance": copy.deepcopy(_mapping(result.get("case_provenance"))),
                "case_snapshot": copy.deepcopy(_mapping(result.get("case_snapshot"))),
                "case_snapshot_sha256": _text(result.get("case_snapshot_sha256")),
            }
        )
    return snapshot


def _saved_payload(draft: PlantDesignProjectDraft) -> dict[str, Any]:
    state = _mapping(draft.manual_review_state)
    if MVP_SINGLE_GENE_PERSISTENCE_KEY in state and MVP_MULTI_TU_PERSISTENCE_KEY not in state:
        raise MvpMultiTuPersistenceError("The saved project is single_gene, not multi_tu.")
    payload = _mapping(state.get(MVP_MULTI_TU_PERSISTENCE_KEY))
    if not payload:
        raise MvpMultiTuPersistenceError("The saved project does not contain an MVP9 multi_tu record.")
    return payload


def _decoded_exports(payload: dict[str, Any]) -> dict[str, Any]:
    encoded_exports = _mapping(payload.get("exports"))
    exports: dict[str, Any] = {}
    export_keys = ASSEMBLY_EXPORT_KEYS if _is_assembly_result(payload) else COMPLETE_EXPORT_KEYS
    for export_key in export_keys:
        encoded = _mapping(encoded_exports.get(export_key))
        data = _decode_text(_text(encoded.get("data_b64")), label=export_key)
        if _sha256_text(data) != _text(encoded.get("sha256")):
            raise MvpMultiTuPersistenceError(f"Saved {export_key} checksum does not match its bytes.")
        exports[export_key] = {
            "label": _text(encoded.get("label")),
            "file_name": _text(encoded.get("file_name")),
            "mime": _text(encoded.get("mime")) or "text/plain",
            "data": data,
        }
    exports["metadata"] = copy.deepcopy(_mapping(encoded_exports.get("metadata")))
    encoded_unit_fastas = _mapping(encoded_exports.get("unit_fastas"))
    unit_fastas: dict[str, Any] = {}
    for unit_id, value in encoded_unit_fastas.items():
        encoded = _mapping(value)
        data = _decode_text(_text(encoded.get("data_b64")), label=f"{unit_id} FASTA")
        if _sha256_text(data) != _text(encoded.get("sha256")):
            raise MvpMultiTuPersistenceError(f"Saved {unit_id} FASTA checksum does not match its bytes.")
        unit_fastas[_text(unit_id)] = {
            "label": _text(encoded.get("label")),
            "file_name": _text(encoded.get("file_name")),
            "mime": _text(encoded.get("mime")) or "text/plain",
            "data": data,
        }
    exports["unit_fastas"] = unit_fastas
    return exports


def _validate_reopened_design(
    draft: PlantDesignProjectDraft, *, registry_path: str | Path | None = None
) -> dict[str, Any]:
    payload = _saved_payload(draft)
    real_case_id = _real_case_id(payload)
    real_case_claim = bool(real_case_id)
    if _text(payload.get("persistence_schema_version")) != MVP_MULTI_TU_PERSISTENCE_SCHEMA_VERSION:
        raise MvpMultiTuPersistenceError("The saved multi_tu persistence version is not supported.")
    if _text(payload.get("project_schema_version")) != MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION:
        raise MvpMultiTuPersistenceError("The saved multi_tu project version is not supported.")
    saved_project_type = _text(payload.get("project_type"))
    if saved_project_type not in SUPPORTED_PROJECT_TYPES:
        raise MvpMultiTuPersistenceError("The saved project type is not multi_tu or dual_tu.")
    if _text(payload.get("runtime_schema_version")) != MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION:
        raise MvpMultiTuPersistenceError("The saved multi_tu runtime version is not supported.")
    runtime = _mapping(draft.canonical_construct_runtime)
    if _text(runtime.get("project_type")) != PROJECT_TYPE:
        raise MvpMultiTuPersistenceError("The canonical runtime is not a multi_tu runtime.")
    if _sha256_text(_canonical_json(runtime)) != _text(payload.get("runtime_sha256")):
        raise MvpMultiTuPersistenceError("The saved multi_tu runtime checksum does not match its record.")
    assembly_only = _is_assembly_result(payload)
    try:
        active = (
            multi_tu_assembly_snapshot(runtime)
            if assembly_only
            else multi_tu_snapshot(runtime)
        )
    except MvpMultiTuRuntimeError as exc:
        raise MvpMultiTuPersistenceError(str(exc)) from exc
    if active["combined_construct"] != _mapping(payload.get("combined_construct")):
        raise MvpMultiTuPersistenceError("The saved combined construct does not match the canonical runtime.")
    if not assembly_only and active["complete_plasmid"] != _mapping(payload.get("complete_plasmid")):
        raise MvpMultiTuPersistenceError("The saved complete plasmid does not match the canonical runtime.")
    if list(active["unit_order"]) != list(payload.get("unit_order") or []):
        raise MvpMultiTuPersistenceError("The saved expression-unit order does not match the canonical runtime.")
    registry_comparisons = _validated_component_references(
        _mapping(payload.get("original_input")), active, registry_path=registry_path
    )

    exports = _decoded_exports(payload)
    if not _mapping(exports.get("unit_fastas")):
        fallback = (
            export_multi_tu_assembly_outputs(runtime, project_name=draft.project_name)
            if assembly_only
            else export_multi_tu_outputs(runtime, project_name=draft.project_name)
        )
        exports["unit_fastas"] = copy.deepcopy(fallback["unit_fastas"])
    if assembly_only:
        combined_fasta = next(
            SeqIO.parse(StringIO(exports["combined_construct_fasta"]["data"]), "fasta")
        )
        combined_genbank = next(
            SeqIO.parse(StringIO(exports["combined_construct_genbank"]["data"]), "genbank")
        )
        combined_sequence = _text(active["combined_construct"].get("dna"))
        if str(combined_fasta.seq).upper() != combined_sequence:
            raise MvpMultiTuPersistenceError("Saved multi-TU FASTA does not match the runtime sequence.")
        if str(combined_genbank.seq).upper() != combined_sequence:
            raise MvpMultiTuPersistenceError("Saved multi-TU GenBank does not match the runtime sequence.")
        if not real_case_claim:
            _validate_genbank_component_qualifiers(combined_genbank, active)
    else:
        complete_fasta = next(
            SeqIO.parse(StringIO(exports["complete_plasmid_fasta"]["data"]), "fasta")
        )
        complete_genbank = next(
            SeqIO.parse(StringIO(exports["complete_plasmid_genbank"]["data"]), "genbank")
        )
        complete_sequence = _text(active["complete_plasmid"].get("dna"))
        if str(complete_fasta.seq).upper() != complete_sequence:
            raise MvpMultiTuPersistenceError("Saved complete-plasmid FASTA does not match the runtime sequence.")
        if str(complete_genbank.seq).upper() != complete_sequence:
            raise MvpMultiTuPersistenceError("Saved complete-plasmid GenBank does not match the runtime sequence.")
    unit_fastas = _mapping(exports.get("unit_fastas"))
    for unit in active["expression_units"]:
        unit_id = _text(unit.get("unit_id"))
        export_record = _mapping(unit_fastas.get(unit_id))
        if not export_record:
            # Legacy dual-TU records predate per-unit FASTA persistence.
            continue
        unit_fasta = next(SeqIO.parse(StringIO(_text(export_record.get("data"))), "fasta"))
        if str(unit_fasta.seq).upper() != _text(unit.get("dna")):
            raise MvpMultiTuPersistenceError(f"Saved {unit_id} FASTA does not match the runtime sequence.")

    reopened = {
        "schema_version": MVP9_MULTI_TU_RUNTIME_SCHEMA_VERSION,
        "project_schema_version": MVP9_MULTI_TU_PROJECT_SCHEMA_VERSION,
        "project_type": saved_project_type,
        "project_id": draft.project_id,
        "project_name": draft.project_name,
        "workflow_kind": _text(payload.get("workflow_kind")) or GENERIC_MULTI_TU_WORKFLOW,
        "result_kind": _text(payload.get("result_kind")) or LEGACY_COMPLETE_VECTOR_RECORD,
        "contains_vector": bool(payload.get("contains_vector", not assembly_only)),
        "topology": _text(payload.get("topology")) or ("linear" if assembly_only else ""),
        "capability_limits": copy.deepcopy(_mapping(payload.get("capability_limits"))),
        "current_step_state": int(payload.get("current_step_state") or 6),
        "original_input": copy.deepcopy(_mapping(payload.get("original_input"))),
        "expression_units": copy.deepcopy(active["expression_units"]),
        "unit_input_signatures": {
            unit["unit_id"]: _text(unit.get("input_signature"))
            for unit in active["expression_units"]
        },
        "unit_order": list(active["unit_order"]),
        "combined_construct": copy.deepcopy(active["combined_construct"]),
        "complete_plasmid": copy.deepcopy(active.get("complete_plasmid") or {}),
        "input_signature": _text(
            active["combined_construct"].get("input_signature")
            if assembly_only
            else active["complete_plasmid"].get("input_signature")
        ),
        "formal_project_context": copy.deepcopy(_mapping(payload.get("formal_project_context"))),
        "registry_comparisons": registry_comparisons,
        "runtime": active["runtime"],
        "exports": exports,
    }
    if real_case_claim:
        reopened.update(
            {
                "case_id": _text(payload.get("case_id")),
                "case_verified": bool(payload.get("case_verified")),
                "case_provenance": copy.deepcopy(_mapping(payload.get("case_provenance"))),
                "case_snapshot": copy.deepcopy(_mapping(payload.get("case_snapshot"))),
                "case_snapshot_sha256": _text(payload.get("case_snapshot_sha256")),
            }
        )
    if assembly_only:
        reopened["vector_asset_admission"] = _assembly_vector_status()
    else:
        from services.vector_asset_admission import assess_legacy_project_vector

        reopened_original = _mapping(reopened.get("original_input"))
        reopened_context = _mapping(reopened.get("formal_project_context"))
        reopened_workflow = _formal_vector_workflow_id(reopened_context)
        reopened["vector_asset_admission"] = assess_legacy_project_vector(
            _mapping(reopened_original.get("backbone")),
            workflow_id=reopened_workflow,
            insertion_settings=_mapping(reopened_original.get("insertion_settings")),
        )
    if real_case_id == "MT-01":
        _validate_mt01_claim(reopened)
    elif real_case_id == "MT-02":
        _validate_mt02_claim(reopened)
    restore_reason = multi_tu_formal_editor_restore_reason(reopened)
    reopened["formal_editor_restore_reason"] = restore_reason
    reopened["formal_editor_restoration_eligible"] = not restore_reason
    return reopened


def save_mvp_multi_tu_design(
    result: dict[str, Any],
    *,
    repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository | None = None,
    registry_path: str | Path | None = None,
) -> PlantDesignProjectDraft:
    repo = repository or (
        PlantProjectDraftRepository()
        if _is_gate3_context(result) or not _is_assembly_result(result)
        else _default_multi_tu_repository()
    )
    snapshot = _snapshot_payload(result, registry_path=registry_path)
    original_input = _mapping(result.get("original_input"))
    formal_context = _mapping(result.get("formal_project_context"))
    if _is_assembly_result(snapshot):
        vector_asset_admission = _assembly_vector_status()
    else:
        from services.vector_asset_admission import assess_legacy_project_vector

        vector_workflow = _formal_vector_workflow_id(formal_context)
        vector_asset_admission = assess_legacy_project_vector(
            _mapping(original_input.get("backbone")),
            workflow_id=vector_workflow,
            insertion_settings=_mapping(original_input.get("insertion_settings")),
        )
    snapshot["vector_asset_admission"] = vector_asset_admission
    project_id = snapshot["project_id"]
    try:
        draft = repo.load(project_id)
        if MVP_SINGLE_GENE_PERSISTENCE_KEY in _mapping(draft.manual_review_state):
            raise MvpMultiTuPersistenceError("A single_gene project cannot be overwritten as multi_tu.")
        draft = update_plant_project_draft(
            draft,
            project_name=snapshot["project_name"],
            canonical_construct_runtime=_mapping(result.get("runtime")),
        )
    except PlantProjectDraftError:
        draft = PlantDesignProjectDraft.blank(project_name=snapshot["project_name"])
        draft.project_id = project_id
        draft = update_plant_project_draft(
            draft,
            project_name=snapshot["project_name"],
            canonical_construct_runtime=_mapping(result.get("runtime")),
        )
    state = _mapping(draft.manual_review_state)
    state.pop(MVP_SINGLE_GENE_PERSISTENCE_KEY, None)
    state[MVP_MULTI_TU_PERSISTENCE_KEY] = snapshot
    draft.manual_review_state = state
    context = _mapping(snapshot.get("formal_project_context"))
    workflow_type = (
        WORKFLOW_GATE3_PATHWAY
        if _text(context.get("design_scenario")) == "metabolic_pathway_multi_tu_vector"
        else WORKFLOW_MULTI_TU
    )
    if vector_asset_admission["completed_design_allowed"]:
        draft = mark_formal_project_completed(draft, workflow_type=workflow_type)
    try:
        saved = repo.save(draft)
        reopened_repo = _fresh_repository(repo)
        reopened = _validate_reopened_design(
            reopened_repo.load(saved.project_id), registry_path=registry_path
        )
        listed_ids = {
            summary.project_id for summary in reopened_repo.list_summaries()
        }
        if (
            _text(reopened.get("project_id")) != saved.project_id
            or _text(reopened.get("result_kind")) != _text(snapshot.get("result_kind"))
            or _text(_mapping(reopened.get("combined_construct")).get("sequence_sha256"))
            != _text(_mapping(snapshot.get("combined_construct")).get("sequence_sha256"))
            or saved.project_id not in listed_ids
        ):
            raise PlantProjectDraftError(
                "Saved Multi-TU project could not be verified after commit."
            )
        return saved
    except PlantProjectDraftError as exc:
        raise MvpMultiTuPersistenceError(str(exc)) from exc


def open_mvp_multi_tu_design(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository | None = None,
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    repositories = (
        [repository]
        if repository is not None
        else [_default_multi_tu_repository(), PlantProjectDraftRepository()]
    )
    for repo in repositories:
        try:
            draft = repo.load(project_id)
        except PlantProjectDraftError:
            continue
        try:
            require_active_project(draft)
        except PlantProjectDraftError as exc:
            raise MvpMultiTuPersistenceError(
                "The requested project lifecycle status does not allow editing or saving."
            ) from exc
        return _validate_reopened_design(draft, registry_path=registry_path)
    raise MvpMultiTuPersistenceError("The requested multi_tu project could not be read.")


def list_mvp_multi_tu_designs(
    *,
    repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository | None = None,
) -> list[PlantProjectDraftSummary]:
    repositories = (
        [repository]
        if repository is not None
        else [_default_multi_tu_repository(), PlantProjectDraftRepository()]
    )
    summaries_by_id: dict[str, PlantProjectDraftSummary] = {}
    for repo in repositories:
        try:
            candidates = repo.list_summaries()
        except PlantProjectDraftError:
            continue
        for summary in candidates:
            if summary.project_id in summaries_by_id:
                continue
            try:
                draft = repo.load(summary.project_id)
                _saved_payload(draft)
            except (PlantProjectDraftError, MvpMultiTuPersistenceError):
                continue
            summaries_by_id[summary.project_id] = summary
    return sorted(
        summaries_by_id.values(),
        key=lambda summary: (summary.updated_at, summary.project_id),
        reverse=True,
    )


def delete_mvp_multi_tu_design(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository | None = None,
) -> None:
    repositories = (
        [repository]
        if repository is not None
        else [_default_multi_tu_repository(), PlantProjectDraftRepository()]
    )
    for repo in repositories:
        try:
            draft = repo.load(project_id)
            _saved_payload(draft)
            repo.delete(project_id)
            return
        except (PlantProjectDraftError, MvpMultiTuPersistenceError):
            continue
    raise MvpMultiTuPersistenceError("The requested multi_tu project could not be deleted.")
