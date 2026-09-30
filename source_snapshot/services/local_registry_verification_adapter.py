"""Read-only local Parts Registry adapter for sequence verification."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from services.parts_service import canonical_parts_from_registry

LOCAL_REGISTRY_SOURCE = "Local Parts Registry"
LOCAL_REGISTRY_ADAPTER_NAME = "local-parts-registry"


def _load_initialized_local_registry() -> Iterable[Mapping[str, Any]]:
    """Load local registry records through the same initialized contract as the app."""
    from core.database import init_db

    init_db()
    return canonical_parts_from_registry()


def _normalize_sequence(sequence: str) -> str:
    return re.sub(r"[^ATGCNatgcn]", "", str(sequence or "")).upper()


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ATGCN", "TACGN"))[::-1]


def _first_present(record: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


class LocalRegistryVerificationAdapter:
    """Compare a query sequence against local Parts Registry records."""

    name = LOCAL_REGISTRY_ADAPTER_NAME
    source = LOCAL_REGISTRY_SOURCE

    def __init__(self, registry_loader: Callable[[], Iterable[Mapping[str, Any]]] | None = None) -> None:
        self._registry_loader = registry_loader or _load_initialized_local_registry

    def verify(self, sequence: str, database_label: str = LOCAL_REGISTRY_SOURCE) -> dict[str, Any]:
        """Return deterministic local similarity hits without external services."""
        query = _normalize_sequence(sequence)
        if not query:
            return {"status": "no_query", "hits": [], "source": database_label or self.source}

        records = list(self._registry_loader())
        hits = [hit for record in records if (hit := self._match_record(query, record))]
        hits.sort(key=lambda hit: (-float(hit.get("coverage") or 0), -int(hit.get("alignment_length") or 0), hit.get("accession") or ""))
        for index, hit in enumerate(hits, start=1):
            hit["rank"] = index
        return {
            "status": "completed" if hits else "no_hits",
            "hits": hits,
            "source": database_label or self.source,
        }

    def _match_record(self, query: str, record: Mapping[str, Any]) -> dict[str, Any] | None:
        part_sequence = _normalize_sequence(str(_first_present(record, "sequence", "Sequence")))
        if not part_sequence:
            return None

        match_type = ""
        alignment_length = 0
        coverage = 0.0
        if query == part_sequence:
            match_type = "exact_match"
            alignment_length = len(query)
            coverage = 100.0
        elif part_sequence in query:
            match_type = "query_contains_part"
            alignment_length = len(part_sequence)
            coverage = round((len(part_sequence) / max(len(query), 1)) * 100, 2)
        elif query in part_sequence:
            match_type = "part_contains_query"
            alignment_length = len(query)
            coverage = 100.0
        elif query == _reverse_complement(part_sequence):
            match_type = "reverse_complement_exact_match"
            alignment_length = len(query)
            coverage = 100.0

        if not match_type:
            return None

        part_id = str(_first_present(record, "id", "ID"))
        name = str(_first_present(record, "name", "Name", default=part_id or "Local part"))
        host = str(_first_present(record, "host", "organism", "Organism"))
        part_type = str(_first_present(record, "part_type", "canonical_type", "Type"))
        description = str(_first_present(record, "description", "Description", default=name))
        accession = part_id or name

        return {
            "accession": accession,
            "organism": host,
            "description": description or name,
            "percent_identity": 100.0,
            "coverage": coverage,
            "e_value": "local_exact",
            "alignment_length": alignment_length,
            "alignment_summary": self._alignment_summary(match_type, name, alignment_length),
            "match_type": match_type,
            "part_type": part_type,
            "source": self.source,
        }

    @staticmethod
    def _alignment_summary(match_type: str, part_name: str, alignment_length: int) -> str:
        label = match_type.replace("_", " ")
        return f"Local registry {label} with {part_name} over {alignment_length} bp."
