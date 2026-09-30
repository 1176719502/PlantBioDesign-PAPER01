from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COPY_TARGETS = [
    ROOT / "views" / "Data.py",
    ROOT / "views" / "DesignLibrary.py",
    ROOT / "components" / "project_manager.py",
    ROOT / "locales" / "en.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _combined() -> str:
    return "\n".join(_read(path) for path in COPY_TARGETS)


def _copy_text(text: str) -> str:
    return " ".join(text.split())


def test_parts_registry_boundary_copy_is_explicit() -> None:
    combined = _combined()

    assert "reference records" in combined
    assert "documentation-only registry records" in combined
    assert "do not certify experimental readiness" in combined
    assert "design support" in combined


def test_data_page_distinguishes_registry_from_local_design_asset_catalog() -> None:
    combined = _combined()

    assert "Component Library brings together separate documentation surfaces" in combined
    assert "Source family: Parts Registry saved rows" in combined
    assert "Source family: Local Design Asset Catalog." in combined
    assert "Source family: Plant Promoter Catalog." in combined
    assert "Bundled asset records" in combined
    assert "Filtered table rows" in combined
    assert "Saved bundled asset records stay separate from filtered table rows" in combined
    assert "Source/provenance review rows" in combined
    assert "Computed readback rows" in combined
    assert "Plant component/source/provenance review" in combined
    assert "Core component browsing" in combined
    assert "Review / source follow-up" in combined
    assert "Documentation preview / readback actions" in combined
    assert "Admin / diagnostic / write controls" in combined
    assert "Selected asset documentation details" in combined
    assert "documentation-only source/provenance review context for the selected row" in combined
    assert "not experimental validation or biological approval" in combined
    assert "documentation-only review aids" in combined
    assert "These library surfaces are documentation-only review aids" in combined


def test_component_library_top_context_is_concise_and_details_are_collapsed() -> None:
    data_view = _read(ROOT / "views" / "Data.py")
    data_copy = _copy_text(data_view)
    locale_copy = _read(ROOT / "locales" / "en.py")

    assert "Plant component/source/provenance review for documentation-only plant component library records." in locale_copy
    assert "PLANT_MVP_CONTEXT_TITLE = \"Plant component/source/provenance review\"" in data_view
    assert "Plant recombinant protein / molecular farming" in data_view
    assert "Documentation-only boundary: source/provenance review and manual follow-up only" in data_view
    assert "It does not" in data_copy
    assert "recommend components" in data_copy
    assert "st.dataframe(pd.DataFrame(category_rows), hide_index=True, use_container_width=True)" in data_view
    assert "Plant component source/provenance review details" in data_view
    assert "Manual follow-up guidance" in data_view
    assert "Advanced component evidence readback" in data_view
    assert 'with st.expander("Plant component source/provenance review details", expanded=False)' in data_view
    assert 'with st.expander("Manual follow-up guidance", expanded=False)' in data_view
    assert 'with st.expander("Advanced component evidence readback", expanded=False)' in data_view
    assert 'with st.expander("Compact slot details for narrow screens", expanded=False)' in data_view


def test_component_library_uses_plant_mvp_context_framing() -> None:
    data_view = _read(ROOT / "views" / "Data.py")
    locale_copy = _read(ROOT / "locales" / "en.py")
    presenter = _read(ROOT / "services" / "component_library_slot_browse_presenter.py")
    combined = _copy_text("\n".join([data_view, locale_copy, presenter]))

    required_copy = [
        "Plant component/source/provenance review",
        "Plant recombinant protein / molecular farming",
        "documentation-only plant component library records",
        "source/provenance",
        "manual follow-up for plant expression",
        "plant component library records",
        "Plant promoter context",
        "Terminator context",
        "Signal peptide",
        "Transit peptide",
        "Subcellular targeting",
        "Selectable Marker / Reporter",
        "Vector / backbone context",
        "Plant species / host context",
        "Tissue / organ / expression compartment",
        "Expression mode",
        "Source / Provenance",
        "Manual Follow-up",
        "recommend components",
        "certify construct readiness",
        "generate protocols",
        "optimize sequences",
        "validate plant lines",
        "predict yield",
    ]
    missing = [text for text in required_copy if text not in combined]

    assert not missing


def test_component_library_plant_context_copy_avoids_unsafe_claims() -> None:
    combined = "\n".join(
        [
            _read(ROOT / "views" / "Data.py"),
            _read(ROOT / "locales" / "en.py"),
            _read(ROOT / "services" / "component_library_slot_browse_presenter.py"),
        ]
    ).casefold()

    forbidden = [
        "successful import",
        "project imported",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "validated plant line",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_component_library_frames_plant_promoters_as_assets() -> None:
    data_view = _read(ROOT / "views" / "Data.py")
    registry = _read(ROOT / "core" / "module_registry.py")

    required_data_copy = [
        "Source family: Plant Promoter Catalog.",
        "Record scope: promoter profile rows.",
        "Row granularity: profile records, tissue evidence rows, motif rows, and review rows.",
        "Review / source follow-up",
        "The Plant Promoter Catalog detail surface is plant promoter expression documentation and provenance",
        "not a promoter choice engine",
        "Plant promoter asset context",
        "Promoter asset readback is documentation-only.",
        "not a biological recommendation",
        "not compatibility proof",
        "not a validation claim",
        "not a behavior forecast",
        "not wet-lab use guidance",
    ]
    missing = [text for text in required_data_copy if text not in data_view]

    assert not missing
    assert "plant promoter assets as documentation-only Component Library records" in registry
    assert "render_plant_promoter_catalog()" in data_view


def test_data_page_exposes_generic_asset_readback_without_universal_model_claim() -> None:
    data_view = _read(ROOT / "views" / "Data.py")

    required_copy = [
        "Computed Component Library readback",
        "Generic Component Library readback summarizes Local Design Asset Catalog records as computed readback rows",
        "computed readback rows",
        "preserves source/provenance identity",
        "does not create a universal asset database model",
        "Readback asset rows",
        "Asset type groups",
        "Source/provenance rows",
        "Evidence/review rows",
    ]
    missing = [text for text in required_copy if text not in data_view]

    assert not missing
    assert "Registry admin and write controls" in data_view
    assert "Admin / diagnostic / write controls" in data_view
    assert "Admin and diagnostic tools are collapsed here so normal browsing stays first." in data_view
    assert "render_read_only_parts_catalog(show_admin=False)" in data_view
    assert "Saved documentation artifacts" in data_view


def test_data_page_keeps_registry_browse_read_only_in_the_main_surface() -> None:
    data_view = _read(ROOT / "views" / "Data.py")

    assert "render_read_only_parts_catalog(show_admin=False)" in data_view
    assert "_register_dialog()" in data_view
    assert "Admin and diagnostic tools are collapsed here so normal browsing stays first." in data_view
    assert "Documentation preview export actions" in data_view


def test_design_library_boundary_copy_is_explicit() -> None:
    combined = _combined()

    assert "documentation records" in combined
    assert "local DNA part reference records" in combined
    assert "documentation-only registry records" in combined
    assert "transient Wizard Step 2 candidates" in combined
    assert "does not certify experimental readiness" in combined
    assert "review records only" in combined
    assert "do not predict yield" in combined
    assert "do not optimize pathways" in combined
    assert "do not provide wet-lab protocols" in combined


def test_empty_states_use_safe_documentation_framing() -> None:
    combined = _combined()

    assert "No reference records found." in combined
    assert "No documentation records yet." in combined
    assert "Select a record in the table to view documentation details" in combined

    forbidden = [
        "No validated parts",
        "No successful designs",
        "No ready projects",
        "No experiment results",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_actions_use_safe_documentation_framing() -> None:
    combined = _combined()

    expected = [
        "Add Reference Record",
        "Save Documentation Record",
        "View Documentation Details",
        "Remove Record",
    ]
    assert [phrase for phrase in expected if phrase in combined]

    forbidden = [
        "Validate Part",
        "Save Validated Design",
        "Mark Ready",
        "Confirm Success",
        "Generate Protocol",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_data_page_uses_documented_pairing_context_instead_of_recommendation_label() -> None:
    data_view = _read(ROOT / "views" / "Data.py")

    assert '("Documented Pairing Context", "Documented Pairing Context")' in data_view
    assert '"Documented Pairing Context"' in data_view
    assert 'selected_row.get(\n                    "Documented Pairing Context",' in data_view
    assert 'selected_row.get("Review Pairing Notes", selected_row.get("Recommended Pairing", ""))' in data_view


def test_default_registry_pairing_text_is_documentation_context_not_pairing_instruction() -> None:
    database_source = _read(ROOT / "core" / "database.py")

    assert "Documented context: commonly recorded" in database_source
    assert 'recommended_pairing = "Pair with' not in database_source
    assert "plant-compatible CDS" not in database_source
    assert "compatible expression vector" not in database_source


def test_forbidden_registry_library_data_claims_are_absent() -> None:
    combined = _combined().lower()
    forbidden = [
        "validated part",
        "validated design",
        "optimized design",
        "ready-to-use",
        "experiment-ready",
        "production-ready",
        "successful expression design",
        "protocol generated",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
