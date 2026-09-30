"""Formal app.py acceptance for a blank two- or three-TU cold-reopen loop."""
from __future__ import annotations

import hashlib
import json
import copy
from contextlib import nullcontext
import os
import re
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO
from playwright.sync_api import Page, expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.acceptance.run_formal_single_gene_blank_acceptance import (
    ARTIFACT_ROOT as _SINGLE_ARTIFACT_ROOT,
    SERVER_EXCEPTION_PATTERN,
    _assert_clean_page,
    _attach_browser_errors,
    _click_button,
    _download,
    _port_is_free,
    _reserve_local_url,
    _wait_for_server,
    _stop_server,
)
from services.canonical_construct_runtime import active_construct_snapshot
from services.acceptance_fixture_identity import (
    clear_acceptance_fixture_context,
    configure_acceptance_fixture_context,
    refresh_acceptance_fixture_authority,
    snapshot_active_production_database,
)
from services.mvp_multi_tu_persistence import list_mvp_multi_tu_designs, open_mvp_multi_tu_design
from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design
from services.mvp_multi_tu_runtime import generate_multi_tu_construct
from services.plant_project_draft_repository import SqlitePlantProjectDraftRepository


TU_COUNT = int(os.environ.get("BIODESIGN_ACCEPTANCE_MULTI_TU_COUNT", "3"))
if TU_COUNT not in {2, 3}:
    raise ValueError("BIODESIGN_ACCEPTANCE_MULTI_TU_COUNT must be 2 or 3")
ARTIFACT_ROOT = _SINGLE_ARTIFACT_ROOT.parent / (
    f"formal_multi_tu_blank_acceptance_{TU_COUNT}tu"
)
PROJECT_NAME = f"V1 formal Multi-TU blank fixture {TU_COUNT} TU"
LEGACY_PROJECT_NAME = "V1 legacy Multi-TU three-role fixture 97 bp"
FIXTURE_IDENTITY = f"v1-formal-multi-tu-blank-fixture-{TU_COUNT}tu-v1"
EXPECTED_DISPLAY_ORDER = [
    "植物选择标记表达单元",
    "目标基因表达单元",
    "报告基因表达单元",
][:TU_COUNT]
EXPECTED_ORIENTATIONS = ["forward", "reverse", "forward"][:TU_COUNT]
FIXTURE_SOURCE = "tests/data/mvp9_multi_tu_cases.json and tests/test_gate2_formal_multi_tu_workflow.py"
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
        "orientation": "reverse",
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
        "orientation": "forward",
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
        "orientation": "forward",
    },
]


def _start_server_with_authority(
    *, log_path: Path, persistence_dir: Path, local_url: str, port: int
) -> Any:
    """Start the app while inheriting the launcher-owned OS authority handle."""
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(persistence_dir)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(port),
                "--server.headless",
                "true",
            ],
            cwd=REPO_ROOT,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            close_fds=False,
        )
    _wait_for_server(process, local_url)
    return process


def _seed_legacy_multi_tu_record(repository: SqlitePlantProjectDraftRepository) -> None:
    """Seed a real isolated legacy three-role record for the blocked surface."""
    from tests.test_gate2_formal_multi_tu_workflow import _generate_three_tu
    from core.database_lifecycle import ensure_database_ready

    if not repository.database_path.exists():
        ensure_database_ready(repository.database_path)

    base = _generate_three_tu()
    original_input = copy.deepcopy(base["original_input"])
    legacy_units = original_input["expression_units"]
    for unit in legacy_units:
        unit.pop("five_prime_region", None)
    result = generate_multi_tu_construct(
        project_id="v1-legacy-multi-tu-three-role-97bp",
        project_name=LEGACY_PROJECT_NAME,
        expression_units=legacy_units,
        backbone=original_input["backbone"],
        insertion_settings=original_input["insertion_settings"],
    )
    result["project_id"] = "v1-legacy-multi-tu-three-role-97bp"
    result["project_name"] = LEGACY_PROJECT_NAME
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "project_type": "dual_tu",
        "host_key": "Rice (O. sativa)",
        "expression_target": "Legacy three-role Multi-TU documentation record",
        "current_step": 6,
    }
    result["original_input"] = original_input
    save_mvp_multi_tu_design(result, repository=repository)


