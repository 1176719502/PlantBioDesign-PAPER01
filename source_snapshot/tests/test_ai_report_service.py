from __future__ import annotations

import copy
import hashlib
import json

import pytest

from services.ai_provider import DisabledAIReportProvider, ProviderResponse
from services.ai_report_service import (
    STATUS_AI_ASSISTED_DRAFT,
    STATUS_REJECTED,
    STATUS_UNAVAILABLE,
    approved_fact_refs,
    build_ai_report_draft,
    build_provider_report_projection,
)
from services.formal_report_snapshot import build_formal_report_snapshot


HASH_A = "0123456789abcdef" * 4
HASH_B = "fedcba9876543210" * 4


class FakeProvider:
    def __init__(self, content):
        self.content = content
        self.request_payload = None
        self.calls = 0

    def generate_report_draft(self, request_payload):
        self.calls += 1
        self.request_payload = request_payload
        content = copy.deepcopy(self.content)
        if isinstance(content, dict) and "provider_request_id" not in content:
            content["provider_request_id"] = request_payload["projection"]["provider_request_id"]
        return ProviderResponse(content=content, metadata={"provider": "fake", "model": "test-model"})


class FailingProvider:
    def generate_report_draft(self, request_payload):
        del request_payload
        raise TimeoutError("test timeout")


def _snapshot(*, blocking_count: int = 0, warning_count: int = 1) -> dict:
    return build_formal_report_snapshot(
        workflow_type="single_gene",
        freshness={"state": "current"},
        project={"project_id": "case-1", "name": "Review case"},
        design_goal={"summary": "Document the design for review."},
        component_summary={
            "components": [
                {
                    "order": 1,
                    "component_id": "marker-a",
                    "name": "Marker A",
                    "role": "marker",
                    "accession": "AB123456.1",
                    "source": "registry",
                    "length_bp": 11,
                }
            ]
        },
        construct_summary={"canonical_construct_present": True, "canonical_length_bp": 100, "canonical_hash": HASH_A, "topology": "circular"},
        feature_summary={"features": [{"name": "Marker A", "start": 10, "end": 20}]},
        validation_summary={"blocking_count": blocking_count, "warning_count": warning_count},
        provenance_summary={"source_count": 2},
        delivery_artifacts=[{"artifact_id": "fasta", "sha256": HASH_B, "size_bytes": 22, "available": True}],
        route_specific_data={"route": "single_gene"},
    )


def _item(code: str, *tokens: str, display_order: int | None = None) -> dict:
    item = {"interpretation_code": code, "semantic_fact_tokens": list(tokens)}
    if display_order is not None:
        item["display_order"] = display_order
    return item


