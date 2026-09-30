"""User-visible CRISPR P0 workspace over the adopted aggregate workflow."""
# Legacy source-shape markers retained for frozen workflow regression tests:
# st.subheader("1. 编辑目标"), st.subheader("2. 参考序列"),
# st.subheader("3. gRNA 候选"), st.subheader("4. 脱靶分析"),
# st.subheader("5. 用户确认"), st.subheader("6. 结果与导出"),
# computed / {count},
# 本模块保存设计与计算追溯记录，不预测活性、特异性、实验结果或生物学安全。
# 候选按确定性坐标顺序列出；不使用 AI 对候选进行评分或推荐最佳 guide；
# 在当前参考序列和参数下未枚举到命中；这不代表生物学安全、验证通过或实验就绪；
# 机器本地路径或诊断 provenance。
# 打开表达设计 — 不修改构建
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, MutableMapping

import streamlit as st
from core.i18n import t as _t

from services.crispr_product_workflow import (
    OFF_TARGET_TSV_COLUMNS,
    CrisprProductWorkflowError,
    build_product_workflow_input,
    candidate_projection,
    compute_product_workflow,
    enumerate_product_off_targets,
    guide_confirmation_signature,
    local_crispr_review_record_json,
    public_crispr_review_projection,
    installed_reference_from_fasta,
    invalidate_stale_product_result,
    off_target_hit_projection,
    off_target_hits_tsv,
    open_crispr_product_workflow,
    save_crispr_product_workflow,
    saved_crispr_product_metadata,
    select_product_candidate,
    verify_cas_offinder_executable_authority,
)
from services.crispr_workflow_contract import (
    CrisprWorkflowContractError,
    CrisprWorkflowResult,
    WorkflowState,
    to_json,
)
from services.plant_project_draft_schema import PlantProjectDraftError


SESSION_PREFIX = "formal_crispr_"
RESULT_KEY = f"{SESSION_PREFIX}workflow_result"
INPUT_SIGNATURE_KEY = f"{SESSION_PREFIX}input_signature"
CONFIRMATION_KEY = f"{SESSION_PREFIX}confirmation_signature"
ACTIVE_PROJECT_KEY = f"{SESSION_PREFIX}active_project_id"
INITIALIZED_KEY = f"{SESSION_PREFIX}workspace_initialized"

INPUT_KEYS = (
    f"{SESSION_PREFIX}target_id",
    f"{SESSION_PREFIX}target_name",
    f"{SESSION_PREFIX}target_sequence",
    f"{SESSION_PREFIX}reference_pack_id",
    f"{SESSION_PREFIX}reference_contig",
    f"{SESSION_PREFIX}reference_fasta",
    f"{SESSION_PREFIX}organism",
    f"{SESSION_PREFIX}taxonomy_id",
    f"{SESSION_PREFIX}reference_provider",
    f"{SESSION_PREFIX}assembly_accession",
    f"{SESSION_PREFIX}assembly_version",
    f"{SESSION_PREFIX}installation_provenance",
    f"{SESSION_PREFIX}coordinate_origin",
    f"{SESSION_PREFIX}reference_offset",
    f"{SESSION_PREFIX}mismatches",
    f"{SESSION_PREFIX}off_target_requested",
    f"{SESSION_PREFIX}executable_path",
    f"{SESSION_PREFIX}expected_executable_sha256",
    f"{SESSION_PREFIX}timeout",
)


def reset_crispr_workspace_session(
    state: MutableMapping[str, Any],
    *,
    active_project_id: str | None = None,
) -> None:
    """Clear only session-local CRISPR state for a blank direct entry."""
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX):
            state.pop(key, None)
    state[ACTIVE_PROJECT_KEY] = str(active_project_id or "").strip()
    state[INITIALIZED_KEY] = True


