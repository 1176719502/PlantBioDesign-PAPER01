from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
SECTION = SECTIONS_DIR / "linked_catalog_assets_section.py"
BASKET_SERVICE = ROOT / "services" / "catalog_reference_basket_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_linked_catalog_assets_section_exists_and_is_delegated() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert SECTION.exists()
    assert "from views.pathway_workspace_sections.linked_catalog_assets_section import render_linked_catalog_assets_section" in source
    assert "Linked Catalog Assets" in source
    assert "render_linked_catalog_assets_section(project)" in source


def test_linked_catalog_assets_copy_preserved() -> None:
    section_source = _read(SECTION)
    combined_source = section_source + "\n" + _read(BASKET_SERVICE)
    required = [
        "Linked Catalog Assets",
        "Linked assets are documentation references only.",
        "Linking an asset does not indicate biological fit, source verification, or downstream use state.",
        "Human review is required before downstream use; links do not endorse or select an asset.",
        "Linked catalog references can point to persistent records, bundled seed records, example catalog records, or documentation-only reference records.",
        "Add catalog asset reference",
        "reference-only documentation links",
        "Search existing catalog assets",
        "Select catalog asset",
        "Select linkage role",
        "Project documentation context",
        "Optional documentation note",
        "Add documentation reference",
        "Reference basket",
        "Staged documentation reference",
        "No staged documentation references are in the basket yet.",
        "Each staged documentation reference keeps documentation-only context visible before persistence.",
        "Clear staged documentation references",
        "Add reference to project documentation",
        "already linked to project documentation",
        "Project documentation context",
        "Selected asset preview",
        "source/provenance status",
        "review status",
        "human review note",
        "No linked catalog references are recorded for this project yet.",
        "Add catalog records when project documentation needs reference-only source, review, or traceability context.",
        "Total linked assets",
        "count by asset type",
        "count by linkage role",
        "Source/status language: persistent records, bundled seed records, example catalog records, and documentation-only reference records may all appear in this workspace panel.",
        "Bridge fields shown below keep record identifier, catalog reference context, source/review context, evidence metadata, and project documentation note visible in one place.",
        "Linked catalog reference rows keep metadata gaps visible for human review; they do not endorse or select assets, verify sources, or judge downstream-use state.",
        "Add Component Library promoter asset reference",
        "Select Component Library promoter asset reference",
        "Component Library promoter asset reference role",
        "Component Library promoter asset project documentation context",
        "Add Component Library promoter asset documentation reference",
        "Component Library Promoter Asset Readback",
        "Component Library promoter asset context is shown separately from the generic linked catalog asset table",
        "Compact Component Library promoter asset readback for project review",
        "No Component Library promoter asset context readback rows are available for the current linked catalog assets.",
        "Generic linked catalog references remain visible below as documentation-only references.",
        "No Component Library promoter asset references are linked yet. Generic linked catalog references, if present, remain listed below as documentation-only references.",
        "Documentation-only context. This readback is not a promoter recommendation",
        "not a host compatibility proof",
        "not an expression prediction",
        "not experimental validation",
        "not a wet-lab readiness judgment",
        "Component Library promoter asset",
        "Species or clade context",
        "Tissue evidence context",
        "Source/review metadata",
        "Metadata gap",
        "Manual review note",
        "Links needing human review",
        "Asset display name",
        "Linked reference",
        "Asset type",
        "Record identifier",
        "Linkage role",
        "Reference origin",
        "Project documentation context",
        "Catalog source/status",
        "Documentation note",
        "Source context snapshot",
        "Review status snapshot",
        "Human review required",
    ]
    for text in required:
        assert text in combined_source


def test_linked_catalog_assets_section_safety_copy_preserved() -> None:
    section_source = _read(SECTION)
    forbidden = [
        "recommended promoter",
        "best promoter",
        "optimized promoter",
        "ranked promoter",
        "host compatible promoter",
        "validated promoter",
        "expression-optimized",
        "ready for wet lab",
        "ready for synthesis",
        "experimentally confirmed",
    ]
    for text in forbidden:
        assert text not in section_source.lower()

    standalone_framing = [
        "Add Plant Promoter Catalog reference",
        "Compact promoter catalog context readback",
        "Plant promoter profile context is shown separately",
        "No plant promoter profile references are linked yet",
        "Promoter / catalog label",
    ]
    for text in standalone_framing:
        assert text not in section_source

    required_negative_boundaries = [
        "not a promoter recommendation",
        "not a host compatibility proof",
        "not an expression prediction",
        "not experimental validation",
        "not a wet-lab readiness judgment",
    ]
    lowered = section_source.lower()
    for text in required_negative_boundaries:
        assert text in lowered
