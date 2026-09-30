"""Real Streamlit 1.55 browser regression for Single-Gene Step 3 hydration."""
from __future__ import annotations

import re
import time

from playwright.sync_api import expect, sync_playwright

from scripts.acceptance import run_formal_single_gene_blank_acceptance as acceptance
from services.mvp_single_gene_persistence import list_mvp_single_gene_designs, open_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.rice_hsa_ncbi_mvp10_case import load_rice_hsa_ncbi_case


PROMOTER_NAME = "CaMV35S promoter"
THREE_PRIME_NAME = "CaMV 3'UTR (polyA signal)"


def _build_saved_case(page, assets) -> None:
    acceptance._click_button(page, "新建单基因项目")
    page.get_by_role("heading", name="第一步：项目定义与表达目标", exact=True).wait_for(timeout=30_000)
    page.get_by_role("textbox", name="项目名称 *", exact=True).fill("Project")
    acceptance._select_streamlit_option(page, re.compile(r"植物宿主 \*$"), "Rice / Oryza sativa")
    acceptance._click_button(page, "下一步")
    page.get_by_role("heading", name="第二步：目标基因与编码序列（CDS）", exact=True).wait_for(timeout=30_000)
    page.get_by_role("textbox", name="目标基因名称（必填）", exact=True).fill("ALB CDS")
    page.get_by_role("textbox", name="accession 或来源说明（必填）", exact=True).fill("NM_000477.7")
    cds = page.get_by_role("textbox", name="粘贴核酸序列", exact=True)
    cds.fill(assets["cds"]["sequence"])
    cds.press("Control+Enter")
    acceptance._click_button(page, "确认 CDS 并继续")
    page.get_by_role("heading", name="第三步：植物表达盒设计", exact=True).wait_for(timeout=30_000)
    page.locator(".st-key-formal_step3_component_promoter").get_by_role("button", name="用户序列", exact=True).click()
    page.get_by_role("textbox", name="启动子名称", exact=True).fill(PROMOTER_NAME)
    page.get_by_role("textbox", name="启动子 DNA/FASTA", exact=True).fill(assets["promoter"]["sequence"])
    page.locator(".st-key-formal_step3_component_three_prime").get_by_role("button", name="用户序列", exact=True).click()
    acceptance._select_streamlit_option(page, re.compile(r"3′调控元件生物学角色（用户声明）$"), "3′非翻译区（3′ UTR）")
    page.get_by_role("textbox", name="3′非翻译区（3′ UTR）名称", exact=True).fill(THREE_PRIME_NAME)
    page.get_by_role("textbox", name="3′非翻译区（3′ UTR） DNA/FASTA", exact=True).fill(assets["terminator"]["sequence"])
    page.get_by_text("我已确认组件排列和方向", exact=True).click()
    acceptance._click_button(page, "生成表达盒")
    acceptance._assert_current_step3_can_continue_to_step4(page)
    acceptance._click_button(page, "下一步")
    page.get_by_role("heading", name="第四步：植物二元载体骨架与组装策略", exact=True).wait_for(timeout=30_000)
    acceptance._click_button(page, "选择")
    acceptance._click_button(page, "确认骨架并继续")
    page.get_by_role("heading", name="第五步：载体构建设计与计算校验", exact=True).wait_for(timeout=30_000)
    acceptance._click_button(page, "生成完整载体")
    acceptance._click_button(page, "下一步")
    page.get_by_role("heading", name="第六步：项目保存、结果审查与交付", exact=True).wait_for(timeout=30_000)
    acceptance._click_button(page, "保存项目")
    expect(page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)).to_be_visible(timeout=30_000)


def _assert_step3(page, language: str, promoter_sequence: str, three_prime_sequence: str) -> None:
    if language == "zh-CN":
        heading = "第三步：植物表达盒设计"
        user_source = "用户序列"
        promoter_label = "启动子"
        three_prime_label = "3′非翻译区（3′ UTR）"
        role_label = "3′非翻译区（3′ UTR）"
        next_label = "下一步"
        step4_label = "4. 载体骨架"
    else:
        heading = "Step 3: Plant Expression Cassette Design"
        user_source = "User sequence"
        promoter_label = "Promoter"
        three_prime_label = "3′ untranslated region (3′ UTR)"
        role_label = three_prime_label
        next_label = "Next"
        step4_label = "4. Vector Backbone"
    page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=30_000)
    for key in ("promoter", "three_prime"):
        control = page.locator(f".st-key-formal_step3_component_{key}")
        source = control.get_by_role("button", name=user_source, exact=True)
        expect(source).to_have_attribute("data-testid", "stBaseButton-segmented_controlActive")
    expect(page.get_by_role("textbox", name=f"{promoter_label} name" if language == "en" else "启动子名称", exact=True)).to_have_value(PROMOTER_NAME)
    expect(page.get_by_role("textbox", name=f"{promoter_label} DNA/FASTA", exact=True)).to_have_value(promoter_sequence)
    expect(page.get_by_role("textbox", name=f"{three_prime_label} name" if language == "en" else "3′非翻译区（3′ UTR）名称", exact=True)).to_have_value(THREE_PRIME_NAME)
    expect(page.get_by_role("textbox", name=f"{three_prime_label} DNA/FASTA", exact=True)).to_have_value(three_prime_sequence)
    role = page.get_by_role("combobox", name=re.compile("biological role|生物学角色", re.IGNORECASE))
    expect(role).to_have_attribute("aria-label", re.compile(re.escape(role_label)))
    expect(page.get_by_role("button", name=step4_label, exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name=next_label, exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name=re.compile("Generate Expression Cassette|生成表达盒"))).to_have_count(0)


