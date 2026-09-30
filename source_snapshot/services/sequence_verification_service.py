"""Read-only sequence verification service with a mockable adapter contract."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Mapping

DISCLAIMER = (
    "Sequence verification is informational only. It does not certify experimental readiness, "
    "does not change validation status, and does not override primer or export safety recommendations."
)

_ALLOWED_WARNING_CODES = {
    "NO_QUERY",
    "NO_HITS",
    "LOW_COVERAGE",
    "LOW_IDENTITY",
    "REMOTE_UNAVAILABLE",
    "LOCAL_REGISTRY_ONLY",
    "INFORMATIONAL_ONLY",
    "AMBIGUOUS_BASES",
    "SHORT_QUERY",
    "REGISTRY_UNAVAILABLE",
}

_LOW_COVERAGE_THRESHOLD = 80.0
_LOW_IDENTITY_THRESHOLD = 70.0


def _normalize_sequence(sequence: str) -> str:
    """Return uppercase DNA bases from a raw sequence-like value."""
    lines = []
    for line in str(sequence or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        lines.append(stripped)
    return re.sub(r"[^ATGCNatgcn]", "", "".join(lines)).upper()


def _sequence_hash(sequence: str) -> str:
    if not sequence:
        return ""
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _warning(code: str, message: str, severity: str = "info") -> dict[str, str]:
    normalized_code = code if code in _ALLOWED_WARNING_CODES else "INFORMATIONAL_ONLY"
    return {"code": normalized_code, "message": message, "severity": severity}


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_hit(raw_hit: Mapping[str, Any], rank: int) -> dict[str, Any]:
    percent_identity = _coerce_float(raw_hit.get("percent_identity"))
    coverage = _coerce_float(raw_hit.get("coverage"))
    alignment_length = raw_hit.get("alignment_length")
    try:
        alignment_length = int(alignment_length) if alignment_length not in (None, "") else 0
    except (TypeError, ValueError):
        alignment_length = 0

    return {
        "rank": int(raw_hit.get("rank") or rank),
        "accession": str(raw_hit.get("accession") or ""),
        "organism": str(raw_hit.get("organism") or raw_hit.get("host") or ""),
        "description": str(raw_hit.get("description") or ""),
        "percent_identity": percent_identity,
        "coverage": coverage,
        "e_value": raw_hit.get("e_value"),
        "alignment_length": alignment_length,
        "alignment_summary": str(raw_hit.get("alignment_summary") or ""),
        "match_type": str(raw_hit.get("match_type") or ""),
        "part_type": str(raw_hit.get("part_type") or ""),
        "source": str(raw_hit.get("source") or ""),
    }


def _extract_hits(adapter_result: Any) -> list[dict[str, Any]]:
    if adapter_result is None:
        return []
    if isinstance(adapter_result, list):
        raw_hits = adapter_result
    elif isinstance(adapter_result, Mapping):
        raw_hits = adapter_result.get("hits") or []
    else:
        raw_hits = []
    return [
        _normalize_hit(hit, index + 1)
        for index, hit in enumerate(raw_hits)
        if isinstance(hit, Mapping)
    ]


def _adapter_name(adapter: Any) -> str:
    if adapter is None:
        return "placeholder"
    if hasattr(adapter, "name"):
        return str(getattr(adapter, "name") or adapter.__class__.__name__)
    if hasattr(adapter, "__name__"):
        return str(adapter.__name__)
    return adapter.__class__.__name__


def _call_adapter(adapter: Any, sequence: str, database_label: str) -> Any:
    if isinstance(adapter, Mapping):
        return adapter
    if hasattr(adapter, "verify"):
        return adapter.verify(sequence=sequence, database_label=database_label)
    if callable(adapter):
        return adapter(sequence=sequence, database_label=database_label)
    raise TypeError("Verification adapter must be callable, expose verify(), or provide imported hits.")


def _base_payload(
    sequence: str,
    source_label: str,
    database_label: str,
    adapter_name: str,
    status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "query": {
            "length": len(sequence),
            "source_label": str(source_label or "Current sequence"),
            "hash": _sequence_hash(sequence),
        },
        "database": {
            "source": str(database_label or "Placeholder verification adapter"),
        },
        "adapter_name": adapter_name,
        "top_hit": None,
        "hits": [],
        "warnings": [_warning("INFORMATIONAL_ONLY", DISCLAIMER, "info")],
        "timestamp": _timestamp(),
        "disclaimer": DISCLAIMER,
    }


def _append_hit_warnings(payload: dict[str, Any]) -> None:
    hits = payload.get("hits") or []
    if not hits:
        payload["warnings"].append(
            _warning(
                "NO_HITS",
                "No similarity hits are available from the current verification adapter.",
                "info",
            )
        )
        return

    top_hit = hits[0]
    coverage = top_hit.get("coverage")
    percent_identity = top_hit.get("percent_identity")
    if coverage is not None and coverage < _LOW_COVERAGE_THRESHOLD:
        payload["warnings"].append(
            _warning(
                "LOW_COVERAGE",
                f"Top hit covers less than {_LOW_COVERAGE_THRESHOLD:.0f}% of the query sequence.",
                "warning",
            )
        )
    if percent_identity is not None and percent_identity < _LOW_IDENTITY_THRESHOLD:
        payload["warnings"].append(
            _warning(
                "LOW_IDENTITY",
                f"Top hit identity is below {_LOW_IDENTITY_THRESHOLD:.0f}%.",
                "warning",
            )
        )


def run_sequence_verification(
    sequence: str,
    source_label: str = "Current sequence",
    adapter: Any = None,
    database_label: str = "Placeholder verification adapter",
) -> dict[str, Any]:
    """Run read-only sequence verification and return a stable payload.

    The default path is intentionally local and deterministic. It does not
    call online BLAST, does not start background workers, and does not mutate
    any design state.
    """
    normalized = _normalize_sequence(sequence)
    adapter_display_name = _adapter_name(adapter)
    payload = _base_payload(
        normalized,
        source_label,
        database_label,
        adapter_display_name,
        "completed",
    )

    if not normalized:
        payload["status"] = "no_query"
        payload["warnings"].append(
            _warning("NO_QUERY", "No DNA sequence was provided for verification.", "warning")
        )
        return payload

    if "N" in normalized:
        payload["warnings"].append(
            _warning(
                "AMBIGUOUS_BASES",
                "The query contains N bases; similarity evidence may require manual review.",
                "warning",
            )
        )

    if len(normalized) < 20:
        payload["warnings"].append(
            _warning(
                "SHORT_QUERY",
                "The query is short; local containment evidence may require manual review.",
                "info",
            )
        )

    if adapter is None:
        payload["status"] = "unavailable"
        payload["warnings"].append(
            _warning(
                "REMOTE_UNAVAILABLE",
                "No verification adapter is configured. Online BLAST is intentionally disabled in this phase.",
                "info",
            )
        )
        payload["warnings"].append(
            _warning(
                "NO_HITS",
                "No similarity hits are available from the placeholder adapter.",
                "info",
            )
        )
        return payload

    try:
        adapter_result = _call_adapter(adapter, normalized, database_label)
        hits = _extract_hits(adapter_result)
        payload["hits"] = hits
        payload["top_hit"] = hits[0] if hits else None
        adapter_status = adapter_result.get("status") if isinstance(adapter_result, Mapping) else None
        payload["status"] = str(adapter_status or ("completed" if hits else "no_hits"))
        if str(database_label).strip().lower() == "local parts registry":
            payload["warnings"].append(
                _warning(
                    "LOCAL_REGISTRY_ONLY",
                    "Verification used only the local Parts Registry and did not query external databases.",
                    "info",
                )
            )
        _append_hit_warnings(payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - adapter boundary must be defensive
        payload["status"] = "unavailable"
        payload["warnings"].append(
            _warning(
                "REGISTRY_UNAVAILABLE" if str(database_label).strip().lower() == "local parts registry" else "REMOTE_UNAVAILABLE",
                f"The verification adapter is unavailable: {exc}",
                "warning",
            )
        )
        return payload
