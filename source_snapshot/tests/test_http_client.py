from __future__ import annotations

import os
import sys

import pytest
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import http_client
from services.http_client import HttpServiceError, request_json


class _FakeResponse:
    def __init__(self, payload=None, status_code: int = 200, json_error: bool = False):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError("boom")
            error.response = self
            raise error

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._payload


def test_request_json_returns_dict_payload(monkeypatch):
    monkeypatch.setattr(
        http_client._session,
        "request",
        lambda **kwargs: _FakeResponse(payload={"ok": True}),
    )

    result = request_json(
        "GET",
        base_url="http://127.0.0.1:8000",
        path="/health",
        timeout=5,
        service_name="Test API",
    )

    assert result == {"ok": True}


def test_request_json_normalizes_timeout(monkeypatch):
    def _raise_timeout(**kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(http_client._session, "request", _raise_timeout)

    with pytest.raises(HttpServiceError, match="timed out"):
        request_json(
            "GET",
            base_url="http://127.0.0.1:8000",
            path="/health",
            timeout=5,
            service_name="Test API",
        )


def test_request_json_normalizes_connection_error(monkeypatch):
    def _raise_connection(**kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(http_client._session, "request", _raise_connection)

    with pytest.raises(HttpServiceError, match="unavailable"):
        request_json(
            "GET",
            base_url="http://127.0.0.1:8000",
            path="/health",
            timeout=5,
            service_name="Test API",
        )


def test_request_json_normalizes_http_error(monkeypatch):
    monkeypatch.setattr(
        http_client._session,
        "request",
        lambda **kwargs: _FakeResponse(payload={"detail": "error"}, status_code=500),
    )

    with pytest.raises(HttpServiceError, match="HTTP 500"):
        request_json(
            "GET",
            base_url="http://127.0.0.1:8000",
            path="/health",
            timeout=5,
            service_name="Test API",
        )


def test_request_json_normalizes_invalid_json(monkeypatch):
    monkeypatch.setattr(
        http_client._session,
        "request",
        lambda **kwargs: _FakeResponse(json_error=True),
    )

    with pytest.raises(HttpServiceError, match="invalid JSON"):
        request_json(
            "GET",
            base_url="http://127.0.0.1:8000",
            path="/health",
            timeout=5,
            service_name="Test API",
        )
