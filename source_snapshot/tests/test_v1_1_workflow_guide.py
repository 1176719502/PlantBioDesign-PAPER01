from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from views.Homepage import (
    PLANT_PROJECT_TYPE_BOUNDARY_COPY,
    PLANT_PROJECT_TYPES,
    PRODUCT_WORKFLOW_BOUNDARY_COPY,
    PRODUCT_WORKFLOW_STEPS,
    PROJECT_REVIEW_WORKFLOW_BOUNDARY_COPY,
    PROJECT_REVIEW_WORKFLOW_STEPS,
    WORKFLOW_GUIDE_BOUNDARY_COPY,
    WORKFLOW_GUIDE_RELATIONSHIP_COPY,
    WORKFLOW_GUIDE_STEPS,
    _FEATURED_ID,
    _plant_project_types,
    _product_workflow_steps,
    _project_review_workflow_steps,
    _render_documentation_boundary_notice,
    _render_plant_project_type_selection,
    _render_product_workflow,
    _render_product_workflow_step,
    _render_project_review_workflow,
    _render_project_review_workflow_step,
    _render_workflow_guide,
    _render_workflow_step,
    _workflow_steps,
)


FORBIDDEN_WORKFLOW_GUIDE_TERMS = [
    "successful " + "import",
    "project " + "imported",
    "ready for " + "execution",
    "experiment" + "-ready",
    "production" + "-ready",
    "validated " + "construct",
    "optimized " + "pathway",
    "yield " + "prediction",
    "lab" + "-ready",
    "wet-lab " + "ready",
    "proven " + "construct",
    "validated " + "pathway",
]

REQUIRED_SAFE_WORKFLOW_TERMS = [
    "documentation-only",
    "local project workspace",
    "design record",
    "documentation snapshot",
    "import preview",
    "export package",
    "duplicate guard",
    "traceability",
]


def _homepage_text() -> str:
    homepage_path = Path(ROOT) / "views" / "Homepage.py"
    return homepage_path.read_text(encoding="utf-8")


def _workflow_guide_text() -> str:
    parts = [WORKFLOW_GUIDE_BOUNDARY_COPY, *WORKFLOW_GUIDE_RELATIONSHIP_COPY]
    for step in WORKFLOW_GUIDE_STEPS:
        parts.extend([step["title"], step["description"], step["button"], step["page_key"]])
    return "\n".join(parts)


def _plant_project_type_text() -> str:
    parts = [PLANT_PROJECT_TYPE_BOUNDARY_COPY]
    for project_type in PLANT_PROJECT_TYPES:
        parts.extend(
            [
                project_type["title"],
                project_type["examples"],
                project_type["status"],
                project_type["cta"],
                project_type["readback"],
            ]
        )
    return "\n".join(parts)


def _product_workflow_text() -> str:
    parts = [PRODUCT_WORKFLOW_BOUNDARY_COPY]
    for step in PRODUCT_WORKFLOW_STEPS:
        parts.extend([step["phase"], step["title"], step["description"], step["button"], step["page_key"]])
    return "\n".join(parts)


def _project_review_workflow_text() -> str:
    parts = [PROJECT_REVIEW_WORKFLOW_BOUNDARY_COPY]
    for step in PROJECT_REVIEW_WORKFLOW_STEPS:
        parts.extend([step["phase"], step["title"], step["description"], step["button"], step["page_key"]])
    return "\n".join(parts)


def test_workflow_guide_copy_exists_on_homepage() -> None:
    content = _homepage_text()

    assert "BioDesign Studio Plant" in content
    assert "Plant Synthetic Biology Design Review Workspace" in content
    assert "pre-experiment design review" in content
    assert "Workflow Guide" in content
    assert "Plant Project Type Selection" in content
    assert "Expression vector construction preparation map" in content
    assert "Expression Vector Design Package workflow" in content
    assert "Advanced existing workflow map" in content
    assert "Compact plant project type readback" in content
    assert "WORKFLOW_GUIDE_STEPS" in content
    assert "WORKFLOW_GUIDE_BOUNDARY_COPY" in content
    assert "PLANT_PROJECT_TYPES" in content
    assert "PLANT_PROJECT_TYPE_BOUNDARY_COPY" in content
    assert "PRODUCT_WORKFLOW_STEPS" in content
    assert "PROJECT_REVIEW_WORKFLOW_STEPS" in content
    assert "_render_workflow_guide(change_page)" in content
    assert "_render_plant_project_type_selection(change_page)" in content
    assert content.index("_render_plant_project_type_selection(change_page)") < content.index(
        "_render_workflow_guide(change_page)"
    )
    assert "Existing documentation workflow modules" in content
    assert "_render_project_review_workflow(change_page)" in content
    assert "_render_product_workflow(change_page)" in content