def _with_recomputed_snapshot_id(snapshot: dict) -> dict:
    """Model an attacker who changes a snapshot and recomputes its content hash."""
    resigned = copy.deepcopy(snapshot)
    payload = {key: value for key, value in resigned.items() if key != "snapshot_id"}
    resigned["snapshot_id"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return resigned


def _valid_draft(snapshot: dict) -> dict:
    return {
        "schema_version": "ai-final-report-v1",
        "snapshot_id": snapshot["snapshot_id"],
        "status": STATUS_AI_ASSISTED_DRAFT,
        "executive_summary": [_item("NO_BLOCKERS_REPORTED", "VAL_BLOCKING_COUNT")],
        "design_interpretation": [_item("CANONICAL_CONSTRUCT_PRESENT", "CANONICAL_PRESENT")],
        "validation_interpretation": [_item("WARNINGS_REQUIRE_REVIEW", "VAL_WARNING_COUNT")],
        "manual_review_points": [_item("MANUAL_REVIEW_REQUIRED", "MANUAL_REVIEW_FLAG")],
        "limitations": [_item("DOCUMENTATION_ONLY", "DOC_ONLY_FLAG")],
        "delivery_summary": [_item("DELIVERY_ARTIFACTS_AVAILABLE", "DELIVERY_AVAILABLE")],
    }


def test_valid_fake_provider_draft_is_evidence_bound_and_rendered_from_snapshot() -> None:
    snapshot = _snapshot()
    provider = FakeProvider(_valid_draft(snapshot))

    report = build_ai_report_draft(snapshot, provider=provider)

    assert report["status"] == STATUS_AI_ASSISTED_DRAFT
    assert report["snapshot_id"] == snapshot["snapshot_id"]
    assert report["executive_summary"] == [_item("NO_BLOCKERS_REPORTED", "VAL_BLOCKING_COUNT")]
    assert report["rendered_sections"]["executive_summary"] == [
        "No blockers are recorded in the referenced validation facts. Referenced facts: VAL_BLOCKING_COUNT: 0."
    ]
    assert set(provider.request_payload) == {"projection"}
    assert "provider_request_id" in provider.request_payload["projection"]
    assert set(fact["token"] for fact in provider.request_payload["projection"]["facts"]) == approved_fact_refs(snapshot)


def test_provider_receives_only_the_typed_projection_without_local_snapshot_values() -> None:
    snapshot = _snapshot()
    provider = FakeProvider(_valid_draft(snapshot))

    build_ai_report_draft(snapshot, provider=provider)

    payload = provider.request_payload
    encoded_payload = json.dumps(payload, sort_keys=True)
    assert "snapshot" not in payload
    assert "canonical_hash" not in encoded_payload
    assert "route_specific_data" not in encoded_payload
    assert "Marker A" not in encoded_payload
    assert "AB123456.1" not in encoded_payload
    assert HASH_A not in encoded_payload
    assert HASH_B not in encoded_payload
    assert payload["projection"]["canonical_construct_present"] is True
    assert all(set(fact) == {"token", "kind", "value"} for fact in payload["projection"]["facts"])


def test_nucleotide_looking_sha256_stays_local_and_never_enters_provider_projection() -> None:
    nucleotide_looking_hash = "AC" * 32
    snapshot = build_formal_report_snapshot(
        workflow_type="single_gene",
        freshness={"state": "current"},
        construct_summary={"canonical_construct_present": True, "canonical_hash": nucleotide_looking_hash},
        validation_summary={"blocking_count": 0, "warning_count": 0},
        boundary={"documentation_only": True, "manual_review_required": True},
    )

    projection = build_provider_report_projection(snapshot)

    assert snapshot["construct_summary"]["canonical_hash"] == nucleotide_looking_hash
    assert nucleotide_looking_hash not in json.dumps(projection)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "ATGCGTAT GCATGCAT",
        "ATGCGTAT\nGCATGCAT",
        "5'-ATGCGTATGCGT-3'",
        "5\u2032-ATGCGTATGCGT 3\u2032",
        "a t g c g t a t",
    ],
)
def test_formatted_sequence_smuggling_rejects_before_provider_call(unsafe_value: str) -> None:
    snapshot = _snapshot()
    unsafe_snapshot = copy.deepcopy(snapshot)
    unsafe_snapshot["route_specific_data"] = {"nested": [{"sequence_like": unsafe_value}]}
    provider = FakeProvider(_valid_draft(snapshot))

    report = build_ai_report_draft(unsafe_snapshot, provider=provider)

    assert report["status"] == STATUS_REJECTED
    assert provider.calls == 0


def test_interpretation_codes_require_the_exact_semantic_fact_and_local_predicate() -> None:
    snapshot = _snapshot()
    wrong_domain = _valid_draft(snapshot)
    wrong_domain["executive_summary"] = [_item("NO_BLOCKERS_REPORTED", "VAL_WARNING_COUNT")]
    blockers_snapshot = _snapshot(blocking_count=1)
    blockers_mismatch = _valid_draft(blockers_snapshot)
    warnings_snapshot = _snapshot(warning_count=0)
    warnings_mismatch = _valid_draft(warnings_snapshot)

    wrong_domain_report = build_ai_report_draft(snapshot, provider=FakeProvider(wrong_domain))
    blockers_report = build_ai_report_draft(blockers_snapshot, provider=FakeProvider(blockers_mismatch))
    warnings_report = build_ai_report_draft(warnings_snapshot, provider=FakeProvider(warnings_mismatch))

    assert wrong_domain_report["status"] == STATUS_REJECTED
    assert blockers_report["status"] == STATUS_REJECTED
    assert warnings_report["status"] == STATUS_REJECTED


