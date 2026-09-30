# -*- coding: utf-8 -*-
"""
core/module_registry.py
~~~~~~~~~~~~~~~~~~~~~~~
Single source of truth for all BioDesign Studio modules.

Layering
--------
  "core"   — Always active, never toggled. Sidebar Workflow + Help sections.
  "tool"   — Shipped with app, sidebar visibility toggleable by user.
  "hidden" — Frozen. Router branch preserved; not shown in sidebar or Homepage.

Schema fields (V1.2)
--------------------
  id          : str   Stable snake_case identifier. Never rename.
  name        : str   Display name (sidebar, tiles, cards).
  icon        : str   Short plain-text abbreviation (e.g. "EW", "DB").
  layer       : str   "core" | "tool" | "hidden"
  category    : str   "workflow" | "data" | "tools" | "system" | "experimental"
  status      : str   "active" | "hidden" | "coming_soon"
  version     : str   Semantic version string.
  description : str   One sentence for Module Center card and Homepage tile.
  route_key   : str   Exact string used in st.session_state["selected_page"].
                      Must match an entry in _ALL_PAGES in app.py exactly.

Not in V1.2 schema (reserved for Plugin Store era):
  author, homepage_url, license, install_path, dependencies,
  min_app_version, checksum.
"""
from __future__ import annotations

