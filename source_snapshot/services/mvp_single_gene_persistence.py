"""Durable save, reopen, and delete support for the three-page MVP design record."""
from __future__ import annotations

import base64
import hashlib
from io import StringIO
from typing import Any

from Bio import SeqIO

from core.pcambia1300_exact_insertion_contract import (
    Pcambia1300ExactInsertionContractError,
    exact_insertion_contract,
    is_pcambia1300_record,
    sequence_sha256 as pcambia_sequence_sha256,
    validate_pcambia1300_operation,
)
from services.canonical_construct_runtime import (
    R227_RUNTIME_SCHEMA_VERSION,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.sequence_service import reverse_complement
from services.mvp_cds_input import analyze_cds_input
from services.mvp_company_review_package import (
    ALLOWED_SOURCE_KINDS,
    PROJECT_SCHEMA_VERSION,
    PROJECT_TYPE,
    MvpCompanyReviewPackageError,
    build_company_review_package,
    normalized_source_provenance,
    safe_project_directory_name,
    validate_company_review_package_bytes,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    PlantProjectDraftSummary,
    require_active_project,
)
from services.plant_project_draft_schema import PlantDesignProjectDraft, PlantProjectDraftError, update_plant_project_draft
from services.formal_project_persistence import mark_formal_project_completed, WORKFLOW_SINGLE_GENE
from services.formal_editor_state_contract import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION,
    RECORD_KIND_FORMAL_EDITOR_COMPLETED,
    RECORD_KIND_RESULT_ONLY_COMPLETED,
)


