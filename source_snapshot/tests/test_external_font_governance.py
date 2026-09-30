"""Static governance checks for font resources used by the formal app."""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FORMAL_RUNTIME_STYLE_SOURCES = (
    ROOT / "app.py",
    ROOT / "views" / "SequenceToolbox.py",
    ROOT / "views" / "tool_typography.py",
    ROOT / "views" / "formal_construct_findings.py",
)
EXPECTED_UI_FONT_STACK = (
    '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", Arial, sans-serif'
)
EXPECTED_MONO_FONT_STACK = (
    '"Cascadia Mono", Consolas, "Courier New", monospace'
)

REMOTE_FONT_ORIGINS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "fonts.bunny.net",
    "fonts.cdnfonts.com",
)
REMOTE_IMPORT_RE = re.compile(r"@import\s+(?:url\s*\()?[^;\n]*https?://", re.IGNORECASE)
REMOTE_FONT_FACE_RE = re.compile(
    r"@font-face\s*\{[^}]*https?://[^}]*\}",
    re.IGNORECASE | re.DOTALL,
)
REMOTE_FONT_FILE_RE = re.compile(
    r"https?://[^\s\"')]+\.(?:eot|otf|ttf|woff2?)(?:[?#][^\s\"')]*)?",
    re.IGNORECASE,
)


def _formal_runtime_style_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in FORMAL_RUNTIME_STYLE_SOURCES)


def test_formal_runtime_styles_do_not_reference_remote_fonts() -> None:
    source = _formal_runtime_style_text()
    lowered = source.casefold()

    assert not [origin for origin in REMOTE_FONT_ORIGINS if origin in lowered]
    assert REMOTE_IMPORT_RE.search(source) is None
    assert REMOTE_FONT_FACE_RE.search(source) is None
    assert REMOTE_FONT_FILE_RE.search(source) is None


def test_formal_entry_uses_governed_local_ui_font_stack() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert f"--font-ui: {EXPECTED_UI_FONT_STACK};" in source
    assert f"--font-mono: {EXPECTED_MONO_FONT_STACK};" in source
    assert "--font: var(--font-ui);" in source
    assert "--mono: var(--font-mono);" in source