def _assert_professional_review_zip_unavailable(page: Page) -> None:
    boundary = page.get_by_text("专业审查包在当前版本不可用", exact=False)
    if boundary.count():
        expect(boundary).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name=re.compile("ZIP", re.IGNORECASE))).to_have_count(0)


def _switch_locale(page: Page, option: str, heading: str) -> None:
    radio = page.get_by_role("radio", name=option, exact=True)
    # Streamlit keeps the sidebar language control mounted even when its input
    # is outside the current scroll viewport on long result pages.
    radio.evaluate("element => element.click()")
    expect(radio).to_be_checked(timeout=30_000)
    page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=30_000)


def _assert_no_chinese_leakage(page: Page) -> None:
    # The persistent language control intentionally exposes the option label
    # "中文" even while English is selected; exclude that control from the
    # target-surface copy check.
    body = page.locator("body").inner_text().replace("中文", "")
    assert not re.search(r"[\u3400-\u9fff]", body), body[-2_000:]


def _open_project(page: Page, project_name: str, *, expected_heading: str) -> None:
    expect(page.get_by_text(project_name, exact=True)).to_be_visible(timeout=30_000)
    project_card = page.get_by_text(project_name, exact=True).locator(
        "xpath=ancestor::div[.//button][1]"
    )
    project_card.get_by_role("button", name=re.compile("Open|打开", re.IGNORECASE)).click()
    page.get_by_role("heading", name=expected_heading, exact=True).wait_for(timeout=30_000)
    expect(page.locator('[class*="st-key-formal_project_table_head"]')).to_have_count(0)
    expect(page.locator('[class*="st-key-formal_project_summary_"]')).to_have_count(0)


def _plan_units(page: Page) -> None:
    if TU_COUNT == 3:
        _click_button(page, "添加转录单元")
    expect(page.get_by_role("textbox", name="TU 名称", exact=True)).to_have_count(
        TU_COUNT, timeout=30_000
    )
    first_direction = page.get_by_role("combobox", name=re.compile(r"方向$")).nth(0)
    first_direction.click()
    page.get_by_role("option", name="反向", exact=True).click()
    down_buttons = page.get_by_role("button", name="下移", exact=True)
    expect(down_buttons).to_have_count(TU_COUNT)
    down_buttons.nth(0).click()
    expect(page.get_by_role("textbox", name="TU 名称", exact=True).nth(0)).to_have_value(
        EXPECTED_DISPLAY_ORDER[0], timeout=30_000
    )
    _click_button(page, "保存 TU 规划并继续")


def _activate_user_sequence_textbox(page: Page, source_index: int, textbox_name: str):
    unit_label = textbox_name.split(" ", 1)[0]
    for _ in range(3):
        page.get_by_role("tab", name=f"{unit_label} 表达盒", exact=True).click()
        page.wait_for_timeout(500)
        active_panel = page.locator('[role="tabpanel"]:visible')
        textbox = active_panel.get_by_role("textbox", name=textbox_name, exact=True)
        source_groups = active_panel.get_by_role(
            "radiogroup", name="button group", exact=True
        )
        if source_groups.count() == 4:
            source_groups.nth(source_index).get_by_role(
                "button", name="用户序列", exact=True
            ).click()
        else:
            source_options = active_panel.get_by_text("用户序列", exact=True)
            expect(source_options).to_have_count(4)
            source_options.nth(source_index).click()
        page.wait_for_timeout(750)
        if textbox.count() == 1 and textbox.is_visible():
            return textbox
    expect(textbox).to_be_visible(timeout=5_000)
    return textbox


