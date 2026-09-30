from __future__ import annotations

import gzip
import json

import httpx
import pytest

from services.agent_contracts import AgentRequest, ComponentReference, ComponentTier, safe_fingerprint
from services.agent_provider import (
    OpenAICompatibleQwenTransport,
    ProviderError,
    ProviderFailureCode,
    QWEN_RESPONSE_JSON_SCHEMA,
    QwenConfig,
    QwenProvider,
    RetryPolicy,
    StructuredOutputMode,
    _SafeTransportFailure,
    _openai_request_body,
    _provider_request,
)


def _request(*, with_component: bool = False) -> AgentRequest:
    components = ()
    evidence = ()
    if with_component:
        components = (
            ComponentReference(
                "component-1",
                role="promoter",
                tier=ComponentTier.DIRECT_USE,
                sequence_reference="sequence-1",
                evidence_references=("evidence-1",),
                provenance_references=("provenance-1",),
            ),
        )
        evidence = ("evidence-1",)
    return AgentRequest(
        request_id="req-qwen-compat-r1",
        workflow_type="single_gene",
        host="Arabidopsis",
        user_intent="prepare a design-record candidate",
        cds_or_reference_input="ATG",
        component_references=components,
        evidence_references=evidence,
        context={"project_id": "project-1"},
    )


def _valid_response(*, with_component: bool = False) -> dict:
    request = _request(with_component=with_component)
    return {
        "schema_version": "qwen-agent-response-v1",
        "status": "CANDIDATES",
        "interpretation": "A documentation-only candidate is requested.",
        "missing_inputs": [],
        "candidates": [
            {
                "candidate_id": "candidate-qwen-compat-r1",
                "evidence_references": list(request.evidence_references),
                "unresolved_requirements": [],
                "rationale": "Records the supplied facts for deterministic review.",
            }
        ],
        "alternatives": [],
        "explanation": "The provider remains advisory only.",
        "explanation_metadata": {"confidence": 0.5, "basis": ["user_supplied_facts"]},
    }


def _openai_envelope(content: dict, *, model: str = "test-model", response_id="response-1") -> bytes:
    return json.dumps(
        {
            "id": response_id,
            "model": model,
            "choices": [{"message": {"content": json.dumps(content, separators=(",", ":"))}}],
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _config(*, max_response_bytes: int = 1_000_000) -> QwenConfig:
    return QwenConfig(
        model="test-model",
        base_url="https://provider.example/v1",
        max_response_bytes=max_response_bytes,
        retry_policy=RetryPolicy(max_retries=0),
        structured_output_mode=StructuredOutputMode.JSON_OBJECT,
    )


def _post_response(body: bytes, headers: dict[str, str], *, max_response_bytes: int = 1_000_000):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers=headers, content=body))
    )
    transport = OpenAICompatibleQwenTransport(client=client)
    config = _config(max_response_bytes=max_response_bytes)
    response = transport._post_with_retries(
        client,
        _provider_request(_request(), config.model),
        config,
        "test-key",
        httpx.Timeout(5.0),
    )
    return transport, response


def _generate(
    payload: dict | str,
    *,
    with_component: bool = False,
    response_id: str | None = "response-1",
):
    from services.agent_provider import FakeQwenTransport

    return QwenProvider(
        config=QwenConfig(
            model="test-model",
            structured_output_mode=StructuredOutputMode.JSON_OBJECT,
        ),
        transport=FakeQwenTransport(payload, response_id=response_id),
    ).generate(_request(with_component=with_component))


def test_gzip_http_200_is_detached_after_decoding_without_encoded_headers() -> None:
    decoded = _openai_envelope(_valid_response())
    encoded = gzip.compress(decoded)
    transport, response = _post_response(
        encoded,
        {
            "Content-Encoding": "gzip",
            "Content-Length": str(len(encoded)),
            "Transfer-Encoding": "chunked",
            "Content-Type": "application/json",
            "X-Request-Id": "request-correlation-1",
        },
    )

    assert isinstance(response, httpx.Response)
    assert response.content == decoded
    assert "content-encoding" not in response.headers
    assert "transfer-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(decoded))
    assert response.headers["content-length"] != str(len(encoded))
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-request-id"] == "request-correlation-1"
    assert transport._adapt_response(response, _config()).content == json.dumps(
        _valid_response(), separators=(",", ":")
    )


