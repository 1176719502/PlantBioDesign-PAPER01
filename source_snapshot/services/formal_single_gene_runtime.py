"""Formal single-gene runtime helpers shared with the compatibility entry."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO

from core.pcambia1300_exact_insertion_contract import (
    Pcambia1300ExactInsertionContractError,
    exact_insertion_contract,
    fixed_insertion_settings,
    is_pcambia1300_record,
    sequence_sha256 as pcambia_sequence_sha256,
    validate_pcambia1300_operation,
)
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    create_component,
    create_insertion_site,
    create_sequence_asset,
    export_active_complete_plasmid,
    generate_active_complete_plasmid,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_insertion_site,
    upsert_sequence_asset,
)
from services.mvp_cds_input import analyze_cds_input
from services.mvp_company_review_package import build_company_review_package
from services.mvp_sequence_input import analyze_dna_component_input, analyze_genbank_backbone_input
from services.plant_project_draft_schema import new_project_id


CASE_DIRECTORY = Path(__file__).resolve().parent.parent / "examples" / "plant_single_gene_mvp"
CASE_FILES = {
    "promoter": "r229_promoter.fasta",
    "cds": "r229_cds.fasta",
    "terminator": "r229_terminator.fasta",
    "backbone": "r229_backbone.gb",
}
COMPONENT_NAMES = {
    "promoter": "PROMOTER_COMPONENT_R229",
    "cds": "CDS_COMPONENT_R229",
    "terminator": "TERMINATOR_COMPONENT_R229",
}
DEFAULT_PROJECT_NAME = "Plant single-gene MVP"


def _sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def load_real_case() -> dict[str, str]:
    """Read the fixed, real-scale local fixture without modifying it."""
    return {
        role: (CASE_DIRECTORY / filename).read_text(encoding="utf-8")
        for role, filename in CASE_FILES.items()
    }


def real_case_cds_input(case: dict[str, str] | None = None) -> dict[str, Any]:
    fixture = case or load_real_case()
    return analyze_cds_input(
        fixture["cds"],
        source_kind="example",
        source_name=CASE_FILES["cds"],
    )


def _runtime_cds_findings(cassette: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": str(item.get("rule_id") or ""),
            "message": str(item.get("explanation") or ""),
            "blocking": bool(item.get("blocking")),
        }
        for item in list(cassette.get("validation_findings") or [])
        if str(item.get("rule_id") or "").startswith("cds_")
        or str(item.get("rule_id") or "") == "internal_in_frame_stop_codon"
    ]


def _component_record_from_example(role: str, *, project_id: str, case: dict[str, str]) -> dict[str, Any]:
    return analyze_dna_component_input(
        case[role],
        project_id=project_id,
        component_type=role,
        display_name=COMPONENT_NAMES[role],
        source_kind="example",
        source_name=CASE_FILES[role],
    )


def _backbone_record_from_example(*, project_id: str, case: dict[str, str]) -> dict[str, Any]:
    return analyze_genbank_backbone_input(
        case["backbone"],
        project_id=project_id,
        display_name="BACKBONE_SYNTH_R229",
        source_kind="example",
        source_name=CASE_FILES["backbone"],
    )


def _cds_record(cds_input: dict[str, Any], *, display_name: str) -> dict[str, Any]:
    return {
        "role": "cds",
        "source_kind": str(cds_input.get("source_kind") or ""),
        "source_name": str(cds_input.get("source_name") or ""),
        "source_format": str(cds_input.get("source_format") or "plain"),
        "display_name": display_name,
        "original_text": str(cds_input.get("original_text") or ""),
        "normalized_sequence": str(cds_input.get("normalized_cds") or ""),
        "length": int(cds_input.get("normalized_length") or 0),
    }


def _signature_record(record: dict[str, Any]) -> dict[str, Any]:
    stable_features = [
        {key: value for key, value in dict(feature).items() if key != "feature_id"}
        for feature in list(record.get("imported_feature_records") or [])
    ]
    return {
        "role": str(record.get("role") or ""),
        "source_kind": str(record.get("source_kind") or ""),
        "source_name": str(record.get("source_name") or ""),
        "source_format": str(record.get("source_format") or ""),
        "display_name": str(record.get("display_name") or ""),
        "original_text_sha256": _sha256(str(record.get("original_text") or "")),
        "normalized_sequence": str(record.get("normalized_sequence") or ""),
        "topology": str(record.get("topology") or ""),
        "original_record_identifier": str(record.get("original_record_identifier") or ""),
        "imported_feature_records": stable_features,
        "source_accession_version": str(record.get("source_accession_version") or ""),
        "source_record_name": str(record.get("source_record_name") or ""),
        "source_definition": str(record.get("source_definition") or ""),
        "source_location": str(record.get("source_location") or ""),
        "source_strand": int(record.get("source_strand") or 0),
        "source_record_length": int(record.get("source_record_length") or 0),
        "source_file_name": str(record.get("source_file_name") or ""),
        "source_file_sha256": str(record.get("source_file_sha256") or ""),
        "extracted_sequence_sha256": str(record.get("extracted_sequence_sha256") or ""),
        "source_mrna_sha256": str(record.get("source_mrna_sha256") or ""),
        "error": str(record.get("error") or ""),
    }


def cassette_input_signature(input_records: dict[str, dict[str, Any]]) -> str:
    """Hash only the ordered canonical expression-cassette inputs."""
    payload = {
        "components": {
            role: _signature_record(dict(input_records.get(role) or {}))
            for role in ("promoter", "cds", "terminator")
        },
        "component_order": ["promoter", "cds", "terminator"],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(encoded)


def construct_input_signature(
    input_records: dict[str, dict[str, Any]],
    insertion_settings: dict[str, Any],
    *,
    cassette_signature: str | None = None,
) -> str:
    """Hash the active cassette plus the backbone insertion inputs only."""
    backbone = dict(input_records.get("backbone") or {})
    operation = {
        "mode": str(insertion_settings.get("mode") or ""),
        "start_coordinate": int(insertion_settings.get("start_coordinate") or 0),
        "end_coordinate": int(insertion_settings.get("end_coordinate") or 0),
        "expected_removed_sequence": str(insertion_settings.get("expected_removed_sequence") or "").upper(),
        "insertion_orientation": str(insertion_settings.get("insertion_orientation") or "forward"),
        "topology": str(backbone.get("topology") or ""),
        "t_dna_confirmation_signature": str(
            (insertion_settings.get("t_dna_confirmation") or {}).get("confirmation_signature") or ""
        ),
    }
    if str(insertion_settings.get("workflow_id") or ""):
        operation["workflow_id"] = str(insertion_settings["workflow_id"])
    if str(insertion_settings.get("exact_insertion_contract_version") or ""):
        operation["exact_insertion_contract_version"] = str(
            insertion_settings["exact_insertion_contract_version"]
        )
    payload = {
        "cassette_input_signature": str(cassette_signature or cassette_input_signature(input_records)),
        "backbone": {
            "original_text_sha256": _sha256(str(backbone.get("original_text") or "")),
            "source_file_sha256": str(backbone.get("source_file_sha256") or ""),
        },
        "operation": operation,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(encoded)


def generation_input_signature(
    input_records: dict[str, dict[str, Any]],
    insertion_settings: dict[str, Any],
    *,
    project_name: str,
) -> str:
    """Compatibility alias for the complete-plasmid construct signature."""
    del project_name
    return construct_input_signature(input_records, insertion_settings)


def _runtime_error_message(plasmid: dict[str, Any]) -> str:
    rule_ids = {
        str(item.get("rule_id") or "")
        for item in plasmid.get("validation_findings") or []
        if item.get("blocking")
    }
    if rule_ids & {
        "invalid_insertion_coordinate",
        "insertion_interval_outside_backbone_bounds",
        "replacement_end_before_start",
    }:
        return "插入或替换坐标无效，请按骨架长度检查设置。"
    if "overlapping_backbone_feature_conflict" in rule_ids:
        return "所选位置与骨架原有 feature 重叠，请调整坐标。"
    if "backbone_topology_requires_confirmation" in rule_ids:
        return "骨架未声明拓扑；请确认按环状骨架处理。"
    if "pcambia1300_exact_insertion_contract_mismatch" in rule_ids:
        details = [
            str(item.get("explanation") or "")
            for item in plasmid.get("validation_findings") or []
            if str(item.get("rule_id") or "") == "pcambia1300_exact_insertion_contract_mismatch"
        ]
        return details[0] if details else "AF234296.1 来源或固定精确插入合同不一致，不能生成完整载体构建设计。"
    return "当前输入未通过完整质粒校验；阻断规则：" + ", ".join(sorted(rule_ids))


def _prepare_expression_inputs(
    case: dict[str, str] | None = None,
    *,
    cds_input: dict[str, Any] | None = None,
    input_records: dict[str, dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> tuple[str, dict[str, str], dict[str, Any], dict[str, dict[str, Any]]]:
    resolved_project_id = str(project_id or new_project_id())
    records = dict(input_records or {})
    requires_fixture = cds_input is None or any(
        role not in records for role in ("promoter", "cds", "terminator", "backbone")
    )
    fixture = case or (load_real_case() if requires_fixture else {})
    resolved_cds_input = dict(cds_input or real_case_cds_input(fixture))
    if bool(resolved_cds_input.get("blocking")) or not str(resolved_cds_input.get("normalized_cds") or ""):
        raise RuntimeError("CDS 输入未通过校验。")
    if "promoter" not in records:
        records["promoter"] = _component_record_from_example(
            "promoter", project_id=resolved_project_id, case=fixture
        )
    if "cds" not in records:
        records["cds"] = _cds_record(
            resolved_cds_input, display_name=COMPONENT_NAMES["cds"]
        )
    if "terminator" not in records:
        records["terminator"] = _component_record_from_example(
            "terminator", project_id=resolved_project_id, case=fixture
        )
    if "backbone" not in records:
        records["backbone"] = _backbone_record_from_example(
            project_id=resolved_project_id, case=fixture
        )
    return resolved_project_id, fixture, resolved_cds_input, records


def _build_expression_cassette_runtime(
    *,
    project_id: str,
    records: dict[str, dict[str, Any]],
    cds_input: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int], dict[str, Any]]:
    runtime: dict[str, Any] = {"project_id": project_id}
    component_ids: list[str] = []
    input_lengths: dict[str, int] = {}

    for component_type in ("promoter", "cds", "terminator"):
        record = dict(records[component_type])
        if not str(record.get("normalized_sequence") or ""):
            raise RuntimeError(f"{component_type} 输入为空。")
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=str(record.get("display_name") or COMPONENT_NAMES[component_type]),
            raw_text=str(record["normalized_sequence"]),
            molecule_type="dna",
            source_type=str(record.get("source_kind") or "paste"),
            source_format="plain",
            source_name=str(record.get("source_name") or ""),
            source_description=str(record.get("source_definition") or record.get("source_rationale") or ""),
            provenance_reference=str(record.get("source_reference") or record.get("source_location") or ""),
            source_file_checksum=str(record.get("source_file_sha256") or "")
            or _sha256(str(record.get("original_text") or "")),
            asset_role="construct_component",
        )
        input_lengths[component_type] = int(asset["length"])
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id=project_id,
            component_type=component_type,
            display_name=str(record.get("display_name") or COMPONENT_NAMES[component_type]),
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        component_ids.append(component["component_id"])

    runtime = set_active_component_order(runtime, component_ids)
    runtime = generate_active_construct(runtime)
    cassette = active_construct_snapshot(runtime)
    resolved_cds_input = dict(cds_input)
    resolved_cds_input["runtime_findings"] = _runtime_cds_findings(cassette)
    if int(cassette["validation_summary"].get("blocking_count", 0)):
        raise RuntimeError("CDS 输入未通过表达盒校验。")
    return runtime, cassette, input_lengths, resolved_cds_input


def generate_expression_cassette(
    case: dict[str, str] | None = None,
    *,
    cds_input: dict[str, Any] | None = None,
    input_records: dict[str, dict[str, Any]] | None = None,
    project_id: str | None = None,
    project_name: str = DEFAULT_PROJECT_NAME,
    input_signature: str = "",
) -> dict[str, Any]:
    """Generate the expression cassette through the existing R227 runtime."""
    resolved_project_id, _fixture, resolved_cds_input, records = _prepare_expression_inputs(
        case,
        cds_input=cds_input,
        input_records=input_records,
        project_id=project_id,
    )
    runtime, cassette, input_lengths, resolved_cds_input = _build_expression_cassette_runtime(
        project_id=resolved_project_id,
        records=records,
        cds_input=resolved_cds_input,
    )
    resolved_project_name = str(project_name or DEFAULT_PROJECT_NAME).strip() or DEFAULT_PROJECT_NAME
    resolved_signature = input_signature or cassette_input_signature(records)
    return {
        "project_id": resolved_project_id,
        "project_name": resolved_project_name,
        "runtime": runtime,
        "input_records": records,
        "cds_input": resolved_cds_input,
        "input_lengths": input_lengths,
        "cassette_length": int(cassette["sequence_length"]),
        "validation_summary": dict(cassette.get("validation_summary") or {}),
        "input_signature": resolved_signature,
        "cassette_input_signature": resolved_signature,
    }


def generate_complete_vector(
    case: dict[str, str] | None = None,
    *,
    cds_input: dict[str, Any] | None = None,
    input_records: dict[str, dict[str, Any]] | None = None,
    insertion_settings: dict[str, Any] | None = None,
    project_id: str | None = None,
    project_name: str = DEFAULT_PROJECT_NAME,
    input_signature: str = "",
    cassette_runtime: dict[str, Any] | None = None,
    cassette_signature: str = "",
    workflow_id: str = "formal_single_gene",
) -> dict[str, Any]:
    """Compose the existing R227 cassette and R228 complete-plasmid APIs."""
    resolved_project_id, _fixture, resolved_cds_input, records = _prepare_expression_inputs(
        case,
        cds_input=cds_input,
        input_records=input_records,
        project_id=project_id,
    )
    resolved_project_name = str(project_name or DEFAULT_PROJECT_NAME).strip() or DEFAULT_PROJECT_NAME
    requested_settings = {
        "mode": "insertion",
        "start_coordinate": 2100,
        "end_coordinate": 2101,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
        **dict(insertion_settings or {}),
    }
    backbone_record = dict(records["backbone"])
    pcambia_contract: dict[str, Any] = {}
    if is_pcambia1300_record(backbone_record):
        from services.vector_asset_admission import require_vector_operation

        vector_asset_admission = require_vector_operation(
            backbone_record,
            workflow_id=workflow_id,
            insertion_settings=requested_settings,
        )
        accession_version = str(
            backbone_record.get("source_accession_version")
            or backbone_record.get("original_record_identifier")
            or backbone_record.get("source_name")
            or ""
        )
        try:
            pcambia_contract = validate_pcambia1300_operation(
                source_sequence=str(backbone_record.get("normalized_sequence") or ""),
                accession_version=accession_version,
                circular=str(backbone_record.get("topology") or "").lower() == "circular",
                mode=str(requested_settings.get("mode") or ""),
                start_coordinate=int(requested_settings.get("start_coordinate") or 0),
                end_coordinate=int(requested_settings.get("end_coordinate") or 0),
                insertion_orientation=str(requested_settings.get("insertion_orientation") or "forward"),
                workflow_id=workflow_id,
            )
        except Pcambia1300ExactInsertionContractError as exc:
            raise RuntimeError(str(exc)) from exc
        settings = fixed_insertion_settings()
        settings["workflow_id"] = "rice_alb_single_gene"
    else:
        settings = requested_settings
    if cassette_runtime is None:
        runtime, cassette, input_lengths, resolved_cds_input = _build_expression_cassette_runtime(
            project_id=resolved_project_id,
            records=records,
            cds_input=resolved_cds_input,
        )
    else:
        runtime = deepcopy(cassette_runtime)
        cassette = active_construct_snapshot(runtime)
        if str(cassette.get("construct_status") or "") != "current" or not str(cassette.get("sequence") or ""):
            raise RuntimeError("The saved canonical cassette is not current.")
        input_lengths = {role: int(records[role].get("length") or 0) for role in ("promoter", "cds", "terminator")}

    backbone = create_sequence_asset(
        project_id=resolved_project_id,
        display_name=str(backbone_record.get("display_name") or "Backbone"),
        raw_text=str(backbone_record.get("original_text") or ""),
        molecule_type="dna",
        source_type=str(backbone_record.get("source_kind") or "upload"),
        source_format="genbank",
        source_name=str(backbone_record.get("source_name") or ""),
        source_description=str(backbone_record.get("source_definition") or backbone_record.get("source_rationale") or ""),
        provenance_reference=str(backbone_record.get("source_reference") or backbone_record.get("source_location") or ""),
        source_file_checksum=str(backbone_record.get("source_file_sha256") or "")
        or _sha256(str(backbone_record.get("original_text") or "")),
        asset_role="backbone",
    )
    input_lengths["backbone"] = int(backbone["length"])
    runtime = upsert_sequence_asset(runtime, backbone)
    insertion_site = create_insertion_site(
        project_id=resolved_project_id,
        backbone_asset_id=backbone["asset_id"],
        start_coordinate=int(settings["start_coordinate"]),
        end_coordinate=int(settings["end_coordinate"]),
        mode=str(settings["mode"]),
        expected_removed_sequence=str(settings.get("expected_removed_sequence") or ""),
        insertion_orientation=str(settings.get("insertion_orientation") or "forward"),
        user_confirmation=True,
        topology_confirmation=bool(settings.get("topology_confirmation")),
    )
    if pcambia_contract:
        insertion_site["workflow_id"] = "rice_alb_single_gene"
        insertion_site["exact_insertion_contract"] = exact_insertion_contract()
        insertion_site["exact_insertion_contract_version"] = pcambia_contract["contract_version"]
    runtime = upsert_insertion_site(runtime, insertion_site)
    runtime = generate_active_complete_plasmid(runtime)
    plasmid = active_complete_plasmid_snapshot(runtime)
    if int(plasmid["validation_summary"].get("blocking_count", 0)):
        raise RuntimeError(_runtime_error_message(plasmid))

    exports = export_active_complete_plasmid(runtime, project_name=resolved_project_name)
    fasta_records = list(SeqIO.parse(StringIO(exports["fasta"]["data"]), "fasta"))
    genbank_records = list(SeqIO.parse(StringIO(exports["genbank"]["data"]), "genbank"))
    if len(fasta_records) != 1 or len(genbank_records) != 1:
        raise RuntimeError("Export reparse did not yield exactly one record per format.")
    final_sequence = str(plasmid["sequence"])
    fasta_sequence = str(fasta_records[0].seq).upper()
    genbank_sequence = str(genbank_records[0].seq).upper()
    if fasta_sequence != final_sequence or genbank_sequence != final_sequence:
        raise RuntimeError("导出序列与完整质粒不一致。")
    if str(genbank_records[0].annotations.get("topology", "")).lower() != str(plasmid.get("topology") or "").lower():
        raise RuntimeError("Export GenBank topology does not match the canonical complete plasmid.")

    resolved_cassette_signature = str(cassette_signature or cassette_input_signature(records))
    resolved_signature = input_signature or construct_input_signature(
        records,
        settings,
        cassette_signature=resolved_cassette_signature,
    )
    result = {
        "project_id": resolved_project_id,
        "project_name": resolved_project_name,
        "input_lengths": input_lengths,
        "cassette_length": int(cassette["sequence_length"]),
        "plasmid_length": int(plasmid["sequence_length"]),
        "plasmid_sha256": _sha256(final_sequence),
        "fasta_sequence_sha256": _sha256(fasta_sequence),
        "genbank_sequence_sha256": _sha256(genbank_sequence),
        "runtime": runtime,
        "source_inputs": {
            role: str(records[role].get("original_text") or "")
            for role in ("promoter", "cds", "terminator", "backbone")
        },
        "input_records": records,
        "cds_input": resolved_cds_input,
        "insertion_settings": settings,
        "validation_summary": dict(plasmid.get("validation_summary") or {}),
        "input_signature": resolved_signature,
        "construct_input_signature": resolved_signature,
        "cassette_input_signature": resolved_cassette_signature,
        "exports": exports,
    }
    if pcambia_contract:
        cassette_sequence = str(cassette.get("sequence") or "").upper()
        source_sequence = str(backbone_record.get("normalized_sequence") or "").upper()
        shift = len(cassette_sequence)
        feature_rows = list(plasmid.get("feature_rows") or [])
        result["exact_insertion_contract"] = exact_insertion_contract()
        result["exact_insertion_record"] = {
            "asset_id": pcambia_contract["asset_id"],
            "asset_kind": pcambia_contract["asset_kind"],
            "accession_version": pcambia_contract["accession_version"],
            "exact_insertion_contract_version": pcambia_contract["contract_version"],
            "internal_cut_index": pcambia_contract["internal_cut_index"],
            "source_hash": pcambia_sequence_sha256(source_sequence),
            "cassette_hash": pcambia_sequence_sha256(cassette_sequence),
            "output_sequence_hash": pcambia_sequence_sha256(final_sequence),
            "workflow_support_status": "supported_rice_alb_single_gene",
        }
        result["pcambia1300_validation"] = {
            "output_length_formula": len(final_sequence) == 8958 + len(cassette_sequence),
            "all_source_bases_retained": final_sequence[:27]
            + final_sequence[27 + len(cassette_sequence) :]
            == source_sequence,
            "right_border_retained": final_sequence[297 + shift : 323 + shift]
            == source_sequence[297:323],
            "left_border_retained": final_sequence[6556 + shift : 6582 + shift]
            == source_sequence[6556:6582],
            "hptii_cassette_retained": final_sequence[6648 + shift : 8714 + shift]
            == source_sequence[6648:8714],
            "mcs_superseded": any(
                "MCS / polylinker (superseded" in str(row.get("name") or "")
                for row in feature_rows
            ),
            "lacz_interrupted": any(
                "lacz alpha" in str(row.get("name") or "").lower()
                and "interrupted" in str(row.get("name") or "").lower()
                for row in feature_rows
            ),
            "legacy_219_220_absent": (
                int(settings.get("start_coordinate") or 0),
                int(settings.get("end_coordinate") or 0),
            )
            != (219, 220),
        }
        if not all(result["pcambia1300_validation"].values()):
            failed = [
                key for key, passed in result["pcambia1300_validation"].items() if not passed
            ]
            raise RuntimeError(
                "AF234296.1 exact-insertion output failed required preservation checks: "
                + ", ".join(failed)
            )
        result["vector_asset_admission"] = vector_asset_admission
    else:
        from services.vector_asset_admission import validate_vector_operation

        result["vector_asset_admission"] = validate_vector_operation(
            backbone_record,
            workflow_id=workflow_id,
            insertion_settings=settings,
        )
    result["company_review_package"] = build_company_review_package(result)
    return result


def generate_admitted_complete_vector(
    *,
    input_records: dict[str, dict[str, Any]],
    insertion_settings: dict[str, Any],
    workflow_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate through the formal service only after contract admission."""
    from services.vector_asset_admission import require_vector_operation

    records = dict(input_records or {})
    require_vector_operation(
        dict(records.get("backbone") or {}),
        workflow_id=workflow_id,
        insertion_settings=insertion_settings,
    )
    return generate_complete_vector(
        input_records=records,
        insertion_settings=insertion_settings,
        workflow_id=workflow_id,
        **kwargs,
    )
