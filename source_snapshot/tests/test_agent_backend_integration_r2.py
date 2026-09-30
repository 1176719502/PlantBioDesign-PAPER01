from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

import pytest

from services.agent_candidate_store import AdoptionService, CandidateStore, CandidateStoreError
from services.agent_contracts import AdoptionRequest, AgentRequest, candidate_digest
from services.agent_provider import FakeQwenTransport, ProviderFailureCode, ProviderError, QwenConfig, QwenProvider
from services.agent_service import AgentService


@dataclass
class Project:
    project_id: str
    extra_fields: dict = field(default_factory=dict)


class Repo:
    def __init__(self) -> None:
        self.projects = {"project-1": Project("project-1")}

    def load(self, project_id: str) -> Project:
        return self.projects[project_id]

    def save(self, project: Project) -> Project:
        self.projects[project.project_id] = project
        return project


def _request() -> AgentRequest:
    return AgentRequest(
        request_id="req-r2",
        workflow_type="single_gene",
        host="Arabidopsis",
        user_intent="prepare a candidate",
        cds_or_reference_input="ATG",
        context={"project_id": "project-1"},
    )


def _confirmed(tmp_path: Path, *, artifacts: dict | None = None):
    store = CandidateStore(tmp_path)
    service = AgentService(QwenProvider(config=QwenConfig(model="test-model"), transport=FakeQwenTransport()), candidate_store=store, project_id="project-1")
    generated = service.generate(_request()).candidates[0]
    if artifacts is not None:
        store.update(generated, artifacts=artifacts)
    validated = service.validate_candidate(generated)
    if artifacts is not None:
        store.update(validated, artifacts=artifacts)
    preview = service.build_adoption_preview(validated)
    confirmed = service.confirm_candidate(validated, confirmation_id="confirm-r2", preview=preview)
    return store, confirmed


def _adopt(store: CandidateStore, candidate, repo: Repo | None = None):
    repo = repo or Repo()
    return AdoptionService(store, formal_repository=repo).adopt(
        AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
    )


