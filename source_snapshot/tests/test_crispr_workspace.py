from __future__ import annotations

from pathlib import Path

from views.CrisprWorkspace import (
    ACTIVE_PROJECT_KEY,
    CONFIRMATION_KEY,
    INITIALIZED_KEY,
    INPUT_SIGNATURE_KEY,
    RESULT_KEY,
    _confirmation_signature,
    _set_defaults,
    reset_crispr_workspace_session,
)


ROOT = Path(__file__).resolve().parents[1]
VIEW_SOURCE = (ROOT / "views" / "CrisprWorkspace.py").read_text(encoding="utf-8")
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_direct_navigation_reset_is_blank_and_preserves_expression_authority() -> None:
    canonical = {"sequence": "ACGT", "fasta": b">x\nACGT\n", "genbank": b"LOCUS"}
    expression_state = {"formal_step2_cds_text": "EXPRESSION-CDS", "mvp_vector_result": canonical}
    state = {
        **expression_state,
        "formal_crispr_target_sequence": "STALE-TARGET",
        RESULT_KEY: object(),
        INPUT_SIGNATURE_KEY: "stale",
        CONFIRMATION_KEY: "stale",
    }

    reset_crispr_workspace_session(state, active_project_id="project-1")
    _set_defaults(state)

    assert state["formal_step2_cds_text"] == "EXPRESSION-CDS"
    assert state["mvp_vector_result"] is canonical
    assert state["formal_crispr_target_sequence"] == ""
    assert RESULT_KEY not in state
    assert INPUT_SIGNATURE_KEY not in state
    assert CONFIRMATION_KEY not in state
    assert state[ACTIVE_PROJECT_KEY] == "project-1"
    assert state[INITIALIZED_KEY] is True


def test_user_confirmation_is_bound_to_exact_workflow_selection(tmp_path: Path) -> None:
    from services.crispr_product_workflow import (
        build_product_workflow_input,
        compute_product_workflow,
        installed_reference_from_fasta,
        select_product_candidate,
    )

    sequence = "AAA" + "ACGT" * 5 + "TGG" + "AAA"
    fasta = tmp_path / "assembly.fa"
    fasta.write_text(f">chr1\n{sequence}\n", encoding="utf-8")
    reference = installed_reference_from_fasta(
        fasta,
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture",
        assembly_accession="GCF_000001735.4",
        assembly_version="TAIR10.1",
        installation_provenance="workspace fixture",
    )

    def build(target: str):
        return build_product_workflow_input(
            target_sequence=target,
            target_id="target-1",
            target_display_name="Target 1",
            reference_pack_id="fixture-pack",
            contig="chr1",
            reference=reference,
            off_target_requested=False,
        )

    computed = compute_product_workflow(build(sequence))
    first = select_product_candidate(computed, computed.scan.candidates[0].candidate_id)
    changed = compute_product_workflow(build("T" + sequence[1:]))
    second = select_product_candidate(changed, changed.scan.candidates[0].candidate_id)

    assert _confirmation_signature(first)
    assert _confirmation_signature(first) != _confirmation_signature(second)


def test_workspace_has_exact_six_sections_and_required_boundary_copy() -> None:
    headings = (
        "1. 编辑目标",
        "2. 参考序列",
        "3. gRNA 候选",
        "4. 脱靶分析",
        "5. 用户确认",
        "6. 结果与导出",
    )

    assert 'st.subheader(_t("v1.crispr.1_edit_target"))' in VIEW_SOURCE
    assert 'st.subheader(_t("v1.crispr.4_off_target_analysis"))' in VIEW_SOURCE
    assert "候选按确定性坐标顺序列出" in VIEW_SOURCE
    assert "不使用 AI 对候选进行评分或推荐最佳 guide" in VIEW_SOURCE
    assert "在当前参考序列和参数下未枚举到命中" in VIEW_SOURCE
    assert "这不代表生物学安全、验证通过或实验就绪" in VIEW_SOURCE
    assert "打开表达设计 — 不修改构建" in VIEW_SOURCE


def test_reproducibility_controls_are_progressively_disclosed() -> None:
    assert VIEW_SOURCE.count('st.expander("高级 / Reproducibility", expanded=False)') == 2
    reference_block = VIEW_SOURCE.split("def _render_reference_section", 1)[1].split(
        "def _render_candidate_section", 1
    )[0]
    off_target_block = VIEW_SOURCE.split("def _render_off_target_section", 1)[1].split(
        "def _render_confirmation_section", 1
    )[0]
    assert 'with st.expander("高级 / Reproducibility", expanded=False):' in reference_block
    assert 'with st.expander("高级 / Reproducibility", expanded=False):' in off_target_block
    assert 'st.checkbox(\n        _t("v1.crispr.request_cas_offinder_enumeration")' in off_target_block


def test_complete_input_refresh_has_distinct_semantic_messages() -> None:
    refresh_block = VIEW_SOURCE
    assert "v1.crispr.input_refresh_failed_workflow_inputs_incomplete" in refresh_block
    assert "v1.crispr.input_refresh_complete_guide_selection_retained" in refresh_block
    assert "v1.crispr.input_refresh_complete_candidate_off_target_state_reset" in refresh_block
    complete_block = refresh_block.split("def _complete_input_refresh_message", 1)[-1].split("def render(", 1)[0]
    assert "v1.crispr.input_refresh_complete_guide_selection_retained" in complete_block
    assert "v1.crispr.input_refresh_complete_candidate_off_target_state_reset" in complete_block
    assert "v1.crispr.input_refresh_failed_workflow_inputs_incomplete" not in complete_block


def test_workspace_exposes_exact_states_and_deterministic_downloads() -> None:
    for state in ("not_run", "computed", "unavailable", "failed"):
        assert state in VIEW_SOURCE
    assert "computed / {count}" in VIEW_SOURCE
    assert "to_json(result)" in VIEW_SOURCE
    assert 'f"crispr_{result.workflow_id}.json"' in VIEW_SOURCE
    assert 'f"crispr_{result.workflow_id}_off_targets.tsv"' in VIEW_SOURCE
    assert "off_target_hits_tsv(result)" in VIEW_SOURCE
    assert "机器本地路径或诊断 provenance" in VIEW_SOURCE


def test_navigation_is_primary_and_expression_workspace_has_no_crispr_launcher() -> None:
    primary = APP_SOURCE.split("_PRIMARY_NAV_PAGES = (", 1)[1].split(")", 1)[0]
    aliases = APP_SOURCE.split("_PRIMARY_NAV_ROUTE_ALIASES = {", 1)[1].split("}", 1)[0]
    expression_workspace = APP_SOURCE.split("def _render_design_workspace", 1)[1].split(
        "def _render_crispr_product_workflow", 1
    )[0]

    assert "PAGE_CRISPR_WORKFLOW" in primary
    assert "PAGE_CRISPR_WORKFLOW" not in aliases
    assert "formal_crispr_product_entry" not in expression_workspace
    assert '"基因编辑</div>"' in APP_SOURCE
    assert 'PAGE_CRISPR_WORKFLOW: "CRISPR"' in APP_SOURCE


def test_workspace_copy_does_not_claim_ranking_or_biological_readiness() -> None:
    forbidden_positive_claims = (
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "best guide is",
        "recommended guide",
    )

    lowered = VIEW_SOURCE.casefold()
    assert all(term not in lowered for term in forbidden_positive_claims)
    assert "不预测活性、特异性、实验结果或生物学安全" in VIEW_SOURCE
