"""Run the three-round MVP workflow through the shipped Windows launcher."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright

from run_mvp_three_round_acceptance import (
    SERVER_EXCEPTION_PATTERN,
    parse_downloads,
    sha256_bytes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "Start_BioDesign_MVP.bat"
STOP_SCRIPT = REPO_ROOT / "Stop_BioDesign_MVP.bat"
STATE_PATH = REPO_ROOT / ".runtime" / "mvp_runtime.json"
ARTIFACT_ROOT = Path(
    os.environ.get("BIODESIGN_MVP4_ACCEPTANCE_DIR", REPO_ROOT / "artifacts" / "mvp4_acceptance")
).resolve()
PROGRESS_PATH = ARTIFACT_ROOT / "progress.json"
RESULT_PATH = ARTIFACT_ROOT / "acceptance_result.json"
WORKER_LOG_PATH = ARTIFACT_ROOT / "acceptance_worker.log"
DIAGNOSTIC_ROOT = ARTIFACT_ROOT / "diagnostics"
ACTION_TIMEOUT_MS = 20_000
APP_TITLE = "项目首页"
LOAD_BUTTON = "加载示例项目"
GENERATE_CASSETTE_BUTTON = "生成表达盒"
GENERATE_BUTTON = "生成完整质粒"
SAVE_BUTTON = "保存项目"
OPEN_BUTTON = "打开"
FASTA_BUTTON = "下载完整质粒 FASTA"
GENBANK_BUTTON = "下载完整质粒 GenBank"
CASSETTE_RESULT = "1750 bp"
PLASMID_RESULT = "5950 bp"
EXPECTED_SEQUENCE_SHA256 = "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"
FORBIDDEN_PAGE_TEXT = ("Traceback", "StreamlitAPIException", "NotFoundError", "DuplicateElementKey")
BENIGN_WEBSOCKET_SHUTDOWN_PATTERN = re.compile(
    r"Task exception was never retrieved\s+future:.*?tornado\.websocket\.WebSocketClosedError\s*",
    re.DOTALL,
)
REPRESENTATIVE_SCREENSHOTS = {
    "after_complete_vector": ARTIFACT_ROOT / "after_complete_vector.png",
    "reopened_design": ARTIFACT_ROOT / "reopened_design.png",
}
ACTIVE_RUN_ID = ""


def _configure_output_dir(output_dir: str) -> None:
    global ARTIFACT_ROOT, PROGRESS_PATH, RESULT_PATH, WORKER_LOG_PATH, DIAGNOSTIC_ROOT
    if output_dir:
        ARTIFACT_ROOT = Path(output_dir).resolve()
    PROGRESS_PATH = ARTIFACT_ROOT / "progress.json"
    RESULT_PATH = ARTIFACT_ROOT / "acceptance_result.json"
    WORKER_LOG_PATH = ARTIFACT_ROOT / "acceptance_worker.log"
    DIAGNOSTIC_ROOT = ARTIFACT_ROOT / "diagnostics"
    REPRESENTATIVE_SCREENSHOTS.update(
        {
            "after_complete_vector": ARTIFACT_ROOT / "after_complete_vector.png",
            "reopened_design": ARTIFACT_ROOT / "reopened_design.png",
        }
    )


def _new_run_id() -> str:
    return f"mvp4-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _begin_run(run_id: str) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.unlink(missing_ok=True)
    PROGRESS_PATH.unlink(missing_ok=True)
    _atomic_write_json(
        PROGRESS_PATH,
        {
            "run_id": run_id,
            "phase": "initialized",
            "round": None,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "stages": [],
        },
    )


def _launcher(script: Path, cwd: Path, environment: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(script), *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=75,
        check=False,
    )


def _write_progress(run_id: str, phase: str, round_number: int | None = None, **extra: Any) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"run_id": run_id, "stages": []}
    if payload.get("run_id") != run_id:
        payload = {"run_id": run_id, "stages": []}
    stage = {"run_id": run_id, "phase": phase, "round": round_number, "updated_at_utc": datetime.now(timezone.utc).isoformat(), **extra}
    payload.update(stage)
    payload.setdefault("stages", []).append(stage)
    _atomic_write_json(PROGRESS_PATH, payload)


def _read_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))


def _page_errors(page: Page, browser_errors: list[str]) -> list[str]:
    errors = list(browser_errors)
    body = page.locator("body").inner_text()
    for forbidden in FORBIDDEN_PAGE_TEXT:
        if forbidden.lower() in body.lower():
            errors.append(f"visible forbidden page text: {forbidden}")
    if page.locator('[data-testid="stException"]').count():
        errors.append("Streamlit exception widget was visible")
    return errors


def _attach_browser_errors(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)


def _attach_diagnostic_events(page: Page, events: dict[str, list[str]]) -> None:
    page.on("pageerror", lambda error: events["pageerrors"].append(str(error)))
    page.on("console", lambda message: events["console"].append(f"{message.type}: {message.text}"))
    page.on("requestfailed", lambda request: events["requestfailed"].append(f"{request.method} {request.url}: {request.failure}"))


def _capture_diagnostic(page: Page | None, directory: Path, phase: str, when: str) -> dict[str, str]:
    if page is None:
        return {}
    directory.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", phase) + "_" + when
    screenshot = directory / f"{stem}.png"
    html = directory / f"{stem}.html"
    try:
        page.screenshot(path=str(screenshot), full_page=True, timeout=ACTION_TIMEOUT_MS)
        html.write_text(page.content(), encoding="utf-8")
        return {"screenshot": str(screenshot), "html": str(html), "url": page.url}
    except Exception as exc:
        return {"capture_error": f"{type(exc).__name__}: {exc}"}


def _diagnostic_stage(
    phase: str,
    round_number: int,
    page: Page | None,
    directory: Path,
    locator: str | None,
    action: Any,
    timeout_ms: int = ACTION_TIMEOUT_MS,
) -> Any:
    _write_progress(ACTIVE_RUN_ID, phase, round_number, state="started", locator=locator, timeout_seconds=timeout_ms / 1000, evidence_before=_capture_diagnostic(page, directory, phase, "before"))
    try:
        value = action()
    except Exception as exc:
        evidence = _capture_diagnostic(page, directory, phase, "failed")
        _write_progress(ACTIVE_RUN_ID, phase, round_number, state="failed", locator=locator, timeout_seconds=timeout_ms / 1000, evidence_after=evidence, error=f"{type(exc).__name__}: {exc}")
        raise RuntimeError(f"phase={phase}; locator={locator}; timeout_seconds={timeout_ms / 1000}; {type(exc).__name__}: {exc}") from exc
    _write_progress(ACTIVE_RUN_ID, phase, round_number, state="completed", locator=locator, timeout_seconds=timeout_ms / 1000, evidence_after=_capture_diagnostic(page, directory, phase, "after"))
    return value


def _http_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=5) as response:
        return int(response.status)


def _wait_for_mvp_interaction(page: Page) -> None:
    expect(page.locator('[data-testid="stAppViewContainer"]')).to_be_visible(timeout=ACTION_TIMEOUT_MS)
    expect(page.get_by_text(APP_TITLE, exact=True)).to_be_visible(timeout=ACTION_TIMEOUT_MS)
    expect(page.get_by_role("button", name=LOAD_BUTTON)).to_be_enabled(timeout=ACTION_TIMEOUT_MS)


def _download_named(page: Page, button_name: str, target: Path) -> Path:
    with page.expect_download(timeout=ACTION_TIMEOUT_MS) as download_info:
        page.get_by_role("button", name=button_name).click(timeout=ACTION_TIMEOUT_MS)
    download_info.value.save_as(target)
    return target


def _download_pair(page: Page, directory: Path, prefix: str) -> tuple[Path, Path]:
    fasta_path = directory / f"{prefix}.fasta"
    genbank_path = directory / f"{prefix}.gb"
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role("button", name=FASTA_BUTTON, exact=True).click(timeout=10_000)
    download_info.value.save_as(fasta_path)
    with page.expect_download(timeout=45_000) as download_info:
        page.get_by_role("button", name=GENBANK_BUTTON, exact=True).click(timeout=10_000)
    download_info.value.save_as(genbank_path)
    return fasta_path, genbank_path


def _server_exception_count(log_texts: list[str]) -> int:
    return sum(
        len(
            SERVER_EXCEPTION_PATTERN.findall(
                BENIGN_WEBSOCKET_SHUTDOWN_PATTERN.sub("", text)
            )
        )
        for text in log_texts
    )


def _primary_button(page: Page, index: int):
    buttons = page.locator('[data-testid="stButton"] button')
    buttons.nth(index).wait_for(state="visible", timeout=20_000)
    button = buttons.nth(index)
    expect(button).to_be_enabled(timeout=20_000)
    return button


def _wait_for_page_text(page: Page, text: str) -> None:
    expect(page.locator("body")).to_contain_text(text, timeout=45_000)


def _select_saved_design(page: Page) -> None:
    expect(page.get_by_text(re.compile(r"Plant single-gene MVP")).first).to_be_visible(
        timeout=ACTION_TIMEOUT_MS
    )


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)


def run_round(run_id: str, round_number: int, browser: Browser, work_root: Path) -> dict[str, Any]:
    _write_progress(run_id, "round_running", round_number)
    round_started_at_ns = time.time_ns()
    round_dir = work_root / f"round-{round_number}"
    round_dir.mkdir(parents=True, exist_ok=True)
    unrelated_cwd = round_dir / "unrelated_cwd"
    unrelated_cwd.mkdir()
    persistence_dir = round_dir / "stable_design_store"
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(persistence_dir)
    result: dict[str, Any] = {
        "round": round_number,
        "url": None,
        "first_pid": None,
        "second_pid": None,
        "reused_pid": None,
        "fasta_before_sha256": None,
        "genbank_before_sha256": None,
        "fasta_after_sha256": None,
        "genbank_after_sha256": None,
        "parsed_sequence_sha256": None,
        "browser_error_count": 0,
        "server_exception_count": 0,
        "passed": False,
        "errors": [],
    }
    browser_errors: list[str] = []
    logs: list[str] = []
    first_page: Page | None = None
    second_page: Page | None = None
    unrelated_process: subprocess.Popen[str] | None = None
    try:
        _launcher(STOP_SCRIPT, REPO_ROOT, environment)
        started = _launcher(START_SCRIPT, REPO_ROOT, environment, "-NoBrowser")
        if started.returncode != 0:
            raise RuntimeError(f"launcher start failed: {started.stdout}\n{started.stderr}")
        first_state = _read_state()
        required_state_keys = {"pid", "python_executable", "process_start_time_utc", "repository_root", "port", "url", "mvp_entry_path"}
        if not required_state_keys <= set(first_state):
            raise RuntimeError("runtime state omitted required ownership fields")
        result["url"] = first_state["url"]
        result["first_pid"] = first_state["pid"]

        first_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_browser_errors(first_page, browser_errors)
        first_page.goto(first_state["url"], wait_until="domcontentloaded", timeout=45_000)
        first_page.get_by_role("button", name=LOAD_BUTTON, exact=True).click(timeout=10_000)
        first_page.wait_for_timeout(750)
        first_page.get_by_role("button", name=GENERATE_CASSETTE_BUTTON, exact=True).click(timeout=10_000)
        first_page.get_by_text("表达盒记录已生成。", exact=True).wait_for(timeout=45_000)
        first_page.get_by_role("button", name=GENERATE_BUTTON, exact=True).click(timeout=10_000)
        _wait_for_page_text(first_page, "1750 bp")
        _wait_for_page_text(first_page, "5950 bp")
        first_page.get_by_role("button", name=SAVE_BUTTON, exact=True).click(timeout=10_000)
        first_page.get_by_text(re.compile(r"项目已保存：Plant single-gene MVP")).wait_for(timeout=20_000)
        before_fasta, before_genbank = _download_pair(first_page, round_dir, "before_restart")
        result["fasta_before_sha256"] = sha256_bytes(before_fasta)
        result["genbank_before_sha256"] = sha256_bytes(before_genbank)
        first_page.screenshot(path=str(round_dir / "after_complete_vector.png"), full_page=True)
        if round_number == 3:
            shutil.copy2(round_dir / "after_complete_vector.png", REPRESENTATIVE_SCREENSHOTS["after_complete_vector"])
        first_page.close()
        first_page = None

        unrelated_process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=unrelated_cwd)
        stopped = _launcher(STOP_SCRIPT, REPO_ROOT, environment)
        if stopped.returncode != 0 or STATE_PATH.exists():
            raise RuntimeError(f"launcher stop failed: {stopped.stdout}\n{stopped.stderr}")
        if unrelated_process.poll() is not None:
            raise RuntimeError("stop script affected an unrelated Python process")
        restarted = _launcher(START_SCRIPT, unrelated_cwd, environment, "-NoBrowser")
        if restarted.returncode != 0:
            raise RuntimeError(f"launcher restart from unrelated cwd failed: {restarted.stdout}\n{restarted.stderr}")
        second_state = _read_state()
        result["second_pid"] = second_state["pid"]
        repeated = _launcher(START_SCRIPT, unrelated_cwd, environment, "-NoBrowser")
        if repeated.returncode != 0:
            raise RuntimeError(f"repeated launcher start failed: {repeated.stdout}\n{repeated.stderr}")
        repeated_state = _read_state()
        result["reused_pid"] = repeated_state["pid"]
        if repeated_state["pid"] != second_state["pid"]:
            raise RuntimeError("repeated start created a second Streamlit process")

        second_page = browser.new_page(viewport={"width": 1440, "height": 1000})
        _attach_browser_errors(second_page, browser_errors)
        second_page.goto(second_state["url"], wait_until="domcontentloaded", timeout=45_000)
        second_page.get_by_text(re.compile(r"Plant single-gene MVP")).wait_for(timeout=20_000)
        second_page.get_by_role("button", name=OPEN_BUTTON, exact=True).first.click(timeout=10_000)
        second_page.get_by_text(re.compile(r"已打开项目：Plant single-gene MVP")).wait_for(timeout=20_000)
        _wait_for_page_text(second_page, "5950 bp")
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
        if parsed_length != 5950 or parsed_sha256 != EXPECTED_SEQUENCE_SHA256:
            result["errors"].append("reopened exported sequence did not match the fixed MVP construct")
        result["errors"].extend(_page_errors(second_page, browser_errors))
        second_page.screenshot(path=str(round_dir / "reopened_design.png"), full_page=True)
        if round_number == 3:
            shutil.copy2(round_dir / "reopened_design.png", REPRESENTATIVE_SCREENSHOTS["reopened_design"])
    except Exception as exc:
        result["errors"].append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        for page in (first_page, second_page):
            if page is not None:
                page.close()
        if STATE_PATH.exists():
            _launcher(STOP_SCRIPT, REPO_ROOT, environment)
        for log in (REPO_ROOT / ".runtime").glob("mvp_streamlit.*.log"):
            if log.stat().st_mtime_ns >= round_started_at_ns:
                logs.append(log.read_text(encoding="utf-8", errors="replace"))
        if unrelated_process is not None:
            _terminate(unrelated_process)
        result["server_exception_count"] = _server_exception_count(logs)
        if result["server_exception_count"]:
            result["errors"].append(f"server exception marker count: {result['server_exception_count']}")
        result["browser_error_count"] = len(browser_errors)
        result["passed"] = not result["errors"]
    return result


def run_diagnostic_one(run_id: str) -> int:
    """Run one foreground round with evidence for every browser action."""
    round_number = 1
    diagnostic_dir = DIAGNOSTIC_ROOT / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    events = {"console": [], "pageerrors": [], "requestfailed": []}
    result: dict[str, Any] = {"round": round_number, "passed": False, "errors": [], "browser_events": events}
    environment = dict(os.environ)
    started_at = time.monotonic()
    run_started_at_ns = time.time_ns()
    context: BrowserContext | None = None
    first_page: Page | None = None
    second_page: Page | None = None
    unrelated_process: subprocess.Popen[str] | None = None
    work_root: Path | None = None
    try:
        temp = tempfile.mkdtemp(prefix="mvp4_windows_launcher_", dir=ARTIFACT_ROOT)
        work_root = Path(temp)
        if work_root is not None:
            unrelated_cwd = work_root / "unrelated_cwd"
            unrelated_cwd.mkdir()
            environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(work_root / "stable_design_store")
            _launcher(STOP_SCRIPT, REPO_ROOT, environment)
            started = _diagnostic_stage("launcher_start_requested", round_number, None, diagnostic_dir, str(START_SCRIPT), lambda: _launcher(START_SCRIPT, REPO_ROOT, environment, "-NoBrowser"), 75_000)
            if started.returncode != 0:
                raise RuntimeError(f"launcher start failed: {started.stdout}\n{started.stderr}")
            state = _read_state()
            result.update(url=state["url"], first_pid=state["pid"])
            status = _diagnostic_stage("launcher_http_ready", round_number, None, diagnostic_dir, "HTTP GET runtime.json.url", lambda: _http_status(state["url"]))
            if status != 200:
                raise RuntimeError(f"launcher HTTP status was {status}, expected 200")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
                    context.tracing.start(screenshots=True, snapshots=True, sources=True)
                    first_page = _diagnostic_stage("browser_opened", round_number, None, diagnostic_dir, state["url"], context.new_page)
                    _attach_diagnostic_events(first_page, events)
                    _diagnostic_stage("app_root_visible", round_number, first_page, diagnostic_dir, f"URL {state['url']}; stAppViewContainer; text={APP_TITLE}", lambda: (first_page.goto(state["url"], wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS), _wait_for_mvp_interaction(first_page)))
                    _diagnostic_stage("examples_loaded", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={LOAD_BUTTON!r})", lambda: first_page.get_by_role("button", name=LOAD_BUTTON, exact=True).click(timeout=ACTION_TIMEOUT_MS))
                    _diagnostic_stage("cassette_generated", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={GENERATE_CASSETTE_BUTTON!r})", lambda: (first_page.get_by_role("button", name=GENERATE_CASSETTE_BUTTON, exact=True).click(timeout=ACTION_TIMEOUT_MS), expect(first_page.get_by_text("表达盒记录已生成。", exact=True)).to_be_visible(timeout=ACTION_TIMEOUT_MS)))
                    _diagnostic_stage("generate_clicked", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={GENERATE_BUTTON!r})", lambda: first_page.get_by_role("button", name=GENERATE_BUTTON, exact=True).click(timeout=ACTION_TIMEOUT_MS))
                    _diagnostic_stage("generation_result_visible", round_number, first_page, diagnostic_dir, f"body contains {CASSETTE_RESULT!r} and {PLASMID_RESULT!r}", lambda: (expect(first_page.locator("body")).to_contain_text(CASSETTE_RESULT, timeout=ACTION_TIMEOUT_MS), expect(first_page.locator("body")).to_contain_text(PLASMID_RESULT, timeout=ACTION_TIMEOUT_MS)))
                    before_fasta = _diagnostic_stage("fasta_downloaded", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={FASTA_BUTTON!r})", lambda: _download_named(first_page, FASTA_BUTTON, work_root / "before.fasta"))
                    before_genbank = _diagnostic_stage("genbank_downloaded", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={GENBANK_BUTTON!r})", lambda: _download_named(first_page, GENBANK_BUTTON, work_root / "before.gb"))
                    result["fasta_before_sha256"] = sha256_bytes(before_fasta)
                    result["genbank_before_sha256"] = sha256_bytes(before_genbank)
                    _diagnostic_stage("save_clicked", round_number, first_page, diagnostic_dir, f"get_by_role('button', name={SAVE_BUTTON!r})", lambda: first_page.get_by_role("button", name=SAVE_BUTTON, exact=True).click(timeout=ACTION_TIMEOUT_MS))
                    _diagnostic_stage("save_confirmed", round_number, first_page, diagnostic_dir, "get_by_text('项目已保存：')", lambda: expect(first_page.get_by_text(re.compile("项目已保存："))).to_be_visible(timeout=ACTION_TIMEOUT_MS))
                    unrelated_process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=unrelated_cwd)
                    stopped = _diagnostic_stage("launcher_stopped", round_number, first_page, diagnostic_dir, str(STOP_SCRIPT), lambda: _launcher(STOP_SCRIPT, REPO_ROOT, environment))
                    if stopped.returncode != 0 or STATE_PATH.exists() or unrelated_process.poll() is not None:
                        raise RuntimeError("stop did not remove only the owned runtime")
                    first_page.close()
                    first_page = None
                    restarted = _diagnostic_stage("restart_from_unrelated_cwd", round_number, None, diagnostic_dir, str(START_SCRIPT), lambda: _launcher(START_SCRIPT, unrelated_cwd, environment, "-NoBrowser"), 75_000)
                    if restarted.returncode != 0:
                        raise RuntimeError(f"restart failed: {restarted.stdout}\n{restarted.stderr}")
                    restarted_state = _read_state()
                    result["second_pid"] = restarted_state["pid"]
                    repeated = _launcher(START_SCRIPT, unrelated_cwd, environment, "-NoBrowser")
                    repeated_state = _read_state()
                    result["reused_pid"] = repeated_state["pid"]
                    if repeated.returncode != 0 or repeated_state["pid"] != restarted_state["pid"]:
                        raise RuntimeError("repeated start did not reuse the same PID")
                    second_page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    _attach_diagnostic_events(second_page, events)
                    _diagnostic_stage("saved_design_selected", round_number, second_page, diagnostic_dir, "recent project list", lambda: (second_page.goto(restarted_state["url"], wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS), _wait_for_mvp_interaction(second_page), _select_saved_design(second_page)))
                    _diagnostic_stage("saved_design_opened", round_number, second_page, diagnostic_dir, f"get_by_role('button', name={OPEN_BUTTON!r}); text=已打开项目：", lambda: (second_page.get_by_role("button", name=OPEN_BUTTON, exact=True).first.click(timeout=ACTION_TIMEOUT_MS), expect(second_page.get_by_text(re.compile("已打开项目："))).to_be_visible(timeout=ACTION_TIMEOUT_MS)))
                    _diagnostic_stage("post_restart_downloads_completed", round_number, second_page, diagnostic_dir, f"body contains {CASSETTE_RESULT!r} and {PLASMID_RESULT!r}", lambda: (expect(second_page.locator("body")).to_contain_text(CASSETTE_RESULT, timeout=ACTION_TIMEOUT_MS), expect(second_page.locator("body")).to_contain_text(PLASMID_RESULT, timeout=ACTION_TIMEOUT_MS)))
                    after_fasta = _diagnostic_stage("post_restart_fasta_downloaded", round_number, second_page, diagnostic_dir, f"get_by_role('button', name={FASTA_BUTTON!r})", lambda: _download_named(second_page, FASTA_BUTTON, work_root / "after.fasta"))
                    after_genbank = _diagnostic_stage("post_restart_genbank_downloaded", round_number, second_page, diagnostic_dir, f"get_by_role('button', name={GENBANK_BUTTON!r})", lambda: _download_named(second_page, GENBANK_BUTTON, work_root / "after.gb"))
                    result["fasta_after_sha256"] = sha256_bytes(after_fasta)
                    result["genbank_after_sha256"] = sha256_bytes(after_genbank)
                    if before_fasta.read_bytes() != after_fasta.read_bytes() or before_genbank.read_bytes() != after_genbank.read_bytes():
                        result["errors"].append("restart download bytes differed")
                    parsed_length, parsed_sha256, parse_errors = parse_downloads(after_fasta, after_genbank)
                    result["parsed_sequence_sha256"] = parsed_sha256
                    result["errors"].extend(parse_errors)
                    if parsed_length != 5950 or parsed_sha256 != EXPECTED_SEQUENCE_SHA256:
                        result["errors"].append("reopened exported sequence did not match the fixed MVP construct")
                    result["errors"].extend(_page_errors(second_page, [entry for entry in events["console"] if entry.startswith("error:")] + [f"pageerror: {entry}" for entry in events["pageerrors"]] + [f"requestfailed: {entry}" for entry in events["requestfailed"]]))
                finally:
                    if context is not None:
                        context.tracing.stop(path=str(diagnostic_dir / "trace.zip"))
                    browser.close()
    except Exception as exc:
        result["errors"].append(f"acceptance execution error: {type(exc).__name__}: {exc}")
    finally:
        for page in (first_page, second_page):
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
        if STATE_PATH.exists():
            _diagnostic_stage("launcher_stopped", round_number, None, diagnostic_dir, str(STOP_SCRIPT), lambda: _launcher(STOP_SCRIPT, REPO_ROOT, environment))
        if unrelated_process is not None:
            _terminate(unrelated_process)
            unrelated_process = None
        if work_root is not None and result["passed"]:
            shutil.rmtree(work_root, ignore_errors=True)
        result["trace_path"] = str(diagnostic_dir / "trace.zip")
        result["server_exception_count"] = _server_exception_count(
            [
                log.read_text(encoding="utf-8", errors="replace")
                for log in (REPO_ROOT / ".runtime").glob("mvp_streamlit.*.log")
                if log.stat().st_mtime_ns >= run_started_at_ns
            ]
        )
        result["browser_error_count"] = len(events["pageerrors"]) + len(events["requestfailed"]) + len([entry for entry in events["console"] if entry.startswith("error:")])
        result["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        result["passed"] = not result["errors"]
    report = {"run_id": run_id, "playwright": "diagnostic one round", "passed": result["passed"], "rounds": [result]}
    _atomic_write_json(RESULT_PATH, report)
    _write_progress(run_id, "completed", round_number, passed=result["passed"], elapsed_seconds=result["elapsed_seconds"])
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


def run_worker(run_id: str) -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    _write_progress(run_id, "starting")
    try:
        with tempfile.TemporaryDirectory(prefix="mvp4_windows_launcher_", dir=ARTIFACT_ROOT) as temporary_directory:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    rounds = [run_round(run_id, index, browser, Path(temporary_directory)) for index in range(1, 4)]
                finally:
                    browser.close()
        report = {"run_id": run_id, "playwright": "successfully executed", "passed": all(item["passed"] for item in rounds), "rounds": rounds}
    except Exception as exc:
        report = {"run_id": run_id, "playwright": "worker failed", "passed": False, "rounds": [], "errors": [f"{type(exc).__name__}: {exc}"]}
    _atomic_write_json(RESULT_PATH, report)
    _write_progress(run_id, "completed", passed=report["passed"])
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["passed"] else 1


def main() -> int:
    global ACTIVE_RUN_ID
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--diagnostic-one", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output-dir", default=os.environ.get("BIODESIGN_MVP4_ACCEPTANCE_DIR", ""))
    args = parser.parse_args()
    _configure_output_dir(args.output_dir)
    run_id = args.run_id or _new_run_id()
    ACTIVE_RUN_ID = run_id
    if args.diagnostic_one:
        _begin_run(run_id)
        return run_diagnostic_one(run_id)
    if args.worker:
        return run_worker(run_id)
    _begin_run(run_id)
    _write_progress(run_id, "queued")
    with WORKER_LOG_PATH.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--run-id",
                run_id,
                "--output-dir",
                str(ARTIFACT_ROOT),
            ],
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    _write_progress(run_id, "running", worker_pid=process.pid, timeout_seconds=900)
    print(json.dumps({"started": True, "run_id": run_id, "worker_pid": process.pid, "progress_path": str(PROGRESS_PATH), "timeout_seconds": 900}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
