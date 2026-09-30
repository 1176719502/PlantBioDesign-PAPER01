"""
Global configuration management — centralises all hard-coded values.
Avoids duplication and improves maintainability.
"""

import os as _os
import tempfile as _tempfile
from pathlib import Path as _Path

# ==========================================
# Menu Configuration
# ==========================================
MENU_ITEMS = {
    "dashboard": {
        "label": "🏠 Dashboard",
        "icon": "📊",
        "description": "View project statistics and quick-start guides",
    },
    "design": {
        "label": "🧬 Design",
        "icon": "🧪",
        "description": "AI-assisted biological parts design",
    },
    "build": {
        "label": "🧱 Build",
        "icon": "🔧",
        "description": "DNA sequence assembly and optimisation",
    },
    "test": {
        "label": "🩺 Test",
        "icon": "✅",
        "description": "Virtual simulation and QC inspection",
    },
    "database": {
        "label": "🗄️ Parts Library",
        "icon": "📦",
        "description": "Standard biological parts library management",
    },
}

# ==========================================
# App Configuration
# ==========================================
APP_CONFIG = {
    "title": "BioDesign Studio | Enterprise",
    "version": "22.0 Pro",
    "subtitle": "In-silico Synthetic Biology Platform",
    "page_icon": "🧬",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# ==========================================
# Color Theme
# ==========================================
COLORS = {
    "primary":    "#2E7D32",   # green  — main brand color
    "success":    "#4CAF50",   # success green
    "warning":    "#FF9800",   # warning orange
    "error":      "#F44336",   # error red
    "info":       "#2196F3",   # info blue
    "text_dark":  "#333333",   # dark text
    "text_light": "#888888",   # light text
    "bg_light":   "#f9f9f9",   # light background
    "border":     "#ddd",      # border grey
}

# ==========================================
# CSS Styles
# ==========================================
CSS_STYLES = f"""
<style>
    /* Main header */
    .main-header {{
        font-size: 2.5rem;
        color: {COLORS['primary']};
        font-weight: 700;
        margin-bottom: 10px;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    
    /* Sub-header */
    .sub-header {{
        font-size: 1.2rem;
        color: {COLORS['text_light']};
        margin-bottom: 20px;
        font-weight: 300;
    }}
    
    /* Card */
    .card {{
        padding: 20px;
        background-color: {COLORS['bg_light']};
        border-radius: 10px;
        border: 1px solid {COLORS['border']};
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }}
    
    .card:hover {{
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        border-color: {COLORS['primary']};
    }}
    
    /* Button */
    .stButton > button {{
        width: 100%;
        border-radius: 5px;
        font-weight: 600;
        background-color: {COLORS['primary']};
        color: white;
        border: none;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }}
    
    .stButton > button:hover {{
        background-color: #1b5e20;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }}
    
    /* Hide default Streamlit chrome */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
</style>
"""

# ==========================================
# Design Object Structure Template
# ==========================================
DESIGN_OBJECT_TEMPLATE = {
    "meta": {
        "project_name": "",      # project name
        "organism":     "",      # organism (Plant / Bacteria)
        "created_at":   "",      # creation time (ISO format)
        "updated_at":   "",      # last update time
        "description":  "",      # project description
    },
    "design": {
        "status":         "Empty",  # Empty → Ready → Validated
        "ai_predictions": {},
        "notes":          "",
    },
    "build": {
        "status":       "Empty",  # Empty → Constructed → Optimized
        "full_sequence": "",
        "components":    [],
        "total_bp":      0,
        "gc_content":    0.0,
    },
    "qc": {
        "status":    "Empty",   # Empty → PASS → FAIL
        "tests_run": [],
        "score":     0.0,
        "notes":     "",
    },
}

# ==========================================
# External Tool Paths (can be overridden via environment variables)
# ==========================================
TOOLS_CONFIG = {
    "MUSCLE_PATH": _os.environ.get("MUSCLE_PATH") or ("muscle.exe" if _os.name == "nt" else "muscle"),
}

# ==========================================
# Runtime Paths
# ==========================================

BIODESIGN_PYDNA_LOG_DIR_ENV = "BIODESIGN_PYDNA_LOG_DIR"
BIODESIGN_PYDNA_CONFIG_DIR_ENV = "BIODESIGN_PYDNA_CONFIG_DIR"
BIODESIGN_PYDNA_DATA_DIR_ENV = "BIODESIGN_PYDNA_DATA_DIR"
PYDNA_CONFIG_DIR_ENV = "pydna_config_dir"
PYDNA_DATA_DIR_ENV = "pydna_data_dir"
PYDNA_LOG_DIR_ENV = "pydna_log_dir"
BIODESIGN_APP_DIRNAME = "BioDesignStudio"


class RuntimePathError(RuntimeError):
    """Raised when a required per-user runtime directory cannot be created."""


def resolve_biodesign_app_data_dir(
    environ: dict[str, str] | None = None,
) -> _Path:
    """Return the per-user application directory without creating it."""
    env = _os.environ if environ is None else environ
    local_app_data = (env.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        root = _Path(local_app_data)
    elif _os.name == "nt":
        home = (env.get("USERPROFILE") or env.get("HOME") or "").strip()
        root = (_Path(home) if home else _Path.home()) / "AppData" / "Local"
    else:
        root = _Path((env.get("XDG_DATA_HOME") or "").strip() or _Path.home() / ".local" / "share")
    return (root / BIODESIGN_APP_DIRNAME).expanduser().resolve(strict=False)


def resolve_biodesign_runtime_dir(environ: dict[str, str] | None = None) -> _Path:
    """Return the formal per-user launcher state directory."""
    return resolve_biodesign_app_data_dir(environ) / "runtime"


def resolve_biodesign_log_dir(environ: dict[str, str] | None = None) -> _Path:
    """Return the formal per-user application log directory."""
    return resolve_biodesign_app_data_dir(environ) / "logs"


def _ensure_runtime_directory(path: _Path, purpose: str) -> _Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimePathError(
            f"Cannot create BioDesign Studio {purpose} directory at {path}: {exc}"
        ) from exc
    return path


def ensure_biodesign_runtime_dir(environ: dict[str, str] | None = None) -> _Path:
    return _ensure_runtime_directory(resolve_biodesign_runtime_dir(environ), "runtime")


def ensure_biodesign_log_dir(environ: dict[str, str] | None = None) -> _Path:
    return _ensure_runtime_directory(resolve_biodesign_log_dir(environ), "log")


def resolve_pydna_log_dir(environ: dict[str, str] | None = None) -> _Path:
    """Resolve the preferred writable pydna log directory."""
    env = _os.environ if environ is None else environ
    explicit = (env.get(BIODESIGN_PYDNA_LOG_DIR_ENV) or env.get(PYDNA_LOG_DIR_ENV) or "").strip()
    default = resolve_biodesign_log_dir(env) / "pydna"
    return _absolute_runtime_override(explicit, default)


def _absolute_runtime_override(value: str, default: _Path) -> _Path:
    path = _Path(value).expanduser() if value.strip() else default
    if not path.is_absolute():
        path = default
    return path.resolve(strict=False)


def resolve_pydna_config_dir(environ: dict[str, str] | None = None) -> _Path:
    """Resolve pydna configuration outside the application working directory."""
    env = _os.environ if environ is None else environ
    default = resolve_biodesign_app_data_dir(env) / "pydna" / "config"
    explicit = (
        env.get(BIODESIGN_PYDNA_CONFIG_DIR_ENV)
        or env.get(PYDNA_CONFIG_DIR_ENV)
        or ""
    ).strip()
    return _absolute_runtime_override(explicit, default)


def resolve_pydna_data_dir(environ: dict[str, str] | None = None) -> _Path:
    """Resolve pydna mutable data outside the application working directory."""
    env = _os.environ if environ is None else environ
    default = resolve_biodesign_app_data_dir(env) / "pydna" / "data"
    explicit = (
        env.get(BIODESIGN_PYDNA_DATA_DIR_ENV)
        or env.get(PYDNA_DATA_DIR_ENV)
        or ""
    ).strip()
    return _absolute_runtime_override(explicit, default)


def _ensure_writable_directory(path: _Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = _tempfile.NamedTemporaryFile(prefix=".pydna-write-", dir=path, delete=False)
    probe_path = _Path(probe.name)
    try:
        probe.close()
    finally:
        probe_path.unlink(missing_ok=True)


def _temporary_pydna_log_dir(environ: dict[str, str]) -> _Path:
    temp_root = (environ.get("TEMP") or environ.get("TMP") or "").strip()
    base = _Path(temp_root) if temp_root else _Path(_tempfile.gettempdir())
    return (base / "BioDesignStudio" / "logs" / "pydna").resolve(strict=False)


def configure_pydna_log_dir(environ: dict[str, str] | None = None) -> _Path:
    """Set all pydna write paths before import, with writable temp fallbacks."""
    env = _os.environ if environ is None else environ
    preferred_paths = {
        PYDNA_CONFIG_DIR_ENV: resolve_pydna_config_dir(env),
        PYDNA_DATA_DIR_ENV: resolve_pydna_data_dir(env),
        PYDNA_LOG_DIR_ENV: resolve_pydna_log_dir(env),
    }
    selected_paths: dict[str, _Path] = {}
    for variable, preferred in preferred_paths.items():
        try:
            _ensure_writable_directory(preferred)
            selected_paths[variable] = preferred
        except OSError:
            suffix = {
                PYDNA_CONFIG_DIR_ENV: ("pydna", "config"),
                PYDNA_DATA_DIR_ENV: ("pydna", "data"),
                PYDNA_LOG_DIR_ENV: ("logs", "pydna"),
            }[variable]
            temp_root = (env.get("TEMP") or env.get("TMP") or "").strip()
            base = _Path(temp_root) if temp_root else _Path(_tempfile.gettempdir())
            fallback = (base / BIODESIGN_APP_DIRNAME).joinpath(*suffix).resolve(strict=False)
            _ensure_writable_directory(fallback)
            selected_paths[variable] = fallback
        env[variable] = str(selected_paths[variable])
    return selected_paths[PYDNA_LOG_DIR_ENV]

# ==========================================

# Database Path

# ==========================================

BIODESIGN_DB_PATH_ENV = "BIODESIGN_DB_PATH"
BIODESIGN_BACKUP_DIR_ENV = "BIODESIGN_BACKUP_DIR"
BIODESIGN_DB_FILENAME = "biodesign_unified.db"


def resolve_biodesign_db_path(environ: dict[str, str] | None = None) -> str:
    """Return the unified SQLite path, allowing an explicit env override."""
    env = _os.environ if environ is None else environ
    override = (env.get(BIODESIGN_DB_PATH_ENV) or "").strip()
    if override:
        return str(_Path(override).expanduser().resolve(strict=False))
    return str(resolve_biodesign_app_data_dir(env) / "data" / BIODESIGN_DB_FILENAME)


def resolve_biodesign_backup_dir(
    environ: dict[str, str] | None = None,
) -> _Path:
    """Return the formal database-backup directory."""
    env = _os.environ if environ is None else environ
    override = (env.get(BIODESIGN_BACKUP_DIR_ENV) or "").strip()
    if override:
        return _Path(override).expanduser().resolve(strict=False)
    return resolve_biodesign_app_data_dir(env) / "backups" / "database"


# Lightweight constant - no side effects on import.
DB_PATH = resolve_biodesign_db_path()



# ==========================================
# Database Configuration
# ==========================================
DB_CONFIG = {
    "max_sequence_length": 500000,       # maximum sequence length (bp)
    "min_sequence_length": 100,          # minimum sequence length
    "default_gc_target":   50,           # target GC content (%)
    "codons_genetic_code": "standard",   # genetic code table
}

# ==========================================
# UI Messages
# ==========================================
MESSAGES = {
    "welcome":        "Welcome back to BioDesign Workbench",
    "subtitle":       "Next-generation intelligent design and validation system for plant synthetic biology",
    "waiting_init":   "⚪ Waiting for design initialisation...",
    "design_ready":   "🟢 Design ready",
    "design_pending": "⚪ Design pending",
    "build_ready":    "🟢 Assembled",
    "build_pending":  "⚪ Assembly pending",
    "test_pass":      "🟢 Test passed",
    "test_fail":      "🟠 Test failed",
    "test_pending":   "⚪ Test pending",
}
