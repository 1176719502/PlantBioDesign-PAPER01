from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.dev.api_primer import app


client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_primer_design_endpoint_returns_structured_payload():
    sequence = ("ATGGCCATGGCCATTA" * 8)[:128]

    response = client.post(
        "/primers/design",
        json={
            "sequence": sequence,
            "target_tm": 60.0,
            "tm_tolerance": 2.0,
            "min_length": 18,
            "max_length": 30,
            "num_designs": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["results"]
    assert len(payload["results"]) <= 3
    assert payload["results"][0]["primers"]


def test_primer_task_status_endpoint_returns_not_found_for_unknown_task():
    response = client.get("/primers/design/tasks/missing-task")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_found"


def test_validation_run_endpoint_returns_structured_payload():
    response = client.post(
        "/validation/run",
        json={
            "frame": {
                "success": True,
                "final_sequence": "ATGGCC" * 20 + "TAA",
                "gc_content": 52.0,
                "features": [
                    {"name": "Target Gene (CDS)", "type": "CDS", "start": 1, "end": 123},
                ],
                "kingdom": "prokaryote",
            },
            "primers": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "issues" in payload
    assert "primer_summary" in payload


def test_validation_task_status_endpoint_returns_not_found_for_unknown_task():
    response = client.get("/validation/tasks/missing-task")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_found"
