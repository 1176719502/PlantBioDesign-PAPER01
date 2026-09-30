# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib

from services import evidence_query_builder as builder
from services import evidence_retrieval_provider as provider_module


def _query_bundle() -> dict[str, object]:
    return builder.build_evidence_query_bundle(
        {
            "target gene/product": "rice albumin",
            "host/chassis": "Nicotiana benthamiana",
        }
    )


def test_fake_provider_returns_deterministic_matching_records() -> None:
    provider = provider_module.FakeEvidenceRetrievalProvider(
        [
            {
                "record_id": "R2",
                "title": "Nicotiana host context note",
                "keywords": ["host"],
                "design_slots": ["host_chassis"],
            },
            {
                "record_id": "R1",
                "title": "Rice albumin source note",
                "abstract": "Evidence metadata mentions rice albumin.",
            },
            {
                "record_id": "R3",
                "title": "Unrelated source note",
                "keywords": ["maize"],
            },
        ]
    )

    records = provider.retrieve(_query_bundle())

    assert [record["record_id"] for record in records] == ["R1", "R2"]
    assert all(record["manual_review_flags"] == ["manual_review_required"] for record in records)


def test_fake_provider_empty_queries_return_no_records() -> None:
    provider = provider_module.FakeEvidenceRetrievalProvider(
        [{"record_id": "R1", "title": "Rice albumin source note"}]
    )

    assert provider.retrieve({"queries": []}) == []


def test_fake_provider_assigns_stable_id_when_source_identifier_exists() -> None:
    provider = provider_module.FakeEvidenceRetrievalProvider(
        [
            {
                "title": "Rice albumin source note",
                "abstract": "rice albumin evidence metadata",
                "source_identifier": "SRC-001",
            }
        ]
    )

    records = provider.retrieve(_query_bundle())

    assert records[0]["record_id"] == "SRC-001"


def test_fake_provider_does_not_import_network_or_streamlit_modules(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("fake evidence provider must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    provider = provider_module.FakeEvidenceRetrievalProvider(
        [{"record_id": "R1", "title": "Rice albumin source note"}]
    )
    assert provider.retrieve(_query_bundle())
    importlib.reload(provider_module)
