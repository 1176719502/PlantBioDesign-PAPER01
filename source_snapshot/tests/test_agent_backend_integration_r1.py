from __future__ import annotations

from dataclasses import dataclass, field
import json

import pytest

from services.agent_candidate_store import AdoptionService, CandidateStore, CandidateStoreError
from services.agent_contracts import AdoptionRequest, AgentRequest, ComponentReference, ComponentTier, ToolCallRequest, candidate_digest
from services.agent_product_adapter import AgentProductAdapter, AgentToolDispatcher
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider, ProviderError, ProviderFailureCode
from services.agent_service import AgentService, V2ComponentRepository


def provider(transport=None):
    return QwenProvider(config=QwenConfig(model="test-model"), transport=transport or FakeQwenTransport())


def request(project_id="project-1"):
    return AgentRequest(request_id="req-r1", workflow_type="single_gene", host="Arabidopsis", user_intent="prepare a candidate", cds_or_reference_input="ATG", context={"project_id": project_id})


def test_v2_repository_uses_current_counts_and_blocks_known_ids():
    repo = V2ComponentRepository()
    assert len(repo._rows) == 171
    assert repo.resolve("V2-CMP-003").tier is ComponentTier.REFERENCE_ONLY
    assert repo.resolve("V2-CMP-126").tier is ComponentTier.REFERENCE_ONLY


def test_candidates_are_isolated_and_malformed_provider_does_not_write(tmp_path):
    store = CandidateStore(tmp_path)
    svc = AgentService(provider(), candidate_store=store, project_id="project-1")
    first = svc.generate(request()).candidates[0]
    second = svc.generate(AgentRequest(**{**request().__dict__, "request_id": "req-r2"})).candidates[0]
    assert first.candidate_id != second.candidate_id
    assert store.load(first.candidate_id).candidate_id == first.candidate_id
    bad = AgentService(provider(FakeQwenTransport({"schema_version": "wrong"})), candidate_store=store, project_id="project-1").generate(request("project-2"))
    assert bad.error_code == "schema_mismatch"
    assert len(list((tmp_path / "candidates").glob("*.json"))) == 2


def test_dispatcher_never_allows_model_formal_mutation():
    result = AgentToolDispatcher(AgentProductAdapter()).dispatch(ToolCallRequest("formal_project_write", {"project_id": "p"}))
    assert not result.ok and result.error_code == "MUTATION_REQUIRES_ADOPTION"


@dataclass
class FakeProject:
    project_id: str
    extra_fields: dict = field(default_factory=dict)


class FakeProjectRepo:
    def __init__(self): self.projects = {"project-1": FakeProject("project-1")}
    def load(self, project_id): return self.projects[project_id]
    def save(self, project): self.projects[project.project_id] = project; return project


def test_adoption_is_explicit_durable_and_survives_reopen(tmp_path):
    store = CandidateStore(tmp_path)
    repo = FakeProjectRepo()
    svc = AgentService(provider(), candidate_store=store, project_id="project-1")
    generated = svc.generate(request()).candidates[0]
    validated = svc.validate_candidate(generated)
    preview = svc.build_adoption_preview(validated)
    confirmed = svc.confirm_candidate(validated, confirmation_id="user-confirmed", preview=preview)
    with pytest.raises(Exception):
        AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(confirmed.candidate_id, "project-1", candidate_digest(confirmed), "wrong-token"))
    receipt = AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(confirmed.candidate_id, "project-1", candidate_digest(confirmed), "user-confirmed"))
    assert repo.load("project-1").extra_fields["agent_adoption"]["candidate_id"] == validated.candidate_id
    reopened = CandidateStore(tmp_path)
    assert reopened.load(confirmed.candidate_id).state.value == "USER_ADOPTED"
    assert reopened.load_receipt(receipt.receipt_id).candidate_digest == candidate_digest(confirmed)


def _confirmed_candidate(tmp_path, *, project_id="project-1", token="confirm-1"):
    store = CandidateStore(tmp_path)
    svc = AgentService(provider(), candidate_store=store, project_id=project_id)
    candidate = svc.validate_candidate(svc.generate(request(project_id)).candidates[0])
    preview = svc.build_adoption_preview(candidate)
    confirmed = svc.confirm_candidate(candidate, confirmation_id=token, preview=preview)
    return store, svc, confirmed