def test_cold_reopen_step3_hydrates_before_both_locale_cycles(tmp_path, monkeypatch) -> None:
    # Project is deliberately a display-copy collision value.
    monkeypatch.setattr(acceptance, "PROJECT_NAME", "Project")
    assets = load_rice_hsa_ncbi_case()["assets"]
    promoter_sequence = assets["promoter"]["sequence"]
    three_prime_sequence = assets["terminator"]["sequence"]
    persistence_dir = tmp_path / "projects"
    url, port = acceptance._reserve_local_url()
    first = second = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = None
        errors: list[str] = []
        try:
            first = acceptance._start_server(log_path=tmp_path / "before.log", persistence_dir=persistence_dir, local_url=url, port=port)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            acceptance._attach_browser_errors(page, errors)
            page.goto(url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
            acceptance._switch_locale(page, "中文", "项目中心")
            _build_saved_case(page, assets)
            repository = PlantProjectDraftRepository(persistence_dir)
            summaries = []
            for _ in range(60):
                summaries = list_mvp_single_gene_designs(repository=repository)
                if summaries:
                    break
                page.wait_for_timeout(250)
            assert len(summaries) == 1, page.locator("body").inner_text()[-2500:]
            saved = open_mvp_single_gene_design(summaries[0].project_id, repository=repository)
            assert saved["project_name"] == "Project"
            records = saved["input_records"]
            assert records["promoter"]["display_name"] == PROMOTER_NAME
            assert len(records["promoter"]["normalized_sequence"]) == len(promoter_sequence)
            assert records["terminator"]["display_name"] == THREE_PRIME_NAME
            assert len(records["terminator"]["normalized_sequence"]) == len(three_prime_sequence)
            assert saved["formal_expression_cassette"]["components"][-1]["biological_role"] == "three_prime_utr"
            page.close()
            page = None
            acceptance._stop_server(first)
            deadline = time.monotonic() + 15
            while not acceptance._port_is_free(port) and time.monotonic() < deadline:
                time.sleep(0.25)
            assert first.poll() is not None and acceptance._port_is_free(port)
            second = acceptance._start_server(log_path=tmp_path / "after.log", persistence_dir=persistence_dir, local_url=url, port=port)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            acceptance._attach_browser_errors(page, errors)
            page.goto(url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
            acceptance._switch_locale(page, "中文", "项目中心")
            acceptance._reopen_from_home(page)
            acceptance._switch_locale(page, "EN", "Step 6: Project Save, Result Review, and Delivery")
            acceptance._switch_locale(page, "中文", "第六步：项目保存、结果审查与交付")
            page.get_by_role("button", name="3. 植物表达盒", exact=True).click()
            for language, option, heading in (
                ("zh-CN", None, None),
                ("en", "EN", "Step 3: Plant Expression Cassette Design"),
                ("zh-CN", "中文", "第三步：植物表达盒设计"),
                ("en", "EN", "Step 3: Plant Expression Cassette Design"),
                ("zh-CN", "中文", "第三步：植物表达盒设计"),
                ("en", "EN", "Step 3: Plant Expression Cassette Design"),
            ):
                if option:
                    acceptance._switch_locale(page, option, heading)
                _assert_step3(page, language, promoter_sequence, three_prime_sequence)
            page.get_by_role("button", name="4. Vector Backbone", exact=True).click()
            page.get_by_role("heading", name=re.compile("Step 4"), exact=False).wait_for(timeout=30_000)
            assert saved["input_records"]["terminator"]["source_kind"] == "user_recorded"
            assert not errors, errors
        finally:
            if page is not None and not page.is_closed():
                page.close()
            if second is not None:
                acceptance._stop_server(second)
            if first is not None:
                acceptance._stop_server(first)
            browser.close()
    assert acceptance._port_is_free(port)
