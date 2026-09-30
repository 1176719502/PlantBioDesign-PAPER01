from __future__ import annotations

import copy
from pathlib import Path

import pytest

from services.agent_candidate_store import AdoptionService, CandidateStore, CandidateStoreError
from services.agent_contracts import AdoptionRequest, AgentRequest, CandidateState, candidate_digest
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider
from services.agent_service import AgentBackend
from services.plant_project_draft_repository import PlantProjectDraftRepository


PROJECT_ID = "formal-project-rollback"
CONFIRMATION_TOKEN = "formal-rollback-confirmation"


class ReceiptWriteThenFailStore(CandidateStore):
    def save_receipt(self, receipt):
        super().save_receipt(receipt)
        raise OSError("receipt persistence acknowledgement fault")


class FinalJournalFailOnceStore(CandidateStore):
    def __init__(self, storage_dir: str | Path) -> None:
        super().__init__(storage_dir)
        self.journal_calls = 0

    def write_journal(self, transaction_id: str, payload):
        self.journal_calls += 1
        if self.journal_calls == 2:
            super().write_journal(transaction_id, payload)
            raise OSError("final journal persistence fault")
        return super().write_journal(transaction_id, payload)


class CandidateUpdateFailStore(CandidateStore):
    def update(self, candidate, **fields):
        raise OSError("candidate state persistence fault")


class RestoreFailRepository(PlantProjectDraftRepository):
    def restore_exact(self, snapshot):
        raise OSError("exact Formal restore fault")


class NoopRestoreRepository(PlantProjectDraftRepository):
    def restore_exact(self, snapshot):
        return snapshot


def _provider() -> QwenProvider:
    return QwenProvider(
        config=QwenConfig(model="test-model"),
        transport=FakeQwenTransport(),
    )


def _request() -> AgentRequest:
    return AgentRequest(
        request_id="formal-rollback-request",
        workflow_type="single_gene",
        host="Arabidopsis",
        user_intent="prepare a reviewable candidate",
        cds_or_reference_input="ATG",
        context={"project_id": PROJECT_ID},
    )


def _confirmed_context(tmp_path: Path, extra_fields: dict | None = None):
    formal_dir = tmp_path / "formal-projects"
    agent_dir = tmp_path / "agent-state"
    repository = PlantProjectDraftRepository(formal_dir)
    draft = repository.create_blank(project_name="Formal rollback correction")
    draft.project_id = PROJECT_ID
    draft.extra_fields = copy.deepcopy(extra_fields or {})
    before = repository.save(draft).to_dict()

    store = CandidateStore(agent_dir)
    backend = AgentBackend(_provider(), candidate_store=store, project_repository=repository)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(
        candidate,
        confirmation_id=CONFIRMATION_TOKEN,
        preview=preview,
    )
    request = AdoptionRequest(
        confirmed.candidate_id,
        PROJECT_ID,
        candidate_digest(confirmed),
        CONFIRMATION_TOKEN,
    )
    return formal_dir, agent_dir, before, confirmed, request


def _assert_proven_rollback(
    formal_dir: Path,
    agent_dir: Path,
    before: dict,
    candidate_id: str,
) -> None:
    reopened_repository = PlantProjectDraftRepository(formal_dir)
    reopened_store = CandidateStore(agent_dir)
    assert reopened_repository.load(PROJECT_ID).to_dict() == before
    assert reopened_store.load(candidate_id).state is CandidateState.VALIDATED_CANDIDATE
    assert reopened_store.list_journal()[-1]["status"] == "FAILED_ROLLED_BACK"
    assert reopened_store.list_recovery_markers() == []
    assert not reopened_store.adoption_requires_recovery(candidate_id, PROJECT_ID)
    assert not list((agent_dir / "receipts").glob("*.json"))


def test_normal_save_keeps_merge_semantics_while_exact_restore_replaces_snapshot(
    tmp_path: Path,
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "formal-projects")
    draft = repository.create_blank(project_name="Repository semantics")
    draft.project_id = PROJECT_ID
    draft.extra_fields = {"existing": {"preserve": True}}
    snapshot = repository.save(draft).to_dict()

    update = repository.load(PROJECT_ID)
    update.extra_fields = {"introduced": {"remove": True}}
    repository.save(update)
    assert repository.load(PROJECT_ID).extra_fields == {
        "existing": {"preserve": True},
        "introduced": {"remove": True},
    }

    repository.restore_exact(snapshot)
    assert PlantProjectDraftRepository(repository.storage_dir).load(PROJECT_ID).to_dict() == snapshot


