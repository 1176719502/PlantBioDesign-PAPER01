"""Durable, isolated Agent candidate and adoption storage.

The store deliberately lives beside (rather than inside) Formal state.  It
uses atomic JSON replacement, a signed journal, and an independent recovery
marker so a process restart can classify an adoption as not-started,
in-progress, committed, or recovery-required.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from services import agent_contracts as _agent_contracts
from services.agent_contracts import (
    AdoptionReceipt,
    AdoptionRequest,
    AgentCandidate,
    AgentValidationSummary,
    CandidateState,
    ComponentReference,
    ComponentTier,
    DeterministicValidationStatus,
    AgentIntegrityKey,
    IntegrityKeyError,
    candidate_digest,
    sign_payload,
    utc_timestamp,
    verify_payload,
)


class CandidateStoreError(RuntimeError):
    pass


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _normalized_inputs_digest(value: Any) -> str:
    canonical = json.dumps(_json(value or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _confirmation_token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stored_enum_member(enum_type: Any, value: Any) -> Any:
    if type(value) is not str:
        raise ValueError("stored enum value must be a string")
    return enum_type(value)


def _validator_accepts_component_generation(
    validator: Callable[[Any], Any], candidate: Any
) -> bool:
    refs = tuple(getattr(candidate, "component_references", ()) or ())
    if not refs:
        return True
    function = getattr(validator, "__func__", validator)
    expected_tier = getattr(function, "__globals__", {}).get("ComponentTier")
    if not isinstance(expected_tier, type):
        return True
    trusted_enum_value_is = getattr(function, "__globals__", {}).get(
        "_trusted_enum_value_is"
    )
    if callable(trusted_enum_value_is):
        try:
            return all(
                any(trusted_enum_value_is(ref.tier, member) for member in expected_tier)
                for ref in refs
            )
        except (AttributeError, TypeError, ValueError):
            return False
    return all(type(ref.tier) is expected_tier for ref in refs)


def _formal_snapshot_payload(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    elif is_dataclass(value):
        value = asdict(value)
    elif isinstance(value, Mapping):
        value = dict(value)
    elif hasattr(value, "__dict__"):
        value = vars(value)
    return _json(value)


def _artifact_sha256(row: Mapping[str, Any]) -> str | None:
    if "data" in row:
        return hashlib.sha256(str(row.get("data") or "").encode("utf-8")).hexdigest()
    if row.get("path"):
        try:
            return hashlib.sha256(Path(str(row["path"])).read_bytes()).hexdigest()
        except OSError:
            return None
    return str(row.get("sha256") or "") or None


def candidate_to_dict(candidate: AgentCandidate, *, project_id: str = "", normalized_inputs: Mapping[str, Any] | None = None, artifacts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    digest = _agent_contracts.candidate_digest(candidate)
    artifact_rows = {}
    for name, artifact in dict(artifacts or {}).items():
        row = dict(artifact) if isinstance(artifact, Mapping) else {"data": str(artifact)}
        row["input_signature"] = digest
        artifact_digest = _artifact_sha256(row)
        if artifact_digest: row["sha256"] = artifact_digest
        artifact_rows[str(name)] = row
    normalized = _json(normalized_inputs or {})
    return {
        "candidate_id": candidate.candidate_id,
        "project_id": project_id,
        "request_id": candidate.request_id,
        "workflow_type": candidate.workflow_type,
        "host": candidate.host,
        "user_intent": candidate.user_intent,
        "cds_or_reference_input": _json(candidate.cds_or_reference_input),
        "component_references": [asdict(ref) | {"tier": ref.tier.value} for ref in candidate.component_references],
        "component_tiers": [tier.value for tier in candidate.component_tiers],
        "component_identities": [ref.component_id for ref in candidate.component_references],
        "admission_modes": [ref.tier.value for ref in candidate.component_references],
        "evidence_references": list(candidate.evidence_references),
        "provenance_references": list(candidate.provenance_references),
        "unresolved_requirements": list(candidate.unresolved_requirements),
        "deterministic_validation": asdict(candidate.deterministic_validation) | {"status": candidate.deterministic_validation.status.value},
        "provider_metadata": _json(candidate.provider_metadata),
        "human_confirmation_state": candidate.human_confirmation_state,
        "state": candidate.state.value,
        "rationale": candidate.rationale,
        "content_digest": digest,
        "normalized_inputs": normalized,
        "normalized_inputs_digest": _normalized_inputs_digest(normalized),
        "artifacts": _json(artifact_rows),
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
    }


def candidate_from_dict(payload: Mapping[str, Any]) -> AgentCandidate:
    contracts = _agent_contracts
    refs = []
    for item in payload.get("component_references") or ():
        row = dict(item)
        if "tier" in row:
            row["tier"] = _stored_enum_member(contracts.ComponentTier, row["tier"])
        refs.append(contracts.ComponentReference(**row))
    refs = tuple(refs)
    validation = dict(payload.get("deterministic_validation") or {})
    validation["status"] = _stored_enum_member(
        contracts.DeterministicValidationStatus,
        validation.get("status", "NOT_RUN"),
    )
    return contracts.AgentCandidate(
        candidate_id=str(payload["candidate_id"]), workflow_type=str(payload.get("workflow_type") or ""),
        host=payload.get("host"), user_intent=str(payload.get("user_intent") or ""),
        cds_or_reference_input=payload.get("cds_or_reference_input"), component_references=refs,
        component_tiers=tuple(_stored_enum_member(contracts.ComponentTier, x) for x in (payload.get("component_tiers") or [r.tier.value for r in refs])),
        evidence_references=tuple(payload.get("evidence_references") or ()), provenance_references=tuple(payload.get("provenance_references") or ()),
        unresolved_requirements=tuple(payload.get("unresolved_requirements") or ()), deterministic_validation=contracts.AgentValidationSummary(**validation),
        provider_metadata=dict(payload.get("provider_metadata") or {}), human_confirmation_state=str(payload.get("human_confirmation_state") or "NOT_CONFIRMED"),
        state=_stored_enum_member(contracts.CandidateState, payload.get("state", contracts.CandidateState.AUTO_GENERATED.value)), rationale=str(payload.get("rationale") or ""),
        request_id=str(payload.get("request_id") or ""), content_digest=str(payload.get("content_digest") or ""),
    )


class CandidateStore:
    def __init__(self, storage_dir: str | os.PathLike[str]) -> None:
        self.storage_dir = Path(storage_dir)
        self.candidates_dir = self.storage_dir / "candidates"
        self.receipts_dir = self.storage_dir / "receipts"
        self.journal_dir = self.storage_dir / "journal"
        self.recovery_dir = self.storage_dir / "recovery"
        try:
            self._integrity_key = AgentIntegrityKey(self.storage_dir).read()
        except IntegrityKeyError as exc:
            raise CandidateStoreError(str(exc)) from exc

    def _ensure(self) -> None:
        for path in (self.candidates_dir, self.receipts_dir, self.journal_dir, self.recovery_dir):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(value: str) -> str:
        if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for ch in value):
            raise CandidateStoreError("invalid candidate storage identity")
        return value

    def _atomic(self, path: Path, payload: Mapping[str, Any]) -> None:
        self._ensure()
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def _authenticated(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result["integrity"] = sign_payload(result, self._integrity_key)
        return result

    def verify_payload(self, payload: Mapping[str, Any]) -> None:
        if not verify_payload(payload, self._integrity_key):
            raise CandidateStoreError("candidate integrity verification failed")

    def save(self, candidate: AgentCandidate, *, project_id: str, normalized_inputs: Mapping[str, Any] | None = None, artifacts: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = candidate_to_dict(candidate, project_id=project_id, normalized_inputs=normalized_inputs, artifacts=artifacts)
        path = self.candidates_dir / f"{self._safe(candidate.candidate_id)}.json"
        existing = self.load_payload(candidate.candidate_id, required=False, verify=True)
        if existing:
            payload["created_at"] = existing.get("created_at", payload["created_at"])
            payload["candidate_revision"] = int(existing.get("candidate_revision") or 0) + 1
        else:
            payload["candidate_revision"] = 1
        payload = self._authenticated(payload)
        self._atomic(path, payload)
        return payload

    def load_payload(self, candidate_id: str, *, required: bool = True, verify: bool = False) -> dict[str, Any] | None:
        path = self.candidates_dir / f"{self._safe(candidate_id)}.json"
        if not path.exists():
            if required: raise CandidateStoreError("candidate was not found")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise CandidateStoreError("candidate record is invalid")
            if verify:
                self.verify_payload(payload)
            return payload
        except (OSError, json.JSONDecodeError) as exc: raise CandidateStoreError("candidate record is unreadable") from exc

    def load(self, candidate_id: str) -> AgentCandidate: return candidate_from_dict(self.load_payload(candidate_id, verify=True) or {})

    def update(self, candidate: AgentCandidate, **fields: Any) -> dict[str, Any]:
        payload = self.load_payload(candidate.candidate_id, verify=True)
        payload.update(_json(fields)); payload["updated_at"] = utc_timestamp()
        if "artifacts" in payload:
            normalized_artifacts: dict[str, Any] = {}
            for name, artifact in dict(payload.get("artifacts") or {}).items():
                row = dict(artifact) if isinstance(artifact, Mapping) else {"data": str(artifact)}
                row["input_signature"] = str(payload.get("content_digest") or _agent_contracts.candidate_digest(candidate))
                digest = _artifact_sha256(row)
                if digest:
                    row["sha256"] = digest
                normalized_artifacts[str(name)] = row
            payload["artifacts"] = normalized_artifacts
        payload["candidate_revision"] = int(payload.get("candidate_revision") or 0) + 1
        payload = self._authenticated(payload)
        self._atomic(self.candidates_dir / f"{self._safe(candidate.candidate_id)}.json", payload)
        return payload

    def restore_payload(self, candidate_id: str, payload: Mapping[str, Any]) -> None:
        restored = dict(payload)
        self.verify_payload(restored)
        self._atomic(self.candidates_dir / f"{self._safe(candidate_id)}.json", restored)

    def write_journal(self, transaction_id: str, payload: Mapping[str, Any]) -> None:
        row = {"transaction_id": transaction_id, **_json(payload), "updated_at": utc_timestamp()}
        row["integrity"] = sign_payload(row, self._integrity_key)
        self._atomic(self.journal_dir / f"{self._safe(transaction_id)}.json", row)

    def journal(self, transaction_id: str) -> dict[str, Any]:
        path = self.journal_dir / f"{self._safe(transaction_id)}.json"
        if not path.exists(): raise CandidateStoreError("adoption journal was not found")
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict) or not verify_payload(row, self._integrity_key):
            raise CandidateStoreError("adoption journal integrity verification failed")
        return row

    def list_journal(self) -> list[dict[str, Any]]:
        self._ensure()
        rows = []
        for path in self.journal_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict) and verify_payload(row, self._integrity_key):
                    rows.append(row)
            except (OSError, json.JSONDecodeError): continue
        return sorted(rows, key=lambda row: str(row.get("updated_at") or ""))

    def write_recovery_marker(self, transaction_id: str, payload: Mapping[str, Any]) -> None:
        row = {
            **_json(payload),
            "transaction_id": transaction_id,
            "status": "RECOVERY_REQUIRED",
            "updated_at": utc_timestamp(),
        }
        row["integrity"] = sign_payload(row, self._integrity_key)
        self._atomic(self.recovery_dir / f"{self._safe(transaction_id)}.json", row)

    def list_recovery_markers(self) -> list[dict[str, Any]]:
        self._ensure()
        rows = []
        for path in self.recovery_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CandidateStoreError("adoption recovery marker is unreadable") from exc
            if not isinstance(row, dict) or not verify_payload(row, self._integrity_key):
                raise CandidateStoreError("adoption recovery marker integrity verification failed")
            if row.get("status") != "RECOVERY_REQUIRED" or row.get("transaction_id") != path.stem:
                raise CandidateStoreError("adoption recovery marker is invalid")
            rows.append(row)
        return sorted(rows, key=lambda row: str(row.get("updated_at") or ""))

    def save_receipt(self, receipt: AdoptionReceipt) -> AdoptionReceipt:
        payload = self._authenticated(asdict(receipt))
        self._atomic(self.receipts_dir / f"{self._safe(receipt.receipt_id)}.json", payload)
        return receipt

    def delete_receipt(self, receipt_id: str) -> None:
        path = self.receipts_dir / f"{self._safe(receipt_id)}.json"
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise CandidateStoreError("adoption receipt rollback failed") from exc

    def _load_receipt_record(self, receipt_id: str) -> tuple[AdoptionReceipt, dict[str, Any]]:
        path = self.receipts_dir / f"{self._safe(receipt_id)}.json"
        if not path.exists():
            raise CandidateStoreError("adoption receipt was not found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CandidateStoreError("adoption receipt is unreadable") from exc
        if not isinstance(payload, dict) or not verify_payload(payload, self._integrity_key):
            raise CandidateStoreError("adoption receipt integrity verification failed")
        receipt_payload = {key: value for key, value in payload.items() if key != "integrity"}
        try:
            receipt = _agent_contracts.AdoptionReceipt(**receipt_payload)
        except (TypeError, ValueError) as exc:
            raise CandidateStoreError("adoption receipt is invalid") from exc
        if receipt.receipt_id != receipt_id:
            raise CandidateStoreError("adoption receipt storage identity mismatch")
        return receipt, payload

    def _load_receipt_raw(self, receipt_id: str) -> AdoptionReceipt:
        return self._load_receipt_record(receipt_id)[0]

    def adoption_requires_recovery(self, candidate_id: str, project_id: str) -> bool:
        candidate_id = self._safe(candidate_id)
        project_id = self._safe(project_id)
        try:
            markers = self.list_recovery_markers()
            journals = [
                row for row in self.list_journal()
                if row.get("candidate_id") == candidate_id and row.get("project_id") == project_id
            ]
            if any(
                row.get("candidate_id") == candidate_id and row.get("project_id") == project_id
                for row in markers
            ):
                return True
            if any(row.get("status") in {"IN_PROGRESS", "RECOVERY_REQUIRED"} for row in journals):
                return True
            payload = self.load_payload(candidate_id, required=False, verify=True)
            if payload is None:
                return False
            if payload.get("state") == CandidateState.USER_ADOPTED.value:
                receipt_id = str(payload.get("adoption_receipt_id") or "")
                return not receipt_id or not self.receipt_is_authoritative(receipt_id)
            return False
        except CandidateStoreError as exc:
            # A corrupt candidate is handled by the normal adoption validation
            # path, which records a deterministic FAILED journal.  Only
            # recovery-store failures themselves force the conservative block.
            if "recovery marker" in str(exc):
                return True
            return False

    def receipt_is_authoritative(self, receipt_id: str) -> bool:
        try:
            receipt, receipt_payload = self._load_receipt_record(receipt_id)
            if any(row.get("transaction_id") == receipt.transaction_id for row in self.list_recovery_markers()):
                return False
            journal = next(
                (row for row in self.list_journal() if row.get("transaction_id") == receipt.transaction_id),
                None,
            )
            if not journal or journal.get("status") != "COMMITTED":
                return False
            payload = self.load_payload(receipt.candidate_id, verify=True) or {}
            candidate = candidate_from_dict(payload)
            return (
                receipt.adoption_status == "COMMITTED"
                and candidate.state is _agent_contracts.CandidateState.USER_ADOPTED
                and payload.get("adoption_receipt_id") == receipt_id
                and payload.get("project_id") == receipt.project_id
                and payload.get("content_digest") == receipt.candidate_digest
                and _agent_contracts.candidate_digest(candidate) == receipt.candidate_digest
                and payload.get("candidate_revision") == receipt.candidate_revision
                and journal.get("candidate_id") == receipt.candidate_id
                and journal.get("project_id") == receipt.project_id
                and journal.get("receipt_id") == receipt.receipt_id
                and journal.get("candidate_digest") == receipt.candidate_digest
                and journal.get("candidate_revision") == receipt.candidate_revision
                and journal.get("receipt_signature") == receipt_payload["integrity"]["signature"]
            )
        except (CandidateStoreError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return False

    def load_receipt(self, receipt_id: str) -> AdoptionReceipt:
        if not self.receipt_is_authoritative(receipt_id):
            raise CandidateStoreError("adoption receipt is not authoritative")
        return self._load_receipt_raw(receipt_id)


class AdoptionService:
    """Explicit, fail-closed adoption boundary for a CandidateStore."""
    def __init__(self, store: CandidateStore, *, formal_repository: Any | None = None, formal_applier: Callable[[Any, AgentCandidate], Any] | None = None, validator: Callable[[AgentCandidate], AgentCandidate] | None = None) -> None:
        self.store, self.formal_repository, self.formal_applier, self.validator = store, formal_repository, formal_applier, validator

    def adopt(self, request: AdoptionRequest) -> AdoptionReceipt:
        if self.store.adoption_requires_recovery(request.candidate_id, request.project_id):
            raise CandidateStoreError("adoption blocked; recovery required")
        transaction_id = f"adopt-{uuid4().hex}"
        try:
            self.store.write_journal(transaction_id, {"status": "IN_PROGRESS", "candidate_id": request.candidate_id, "project_id": request.project_id})
        except Exception as exc:
            raise CandidateStoreError("adoption failed; recovery required because the journal could not be started") from exc
        try:
            payload = self.store.load_payload(request.candidate_id, verify=True) or {}
        except CandidateStoreError:
            return self._fail(transaction_id, "candidate_revision_mismatch")
        try:
            candidate = candidate_from_dict(payload)
        except (TypeError, ValueError, KeyError) as exc:
            return self._fail(transaction_id, "candidate_revision_mismatch")
        if str(payload.get("project_id") or "") != request.project_id: return self._fail(transaction_id, "project_mismatch")
        if _agent_contracts.candidate_digest(candidate) != request.candidate_digest or str(payload.get("content_digest")) != request.candidate_digest: return self._fail(transaction_id, "candidate_revision_mismatch")
        if str(payload.get("normalized_inputs_digest") or "") != _normalized_inputs_digest(payload.get("normalized_inputs") or {}): return self._fail(transaction_id, "candidate_revision_mismatch")
        if candidate.state is not _agent_contracts.CandidateState.VALIDATED_CANDIDATE or candidate.deterministic_validation.status is not _agent_contracts.DeterministicValidationStatus.PASS: return self._fail(transaction_id, "candidate_not_validated")
        binding = payload.get("confirmation_binding")
        if not isinstance(binding, Mapping): return self._fail(transaction_id, "confirmation_required")
        if (
            binding.get("candidate_id") != candidate.candidate_id
            or binding.get("project_id") != request.project_id
            or binding.get("request_id") != candidate.request_id
            or binding.get("candidate_digest") != request.candidate_digest
            or not hmac.compare_digest(str(binding.get("token_sha256") or ""), _confirmation_token_digest(request.confirmation_token))
        ):
            return self._fail(transaction_id, "confirmation_mismatch")
        for artifact in (payload.get("artifacts") or {}).values():
            if isinstance(artifact, Mapping):
                if artifact.get("fresh") is False or artifact.get("input_signature") not in {request.candidate_digest, ""}:
                    return self._fail(transaction_id, "artifact_stale")
                if not self._artifact_matches(artifact):
                    return self._fail(transaction_id, "artifact_digest_mismatch")
        if self.validator is not None:
            if not _validator_accepts_component_generation(self.validator, candidate):
                return self._fail(transaction_id, "candidate_contract_generation_mismatch")
            try:
                candidate = self.validator(candidate)
            except Exception:
                return self._fail(transaction_id, "deterministic_validation_failed")
        if candidate.deterministic_validation.status is not _agent_contracts.DeterministicValidationStatus.PASS: return self._fail(transaction_id, "deterministic_validation_failed")
        previous = None
        original_payload = copy.deepcopy(payload)
        receipt = None
        try:
            if self.formal_repository is not None:
                previous = self.formal_repository.load(request.project_id)
                rollback_snapshot = copy.deepcopy(previous)
                if self.formal_applier is not None:
                    applied = self.formal_applier(copy.deepcopy(previous), candidate)
                    if applied is not None:
                        self.formal_repository.save(applied)
                else:
                    applied = copy.deepcopy(previous)
                    applied.extra_fields = dict(applied.extra_fields); applied.extra_fields["agent_adoption"] = {"candidate_id": candidate.candidate_id, "candidate_digest": request.candidate_digest, "adopted_at": utc_timestamp()}
                    self.formal_repository.save(applied)
            receipt = _agent_contracts.AdoptionReceipt(receipt_id=f"receipt-{uuid4().hex}", transaction_id=transaction_id, candidate_id=candidate.candidate_id, project_id=request.project_id, candidate_digest=request.candidate_digest, candidate_revision=int(payload.get("candidate_revision") or 0) + 1, adopted_at=utc_timestamp(), validation_version="agent-product-deterministic-v1", component_identities=tuple(ref.component_id for ref in candidate.component_references), sequence_provenance={"references": list(candidate.provenance_references)}, artifact_identities=dict(payload.get("artifacts") or {}), provider=str(candidate.provider_metadata.get("provider") or ""), model=str(candidate.provider_metadata.get("model") or ""))
            adopted_payload = self.store.update(candidate, state=_agent_contracts.CandidateState.USER_ADOPTED.value, adoption_receipt_id=receipt.receipt_id)
            if adopted_payload.get("candidate_revision") != receipt.candidate_revision:
                raise CandidateStoreError("adoption candidate revision did not match the receipt")
            self.store.save_receipt(receipt)
            _, receipt_payload = self.store._load_receipt_record(receipt.receipt_id)
            self.store.write_journal(transaction_id, {"status": "COMMITTED", "candidate_id": candidate.candidate_id, "project_id": request.project_id, "receipt_id": receipt.receipt_id, "candidate_digest": request.candidate_digest, "candidate_revision": receipt.candidate_revision, "receipt_signature": receipt_payload["integrity"]["signature"]})
            return receipt
        except Exception as exc:
            rollback_errors: list[str] = []
            try:
                self.store.restore_payload(candidate.candidate_id, original_payload)
            except Exception as rollback_exc:
                rollback_errors.append(f"candidate:{type(rollback_exc).__name__}")
            if receipt is not None:
                try:
                    self.store.delete_receipt(receipt.receipt_id)
                except Exception as rollback_exc:
                    rollback_errors.append(f"receipt:{type(rollback_exc).__name__}")
            status = "FAILED_ROLLED_BACK"
            if previous is not None and self.formal_repository is not None:
                try:
                    restore_exact = getattr(self.formal_repository, "restore_exact", None)
                    if callable(restore_exact):
                        restore_exact(rollback_snapshot)
                    else:
                        self.formal_repository.save(rollback_snapshot)
                    restored = self.formal_repository.load(request.project_id)
                    if _formal_snapshot_payload(restored) != _formal_snapshot_payload(rollback_snapshot):
                        raise CandidateStoreError("formal rollback verification failed")
                except Exception as rollback_exc:
                    rollback_errors.append(f"formal:{type(rollback_exc).__name__}")
            if rollback_errors:
                status = "RECOVERY_REQUIRED"
                try:
                    self.store.write_recovery_marker(transaction_id, {"candidate_id": candidate.candidate_id, "project_id": request.project_id, "receipt_id": receipt.receipt_id if receipt is not None else "", "error": type(exc).__name__, "rollback_errors": rollback_errors})
                except Exception:
                    pass
            try:
                self.store.write_journal(transaction_id, {"status": status, "candidate_id": candidate.candidate_id, "project_id": request.project_id, "receipt_id": receipt.receipt_id if receipt is not None else "", "error": type(exc).__name__, "rollback_errors": rollback_errors})
            except Exception as journal_exc:
                try:
                    self.store.write_recovery_marker(transaction_id, {"candidate_id": candidate.candidate_id, "project_id": request.project_id, "receipt_id": receipt.receipt_id if receipt is not None else "", "error": type(exc).__name__, "rollback_errors": rollback_errors, "primary_journal_error": type(journal_exc).__name__})
                except Exception:
                    pass
                raise CandidateStoreError("adoption failed; recovery required because the failure journal could not be persisted") from journal_exc
            message = "adoption failed and was rolled back" if status == "FAILED_ROLLED_BACK" else "adoption failed; recovery required"
            raise CandidateStoreError(message) from exc

    @staticmethod
    def _artifact_matches(artifact: Mapping[str, Any]) -> bool:
        expected = str(artifact.get("sha256") or "")
        if not expected:
            return False
        if "data" in artifact:
            actual = hashlib.sha256(str(artifact.get("data") or "").encode("utf-8")).hexdigest()
        elif artifact.get("path"):
            try:
                actual = hashlib.sha256(Path(str(artifact["path"])).read_bytes()).hexdigest()
            except OSError:
                return False
        else:
            return False
        return hmac.compare_digest(actual, expected)

    def _fail(self, transaction_id: str, reason: str):
        try:
            self.store.write_journal(transaction_id, {"status": "FAILED", "error": reason})
        except Exception as exc:
            raise CandidateStoreError("adoption failed; recovery required because the failure journal could not be persisted") from exc
        raise CandidateStoreError(reason)


__all__ = ["AdoptionService", "CandidateStore", "CandidateStoreError", "candidate_from_dict", "candidate_to_dict"]