def test_stale_encoded_headers_cannot_trigger_second_decoding() -> None:
    decoded = _openai_envelope(_valid_response())
    _, response = _post_response(
        gzip.compress(decoded),
        {"content-encoding": "gzip", "content-length": "1", "transfer-encoding": "chunked"},
    )

    assert isinstance(response, httpx.Response)
    assert response.json()["id"] == "response-1"
    assert not {"content-encoding", "transfer-encoding"} & set(response.headers)
    assert response.headers["content-length"] == str(len(decoded))


def test_decoded_response_size_limit_remains_enforced() -> None:
    decoded = b'{"padding":"' + (b"A" * 4_096) + b'"}'
    encoded = gzip.compress(decoded)
    assert len(encoded) < 256 < len(decoded)

    _, response = _post_response(
        encoded,
        {"content-encoding": "gzip", "content-length": str(len(encoded))},
        max_response_bytes=256,
    )

    assert isinstance(response, _SafeTransportFailure)
    assert response.code == ProviderFailureCode.OVERSIZED_RESPONSE


def test_unencoded_http_200_content_and_safe_headers_are_unchanged() -> None:
    body = _openai_envelope(_valid_response())
    _, response = _post_response(
        body,
        {"content-type": "application/json", "x-request-id": "request-correlation-2"},
    )

    assert isinstance(response, httpx.Response)
    assert response.content == body
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-request-id"] == "request-correlation-2"


def test_response_id_fingerprint_comes_from_real_transport_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_response_id = "provider-sensitive-response-id"
    payload = _valid_response()
    body = _openai_envelope(payload, response_id=raw_response_id)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    result = QwenProvider(
        config=_config(), transport=OpenAICompatibleQwenTransport(client=client)
    ).generate(_request())

    assert result.metadata.response_id == safe_fingerprint(raw_response_id)
    assert result.metadata.response_id != raw_response_id


def test_json_object_request_includes_authoritative_ubd_contract_instruction() -> None:
    request = _provider_request(_request(with_component=True), "test-model")
    body = _openai_request_body(request, _config())
    instruction = body["messages"][0]["content"]
    serialized_schema = json.dumps(
        QWEN_RESPONSE_JSON_SCHEMA, sort_keys=True, separators=(",", ":"), allow_nan=False
    )

    assert body["response_format"] == {"type": "json_object"}
    assert serialized_schema in instruction
    assert "metadata" not in QWEN_RESPONSE_JSON_SCHEMA["required"]
    assert "metadata" not in QWEN_RESPONSE_JSON_SCHEMA["properties"]
    assert "metadata.provider" not in instruction
    assert "metadata.model" not in instruction
    candidate_schema = QWEN_RESPONSE_JSON_SCHEMA["properties"]["candidates"]["items"]
    request_authoritative_fields = {
        "workflow_type",
        "host",
        "user_intent",
        "cds_or_reference_input",
        "component_references",
    }
    assert request_authoritative_fields.isdisjoint(candidate_schema["required"])
    assert request_authoritative_fields.isdisjoint(candidate_schema["properties"])
    for phrase in (
        "JSON object only",
        "no Markdown or code fences",
        "no extra top-level fields",
        "advisory_only",
        "intentionally absent from the response schema",
        "Do not regenerate or add those fields",
        "Fill only model-authorized response fields",
        "only select a subset",
        "Deterministic UBD validation remains authoritative",
    ):
        assert phrase in instruction


