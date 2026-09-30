from __future__ import annotations

import copy
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_dry_run_planner import build_project_import_dry_run_plan
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace
from views.pathway_workspace_sections import import_preview_section
from views.pathway_workspace_sections import import_safety_section

ROOT_PATH = Path(ROOT)
PATHWAY_WORKSPACE = ROOT_PATH / "views" / "PathwayWorkspace.py"
VALIDATOR = ROOT_PATH / "services" / "project_import_package_validator.py"
DRY_RUN_PLANNER = ROOT_PATH / "services" / "project_import_dry_run_planner.py"
DESIGN_DOC = ROOT_PATH / "docs" / "project_import_package_design.md"
IMPORT_PREVIEW_SECTION = ROOT_PATH / "views" / "pathway_workspace_sections" / "import_preview_section.py"
IMPORT_SAFETY_SECTION = ROOT_PATH / "views" / "pathway_workspace_sections" / "import_safety_section.py"
IMPORT_RELATED_FILES = (PATHWAY_WORKSPACE, IMPORT_PREVIEW_SECTION, IMPORT_SAFETY_SECTION, VALIDATOR, DRY_RUN_PLANNER, DESIGN_DOC)
CODE_FILES = (PATHWAY_WORKSPACE, IMPORT_PREVIEW_SECTION, IMPORT_SAFETY_SECTION, VALIDATOR, DRY_RUN_PLANNER)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_preview_source() -> str:
    return "\n".join([_read(IMPORT_PREVIEW_SECTION), _read(IMPORT_SAFETY_SECTION)])


def _combined_import_text(paths: tuple[Path, ...] = IMPORT_RELATED_FILES) -> str:
    return "\n".join(_read(path) for path in paths)


def _minimal_payload() -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 42,
            "name": "Safety Regression Project",
            "target_product": "Demo product",
            "host": "Demo host",
            "status": "draft",
            "description": "Import safety regression fixture.",
        },
        steps=[
            {
                "id": 7,
                "project_id": 42,
                "step_order": 1,
                "step_name": "Recorded step",
                "reaction_name": "A to B",
                "substrate": "A",
                "product": "B",
                "enzyme_name": "Demo enzyme",
                "gene_name": "demo_gene",
                "gene_sequence": "ATGAAATAA",
            }
        ],
        expression_links=[{"id": 8, "step_id": 7, "design_id": 99, "design_name": "Design reference"}],
        test_records=[{"id": 9, "step_id": None, "sample_name": "Project observation"}],
        completeness_result={"score": 50, "status": "partial", "missing_items": [], "step_summaries": []},
        review_signals=[],
        linked_tool_artifacts=[
            {
                "created_at": "2026-06-02T10:00:00",
                "artifact_type": "codon_analysis",
                "source_module": "Lab Tools",
                "title": "Codon Preview",
                "summary": "Documentation codon summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 42,
                "payload_json": {"gc_content": 0.5},
            }
        ],
        documentation_report="# Documentation report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _valid_zip_bytes() -> bytes:
    return build_project_export_zip(_minimal_payload())


def _invalid_zip_without_manifest() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_valid_zip_bytes()), "r") as source, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            if name != "manifest.json":
                target.writestr(name, source.read(name))
    return buffer.getvalue()


def _zip_with_payload_json_artifact() -> bytes:
    payload = _minimal_payload()
    linked_tool_artifacts = copy.deepcopy(payload["linked_tool_artifacts"])
    linked_tool_artifacts["linked_tool_artifacts"] = [
        {
            "title": "Unsafe raw artifact",
            "readable_payload_summary": [],
            "payload_json": {"raw": "must not be restored"},
        }
    ]
    payload["linked_tool_artifacts"] = linked_tool_artifacts
    return build_project_export_zip(payload)


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(import_preview_section, "st", fake_st)
    monkeypatch.setattr(import_safety_section, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.file_uploader_calls]
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
    )


