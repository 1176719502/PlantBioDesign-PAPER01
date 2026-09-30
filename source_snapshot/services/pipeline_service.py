# -*- coding: utf-8 -*-
"""
services/pipeline_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Automated 3-step expression design pipeline.

Pipeline stages
---------------
  Stage 1 — Codon Optimization
      core.codon_optimizer.optimize_cds_sequence()

  Stage 2 — Expression Frame Assembly
      core.expression_frame_builder.build_expression_frame()
      core.expression_frame_builder.validate_frame()

  Stage 3 — Gibson Assembly Primer Design
      core.assembly_planner.AssemblyPlanner.plan_gibson_assembly()

Each stage produces a typed result dict.  Failures are captured in-band
(success=False + errors list) so the caller can show partial results.
No Streamlit imports — pure Python only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Stage result containers
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Result for a single pipeline stage."""
    stage_id: int                           # 1, 2, or 3
    name: str                               # human-readable stage name
    success: bool = False
    skipped: bool = False
    duration_ms: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Aggregated result across all three stages."""
    success: bool = False                   # True only if ALL stages succeed
    stages: List[StageResult] = field(default_factory=list)
    # Convenience shortcuts populated on completion
    optimized_seq: str = ""
    codon_report: Dict[str, Any] = field(default_factory=dict)
    frame: Dict[str, Any] = field(default_factory=dict)
    validation_issues: List[Dict[str, Any]] = field(default_factory=list)
    primers: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def critical_issues(self) -> List[Dict[str, Any]]:
        return [i for i in self.validation_issues if i.get("severity") == "critical"]

    @property
    def warning_issues(self) -> List[Dict[str, Any]]:
        return [i for i in self.validation_issues if i.get("severity") == "warning"]

    def stage(self, stage_id: int) -> Optional[StageResult]:
        for s in self.stages:
            if s.stage_id == stage_id:
                return s
        return None


# ---------------------------------------------------------------------------
# Progress callback protocol
# ---------------------------------------------------------------------------
# Callers may pass a progress_cb with signature:
#   progress_cb(stage_id: int, total_stages: int, message: str, fraction: float)
# Fraction is in [0.0, 1.0].  The callback is never required.

ProgressCallback = Optional[Callable[[int, int, str, float], None]]


# ---------------------------------------------------------------------------
# Codon-table key resolver (reuses expression_frame_builder host rules)
# ---------------------------------------------------------------------------

def _resolve_optimizer_host(host: str) -> str:
    """Map expression host label to codon optimizer host key."""
    try:
        from core.expression_frame_builder import get_host_rules
        rules = get_host_rules(host)
        return rules.get("codon_table_key") or "E.coli"
    except Exception:
        return "E.coli"


# ---------------------------------------------------------------------------
# Stage 1 — Codon Optimization
# ---------------------------------------------------------------------------

def _run_codon_optimization(
    sequence: str,
    host: str,
    progress_cb: ProgressCallback = None,
) -> StageResult:
    result = StageResult(stage_id=1, name="Codon Optimization")
    if progress_cb:
        progress_cb(1, 3, "Running codon optimization...", 0.05)

    t0 = time.perf_counter()
    try:
        from core.codon_optimizer import optimize_cds_sequence
        optimizer_host = _resolve_optimizer_host(host)
        opt_result = optimize_cds_sequence(sequence=sequence, host=optimizer_host)
        result.duration_ms = (time.perf_counter() - t0) * 1000

        if not opt_result.get("success"):
            result.success = False
            result.errors = opt_result.get("errors") or ["Codon optimization returned no result."]
            result.data = opt_result
            return result

        result.success = True
        result.data = opt_result
        result.warnings = list(opt_result.get("warnings") or [])

        if progress_cb:
            progress_cb(1, 3, "Codon optimization complete.", 0.33)

    except Exception as exc:
        result.duration_ms = (time.perf_counter() - t0) * 1000
        result.success = False
        result.errors = [f"Codon optimization error: {exc}"]

    return result


# ---------------------------------------------------------------------------
# Stage 2 — Expression Frame Assembly + Validation
# ---------------------------------------------------------------------------

def _run_expression_frame(
    optimized_seq: str,
    host: str,
    tag: str,
    progress_cb: ProgressCallback = None,
) -> StageResult:
    result = StageResult(stage_id=2, name="Expression Frame Assembly")
    if progress_cb:
        progress_cb(2, 3, "Assembling expression frame...", 0.38)

    t0 = time.perf_counter()
    try:
        from core.expression_frame_builder import build_expression_frame, validate_frame

        frame = build_expression_frame(
            gene_seq=optimized_seq,
            host=host,
            tag=tag,
        )
        if not frame.get("success"):
            result.duration_ms = (time.perf_counter() - t0) * 1000
            result.success = False
            result.errors = [frame.get("error") or "Expression frame assembly failed."]
            result.data = {"frame": frame, "validation_issues": []}
            return result

        issues = validate_frame(frame)
        result.duration_ms = (time.perf_counter() - t0) * 1000
        result.success = True
        result.data = {"frame": frame, "validation_issues": issues}
        result.warnings = [
            i["title"] for i in issues if i.get("severity") == "warning"
        ]
        # critical validation issues are non-fatal at the service level —
        # the caller decides whether to continue to primer design
        result.errors = [
            i["title"] for i in issues if i.get("severity") == "critical"
        ]

        if progress_cb:
            progress_cb(2, 3, "Expression frame assembled.", 0.66)

    except Exception as exc:
        result.duration_ms = (time.perf_counter() - t0) * 1000
        result.success = False
        result.errors = [f"Expression frame error: {exc}"]

    return result


# ---------------------------------------------------------------------------
# Stage 3 — Gibson Assembly Primer Design
# ---------------------------------------------------------------------------

def _run_primer_design(
    frame: Dict[str, Any],
    overlap_len: int,
    target_tm: float,
    progress_cb: ProgressCallback = None,
) -> StageResult:
    result = StageResult(stage_id=3, name="Primer Design")
    if progress_cb:
        progress_cb(3, 3, "Designing Gibson Assembly primers...", 0.70)

    t0 = time.perf_counter()
    try:
        from core.assembly_planner import AssemblyPlanner

        planner = AssemblyPlanner()
        plan = planner.plan_gibson_assembly(
            construct_result=frame,
            overlap_len=overlap_len,
            target_tm=target_tm,
        )
        result.duration_ms = (time.perf_counter() - t0) * 1000

        primers = plan.get("primers", [])
        if not primers:
            # The planner silently returns an empty list when there are fewer
            # than 2 features — treat this as a warning, not a hard error.
            result.success = True
            result.warnings = [
                "Primer design returned 0 primers. "
                "The construct may have fewer than 2 annotated features."
            ]
            result.data = plan
        else:
            result.success = True
            result.data = plan

        if progress_cb:
            progress_cb(3, 3, "Primer design complete.", 1.0)

    except Exception as exc:
        result.duration_ms = (time.perf_counter() - t0) * 1000
        result.success = False
        result.errors = [f"Primer design error: {exc}"]

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    sequence: str,
    host: str,
    tag: str = "No tag",
    overlap_len: int = 20,
    target_tm: float = 60.0,
    progress_cb: ProgressCallback = None,
    stop_on_critical: bool = True,
) -> PipelineResult:
    """
    Run the full automated 3-stage pipeline.

    Parameters
    ----------
    sequence : str
        Input CDS (raw DNA string; will be validated/cleaned by codon optimizer).
    host : str
        Expression host label, e.g. 'E.coli BL21(DE3)'.
    tag : str
        Affinity tag label, e.g. 'His6-tag (C-term)' or 'No tag'.
    overlap_len : int
        Gibson Assembly overlap length in bp (default 20).
    target_tm : float
        Target annealing Tm for primer design in °C (default 60.0).
    progress_cb : callable, optional
        Called after each stage: (stage_id, total, message, fraction).
    stop_on_critical : bool
        If True, halt after Stage 2 when critical validation issues are found
        and do not proceed to primer design (default True).

    Returns
    -------
    PipelineResult
        Aggregated result.  Check .success and each .stages[i].success.
    """
    pipeline_t0 = time.perf_counter()
    result = PipelineResult()

    # ── Stage 1: Codon Optimization ────────────────────────────────────────
    s1 = _run_codon_optimization(sequence, host, progress_cb)
    result.stages.append(s1)

    if not s1.success:
        result.success = False
        result.total_duration_ms = (time.perf_counter() - pipeline_t0) * 1000
        return result

    optimized_seq: str = (
        s1.data.get("optimized_sequence") or sequence
    )
    result.optimized_seq = optimized_seq
    result.codon_report = s1.data

    # ── Stage 2: Expression Frame Assembly ────────────────────────────────
    s2 = _run_expression_frame(optimized_seq, host, tag, progress_cb)
    result.stages.append(s2)

    if not s2.success:
        result.success = False
        result.total_duration_ms = (time.perf_counter() - pipeline_t0) * 1000
        return result

    frame: Dict[str, Any] = s2.data.get("frame", {})
    issues: List[Dict[str, Any]] = s2.data.get("validation_issues", [])
    result.frame = frame
    result.validation_issues = issues

    # Respect stop_on_critical flag
    critical_issues = [i for i in issues if i.get("severity") == "critical"]
    if stop_on_critical and critical_issues:
        result.success = False
        result.stages.append(
            StageResult(
                stage_id=3,
                name="Primer Design",
                skipped=True,
                warnings=[
                    "Skipped: critical validation issues must be resolved first."
                ],
            )
        )
        result.total_duration_ms = (time.perf_counter() - pipeline_t0) * 1000
        return result

    # ── Stage 3: Primer Design ─────────────────────────────────────────────
    s3 = _run_primer_design(frame, overlap_len, target_tm, progress_cb)
    result.stages.append(s3)

    result.total_duration_ms = (time.perf_counter() - pipeline_t0) * 1000
    result.success = s3.success
    result.primers = s3.data.get("primers", []) if s3.success else []

    return result
