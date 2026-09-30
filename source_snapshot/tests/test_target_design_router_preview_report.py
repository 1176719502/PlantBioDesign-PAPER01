from __future__ import annotations

import importlib
import inspect
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import target_design_router as router
from services import target_design_router_preview as previewer
from services import target_design_router_preview_report as report


FORBIDDEN_POSITIVE_CLAIMS = [
    "recommend" + "ation",
    "recommend" + "ed",
    "optimization",
    "prediction",
    "production readiness",
    "wet-lab readiness",
    "experimental success",
    "validated design",
    "guaranteed expression",
    "guaranteed activity",
    "therapeutic success",
    "ready for " + "execution",
    "ready for experiment",
    "ready for production",
    "validated " + "construct",
    "optimized " + "pathway",
    "yield " + "prediction",
]


def _markdown_for(**kwargs: object) -> str:
    preview = previewer.build_target_design_preview(router.route_target_design(**kwargs))
    return report.format_target_design_preview_markdown(preview)


def test_report_returns_deterministic_markdown_for_repeated_calls() -> None:
    kwargs = {
        "target_name": "DHAA",
        "target_type": "pathway",
        "host_category": "plant",
        "specific_host": "Nicotiana benthamiana",
        "source_hint": "project source note",
    }

    assert _markdown_for(**kwargs) == _markdown_for(**kwargs)


def test_report_includes_stable_headings() -> None:
    markdown = _markdown_for(target_name="GOI", target_type="gene", host_category="plant")

    for heading in report.REPORT_HEADINGS:
        assert heading in markdown
    assert markdown.startswith("# Target Design Preview\n")


def test_hsa_report_includes_protein_construct_draft_and_source_review_wording() -> None:
    markdown = _markdown_for(
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        expression_purpose="protein expression",
        route_hint="secreted protein",
        source_hint="local source note",
    )

    assert "HSA protein expression construct draft" in markdown
    assert "secreted_protein_expression" in markdown
    assert "HSA CDS source/provenance" in markdown
    assert "source required" in markdown
    assert "manual confirmation required" in markdown
    assert "documentation-only" in markdown.lower()


def test_artemisinin_report_includes_gene_slots_and_cassette_slot_structure() -> None:
    markdown = _markdown_for(
        target_name="artemisinin precursor",
        target_type="pathway",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
    )

    for gene in ["ADS", "CYP71AV1", "CPR", "ADH1", "DBR2", "ALDH1"]:
        assert gene in markdown
        assert f"{gene} cassette draft" in markdown
    assert "promoter" in markdown
    assert "CDS" in markdown
    assert "terminator" in markdown
    assert "promoter_choices" in markdown
    assert "CDS_sources" in markdown
    assert "source_or_reference_confirmation" in markdown
    assert "documentation-only pathway construct draft" in markdown
    assert "not production, yield, or experimental validation" in markdown


def test_sugarcane_report_shows_target_clarification_without_ready_cassette_claim() -> None:
    markdown = _markdown_for(
        target_name="sugarcane healthy sugar",
        target_type="trait",
        host_category="plant",
        specific_host="sugarcane",
    )

    assert "needs_target_clarification" in markdown
    assert "Needs target clarification" in markdown
    assert "No cassette slots are available until the route is clarified" in markdown
    assert "remain target-clarification previews" in markdown
    assert "this empty section is not a complete design" in markdown
    assert "sweet protein expression" in markdown
    assert "rare sugar enzyme expression" in markdown
    assert "steviol glycoside pathway" in markdown
    assert "sugar metabolism modification" in markdown
    assert "cassette draft |" not in markdown
    assert "Ready for manual design review" not in markdown


def test_unknown_target_report_is_safe_and_unresolved() -> None:
    markdown = _markdown_for(target_name="mystery target")

    assert "Unresolved target" not in markdown
    assert "mystery target" in markdown
    assert "unresolved_target" in markdown
    assert "needs_target_clarification" in markdown
    assert "No gene slots are available because target clarification is required" in markdown
    assert "No cassette slots are available until the route is clarified" in markdown
    assert "documentation-only" in markdown.lower()


def test_report_has_no_streamlit_dependency() -> None:
    source = inspect.getsource(importlib.import_module("services.target_design_router_preview_report"))

    assert "streamlit" not in source.lower()


def test_report_markdown_does_not_include_forbidden_positive_claims() -> None:
    markdown_samples = [
        _markdown_for(target_name="HSA", target_type="protein", route_hint="secreted protein"),
        _markdown_for(target_name="GOI", target_type="gene", host_category="plant"),
        _markdown_for(target_name="artemisinic acid"),
        _markdown_for(target_name="healthy sugar in sugarcane", target_type="trait"),
        _markdown_for(target_name="mystery target"),
    ]
    combined = "\n".join(markdown_samples).lower()
    combined = combined.replace("not production, yield, or experimental validation", "")
    combined = combined.replace("not experimental validation", "")

    assert [phrase for phrase in FORBIDDEN_POSITIVE_CLAIMS if phrase in combined] == []


def test_report_normalizes_generated_boundary_terms_without_changing_router_payload() -> None:
    preview = previewer.build_target_design_preview(
        router.route_target_design(target_name="GOI", target_type="gene", host_category="plant")
    )
    preview["review_notes"] = ["Host compatibility note from generated readback."]

    markdown = report.format_target_design_preview_markdown(preview)

    assert preview["review_notes"] == ["Host compatibility note from generated readback."]
    assert "Host compatibility" not in markdown
    assert "host/context documentation" in markdown
