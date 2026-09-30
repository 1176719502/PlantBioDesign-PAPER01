"""Fail-closed, stateless identities for isolated Multi-TU acceptance runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import threading
from pathlib import Path
from uuid import uuid4

from core.config import resolve_biodesign_app_data_dir, resolve_biodesign_db_path


FIXTURE_ID_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_ID"
FIXTURE_MODE_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_MODE"
RUN_ROOT_ENV = "BIODESIGN_ACCEPTANCE_RUN_ROOT"
DB_PATH_ENV = "BIODESIGN_DB_PATH"
CAPABILITY_FILE_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE"
LEGACY_CAPABILITY_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY"
AUTHORITY_HANDLE_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE"
AUTHORITY_ID_ENV = "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID"
PRE_ACCEPTANCE_PRODUCTION_DB_ENV = "BIODESIGN_ACCEPTANCE_PRE_PRODUCTION_DB_PATH"
MULTI_TU_MODE = "multi_tu"
CAPABILITY_VERSION = 3
SEED_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
CAPABILITY_FILENAME = ".biodesign-acceptance-capability.json"


class _FixtureAuthority:
    """Launcher-owned OS socket capability for one acceptance run."""

    def __init__(self, expected: dict[str, str]) -> None:
        self.expected = dict(expected)
        self.authority_id = secrets.token_urlsafe(24)
        self._server_socket, self._client_socket = socket.socketpair()
        self._client_socket.set_inheritable(True)
        self.handle = self._client_socket.fileno()
        self._thread = threading.Thread(
            target=self._serve,
            name="biodesign-acceptance-authority",
            daemon=True,
        )
        self._thread.start()

    def _serve(self) -> None:
        reader = self._server_socket.makefile("rb")
        try:
            while True:
                line = reader.readline()
                if not line:
                    return
                try:
                    request = json.loads(line.decode("utf-8"))
                    claims = request.get("claims") if isinstance(request, dict) else None
                    nonce = str(request.get("nonce") or "") if isinstance(request, dict) else ""
                    accepted = (
                        isinstance(claims, dict)
                        and bool(nonce)
                        and str(request.get("authority_id") or "") == self.authority_id
                        and claims == self.expected
                    )
                    response = {"ok": accepted, "nonce": nonce if accepted else ""}
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                    response = {"ok": False, "nonce": ""}
                self._server_socket.sendall(
                    (json.dumps(response, sort_keys=True) + "\n").encode("utf-8")
                )
        except OSError:
            return
        finally:
            reader.close()

    def close(self) -> None:
        self._client_socket.close()
        self._server_socket.close()
        self._thread.join(timeout=2)


_ACTIVE_AUTHORITY: _FixtureAuthority | None = None


_AUTHORITY_IO_LOCK = threading.Lock()


def _authorize_live(*, handle: str, authority_id: str, claims: dict[str, str]) -> bool:
    connection: socket.socket | None = None
    try:
        handle_value = int(handle)
        if handle_value < 0:
            return False
        nonce = secrets.token_urlsafe(16)
        connection = socket.socket(fileno=handle_value)
        if not connection.get_inheritable():
            return False
        connection.settimeout(1.5)
        with _AUTHORITY_IO_LOCK:
            payload = {
                "authority_id": authority_id,
                "claims": claims,
                "nonce": nonce,
            }
            connection.sendall((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
            response_bytes = b""
            while b"\n" not in response_bytes:
                chunk = connection.recv(4096)
                if not chunk:
                    return False
                response_bytes += chunk
            response = json.loads(response_bytes.splitlines()[0].decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False
    finally:
        if connection is not None:
            connection.detach()
    return bool(response.get("ok")) and response.get("nonce") == nonce


class AcceptanceFixtureConfigurationError(ValueError):
    """Raised when deterministic fixture activation is incomplete or unsafe."""


def _text(value: object) -> str:
    return str(value or "").strip()


def validate_fixture_seed(seed: object) -> str:
    normalized = _text(seed)
    if not normalized or not SEED_PATTERN.fullmatch(normalized):
        raise AcceptanceFixtureConfigurationError(
            "Acceptance fixture seed must be 1-128 ASCII letters, digits, '.', '_' or '-'."
        )
    return normalized


def _resolved_path(value: object, *, label: str) -> Path:
    raw = _text(value)
    if not raw:
        raise AcceptanceFixtureConfigurationError(f"Acceptance {label} is required.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise AcceptanceFixtureConfigurationError(f"Acceptance {label} must be an absolute path.")
    # realpath resolves existing junction/symlink aliases; normcase applies
    # Windows case-folding while remaining a no-op on case-sensitive hosts.
    return Path(os.path.normcase(os.path.realpath(path)))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _paths_equivalent(left: Path, right: Path) -> bool:
    if left == right:
        return True
    if left.exists() and right.exists():
        try:
            return os.path.samefile(left, right)
        except OSError:
            pass
    return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _canonical_default_production_paths() -> tuple[Path, Path]:
    """Resolve the default production DB and its canonical data directory.

    The explicit acceptance DB override must not participate in this lookup.
    Other resolver inputs, including LOCALAPPDATA, remain authoritative for
    the current process and are therefore treated consistently with runtime
    persistence resolution.
    """
    resolver_environment = dict(os.environ)
    resolver_environment.pop(DB_PATH_ENV, None)
    production_db = _resolved_path(
        resolve_biodesign_db_path(resolver_environment),
        label="default database",
    )
    production_data_root = _resolved_path(
        resolve_biodesign_app_data_dir(resolver_environment) / "data",
        label="default data root",
    )
    return production_db, production_data_root


def snapshot_active_production_database(
    environ: dict[str, str] | None = None,
) -> Path:
    """Resolve the caller's active production DB before acceptance isolation."""
    environment = dict(os.environ if environ is None else environ)
    return _resolved_path(
        resolve_biodesign_db_path(environment),
        label="pre-acceptance active production database",
    )


