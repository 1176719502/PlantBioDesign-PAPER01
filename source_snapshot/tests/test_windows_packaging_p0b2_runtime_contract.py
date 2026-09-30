from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_runtime_package_contract.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("runtime_package_contract", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_direct_dependency_input_is_exactly_approved() -> None:
    validator = _load_validator()
    assert validator.parse_direct_requirements() == validator.APPROVED_DIRECT


def test_lock_is_exact_hashed_and_excludes_forbidden_distributions() -> None:
    validator = _load_validator()
    lock = validator.parse_lock()
    assert len(lock) == 49
    assert not (set(lock) & validator.FORBIDDEN_DISTRIBUTIONS)
    assert all(len(hash_value) == 64 for _, hash_value in lock.values())


def test_resource_manifest_contains_only_the_approved_read_only_database() -> None:
    validator = _load_validator()
    manifest, _ = validator.validate_resources()
    serialized = json.dumps(manifest).lower()
    assert "secrets.toml" not in serialized.split('"excluded_patterns"', 1)[0]
    included = json.dumps(manifest["application_resources"]).lower()
    database_sources = {
        entry["source"]
        for entry in manifest["application_resources"]
        if Path(entry["source"]).suffix.lower() in {".db", ".sqlite", ".sqlite3"}
    }
    assert database_sources == {"data/knowledge_base_v0/kb_v0.sqlite3"}
    kb_entry = next(
        entry for entry in manifest["application_resources"]
        if entry["source"] == "data/knowledge_base_v0/kb_v0.sqlite3"
    )
    assert kb_entry["required"] is True
    assert kb_entry["read_only"] is True
    assert "plant_design_project_drafts" not in included


def test_manifest_covers_new_vector_and_registry_runtime_resources() -> None:
    validator = _load_validator()
    manifest, _ = validator.validate_resources()
    included = {path.relative_to(ROOT).as_posix() for path in validator.manifest_resource_files(manifest)}
    assert "data/vector_asset_contracts_v1/contracts.json" in included
    assert "data/vector_asset_contracts_v1/contracts.schema.json" in included
    assert "case_inputs/rice_hsa/raw/AF234296.1.gb" in included
    assert "data/real_assets/pbi121/source_records/AF485783.1.gb" in included
    assert "data/plant_component_registry_v1/source_records/U09365.1.gb" in included
    assert "data/knowledge_base_v0/kb_v0.sqlite3" in included
    assert "data/knowledge_base_v0/manifest.json" in included
    assert "core/pcambia1300_exact_insertion_contract.py" in included
    assert "core/pbi121_replacement_contract.py" in included
    assert "core/vector_asset_contracts_v1.py" in included
    assert "core/database_migrations/V10000__adopt_versioned_database.py" in included
    assert "components/design_modules/static_data.py" in included
    assert "mvp_app.py" not in included
    assert "services/vector_asset_admission.py" in included
    assert "locales/en.py" in included
    assert "views/wizard_steps/_shared.py" in included
    assert not any("views/wizard_steps/step" in path for path in included)
    assert not any(path.startswith("services/async_") for path in included)
    assert not any("r229_" in Path(path).name.casefold() for path in included)
    assert not any(path.startswith("examples/plant_single_gene_mvp/") for path in included)


def test_excludes_cover_secrets_sqlite_user_data_and_optional_stacks() -> None:
    excludes = json.loads((ROOT / "packaging" / "package_excludes.json").read_text(encoding="utf-8"))
    patterns = {entry["pattern"] for entry in excludes["excludes"]}
    assert ".streamlit/secrets.toml" in patterns
    assert "data/*.db" in patterns
    assert "data/*.sqlite" in patterns
    assert "data/biodesign_unified.*" in patterns
    assert "data/plant_expression_candidates.*" in patterns
    assert "**/*-wal" in patterns
    assert "**/*-shm" in patterns
    assert "plant_design_project_drafts/**" in patterns
    assert "views/legacy_ui_registry.py" in patterns
    assert "views/**" not in patterns


def test_license_inventory_and_notices_cover_runtime_lock() -> None:
    validator = _load_validator()
    lock = validator.parse_lock()
    rows = validator.validate_license_inventory(lock)
    assert len(rows) == len(lock) == 49
    validator.validate_notices()


def test_hidden_import_and_package_data_contracts_are_valid() -> None:
    validator = _load_validator()
    validator.validate_hidden_imports_and_package_data(validator.parse_lock())


def test_staging_replay_is_offline_and_preserves_registry_source_bytes(tmp_path: Path) -> None:
    validator = _load_validator()
    summary = validator.replay_staging(tmp_path / "staging")
    assert summary["files"] > 0
    assert summary["bytes"] > 0
    assert (tmp_path / "staging" / "data/vector_asset_contracts_v1/contracts.json").is_file()
    assert (tmp_path / "staging" / "data/plant_component_registry_v1/registry.batch1.json").is_file()
    assert (tmp_path / "staging" / "data/knowledge_base_v0/kb_v0.sqlite3").is_file()
    validator.validate_knowledge_base_resource(tmp_path / "staging")


def test_validator_succeeds_as_an_offline_read_only_command() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "RUNTIME_PACKAGE_CONTRACT_PASS" in result.stdout
