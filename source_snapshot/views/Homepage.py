"""views/Homepage.py
~~~~~~~~~~~~~~~~~~~
App-style homepage for BioDesign Studio.

Shows a tile grid of available modules. Each live tile navigates
directly using the shared _change_page callback.

Tile source (V1.2): derived from core.module_registry, the single source of
truth for name, icon, description, route_key, and layer. Presentation
details (stars, chip colours) are derived locally from layer/category.
"""
from __future__ import annotations

from html import escape

import streamlit as st

from core.module_registry import MODULE_REGISTRY
from services.rice_albumin_example_fixture import (
    build_rice_albumin_example_preview,
)


# ---------------------------------------------------------------------------
# IDs excluded from the tile grid
# ---------------------------------------------------------------------------
# homepage: this page itself
# support: docs/help link; lives in sidebar Help section
# module_center: system admin page; lives in sidebar Help section
# plant_promoter_catalog: preserved as a route/detail surface inside the library context
# sequence_tools / codon_optimizer: preserved as compatibility routes, but hidden
# from first-path navigation for the expression-vector MVP.
_TILE_EXCLUDE_IDS = {
    "homepage",
    "support",
    "module_center",
    "plant_promoter_catalog",
    "sequence_tools",
    "codon_optimizer",
}

# The featured tile (full-width hero card)
_FEATURED_ID = "expression_wizard"


# ---------------------------------------------------------------------------
# Presentation helpers derived from registry layer / category
# ---------------------------------------------------------------------------

# stars: core workflow modules get 5, core system/data get 4, tools get 3
_STARS_BY_LAYER_CATEGORY: dict[tuple[str, str], int] = {
    ("core", "workflow"): 5,
    ("core", "system"):   4,
    ("core", "data"):     4,
    ("tool", "data"):     4,
    ("tool", "tools"):    3,
    ("tool", "system"):   3,
}

def _stars_for(m: dict) -> int:
    return _STARS_BY_LAYER_CATEGORY.get((m["layer"], m["category"]), 3)


# chip label + colours: derived from layer
_CHIP_BY_LAYER: dict[str, dict] = {
    "core":   {"label": "Core",  "bg": "#dcfce7", "fg": "#15803d"},
    "tool":   {"label": "Beta",  "bg": "#eff6ff", "fg": "#1d4ed8"},
    "hidden": {"label": "Hidden", "bg": "#f3f4f6", "fg": "#6b7280"},
}

def _chip_for(m: dict) -> dict:
    return _CHIP_BY_LAYER.get(m["layer"], _CHIP_BY_LAYER["tool"])


# ---------------------------------------------------------------------------
# Build tile list from registry at import time
# ---------------------------------------------------------------------------

def _build_tiles() -> list[dict]:
    """Return display-ready tile dicts derived from MODULE_REGISTRY."""
    tiles = []
    for m in MODULE_REGISTRY:
        if m["id"] in _TILE_EXCLUDE_IDS:
            continue
        if m["layer"] not in ("core", "tool"):
            continue
        if m["status"] != "active":
            continue
        chip = _chip_for(m)
        tiles.append({
            "name":        m["name"],
            "page_key":    m["route_key"],
            "icon":        m["icon"],
            "description": m["description"],
            "stars":       _stars_for(m),
            "chip":        chip["label"],
            "chip_bg":     chip["bg"],
            "chip_fg":     chip["fg"],
            "featured":    m["id"] == _FEATURED_ID,
        })
    return tiles


_MODULES: list[dict] = _build_tiles()

WORKFLOW_GUIDE_BOUNDARY_COPY = (
    "Workflow Guide is documentation-only: this local project workspace supports expression vector "
    "construction design record preparation, source/provenance review, traceability, documentation "
    "snapshots, import preview, export package review, and duplicate guard checks. It does not represent "
    "experimental success, does not predict production output, does not prove experimental readiness, "
    "and does not make production-level conclusions."
)

WORKFLOW_GUIDE_RELATIONSHIP_COPY: list[str] = [
    "Start here: Expression Wizard is the primary single-gene / single-protein expression vector design preparation path.",
    "Use Component Library as a supporting source/provenance library for expression cassette and vector/backbone components.",
    "Sequence and codon checks are supporting read-only review context, not standalone first-path choices or optimization output.",
    "Use Pathway Projects and Pathway Workspace when the expression vector record needs project grouping, review notes, traceability, or Project Outputs.",
    "Design Snapshot != Documentation Snapshot: a design snapshot stores Expression Wizard design state; a documentation snapshot stores Pathway Workspace project documentation state.",
    "Project Outputs is the place for documentation snapshots, reports, documentation-only export package review, and import preview review.",
]

