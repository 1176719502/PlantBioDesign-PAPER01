from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from services.plant_expression_candidate_ingestion.registry import SourceDefinition


class SourceAdapterError(RuntimeError):
    """Raised when a source adapter cannot fetch or parse a page."""


@dataclass(frozen=True)
class AdapterConfig:
    timeout: float = 20.0
    retries: int = 2
    retry_delay: float = 1.0
    page_size: int = 100
    pace_seconds: float = 0.2


@dataclass(frozen=True)
class AdapterPage:
    endpoint: str
    request_params: dict[str, Any]
    payload: dict[str, Any]
    records: list[dict[str, Any]]
    next_token: str


class BaseSourceAdapter:
    def __init__(
        self,
        source: SourceDefinition,
        *,
        config: AdapterConfig | None = None,
        session: requests.Session | None = None,
    ):
        self.source = source
        self.config = config or AdapterConfig()
        self.session = session or requests.Session()

    def fetch_pages(self, query_params: dict[str, Any], *, max_records: int) -> list[AdapterPage]:
        raise NotImplementedError

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        last_error: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self.session.get(endpoint, params=params, timeout=self.config.timeout)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SourceAdapterError("Source returned a non-object JSON payload.")
                return payload, dict(response.headers)
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError, SourceAdapterError) as exc:
                last_error = exc
                if attempt >= self.config.retries:
                    break
                time.sleep(self.config.retry_delay)
        raise SourceAdapterError(f"{self.source.source_id} request failed after retries: {last_error}") from last_error


class EuropePMCAdapter(BaseSourceAdapter):
    endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def fetch_pages(self, query_params: dict[str, Any], *, max_records: int) -> list[AdapterPage]:
        query_text = str(query_params.get("query") or "").strip()
        if not query_text:
            raise SourceAdapterError("Europe PMC query text is required.")
        cursor = "*"
        pages: list[AdapterPage] = []
        retrieved = 0
        page_size = min(int(query_params.get("page_size") or self.config.page_size), self.config.page_size)
        while retrieved < max_records:
            params = {
                "query": query_text,
                "format": "json",
                "pageSize": min(page_size, max_records - retrieved),
                "cursorMark": cursor,
                "resultType": query_params.get("result_type") or "core",
            }
            payload, _headers = self._get_json(self.endpoint, params)
            results = payload.get("resultList", {}).get("result", [])
            if not isinstance(results, list):
                raise SourceAdapterError("Europe PMC resultList.result must be a list.")
            records = [item for item in results if isinstance(item, dict)]
            pages.append(
                AdapterPage(
                    endpoint=self.endpoint,
                    request_params=params,
                    payload=payload,
                    records=records,
                    next_token=str(payload.get("nextCursorMark") or ""),
                )
            )
            retrieved += len(records)
            next_cursor = str(payload.get("nextCursorMark") or "")
            if not records or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(self.config.pace_seconds)
        return pages


class UniProtAdapter(BaseSourceAdapter):
    endpoint = "https://rest.uniprot.org/uniprotkb/search"

    def fetch_pages(self, query_params: dict[str, Any], *, max_records: int) -> list[AdapterPage]:
        query_text = str(query_params.get("query") or "").strip()
        if not query_text:
            raise SourceAdapterError("UniProt query text is required.")
        cursor = ""
        pages: list[AdapterPage] = []
        retrieved = 0
        page_size = min(int(query_params.get("page_size") or self.config.page_size), self.config.page_size)
        while retrieved < max_records:
            params = {
                "query": query_text,
                "format": "json",
                "size": min(page_size, max_records - retrieved),
                "fields": query_params.get("fields")
                or "accession,id,protein_name,gene_names,organism_name,organism_id",
            }
            if cursor:
                params["cursor"] = cursor
            payload, headers = self._get_json(self.endpoint, params)
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise SourceAdapterError("UniProt results must be a list.")
            records = [item for item in results if isinstance(item, dict)]
            next_cursor = _extract_uniprot_next_cursor(headers.get("Link", ""))
            pages.append(
                AdapterPage(
                    endpoint=self.endpoint,
                    request_params=params,
                    payload=payload,
                    records=records,
                    next_token=next_cursor,
                )
            )
            retrieved += len(records)
            if not records or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(self.config.pace_seconds)
        return pages


def _extract_uniprot_next_cursor(link_header: str) -> str:
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start < 0 or end <= start:
            continue
        parsed = urlparse(part[start + 1 : end])
        values = parse_qs(parsed.query).get("cursor", [])
        if values:
            return values[0]
    return ""


def build_adapter(
    source: SourceDefinition,
    *,
    config: AdapterConfig | None = None,
    session: requests.Session | None = None,
) -> BaseSourceAdapter:
    if source.adapter == "europe_pmc":
        return EuropePMCAdapter(source, config=config, session=session)
    if source.adapter == "uniprot":
        return UniProtAdapter(source, config=config, session=session)
    raise SourceAdapterError(f"Unsupported source adapter: {source.adapter}")
