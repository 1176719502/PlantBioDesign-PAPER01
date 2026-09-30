# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_expression_candidate_ingestion import config
from services.plant_expression_candidate_ingestion.adapters import (
    AdapterConfig,
    EuropePMCAdapter,
    SourceAdapterError,
    UniProtAdapter,
)
from services.plant_expression_candidate_ingestion.normalizers import (
    NormalizationError,
    NormalizedRecord,
    normalize_europe_pmc_record,
    normalize_uniprot_record,
)
from services.plant_expression_candidate_ingestion.pipeline import IngestionOptions, run_ingestion
from services.plant_expression_candidate_ingestion.registry import (
    QueryDefinition,
    RegistryError,
    SourceDefinition,
    load_query_plan,
    load_source_registry,
)
from services.plant_expression_candidate_ingestion.repository import CandidateRepository
from services.plant_expression_candidate_ingestion.storage import KnowledgePaths, RawSnapshotStore
from services.plant_expression_candidate_ingestion.utils import build_run_id, write_json
from scripts.data import ingest_plant_expression_candidates as ingest_cli


REGISTRY_PATH = ROOT / "data" / "plant_expression_ingestion" / "source_registry.v1.json"
QUERY_PLAN_PATH = ROOT / "data" / "plant_expression_ingestion" / "plant_expression_batch_1.query_plan.json"


def _source(source_id: str = "europe_pmc") -> SourceDefinition:
    return SourceDefinition(
        source_id=source_id,
        source_name="Test Source",
        adapter=source_id,
        base_url="https://example.test/api",
        endpoint_note="metadata endpoint",
        license_note="test metadata license note",
        usage_policy_note="test usage policy",
    )


def _query(query_id: str = "plant_promoter_expression") -> QueryDefinition:
    return QueryDefinition(
        query_id=query_id,
        description="Plant promoter expression",
        domain_label="plant promoter expression",
        enabled=True,
        max_records=10,
        version_date="2026-07-10",
        notes="metadata candidates only",
        source_queries={"europe_pmc": {"query": "plant promoter"}, "uniprot": {"query": "taxonomy_id:33090"}},
    )


def _europe_record(**patch: Any) -> dict[str, Any]:
    record = {
        "id": "123456",
        "pmid": "123456",
        "pmcid": "PMC123456",
        "doi": "10.1000/plant.1",
        "title": "Plant promoter expression vector metadata",
        "abstractText": "A metadata abstract mentioning a plant promoter and transient expression.",
        "pubYear": "2024",
        "journalTitle": "Metadata Journal",
        "authorString": "Curator A",
    }
    record.update(patch)
    return record


def _uniprot_record(**patch: Any) -> dict[str, Any]:
    record = {
        "primaryAccession": "P12345",
        "uniProtkbId": "TEST_PLANT",
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Plant signal peptide protein"}}},
        "organism": {"taxonId": 3702, "scientificName": "Arabidopsis thaliana"},
        "genes": [{"geneName": {"value": "SIG1"}, "synonyms": [{"value": "SP1"}]}],
        "comments": [
            {
                "commentType": "SUBCELLULAR LOCATION",
                "subcellularLocations": [{"location": {"value": "Secreted"}}],
            }
        ],
        "keywords": [{"name": "Signal"}, {"name": "Secreted"}],
    }
    record.update(patch)
    return record


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        json_error: bool = False,
    ):
        self.payload = payload or {}
        self.status_code = status_code
        self.headers = headers or {}
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            exc = requests.HTTPError("boom")
            exc.response = self
            raise exc

    def json(self) -> dict[str, Any]:
        if self.json_error:
            raise ValueError("bad json")
        return self.payload