MVP_SINGLE_GENE_PERSISTENCE_KEY = "mvp_single_gene_persistence"
MVP_SINGLE_GENE_PERSISTENCE_SCHEMA_VERSION = "v2.7-mvp5-single-gene-persistence"
class MvpSingleGenePersistenceError(ValueError):
    """Raised when an MVP saved-design record cannot be used safely."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_sequence(value: str) -> str:
    return hashlib.sha256(value.upper().encode("ascii")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "")


def _validated_pcambia1300_persistence_record(
    *,
    input_records: dict[str, Any],
    insertion_settings: dict[str, Any],
    exact_contract_snapshot: dict[str, Any],
    exact_record: dict[str, Any],
    cassette_sequence: str,
    plasmid_sequence: str,
) -> dict[str, Any]:
    backbone = _mapping(input_records.get("backbone"))
    if not is_pcambia1300_record(backbone):
        return {}
    if not exact_record:
        raise MvpSingleGenePersistenceError(
            "This saved AF234296.1 project predates the fixed 27|28 contract. Reapply the formal exact-insertion contract before generation."
        )
    accession = _text(
        backbone.get("source_accession_version")
        or backbone.get("original_record_identifier")
        or backbone.get("source_name")
    )
    try:
        contract = validate_pcambia1300_operation(
            source_sequence=_text(backbone.get("normalized_sequence")),
            accession_version=accession,
            circular=_text(backbone.get("topology")).lower() == "circular",
            mode=_text(insertion_settings.get("mode")),
            start_coordinate=int(insertion_settings.get("start_coordinate") or 0),
            end_coordinate=int(insertion_settings.get("end_coordinate") or 0),
            insertion_orientation=_text(insertion_settings.get("insertion_orientation")) or "forward",
            workflow_id="rice_alb_single_gene",
        )
    except Pcambia1300ExactInsertionContractError as exc:
        raise MvpSingleGenePersistenceError(str(exc)) from exc
    expected = {
        "asset_id": contract["asset_id"],
        "asset_kind": contract["asset_kind"],
        "accession_version": contract["accession_version"],
        "exact_insertion_contract_version": contract["contract_version"],
        "internal_cut_index": contract["internal_cut_index"],
        "source_hash": pcambia_sequence_sha256(_text(backbone.get("normalized_sequence"))),
        "cassette_hash": pcambia_sequence_sha256(cassette_sequence),
        "output_sequence_hash": pcambia_sequence_sha256(plasmid_sequence),
        "workflow_support_status": "supported_rice_alb_single_gene",
    }
    if exact_record != expected:
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 exact-insertion identity record does not match the canonical sequence snapshot."
        )
    if _mapping(insertion_settings.get("exact_insertion_contract")) != exact_insertion_contract():
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 exact-insertion contract snapshot is missing or has been changed."
        )
    if exact_contract_snapshot != exact_insertion_contract():
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 top-level exact-insertion contract is missing or has been changed."
        )
    if _text(insertion_settings.get("exact_insertion_contract_version")) != contract["contract_version"]:
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 exact-insertion contract version is missing or has been changed."
        )
    if _text(insertion_settings.get("workflow_id")) != "rice_alb_single_gene":
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 project is not recorded as the supported rice/ALB single-gene workflow."
        )
    if _text(insertion_settings.get("workflow_support_status")) != "supported_rice_alb_single_gene":
        raise MvpSingleGenePersistenceError(
            "The saved AF234296.1 workflow support status is missing or has been changed."
        )
    return expected


def _formal_project_context(result: dict[str, Any]) -> dict[str, Any]:
    """Keep formal UI identity with the canonical snapshot, not in session state."""
    context = _mapping(result.get("formal_project_context"))
    normalized = {
        "host_key": _text(context.get("host_key")),
        "expression_target": _text(context.get("expression_target")),
        "current_step": int(context.get("current_step") or 6),
    }
    # First-step fields are optional so existing saved records remain readable.
    # They remain in the shared project snapshot rather than creating a second
    # persistence model.
    for key in (
        "record_kind",
        "formal_editor_state_contract_version",
        "project_definition",
        "construct_review_basis",
        "construct_review_status",
        "cds_source_review_basis",
        "cds_source_review_status",
        "formal_state",
    ):
        if key in context:
            normalized[key] = context[key]
    return normalized


def _formal_editor_state_reason(
    context: dict[str, Any],
    formal_cassette: dict[str, Any],
    *,
    cassette_sequence: str,
    cds_input: dict[str, Any],
    input_records: dict[str, Any],
    insertion_settings: dict[str, Any],
) -> str:
    """Classify whether a completed formal editor can be restored safely.

    Result-only and older records remain readable.  Only records explicitly
    marked as formal-editor completed are required to satisfy the editor-state
    contract; this keeps old MVP result snapshots on the historical-preview
    path instead of manufacturing editable state from canonical output.
    """
    record_kind = _text(context.get("record_kind"))
    state = _mapping(context.get("formal_state"))
    if not record_kind:
        # Older records with a formal project definition were intended for the
        # editor but predate the contract.  Report their precise missing field
        # before falling back to the generic legacy-record reason.
        if _mapping(context.get("project_definition")) and not state:
            return "missing_formal_state"
        if _mapping(context.get("project_definition")) and not list(formal_cassette.get("components") or []):
            return "missing_step3_components"
        return "legacy_record"
    if record_kind == RECORD_KIND_RESULT_ONLY_COMPLETED:
        return "result_only_completed"
    if record_kind != RECORD_KIND_FORMAL_EDITOR_COMPLETED:
        return "unsupported_version"
    if _text(context.get("formal_editor_state_contract_version")) != FORMAL_EDITOR_STATE_CONTRACT_VERSION:
        return "unsupported_version"
    if not state:
        return "missing_formal_state"
    if not list(formal_cassette.get("components") or []):
        return "missing_step3_components"
    required_mappings = {
        "formal_project_definition": _mapping(state.get("formal_project_definition")),
        "formal_cds_input": _mapping(state.get("formal_cds_input")),
        "formal_expression_cassette": _mapping(state.get("formal_expression_cassette")),
        "formal_backbone_record": _mapping(state.get("formal_backbone_record")),
        "formal_insertion_settings": _mapping(state.get("formal_insertion_settings")),
        "formal_cassette_result": _mapping(state.get("formal_cassette_result")),
    }
    if not all(required_mappings.values()):
        return "missing_formal_state"
    state_cassette = required_mappings["formal_expression_cassette"]
    if not list(state_cassette.get("components") or []):
        return "missing_step3_components"
    if not bool(state.get("formal_step3_order_confirmation_recorded")):
        return "missing_formal_state"
    if not bool(state.get("formal_step4_strategy_confirmed")):
        return "missing_formal_state"
    if not bool(state.get("formal_step5_strategy_confirmed")):
        return "missing_formal_state"
    construct_review_status = _text(state.get("formal_construct_review_status"))
    cds_review_status = _text(state.get("formal_cds_source_review_status"))
    if construct_review_status not in {"current", "needs_review"} or cds_review_status not in {"current", "needs_review"}:
        return "missing_formal_state"
    if (
        construct_review_status != _text(context.get("construct_review_status") or "current")
        or cds_review_status != _text(context.get("cds_source_review_status") or "current")
    ):
        return "state_canonical_mismatch"
    if int(context.get("current_step") or 0) != 6:
        return "state_canonical_mismatch"
    definition = _mapping(context.get("project_definition"))
    state_definition = required_mappings["formal_project_definition"]
    if not definition or state_definition != definition:
        return "state_canonical_mismatch"
    if (
        _text(required_mappings["formal_cds_input"].get("normalized_cds"))
        != _text(cds_input.get("normalized_cds"))
        or _text(required_mappings["formal_backbone_record"].get("normalized_sequence"))
        != _text(_mapping(input_records.get("backbone")).get("normalized_sequence"))
        or required_mappings["formal_insertion_settings"] != insertion_settings
    ):
        return "state_canonical_mismatch"
    try:
        validated_state_cassette = _validated_formal_expression_cassette(
            state_cassette, cassette_sequence
        )
    except MvpSingleGenePersistenceError:
        return "state_canonical_mismatch"
    if (
        list(validated_state_cassette.get("components") or [])
        != list(formal_cassette.get("components") or [])
        or _text(validated_state_cassette.get("input_signature"))
        != _text(formal_cassette.get("input_signature"))
        or _text(required_mappings["formal_cassette_result"].get("cassette_input_signature")
                 or required_mappings["formal_cassette_result"].get("input_signature"))
        != _text(formal_cassette.get("input_signature"))
    ):
        return "state_canonical_mismatch"
    return ""


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = _mapping(payload.get(key))
    if not value:
        raise MvpSingleGenePersistenceError("保存的设计记录不完整，无法打开。")
    return value


def _expected_input_lengths(input_records: dict[str, Any]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for role in ("promoter", "cds", "terminator", "backbone"):
        record = _mapping(input_records.get(role))
        sequence = _text(record.get("normalized_sequence"))
        if not sequence:
            raise MvpSingleGenePersistenceError("当前设计缺少可保存的完整输入。")
        expected[role] = len(sequence)
        if int(record.get("length", 0)) != len(sequence):
            raise MvpSingleGenePersistenceError("当前设计的输入长度记录不一致。")
    return expected


def _expected_result_lengths(
    input_lengths: dict[str, int],
    insertion_settings: dict[str, Any],
    *,
    cassette_length: int | None = None,
) -> tuple[int, int]:
    cassette_length = int(cassette_length) if cassette_length is not None else sum(
        input_lengths[role] for role in ("promoter", "cds", "terminator")
    )
    plasmid_length = input_lengths["backbone"] + cassette_length
    if _text(insertion_settings.get("mode")) == "replacement":
        start = int(insertion_settings.get("start_coordinate", 0))
        end = int(insertion_settings.get("end_coordinate", 0))
        if start < 1 or end < start or end > input_lengths["backbone"]:
            raise MvpSingleGenePersistenceError("当前设计的替换坐标无效。")
        plasmid_length -= end - start + 1
    return cassette_length, plasmid_length


def _validated_formal_expression_cassette(value: Any, cassette_sequence: str) -> dict[str, Any]:
    """Validate the optional Step 3 detail without introducing a second cassette model."""
    payload = _mapping(value)
    if not payload:
        return {}
    components = list(payload.get("components") or [])
    if not components or len(_text(payload.get("input_signature"))) != 64:
        raise MvpSingleGenePersistenceError("第三步表达盒记录不完整，无法保存或打开。")
    assembled: list[str] = []
    cursor = 1
    for index, component in enumerate(components, start=1):
        if not isinstance(component, dict):
            raise MvpSingleGenePersistenceError("第三步表达盒组件记录不完整，无法保存或打开。")
        sequence = _text(component.get("sequence")).upper()
        if not sequence or set(sequence) - set("ATCG"):
            raise MvpSingleGenePersistenceError("第三步表达盒组件序列不合法，无法保存或打开。")
        oriented = reverse_complement(sequence) if _text(component.get("strand")) == "reverse" else sequence
        start, end = int(component.get("start", 0)), int(component.get("end", 0))
        if int(component.get("order", 0)) != index or start != cursor or end != cursor + len(oriented) - 1:
            raise MvpSingleGenePersistenceError("第三步表达盒组件顺序或坐标不正确，无法保存或打开。")
        if not _text(component.get("biological_role")) or not _text(component.get("display_name")):
            raise MvpSingleGenePersistenceError("第三步表达盒组件缺少名称或 biological role，无法保存或打开。")
        assembled.append(oriented)
        cursor = end + 1
    rebuilt = "".join(assembled)
    if rebuilt != _text(cassette_sequence) or int(payload.get("total_length", 0)) != len(rebuilt):
        raise MvpSingleGenePersistenceError("第三步表达盒序列、长度或坐标不一致，无法保存或打开。")
    return payload


def _encoded_export_bytes(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _encoded_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decoded_export_text(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise MvpSingleGenePersistenceError("保存的导出字节已损坏，无法打开。") from exc


def _decoded_bytes(value: str, *, label: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except ValueError as exc:
        raise MvpSingleGenePersistenceError(f"保存的{label}字节已损坏，无法打开。") from exc


def _project_compatibility(payload: dict[str, Any]) -> tuple[str, str, bool]:
    raw_version = _text(payload.get("project_schema_version"))
    raw_type = _text(payload.get("project_type"))
    legacy = not raw_version and not raw_type
    version = raw_version or PROJECT_SCHEMA_VERSION
    project_type = raw_type or PROJECT_TYPE
    if version != PROJECT_SCHEMA_VERSION or project_type != PROJECT_TYPE:
        raise MvpSingleGenePersistenceError("保存的单基因项目版本不兼容，无法打开。")
    return version, project_type, legacy


def _validated_cds_input(payload: dict[str, Any], source_inputs: dict[str, Any]) -> dict[str, Any]:
    source_text = str(source_inputs.get("cds") or "")
    supplied = _mapping(payload.get("cds_input"))
    if supplied and str(supplied.get("original_text") or "") != source_text:
        raise MvpSingleGenePersistenceError("保存的 CDS 原始输入与来源记录不一致，无法打开。")
    analyzed = analyze_cds_input(
        source_text,
        source_kind=_text(supplied.get("source_kind")) or "real_case",
        source_name=_text(supplied.get("source_name")),
    )
    if bool(analyzed.get("blocking")):
        raise MvpSingleGenePersistenceError("保存的 CDS 输入未通过校验，无法保存或打开。")
    if supplied and (
        _text(supplied.get("normalized_cds")) != _text(analyzed.get("normalized_cds"))
        or int(supplied.get("normalized_length", 0)) != int(analyzed.get("normalized_length", 0))
        or _text(supplied.get("original_text_sha256")) != _text(analyzed.get("original_text_sha256"))
    ):
        raise MvpSingleGenePersistenceError("保存的 CDS 规范化记录与原始输入不一致，无法打开。")
    merged = dict(analyzed)
    if supplied:
        merged["runtime_findings"] = list(supplied.get("runtime_findings") or [])
        # These are Step 2 documentation fields.  The sequence itself has
        # already been re-analyzed above from its preserved original input.
        for key in ("gene_information", "source_review_basis", "sequence_signature", "manual_review_items"):
            if key in supplied:
                merged[key] = supplied[key]
    return merged


def _snapshot_payload(result: dict[str, Any]) -> dict[str, Any]:
    runtime = _mapping(result.get("runtime"))
    source_inputs = _mapping(result.get("source_inputs"))
    input_records = _mapping(result.get("input_records"))
    source_provenance = {
        role: normalized_source_provenance(_mapping(input_records.get(role)))
        for role in ("promoter", "cds", "terminator", "backbone")
    }
    insertion_settings = _mapping(result.get("insertion_settings"))
    exports = _mapping(result.get("exports"))
    fasta = _require_mapping(exports, "fasta")
    genbank = _require_mapping(exports, "genbank")
    cassette = active_construct_snapshot(runtime)
    plasmid = active_complete_plasmid_snapshot(runtime)
    formal_cassette = _mapping(result.get("formal_expression_cassette"))
    formal_cassette = _validated_formal_expression_cassette(
        formal_cassette,
        _text(cassette.get("sequence")),
    )
    cds_input = _validated_cds_input(result, source_inputs)
    formal_context = _formal_project_context(result)
    record_kind = _text(formal_context.get("record_kind")) or RECORD_KIND_RESULT_ONLY_COMPLETED
    if record_kind not in {
        RECORD_KIND_FORMAL_EDITOR_COMPLETED,
        RECORD_KIND_RESULT_ONLY_COMPLETED,
    }:
        raise MvpSingleGenePersistenceError("The completed project record kind is unsupported.")
    if record_kind == RECORD_KIND_FORMAL_EDITOR_COMPLETED:
        contract_reason = _formal_editor_state_reason(
            formal_context,
            formal_cassette,
            cassette_sequence=_text(cassette.get("sequence")),
            cds_input=cds_input,
            input_records=input_records,
            insertion_settings=insertion_settings,
        )
        if contract_reason:
            raise MvpSingleGenePersistenceError(
                "A formal-editor completed project requires a complete, canonical-consistent editor-state contract "
                f"({contract_reason})."
            )
    expected_input_lengths = _expected_input_lengths(input_records)
    expected_cassette_length, expected_plasmid_length = _expected_result_lengths(
        expected_input_lengths,
        insertion_settings,
        cassette_length=(int(formal_cassette.get("total_length")) if formal_cassette else None),
    )
    if not runtime or set(source_inputs) != {"promoter", "cds", "terminator", "backbone"}:
        raise MvpSingleGenePersistenceError("当前设计缺少可保存的完整输入。")
    if not _text(result.get("project_id")) or not _text(result.get("project_name")):
        raise MvpSingleGenePersistenceError("当前设计缺少项目名称或项目标识。")
    if _text(_formal_project_context(result).get("construct_review_status")) == "needs_review":
        raise MvpSingleGenePersistenceError("第一步项目背景已变化，当前结果需要重新审查后才能保存为项目记录。")
    if len(_text(result.get("input_signature"))) != 64:
        raise MvpSingleGenePersistenceError("当前设计缺少有效的输入签名。")
    if set(input_records) != {"promoter", "cds", "terminator", "backbone"}:
        raise MvpSingleGenePersistenceError("当前设计缺少可保存的输入记录。")
    for role, source_text in source_inputs.items():
        if _text(_mapping(input_records.get(role)).get("original_text")) != _text(source_text):
            raise MvpSingleGenePersistenceError("当前设计的原始输入与输入记录不一致。")
    source_input_sha256 = {role: _sha256_text(_text(source_inputs[role])) for role in source_inputs}
    if not _text(fasta.get("data")) or not _text(genbank.get("data")):
        raise MvpSingleGenePersistenceError("当前设计缺少可保存的下载文件。")
    if (
        {key: int(value) for key, value in dict(result.get("input_lengths") or {}).items()} != expected_input_lengths
        or int(cassette.get("sequence_length", 0)) != expected_cassette_length
        or int(plasmid.get("sequence_length", 0)) != expected_plasmid_length
    ):
        raise MvpSingleGenePersistenceError("当前设计长度与实际输入不一致，无法保存。")

    plasmid_sequence = _text(plasmid.get("sequence"))
    fasta_sequence = _parse_single_sequence(_text(fasta.get("data")), "fasta")
    genbank_sequence = _parse_single_sequence(_text(genbank.get("data")), "genbank")
    if fasta_sequence != plasmid_sequence or genbank_sequence != plasmid_sequence:
        raise MvpSingleGenePersistenceError("当前下载文件与完整质粒记录不一致，无法保存。")
    exact_insertion_record = _validated_pcambia1300_persistence_record(
        input_records=input_records,
        insertion_settings=insertion_settings,
        exact_contract_snapshot=_mapping(result.get("exact_insertion_contract")),
        exact_record=_mapping(result.get("exact_insertion_record")),
        cassette_sequence=_text(cassette.get("sequence")),
        plasmid_sequence=plasmid_sequence,
    )

    package = _mapping(result.get("company_review_package"))
    if not isinstance(package.get("data"), bytes):
        try:
            package = build_company_review_package(
                dict(result, input_records=input_records, cds_input=cds_input)
            )
        except MvpCompanyReviewPackageError as exc:
            raise MvpSingleGenePersistenceError("当前设计缺少可保存的公司审查包。") from exc
    package_bytes = package.get("data")
    if not isinstance(package_bytes, bytes) or not package_bytes:
        raise MvpSingleGenePersistenceError("当前设计缺少可保存的公司审查包。")
    expected_package_hash = hashlib.sha256(package_bytes).hexdigest()
    if _text(package.get("sha256")) != expected_package_hash:
        raise MvpSingleGenePersistenceError("当前公司审查包校验值不一致，无法保存。")
    expected_root = safe_project_directory_name(_text(result.get("project_name")))
    try:
        validate_company_review_package_bytes(
            package_bytes,
            expected_root_directory=expected_root,
        )
    except MvpCompanyReviewPackageError as exc:
        raise MvpSingleGenePersistenceError("当前公司审查包无法安全保存。") from exc

    return {
        "persistence_schema_version": MVP_SINGLE_GENE_PERSISTENCE_SCHEMA_VERSION,
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "project_type": PROJECT_TYPE,
        "record_kind": record_kind,
        "formal_editor_state_contract_version": _text(formal_context.get("formal_editor_state_contract_version")),
        "runtime_schema_version": _text(runtime.get("schema_version")),
        "project_id": _text(result.get("project_id")),
        "project_name": _text(result.get("project_name")),
        "formal_project_context": formal_context,
        "input_lengths": dict(result.get("input_lengths") or {}),
        "source_inputs": source_inputs,
        "source_input_sha256": source_input_sha256,
        "input_records": input_records,
        "source_provenance": source_provenance,
        "cds_input": cds_input,
        "insertion_settings": insertion_settings,
        "exact_insertion_contract": _mapping(result.get("exact_insertion_contract")),
        "exact_insertion_record": exact_insertion_record,
        "input_signature": _text(result.get("input_signature")),
        "cassette_input_signature": _text(result.get("cassette_input_signature")),
        "validation_summary": _mapping(result.get("validation_summary")),
        "cassette": {
            "sequence": _text(cassette.get("sequence")),
            "sequence_length": int(cassette.get("sequence_length", 0)),
            "sequence_checksum": _text(cassette.get("sequence_checksum")),
            "feature_rows": list(cassette.get("feature_rows") or []),
        },
        "formal_expression_cassette": formal_cassette,
        "complete_plasmid": {
            "sequence": plasmid_sequence,
            "sequence_length": int(plasmid.get("sequence_length", 0)),
            "sequence_checksum": _text(plasmid.get("sequence_checksum")),
            "cassette_coordinates": dict(plasmid.get("cassette_coordinates") or {}),
            "feature_rows": list(plasmid.get("feature_rows") or []),
            "topology": _text(plasmid.get("topology")),
        },
        "exports": {
            "fasta": fasta,
            "genbank": genbank,
            "metadata": _mapping(exports.get("metadata")),
        },
        "export_bytes_b64": {
            "fasta": _encoded_export_bytes(_text(fasta.get("data"))),
            "genbank": _encoded_export_bytes(_text(genbank.get("data"))),
        },
        "sequence_sha256": {
            "plasmid": _sha256_sequence(plasmid_sequence),
            "fasta": _sha256_sequence(fasta_sequence),
            "genbank": _sha256_sequence(genbank_sequence),
        },
        "export_sha256": {
            "fasta": _sha256_text(_text(fasta.get("data"))),
            "genbank": _sha256_text(_text(genbank.get("data"))),
        },
        "company_review_package": {
            "package_schema_version": _text(package.get("package_schema_version")),
            "project_schema_version": PROJECT_SCHEMA_VERSION,
            "project_type": PROJECT_TYPE,
            "root_directory": expected_root,
            "file_name": _text(package.get("file_name")),
            "mime": _text(package.get("mime")) or "application/zip",
            "sha256": expected_package_hash,
            "data_b64": _encoded_bytes(package_bytes),
        },
    }


def _parse_single_sequence(text: str, file_format: str) -> str:
    try:
        records = list(SeqIO.parse(StringIO(text), file_format))
    except Exception as exc:
        raise MvpSingleGenePersistenceError("保存的下载文件无法解析，无法打开。") from exc
    if len(records) != 1:
        raise MvpSingleGenePersistenceError("保存的下载文件记录数不正确，无法打开。")
    return str(records[0].seq).upper()


def _saved_design_payload(draft: PlantDesignProjectDraft) -> dict[str, Any]:
    payload = _mapping(draft.manual_review_state).get(MVP_SINGLE_GENE_PERSISTENCE_KEY)
    if not isinstance(payload, dict):
        raise MvpSingleGenePersistenceError("所选记录不是单基因 MVP 保存设计。")
    return dict(payload)


def _validate_reopened_design(draft: PlantDesignProjectDraft) -> dict[str, Any]:
    payload = _saved_design_payload(draft)
    if _text(payload.get("persistence_schema_version")) != MVP_SINGLE_GENE_PERSISTENCE_SCHEMA_VERSION:
        raise MvpSingleGenePersistenceError("保存的设计版本不兼容，无法打开。")
    if _text(payload.get("runtime_schema_version")) != R227_RUNTIME_SCHEMA_VERSION:
        raise MvpSingleGenePersistenceError("保存的运行时版本不兼容，无法打开。")
    project_schema_version, project_type, legacy_project = _project_compatibility(payload)

    source_inputs = _require_mapping(payload, "source_inputs")
    source_input_sha256 = _mapping(payload.get("source_input_sha256"))
    input_records = _require_mapping(payload, "input_records")
    saved_source_provenance = _mapping(payload.get("source_provenance"))
    source_provenance = {
        role: (
            _mapping(saved_source_provenance.get(role))
            or normalized_source_provenance(_mapping(input_records.get(role)))
        )
        for role in ("promoter", "cds", "terminator", "backbone")
    }
    insertion_settings = _require_mapping(payload, "insertion_settings")
    input_lengths = _require_mapping(payload, "input_lengths")
    cds_input = _validated_cds_input(payload, source_inputs)
    cassette = _require_mapping(payload, "cassette")
    formal_cassette = _validated_formal_expression_cassette(
        payload.get("formal_expression_cassette"),
        _text(cassette.get("sequence")),
    )
    formal_context = _mapping(payload.get("formal_project_context"))
    contract_context = dict(formal_context)
    payload_record_kind = _text(payload.get("record_kind"))
    context_record_kind = _text(formal_context.get("record_kind"))
    if payload_record_kind and context_record_kind and payload_record_kind != context_record_kind:
        raise MvpSingleGenePersistenceError("The completed project record kind is inconsistent.")
    if payload_record_kind:
        contract_context["record_kind"] = payload_record_kind
    payload_contract_version = _text(payload.get("formal_editor_state_contract_version"))
    context_contract_version = _text(formal_context.get("formal_editor_state_contract_version"))
    if payload_contract_version and context_contract_version and payload_contract_version != context_contract_version:
        raise MvpSingleGenePersistenceError("The formal editor-state contract version is inconsistent.")
    if payload_contract_version:
        contract_context["formal_editor_state_contract_version"] = payload_contract_version
    expected_input_lengths = _expected_input_lengths(input_records)
    expected_cassette_length, expected_plasmid_length = _expected_result_lengths(
        expected_input_lengths,
        insertion_settings,
        cassette_length=(int(formal_cassette.get("total_length")) if formal_cassette else None),
    )
    plasmid = _require_mapping(payload, "complete_plasmid")
    exports = _require_mapping(payload, "exports")
    fasta = _require_mapping(exports, "fasta")
    genbank = _require_mapping(exports, "genbank")
    sequence_hashes = _require_mapping(payload, "sequence_sha256")
    export_hashes = _require_mapping(payload, "export_sha256")
    export_bytes = _require_mapping(payload, "export_bytes_b64")

    if set(source_inputs) != {"promoter", "cds", "terminator", "backbone"}:
        raise MvpSingleGenePersistenceError("保存的设计输入不完整，无法打开。")
    if source_input_sha256 and any(
        _text(source_input_sha256.get(role)) != _sha256_text(_text(source_inputs[role]))
        for role in source_inputs
    ):
        raise MvpSingleGenePersistenceError("保存的原始输入文件校验值不一致，无法打开。")
    if set(input_records) != {"promoter", "cds", "terminator", "backbone"}:
        raise MvpSingleGenePersistenceError("保存的输入记录不完整，无法打开。")
    if any(
        _text(item.get("source_kind")) not in ALLOWED_SOURCE_KINDS
        or not _text(item.get("source_reference"))
        for item in source_provenance.values()
    ):
        raise MvpSingleGenePersistenceError("保存的来源记录不兼容，无法打开。")
    if {key: int(value) for key, value in input_lengths.items()} != expected_input_lengths:
        raise MvpSingleGenePersistenceError("保存的设计输入长度不正确，无法打开。")
    if len(_text(payload.get("input_signature"))) != 64:
        raise MvpSingleGenePersistenceError("保存的输入签名不正确，无法打开。")

    fasta_text = _decoded_export_text(_text(export_bytes.get("fasta")))
    genbank_text = _decoded_export_text(_text(export_bytes.get("genbank")))
    if fasta_text != _text(fasta.get("data")):
        raise MvpSingleGenePersistenceError("保存的 FASTA 文件已损坏，无法打开。")
    if genbank_text != _text(genbank.get("data")):
        raise MvpSingleGenePersistenceError("保存的 GenBank 文件已损坏，无法打开。")
    if _sha256_text(fasta_text) != _text(export_hashes.get("fasta")):
        raise MvpSingleGenePersistenceError("保存的 FASTA 文件已损坏，无法打开。")
    if _sha256_text(genbank_text) != _text(export_hashes.get("genbank")):
        raise MvpSingleGenePersistenceError("保存的 GenBank 文件已损坏，无法打开。")
    fasta_sequence = _parse_single_sequence(fasta_text, "fasta")
    genbank_sequence = _parse_single_sequence(genbank_text, "genbank")
    plasmid_sequence = _text(plasmid.get("sequence"))
    if fasta_sequence != plasmid_sequence or genbank_sequence != plasmid_sequence:
        raise MvpSingleGenePersistenceError("保存的下载文件与质粒记录不一致，无法打开。")
    if int(plasmid.get("sequence_length", 0)) != expected_plasmid_length or len(plasmid_sequence) != expected_plasmid_length:
        raise MvpSingleGenePersistenceError("保存的完整质粒长度不正确，无法打开。")
    if int(cassette.get("sequence_length", 0)) != expected_cassette_length or len(_text(cassette.get("sequence"))) != expected_cassette_length:
        raise MvpSingleGenePersistenceError("保存的表达盒长度不正确，无法打开。")
    formal_editor_restore_reason = _formal_editor_state_reason(
        contract_context,
        formal_cassette,
        cassette_sequence=_text(cassette.get("sequence")),
        cds_input=cds_input,
        input_records=input_records,
        insertion_settings=insertion_settings,
    )
    exact_insertion_record = _validated_pcambia1300_persistence_record(
        input_records=input_records,
        insertion_settings=insertion_settings,
        exact_contract_snapshot=_mapping(payload.get("exact_insertion_contract")),
        exact_record=_mapping(payload.get("exact_insertion_record")),
        cassette_sequence=_text(cassette.get("sequence")),
        plasmid_sequence=plasmid_sequence,
    )
    expected_sequence_hash = _sha256_sequence(plasmid_sequence)
    if any(_text(sequence_hashes.get(key)) != expected_sequence_hash for key in ("plasmid", "fasta", "genbank")):
        raise MvpSingleGenePersistenceError("保存的序列校验值不一致，无法打开。")

    try:
        runtime_cassette = active_construct_snapshot(draft.canonical_construct_runtime)
        runtime_plasmid = active_complete_plasmid_snapshot(draft.canonical_construct_runtime)
    except Exception as exc:
        raise MvpSingleGenePersistenceError("保存的运行时记录已损坏，无法打开。") from exc
    if (
        _text(runtime_cassette.get("sequence")) != _text(cassette.get("sequence"))
        or list(runtime_cassette.get("feature_rows") or []) != list(cassette.get("feature_rows") or [])
        or _text(runtime_plasmid.get("sequence")) != plasmid_sequence
        or dict(runtime_plasmid.get("cassette_coordinates") or {}) != dict(plasmid.get("cassette_coordinates") or {})
        or list(runtime_plasmid.get("feature_rows") or []) != list(plasmid.get("feature_rows") or [])
    ):
        raise MvpSingleGenePersistenceError("保存的运行时记录与设计快照不一致，无法打开。")

    reopened = {
        "project_id": draft.project_id,
        "project_name": draft.project_name,
        "formal_project_context": formal_context,
        "record_kind": payload_record_kind or context_record_kind or "legacy_record",
        "formal_editor_state_contract_version": payload_contract_version or context_contract_version,
        "formal_editor_restore_reason": formal_editor_restore_reason,
        "project_schema_version": project_schema_version,
        "project_type": project_type,
        "legacy_project_compatibility": legacy_project,
        "input_lengths": input_lengths,
        "cassette_length": int(cassette["sequence_length"]),
        "plasmid_length": int(plasmid["sequence_length"]),
        "plasmid_sha256": expected_sequence_hash,
        "fasta_sequence_sha256": expected_sequence_hash,
        "genbank_sequence_sha256": expected_sequence_hash,
        "runtime": draft.canonical_construct_runtime,
        "source_inputs": source_inputs,
        "source_input_sha256": source_input_sha256,
        "input_records": input_records,
        "source_provenance": source_provenance,
        "cds_input": cds_input,
        "insertion_settings": insertion_settings,
        "exact_insertion_contract": _mapping(payload.get("exact_insertion_contract")),
        "exact_insertion_record": exact_insertion_record,
        "validation_summary": _mapping(payload.get("validation_summary")),
        "input_signature": _text(payload.get("input_signature")),
        "cassette_input_signature": _text(payload.get("cassette_input_signature")),
        "exports": exports,
        "formal_expression_cassette": formal_cassette,
    }
    from services.vector_asset_admission import assess_legacy_project_vector

    reopened["vector_asset_admission"] = assess_legacy_project_vector(
        _mapping(input_records.get("backbone")),
        workflow_id=_text(insertion_settings.get("workflow_id")) or "formal_single_gene",
        insertion_settings=insertion_settings,
    )
    saved_package = _mapping(payload.get("company_review_package"))
    if saved_package:
        package_bytes = _decoded_bytes(_text(saved_package.get("data_b64")), label="公司审查包")
        expected_hash = hashlib.sha256(package_bytes).hexdigest()
        if expected_hash != _text(saved_package.get("sha256")):
            raise MvpSingleGenePersistenceError("保存的公司审查包校验值不一致，无法打开。")
        expected_root = safe_project_directory_name(draft.project_name)
        try:
            validate_company_review_package_bytes(
                package_bytes,
                expected_root_directory=expected_root,
            )
        except MvpCompanyReviewPackageError as exc:
            raise MvpSingleGenePersistenceError("保存的公司审查包已损坏，无法打开。") from exc
        reopened["company_review_package"] = {
            "package_schema_version": _text(saved_package.get("package_schema_version")) or "1.0.0",
            "project_schema_version": project_schema_version,
            "project_type": project_type,
            "root_directory": expected_root,
            "file_name": _text(saved_package.get("file_name")) or f"{expected_root}_company_review_package.zip",
            "mime": _text(saved_package.get("mime")) or "application/zip",
            "sha256": expected_hash,
            "data": package_bytes,
        }
    else:
        try:
            reopened["company_review_package"] = build_company_review_package(reopened)
        except MvpCompanyReviewPackageError as exc:
            raise MvpSingleGenePersistenceError("旧版单基因项目无法生成公司审查包。") from exc
    from services.single_gene_assisted_components import validate_single_gene_assisted_result

    try:
        validate_single_gene_assisted_result(reopened, repository=None)
    except ValueError as exc:
        raise MvpSingleGenePersistenceError(str(exc)) from exc
    return reopened


def save_mvp_single_gene_design(
    result: dict[str, Any], *, repository: PlantProjectDraftRepository | None = None
) -> PlantDesignProjectDraft:
    """Save one generalized MVP design through the existing R224 repository."""
    repo = repository or PlantProjectDraftRepository()
    from services.single_gene_assisted_components import validate_single_gene_assisted_result

    try:
        validate_single_gene_assisted_result(result, repository=repo)
    except ValueError as exc:
        raise MvpSingleGenePersistenceError(str(exc)) from exc
    snapshot = _snapshot_payload(result)
    from services.vector_asset_admission import assess_legacy_project_vector

    input_records = _mapping(result.get("input_records"))
    insertion_settings = _mapping(result.get("insertion_settings"))
    vector_asset_admission = assess_legacy_project_vector(
        _mapping(input_records.get("backbone")),
        workflow_id=_text(insertion_settings.get("workflow_id")) or "formal_single_gene",
        insertion_settings=insertion_settings,
    )
    snapshot["vector_asset_admission"] = vector_asset_admission
    project_id = _text(result.get("project_id"))
    project_name = _text(result.get("project_name"))
    try:
        try:
            draft = repo.load(project_id)
        except PlantProjectDraftError:
            draft = repo.create_blank(project_name=project_name)
            draft.project_id = project_id
        review_state = _mapping(draft.manual_review_state)
        review_state[MVP_SINGLE_GENE_PERSISTENCE_KEY] = snapshot
        draft.manual_review_state = review_state
        draft = update_plant_project_draft(
            draft,
            project_name=project_name,
            plant_design_goal="Documentation-only single-gene complete plasmid design record.",
            host_context=_text(_formal_project_context(result).get("host_key")) or "User-provided plant single-gene project inputs",
            expression_context=_text(_formal_project_context(result).get("expression_target")) or "Local single-gene expression design record",
            canonical_construct_runtime=_mapping(result.get("runtime")),
        )
        draft.manual_review_state = review_state
        if vector_asset_admission["completed_design_allowed"]:
            draft = mark_formal_project_completed(draft, workflow_type=WORKFLOW_SINGLE_GENE)
        saved = repo.save(draft)

        # A successful write is not enough for the UI claim. Re-open through a
        # fresh repository instance so a later cold start uses the same durable
        # file and validation path before the caller can report success.
        reopened_repo = PlantProjectDraftRepository(repo.storage_dir)
        reopened = _validate_reopened_design(reopened_repo.load(saved.project_id))
        if (
            _text(reopened.get("project_id")) != saved.project_id
            or _text(reopened.get("project_name")) != saved.project_name
            or not _mapping(reopened.get("runtime"))
            or saved.project_id not in {
                summary.project_id for summary in list_mvp_single_gene_designs(repository=reopened_repo)
            }
        ):
            raise PlantProjectDraftError("Saved project could not be verified from the local project store.")
        return saved
    except PlantProjectDraftError as exc:
        raise MvpSingleGenePersistenceError("保存设计失败，请检查本地记录目录。") from exc


def list_mvp_single_gene_designs(
    *, repository: PlantProjectDraftRepository | None = None
) -> list[PlantProjectDraftSummary]:
    """List only valid MVP save records from the shared R224 repository."""
    repo = repository or PlantProjectDraftRepository()
    designs: list[PlantProjectDraftSummary] = []
    for summary in repo.list_summaries():
        try:
            draft = repo.load(summary.project_id)
            _validate_reopened_design(draft)
        except (PlantProjectDraftError, MvpSingleGenePersistenceError):
            continue
        designs.append(summary)
    return designs


def open_mvp_single_gene_design(
    project_id: str, *, repository: PlantProjectDraftRepository | None = None
) -> dict[str, Any]:
    """Open and validate persisted bytes; this deliberately never regenerates the design."""
    repo = repository or PlantProjectDraftRepository()
    try:
        draft = repo.load(project_id)
        require_active_project(draft)
    except PlantProjectDraftError as exc:
        if "does not allow editing or saving" in str(exc):
            raise MvpSingleGenePersistenceError(
                "Project lifecycle status does not allow editing or saving."
            ) from exc
        raise MvpSingleGenePersistenceError("保存的设计不存在或无法读取。") from exc
    from services.single_gene_assisted_components import validate_single_gene_assisted_result

    reopened = _validate_reopened_design(draft)
    validate_single_gene_assisted_result(reopened, repository=repo)
    return reopened


def delete_mvp_single_gene_design(
    project_id: str, *, repository: PlantProjectDraftRepository | None = None
) -> None:
    """Delete one validated MVP design through the existing R224 repository."""
    repo = repository or PlantProjectDraftRepository()
    try:
        draft = repo.load(project_id)
        _validate_reopened_design(draft)
        repo.delete(project_id)
    except PlantProjectDraftError as exc:
        raise MvpSingleGenePersistenceError("保存的设计不存在或无法删除。") from exc