def test_confirmation_token_is_bound_to_candidate_context(tmp_path):
    store, _, candidate = _confirmed_candidate(tmp_path, token="token-a")
    service = AdoptionService(store, formal_repository=FakeProjectRepo())
    with pytest.raises(CandidateStoreError, match="confirmation_mismatch"):
        service.adopt(AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "wrong-token"))


def test_confirmation_token_from_another_candidate_cannot_be_replayed(tmp_path):
    store, svc, first = _confirmed_candidate(tmp_path, token="token-a")
    second = svc.validate_candidate(svc.generate(AgentRequest(**{**request().__dict__, "request_id": "req-r2"})).candidates[0])
    second_preview = svc.build_adoption_preview(second)
    svc.confirm_candidate(second, confirmation_id="token-b", preview=second_preview)
    with pytest.raises(CandidateStoreError, match="confirmation_mismatch"):
        AdoptionService(store, formal_repository=FakeProjectRepo()).adopt(AdoptionRequest(first.candidate_id, "project-1", candidate_digest(first), "token-b"))


def test_normalized_inputs_tampering_fails_before_formal_mutation(tmp_path):
    store, _, candidate = _confirmed_candidate(tmp_path)
    path = tmp_path / "candidates" / f"{candidate.candidate_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["normalized_inputs"]["request_digest"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    repo = FakeProjectRepo()
    with pytest.raises(CandidateStoreError, match="candidate_revision_mismatch"):
        AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-1"))
    assert repo.load("project-1").extra_fields == {}


class FailingReceiptStore(CandidateStore):
    def save_receipt(self, receipt):
        raise OSError("receipt persistence fault")


def test_post_formal_receipt_failure_rolls_back_candidate_and_formal_state(tmp_path):
    base_store, _, candidate = _confirmed_candidate(tmp_path)
    store = FailingReceiptStore(tmp_path)
    repo = FakeProjectRepo()
    with pytest.raises(CandidateStoreError, match="adoption failed"):
        AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-1"))
    assert store.load(candidate.candidate_id).state.value == "VALIDATED_CANDIDATE"
    assert list((tmp_path / "receipts").glob("*.json")) == []
    assert repo.load("project-1").extra_fields == {}


def test_candidate_state_failure_cannot_leave_success_receipt(tmp_path, monkeypatch):
    store, _, candidate = _confirmed_candidate(tmp_path)
    repo = FakeProjectRepo()
    original_update = store.update
    def fail_update(*args, **kwargs):
        raise OSError("candidate state fault")
    monkeypatch.setattr(store, "update", fail_update)
    with pytest.raises(CandidateStoreError, match="adoption failed"):
        AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-1"))
    assert list((tmp_path / "receipts").glob("*.json")) == []
    assert repo.load("project-1").extra_fields == {}


def test_empty_confirmation_token_is_rejected():
    with pytest.raises(Exception):
        AdoptionRequest("candidate-1", "project-1", "digest-1", "")


class FailingFormalRepo(FakeProjectRepo):
    def save(self, project):
        raise OSError("formal write fault")


def test_formal_write_failure_leaves_no_receipt_or_adopted_candidate(tmp_path):
    store, _, candidate = _confirmed_candidate(tmp_path)
    repo = FailingFormalRepo()
    with pytest.raises(CandidateStoreError, match="adoption failed"):
        AdoptionService(store, formal_repository=repo).adopt(AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-1"))
    assert store.load(candidate.candidate_id).state.value == "VALIDATED_CANDIDATE"
    assert list((tmp_path / "receipts").glob("*.json")) == []
    assert repo.load("project-1").extra_fields == {}


class SecretLeakingTransport:
    name = "secret-test"
    def generate(self, request, *, config):
        raise ProviderError(ProviderFailureCode.PROVIDER_UNAVAILABLE, "oops UBD_AGENT_SECRET_SENTINEL_DO_NOT_STORE")


def test_provider_transport_exception_is_secret_free():
    with pytest.raises(ProviderError) as caught:
        QwenProvider(config=QwenConfig(model="test-model"), transport=SecretLeakingTransport()).generate(request())
    assert "UBD_AGENT_SECRET_SENTINEL_DO_NOT_STORE" not in str(caught.value)
    assert caught.value.code == "provider_unavailable"