MODULE_REGISTRY: list[dict] = [
    {
        "id": "homepage",
        "name": "Home",
        "icon": "HM",
        "layer": "core",
        "category": "system",
        "status": "active",
        "version": "1.1.0",
        "description": "Application entry point with a module tile grid and navigation hub.",
        "route_key": "Homepage",
    },
    {
        "id": "dashboard",
        "name": "Saved Designs",
        "icon": "DB",
        "layer": "core",
        "category": "system",
        "status": "active",
        "version": "1.1.0",
        "description": "Saved design records and design snapshots review surface for reopening records in the wizard.",
        "route_key": "Dashboard",
    },
    {
        "id": "application_scenario",
        "name": "Application Scenario",
        "icon": "AS",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "2.6.0",
        "description": "Biology-facing read-only context page for pre-experiment design documentation review.",
        "route_key": "Application Scenario",
    },
    {
        "id": "pathway_projects",
        "name": "Pathway Projects",
        "icon": "PP",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "2.1.0",
        "description": "Optional project grouping surface for expression vector records, review notes, and documentation traceability.",
        "route_key": "Pathway Projects",
    },
    {
        "id": "pathway_workspace",
        "name": "Pathway Workspace",
        "icon": "PW",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "2.1.0",
        "description": "Project-level review workspace for linked expression design records, documentation gaps, traceability, and outputs.",
        "route_key": "Pathway Workspace",
    },
    {
        "id": "plant_design_workspace",
        "name": "Plant Design Workspace",
        "icon": "PD",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "2.6.0",
        "description": "Read-only plant route review shell for fixture-based candidate match, source/evidence, gap, package, and Markdown readback.",
        "route_key": "Plant Design Workspace",
    },
    {
        "id": "expression_wizard",
        "name": "Expression Wizard",
        "icon": "EW",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "1.1.0",
        "description": "Primary 6-step single-gene expression vector construction design preparation workflow.",
        "route_key": "Expression Wizard",
    },
    {
        "id": "plant_expression_workspace",
        "name": "Plant Expression Workspace",
        "icon": "PE",
        "layer": "core",
        "category": "workflow",
        "status": "active",
        "version": "2.7.0",
        "description": "Independent read-only prototype for reviewing plant expression goals, construct components, gaps, and traceability details.",
        "route_key": "Plant Expression Workspace",
    },
    {
        "id": "case_library",
        "name": "Case Library",
        "icon": "CL",
        "layer": "tool",
        "category": "data",
        "status": "active",
        "version": "1.1.0",
        "description": "Reference case examples and internal examples for the current workspace.",
        "route_key": "Case Library",
    },
    {
        "id": "support",
        "name": "Support",
        "icon": "SD",
        "layer": "core",
        "category": "system",
        "status": "active",
        "version": "1.1.0",
        "description": "Help documentation, references, and usage guidance.",
        "route_key": "Support",
    },
    {
        "id": "ai_literature_research",
        "name": "AI Literature Research",
        "icon": "LR",
        "layer": "hidden",
        "category": "experimental",
        "status": "hidden",
        "version": "2.6.0",
        "description": "Future-facing local research brief surface retained outside visible product navigation.",
        "route_key": "AI Literature Research",
    },
    {
        "id": "module_center",
        "name": "Module Overview",
        "icon": "MC",
        "layer": "hidden",
        "category": "experimental",
        "status": "hidden",
        "version": "1.2.0",
        "description": "Deferred module catalog retained for internal access outside active MVP navigation.",
        "route_key": "Module Overview",
    },
    {
        "id": "parts_registry",
        "name": "Component Library",
        "icon": "PR",
        "layer": "tool",
        "category": "data",
        "status": "active",
        "version": "1.1.0",
        "description": "Browse plant expression component source/provenance records, Parts Registry references, local assets, promoter context, and plant promoter assets as documentation-only Component Library records.",
        "route_key": "Data",
    },
    {
        "id": "plant_promoter_catalog",
        "name": "Promoter Assets - Plant Domain",
        "icon": "PC",
        "layer": "tool",
        "category": "data",
        "status": "active",
        "version": "2.6.0",
        "description": "Read-only component-library detail surface for plant promoter source profiles, tissue-context evidence, motif notes, and review metadata.",
        "route_key": "Plant Promoter Catalog",
    },
    {
        "id": "expression_constructs",
        "name": "Expression Constructs",
        "icon": "EC",
        "layer": "tool",
        "category": "data",
        "status": "active",
        "version": "2.6.0",
        "description": "Read-only browse surface for documentation-only construct, cassette, cassette-part, gene, and project-link records.",
        "route_key": "Expression Constructs",
    },
    {
        "id": "sequence_tools",
        "name": "Sequence Tools",
        "icon": "ST",
        "layer": "tool",
        "category": "tools",
        "status": "active",
        "version": "1.1.0",
        "description": "Local sequence inspection summaries, annotation, translation, and linear maps for documentation review.",
        "route_key": "Sequence Tools",
    },
    {
        "id": "codon_optimizer",
        "name": "Codon Optimizer",
        "icon": "CO",
        "layer": "tool",
        "category": "tools",
        "status": "active",
        "version": "1.1.0",
        "description": "Preview host-linked codon usage context for a CDS and summarize CAI and rare-codon changes as documentation-only review context.",
        "route_key": "Codon Optimizer",
    },
    {
        "id": "assembly_cloning",
        "name": "Assembly & Cloning",
        "icon": "AC",
        "layer": "hidden",
        "category": "experimental",
        "status": "hidden",
        "version": "1.1.0",
        "description": "Deferred cloning workspace retained for internal access outside active MVP navigation.",
        "route_key": "Assembly & Cloning",
    },
    {
        "id": "structure_analysis",
        "name": "Structure Analysis",
        "icon": "SA",
        "layer": "hidden",
        "category": "experimental",
        "status": "hidden",
        "version": "1.0.0",
        "description": "Deferred structure-analysis page retained for internal access outside active MVP navigation.",
        "route_key": "Structure Analysis",
    },
    {
        "id": "lab_tools",
        "name": "Lab Tools",
        "icon": "LT",
        "layer": "hidden",
        "category": "experimental",
        "status": "hidden",
        "version": "0.9.0",
        "description": "Combined tabbed view of Assembly & Cloning and Test & Validation.",
        "route_key": "Lab Tools",
    },
]


def get_by_id(module_id: str) -> dict | None:
    """Return the registry entry for the given stable id, or None."""
    for m in MODULE_REGISTRY:
        if m["id"] == module_id:
            return m
    return None


def get_by_route_key(route_key: str) -> dict | None:
    """Return the registry entry for the given route_key, or None."""
    for m in MODULE_REGISTRY:
        if m["route_key"] == route_key:
            return m
    return None


def list_by_layer(layer: str) -> list[dict]:
    """Return all registry entries whose layer matches the given string."""
    return [m for m in MODULE_REGISTRY if m["layer"] == layer]


def list_active() -> list[dict]:
    """Return all entries with status == 'active'."""
    return [m for m in MODULE_REGISTRY if m["status"] == "active"]
