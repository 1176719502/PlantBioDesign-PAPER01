"""Offline, read-only validation for the Windows runtime package contract."""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DATABASE = "data/knowledge_base_v0/kb_v0.sqlite3"
KNOWLEDGE_MANIFEST = "data/knowledge_base_v0/manifest.json"
APPROVED_DATABASE_RESOURCES = {KNOWLEDGE_DATABASE}
APPROVED_DIRECT = {
    "streamlit": "1.55.0",
    "pandas": "2.2.2",
    "numpy": "1.26.4",
    "matplotlib": "3.8.4",
    "biopython": "1.87",
    "httpx": "0.28.1",
}
FORBIDDEN_DISTRIBUTIONS = {
    "pydna",
    "primer3",
    "primer3-py",
    "matplotlib-venn",
    "plotly",
    "seaborn",
    "openpyxl",
    "reportlab",
    "fastapi",
    "uvicorn",
    "redis",
    "rq",
    "scikit-learn",
    "pytest",
    "playwright",
}
LOCK_PATTERN = re.compile(
    r"^([A-Za-z0-9_.-]+)==([^\s;@]+)\s+--hash=sha256:([0-9a-f]{64})$"
)
NAME_SEPARATORS = re.compile(r"[-_.]+")
VALID_CLASSIFICATIONS = {
    "formal_required",
    "conditional_excluded",
    "historical_excluded",
    "verify_in_p0b2b",
    "formal_static",
}
VALID_LICENSE_STATUSES = {"CLEAR", "NEEDS_ATTRIBUTION", "NEEDS_REVIEW", "UNKNOWN"}
LICENSE_COLUMNS = {
    "package",
    "version",
    "license_expression",
    "metadata_source",
    "license_file",
    "redistribution_status",
    "attribution_required",
    "review_status",
    "notes",
}


class ContractError(RuntimeError):
    """Raised when a packaging contract invariant is not satisfied."""


def normalize_name(value: str) -> str:
    return NAME_SEPARATORS.sub("-", value.strip()).lower()


def _read_utf8(relative_path: str) -> str:
    try:
        return (ROOT / relative_path).read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ContractError(f"{relative_path} is not valid UTF-8: {exc}") from exc


