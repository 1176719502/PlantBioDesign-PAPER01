from __future__ import annotations

import os
from typing import Any

from services.http_client import HttpServiceError, request_json


DEFAULT_TIMEOUT = float(os.getenv("VALIDATION_API_TIMEOUT_SECONDS", os.getenv("PRIMER_API_TIMEOUT_SECONDS", "20")))
DEFAULT_API_BASE_URL = os.getenv("VALIDATION_API_BASE_URL", os.getenv("PRIMER_API_BASE_URL", "http://127.0.0.1:8000"))
SERVICE_NAME = "Validation API"


class ValidationApiError(HttpServiceError):
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
        raise ValidationApiError(str(exc)) from exc


def request_validation_report(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/validation/run", payload)


def enqueue_validation_task(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/validation/tasks", payload)


def get_validation_task(task_id: str) -> dict[str, Any]:
    return _request("GET", f"/validation/tasks/{task_id}")