def test_workflow_guide_is_split_into_maintainable_helpers() -> None:
    content = _homepage_text()

    assert callable(_render_workflow_guide)
    assert callable(_render_workflow_step)
    assert callable(_render_documentation_boundary_notice)
    assert callable(_workflow_steps)
    assert callable(_render_plant_project_type_selection)
    assert callable(_plant_project_types)
    assert callable(_render_product_workflow)
    assert callable(_render_product_workflow_step)
    assert callable(_product_workflow_steps)
    assert callable(_render_project_review_workflow)
    assert callable(_render_project_review_workflow_step)
    assert callable(_project_review_workflow_steps)
    assert "def _workflow_steps()" in content
    assert "def _render_workflow_step(" in content
    assert "def _render_documentation_boundary_notice()" in content
    assert "def _plant_project_types()" in content
    assert "def _render_plant_project_type_selection(" in content
    assert "def _product_workflow_steps()" in content
    assert "def _render_product_workflow(" in content
    assert "def _project_review_workflow_steps()" in content
    assert "def _render_project_review_workflow(" in content
    assert _workflow_steps() == WORKFLOW_GUIDE_STEPS
    assert _plant_project_types() == PLANT_PROJECT_TYPES
    assert _product_workflow_steps() == PRODUCT_WORKFLOW_STEPS
    assert _project_review_workflow_steps() == PROJECT_REVIEW_WORKFLOW_STEPS


def test_plant_project_type_selection_shows_three_plant_only_options() -> None:
    guide_text = _plant_project_type_text()
    titles = [project_type["title"] for project_type in PLANT_PROJECT_TYPES]
    statuses = [project_type["status"] for project_type in PLANT_PROJECT_TYPES]

    assert titles == [
        "Plant recombinant protein / molecular farming",
        "Plant metabolic product / quality improvement",
        "Plant trait / gene-function expression review",
    ]
    assert statuses == [
        "Current first MVP",
        "Planned / read-only",
        "Planned / read-only",
    ]
    assert "Start first MVP review" in guide_text
    assert "Read-only direction preview" in guide_text
    assert "Start first MVP review" in _homepage_text()
    assert "change_page(\"Expression Wizard\")" in _homepage_text()
    assert "rice albumin" in guide_text
    assert "plant-made antigen" in guide_text
    assert "industrial enzyme" in guide_text
    assert "artemisinin precursor" in guide_text
    assert "carotenoids" in guide_text
    assert "anthocyanins" in guide_text
    assert "healthy sugar/sweetness traits" in guide_text
    assert "stress tolerance" in guide_text
    assert "disease resistance" in guide_text
    assert "tissue-specific expression" in guide_text
    assert "inducible expression" in guide_text
    assert "metabolic-product workflow behavior is implemented" in guide_text
    assert "trait or gene-function workflow behavior is implemented" in guide_text
    assert "bacteria" not in guide_text.lower()
    assert "yeast" not in guide_text.lower()
    assert "mammalian" not in guide_text.lower()


def test_plant_project_type_selection_states_documentation_only_boundaries() -> None:
    guide_text = _plant_project_type_text()

    assert "Documentation-only pre-experiment design review for plant expression construct preparation" in guide_text
    assert "provenance review, gap identification, and report handoff" in guide_text
    assert "first MVP is plant recombinant protein / molecular farming" in guide_text
    assert "Planned workflows are read-only direction previews" in guide_text
    assert "no protocols" in guide_text
    assert "construct-readiness certification" in guide_text
    assert "sequence optimization output" in guide_text
    assert "plant-line proof claims" in guide_text
    assert "yield estimates are provided" in guide_text
    assert "Expression Wizard and handoff review surfaces" in guide_text

    for forbidden in FORBIDDEN_WORKFLOW_GUIDE_TERMS:
        assert forbidden not in guide_text.lower()