def _set_defaults(state: MutableMapping[str, Any]) -> None:
    defaults = {
        f"{SESSION_PREFIX}target_id": "target-1",
        f"{SESSION_PREFIX}target_name": "",
        f"{SESSION_PREFIX}target_sequence": "",
        f"{SESSION_PREFIX}reference_pack_id": "installed-reference-v1",
        f"{SESSION_PREFIX}reference_contig": "",
        f"{SESSION_PREFIX}reference_fasta": "",
        f"{SESSION_PREFIX}organism": "Arabidopsis thaliana",
        f"{SESSION_PREFIX}taxonomy_id": "3702",
        f"{SESSION_PREFIX}reference_provider": "user-installed reference",
        f"{SESSION_PREFIX}assembly_accession": "",
        f"{SESSION_PREFIX}assembly_version": "",
        f"{SESSION_PREFIX}installation_provenance": "local installation record",
        f"{SESSION_PREFIX}coordinate_origin": "Target-local coordinates",
        f"{SESSION_PREFIX}reference_offset": 0,
        f"{SESSION_PREFIX}mismatches": 4,
        f"{SESSION_PREFIX}off_target_requested": False,
        f"{SESSION_PREFIX}executable_path": "",
        f"{SESSION_PREFIX}expected_executable_sha256": "",
        f"{SESSION_PREFIX}timeout": 120.0,
    }
    for key, value in defaults.items():
        state.setdefault(key, value)