def test_disabled_and_timeout_provider_fallbacks_do_not_block_deterministic_delivery() -> None:
    snapshot = _snapshot()
    deterministic = {"markdown": "unchanged deterministic record"}
    before = copy.deepcopy(deterministic)

    disabled = build_ai_report_draft(snapshot, provider=DisabledAIReportProvider(), deterministic_report=deterministic)
    timed_out = build_ai_report_draft(snapshot, provider=FailingProvider(), deterministic_report=deterministic)

    assert disabled["status"] == STATUS_UNAVAILABLE
    assert disabled["provider_metadata"]["reason"] == "provider_disabled"
    assert timed_out["status"] == STATUS_UNAVAILABLE
    assert all(not timed_out[field] for field in ("executive_summary", "design_interpretation", "validation_interpretation"))
    assert deterministic == before


def test_malformed_json_snapshot_mismatch_and_unknown_fact_refs_are_rejected() -> None:
    snapshot = _snapshot()
    malformed = build_ai_report_draft(snapshot, provider=FakeProvider("not json"))
    mismatch_payload = _valid_draft(snapshot)
    mismatch_payload["snapshot_id"] = "0" * 64
    mismatch = build_ai_report_draft(snapshot, provider=FakeProvider(mismatch_payload))
    unknown_payload = _valid_draft(snapshot)
    unknown_payload["executive_summary"] = [_item("NO_BLOCKERS_REPORTED", "UNKNOWN_TOKEN")]
    unknown = build_ai_report_draft(snapshot, provider=FakeProvider(unknown_payload))

    assert malformed["status"] == STATUS_REJECTED
    assert mismatch["status"] == STATUS_REJECTED
    assert unknown["status"] == STATUS_REJECTED


def test_fabricated_component_validation_and_ai_fact_values_are_rejected() -> None:
    snapshot = _snapshot()
    fabricated_component = _valid_draft(snapshot)
    fabricated_component["design_interpretation"][0]["component_name"] = "NewMarker"
    fabricated_validation = _valid_draft(snapshot)
    fabricated_validation["validation_interpretation"][0]["validation_passed"] = True
    altered_hash = _valid_draft(snapshot)
    altered_hash["design_interpretation"][0]["canonical_hash"] = HASH_B

    assert build_ai_report_draft(snapshot, provider=FakeProvider(fabricated_component))["status"] == STATUS_REJECTED
    assert build_ai_report_draft(snapshot, provider=FakeProvider(fabricated_validation))["status"] == STATUS_REJECTED
    assert build_ai_report_draft(snapshot, provider=FakeProvider(altered_hash))["status"] == STATUS_REJECTED


@pytest.mark.parametrize(
    "claim",
    [
        "Expected high expression.",
        "High expression is expected.",
        "Likely to express strongly.",
        "Expected increased yield.",
        "Likely successful in wet-lab experiments.",
        "Ready for wet lab.",
        "Production ready.",
        "Optimized for expression.",
        "Recommended for experimental use.",
    ],
)
def test_free_text_and_prohibited_biological_claims_cannot_enter_accepted_drafts(claim: str) -> None:
    snapshot = _snapshot()
    unsafe = _valid_draft(snapshot)
    unsafe["executive_summary"][0]["commentary"] = claim

    report = build_ai_report_draft(snapshot, provider=FakeProvider(unsafe))

    assert report["status"] == STATUS_REJECTED


def test_lowercase_accession_and_split_coordinate_cannot_be_supplied_by_ai() -> None:
    snapshot = _snapshot()
    accession = _valid_draft(snapshot)
    accession["design_interpretation"][0]["accession"] = "ab123456.1"
    coordinate = _valid_draft(snapshot)
    coordinate["design_interpretation"][0]["coordinate"] = "start 12, end 99"

    assert build_ai_report_draft(snapshot, provider=FakeProvider(accession))["status"] == STATUS_REJECTED
    assert build_ai_report_draft(snapshot, provider=FakeProvider(coordinate))["status"] == STATUS_REJECTED