def test_production_default_uses_json_object_without_changing_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_QWEN_MODEL", raising=False)
    monkeypatch.delenv("AGENT_QWEN_STRUCTURED_OUTPUT_MODE", raising=False)

    assert QwenConfig().structured_output_mode is StructuredOutputMode.JSON_OBJECT
    assert QwenConfig.from_env().structured_output_mode is StructuredOutputMode.JSON_OBJECT
    assert QwenConfig.from_env().model == "qwen-plus"


def test_conforming_json_object_response_parses_successfully() -> None:
    result = _generate(_valid_response())

    assert result.status.value == "CANDIDATES"
    assert result.metadata.provider == "qwen"
    assert result.metadata.model == "test-model"
    assert result.metadata.request_id == _request().request_id
    assert result.metadata.schema_version == "qwen-agent-response-v1"
    assert result.metadata.transport == "fake"
    assert result.metadata.response_id == safe_fingerprint("response-1")
    assert result.metadata.structured_output_validation == "PASS"


def test_request_authoritative_facts_are_materialized_without_model_echo() -> None:
    request = _request(with_component=True)
    result = _generate(_valid_response(with_component=True), with_component=True)
    candidate = result.candidates[0]

    assert candidate.workflow_type == request.workflow_type
    assert candidate.host == request.host
    assert candidate.user_intent == request.user_intent
    assert candidate.cds_or_reference_input == request.cds_or_reference_input
    assert candidate.component_references == request.component_references


def test_model_advisory_evidence_subset_remains_strict_and_is_preserved() -> None:
    payload = _valid_response(with_component=True)
    payload["candidates"][0]["evidence_references"] = []

    result = _generate(payload, with_component=True)

    assert result.candidates[0].evidence_references == ()


@pytest.mark.parametrize(
    "legacy_metadata",
    [
        {"provider": "spoofed-provider", "model": "test-model", "response_id": "response-1"},
        {"provider": "qwen", "model": "spoofed-model", "response_id": "response-1"},
        {"provider": "qwen", "model": "test-model", "response_id": "spoofed-response-id"},
    ],
)
def test_legacy_model_metadata_cannot_spoof_transport_authority(legacy_metadata: dict) -> None:
    payload = _valid_response()
    payload["metadata"] = legacy_metadata

    result = _generate(
        payload,
        response_id="trusted-transport-response-id",
    )

    assert result.metadata.provider == "qwen"
    assert result.metadata.model == "test-model"
    assert result.metadata.response_id == safe_fingerprint("trusted-transport-response-id")


def test_legacy_metadata_extra_fields_remain_schema_invalid() -> None:
    payload = _valid_response()
    payload["metadata"] = {
        "provider": "qwen",
        "model": "test-model",
        "response_id": "response-1",
        "authority": "spoofed",
    }

    with pytest.raises(ProviderError) as caught:
        _generate(payload)

    assert caught.value.code == ProviderFailureCode.SCHEMA_MISMATCH.value


def test_missing_transport_response_identity_remains_supported() -> None:
    result = _generate(_valid_response(), response_id=None)

    assert result.metadata.response_id is None


@pytest.mark.parametrize("response_id", [123, {"id": "response-1"}])
def test_malformed_transport_response_identity_fails_safely(response_id) -> None:
    from services.agent_provider import FakeQwenTransport

    provider = QwenProvider(
        config=QwenConfig(model="test-model", structured_output_mode=StructuredOutputMode.JSON_OBJECT),
        transport=FakeQwenTransport(_valid_response(), response_id=response_id),
    )

    with pytest.raises(ProviderError) as caught:
        provider.generate(_request())

    assert caught.value.code == ProviderFailureCode.PROVIDER_UNAVAILABLE.value


def test_http_envelope_model_mismatch_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _openai_envelope(_valid_response(), model="spoofed-model")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    with pytest.raises(ProviderError) as caught:
        QwenProvider(config=_config(), transport=OpenAICompatibleQwenTransport(client=client)).generate(_request())

    assert caught.value.code == ProviderFailureCode.PROVIDER_METADATA_MISSING.value


