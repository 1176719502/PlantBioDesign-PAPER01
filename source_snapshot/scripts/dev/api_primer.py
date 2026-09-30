from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from services.primer_queue import enqueue_primer_design, get_primer_task_status
from services.primer_service import design_and_evaluate_primers, design_outer_primers_for_cassette
from services.validation_queue import enqueue_validation_report, get_validation_task_status
from services.validation_service import run_validation_report


app = FastAPI(
    title="BioDesign Studio Primer API",
    version="1.1.0",
    description="Stateless Primer3-based primer design API for concurrent multi-user use.",
)


class PrimerDesignRequest(BaseModel):
    sequence: str = Field(..., min_length=1, description="DNA template sequence")
    target_tm: float = Field(60.0, ge=40.0, le=80.0)
    tm_tolerance: float = Field(2.0, ge=0.0, le=10.0)
    min_length: int = Field(18, ge=12, le=40)
    max_length: int = Field(30, ge=12, le=60)
    num_designs: int = Field(5, ge=1, le=10)
    design_scope: str | None = Field(None, description="Optional primer design scope")


class ValidationReportRequest(BaseModel):
    frame: dict = Field(..., description="Expression frame payload for biological validation")
    primers: list[dict] = Field(default_factory=list, description="Primer rows carried over from Step 4")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/primers/design")
def design_primers_endpoint(payload: PrimerDesignRequest) -> dict:
    if payload.design_scope == "expression_cassette":
        return design_outer_primers_for_cassette(
            payload.sequence,
            target_tm=payload.target_tm,
            tm_tolerance=payload.tm_tolerance,
            min_length=payload.min_length,
            max_length=payload.max_length,
            num_designs=payload.num_designs,
        )
    return design_and_evaluate_primers(
        payload.sequence,
        target_tm=payload.target_tm,
        tm_tolerance=payload.tm_tolerance,
        min_length=payload.min_length,
        max_length=payload.max_length,
        num_designs=payload.num_designs,
    )


@app.post("/primers/design/tasks")
def enqueue_design_task_endpoint(payload: PrimerDesignRequest) -> dict[str, str]:
    task_id = enqueue_primer_design(payload.model_dump())
    return {"task_id": task_id, "status": "queued"}


@app.get("/primers/design/tasks/{task_id}")
def primer_design_task_status(task_id: str) -> dict:
    return get_primer_task_status(task_id)


@app.post("/validation/tasks")
def enqueue_validation_task_endpoint(payload: ValidationReportRequest) -> dict[str, str]:
    task_id = enqueue_validation_report(payload.model_dump())
    return {"task_id": task_id, "status": "queued"}


@app.get("/validation/tasks/{task_id}")
def validation_task_status(task_id: str) -> dict:
    return get_validation_task_status(task_id)


@app.post("/validation/run")
def run_validation_endpoint(payload: ValidationReportRequest) -> dict:
    return run_validation_report(
        frame=payload.frame,
        primers=payload.primers,
    )
