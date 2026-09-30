"""Exercise the MVP8 three-page package/save/restart/stale/delete flow three times."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from Bio import SeqIO
from playwright.sync_api import Browser, Page, expect, sync_playwright

from run_mvp_three_round_acceptance import (
    ARTIFACT_ROOT,
    DOWNLOAD_FASTA,
    DOWNLOAD_GENBANK,
    EXPECTED_FASTA_SHA256,
    EXPECTED_GENBANK_SHA256,
    EXPECTED_SEQUENCE_SHA256,
    GENERATE_EXPRESSION_CASSETTE,
    GENERATE_COMPLETE_VECTOR,
    SERVER_EXCEPTION_PATTERN,
    parse_downloads,
    reserve_local_url,
    sha256_bytes,
    stop_server,
    wait_for_server,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SAVE_CURRENT_DESIGN = "保存项目"
OPEN_SAVED_DESIGN = "打开"
DOWNLOAD_CASSETTE_FASTA = "下载表达盒 FASTA"
DOWNLOAD_COMPANY_REVIEW_PACKAGE = "导出公司审查包 ZIP"
FORBIDDEN_PAGE_TEXT = ("Traceback", "StreamlitAPIException", "NotFoundError", "DuplicateElementKey")
PACKAGE_FILE_ORDER = (
    "complete_plasmid.gb",
    "complete_plasmid.fasta",
    "expression_cassette.fasta",
    "component_coordinates.csv",
    "validation_summary.json",
    "construct_manifest.json",
    "construct_summary.txt",
    "checksums.sha256",
)
CHECKSUM_FILE_ORDER = PACKAGE_FILE_ORDER[:-1]
PACKAGE_BOUNDARY_TEXT = "本交付包用于序列审查、报价和构建可行性评估"


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


def _attach_browser_error_collection(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)


def _page_errors(page: Page, browser_errors: list[str]) -> list[str]:
    errors = list(browser_errors)
    body_text = page.locator("body").inner_text()
    for forbidden in FORBIDDEN_PAGE_TEXT:
        if forbidden.lower() in body_text.lower():
            errors.append(f"visible forbidden page text: {forbidden}")
    exception_count = page.locator('[data-testid="stException"]').count()
    if exception_count:
        errors.append(f"Streamlit exception widget count: {exception_count}")
    return errors


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


def _download_cassette(page: Page, directory: Path, prefix: str) -> Path:
    path = directory / f"{prefix}.fasta"
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role("button", name=DOWNLOAD_CASSETTE_FASTA, exact=True).click(timeout=10_000)
    download_info.value.save_as(path)
    return path


def _download_company_review_package(page: Page, directory: Path, prefix: str) -> Path:
    path = directory / f"{prefix}.zip"
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role(
            "button", name=DOWNLOAD_COMPANY_REVIEW_PACKAGE, exact=True
        ).click(timeout=10_000)
    download_info.value.save_as(path)
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _genbank_feature_tuple(feature) -> tuple[str, str, int, int, int, int]:
    label = str(((feature.qualifiers or {}).get("label") or [""])[0])
    parts = list(getattr(feature.location, "parts", None) or [feature.location])
    return (
        label,
        str(feature.type),
        int(feature.location.strand or 1),
        min(int(part.start) + 1 for part in parts),
        max(int(part.end) for part in parts),
        sum(int(part.end) - int(part.start) for part in parts),
    )


def _csv_feature_tuple(row: dict[str, str]) -> tuple[str, str, int, int, int, int]:
    return (
        row["component_name"],
        row["component_type"],
        int(row["strand"]),
        int(row["start_1_based"]),
        int(row["end_1_based"]),
        int(row["length_bp"]),
    )


def _validate_company_review_package(package_path: Path, unpack_root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    evidence: dict[str, Any] = {
        "zip_sha256": _sha256_file(package_path),
        "file_count": 0,
        "parsed_sequence_sha256": None,
        "checksums_valid": False,
        "coordinates_valid": False,
        "json_valid": False,
        "boundary_copy_present": False,
    }
    unpack_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            names = archive.namelist()
            evidence["file_count"] = len(names)
            roots: set[str] = set()
            for name in names:
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
                    errors.append(f"unsafe ZIP path: {name}")
                    continue
                roots.add(relative.parts[0])
                target = (unpack_root / Path(*relative.parts)).resolve()
                if not target.is_relative_to(unpack_root.resolve()):
                    errors.append(f"ZIP path escaped unpack root: {name}")
            if len(roots) != 1:
                errors.append(f"ZIP root directory count was {len(roots)}, expected 1")
                return evidence, errors
            root_name = next(iter(roots))
            expected_names = [f"{root_name}/{name}" for name in PACKAGE_FILE_ORDER]
            if names != expected_names:
                errors.append("ZIP file list or order did not match the fixed eight-file contract")
            archive.extractall(unpack_root)

        project_root = unpack_root / root_name
        actual_files = sorted(
            path.relative_to(project_root).as_posix()
            for path in project_root.rglob("*")
            if path.is_file()
        )
        if actual_files != sorted(PACKAGE_FILE_ORDER):
            errors.append("extracted package contained missing or unknown files")

        checksum_lines = (project_root / "checksums.sha256").read_text(
            encoding="utf-8"
        ).splitlines()
        expected_checksum_lines = [
            f"{_sha256_file(project_root / name)}  {name}"
            for name in CHECKSUM_FILE_ORDER
        ]
        evidence["checksums_valid"] = checksum_lines == expected_checksum_lines
        if not evidence["checksums_valid"]:
            errors.append("checksums.sha256 did not match independently calculated hashes")

        with (project_root / "complete_plasmid.fasta").open("r", encoding="utf-8") as handle:
            fasta_records = list(SeqIO.parse(handle, "fasta"))
        with (project_root / "expression_cassette.fasta").open("r", encoding="utf-8") as handle:
            cassette_records = list(SeqIO.parse(handle, "fasta"))
        with (project_root / "complete_plasmid.gb").open("r", encoding="utf-8") as handle:
            genbank_records = list(SeqIO.parse(handle, "genbank"))
        if len(fasta_records) != 1 or len(cassette_records) != 1 or len(genbank_records) != 1:
            errors.append("package FASTA/GenBank record counts were not exactly one")
            return evidence, errors
        fasta_sequence = str(fasta_records[0].seq).upper()
        genbank_sequence = str(genbank_records[0].seq).upper()
        if fasta_sequence != genbank_sequence:
            errors.append("package complete FASTA and GenBank sequences differed")
        evidence["parsed_sequence_sha256"] = hashlib.sha256(
            fasta_sequence.encode("ascii")
        ).hexdigest()

        with (project_root / "component_coordinates.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            coordinate_rows = list(csv.DictReader(handle))
        evidence["coordinates_valid"] = Counter(
            _csv_feature_tuple(row) for row in coordinate_rows
        ) == Counter(_genbank_feature_tuple(feature) for feature in genbank_records[0].features)
        if not evidence["coordinates_valid"]:
            errors.append("CSV coordinates differed from independently parsed GenBank features")

        validation = json.loads(
            (project_root / "validation_summary.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (project_root / "construct_manifest.json").read_text(encoding="utf-8")
        )
        evidence["json_valid"] = bool(
            validation.get("validation_scope")
            == "software_sequence_and_structure_validation"
            and validation.get("wet_lab_validated") is False
            and validation.get("experimental_success_guaranteed") is False
            and manifest.get("package_schema_version") == "1.0.0"
            and manifest.get("project_schema_version") == "1.0.0"
            and manifest.get("project_type") == "single_gene"
            and isinstance(manifest.get("components"), list)
            and isinstance(manifest.get("files"), list)
        )
        if not evidence["json_valid"]:
            errors.append("package JSON required fields or types were invalid")
        summary = (project_root / "construct_summary.txt").read_text(encoding="utf-8")
        evidence["boundary_copy_present"] = PACKAGE_BOUNDARY_TEXT in summary
        if not evidence["boundary_copy_present"]:
            errors.append("construct summary boundary copy was missing")
    except Exception as exc:
        errors.append(f"independent package validation error: {type(exc).__name__}: {exc}")
    return evidence, errors


def _select_radio(page: Page, group_name: str, option_name: str) -> None:
    page.get_by_role("radiogroup", name=group_name).get_by_text(
        option_name, exact=True
    ).click(timeout=10_000)


def _set_coordinate(page: Page, label: str, value: int) -> None:
    last_error: Exception | None = None
    for _attempt in range(4):
        try:
            field = page.get_by_label(label)
            if not field.is_visible(timeout=2_000):
                expander = page.locator('[data-testid="stExpander"]').filter(
                    has_text="高级设置"
                ).first
                summary = expander.locator("summary")
                if summary.get_attribute("aria-expanded") != "true":
                    summary.click(timeout=10_000)
                field = page.get_by_label(label)
                field.wait_for(state="visible", timeout=10_000)
            field.fill(str(value), timeout=10_000)
            field.press("Tab", timeout=10_000)
            page.wait_for_timeout(1_000)
            current = page.get_by_label(label)
            if current.is_visible(timeout=2_000) and current.input_value() == str(value):
                return
        except Exception as exc:
            last_error = exc
        page.wait_for_timeout(500)
    raise RuntimeError(f"could not set coordinate {label}={value}: {last_error}")


def _select_all_examples(page: Page) -> None:
    for group in ("启动子输入方式", "CDS 输入方式", "终止子输入方式"):
        _select_radio(page, group, "使用示例")
    _select_radio(page, "载体骨架输入方式", "使用示例骨架")
    _set_coordinate(page, "起始坐标（1-based）", 2100)
    _set_coordinate(page, "结束坐标（1-based）", 2101)


def _generate_to_results(page: Page) -> None:
    cassette_button = page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE, exact=True)
    try:
        expect(cassette_button).to_be_enabled(timeout=20_000)
    except AssertionError as exc:
        raise RuntimeError(
            "expression-cassette generation remained disabled:\n"
            + page.locator("body").inner_text()
        ) from exc
    cassette_button.click(timeout=10_000)
    page.get_by_text("表达盒记录已生成。", exact=True).wait_for(timeout=45_000)
    complete_button = page.get_by_role("button", name=GENERATE_COMPLETE_VECTOR, exact=True)
    expect(complete_button).to_be_enabled(timeout=20_000)
    complete_button.click(timeout=10_000)
    page.get_by_role("heading", name="结果与导出", exact=True).wait_for(timeout=45_000)


def _select_and_open_saved_design(page: Page, project_name: str) -> None:
    page.get_by_text(project_name, exact=True).wait_for(timeout=20_000)
    page.get_by_role("button", name=OPEN_SAVED_DESIGN, exact=True).first.click(timeout=10_000)


def _assert_visible_lengths(page: Page, errors: list[str]) -> None:
    for expected in (640, 900, 210, 4200):
        if expected == 4200:
            page.get_by_role("heading", name="载体骨架", exact=True).scroll_into_view_if_needed(
                timeout=10_000
            )
        locator = page.get_by_text(re.compile(fr"长度：\s*{expected}\s*bp")).first
        try:
            locator.scroll_into_view_if_needed(timeout=10_000)
            locator.wait_for(state="visible", timeout=10_000)
        except Exception:
            errors.append(f"missing visible expected length: {expected}")


def _server_exception_count(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return len(SERVER_EXCEPTION_PATTERN.findall(log_path.read_text(encoding="utf-8", errors="replace")))


def run_round(round_number: int, browser: Browser, work_root: Path, persistence_dir: Path) -> dict[str, Any]:
    round_dir = work_root / f"round-{round_number}"
    round_dir.mkdir(parents=True, exist_ok=True)
    first_log = round_dir / "streamlit-before-restart.log"
    second_log = round_dir / "streamlit-after-restart.log"
    result: dict[str, Any] = {
        "round": round_number,
        "fasta_before_sha256": None,
        "genbank_before_sha256": None,
        "fasta_after_sha256": None,
        "genbank_after_sha256": None,
        "parsed_sequence_sha256": None,
        "cassette_fasta_sha256": None,
        "initial_package_sha256": None,
        "package_before_restart_sha256": None,
        "package_after_restart_sha256": None,
        "changed_package_sha256": None,
        "package_bytes_persisted": False,
        "package_validation_passed": False,
        "stale_downloads_disabled": False,
        "post_restart_stale_downloads_disabled": False,
        "project_deleted": False,
        "browser_error_count": 0,
        "server_exception_count": 0,
        "passed": False,
        "errors": [],
    }
    browser_errors: list[str] = []
    first_process: subprocess.Popen[str] | None = None
    second_process: subprocess.Popen[str] | None = None
    first_page: Page | None = None
    second_page: Page | None = None
    project_name = f"MVP8 验收项目 {round_number}"
    try:
        first_process, first_url = _start_server(first_log, persistence_dir)
        first_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_browser_error_collection(first_page, browser_errors)
        first_page.goto(first_url, wait_until="domcontentloaded", timeout=45_000)
        first_page.get_by_role("heading", name="项目首页", exact=True).wait_for(timeout=20_000)
        first_page.get_by_role("button", name="新建空白单基因项目", exact=True).click(timeout=10_000)
        first_page.get_by_role("heading", name="设计工作区", exact=True).wait_for(timeout=20_000)
        first_page.get_by_role("textbox", name="项目名称", exact=True).fill(project_name)
        _select_all_examples(first_page)
        _generate_to_results(first_page)
        first_page.get_by_role("heading", name="软件校验结果", exact=True).wait_for(timeout=20_000)
        initial_package = _download_company_review_package(
            first_page, round_dir, "initial_company_review_package"
        )
        initial_evidence, initial_errors = _validate_company_review_package(
            initial_package, round_dir / "initial_package_unpacked"
        )
        result["initial_package_sha256"] = initial_evidence["zip_sha256"]
        result["errors"].extend(initial_errors)
        first_page.get_by_role("button", name=SAVE_CURRENT_DESIGN).click(timeout=10_000)
        first_page.get_by_text(f"项目已保存：{project_name}", exact=True).wait_for(timeout=20_000)
        cassette_path = _download_cassette(first_page, round_dir, "expression_cassette")
        result["cassette_fasta_sha256"] = sha256_bytes(cassette_path)
        cassette_records = list(SeqIO.parse(str(cassette_path), "fasta"))
        if len(cassette_records) != 1 or len(cassette_records[0].seq) != 1750:
            result["errors"].append("expression cassette FASTA did not parse as one 1750 bp record")
        before_fasta, before_genbank = _download_pair(first_page, round_dir, "before_restart")
        result["fasta_before_sha256"] = sha256_bytes(before_fasta)
        result["genbank_before_sha256"] = sha256_bytes(before_genbank)

        first_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _set_coordinate(first_page, "起始坐标（1-based）", 2101)
        first_page.get_by_text(re.compile(r"旧结果已失效")).wait_for(timeout=20_000)
        first_page.get_by_role("button", name="查看结果", exact=True).click(timeout=10_000)
        stale_disabled = all(
            first_page.get_by_role("button", name=label, exact=True).is_disabled()
            for label in (
                DOWNLOAD_CASSETTE_FASTA,
                DOWNLOAD_FASTA,
                DOWNLOAD_GENBANK,
                DOWNLOAD_COMPANY_REVIEW_PACKAGE,
            )
        )
        result["stale_downloads_disabled"] = stale_disabled
        if not stale_disabled:
            result["errors"].append("stale result left one or more old downloads enabled")
        first_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _set_coordinate(first_page, "起始坐标（1-based）", 2100)
        _generate_to_results(first_page)
        first_page.get_by_role("button", name=SAVE_CURRENT_DESIGN, exact=True).click(timeout=10_000)
        rebuilt_fasta, rebuilt_genbank = _download_pair(first_page, round_dir, "after_rebuild")
        if before_fasta.read_bytes() != rebuilt_fasta.read_bytes():
            result["errors"].append("FASTA bytes changed after stale/rebuild with restored inputs")
        if before_genbank.read_bytes() != rebuilt_genbank.read_bytes():
            result["errors"].append("GenBank bytes changed after stale/rebuild with restored inputs")
        package_before_restart = _download_company_review_package(
            first_page, round_dir, "company_review_package_before_restart"
        )
        before_package_evidence, before_package_errors = _validate_company_review_package(
            package_before_restart, round_dir / "package_before_restart_unpacked"
        )
        result["package_before_restart_sha256"] = before_package_evidence["zip_sha256"]
        result["errors"].extend(before_package_errors)
        first_page.close()
        first_page = None
        stop_server(first_process)
        first_process = None

        second_process, second_url = _start_server(second_log, persistence_dir)
        second_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_browser_error_collection(second_page, browser_errors)
        second_page.goto(second_url, wait_until="domcontentloaded", timeout=45_000)
        second_page.get_by_role("heading", name="项目首页", exact=True).wait_for(timeout=20_000)
        _select_and_open_saved_design(second_page, project_name)
        second_page.get_by_text(f"已打开项目：{project_name}", exact=True).wait_for(timeout=20_000)
        second_page.get_by_text(re.compile(r"5950 bp")).first.wait_for(timeout=20_000)
        second_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _assert_visible_lengths(second_page, result["errors"])
        second_page.get_by_role("button", name="查看结果", exact=True).click(timeout=10_000)
        second_page.get_by_role("heading", name="结果与导出", exact=True).wait_for(
            timeout=20_000
        )
        expect(
            second_page.get_by_role("button", name=DOWNLOAD_FASTA, exact=True)
        ).to_be_enabled(timeout=20_000)
        second_page.wait_for_timeout(1_000)
        after_fasta, after_genbank = _download_pair(second_page, round_dir, "after_restart")
        result["fasta_after_sha256"] = sha256_bytes(after_fasta)
        result["genbank_after_sha256"] = sha256_bytes(after_genbank)
        if before_fasta.read_bytes() != after_fasta.read_bytes():
            result["errors"].append("FASTA bytes differed before and after restart")
        if before_genbank.read_bytes() != after_genbank.read_bytes():
            result["errors"].append("GenBank bytes differed before and after restart")
        parsed_length, parsed_sha256, parse_errors = parse_downloads(after_fasta, after_genbank)
        result["parsed_sequence_sha256"] = parsed_sha256
        result["errors"].extend(parse_errors)
        if parsed_length != 5950:
            result["errors"].append(f"parsed plasmid length was {parsed_length}, expected 5950")
        if parsed_sha256 != EXPECTED_SEQUENCE_SHA256:
            result["errors"].append(f"parsed sequence SHA-256 was {parsed_sha256}, expected {EXPECTED_SEQUENCE_SHA256}")
        if result["fasta_after_sha256"] != EXPECTED_FASTA_SHA256:
            result["errors"].append(
                f"FASTA SHA-256 was {result['fasta_after_sha256']}, expected {EXPECTED_FASTA_SHA256}"
            )
        if result["genbank_after_sha256"] != EXPECTED_GENBANK_SHA256:
            result["errors"].append(
                f"GenBank SHA-256 was {result['genbank_after_sha256']}, expected {EXPECTED_GENBANK_SHA256}"
            )
        package_after_restart = _download_company_review_package(
            second_page, round_dir, "company_review_package_after_restart"
        )
        after_package_evidence, after_package_errors = _validate_company_review_package(
            package_after_restart, round_dir / "package_after_restart_unpacked"
        )
        result["package_after_restart_sha256"] = after_package_evidence["zip_sha256"]
        result["errors"].extend(after_package_errors)
        result["package_bytes_persisted"] = (
            package_before_restart.read_bytes() == package_after_restart.read_bytes()
        )
        if not result["package_bytes_persisted"]:
            result["errors"].append("company review ZIP bytes differed before and after restart")
        result["package_validation_passed"] = not (
            initial_errors or before_package_errors or after_package_errors
        )

        second_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _set_coordinate(second_page, "起始坐标（1-based）", 2101)
        _set_coordinate(second_page, "结束坐标（1-based）", 2102)
        second_page.get_by_text(re.compile(r"旧结果已失效")).wait_for(timeout=20_000)
        second_page.get_by_role("button", name="查看结果", exact=True).click(timeout=10_000)
        post_restart_stale_disabled = all(
            second_page.get_by_role("button", name=label, exact=True).is_disabled()
            for label in (
                DOWNLOAD_CASSETTE_FASTA,
                DOWNLOAD_FASTA,
                DOWNLOAD_GENBANK,
                DOWNLOAD_COMPANY_REVIEW_PACKAGE,
            )
        )
        result["post_restart_stale_downloads_disabled"] = post_restart_stale_disabled
        if not post_restart_stale_disabled:
            result["errors"].append("post-restart stale result left an old download enabled")
        second_page.get_by_role("button", name="返回修改设计", exact=True).click(timeout=10_000)
        _generate_to_results(second_page)
        changed_package = _download_company_review_package(
            second_page, round_dir, "company_review_package_after_changed_rebuild"
        )
        changed_evidence, changed_errors = _validate_company_review_package(
            changed_package, round_dir / "changed_package_unpacked"
        )
        result["changed_package_sha256"] = changed_evidence["zip_sha256"]
        result["errors"].extend(changed_errors)
        if changed_errors:
            result["package_validation_passed"] = False
        if changed_package.read_bytes() == package_after_restart.read_bytes():
            result["errors"].append("changed core input did not produce a new company review ZIP")
        second_page.get_by_role("button", name="返回项目首页", exact=True).click(timeout=10_000)
        second_page.get_by_role("button", name="删除", exact=True).first.click(timeout=10_000)
        second_page.get_by_role("button", name="确认删除项目", exact=True).click(timeout=10_000)
        second_page.get_by_text(f"已删除项目：{project_name}", exact=True).wait_for(timeout=20_000)
        second_page.reload(wait_until="domcontentloaded", timeout=45_000)
        second_page.get_by_role("heading", name="项目首页", exact=True).wait_for(timeout=20_000)
        result["project_deleted"] = second_page.get_by_text(project_name, exact=True).count() == 0
        if not result["project_deleted"]:
            result["errors"].append("deleted project remained visible on the project home page")
        result["errors"].extend(_page_errors(second_page, browser_errors))
    except Exception as exc:
        result["errors"].append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        for page in (first_page, second_page):
            if page is not None:
                page.close()
        for process in (first_process, second_process):
            if process is not None:
                stop_server(process)
        result["server_exception_count"] = _server_exception_count(first_log) + _server_exception_count(second_log)
        if result["server_exception_count"]:
            result["errors"].append(f"server exception marker count: {result['server_exception_count']}")
        result["browser_error_count"] = len(browser_errors)
        result["passed"] = not result["errors"]
    return result


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    round_count = int(os.environ.get("BIODESIGN_MVP_ACCEPTANCE_ROUNDS", "3"))
    with tempfile.TemporaryDirectory(prefix="mvp_persistence_acceptance_") as temporary_directory:
        work_root = Path(temporary_directory)
        persistence_dir = work_root / "shared_r224_drafts"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                rounds = [
                    run_round(round_number, browser, work_root, persistence_dir)
                    for round_number in range(1, round_count + 1)
                ]
            finally:
                browser.close()

    report = {
        "playwright": "successfully executed",
        "passed": all(item["passed"] for item in rounds),
        "rounds": rounds,
    }
    report_path = ARTIFACT_ROOT / "persistence_acceptance_result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