@pytest.mark.parametrize(
    ("extra_fields", "add_future_field"),
    [
        pytest.param({}, False, id="empty-extra-fields"),
        pytest.param(
            {"existing_a": {"nested": [1, 2]}, "existing_b": "preserved"},
            True,
            id="unrelated-extra-fields",
        ),
        pytest.param(
            {"agent_adoption": {"candidate_id": "original", "value": {"keep": True}}},
            False,
            id="pre-existing-agent-adoption",
        ),
    ],
)
def test_receipt_failure_exactly_restores_real_repository_snapshot_after_cold_reopen(
    tmp_path: Path,
    extra_fields: dict,
    add_future_field: bool,
) -> None:
    formal_dir, agent_dir, before, candidate, request = _confirmed_context(tmp_path, extra_fields)
    store = ReceiptWriteThenFailStore(agent_dir)
    repository = PlantProjectDraftRepository(formal_dir)

    def apply_adoption(draft, current_candidate):
        draft.extra_fields = dict(draft.extra_fields)
        draft.extra_fields["agent_adoption"] = {"candidate_id": current_candidate.candidate_id}
        if add_future_field:
            draft.extra_fields["agent_future_managed_field"] = {"introduced": True}
        return draft

    with pytest.raises(CandidateStoreError, match="was rolled back"):
        AdoptionService(
            store,
            formal_repository=repository,
            formal_applier=apply_adoption,
        ).adopt(request)

    _assert_proven_rollback(formal_dir, agent_dir, before, candidate.candidate_id)


@pytest.mark.parametrize(
    "store_type",
    [
        pytest.param(FinalJournalFailOnceStore, id="final-journal"),
        pytest.param(CandidateUpdateFailStore, id="candidate-state"),
    ],
)
def test_other_post_formal_failures_restore_exact_state_with_real_repository(
    tmp_path: Path,
    store_type,
) -> None:
    formal_dir, agent_dir, before, candidate, request = _confirmed_context(
        tmp_path,
        {"existing_a": "preserved", "existing_b": [1, 2, 3]},
    )

    with pytest.raises(CandidateStoreError, match="was rolled back"):
        AdoptionService(
            store_type(agent_dir),
            formal_repository=PlantProjectDraftRepository(formal_dir),
        ).adopt(request)

    _assert_proven_rollback(formal_dir, agent_dir, before, candidate.candidate_id)


@pytest.mark.parametrize(
    "repository_type",
    [
        pytest.param(RestoreFailRepository, id="restore-raises"),
        pytest.param(NoopRestoreRepository, id="restore-not-persisted"),
    ],
)
def test_unproven_exact_restore_remains_recovery_required_and_blocks_retry(
    tmp_path: Path,
    repository_type,
) -> None:
    formal_dir, agent_dir, before, candidate, request = _confirmed_context(tmp_path)
    store = ReceiptWriteThenFailStore(agent_dir)

    with pytest.raises(CandidateStoreError, match="recovery required"):
        AdoptionService(
            store,
            formal_repository=repository_type(formal_dir),
        ).adopt(request)

    reopened_repository = PlantProjectDraftRepository(formal_dir)
    reopened_store = CandidateStore(agent_dir)
    after = reopened_repository.load(PROJECT_ID).to_dict()
    assert after != before
    assert "agent_adoption" in after
    assert reopened_store.load(candidate.candidate_id).state is CandidateState.VALIDATED_CANDIDATE
    assert reopened_store.list_journal()[-1]["status"] == "RECOVERY_REQUIRED"
    assert len(reopened_store.list_recovery_markers()) == 1
    assert reopened_store.adoption_requires_recovery(candidate.candidate_id, PROJECT_ID)
    assert not list((agent_dir / "receipts").glob("*.json"))
    with pytest.raises(CandidateStoreError, match="recovery required"):
        AdoptionService(
            reopened_store,
            formal_repository=reopened_repository,
        ).adopt(request)


def test_successful_adoption_remains_committed_and_consistent_after_cold_reopen(
    tmp_path: Path,
) -> None:
    formal_dir, agent_dir, before, candidate, request = _confirmed_context(
        tmp_path,
        {"existing_a": "preserved", "existing_b": {"nested": True}},
    )
    receipt = AdoptionService(
        CandidateStore(agent_dir),
        formal_repository=PlantProjectDraftRepository(formal_dir),
    ).adopt(request)

    reopened_repository = PlantProjectDraftRepository(formal_dir)
    reopened_store = CandidateStore(agent_dir)
    after = reopened_repository.load(PROJECT_ID).to_dict()
    assert after != before
    assert after["existing_a"] == "preserved"
    assert after["existing_b"] == {"nested": True}
    assert after["agent_adoption"]["candidate_id"] == candidate.candidate_id
    assert reopened_store.load(candidate.candidate_id).state is CandidateState.USER_ADOPTED
    assert reopened_store.receipt_is_authoritative(receipt.receipt_id)
    assert reopened_store.list_journal()[-1]["status"] == "COMMITTED"
    assert reopened_store.list_recovery_markers() == []