def _validate_external_run_root(run_root: Path, production_data_root: Path) -> None:
    if not run_root.exists() or not run_root.is_dir():
        raise AcceptanceFixtureConfigurationError("Acceptance run root must be an existing directory.")
    if _is_within(run_root, _repo_root()):
        raise AcceptanceFixtureConfigurationError("Acceptance run root must be outside the repository.")
    if run_root == production_data_root:
        raise AcceptanceFixtureConfigurationError(
            "Acceptance run root must not be the normal production data root."
        )


def _validate_database_path(
    database_path: Path,
    run_root: Path,
    *,
    canonical_default_production_db: Path,
    pre_acceptance_active_production_db: Path,
) -> None:
    if database_path.name != "biodesign_unified.db" or not _is_within(database_path, run_root):
        raise AcceptanceFixtureConfigurationError(
            "Acceptance database must be biodesign_unified.db below the isolated run root."
        )
    if _paths_equivalent(database_path, canonical_default_production_db):
        raise AcceptanceFixtureConfigurationError(
            "Acceptance database must not be the canonical default production database."
        )
    if _paths_equivalent(database_path, pre_acceptance_active_production_db):
        raise AcceptanceFixtureConfigurationError(
            "Acceptance database must not be the pre-acceptance active production database."
        )


def _validate_configured_database_path(database_path: Path) -> None:
    configured = _text(os.environ.get(DB_PATH_ENV))
    if not configured or _resolved_path(configured, label="database path") != database_path:
        raise AcceptanceFixtureConfigurationError(
            "Acceptance database path must be explicitly bound to the isolated run database."
        )