def test_missing_http_envelope_model_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = json.loads(_openai_envelope(_valid_response()))
    envelope.pop("model")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(envelope).encode()))
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    with pytest.raises(ProviderError) as caught:
        QwenProvider(config=_config(), transport=OpenAICompatibleQwenTransport(client=client)).generate(_request())

    assert caught.value.code == ProviderFailureCode.PROVIDER_METADATA_MISSING.value


def test_missing_http_response_identity_preserves_existing_optional_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = json.loads(_openai_envelope(_valid_response()))
    envelope.pop("id")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(envelope).encode()))
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    result = QwenProvider(
        config=_config(), transport=OpenAICompatibleQwenTransport(client=client)
    ).generate(_request())

    assert result.metadata.response_id is None


@pytest.mark.parametrize("response_id", [123, {"id": "response-1"}])
def test_malformed_http_response_identity_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
    response_id,
) -> None:
    body = _openai_envelope(_valid_response(), response_id=response_id)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    with pytest.raises(ProviderError) as caught:
        QwenProvider(config=_config(), transport=OpenAICompatibleQwenTransport(client=client)).generate(_request())

    assert caught.value.code == ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE.value


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda payload: payload.pop("interpretation"), ProviderFailureCode.SCHEMA_MISMATCH),
        (lambda payload: payload.__setitem__("design_record", {}), ProviderFailureCode.SCHEMA_MISMATCH),
        (lambda payload: payload["candidates"][0].__setitem__("component_references", {}), ProviderFailureCode.SCHEMA_MISMATCH),
    ],
)
def test_invalid_json_object_shapes_fail_closed(mutation, expected_code) -> None:
    payload = _valid_response()
    mutation(payload)

    with pytest.raises(ProviderError) as caught:
        _generate(payload)

    assert caught.value.code == expected_code.value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "Nicotiana benthamiana"),
        ("user_intent", "rewritten intent"),
        ("cds_or_reference_input", "ATGAAA"),
        ("workflow_type", "multi_tu"),
    ],
)
def test_model_cannot_add_or_override_request_authoritative_fact(field: str, value) -> None:
    payload = _valid_response()
    payload["candidates"][0][field] = value

    with pytest.raises(ProviderError) as caught:
        _generate(payload)

    assert caught.value.code == ProviderFailureCode.SCHEMA_MISMATCH.value


@pytest.mark.parametrize("mutation", ["unauthorized_component", "invented_evidence"])
def test_component_and_evidence_invention_remains_fail_closed(mutation: str) -> None:
    payload = _valid_response(with_component=True)
    if mutation == "unauthorized_component":
        payload["candidates"][0]["component_references"] = [{"component_id": "invented-component"}]
    else:
        payload["candidates"][0]["evidence_references"].append("invented-evidence")

    with pytest.raises(ProviderError) as caught:
        _generate(payload, with_component=True)

    expected = (
        ProviderFailureCode.SCHEMA_MISMATCH
        if mutation == "unauthorized_component"
        else ProviderFailureCode.GOVERNANCE_VIOLATION
    )
    assert caught.value.code == expected.value


def test_prohibited_authority_claim_remains_fail_closed() -> None:
    payload = _valid_response()
    payload["status"] = "NEEDS_INPUT"
    payload["candidates"] = []
    payload["missing_inputs"] = [
        {
            "code": "MISSING_HOST",
            "field": "host",
            "message": "Host is required.",
            "blocking": True,
            "details": {"formal_adoption": True},
        }
    ]

    with pytest.raises(ProviderError) as caught:
        _generate(payload)

    assert caught.value.code == ProviderFailureCode.GOVERNANCE_VIOLATION.value


def test_malformed_json_remains_fail_closed() -> None:
    with pytest.raises(ProviderError) as caught:
        _generate('{"schema_version":')

    assert caught.value.code == ProviderFailureCode.MALFORMED_JSON.value
