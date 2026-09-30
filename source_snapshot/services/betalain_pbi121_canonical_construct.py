"""Gate 3 adapter for the reviewed betalain three-TU pBI121 replacement case.

This module only composes verified local records through the public multi-TU
runtime.  It does not change the immutable source assets, the replacement
strategy, or canonical runtime behavior.
"""
from __future__ import annotations

import copy
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO

from core.pbi121_replacement_contract import (
    Pbi121ReplacementContractError,
    replacement_contract,
    replace_pbi121_reporter_cassette,
    validate_pbi121_operation,
)
from services.betalain_three_enzyme_gate3_case import (
    apply_betalain_case_to_units,
    load_betalain_three_enzyme_case,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_construct
from services.pbi121_replacement_strategy import Pbi121ReplacementStrategyError, load_strategy
from services.real_genbank_asset_import import (
    PBI121_SOURCE_RECORD,
    build_pbi121_asset_bundle,
)


ADAPTER_SCHEMA_VERSION = "betalain-pbi121-canonical-construct-v1"
REPEATED_REGULATORY_WARNING = (
    "Multiple transcription units use the same regulatory sequence; repeated homologous regions require professional review."
)
BOUNDARY_COPY = (
    "当前结果用于植物表达载体的计算设计、计算校验、项目保存和文件导出；尚未经过湿实验验证，不代表实际表达成功或湿实验就绪。"
)


class BetalainPbi121CanonicalConstructError(ValueError):
    """Raised when the verified Gate 3 construct cannot be generated."""


def _sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.upper().encode("ascii")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _registered_components() -> dict[str, dict[str, Any]]:
    bundle = build_pbi121_asset_bundle()
    required_types = {"promoter", "three_prime_regulatory_region"}
    components = {
        _text(component.get("asset_type")): dict(component)
        for component in bundle["components"]
        if _text(component.get("asset_type")) in required_types
    }
    if set(components) != required_types:
        raise BetalainPbi121CanonicalConstructError(
            "The bundled pBI121 audit does not contain both a verified promoter and a verified 3' regulatory region."
        )
    for asset_type, component in components.items():
        required = {
            "exact_sequence",
            "source_accession",
            "source_record_sha256",
            "sequence_sha256",
            "biological_role",
            "provenance_status",
            "verification_status",
            "source_feature_location",
            "strand",
        }
        if not required <= set(component) or not _text(component.get("exact_sequence")):
            raise BetalainPbi121CanonicalConstructError(f"The pBI121 {asset_type} asset has incomplete provenance.")
        if component["provenance_status"] != "verified_source" or component["verification_status"] != "source_feature_parsed":
            raise BetalainPbi121CanonicalConstructError(f"The pBI121 {asset_type} asset is not verified for construct use.")
        if _sha256(component["exact_sequence"]) != component["sequence_sha256"]:
            raise BetalainPbi121CanonicalConstructError(f"The pBI121 {asset_type} sequence SHA-256 does not match its asset record.")
    return components


def _strategy_gate(strategy_root: Path | None) -> tuple[dict[str, Any], list[str]]:
    try:
        strategy = load_strategy(runtime_root=strategy_root)
    except Pbi121ReplacementStrategyError as exc:
        return {}, [str(exc)]
    audit = build_pbi121_asset_bundle()["audit"]
    contract = replacement_contract()
    blockers: list[str] = []
    if strategy.get("source_accession") != audit["accession"]:
        blockers.append("The saved replacement strategy source accession does not match pBI121.")
    if strategy.get("source_record_sha256") != audit["source_record_sha256"]:
        blockers.append("The saved replacement strategy source record SHA-256 does not match pBI121.")
    if strategy.get("strategy_status") != "ready_for_construct_use":
        blockers.append("The saved pBI121 replacement strategy is not ready for construct use.")
    if (int(strategy.get("replacement_start") or 0), int(strategy.get("replacement_end") or 0)) != (4974, 7979):
        blockers.append("The saved pBI121 replacement interval is not 4974..7979 (1-based inclusive).")
    if strategy.get("t_dna_direction") != "RB_to_LB" or strategy.get("insertion_orientation") != "forward":
        blockers.append("The saved pBI121 T-DNA direction or insertion orientation differs from the reviewed strategy.")
    if list(strategy.get("partially_overlapped_feature_ids") or []):
        blockers.append("The saved replacement strategy contains partially overlapped source features.")
    if not all(bool((strategy.get("reviewed_key_features") or {}).get(key)) for key in ("gus", "nptii")):
        blockers.append("The saved GUS and NPTII feature reviews are incomplete.")
    if strategy.get("replacement_contract") != contract:
        blockers.append("The saved pBI121 replacement contract differs from the fixed AF485783.1 contract.")
    try:
        validate_pbi121_operation(
            source_sequence=audit["sequence"],
            accession_version=strategy.get("source_accession") or "",
            mode=strategy.get("replacement_mode") or "",
            replacement_start=int(strategy.get("replacement_start") or 0),
            replacement_end=int(strategy.get("replacement_end") or 0),
        )
    except Pbi121ReplacementContractError as exc:
        blockers.append(str(exc))
    return strategy, blockers


def evaluate_betalain_pbi121_prerequisites(
    *,
    repeated_regulatory_confirmed: bool,
    strategy_root: Path | None = None,
) -> dict[str, Any]:
    """Return all construct gates without generating a sequence."""
    blockers: list[str] = []
    information: list[str] = []
    warnings: list[str] = []
    case = load_betalain_three_enzyme_case()
    components = _registered_components()
    strategy, strategy_blockers = _strategy_gate(strategy_root)
    blockers.extend(strategy_blockers)
    if not repeated_regulatory_confirmed:
        blockers.append("Explicit confirmation is required before reusing the same promoter and 3' regulatory region across TU1, TU2, and TU3.")
    else:
        warnings.append(REPEATED_REGULATORY_WARNING)
    information.append(BOUNDARY_COPY)
    information.append("wet_lab_readiness: not_assessed")
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "blockers": blockers,
        "warnings": warnings,
        "information": information,
        "component_provenance_summary": {
            "promoter": copy.deepcopy(components["promoter"]),
            "three_prime_regulatory_region": copy.deepcopy(components["three_prime_regulatory_region"]),
            "cds_records": [
                {
                    key: record[key]
                    for key in (
                        "gene", "version", "cds_coordinates", "strand", "cds_length",
                        "cds_sha256", "source_record_sha256", "verification_status",
                    )
                }
                for record in case["cds_records"]
            ],
        },
        "replacement_strategy_summary": {
            key: copy.deepcopy(strategy.get(key))
            for key in (
                "source_accession", "source_record_sha256", "strategy_id", "strategy_status",
                "t_dna_direction", "replacement_start", "replacement_end", "insertion_orientation",
            )
        },
        "retained_removed_feature_summary": {
            "retained_feature_ids": list(strategy.get("retained_feature_ids") or []),
            "removed_feature_ids": list(strategy.get("removed_feature_ids") or []),
            "partially_overlapped_feature_ids": list(strategy.get("partially_overlapped_feature_ids") or []),
        },
        "wet_lab_readiness": "not_assessed",
        "repeated_regulatory_confirmed": bool(repeated_regulatory_confirmed),
    }


