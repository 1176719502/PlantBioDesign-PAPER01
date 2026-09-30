from __future__ import annotations

import importlib
import inspect

from services import target_design_router as router
from services import target_design_router_preview as previewer
from services import target_design_router_preview_report as preview_report
from services.project_review_report_service import build_project_review_report
from services.project_review_target_preview_adapter import (
    EMPTY_STATE_MESSAGE,
    build_project_review_target_preview_section,
)


FORBIDDEN_POSITIVE_CLAIMS = [
    "recommend" + "ation",
    "optimization",
    "prediction",
    "production readiness",
    "wet-lab readiness",
    "experimental success",
    "validated design",
    "guaranteed " + "expression",
    "yield",
    "purity",
    "activity",
    "therapeutic " + "success",
    "save target preview",
    "create construct",
    "create cassette",
    "export target preview",
    "download target preview",
    "ready for " + "execution",
    "experiment-" + "ready",
    "production-" + "ready",
    "validated " + "construct",
    "optimized " + "pathway",
    "yield " + "prediction",
]


def _target_preview_markdown() -> str:
    route = router.route_target_design(
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        route_hint="secreted protein",
        source_hint="manual source note",
    )
    preview = previewer.build_target_design_preview(route)
    return preview_report.format_target_design_preview_markdown(preview)


def _safe_scan_text(text: str) -> str:
    return (
        text.lower()
        .replace("not saved as construct/cassette records", "")
        .replace("not experimental validation", "")
        .replace("not production, yield, or experimental validation", "")
        .replace("no yield, purity, activity, therapeutic, production, or success claim is made", "")
    )


def test_adapter_renders_target_preview_markdown_report_section() -> None:
    target_markdown = _target_preview_markdown()

    section = build_project_review_target_preview_section(target_markdown)
    rendered = section.as_markdown()

    assert section.status == "ATTACHED_READ_ONLY"
    assert section.has_markdown_readback is True
    assert "## Target Design Preview" in rendered
    assert "Documentation-only route preview" in rendered
    assert "Read-only report section" in rendered
    assert "Not saved as construct/cassette records" in rendered
    assert "Manual review and source confirmation required" in rendered
    assert "Not experimental validation" in rendered
    assert "# Target Design Preview" in rendered
    assert "HSA protein expression construct draft" in rendered
    assert "manual source note" in rendered


def test_adapter_empty_state_is_safe_when_no_markdown_is_supplied() -> None:
    section = build_project_review_target_preview_section("")
    rendered = section.as_markdown()

    assert section.status == "NOT_ATTACHED"
    assert section.has_markdown_readback is False
    assert EMPTY_STATE_MESSAGE in rendered
    assert "Create or copy the read-only preview from Expression Constructs before manual review." in rendered
    assert "failure" not in rendered.lower()
    assert "ready" not in rendered.lower()


def test_adapter_has_no_streamlit_dependency() -> None:
    source = inspect.getsource(importlib.import_module("services.project_review_target_preview_adapter"))

    assert "streamlit" not in source.lower()


def test_adapter_does_not_expose_save_create_export_or_download_language() -> None:
    rendered = build_project_review_target_preview_section(_target_preview_markdown()).as_markdown().lower()

    for forbidden in [
        "save target preview",
        "save preview",
        "create construct",
        "create cassette",
        "export target preview",
        "download target preview",
        "download button",
    ]:
        assert forbidden not in rendered
    assert "not saved as construct/cassette records" in rendered


def test_adapter_output_does_not_contain_forbidden_positive_claims() -> None:
    samples = [
        build_project_review_target_preview_section(_target_preview_markdown()).as_markdown(),
        build_project_review_target_preview_section(None).as_markdown(),
    ]
    combined = _safe_scan_text("\n".join(samples))

    assert [phrase for phrase in FORBIDDEN_POSITIVE_CLAIMS if phrase in combined] == []


def test_project_review_report_can_include_target_preview_section_without_persisting_it(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )

    target_markdown = _target_preview_markdown()
    report = build_project_review_report(
        {"id": 178, "name": "R178 preview report"},
        target_preview_markdown=target_markdown,
    )

    section = report["target_design_preview_report_section"]
    assert section["status"] == "ATTACHED_READ_ONLY"
    assert section["has_markdown_readback"] is True
    assert section["markdown_readback"] == target_markdown.strip()
    assert section["empty_state_message"] == ""
    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "## Target Design Preview" in markdown
        assert "Documentation-only route preview" in markdown
        assert "Read-only report section" in markdown
        assert "Not saved as construct/cassette records" in markdown
        assert "Manual review and source confirmation required" in markdown
        assert "Not experimental validation" in markdown
        assert "HSA protein expression construct draft" in markdown


def test_project_review_report_includes_safe_target_preview_empty_state(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )

    report = build_project_review_report({"id": 179, "name": "R178 empty report"})
    section = report["target_design_preview_report_section"]

    assert section["status"] == "NOT_ATTACHED"
    assert section["has_markdown_readback"] is False
    assert section["markdown_readback"] == ""
    assert EMPTY_STATE_MESSAGE in report["markdown"]
    assert EMPTY_STATE_MESSAGE in report["detailed_documentation_report_draft"]["markdown"]
