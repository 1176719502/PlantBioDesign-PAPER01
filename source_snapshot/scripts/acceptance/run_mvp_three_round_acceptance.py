"""Run three isolated Playwright acceptance rounds for the MVP app."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from Bio import SeqIO
from playwright.sync_api import Browser, Page, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "mvp_acceptance"
REPRESENTATIVE_SCREENSHOTS = {
    "after_real_case": ARTIFACT_ROOT / "after_real_case.png",
    "after_complete_vector": ARTIFACT_ROOT / "after_complete_vector.png",
}
INPUT_LENGTHS = {
    "启动子": 640,
    "CDS": 900,
    "终止子": 210,
    "载体骨架": 4200,
}
FORBIDDEN_PAGE_TEXT = (
    "Traceback",
    "StreamlitAPIException",
    "NotFoundError",
    "DuplicateElementKey",
)
LOAD_REAL_CASE = "加载示例项目"
GENERATE_EXPRESSION_CASSETTE = "生成表达盒"
GENERATE_COMPLETE_VECTOR = "生成完整质粒"
DOWNLOAD_FASTA = "下载完整质粒 FASTA"
DOWNLOAD_GENBANK = "下载完整质粒 GenBank"
EXPECTED_FASTA_SHA256 = "bff837583dad749f5b7e84c40750e3d479770ac534bcf4e9a1b0d2149b1577a3"
EXPECTED_GENBANK_SHA256 = "718a9dc01e371d6ee8e92b6f26d3f046d2de67749967a3ed458926014f23723b"
EXPECTED_SEQUENCE_SHA256 = "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"
SERVER_EXCEPTION_PATTERN = re.compile(
    r"Traceback \(most recent call last\)|StreamlitAPIException|"
    r"NotFoundError|DuplicateElementKey",
    re.IGNORECASE,
)


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def sha256_sequence(sequence: str) -> str:
    return hashlib.sha256(sequence.upper().encode("ascii")).hexdigest()


def wait_for_server(process: subprocess.Popen[str], local_url: str) -> None:
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited before becoming ready (exit {process.returncode}).")
        try:
            with urllib.request.urlopen(local_url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return
        except Exception as error:
            last_error = error
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become ready at {local_url}: {last_error}")


def reserve_local_url() -> tuple[str, int]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    return f"http://127.0.0.1:{port}", port


def stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
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


def visible_input_lengths(page: Page) -> list[str]:
    missing: list[str] = []
    for name, length in INPUT_LENGTHS.items():
        if name == "载体骨架":
            page.get_by_role("heading", name="载体骨架", exact=True).scroll_into_view_if_needed(
                timeout=10_000
            )
        locator = page.get_by_text(re.compile(fr"长度：\s*{length}\s*bp")).first
        try:
            locator.scroll_into_view_if_needed(timeout=10_000)
            locator.wait_for(state="visible", timeout=10_000)
        except Exception:
            missing.append(f"{name} {length} bp")
    return missing


def page_error_messages(page: Page, browser_errors: list[str]) -> list[str]:
    messages = list(browser_errors)
    body_text = page.locator("body").inner_text()
    for forbidden in FORBIDDEN_PAGE_TEXT:
        if forbidden.lower() in body_text.lower():
            messages.append(f"visible forbidden page text: {forbidden}")
    exception_count = page.locator('[data-testid="stException"]').count()
    if exception_count:
        messages.append(f"Streamlit exception widget count: {exception_count}")
    alert_count = page.locator('[data-testid="stAlert"]').count()
    if alert_count:
        messages.append(f"Streamlit alert widget count: {alert_count}")
    return messages


def primary_button(
    page: Page, expected_name: str, fallback_index: int, result: dict[str, Any]
) -> Any:
    named_button = page.get_by_role("button", name=expected_name)
    if named_button.count() == 1:
        return named_button
    buttons = page.locator('[data-testid="stButton"] button')
    if buttons.count() != 2:
        raise RuntimeError(
            f"Expected exactly two primary buttons when {expected_name!r} was unavailable; "
            f"found {buttons.count()}: {buttons.all_inner_texts()[:12]!r}."
        )
    result["errors"].append(
        f"expected visible button label was unavailable: {expected_name}; "
        f"used primary button index {fallback_index} to continue evidence collection"
    )
    return buttons.nth(fallback_index)


def parse_downloads(fasta_path: Path, genbank_path: Path) -> tuple[int, str, list[str]]:
    errors: list[str] = []
    with fasta_path.open(encoding="utf-8") as fasta_handle:
        fasta_records = list(SeqIO.parse(fasta_handle, "fasta"))
    with genbank_path.open(encoding="utf-8") as genbank_handle:
        genbank_records = list(SeqIO.parse(genbank_handle, "genbank"))
    if len(fasta_records) != 1:
        errors.append(f"FASTA record count was {len(fasta_records)}, expected 1")
    if len(genbank_records) != 1:
        errors.append(f"GenBank record count was {len(genbank_records)}, expected 1")
    if errors:
        return 0, "", errors

    fasta_sequence = str(fasta_records[0].seq).upper()
    genbank_record = genbank_records[0]
    genbank_sequence = str(genbank_record.seq).upper()
    if len(fasta_sequence) != 5950:
        errors.append(f"FASTA sequence length was {len(fasta_sequence)}, expected 5950")
    if len(genbank_sequence) != 5950:
        errors.append(f"GenBank sequence length was {len(genbank_sequence)}, expected 5950")
    if fasta_sequence != genbank_sequence:
        errors.append("FASTA and GenBank parsed sequences differ")
    if str(genbank_record.annotations.get("topology", "")).lower() != "circular":
        errors.append("GenBank topology is not circular")
    if not genbank_record.features:
        errors.append("GenBank FEATURES did not parse into any features")
    return len(fasta_sequence), sha256_sequence(fasta_sequence), errors


def run_round(round_number: int, browser: Browser, work_root: Path) -> dict[str, Any]:
    round_dir = work_root / f"round-{round_number}"
    round_dir.mkdir(parents=True, exist_ok=True)
    log_path = round_dir / "streamlit.log"
    local_url, port = reserve_local_url()
    process: subprocess.Popen[str] | None = None
    result: dict[str, Any] = {
        "round": round_number,
        "local_url": local_url,
        "cassette_length": None,
        "plasmid_length": None,
        "fasta_path": None,
        "genbank_path": None,
        "fasta_file_sha256": None,
        "genbank_file_sha256": None,
        "parsed_sequence_sha256": None,
        "browser_error_count": 0,
        "server_exception_count": 0,
        "passed": False,
        "errors": [],
        "screenshots": {
            "after_real_case": str(round_dir / "after_real_case.png"),
            "after_complete_vector": str(round_dir / "after_complete_vector.png"),
        },
        "server_log": str(log_path),
    }
    browser_errors: list[str] = []
    try:
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
            )
            wait_for_server(process, local_url)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: browser_errors.append(f"pageerror: {error}"))
            page.on(
                "console",
                lambda message: browser_errors.append(f"console: {message.text}")
                if message.type == "error"
                else None,
            )
            page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
            page.locator('[data-testid="stButton"] button').first.wait_for(
                state="visible", timeout=20_000
            )
            page.get_by_role("button", name=LOAD_REAL_CASE, exact=True).click(timeout=10_000)
            page.get_by_role("heading", name="设计工作区", exact=True).wait_for(timeout=20_000)
            page.get_by_text(re.compile(r"长度：640 bp")).wait_for(timeout=20_000)
            missing_input_lengths = visible_input_lengths(page)
            if missing_input_lengths:
                result["errors"].append(
                    "missing visible input lengths after real-case load: "
                    + ", ".join(missing_input_lengths)
                )
            page.get_by_role("heading", name="设计工作区", exact=True).scroll_into_view_if_needed()
            page.screenshot(path=result["screenshots"]["after_real_case"], full_page=True)
            if round_number == 3:
                page.screenshot(
                    path=str(REPRESENTATIVE_SCREENSHOTS["after_real_case"]), full_page=True
                )

            page.get_by_role("button", name=GENERATE_EXPRESSION_CASSETTE, exact=True).click(
                timeout=10_000
            )
            page.get_by_text("表达盒记录已生成。", exact=True).wait_for(timeout=45_000)
            page.get_by_role("button", name=GENERATE_COMPLETE_VECTOR, exact=True).click(
                timeout=10_000
            )
            page.get_by_role("heading", name="结果与导出", exact=True).wait_for(timeout=45_000)
            page.get_by_text(re.compile(r"1750 bp")).first.wait_for(timeout=45_000)
            page.get_by_text(re.compile(r"5950 bp")).first.wait_for(timeout=45_000)
            page.get_by_role("heading", name="结果与导出", exact=True).scroll_into_view_if_needed()
            result["cassette_length"] = 1750
            result["plasmid_length"] = 5950
            page.screenshot(path=result["screenshots"]["after_complete_vector"], full_page=True)
            if round_number == 3:
                page.screenshot(
                    path=str(REPRESENTATIVE_SCREENSHOTS["after_complete_vector"]), full_page=True
                )

            fasta_path = round_dir / "complete_plasmid.fasta"
            genbank_path = round_dir / "complete_plasmid.gb"
            with page.expect_download(timeout=45_000) as download_info:
                page.get_by_role("button", name=DOWNLOAD_FASTA, exact=True).click(timeout=10_000)
            download_info.value.save_as(fasta_path)
            with page.expect_download(timeout=45_000) as download_info:
                page.get_by_role("button", name=DOWNLOAD_GENBANK, exact=True).click(timeout=10_000)
            download_info.value.save_as(genbank_path)
            result["fasta_path"] = str(fasta_path)
            result["genbank_path"] = str(genbank_path)
            result["fasta_file_sha256"] = sha256_bytes(fasta_path)
            result["genbank_file_sha256"] = sha256_bytes(genbank_path)
            parsed_length, parsed_sha256, parse_errors = parse_downloads(fasta_path, genbank_path)
            result["parsed_sequence_sha256"] = parsed_sha256
            result["errors"].extend(parse_errors)
            if result["fasta_file_sha256"] != EXPECTED_FASTA_SHA256:
                result["errors"].append(
                    f"FASTA byte SHA-256 was {result['fasta_file_sha256']}, expected {EXPECTED_FASTA_SHA256}"
                )
            if result["genbank_file_sha256"] != EXPECTED_GENBANK_SHA256:
                result["errors"].append(
                    f"GenBank byte SHA-256 was {result['genbank_file_sha256']}, expected {EXPECTED_GENBANK_SHA256}"
                )
            if parsed_sha256 != EXPECTED_SEQUENCE_SHA256:
                result["errors"].append(
                    f"parsed sequence SHA-256 was {parsed_sha256}, expected {EXPECTED_SEQUENCE_SHA256}"
                )
            if parsed_length != 5950:
                result["errors"].append(f"parsed plasmid length was {parsed_length}, expected 5950")
            result["errors"].extend(page_error_messages(page, browser_errors))
            page.close()
    except Exception as error:
        result["errors"].append(f"acceptance execution error: {type(error).__name__}: {error}")
    finally:
        if process is not None:
            stop_server(process)
        if log_path.exists():
            server_log = log_path.read_text(encoding="utf-8", errors="replace")
            result["server_exception_count"] = len(SERVER_EXCEPTION_PATTERN.findall(server_log))
            if result["server_exception_count"]:
                result["errors"].append(
                    f"server exception marker count: {result['server_exception_count']}"
                )
        result["browser_error_count"] = len(browser_errors)
        result["passed"] = not result["errors"]
    return result


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mvp_acceptance_") as temporary_directory:
        work_root = Path(temporary_directory)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                rounds = [run_round(round_number, browser, work_root) for round_number in range(1, 4)]
            finally:
                browser.close()

    fasta_hashes = {item["fasta_file_sha256"] for item in rounds}
    genbank_hashes = {item["genbank_file_sha256"] for item in rounds}
    parsed_hashes = {item["parsed_sequence_sha256"] for item in rounds}
    cross_round_errors: list[str] = []
    if len(fasta_hashes) != 1 or None in fasta_hashes:
        cross_round_errors.append("FASTA byte SHA-256 values were not identical across rounds")
    if len(genbank_hashes) != 1 or None in genbank_hashes:
        cross_round_errors.append("GenBank byte SHA-256 values were not identical across rounds")
    if len(parsed_hashes) != 1 or None in parsed_hashes:
        cross_round_errors.append("Parsed sequence SHA-256 values were not identical across rounds")

    evidence_rounds = [
        {
            key: item[key]
            for key in (
                "round",
                "cassette_length",
                "plasmid_length",
                "fasta_file_sha256",
                "genbank_file_sha256",
                "parsed_sequence_sha256",
                "browser_error_count",
                "server_exception_count",
                "passed",
                "errors",
            )
        }
        for item in rounds
    ]
    report = {
        "playwright": "successfully executed",
        "passed": all(item["passed"] for item in rounds) and not cross_round_errors,
        "rounds": evidence_rounds,
        "cross_round_errors": cross_round_errors,
        "representative_screenshots": {
            name: str(path.relative_to(REPO_ROOT)) for name, path in REPRESENTATIVE_SCREENSHOTS.items()
        },
    }
    report_path = ARTIFACT_ROOT / "acceptance_result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
