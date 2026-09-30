from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any, Callable

from services.project_export_package_service import PACKAGE_VERSION
from services.project_import_package_validator import REQUIRED_MANIFEST_FIELDS, SUPPORTED_PACKAGE_VERSIONS

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"

SAFETY_CHECK_BOUNDARY_COPY = (
    "This is a read-only safety check.",
    "This report does not import or modify any project.",
    "No database writes are performed by the safety check.",
    "Create New Documentation Project is allowed only after validation, safety review, dry-run planning, and explicit final confirmation.",
    "This report does not certify experimental readiness.",
    "This report does not predict yield.",
    "This report does not optimize pathways.",
    "This report does not provide wet-lab protocols.",
)

STATUS_USER_SUMMARIES = {
    STATUS_PASS: "Safe for read-only review.",
    STATUS_WARNING: "Review warnings before future import planning.",
    STATUS_BLOCKED: "Package is blocked for future execution planning until issues are resolved.",
    STATUS_NOT_EVALUATED: "This check could not be evaluated from the available package metadata.",
}

DEFAULT_NEXT_STEPS = (
    "Review blocking issues first.",
    "Re-export the package from a supported build if version checks fail.",
    "Keep this package as a review/archive artifact.",
    "Use dry-run preview for planning only.",
    "Treat this report as one required gate before any documentation project creation.",
)

STALE_EXPORT_BEFORE = "2026-01-01T00:00:00"


def _item(check_id: str, label: str, status: str, summary: str, detail: str, user_guidance: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "label": label,
        "status": status,
        "summary": summary,
        "detail": detail,
        "user_guidance": user_guidance,
    }