def parse_direct_requirements() -> dict[str, str]:
    found: dict[str, str] = {}
    for line_number, raw in enumerate(_read_utf8("requirements-runtime.in").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if any(token in line.lower() for token in (" -e ", "git+", "file:", "http:", "https:", " @ ")):
            raise ContractError(f"requirements-runtime.in:{line_number} uses a forbidden source")
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if not match:
            raise ContractError(f"requirements-runtime.in:{line_number} is not an exact pin")
        name, version = normalize_name(match.group(1)), match.group(2)
        if name in found:
            raise ContractError(f"requirements-runtime.in duplicates {name}")
        found[name] = version
    if found != APPROVED_DIRECT:
        raise ContractError(f"direct requirements differ from approved set: {found!r}")
    return found


def parse_lock() -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for line_number, raw in enumerate(_read_utf8("requirements-runtime.lock").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if any(token in lowered for token in (" -e ", "git+", "file:", "http:", "https:", " @ ", "../", "\\\\")):
            raise ContractError(f"requirements-runtime.lock:{line_number} uses a forbidden source")
        match = LOCK_PATTERN.fullmatch(line)
        if not match:
            raise ContractError(f"requirements-runtime.lock:{line_number} lacks one exact pin and SHA-256 hash")
        name = normalize_name(match.group(1))
        if name in found:
            raise ContractError(f"requirements-runtime.lock duplicates {name}")
        found[name] = (match.group(2), match.group(3))
    missing_direct = set(APPROVED_DIRECT) - set(found)
    forbidden = set(found) & FORBIDDEN_DISTRIBUTIONS
    if missing_direct:
        raise ContractError(f"lock is missing direct dependencies: {sorted(missing_direct)}")
    if forbidden:
        raise ContractError(f"lock contains forbidden dependencies: {sorted(forbidden)}")
    return found


def load_json(relative_path: str) -> object:
    try:
        return json.loads(_read_utf8(relative_path))
    except json.JSONDecodeError as exc:
        raise ContractError(f"{relative_path} is invalid JSON: {exc}") from exc


def _safe_repo_source(source: str) -> Path:
    normalized = source.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractError(f"resource source escapes repository: {source}")
    return ROOT.joinpath(*pure.parts)


def _relative_source(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def manifest_resource_files(manifest: dict) -> list[Path]:
    """Return the exact files staging must copy, preserving source bytes."""
    paths: set[Path] = set()
    for entry in manifest["application_resources"]:
        source = _safe_repo_source(str(entry["source"]))
        if source.is_file():
            paths.add(source)
        else:
            paths.update(path for path in source.rglob("*") if path.is_file())
    for relative_path in manifest["runtime_python_modules"]:
        source = _safe_repo_source(relative_path)
        if not source.is_file():
            raise ContractError(f"runtime Python module does not exist: {relative_path}")
        paths.add(source)
    return sorted(paths, key=_relative_source)


def validate_resources() -> tuple[dict, dict]:
    manifest = load_json("packaging/resource_manifest.json")
    excludes = load_json("packaging/package_excludes.json")
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
        raise ContractError("resource manifest version is invalid")
    if manifest.get("target") != "windows-x64-cpython312":
        raise ContractError("resource manifest target is invalid")
    if not isinstance(excludes, dict) or excludes.get("manifest_version") != 1:
        raise ContractError("package exclude manifest version is invalid")

    entries = manifest.get("application_resources")
    if not isinstance(entries, list) or not entries:
        raise ContractError("application resource whitelist is empty")
    required_fields = {
        "source", "destination", "kind", "required", "read_only", "missing_behavior", "validation"
    }
    deny_fragments = ("secrets.toml", "plant_design_project_drafts")
    required_sources: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not required_fields <= set(entry):
            raise ContractError("application resource entry is missing required fields")
        source = str(entry["source"]).replace("\\", "/")
        lowered = source.lower()
        if any(fragment in lowered for fragment in deny_fragments):
            raise ContractError(f"denied resource is included: {source}")
        if Path(source).suffix.casefold() in {".db", ".sqlite", ".sqlite3"} and source not in APPROVED_DATABASE_RESOURCES:
            raise ContractError(f"unapproved database resource is included: {source}")
        if not _safe_repo_source(source).exists():
            raise ContractError(f"repository resource does not exist: {source}")
        if entry["required"]:
            required_sources.append(source)

    patterns = [row.get("pattern", "") for row in excludes.get("excludes", []) if isinstance(row, dict)]
    for source in required_sources:
        for pattern in patterns:
            if fnmatch.fnmatchcase(source, pattern) or PurePosixPath(source).match(pattern):
                raise ContractError(f"required resource {source} is excluded by {pattern}")

    exclude_names = {normalize_name(name) for name in excludes.get("forbidden_distributions", [])}
    if not FORBIDDEN_DISTRIBUTIONS <= exclude_names:
        raise ContractError("package exclude denylist is incomplete")
    runtime_modules = manifest.get("runtime_python_modules")
    if not isinstance(runtime_modules, list) or not runtime_modules:
        raise ContractError("runtime Python closure is empty")
    if len(runtime_modules) != len(set(runtime_modules)):
        raise ContractError("runtime Python closure contains duplicate modules")
    for module in runtime_modules:
        if not isinstance(module, str) or not module.endswith(".py"):
            raise ContractError("runtime Python closure contains a non-Python path")
        if module.startswith(("tests/", "archive/", "archive_v1_dormant/")):
            raise ContractError(f"runtime Python closure contains an excluded module: {module}")
        _safe_repo_source(module)

    included_paths = {_relative_source(path) for path in manifest_resource_files(manifest)}
    required_vector_paths = {
        "data/vector_asset_contracts_v1/contracts.json",
        "data/vector_asset_contracts_v1/contracts.schema.json",
        "case_inputs/rice_hsa/raw/AF234296.1.gb",
        "case_inputs/rice_hsa/raw/AF234296.1.fasta",
        "data/real_assets/pbi121/source_records/AF485783.1.gb",
        "data/plant_component_registry_v1/source_records/U09365.1.gb",
        KNOWLEDGE_DATABASE,
        KNOWLEDGE_MANIFEST,
    }
    missing_vector_paths = required_vector_paths - included_paths
    if missing_vector_paths:
        raise ContractError(f"formal vector resources are missing: {sorted(missing_vector_paths)}")
    if any("r229_backbone" in path.casefold() for path in included_paths):
        raise ContractError("r229 source record is not a formal release resource")
    validate_knowledge_base_resource(ROOT)
    return manifest, excludes


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_knowledge_base_resource(resource_root: Path) -> dict[str, object]:
    database_path = resource_root / KNOWLEDGE_DATABASE
    manifest_path = resource_root / KNOWLEDGE_MANIFEST
    if not database_path.is_file() or not manifest_path.is_file():
        raise ContractError("versioned knowledge database resource pair is incomplete")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"knowledge database manifest is invalid: {exc}") from exc
    database = manifest.get("database") if isinstance(manifest, dict) else None
    if not isinstance(database, dict):
        raise ContractError("knowledge database manifest lacks database metadata")
    if database.get("relative_path") != KNOWLEDGE_DATABASE:
        raise ContractError("knowledge database manifest path is not the approved resource")
    if database.get("sha256") != _file_sha256(database_path):
        raise ContractError("knowledge database SHA-256 differs from its manifest")
    if database.get("size_bytes") != database_path.stat().st_size:
        raise ContractError("knowledge database size differs from its manifest")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if (application_id, user_version) != (1262634032, 1):
            raise ContractError("knowledge database application_id or user_version is unsupported")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ContractError("knowledge database integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ContractError("knowledge database foreign_key_check failed")
        releases = connection.execute(
            "SELECT release_id, dataset_version, build_manifest_sha256, source_bundle_sha256, "
            "release_status, approved_by, approved_at_utc FROM kb_release"
        ).fetchall()
    except sqlite3.Error as exc:
        raise ContractError(f"knowledge database could not be verified: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    expected = [
        manifest.get("release_id"),
        manifest.get("dataset_version"),
        manifest.get("build_manifest_sha256"),
        manifest.get("source_bundle_sha256"),
        manifest.get("release_status"),
        manifest.get("approved_by"),
        manifest.get("approved_at_utc"),
    ]
    if len(releases) != 1 or list(releases[0]) != expected or releases[0][4] != "HUMAN_APPROVED":
        raise ContractError("knowledge database release metadata differs from manifest")
    return {"sha256": database["sha256"], "size_bytes": database["size_bytes"]}


def validate_license_inventory(lock: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    with (ROOT / "packaging/license_inventory.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != LICENSE_COLUMNS:
            raise ContractError("license inventory columns do not match the contract")
        rows = list(reader)
    names: set[str] = set()
    for row in rows:
        name = normalize_name(row["package"])
        if name in names:
            raise ContractError(f"license inventory duplicates {name}")
        names.add(name)
        if row["review_status"] not in VALID_LICENSE_STATUSES:
            raise ContractError(f"invalid license review status for {name}")
        if row["redistribution_status"] not in VALID_LICENSE_STATUSES:
            raise ContractError(f"invalid redistribution status for {name}")
        if name in lock and row["version"] != lock[name][0]:
            raise ContractError(f"license version differs from lock for {name}")
    if names != set(lock):
        raise ContractError(
            f"license inventory coverage differs from lock; missing={sorted(set(lock)-names)}, extra={sorted(names-set(lock))}"
        )
    return rows


def validate_notices() -> None:
    notices = _read_utf8("THIRD_PARTY_NOTICES.md").lower()
    for name in APPROVED_DIRECT:
        if name not in notices:
            raise ContractError(f"third-party notices omit direct dependency {name}")
    if "legal approval" in notices and "does not claim legal" not in notices:
        raise ContractError("third-party notices overstate legal approval")


def validate_hidden_imports_and_package_data(lock: dict[str, tuple[str, str]]) -> None:
    rows = []
    for line_number, raw in enumerate(_read_utf8("packaging/hidden_imports.txt").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) != 3 or parts[0] not in VALID_CLASSIFICATIONS or not parts[1].strip():
            raise ContractError(f"hidden_imports.txt:{line_number} has invalid format")
        rows.append(parts)
    if not rows:
        raise ContractError("hidden import contract has no classified decisions")

    contract = load_json("packaging/package_data_contract.json")
    if not isinstance(contract, dict) or contract.get("contract_version") != 1:
        raise ContractError("package data contract version is invalid")
    for entry in contract.get("entries", []):
        classification = entry.get("classification")
        package = normalize_name(str(entry.get("package", "")))
        if classification not in VALID_CLASSIFICATIONS:
            raise ContractError(f"invalid package-data classification for {package}")
        if classification in {"formal_required", "verify_in_p0b2b"} and package not in lock:
            raise ContractError(f"package-data contract references unlocked package {package}")
        if classification == "conditional_excluded" and package in lock:
            raise ContractError(f"excluded package-data package is locked: {package}")


def validate_text_encodings() -> None:
    paths = [
        "requirements-runtime.in",
        "requirements-runtime.lock",
        "packaging/resource_manifest.json",
        "packaging/package_excludes.json",
        "packaging/package_data_contract.json",
        "packaging/application_version.json",
        "packaging/hidden_imports.txt",
        "packaging/license_inventory.csv",
        "THIRD_PARTY_NOTICES.md",
        KNOWLEDGE_MANIFEST,
    ]
    for path in paths:
        _read_utf8(path)


def replay_staging(staging_root: Path) -> dict[str, int]:
    """Copy the manifest closure without parsing source records or installing packages."""
    manifest, excludes = validate_resources()
    if staging_root.exists():
        raise ContractError(f"staging path already exists: {staging_root}")
    staging_root.mkdir(parents=True)
    source_files = manifest_resource_files(manifest)
    for source in source_files:
        destination = staging_root / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            raise ContractError(f"staging byte mismatch: {_relative_source(source)}")

    staged_files = [path for path in staging_root.rglob("*") if path.is_file()]
    for path in staged_files:
        relative = path.relative_to(staging_root).as_posix()
        lowered = relative.casefold()
        if "secrets.toml" in lowered:
            raise ContractError(f"forbidden staged file: {relative}")
        is_database = Path(relative).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
        is_sidecar = lowered.endswith(("-wal", "-shm"))
        is_backup_or_temp = lowered.endswith((".backup", ".bak", ".tmp"))
        if (is_database and relative not in APPROVED_DATABASE_RESOURCES) or is_sidecar or is_backup_or_temp:
            raise ContractError(f"forbidden staged database artifact: {relative}")
        if relative.startswith(("tests/", "audit_reports/", ".git/", ".codex/")):
            raise ContractError(f"forbidden staged directory: {relative}")
        if str(ROOT).casefold() in path.read_bytes().decode("utf-8", errors="ignore").casefold():
            raise ContractError(f"absolute development path found in staging: {relative}")

    registry_root = ROOT / "data" / "plant_component_registry_v1" / "source_records"
    for source in registry_root.glob("*.gb"):
        copied = staging_root / source.relative_to(ROOT)
        if hashlib.sha256(source.read_bytes()).hexdigest() != hashlib.sha256(copied.read_bytes()).hexdigest():
            raise ContractError(f"registry source-record hash mismatch: {source.name}")
    # Ensure the staging copy can read the two data contracts without repository access.
    json.loads((staging_root / "data/vector_asset_contracts_v1/contracts.json").read_text(encoding="utf-8"))
    json.loads((staging_root / "data/plant_component_registry_v1/registry.batch1.json").read_text(encoding="utf-8"))
    validate_knowledge_base_resource(staging_root)
    return {"files": len(staged_files), "bytes": sum(path.stat().st_size for path in staged_files)}


def validate_contract() -> dict[str, int]:
    direct = parse_direct_requirements()
    lock = parse_lock()
    validate_resources()
    license_rows = validate_license_inventory(lock)
    validate_notices()
    validate_hidden_imports_and_package_data(lock)
    validate_text_encodings()
    return {"direct_dependencies": len(direct), "locked_distributions": len(lock), "license_rows": len(license_rows)}


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--staging":
            summary = replay_staging(Path(sys.argv[2]))
            print(f"RUNTIME_PACKAGE_STAGING_PASS: files={summary['files']} bytes={summary['bytes']}")
            return 0
        if len(sys.argv) != 1:
            raise ContractError("usage: validate_runtime_package_contract.py [--staging PATH]")
        summary = validate_contract()
    except ContractError as exc:
        print(f"RUNTIME_PACKAGE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "RUNTIME_PACKAGE_CONTRACT_PASS: "
        f"direct={summary['direct_dependencies']} "
        f"locked={summary['locked_distributions']} "
        f"licenses={summary['license_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