def _validated_context() -> dict[str, str] | None:
    values = {
        "seed": _text(os.environ.get(FIXTURE_ID_ENV)),
        "mode": _text(os.environ.get(FIXTURE_MODE_ENV)),
        "run_root": _text(os.environ.get(RUN_ROOT_ENV)),
        "database_path": _text(os.environ.get(DB_PATH_ENV)),
        "capability_file": _text(os.environ.get(CAPABILITY_FILE_ENV)),
        "authority_handle": _text(os.environ.get(AUTHORITY_HANDLE_ENV)),
        "authority_id": _text(os.environ.get(AUTHORITY_ID_ENV)),
        "pre_acceptance_production_database_path": _text(
            os.environ.get(PRE_ACCEPTANCE_PRODUCTION_DB_ENV)
        ),
    }
    if not any(
        values[key]
        for key in (
            "seed",
            "mode",
            "run_root",
            "capability_file",
            "authority_handle",
            "authority_id",
            "pre_acceptance_production_database_path",
        )
    ):
        return None
    if values["mode"] != MULTI_TU_MODE:
        raise AcceptanceFixtureConfigurationError(
            "Deterministic fixture identity requires BIODESIGN_ACCEPTANCE_FIXTURE_MODE=multi_tu."
        )
    seed = validate_fixture_seed(values["seed"])
    run_root = _resolved_path(values["run_root"], label="run root")
    database_path = _resolved_path(values["database_path"], label="database path")
    capability_file = _resolved_path(values["capability_file"], label="capability file")
    pre_acceptance_active_production_db = _resolved_path(
        values["pre_acceptance_production_database_path"],
        label="pre-acceptance active production database",
    )
    canonical_default_production_db, production_data_root = (
        _canonical_default_production_paths()
    )
    _validate_external_run_root(run_root, production_data_root)
    _validate_database_path(
        database_path,
        run_root,
        canonical_default_production_db=canonical_default_production_db,
        pre_acceptance_active_production_db=pre_acceptance_active_production_db,
    )
    _validate_configured_database_path(database_path)
    if not _is_within(capability_file, run_root) or not capability_file.is_file():
        raise AcceptanceFixtureConfigurationError(
            "Acceptance capability file must exist below the isolated run root."
        )
    try:
        payload = json.loads(capability_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFixtureConfigurationError("Acceptance capability file is unreadable.") from exc
    expected = {
        "version": CAPABILITY_VERSION,
        "mode": MULTI_TU_MODE,
        "seed": seed,
        "run_root": str(run_root),
        "database_path": str(database_path),
        "canonical_default_production_database_path": str(
            canonical_default_production_db
        ),
        "pre_acceptance_active_production_database_path": str(
            pre_acceptance_active_production_db
        ),
        "authority_handle": values["authority_handle"],
        "authority_id": values["authority_id"],
    }
    if payload != expected or not values["authority_handle"] or not values["authority_id"]:
        raise AcceptanceFixtureConfigurationError(
            "Acceptance capability is not bound to the requested seed, run root, and database."
        )
    claims = {
        "mode": MULTI_TU_MODE,
        "seed": seed,
        "run_root": str(run_root),
        "database_path": str(database_path),
        "canonical_default_production_database_path": str(canonical_default_production_db),
        "pre_acceptance_active_production_database_path": str(pre_acceptance_active_production_db),
    }
    # A live launcher-owned broker is the trust root. Environment and JSON
    # claims alone are deliberately insufficient.
    if not _authorize_live(
        handle=values["authority_handle"],
        authority_id=values["authority_id"],
        claims=claims,
    ):
        raise AcceptanceFixtureConfigurationError(
            "Acceptance launch authority is unavailable, stale, or rejected the current context."
        )
    return {
        "seed": seed,
        "mode": MULTI_TU_MODE,
        "run_root": str(run_root),
        "database_path": str(database_path),
        "pre_acceptance_active_production_database_path": str(
            pre_acceptance_active_production_db
        ),
        "capability_file": str(capability_file),
    }


def configure_acceptance_fixture_context(
    *,
    seed: object,
    run_root: str | os.PathLike[str],
    database_path: str | os.PathLike[str],
    pre_acceptance_production_database_path: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    """Create a per-run capability marker and bind the current process to it."""
    normalized_seed = validate_fixture_seed(seed)
    resolved_root = _resolved_path(run_root, label="run root")
    resolved_db = _resolved_path(database_path, label="database path")
    if pre_acceptance_production_database_path is None:
        raise AcceptanceFixtureConfigurationError(
            "Pre-acceptance active production database binding is required."
        )
    bound_pre_acceptance_production_db = _resolved_path(
        pre_acceptance_production_database_path,
        label="pre-acceptance active production database",
    )
    current_pre_acceptance_production_db = snapshot_active_production_database()
    if not _paths_equivalent(
        bound_pre_acceptance_production_db,
        current_pre_acceptance_production_db,
    ):
        raise AcceptanceFixtureConfigurationError(
            "Pre-acceptance active production database binding does not match the caller configuration."
        )
    canonical_default_production_db, production_data_root = (
        _canonical_default_production_paths()
    )
    _validate_external_run_root(resolved_root, production_data_root)
    _validate_database_path(
        resolved_db,
        resolved_root,
        canonical_default_production_db=canonical_default_production_db,
        pre_acceptance_active_production_db=bound_pre_acceptance_production_db,
    )
    global _ACTIVE_AUTHORITY
    if _ACTIVE_AUTHORITY is not None:
        _ACTIVE_AUTHORITY.close()
        _ACTIVE_AUTHORITY = None
    authority_claims = {
        "mode": MULTI_TU_MODE,
        "seed": normalized_seed,
        "run_root": str(resolved_root),
        "database_path": str(resolved_db),
        "canonical_default_production_database_path": str(canonical_default_production_db),
        "pre_acceptance_active_production_database_path": str(bound_pre_acceptance_production_db),
    }
    _ACTIVE_AUTHORITY = _FixtureAuthority(authority_claims)
    os.environ[DB_PATH_ENV] = str(resolved_db)
    _validate_configured_database_path(resolved_db)
    capability_file = resolved_root / CAPABILITY_FILENAME
    payload = {
        "version": CAPABILITY_VERSION,
        "mode": MULTI_TU_MODE,
        "seed": normalized_seed,
        "run_root": str(resolved_root),
        "database_path": str(resolved_db),
        "canonical_default_production_database_path": str(
            canonical_default_production_db
        ),
        "pre_acceptance_active_production_database_path": str(
            bound_pre_acceptance_production_db
        ),
        "authority_handle": str(_ACTIVE_AUTHORITY.handle),
        "authority_id": _ACTIVE_AUTHORITY.authority_id,
    }
    try:
        capability_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    except (OSError, UnicodeError):
        _ACTIVE_AUTHORITY.close()
        _ACTIVE_AUTHORITY = None
        raise
    os.environ[FIXTURE_ID_ENV] = normalized_seed
    os.environ[FIXTURE_MODE_ENV] = MULTI_TU_MODE
    os.environ[RUN_ROOT_ENV] = str(resolved_root)
    os.environ[CAPABILITY_FILE_ENV] = str(capability_file)
    os.environ[AUTHORITY_HANDLE_ENV] = str(_ACTIVE_AUTHORITY.handle)
    os.environ[AUTHORITY_ID_ENV] = _ACTIVE_AUTHORITY.authority_id
    os.environ[PRE_ACCEPTANCE_PRODUCTION_DB_ENV] = str(
        bound_pre_acceptance_production_db
    )
    return dict(_validated_context() or {})


def fixture_identity_enabled() -> bool:
    """Validate activation and report whether deterministic Multi-TU IDs are enabled."""
    return _validated_context() is not None


def refresh_acceptance_fixture_authority() -> dict[str, str]:
    """Mint a new child-process capability after the prior app process stops."""
    global _ACTIVE_AUTHORITY
    previous = _ACTIVE_AUTHORITY
    if previous is None:
        raise AcceptanceFixtureConfigurationError(
            "Acceptance launch authority cannot be refreshed without a launcher context."
        )
    claims = dict(previous.expected)
    previous.close()
    _ACTIVE_AUTHORITY = _FixtureAuthority(claims)
    capability_file = _resolved_path(
        os.environ.get(CAPABILITY_FILE_ENV), label="capability file"
    )
    try:
        payload = json.loads(capability_file.read_text(encoding="utf-8"))
        payload["authority_handle"] = str(_ACTIVE_AUTHORITY.handle)
        payload["authority_id"] = _ACTIVE_AUTHORITY.authority_id
        capability_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        _ACTIVE_AUTHORITY.close()
        _ACTIVE_AUTHORITY = None
        raise AcceptanceFixtureConfigurationError(
            "Acceptance capability could not be refreshed."
        ) from exc
    os.environ[AUTHORITY_HANDLE_ENV] = str(_ACTIVE_AUTHORITY.handle)
    os.environ[AUTHORITY_ID_ENV] = _ACTIVE_AUTHORITY.authority_id
    return dict(_validated_context() or {})


def clear_acceptance_fixture_context() -> None:
    """Remove only the acceptance capability variables from the current process."""
    global _ACTIVE_AUTHORITY
    if _ACTIVE_AUTHORITY is not None:
        _ACTIVE_AUTHORITY.close()
        _ACTIVE_AUTHORITY = None
    for name in (
        FIXTURE_ID_ENV,
        FIXTURE_MODE_ENV,
        RUN_ROOT_ENV,
        CAPABILITY_FILE_ENV,
        AUTHORITY_HANDLE_ENV,
        AUTHORITY_ID_ENV,
        LEGACY_CAPABILITY_ENV,
        PRE_ACCEPTANCE_PRODUCTION_DB_ENV,
    ):
        os.environ.pop(name, None)


def runtime_identity(prefix: str, *, stable_key: str = "") -> str:
    """Return a UUID in normal runtime or a pure deterministic fixture identity."""
    normalized_prefix = _text(prefix) or "id"
    context = _validated_context()
    if context is None:
        return f"{normalized_prefix}-{uuid4().hex}"
    normalized_key = _text(stable_key)
    if not normalized_key:
        raise AcceptanceFixtureConfigurationError(
            "Deterministic acceptance identities require an explicit stable semantic key."
        )
    digest = hashlib.sha256(
        "|".join(
            (
                "biodesign-acceptance-fixture-v1",
                context["mode"],
                context["seed"],
                normalized_prefix,
                normalized_key,
            )
        ).encode("utf-8")
    ).hexdigest()
    return f"{normalized_prefix}-{digest[:32]}"