PLANT_PROJECT_TYPE_BOUNDARY_COPY = (
    "Documentation-only pre-experiment design review for plant expression construct preparation, "
    "provenance review, gap identification, and report handoff. The first MVP is plant recombinant "
    "protein / molecular farming. Planned workflows are read-only direction previews; no protocols, "
    "construct-readiness certification, sequence optimization output, plant-line proof claims, "
    "or yield estimates are provided."
)

PLANT_PROJECT_TYPES: list[dict[str, str]] = [
    {
        "title": "Plant recombinant protein / molecular farming",
        "examples": "Examples: rice albumin, plant-made antigen, industrial enzyme.",
        "status": "Current first MVP",
        "cta": "Start first MVP review",
        "readback": "Use the existing Expression Wizard and handoff review surfaces for plant expression construct documentation review.",
    },
    {
        "title": "Plant metabolic product / quality improvement",
        "examples": "Examples: artemisinin precursor, carotenoids, anthocyanins, healthy sugar/sweetness traits.",
        "status": "Planned / read-only",
        "cta": "Read-only direction preview",
        "readback": "Shown for direction/readback only; no metabolic-product workflow behavior is implemented in this selector.",
    },
    {
        "title": "Plant trait / gene-function expression review",
        "examples": "Examples: stress tolerance, disease resistance, tissue-specific expression, inducible expression.",
        "status": "Planned / read-only",
        "cta": "Read-only direction preview",
        "readback": "Shown for direction/readback only; no trait or gene-function workflow behavior is implemented in this selector.",
    },
]

PRODUCT_WORKFLOW_BOUNDARY_COPY = (
    "Expression vector construction preparation map: Target Sequence -> Source/Provenance -> Host System "
    "-> Expression Cassette -> Vector/Backbone -> Component Sources -> Sequence Check -> Gap Review "
    "-> Expression Vector Design Package. This map is documentation-only and review-only; it does not "
    "add generated vector sequences, rewritten CDS output, biological ranking, cloning strategy drafting, "
    "wet-lab procedure drafting, production output forecasting, or wet-lab instructions."
)

PRODUCT_WORKFLOW_STEPS: list[dict[str, str]] = [
    {
        "phase": "Target",
        "title": "Target Sequence",
        "description": "Start in Expression Wizard with the target gene, CDS, or protein-linked sequence record.",
        "page_key": "Expression Wizard",
        "button": "Open Wizard",
    },
    {
        "phase": "Source",
        "title": "Source / Provenance",
        "description": "Record sequence type, source notes, provenance context, and manual follow-up needs.",
        "page_key": "Expression Wizard",
        "button": "Open Source Review",
    },
    {
        "phase": "Host",
        "title": "Host System",
        "description": "Document the expression host or system as review context without host ranking.",
        "page_key": "Expression Wizard",
        "button": "Open Host Review",
    },
    {
        "phase": "Cassette",
        "title": "Expression Cassette",
        "description": "Review cassette slots: promoter, 5' UTR/RBS/Kozak, signal or targeting context, CDS, tag/linker, and terminator/polyA.",
        "page_key": "Expression Wizard",
        "button": "Open Cassette Review",
    },
    {
        "phase": "Vector",
        "title": "Vector / Backbone",
        "description": "Record backbone name, marker, origin or integration context when known, and source/lab/vendor/manual notes.",
        "page_key": "Expression Constructs",
        "button": "Open Construct Records",
    },
    {
        "phase": "Sources",
        "title": "Component Sources",
        "description": "Use Component Library as supporting expression vector component source and provenance context.",
        "page_key": "Data",
        "button": "Open Component Library",
    },
    {
        "phase": "Check",
        "title": "Sequence Check",
        "description": "Review sequence type, length, CDS frame status, start/stop status, internal stops, ambiguous bases, GC percentage, and read-only codon usage context inside the expression-vector review path.",
        "page_key": "Expression Wizard",
        "button": "Open Wizard Review",
    },
    {
        "phase": "Gaps",
        "title": "Gap Review",
        "description": "Capture missing source, host, promoter, backbone, tag position, targeting context, and stop-codon handling as manual follow-up.",
        "page_key": "Pathway Workspace",
        "button": "Open Gap Review",
    },
    {
        "phase": "Package",
        "title": "Expression Vector Design Package",
        "description": "Use Project Outputs for a documentation-only package/report role with QR/MD5 identity and review notes.",
        "page_key": "Pathway Workspace",
        "button": "Open Outputs",
    },
]

