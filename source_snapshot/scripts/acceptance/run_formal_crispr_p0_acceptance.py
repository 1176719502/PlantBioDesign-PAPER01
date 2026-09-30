"""Browser acceptance for the bounded CRISPR P0 product workspace."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

from playwright.sync_api import Page, expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.acceptance.run_formal_single_gene_blank_acceptance import (
    _attach_browser_errors,
    _click_button,
    _download,
    _port_is_free,
    _reserve_local_url,
    _start_server,
    _stop_server,
)
from services.crispr_product_workflow import CRISPR_PRODUCT_STATE_KEY
from services.plant_project_draft_repository import PlantProjectDraftRepository
ARTIFACT_BASE = Path(
    os.environ.get("BIODESIGN_ACCEPTANCE_ARTIFACT_ROOT")
    or Path(tempfile.gettempdir()) / "BioDesignStudio" / "acceptance"
).resolve()
ARTIFACT_ROOT = ARTIFACT_BASE / "formal_crispr_p0_acceptance"
RESULT_PATH = ARTIFACT_ROOT / "acceptance_result.json"
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
TARGET_SEQUENCE = "AAA" + "ACGT" * 5 + "TGG" + "AAA"
PROJECT_NAME = "CRISPR P0 browser acceptance"
STREAMLIT_STALE_SELECTOR = '[data-stale="true"]'
STREAMLIT_CRISPR_ACK_KEY = "__biodesignCrisprRerunAcknowledgement"
WEBSOCKET_CLOSED_ERROR_MARKER = "tornado.websocket.WebSocketClosedError"
EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE = "EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE"
TEARDOWN_PHASES = {
    "browser/page close",
    "final browser close",
    "process stop",
    "final process stop",
    "port release",
    "final port release",
}
REQUIRED_PHASES = {
    "initial app start",
    "websocket/session ready",
    "crispr workflow completion",
    "save",
    "download verification",
    "browser/page close",
    "process stop",
    "port release",
    "restart",
    "cold reopen",
    "final verification",
    "final browser close",
    "final process stop",
    "final port release",
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_dimensions(path: Path) -> dict[str, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG: {path}")
    return {
        "width": int.from_bytes(header[16:20], "big"),
        "height": int.from_bytes(header[20:24], "big"),
    }


def _screenshot(page: Page, name: str, viewport: dict[str, int]) -> dict[str, Any]:
    actual = page.evaluate("({width: window.innerWidth, height: window.innerHeight})")
    if actual != viewport:
        raise AssertionError(f"actual viewport {actual!r} != requested {viewport!r}")
    path = ARTIFACT_ROOT / f"{name}-{viewport['width']}x{viewport['height']}.png"
    page.screenshot(path=str(path), full_page=False)
    if _png_dimensions(path) != viewport:
        raise AssertionError("screenshot dimensions did not match the viewport")
    return {
        "viewport": f"{viewport['width']}x{viewport['height']}",
        "requested_viewport": viewport,
        "actual_viewport": actual,
        "screenshot_dimensions": _png_dimensions(path),
        "screenshot_path": path.name,
        "screenshot_sha256": _sha256(path),
        "result": "PASS",
    }


def _arm_streamlit_rerun_acknowledgement(page: Page) -> None:
    """Arm a stale-to-fresh observer before an interaction-triggered rerun."""

    expect(page.locator(STREAMLIT_STALE_SELECTOR)).to_have_count(0, timeout=30_000)
    page.evaluate(
        """([ackKey, staleSelector]) => {
            const previous = window[ackKey];
            if (previous?.observer) previous.observer.disconnect();
            const state = { sawStale: false, sawFresh: false };
            const hasStale = () => Boolean(document.querySelector(staleSelector));
            const markAddedNode = node => {
                if (node.nodeType !== Node.ELEMENT_NODE) return false;
                return node.matches(staleSelector) || Boolean(node.querySelector(staleSelector));
            };
            const observe = mutations => {
                for (const mutation of mutations) {
                    if (mutation.type === "attributes"
                        && mutation.attributeName === "data-stale"
                        && mutation.target.matches(staleSelector)
                        && mutation.target.getAttribute("data-stale") === "true") {
                        state.sawStale = true;
                    }
                    if (mutation.type === "childList"
                        && [...mutation.addedNodes].some(markAddedNode)) {
                        state.sawStale = true;
                    }
                }
                if (hasStale()) state.sawStale = true;
                if (state.sawStale && !hasStale()) state.sawFresh = true;
            };
            const observer = new MutationObserver(observe);
            observer.observe(document.documentElement, {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: ["data-stale"],
            });
            window[ackKey] = { observer, state, staleSelector };
        }""",
        [STREAMLIT_CRISPR_ACK_KEY, STREAMLIT_STALE_SELECTOR],
    )


def _wait_for_streamlit_rerun_acknowledgement(page: Page) -> None:
    page.wait_for_function(
        """ackKey => {
            const acknowledgement = window[ackKey];
            return Boolean(
                acknowledgement?.state?.sawStale
                && acknowledgement?.state?.sawFresh
                && !document.querySelector(acknowledgement.staleSelector)
            );
        }""",
        arg=STREAMLIT_CRISPR_ACK_KEY,
        timeout=30_000,
    )
    page.evaluate(
        """ackKey => {
            const acknowledgement = window[ackKey];
            if (acknowledgement?.observer) acknowledgement.observer.disconnect();
            delete window[ackKey];
        }""",
        STREAMLIT_CRISPR_ACK_KEY,
    )


def _click_and_wait_for_streamlit_rerun(page: Page, locator: Any) -> None:
    _arm_streamlit_rerun_acknowledgement(page)
    locator.click()
    _wait_for_streamlit_rerun_acknowledgement(page)


def _commit_text(page: Page, label: str, value: str) -> None:
    _arm_streamlit_rerun_acknowledgement(page)
    textbox = page.get_by_role("textbox", name=label, exact=True)
    expect(textbox).to_have_count(1, timeout=30_000)
    textbox.fill(value)
    textbox.press("Tab")
    _wait_for_streamlit_rerun_acknowledgement(page)
    expect(
        page.get_by_role("textbox", name=label, exact=True)
    ).to_have_value(value, timeout=30_000)


def _commit_reference_identity_text(page: Page, label: str, value: str) -> None:
    _arm_streamlit_rerun_acknowledgement(page)
    expander = page.locator('[data-testid="stExpander"]').filter(
        has_text="高级 / Reproducibility"
    ).first
    expect(expander).to_have_count(1, timeout=30_000)
    textbox = expander.get_by_role("textbox", name=label, exact=True)
    if textbox.count() == 0:
        expander.locator("summary").click()
        textbox = expander.get_by_role("textbox", name=label, exact=True)
    expect(textbox).to_have_count(1, timeout=30_000)
    textbox.fill(value)
    textbox.press("Tab")
    _wait_for_streamlit_rerun_acknowledgement(page)
    current_expander = page.locator('[data-testid="stExpander"]').filter(
        has_text="高级 / Reproducibility"
    ).first
    current_textbox = current_expander.get_by_role(
        "textbox", name=label, exact=True
    )
    if current_textbox.count() == 0:
        current_expander.locator("summary").click()
        current_textbox = current_expander.get_by_role(
            "textbox", name=label, exact=True
        )
    expect(current_textbox).to_have_count(1, timeout=30_000)
    expect(current_textbox).to_have_value(value, timeout=30_000)


def _wait_port_free(port: int, timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _port_is_free(port):
            return True
        time.sleep(0.1)
    return _port_is_free(port)


def _mark_phase(
    result: dict[str, Any],
    phase: str,
    *,
    process: subprocess.Popen[str] | None = None,
    port: int | None = None,
) -> None:
    """Record an observable acceptance phase and the owned runtime state."""

    result.setdefault("phase_markers", []).append(
        {
            "phase": phase,
            "monotonic": time.monotonic(),
            "wall_time": time.time(),
            "process_pid": process.pid if process is not None else None,
            "process_alive": process is not None and process.poll() is None,
            "port_free": _port_is_free(port) if port is not None else None,
        }
    )


def _close_page_cleanly(
    page: Page,
    result: dict[str, Any],
    *,
    phase: str = "browser/page close",
) -> None:
    """Detach a Streamlit session before closing its browser page."""

    if page.is_closed():
        return
    _mark_phase(result, phase)
    page.goto("about:blank", wait_until="domcontentloaded", timeout=10_000)
    page.close(run_before_unload=True)
    _mark_phase(result, phase)


def _server_log_blocks(paths: list[Path]) -> list[dict[str, Any]]:
    """Split server output into timestamped error blocks for phase classification."""

    blocks: list[dict[str, Any]] = []
    timestamp_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    for path in paths:
        if not path.exists():
            continue
        current: list[str] = []
        timestamp: float | None = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = timestamp_pattern.match(line)
            if match and current:
                text = "\n".join(current)
                if "ERROR" in text or "Traceback" in text:
                    blocks.append({"path": str(path), "wall_time": timestamp, "text": text})
                current = []
                timestamp = None
            if match and timestamp is None:
                try:
                    timestamp = time.mktime(time.strptime(match.group(1), "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    timestamp = None
            current.append(line)
        if current:
            text = "\n".join(current)
            if "ERROR" in text or "Traceback" in text:
                blocks.append({"path": str(path), "wall_time": timestamp, "text": text})
    return blocks


def _classify_server_logs(
    paths: list[Path], result: dict[str, Any]
) -> dict[str, Any]:
    """Classify only a WebSocket close observed after successful product assertions."""

    markers = list(result.get("phase_markers") or [])
    blocks = _server_log_blocks(paths)
    websocket_events: list[dict[str, Any]] = []
    unexpected_events: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block["text"])
        if WEBSOCKET_CLOSED_ERROR_MARKER in text:
            websocket_events.append(block)
        elif "ERROR" in text or "Traceback" in text:
            unexpected_events.append(block)

    success_times = [
        marker["wall_time"]
        for marker in markers
        if marker["phase"] in {"crispr workflow completion", "final verification"}
    ]
    teardown_times = [
        marker["wall_time"]
        for marker in markers
        if marker["phase"] in TEARDOWN_PHASES
    ]
    benign: list[dict[str, Any]] = []
    misphased: list[dict[str, Any]] = []
    for event in websocket_events:
        event_time = event.get("wall_time")
        latest_phase = None
        phase_resolution_anchor = None
        if event_time is not None:
            prior = [
                marker for marker in markers if marker["wall_time"] <= event_time
            ]
            if prior:
                latest_phase = prior[-1]["phase"]
            if latest_phase not in TEARDOWN_PHASES:
                nearby_teardown = [
                    marker
                    for marker in markers
                    if marker["phase"] in TEARDOWN_PHASES
                    # Streamlit's log timestamp has one-second precision; only
                    # accept an exact-second match to an observed teardown marker.
                    and int(marker["wall_time"]) == int(event_time)
                ]
                if nearby_teardown:
                    phase_resolution_anchor = min(
                        nearby_teardown, key=lambda marker: marker["wall_time"]
                    )
                    latest_phase = phase_resolution_anchor["phase"]
        is_post_success = bool(success_times and event_time is not None and event_time >= min(success_times))
        is_teardown = latest_phase in TEARDOWN_PHASES and bool(teardown_times)
        classified = dict(event)
        classified["latest_phase"] = latest_phase
        classified["phase_resolution_anchor"] = phase_resolution_anchor
        classified["post_success"] = is_post_success
        classified["deliberate_teardown"] = is_teardown
        if is_post_success and is_teardown:
            benign.append(classified)
        else:
            misphased.append(classified)

    classification = None
    if websocket_events:
        classification = (
            EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE
            if not misphased and not unexpected_events
            else "PRODUCT_RUNTIME_DEFECT"
        )
    return {
        "websocket_error_count": len(websocket_events),
        "websocket_events": websocket_events,
        "benign_websocket_events": benign,
        "misphased_websocket_events": misphased,
        "unexpected_server_error_count": len(unexpected_events),
        "unexpected_server_errors": unexpected_events,
        "classification": classification,
    }


def _acceptance_passes(result: dict[str, Any]) -> bool:
    """Apply the fail-closed acceptance contract after phase classification."""

    observed_phases = {marker.get("phase") for marker in result.get("phase_markers", [])}
    return bool(
        REQUIRED_PHASES <= observed_phases
        and
        result.get("first_blocker") is None
        and not result.get("browser_errors")
        and result.get("server_exception_count") == 0
        and result.get("process_cleanup_complete") is True
        and result.get("port_cleanup_complete") is True
        and result.get("websocket_error_count", 0) == len(result.get("benign_websocket_events", []))
        and result.get("direct_compute_export_without_project") is True
        and result.get("desktop", {}).get("viewport") == "1440x900"
        and result.get("mobile", {}).get("viewport") == "390x844"
    )


def _collapse_mobile_sidebar(page: Page) -> bool:
    if int(page.evaluate("window.innerWidth")) > MOBILE_VIEWPORT["width"]:
        return False
    sidebar = page.locator('[data-testid="stSidebar"]').first
    if sidebar.count() == 0 or not sidebar.is_visible():
        return False
    box = sidebar.bounding_box()
    if box is None or box["x"] + box["width"] <= 0:
        return False
    collapse = page.locator(
        '[data-testid="stSidebarCollapseButton"] button'
    ).first
    expect(collapse).to_be_visible(timeout=30_000)
    collapse.click()
    expect(sidebar).not_to_be_in_viewport(timeout=30_000)
    return True


def _expand_mobile_sidebar(page: Page) -> None:
    expand = page.locator(
        '[data-testid="stSidebarCollapsedControl"] button'
    ).first
    if expand.count() == 0:
        expand = page.get_by_role(
            "button", name="keyboard_double_arrow_right", exact=True
        ).first
    expect(expand).to_be_visible(timeout=30_000)
    expand.click()
    expect(page.get_by_role("button", name="CRISPR", exact=True)).to_be_visible(
        timeout=30_000
    )


def _open_project_and_crispr(
    page: Page,
    local_url: str,
    *,
    expect_existing: bool,
) -> None:
    page.goto(local_url, wait_until="domcontentloaded", timeout=45_000)
    page.get_by_role("heading", name="项目中心", exact=True).wait_for(timeout=30_000)
    sidebar_collapsed = _collapse_mobile_sidebar(page)
    if expect_existing:
        expect(page.get_by_text(PROJECT_NAME, exact=True)).to_be_visible(
            timeout=30_000
        )
        _click_and_wait_for_streamlit_rerun(
            page, page.get_by_role("button", name="打开", exact=True)
        )
    else:
        _click_and_wait_for_streamlit_rerun(
            page, page.get_by_role("button", name="新建单基因项目", exact=True)
        )
        page.get_by_role(
            "heading", name="第一步：项目定义与表达目标", exact=True
        ).wait_for(timeout=30_000)
        _commit_text(page, "项目名称 *", PROJECT_NAME)
        _click_and_wait_for_streamlit_rerun(
            page, page.get_by_role("button", name="保存草稿", exact=True)
        )
        expect(page.locator("body")).to_contain_text(
            "项目草稿已保存，可从项目中心重新打开。",
            timeout=30_000,
        )
    page.get_by_role(
        "heading", name="第一步：项目定义与表达目标", exact=True
    ).wait_for(timeout=30_000)
    if sidebar_collapsed:
        _expand_mobile_sidebar(page)
    _click_and_wait_for_streamlit_rerun(
        page, page.get_by_role("button", name="CRISPR", exact=True)
    )
    page.get_by_role("heading", name="基因编辑 · CRISPR", exact=True).wait_for(
        timeout=30_000
    )


def _assert_blank_direct_entry(page: Page) -> None:
    target = page.get_by_role("textbox", name="目标 DNA 序列", exact=True)
    expect(target).to_have_value("")
    expect(page.locator("body")).not_to_contain_text("EXPRESSION-CDS-SENTINEL")
    for heading in (
        "1. 编辑目标",
        "2. 参考序列",
        "3. gRNA 候选",
        "4. 脱靶分析",
        "5. 用户确认",
        "6. 结果与导出",
    ):
        expect(page.get_by_role("heading", name=heading, exact=True)).to_have_count(1)


def _compute_select_confirm_export(
    page: Page,
    *,
    reference_path: Path,
    download_path: Path,
    project_linked: bool,
) -> bytes:
    _commit_text(page, "目标名称", "Browser target")
    _commit_text(page, "目标 DNA 序列", TARGET_SEQUENCE)
    _commit_text(page, "本机参考 FASTA 路径", str(reference_path))
    _commit_text(page, "参考 contig", "chr1")
    _commit_reference_identity_text(
        page, "Assembly accession", "GCF_000001735.4"
    )
    _commit_reference_identity_text(page, "Assembly version", "TAIR10.1")
    _click_and_wait_for_streamlit_rerun(
        page, page.get_by_role("button", name="枚举确定性候选", exact=True)
    )
    expect(page.get_by_role("button", name="选择此 guide", exact=True)).to_be_enabled(
        timeout=30_000
    )
    expect(page.locator("body")).to_contain_text("SpCas9CandidateScannerV1")
    _click_and_wait_for_streamlit_rerun(
        page, page.get_by_role("button", name="选择此 guide", exact=True)
    )
    expect(page.locator("body")).to_contain_text("已选择：")
    expect(page.locator("body")).to_contain_text("状态：not_run")
    _click_and_wait_for_streamlit_rerun(
        page, page.get_by_role("button", name="确认此 guide 选择", exact=True)
    )
    expect(page.locator("body")).to_contain_text("用户选择已确认")
    _download(page, "下载 CRISPR JSON", download_path)
    payload = download_path.read_bytes()
    decoded = json.loads(payload.decode("utf-8"))
    if decoded["workflow_id"] not in download_path.read_text(encoding="utf-8"):
        raise AssertionError("downloaded JSON did not preserve workflow identity")
    if decoded["selection"] is None:
        raise AssertionError("downloaded JSON did not preserve explicit selection")
    tsv = page.get_by_role("button", name="下载脱靶 TSV", exact=True)
    expect(tsv).to_be_disabled()
    if project_linked:
        _click_and_wait_for_streamlit_rerun(
            page,
            page.get_by_role("button", name="保存 CRISPR 审阅记录", exact=True),
        )
        expect(page.locator("body")).to_contain_text(
            "CRISPR 审阅记录已保存",
            timeout=30_000,
        )
    else:
        expect(
            page.get_by_role(
                "button", name="保存 CRISPR 审阅记录", exact=True
            )
        ).to_have_count(0)
        expect(page.locator("body")).to_contain_text(
            "当前没有活动项目：可计算和导出",
            timeout=30_000,
        )
    return payload


def _reopen_and_download(
    page: Page,
    local_url: str,
    target: Path,
    *,
    persistence_dir: Path,
    result: dict[str, Any],
    checkpoint: str,
) -> bytes:
    _open_project_and_crispr(page, local_url, expect_existing=True)
    _collapse_mobile_sidebar(page)
    repository = PlantProjectDraftRepository(persistence_dir)
    summaries = repository.list_summaries()
    result[f"{checkpoint}_project_ids"] = [item.project_id for item in summaries]
    result[f"{checkpoint}_manual_review_keys"] = {
        item.project_id: sorted(repository.load(item.project_id).manual_review_state)
        for item in summaries
    }
    expect(page.get_by_text("已保存的 CRISPR 审阅记录", exact=True)).to_be_visible(
        timeout=30_000
    )
    _click_and_wait_for_streamlit_rerun(
        page, page.get_by_role("button", name="验证并重新打开", exact=True)
    )
    expect(page.locator("body")).to_contain_text("已选择：", timeout=30_000)
    _download(page, "下载 CRISPR JSON", target)
    return target.read_bytes()


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "schema_version": "biodesign.v1.crispr-p0-acceptance.r2",
        "passed": False,
        "entrypoint": "app.py",
        "route": "CRISPR V1 Workflow",
        "candidate_sha": _git("rev-parse", "HEAD"),
        "lane": os.environ.get("BIODESIGN_QUALIFICATION_LANE"),
        "browser_errors": [],
        "first_blocker": None,
        "process_cleanup_complete": False,
        "port_cleanup_complete": False,
        "phase_markers": [],
    }
    browser_errors: list[str] = []
    local_url, port = _reserve_local_url()
    result["port"] = port
    processes: list[subprocess.Popen[str]] = []
    active: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="crispr_p0_") as temp_dir:
        work_dir = Path(temp_dir)
        persistence_dir = work_dir / "drafts"
        reference = work_dir / "reference.fa"
        reference.write_text(f">chr1\n{TARGET_SEQUENCE}\n", encoding="utf-8")
        os.environ["BIODESIGN_DB_PATH"] = str(work_dir / "runtime.db")
        first_log = ARTIFACT_ROOT / "streamlit-before-restart.log"
        second_log = ARTIFACT_ROOT / "streamlit-after-restart.log"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    _mark_phase(result, "initial app start", port=port)
                    active = _start_server(
                        log_path=first_log,
                        persistence_dir=persistence_dir,
                        local_url=local_url,
                        port=port,
                    )
                    processes.append(active)
                    desktop = browser.new_page(
                        viewport=DESKTOP_VIEWPORT,
                        accept_downloads=True,
                    )
                    _attach_browser_errors(desktop, browser_errors)
                    desktop.goto(
                        local_url,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    desktop.get_by_role(
                        "heading", name="项目中心", exact=True
                    ).wait_for(timeout=30_000)
                    _mark_phase(result, "websocket/session ready", process=active, port=port)
                    _click_and_wait_for_streamlit_rerun(
                        desktop,
                        desktop.get_by_role("button", name="CRISPR", exact=True),
                    )
                    desktop.get_by_role(
                        "heading", name="基因编辑 · CRISPR", exact=True
                    ).wait_for(timeout=30_000)
                    _assert_blank_direct_entry(desktop)
                    direct_json = _compute_select_confirm_export(
                        desktop,
                        reference_path=reference,
                        download_path=work_dir / "direct.json",
                        project_linked=False,
                    )
                    result["direct_compute_export_without_project"] = True
                    _open_project_and_crispr(
                        desktop,
                        local_url,
                        expect_existing=False,
                    )
                    _assert_blank_direct_entry(desktop)
                    before_json = _compute_select_confirm_export(
                        desktop,
                        reference_path=reference,
                        download_path=work_dir / "before.json",
                        project_linked=True,
                    )
                    if direct_json != before_json:
                        raise AssertionError(
                            "project association changed deterministic CRISPR JSON bytes"
                        )
                    repository = PlantProjectDraftRepository(persistence_dir)
                    summaries = repository.list_summaries()
                    if len(summaries) != 1:
                        raise AssertionError(
                            f"expected one project after CRISPR save, got {len(summaries)}"
                        )
                    persisted = repository.load(summaries[0].project_id)
                    result["persisted_project_id"] = persisted.project_id
                    result["persisted_project_name"] = persisted.project_name
                    result["persisted_manual_review_keys"] = sorted(
                        persisted.manual_review_state
                    )
                    if CRISPR_PRODUCT_STATE_KEY not in persisted.manual_review_state:
                        raise AssertionError("CRISPR namespace was absent after browser save")
                    _mark_phase(result, "save", process=active, port=port)
                    _mark_phase(result, "download verification", process=active, port=port)
                    _mark_phase(result, "crispr workflow completion", process=active, port=port)
                    result["desktop"] = _screenshot(
                        desktop,
                        "crispr-p0-desktop",
                        DESKTOP_VIEWPORT,
                    )
                    _close_page_cleanly(desktop, result)

                    _mark_phase(result, "process stop", process=active, port=port)
                    _stop_server(active)
                    active = None
                    if not _wait_port_free(port):
                        raise AssertionError("formal port was not released before cold restart")
                    _mark_phase(result, "port release", port=port)

                    _mark_phase(result, "restart", port=port)
                    active = _start_server(
                        log_path=second_log,
                        persistence_dir=persistence_dir,
                        local_url=local_url,
                        port=port,
                    )
                    processes.append(active)
                    reopened_page = browser.new_page(
                        viewport=DESKTOP_VIEWPORT,
                        accept_downloads=True,
                    )
                    _attach_browser_errors(reopened_page, browser_errors)
                    after_json = _reopen_and_download(
                        reopened_page,
                        local_url,
                        work_dir / "after.json",
                        persistence_dir=persistence_dir,
                        result=result,
                        checkpoint="desktop_reopen",
                    )
                    if after_json != before_json:
                        raise AssertionError("cold-reopened aggregate JSON bytes changed")
                    _mark_phase(result, "cold reopen", process=active, port=port)
                    _close_page_cleanly(reopened_page, result)

                    mobile = browser.new_page(
                        viewport=MOBILE_VIEWPORT,
                        accept_downloads=True,
                    )
                    _attach_browser_errors(mobile, browser_errors)
                    mobile_json = _reopen_and_download(
                        mobile,
                        local_url,
                        work_dir / "mobile.json",
                        persistence_dir=persistence_dir,
                        result=result,
                        checkpoint="mobile_reopen",
                    )
                    if mobile_json != before_json:
                        raise AssertionError("mobile reopened aggregate JSON bytes changed")
                    overflow = mobile.evaluate(
                        "document.documentElement.scrollWidth - window.innerWidth"
                    )
                    if int(overflow) != 0:
                        raise AssertionError(f"mobile horizontal overflow: {overflow}")
                    result["mobile"] = _screenshot(
                        mobile,
                        "crispr-p0-mobile",
                        MOBILE_VIEWPORT,
                    )
                    _mark_phase(result, "final verification", process=active, port=port)
                    _close_page_cleanly(mobile, result, phase="final browser close")
                finally:
                    _mark_phase(result, "final browser close", process=active, port=port)
                    browser.close()
        except Exception as exc:
            result["first_blocker"] = f"{type(exc).__name__}: {exc}"
        finally:
            if active is not None:
                _mark_phase(result, "final process stop", process=active, port=port)
                _stop_server(active)
            result["process_cleanup_complete"] = all(
                process.poll() is not None for process in processes
            )
            result["port_cleanup_complete"] = _wait_port_free(port)
            _mark_phase(result, "final port release", port=port)

    result["browser_errors"] = browser_errors
    log_paths = [path for path in (first_log, second_log) if path.exists()]
    server_log_result = _classify_server_logs(log_paths, result)
    result.update(server_log_result)
    result["server_exception_count"] = result["unexpected_server_error_count"]
    if result["classification"] is None and result["websocket_error_count"] == 0:
        result["classification"] = "NO_WEBSOCKET_ERROR"
    if result["classification"] != EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE and result["websocket_error_count"]:
        result["first_blocker"] = result["first_blocker"] or (
            "WebSocketClosedError was not confined to deliberate post-success teardown"
        )
    if result["unexpected_server_error_count"]:
        result["first_blocker"] = result["first_blocker"] or "unexpected server errors were recorded"
    result["passed"] = _acceptance_passes(result)
    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
