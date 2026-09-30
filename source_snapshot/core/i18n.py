from __future__ import annotations

from typing import Any

from locales import LOCALES

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "zh-CN")

# Keep one canonical internal value while accepting the spellings commonly
# produced by browser controls and older session-state snapshots.
_LANGUAGE_ALIASES = {
    "en": "en",
    "en-us": "en",
    "english": "en",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "chinese": "zh-CN",
    "中文": "zh-CN",
}


def normalize_language(language: str | None) -> str:
    candidate = str(language or "").strip().lower()
    return _LANGUAGE_ALIASES.get(candidate, DEFAULT_LANGUAGE)


def get_language(session_state: Any | None = None) -> str:
    if session_state is None:
        try:
            import streamlit as st
            session_state = st.session_state
        except Exception:
            return DEFAULT_LANGUAGE

    try:
        current = session_state.get("ui_language")
    except Exception:
        current = None
    return normalize_language(current)


def set_language(language: str, session_state: Any | None = None) -> str:
    resolved = normalize_language(language)
    if session_state is None:
        import streamlit as st
        session_state = st.session_state
    session_state["ui_language"] = resolved
    return resolved


def translate(key: str, /, language: str | None = None, default: str | None = None, **kwargs: Any) -> str:
    resolved_language = normalize_language(language)
    table = LOCALES.get(resolved_language, {})
    template = table.get(key)
    if template is None:
        # English is the stable fallback for a partially extended locale.
        template = LOCALES[DEFAULT_LANGUAGE].get(
            key, default if default is not None else key
        )
    if template is None:
        template = key
    # The approved copy freeze uses `{...}` as an inventory placeholder for
    # values whose concrete runtime names vary by call site.  Resolve those
    # placeholders in insertion order while preserving normal named fields.
    if "{...}" in str(template) and kwargs:
        remaining = iter(str(value) for value in kwargs.values())
        while "{...}" in str(template):
            try:
                replacement = next(remaining)
            except StopIteration:
                break
            template = str(template).replace("{...}", replacement, 1)
    try:
        return str(template).format(**kwargs)
    except Exception:
        return str(template)


def t(key: str, /, default: str | None = None, session_state: Any | None = None, **kwargs: Any) -> str:
    return translate(key, language=get_language(session_state), default=default, **kwargs)
