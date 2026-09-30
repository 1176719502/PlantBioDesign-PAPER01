from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import services.acceptance_fixture_identity as fixture_identity
from core.config import resolve_biodesign_app_data_dir, resolve_biodesign_db_path
from services.acceptance_fixture_identity import (
    AcceptanceFixtureConfigurationError,
    clear_acceptance_fixture_context,
    configure_acceptance_fixture_context,
    fixture_identity_enabled,
    refresh_acceptance_fixture_authority,
    runtime_identity,
    snapshot_active_production_database,
)


ENV_NAMES = (
    "BIODESIGN_ACCEPTANCE_FIXTURE_ID",
    "BIODESIGN_ACCEPTANCE_FIXTURE_MODE",
    "BIODESIGN_ACCEPTANCE_RUN_ROOT",
    "BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE",
    "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE",
    "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID",
    "BIODESIGN_ACCEPTANCE_PRE_PRODUCTION_DB_PATH",
    "BIODESIGN_DB_PATH",
)


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _configure(
    *, seed: object, run_root: Path, database_path: Path
) -> dict[str, str]:
    return configure_acceptance_fixture_context(
        seed=seed,
        run_root=run_root,
        database_path=database_path,
        pre_acceptance_production_database_path=snapshot_active_production_database(),
    )


def _canonical_path(path: Path) -> str:
    return str(Path(os.path.normcase(os.path.realpath(path))))


@pytest.fixture(autouse=True)
def _clean_fixture_environment():
    clear_acceptance_fixture_context()
    previous = {name: os.environ.get(name) for name in ENV_NAMES}
    for name in ENV_NAMES:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        clear_acceptance_fixture_context()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_normal_runtime_is_uuid_based_and_process_global_counter_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    assert not hasattr(fixture_identity, "_COUNTERS")
    assert runtime_identity("tu") != runtime_identity("tu")


def test_fixture_id_alone_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_ID", "v1-formal-multi-tu-blank-fixture-v1")
    with pytest.raises(AcceptanceFixtureConfigurationError):
        runtime_identity("tu", stable_key="unit-1")


@pytest.mark.parametrize("seed", ("", "seed with spaces", "x" * 129, "seed/path"))
def test_invalid_seed_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    seed: str,
) -> None:
    _clear_environment(monkeypatch)
    with pytest.raises(AcceptanceFixtureConfigurationError):
        _configure(
            seed=seed,
            run_root=tmp_path,
            database_path=tmp_path / "biodesign_unified.db",
        )


def test_mode_and_seed_without_run_capability_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_MODE", "multi_tu")
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_ID", "seed-a")
    with pytest.raises(AcceptanceFixtureConfigurationError):
        runtime_identity("tu", stable_key="unit-1")


