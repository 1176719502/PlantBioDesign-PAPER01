from __future__ import annotations

import json
import posixpath
import re
import zipfile
from io import BytesIO
from typing import Any

from services.project_export_package_service import INCLUDED_FILES, PACKAGE_VERSION

REQUIRED_FILES = tuple(INCLUDED_FILES)
JSON_FILES = tuple(name for name in REQUIRED_FILES if name.endswith(".json"))
REQUIRED_MANIFEST_FIELDS = (
    "package_version",
    "exported_at",
    "app_context",
    "project_id",
    "project_name",
    "boundary_statement",
    "included_sections",
)
SUPPORTED_PACKAGE_VERSIONS = {PACKAGE_VERSION}
UNSAFE_EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".js",
    ".vbs",
    ".scr",
    ".dll",
    ".jar",
    ".py",
}
BOUNDARY_REQUIRED_PHRASES = (
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
)
VALIDATION_BOUNDARY_LANGUAGE = (
    "This validation report is documentation-only and read-only. It does not certify experimental readiness, "
    "does not validate the pathway, does not predict yield, does not optimize pathways, and does not provide wet-lab protocols."
)
DEVELOPER_PAYLOAD_PREVIEW_MAX_LENGTH = 1000
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _base_report() -> dict[str, Any]:
    return {
        "is_valid": False,
        "errors": [],
        "warnings": [],
        "package_version": None,
        "project_name": None,
        "included_files": [],
        "boundary_confirmed": False,
        "json_files_valid": False,
        "unsafe_files": [],
        "documentation_only_boundary": VALIDATION_BOUNDARY_LANGUAGE,
    }


def _add_error(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)


def inspect_zip_file_list(zip_bytes: bytes) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
            return archive.namelist(), errors
    except (zipfile.BadZipFile, OSError, ValueError):
        _add_error(errors, "Zip file could not be opened as a valid project export package.")
        return [], errors


def validate_required_files(file_list: list[str]) -> list[str]:
    errors: list[str] = []
    present = set(file_list)
    for required_file in REQUIRED_FILES:
        if required_file not in present:
            _add_error(errors, f"Missing required file: {required_file}")
    return errors


def _is_unsafe_filename(filename: str) -> bool:
    normalized = filename.replace("\\", "/")
    if filename.startswith("/") or normalized.startswith("/"):
        return True
    if _WINDOWS_ABSOLUTE_RE.match(filename):
        return True
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if ".." in parts:
        return True
    collapsed = posixpath.normpath(normalized)
    return collapsed == ".." or collapsed.startswith("../")


def validate_no_unsafe_filenames(file_list: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unsafe_files: list[str] = []
    for filename in file_list:
        suffix = posixpath.splitext(filename.replace("\\", "/"))[1].lower()
        is_unsafe = _is_unsafe_filename(filename) or suffix in UNSAFE_EXECUTABLE_EXTENSIONS
        if is_unsafe:
            unsafe_files.append(filename)
    if unsafe_files:
        _add_error(errors, "Package contains unsafe filenames or executable payloads.")
    return errors, unsafe_files


def validate_json_files(zip_bytes: bytes, file_list: list[str]) -> tuple[bool, dict[str, Any], list[str]]:
    errors: list[str] = []
    parsed: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
            for filename in JSON_FILES:
                if filename not in file_list:
                    continue
                try:
                    parsed[filename] = json.loads(archive.read(filename).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, OSError, KeyError):
                    _add_error(errors, f"Malformed JSON file: {filename}")
    except (zipfile.BadZipFile, OSError, ValueError):
        _add_error(errors, "Zip file could not be opened as a valid project export package.")
    return not errors, parsed, errors


def validate_manifest(manifest: Any) -> tuple[list[str], str | None, str | None]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest.json must contain a JSON object."], None, None
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            _add_error(errors, f"manifest.json missing required field: {field}")
    package_version = manifest.get("package_version")
    if package_version not in SUPPORTED_PACKAGE_VERSIONS:
        _add_error(errors, f"Unsupported package_version: {package_version}")
    return errors, package_version, manifest.get("project_name")


def validate_boundary_readme(zip_bytes: bytes, file_list: list[str]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if "README_BOUNDARY.txt" not in file_list:
        return False, ["Missing required file: README_BOUNDARY.txt"]
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
            readme_text = archive.read("README_BOUNDARY.txt").decode("utf-8").lower()
    except (zipfile.BadZipFile, OSError, UnicodeDecodeError, KeyError, ValueError):
        return False, ["README_BOUNDARY.txt could not be read."]
    for phrase in BOUNDARY_REQUIRED_PHRASES:
        if phrase not in readme_text:
            _add_error(errors, f"README_BOUNDARY.txt missing required boundary phrase: {phrase}")
    return not errors, errors


def _contains_key(value: Any, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        return forbidden_key in value or any(_contains_key(item, forbidden_key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden_key) for item in value)
    return False


def _developer_preview_too_long(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "developer_payload_preview" and len(str(item)) > DEVELOPER_PAYLOAD_PREVIEW_MAX_LENGTH:
                return True
            if _developer_preview_too_long(item):
                return True
    if isinstance(value, list):
        return any(_developer_preview_too_long(item) for item in value)
    return False


def validate_linked_tool_artifacts(linked_tool_artifacts: Any) -> list[str]:
    errors: list[str] = []
    if _contains_key(linked_tool_artifacts, "payload_json"):
        _add_error(errors, "linked_tool_artifacts.json must not include raw payload_json.")
    if _developer_preview_too_long(linked_tool_artifacts):
        _add_error(errors, "linked_tool_artifacts.json developer_payload_preview exceeds safe length limit.")
    artifacts = linked_tool_artifacts.get("linked_tool_artifacts") if isinstance(linked_tool_artifacts, dict) else None
    if isinstance(artifacts, list):
        for index, artifact in enumerate(artifacts):
            if isinstance(artifact, dict) and "readable_payload_summary" not in artifact:
                _add_error(errors, f"linked_tool_artifacts[{index}] missing readable_payload_summary.")
    return errors


def validate_project_import_package(zip_bytes: bytes) -> dict[str, Any]:
    report = _base_report()
    file_list, zip_errors = inspect_zip_file_list(zip_bytes)
    report["included_files"] = file_list
    report["errors"].extend(zip_errors)
    if zip_errors:
        return report

    required_errors = validate_required_files(file_list)
    filename_errors, unsafe_files = validate_no_unsafe_filenames(file_list)
    json_files_valid, parsed_json, json_errors = validate_json_files(zip_bytes, file_list)
    boundary_confirmed, boundary_errors = validate_boundary_readme(zip_bytes, file_list)

    report["unsafe_files"] = unsafe_files
    report["json_files_valid"] = json_files_valid
    report["boundary_confirmed"] = boundary_confirmed
    report["errors"].extend(required_errors)
    report["errors"].extend(filename_errors)
    report["errors"].extend(json_errors)
    report["errors"].extend(boundary_errors)

    if "manifest.json" in parsed_json:
        manifest_errors, package_version, project_name = validate_manifest(parsed_json["manifest.json"])
        report["package_version"] = package_version
        report["project_name"] = project_name
        report["errors"].extend(manifest_errors)

    if "linked_tool_artifacts.json" in parsed_json:
        report["errors"].extend(validate_linked_tool_artifacts(parsed_json["linked_tool_artifacts.json"]))

    report["is_valid"] = not report["errors"]
    return report