PROJECT_REVIEW_WORKFLOW_BOUNDARY_COPY = (
    "Expression Vector Design Package workflow: reuse existing project review and handoff surfaces to explain "
    "target context, component provenance, sequence checks, manual follow-up, package identity, and traceability. "
    "This path is for local documentation review only and does not claim biological validation, readiness, ranking, "
    "scoring, optimization, host compatibility, or wet-lab use."
)

PROJECT_REVIEW_WORKFLOW_STEPS: list[dict[str, str]] = [
    {
        "phase": "Record",
        "title": "Create an expression design record",
        "description": "Use Expression Wizard to capture the single-gene or single-protein design preparation record.",
        "page_key": "Expression Wizard",
        "button": "Open Wizard",
    },
    {
        "phase": "Context",
        "title": "Attach project review context when needed",
        "description": "Use Pathway Projects and Pathway Workspace only when the record needs project grouping, linked notes, and traceability.",
        "page_key": "Pathway Projects",
        "button": "Open Projects",
    },
    {
        "phase": "Sources",
        "title": "Review component source context",
        "description": "Use Component Library and Expression Constructs as documentation-only component and cassette record surfaces.",
        "page_key": "Data",
        "button": "Open Library",
    },
    {
        "phase": "Review",
        "title": "Inspect gaps and follow-up notes",
        "description": "Use Project Review Report and Project Quality Dashboard to explain documentation state and human review prompts.",
        "page_key": "Pathway Workspace",
        "button": "Open Review",
    },
    {
        "phase": "Package",
        "title": "Prepare the design package readback",
        "description": "Use Project Outputs for documentation snapshots, report identity, export package review, and import preview review.",
        "page_key": "Pathway Workspace",
        "button": "Open Outputs",
    },
]