def test_r4_matching_environment_and_forged_json_without_authority_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    run_root = tmp_path / "forged-isolated-run"
    run_root.mkdir()
    database_path = run_root / "data" / "biodesign_unified.db"
    default_database = Path(resolve_biodesign_db_path(dict(os.environ)))
    production_database = tmp_path / "forged-production" / "biodesign_unified.db"
    capability_file = run_root / fixture_identity.CAPABILITY_FILENAME
    claims = {
        "version": fixture_identity.CAPABILITY_VERSION,
        "mode": fixture_identity.MULTI_TU_MODE,
        "seed": "forged-r4",
        "run_root": _canonical_path(run_root),
        "database_path": _canonical_path(database_path),
        "canonical_default_production_database_path": _canonical_path(default_database),
        "pre_acceptance_active_production_database_path": _canonical_path(production_database),
        "authority_handle": "987654321",
        "authority_id": "forged-authority-id",
    }
    capability_file.write_text(json.dumps(claims, sort_keys=True), encoding="utf-8")
    environment = {
        "BIODESIGN_ACCEPTANCE_FIXTURE_ID": claims["seed"],
        "BIODESIGN_ACCEPTANCE_FIXTURE_MODE": claims["mode"],
        "BIODESIGN_ACCEPTANCE_RUN_ROOT": claims["run_root"],
        "BIODESIGN_DB_PATH": claims["database_path"],
        "BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE": str(capability_file.resolve()),
        "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE": claims["authority_handle"],
        "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID": claims["authority_id"],
        "BIODESIGN_ACCEPTANCE_PRE_PRODUCTION_DB_PATH": claims[
            "pre_acceptance_active_production_database_path"
        ],
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(AcceptanceFixtureConfigurationError, match="launch authority"):
        runtime_identity("tu", stable_key="unit-1")


def test_copied_legitimate_environment_is_stale_after_launcher_authority_closes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "legitimate-run"
    run_root.mkdir()
    _configure(
        seed="legitimate-r5",
        run_root=run_root,
        database_path=run_root / "data" / "biodesign_unified.db",
    )
    copied = {name: os.environ[name] for name in ENV_NAMES}
    assert fixture_identity_enabled()
    clear_acceptance_fixture_context()
    for name, value in copied.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(AcceptanceFixtureConfigurationError, match="launch authority"):
        runtime_identity("tu", stable_key="unit-1")


def test_live_authority_rejects_matching_json_and_environment_for_run_b(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_a.mkdir()
    run_b.mkdir()
    _configure(
        seed="cross-run-r5",
        run_root=run_a,
        database_path=run_a / "data" / "biodesign_unified.db",
    )
    payload_path = Path(os.environ[fixture_identity.CAPABILITY_FILE_ENV])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    run_b_payload = run_b / fixture_identity.CAPABILITY_FILENAME
    payload["run_root"] = _canonical_path(run_b)
    payload["database_path"] = _canonical_path(run_b / "data" / "biodesign_unified.db")
    run_b_payload.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv(fixture_identity.RUN_ROOT_ENV, payload["run_root"])
    monkeypatch.setenv(fixture_identity.DB_PATH_ENV, payload["database_path"])
    monkeypatch.setenv(fixture_identity.CAPABILITY_FILE_ENV, str(run_b_payload.resolve()))
    with pytest.raises(AcceptanceFixtureConfigurationError, match="launch authority"):
        runtime_identity("tu", stable_key="unit-1")


def test_live_authority_rejects_matching_json_and_environment_with_modified_production_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "bound-run"
    run_root.mkdir()
    _configure(
        seed="production-binding-r5",
        run_root=run_root,
        database_path=run_root / "data" / "biodesign_unified.db",
    )
    payload_path = Path(os.environ[fixture_identity.CAPABILITY_FILE_ENV])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    modified_production = _canonical_path(
        tmp_path / "other-production" / "biodesign_unified.db"
    )
    payload["pre_acceptance_active_production_database_path"] = modified_production
    payload_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv(
        fixture_identity.PRE_ACCEPTANCE_PRODUCTION_DB_ENV,
        modified_production,
    )
    with pytest.raises(AcceptanceFixtureConfigurationError, match="launch authority"):
        runtime_identity("tu", stable_key="unit-1")


def test_live_launcher_authority_authorizes_the_streamlit_process_model(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "live-child-run"
    run_root.mkdir()
    _configure(
        seed="live-child-r5",
        run_root=run_root,
        database_path=run_root / "data" / "biodesign_unified.db",
    )
    probe = (
        "from services.acceptance_fixture_identity import runtime_identity; "
        "print(runtime_identity('tu', stable_key='unit-1'))"
    )
    expected = runtime_identity("tu", stable_key="unit-1")
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ),
            check=True,
            close_fds=False,
            capture_output=True,
            text=True,
        )
        assert completed.stdout.strip() == expected
        refresh_acceptance_fixture_authority()


def test_valid_capability_is_bound_to_external_run_and_exact_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    run_root = tmp_path / "run"
    run_root.mkdir()
    database_path = run_root / "data" / "biodesign_unified.db"
    _configure(
        seed="seed-a",
        run_root=run_root,
        database_path=database_path,
    )
    expected = runtime_identity("tu", stable_key="order=1|role=cds")
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(run_root / "other" / "biodesign_unified.db"))
    with pytest.raises(AcceptanceFixtureConfigurationError):
        runtime_identity("tu", stable_key="order=1|role=cds")
    assert expected
    with pytest.raises(AcceptanceFixtureConfigurationError):
        _configure(
            seed="seed-a",
            run_root=run_root,
            database_path=tmp_path.parent / "biodesign_unified.db",
        )


