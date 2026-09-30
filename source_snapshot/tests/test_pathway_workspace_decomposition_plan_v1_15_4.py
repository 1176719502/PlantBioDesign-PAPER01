from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "pathway_workspace_decomposition_plan_v1_15_4.md"
TEST = ROOT / "tests" / "test_pathway_workspace_decomposition_plan_v1_15_4.py"


def _doc_source() -> str:
    return DOC.read_text(encoding="utf-8")


def test_decomposition_plan_document_exists() -> None:
    assert DOC.exists()


def test_decomposition_plan_required_sections_are_present() -> None:
    source = _doc_source()

    required = [
        "Executive summary",
        "Current PathwayWorkspace responsibilities",
        "Current risks",
        "Proposed target module layout",
        "Extraction principles",
        "Recommended extraction sequence",
        "Safety boundaries to preserve",
        "Regression test gate",
        "Manual UI smoke gate",
        "GO / NO-GO summary",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_current_responsibilities_are_covered() -> None:
    source = _doc_source()

    required = [
        "Project Export Package",
        "Project Import Package Preview",
        "Import Package Safety Check Report",
        "Project Review Report",
        "Project Quality Dashboard",
        "linked documentation artifacts",
        "documentation snapshots",
        "delete/confirmation flows",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_target_module_layout_is_covered() -> None:
    source = _doc_source()

    required = [
        "views/pathway_workspace_sections/project_header.py",
        "views/pathway_workspace_sections/empty_state.py",
        "views/pathway_workspace_sections/linked_artifacts_section.py",
        "views/pathway_workspace_sections/export_package_section.py",
        "views/pathway_workspace_sections/import_preview_section.py",
        "views/pathway_workspace_sections/project_review_report_section.py",
        "views/pathway_workspace_sections/project_quality_dashboard_section.py",
        "services/pathway_workspace_presenter.py",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_extraction_sequence_is_covered() -> None:
    source = _doc_source()

    required = [
        "V1.15.5 Extract Project Quality Dashboard section",
        "V1.15.6 Extract Project Review Report section",
        "V1.15.7 Extract Import Preview and Safety Check section",
        "V1.15.8 Extract Export Package section",
        "V1.15.9 Extract Linked Artifacts section",
        "V1.15.10 Extract Project Header and Empty State section",
        "V1.15.11 PathwayWorkspace RC sanity sweep",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_safety_boundaries_are_covered() -> None:
    source = _doc_source()

    required = [
        "documentation-only",
        "review records only",
        "computational previews only",
        "read-only safety check",
        "no database writes by preview",
        "no project creation by preview",
        "Real import execution remains disabled / NO-GO.",
        "no overwrite",
        "no merge",
        "no raw payload_json restoration",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_go_no_go_summary_is_covered() -> None:
    source = _doc_source()

    required = [
        "PathwayWorkspace decomposition planning: GO.",
        "Immediate large refactor: NO-GO.",
        "One-section-at-a-time extraction: GO.",
        "Mixing extraction with new features: NO-GO.",
        "Real import execution: NO-GO.",
        "DB schema migration: NO-GO.",
    ]
    for text in required:
        assert text in source


def test_decomposition_plan_changes_do_not_enable_import_execution() -> None:
    combined_source = _doc_source() + "\n" + TEST.read_text(encoding="utf-8")

    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
    ]
    for text in forbidden:
        assert text not in combined_source
