from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_package_safety_checker import build_import_package_safety_check_report


def _payload() -> dict[str, Any]:
    return build_project_export_payload(
        project={"id": 42, "name": "Safety Checker Project", "target_product": "Demo"},
        steps=[],
        expression_links=[],
        test_records=[],
        completeness_result={},
        review_signals=[],
        linked_tool_artifacts=[{"title": "Artifact A", "payload_json": {"summary": "review"}}],
        documentation_report="# Report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _zip_from_payload(payload: dict[str, Any]) -> bytes:
    return build_project_export_zip(payload)


def _rewrite_manifest(zip_bytes: bytes, manifest: dict[str, Any] | None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name == "manifest.json":
                if manifest is not None:
                    target.writestr(name, json.dumps(manifest, ensure_ascii=False, indent=2))
            else:
                target.writestr(name, source.read(name))
    return buffer.getvalue()


def _status(report: dict[str, Any], check_id: str) -> str:
    for item in report["check_items"]:
        if item["check_id"] == check_id:
            return item["status"]
    raise AssertionError(check_id)


def test_valid_minimal_package_metadata_is_warning_not_fake_pass() -> None:
    report = build_import_package_safety_check_report(_zip_from_payload(_payload()))

    assert report["overall_status"] in {"PASS", "WARNING"}
    assert _status(report, "manifest_presence") == "PASS"
    assert _status(report, "schema_version") == "PASS"
    assert _status(report, "package_fingerprint") == "NOT_EVALUATED"
    assert _status(report, "manifest_integrity") == "NOT_EVALUATED"
    assert report["database_writes_performed"] is False


def test_missing_manifest_is_blocked() -> None:
    report = build_import_package_safety_check_report(_rewrite_manifest(_zip_from_payload(_payload()), None))

    assert report["overall_status"] == "BLOCKED"
    assert _status(report, "manifest_presence") == "BLOCKED"


def test_missing_schema_version_is_blocked() -> None:
    payload = _payload()
    payload["manifest"].pop("package_version")

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "schema_version") == "BLOCKED"


def test_unsupported_old_schema_version_is_blocked() -> None:
    payload = _payload()
    payload["manifest"]["package_version"] = "0.1"

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "schema_version") == "BLOCKED"


def test_future_package_version_is_blocked() -> None:
    payload = _payload()
    payload["manifest"]["package_version"] = "999.0"

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "schema_version") == "BLOCKED"


def test_fingerprint_mismatch_is_blocked() -> None:
    payload = _payload()
    payload["manifest"]["package_fingerprint"] = "not-the-real-sha256"

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "package_fingerprint") == "BLOCKED"


def test_fingerprint_unavailable_is_not_evaluated_not_fake_pass() -> None:
    report = build_import_package_safety_check_report(_zip_from_payload(_payload()))

    assert _status(report, "package_fingerprint") == "NOT_EVALUATED"


def test_integrity_hash_mismatch_is_blocked() -> None:
    payload = _payload()
    payload["manifest"]["manifest_integrity_hash"] = "not-the-real-integrity"

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "manifest_integrity") == "BLOCKED"


def test_integrity_hash_unavailable_is_not_evaluated() -> None:
    report = build_import_package_safety_check_report(_zip_from_payload(_payload()))

    assert _status(report, "manifest_integrity") == "NOT_EVALUATED"


def test_missing_linked_artifact_reference_is_warning() -> None:
    payload = _payload()
    payload["manifest"]["linked_artifact_references"] = [{"title": "Missing Artifact"}]

    report = build_import_package_safety_check_report(_zip_from_payload(payload))

    assert _status(report, "linked_artifact_references") == "WARNING"


def test_duplicate_risk_detected_with_read_only_local_project_list() -> None:
    report = build_import_package_safety_check_report(
        _zip_from_payload(_payload()),
        local_project_reader=lambda: [{"id": 99, "name": "Safety Checker Project"}],
    )

    assert _status(report, "duplicate_risk") == "WARNING"


def test_duplicate_check_not_evaluated_without_local_project_list() -> None:
    report = build_import_package_safety_check_report(_zip_from_payload(_payload()))

    assert _status(report, "duplicate_risk") == "NOT_EVALUATED"


def test_checker_never_writes_database() -> None:
    called = False

    def read_only_projects() -> list[dict[str, Any]]:
        nonlocal called
        called = True
        return []

    report = build_import_package_safety_check_report(_zip_from_payload(_payload()), local_project_reader=read_only_projects)

    assert called is True
    assert report["database_writes_performed"] is False


def test_checker_output_includes_boundary_copy() -> None:
    report = build_import_package_safety_check_report(_zip_from_payload(_payload()))
    text = "\n".join(report["read_only_notes"] + report["next_steps"])

    for expected in [
        "This is a read-only safety check.",
        "This report does not import or modify any project.",
        "No database writes are performed by the safety check.",
        "Create New Documentation Project is allowed only after validation, safety review, dry-run planning, and explicit final confirmation.",
        "This report does not certify experimental readiness.",
        "This report does not predict yield.",
        "This report does not optimize pathways.",
        "This report does not provide wet-lab protocols.",
        "Treat this report as one required gate before any documentation project creation.",
    ]:
        assert expected in text