def test_default_production_database_and_data_root_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    production_db = Path(resolve_biodesign_db_path(dict(os.environ)))
    production_data_root = resolve_biodesign_app_data_dir(dict(os.environ)) / "data"
    production_data_root.mkdir(parents=True)

    with pytest.raises(AcceptanceFixtureConfigurationError, match="production data root"):
        _configure(
            seed="seed-default-db",
            run_root=production_data_root,
            database_path=production_db,
        )

    production_app_root = production_data_root.parent
    monkeypatch.delenv("BIODESIGN_DB_PATH", raising=False)
    with pytest.raises(AcceptanceFixtureConfigurationError, match="production database"):
        _configure(
            seed="seed-default-db",
            run_root=production_app_root,
            database_path=production_db,
        )


def test_default_database_aliases_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    production_db = Path(resolve_biodesign_db_path(dict(os.environ)))
    production_db.parent.mkdir(parents=True)
    production_app_root = production_db.parent.parent

    alias = (
        Path(str(production_db.parent).upper().replace("\\", "/"))
        / "."
        / production_db.name
        if os.name == "nt"
        else production_db.parent / "." / "nested" / ".." / production_db.name
    )
    with pytest.raises(AcceptanceFixtureConfigurationError, match="production database"):
        _configure(
            seed="seed-default-alias",
            run_root=production_app_root,
            database_path=alias,
        )


def test_isolated_external_database_remains_valid_when_local_app_data_is_overridden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "acceptance-local-app-data"))
    run_root = tmp_path / "isolated-run"
    run_root.mkdir()
    database_path = run_root / "sqlite" / "biodesign_unified.db"
    _configure(
        seed="seed-isolated-db",
        run_root=run_root,
        database_path=database_path,
    )
    assert fixture_identity_enabled()


def test_external_active_production_database_is_denied_and_isolated_database_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "default-local-app-data"))
    production_root = tmp_path / "external-production-a"
    production_root.mkdir()
    production_db = production_root / "biodesign_unified.db"
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_db))
    captured_production_db = snapshot_active_production_database()
    assert captured_production_db == production_db.resolve()

    with pytest.raises(
        AcceptanceFixtureConfigurationError,
        match="pre-acceptance active production database",
    ):
        configure_acceptance_fixture_context(
            seed="r4-o2-external-production",
            run_root=production_root,
            database_path=production_db,
            pre_acceptance_production_database_path=captured_production_db,
        )

    isolated_root = tmp_path / "isolated-run-b"
    isolated_root.mkdir()
    isolated_db = isolated_root / "data" / "biodesign_unified.db"
    context = configure_acceptance_fixture_context(
        seed="r4-o3-isolated-database",
        run_root=isolated_root,
        database_path=isolated_db,
        pre_acceptance_production_database_path=captured_production_db,
    )
    assert context["database_path"] == _canonical_path(isolated_db)
    assert context["pre_acceptance_active_production_database_path"] == _canonical_path(
        production_db
    )
    assert fixture_identity_enabled()


def test_guard_remembers_active_production_database_after_isolation_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    production_db = tmp_path / "production-a" / "biodesign_unified.db"
    isolated_root = tmp_path / "isolated-b"
    isolated_root.mkdir()
    isolated_db = isolated_root / "biodesign_unified.db"
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_db))
    captured_production_db = snapshot_active_production_database()
    configure_acceptance_fixture_context(
        seed="r4-o4-remember-production",
        run_root=isolated_root,
        database_path=isolated_db,
        pre_acceptance_production_database_path=captured_production_db,
    )
    expected = runtime_identity("tu", stable_key="unit-1")

    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_db))
    with pytest.raises(AcceptanceFixtureConfigurationError):
        runtime_identity("tu", stable_key="unit-1")
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(isolated_db))
    assert runtime_identity("tu", stable_key="unit-1") == expected
    payload = json.loads(
        Path(os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE"]).read_text(
            encoding="utf-8"
        )
    )
    assert payload["pre_acceptance_active_production_database_path"] == _canonical_path(
        production_db
    )


