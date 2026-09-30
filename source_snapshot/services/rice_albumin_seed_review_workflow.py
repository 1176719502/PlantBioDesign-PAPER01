from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from services.plant_seed_review_workflow import (
    RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BATCH,
    RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BOUNDARY_NOTE,
    RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION,
    RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BATCH,
    RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BOUNDARY_NOTE,
    RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_SCHEMA_VERSION,
    RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_EMPTY,
    RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_READY,
    build_plant_seed_review_visible_mount,
    build_plant_seed_review_workflow,
)
from services.plant_evidence_seed_intake import DEFAULT_RICE_ALBUMIN_SEED_DIR


SEED_REVIEW_WORKFLOW_SCHEMA_VERSION = RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_SCHEMA_VERSION
SEED_REVIEW_WORKFLOW_BATCH = RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BATCH
SEED_REVIEW_WORKFLOW_STATUS_READY = RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_READY
SEED_REVIEW_WORKFLOW_STATUS_EMPTY = RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_EMPTY
SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION = RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION
SEED_REVIEW_VISIBLE_MOUNT_BATCH = RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BATCH
SEED_REVIEW_WORKFLOW_BOUNDARY_NOTE = RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BOUNDARY_NOTE
SEED_REVIEW_VISIBLE_MOUNT_BOUNDARY_NOTE = RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BOUNDARY_NOTE


def build_rice_albumin_seed_review_visible_mount(
    workflow_payload: Mapping[str, Any] | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
) -> dict[str, Any]:
    """Return the legacy R134 rice albumin visible mount via the generic dispatcher."""
    return build_plant_seed_review_visible_mount(
        workflow_payload,
        dataset_key="rice_albumin",
        seed_path=seed_dir,
    )


def build_rice_albumin_seed_review_workflow(
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
) -> dict[str, Any]:
    """Return the legacy R133 rice albumin workflow via the generic dispatcher."""
    return build_plant_seed_review_workflow(
        dataset_key="rice_albumin",
        seed_path=seed_dir,
    )