def _fill_unit(page: Page, index: int, fixture: dict[str, str]) -> None:
    page.get_by_role("tab", name=f"TU{index} 表达盒", exact=True).click()
    # The first analyzed user sequence allocates the project identity used by
    # Streamlit's Multi-TU widget owner. Establish it before the other roles.
    cds_name_input = _activate_user_sequence_textbox(page, 2, f"TU{index} CDS名称")
    cds_name_input.fill(fixture["cds_name"])
    cds_input = page.get_by_role("textbox", name=f"TU{index} CDS DNA/FASTA", exact=True)
    cds_input.fill(fixture["cds"])
    cds_input.press("Control+Enter")
    page.wait_for_timeout(750)

    # The final CDS hydration rerun can restore the first segmented control to
    # its default. Reconfirm the promoter last so all four required roles are
    # current in the same rendered TU state.
    promoter_name_input = _activate_user_sequence_textbox(
        page, 0, f"TU{index} 启动子名称"
    )
    promoter_name_input.fill(fixture["promoter_name"])
    promoter_input = page.get_by_role(
        "textbox", name=f"TU{index} 启动子 DNA/FASTA", exact=True
    )
    promoter_input.fill(fixture["promoter"])
    promoter_input.press("Control+Enter")
    page.wait_for_timeout(1_000)

    promoter_name_input = _activate_user_sequence_textbox(
        page, 0, f"TU{index} 启动子名称"
    )
    promoter_name_input.fill(fixture["promoter_name"])
    promoter_input = page.get_by_role(
        "textbox", name=f"TU{index} 启动子 DNA/FASTA", exact=True
    )
    promoter_input.fill(fixture["promoter"])
    promoter_input.press("Control+Enter")

    five_prime_name_input = _activate_user_sequence_textbox(
        page, 1, f"TU{index} 5′端调控区名称"
    )
    five_prime_name_input.fill(fixture["five_prime_name"])
    page.get_by_role(
        "textbox", name=f"TU{index} 5′端调控区 DNA/FASTA", exact=True
    ).fill(fixture["five_prime"])
    page.get_by_role(
        "textbox", name=f"TU{index} 5′端调控区 DNA/FASTA", exact=True
    ).press("Control+Enter")

    _activate_user_sequence_textbox(page, 3, f"TU{index} 3′端调控区名称")
    page.get_by_role(
        "textbox", name=f"TU{index} 3′端调控区名称", exact=True
    ).fill(fixture["three_prime_name"])
    three_prime = page.get_by_role(
        "textbox", name=f"TU{index} 3′端调控区 DNA/FASTA", exact=True
    )
    three_prime.fill(fixture["three_prime"])
    three_prime.press("Control+Enter")

    # Reconfirm CDS after the initial widget-owner hydration rerun.
    cds_name_input = _activate_user_sequence_textbox(page, 2, f"TU{index} CDS名称")
    cds_name_input.fill(fixture["cds_name"])
    cds_input = page.get_by_role("textbox", name=f"TU{index} CDS DNA/FASTA", exact=True)
    cds_input.fill(fixture["cds"])
    cds_input.press("Control+Enter")


def _ensure_all_units_ready(page: Page, fixtures: tuple[dict[str, str], ...]) -> None:
    """Rehydrate any earlier TU invalidated by a later Streamlit widget rerun."""
    for _ in range(2):
        pending: list[tuple[int, dict[str, str]]] = []
        for index, fixture in enumerate(fixtures, start=1):
            page.get_by_role("tab", name=f"TU{index} 表达盒", exact=True).click()
            active_panel = page.locator('[role="tabpanel"]:visible')
            if "可生成" not in active_panel.inner_text():
                pending.append((index, fixture))
        if not pending:
            return
        for index, fixture in pending:
            _fill_unit(page, index, fixture)
            expect(page.locator('[role="tabpanel"]:visible')).to_contain_text(
                "可生成", timeout=30_000
            )
    for index in range(1, len(fixtures) + 1):
        page.get_by_role("tab", name=f"TU{index} 表达盒", exact=True).click()
        expect(page.locator('[role="tabpanel"]:visible')).to_contain_text(
            "可生成", timeout=30_000
        )