def test_invalid_snapshot_is_rejected_before_the_provider_is_called() -> None:
    snapshot = _snapshot()
    unsafe_snapshot = copy.deepcopy(snapshot)
    unsafe_snapshot["construct_summary"]["canonical_hash"] = "ATGCGTATGCGTATGCGT"
    provider = FakeProvider(_valid_draft(snapshot))

    report = build_ai_report_draft(unsafe_snapshot, provider=provider)

    assert report["status"] == STATUS_REJECTED
    assert report["provider_metadata"]["reason"] == "snapshot_sanitization_failed"
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("freshness",), "current"),
        (("freshness",), []),
        (("validation_summary",), "ok"),
        (("validation_summary",), []),
        (("construct_summary",), None),
        (("route_specific_data",), "text"),
        (("delivery_artifacts",), "FASTA"),
        (("delivery_artifacts",), {"available": True}),
        (("component_summary", "components"), "not-a-list"),
        (("component_summary", "components"), {"source": "registry"}),
        (("component_summary", "components"), {"accession": "ABC"}),
        (("component_summary", "components"), 1),
        (("component_summary", "components"), None),
        (("component_summary", "components"), [123]),
        (("component_summary", "components"), ["source"]),
        (("component_summary", "components"), [{"source": "registry"}]),
    ],
)
def test_recomputed_id_malformed_snapshot_matrix_fails_closed_before_provider(path: tuple[str, ...], value: object) -> None:
    malformed = _snapshot()
    target = malformed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    malformed = _with_recomputed_snapshot_id(malformed)
    provider = FakeProvider(_valid_draft(_snapshot()))

    report = build_ai_report_draft(malformed, provider=provider, deterministic_report={"final_review": "preserved"})

    assert report["status"] == STATUS_REJECTED
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("freshness",), "current"),
        (("validation_summary",), "ok"),
        (("construct_summary",), None),
        (("component_summary",), []),
        (("component_summary", "components"), {"source": "registry"}),
        (("component_summary", "components"), [123]),
        (("route_specific_data",), "text"),
        (("delivery_artifacts",), "FASTA"),
    ],
)
def test_stale_id_malformed_snapshot_matrix_fails_closed_before_provider(path: tuple[str, ...], value: object) -> None:
    malformed = _snapshot()
    target = malformed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    provider = FakeProvider(_valid_draft(_snapshot()))

    report = build_ai_report_draft(malformed, provider=provider, deterministic_report={"final_review": "preserved"})

    assert report["status"] == STATUS_REJECTED
    assert report["provider_metadata"]["reason"] == "snapshot_sanitization_failed"
    assert provider.calls == 0


def test_source_and_accession_names_cannot_create_provider_semantics() -> None:
    snapshot = _snapshot()
    snapshot["component_summary"]["not_a_component"] = {"source": "registry"}
    snapshot["component_summary"]["metadata"] = {"accession": "ABC"}
    snapshot["route_specific_data"] = {"source": "registry"}
    snapshot = _with_recomputed_snapshot_id(snapshot)
    provider = FakeProvider(_valid_draft(snapshot))

    report = build_ai_report_draft(snapshot, provider=provider)

    assert report["status"] == STATUS_AI_ASSISTED_DRAFT
    assert provider.calls == 1
    tokens = {fact["token"] for fact in provider.request_payload["projection"]["facts"]}
    assert "COMPONENT_RECORD_FLAG" not in tokens
    assert "COMPONENT_RECORD_PRESENT" not in provider.request_payload["projection"]["allowed_interpretation_codes"]


def test_provider_payload_contains_no_internal_snapshot_paths_or_provenance_names() -> None:
    provider = FakeProvider(_valid_draft(_snapshot()))
    build_ai_report_draft(_snapshot(), provider=provider)
    encoded = json.dumps(provider.request_payload, sort_keys=True).lower()

    for forbidden in ("accession", "source", "provenance", "canonical_hash", "component_summary", "validation_summary", "route_specific_data", "sequence", "fasta", "genbank", "primer"):
        assert forbidden not in encoded


def test_request_and_snapshot_identity_mismatches_are_rejected_independently() -> None:
    snapshot = _snapshot()
    wrong_request = _valid_draft(snapshot)
    wrong_request["provider_request_id"] = "wrong-request"
    wrong_snapshot = _valid_draft(snapshot)
    wrong_snapshot["snapshot_id"] = "0" * 64

    assert build_ai_report_draft(snapshot, provider=FakeProvider(wrong_request))["status"] == STATUS_REJECTED
    assert build_ai_report_draft(snapshot, provider=FakeProvider(wrong_snapshot))["status"] == STATUS_REJECTED
