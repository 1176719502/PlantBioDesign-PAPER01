from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class HttpClientConfig:
    base_url: str
    timeout: float
    service_name: str


class HttpServiceError(RuntimeError):
    """Normalized external-service failure for local API wrappers."""


_session = requests.Session()


def build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def request_json(
    method: str,
    *,
    base_url: str,
    path: str,
    timeout: float,
    service_name: str,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = build_url(base_url, path)
    try:
        response = _session.request(
            method=method.upper(),
            url=url,
            json=json_payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise HttpServiceError(f"{service_name} request timed out after {timeout} seconds.") from exc
    except requests.ConnectionError as exc:
        raise HttpServiceError(f"{service_name} is unavailable at {base_url}.") from exc
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        raise HttpServiceError(f"{service_name} request failed with HTTP {status_code}.") from exc
    except requests.RequestException as exc:
        raise HttpServiceError(f"{service_name} request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HttpServiceError(f"{service_name} returned an invalid JSON response.") from exc

    if not isinstance(payload, dict):
        raise HttpServiceError(f"{service_name} returned an unexpected response payload.")
    return payload