def _build_blank_multi_tu(page: Page, *, confirm_step5: bool = True) -> None:
    _click_button(page, "新建多转录单元项目")
    page.get_by_role("heading", name="第一步：项目定义与表达目标", exact=True).wait_for()
    page.get_by_role("textbox", name="项目名称 *", exact=True).fill(PROJECT_NAME)
    host_combobox = page.get_by_role("combobox", name=re.compile(r"植物宿主 \*$"))
    expect(host_combobox).to_have_count(1)
    host_combobox.click()
    host_option = page.get_by_role(
        "option", name="Tobacco / Nicotiana benthamiana", exact=True
    )
    expect(host_option).to_have_count(1)
    host_option.evaluate("element => element.click()")
    _click_button(page, "下一步")

    page.get_by_role("heading", name="第二步：TU 规划", exact=True).wait_for()
    _plan_units(page)
    page.get_by_role("heading", name="第三步：TU 元件设计", exact=True).wait_for()

    # The first move-down changes the original Alpha/Beta order to Beta/Alpha/Gamma.
    ordered_fixtures = (TU_FIXTURES[1], TU_FIXTURES[0], TU_FIXTURES[2])[:TU_COUNT]
    for index, fixture in enumerate(ordered_fixtures, start=1):
        _fill_unit(page, index, fixture)
        active_panel = page.locator('[role="tabpanel"]:visible')
        expect(active_panel).to_contain_text("可生成", timeout=30_000)
    _ensure_all_units_ready(page, ordered_fixtures)
    _click_button(page, "确认全部 TU 配置并生成组装体，进入下一步")

    page.get_by_role("heading", name="第四步：组装设置 / Canonical assembly", exact=True).wait_for()
    _click_button(page, "确认 Step 4 并继续")

    page.get_by_role("heading", name="第五步：Canonical assembly 校验", exact=True).wait_for()
    expect(page.locator("body")).to_contain_text("计算阻断", timeout=30_000)
    expect(page.locator("body")).to_contain_text("97 bp", timeout=30_000)
    if not confirm_step5:
        return
    _click_button(page, "确认并查看结果")
    page.get_by_role("heading", name="第六步：结果与导出", exact=True).wait_for()
    page.get_by_role("heading", name="保存与导出", exact=True).wait_for(timeout=30_000)
    _assert_sequence_viewer_dom(page, expected_length=97)
    _click_button(page, "保存项目")
    expect(page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)).to_be_visible(
        timeout=30_000
    )


def _assert_sequence_viewer_dom(page: Page, *, expected_length: int) -> None:
    """Prove the shared viewer's real DOM line contract for the 97 bp fixture."""
    page.get_by_role("tab", name="序列", exact=True).click()
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
    assert lines.nth(expected_lines - 1).get_attribute("data-start") == "61"
    assert lines.nth(expected_lines - 1).get_attribute("data-end") == "97"
    assert lines.evaluate_all("rows => rows.map(row => row.textContent.trim().split(/\\s+/).at(-1).length)") == [60, 37]
    assert "mono" in viewer.evaluate("el => getComputedStyle(el).fontFamily").lower()
    metrics = viewer.evaluate(
        "el => ({height: el.clientHeight, scrollHeight: el.scrollHeight, overflowY: getComputedStyle(el).overflowY})"
    )
    assert metrics["height"] <= 360
    assert metrics["overflowY"] in {"auto", "scroll"}


