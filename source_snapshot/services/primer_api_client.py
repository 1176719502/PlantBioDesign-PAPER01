from __future__ import annotations

import os
from typing import Any

from services.http_client import HttpServiceError, request_json


DEFAULT_TIMEOUT = float(os.getenv("PRIMER_API_TIMEOUT_SECONDS", "20"))
DEFAULT_API_BASE_URL = os.getenv("PRIMER_API_BASE_URL", "http://127.0.0.1:8000")
SERVICE_NAME = "Primer API"


class PrimerApiError(HttpServiceError):
    pass


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return request_json(
            method,
            base_url=DEFAULT_API_BASE_URL,
            path=path,
            timeout=DEFAULT_TIMEOUT,
            service_name=SERVICE_NAME,
            json_payload=payload,
        )
    except HttpServiceError as exc:
        raise PrimerApiError(str(exc)) from exc


def request_primer_design(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/primers/design", payload)


def enqueue_primer_design_task(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/primers/design/tasks", payload)


def get_primer_design_task(task_id: str) -> dict[str, Any]:
    return _request("GET", f"/primers/design/tasks/{task_id}")
