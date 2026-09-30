from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def ensure_safe_id(value: str, field_name: str) -> str:
    clean = clean_text(value)
    if not clean or not SAFE_ID_PATTERN.match(clean):
        raise ValueError(f"Unsafe {field_name}: {value!r}")
    return clean


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def build_run_id(source_id: str, started_at: str, explicit_run_id: str | None = None) -> str:
    if explicit_run_id:
        return ensure_safe_id(explicit_run_id, "ingestion_run_id")
    digest = sha256_text(f"{source_id}|{started_at}")[:12]
    stamp = re.sub(r"[^0-9A-Za-z]", "", started_at)[:14]
    return f"r225-{source_id}-{stamp}-{digest}"