def _download_pair(page: Page, directory: Path, prefix: str) -> tuple[Path, Path]:
    return (
        _download(page, "多 TU 区域 canonical FASTA", directory / f"{prefix}.fasta"),
        _download(page, "多 TU 区域 canonical GenBank", directory / f"{prefix}.gb"),
    )


def _assert_wide_download_layout(page: Page) -> dict[str, Any]:
    page.set_viewport_size({"width": 2560, "height": 1440})
    page.get_by_role("heading", name="保存与导出", exact=True).scroll_into_view_if_needed()

    def row_widths(button_name: str, expected_count: int) -> list[float]:
        button = page.get_by_role("button", name=button_name, exact=True)
        expect(button).to_be_visible(timeout=30_000)
        row = button.locator("xpath=ancestor::div[@data-testid='stHorizontalBlock'][1]")
        expect(row).to_have_count(1)
        columns = row.locator('[data-testid="stColumn"]')
        expect(columns).to_have_count(expected_count)
        widths = [
            float(columns.nth(index).bounding_box()["width"])
            for index in range(expected_count)
        ]
        assert max(widths) - min(widths) <= 2.0, widths
        return widths

    unit_widths = row_widths("TU1 FASTA", 3)
    canonical_widths = row_widths("多 TU 区域 canonical FASTA", 2)
    overflow = page.evaluate(
        "() => ({scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth})"
    )
    assert overflow["scrollWidth"] <= overflow["innerWidth"], overflow
    return {
        "viewport": "2560x1440",
        "unit_column_widths": unit_widths,
        "canonical_column_widths": canonical_widths,
        "horizontal_overflow": overflow,
    }


