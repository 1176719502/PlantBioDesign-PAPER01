"""Formal app.py acceptance for a current-UI single-gene cold-reopen loop."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO
from playwright.sync_api import Page, expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.canonical_construct_runtime import active_complete_plasmid_snapshot
from services.mvp_single_gene_persistence import list_mvp_single_gene_designs, open_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.rice_hsa_ncbi_mvp10_case import load_rice_hsa_ncbi_case


ACCEPTANCE_ARTIFACT_BASE = Path(
    os.environ.get("BIODESIGN_ACCEPTANCE_ARTIFACT_ROOT")
    or Path(tempfile.gettempdir()) / "BioDesignStudio" / "formal_acceptance"
).expanduser().resolve(strict=False)
if ACCEPTANCE_ARTIFACT_BASE == REPO_ROOT or REPO_ROOT in ACCEPTANCE_ARTIFACT_BASE.parents:
    raise RuntimeError("BIODESIGN_ACCEPTANCE_ARTIFACT_ROOT must be outside the repository")
ARTIFACT_ROOT = ACCEPTANCE_ARTIFACT_BASE / "formal_single_gene_blank_acceptance"
PROJECT_NAME = "正式单基因保存重开验收"
EXPECTED_CANONICAL_LENGTH = 11_778
EXPECTED_CANONICAL_SHA256 = (
    "bc8539b361349611fde41fa5e0292d68b6327bc9ec0f834aaa6ec566882c12d2"
)
FORMAL_REVIEW_ZIP_BOUNDARY = "专业审查 ZIP 不在正式 V1 产品范围内"
MULTI_TU_REVIEW_ZIP_BOUNDARY = "专业审查包当前版本不可用"
FORBIDDEN_PAGE_TEXT = (
    "Traceback",
    "StreamlitAPIException",
    "NotFoundError",
    "DuplicateElementKey",
)
SERVER_EXCEPTION_PATTERN = re.compile(
    r"Traceback \(most recent call last\)|StreamlitAPIException|"
    r"NotFoundError|DuplicateElementKey",
    re.IGNORECASE,
)


def _reserve_local_url() -> tuple[str, int]:
    configured_port = os.environ.get("BIODESIGN_ACCEPTANCE_PORT")
    requested_port = int(configured_port) if configured_port else 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", requested_port))
        port = int(sock.getsockname()[1])
    return f"http://127.0.0.1:{port}", port


def _assert_professional_review_zip_unavailable(page: Page) -> None:
    formal_boundary = page.get_by_text(FORMAL_REVIEW_ZIP_BOUNDARY, exact=False)
    zip_buttons = page.get_by_role("button", name=re.compile("ZIP", re.IGNORECASE))
    if formal_boundary.count():
        expect(formal_boundary).to_be_visible(timeout=30_000)
        if zip_buttons.count() != 0:
            raise AssertionError("the complete-plasmid result route exposed a ZIP button")
        return

    expect(page.get_by_text(MULTI_TU_REVIEW_ZIP_BOUNDARY, exact=False)).to_be_visible(
        timeout=30_000
    )
    expect(zip_buttons).to_have_count(1)
    expect(zip_buttons).to_be_disabled()


def _assert_single_gene_review_zip_unavailable(page: Page) -> None:
    expect(page.get_by_role("button", name=re.compile("ZIP", re.IGNORECASE))).to_have_count(0)


def _wait_for_server(process: subprocess.Popen[str], local_url: str) -> None:
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited before readiness (exit {process.returncode}).")
        try:
            with urllib.request.urlopen(local_url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become ready at {local_url}: {last_error}")


def _start_server(
    *, log_path: Path, persistence_dir: Path, local_url: str, port: int
) -> subprocess.Popen[str]:
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
        )
    _wait_for_server(process, local_url)
    return process


def _stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        process.wait(timeout=10)


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _attach_browser_errors(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}")
        if message.type == "error"
        else None,
    )


def _assert_clean_page(page: Page, browser_errors: list[str]) -> None:
    body_text = page.locator("body").inner_text()
    visible = [item for item in FORBIDDEN_PAGE_TEXT if item.casefold() in body_text.casefold()]
    if visible:
        raise AssertionError(f"forbidden page text was visible: {visible}")
    if page.locator('[data-testid="stException"]').count():
        raise AssertionError("Streamlit exception widget was visible")
    if browser_errors:
        raise AssertionError("browser errors: " + " | ".join(browser_errors))


def _switch_locale(page: Page, option: str, heading: str) -> None:
    radio = page.get_by_role("radio", name=option, exact=True)
    radio.evaluate("element => element.click()")
    expect(radio).to_be_checked(timeout=30_000)
    page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=30_000)


def _click_button(page: Page, name: str, *, timeout: int = 30_000) -> None:
    button = page.get_by_role("button", name=name, exact=True)
    expect(button).to_have_count(1, timeout=timeout)
    expect(button).to_be_enabled(timeout=timeout)
    button.click(timeout=timeout)


def _assert_current_step3_can_continue_to_step4(page: Page) -> None:
    """Require the current cassette and the production Step 4 availability gate."""
    step4_card = page.locator(".st-key-formal_step_card_4_available")
    expect(step4_card).to_have_count(1, timeout=30_000)

    step4_button = step4_card.get_by_role(
        "button", name="4. 载体骨架", exact=True
    )
    expect(step4_button).to_have_count(1)
    expect(step4_button).to_be_enabled()

    continue_button = page.get_by_role("button", name="下一步", exact=True)
    expect(continue_button).to_have_count(1)
    expect(continue_button).to_be_enabled()
    expect(
        page.get_by_role("button", name="生成表达盒", exact=True)
    ).to_have_count(0)


def _assert_publication_map_current(page: Page, *, expected_count: int) -> None:
    publication_map_downloads = page.get_by_role(
        "button", name="下载 Publication Map SVG", exact=True
    )
    expect(publication_map_downloads).to_have_count(expected_count, timeout=30_000)
    for index in range(expected_count):
        expect(publication_map_downloads.nth(index)).to_be_enabled()


def _assert_step6_publication_maps_current(page: Page) -> None:
    for tab_name in ("环状图", "线性图"):
        tab = page.get_by_text(tab_name, exact=True)
        expect(tab).to_have_count(1, timeout=30_000)
        tab.click()
        publication_map_download = page.get_by_role(
            "button", name="下载 Publication Map SVG", exact=True
        )
        expect(publication_map_download).to_have_count(1, timeout=30_000)
        expect(publication_map_download).to_be_enabled()


def _select_streamlit_option(page: Page, combobox_name: re.Pattern[str], option_name: str) -> None:
    combobox = page.get_by_role("combobox", name=combobox_name)
    expect(combobox).to_have_count(1)
    combobox.click()
    option = page.get_by_role("option", name=option_name, exact=True)
    expect(option).to_have_count(1)
    option.click()


def _activate_single_gene_user_sequence(
    page: Page, source_index: int, textbox_name: str
):
    textbox = page.get_by_role("textbox", name=textbox_name, exact=True)
    source_groups = page.get_by_role(
        "radiogroup", name="button group", exact=True
    ).filter(has=page.get_by_role("button", name="元件库", exact=True))
    if source_groups.count() == 2:
        source_groups.nth(source_index).get_by_role(
            "button", name="用户序列", exact=True
        ).click()
    else:
        source_options = page.get_by_text("用户序列", exact=True)
        expect(source_options).to_have_count(2)
        source_options.nth(source_index).click()
    expect(textbox).to_be_visible(timeout=30_000)
    return textbox


def _build_blank_single_gene(page: Page) -> None:
    case = load_rice_hsa_ncbi_case()
    assets = case["assets"]

    _click_button(page, "新建单基因项目")
    page.get_by_role("heading", name="第一步：项目定义与表达目标", exact=True).wait_for(
        timeout=30_000
    )
    page.get_by_role("textbox", name="项目名称 *", exact=True).fill(PROJECT_NAME)
    _select_streamlit_option(page, re.compile(r"植物宿主 \*$"), "Rice / Oryza sativa")
    _click_button(page, "下一步")

    page.get_by_role("heading", name="第二步：目标基因与编码序列（CDS）", exact=True).wait_for(
        timeout=30_000
    )
    page.get_by_role("textbox", name="目标基因名称（必填）", exact=True).fill("ALB CDS")
    page.get_by_role("textbox", name="accession 或来源说明（必填）", exact=True).fill(
        "NM_000477.7"
    )
    cds_input = page.get_by_role("textbox", name="粘贴核酸序列", exact=True)
    cds_input.fill(assets["cds"]["sequence"])
    cds_input.press("Control+Enter")
    _click_button(page, "确认 CDS 并继续")

    page.get_by_role("heading", name="第三步：植物表达盒设计", exact=True).wait_for(
        timeout=30_000
    )
    promoter_name = _activate_single_gene_user_sequence(page, 0, "启动子名称")
    promoter_name.fill("CaMV35S promoter")
    page.get_by_role("textbox", name="启动子 DNA/FASTA", exact=True).fill(
        assets["promoter"]["sequence"]
    )
    three_prime_name = _activate_single_gene_user_sequence(page, 1, "3′端调控元件名称")
    three_prime_name.fill("CaMV 3'UTR (polyA signal)")
    page.get_by_role("textbox", name="3′端调控元件 DNA/FASTA", exact=True).fill(
        assets["terminator"]["sequence"]
    )
    _select_streamlit_option(
        page,
        re.compile(r"3′调控元件生物学角色（用户声明）$"),
        "3′非翻译区（3′ UTR）",
    )
    order_confirmation = page.get_by_role(
        "checkbox", name="我已确认组件排列和方向", exact=True
    )
    page.get_by_text("我已确认组件排列和方向", exact=True).click()
    expect(order_confirmation).to_be_checked(timeout=30_000)
    _click_button(page, "生成表达盒")
    _assert_current_step3_can_continue_to_step4(page)
    _click_button(page, "下一步")

    page.get_by_role("heading", name="第四步：植物二元载体骨架与组装策略", exact=True).wait_for(
        timeout=30_000
    )
    _click_button(page, "选择")
    _click_button(page, "确认骨架并继续")
    page.get_by_role("heading", name="第五步：载体构建设计与计算校验", exact=True).wait_for(
        timeout=30_000
    )
    _click_button(page, "生成完整载体")
    expect(
        page.get_by_text("已生成：载体设计已生成，可以继续第六步。", exact=True)
    ).to_be_visible(timeout=30_000)
    _assert_publication_map_current(page, expected_count=1)
    _click_button(page, "下一步")
    page.get_by_role("heading", name="第六步：项目保存、结果审查与交付", exact=True).wait_for(
        timeout=30_000
    )
    expect(page.locator("body")).to_contain_text("11,778 bp", timeout=30_000)
    expect(page.locator("body")).to_contain_text("AF234296.1", timeout=30_000)
    _assert_step6_publication_maps_current(page)
    _click_button(page, "保存项目")
    expect(
        page.get_by_text("项目已保存，可从项目中心重新打开。", exact=True)
    ).to_be_visible(timeout=30_000)


def _download(page: Page, button_name: str, target: Path) -> Path:
    with page.expect_download(timeout=45_000) as download_info:
        _click_button(page, button_name, timeout=45_000)
    download_info.value.save_as(target)
    return target


def _download_pair(page: Page, directory: Path, prefix: str) -> tuple[Path, Path]:
    return (
        _download(page, "完整质粒 FASTA", directory / f"{prefix}.fasta"),
        _download(page, "完整质粒 GenBank", directory / f"{prefix}.gb"),
    )


def _canonical_and_export_evidence(
    persistence_dir: Path, fasta_path: Path, genbank_path: Path
) -> dict[str, Any]:
    repository = PlantProjectDraftRepository(persistence_dir)
    summaries = list_mvp_single_gene_designs(repository=repository)
    if len(summaries) != 1:
        raise AssertionError(f"expected one saved single-gene project, got {len(summaries)}")
    reopened = open_mvp_single_gene_design(summaries[0].project_id, repository=repository)
    canonical = active_complete_plasmid_snapshot(reopened["runtime"])
    canonical_sequence = str(canonical["sequence"]).upper()
    fasta = SeqIO.read(StringIO(fasta_path.read_text(encoding="utf-8")), "fasta")
    genbank = SeqIO.read(StringIO(genbank_path.read_text(encoding="utf-8")), "genbank")
    fasta_sequence = str(fasta.seq).upper()
    genbank_sequence = str(genbank.seq).upper()
    if fasta_sequence != canonical_sequence:
        raise AssertionError("FASTA sequence differed from the active canonical complete plasmid")
    if genbank_sequence != canonical_sequence:
        raise AssertionError("GenBank sequence differed from the active canonical complete plasmid")
    if int(canonical["validation_summary"]["blocking_count"]) != 0:
        raise AssertionError("canonical validation retained blocking findings")
    canonical_sha256 = hashlib.sha256(canonical_sequence.encode("ascii")).hexdigest()
    if len(canonical_sequence) != EXPECTED_CANONICAL_LENGTH:
        raise AssertionError(
            f"canonical length changed: {len(canonical_sequence)} != "
            f"{EXPECTED_CANONICAL_LENGTH}"
        )
    if canonical_sha256 != EXPECTED_CANONICAL_SHA256:
        raise AssertionError(
            f"canonical SHA-256 changed: {canonical_sha256} != "
            f"{EXPECTED_CANONICAL_SHA256}"
        )
    formal_context = reopened.get("formal_project_context")
    formal_context = formal_context if isinstance(formal_context, dict) else {}
    formal_state = formal_context.get("formal_state")
    formal_state = formal_state if isinstance(formal_state, dict) else {}
    persisted = repository.load(summaries[0].project_id)
    if persisted.draft_status != "completed" or not persisted.canonical_available:
        raise AssertionError("single-gene Step 6 save did not create a completed project record")
    if persisted.workflow_type != "single_gene":
        raise AssertionError("single-gene Step 6 save changed the workflow identity")
    if formal_context.get("record_kind") != "formal_editor_completed":
        raise AssertionError("single-gene completed editor state was not persisted")
    if int(formal_context.get("current_step") or 0) != 6:
        raise AssertionError("single-gene completed editor state did not retain Step 6")
    if not formal_state.get("formal_step4_strategy_confirmed"):
        raise AssertionError("single-gene Step 4 confirmation was not persisted")
    if not formal_state.get("formal_step5_strategy_confirmed"):
        raise AssertionError("single-gene Step 5 confirmation was not persisted")
    persisted_ai_route_keys = sorted(
        str(key) for key in formal_state if str(key).startswith("formal_ai_route_")
    )
    if persisted_ai_route_keys:
        raise AssertionError(
            "session-only formal AI route state was persisted: "
            + ", ".join(persisted_ai_route_keys)
        )
    return {
        "project_id": summaries[0].project_id,
        "canonical_length": len(canonical_sequence),
        "canonical_sha256": canonical_sha256,
        "validation_blocking_count": int(canonical["validation_summary"]["blocking_count"]),
        "validation_warning_count": int(canonical["validation_summary"]["warning_count"]),
        "fasta_matches_canonical": True,
        "genbank_matches_canonical": True,
        "completed_record": True,
        "restored_step": 6,
        "step4_confirmation_persisted": True,
        "step5_confirmation_persisted": True,
        "persisted_formal_ai_route_keys": persisted_ai_route_keys,
    }


def _reopen_from_home(page: Page) -> None:
    page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)
    expect(page.get_by_text(PROJECT_NAME, exact=True)).to_be_visible(timeout=30_000)
    project_card = page.locator(
        '[class*="st-key-formal_project_summary_"]'
    ).filter(has_text=PROJECT_NAME)
    expect(project_card).to_have_count(1)
    open_button = project_card.get_by_role("button", name="打开", exact=True)
    expect(open_button).to_have_count(1)
    open_button.click()
    page.get_by_role(
        "heading", name="第六步：项目保存、结果审查与交付", exact=True
    ).wait_for(timeout=30_000)
    expect(page.locator('[class*="st-key-formal_project_table_head"]')).to_have_count(0)
    expect(page.locator('[class*="st-key-formal_project_summary_"]')).to_have_count(0)
    expect(page.locator("body")).to_contain_text("11,778 bp", timeout=30_000)
    expect(page.locator("body")).to_contain_text("CaMV35S 启动子")
    expect(page.locator("body")).to_contain_text("ALB 编码序列")
    expect(page.locator("body")).to_contain_text("CaMV 3′ UTR（polyA 信号）")
    _assert_step6_publication_maps_current(page)


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    first_log = ARTIFACT_ROOT / "streamlit-before-restart.log"
    second_log = ARTIFACT_ROOT / "streamlit-after-restart.log"
    result: dict[str, Any] = {
        "passed": False,
        "entrypoint": "app.py",
        "fixture_source": "current Project Center workflow with repository NCBI ALB/CaMV sequence snapshots and the fixed pCAMBIA-1300 contract",
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
    processes: list[subprocess.Popen[str]] = []
    active_process: subprocess.Popen[str] | None = None
    page: Page | None = None
    local_url, port = _reserve_local_url()
    result["port"] = port

    with tempfile.TemporaryDirectory(prefix="formal_single_gene_blank_") as temp_dir:
        work_dir = Path(temp_dir)
        persistence_dir = work_dir / "isolated_project_drafts"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                active_process = _start_server(
                    log_path=first_log,
                    persistence_dir=persistence_dir,
                    local_url=local_url,
                    port=port,
                )
                processes.append(active_process)
                page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
                _attach_browser_errors(page, browser_errors)
                page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
                page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
                _switch_locale(page, "中文", "项目中心")
                _build_blank_single_gene(page)
                _assert_single_gene_review_zip_unavailable(page)
                result["professional_review_zip_unavailable_before_restart"] = True
                result["steps"]["blank_home_to_complete_plasmid_validation_and_save"] = "passed"
                result["steps"]["publication_map_current_before_restart"] = "passed"
                _assert_clean_page(page, browser_errors)
                before_fasta, before_genbank = _download_pair(page, work_dir, "before_restart")
                before_evidence = _canonical_and_export_evidence(
                    persistence_dir, before_fasta, before_genbank
                )
                result["before_restart"] = before_evidence
                result["steps"]["exports_match_current_canonical"] = "passed"

                page.close()
                page = None
                _stop_server(active_process)
                active_process = None
                if processes[0].poll() is None:
                    raise AssertionError("the first Streamlit process remained alive after stop")
                result["steps"]["complete_stop_before_cold_start"] = "passed"

                active_process = _start_server(
                    log_path=second_log,
                    persistence_dir=persistence_dir,
                    local_url=local_url,
                    port=port,
                )
                processes.append(active_process)
                page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
                _attach_browser_errors(page, browser_errors)
                page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
                page.get_by_role("heading", name="Project Center", exact=True).wait_for(timeout=30_000)
                _switch_locale(page, "中文", "项目中心")
                _reopen_from_home(page)
                _assert_single_gene_review_zip_unavailable(page)
                result["professional_review_zip_unavailable_after_restart"] = True
                result["steps"]["publication_map_current_after_restart"] = "passed"
                _assert_clean_page(page, browser_errors)
                after_fasta, after_genbank = _download_pair(page, work_dir, "after_restart")
                after_evidence = _canonical_and_export_evidence(
                    persistence_dir, after_fasta, after_genbank
                )
                result["after_restart"] = after_evidence
                fasta_equal = before_fasta.read_bytes() == after_fasta.read_bytes()
                genbank_equal = before_genbank.read_bytes() == after_genbank.read_bytes()
                result["fasta_bytes_identical"] = fasta_equal
                result["genbank_bytes_identical"] = genbank_equal
                result["fasta_sha256"] = hashlib.sha256(after_fasta.read_bytes()).hexdigest()
                result["genbank_sha256"] = hashlib.sha256(after_genbank.read_bytes()).hexdigest()
                if not fasta_equal or not genbank_equal:
                    raise AssertionError("restart export bytes were not identical")
                if before_evidence != after_evidence:
                    raise AssertionError("canonical evidence changed after cold restart")
                result["steps"]["cold_start_home_reopen_and_deterministic_export"] = "passed"
                result["passed"] = True
            except Exception as exc:
                result["first_blocker"] = f"{type(exc).__name__}: {exc}"
                if page is not None and not page.is_closed():
                    result["failure_body_tail"] = page.locator("body").inner_text()[-4000:]
                    page.screenshot(
                        path=str(ARTIFACT_ROOT / "failure.png"),
                        full_page=True,
                    )
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
    if (not result["process_cleanup_complete"] or not result["port_cleanup_complete"]) and not result[
        "first_blocker"
    ]:
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
    report_path = ARTIFACT_ROOT / "acceptance_result.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