def test_no_real_import_controls_in_preview_ui_source() -> None:
    preview_source = _import_preview_source()

    forbidden_controls = [
        "Import Project",
        "Create Imported Project",
        "Merge Project",
        "Overwrite Project",
        "Confirm Import",
        "Execute Import",
        "Restore Project",
    ]

    assert not [control for control in forbidden_controls if control in preview_source]
    assert "st.button" in preview_source
    assert "Create New Documentation Project" in preview_source
    assert "enable_database_write=True" in preview_source
    assert "execute_project_import_as_new_project" in preview_source


def test_import_preview_validator_and_planner_have_no_database_write_calls() -> None:
    dangerous_call_patterns = [
        "create_project(",
        "update_project(",
        "delete_project(",
        "save_project(",
        "insert(",
        "update(",
        "delete(",
        "commit(",
        "execute(",
        "executemany(",
        "persist(",
        "migrate(",
        ".insert(",
        ".update(",
        ".delete(",
        ".commit(",
        ".execute(",
        ".executemany(",
        ".persist(",
        ".migrate(",
    ]
    dangerous_terms = ["sqlite"]
    scanned_sources = {
        "PathwayWorkspace.import_preview": _import_preview_source(),
        str(VALIDATOR): _read(VALIDATOR),
        str(DRY_RUN_PLANNER): _read(DRY_RUN_PLANNER),
    }

    offenders: dict[str, list[str]] = {}
    for name, source in scanned_sources.items():
        source_lower = source.lower()
        found = [pattern for pattern in dangerous_call_patterns if pattern in source_lower]
        found.extend(term for term in dangerous_terms if term in source_lower)
        if found:
            offenders[name] = found

    assert offenders == {}


def test_no_overwrite_or_merge_behavior_positive_semantics() -> None:
    combined_lower = _combined_import_text().lower()
    forbidden_positive_phrases = [
        "overwrite existing project",
        "merge into existing project",
        "merge project",
        "update existing project",
        "replace project",
    ]
    allowed_negative_boundaries = [
        "no overwrite",
        "no merge",
        "does not overwrite",
        "does not merge",
        "must not overwrite",
        "must not merge",
        "not overwritten",
    ]

    for allowed in allowed_negative_boundaries:
        combined_lower = combined_lower.replace(allowed, "")

    assert not [phrase for phrase in forbidden_positive_phrases if phrase in combined_lower]


def test_no_raw_payload_restoration_in_preview_or_dry_run_plan() -> None:
    preview_and_planner = f"{_import_preview_source()}\n{_read(DRY_RUN_PLANNER)}".lower()
    forbidden_restoration_phrases = [
        "raw payload restoration",
        "full raw payload",
        "developer payload restoration",
        "restore raw payload",
        "restores raw payload",
    ]

    assert not [phrase for phrase in forbidden_restoration_phrases if phrase in preview_and_planner]

    plan = build_project_import_dry_run_plan(_zip_with_payload_json_artifact())
    rendered_plan = repr(plan)
    assert plan["is_plan_available"] is False
    assert plan["would_create"] == {}
    assert "payload_json" in "\n".join(plan["errors"])
    assert "payload_json" not in rendered_plan.replace("'linked_tool_artifacts.json must not include raw payload_json.'", "")


def test_documentation_only_boundaries_present_in_import_services_and_ui() -> None:
    required_phrases = [
        "documentation-only",
        "read-only",
        "no database writes",
        "no project creation during preview",
        "no overwrite",
        "no merge",
        "no readiness boost",
        "no validation claim",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab instructions",
        "computational previews",
        "review records only",
    ]

    combined_code_lower = _combined_import_text(CODE_FILES).lower()
    assert not [phrase for phrase in required_phrases if phrase not in combined_code_lower]

    scanned_files_with_boundaries = (PATHWAY_WORKSPACE, IMPORT_PREVIEW_SECTION, IMPORT_SAFETY_SECTION)
    for path in scanned_files_with_boundaries:
        source_lower = _read(path).lower()
        assert "documentation-only" in source_lower
        assert ("does not provide wet-lab instructions" in source_lower) or (
            "does not provide wet-lab protocols" in source_lower
        )