def _canonical_export_evidence(
    fasta_path: Path,
    genbank_path: Path,
    *,
    repository: SqlitePlantProjectDraftRepository | None = None,
    expected_project_name: str = PROJECT_NAME,
    expected_display_order: list[str] | None = None,
    expected_orientations: list[str] | None = None,
) -> dict[str, Any]:
    repository = repository or SqlitePlantProjectDraftRepository()
    summaries = [
        summary
        for summary in list_mvp_multi_tu_designs(repository=repository)
        if summary.project_name == expected_project_name
    ]
    if len(summaries) != 1:
        raise AssertionError(f"expected one saved multi-TU project, got {len(summaries)}")
    reopened = open_mvp_multi_tu_design(summaries[0].project_id, repository=repository)
    context = dict(reopened.get("formal_project_context") or {})
    formal_state = dict(context.get("formal_state") or {})
    if context.get("record_kind") != "formal_editor_completed":
        raise AssertionError("Multi-TU completed editor state was not persisted")
    if int(context.get("current_step") or 0) != 6:
        raise AssertionError("Multi-TU completed editor state did not retain Step 6")
    if not formal_state.get("formal_multi_tu_step4_confirmation_signature"):
        raise AssertionError("Multi-TU Step 4 confirmation was not persisted")
    if not formal_state.get("formal_multi_tu_step5_confirmation_signature"):
        raise AssertionError("Multi-TU Step 5 confirmation was not persisted")
    if not reopened.get("formal_editor_restoration_eligible"):
        raise AssertionError("Multi-TU completed editor record was not reopenable")
    canonical = active_construct_snapshot(reopened["runtime"])
    canonical_sequence = str(canonical["sequence"]).upper()
    fasta = SeqIO.read(StringIO(fasta_path.read_text(encoding="utf-8")), "fasta")
    genbank = SeqIO.read(StringIO(genbank_path.read_text(encoding="utf-8")), "genbank")
    if str(fasta.seq).upper() != canonical_sequence:
        raise AssertionError("FASTA sequence differed from the active canonical Multi-TU assembly")
    if str(genbank.seq).upper() != canonical_sequence:
        raise AssertionError("GenBank sequence differed from the active canonical Multi-TU assembly")

    units = sorted(reopened["expression_units"], key=lambda unit: int(unit["order"]))
    display_order = [str(unit["display_name"]) for unit in units]
    orientations = [str(unit["orientation"]) for unit in units]
    unit_ids = [str(unit["unit_id"]) for unit in units]
    expected_display_order = expected_display_order or EXPECTED_DISPLAY_ORDER
    expected_orientations = expected_orientations or EXPECTED_ORIENTATIONS
    if display_order != expected_display_order:
        raise AssertionError(f"unexpected saved TU order: {display_order}")
    if orientations != expected_orientations:
        raise AssertionError(f"unexpected saved orientations: {orientations}")
    if len(set(unit_ids)) != TU_COUNT:
        raise AssertionError(
            f"expected {TU_COUNT} stable unique unit IDs: {unit_ids}"
        )
    previous_end = 0
    for unit in units:
        unit_range = dict(unit.get("range") or {})
        if int(unit_range.get("start") or 0) != previous_end + 1:
            raise AssertionError(f"non-contiguous unit coordinate: {unit_range}")
        if int(unit_range.get("strand") or 0) != (-1 if unit["orientation"] == "reverse" else 1):
            raise AssertionError(f"unit strand did not match orientation: {unit_range}")
        previous_end = int(unit_range.get("end") or 0)
        for component in unit.get("components") or []:
            if str(component.get("unit_id")) != str(unit["unit_id"]):
                raise AssertionError("component unit_id differed from its enclosing TU")
            if not (int(unit_range["start"]) <= int(component["start"]) <= int(component["end"]) <= int(unit_range["end"])):
                raise AssertionError("component coordinate fell outside its TU range")

    validation = dict(canonical.get("validation_summary") or {})
    if int(validation.get("blocking_count") or 0) != 0:
        raise AssertionError("canonical validation retained blocking findings")
    return {
        "project_id": summaries[0].project_id,
        "canonical_length": len(canonical_sequence),
        "canonical_sha256": hashlib.sha256(canonical_sequence.encode("ascii")).hexdigest(),
        "validation_blocking_count": int(validation.get("blocking_count") or 0),
        "validation_warning_count": int(validation.get("warning_count") or 0),
        "display_order": display_order,
        "unit_order": list(reopened["unit_order"]),
        "unit_ids": unit_ids,
        "orientations": orientations,
        "unit_ranges": [dict(unit["range"]) for unit in units],
        "component_coordinates": [list(unit.get("components") or []) for unit in units],
        "fasta_matches_canonical": True,
        "genbank_matches_canonical": True,
        "completed_editor_record": True,
        "restored_step": 6,
        "step4_confirmation_persisted": True,
        "step5_confirmation_persisted": True,
    }


