"""Lazy compatibility registry for historical Streamlit UI modules.

The formal ``app.py`` entrypoint must not import this registry. Historical
launchers and compatibility tests may opt in and load a retained page by its
stable identifier.
"""
from __future__ import annotations

from importlib import import_module
from types import MappingProxyType, ModuleType


LEGACY_UI_MODULE_PATHS = MappingProxyType(
    {
        "expression_wizard": "views.ExpressionWizard",
        "pathway_workspace": "views.PathwayWorkspace",
        "design_library": "views.DesignLibrary",
        "lab_tools": "views.LabTools",
        "structure_analysis": "views.StructureAnalysis",
    }
)


def load_legacy_ui_module(page_id: str) -> ModuleType:
    """Load one retained historical UI module only when explicitly requested."""
    try:
        module_path = LEGACY_UI_MODULE_PATHS[page_id]
    except KeyError as exc:
        available = ", ".join(LEGACY_UI_MODULE_PATHS)
        raise KeyError(f"Unknown legacy UI page {page_id!r}; expected one of: {available}") from exc
    return import_module(module_path)


def load_all_legacy_ui_modules() -> dict[str, ModuleType]:
    """Load every retained historical UI module for compatibility diagnostics."""
    return {page_id: load_legacy_ui_module(page_id) for page_id in LEGACY_UI_MODULE_PATHS}