@pytest.mark.parametrize("mutation", ["confirmation", "normalized", "content"])
def test_record_only_recompute_attacks_fail_before_formal_mutation(tmp_path: Path, mutation: str) -> None:
    store, candidate = _confirmed(tmp_path)
    path = tmp_path / "candidates" / f"{candidate.candidate_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "confirmation":
        payload["confirmation_binding"]["token_sha256"] = hashlib.sha256(b"attacker-token").hexdigest()
    elif mutation == "normalized":
        payload["normalized_inputs"]["request_digest"] = "attacker-request"
        payload["normalized_inputs_digest"] = hashlib.sha256(
            json.dumps(payload["normalized_inputs"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    else:
        payload["rationale"] = "attacker content"
        payload["content_digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    repo = Repo()
    with pytest.raises(CandidateStoreError):
        _adopt(store, candidate, repo)
    assert repo.load("project-1").extra_fields == {}
    assert store.list_journal()[-1]["status"] == "FAILED"


def test_artifact_bytes_changed_with_recomputed_local_sha_fail_closed(tmp_path: Path) -> None:
    store, candidate = _confirmed(tmp_path, artifacts={"record": {"identity": "artifact-1", "data": "original"}})
    path = tmp_path / "candidates" / f"{candidate.candidate_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifact = payload["artifacts"]["record"]
    artifact["data"] = "tampered"
    artifact["sha256"] = hashlib.sha256(b"tampered").hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CandidateStoreError):
        _adopt(store, candidate)


def test_artifact_bytes_changed_without_metadata_change_fail_closed(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_bytes(b"original")
    store, candidate = _confirmed(tmp_path, artifacts={"record": {"identity": "artifact-1", "path": str(artifact_path)}})
    artifact_path.write_bytes(b"changed")
    with pytest.raises(CandidateStoreError, match="artifact_digest_mismatch"):
        _adopt(store, candidate)
    assert store.list_journal()[-1]["status"] == "FAILED"


def test_provider_response_id_is_fingerprinted_everywhere(tmp_path: Path) -> None:
    sentinel = "UBD_AGENT_SECRET_SENTINEL_DO_NOT_STORE"
    response = {
        "schema_version": "qwen-agent-response-v1",
        "status": "CANDIDATES",
        "interpretation": "reviewable record",
        "missing_inputs": [],
        "candidates": [{
            "candidate_id": "candidate-secret-r2",
            "evidence_references": [],
            "unresolved_requirements": [],
            "rationale": "record supplied facts",
        }],
        "alternatives": [],
        "explanation": "record only",
        "explanation_metadata": {"confidence": 0.5, "basis": ["user_supplied_facts"]},
        "metadata": {"provider": "qwen", "model": "test-model", "response_id": sentinel},
    }
    provider = QwenProvider(config=QwenConfig(model="test-model"), transport=FakeQwenTransport(response, response_id=sentinel))
    result = AgentService(provider, candidate_store=CandidateStore(tmp_path), project_id="project-1").generate(_request())
    serialized = json.dumps(result.trace.as_dict() if result.trace else {}, ensure_ascii=False)
    serialized += json.dumps(result.candidates[0].provider_metadata if result.candidates else {}, ensure_ascii=False)
    serialized += (tmp_path / "candidates" / "candidate-secret-r2.json").read_text(encoding="utf-8")
    assert sentinel not in serialized
    assert result.trace is not None and result.trace.provider_response_id is not None


class ReceiptWriteThenFailStore(CandidateStore):
    def save_receipt(self, receipt):
        super().save_receipt(receipt)
        raise OSError("receipt write acknowledgement fault")

    def delete_receipt(self, receipt_id: str) -> None:
        raise OSError("receipt cleanup fault")


class CandidateRollbackFailStore(ReceiptWriteThenFailStore):
    def restore_payload(self, candidate_id: str, payload):
        raise OSError("candidate rollback fault")


class FormalRollbackFailRepo(Repo):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def save(self, project: Project) -> Project:
        self.calls += 1
        if self.calls > 1:
            raise OSError("formal rollback fault")
        return super().save(project)


class JournalFailureStore(CandidateStore):
    def __init__(self, storage_dir, *, fail_on_call: int = 2):
        super().__init__(storage_dir)
        self.journal_calls = 0
        self.fail_on_call = fail_on_call

    def write_journal(self, transaction_id: str, payload):
        self.journal_calls += 1
        if self.journal_calls >= self.fail_on_call:
            raise OSError("journal persistence fault")
        return super().write_journal(transaction_id, payload)


@pytest.mark.parametrize("store_type,repo_type", [
    (ReceiptWriteThenFailStore, Repo),
    (CandidateRollbackFailStore, Repo),
    (ReceiptWriteThenFailStore, FormalRollbackFailRepo),
])
def test_rollback_failures_are_recovery_required_and_not_authoritative(tmp_path: Path, store_type, repo_type) -> None:
    base, candidate = _confirmed(tmp_path)
    store = store_type(tmp_path)
    repo = repo_type()
    with pytest.raises(CandidateStoreError, match="recovery required"):
        _adopt(store, candidate, repo)
    journal = store.list_journal()[-1]
    assert journal["status"] == "RECOVERY_REQUIRED"
    assert not any(store.receipt_is_authoritative(path.stem) for path in (tmp_path / "receipts").glob("*.json"))


def test_authoritative_receipt_requires_committed_journal_and_adopted_record(tmp_path: Path) -> None:
    store, candidate = _confirmed(tmp_path)
    receipt = _adopt(store, candidate)
    assert store.receipt_is_authoritative(receipt.receipt_id)
    journal_path = next((tmp_path / "journal").glob("*.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["status"] = "RECOVERY_REQUIRED"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    assert not store.receipt_is_authoritative(receipt.receipt_id)
    with pytest.raises(CandidateStoreError, match="not authoritative"):
        store.load_receipt(receipt.receipt_id)


def test_journal_failure_is_explicitly_recovery_required(tmp_path: Path) -> None:
    base, candidate = _confirmed(tmp_path)
    store = JournalFailureStore(tmp_path)
    with pytest.raises(CandidateStoreError, match="recovery required"):
        _adopt(store, candidate, Repo())


def test_initial_journal_failure_cannot_start_adoption(tmp_path: Path) -> None:
    store = JournalFailureStore(tmp_path, fail_on_call=1)
    candidate_store, candidate = _confirmed(tmp_path / "source")
    with pytest.raises(CandidateStoreError, match="journal could not be started"):
        _adopt(store, candidate, Repo())


def test_packaged_agent_modules_are_in_static_runtime_closure() -> None:
    manifest = json.loads(Path("packaging/resource_manifest.json").read_text(encoding="utf-8"))
    closure = set(manifest["runtime_python_modules"])
    assert {
        "services/agent_candidate_store.py",
        "services/agent_contracts.py",
        "services/agent_product_adapter.py",
        "services/agent_provider.py",
        "services/agent_service.py",
    } <= closure


def test_provider_error_public_message_and_response_id_are_safe() -> None:
    sentinel = "arbitrary-secret-response-id"
    error = ProviderError(ProviderFailureCode.PROVIDER_UNAVAILABLE, sentinel, response_id=sentinel)
    assert sentinel not in str(error)
    assert sentinel not in error.message
    assert error.response_id != sentinel