def _parse_zip(zip_bytes: bytes) -> tuple[list[str], dict[str, Any], dict[str, bytes], list[str]]:
    errors: list[str] = []
    parsed: dict[str, Any] = {}
    raw: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
            names = archive.namelist()
            for name in names:
                try:
                    raw[name] = archive.read(name)
                except (OSError, KeyError):
                    errors.append(f"Could not read package entry: {name}")
                    continue
                if name.endswith(".json"):
                    try:
                        parsed[name] = json.loads(raw[name].decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        errors.append(f"Malformed JSON file: {name}")
            return names, parsed, raw, errors
    except (zipfile.BadZipFile, OSError, ValueError):
        return [], {}, {}, ["Zip file could not be opened as a valid project export package."]


def _package_fingerprint(zip_bytes: bytes) -> str:
    return hashlib.sha256(zip_bytes).hexdigest()


def _canonical_json_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _version_status(version: Any) -> tuple[str, str]:
    if not version:
        return STATUS_BLOCKED, "Package schema version is missing."
    version_text = str(version)
    if version_text in SUPPORTED_PACKAGE_VERSIONS:
        return STATUS_PASS, f"Package schema version {version_text} is supported."
    try:
        current = float(PACKAGE_VERSION)
        observed = float(version_text)
    except (TypeError, ValueError):
        return STATUS_BLOCKED, f"Unsupported package schema version: {version_text}."
    if observed > current:
        return STATUS_BLOCKED, f"Future package schema version {version_text} is not supported by this build."
    return STATUS_BLOCKED, f"Old unsupported package schema version {version_text} is blocked."


def _manifest_integrity_expected(manifest: dict[str, Any]) -> str | None:
    integrity = manifest.get("integrity") or manifest.get("integrity_hash") or manifest.get("manifest_integrity_hash")
    if isinstance(integrity, dict):
        integrity = integrity.get("manifest_sha256") or integrity.get("sha256")
    return str(integrity).strip() if integrity else None


def _fingerprint_expected(manifest: dict[str, Any]) -> str | None:
    fingerprint = manifest.get("package_fingerprint") or manifest.get("fingerprint")
    if isinstance(fingerprint, dict):
        fingerprint = fingerprint.get("sha256") or fingerprint.get("package_sha256")
    return str(fingerprint).strip() if fingerprint else None


def _hash_manifest_without_integrity(manifest: dict[str, Any]) -> str:
    comparable = dict(manifest)
    for key in ("integrity", "integrity_hash", "manifest_integrity_hash"):
        comparable.pop(key, None)
    return _canonical_json_hash(comparable)


def _find_manifest_referenced_artifacts(manifest: dict[str, Any], parsed: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("linked_artifacts", "linked_artifact_references", "artifact_references"):
        value = manifest.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    refs.add(entry)
                elif isinstance(entry, dict):
                    ref = entry.get("id") or entry.get("artifact_id") or entry.get("title")
                    if ref:
                        refs.add(str(ref))
    linked = parsed.get("linked_tool_artifacts.json")
    artifacts = linked.get("linked_tool_artifacts") if isinstance(linked, dict) else None
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                ref = artifact.get("id") or artifact.get("artifact_id") or artifact.get("title")
                if ref:
                    refs.add(str(ref))
    return refs


def _available_artifact_refs(parsed: dict[str, Any]) -> set[str]:
    linked = parsed.get("linked_tool_artifacts.json")
    artifacts = linked.get("linked_tool_artifacts") if isinstance(linked, dict) else None
    available: set[str] = set()
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                for key in ("id", "artifact_id", "title"):
                    if artifact.get(key):
                        available.add(str(artifact[key]))
    return available


def build_import_package_safety_check_report(
    zip_bytes: bytes | None,
    *,
    local_project_reader: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    safe_bytes = zip_bytes or b""
    file_list, parsed, raw_entries, parse_errors = _parse_zip(safe_bytes)
    manifest = parsed.get("manifest.json") if isinstance(parsed.get("manifest.json"), dict) else None
    items: list[dict[str, str]] = []

    if parse_errors:
        items.append(_item("package_read", "Package can be opened", STATUS_BLOCKED, "Package could not be fully read.", "; ".join(parse_errors), "Upload a valid exported package zip."))
    else:
        items.append(_item("package_read", "Package can be opened", STATUS_PASS, "Package zip was readable.", f"Detected {len(file_list)} package entries.", "Continue read-only review."))

    if manifest is None:
        items.append(_item("manifest_presence", "Manifest presence", STATUS_BLOCKED, "manifest.json is missing or malformed.", "A valid manifest is required before future execution planning.", "Re-export the package from a supported build."))
    else:
        missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
        status = STATUS_WARNING if missing else STATUS_PASS
        items.append(_item("manifest_presence", "Manifest presence", status, "manifest.json is present." if not missing else "manifest.json is present but missing metadata fields.", "Missing fields: " + ", ".join(missing) if missing else "Required manifest metadata fields are present.", "Review missing metadata before future import planning." if missing else "Continue read-only review."))

    package_version = manifest.get("package_version") if manifest else None
    version_status, version_detail = _version_status(package_version)
    items.append(_item("schema_version", "Schema/package version", version_status, version_detail, f"Supported versions: {', '.join(sorted(SUPPORTED_PACKAGE_VERSIONS))}.", "Re-export the package from a supported build if version checks fail."))

    exporter_version = manifest.get("exporter_version") or manifest.get("application_version") if manifest else None
    if exporter_version:
        exporter_text = str(exporter_version)
        status = STATUS_WARNING if exporter_text.startswith("999") else STATUS_PASS
        detail = "Exporter/application version metadata is available."
        summary = f"Exporter/application version: {exporter_text}."
    else:
        status = STATUS_NOT_EVALUATED
        summary = "Exporter/application version metadata is not available."
        detail = "Current package format may not store exporter build version metadata."
    items.append(_item("exporter_version", "Exporter/application version", status, summary, detail, "Use packages exported from supported builds for future import planning."))

    actual_fingerprint = _package_fingerprint(safe_bytes) if safe_bytes else None
    expected_fingerprint = _fingerprint_expected(manifest) if manifest else None
    if expected_fingerprint and actual_fingerprint:
        status = STATUS_PASS if expected_fingerprint == actual_fingerprint else STATUS_BLOCKED
        summary = "Package fingerprint matches manifest metadata." if status == STATUS_PASS else "Package fingerprint mismatch detected."
        detail = f"Expected {expected_fingerprint}; calculated {actual_fingerprint}."
    elif actual_fingerprint:
        status = STATUS_NOT_EVALUATED
        summary = "Package fingerprint was calculated but no stored fingerprint was available for comparison."
        detail = f"Calculated sha256: {actual_fingerprint}. Current package format may not store package fingerprint metadata."
    else:
        status = STATUS_NOT_EVALUATED
        summary = "Package fingerprint could not be calculated from available bytes."
        detail = "No package bytes were available."
    items.append(_item("package_fingerprint", "Package fingerprint", status, summary, detail, "Do not treat an unavailable comparison as a pass."))

    expected_integrity = _manifest_integrity_expected(manifest) if manifest else None
    if expected_integrity and manifest:
        actual_integrity = _hash_manifest_without_integrity(manifest)
        status = STATUS_PASS if expected_integrity == actual_integrity else STATUS_BLOCKED
        summary = "Manifest integrity hash matches." if status == STATUS_PASS else "Manifest integrity hash mismatch detected."
        detail = f"Expected {expected_integrity}; calculated {actual_integrity}."
    elif manifest:
        status = STATUS_NOT_EVALUATED
        summary = "Manifest integrity hash is not available in this package."
        detail = "Current package format may not include manifest integrity metadata; schema is not changed by this checker."
    else:
        status = STATUS_BLOCKED
        summary = "Manifest integrity cannot be checked because manifest is missing."
        detail = "manifest.json is required."
    items.append(_item("manifest_integrity", "Manifest integrity/checksum", status, summary, detail, "Re-export the package if integrity metadata is present but mismatched."))

    if manifest:
        requested_refs = _find_manifest_referenced_artifacts(manifest, parsed)
        available_refs = _available_artifact_refs(parsed)
        missing_refs = sorted(ref for ref in requested_refs if available_refs and ref not in available_refs)
        if missing_refs:
            status = STATUS_WARNING
            summary = "Some linked documentation artifact references are missing from package contents."
            detail = "Missing references: " + ", ".join(missing_refs)
        elif "linked_tool_artifacts.json" in parsed:
            status = STATUS_PASS
            summary = "Linked documentation artifact references are internally present where available."
            detail = f"Checked {len(available_refs)} linked artifact references without restoring raw payload_json."
        else:
            status = STATUS_NOT_EVALUATED
            summary = "No linked artifact package section was available to evaluate."
            detail = "linked_tool_artifacts.json was not present or not parseable."
    else:
        status = STATUS_NOT_EVALUATED
        summary = "Linked artifact references could not be evaluated without manifest metadata."
        detail = "manifest.json is missing."
    items.append(_item("linked_artifact_references", "Linked documentation artifact references", status, summary, detail, "Review missing linked artifact records before future import planning."))

    exported_at = manifest.get("exported_at") if manifest else None
    if exported_at:
        try:
            exported_dt = datetime.fromisoformat(str(exported_at))
            stale_dt = datetime.fromisoformat(STALE_EXPORT_BEFORE)
            status = STATUS_WARNING if exported_dt < stale_dt else STATUS_PASS
            summary = "Package export timestamp is within supported review window." if status == STATUS_PASS else "Package may be stale for future execution planning."
            detail = f"exported_at: {exported_at}; stale threshold: {STALE_EXPORT_BEFORE}."
        except ValueError:
            status = STATUS_WARNING
            summary = "Package export timestamp could not be parsed."
            detail = f"exported_at: {exported_at}."
    else:
        status = STATUS_NOT_EVALUATED
        summary = "Package export timestamp is not available."
        detail = "Missing timestamp prevents stale package evaluation."
    items.append(_item("stale_package", "Stale/unsupported/future package", status, summary, detail, "Re-export stale or unsupported packages from a supported build."))

    if local_project_reader is None:
        items.append(_item("duplicate_risk", "Duplicate risk", STATUS_NOT_EVALUATED, "Duplicate risk could not be evaluated from local projects.", "No safe read-only local project list provider was supplied.", "Use read-only local project comparison before any future import execution planning."))
    else:
        local_projects = local_project_reader() or []
        source_id = manifest.get("project_id") if manifest else None
        source_name = str(manifest.get("project_name") or "").strip().lower() if manifest else ""
        matches = []
        for project in local_projects:
            if not isinstance(project, dict):
                continue
            if source_id is not None and str(project.get("id")) == str(source_id):
                matches.append(f"id={source_id}")
            if source_name and str(project.get("name") or project.get("target_product") or "").strip().lower() == source_name:
                matches.append(f"name={manifest.get('project_name')}")
        if matches:
            items.append(_item("duplicate_risk", "Duplicate risk", STATUS_WARNING, "Potential duplicate local project detected.", "Matched local project by " + ", ".join(sorted(set(matches))) + ".", "Review duplicate risk before future import planning; this checker does not create projects."))
        else:
            items.append(_item("duplicate_risk", "Duplicate risk", STATUS_PASS, "No duplicate local project was detected by the supplied read-only project list.", f"Checked {len(local_projects)} local project records without writes.", "Continue read-only review."))

    blocking = [item["summary"] for item in items if item["status"] == STATUS_BLOCKED]
    warnings = [item["summary"] for item in items if item["status"] == STATUS_WARNING]
    if blocking:
        overall = STATUS_BLOCKED
    elif warnings:
        overall = STATUS_WARNING
    else:
        overall = STATUS_PASS

    return {
        "overall_status": overall,
        "check_items": items,
        "safe_user_summary": STATUS_USER_SUMMARIES[overall],
        "blocking_issues": blocking,
        "warnings": warnings,
        "read_only_notes": list(SAFETY_CHECK_BOUNDARY_COPY),
        "package_identity": {
            "project_id": manifest.get("project_id") if manifest else None,
            "project_name": manifest.get("project_name") if manifest else None,
            "package_version": package_version,
            "exported_at": exported_at,
            "app_context": manifest.get("app_context") if manifest else None,
            "calculated_package_sha256": actual_fingerprint,
        },
        "next_steps": list(DEFAULT_NEXT_STEPS),
        "database_writes_performed": False,
    }