def test_capability_from_different_active_production_context_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    isolated_db = isolated_root / "biodesign_unified.db"
    production_a = tmp_path / "production-a" / "biodesign_unified.db"
    production_c = tmp_path / "production-c" / "biodesign_unified.db"

    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_a))
    configure_acceptance_fixture_context(
        seed="r4-o5-context-copy",
        run_root=isolated_root,
        database_path=isolated_db,
        pre_acceptance_production_database_path=snapshot_active_production_database(),
    )
    capability_file = Path(os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE"])
    payload_a = capability_file.read_text(encoding="utf-8")
    authority_id_a = os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID"]
    handle_a = os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE"]

    clear_acceptance_fixture_context()
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_c))
    configure_acceptance_fixture_context(
        seed="r4-o5-context-copy",
        run_root=isolated_root,
        database_path=isolated_db,
        pre_acceptance_production_database_path=snapshot_active_production_database(),
    )
    capability_file.write_text(payload_a, encoding="utf-8")
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID", authority_id_a)
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE", handle_a)
    with pytest.raises(AcceptanceFixtureConfigurationError, match="not bound"):
        runtime_identity("tu", stable_key="unit-1")


def test_production_database_capability_tamper_and_missing_binding_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    production_db = tmp_path / "production-a" / "biodesign_unified.db"
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    isolated_db = isolated_root / "biodesign_unified.db"
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_db))
    captured_production_db = snapshot_active_production_database()

    with pytest.raises(AcceptanceFixtureConfigurationError, match="binding is required"):
        configure_acceptance_fixture_context(
            seed="r4-o7-missing-binding",
            run_root=isolated_root,
            database_path=isolated_db,
        )

    configure_acceptance_fixture_context(
        seed="r4-o6-tamper",
        run_root=isolated_root,
        database_path=isolated_db,
        pre_acceptance_production_database_path=captured_production_db,
    )
    capability_file = Path(os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE"])
    payload = json.loads(capability_file.read_text(encoding="utf-8"))
    payload["pre_acceptance_active_production_database_path"] = str(
        tmp_path / "tampered" / "biodesign_unified.db"
    )
    capability_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(AcceptanceFixtureConfigurationError, match="not bound"):
        runtime_identity("tu", stable_key="unit-1")

    payload["pre_acceptance_active_production_database_path"] = str(production_db.resolve())
    capability_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    monkeypatch.delenv("BIODESIGN_ACCEPTANCE_PRE_PRODUCTION_DB_PATH")
    with pytest.raises(AcceptanceFixtureConfigurationError, match="is required"):
        runtime_identity("tu", stable_key="unit-1")


def test_external_production_database_alias_is_denied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    production_root = tmp_path / "External-Production-A"
    production_root.mkdir()
    production_db = production_root / "biodesign_unified.db"
    production_db.touch()
    configured_alias = (
        Path(str(production_root).upper().replace("\\", "/"))
        / "."
        / production_db.name
        if os.name == "nt"
        else production_root / "." / "nested" / ".." / production_db.name
    )
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(configured_alias))
    captured_production_db = snapshot_active_production_database()
    with pytest.raises(
        AcceptanceFixtureConfigurationError,
        match="pre-acceptance active production database",
    ):
        configure_acceptance_fixture_context(
            seed="r4-o8-production-alias",
            run_root=production_root,
            database_path=production_db,
            pre_acceptance_production_database_path=captured_production_db,
        )


def test_claimed_pre_acceptance_database_must_match_caller_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    production_a = tmp_path / "production-a" / "biodesign_unified.db"
    production_c = tmp_path / "production-c" / "biodesign_unified.db"
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_c))
    with pytest.raises(AcceptanceFixtureConfigurationError, match="caller configuration"):
        configure_acceptance_fixture_context(
            seed="r4-untrusted-claim",
            run_root=isolated_root,
            database_path=isolated_root / "biodesign_unified.db",
            pre_acceptance_production_database_path=production_a,
        )


