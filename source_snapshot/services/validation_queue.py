from __future__ import annotations

import os
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job

from services.validation_service import run_validation_report


_QUEUE_NAME = os.getenv("VALIDATION_QUEUE_NAME", "validation-report")
_REDIS_URL = os.getenv("VALIDATION_REDIS_URL", os.getenv("PRIMER_REDIS_URL", "redis://localhost:6379/0"))


def _redis_connection() -> Redis:
    return Redis.from_url(_REDIS_URL)


def get_validation_queue() -> Queue:
    return Queue(_QUEUE_NAME, connection=_redis_connection())


def enqueue_validation_report(payload: dict[str, Any]) -> str:
    queue = get_validation_queue()
    job = queue.enqueue(run_validation_report, kwargs=payload)
    return job.id


def get_validation_task_status(task_id: str) -> dict[str, Any]:
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
