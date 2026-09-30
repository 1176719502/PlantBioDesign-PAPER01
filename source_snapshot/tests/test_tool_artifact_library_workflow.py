import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.tool_artifact_library_presenter import (
    artifact_save_success_message,
    filter_documentation_artifacts,
)

WORKFLOW_FILES = [
    ROOT / "services" / "tool_artifact_library_presenter.py",
    ROOT / "views" / "Data.py",
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "views" / "StructureAnalysis.py",
    ROOT / "views" / "pathway_workspace_sections" / "linked_artifacts_section.py",
]

IMPORT_SAFETY_FILES = [
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "views" / "Data.py",
    ROOT / "services" / "tool_artifact_library_presenter.py",
]


def _read(paths):
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_artifact_library_safety_copy():
    text = _read(WORKFLOW_FILES)

    required = [
        "Documentation artifacts are saved review records only.",
        "They do not certify experimental readiness.",
        "They do not predict yield.",
        "They do not optimize pathways.",
        "They do not provide wet-lab protocols.",
        "Linked artifacts are documentation records connected to a pathway project for traceability.",
    ]
    for phrase in required:
        assert phrase in text


def test_search_filter_empty_state_copy_and_in_memory_filtering():
    text = _read(WORKFLOW_FILES)

    required = [
        "Search saved documentation artifacts",
        "Filter by artifact type",
        "Filter by linked project",
        "Show unlinked documentation artifacts",
        "No saved documentation artifacts yet.",
        "No linked documentation artifacts for this project yet.",
        "Use tool pages to create documentation artifacts",
        "traceability",
    ]
    for phrase in required:
        assert phrase in text

    artifacts = [
        {
            "artifact_id": 1,
            "artifact_type": "lab_tools_pcr_preview",
            "title": "PCR review",
            "source_module": "Lab Tools",
            "summary": "primer documentation",
            "project_id": 42,
        },
        {
            "artifact_id": 2,
            "artifact_type": "protein_structure_analysis",
            "title": "Structure review",
            "source_module": "Structure Analysis",
            "summary": "folding documentation",
            "project_id": None,
        },
    ]

    assert [item["artifact_id"] for item in filter_documentation_artifacts(artifacts, search_query="primer")] == [1]
    assert [item["artifact_id"] for item in filter_documentation_artifacts(artifacts, artifact_type="protein_structure_analysis")] == [2]
    assert [item["artifact_id"] for item in filter_documentation_artifacts(artifacts, linked_project="42")] == [1]
    assert [item["artifact_id"] for item in filter_documentation_artifacts(artifacts, show_unlinked=True)] == [2]


def test_detail_preview_copy():
    text = _read(WORKFLOW_FILES)

    required = [
        "detail preview",
        "traceability only",
        "documentation record only",
        "record type",
        "created from",
        "linked project",
    ]
    for phrase in required:
        assert phrase in text


def test_delete_confirmation_copy():
    text = _read(WORKFLOW_FILES)

    required = [
        "This removes the saved documentation artifact only.",
        "It does not delete the linked pathway project.",
        "It does not certify or change experimental readiness.",
        "This action does not affect import/export package safety.",
    ]
    for phrase in required:
        assert phrase in text


def test_project_linked_artifact_boundary():
    text = _read(WORKFLOW_FILES)

    required = [
        "Linked artifact = documentation record connected to a pathway project",
        "Linked artifacts support traceability only.",
        "Linked artifacts remain review records only.",
        "They do not increase readiness or evidence score as experimental proof.",
    ]
    for phrase in required:
        assert phrase in text


def test_artifact_save_success_message_keeps_documentation_only_context():
    message = artifact_save_success_message(12, project_id=5)

    required = [
        "Saved documentation artifact #12.",
        "Artifact saved as a documentation artifact.",
        "reviewed in linked project context",
        "Pathway Project 5",
        "Pathway Workspace linked documentation artifacts",
        "documentation-only",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
    ]
    for phrase in required:
        assert phrase in message


def test_lab_tools_dormant_artifact_boundary_copy_is_present():
    text = _read([ROOT / "views" / "LabTools.py", ROOT / "services" / "tool_artifact_library_presenter.py"])

    required = [
        "Lab Tools is a dormant / V1 frozen / documentation artifact preview surface.",
        "not the current mainline tool path",
        "not a wet-lab execution workflow",
        "saved as documentation artifacts",
        "reviewed in linked project context",
        "visible from Pathway Workspace linked documentation artifacts",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
    ]
    for phrase in required:
        assert phrase in text


def test_structure_analysis_artifact_copy_frames_local_review_context():
    text = _read(WORKFLOW_FILES)

    required = [
        "Documentation-only inspection and structure review helper",
        "PDB and uploaded structure results are local documentation review context.",
        "saved as a documentation artifact",
        "can be reviewed in linked project context",
        "visible from Pathway Workspace linked documentation artifacts",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
        "Pathway Workspace / Linked Documentation Artifacts",
    ]
    for phrase in required:
        assert phrase in text


def test_forbidden_misleading_copy_absent():
    text = _read(WORKFLOW_FILES)

    forbidden = [
        "Save " + "Validation",
        "Save " + "Protocol",
        "Save " + "Experiment",
        "Save " + "Result",
        "Delete " + "result",
        "Delete " + "experiment",
        "Delete " + "validation",
        "successful " + "artifact",
        "validated " + "artifact",
        "experiment" + "-ready package",
        "production" + "-ready package",
        "validated " + "project",
        "readiness " + "confirmed",
        "yield prediction " + "result",
        "wet-lab protocol " + "generated",
    ]
    for phrase in forbidden:
        assert phrase not in text


def test_import_safety_still_locked():
    text = _read(IMPORT_SAFETY_FILES)

    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import_as_new" + "_project",
        "Import " + "Project",
        "Execute " + "Import",
        "Confirm " + "Import",
        "Import " + "now",
        "Ready " + "to import",
        "Ready " + "for execution",
    ]
    for phrase in forbidden:
        assert phrase not in text
