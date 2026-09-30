from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def coerce_text(value: Any) -> str:
    return str(value or "").strip()


def coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def coerce_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def coerce_mapping_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in coerce_list(value) if isinstance(item, Mapping)]


def first_text(*values: Any) -> str:
    for value in values:
        clean = coerce_text(value)
        if clean:
            return clean
    return ""


def status_label(value: Any) -> str:
    return coerce_text(value).replace("_", " ") or "not recorded"


def readback_summary(value: Any, preferred_keys: Sequence[str] = ()) -> str:
    value_map = coerce_mapping(value)
    if not value_map:
        return "not recorded"

    parts: list[str] = []
    for key in preferred_keys:
        clean = coerce_text(value_map.get(key))
        if clean:
            parts.append(f"{key}: {clean}")

    if not parts:
        for key in sorted(value_map):
            raw = value_map[key]
            if isinstance(raw, (Mapping, list, tuple)):
                continue
            clean = coerce_text(raw)
            if clean:
                parts.append(f"{key}: {clean}")
            if len(parts) >= 3:
                break

    return "; ".join(parts) or "not recorded"


def readback_list(values: Any) -> str:
    texts = [coerce_text(value) for value in coerce_list(values) if coerce_text(value)]
    if not texts:
        return "none visible"
    return "; ".join(texts)