WORKFLOW_GUIDE_STEPS: list[dict[str, str]] = [
    {
        "title": "Expression Wizard",
        "description": "Primary path for one expression vector construction design preparation record.",
        "page_key": "Expression Wizard",
        "button": "Open Expression Wizard",
    },
    {
        "title": "Expression Constructs",
        "description": "Browse documentation-only construct, cassette, cassette-part, and linked gene records.",
        "page_key": "Expression Constructs",
        "button": "Open Expression Constructs",
    },
    {
        "title": "Handoff Review",
        "description": "Inspect documentation gaps, follow-up notes, traceability rows, and expression-vector package readback before any project output review.",
        "page_key": "Pathway Workspace",
        "button": "Open Handoff Review",
    },
    {
        "title": "Component Library",
        "description": "Review component source/provenance context for cassette and vector/backbone records.",
        "page_key": "Data",
        "button": "Open Component Library",
    },
    {
        "title": "Pathway Projects",
        "description": "Use optional project grouping when expression vector records need project-level traceability.",
        "page_key": "Pathway Projects",
        "button": "Open Pathway Projects",
    },
    {
        "title": "Pathway Workspace",
        "description": "Review project context, linked records, documentation gaps, and traceability notes.",
        "page_key": "Pathway Workspace",
        "button": "Open Pathway Workspace",
    },
    {
        "title": "Project Outputs",
        "description": "Review documentation snapshots, reports, export package review, and import preview review.",
        "page_key": "Pathway Workspace",
        "button": "Open Project Outputs",
    },
    {
        "title": "Design Library",
        "description": "View and reopen saved Expression Wizard design snapshots.",
        "page_key": "Design Library",
        "button": "Open Design Library",
    },
    {
        "title": "Duplicate Guard",
        "description": "Check for existing documentation projects before adding another local record.",
        "page_key": "Pathway Projects",
        "button": "Open Project List",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stars_html(n: int) -> str:
    """Return an HTML star-rating string using ASCII-safe markers."""
    filled = "*" * n
    hollow = "-" * (5 - n)
    return (
        f"<span style='color:#f59e0b;font-size:.85rem;letter-spacing:1px'>{filled}</span>"
        f"<span style='color:#d1d5db;font-size:.85rem;letter-spacing:1px'>{hollow}</span>"
    )


def _chip_html(label: str, bg: str, fg: str) -> str:
    return (
        f"<span style='"
        f"background:{bg};color:{fg};"
        f"font-size:.68rem;font-weight:700;"
        f"padding:2px 9px;border-radius:20px;"
        f"letter-spacing:.4px;text-transform:uppercase;"
        f"'>{label}</span>"
    )


# ---------------------------------------------------------------------------
# CSS injected once
# ---------------------------------------------------------------------------

_CSS = """
<style>
/* Homepage hero banner */
.homepage-root .hp-hero {
    background: #f8fbf7;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 26px 30px;
    margin-bottom: 18px;
    position: relative;
    overflow: hidden;
}
.homepage-root .hp-hero-eyebrow {
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #15803d;
    margin-bottom: 8px;
}
.homepage-root .hp-hero-title {
    font-size: 1.9rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: 0;
    line-height: 1.2;
    margin-bottom: 6px;
}
.homepage-root .hp-hero-sub {
    font-size: 1rem;
    color: #334155;
    max-width: 820px;
    line-height: 1.5;
}
.homepage-root .hp-hero-note {
    margin-top: 12px;
    padding: 10px 12px;
    background: #ffffff;
    border: 1px solid #d9f99d;
    border-radius: 8px;
    font-size: .86rem;
    color: #475569;
    line-height: 1.5;
}

/* Section heading */
.homepage-root .hp-section {
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #6b7280;
    margin: 8px 0 14px 2px;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 6px;
}

/* Module card (standard) */
.homepage-root .hp-card {
    background: #ffffff;
    border: 1.5px solid #e5e7eb;
    border-radius: 12px;
    padding: 20px 22px 18px 22px;
    height: 100%;
    transition: border-color .18s, box-shadow .18s, transform .15s;
    cursor: pointer;
    position: relative;
    box-sizing: border-box;
}
.homepage-root .hp-card:hover {
    border-color: #93c5fd;
    box-shadow: 0 4px 18px rgba(37,99,235,.10);
    transform: translateY(-2px);
}
.homepage-root .hp-card.placeholder {
    background: #fafafa;
    border-color: #e5e7eb;
    cursor: default;
    opacity: .72;
}
.homepage-root .hp-card.placeholder:hover {
    border-color: #e5e7eb;
    box-shadow: none;
    transform: none;
}

/* Featured card (Expression Design hero) */
.homepage-root .hp-card-featured {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    border: 2px solid #93c5fd;
    border-radius: 14px;
    padding: 26px 28px 22px 28px;
    transition: border-color .18s, box-shadow .18s, transform .15s;
    cursor: pointer;
    position: relative;
    overflow: hidden;
}
.homepage-root .hp-card-featured::before {
    content: '';
    position: absolute;
    right: -20px; top: -20px;
    width: 120px; height: 120px;
    background: radial-gradient(circle, rgba(37,99,235,.12) 0%, transparent 70%);
    pointer-events: none;
}
.homepage-root .hp-card-featured:hover {
    border-color: #3b82f6;
    box-shadow: 0 6px 28px rgba(37,99,235,.18);
    transform: translateY(-2px);
}
.homepage-root .hp-card-name {
    font-size: .98rem;
    font-weight: 700;
    color: #111827;
    margin-bottom: 5px;
    letter-spacing: -.2px;
}
.homepage-root .hp-card-featured .hp-card-name {
    font-size: 1.25rem;
    color: #1e3a8a;
}
.homepage-root .hp-card-desc {
    font-size: .88rem;
    color: #6b7280;
    line-height: 1.58;
    margin-bottom: 11px;
}
.homepage-root .hp-card-featured .hp-card-desc {
    font-size: .95rem;
    color: #374151;
    margin-bottom: 14px;
}
.homepage-root .hp-card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.homepage-root .hp-workflow-guide {
    background: #f8fafc;
    border: 1px solid #dbeafe;
    border-radius: 8px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
}
.homepage-root .hp-workflow-title {
    font-size: 1rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 6px;
}
.homepage-root .hp-workflow-boundary {
    font-size: .92rem;
    color: #475569;
    line-height: 1.62;
    margin-bottom: 14px;
}
.homepage-root .hp-workflow-step {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
    min-height: 112px;
    overflow-wrap: anywhere;
}
.homepage-root .hp-workflow-step-index {
    font-size: .68rem;
    font-weight: 800;
    color: #2563eb;
    letter-spacing: .8px;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.homepage-root .hp-workflow-step-title {
    font-size: .95rem;
    font-weight: 750;
    color: #111827;
    margin-bottom: 5px;
}
.homepage-root .hp-workflow-step-desc {
    font-size: .86rem;
    color: #64748b;
    line-height: 1.55;
}
.homepage-root .hp-demo-flow {
    background: #f8fafc;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
}
.homepage-root .hp-demo-phase {
    font-size: .66rem;
    font-weight: 850;
    color: #0369a1;
    letter-spacing: .9px;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.homepage-root .hp-plant-selector {
    background: #f8fbf7;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 16px 18px;
    margin: 14px 0 18px 0;
}
.homepage-root .hp-plant-selector-readback {
    background: #ffffff;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 12px 14px;
    margin-top: 12px;
    font-size: .88rem;
    color: #334155;
    line-height: 1.55;
}
.homepage-root .hp-plant-status {
    display: inline-block;
    font-size: .68rem;
    font-weight: 850;
    color: #166534;
    background: #dcfce7;
    border-radius: 999px;
    padding: 2px 8px;
    margin-bottom: 6px;
}
.homepage-root .hp-plant-card {
    background: #ffffff;
    border: 1px solid #d9f99d;
    border-radius: 8px;
    padding: 14px 15px;
    min-height: 176px;
    overflow-wrap: anywhere;
}
.homepage-root .hp-example-preview {
    background: #f8fafc;
    border: 1px solid #dbeafe;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 4px 0 14px 0;
}
.homepage-root .hp-example-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 5px;
}
.homepage-root .hp-example-labels {
    font-size: .82rem;
    font-weight: 700;
    color: #2563eb;
    margin-bottom: 10px;
}
.homepage-root .hp-example-boundary {
    background: #ffffff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: .88rem;
    color: #334155;
    line-height: 1.55;
}
.homepage-root .hp-example-row {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 92px;
    overflow-wrap: anywhere;
}
.homepage-root .hp-example-row-label {
    font-size: .68rem;
    font-weight: 850;
    color: #64748b;
    letter-spacing: .8px;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.homepage-root .hp-example-row-value {
    font-size: .88rem;
    color: #1f2937;
    line-height: 1.48;
}
.homepage-root .hp-example-identity {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
    margin-top: 10px;
    font-size: .88rem;
    color: #334155;
    line-height: 1.58;
    overflow-wrap: anywhere;
}
.homepage-root .hp-example-identity-heading {
    font-size: .9rem;
    font-weight: 850;
    color: #0f172a;
    margin: 16px 0 6px 0;
}
.homepage-root .hp-example-details {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 12px;
    margin-top: 12px;
}
.homepage-root .hp-example-details summary {
    cursor: pointer;
    font-size: .9rem;
    font-weight: 800;
    color: #0f172a;
}
.homepage-root .hp-example-details table {
    width: 100%;
    margin-top: 10px;
    border-collapse: collapse;
    font-size: .84rem;
}
.homepage-root .hp-example-details th,
.homepage-root .hp-example-details td {
    border-top: 1px solid #e5e7eb;
    padding: 7px 6px;
    text-align: left;
    vertical-align: top;
}
.homepage-root .hp-example-code {
    display: block;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 9px 10px;
    margin-top: 10px;
    font-size: .78rem;
    color: #334155;
}
.homepage-root .hp-secondary-modules {
    margin-top: 26px;
    padding-top: 6px;
    border-top: 1px solid #e5e7eb;
}
.homepage-root .hp-secondary-heading {
    font-size: 1.08rem;
    font-weight: 800;
    color: #0f172a;
    margin: 0 0 6px 0;
}
.homepage-root .hp-secondary-copy {
    font-size: .9rem;
    color: #64748b;
    line-height: 1.58;
    margin-bottom: 16px;
}
@media (max-width: 900px) {
    .homepage-root .hp-hero {
        padding: 28px 26px;
        border-radius: 10px;
    }
    .homepage-root .hp-hero-title {
        font-size: 1.62rem;
    }
    .homepage-root .hp-card,
    .homepage-root .hp-card-featured,
    .homepage-root .hp-workflow-guide,
    .homepage-root .hp-demo-flow {
        border-radius: 10px;
        padding: 18px;
    }
    .homepage-root .hp-workflow-step {
        min-height: 0;
        margin-bottom: 10px;
    }
}
</style>
"""


# ---------------------------------------------------------------------------
# Public render entry point
# ---------------------------------------------------------------------------

def _workflow_steps() -> list[dict[str, str]]:
    """Return the stable Homepage workflow guide sequence."""
    return WORKFLOW_GUIDE_STEPS


def _plant_project_types() -> list[dict[str, str]]:
    """Return plant-only project type readback options."""
    return PLANT_PROJECT_TYPES


def _rice_albumin_example_preview() -> dict:
    """Return the read-only rice albumin plant example preview."""
    return build_rice_albumin_example_preview()


def _product_workflow_steps() -> list[dict[str, str]]:
    """Return the stable product workflow sequence."""
    return PRODUCT_WORKFLOW_STEPS


def _project_review_workflow_steps() -> list[dict[str, str]]:
    """Return the project review package/report sequence."""
    return PROJECT_REVIEW_WORKFLOW_STEPS


def _render_documentation_boundary_notice() -> None:
    """Render documentation-only boundary and page relationship copy."""
    relationship_items = "".join(
        f"<li>{item}</li>" for item in WORKFLOW_GUIDE_RELATIONSHIP_COPY
    )
    st.markdown(
        f"""
        <div class="hp-workflow-guide">
            <div class="hp-workflow-title">Workflow Guide</div>
            <div class="hp-workflow-boundary">{WORKFLOW_GUIDE_BOUNDARY_COPY}</div>
            <ul class="hp-workflow-boundary">
                {relationship_items}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_plant_project_type_selection(change_page) -> None:
    """Render plant-only project type selection and readback without persistence."""
    project_types = _plant_project_types()
    st.markdown(
        f"""
        <div class="hp-plant-selector">
            <div class="hp-workflow-title">Plant Project Type Selection</div>
            <div class="hp-workflow-boundary">{PLANT_PROJECT_TYPE_BOUNDARY_COPY}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(project_types))
    for col, project_type in zip(cols, project_types):
        with col:
            st.markdown(
                f"""
                <div class="hp-plant-card">
                    <div class="hp-demo-phase">Plant-only project type</div>
                    <div class="hp-plant-status">{project_type['status']}</div>
                    <div class="hp-workflow-step-title">{project_type['title']}</div>
                    <div class="hp-workflow-step-desc">{project_type['examples']}</div>
                    <div class="hp-workflow-step-desc"><strong>{project_type['cta']}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if project_type["status"] == "Current first MVP":
                if st.button(
                    "Start first MVP review ->",
                    key="plant_project_type_open_first_mvp",
                    width="stretch",
                ):
                    change_page("Expression Wizard")
            else:
                st.button(
                    "Read-only direction preview",
                    key=f"plant_project_type_planned_{project_type['title'].replace(' ', '_').replace('/', '_')}",
                    disabled=True,
                    width="stretch",
                )

    with st.expander("Compact plant project type readback", expanded=False):
        selected_title = st.selectbox(
            "Plant project type",
            [project_type["title"] for project_type in project_types],
            key="homepage_plant_project_type_selection",
        )
        selected = next(
            project_type for project_type in project_types if project_type["title"] == selected_title
        )
        st.markdown(
            f"""
            <div class="hp-plant-selector-readback">
                <div class="hp-plant-status">{selected['status']}</div>
                <div><strong>{selected['title']}</strong></div>
                <div>{selected['examples']}</div>
                <div>{selected['readback']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_rice_albumin_example_preview() -> None:
    """Render a collapsed read-only rice albumin example preview."""
    preview = _rice_albumin_example_preview()
    identity = preview["identity"]
    with st.expander("View rice albumin example preview", expanded=False):
        labels = " · ".join(preview["labels"])
        st.markdown(
            f"""
            <div class="hp-example-preview">
                <div class="hp-example-title">Rice albumin example preview</div>
                <div class="hp-example-labels">{labels}</div>
                <div class="hp-example-boundary">{preview['boundary_note']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        summary_rows = [
            ("Project direction", preview["project_direction"]),
            ("Plant context", preview["plant_host_context"]),
            ("Evidence status", "source/provenance required; manual follow-up required"),
            (
                "Workflow continuity",
                "Home -> Expression Wizard -> Component Library -> Plant Design Review Package -> QR/MD5 identity",
            ),
        ]
        cols = st.columns(2)
        for index, (label, value) in enumerate(summary_rows):
            with cols[index % 2]:
                st.markdown(
                    f"""
                    <div class="hp-example-row">
                        <div class="hp-example-row-label">{label}</div>
                        <div class="hp-example-row-value">{value}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.caption(preview["read_only_note"])

        detail_rows = []
        for row in preview["review_placeholders"]:
            detail_rows.append(
                "<tr>"
                f"<td>{escape(row['field'])}</td>"
                f"<td>{escape(row['readback'])}</td>"
                "</tr>"
            )
        detail_rows.append(
            "<tr>"
            "<td>Evidence / provenance gaps</td>"
            f"<td>{escape('; '.join(preview['evidence_provenance_gaps']))}</td>"
            "</tr>"
        )
        st.markdown(
            f"""
            <details class="hp-example-details">
                <summary>Detailed example readback</summary>
                <table>
                    <thead>
                        <tr><th>Field</th><th>Example readback</th></tr>
                    </thead>
                    <tbody>
                        {''.join(detail_rows)}
                    </tbody>
                </table>
            </details>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="hp-example-identity-heading">Example package identity</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="hp-example-identity">
                <div><strong>Snapshot ID:</strong> {identity['snapshot_id']}</div>
                <div><strong>MD5 checksum:</strong> {identity['md5_checksum']}</div>
                <div><strong>QR status:</strong> payload-only</div>
                <div><strong>Boundary:</strong> QR/MD5 verifies only example package identity.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <details class="hp-example-details">
                <summary>Show QR payload</summary>
                <code class="hp-example-code">{escape(identity['qr_payload'])}</code>
            </details>
            """,
            unsafe_allow_html=True,
        )


def _render_product_workflow_step(step: dict[str, str], step_number: int, change_page) -> None:
    """Render one product workflow card and navigation button."""
    st.markdown(
        f"""
        <div class="hp-workflow-step">
            <div class="hp-workflow-step-index">Step {step_number}</div>
            <div class="hp-demo-phase">{step['phase']}</div>
            <div class="hp-workflow-step-title">{step['title']}</div>
            <div class="hp-workflow-step-desc">{step['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        f"{step['button']} ->",
        key=f"product_workflow_{step_number}_{step['page_key'].replace(' ', '_')}",
        width="stretch",
    ):
        change_page(step["page_key"])


def _render_product_workflow(change_page) -> None:
    """Render the stable general synthetic biology workflow path."""
    st.markdown(
        f"""
        <div class="hp-demo-flow">
            <div class="hp-workflow-title">Expression Vector Construction Preparation Map</div>
            <div class="hp-workflow-boundary">{PRODUCT_WORKFLOW_BOUNDARY_COPY}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = _product_workflow_steps()
    cols = st.columns(len(steps))
    for step_number, (col, step) in enumerate(zip(cols, steps), start=1):
        with col:
            _render_product_workflow_step(step, step_number, change_page)


def _render_project_review_workflow_step(step: dict[str, str], step_number: int, change_page) -> None:
    """Render one project review workflow card and navigation button."""
    st.markdown(
        f"""
        <div class="hp-workflow-step">
            <div class="hp-workflow-step-index">Step {step_number}</div>
            <div class="hp-demo-phase">{step['phase']}</div>
            <div class="hp-workflow-step-title">{step['title']}</div>
            <div class="hp-workflow-step-desc">{step['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        f"{step['button']} ->",
        key=f"project_review_workflow_{step_number}_{step['page_key'].replace(' ', '_')}",
        width="stretch",
    ):
        change_page(step["page_key"])


def _render_project_review_workflow(change_page) -> None:
    """Render the project review walkthrough path."""
    st.markdown(
        f"""
        <div class="hp-demo-flow">
            <div class="hp-workflow-title">Expression Vector Design Package Workflow</div>
            <div class="hp-workflow-boundary">{PROJECT_REVIEW_WORKFLOW_BOUNDARY_COPY}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = _project_review_workflow_steps()
    cols = st.columns(len(steps))
    for step_number, (col, step) in enumerate(zip(cols, steps), start=1):
        with col:
            _render_project_review_workflow_step(step, step_number, change_page)


def _render_workflow_step(step: dict[str, str], step_number: int, change_page) -> None:
    """Render one workflow guide card and navigation button."""
    st.markdown(
        f"""
        <div class="hp-workflow-step">
            <div class="hp-workflow-step-index">Step {step_number}</div>
            <div class="hp-workflow-step-title">{step['title']}</div>
            <div class="hp-workflow-step-desc">{step['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        f"{step['button']} ->",
        key=f"workflow_guide_{step_number}_{step['page_key'].replace(' ', '_')}",
        width="stretch",
    ):
        change_page(step["page_key"])


def _render_workflow_guide(change_page) -> None:
    """Render lightweight first-run workflow guidance."""
    _render_documentation_boundary_notice()

    steps = _workflow_steps()
    for i in range(0, len(steps), 4):
        row_steps = steps[i : i + 4]
        cols = st.columns(len(row_steps))
        for offset, (col, step) in enumerate(zip(cols, row_steps), start=1):
            with col:
                _render_workflow_step(step, i + offset, change_page)


def render(change_page) -> None:  # noqa: D401
    """Render the app-style homepage tile grid."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("<div class='homepage-root'>", unsafe_allow_html=True)

    # Hero banner
    st.markdown(
        """
        <div class="hp-hero">
            <div class="hp-hero-eyebrow">Documentation-only local project workspace</div>
            <div class="hp-hero-title">BioDesign Studio Plant</div>
            <div class="hp-hero-sub">
                Plant Synthetic Biology Design Review Workspace
            </div>
            <div class="hp-hero-note">
                Documentation-only pre-experiment design review for plant expression construct preparation,
                provenance review, gap identification, and report handoff.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_plant_project_type_selection(change_page)
    _render_rice_albumin_example_preview()

    st.markdown(
        """
        <div class="hp-secondary-modules">
            <div class="hp-secondary-heading">Existing documentation workflow modules</div>
            <div class="hp-secondary-copy">
                These existing Expression Wizard, project review, and module surfaces remain available
                as documentation-only review tools beneath the plant-first entry point.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Advanced existing workflow map", expanded=False):
        _render_workflow_guide(change_page)
        _render_project_review_workflow(change_page)
        _render_product_workflow(change_page)

    # Split into featured + rest
    featured = [m for m in _MODULES if m.get("featured")]

    # Explicit display order for regular tiles
    _REGULAR_ORDER = [
        "Expression Constructs",
        "Component Library",
        "Pathway Workspace",
        "Pathway Projects",
        "Application Scenario",
        "Saved Designs",
        "Case Library",
        "Assembly & Cloning",
    ]
    _regular_map = {m["name"]: m for m in _MODULES if not m.get("featured")}
    regular = [_regular_map[name] for name in _REGULAR_ORDER if name in _regular_map]
    # Append any remaining tiles not in the explicit order list
    _ordered_names = set(_REGULAR_ORDER)
    regular += [m for m in _MODULES if not m.get("featured") and m["name"] not in _ordered_names]

    with st.expander("Existing documentation workflow modules", expanded=False):
        # Featured tile (full-width row)
        if featured:
            m = featured[0]
            st.markdown(
                "<div class='hp-section'>Main Workflow</div>",
                unsafe_allow_html=True,
            )
            col_feat, col_spacer = st.columns([2, 1])
            with col_feat:
                st.markdown(
                    f"""
                    <div class="hp-card-featured">
                        <div class="hp-card-name">{m['name']}</div>
                        <div class="hp-card-desc">{m['description']}</div>
                        <div class="hp-card-meta">
                            {_stars_html(m['stars'])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                # Invisible Streamlit button overlaid via layout trick
                if st.button(
                    f"Open {m['name']} ->",
                    key="tile_featured",
                    type="primary",
                    use_container_width=True,
                ):
                    change_page(m["page_key"])

        # Regular tiles (2-column grid)
        st.markdown(
            "<div class='hp-section' style='margin-top:28px'>All Modules</div>",
            unsafe_allow_html=True,
        )

        # Pair up tiles into rows of 2
        for i in range(0, len(regular), 2):
            row_mods = regular[i : i + 2]
            cols = st.columns(len(row_mods))
            for col, m in zip(cols, row_mods):
                with col:
                    is_placeholder = m["page_key"] is None
                    card_cls = "hp-card placeholder" if is_placeholder else "hp-card"
                    st.markdown(
                        f"""
                        <div class="{card_cls}">
                            <div class="hp-card-name">{m['name']}</div>
                            <div class="hp-card-desc">{m['description']}</div>
                            <div class="hp-card-meta">
                                {_stars_html(m['stars'])}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if not is_placeholder:
                        btn_label = f"Open {m['name']} ->"
                        if st.button(
                            btn_label,
                            key=f"tile_{m['page_key']}",
                            use_container_width=True,
                        ):
                            change_page(m["page_key"])
                    else:
                        st.button(
                            "Coming soon",
                            key=f"tile_placeholder_{m['name'].replace(' ', '_')}",
                            disabled=True,
                            use_container_width=True,
                        )

    # Footer note
    st.markdown(
        "<div style='margin-top:36px;font-size:.72rem;color:#9ca3af;text-align:center'>"
        "BioDesign Studio v8.0.0 &nbsp;|&nbsp; "
        "Documentation-only local project workspace &nbsp;|&nbsp; "
        "&copy; 2026"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
