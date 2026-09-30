from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.agent_candidate_store import AdoptionService, CandidateStore, CandidateStoreError
from services.agent_contracts import AdoptionRequest, candidate_digest
from tests.test_agent_backend_integration_r2 import JournalFailureStore, ReceiptWriteThenFailStore, Repo, _confirmed


class RecoveryMarkerFailureStore(ReceiptWriteThenFailStore):
    def write_recovery_marker(self, transaction_id: str, payload):
        raise OSError("recovery marker persistence fault")


def _receipt_path(tmp_path: Path, receipt_id: str) -> Path:
    return tmp_path / "receipts" / f"{receipt_id}.json"


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "attacker-provider"),
        ("artifact_identities", {"record": {"identity": "attacker-artifact"}}),
        ("candidate_id", "other-candidate"),
        ("project_id", "other-project"),
        ("candidate_digest", "0" * 64),
        ("candidate_revision", 999),
        ("receipt_id", "receipt-attacker"),
        ("adoption_status", "FAILED"),
    ],
)
def test_complete_receipt_payload_tampering_is_not_authoritative(tmp_path: Path, field: str, value) -> None:
    store, candidate = _confirmed(tmp_path)
    receipt = AdoptionService(store, formal_repository=Repo()).adopt(
        AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
    )
    path = _receipt_path(tmp_path, receipt.receipt_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not store.receipt_is_authoritative(receipt.receipt_id)
    with pytest.raises(CandidateStoreError, match="not authoritative"):
        store.load_receipt(receipt.receipt_id)


def test_receipt_authentication_cannot_be_copied_between_candidates(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_store, first_candidate = _confirmed(first_root)
    first_receipt = AdoptionService(first_store, formal_repository=Repo()).adopt(
        AdoptionRequest(first_candidate.candidate_id, "project-1", candidate_digest(first_candidate), "confirm-r2")
    )
    second_store, second_candidate = _confirmed(second_root)
    second_receipt = AdoptionService(second_store, formal_repository=Repo()).adopt(
        AdoptionRequest(second_candidate.candidate_id, "project-1", candidate_digest(second_candidate), "confirm-r2")
    )
    copied = json.loads(_receipt_path(first_root, first_receipt.receipt_id).read_text(encoding="utf-8"))
    target = _receipt_path(second_root, second_receipt.receipt_id)
    target.write_text(json.dumps(copied), encoding="utf-8")
    assert not second_store.receipt_is_authoritative(second_receipt.receipt_id)


def test_unsigned_receipt_and_plain_sha_recomputation_are_rejected(tmp_path: Path) -> None:
    store, candidate = _confirmed(tmp_path)
    receipt = AdoptionService(store, formal_repository=Repo()).adopt(
        AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
    )
    path = _receipt_path(tmp_path, receipt.receipt_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("integrity", None)
    payload["provider"] = "attacker-provider"
    payload["candidate_digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert not store.receipt_is_authoritative(receipt.receipt_id)
    with pytest.raises(CandidateStoreError):
        store.load_receipt(receipt.receipt_id)


def test_primary_journal_failure_leaves_durable_recovery_after_reopen(tmp_path: Path) -> None:
    _, candidate = _confirmed(tmp_path)
    failing = JournalFailureStore(tmp_path, fail_on_call=2)
    with pytest.raises(CandidateStoreError, match="recovery required"):
        AdoptionService(failing, formal_repository=Repo()).adopt(
            AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
        )
    markers = list((tmp_path / "recovery").glob("*.json"))
    assert markers

    reopened = CandidateStore(tmp_path)
    assert reopened.adoption_requires_recovery(candidate.candidate_id, "project-1")
    assert not any(reopened.receipt_is_authoritative(path.stem) for path in (tmp_path / "receipts").glob("*.json"))
    with pytest.raises(CandidateStoreError, match="recovery required"):
        AdoptionService(reopened, formal_repository=Repo()).adopt(
            AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
        )


def test_recovery_marker_failure_still_preserves_recovery_journal(tmp_path: Path) -> None:
    _, candidate = _confirmed(tmp_path)
    store = RecoveryMarkerFailureStore(tmp_path)
    # Receipt acknowledgement failure creates rollback uncertainty.  The
    # independent marker is unavailable, so the signed primary journal must
    # still carry RECOVERY_REQUIRED.
    with pytest.raises(CandidateStoreError, match="recovery required"):
        AdoptionService(store, formal_repository=Repo()).adopt(
            AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
        )
    assert store.list_journal()[-1]["status"] == "RECOVERY_REQUIRED"


def test_in_progress_journal_with_adopted_candidate_fails_closed_after_reopen(tmp_path: Path) -> None:
    store, candidate = _confirmed(tmp_path)
    receipt = AdoptionService(store, formal_repository=Repo()).adopt(
        AdoptionRequest(candidate.candidate_id, "project-1", candidate_digest(candidate), "confirm-r2")
    )
    journal_path = next((tmp_path / "journal").glob("*.json"))
    transaction_id = journal_path.stem
    store.write_journal(
        transaction_id,
        {
            "status": "IN_PROGRESS",
            "candidate_id": candidate.candidate_id,
            "project_id": "project-1",
            "receipt_id": receipt.receipt_id,
        },
    )
    reopened = CandidateStore(tmp_path)
    assert not reopened.receipt_is_authoritative(receipt.receipt_id)
    assert reopened.adoption_requires_recovery(candidate.candidate_id, "project-1")