def _reopen_from_home(page: Page) -> None:
    page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text(PROJECT_NAME, exact=True)).to_be_visible(timeout=30_000)
    project_card = page.get_by_text(PROJECT_NAME, exact=True).locator(
        "xpath=ancestor::div[.//button][1]"
    )
    open_button = project_card.get_by_role("button", name="打开", exact=True)
    expect(open_button).to_have_count(1)
    open_button.click()
    page.get_by_role("heading", name="第六步：结果与导出", exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator('[class*="st-key-formal_project_table_head"]')).to_have_count(0)
    expect(page.locator('[class*="st-key-formal_project_summary_"]')).to_have_count(0)
    expect(
        page.get_by_role("heading", name="结果与导出（历史结果预览）", exact=True)
    ).to_have_count(0)
    for name in EXPECTED_DISPLAY_ORDER:
        expect(page.locator("body")).to_contain_text(name)
    _click_button(page, "1. 项目定义")
    page.get_by_role(
        "heading", name="第一步：项目定义与表达目标", exact=True
    ).wait_for(timeout=30_000)
    expect(page.get_by_role("textbox", name="项目名称 *", exact=True)).to_have_value(
        PROJECT_NAME
    )
    _click_button(page, "6. 结果与导出")
    page.get_by_role("heading", name="第六步：结果与导出", exact=True).wait_for(
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
    pre_acceptance_production_database = snapshot_active_production_database()

    configured_run_root = os.environ.get("BIODESIGN_ACCEPTANCE_RUN_ROOT")
    run_root_context = (
        nullcontext(Path(configured_run_root).expanduser().resolve(strict=False))
        if configured_run_root
        else tempfile.TemporaryDirectory(prefix="formal_multi_tu_blank_")
    )
    with run_root_context as temp_dir:
        work_dir = Path(temp_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        persistence_dir = work_dir / "isolated_project_drafts"
        database_path = persistence_dir / "biodesign_unified.db"
        repository = SqlitePlantProjectDraftRepository(database_path)
        export_dir = ARTIFACT_ROOT / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                configure_acceptance_fixture_context(
                    seed=FIXTURE_IDENTITY,
                    run_root=work_dir,
                    database_path=database_path,
                    pre_acceptance_production_database_path=pre_acceptance_production_database,
                )
                _seed_legacy_multi_tu_record(repository)
                active_process = _start_server_with_authority(
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
                _assert_no_chinese_leakage(page)
                result["steps"]["initial_english_project_center"] = "passed"

                # Scenario A: an isolated legacy three-role record is blocked
                # before Step 5 and exposes the localized review surface.
                _open_project(
                    page,
                    LEGACY_PROJECT_NAME,
                    expected_heading="Results & Export (Historical Results Preview)",
                )
                expect(page.locator("body")).to_contain_text("5-prime region required")
                expect(page.locator("body")).to_contain_text(
                    "A legacy three-role record was loaded."
                )
                expect(page.locator("body")).to_contain_text("97 bp")
                _assert_no_chinese_leakage(page)
                result["steps"]["legacy_blocking_reason_en"] = "passed"
                _switch_locale(page, "中文", "结果与导出（历史结果预览）")
                expect(page.locator("body")).to_contain_text("需补充 5′ 区域")
                expect(page.locator("body")).to_contain_text("已读取旧版三角色记录")
                expect(page.locator("body")).to_contain_text("97 bp")
                result["steps"]["legacy_blocking_reason_zh_and_state_preserved"] = "passed"

                _click_button(page, "项目中心")
                page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)

                # Scenario B: build a valid 97 bp record, compare Step 5 in
                # English and Chinese, then confirm without a durable save.
                _build_blank_multi_tu(page, confirm_step5=False)
                expect(page.get_by_role("button", name="确认并查看结果", exact=True)).to_be_visible()
                expect(page.locator("body")).to_contain_text("97 bp")
                _switch_locale(page, "EN", "Step 5: Canonical Assembly Check")
                expect(page.get_by_role("button", name="Confirm and view results", exact=True)).to_be_visible()
                expect(page.locator("body")).to_contain_text("97 bp")
                _assert_no_chinese_leakage(page)
                result["steps"]["valid_step5_action_en"] = "passed"
                _switch_locale(page, "中文", "第五步：Canonical assembly 校验")
                expect(page.get_by_role("button", name="确认并查看结果", exact=True)).to_be_visible()
                expect(page.locator("body")).to_contain_text("97 bp")
                _click_button(page, "确认并查看结果")
                expect(page.get_by_role("heading", name="第六步：结果与导出", exact=True)).to_be_visible()
                expect(page.locator("body")).to_contain_text("97 bp")
                _assert_sequence_viewer_dom(page, expected_length=97)
                page.screenshot(path=str(ARTIFACT_ROOT / "step6-97bp-sequence.png"), full_page=True)
                (ARTIFACT_ROOT / "step6-97bp-sequence-dom.html").write_text(page.content(), encoding="utf-8")
                expect(page.locator("body")).not_to_contain_text("st.dataframe(")
                result["wide_download_layout"] = _assert_wide_download_layout(page)
                page.screenshot(path=str(ARTIFACT_ROOT / "step6-download-layout-2560x1440.png"), full_page=True)
                result["steps"]["multi_tu_download_layout_2560x1440"] = "passed"
                result["steps"]["step6_intended_results_without_source_fragment"] = "passed"
                result["steps"]["valid_step5_action_zh_confirm_to_step6"] = "passed"
                if not os.environ.get("BIODESIGN_ACCEPTANCE_FULL_LOOP"):
                    # The focused R1 contract deliberately stops at Step 6:
                    # it proves navigation without making a durable-save claim.
                    _assert_clean_page(page, browser_errors)
                    result["steps"]["focused_browser_contract"] = "passed"
                    result["passed"] = True
                else:
                    _assert_professional_review_zip_unavailable(page)
                    result["professional_review_zip_unavailable_before_restart"] = True
                    _assert_clean_page(page, browser_errors)
                    _click_button(page, "保存项目")
                    expect(page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)).to_be_visible(
                        timeout=30_000
                    )
                    result["steps"]["valid_step6_save_after_confirmation"] = "passed"
                    before_fasta, before_genbank = _download_pair(page, export_dir, "before_restart")
                    before_evidence = _canonical_export_evidence(
                        before_fasta, before_genbank, repository=repository
                    )
                    result["before_restart"] = before_evidence

                    page.close()
                    page = None
                    _stop_server(active_process)
                    active_process = None
                    if processes[0].poll() is None:
                        raise AssertionError("the first Streamlit process remained alive after stop")
                    result["steps"]["complete_stop_before_cold_start"] = "passed"
                    refresh_acceptance_fixture_authority()

                    active_process = _start_server_with_authority(
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
                    _assert_sequence_viewer_dom(page, expected_length=97)
                    page.screenshot(path=str(ARTIFACT_ROOT / "cold-reopen-97bp-sequence.png"), full_page=True)
                    _assert_professional_review_zip_unavailable(page)
                    result["professional_review_zip_unavailable_after_restart"] = True
                    _assert_clean_page(page, browser_errors)
                    after_fasta, after_genbank = _download_pair(page, export_dir, "after_restart")
                    after_evidence = _canonical_export_evidence(
                        after_fasta, after_genbank, repository=repository
                    )
                    result["after_restart"] = after_evidence
                    result["fasta_bytes_identical"] = before_fasta.read_bytes() == after_fasta.read_bytes()
                    result["genbank_bytes_identical"] = before_genbank.read_bytes() == after_genbank.read_bytes()
                    if not result["fasta_bytes_identical"] or not result["genbank_bytes_identical"]:
                        raise AssertionError("restart export bytes were not identical")
                    if before_evidence != after_evidence:
                        raise AssertionError("TU or canonical evidence changed after cold restart")
                    result["initial_fasta_sha256"] = hashlib.sha256(before_fasta.read_bytes()).hexdigest()
                    result["initial_genbank_sha256"] = hashlib.sha256(before_genbank.read_bytes()).hexdigest()
                    result["fasta_sha256"] = hashlib.sha256(after_fasta.read_bytes()).hexdigest()
                    result["genbank_sha256"] = hashlib.sha256(after_genbank.read_bytes()).hexdigest()
                    result["retained_exports"] = [
                        str(path.relative_to(ARTIFACT_ROOT)).replace("\\", "/")
                        for path in (before_fasta, before_genbank, after_fasta, after_genbank)
                    ]
                    result["steps"]["cold_start_home_reopen_and_deterministic_export"] = "passed"
                    result["passed"] = True
            except Exception as exc:
                result["first_blocker"] = f"{type(exc).__name__}: {exc}"
                if page is not None and not page.is_closed():
                    result["visible_page_tail"] = page.locator("body").inner_text()[-4_000:]
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
    clear_acceptance_fixture_context()
    # Keep machine-readable launcher output safe on Windows consoles whose
    # legacy code page cannot encode the browser's Chinese evidence text.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