def _component_input(component: dict[str, Any]) -> dict[str, str]:
    return {
        "display_name": _text(component["biological_role"]),
        "raw_text": _text(component["exact_sequence"]),
        "source_type": "official_ncbi_genbank",
        "source_format": "plain",
        "source_name": _text(component["source_accession"]),
        "source_description": _text(component["source_feature_location"]),
        "provenance_reference": (
            f"{component['source_accession']} {component['source_feature_location']}; "
            f"source_record_sha256={component['source_record_sha256']}; sequence_sha256={component['sequence_sha256']}"
        ),
    }


def _expression_units(case: dict[str, Any], components: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for order, record in enumerate(case["cds_records"], start=1):
        units.append(
            {
                "unit_id": f"TU{order}",
                "display_name": f"TU{order}: {record['gene']}",
                "orientation": "forward",
                "order": order,
                "promoter": _component_input(components["promoter"]),
                "cds": {
                    "display_name": record["gene"],
                    "raw_text": record["cds_sequence"],
                    "source_type": "official_ncbi_genbank",
                    "source_format": "plain",
                    "source_name": record["version"],
                    "source_description": record["cds_coordinates"],
                    "provenance_reference": (
                        f"{record['version']} {record['cds_coordinates']}; "
                        f"source_record_sha256={record['source_record_sha256']}; cds_sha256={record['cds_sha256']}"
                    ),
                },
                "3_prime_regulatory_region": _component_input(components["three_prime_regulatory_region"]),
                "validation_state": "current",
                "provenance_state": "verified_source",
            }
        )
    return units


def _runtime_backbone_genbank(strategy: dict[str, Any]) -> str:
    """Provide the public runtime only the source features retained by the strategy.

    The runtime correctly refuses to remap a feature that overlaps a replacement
    interval.  The saved strategy has already classified such features as
    removed, so this derived GenBank view retains source provenance while
    preventing invalid annotations from reaching the remapping contract.
    """
    source = next(SeqIO.parse(StringIO(PBI121_SOURCE_RECORD.read_text(encoding="ascii")), "genbank"))
    retained_ordinals = {
        int(feature_id.rsplit(":", 1)[-1])
        for feature_id in [
            *(strategy.get("retained_feature_ids") or []),
            *(strategy.get("protected_feature_ids") or []),
        ]
    }
    source.features = [
        feature
        for ordinal, feature in enumerate(source.features, start=1)
        if feature.type == "source" or ordinal in retained_ordinals
    ]
    output = StringIO()
    SeqIO.write(source, output, "genbank")
    return output.getvalue()


def _decorate_genbank_export(result: dict[str, Any], report: dict[str, Any]) -> None:
    """Add stable source and confirmation qualifiers to the runtime-derived GenBank."""
    export_record = dict((result.get("exports") or {}).get("complete_plasmid_genbank") or {})
    record = next(SeqIO.parse(StringIO(_text(export_record.get("data"))), "genbank"))
    provenance = report["component_provenance_summary"]
    component_by_name = {
        provenance["promoter"]["biological_role"]: provenance["promoter"],
        provenance["three_prime_regulatory_region"]["biological_role"]: provenance["three_prime_regulatory_region"],
        **{item["gene"]: item for item in provenance["cds_records"]},
    }
    for feature in record.features:
        label = _text((feature.qualifiers.get("label") or [""])[0])
        component = component_by_name.get(label)
        if component is None:
            continue
        feature.qualifiers["source_accession"] = [_text(component.get("source_accession") or component.get("version"))]
        feature.qualifiers["source_record_sha256"] = [_text(component["source_record_sha256"])]
        feature.qualifiers["sequence_sha256"] = [_text(component.get("sequence_sha256") or component.get("cds_sha256"))]
        feature.qualifiers["provenance_status"] = [_text(component.get("provenance_status") or "verified_source")]
        feature.qualifiers["verification_status"] = [_text(component["verification_status"])]
        feature.qualifiers["manual_confirmation"] = ["repeated regulatory reuse confirmed"]
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    export_record["data"] = output.getvalue()
    result["exports"]["complete_plasmid_genbank"] = export_record


def generate_betalain_pbi121_canonical_construct(
    *,
    project_id: str,
    project_name: str,
    repeated_regulatory_confirmed: bool,
    strategy_root: Path | None = None,
) -> dict[str, Any]:
    """Generate the reviewed three-TU pBI121 replacement through frozen public APIs."""
    report = evaluate_betalain_pbi121_prerequisites(
        repeated_regulatory_confirmed=repeated_regulatory_confirmed,
        strategy_root=strategy_root,
    )
    if report["blockers"]:
        raise BetalainPbi121CanonicalConstructError("; ".join(report["blockers"]))
    case = load_betalain_three_enzyme_case()
    components = _registered_components()
    strategy, _ = _strategy_gate(strategy_root)
    expression_units = _expression_units(case, components)
    pathway_steps, _mapped_units, pathway_mapping = apply_betalain_case_to_units(
        copy.deepcopy(expression_units)
    )
    contract = replacement_contract()
    audit = build_pbi121_asset_bundle()["audit"]
    from services.vector_asset_admission import require_vector_operation

    vector_asset_admission = require_vector_operation(
        {
            "normalized_sequence": audit["sequence"],
            "source_accession_version": audit["accession"],
            "topology": audit["topology"],
        },
        workflow_id="betalain_gate3",
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": contract["replacement_start"],
            "end_coordinate": contract["replacement_end"],
            "insertion_orientation": "forward",
        },
    )
    result = generate_multi_tu_construct(
        project_id=project_id,
        project_name=project_name,
        expression_units=expression_units,
        backbone={
            "display_name": "pBI121",
            "raw_text": _runtime_backbone_genbank(strategy),
            "length": contract["full_sequence_length"],
            "source_type": "official_ncbi_genbank",
            "source_format": "genbank",
            "source_name": "AF485783.1",
            "provenance_reference": f"source_record_sha256={strategy['source_record_sha256']}",
            "topology": "circular",
        },
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": contract["replacement_start"],
            "end_coordinate": contract["replacement_end"],
            "expected_removed_sequence": audit["sequence"][
                contract["normalized_replacement_start"] : contract["normalized_replacement_end"]
            ],
            "insertion_orientation": "forward",
            "user_confirmation": True,
        },
    )
    combined_sequence = result["combined_construct"]["dna"]
    complete_sequence = result["complete_plasmid"]["dna"]
    expected_sequence = replace_pbi121_reporter_cassette(
        audit["sequence"],
        combined_sequence,
        accession_version=audit["accession"],
    )
    delta = len(combined_sequence) - contract["replacement_length"]
    source_reporter = audit["sequence"][
        contract["normalized_replacement_start"] : contract["normalized_replacement_end"]
    ]
    checks = {
        "pbi121_length": len(audit["sequence"]),
        "pbi121_sequence_sha256": audit["sequence_sha256"],
        "replacement_length": contract["replacement_length"],
        "replacement_sha256": contract["replacement_sha256"],
        "multi_tu_region_length": int(result["combined_construct"]["total_length"]),
        "final_length": int(result["complete_plasmid"]["total_length"]),
        "final_length_formula_matches": int(result["complete_plasmid"]["total_length"])
        == contract["full_sequence_length"] - contract["replacement_length"] + len(combined_sequence),
        "canonical_matches_exact_replacement": complete_sequence == expected_sequence,
        "source_prefix_preserved": complete_sequence[:4973] == audit["sequence"][:4973],
        "source_suffix_preserved": complete_sequence[4973 + len(combined_sequence) :] == audit["sequence"][7979:],
        "original_reporter_cassette_absent": source_reporter not in complete_sequence,
        "right_border_retained": complete_sequence[2453:2478] == audit["sequence"][2453:2478],
        "nptii_selection_cassette_retained": complete_sequence[2518:4277] == audit["sequence"][2518:4277],
        "left_border_retained": complete_sequence[8620 + delta : 8646 + delta] == audit["sequence"][8620:8646],
        "col_e1_ori_retained": complete_sequence[789:1168] == audit["sequence"][789:1168],
        "ori_v_retained": complete_sequence[14140 + delta : 14758 + delta] == audit["sequence"][14140:14758],
        "complete_sequence_sha256": result["complete_plasmid"]["sequence_sha256"],
    }
    failed_checks = [key for key, value in checks.items() if isinstance(value, bool) and not value]
    if failed_checks:
        raise BetalainPbi121CanonicalConstructError(
            "The pBI121 exact-replacement sequence checks failed: " + ", ".join(failed_checks)
        )
    report["sequence_identity_checks"] = checks
    report["replacement_contract"] = copy.deepcopy(contract)
    report["strategy_reference"] = {"strategy_id": strategy["strategy_id"], "strategy_status": strategy["strategy_status"]}
    _decorate_genbank_export(result, report)
    fasta = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    exports_match = str(fasta.seq).upper() == str(genbank.seq).upper() == complete_sequence
    report["sequence_identity_checks"]["fasta_genbank_canonical_match"] = exports_match
    if not exports_match:
        raise BetalainPbi121CanonicalConstructError(
            "The pBI121 FASTA, GenBank, and canonical sequences do not match."
        )
    result["input_lengths"] = {"backbone": 14758}
    result["betalain_pbi121_validation"] = report
    result["vector_asset_admission"] = vector_asset_admission
    result["formal_project_context"] = {
        "design_scenario": "metabolic_pathway_multi_tu_vector",
        "host_key": case["plant_host"],
        "expression_target": "Betalain three-enzyme design record",
        "pathway_steps": copy.deepcopy(pathway_steps),
        "pathway_mapping": copy.deepcopy(pathway_mapping),
        "current_step": 6,
        "wet_lab_readiness": "not_assessed",
        "repeated_regulatory_confirmed": True,
        "replacement_strategy_id": strategy["strategy_id"],
        "pbi121_replacement_contract": copy.deepcopy(contract),
        "source_backbone_length": 14758,
        "boundary_note": BOUNDARY_COPY,
        "betalain_pbi121_validation": copy.deepcopy(report),
    }
    return result
