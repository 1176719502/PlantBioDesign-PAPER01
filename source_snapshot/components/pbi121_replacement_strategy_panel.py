"""Local Step 4 panel for the manual pBI121 replacement-strategy record."""
from __future__ import annotations

from typing import Any

import streamlit as st

from services.pbi121_replacement_strategy import (
    load_strategy,
    source_audit,
    update_strategy,
    save_strategy,
)


def _feature_label(row: dict[str, Any]) -> str:
    return f"{row['name']} | {row['type']} | {row['location_expression']} | strand {row['strand']}"


def _choice_index(rows: list[dict[str, Any]], feature_id: str) -> int:
    return next((index for index, row in enumerate(rows) if isinstance(row, dict) and row["feature_id"] == feature_id), 0)


def _status_label(status: str) -> str:
    return {
        "draft": "草稿",
        "needs_border_confirmation": "需要边界确认",
        "needs_direction_confirmation": "需要方向确认",
        "needs_region_selection": "需要区域选择",
        "needs_feature_review": "需要 feature 审查",
        "blocked": "已阻断",
        "ready_for_construct_use": "具备后续计算构建条件",
    }.get(status, status)


def render_pbi121_replacement_strategy_panel() -> None:
    """Render manual controls only; this panel never creates a plasmid or export."""
    audit = source_audit()
    record = st.session_state.get("pbi121_replacement_strategy_draft")
    if not isinstance(record, dict):
        record = load_strategy()
        st.session_state["pbi121_replacement_strategy_draft"] = record

    st.subheader("T-DNA 人工替换策略")
    st.caption("这是保存的审查记录；不替换、插入、删除、导出或生成序列数据。")
    st.markdown(f"**pBI121 来源：** {audit['accession']} | {audit['record_name']} | {int(audit['length']):,} bp | `{_status_label(str(record['strategy_status']))}`")

    st.markdown("**1. LB/RB 确认**")
    options = [None, *audit["features"]]
    formatter = lambda row: "请选择来源 feature" if row is None else _feature_label(row)
    borders = st.columns(2)
    lb = borders[0].selectbox(
        "左边界（LB）", options, index=_choice_index(options, str(record.get("confirmed_left_border") or "")),
        format_func=formatter, key="pbi121_strategy_lb",
    )
    rb = borders[1].selectbox(
        "右边界（RB）", options, index=_choice_index(options, str(record.get("confirmed_right_border") or "")),
        format_func=formatter, key="pbi121_strategy_rb",
    )

    st.markdown("**2. 目标 T-DNA 方向**")
    direction_options = ["", "LB_to_RB", "RB_to_LB"]
    direction = st.radio(
        "人工确认的方向", direction_options,
        index=direction_options.index(str(record.get("t_dna_direction") or "")),
        format_func=lambda value: {"": "未确认", "LB_to_RB": "LB -> RB", "RB_to_LB": "RB -> LB"}[value],
        horizontal=True, key="pbi121_strategy_direction",
    )

    st.markdown("**3. 替换区间**")
    input_mode = st.radio("区间输入方式", ["从 feature 边界选择", "精确 1-based 坐标"], horizontal=True, key="pbi121_strategy_interval_mode")
    start, end = record.get("replacement_start"), record.get("replacement_end")
    if input_mode == "从 feature 边界选择":
        boundary_options = [None, *audit["features"]]
        start_feature = st.selectbox("起点 feature 边界", boundary_options, format_func=formatter, key="pbi121_strategy_start_feature")
        end_feature = st.selectbox("终点 feature 边界", boundary_options, format_func=formatter, key="pbi121_strategy_end_feature")
        boundary_cols = st.columns(2)
        start_edge = boundary_cols[0].selectbox("起点边界", ["start", "end"], key="pbi121_strategy_start_edge")
        end_edge = boundary_cols[1].selectbox("终点边界", ["start", "end"], key="pbi121_strategy_end_edge")
        if start_feature is not None:
            start = int(start_feature[f"{start_edge}_one_based" + ("_inclusive" if start_edge == "end" else "")])
        if end_feature is not None:
            end = int(end_feature[f"{end_edge}_one_based" + ("_inclusive" if end_edge == "end" else "")])
    else:
        coordinate_cols = st.columns(2)
        start = coordinate_cols[0].number_input("替换起点（1-based）", min_value=1, max_value=int(audit["length"]), value=int(start or 1), key="pbi121_strategy_start")
        end = coordinate_cols[1].number_input("替换终点（1-based）", min_value=1, max_value=int(audit["length"]), value=int(end or 1), key="pbi121_strategy_end")

    st.markdown("**4. Feature 冲突审查**")
    preview = update_strategy(
        record,
        confirmed_left_border=str((lb or {}).get("feature_id") or ""),
        confirmed_right_border=str((rb or {}).get("feature_id") or ""),
        t_dna_direction=direction,
        replacement_start=int(start) if start else None,
        replacement_end=int(end) if end else None,
    )
    review_rows = preview.get("feature_review_rows") or []
    st.dataframe(
        [{"原始名称": row["name"], "类型": row["type"], "位置": row["location"], "链方向": row["strand"], "关系": row["relationship"], "审查": "需要人工审查" if row["relationship"] in {"partially_overlapped", "needs_manual_review"} else "已记录"} for row in review_rows],
        hide_index=True, use_container_width=True,
    )

    st.markdown("**5. GUS/NPTII 人工审查**")
    relationship_by_id = {row["feature_id"]: row["relationship"] for row in review_rows}
    key_ids = preview.get("key_feature_ids") or {}
    gus_relationships = sorted({relationship_by_id.get(item, "尚未评估") for item in key_ids.get("gus", [])})
    nptii_relationships = sorted({relationship_by_id.get(item, "尚未评估") for item in key_ids.get("nptii", [])})
    st.write(f"GUS 来源 feature：{', '.join(gus_relationships) or '尚未评估'}")
    st.write(f"NPTII 来源 feature：{', '.join(nptii_relationships) or '尚未评估'}")
    key_cols = st.columns(2)
    gus_reviewed = key_cols[0].checkbox("我已审查报告的 GUS 关系", value=bool((record.get("reviewed_key_features") or {}).get("gus")), key="pbi121_strategy_gus_review")
    nptii_reviewed = key_cols[1].checkbox("我已审查报告的 NPTII 关系", value=bool((record.get("reviewed_key_features") or {}).get("nptii")), key="pbi121_strategy_nptii_review")

    st.markdown("**6. 新多 TU 区域方向**")
    orientation_options = ["", "forward", "reverse"]
    orientation = st.radio(
        "相对于 pBI121 原始序列的方向", orientation_options,
        index=orientation_options.index(str(record.get("insertion_orientation") or "")),
        format_func=lambda value: {"": "未确认", "forward": "正向", "reverse": "反向"}[value],
        horizontal=True, key="pbi121_strategy_orientation",
    )
    notes = st.text_area("人工审查备注", value=str(record.get("manual_review_notes") or ""), key="pbi121_strategy_notes")
    draft = update_strategy(
        preview,
        insertion_orientation=orientation,
        insertion_orientation_relative_to_t_dna=orientation,
        normalized_canonical_orientation=orientation,
        reviewed_key_features={"gus": gus_reviewed, "nptii": nptii_reviewed},
        manual_review_notes=notes,
    )
    st.session_state["pbi121_replacement_strategy_draft"] = draft

    st.markdown("**7. 校验结果**")
    if draft["validation_blockers"]:
        for blocker in draft["validation_blockers"]:
            st.warning(blocker)
    else:
        st.info("pBI121 替换策略已具备后续计算构建条件。")
    if st.button("保存替换策略", type="primary", key="pbi121_strategy_save"):
        saved = save_strategy(draft)
        st.session_state["pbi121_replacement_strategy_draft"] = saved
        st.success("本地 pBI121 替换策略审查记录已保存。")
    with st.expander("技术详情", expanded=False):
        st.write(f"accession: {audit['accession']}")
        st.write(f"source record SHA-256: `{audit['source_record_sha256']}`")
        st.json({"target_t_dna_interval": draft.get("target_t_dna_interval"), "normalized_orientation": draft.get("normalized_canonical_orientation"), "strategy_version": draft.get("schema_version")})
