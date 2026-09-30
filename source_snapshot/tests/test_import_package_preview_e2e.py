from __future__ import annotations

import copy
import io
import json
import os
import sys
import zipfile
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import README_BOUNDARY_TEXT, build_project_export_payload, build_project_export_zip
from services.project_import_package_validator import validate_project_import_package
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace
from views.pathway_workspace_sections import import_preview_section

TEST_README_BOUNDARY_TEXT = README_BOUNDARY_TEXT.replace("wet-lab instructions", "wet-lab protocols")


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(import_preview_section, "st", fake_st)
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


def _minimal_payload() -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 42,
            "name": "Preview E2E Project",
            "target_product": "Demo product",
            "host": "Demo host",
            "status": "draft",
            "description": "Preview test project.",
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
        expression_links=[],
        test_records=[],
        completeness_result={"score": 50, "status": "partial", "missing_items": [], "step_summaries": []},
        review_signals=[],
        linked_tool_artifacts=[],
        documentation_report="# Documentation report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _valid_zip_bytes() -> bytes:
    payload = _minimal_payload()
    payload["readme_boundary"] = TEST_README_BOUNDARY_TEXT
    return build_project_export_zip(payload)


def _zip_without(*excluded_names: str) -> bytes:
    excluded = set(excluded_names)
    source = _valid_zip_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as src, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name not in excluded:
                dst.writestr(name, src.read(name))
    return buffer.getvalue()


def _zip_with_extra_file(filename: str, data: str = "unsafe") -> bytes:
    source = _valid_zip_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as src, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr(filename, data)
    return buffer.getvalue()


def _zip_with_payload_json_artifact() -> bytes:
    payload = _minimal_payload()
    linked_tool_artifacts = copy.deepcopy(payload["linked_tool_artifacts"])
    linked_tool_artifacts["linked_tool_artifacts"] = [
        {
            "title": "Unsafe raw artifact",
            "readable_payload_summary": [],
            "payload_json": {"raw": "must not be imported"},
        }
    ]
    payload["linked_tool_artifacts"] = linked_tool_artifacts
    return build_project_export_zip(payload)


def _render_report_for_zip(monkeypatch, zip_bytes: bytes) -> tuple[FakeStreamlit, dict[str, Any]]:
    fake_st = _install_fake_streamlit(monkeypatch)
    report = validate_project_import_package(zip_bytes)
    pathway_workspace._render_import_validation_report(report)
    return fake_st, report


def test_valid_export_zip_end_to_end_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _valid_zip_bytes())

    assert report["is_valid"] is True
    ui_text = _rendered_text(fake_st)
    for expected in [
        "Valid package",
        "package_version: 1.0",
        "project_name: Preview E2E Project",
        "boundary_confirmed: True",
        "json_files_valid: True",
        "No validation errors found.",
        "No unsafe files detected.",
    ]:
        assert expected in ui_text


def test_valid_export_zip_preview_upload_path_includes_read_only_copy(monkeypatch):
    class UploadedZip:
        def getvalue(self) -> bytes:
            return _valid_zip_bytes()

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.file_uploader_value = UploadedZip()

    pathway_workspace._render_import_package_preview()

    ui_text = _rendered_text(fake_st)
    for expected in [
        "Valid package",
        "This preview does not import or modify any project.",
        "Dry-run import plan",
        "Proposed: Imported - Preview E2E Project",
        "Would create preview",
        "Project 1",
        "Pathway steps",
        "Test record summaries",
        "Linked expression references",
        "Linked tool artifact summaries",
        "Mode: import as new project only",
        "Read-only",
        "No database writes are performed.",
        "documentation-only",
        "read-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "computational previews",
        "review records only",
        "A separate gated action below may create a local documentation-only project only after package validation, safety review, dry-run planning, and explicit final confirmation.",
        "If a blocked state is shown below, it applies only to the separate gated create-as-new action",
    ]:
        assert expected in ui_text
    assert fake_st.rerun_calls == 0
    assert len(fake_st.button_calls) == 1
    assert fake_st.button_calls[0]["label"] == "Create New Documentation Project"
    assert fake_st.button_calls[0]["disabled"] is True


def test_missing_manifest_invalid_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _zip_without("manifest.json"))

    assert report["is_valid"] is False
    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "Errors" in ui_text
    assert "manifest.json" in ui_text


def test_missing_readme_boundary_invalid_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _zip_without("README_BOUNDARY.txt"))

    assert report["is_valid"] is False
    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "README_BOUNDARY.txt" in ui_text


def test_invalid_upload_path_does_not_show_create_counts(monkeypatch):
    class UploadedZip:
        def getvalue(self) -> bytes:
            return _zip_without("manifest.json")

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.file_uploader_value = UploadedZip()

    pathway_workspace._render_import_package_preview()

    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "manifest.json" in ui_text
    assert "Would create" not in ui_text
    assert "Project: 1" not in ui_text
    assert "Pathway steps:" not in ui_text


def test_import_dry_run_plan_unavailable_shows_validation_only_without_counts(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    pathway_workspace._render_import_dry_run_plan({"is_plan_available": False})

    ui_text = _rendered_text(fake_st)
    assert "Validation-only preview" in ui_text
    assert "Would create" not in ui_text
    assert "Project: 1" not in ui_text


def test_path_traversal_invalid_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _zip_with_extra_file("nested/../../evil.txt"))

    assert report["is_valid"] is False
    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "Unsafe files" in ui_text
    assert "nested/../../evil.txt" in ui_text
    assert "unsafe filenames" in ui_text


def test_executable_file_invalid_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _zip_with_extra_file("evil.ps1"))

    assert report["is_valid"] is False
    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "Unsafe files" in ui_text
    assert "evil.ps1" in ui_text
    assert "executable payloads" in ui_text


def test_payload_json_rejected_preview(monkeypatch):
    fake_st, report = _render_report_for_zip(monkeypatch, _zip_with_payload_json_artifact())

    assert report["is_valid"] is False
    ui_text = _rendered_text(fake_st)
    assert "Invalid package" in ui_text
    assert "linked_tool_artifacts.json" in ui_text
    assert "payload_json" in ui_text


def test_import_preview_static_read_only_guard():
    preview_source = open(import_preview_section.__file__, encoding="utf-8").read()
    for forbidden in [
        "Import Project",
        "Create Imported Project",
        "Merge Project",
        "Overwrite Project",
        "create_project",
        "update_project",
        "delete_project",
        "insert",
        "update",
        "delete",
        "commit",
    ]:
        assert forbidden not in preview_source


def test_import_preview_boundary_copy_remains_safe():
    preview_source = open(import_preview_section.__file__, encoding="utf-8").read()
    combined_text = f"{preview_source}\n{README_BOUNDARY_TEXT}"
    for expected in [
        "documentation-only",
        "read-only",
        "does not import or modify any project",
        "No database writes are performed",
        "A separate gated action below may create a local documentation-only project only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
    ]:
        assert expected in combined_text.replace("wet-lab instructions", "wet-lab protocols")
