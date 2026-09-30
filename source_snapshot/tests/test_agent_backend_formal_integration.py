from __future__ import annotations

from collections import Counter

import pytest

from services.agent_candidate_store import CandidateStore, CandidateStoreError
from services.agent_contracts import AdoptionRequest, AgentRequest, candidate_digest
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider
from services.agent_service import AgentBackend
from services.component_library_v2_adoption import build_v2_canonical_inventory
from services.plant_project_draft_repository import PlantProjectDraftRepository


def _provider() -> QwenProvider:
    return QwenProvider(config=QwenConfig(model="test-model"), transport=FakeQwenTransport())


def _request() -> AgentRequest:
    return AgentRequest(
        request_id="formal-agent-request",
        workflow_type="single_gene",
        host="Arabidopsis",
        user_intent="prepare a reviewable candidate",
        cds_or_reference_input="ATG",
        context={"project_id": "formal-project-1"},
    )


def _formal_repository(tmp_path):
    repository = PlantProjectDraftRepository(tmp_path / "formal-projects")
    draft = repository.create_blank(project_name="Formal Agent Integration")
    draft.project_id = "formal-project-1"
    return repository, repository.save(draft)


def test_component_library_v2_freeze_counts_and_blocked_ids_are_preserved():
    rows = build_v2_canonical_inventory()
    assert len(rows) == 171
    assert Counter(row["library_tier"] for row in rows) == {
        "CORE": 41,
        "REFERENCE": 95,
        "RETIRED": 35,
    }
    assert Counter(row["admission_mode"] for row in rows) == {
        "DIRECT_USE": 17,
        "USER_SEQUENCE_ASSISTED": 24,
        "REFERENCE_ONLY": 130,
    }
    blocked = {row["canonical_v2_component_id"] for row in rows if row.get("canonical_v2_component_id") in {"V2-CMP-003", "V2-CMP-126"}}
    assert blocked == {"V2-CMP-003", "V2-CMP-126"}


def test_agent_backend_persists_validated_candidate_without_formal_mutation(tmp_path):
    repository, before = _formal_repository(tmp_path)
    store = CandidateStore(tmp_path / "agent-state")
    backend = AgentBackend(_provider(), candidate_store=store, project_repository=repository)

    result = backend.generate_and_validate(_request())

    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.state.value == "VALIDATED_CANDIDATE"
    assert store.load(candidate.candidate_id).state.value == "VALIDATED_CANDIDATE"
    reopened = PlantProjectDraftRepository(tmp_path / "formal-projects").load("formal-project-1")
    assert reopened.extra_fields == before.extra_fields == {}


def test_formal_adoption_requires_current_confirmation_and_writes_through_repository(tmp_path):
    repository, _ = _formal_repository(tmp_path)
    store = CandidateStore(tmp_path / "agent-state")
    backend = AgentBackend(_provider(), candidate_store=store, project_repository=repository)
    candidate = backend.generate_and_validate(_request()).candidates[0]

    with pytest.raises(CandidateStoreError):
        backend.adopt(AdoptionRequest(candidate.candidate_id, "formal-project-1", candidate_digest(candidate), "missing"))
    assert repository.load("formal-project-1").extra_fields == {}

    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(candidate, confirmation_id="formal-confirmation", preview=preview)
    with pytest.raises(CandidateStoreError):
        backend.adopt(AdoptionRequest(confirmed.candidate_id, "formal-project-1", candidate_digest(confirmed), "wrong"))
    assert repository.load("formal-project-1").extra_fields == {}

    receipt = backend.adopt(
        AdoptionRequest(
            confirmed.candidate_id,
            "formal-project-1",
            candidate_digest(confirmed),
            "formal-confirmation",
        )
    )
    reopened_store = CandidateStore(tmp_path / "agent-state")
    reopened_repository = PlantProjectDraftRepository(tmp_path / "formal-projects")
    assert reopened_store.receipt_is_authoritative(receipt.receipt_id)
    assert reopened_store.load(candidate.candidate_id).state.value == "USER_ADOPTED"
    assert reopened_repository.load("formal-project-1").extra_fields["agent_adoption"]["candidate_id"] == candidate.candidate_id
