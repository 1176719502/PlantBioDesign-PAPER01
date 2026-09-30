from __future__ import annotations

import os
from typing import Any

from services.validation_api_client import enqueue_validation_task
from services.validation_service import run_validation_report


_EXECUTION_MODE_ENV = "VALIDATION_EXECUTION_MODE"


def validation_execution_mode() -> str:
    mode = str(os.getenv(_EXECUTION_MODE_ENV, "local") or "local").strip().lower()
    return "async" if mode == "async" else "local"


def run_or_enqueue_validation(payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = payload if isinstance(payload, dict) else {}
    if validation_execution_mode() == "async":
        task_payload = enqueue_validation_task(safe_payload)
        return {
            "mode": "async",
            "status": "queued",
            "task": task_payload,
        }

    frame = safe_payload.get("frame") if isinstance(safe_payload.get("frame"), dict) else {}
    primers = safe_payload.get("primers") if isinstance(safe_payload.get("primers"), list) else []
    result_payload = run_validation_report(frame=frame, primers=primers)
    return {
        "mode": "local",
        "status": "finished",
        "result": result_payload,
    }