def test_homepage_plant_first_copy_deemphasizes_existing_expression_workflows() -> None:
    content = _homepage_text()
    render_body = content[content.index("def render(change_page)") :]

    assert render_body.index("BioDesign Studio Plant") < render_body.index(
        "_render_plant_project_type_selection(change_page)"
    )
    assert render_body.index("_render_plant_project_type_selection(change_page)") < render_body.index(
        "Existing documentation workflow modules"
    )
    assert render_body.index("Existing documentation workflow modules") < render_body.index(
        "Advanced existing workflow map"
    )
    assert render_body.index("Advanced existing workflow map") < render_body.index(
        "_render_workflow_guide(change_page)"
    )
    assert render_body.index("Advanced existing workflow map") < render_body.index(
        "_render_project_review_workflow(change_page)"
    )
    assert render_body.index("Advanced existing workflow map") < render_body.index(
        "_render_product_workflow(change_page)"
    )
    assert 'st.expander("Advanced existing workflow map", expanded=False)' in content
    assert 'st.expander("Existing documentation workflow modules", expanded=False)' in content
    assert render_body.index('st.expander("Existing documentation workflow modules", expanded=False)') < render_body.index(
        "Main Workflow"
    )


def test_project_review_workflow_shows_expression_vector_package_story() -> None:
    guide_text = _project_review_workflow_text()
    phases = [step["phase"] for step in PROJECT_REVIEW_WORKFLOW_STEPS]
    titles = [step["title"] for step in PROJECT_REVIEW_WORKFLOW_STEPS]
    page_keys = [step["page_key"] for step in PROJECT_REVIEW_WORKFLOW_STEPS]

    assert phases == ["Record", "Context", "Sources", "Review", "Package"]
    assert titles == [
        "Create an expression design record",
        "Attach project review context when needed",
        "Review component source context",
        "Inspect gaps and follow-up notes",
        "Prepare the design package readback",
    ]
    assert page_keys == [
        "Expression Wizard",
        "Pathway Projects",
        "Data",
        "Pathway Workspace",
        "Pathway Workspace",
    ]
    assert "Expression Vector Design Package workflow" in guide_text
    assert "single-gene or single-protein design preparation record" in guide_text
    assert "project grouping, linked notes, and traceability" in guide_text
    assert "Component Library and Expression Constructs" in guide_text
    assert "Project Review Report and Project Quality Dashboard" in guide_text
    assert "documentation snapshots, report identity, export package review, and import preview review" in guide_text
    assert "local documentation review only" in guide_text
    for forbidden in FORBIDDEN_WORKFLOW_GUIDE_TERMS:
        assert forbidden not in guide_text.lower()


def test_product_workflow_shows_expression_vector_preparation_map() -> None:
    guide_text = _product_workflow_text()
    phases = [step["phase"] for step in PRODUCT_WORKFLOW_STEPS]
    titles = [step["title"] for step in PRODUCT_WORKFLOW_STEPS]
    page_keys = [step["page_key"] for step in PRODUCT_WORKFLOW_STEPS]

    assert phases == [
        "Target",
        "Source",
        "Host",
        "Cassette",
        "Vector",
        "Sources",
        "Check",
        "Gaps",
        "Package",
    ]
    assert titles == [
        "Target Sequence",
        "Source / Provenance",
        "Host System",
        "Expression Cassette",
        "Vector / Backbone",
        "Component Sources",
        "Sequence Check",
        "Gap Review",
        "Expression Vector Design Package",
    ]
    assert page_keys == [
        "Expression Wizard",
        "Expression Wizard",
        "Expression Wizard",
        "Expression Wizard",
        "Expression Constructs",
        "Data",
        "Expression Wizard",
        "Pathway Workspace",
        "Pathway Workspace",
    ]
    assert "Target Sequence -> Source/Provenance -> Host System" in guide_text
    assert "Expression Cassette -> Vector/Backbone -> Component Sources" in guide_text
    assert "Sequence Check -> Gap Review -> Expression Vector Design Package" in guide_text
    assert "target gene, CDS, or protein-linked sequence record" in guide_text
    assert "sequence type, source notes, provenance context" in guide_text
    assert "promoter, 5' UTR/RBS/Kozak" in guide_text
    assert "backbone name, marker, origin or integration context" in guide_text
    assert "read-only codon usage context inside the expression-vector review path" in guide_text
    assert "manual follow-up" in guide_text
    assert "QR/MD5 identity" in guide_text
    assert "does not add generated vector sequences" in guide_text
    assert "rewritten CDS output" in guide_text
    assert "wet-lab procedure drafting" in guide_text
    assert "AI Literature Research" not in guide_text