def test_dry_run_plan_remains_non_mutating_and_requires_id_remapping() -> None:
    plan = build_project_import_dry_run_plan(_valid_zip_bytes())

    assert plan["is_plan_available"] is True
    assert plan["read_only"] is True
    assert plan["database_writes_performed"] is False
    assert plan["import_mode"] == "import_as_new_project_only"
    assert plan["id_remapping_required"] == {
        "project_id": True,
        "pathway_step_ids": True,
        "linked_tool_artifact_ids": True,
        "test_record_ids": True,
    }


def test_invalid_package_never_produces_create_counts_or_ui_create_counts(monkeypatch) -> None:
    class UploadedZip:
        def getvalue(self) -> bytes:
            return _invalid_zip_without_manifest()

    plan = build_project_import_dry_run_plan(_invalid_zip_without_manifest())
    assert plan["is_plan_available"] is False
    assert plan["would_create"] == {}

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.file_uploader_value = UploadedZip()
    pathway_workspace._render_import_package_preview()

    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "Would create" not in ui_text
    assert "Project: 1" not in ui_text


def test_import_preview_ui_remains_validation_and_dry_run_only(monkeypatch) -> None:
    class UploadedZip:
        def getvalue(self) -> bytes:
            return _valid_zip_bytes()

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.file_uploader_value = UploadedZip()
    pathway_workspace._render_import_package_preview()

    ui_text = _rendered_text(fake_st)
    for expected in [
        "Project Import Package Preview",
        "Pathway Workspace > Project Outputs > Import Preview",
        "documentation-only package inspection for validation and dry-run planning",
        "The preview step itself does not create a project",
        "Validation status",
        "Dry-run import plan",
        "This preview does not import or modify any project.",
        "No database writes are performed.",
        "A separate gated action below may create a local documentation-only project only after package validation, safety review, dry-run planning, and explicit final confirmation.",
        "If a blocked state is shown below, it applies only to the separate gated create-as-new action",
    ]:
        assert expected in ui_text
    assert len(fake_st.button_calls) == 1
    assert fake_st.button_calls[0]["label"] == "Create New Documentation Project"
    assert fake_st.button_calls[0]["disabled"] is True
    assert fake_st.rerun_calls == 0


def test_import_preview_blocked_state_copy_does_not_mix_no_go_with_allowed_creation() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)

    assert "Preview/review blocked: safety review is blocked, so no local documentation project will be created." in source
    assert "Preview/review blocked for local documentation project creation." in source
    assert "Local documentation project creation allowed after explicit confirmation." in source
    assert "Execution remains disabled in this build." not in source
    assert "future gated action preview only" not in source


def test_forbidden_product_claims_absent_from_preview_and_dry_run_positive_claims() -> None:
    import_surface = f"{_import_preview_source()}\n{_read(DRY_RUN_PLANNER)}".lower()
    allowed_negative_claims = [
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "not experimental recommendations",
    ]
    forbidden_claims = [
        "experiment-ready",
        "production-ready",
        "validated pathway",
        "yield prediction result",
        "optimized pathway",
        "wet-lab protocol provided",
        "successful cloning",
        "successful pcr",
        "successful expression",
    ]

    for allowed in allowed_negative_claims:
        import_surface = import_surface.replace(allowed, "")

    assert not [claim for claim in forbidden_claims if claim in import_surface]


def test_design_doc_remains_aligned_with_import_safety_scope() -> None:
    doc_lower = _read(DESIGN_DOC).lower()
    required_phrases = [
        "import as new project only",
        "no overwrite",
        "no merge",
        "path traversal",
        "executable files",
        "malformed json",
        "project_id remapping",
        "linked tool artifact id remapping",
        "dry-run planner",
    ]

    assert not [phrase for phrase in required_phrases if phrase not in doc_lower]
    assert "does not write database" in doc_lower or "no database writes" in doc_lower