class _FakeSession:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, endpoint: str, params: dict[str, Any], timeout: float) -> _FakeResponse:
        self.calls.append({"endpoint": endpoint, "params": dict(params), "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_source_registry_loading_and_query_plan_validation() -> None:
    sources = load_source_registry(REGISTRY_PATH)
    plan = load_query_plan(QUERY_PLAN_PATH)

    assert {"europe_pmc", "uniprot"}.issubset(sources)
    assert plan["query_plan_id"] == "plant_expression_batch_1"
    assert len(plan["queries"]) >= 18
    assert all(query.query_for_source("europe_pmc") for query in plan["queries"])


def test_unsupported_registry_and_query_schema_fail_safely(tmp_path: Path) -> None:
    bad_registry = tmp_path / "bad_registry.json"
    write_json(bad_registry, {"schema_version": "future", "sources": []})
    with pytest.raises(RegistryError):
        load_source_registry(bad_registry)

    bad_plan = tmp_path / "bad_plan.json"
    write_json(bad_plan, {"schema_version": "future", "queries": []})
    with pytest.raises(RegistryError):
        load_query_plan(bad_plan)


def test_run_id_explicit_behavior_and_generated_identity() -> None:
    assert build_run_id("europe_pmc", "2026-07-10T00:00:00Z", "manual-run-1") == "manual-run-1"
    generated = build_run_id("europe_pmc", "2026-07-10T00:00:00Z")
    assert generated.startswith("r225-europe_pmc-20260710T0000")
    assert generated == build_run_id("europe_pmc", "2026-07-10T00:00:00Z")


def test_raw_snapshot_writing_and_non_overwrite_behavior(tmp_path: Path) -> None:
    paths = KnowledgePaths(tmp_path / "Root With Space")
    paths.ensure_runtime_dirs()
    store = RawSnapshotStore(paths)
    payload = {"source": "europe_pmc", "records": [{"id": "1"}]}

    result = store.write_snapshot(
        source_id="europe_pmc",
        ingestion_run_id="run-1",
        query_id="q1",
        page_index=1,
        payload=payload,
    )

    assert (paths.root / result.relative_path).exists()
    assert result.content_hash
    with pytest.raises(FileExistsError):
        store.write_snapshot(
            source_id="europe_pmc",
            ingestion_run_id="run-1",
            query_id="q1",
            page_index=1,
            payload=payload,
        )


def test_europe_pmc_adapter_pagination_retry_timeout_and_malformed_payload() -> None:
    session = _FakeSession(
        [
            requests.Timeout("slow"),
            _FakeResponse(
                {
                    "resultList": {"result": [_europe_record(id="1", pmid="1"), _europe_record(id="2", pmid="2")]},
                    "nextCursorMark": "next-1",
                }
            ),
            _FakeResponse({"resultList": {"result": [_europe_record(id="3", pmid="3")]}, "nextCursorMark": "next-1"}),
        ]
    )
    adapter = EuropePMCAdapter(_source("europe_pmc"), config=AdapterConfig(retries=1, retry_delay=0, page_size=2, pace_seconds=0), session=session)

    pages = adapter.fetch_pages({"query": "plant promoter"}, max_records=3)

    assert len(pages) == 2
    assert sum(len(page.records) for page in pages) == 3
    assert len(session.calls) == 3

    malformed = EuropePMCAdapter(
        _source("europe_pmc"),
        config=AdapterConfig(retries=0, retry_delay=0, pace_seconds=0),
        session=_FakeSession([_FakeResponse({"resultList": {"result": {}}})]),
    )
    with pytest.raises(SourceAdapterError):
        malformed.fetch_pages({"query": "plant promoter"}, max_records=1)


def test_uniprot_adapter_pagination() -> None:
    link = '<https://rest.uniprot.org/uniprotkb/search?cursor=next-token>; rel="next"'
    session = _FakeSession(
        [
            _FakeResponse({"results": [_uniprot_record(primaryAccession="P1")]}, headers={"Link": link}),
            _FakeResponse({"results": [_uniprot_record(primaryAccession="P2")]}, headers={}),
        ]
    )
    adapter = UniProtAdapter(_source("uniprot"), config=AdapterConfig(page_size=1, pace_seconds=0), session=session)

    pages = adapter.fetch_pages({"query": "taxonomy_id:33090"}, max_records=2)

    assert [page.records[0]["primaryAccession"] for page in pages] == ["P1", "P2"]
    assert session.calls[1]["params"]["cursor"] == "next-token"


def test_normalization_of_publication_and_protein_metadata_preserves_boundaries() -> None:
    pub = normalize_europe_pmc_record(source=_source("europe_pmc"), query=_query(), record=_europe_record())
    protein = normalize_uniprot_record(source=_source("uniprot"), query=_query(), record=_uniprot_record())

    assert pub.pmid == "123456"
    assert pub.doi == "10.1000/plant.1"
    assert pub.review_status == "needs_manual_review"
    assert pub.provenance_status == "candidate"
    assert pub.evidence_status == "metadata_candidate"
    assert pub.component_type_candidate == "promoter/regulatory region metadata"
    assert protein.accession == "P12345"
    assert protein.taxon_id == "3702"
    assert "SIG1" in protein.aliases
    assert protein.evidence_status == "accession_metadata_candidate"


def test_malformed_records_and_unsafe_statuses_are_rejected() -> None:
    with pytest.raises(NormalizationError):
        normalize_europe_pmc_record(source=_source("europe_pmc"), query=_query(), record={"id": "missing-title"})

    unsafe = NormalizedRecord(
        canonical_record_id="x",
        record_type="publication",
        primary_name="Unsafe",
        source_id="europe_pmc",
        source_record_id="1",
        content_hash="hash",
        review_status="validated",
    )
    with pytest.raises(NormalizationError):
        unsafe.validate()


def test_sqlite_insert_reload_dedup_cross_query_uncertain_identity_and_search(tmp_path: Path) -> None:
    repo = CandidateRepository(tmp_path / "kb" / "database" / "plant_expression_candidates.sqlite3")
    repo.init_schema()
    source = _source("europe_pmc")
    repo.register_source(source)
    for run_id in ("run-1", "run-2"):
        repo.start_run(
            {
                "ingestion_run_id": run_id,
                "source_id": source.source_id,
                "query_plan_id": "plant_expression_batch_1",
                "adapter_version": source.adapter_version,
                "started_at": "2026-07-10T00:00:00Z",
            }
        )

    first = normalize_europe_pmc_record(source=source, query=_query("q1"), record=_europe_record(id="SRC1", pmid="111", doi="10.1000/same"))
    duplicate = normalize_europe_pmc_record(source=source, query=_query("q2"), record=_europe_record(id="SRC1", pmid="111", doi="10.1000/same"))
    uncertain = normalize_europe_pmc_record(source=source, query=_query("q2"), record=_europe_record(id="SRC2", pmid="", pmcid="", doi="", title=first.primary_name))

    first_stats = repo.insert_records(
        ingestion_run_id="run-1",
        query_id="q1",
        raw_snapshot_path="raw/europe_pmc/run-1/q1.page-00001.json",
        raw_snapshot_hash="hash1",
        records=[first],
    )
    duplicate_stats = repo.insert_records(
        ingestion_run_id="run-2",
        query_id="q2",
        raw_snapshot_path="raw/europe_pmc/run-2/q2.page-00001.json",
        raw_snapshot_hash="hash2",
        records=[duplicate, uncertain],
    )
    repo.finish_run("run-1", status="completed", manifest_path="manifests/run-1.json", summary={})
    repo.finish_run("run-2", status="completed", manifest_path="manifests/run-2.json", summary={})

    stats = repo.stats()
    reopened = CandidateRepository(repo.database_path)

    assert first_stats == {"inserted_count": 1, "duplicate_count": 0}
    assert duplicate_stats == {"inserted_count": 1, "duplicate_count": 1}
    assert stats["total_records"] == 2
    assert stats["review_status_counts"] == {"needs_manual_review": 2}
    assert stats["unique_identifier_count"] >= 4
    assert len(stats["latest_ingestion_runs"]) == 2
    assert reopened.search("promoter", limit=5)
    assert "recommended" not in json.dumps(stats).casefold()


def test_pipeline_dry_run_fatal_exit_and_no_import_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("services.plant_expression_candidate_ingestion.pipeline")
    before = set(tmp_path.iterdir())
    importlib.reload(module)
    after = set(tmp_path.iterdir())
    assert before == after

    preview = run_ingestion(
        IngestionOptions(
            data_root=tmp_path / "kb",
            source_id="europe_pmc",
            query_plan_path=QUERY_PLAN_PATH,
            source_registry_path=REGISTRY_PATH,
            query_ids=("plant_expression_vector",),
            dry_run=True,
        )
    )
    assert preview["dry_run"] is True
    assert preview["queries"][0]["query_id"] == "plant_expression_vector"

    exit_code = ingest_cli.main(["--source", "missing_source", "--dry-run", "--data-root", str(tmp_path / "kb")])
    assert exit_code == 2


def test_pipeline_with_fake_adapter_preserves_manifests_and_isolated_storage(
    external_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAdapter:
        def fetch_pages(self, query_params: dict[str, Any], *, max_records: int):
            from services.plant_expression_candidate_ingestion.adapters import AdapterPage

            return [
                AdapterPage(
                    endpoint="https://example.test/europe",
                    request_params={"query": query_params["query"]},
                    payload={"resultList": {"result": [_europe_record()]}},
                    records=[_europe_record()],
                    next_token="",
                )
            ]

    import services.plant_expression_candidate_ingestion.pipeline as pipeline

    monkeypatch.setattr(pipeline, "build_adapter", lambda *args, **kwargs: _FakeAdapter())
    data_root = external_tmp_path / "isolated kb"
    result = run_ingestion(
        IngestionOptions(
            data_root=data_root,
            source_id="europe_pmc",
            query_plan_path=QUERY_PLAN_PATH,
            source_registry_path=REGISTRY_PATH,
            query_ids=("plant_expression_vector",),
            max_records=1,
            page_size=1,
        )
    )

    assert result["retrieved_count"] == 1
    assert result["normalized_count"] == 1
    assert result["error_count"] == 0
    assert (data_root / "database" / "plant_expression_candidates.sqlite3").exists()
    assert list((data_root / "raw" / "europe_pmc").rglob("*.json"))
    assert list((data_root / "manifests").glob("*.manifest.json"))
    assert str(ROOT) not in str(data_root.resolve())


def test_license_metadata_and_windows_path_behavior(tmp_path: Path) -> None:
    paths = KnowledgePaths(tmp_path / "Windows Style Path With Spaces")
    repo = CandidateRepository(paths.database_path)
    repo.init_schema()
    source = _source("uniprot")
    repo.register_source(source)
    repo.start_run(
        {
            "ingestion_run_id": "run-license",
            "source_id": "uniprot",
            "query_plan_id": "plant_expression_batch_1",
            "adapter_version": source.adapter_version,
            "started_at": "2026-07-10T00:00:00Z",
        }
    )
    record = normalize_uniprot_record(source=source, query=_query(), record=_uniprot_record())
    repo.insert_records(
        ingestion_run_id="run-license",
        query_id="q-license",
        raw_snapshot_path="raw/uniprot/run-license/q.page-00001.json",
        raw_snapshot_hash="hash",
        records=[record],
    )

    stats = repo.stats()
    assert stats["database_path"].endswith("plant_expression_candidates.sqlite3")
    assert stats["records_by_source"] == {"uniprot": 1}
