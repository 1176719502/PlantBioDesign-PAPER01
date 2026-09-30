from __future__ import annotations

import ast
from pathlib import Path
import time

import pytest

from scripts.acceptance.run_formal_crispr_p0_acceptance import (
    EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE,
    REQUIRED_PHASES,
    _acceptance_passes,
    _arm_streamlit_rerun_acknowledgement,
    _classify_server_logs,
    _wait_for_streamlit_rerun_acknowledgement,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acceptance" / "run_formal_crispr_p0_acceptance.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")


def test_acceptance_script_is_importable_and_uses_formal_entrypoint() -> None:
    ast.parse(SOURCE)
    assert '"entrypoint": "app.py"' in SOURCE
    assert "_start_server(" in SOURCE
    assert '"route": "CRISPR V1 Workflow"' in SOURCE
    assert "Official R9" not in SOURCE


def test_acceptance_requires_exact_desktop_and_mobile_viewports() -> None:
    assert 'DESKTOP_VIEWPORT = {"width": 1440, "height": 900}' in SOURCE
    assert 'MOBILE_VIEWPORT = {"width": 390, "height": 844}' in SOURCE
    assert '== "1440x900"' in SOURCE
    assert '== "390x844"' in SOURCE
    assert "document.documentElement.scrollWidth - window.innerWidth" in SOURCE
    assert "_png_dimensions(path) != viewport" in SOURCE


def test_acceptance_covers_blank_compute_selection_export_save_and_cold_reopen() -> None:
    for required in (
        "_assert_blank_direct_entry",
        "枚举确定性候选",
        "选择此 guide",
        "确认此 guide 选择",
        "下载 CRISPR JSON",
        "保存 CRISPR 审阅记录",
        "验证并重新打开",
        "项目草稿已保存，可从项目中心重新打开。",
        'has_text="高级 / Reproducibility"',
        'f"{checkpoint}_manual_review_keys"',
        "cold-reopened aggregate JSON bytes changed",
        "formal port was not released before cold restart",
    ):
        assert required in SOURCE


def test_acceptance_isolated_roots_and_fail_closed_result_are_explicit() -> None:
    assert "TemporaryDirectory" in SOURCE
    assert 'environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"]' not in SOURCE
    assert 'os.environ["BIODESIGN_DB_PATH"]' in SOURCE
    assert '"first_blocker": None' in SOURCE
    assert 'return 0 if result["passed"] else 1' in SOURCE
    assert "WEBSOCKET_CLOSED_ERROR_MARKER" in SOURCE


def test_crispr_rerun_acknowledgement_observes_stale_then_fresh_dom() -> None:
    """Exercise the acceptance synchronization against a real DOM mutation."""

    playwright_api = pytest.importorskip("playwright.sync_api")
    try:
        with playwright_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content("<main id='root'></main>")
                _arm_streamlit_rerun_acknowledgement(page)
                page.evaluate(
                    """() => {
                        const stale = document.createElement('div');
                        stale.dataset.stale = 'true';
                        document.querySelector('#root').append(stale);
                        stale.remove();
                    }"""
                )
                _wait_for_streamlit_rerun_acknowledgement(page)
            finally:
                browser.close()
    except Exception as exc:
        if exc.__class__.__name__ in {"Error", "TargetClosedError"}:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        raise


def _phase_markers(*phases: str, timestamp: float) -> list[dict[str, object]]:
    return [
        {"phase": phase, "wall_time": timestamp + index}
        for index, phase in enumerate(phases)
    ]


def _passing_result() -> dict[str, object]:
    now = time.time()
    return {
        "first_blocker": None,
        "browser_errors": [],
        "server_exception_count": 0,
        "process_cleanup_complete": True,
        "port_cleanup_complete": True,
        "websocket_error_count": 0,
        "benign_websocket_events": [],
        "direct_compute_export_without_project": True,
        "desktop": {"viewport": "1440x900"},
        "mobile": {"viewport": "390x844"},
        "phase_markers": _phase_markers(*REQUIRED_PHASES, timestamp=now),
    }


def test_websocket_policy_accepts_only_post_success_deliberate_teardown(tmp_path: Path) -> None:
    event_time = time.mktime(time.strptime("2026-08-24 14:43:07", "%Y-%m-%d %H:%M:%S"))
    log = tmp_path / "streamlit.log"
    log.write_text(
        "2026-08-24 14:43:07 | ERROR | asyncio | Task exception was never retrieved\n"
        "future: exception=WebSocketClosedError()\n"
        "tornado.websocket.WebSocketClosedError\n",
        encoding="utf-8",
    )
    result = {
        "phase_markers": _phase_markers(
            "crispr workflow completion", "browser/page close", timestamp=event_time - 2
        )
    }
    classified = _classify_server_logs([log], result)
    assert classified["websocket_error_count"] == 1
    assert classified["classification"] == EXPECTED_POST_SUCCESS_TEARDOWN_CLOSE
    assert len(classified["benign_websocket_events"]) == 1


def test_websocket_before_success_fails_closed(tmp_path: Path) -> None:
    event_time = time.mktime(time.strptime("2026-08-24 14:43:07", "%Y-%m-%d %H:%M:%S"))
    log = tmp_path / "streamlit.log"
    log.write_text(
        "2026-08-24 14:43:07 | ERROR | asyncio | Task exception was never retrieved\n"
        "tornado.websocket.WebSocketClosedError\n",
        encoding="utf-8",
    )
    result = {"phase_markers": _phase_markers("browser/page close", timestamp=event_time)}
    classified = _classify_server_logs([log], result)
    assert classified["classification"] == "PRODUCT_RUNTIME_DEFECT"
    assert classified["misphased_websocket_events"]


def test_unrelated_server_error_fails_even_during_teardown(tmp_path: Path) -> None:
    event_time = time.mktime(time.strptime("2026-08-24 14:43:07", "%Y-%m-%d %H:%M:%S"))
    log = tmp_path / "streamlit.log"
    log.write_text(
        "2026-08-24 14:43:07 | ERROR | app | unrelated failure\n"
        "Traceback (most recent call last):\n"
        "tornado.iostream.StreamClosedError: unrelated\n",
        encoding="utf-8",
    )
    result = {"phase_markers": _phase_markers(
        "crispr workflow completion", "browser/page close", timestamp=event_time - 2
    )}
    classified = _classify_server_logs([log], result)
    assert classified["unexpected_server_error_count"] == 1
    assert classified["classification"] is None


def test_teardown_contract_fails_for_process_port_or_cold_reopen_gaps() -> None:
    for field in ("process_cleanup_complete", "port_cleanup_complete"):
        result = _passing_result()
        result[field] = False
        assert not _acceptance_passes(result)

    result = _passing_result()
    result["phase_markers"] = [
        marker for marker in result["phase_markers"] if marker["phase"] != "cold reopen"
    ]
    assert not _acceptance_passes(result)
