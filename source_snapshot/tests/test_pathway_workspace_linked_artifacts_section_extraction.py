from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTION = ROOT / "views" / "pathway_workspace_sections" / "linked_artifacts_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_linked_artifacts_section_exists_and_is_delegated() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert SECTION.exists()
    assert "from views.pathway_workspace_sections.linked_artifacts_section import render_linked_artifacts_section" in source
    assert "render_linked_artifacts_section(project.get(\"id\"))" in source


def test_linked_documentation_artifacts_copy_preserved() -> None:
    section_source = _read(SECTION)
    assert "Linked Documentation Artifacts" in section_source
    assert "documentation records" in section_source
    assert "traceability" in section_source
    assert "review records" in section_source
    assert "PROJECT_LINKED_ARTIFACT_BOUNDARY_COPY" in section_source
    assert "does not certify experimental readiness" in section_source
    assert "does not predict yield" in section_source
    assert "does not optimize pathways" in section_source
    assert "does not provide wet-lab protocols" in section_source


def test_linked_artifacts_section_no_forbidden_import_execution_strings() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(SECTION), _read(Path(__file__))])
    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "successful" + " import",
        "import" + " succeeded",
        "project" + " imported",
    ]
    for text in forbidden:
        assert text not in source


def test_linked_artifacts_section_no_readiness_score_or_wet_lab_misleading_copy() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(SECTION), _read(Path(__file__))])
    forbidden = [
        "Quality" + " Score",
        "Evidence" + " Score",
        "Readiness" + " Score",
        "Validation" + " Score",
        "Experiment" + " Ready",
        "Production" + " Ready",
        "validated" + " construct",
        "successful" + " cloning",
        "successful" + " PCR",
        "successful" + " expression",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    for text in forbidden:
        assert text not in source


def test_linked_catalog_assets_section_is_present_and_delegated() -> None:
    source = _read(PATHWAY_WORKSPACE)
    section = ROOT / "views" / "pathway_workspace_sections" / "linked_catalog_assets_section.py"
    assert section.exists()
    assert "from views.pathway_workspace_sections.linked_catalog_assets_section import render_linked_catalog_assets_section" in source
    assert "Linked Catalog Assets" in source
