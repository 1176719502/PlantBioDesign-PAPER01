from __future__ import annotations

import os
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job

from services.primer_service import design_and_evaluate_primers, design_outer_primers_for_cassette


_QUEUE_NAME = os.getenv("PRIMER_QUEUE_NAME", "primer-design")
_REDIS_URL = os.getenv("PRIMER_REDIS_URL", "redis://localhost:6379/0")


def _redis_connection() -> Redis:
    return Redis.from_url(_REDIS_URL)


def get_primer_queue() -> Queue:
    return Queue(_QUEUE_NAME, connection=_redis_connection())


def _run_primer_design(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    design_scope = payload.pop("design_scope", None)
    if design_scope == "expression_cassette":
        return design_outer_primers_for_cassette(**payload)
    return design_and_evaluate_primers(**payload)


def enqueue_primer_design(payload: dict[str, Any]) -> str:
    queue = get_primer_queue()
    job = queue.enqueue(_run_primer_design, payload)
    return job.id


def get_primer_task_status(task_id: str) -> dict[str, Any]:
    try:
        job = Job.fetch(task_id, connection=_redis_connection())
    except Exception as exc:
        return {
            "task_id": task_id,
            "status": "not_found",
            "result": None,
            "error": str(exc),
        }

    return {
        "task_id": task_id,
        "status": job.get_status(),
        "result": job.result if job.is_finished else None,
        "error": str(job.exc_info) if job.is_failed else "",
    }
