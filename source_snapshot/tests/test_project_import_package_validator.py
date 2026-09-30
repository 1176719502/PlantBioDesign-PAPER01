from __future__ import annotations

import json
import os
import sys
import zipfile
from io import BytesIO

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_package_validator import validate_project_import_package


def _payload() -> dict:
    return build_project_export_payload(
        project={"id": 5, "name": "Terpene Pathway", "target_product": "Demo Product", "host": "E.coli", "status": "draft"},
        steps=[{"id": 10, "project_id": 5, "step_order": 1, "step_name": "First step", "gene_sequence": "ATGAAATAA"}],
        expression_links=[{"id": 100, "step_id": 10, "design_id": 77, "design_name": "Linked design"}],
        test_records=[{"id": 200, "step_id": 10, "sample_name": "Observation"}],
        completeness_result={"score": 80, "status": "partial", "missing_items": [], "step_summaries": []},
        review_signals=[],
        linked_tool_artifacts=[
            {
                "created_at": "2026-06-02T10:00:00",
                "artifact_type": "protein_structure_analysis",
                "source_module": "Structure Analysis",
                "title": "Structure Preview",
                "summary": "Documentation preview summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 5,
                "payload_json": {"sequence_properties": {"length": 120}},
            }
        ],
        documentation_report="# Pathway Documentation Report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _zip_with_overrides(*, remove: set[str] | None = None, replace: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> bytes:
    base_zip = build_project_export_zip(_payload())
    remove = remove or set()
    replace = replace or {}
    extra = extra or {}
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(base_zip), "r") as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name in remove:
                continue
            target.writestr(name, replace.get(name, source.read(name)))
        for name, content in extra.items():
            target.writestr(name, content)
    return buffer.getvalue()


def test_valid_export_zip_accepted():
    report = validate_project_import_package(build_project_export_zip(_payload()))

    assert report["is_valid"] is True
    assert report["errors"] == []
    assert report["package_version"] == "1.0"
    assert report["project_name"] == "Terpene Pathway"
    assert report["boundary_confirmed"] is True
    assert report["json_files_valid"] is True
    assert report["unsafe_files"] == []


def test_missing_manifest_rejected():
    report = validate_project_import_package(_zip_with_overrides(remove={"manifest.json"}))

    assert report["is_valid"] is False
    assert any("manifest.json" in error for error in report["errors"])


def test_missing_readme_boundary_rejected():
    report = validate_project_import_package(_zip_with_overrides(remove={"README_BOUNDARY.txt"}))

    assert report["is_valid"] is False
    assert report["boundary_confirmed"] is False
    assert any("README_BOUNDARY.txt" in error for error in report["errors"])


def test_unsupported_package_version_rejected():
    payload = _payload()
    payload["manifest"]["package_version"] = "999.0"
    report = validate_project_import_package(build_project_export_zip(payload))

    assert report["is_valid"] is False
    assert report["package_version"] == "999.0"
    assert any("Unsupported package_version" in error for error in report["errors"])


def test_malformed_json_rejected():
    report = validate_project_import_package(_zip_with_overrides(replace={"project_summary.json": "{"}))

    assert report["is_valid"] is False
    assert report["json_files_valid"] is False
    assert any("Malformed JSON file: project_summary.json" in error for error in report["errors"])


def test_path_traversal_filename_rejected():
    report = validate_project_import_package(_zip_with_overrides(extra={"nested/../../evil.txt": "evil"}))

    assert report["is_valid"] is False
    assert "nested/../../evil.txt" in report["unsafe_files"]


def test_windows_absolute_path_rejected():
    report = validate_project_import_package(_zip_with_overrides(extra={r"C:\evil.txt": "evil"}))

    assert report["is_valid"] is False
    assert any(filename in {r"C:\evil.txt", "C:/evil.txt"} for filename in report["unsafe_files"])


def test_executable_file_rejected_and_marked_unsafe():
    report = validate_project_import_package(_zip_with_overrides(extra={"scripts/run.sh": "echo unsafe"}))

    assert report["is_valid"] is False
    assert "scripts/run.sh" in report["unsafe_files"]


def test_linked_tool_artifacts_payload_json_rejected():
    unsafe_artifacts = {
        "documentation_only_boundary": "Linked artifacts are computational previews / review records only.",
        "linked_tool_artifacts": [{"title": "Unsafe", "payload_json": {"raw": "payload"}, "readable_payload_summary": []}],
    }
    report = validate_project_import_package(
        _zip_with_overrides(replace={"linked_tool_artifacts.json": json.dumps(unsafe_artifacts)})
    )

    assert report["is_valid"] is False
    assert any("payload_json" in error for error in report["errors"])


def test_readme_boundary_missing_required_phrase_rejected():
    readme = "This export package is documentation-only. It does not certify experimental readiness."
    report = validate_project_import_package(_zip_with_overrides(replace={"README_BOUNDARY.txt": readme}))

    assert report["is_valid"] is False
    assert report["boundary_confirmed"] is False
    assert any("does not predict yield" in error for error in report["errors"])
    assert any("does not optimize pathways" in error for error in report["errors"])
    assert any("does not provide wet-lab protocols" in error for error in report["errors"])


def test_validation_is_read_only_without_repository_or_database_writes(monkeypatch):
    import services.project_import_package_validator as validator

    def fail_write(*args, **kwargs):
        raise AssertionError("validator attempted a write")

    monkeypatch.setattr(validator, "open", fail_write, raising=False)
    report = validator.validate_project_import_package(build_project_export_zip(_payload()))

    assert report["is_valid"] is True


def test_report_contains_documentation_only_boundary_language():
    report = validate_project_import_package(build_project_export_zip(_payload()))
    boundary = report["documentation_only_boundary"]

    assert "documentation-only" in boundary
    assert "read-only" in boundary
    assert "does not certify experimental readiness" in boundary
    assert "does not validate the pathway" in boundary
    assert "does not predict yield" in boundary
    assert "does not optimize pathways" in boundary
    assert "does not provide wet-lab protocols" in boundary
