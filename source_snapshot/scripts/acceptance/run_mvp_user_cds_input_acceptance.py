"""Playwright acceptance for the three MVP5 input paths in the MVP6 page flow."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord
from playwright.sync_api import Browser, Page, expect, sync_playwright

from run_mvp_three_round_acceptance import (
    ARTIFACT_ROOT,
    DOWNLOAD_FASTA,
    DOWNLOAD_GENBANK,
    GENERATE_EXPRESSION_CASSETTE,
    GENERATE_COMPLETE_VECTOR,
    SERVER_EXCEPTION_PATTERN,
    reserve_local_url,
    stop_server,
    wait_for_server,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SAVE_CURRENT_DESIGN = "保存项目"
OPEN_SAVED_DESIGN = "打开"
UPLOAD_FASTA = "上传 CDS FASTA"
PASTE_CDS = "粘贴 CDS DNA/FASTA"
INVALID_DNA_MESSAGE = "".join(map(chr, (0x975E, 0x6CD5, 0x20, 0x44, 0x4E, 0x41, 0x20, 0x5B57, 0x6BCD)))


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _start_server(log_path: Path, persistence_dir: Path) -> tuple[subprocess.Popen[str], str]:
    local_url, port = reserve_local_url()
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(persistence_dir)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "mvp_app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(port),
                "--server.headless",
                "true",
            ],
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
        )
    wait_for_server(process, local_url)
    return process, local_url


def _attach_errors(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)


def _download_pair(page: Page, directory: Path, prefix: str) -> tuple[Path, Path]:
    fasta_path = directory / f"{prefix}.fasta"
    genbank_path = directory / f"{prefix}.gb"
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role("button", name=DOWNLOAD_FASTA, exact=True).click(timeout=10_000)
    download_info.value.save_as(fasta_path)
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role("button", name=DOWNLOAD_GENBANK, exact=True).click(timeout=10_000)
    download_info.value.save_as(genbank_path)
    return fasta_path, genbank_path


def _assert_downloads(fasta_path: Path, genbank_path: Path, expected_length: int) -> list[str]:
    errors: list[str] = []
    fasta = list(SeqIO.parse(StringIO(fasta_path.read_text(encoding="utf-8")), "fasta"))
    genbank = list(SeqIO.parse(StringIO(genbank_path.read_text(encoding="utf-8")), "genbank"))
    if len(fasta) != 1 or len(genbank) != 1:
        return [f"expected one FASTA and one GenBank record, got {len(fasta)} and {len(genbank)}"]
    fasta_sequence = str(fasta[0].seq).upper()
    genbank_sequence = str(genbank[0].seq).upper()
    if len(fasta_sequence) != expected_length or len(genbank_sequence) != expected_length:
        errors.append(f"parsed export length was {len(fasta_sequence)}/{len(genbank_sequence)}, expected {expected_length}")
    if fasta_sequence != genbank_sequence:
        errors.append("FASTA and GenBank parsed sequences differed")
    if str(genbank[0].annotations.get("topology", "")).lower() != "circular":
        errors.append("GenBank topology was not circular")
    return errors


def _open_saved_design(page: Page) -> None:
    page.get_by_role("button", name=OPEN_SAVED_DESIGN, exact=True).first.click(timeout=10_000)


def _enter_blank_design(page: Page) -> None:
    page.get_by_role("button", name="新建空白单基因项目", exact=True).click(timeout=10_000)
    page.get_by_role("heading", name="设计工作区", exact=True).wait_for(timeout=20_000)


def _generate_to_results(page: Page) -> None:
    cassette_button = page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE, exact=True)
    expect(cassette_button).to_be_enabled(timeout=20_000)
    cassette_button.click(timeout=10_000)
    page.get_by_text("表达盒记录已生成。", exact=True).wait_for(timeout=45_000)
    complete_button = page.get_by_role("button", name=GENERATE_COMPLETE_VECTOR, exact=True)
    expect(complete_button).to_be_enabled(timeout=20_000)
    complete_button.click(timeout=10_000)
    page.get_by_role("heading", name="结果与导出", exact=True).wait_for(timeout=45_000)


def _fixture_cds_sequence() -> str:
    lines = (REPO_ROOT / "examples" / "plant_single_gene_mvp" / "r229_cds.fasta").read_text(encoding="utf-8").splitlines()
    return "".join(line.strip() for line in lines if not line.startswith(">"))


def _run_valid_path(
    browser: Browser,
    *,
    name: str,
    cds_source: str,
    cds_text: str,
    expected_cds_length: int,
    work_root: Path,
) -> dict[str, Any]:
    path_dir = work_root / name
    path_dir.mkdir(parents=True, exist_ok=True)
    persistence_dir = path_dir / "saved_designs"
    first_log = path_dir / "before_restart.log"
    second_log = path_dir / "after_restart.log"
    browser_errors: list[str] = []
    errors: list[str] = []
    first_process: subprocess.Popen[str] | None = None
    second_process: subprocess.Popen[str] | None = None
    first_page: Page | None = None
    second_page: Page | None = None
    before_fasta: Path | None = None
    before_genbank: Path | None = None
    after_fasta: Path | None = None
    after_genbank: Path | None = None
    expected_plasmid_length = 640 + expected_cds_length + 210 + 4200
    try:
        first_process, first_url = _start_server(first_log, persistence_dir)
        first_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_errors(first_page, browser_errors)
        first_page.goto(first_url, wait_until="domcontentloaded", timeout=45_000)
        _enter_blank_design(first_page)
        _select_radio(first_page, "启动子输入方式", "使用示例")
        _select_radio(first_page, "终止子输入方式", "使用示例")
        _select_radio(first_page, "载体骨架输入方式", "使用示例骨架")
        if cds_source == "paste":
            first_page.get_by_role("textbox", name=PASTE_CDS).fill(cds_text)
        else:
            _select_radio(first_page, "CDS 输入方式", "上传 FASTA")
            first_page.locator('input[type="file"]').set_input_files(
                {"name": "user_cds.fasta", "mimeType": "text/plain", "buffer": cds_text.encode("utf-8")}
            )
        first_page.wait_for_timeout(750)
        _generate_to_results(first_page)
        first_page.get_by_text(re.compile(fr"{expected_plasmid_length} bp")).first.wait_for(timeout=45_000)
        first_page.get_by_role("button", name=SAVE_CURRENT_DESIGN).click(timeout=10_000)
        first_page.get_by_text(re.compile(r"项目已保存：")).wait_for(timeout=20_000)
        before_fasta, before_genbank = _download_pair(first_page, path_dir, "before_restart")
        errors.extend(_assert_downloads(before_fasta, before_genbank, expected_plasmid_length))
        first_page.close()
        first_page = None
        stop_server(first_process)
        first_process = None

        second_process, second_url = _start_server(second_log, persistence_dir)
        second_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_errors(second_page, browser_errors)
        second_page.goto(second_url, wait_until="domcontentloaded", timeout=45_000)
        _open_saved_design(second_page)
        second_page.get_by_text(re.compile(r"已打开项目：")).wait_for(timeout=20_000)
        second_page.get_by_text(re.compile(fr"{expected_plasmid_length} bp")).first.wait_for(timeout=20_000)
        expected_source_name = "pasted-cds" if cds_source == "paste" else "user_cds.fasta"
        second_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        if expected_source_name not in second_page.locator("body").inner_text():
            errors.append(f"reopened page did not show saved CDS source name: {expected_source_name}")
        second_page.get_by_role("button", name="查看结果", exact=True).click(timeout=10_000)
        after_fasta, after_genbank = _download_pair(second_page, path_dir, "after_restart")
        errors.extend(_assert_downloads(after_fasta, after_genbank, expected_plasmid_length))
        if before_fasta.read_bytes() != after_fasta.read_bytes():
            errors.append("FASTA bytes differed before and after restart")
        if before_genbank.read_bytes() != after_genbank.read_bytes():
            errors.append("GenBank bytes differed before and after restart")
    except Exception as exc:
        errors.append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        for page in (first_page, second_page):
            if page is not None:
                page.close()
        for process in (first_process, second_process):
            if process is not None:
                stop_server(process)

    server_exceptions = sum(
        len(SERVER_EXCEPTION_PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))
        for path in (first_log, second_log)
        if path.exists()
    )
    if server_exceptions:
        errors.append(f"server exception marker count: {server_exceptions}")
    if browser_errors:
        errors.extend(browser_errors)
    return {
        "path": name,
        "expected_cds_length": expected_cds_length,
        "plasmid_length": expected_plasmid_length,
        "fasta_sha256": _sha256_bytes(after_fasta) if after_fasta else None,
        "genbank_sha256": _sha256_bytes(after_genbank) if after_genbank else None,
        "browser_error_count": len(browser_errors),
        "server_exception_count": server_exceptions,
        "errors": errors,
        "passed": not errors,
    }


def _run_invalid_path(browser: Browser, work_root: Path) -> dict[str, Any]:
    path_dir = work_root / "invalid_cds"
    path_dir.mkdir(parents=True, exist_ok=True)
    log_path = path_dir / "server.log"
    process: subprocess.Popen[str] | None = None
    page: Page | None = None
    browser_errors: list[str] = []
    errors: list[str] = []
    try:
        process, local_url = _start_server(log_path, path_dir / "saved_designs")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_errors(page, browser_errors)
        page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
        _enter_blank_design(page)
        invalid_input = page.get_by_role("textbox", name=PASTE_CDS)
        invalid_input.fill("ATGBCTAA")
        invalid_input.press("Tab")
        page.wait_for_timeout(1_000)
        initial_body = page.locator("body").inner_text()
        initial_value = invalid_input.input_value()
        if INVALID_DNA_MESSAGE not in initial_body:
            errors.append(f"invalid CDS did not show the Chinese invalid-DNA message; text area value={initial_value!r}")
        if not page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE).is_disabled():
            errors.append("invalid CDS did not disable expression-cassette generation")
        page.locator('input[type="file"]').set_input_files(
            {"name": "other.fasta", "mimeType": "text/plain", "buffer": b">other\nATGGCTTAA\n"}
        )
        page.wait_for_timeout(1_000)
        if invalid_input.input_value() != "ATGBCTAA":
            errors.append("unrelated upload changed the explicitly selected pasted CDS input")
    except Exception as exc:
        errors.append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        if page is not None:
            page.close()
        if process is not None:
            stop_server(process)
    server_exceptions = (
        len(SERVER_EXCEPTION_PATTERN.findall(log_path.read_text(encoding="utf-8", errors="replace"))) if log_path.exists() else 0
    )
    if server_exceptions:
        errors.append(f"server exception marker count: {server_exceptions}")
    if browser_errors:
        errors.extend(browser_errors)
    return {
        "path": "invalid_cds",
        "browser_error_count": len(browser_errors),
        "server_exception_count": server_exceptions,
        "errors": errors,
        "passed": not errors,
    }


def _custom_backbone_text() -> str:
    record = SeqRecord(Seq("ACGT" * 300), id="mvp5_user_backbone", name="mvp5_user_backbone")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"
    record.features = [
        SeqFeature(
            FeatureLocation(800, 850),
            type="misc_feature",
            qualifiers={"label": ["mvp5_user_feature"]},
        )
    ]
    handle = StringIO()
    SeqIO.write(record, handle, "genbank")
    return handle.getvalue()


def _select_radio(page: Page, group_name: str, option_name: str) -> None:
    page.get_by_role("radiogroup", name=group_name).get_by_text(
        option_name, exact=True
    ).click(timeout=10_000)


def _set_coordinate(page: Page, label: str, value: int) -> None:
    field = page.get_by_label(label)
    if not field.is_visible():
        expander = page.locator('[data-testid="stExpander"]').filter(has_text="高级设置").first
        expander.locator("summary").click(timeout=10_000)
        field.wait_for(state="visible", timeout=10_000)
    field.fill(str(value), timeout=10_000)
    field.press("Tab")
    page.wait_for_timeout(1_000)


def _parse_pair(fasta_path: Path, genbank_path: Path) -> tuple[str, Any]:
    fasta_record = next(SeqIO.parse(StringIO(fasta_path.read_text(encoding="utf-8")), "fasta"))
    genbank_record = next(SeqIO.parse(StringIO(genbank_path.read_text(encoding="utf-8")), "genbank"))
    fasta_sequence = str(fasta_record.seq).upper()
    genbank_sequence = str(genbank_record.seq).upper()
    if fasta_sequence != genbank_sequence:
        raise AssertionError("FASTA and GenBank parsed sequences differed")
    return fasta_sequence, genbank_record


def _run_formal_path(
    browser: Browser,
    *,
    name: str,
    promoter: str,
    cds: str,
    terminator: str,
    backbone_text: str,
    use_all_examples: bool,
    use_example_backbone: bool,
    start_coordinate: int,
    end_coordinate: int,
    expected_file_hashes: tuple[str, str] | None,
    work_root: Path,
) -> dict[str, Any]:
    path_dir = work_root / name
    path_dir.mkdir(parents=True, exist_ok=True)
    persistence_dir = path_dir / "saved_designs"
    first_log = path_dir / "before_restart.log"
    second_log = path_dir / "after_restart.log"
    browser_errors: list[str] = []
    errors: list[str] = []
    first_process: subprocess.Popen[str] | None = None
    second_process: subprocess.Popen[str] | None = None
    first_page: Page | None = None
    second_page: Page | None = None
    before_fasta: Path | None = None
    before_genbank: Path | None = None
    after_fasta: Path | None = None
    after_genbank: Path | None = None
    expected_cassette = promoter + cds + terminator
    backbone_record = next(SeqIO.parse(StringIO(backbone_text), "genbank"))
    backbone_sequence = str(backbone_record.seq).upper()
    expected_sequence = (
        backbone_sequence[:start_coordinate]
        + expected_cassette
        + backbone_sequence[start_coordinate:]
    )
    backbone_upload_path = path_dir / "mvp5_user_backbone.gbk"
    if not use_example_backbone:
        backbone_upload_path.write_text(backbone_text, encoding="utf-8")
    try:
        first_process, first_url = _start_server(first_log, persistence_dir)
        first_page = browser.new_page(viewport={"width": 1440, "height": 1100})
        _attach_errors(first_page, browser_errors)
        first_page.goto(first_url, wait_until="domcontentloaded", timeout=45_000)
        if use_all_examples:
            first_page.get_by_role("button", name="加载示例项目", exact=True).click(timeout=10_000)
            first_page.get_by_text(re.compile(r"长度：640 bp")).wait_for(timeout=20_000)
        else:
            _enter_blank_design(first_page)
            first_page.get_by_label("粘贴启动子 DNA/FASTA").fill(promoter)
            first_page.get_by_label(PASTE_CDS).fill(cds)
            first_page.get_by_label("粘贴终止子 DNA/FASTA").fill(terminator)
            if use_example_backbone:
                _select_radio(first_page, "载体骨架输入方式", "使用示例骨架")
            _set_coordinate(first_page, "起始坐标（1-based）", start_coordinate)
            _set_coordinate(first_page, "结束坐标（1-based）", end_coordinate)
            if not use_example_backbone:
                first_page.get_by_text(re.compile(fr"长度：{len(promoter)} bp")).wait_for(timeout=20_000)
                first_page.get_by_text(re.compile(fr"长度：{len(cds)} bp")).wait_for(timeout=20_000)
                first_page.get_by_text(re.compile(fr"长度：{len(terminator)} bp")).wait_for(timeout=20_000)
                first_page.locator('input[type="file"]').set_input_files(
                    str(backbone_upload_path)
                )
                first_page.get_by_text(
                    re.compile(fr"长度：{len(backbone_sequence)} bp")
                ).wait_for(timeout=20_000)
            first_page.wait_for_timeout(1_500)
        cassette_button = first_page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE)
        if cassette_button.is_disabled():
            errors.append("cassette generation remained disabled after valid inputs: " + first_page.locator("body").inner_text())
            raise RuntimeError("cassette generation remained disabled after valid inputs")
        _generate_to_results(first_page)
        first_page.get_by_text(re.compile(fr"{len(expected_cassette)} bp")).first.wait_for(timeout=45_000)
        first_page.get_by_text(re.compile(fr"{len(expected_sequence)} bp")).first.wait_for(timeout=45_000)
        first_page.get_by_role("button", name=SAVE_CURRENT_DESIGN).click(timeout=10_000)
        first_page.get_by_text(re.compile(r"项目已保存：")).wait_for(timeout=20_000)
        before_fasta, before_genbank = _download_pair(first_page, path_dir, "before_restart")
        parsed_before, genbank_before = _parse_pair(before_fasta, before_genbank)
        if parsed_before != expected_sequence:
            errors.append("generated complete plasmid sequence differed from the expected insertion")
        if name == "path_c_user_genbank":
            labels = [str((feature.qualifiers or {}).get("label", [""])[0]) for feature in genbank_before.features]
            if "mvp5_user_feature" not in labels:
                errors.append("user backbone feature was not preserved in exported GenBank")
        first_page.close()
        first_page = None
        stop_server(first_process)
        first_process = None

        second_process, second_url = _start_server(second_log, persistence_dir)
        second_page = browser.new_page(viewport={"width": 1440, "height": 1100})
        _attach_errors(second_page, browser_errors)
        second_page.goto(second_url, wait_until="domcontentloaded", timeout=45_000)
        _open_saved_design(second_page)
        second_page.get_by_text(re.compile(r"已打开项目：")).wait_for(timeout=20_000)
        after_fasta, after_genbank = _download_pair(second_page, path_dir, "after_restart")
        if before_fasta.read_bytes() != after_fasta.read_bytes():
            errors.append("FASTA bytes differed before and after restart")
        if before_genbank.read_bytes() != after_genbank.read_bytes():
            errors.append("GenBank bytes differed before and after restart")
        parsed_after, _ = _parse_pair(after_fasta, after_genbank)
        if parsed_after != expected_sequence:
            errors.append("reopened complete plasmid sequence differed from the expected insertion")
        if expected_file_hashes and (
            _sha256_bytes(after_fasta),
            _sha256_bytes(after_genbank),
        ) != expected_file_hashes:
            errors.append("stable example export hashes changed")
    except Exception as exc:
        errors.append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        for page in (first_page, second_page):
            if page is not None:
                page.close()
        for process in (first_process, second_process):
            if process is not None:
                stop_server(process)
    server_exceptions = sum(
        len(SERVER_EXCEPTION_PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))
        for path in (first_log, second_log)
        if path.exists()
    )
    if browser_errors:
        errors.extend(browser_errors)
    if server_exceptions:
        errors.append(f"server exception marker count: {server_exceptions}")
    parsed_hash = hashlib.sha256(expected_sequence.encode("ascii")).hexdigest()
    return {
        "path": name,
        "cassette_length": len(expected_cassette),
        "plasmid_length": len(expected_sequence),
        "fasta_sha256": _sha256_bytes(after_fasta) if after_fasta else None,
        "genbank_sha256": _sha256_bytes(after_genbank) if after_genbank else None,
        "parsed_sequence_sha256": parsed_hash,
        "browser_error_count": len(browser_errors),
        "server_exception_count": server_exceptions,
        "errors": errors,
        "passed": not errors,
    }


def _run_mvp5_error_paths(browser: Browser, work_root: Path) -> dict[str, Any]:
    path_dir = work_root / "error_paths"
    path_dir.mkdir(parents=True, exist_ok=True)
    log_path = path_dir / "server.log"
    browser_errors: list[str] = []
    errors: list[str] = []
    process: subprocess.Popen[str] | None = None
    page: Page | None = None
    try:
        process, local_url = _start_server(log_path, path_dir / "saved_designs")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        _attach_errors(page, browser_errors)
        page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
        _enter_blank_design(page)
        if not page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE).is_disabled():
            errors.append("blank project did not disable cassette generation")
        if not page.get_by_role("button", name=GENERATE_COMPLETE_VECTOR).is_disabled():
            errors.append("blank project did not disable complete-plasmid generation")

        promoter_field = page.get_by_label("粘贴启动子 DNA/FASTA")
        promoter_field.fill("ATGX")
        promoter_field.press("Tab")
        page.wait_for_timeout(500)
        cds_field = page.get_by_label(PASTE_CDS)
        cds_field.fill("ATGTAATAA")
        cds_field.press("Tab")
        page.wait_for_timeout(500)
        terminator_field = page.get_by_label("粘贴终止子 DNA/FASTA")
        terminator_field.fill("TTTX")
        terminator_field.press("Tab")
        page.wait_for_timeout(1_500)
        updated_body = page.locator("body").inner_text()
        for expected in ("启动子：DNA 包含非法字符", "内部同框终止密码子", "终止子：DNA 包含非法字符"):
            if expected not in updated_body:
                errors.append(f"invalid sequence path did not show: {expected}")
        promoter_field = page.get_by_label("粘贴启动子 DNA/FASTA")
        promoter_field.fill(">one\nAAAA\n>two\nTTTT\n")
        promoter_field.press("Tab")
        page.wait_for_timeout(1_000)
        page.locator('[data-testid="stFileUploader"] input[type="file"]').set_input_files(
            {"name": "broken.gb", "mimeType": "text/plain", "buffer": b"not genbank"}
        )
        page.wait_for_timeout(1_500)
        updated_body = page.locator("body").inner_text()
        if "多条记录" not in updated_body:
            errors.append("multiple FASTA path was not blocked")
        if "GenBank 文件无法解析" not in updated_body:
            errors.append("broken or disguised GenBank path was not blocked")

        page.get_by_role("button", name="返回项目首页", exact=True).click(timeout=10_000)
        page.get_by_role("button", name="加载示例项目", exact=True).click(timeout=10_000)
        _generate_to_results(page)
        page.get_by_text(re.compile(r"5950 bp")).first.wait_for(timeout=45_000)
        page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _select_radio(page, "启动子输入方式", "粘贴 DNA/FASTA")
        page.get_by_label("粘贴启动子 DNA/FASTA").fill("AAAA")
        page.get_by_text(re.compile(r"旧结果已失效")).wait_for(timeout=20_000)
        page.get_by_role("button", name="查看结果", exact=True).click(timeout=10_000)
        if not all(
            page.get_by_role("button", name=label, exact=True).is_disabled()
            for label in ("下载表达盒 FASTA", DOWNLOAD_FASTA, DOWNLOAD_GENBANK)
        ):
            errors.append("stale result left an old download enabled")

        page.get_by_role("button", name="返回项目首页", exact=True).click(timeout=10_000)
        page.get_by_role("button", name="加载示例项目", exact=True).click(timeout=10_000)
        _set_coordinate(page, "起始坐标（1-based）", 99999)
        _set_coordinate(page, "结束坐标（1-based）", 100000)
        page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE, exact=True).click(timeout=10_000)
        page.get_by_text("表达盒记录已生成。", exact=True).wait_for(timeout=45_000)
        page.get_by_role("button", name=GENERATE_COMPLETE_VECTOR).click(timeout=10_000)
        page.get_by_text(re.compile(r"坐标无效")).wait_for(timeout=20_000)
    except Exception as exc:
        errors.append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        if page is not None:
            page.close()
        if process is not None:
            stop_server(process)
    server_exceptions = (
        len(SERVER_EXCEPTION_PATTERN.findall(log_path.read_text(encoding="utf-8", errors="replace")))
        if log_path.exists()
        else 0
    )
    if browser_errors:
        errors.extend(browser_errors)
    if server_exceptions:
        errors.append(f"server exception marker count: {server_exceptions}")
    return {
        "path": "error_paths",
        "browser_error_count": len(browser_errors),
        "server_exception_count": server_exceptions,
        "errors": errors,
        "passed": not errors,
    }


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    fixture = {
        role: (REPO_ROOT / "examples" / "plant_single_gene_mvp" / filename).read_text(encoding="utf-8")
        for role, filename in {
            "promoter": "r229_promoter.fasta",
            "cds": "r229_cds.fasta",
            "terminator": "r229_terminator.fasta",
            "backbone": "r229_backbone.gb",
        }.items()
    }
    example_sequences = {
        role: "".join(line.strip() for line in fixture[role].splitlines() if not line.startswith(">"))
        for role in ("promoter", "cds", "terminator")
    }
    user_promoter = "AACCGGTTAACC"
    user_cds = "ATG" + ("GCT" * 24) + "TAA"
    user_terminator = "TTGGAATTCC"
    custom_backbone = _custom_backbone_text()
    with tempfile.TemporaryDirectory(prefix="mvp5_full_input_acceptance_") as temporary_directory:
        work_root = Path(temporary_directory)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                results = [
                    _run_formal_path(
                        browser,
                        name="path_a_all_examples",
                        promoter=example_sequences["promoter"],
                        cds=example_sequences["cds"],
                        terminator=example_sequences["terminator"],
                        backbone_text=fixture["backbone"],
                        use_all_examples=True,
                        use_example_backbone=True,
                        start_coordinate=2100,
                        end_coordinate=2101,
                        expected_file_hashes=(
                            "bff837583dad749f5b7e84c40750e3d479770ac534bcf4e9a1b0d2149b1577a3",
                            "718a9dc01e371d6ee8e92b6f26d3f046d2de67749967a3ed458926014f23723b",
                        ),
                        work_root=work_root,
                    ),
                    _run_formal_path(
                        browser,
                        name="path_b_user_sequences_example_backbone",
                        promoter=user_promoter,
                        cds=user_cds,
                        terminator=user_terminator,
                        backbone_text=fixture["backbone"],
                        use_all_examples=False,
                        use_example_backbone=True,
                        start_coordinate=2100,
                        end_coordinate=2101,
                        expected_file_hashes=None,
                        work_root=work_root,
                    ),
                    _run_formal_path(
                        browser,
                        name="path_c_user_genbank",
                        promoter=user_promoter,
                        cds=user_cds,
                        terminator=user_terminator,
                        backbone_text=custom_backbone,
                        use_all_examples=False,
                        use_example_backbone=False,
                        start_coordinate=600,
                        end_coordinate=601,
                        expected_file_hashes=None,
                        work_root=work_root,
                    ),
                    _run_mvp5_error_paths(browser, work_root),
                ]
            finally:
                browser.close()
    report = {
        "playwright": "successfully executed",
        "passed": all(item["passed"] for item in results),
        "paths": results,
        "browser_error_count": sum(item["browser_error_count"] for item in results),
        "server_exception_count": sum(item["server_exception_count"] for item in results),
    }
    (ARTIFACT_ROOT / "mvp5_full_user_input_acceptance_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
