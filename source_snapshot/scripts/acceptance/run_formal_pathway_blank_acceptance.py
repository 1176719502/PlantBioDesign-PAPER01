"""Formal app.py acceptance for a non-fixed three-step Pathway cold-reopen loop."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from Bio import SeqIO
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.acceptance.run_formal_multi_tu_blank_acceptance import (
    _assert_professional_review_zip_unavailable,
    _fill_unit,
    _switch_locale,
)
from scripts.acceptance.run_formal_single_gene_blank_acceptance import (
    ARTIFACT_ROOT as _SINGLE_ARTIFACT_ROOT,
    SERVER_EXCEPTION_PATTERN,
    _assert_clean_page,
    _attach_browser_errors,
    _click_button,
    _download,
    _port_is_free,
    _reserve_local_url,
    _select_streamlit_option,
    _start_server,
    _stop_server,
)
from services.canonical_construct_runtime import active_complete_plasmid_snapshot
from services.gate3_pathway_mapping import (
    build_pathway_traceability_rows,
    validate_pathway_mapping,
)
from services.mvp_multi_tu_persistence import (
    list_mvp_multi_tu_designs,
    open_mvp_multi_tu_design,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
)


ARTIFACT_ROOT = _SINGLE_ARTIFACT_ROOT.parent / "formal_pathway_blank_acceptance"
PROJECT_NAME = f"正式非固定Pathway闭环验收-{uuid4().hex[:8]}"
HOST_LABEL = "Tobacco / Nicotiana benthamiana"
PATHWAY_HOST_KEY = "Tobacco (N. benthamiana)"
HOST_KEY = "Nicotiana benthamiana"
# This is deliberately a generic, user-entered route. It is not the dedicated
# preloaded betalain three-enzyme case and does not call its loader.
FIXTURE_IDENTITY = "GENERIC_USER_ENTERED_GATE3_PATHWAY"
FIXTURE_SOURCE = "runner-local user-entered pathway records (generic Gate 3 route)"
# R2 binds browser claims to this exact generic runner fixture.  The separate
# dedicated Betalain acceptance fixture is intentionally not substituted here.
BROWSER_FIXTURE_CANONICAL_LENGTH = 11_849
BROWSER_FIXTURE_CANONICAL_SHA256 = (
    "43f5c937a9298a85d1960b21d762b15a19876111c031950f6d3395efe649574f"
)
# The dedicated Betalain evidence test intentionally remains a separate
# fixture from the generic browser route and keeps its own identity.
BETALAIN_FIXTURE_CANONICAL_LENGTH = 18_841
BETALAIN_FIXTURE_CANONICAL_SHA256 = (
    "cdeb4ea329322b942472b38c44fcad9c11216cd1e3fd4b9540e28a37826e2dc7"
)
TU_FIXTURES = [
    {
        "display_name": "Alpha expression unit",
        "cds_name": "CDS_ALPHA",
        "cds": "ATGGCTGCTTAA",
        "promoter_name": "PROMOTER_ALPHA",
        "promoter": "AACCGGTT",
        "five_prime_name": "FIVE_PRIME_ALPHA",
        "five_prime": "ATGC",
        "three_prime_name": "THREE_PRIME_ALPHA",
        "three_prime": "TTGCAACC",
    },
    {
        "display_name": "Beta expression unit",
        "cds_name": "CDS_BETA",
        "cds": "ATGAAACCCGGGTAG",
        "promoter_name": "PROMOTER_BETA",
        "promoter": "GGTTAACC",
        "five_prime_name": "FIVE_PRIME_BETA",
        "five_prime": "GCTA",
        "three_prime_name": "THREE_PRIME_BETA",
        "three_prime": "CCGGTTAA",
    },
    {
        "display_name": "Gamma expression unit",
        "cds_name": "REPORTER_CDS_FIXTURE",
        "cds": "ATGGTGAAATAA",
        "promoter_name": "REPORTER_PROMOTER_FIXTURE",
        "promoter": "TTGCAACC",
        "five_prime_name": "REPORTER_FIVE_PRIME_FIXTURE",
        "five_prime": "AGTC",
        "three_prime_name": "REPORTER_3PRIME_FIXTURE",
        "three_prime": "GCGTAT",
    },
]
PATHWAY_FIXTURES = [
    {
        "step_name": "Fixture conversion alpha",
        "substrate": "Fixture substrate A",
        "product": "Fixture intermediate B",
        "enzyme": "Fixture enzyme alpha",
        "enzyme_gene": TU_FIXTURES[0]["cds_name"],
        "cds": TU_FIXTURES[0]["cds"],
        "source": "Existing CDS_ALPHA repository fixture",
    },
    {
        "step_name": "Fixture conversion beta",
        "substrate": "Fixture intermediate B",
        "product": "Fixture intermediate C",
        "enzyme": "Fixture enzyme beta",
        "enzyme_gene": TU_FIXTURES[1]["cds_name"],
        "cds": TU_FIXTURES[1]["cds"],
        "source": "Existing CDS_BETA repository fixture",
    },
    {
        "step_name": "Fixture conversion gamma",
        "substrate": "Fixture intermediate C",
        "product": "Fixture product D",
        "enzyme": "Fixture enzyme gamma",
        "enzyme_gene": TU_FIXTURES[2]["cds_name"],
        "cds": TU_FIXTURES[2]["cds"],
        "source": "Existing REPORTER_CDS_FIXTURE repository fixture",
    },
]
PATHWAY_EXPECTED_DISPLAY_ORDER = [
    "目标基因表达单元",
    "植物选择标记表达单元",
    "报告基因表达单元",
]
PATHWAY_EXPECTED_ORIENTATIONS = ["forward", "forward", "forward"]
GATE3_DISPLAY_ORDER = ["TU1: CYP76AD1", "TU2: DODA1", "TU3: cDOPA5GT"]
GATE3_ORIENTATIONS = ["forward", "forward", "forward"]
GATE3_ENZYMES = [
    "CYP76AD1",
    "4,5-DOPA dioxygenase extradiol 1",
    "cyclo-DOPA 5-O-glucosyltransferase",
]
GATE3_CDS_LENGTHS = [1494, 828, 1503]
GATE3_REPLACEMENT_STRATEGY = "pbi121-af485783.1-exact-replacement-v1"
REVISED_ENZYME = "Fixture enzyme alpha revised mapping record"

LOCATOR_INVENTORY = {
    "page_identity": "项目中心 / 六步设计工作区",
    "headings": {
        "home": "项目中心",
        "step1": "第一步：项目定义与表达目标",
        "step2": "第二步：通路步骤与 CDS 映射",
        "step3": "第三步：TU 元件设计",
        "step4": "第四步：植物二元载体骨架与组装策略",
        "step5": "第五步：生成完整环状质粒计算记录",
    },
    "step1_controls": {
        "new_project": "新建多转录单元项目",
        "pathway_mode": "代谢通路多转录单元载体",
        "project_name": "项目名称 *",
        "host": "植物宿主 *",
        "next": "下一步",
    },
    "step2_controls": {
        "add_pathway_step": "添加通路步骤",
        "add_transcription_unit": "添加转录单元",
        "mapping_selector": "映射到转录单元",
        "apply_config": "应用通路步骤配置",
        "apply_cds": "将此步骤的 CDS 应用到所选转录单元",
    },
    "step3_controls": {
        "unit_tab": "TU{index} 表达盒",
        "continue": "确认全部 TU 配置并生成组装体，进入下一步",
    },
    "step4_controls": {
        "pbi121_identity": "pBI121 / AF485783.1",
        "select": "选择",
        "confirm": "确认骨架并继续",
    },
    "step5_controls": {
        "generate": "生成完整质粒",
        "save_draft": "保存草稿",
        "review": "审查结果与导出",
    },
    "step6_controls": {
        "heading": "第六步：项目保存、结果审查与交付",
        "save_entry": "Step 6 保存项目",
    },
}


def _start_isolated_server(*, log_path: Path, persistence_dir: Path, local_url: str, port: int):
    """Start against an acceptance-local SQLite store as well as draft files."""
    database_path = persistence_dir / "biodesign_unified.db"
    previous = os.environ.get("BIODESIGN_DB_PATH")
    os.environ["BIODESIGN_DB_PATH"] = str(database_path)
    try:
        return _start_server(
            log_path=log_path,
            persistence_dir=persistence_dir,
            local_url=local_url,
            port=port,
        )
    finally:
        if previous is None:
            os.environ.pop("BIODESIGN_DB_PATH", None)
        else:
            os.environ["BIODESIGN_DB_PATH"] = previous


def _assert_current_page_clean(page: Page, browser_errors: list[str]) -> None:
    """Reject real exception widgets while ignoring a collapsed traceback label."""
    try:
        _assert_clean_page(page, browser_errors)
    except AssertionError as exc:
        if "forbidden page text was visible: ['Traceback']" not in str(exc):
            raise
        if page.locator('[data-testid="stException"]:visible').count():
            raise


def _select_nth_combobox_option(
    page: Page, label: re.Pattern[str], index: int, option_pattern: re.Pattern[str]
) -> None:
    last_error: AssertionError | PlaywrightTimeoutError | None = None
    for _ in range(3):
        combobox = page.get_by_role("combobox", name=label).nth(index)
        try:
            expect(combobox).to_be_visible(timeout=10_000)
            combobox.click()
            option = page.get_by_role("option", name=option_pattern)
            expect(option).to_have_count(1, timeout=10_000)
            option.click(timeout=10_000)
            unit_match = re.search(r"TU\d+", option_pattern.pattern)
            selected_unit = unit_match.group(0) if unit_match else "TU"
            if not (combobox.input_value() or "").strip():
                expect(combobox).to_have_attribute("aria-label", re.compile(rf"Selected {re.escape(selected_unit)}\b", re.IGNORECASE), timeout=10_000)
        except (AssertionError, PlaywrightTimeoutError) as exc:
            last_error = exc
            continue
        return
    raise AssertionError(
        f"combobox option did not remain selected after the current UI rerun: {last_error}"
    ) from last_error


def _select_localized_streamlit_option(
    page: Page,
    combobox_name: re.Pattern[str],
    option_patterns: tuple[re.Pattern[str], ...],
) -> None:
    """Select a live option by semantic text, reacquiring after each rerun."""
    last_error: AssertionError | PlaywrightTimeoutError | None = None
    for _ in range(4):
        combobox = page.get_by_role("combobox", name=combobox_name)
        try:
            expect(combobox).to_have_count(1, timeout=10_000)
            expect(combobox).to_be_visible(timeout=10_000)
            combobox.click(timeout=10_000)
            option = None
            for pattern in option_patterns:
                candidate = page.get_by_role("option", name=pattern)
                if candidate.count() == 1:
                    option = candidate
                    break
            if option is None:
                raise AssertionError(
                    f"no live option matched locale-aware patterns: {option_patterns!r}"
                )
            expect(option).to_be_visible(timeout=10_000)
            option.click(timeout=10_000)
            refreshed = page.get_by_role("combobox", name=combobox_name)
            expect(refreshed).to_have_count(1, timeout=10_000)
            expect(refreshed).to_be_visible(timeout=10_000)
            return
        except (AssertionError, PlaywrightTimeoutError) as exc:
            last_error = exc
            page.keyboard.press("Escape")
    raise AssertionError(
        f"locale-aware combobox option did not remain selected after rerender: {last_error}"
    ) from last_error


def _fill_project_name(page: Page, value: str) -> None:
    """Commit the Step 1 name through the current input after each rerender."""
    last_error: AssertionError | PlaywrightTimeoutError | None = None
    for _ in range(4):
        project_name = page.get_by_role("textbox", name="项目名称 *", exact=True)
        try:
            expect(project_name).to_be_visible(timeout=10_000)
            project_name.fill(value)
            project_name.press("Enter")
            expect(
                page.get_by_role("textbox", name="项目名称 *", exact=True)
            ).to_have_value(value, timeout=10_000)
            return
        except (AssertionError, PlaywrightTimeoutError) as exc:
            last_error = exc
    raise AssertionError(f"Step 1 project name did not commit: {last_error}") from last_error


def _wait_for_tu_count(page: Page, expected: int, *, timeout: int = 30_000) -> None:
    """Wait for the rerun-produced pathway mapping controls to materialize."""
    selectors = page.get_by_role("combobox", name=re.compile(r"映射到转录单元|Map to transcription unit", re.IGNORECASE))
    expect(selectors).to_have_count(expected, timeout=timeout)


def _click_and_wait_for_tu_count(page: Page, expected: int) -> None:
    _click_button(page, LOCATOR_INVENTORY["step2_controls"]["add_pathway_step"])
    _wait_for_tu_count(page, expected)


def _add_tu_and_prove_tu3(page: Page) -> None:
    """Add one TU and fail closed unless the TU3 selector is in the live DOM."""
    _click_button(page, LOCATOR_INVENTORY["step2_controls"]["add_transcription_unit"])
    _wait_for_tu_count(page, 1)
    selector = page.get_by_role("combobox", name=re.compile(r"映射到转录单元")).first
    selector.click()
    tu3 = page.get_by_role("option", name=re.compile(r"^TU3 · "))
    expect(tu3).to_have_count(1, timeout=30_000)
    expect(tu3).to_be_visible(timeout=30_000)
    page.keyboard.press("Escape")


def _fill_and_apply_pathway_step(page: Page, index: int, fixture: dict[str, str]) -> None:
    page.get_by_role("textbox", name="步骤名称 *", exact=True).nth(index).fill(fixture["step_name"])
    page.get_by_role("textbox", name="酶名称 *", exact=True).nth(index).fill(fixture["enzyme"])
    page.get_by_role("textbox", name="底物", exact=True).nth(index).fill(fixture["substrate"])
    page.get_by_role("textbox", name="产物", exact=True).nth(index).fill(fixture["product"])
    page.get_by_role("textbox", name="酶基因名称（可选）", exact=True).nth(index).fill(fixture["enzyme_gene"])
    page.get_by_role("textbox", name="EC number（可选）", exact=True).nth(index).fill(f"TEST-FIXTURE-{index + 1}")
    page.get_by_role("textbox", name="酶来源生物（可选）", exact=True).nth(index).fill("Repository fixture only")
    page.get_by_role("textbox", name="CDS 来源说明或 accession", exact=True).nth(index).fill(fixture["source"])
    cds_input = page.get_by_role("textbox", name="CDS 输入（DNA 或单记录 FASTA）", exact=True).nth(index)
    cds_input.fill(fixture["cds"])
    cds_input.press("Control+Enter")
    _select_nth_combobox_option(
        page,
        re.compile(r"映射到转录单元"),
        index,
        re.compile(rf"TU{index + 1} · .* · (正向|反向) · (未记录|已记录) CDS"),
    )
    page.get_by_role("button", name="应用通路步骤配置", exact=True).nth(index).click()
    expect(page.get_by_text("当前映射状态：已选择 TU，待应用 CDS", exact=True)).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="将此步骤的 CDS 应用到所选转录单元", exact=True).nth(index).click()
    expect(page.get_by_text("当前映射状态：已应用到 TU", exact=True).nth(index)).to_be_visible(timeout=30_000)


def _fill_and_wait_for_tu_ready(
    page: Page, index: int, fixture: dict[str, str]
) -> None:
    # This helper owns the existing Streamlit widget hydration handshake for
    # component textareas. The surrounding runner still proves readiness via
    # the live panel state before advancing.
    _fill_unit(page, index, fixture)
    tab = page.get_by_role("tab", name=f"TU{index} 表达盒", exact=True)
    expect(tab).to_be_visible(timeout=30_000)
    tab.click()
    expect(page.locator('[role="tabpanel"]:visible')).to_contain_text("可生成", timeout=30_000)


def _build_blank_pathway(page: Page) -> None:
    _click_button(page, LOCATOR_INVENTORY["step1_controls"]["new_project"])
    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step1"], exact=True).wait_for(
        timeout=30_000
    )
    pathway_mode = page.get_by_text(LOCATOR_INVENTORY["step1_controls"]["pathway_mode"], exact=True)
    expect(pathway_mode).to_have_count(1, timeout=30_000)
    pathway_mode.click()
    expect(page.get_by_text(LOCATOR_INVENTORY["step1_controls"]["pathway_mode"], exact=True)).to_be_visible(timeout=30_000)
    _fill_project_name(page, PROJECT_NAME)
    _select_localized_streamlit_option(
        page,
        re.compile(r"植物宿主 \*|Plant host \*", re.IGNORECASE),
        (
            re.compile(r"Tobacco.*Nicotiana benthamiana", re.IGNORECASE),
            re.compile(r"烟草.*Nicotiana benthamiana", re.IGNORECASE),
        ),
    )
    _click_button(page, LOCATOR_INVENTORY["step1_controls"]["next"])

    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step2"], exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator("body")).to_contain_text(
        f"当前项目：{PROJECT_NAME}", timeout=30_000
    )
    # Each click is followed by a DOM proof. This prevents the next action
    # from targeting a pre-rerun fragment of the Streamlit page.
    # Pathway mode starts with one editable step; prove that initial widget
    # before changing the TU list.
    _wait_for_tu_count(page, 1)
    _click_button(page, LOCATOR_INVENTORY["step2_controls"]["add_transcription_unit"])
    _click_and_wait_for_tu_count(page, 2)
    _click_and_wait_for_tu_count(page, 3)
    expect(page.get_by_role("textbox", name="步骤名称 *", exact=True)).to_have_count(3, timeout=30_000)
    for index, fixture in enumerate(PATHWAY_FIXTURES):
        _fill_and_apply_pathway_step(page, index, fixture)
    expect(page.get_by_text("当前映射状态：已应用到 TU", exact=True)).to_have_count(3, timeout=30_000)
    _click_button(page, "下一步")

    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step3"], exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text(re.compile(r"通路步骤.*转录单元溯源"))).to_be_visible(timeout=30_000)
    expect(page.locator("body")).to_contain_text(PATHWAY_FIXTURES[0]["source"], timeout=30_000)
    expect(page.locator("body")).to_contain_text("当前映射状态：已应用到 TU", timeout=30_000)
    page.screenshot(path=str(ARTIFACT_ROOT / "step3-provenance.png"), full_page=True)
    (ARTIFACT_ROOT / "step3-provenance-dom.html").write_text(page.content(), encoding="utf-8")
    for index, fixture in enumerate(TU_FIXTURES, start=1):
        _fill_and_wait_for_tu_ready(page, index, fixture)
    _click_button(page, LOCATOR_INVENTORY["step3_controls"]["continue"])

    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step4"], exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text(LOCATOR_INVENTORY["step4_controls"]["pbi121_identity"], exact=True)).to_be_visible(timeout=30_000)
    expect(page.locator("body")).to_contain_text("AF485783.1", timeout=30_000)
    expect(page.get_by_role("button", name="选择", exact=True)).to_have_count(1)
    _click_button(page, LOCATOR_INVENTORY["step4_controls"]["select"])
    page.screenshot(path=str(ARTIFACT_ROOT / "step4-coordinates.png"), full_page=True)
    (ARTIFACT_ROOT / "step4-coordinates-dom.html").write_text(page.content(), encoding="utf-8")

    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step5"], exact=True).wait_for(timeout=30_000)
    _assert_user_coordinate_split(page)
    _click_button(page, LOCATOR_INVENTORY["step5_controls"]["generate"])
    expect(page.locator("body")).to_contain_text("阻断项： 0 · 警告项：", timeout=30_000)
    _click_button(page, LOCATOR_INVENTORY["step5_controls"]["save_draft"])
    expect(page.get_by_text("项目草稿已保存，可从项目中心重新打开。", exact=True)).to_be_visible(
        timeout=30_000
    )
    _click_button(page, LOCATOR_INVENTORY["step5_controls"]["review"])
    page.get_by_role("heading", name=LOCATOR_INVENTORY["step6_controls"]["heading"], exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator("body")).to_contain_text("11,849 bp", timeout=30_000)
    _assert_sequence_viewer_dom(page, expected_length=BROWSER_FIXTURE_CANONICAL_LENGTH)
    _assert_complete_linear_map_dom(page)
    page.screenshot(path=str(ARTIFACT_ROOT / "step6-complete-linear-map.png"), full_page=True)
    (ARTIFACT_ROOT / "step6-complete-linear-map-dom.html").write_text(page.content(), encoding="utf-8")
    _click_button(page, "保存项目")
    expect(page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)).to_be_visible(
        timeout=30_000
    )


def _assert_sequence_viewer_dom(page: Page, *, expected_length: int) -> None:
    """Prove bounded 60 bp lines and internal scrolling in the real browser DOM."""
    page.get_by_role("tab", name="序列", exact=True).click()
    sequence_expander = page.locator("details").filter(has_text=re.compile(r"完整质粒序列|Full plasmid sequence", re.IGNORECASE)).last
    expect(sequence_expander).to_have_count(1, timeout=30_000)
    sequence_expander.locator("summary").click()
    viewer = page.locator(f'.sequence-review-viewer[data-sequence-length="{expected_length}"]')
    expect(viewer).to_be_visible(timeout=30_000)
    expect(viewer).to_have_attribute("data-line-width", "60")
    expect(viewer).to_have_attribute("data-sequence-length", str(expected_length))
    lines = viewer.locator(".sequence-review-line")
    expected_lines = (expected_length + 59) // 60
    expect(lines).to_have_count(expected_lines)
    assert lines.nth(0).inner_text().strip().startswith("1")
    assert lines.nth(expected_lines - 1).inner_text().strip().startswith(str((expected_lines - 1) * 60 + 1))
    assert lines.nth(0).get_attribute("data-start") == "1"
    assert lines.nth(0).get_attribute("data-end") == "60"
    assert lines.nth(expected_lines - 1).get_attribute("data-start") == "11821"
    assert lines.nth(expected_lines - 1).get_attribute("data-end") == "11849"
    assert lines.nth(0).evaluate("row => row.textContent.trim().split(/\\s+/).at(-1).length") == 60
    assert lines.nth(expected_lines - 1).evaluate("row => row.textContent.trim().split(/\\s+/).at(-1).length") == 29
    assert "mono" in viewer.evaluate("el => getComputedStyle(el).fontFamily").lower()
    metrics = viewer.evaluate(
        "el => ({height: el.clientHeight, scrollHeight: el.scrollHeight, overflowY: getComputedStyle(el).overflowY})"
    )
    assert metrics["height"] <= 360
    assert metrics["scrollHeight"] > metrics["height"]
    assert metrics["overflowY"] in {"auto", "scroll"}


def _assert_user_coordinate_split(page: Page) -> None:
    """Prove the live fixed-route summary uses only the 1-based closed interval."""
    expect(page.get_by_text(re.compile(r"4974.?7979.*1-based|4974.?7979.*1-based", re.IGNORECASE))).to_be_visible(timeout=30_000)
    expect(page.locator("body")).not_to_contain_text("[4973, 7979)")


def _assert_complete_linear_map_dom(page: Page) -> None:
    """Prove the complete-plasmid linear publication map is a live browser view."""
    page.get_by_role("tab", name="线性图", exact=True).click()
    linear_panel = page.locator('[role="tabpanel"]:visible')
    expect(linear_panel).to_have_count(1, timeout=30_000)
    expect(linear_panel.get_by_text("完整质粒 · 线性视图", exact=True)).to_be_visible(timeout=30_000)
    frames = linear_panel.locator("iframe")
    expect(frames).to_have_count(2, timeout=30_000)
    complete_frame = frames.nth(1).content_frame
    expect(complete_frame.locator("svg")).to_be_visible(timeout=30_000)
    expect(complete_frame.locator(".map-viewer-toolbar")).to_be_visible(timeout=30_000)
    metadata_text = complete_frame.locator("svg metadata").evaluate("el => el.textContent")
    metadata = json.loads(metadata_text)
    assert metadata["view_type"] == "complete_linear_plasmid"
    assert metadata["sequence_length"] == BROWSER_FIXTURE_CANONICAL_LENGTH
    assert metadata["sequence_checksum"] == BROWSER_FIXTURE_CANONICAL_SHA256
    assert "label-density" not in linear_panel.inner_text().lower()
    for label in ("下载 Publication Map SVG", "下载 Publication Map PDF", "下载 Publication Map PNG"):
        controls = linear_panel.get_by_role("button", name=label, exact=True)
        expect(controls).to_have_count(2, timeout=30_000)
        for index in range(2):
            expect(controls.nth(index)).to_be_enabled(timeout=30_000)


def _download_pair(page: Page, directory: Path, prefix: str) -> tuple[Path, Path]:
    return (
        _download(page, "完整质粒 FASTA", directory / f"{prefix}.fasta"),
        _download(page, "完整质粒 GenBank", directory / f"{prefix}.gb"),
    )


def _pathway_export_evidence(
    persistence_dir: Path,
    fasta_path: Path,
    genbank_path: Path,
    *,
    expected_first_enzyme: str = PATHWAY_FIXTURES[0]["enzyme"],
    expected_display_order: list[str] | None = None,
    expected_orientations: list[str] | None = None,
    expected_mapped_tu_orders: list[int] | None = None,
    expected_cds_lengths: list[int] | None = None,
) -> dict[str, Any]:
    repositories = (
        PlantProjectDraftRepository(persistence_dir),
        SqlitePlantProjectDraftRepository(persistence_dir / "biodesign_unified.db"),
    )
    saved = [
        (repository, summary)
        for repository in repositories
        for summary in list_mvp_multi_tu_designs(repository=repository)
    ]
    if len(saved) != 1:
        raise AssertionError(f"expected one saved Pathway project, got {len(saved)}")
    repository, summary = saved[0]
    summaries = [summary]
    reopened = open_mvp_multi_tu_design(summaries[0].project_id, repository=repository)
    context = dict(reopened.get("formal_project_context") or {})
    persisted = repository.load(summaries[0].project_id)
    if persisted.workflow_type != "gate3_pathway":
        raise AssertionError("saved project did not retain the Gate 3 workflow identity")
    if context.get("design_scenario") != "metabolic_pathway_multi_tu_vector":
        raise AssertionError("saved result was not the general Pathway design scenario")
    formal_state = dict(context.get("formal_state") or {})
    if context.get("record_kind") != "formal_editor_completed":
        raise AssertionError("Gate 3 completed editor state was not persisted")
    if int(context.get("current_step") or 0) != 6:
        raise AssertionError("Gate 3 completed editor state did not retain Step 6")
    if not reopened.get("formal_editor_restoration_eligible"):
        raise AssertionError("Gate 3 completed editor record was not reopenable")
    if formal_state.get("formal_design_scenario") != "metabolic_pathway_multi_tu_vector":
        raise AssertionError("Gate 3 formal state lost its Pathway scenario")
    replacement_strategy_id = str(context.get("replacement_strategy_id") or "")
    fixed_betalain_record = replacement_strategy_id == GATE3_REPLACEMENT_STRATEGY
    if replacement_strategy_id and not fixed_betalain_record:
        raise AssertionError("saved result used an unexpected replacement strategy")
    expected_workflow_kind = "betalain_gate3" if fixed_betalain_record else "gate3_pathway"
    if reopened.get("workflow_kind") != expected_workflow_kind:
        raise AssertionError("reopened result did not retain its Gate 3 Pathway contract")
    expected_host_key = HOST_KEY if fixed_betalain_record else PATHWAY_HOST_KEY
    if str(reopened.get("project_name")) != PROJECT_NAME or str(context.get("host_key")) != expected_host_key:
        raise AssertionError(
            "project name or host did not survive persistence: "
            f"{reopened.get('project_name')!r} / {context.get('host_key')!r}"
        )

    original = dict(reopened.get("original_input") or {})
    units = sorted(list(original.get("expression_units") or []), key=lambda unit: int(unit.get("order") or 0))
    steps = list(context.get("pathway_steps") or [])
    validation = validate_pathway_mapping(steps, units)
    if not validation["mapping_complete"] or validation["blocking_items"]:
        raise AssertionError(f"saved Pathway mapping was not complete: {validation['blocking_items']}")
    rows = build_pathway_traceability_rows(steps, units)
    if len(rows) != 3 or len(units) != 3:
        raise AssertionError("expected three Pathway steps and three transcription units")
    expected_enzymes = (
        GATE3_ENZYMES
        if fixed_betalain_record
        else [
            expected_first_enzyme,
            PATHWAY_FIXTURES[1]["enzyme"],
            PATHWAY_FIXTURES[2]["enzyme"],
        ]
    )
    if [row["enzyme_name"] for row in rows] != expected_enzymes:
        raise AssertionError("saved enzyme records did not match the Pathway input")
    if any(row["mapping_status"] != "applied" for row in rows):
        raise AssertionError("one or more CDS-to-TU mappings were not applied")
    mapped_tu_orders = [int(row["transcription_unit_order"]) for row in rows]
    expected_mapping_order = expected_mapped_tu_orders or [1, 2, 3]
    if mapped_tu_orders != expected_mapping_order:
        raise AssertionError(f"unexpected Pathway-to-TU mapping order: {mapped_tu_orders}")
    cds_lengths = [int(row["cds_length"]) for row in rows]
    expected_lengths = expected_cds_lengths or (
        GATE3_CDS_LENGTHS if fixed_betalain_record else [12, 15, 12]
    )
    if cds_lengths != expected_lengths:
        raise AssertionError(f"unexpected Pathway CDS lengths: {cds_lengths}")

    display_order = [str(unit.get("display_name")) for unit in units]
    orientations = [str(unit.get("orientation")) for unit in units]
    unit_ids = [str(unit.get("unit_id")) for unit in units]
    expected_display_order = expected_display_order or (
        GATE3_DISPLAY_ORDER if fixed_betalain_record else PATHWAY_EXPECTED_DISPLAY_ORDER
    )
    expected_orientations = expected_orientations or (
        GATE3_ORIENTATIONS if fixed_betalain_record else PATHWAY_EXPECTED_ORIENTATIONS
    )
    if display_order != expected_display_order or orientations != expected_orientations:
        raise AssertionError(f"unexpected TU order/orientation: {display_order} / {orientations}")
    if len(set(unit_ids)) != 3:
        raise AssertionError("transcription-unit IDs were not stable and unique")

    canonical = active_complete_plasmid_snapshot(reopened["runtime"])
    canonical_sequence = str(canonical["sequence"]).upper()
    canonical_sha256 = hashlib.sha256(canonical_sequence.encode("ascii")).hexdigest()
    expected_canonical_length = (
        BETALAIN_FIXTURE_CANONICAL_LENGTH
        if fixed_betalain_record
        else BROWSER_FIXTURE_CANONICAL_LENGTH
    )
    expected_canonical_sha256 = (
        BETALAIN_FIXTURE_CANONICAL_SHA256
        if fixed_betalain_record
        else BROWSER_FIXTURE_CANONICAL_SHA256
    )
    if len(canonical_sequence) != expected_canonical_length:
        raise AssertionError(
            f"canonical fixture length changed: {len(canonical_sequence)} "
            f"!= {expected_canonical_length}"
        )
    if canonical_sha256 != expected_canonical_sha256:
        raise AssertionError(
            f"canonical fixture SHA-256 changed: {canonical_sha256} "
            f"!= {expected_canonical_sha256}"
        )
    fasta = SeqIO.read(StringIO(fasta_path.read_text(encoding="utf-8")), "fasta")
    genbank = SeqIO.read(StringIO(genbank_path.read_text(encoding="utf-8")), "genbank")
    if str(fasta.seq).upper() != canonical_sequence or str(genbank.seq).upper() != canonical_sequence:
        raise AssertionError("FASTA or GenBank differed from the canonical complete plasmid")

    previous_end = 0
    unit_ranges: list[dict[str, Any]] = []
    component_coordinates: list[list[dict[str, Any]]] = []
    for unit in sorted(reopened["expression_units"], key=lambda item: int(item.get("order") or 0)):
        unit_range = dict(unit.get("range") or {})
        if int(unit_range.get("start") or 0) != previous_end + 1:
            raise AssertionError(f"non-contiguous TU coordinate: {unit_range}")
        expected_strand = -1 if unit.get("orientation") == "reverse" else 1
        if int(unit_range.get("strand") or 0) != expected_strand:
            raise AssertionError("TU strand did not match its saved orientation")
        previous_end = int(unit_range.get("end") or 0)
        components = list(unit.get("components") or [])
        for component in components:
            if str(component.get("unit_id")) != str(unit.get("unit_id")):
                raise AssertionError("component identity differed from its enclosing TU")
            if not (
                int(unit_range["start"])
                <= int(component["start"])
                <= int(component["end"])
                <= int(unit_range["end"])
            ):
                raise AssertionError("component coordinate fell outside its TU range")
        unit_ranges.append(unit_range)
        component_coordinates.append(components)

    canonical_validation = dict(canonical.get("validation_summary") or {})
    if int(canonical_validation.get("blocking_count") or 0):
        raise AssertionError("formal complete-plasmid validation retained blockers")
    return {
        "project_id": summaries[0].project_id,
        "project_name": reopened["project_name"],
        "host_key": context["host_key"],
        "replacement_strategy_id": replacement_strategy_id,
        "pathway_steps": [row["step_name"] for row in rows],
        "enzymes": [row["enzyme_name"] for row in rows],
        "cds_lengths": cds_lengths,
        "mapped_tu_orders": mapped_tu_orders,
        "mapping_statuses": [row["mapping_status"] for row in rows],
        "display_order": display_order,
        "orientations": orientations,
        "unit_ids": unit_ids,
        "unit_ranges": unit_ranges,
        "component_coordinates": component_coordinates,
        "pathway_mapping_blocking_count": len(validation["blocking_items"]),
        "validation_blocking_count": int(canonical_validation.get("blocking_count") or 0),
        "validation_warning_count": int(canonical_validation.get("warning_count") or 0),
        "canonical_length": len(canonical_sequence),
        "canonical_sha256": canonical_sha256,
        "fasta_matches_canonical": True,
        "genbank_matches_canonical": True,
        "workflow_type": persisted.workflow_type,
        "workflow_kind": reopened["workflow_kind"],
        "completed_editor_record": True,
        "restored_step": 6,
    }


def _reopen_from_home(page: Page) -> None:
    page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text(PROJECT_NAME, exact=True)).to_be_visible(timeout=30_000)
    open_buttons = page.get_by_role("button", name="打开", exact=True)
    expect(open_buttons).to_have_count(1)
    open_buttons.click()
    page.get_by_role("heading", name="第六步：项目保存、结果审查与交付", exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator('[class*="st-key-formal_project_table_head"]')).to_have_count(0)
    expect(page.locator('[class*="st-key-formal_project_summary_"]')).to_have_count(0)
    expect(page.locator("body")).to_contain_text("TU1", timeout=30_000)
    for fixture in PATHWAY_FIXTURES:
        expect(page.locator("body")).to_contain_text(fixture["enzyme"])


def _reopen_saved_entry(page: Page) -> str:
    page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["home"], exact=True).wait_for(
        timeout=30_000
    )
    expect(page.get_by_text(PROJECT_NAME, exact=True)).to_be_visible(timeout=30_000)
    open_buttons = page.get_by_role("button", name="打开", exact=True)
    expect(open_buttons).to_have_count(1, timeout=30_000)
    open_buttons.click()
    step5 = page.get_by_role("heading", name=LOCATOR_INVENTORY["headings"]["step5"], exact=True)
    step6 = page.get_by_role("heading", name=LOCATOR_INVENTORY["step6_controls"]["heading"], exact=True)
    expect(step5.or_(step6)).to_be_visible(timeout=30_000)
    expect(page.locator('[class*="st-key-formal_project_table_head"]')).to_have_count(0)
    expect(page.locator('[class*="st-key-formal_project_summary_"]')).to_have_count(0)
    return "step5" if step5.count() else "step6"


def _edit_mapping_and_rebuild(page: Page) -> None:
    _click_button(page, "5. 完整构建")
    page.get_by_role("heading", name="第五步：生成完整环状质粒计算记录", exact=True).wait_for(
        timeout=30_000
    )
    _click_button(page, "2. 目标基因")
    page.get_by_role("heading", name="第二步：通路步骤与 CDS 映射", exact=True).wait_for(timeout=30_000)
    for index, fixture in enumerate(PATHWAY_FIXTURES):
        expect(page.get_by_role("textbox", name="步骤名称 *", exact=True).nth(index)).to_have_value(fixture["step_name"])
        expect(page.get_by_role("textbox", name="酶名称 *", exact=True).nth(index)).to_have_value(fixture["enzyme"])
        expect(page.get_by_role("textbox", name="CDS 输入（DNA 或单记录 FASTA）", exact=True).nth(index)).to_have_value(fixture["cds"])
    page.get_by_role("textbox", name="酶名称 *", exact=True).nth(0).fill(REVISED_ENZYME)
    page.get_by_role("textbox", name="酶基因名称（可选）", exact=True).nth(0).fill(
        TU_FIXTURES[1]["cds_name"]
    )
    cds_input = page.get_by_role(
        "textbox", name="CDS 输入（DNA 或单记录 FASTA）", exact=True
    ).nth(0)
    cds_input.fill(TU_FIXTURES[1]["cds"])
    cds_input.press("Control+Enter")
    _select_nth_combobox_option(
        page,
        re.compile(r"映射到转录单元"),
        0,
        re.compile(r"TU2 · .* · (正向|反向) · 已记录 CDS"),
    )
    page.get_by_role("button", name="应用通路步骤配置", exact=True).nth(0).click()
    expect(page.get_by_role("textbox", name="酶名称 *", exact=True).nth(0)).to_have_value(REVISED_ENZYME)
    expect(page.get_by_text("当前映射状态：已选择 TU，待应用 CDS", exact=True)).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="5. 完整构建", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="6. 结果与导出", exact=True)).to_be_disabled()
    page.get_by_role("button", name="将此步骤的 CDS 应用到所选转录单元", exact=True).nth(0).click()
    expect(page.get_by_text("当前映射状态：已应用到 TU", exact=True)).to_have_count(3, timeout=30_000)

    _click_button(page, "3. 植物表达盒")
    page.get_by_role("heading", name="第三步：TU 元件设计", exact=True).wait_for(timeout=30_000)
    expect(page.get_by_role("button", name="确认全部 TU 配置并生成组装体，进入下一步", exact=True)).to_be_disabled()
    _fill_and_wait_for_tu_ready(page, 2, TU_FIXTURES[1])
    _click_button(page, "确认全部 TU 配置并生成组装体，进入下一步")
    page.get_by_role("heading", name="第四步：植物二元载体骨架与组装策略", exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text("已应用 pBI121 / AF485783.1 固定精确替换合同。", exact=True)).to_be_visible(
        timeout=30_000
    )
    _click_button(page, "确认骨架并继续")
    try:
        page.get_by_role("heading", name="第五步：生成完整环状质粒计算记录", exact=True).wait_for(
            timeout=10_000
        )
    except Exception as exc:
        body = page.locator("body").inner_text()
        raise AssertionError(f"rebuild did not advance from Step 4; visible page: {body[-3000:]}") from exc
    _click_button(page, "生成完整质粒")
    expect(page.locator("body")).to_contain_text("阻断项： 0 · 警告项：", timeout=30_000)
    _click_button(page, "保存草稿")
    expect(page.get_by_text("项目草稿已保存，可从项目中心重新打开。", exact=True)).to_be_visible(timeout=30_000)
    _click_button(page, "审查结果与导出")
    page.get_by_role("heading", name="第六步：项目保存、结果审查与交付", exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator("body")).to_contain_text(REVISED_ENZYME)
    _click_button(page, "保存项目")
    expect(page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)).to_be_visible(
        timeout=30_000
    )


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    first_log = ARTIFACT_ROOT / "streamlit-before-restart.log"
    second_log = ARTIFACT_ROOT / "streamlit-after-restart.log"
    result: dict[str, Any] = {
        "passed": False,
        "entrypoint": "app.py",
        "fixture_identity": FIXTURE_IDENTITY,
        "fixture_source": FIXTURE_SOURCE,
        "locator_inventory": LOCATOR_INVENTORY,
        "forbidden_fixture_called": False,
        "fixed_betalain_construct_used": False,
        "project_name": PROJECT_NAME,
        "first_blocker": None,
        "browser_errors": [],
        "server_exception_count": 0,
        "owned_streamlit_process_ids": [],
        "process_cleanup_complete": False,
        "browser_cleanup_complete": False,
        "port_cleanup_complete": False,
        "steps": {},
    }
    browser_errors: list[str] = []
    processes = []
    active_process = None
    page = None
    local_url, port = _reserve_local_url()
    result["port"] = port

    with tempfile.TemporaryDirectory(prefix="formal_pathway_blank_") as temp_dir:
        work_dir = Path(temp_dir)
        persistence_dir = work_dir / "isolated_project_drafts"
        export_dir = ARTIFACT_ROOT / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                active_process = _start_isolated_server(
                    log_path=first_log,
                    persistence_dir=persistence_dir,
                    local_url=local_url,
                    port=port,
                )
                processes.append(active_process)
                page = browser.new_page(viewport={"width": 1600, "height": 1200}, accept_downloads=True)
                _attach_browser_errors(page, browser_errors)
                page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
                page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
                _switch_locale(page, "中文", "项目中心")
                page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)
                _build_blank_pathway(page)
                _assert_professional_review_zip_unavailable(page)
                result["professional_review_zip_unavailable_before_restart"] = True
                _assert_current_page_clean(page, browser_errors)
                result["steps"]["project_center_to_step6_gate3_completed_save"] = "passed"
                before_fasta, before_genbank = _download_pair(
                    page, export_dir, "before_restart"
                )
                before_evidence = _pathway_export_evidence(
                    persistence_dir,
                    before_fasta,
                    before_genbank,
                )
                result["before_restart"] = before_evidence

                page.close()
                page = None
                _stop_server(active_process)
                active_process = None
                if processes[0].poll() is None:
                    raise AssertionError("the first Streamlit process remained alive after stop")
                result["steps"]["complete_stop_before_cold_start"] = "passed"

                active_process = _start_isolated_server(
                    log_path=second_log,
                    persistence_dir=persistence_dir,
                    local_url=local_url,
                    port=port,
                )
                processes.append(active_process)
                page = browser.new_page(viewport={"width": 1600, "height": 1200}, accept_downloads=True)
                _attach_browser_errors(page, browser_errors)
                page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
                page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
                _switch_locale(page, "中文", "项目中心")
                _reopen_from_home(page)
                expect(page.locator("body")).to_contain_text("11,849 bp", timeout=30_000)
                _assert_sequence_viewer_dom(page, expected_length=BROWSER_FIXTURE_CANONICAL_LENGTH)
                _assert_complete_linear_map_dom(page)
                page.screenshot(path=str(ARTIFACT_ROOT / "cold-reopen-complete-linear-map.png"), full_page=True)
                after_fasta, after_genbank = _download_pair(
                    page, export_dir, "after_restart"
                )
                after_evidence = _pathway_export_evidence(
                    persistence_dir,
                    after_fasta,
                    after_genbank,
                )
                result["after_restart"] = after_evidence
                result["fasta_bytes_identical"] = (
                    before_fasta.read_bytes() == after_fasta.read_bytes()
                )
                result["genbank_bytes_identical"] = (
                    before_genbank.read_bytes() == after_genbank.read_bytes()
                )
                if before_evidence != after_evidence:
                    raise AssertionError("Gate 3 persistence evidence changed after cold restart")
                if not result["fasta_bytes_identical"] or not result["genbank_bytes_identical"]:
                    raise AssertionError("Gate 3 export bytes changed after cold restart")
                result["reopened_entry_step"] = "step6"
                result["steps"]["cold_restart_project_center_step6_reopen_and_export"] = "passed"
                _assert_current_page_clean(page, browser_errors)
                result["passed"] = True
            except Exception as exc:
                result["first_blocker"] = f"{type(exc).__name__}: {exc}"
                if page is not None and not page.is_closed():
                    result["visible_page_text"] = page.locator("body").inner_text()
                    result["dom_snapshot_path"] = str(ARTIFACT_ROOT / "failure-dom.html")
                    (ARTIFACT_ROOT / "failure-dom.html").write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(ARTIFACT_ROOT / "failure.png"), full_page=True)
            finally:
                if page is not None and not page.is_closed():
                    page.close()
                if active_process is not None:
                    _stop_server(active_process)
                browser.close()
                result["browser_cleanup_complete"] = True

    result["browser_errors"] = browser_errors
    result["owned_streamlit_process_ids"] = [process.pid for process in processes]
    result["server_exception_count"] = sum(
        len(SERVER_EXCEPTION_PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))
        for path in (first_log, second_log)
        if path.exists()
    )
    result["process_cleanup_complete"] = all(process.poll() is not None for process in processes)
    result["port_cleanup_complete"] = _port_is_free(port)
    if browser_errors and not result["first_blocker"]:
        result["first_blocker"] = "browser errors were recorded"
    if result["server_exception_count"] and not result["first_blocker"]:
        result["first_blocker"] = "server exceptions were recorded"
    if (not result["process_cleanup_complete"] or not result["port_cleanup_complete"]) and not result["first_blocker"]:
        result["first_blocker"] = "acceptance-owned process or port cleanup was incomplete"
    result["passed"] = bool(
        result["passed"]
        and not result["first_blocker"]
        and not result["browser_errors"]
        and result["server_exception_count"] == 0
        and result["process_cleanup_complete"]
        and result["browser_cleanup_complete"]
        and result["port_cleanup_complete"]
    )
    result_path = ARTIFACT_ROOT / "acceptance_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