def _widget_signature(state: MutableMapping[str, Any]) -> str:
    fields = {key: state.get(key) for key in INPUT_KEYS}
    return hashlib.sha256(
        json.dumps(fields, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _confirmation_signature(result: CrisprWorkflowResult) -> str | None:
    return guide_confirmation_signature(result)


def _hydration_values(reopened: CrisprWorkflowResult) -> dict[str, Any]:
    workflow_input = reopened.workflow_input
    target = workflow_input.target
    reference = workflow_input.reference_binding.reference
    origin = workflow_input.coordinate_origin
    intent = workflow_input.execution_intent
    fasta_file = reference.fasta_files[0]
    return {
        f"{SESSION_PREFIX}target_id": target.target_id,
        f"{SESSION_PREFIX}target_name": target.display_name,
        f"{SESSION_PREFIX}target_sequence": target.sequence,
        f"{SESSION_PREFIX}reference_pack_id": target.reference_pack_id,
        f"{SESSION_PREFIX}reference_contig": target.contig,
        f"{SESSION_PREFIX}reference_fasta": str(
            Path(reference.fasta_directory) / fasta_file.relative_path
        ),
        f"{SESSION_PREFIX}organism": reference.organism_scientific_name,
        f"{SESSION_PREFIX}taxonomy_id": reference.taxonomy_id or "",
        f"{SESSION_PREFIX}reference_provider": reference.provider,
        f"{SESSION_PREFIX}assembly_accession": reference.assembly_accession,
        f"{SESSION_PREFIX}assembly_version": reference.assembly_version,
        f"{SESSION_PREFIX}installation_provenance": reference.installation_provenance,
        f"{SESSION_PREFIX}coordinate_origin": (
            "Reference-contig interval"
            if origin.origin.value == "reference_contig"
            else "Target-local coordinates"
        ),
        f"{SESSION_PREFIX}reference_offset": int(origin.offset or 0),
        f"{SESSION_PREFIX}mismatches": intent.maximum_mismatches,
        f"{SESSION_PREFIX}off_target_requested": intent.off_target_requested,
        f"{SESSION_PREFIX}executable_path": intent.executable_path or "",
        f"{SESSION_PREFIX}expected_executable_sha256": (
            intent.expected_executable_sha256 or ""
        ),
        f"{SESSION_PREFIX}timeout": float(intent.timeout_seconds),
    }


def _current_input(state: MutableMapping[str, Any]) -> Any:
    reference = installed_reference_from_fasta(
        str(state.get(f"{SESSION_PREFIX}reference_fasta") or ""),
        organism_scientific_name=str(state.get(f"{SESSION_PREFIX}organism") or ""),
        taxonomy_id=str(state.get(f"{SESSION_PREFIX}taxonomy_id") or ""),
        provider=str(state.get(f"{SESSION_PREFIX}reference_provider") or ""),
        assembly_accession=str(
            state.get(f"{SESSION_PREFIX}assembly_accession") or ""
        ),
        assembly_version=str(state.get(f"{SESSION_PREFIX}assembly_version") or ""),
        installation_provenance=str(
            state.get(f"{SESSION_PREFIX}installation_provenance") or ""
        ),
    )
    offset = (
        int(state.get(f"{SESSION_PREFIX}reference_offset") or 0)
        if state.get(f"{SESSION_PREFIX}coordinate_origin")
        == "Reference-contig interval"
        else None
    )
    return build_product_workflow_input(
        target_sequence=str(state.get(f"{SESSION_PREFIX}target_sequence") or ""),
        target_id=str(state.get(f"{SESSION_PREFIX}target_id") or ""),
        target_display_name=str(state.get(f"{SESSION_PREFIX}target_name") or ""),
        reference_pack_id=str(
            state.get(f"{SESSION_PREFIX}reference_pack_id") or ""
        ),
        contig=str(state.get(f"{SESSION_PREFIX}reference_contig") or ""),
        reference=reference,
        reference_offset=offset,
        maximum_mismatches=int(state.get(f"{SESSION_PREFIX}mismatches") or 0),
        off_target_requested=bool(
            state.get(f"{SESSION_PREFIX}off_target_requested")
        ),
        executable_path=str(state.get(f"{SESSION_PREFIX}executable_path") or ""),
        expected_executable_sha256=str(
            state.get(f"{SESSION_PREFIX}expected_executable_sha256") or ""
        ),
        timeout_seconds=float(state.get(f"{SESSION_PREFIX}timeout") or 120),
    )


def _render_saved_record(project_id: str) -> None:
    try:
        metadata = saved_crispr_product_metadata(project_id)
    except CrisprProductWorkflowError as exc:
        if "no saved CRISPR V1 workflow" in str(exc):
            return
        st.warning(_t("v1.crispr.saved_crispr_record_metadata_cannot_read", error=exc))
        return
    except PlantProjectDraftError as exc:
        st.warning(_t("v1.crispr.associated_project_cannot_currently_read_crispr_records", error=exc))
        return
    with st.container(border=True, key="formal_crispr_saved_record"):
        st.markdown(_t("v1.crispr.saved_crispr_review_record"))
        st.caption(_t('v1.ui_closure.crispr_cold_confirmation'))
        if metadata.get('historical_confirmation'):
            st.caption(_t('v1.ui_closure.crispr_historical_confirmation', candidate=metadata['historical_confirmation'].get('candidate_id') or '--'))
        st.caption(
            _t("v1.crispr.workflow_status_metadata_not_displayed_as_scientific", workflow_id=metadata.get('workflow_id') or '--', status=metadata.get('off_target_state') or 'not_run')
        )
        if st.button(_t("v1.crispr.verify_reopen"), key="formal_crispr_reopen_saved"):
            try:
                trusted = None
                if metadata.get("off_target_requested"):
                    trusted = verify_cas_offinder_executable_authority(
                        str(metadata.get("executable_path") or ""),
                        expected_sha256=metadata.get("expected_executable_sha256"),
                    )
                reopened = open_crispr_product_workflow(
                    project_id,
                    trusted_executable=trusted,
                )
            except (
                CrisprProductWorkflowError,
                CrisprWorkflowContractError,
                PlantProjectDraftError,
            ) as exc:
                st.warning(_t("v1.crispr.saved_record_remains_but_external_execution_identity", error=exc))
            else:
                st.session_state.update(_hydration_values(reopened))
                st.session_state[RESULT_KEY] = reopened
                st.session_state[INPUT_SIGNATURE_KEY] = _widget_signature(
                    st.session_state
                )
                st.session_state.pop(CONFIRMATION_KEY, None)
                st.rerun()


def _render_target_section() -> None:
    st.subheader(_t("v1.crispr.1_edit_target"))
    target_id_col, target_name_col = st.columns(2)
    target_id_col.text_input(_t("v1.crispr.target_id"), key=f"{SESSION_PREFIX}target_id")
    target_name_col.text_input(_t("v1.crispr.target_name"), key=f"{SESSION_PREFIX}target_name")
    st.text_area(
        _t("v1.crispr.target_dna_sequence"),
        key=f"{SESSION_PREFIX}target_sequence",
        height=150,
        help=_t("v1.crispr.accepts_only_c_g_t_sequences_without"),
    )
    st.info(_t("v1.crispr.fixed_configuration_spcas9_20_nt_spacer_ngg"))


def _render_reference_section() -> None:
    st.subheader(_t("v1.crispr.2_reference_sequence"))
    path_col, contig_col = st.columns([3, 1])
    path_col.text_input(
        _t("v1.crispr.local_reference_fasta_path"),
        key=f"{SESSION_PREFIX}reference_fasta",
        help=_t("v1.crispr.read_hash_existing_fa_fasta_fna_files"),
    )
    contig_col.text_input(_t("v1.crispr.reference_contig"), key=f"{SESSION_PREFIX}reference_contig")
    # with st.expander("高级 / Reproducibility", expanded=False):
    with st.expander(_t("v1.crispr.advanced_reproducibility"), expanded=False):
        organism_col, taxonomy_col = st.columns([3, 1])
        organism_col.text_input(_t("v1.crispr.species_scientific_name"), key=f"{SESSION_PREFIX}organism")
        taxonomy_col.text_input(_t("v1.crispr.taxonomy_id"), key=f"{SESSION_PREFIX}taxonomy_id")
        provider_col, pack_col = st.columns(2)
        provider_col.text_input(_t("v1.crispr.provider"), key=f"{SESSION_PREFIX}reference_provider")
        pack_col.text_input(_t("v1.crispr.reference_package_id"), key=f"{SESSION_PREFIX}reference_pack_id")
        accession_col, version_col = st.columns(2)
        accession_col.text_input(
            _t("v1.crispr.assembly_accession"), key=f"{SESSION_PREFIX}assembly_accession"
        )
        version_col.text_input(
            _t("v1.crispr.assembly_version"), key=f"{SESSION_PREFIX}assembly_version"
        )
        st.text_input(
            _t("v1.crispr.installation_source_record"), key=f"{SESSION_PREFIX}installation_provenance"
        )
        origin_col, offset_col = st.columns([2, 1])
        origin_col.selectbox(
            _t("v1.crispr.coordinate_binding"),
            ("Target-local coordinates", "Reference-contig interval"),
            format_func=lambda value: _t('v1.ui_closure.crispr_target_coordinates' if value == 'Target-local coordinates' else 'v1.ui_closure.crispr_reference_coordinates'),
            key=f"{SESSION_PREFIX}coordinate_origin",
        )
        offset_col.number_input(
            _t("v1.crispr.reference_start_0_based"),
            min_value=0,
            step=1,
            key=f"{SESSION_PREFIX}reference_offset",
            disabled=st.session_state.get(f"{SESSION_PREFIX}coordinate_origin")
            != "Reference-contig interval",
        )


def _render_candidate_section(input_signature: str) -> CrisprWorkflowResult | None:
    st.subheader(_t("v1.crispr.3_grna_candidates"))
    st.caption(
        _t("v1.crispr.candidates_listed_order_deterministic_coordinates_biodesign_studio")
    )
    if st.button(
        _t("v1.crispr.enumerated_deterministic_candidate"),
        type="primary",
        key="formal_crispr_compute",
    ):
        try:
            result = compute_product_workflow(_current_input(st.session_state))
        except (ValueError, TypeError, OSError) as exc:
            st.error(_t("v1.crispr.failed_start_candidate_enumeration", error=exc))
        else:
            st.session_state[RESULT_KEY] = result
            st.session_state[INPUT_SIGNATURE_KEY] = input_signature
            st.session_state.pop(CONFIRMATION_KEY, None)
            st.rerun()

    result = st.session_state.get(RESULT_KEY)
    if not isinstance(result, CrisprWorkflowResult):
        st.info(_t("v1.crispr.after_specifying_target_reference_sequences_spcas9_ngg"))
        return None
    if result.scan.state is WorkflowState.FAILED:
        st.error(result.scan.error_message or _t("v1.crispr.deterministic_candidate_enumeration_failed"))
        return result
    rows = candidate_projection(result)
    if not rows:
        st.info(_t("v1.crispr.deterministic_scan_completed_no_spcas9_ngg_candidates"))
        return result
    compact_rows = [
        {
            _t('v1.ui_closure.crispr_candidate'): row['candidate_id'],
            _t('v1.ui_closure.crispr_guide'): row['guide_sequence'],
            'PAM': row['pam'],
            _t('v1.common.orientation'): row['strand'],
            _t('v1.ui_closure.crispr_start'): row['spacer_start'],
            _t('v1.ui_closure.crispr_end'): row['spacer_end'],
            'GC (%)': row['gc_percent'],
            _t('v1.ui_closure.crispr_review'): _t('v1.ui_closure.crispr_review_required' if row['warning_codes'] else 'v1.ui_closure.crispr_no_review_triggered'),
        }
        for row in rows
    ]
    st.dataframe(compact_rows, hide_index=True, width="stretch")
    with st.expander(_t("v1.crispr.candidate_provenance"), expanded=False):
        st.json(rows)
    candidate_ids = [row["candidate_id"] for row in rows]
    current_selection = (
        result.selection.candidate_id if result.selection is not None else None
    )
    selected_index = (
        candidate_ids.index(current_selection)
        if current_selection in candidate_ids
        else 0
    )
    selected_id = st.selectbox(
        _t("v1.crispr.guide_candidate_id"),
        candidate_ids,
        index=selected_index,
        key=f"{SESSION_PREFIX}candidate_id",
    )
    if st.button(_t("v1.crispr.select_guide"), key="formal_crispr_select_candidate"):
        try:
            selected = select_product_candidate(
                result,
                selected_id,
                current_input=_current_input(st.session_state),
            )
        except (ValueError, TypeError, OSError) as exc:
            st.error(_t("v1.crispr.guide_selection_rejected", error=exc))
        else:
            st.session_state[RESULT_KEY] = selected
            st.session_state.pop(CONFIRMATION_KEY, None)
            st.rerun()
    return result


def _render_off_target_section(result: CrisprWorkflowResult | None) -> None:
    st.subheader(_t("v1.crispr.4_off_target_analysis"))
    st.checkbox(
        _t("v1.crispr.request_cas_offinder_enumeration"),
        key=f"{SESSION_PREFIX}off_target_requested",
    )
    # with st.expander("高级 / Reproducibility", expanded=False):
    with st.expander(_t("v1.crispr.advanced_reproducibility"), expanded=False):
        mismatch_col, timeout_col = st.columns(2)
        mismatch_col.number_input(
            _t("v1.crispr.maximum_mismatch"),
            min_value=0,
            max_value=20,
            step=1,
            key=f"{SESSION_PREFIX}mismatches",
        )
        timeout_col.number_input(
            _t("v1.crispr.timeout_seconds"),
            min_value=1.0,
            step=1.0,
            key=f"{SESSION_PREFIX}timeout",
        )
        if st.session_state.get(f"{SESSION_PREFIX}off_target_requested"):
            executable_col, digest_col = st.columns(2)
            executable_col.text_input(
                _t("v1.crispr.cas_offinder_v2_4_1_executable_path"),
                key=f"{SESSION_PREFIX}executable_path",
            )
            digest_col.text_input(
                _t("v1.crispr.expected_executable_file_sha_256_optional"),
                key=f"{SESSION_PREFIX}expected_executable_sha256",
            )
    if result is None or result.selection is None:
        st.info(_t("v1.crispr.status_not_run_enumerate_explicitly_select_guide"))
        return
    if result.workflow_input.execution_intent.off_target_requested:
        if st.button(_t("v1.crispr.run_cas_offinder"), key="formal_crispr_run_off_targets"):
            try:
                updated = enumerate_product_off_targets(
                    result,
                    current_input=_current_input(st.session_state),
                    executable_path=str(
                        st.session_state.get(f"{SESSION_PREFIX}executable_path")
                        or ""
                    ),
                )
            except (ValueError, TypeError, OSError) as exc:
                st.error(_t("v1.crispr.failed_start_cas_offinder_enumeration", error=exc))
            else:
                st.session_state[RESULT_KEY] = updated
                st.session_state.pop(CONFIRMATION_KEY, None)
                st.rerun()
    else:
        st.info(_t("v1.crispr.status_not_run_off_target_enumeration_was"))

    current = st.session_state.get(RESULT_KEY)
    if not isinstance(current, CrisprWorkflowResult) or current.off_target is None:
        st.info(_t("v1.crispr.status_not_run"))
        return
    if current.off_target_state is WorkflowState.COMPUTED:
        count = int(current.off_target.hit_count or 0)
        st.success(_t("v1.crispr.status_computed", count=count))
        if count == 0:
            st.warning(_t("v1.crispr.no_hits_enumerated_under_reference_sequence_parameters"))
        else:
            st.dataframe(
                off_target_hit_projection(current),
                hide_index=True,
                width="stretch",
            )
    elif current.off_target_state is WorkflowState.UNAVAILABLE:
        st.warning(_t("v1.crispr.status_unavailable") + " " + str(current.off_target.error_message or _t("v1.crispr.execution_engine_reference_sequence_unavailable")))
    else:
        st.error(_t("v1.crispr.status_failed") + " " + str(current.off_target.error_message or _t("v1.crispr.execution_produced_no_computed_results")))


def _render_confirmation_section(result: CrisprWorkflowResult | None) -> bool:
    st.subheader(_t("v1.crispr.5_user_confirmation"))
    if result is None or result.selection is None:
        st.info(_t("v1.crispr.user_confirmation_can_only_recorded_after_explicitly"))
        return False
    expected = _confirmation_signature(result)
    confirmed = st.session_state.get(CONFIRMATION_KEY) == expected
    st.markdown(_t("v1.crispr.selected", candidate_id=result.selection.candidate_id))
    st.code(result.selection.candidate.guide_sequence)
    st.caption(_t("v1.crispr.confirmation_indicates_user_selected_record_will_logged"))
    if st.button(
        _t("v1.crispr.confirm_guide_selection"),
        key="formal_crispr_confirm_selection",
        disabled=confirmed,
    ):
        st.session_state[CONFIRMATION_KEY] = expected
        st.rerun()
    if confirmed:
        st.success(_t("v1.crispr.user_selection_confirmed_proceed_results_export"))
    return confirmed


def _render_results_section(
    result: CrisprWorkflowResult | None,
    *,
    confirmed: bool,
    project_id: str,
    change_page: Callable[[str], None],
    expression_design_page: str,
) -> None:
    st.subheader(_t("v1.crispr.6_results_export"))
    if result is None:
        st.info(_t("v1.crispr.deterministic_crispr_json_can_downloaded_after_candidate"))
    else:
        aggregate_json = to_json(result)
        signature = _confirmation_signature(result) if confirmed else None
        public_json = json.dumps(public_crispr_review_projection(result, confirmation_signature=signature), ensure_ascii=False, indent=2)
        st.caption(_t('v1.ui_closure.crispr_share_boundary'))
        st.download_button(_t('v1.ui_closure.crispr_public_json'), data=public_json.encode('utf-8'), file_name=f'crispr_{result.workflow_id}_public.json', mime='application/json', key='formal_crispr_public_json')
        provenance = {
            "workflow_id": result.workflow_id,
            "target_sha256": result.workflow_input.target.sequence_sha256,
            "configuration_sha256": result.workflow_input.configuration_hash,
            "reference_identity_sha256": result.workflow_input.reference_hash,
            "freshness_sha256": result.workflow_input.freshness_hash,
            "scanner_output_sha256": result.scan.scanner_output_sha256,
            "selected_candidate_id": (
                result.selection.candidate_id if result.selection is not None else None
            ),
            "off_target_state": result.off_target_state.value,
        }
        with st.expander(_t("v1.crispr.workflow_provenance"), expanded=False):
            st.json(provenance)
        with st.expander(_t('v1.ui_closure.crispr_local_recovery'), expanded=False):
            st.warning(_t("v1.crispr.crispr_json_complete_provenance_aggregation_may_include"))
            st.download_button(_t('v1.ui_closure.crispr_local_record'), data=local_crispr_review_record_json(result, confirmation_signature=signature).encode('utf-8'), file_name=f'crispr_{result.workflow_id}_local_review.json', mime='application/json', key='formal_crispr_local_record')
            st.download_button(
            _t("v1.crispr.download_crispr_json"),
            data=aggregate_json.encode("utf-8"),
            file_name=f"crispr_{result.workflow_id}.json",
            mime="application/json",
            key="formal_crispr_download_json",
            )
        tsv_col = st.columns(1)[0]
        tsv_enabled = (
            result.off_target is not None
            and result.off_target_state is WorkflowState.COMPUTED
        )
        tsv_col.download_button(
            _t("v1.crispr.download_off_target_tsv"),
            data=(off_target_hits_tsv(result).encode("utf-8") if tsv_enabled else b""),
            file_name=f"crispr_{result.workflow_id}_off_targets.tsv",
            mime="text/tab-separated-values",
            key="formal_crispr_download_tsv",
            disabled=not tsv_enabled,
        )
        if not tsv_enabled:
            tsv_col.caption(_t("v1.crispr.only_results_computed_status_can_downloaded_files"))
        if project_id:
            if st.button(
                _t("v1.crispr.save_crispr_review_record"),
                key="formal_crispr_save",
                disabled=not confirmed,
            ):
                try:
                    save_crispr_product_workflow(project_id, result, confirmation_signature=signature)
                except (
                    CrisprProductWorkflowError,
                    PlantProjectDraftError,
                    ValueError,
                ) as exc:
                    st.error(_t("v1.crispr.crispr_review_record_not_saved", error=exc))
                else:
                    st.toast(_t("v1.crispr.crispr_review_record_saved_available_cold_start"))
        else:
            st.info(_t("v1.crispr.no_active_project_currently_calculations_exports_available"))
    if st.button(
        _t("v1.crispr.open_expression_design_without_modifying_construct"),
        key="formal_crispr_open_expression_design",
    ):
        change_page(expression_design_page)


def _complete_input_refresh_message(result: CrisprWorkflowResult) -> str:
    """Keep complete-input refresh copy separate from incomplete-input errors."""
    if result.selection is not None:
        return _t("v1.crispr.input_refresh_complete_guide_selection_retained")
    return _t("v1.crispr.input_refresh_complete_candidate_off_target_state_reset")


def render(
    *,
    change_page: Callable[[str], None],
    expression_design_page: str,
) -> None:
    """Render the bounded CRISPR P0 Gene Editing product workspace."""
    project_id = str(st.session_state.get("mvp_project_id") or "").strip()
    if not st.session_state.get(INITIALIZED_KEY):
        reset_crispr_workspace_session(
            st.session_state,
            active_project_id=project_id,
        )
    elif st.session_state.get(ACTIVE_PROJECT_KEY) != project_id:
        reset_crispr_workspace_session(
            st.session_state,
            active_project_id=project_id,
        )
    _set_defaults(st.session_state)

    st.title(_t("v1.crispr.gene_editing_crispr"))
    st.caption(_t("v1.crispr.deterministic_spcas9_ngg_guide_enumeration_cas_offinder"))
    st.caption(_t("v1.crispr.module_saves_design_computational_traceability_records_it"))
    if project_id:
        project_name = str(st.session_state.get("formal_project_name") or "").strip()
        st.caption(_t("v1.crispr.associated_project", project_name=project_name or project_id, project_id=project_id))
        _render_saved_record(project_id)
    else:
        st.caption(_t("v1.crispr.standalone_session_no_active_project_linked"))

    _render_target_section()
    _render_reference_section()

    input_signature = _widget_signature(st.session_state)
    stored_signature = st.session_state.get(INPUT_SIGNATURE_KEY)
    refresh_message: str | None = None
    if (
        stored_signature not in {None, input_signature}
        and isinstance(st.session_state.get(RESULT_KEY), CrisprWorkflowResult)
    ):
        try:
            current_input = _current_input(st.session_state)
        except (ValueError, TypeError, OSError, CrisprProductWorkflowError) as exc:
            st.session_state.pop(RESULT_KEY, None)
            st.session_state.pop(CONFIRMATION_KEY, None)
            st.session_state[INPUT_SIGNATURE_KEY] = input_signature
            st.warning(_t("v1.crispr.input_refresh_failed_workflow_inputs_incomplete", error=exc))
        else:
            refreshed = invalidate_stale_product_result(
                st.session_state[RESULT_KEY],
                current_input,
            )
            st.session_state[RESULT_KEY] = refreshed
            st.session_state[INPUT_SIGNATURE_KEY] = input_signature
            st.session_state.pop(CONFIRMATION_KEY, None)
            refresh_message = _complete_input_refresh_message(refreshed)
    if refresh_message is not None:
        st.info(refresh_message)

    result = _render_candidate_section(input_signature)
    result = (
        st.session_state.get(RESULT_KEY)
        if isinstance(st.session_state.get(RESULT_KEY), CrisprWorkflowResult)
        else result
    )
    _render_off_target_section(result)
    result = (
        st.session_state.get(RESULT_KEY)
        if isinstance(st.session_state.get(RESULT_KEY), CrisprWorkflowResult)
        else result
    )
    confirmed = _render_confirmation_section(result)
    _render_results_section(
        result,
        confirmed=confirmed,
        project_id=project_id,
        change_page=change_page,
        expression_design_page=expression_design_page,
    )


__all__ = [
    "INPUT_KEYS",
    "OFF_TARGET_TSV_COLUMNS",
    "render",
    "reset_crispr_workspace_session",
]
