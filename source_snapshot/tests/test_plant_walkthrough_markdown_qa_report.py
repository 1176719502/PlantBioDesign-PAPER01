from __future__ import annotations

from pathlib import Path

from services.plant_walkthrough_chain_runner import run_all_plant_walkthrough_chains
from services.plant_walkthrough_markdown_qa_report import (
    REPORT_KEYS,
    SECTION_ORDER,
    build_plant_walkthrough_markdown_qa_report,
)
from services.plant_walkthrough_validation_summary import build_plant_walkthrough_validation_summary


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
    "best",
}

UNSAFE_NON_SCAN_COPY = (
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "wet-lab ready",
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _walk_dicts(value: object) -> list[dict[str, object]]:
    dicts: list[dict[str, object]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            dicts.extend(_walk_dicts(nested))
    return dicts


def test_markdown_qa_report_has_stable_plain_shape_and_sections() -> None:
    report = build_plant_walkthrough_markdown_qa_report()

    assert list(report) == list(REPORT_KEYS)
    assert report["section_order"] == list(SECTION_ORDER)
    assert report["markdown_text"].startswith("# Plant Walkthrough QA Report")  # type: ignore[union-attr]
    assert len(report["fixture_summary_table"]) == 5  # type: ignore[arg-type]
    _assert_plain_data(report)


def test_report_contains_required_notices_and_fixture_summary_table() -> None:
    report = build_plant_walkthrough_markdown_qa_report()
    text = report["markdown_text"]

    assert "## Not Biological Validation Notice" in text  # type: ignore[operator]
    assert "workflow validation, not biological validation" in text  # type: ignore[operator]
    assert "## Documentation-Only Manual-Review Notice" in text  # type: ignore[operator]
    assert "| Fixture | Chain status | Route | Package status | Markdown |" in text  # type: ignore[operator]
    assert "rice_albumin_expression_review" in text  # type: ignore[operator]


def test_report_summarizes_chain_output_availability_and_gaps() -> None:
    report = build_plant_walkthrough_markdown_qa_report()

    availability = report["chain_output_availability"]
    gap_summary = report["gap_manual_review_summary"]
    assert availability["available_counts"]["route_draft"] == 5  # type: ignore[index]
    assert availability["available_counts"]["markdown_readback"] == 5  # type: ignore[index]
    assert gap_summary["total_missing_fields"] > 0  # type: ignore[index]
    assert gap_summary["total_unresolved_gaps"] > 0  # type: ignore[index]
    assert gap_summary["total_manual_review_items"] > 0  # type: ignore[index]


def test_report_preserves_boundary_and_blocked_claim_scan_summary() -> None:
    report = build_plant_walkthrough_markdown_qa_report()

    assert report["boundary_compliance_summary"]["non_compliant_rows"] == 0  # type: ignore[index]
    assert report["blocked_claim_scan_summary"]["scan_status"] == "review_passed"  # type: ignore[index]
    assert "not biological validation" in report["boundary_notice"]["notice"].casefold()  # type: ignore[index]


def test_report_accepts_explicit_summary_and_chain_outputs() -> None:
    outputs = run_all_plant_walkthrough_chains()[:2]
    summary = build_plant_walkthrough_validation_summary(outputs)
    report = build_plant_walkthrough_markdown_qa_report(summary, outputs)

    assert len(report["fixture_summary_table"]) == 2  # type: ignore[arg-type]
    assert report["chain_output_availability"]["available_counts"]["package_snapshot"] == 2  # type: ignore[index]


def test_report_output_is_deterministic() -> None:
    assert build_plant_walkthrough_markdown_qa_report() == build_plant_walkthrough_markdown_qa_report()


def test_no_unsafe_fields_or_product_claims_appear_in_report_outside_scan_terms() -> None:
    report = build_plant_walkthrough_markdown_qa_report()
    markdown_without_scan = report["markdown_text"].split("## Blocked Claim Scan Summary", 1)[0]
    report_without_scan = {
        key: value
        for key, value in report.items()
        if key not in {"blocked_claim_scan_summary", "markdown_text", "markdown_lines"}
    }
    text = f"{markdown_without_scan} {report_without_scan}".casefold()

    for item in _walk_dicts(report):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)
    for unsafe in UNSAFE_NON_SCAN_COPY:
        assert unsafe not in text


def test_no_ui_db_import_export_package_export_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_walkthrough_markdown_qa_report.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "package_export_service",
        "expression_wizard",
        "component_library_mutation",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
        "write_text",
        "open(",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source
