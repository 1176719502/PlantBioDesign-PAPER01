from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from services.knowledge_base.constants import (
    CONTRACT_VERSION,
    SNAPSHOT_FIELD,
    SNAPSHOT_REQUIRED_FIELDS,
)
from services.knowledge_base.errors import KnowledgeSnapshotError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeSnapshotError(f"{field_name} must be non-empty text")
    return value.strip()


def _require_sha256(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise KnowledgeSnapshotError(f"{field_name} must be a lowercase SHA-256 value")
    return value


def _require_utc(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if not text.endswith("Z"):
        raise KnowledgeSnapshotError(f"{field_name} must be an RFC3339 UTC timestamp")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise KnowledgeSnapshotError(f"{field_name} must be an RFC3339 UTC timestamp") from exc
    return text


@dataclass(frozen=True)
class KnowledgeReferenceSnapshot:
    kb_contract_version: str
    kb_dataset_version: str
    entity_key: str
    entity_revision: int
    entity_payload_sha256: str
    selected_sequence_sha256: str
    snapshot_created_at_utc: str
    registry_component_id: str = ""
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False, compare=True)

    def __post_init__(self) -> None:
        _require_text(self.kb_contract_version, "kb_contract_version")
        _require_text(self.kb_dataset_version, "kb_dataset_version")
        entity_key = _require_text(self.entity_key, "entity_key")
        if not entity_key.startswith("kb:"):
            raise KnowledgeSnapshotError("entity_key must use the kb: namespace")
        if isinstance(self.entity_revision, bool) or not isinstance(self.entity_revision, int):
            raise KnowledgeSnapshotError("entity_revision must be an integer")
        if self.entity_revision < 1:
            raise KnowledgeSnapshotError("entity_revision must be at least 1")
        _require_sha256(self.entity_payload_sha256, "entity_payload_sha256")
        _require_sha256(
            self.selected_sequence_sha256,
            "selected_sequence_sha256",
            allow_empty=True,
        )
        _require_utc(self.snapshot_created_at_utc, "snapshot_created_at_utc")
        if not isinstance(self.registry_component_id, str):
            raise KnowledgeSnapshotError("registry_component_id must be text")
        if not isinstance(self.extra_fields, dict):
            raise KnowledgeSnapshotError("extra_fields must be a mapping")

    @classmethod
    def create(
        cls,
        *,
        dataset_version: str,
        entity_key: str,
        entity_revision: int,
        entity_payload_sha256: str,
        snapshot_created_at_utc: str,
        selected_sequence_sha256: str = "",
        registry_component_id: str = "",
    ) -> "KnowledgeReferenceSnapshot":
        return cls(
            kb_contract_version=CONTRACT_VERSION,
            kb_dataset_version=dataset_version,
            entity_key=entity_key,
            entity_revision=entity_revision,
            entity_payload_sha256=entity_payload_sha256,
            selected_sequence_sha256=selected_sequence_sha256,
            snapshot_created_at_utc=snapshot_created_at_utc,
            registry_component_id=registry_component_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "KnowledgeReferenceSnapshot":
        if not isinstance(payload, Mapping):
            raise KnowledgeSnapshotError("knowledge snapshot must be a mapping")
        missing = [field_name for field_name in SNAPSHOT_REQUIRED_FIELDS if field_name not in payload]
        if missing:
            raise KnowledgeSnapshotError(
                f"knowledge snapshot is missing required fields: {', '.join(missing)}"
            )
        known = set(SNAPSHOT_REQUIRED_FIELDS) | {"registry_component_id"}
        return cls(
            kb_contract_version=payload["kb_contract_version"],
            kb_dataset_version=payload["kb_dataset_version"],
            entity_key=payload["entity_key"],
            entity_revision=payload["entity_revision"],
            entity_payload_sha256=payload["entity_payload_sha256"],
            selected_sequence_sha256=payload["selected_sequence_sha256"],
            snapshot_created_at_utc=payload["snapshot_created_at_utc"],
            registry_component_id=payload.get("registry_component_id", ""),
            extra_fields={
                key: copy.deepcopy(value)
                for key, value in payload.items()
                if key not in known
            },
        )

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra_fields)
        payload.update(
            {
                "kb_contract_version": self.kb_contract_version,
                "kb_dataset_version": self.kb_dataset_version,
                "entity_key": self.entity_key,
                "entity_revision": self.entity_revision,
                "entity_payload_sha256": self.entity_payload_sha256,
                "selected_sequence_sha256": self.selected_sequence_sha256,
                "snapshot_created_at_utc": self.snapshot_created_at_utc,
            }
        )
        if self.registry_component_id:
            payload["registry_component_id"] = self.registry_component_id
        return payload


def attach_snapshot_to_project_payload(
    project_payload: Mapping[str, Any],
    snapshot: KnowledgeReferenceSnapshot | Mapping[str, Any],
) -> dict[str, Any]:
    """Return an additive project payload without changing any project schema."""
    if not isinstance(project_payload, Mapping):
        raise KnowledgeSnapshotError("project payload must be a mapping")
    resolved = (
        snapshot
        if isinstance(snapshot, KnowledgeReferenceSnapshot)
        else KnowledgeReferenceSnapshot.from_mapping(snapshot)
    )
    result = copy.deepcopy(dict(project_payload))
    review_state = result.get("manual_review_state", {})
    if not isinstance(review_state, dict):
        raise KnowledgeSnapshotError("manual_review_state must be a mapping")
    review_state = copy.deepcopy(review_state)
    review_state[SNAPSHOT_FIELD] = resolved.to_dict()
    result["manual_review_state"] = review_state
    return result


def snapshot_from_project_payload(
    project_payload: Mapping[str, Any],
) -> KnowledgeReferenceSnapshot | None:
    if not isinstance(project_payload, Mapping):
        raise KnowledgeSnapshotError("project payload must be a mapping")
    review_state = project_payload.get("manual_review_state", {})
    if review_state is None:
        return None
    if not isinstance(review_state, Mapping):
        raise KnowledgeSnapshotError("manual_review_state must be a mapping")
    snapshot = review_state.get(SNAPSHOT_FIELD)
    if snapshot is None:
        return None
    if not isinstance(snapshot, Mapping):
        raise KnowledgeSnapshotError(f"{SNAPSHOT_FIELD} must be a mapping")
    return KnowledgeReferenceSnapshot.from_mapping(snapshot)