def test_capability_copy_to_shared_default_context_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    production_db = Path(resolve_biodesign_db_path(dict(os.environ)))
    production_app_root = production_db.parent.parent
    production_app_root.mkdir(parents=True)
    capability_file = production_app_root / fixture_identity.CAPABILITY_FILENAME
    authority_id = "copied-authority"
    authority_handle = "987654321"
    capability_file.write_text(
        json.dumps(
            {
                "version": fixture_identity.CAPABILITY_VERSION,
                "mode": fixture_identity.MULTI_TU_MODE,
                "seed": "seed-copied",
                "run_root": str(production_app_root),
                "database_path": str(production_db),
                "authority_handle": authority_handle,
                "authority_id": authority_id,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_ID", "seed-copied")
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_MODE", "multi_tu")
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_RUN_ROOT", str(production_app_root))
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(production_db))
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE", str(capability_file))
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE", authority_handle)
    monkeypatch.setenv("BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID", authority_id)
    with pytest.raises(AcceptanceFixtureConfigurationError, match="production database"):
        runtime_identity("tu", stable_key="unit-1")


def test_stale_capability_marker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    run_root = tmp_path / "run"
    run_root.mkdir()
    _configure(
        seed="seed-current",
        run_root=run_root,
        database_path=run_root / "data" / "biodesign_unified.db",
    )
    capability_file = Path(os.environ["BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE"])
    payload = json.loads(capability_file.read_text(encoding="utf-8"))
    payload["seed"] = "seed-stale"
    capability_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(AcceptanceFixtureConfigurationError):
        runtime_identity("tu", stable_key="unit-1")


def test_seed_order_is_independent_and_concurrent_calls_are_stable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)

    def observe(order: tuple[str, str]) -> dict[str, str]:
        observations: dict[str, str] = {}
        for seed in order:
            _clear_environment(monkeypatch)
            run_root = tmp_path / f"{seed}-{len(observations)}"
            run_root.mkdir()
            _configure(
                seed=seed,
                run_root=run_root,
                database_path=run_root / "biodesign_unified.db",
            )
            observations[seed] = runtime_identity("tu", stable_key="order=1|role=cds")
        return observations

    forward = observe(("seed-a", "seed-b"))
    reverse = observe(("seed-b", "seed-a"))
    assert forward == reverse
    assert forward["seed-a"] != forward["seed-b"]

    run_root = tmp_path / "concurrent"
    run_root.mkdir()
    _configure(
        seed="seed-a",
        run_root=run_root,
        database_path=run_root / "biodesign_unified.db",
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda index: runtime_identity("component", stable_key=f"role={index}"),
                range(32),
            )
        )
    assert results == [
        runtime_identity("component", stable_key=f"role={index}") for index in range(32)
    ]
    clear_acceptance_fixture_context()


def test_seed_order_is_independent_across_fresh_processes(
    tmp_path: Path,
) -> None:
    contexts: dict[str, dict[str, str]] = {}
    for seed in ("seed-a", "seed-b"):
        for name in ENV_NAMES:
            os.environ.pop(name, None)
        run_root = tmp_path / seed
        run_root.mkdir()
        _configure(
            seed=seed,
            run_root=run_root,
            database_path=run_root / "biodesign_unified.db",
        )
        contexts[seed] = {name: os.environ[name] for name in ENV_NAMES}

    probe = """
import json
import os
from services.acceptance_fixture_identity import runtime_identity

output = {}
for row in json.loads(os.environ["BIODESIGN_PROBE_CONTEXTS"]):
    os.environ.update(row["env"])
    output[row["seed"]] = runtime_identity("tu", stable_key="order=1|role=cds")
print(json.dumps(output, sort_keys=True))
"""

    def run(order: tuple[str, str]) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        for name in ENV_NAMES:
            environment.pop(name, None)
        environment["BIODESIGN_PROBE_CONTEXTS"] = json.dumps(
            [{"seed": seed, "env": contexts[seed]} for seed in order]
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed

    # A copied environment can preserve the deterministic declaration but not
    # the launcher-owned broker. A fresh process must therefore fail closed.
    first = run(("seed-a", "seed-b"))
    second = run(("seed-b", "seed-a"))
    assert first.returncode != 0
    assert second.returncode != 0
    assert "launch authority" in first.stderr
    assert "launch authority" in second.stderr
