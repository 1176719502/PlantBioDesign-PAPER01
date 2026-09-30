"""Formal three-page UI for the plant single-gene plasmid design record."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    export_active_construct,
)
from services.mvp_cds_input import analyze_cds_input
from services.mvp_company_review_package import MvpCompanyReviewPackageError
from services.mvp_sequence_input import (
    DNA_FILE_SUFFIXES,
    GENBANK_FILE_SUFFIXES,
    MvpSequenceInputError,
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
    decode_uploaded_text,
)
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    delete_mvp_single_gene_design,
    list_mvp_single_gene_designs,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_schema import new_project_id

from services.formal_single_gene_runtime import (
    CASE_FILES,
    COMPONENT_NAMES,
    DEFAULT_PROJECT_NAME,
    _backbone_record_from_example,
    _cds_record,
    _component_record_from_example,
    cassette_input_signature,
    construct_input_signature,
    generate_complete_vector,
    generate_expression_cassette,
    generation_input_signature,
    load_real_case,
    real_case_cds_input,
)
from views.formal_construct_findings import _render_findings


PAGE_HOME = "home"
PAGE_DESIGN = "design"
PAGE_RESULTS = "results"
DNA_SOURCE_OPTIONS = ["粘贴 DNA/FASTA", "上传 FASTA", "使用示例"]
BACKBONE_SOURCE_OPTIONS = ["上传 GenBank", "使用示例骨架"]


def _uploaded_cds_input(uploaded: Any) -> dict[str, Any]:
    try:
        raw_text = decode_uploaded_text(
            uploaded.getvalue(),
            file_name=str(uploaded.name),
            allowed_suffixes=DNA_FILE_SUFFIXES,
        )
    except MvpSequenceInputError as exc:
        return {
            "source_kind": "upload",
            "source_name": str(uploaded.name),
            "normalized_cds": "",
            "normalized_length": 0,
            "findings": [{"rule_id": "upload_error", "message": str(exc), "blocking": True}],
            "blocking": True,
            "original_text": "",
            "original_text_sha256": "",
        }
    return analyze_cds_input(raw_text, source_kind="upload", source_name=str(uploaded.name))


def _error_record(
    role: str,
    *,
    source_kind: str,
    source_name: str,
    display_name: str,
    raw_text: str,
    error: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "source_kind": source_kind,
        "source_name": source_name,
        "display_name": display_name,
        "original_text": raw_text,
        "normalized_sequence": "",
        "length": 0,
        "error": error,
    }


def _loaded_record(role: str) -> dict[str, Any]:
    return dict((st.session_state.get("mvp_loaded_input_records") or {}).get(role) or {})


def _component_input_ui(
    role: str,
    label: str,
    *,
    project_id: str,
    case: dict[str, str],
) -> dict[str, Any]:
    mode = st.radio(
        f"{label}输入方式",
        DNA_SOURCE_OPTIONS,
        key=f"mvp_{role}_mode",
        horizontal=True,
    )
    name_key = f"mvp_{role}_name"
    st.session_state.setdefault(name_key, COMPONENT_NAMES[role])
    display_name = st.text_input(f"{label}名称", key=name_key)
    raw_text = ""
    source_kind = ""
    source_name = ""
    try:
        if mode == "使用示例":
            record = _component_record_from_example(role, project_id=project_id, case=case) | {
                "display_name": display_name
            }
        elif mode == "粘贴 DNA/FASTA":
            raw_text = st.text_area(
                f"粘贴{label} DNA/FASTA",
                key=f"mvp_{role}_text",
                height=120,
            )
            source_kind, source_name = "paste", f"pasted-{role}"
            record = analyze_dna_component_input(
                raw_text,
                project_id=project_id,
                component_type=role,
                display_name=display_name,
                source_kind=source_kind,
                source_name=source_name,
            )
        else:
            uploaded = st.file_uploader(
                f"上传{label} FASTA",
                type=["fa", "fasta", "fas", "txt"],
                key=f"mvp_{role}_upload",
            )
            if uploaded is None:
                loaded = _loaded_record(role)
                if loaded.get("source_kind") in {"upload", "user_uploaded"}:
                    record = loaded | {"display_name": display_name}
                else:
                    st.info(f"请上传{label} FASTA 文件。")
                    record = _error_record(
                        role,
                        source_kind="upload",
                        source_name="",
                        display_name=display_name,
                        raw_text="",
                        error="尚未上传文件",
                    )
            else:
                raw_text = decode_uploaded_text(
                    uploaded.getvalue(),
                    file_name=str(uploaded.name),
                    allowed_suffixes=DNA_FILE_SUFFIXES,
                )
                source_kind, source_name = "upload", str(uploaded.name)
                record = analyze_dna_component_input(
                    raw_text,
                    project_id=project_id,
                    component_type=role,
                    display_name=display_name,
                    source_kind=source_kind,
                    source_name=source_name,
                )
    except MvpSequenceInputError as exc:
        st.error(f"{label}：{exc}")
        record = _error_record(
            role,
            source_kind=source_kind or mode,
            source_name=source_name,
            display_name=display_name,
            raw_text=raw_text,
            error=str(exc),
        )
    if record.get("normalized_sequence") and not record.get("error"):
        source_name = str(record.get("source_name") or "本地输入")
        st.caption(
            f"名称：{record.get('display_name') or display_name} · 长度：{int(record.get('length') or 0)} bp · "
            f"来源：{source_name} · 软件校验：通过"
        )
    return record


def _current_cds_record_ui(case: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = st.radio("CDS 输入方式", DNA_SOURCE_OPTIONS, key="mvp_cds_mode", horizontal=True)
    st.session_state.setdefault("mvp_cds_name", COMPONENT_NAMES["cds"])
    display_name = st.text_input("CDS 名称", key="mvp_cds_name")
    if mode == "使用示例":
        current = real_case_cds_input(case)
    elif mode == "粘贴 DNA/FASTA":
        pasted = st.text_area("粘贴 CDS DNA/FASTA", key="mvp_cds_text", height=160)
        current = analyze_cds_input(pasted, source_kind="paste", source_name="pasted-cds")
    else:
        uploaded = st.file_uploader(
            "上传 CDS FASTA",
            type=["fa", "fasta", "fas", "txt"],
            key="mvp_cds_upload",
        )
        if uploaded is not None:
            current = _uploaded_cds_input(uploaded)
        else:
            loaded = dict(st.session_state.get("mvp_loaded_cds_input") or {})
            current = (
                loaded
                if loaded.get("source_kind") in {"upload", "user_uploaded"}
                else analyze_cds_input("", source_kind="upload")
            )
    if current.get("blocking"):
        st.error(
            "CDS："
            + "；".join(str(item.get("message") or "") for item in current.get("findings") or [])
        )
    else:
        source_name = str(current.get("source_name") or "本地输入")
        st.caption(
            f"名称：{display_name} · 长度：{int(current.get('normalized_length') or 0)} bp · "
            f"来源：{source_name} · CDS 软件校验：通过"
        )
        for finding in current.get("findings") or []:
            st.warning(str(finding.get("message") or ""))
        if current.get("protein_translation"):
            with st.expander("查看 CDS 翻译提示"):
                st.code(str(current["protein_translation"]), language="text")
    return current, _cds_record(current, display_name=display_name)


def _backbone_input_ui(*, project_id: str, case: dict[str, str]) -> dict[str, Any]:
    mode = st.radio(
        "载体骨架输入方式",
        BACKBONE_SOURCE_OPTIONS,
        key="mvp_backbone_mode",
        horizontal=True,
    )
    st.session_state.setdefault("mvp_backbone_name", "BACKBONE_SYNTH_R229")
    display_name = st.text_input("载体骨架名称", key="mvp_backbone_name")
    record: dict[str, Any]
    if mode == "使用示例骨架":
        try:
            record = _backbone_record_from_example(project_id=project_id, case=case) | {
                "display_name": display_name
            }
        except MvpSequenceInputError as exc:
            st.error(f"载体骨架：{exc}")
            record = _error_record(
                "backbone",
                source_kind="example",
                source_name=CASE_FILES["backbone"],
                display_name=display_name,
                raw_text="",
                error=str(exc),
            )
    else:
        uploaded = st.file_uploader(
            "上传 GenBank 骨架",
            type=["gb", "gbk", "genbank"],
            key="mvp_backbone_upload",
        )
        if uploaded is None:
            loaded = _loaded_record("backbone")
            if loaded.get("source_kind") in {"upload", "user_uploaded"}:
                record = loaded | {"display_name": display_name}
            else:
                st.info("请上传 .gb、.gbk 或 .genbank 骨架文件。")
                record = _error_record(
                    "backbone",
                    source_kind="upload",
                    source_name="",
                    display_name=display_name,
                    raw_text="",
                    error="尚未上传文件",
                )
        else:
            raw_text = ""
            try:
                raw_text = decode_uploaded_text(
                    uploaded.getvalue(),
                    file_name=str(uploaded.name),
                    allowed_suffixes=GENBANK_FILE_SUFFIXES,
                )
                record = analyze_genbank_backbone_input(
                    raw_text,
                    project_id=project_id,
                    display_name=display_name,
                    source_kind="upload",
                    source_name=str(uploaded.name),
                )
            except MvpSequenceInputError as exc:
                st.error(f"载体骨架：{exc}")
                record = _error_record(
                    "backbone",
                    source_kind="upload",
                    source_name=str(uploaded.name),
                    display_name=display_name,
                    raw_text=raw_text,
                    error=str(exc),
                )
    if record.get("normalized_sequence") and not record.get("error"):
        topology = str(record.get("topology") or "未声明")
        source_name = str(record.get("source_name") or "本地输入")
        st.caption(
            f"名称：{record.get('display_name') or display_name} · 长度：{int(record.get('length') or 0)} bp · "
            f"来源：{source_name} · 拓扑：{topology} · 软件解析：通过"
        )
    return record


def _reset_to_blank() -> None:
    for key in list(st.session_state):
        if key.startswith("mvp_"):
            del st.session_state[key]


def _load_all_examples() -> None:
    st.session_state["mvp_promoter_mode"] = "使用示例"
    st.session_state["mvp_cds_mode"] = "使用示例"
    st.session_state["mvp_terminator_mode"] = "使用示例"
    st.session_state["mvp_backbone_mode"] = "使用示例骨架"
    st.session_state["mvp_insertion_mode"] = "插入"
    st.session_state["mvp_start_coordinate"] = 2100
    st.session_state["mvp_end_coordinate"] = 2101
    st.session_state.pop("mvp_vector_result", None)
    st.session_state.pop("mvp_cassette_result", None)


def _mode_for_record(record: dict[str, Any], *, backbone: bool = False) -> str:
    source_kind = str(record.get("source_kind") or "")
    if source_kind == "example":
        return "使用示例骨架" if backbone else "使用示例"
    if source_kind in {"upload", "user_uploaded"}:
        return "上传 GenBank" if backbone else "上传 FASTA"
    return "粘贴 DNA/FASTA"


def _restore_design_input_state(design: dict[str, Any]) -> None:
    records = dict(design.get("input_records") or {})
    st.session_state["mvp_project_id"] = design["project_id"]
    st.session_state["mvp_project_name"] = design["project_name"]
    st.session_state["mvp_loaded_input_records"] = records
    st.session_state["mvp_loaded_cds_input"] = design["cds_input"]
    for role in ("promoter", "terminator"):
        record = dict(records.get(role) or {})
        st.session_state[f"mvp_{role}_mode"] = _mode_for_record(record)
        st.session_state[f"mvp_{role}_name"] = str(
            record.get("display_name") or COMPONENT_NAMES[role]
        )
        if record.get("source_kind") in {"paste", "user_pasted"}:
            st.session_state[f"mvp_{role}_text"] = str(record.get("original_text") or "")
        else:
            st.session_state.pop(f"mvp_{role}_text", None)
    cds_record = dict(records.get("cds") or {})
    st.session_state["mvp_cds_mode"] = _mode_for_record(cds_record)
    st.session_state["mvp_cds_name"] = str(
        cds_record.get("display_name") or COMPONENT_NAMES["cds"]
    )
    if cds_record.get("source_kind") in {"paste", "user_pasted"}:
        st.session_state["mvp_cds_text"] = str(cds_record.get("original_text") or "")
    else:
        st.session_state.pop("mvp_cds_text", None)
    backbone = dict(records.get("backbone") or {})
    st.session_state["mvp_backbone_mode"] = _mode_for_record(backbone, backbone=True)
    st.session_state["mvp_backbone_name"] = str(backbone.get("display_name") or "Backbone")
    settings = dict(design.get("insertion_settings") or {})
    st.session_state["mvp_insertion_mode"] = (
        "替换区间" if settings.get("mode") == "replacement" else "插入"
    )
    st.session_state["mvp_start_coordinate"] = int(settings.get("start_coordinate") or 1)
    st.session_state["mvp_end_coordinate"] = int(settings.get("end_coordinate") or 2)
    st.session_state["mvp_expected_removed_sequence"] = str(
        settings.get("expected_removed_sequence") or ""
    )
    st.session_state["mvp_topology_confirmation"] = bool(
        settings.get("topology_confirmation")
    )


def _restore_reopened_state(reopened: dict[str, Any]) -> None:
    _restore_design_input_state(reopened)
    st.session_state["mvp_current_input_signature"] = reopened["input_signature"]
    st.session_state["mvp_vector_result"] = reopened
    st.session_state["mvp_cassette_result"] = {
        "runtime": reopened["runtime"],
        "cassette_length": reopened["cassette_length"],
        "validation_summary": active_construct_snapshot(reopened["runtime"])["validation_summary"],
        "input_signature": reopened["input_signature"],
    }
    st.session_state["mvp_inputs_stale"] = False
    st.session_state["mvp_saved_project_id"] = reopened["project_id"]
    st.session_state["mvp_saved_input_signature"] = reopened["input_signature"]
    st.session_state["mvp_design_input_state"] = {
        key: deepcopy(reopened[key])
        for key in (
            "project_id",
            "project_name",
            "input_records",
            "cds_input",
            "insertion_settings",
        )
    }
    st.session_state["mvp_page"] = PAGE_RESULTS


def _navigate(page: str) -> None:
    st.session_state["mvp_page"] = page
    st.rerun()


def _format_updated_at(value: str) -> str:
    normalized = str(value or "").replace("T", " ").replace("Z", "")
    return normalized[:16] or "未知"


def _open_saved_project(project_id: str) -> None:
    try:
        reopened = open_mvp_single_gene_design(project_id)
    except MvpSingleGenePersistenceError as exc:
        st.error(str(exc))
        return
    _restore_reopened_state(reopened)
    st.session_state["mvp_flash_message"] = f"已打开项目：{reopened['project_name']}"
    st.rerun()


def _render_home() -> None:
    st.title("项目首页")
    st.caption("BioDesign Studio 植物表达载体设计")
    flash_message = st.session_state.pop("mvp_flash_message", "")
    if flash_message:
        st.success(flash_message)

    saved_designs = list_mvp_single_gene_designs()
    new_col, example_col, recent_col = st.columns(3)
    if new_col.button("新建空白单基因项目", type="primary"):
        _reset_to_blank()
        st.session_state["mvp_project_id"] = new_project_id()
        st.session_state["mvp_project_name"] = "未命名单基因项目"
        st.session_state["mvp_page"] = PAGE_DESIGN
        st.rerun()
    if example_col.button("加载示例项目"):
        _reset_to_blank()
        _load_all_examples()
        st.session_state["mvp_project_id"] = new_project_id()
        st.session_state["mvp_project_name"] = DEFAULT_PROJECT_NAME
        st.session_state["mvp_page"] = PAGE_DESIGN
        st.rerun()
    if recent_col.button("打开最近项目", disabled=not saved_designs):
        _open_saved_project(saved_designs[0].project_id)

    if st.session_state.get("mvp_project_id"):
        if st.button("进入设计工作区"):
            design_state = st.session_state.get("mvp_design_input_state")
            if design_state:
                _restore_design_input_state(dict(design_state))
            _navigate(PAGE_DESIGN)

    st.subheader("最近项目")
    if not saved_designs:
        st.info("还没有已保存项目。可新建空白项目或加载示例项目开始记录。")
        return

    for summary in saved_designs:
        name_col, time_col, open_col, delete_col = st.columns([4, 2, 1, 1])
        name_col.markdown(f"**{summary.project_name}**")
        time_col.caption(f"最后修改：{_format_updated_at(summary.updated_at)}")
        if open_col.button("打开", key=f"mvp_open_{summary.project_id}"):
            _open_saved_project(summary.project_id)
        if delete_col.button("删除", key=f"mvp_delete_{summary.project_id}"):
            st.session_state["mvp_delete_confirm_project_id"] = summary.project_id
            st.rerun()

    confirm_id = st.session_state.get("mvp_delete_confirm_project_id")
    if confirm_id:
        selected = next((item for item in saved_designs if item.project_id == confirm_id), None)
        if selected is not None:
            st.warning(f"确认删除项目“{selected.project_name}”？此操作会删除该项目的本地保存记录。")
            cancel_col, confirm_col = st.columns(2)
            if cancel_col.button("取消删除"):
                st.session_state.pop("mvp_delete_confirm_project_id", None)
                st.rerun()
            if confirm_col.button("确认删除项目", type="primary"):
                try:
                    delete_mvp_single_gene_design(confirm_id)
                except MvpSingleGenePersistenceError as exc:
                    st.error(str(exc))
                else:
                    deleting_current = confirm_id == st.session_state.get("mvp_project_id")
                    if deleting_current:
                        _reset_to_blank()
                    else:
                        st.session_state.pop("mvp_delete_confirm_project_id", None)
                    st.session_state["mvp_page"] = PAGE_HOME
                    st.session_state["mvp_flash_message"] = f"已删除项目：{selected.project_name}"
                    st.rerun()


def _render_design() -> None:
    nav_col, result_col = st.columns([1, 1])
    if nav_col.button("返回项目首页"):
        _navigate(PAGE_HOME)
    result = st.session_state.get("mvp_vector_result")
    if result_col.button("查看结果", disabled=result is None):
        _navigate(PAGE_RESULTS)

    st.title("设计工作区")
    project_id = str(st.session_state.setdefault("mvp_project_id", new_project_id()))
    st.session_state.setdefault("mvp_project_name", DEFAULT_PROJECT_NAME)
    project_name = st.text_input("项目名称", key="mvp_project_name").strip()
    save_status = (
        "已有本地保存记录"
        if st.session_state.get("mvp_saved_project_id") == project_id
        else "尚未保存"
    )
    if result is None:
        stale_status = "尚未生成完整质粒"
    elif st.session_state.get("mvp_inputs_stale"):
        stale_status = "需要重新生成"
    else:
        stale_status = "当前生成结果可查看"
    st.caption(f"当前项目：{project_name or '未命名项目'} · 保存状态：{save_status} · 生成状态：{stale_status}")

    case = load_real_case()
    st.subheader("启动子")
    promoter = _component_input_ui("promoter", "启动子", project_id=project_id, case=case)

    st.subheader("CDS")
    cds_input, cds_record = _current_cds_record_ui(case)

    st.subheader("终止子")
    terminator = _component_input_ui("terminator", "终止子", project_id=project_id, case=case)

    st.subheader("表达盒")
    st.caption("结构：启动子 → CDS → 终止子")

    st.subheader("载体骨架")
    backbone = _backbone_input_ui(project_id=project_id, case=case)

    st.subheader("插入设置")
    st.session_state.setdefault("mvp_start_coordinate", 1)
    st.session_state.setdefault("mvp_end_coordinate", 2)
    with st.expander("高级设置"):
        insertion_label = st.radio(
            "位置模式",
            ["插入", "替换区间"],
            key="mvp_insertion_mode",
            horizontal=True,
        )
        start_coordinate = st.number_input(
            "起始坐标（1-based）",
            min_value=1,
            step=1,
            key="mvp_start_coordinate",
        )
        end_coordinate = st.number_input(
            "结束坐标（1-based）",
            min_value=1,
            step=1,
            key="mvp_end_coordinate",
        )
        expected_removed = ""
        if insertion_label == "替换区间":
            expected_removed = st.text_input(
                "预期被替换序列（可选）",
                key="mvp_expected_removed_sequence",
            )
        topology_confirmation = st.checkbox(
            "骨架未声明拓扑时，按环状骨架记录",
            key="mvp_topology_confirmation",
        )
    insertion_summary = (
        f"替换区间 {int(start_coordinate)}-{int(end_coordinate)}"
        if insertion_label == "替换区间"
        else f"插入位置 {int(start_coordinate)}"
    )
    st.caption(f"当前设置：{insertion_summary}")

    settings = {
        "mode": "replacement" if insertion_label == "替换区间" else "insertion",
        "start_coordinate": int(start_coordinate),
        "end_coordinate": int(end_coordinate),
        "expected_removed_sequence": expected_removed,
        "topology_confirmation": topology_confirmation,
    }
    records = {
        "promoter": promoter,
        "cds": cds_record,
        "terminator": terminator,
        "backbone": backbone,
    }
    current_signature = generation_input_signature(records, settings, project_name=project_name)
    previous_signature = st.session_state.get("mvp_current_input_signature")
    if previous_signature is not None and previous_signature != current_signature:
        if st.session_state.get("mvp_vector_result") is not None:
            st.session_state["mvp_inputs_stale"] = True
        st.session_state.pop("mvp_cassette_result", None)
        st.session_state.pop("mvp_saved_export_bytes", None)
    st.session_state["mvp_current_input_signature"] = current_signature
    st.session_state["mvp_design_input_state"] = {
        "project_id": project_id,
        "project_name": project_name,
        "input_records": deepcopy(records),
        "cds_input": deepcopy(cds_input),
        "insertion_settings": deepcopy(settings),
    }

    if st.session_state.get("mvp_saved_input_signature") not in (None, current_signature):
        st.caption("保存状态：当前输入包含尚未保存的修改。")
    if st.session_state.get("mvp_inputs_stale"):
        st.warning("核心输入已修改，旧结果已失效。请重新生成完整质粒后再下载。")

    component_records = (promoter, cds_record, terminator)
    components_invalid = any(
        not str(record.get("normalized_sequence") or "") or record.get("error")
        for record in component_records
    ) or bool(cds_input.get("blocking"))
    all_inputs_invalid = components_invalid or not str(backbone.get("normalized_sequence") or "") or bool(backbone.get("error"))

    if st.button("生成表达盒", disabled=components_invalid):
        try:
            cassette_result = generate_expression_cassette(
                cds_input=cds_input,
                input_records=records,
                project_id=project_id,
                project_name=project_name,
                input_signature=current_signature,
            )
        except (RuntimeError, CanonicalConstructRuntimeError, MvpSequenceInputError) as exc:
            st.error(str(exc))
            st.session_state.pop("mvp_cassette_result", None)
        else:
            st.session_state["mvp_cassette_result"] = cassette_result

    cassette_result = st.session_state.get("mvp_cassette_result")
    cassette_current = bool(
        cassette_result and cassette_result.get("input_signature") == current_signature
    )
    if cassette_current:
        summary = dict(cassette_result.get("validation_summary") or {})
        st.success("表达盒记录已生成。")
        st.caption(
            f"启动子 → CDS → 终止子 · 表达盒长度：{cassette_result['cassette_length']} bp · "
            f"错误：{int(summary.get('blocking_count', 0))} · 警告：{int(summary.get('warning_count', 0))}"
        )

    st.subheader("生成完整质粒")
    if st.button(
        "生成完整质粒",
        type="primary",
        disabled=all_inputs_invalid or not cassette_current,
    ):
        try:
            result = generate_complete_vector(
                cds_input=cds_input,
                input_records=records,
                insertion_settings=settings,
                project_id=project_id,
                project_name=project_name,
                input_signature=current_signature,
            )
        except (
            RuntimeError,
            CanonicalConstructRuntimeError,
            MvpSequenceInputError,
            MvpCompanyReviewPackageError,
        ) as exc:
            st.error(str(exc))
        else:
            st.session_state["mvp_vector_result"] = result
            st.session_state["mvp_inputs_stale"] = False
            st.session_state["mvp_page"] = PAGE_RESULTS
            st.rerun()


def _render_results() -> None:
    result = st.session_state.get("mvp_vector_result")
    design_col, home_col = st.columns(2)
    if design_col.button("返回修改设计"):
        design_state = st.session_state.get("mvp_design_input_state") or result
        if design_state:
            _restore_design_input_state(dict(design_state))
        _navigate(PAGE_DESIGN)
    if home_col.button("返回项目首页"):
        _navigate(PAGE_HOME)

    st.title("结果与导出")
    flash_message = st.session_state.pop("mvp_flash_message", "")
    if flash_message:
        st.success(flash_message)
    if not result:
        st.warning("当前项目还没有完整质粒结果，请返回设计工作区生成。")
        return

    current_signature = st.session_state.get("mvp_current_input_signature")
    is_valid = bool(
        not st.session_state.get("mvp_inputs_stale")
        and result.get("input_signature") == current_signature
    )
    project_name = str(result.get("project_name") or st.session_state.get("mvp_project_name") or "未命名项目")
    st.caption(
        f"当前项目：{project_name} · 当前生成结果：{'有效' if is_valid else '已失效，需要重新生成'}"
    )
    if not is_valid:
        st.error("核心输入已修改，当前结果不能继续下载。请返回设计工作区重新生成完整质粒。")

    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    validation = dict(result.get("validation_summary") or {})
    blocking_count = int(validation.get("blocking_count", 0))
    warning_count = int(validation.get("warning_count", 0))
    result_status = "存在阻止错误" if blocking_count else ("软件检查完成，有警告" if warning_count else "软件检查完成")
    settings = dict(result.get("insertion_settings") or {})
    position_text = (
        f"替换 {int(settings.get('start_coordinate') or 0)}-{int(settings.get('end_coordinate') or 0)}"
        if settings.get("mode") == "replacement"
        else f"插入 {int(settings.get('start_coordinate') or 0)}"
    )

    cassette_col, backbone_col, plasmid_col = st.columns(3)
    cassette_col.metric("表达盒长度", f"{int(result.get('cassette_length') or 0)} bp")
    backbone_col.metric("骨架长度", f"{int((result.get('input_lengths') or {}).get('backbone') or 0)} bp")
    plasmid_col.metric("完整质粒长度", f"{int(result.get('plasmid_length') or 0)} bp")
    st.write(f"插入模式和位置：{position_text}")
    st.write(f"生成状态：{result_status}")
    st.markdown("**[启动子] → [CDS] → [终止子]**")

    st.subheader("软件校验结果")
    st.caption("软件状态仅表示输入、序列、结构、坐标、持久化和导出记录检查，不代表生物学效果验证或实验可用性。")
    st.write(f"软件校验通过：{1 if not blocking_count else 0} · 警告：{warning_count} · 错误：{blocking_count}")
    with st.expander("查看完整校验"):
        _render_findings(list(plasmid.get("validation_findings") or []))
    with st.expander("查看元件坐标"):
        for row in list(plasmid.get("feature_rows") or []):
            name = str(row.get("name") or row.get("label") or row.get("feature_type") or "元件")
            st.write(f"{name}：{row.get('start')}–{row.get('end')}")
    with st.expander("查看表达盒序列"):
        st.code(str(cassette.get("sequence") or ""), language="text")
    with st.expander("查看完整质粒序列"):
        st.code(str(plasmid.get("sequence") or ""), language="text")
    with st.expander("查看 CDS 翻译"):
        st.code(str((result.get("cds_input") or {}).get("protein_translation") or "无可显示的翻译记录"), language="text")

    st.subheader("保存与下载")
    complete_exports = dict(result.get("exports") or {})
    complete_fasta = dict(complete_exports.get("fasta") or {})
    complete_genbank = dict(complete_exports.get("genbank") or {})
    package = dict(result.get("company_review_package") or {})
    package_bytes = package.get("data") if isinstance(package.get("data"), bytes) else b""
    validation_complete = isinstance(result.get("validation_summary"), dict)
    core_exports_available = bool(
        complete_fasta.get("data")
        and complete_genbank.get("data")
        and not blocking_count
        and validation_complete
    )
    package_available = bool(
        is_valid
        and core_exports_available
        and package_bytes
        and package.get("sha256")
        and package.get("file_name")
    )
    if is_valid and not package_available:
        st.warning("当前结果缺少完整的公司审查包字节，请重新生成完整质粒。")

    if st.button("保存项目", type="primary", disabled=not package_available):
        try:
            saved = save_mvp_single_gene_design(result)
        except (MvpSingleGenePersistenceError, MvpCompanyReviewPackageError) as exc:
            st.error(str(exc))
        else:
            st.session_state["mvp_saved_project_id"] = saved.project_id
            st.session_state["mvp_saved_input_signature"] = result["input_signature"]
            st.success(f"项目已保存：{saved.project_name}")

    cassette_exports: dict[str, Any] = {}
    if is_valid:
        try:
            cassette_exports = export_active_construct(result["runtime"], project_name=project_name)
        except CanonicalConstructRuntimeError as exc:
            st.error(str(exc))
            is_valid = False

    st.download_button(
        "下载表达盒 FASTA",
        data=((cassette_exports.get("fasta") or {}).get("data") or ""),
        file_name=((cassette_exports.get("fasta") or {}).get("file_name") or "expression_cassette.fasta"),
        mime="text/plain",
        disabled=not is_valid,
        on_click="ignore",
    )
    st.download_button(
        "下载完整质粒 FASTA",
        data=complete_fasta.get("data") or "",
        file_name=complete_fasta.get("file_name") or "complete_plasmid.fasta",
        mime=complete_fasta.get("mime") or "text/plain",
        disabled=not (is_valid and bool(complete_fasta.get("data"))),
        on_click="ignore",
    )
    st.download_button(
        "下载完整质粒 GenBank",
        data=complete_genbank.get("data") or "",
        file_name=complete_genbank.get("file_name") or "complete_plasmid.gb",
        mime=complete_genbank.get("mime") or "text/plain",
        disabled=not (is_valid and bool(complete_genbank.get("data"))),
        on_click="ignore",
    )
    st.caption("用于交给实验人员或公司进行序列审查、报价和构建评估；仍需人工确认实际施工方案。")
    st.download_button(
        "导出公司审查包 ZIP",
        data=package_bytes,
        file_name=str(package.get("file_name") or "BioDesign_Project_company_review_package.zip"),
        mime=str(package.get("mime") or "application/zip"),
        disabled=not package_available,
        on_click="ignore",
    )


def main() -> None:
    st.set_page_config(page_title="BioDesign Studio", layout="wide")
    page = str(st.session_state.setdefault("mvp_page", PAGE_HOME))
    if page == PAGE_DESIGN:
        _render_design()
    elif page == PAGE_RESULTS:
        _render_results()
    else:
        _render_home()


if __name__ == "__main__":
    main()
