from __future__ import annotations

import re
from pathlib import Path

from core import expression_frame_builder as frame_builder

ROOT = Path(__file__).resolve().parents[1]

FORMAL_PAGE_CONSTANTS = (
    "PAGE_PROJECT_HOME",
    "PAGE_DESIGN_WORKSPACE",
    "PAGE_RESULTS_EXPORT",
    "PAGE_PLANT_LIBRARY",
    "PAGE_SEQUENCE_TOOLBOX",
)
CRISPR_PAGE_CONSTANT = "PAGE_CRISPR_WORKFLOW"
AGENT_PAGE_CONSTANT = "PAGE_AGENT_WORKSPACE"
SIDEBAR_PAGE_CONSTANTS = (
    "PAGE_PROJECT_HOME",
    "PAGE_AGENT_WORKSPACE",
    "PAGE_DESIGN_WORKSPACE",
    "PAGE_PLANT_LIBRARY",
    "PAGE_SEQUENCE_TOOLBOX",
    "PAGE_CRISPR_WORKFLOW",
)


def test_sidebar_includes_crispr_and_hides_unavailable_analysis_tools() -> None:
    content = (ROOT / "app.py").read_text(encoding="utf-8")

    all_pages_block = content.split("_ALL_PAGES = [", 1)[1].split("]", 1)[0]
    registered_pages = tuple(re.findall(r"\bPAGE_[A-Z_]+\b", all_pages_block))
    assert registered_pages == (*FORMAL_PAGE_CONSTANTS, CRISPR_PAGE_CONSTANT, AGENT_PAGE_CONSTANT)
    assert tuple(page for page in registered_pages if page not in {CRISPR_PAGE_CONSTANT, AGENT_PAGE_CONSTANT}) == FORMAL_PAGE_CONSTANTS

    primary_pages_block = content.split("_PRIMARY_NAV_PAGES = (", 1)[1].split(")", 1)[0]
    assert tuple(re.findall(r"\bPAGE_[A-Z_]+\b", primary_pages_block)) == SIDEBAR_PAGE_CONSTANTS
    assert "for _page in _PRIMARY_NAV_PAGES:" in content
    assert "PAGE_CRISPR_WORKFLOW: PAGE_DESIGN_WORKSPACE" not in content
    assert 'key="formal_open_crispr_product_workflow"' not in content
    assert "基因编辑" in content
    for hidden_route in ("Structure Analysis", "Lab Tools", "AI Literature Research", "Module Overview"):
        assert hidden_route not in all_pages_block
        assert f'page == "{hidden_route}"' not in content

    registry = (ROOT / "core" / "module_registry.py").read_text(encoding="utf-8")
    assert '"route_key": "Structure Analysis"' in registry
    assert '"route_key": "Lab Tools"' in registry


def test_module_registry_codon_page_uses_preview_wording() -> None:
    registry_source = (ROOT / "core" / "module_registry.py").read_text(encoding="utf-8")

    assert "codon usage context" in registry_source.lower()
    assert "Optimize CDS sequences for host codon preference" not in registry_source


def test_runtime_host_rules_remove_positive_claim_wording() -> None:
    disallowed = (
        "yield",
        "opti" + "mization",
        "preferred",
        "recommended",
        "best",
        "vali" + "dated",
        "ready",
    )

    for host in frame_builder.list_supported_hosts():
        rules = frame_builder.get_host_rules(host)
        for key in ("promoter_note", "rbs_note", "terminator_note", "vector_suggestion"):
            value = str(rules.get(key) or "").lower()
            assert not any(term in value for term in disallowed), f"{host} {key}: {value}"


def test_step2_host_note_keeps_documentation_framing() -> None:
    rules = frame_builder.get_host_rules("Tobacco (N. benthamiana)")
    note = str(rules.get("promoter_note") or "").lower()

    assert "documented" in note or "documentation" in note
    assert "preferred" not in note
    assert "yield" not in note