def test_workflow_guide_contains_recommended_flow_items() -> None:
    titles = [step["title"] for step in WORKFLOW_GUIDE_STEPS]
    guide_text = _workflow_guide_text()

    assert titles == [
        "Expression Wizard",
        "Expression Constructs",
        "Handoff Review",
        "Component Library",
        "Pathway Projects",
        "Pathway Workspace",
        "Project Outputs",
        "Design Library",
        "Duplicate Guard",
    ]
    assert "Primary path for one expression vector construction design preparation record" in guide_text
    assert "documentation gaps, follow-up notes, traceability rows, and expression-vector package readback" in guide_text
    assert "component source/provenance context" in guide_text
    assert "construct, cassette, cassette-part, and linked gene records" in guide_text
    assert "optional project grouping" in guide_text
    assert "documentation gaps, and traceability notes" in guide_text
    assert "Review documentation snapshots, reports, export package review, and import preview review" in guide_text
    assert "View and reopen saved Expression Wizard design snapshots" in guide_text
    assert "Check for existing documentation projects" in guide_text


def test_homepage_featured_main_workflow_points_to_expression_wizard() -> None:
    content = _homepage_text()

    assert _FEATURED_ID == "expression_wizard"
    assert '"id": "expression_wizard"' in (Path(ROOT) / "core" / "module_registry.py").read_text(encoding="utf-8")
    assert 'f"Open {m[\'name\']}' in content
    assert 'key="tile_featured"' in content


def test_workflow_guide_explains_page_relationships_and_snapshot_types() -> None:
    guide_text = _workflow_guide_text()

    assert "Start here: Expression Wizard is the primary single-gene / single-protein expression vector design preparation path" in guide_text
    assert "Use Component Library as a supporting source/provenance library" in guide_text
    assert "Sequence and codon checks are supporting read-only review context" in guide_text
    assert "not standalone first-path choices or optimization output" in guide_text
    assert "Use Pathway Projects and Pathway Workspace when the expression vector record needs project grouping" in guide_text
    assert "Project Outputs is the place for documentation snapshots, reports, documentation-only export package review, and import preview review" in guide_text


def test_workflow_guide_states_documentation_only_boundary() -> None:
    guide_text = _workflow_guide_text()

    assert "documentation-only" in guide_text
    assert "expression vector construction design record preparation" in guide_text
    assert "source/provenance review" in guide_text
    assert "documentation snapshots" in guide_text
    assert "import preview" in guide_text
    assert "export package" in guide_text
    assert "duplicate guard" in guide_text
    assert "traceability" in guide_text
    assert "does not represent experimental success" in guide_text
    assert "does not predict production output" in guide_text
    assert "does not prove experimental readiness" in guide_text
    assert "does not make production-level conclusions" in guide_text


def test_workflow_guide_keeps_required_safe_terms_visible() -> None:
    guide_text = _workflow_guide_text().lower()

    for required in REQUIRED_SAFE_WORKFLOW_TERMS:
        assert required in guide_text


def test_workflow_guide_has_navigation_targets_for_existing_pages() -> None:
    page_keys = [step["page_key"] for step in WORKFLOW_GUIDE_STEPS]

    assert page_keys == [
        "Expression Wizard",
        "Expression Constructs",
        "Pathway Workspace",
        "Data",
        "Pathway Projects",
        "Pathway Workspace",
        "Pathway Workspace",
        "Design Library",
        "Pathway Projects",
    ]
    assert all(step["button"].startswith("Open ") for step in WORKFLOW_GUIDE_STEPS)


def test_workflow_guide_does_not_use_forbidden_terms() -> None:
    guide_text = _workflow_guide_text().lower()

    for forbidden in FORBIDDEN_WORKFLOW_GUIDE_TERMS:
        assert forbidden not in guide_text


def test_user_visible_v2_copy_does_not_use_forbidden_terms() -> None:
    user_visible_paths = [
        Path(ROOT) / "views" / "Homepage.py",
        Path(ROOT) / "views" / "Dashboard.py",
        Path(ROOT) / "locales" / "en.py",
    ]
    visible_copy = "\n".join(path.read_text(encoding="utf-8") for path in user_visible_paths).lower()

    for forbidden in FORBIDDEN_WORKFLOW_GUIDE_TERMS:
        assert forbidden not in visible_copy
