# core/assembly_planner.py
"""
Gibson Assembly primer planner.

Primer structure (standard two-region design)
----------------------------------------------
For an interior fragment i with left neighbour (i-1) and right neighbour (i+1):

  Forward primer:
    [5' homology arm = last <overlap_len> bp of fragment i-1]
    + [3' annealing region = first N bp of fragment i, where N is chosen so
       Tm(annealing region) is close to target_tm]

  Reverse primer:
    [5' homology arm = RC of first <overlap_len> bp of fragment i+1]
    + [3' annealing region = RC of last N bp of fragment i, where N is chosen
       so Tm(annealing region) is close to target_tm]

For the first fragment the forward homology arm is empty (no upstream neighbour).
For the last fragment the reverse homology arm is empty (no downstream neighbour).

All Tm calculations use calc_tm() from core.primer_utils, which cascades
through primer3-py, then Biopython, then a Wallace-rule fallback.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import product


HIGH_RISK_WARNING_MARKERS = (
    "High 3' complementarity risk",
    "High cross-dimer risk",
    "Heterodimer thermodynamic risk",
)

MODERATE_RISK_WARNING_MARKERS = (
    "Moderate 3' complementarity risk",
    "Moderate cross-dimer risk",
    "overlap GC out of preferred range",
    "overlap contains poly-",
    "overlap may be non-unique",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def _calc_tm(seq: str) -> float:
    """Return Tm in deg C for *seq* using the best available backend."""
    try:
        from core.primer_utils import calc_tm
        return calc_tm(seq)
    except Exception:
        # Wallace-rule inline fallback so this module is always importable
        s = seq.upper()
        gc = (s.count("G") + s.count("C")) / len(s) if s else 0.0
        return round(2 * (len(s) - gc * len(s)) + 4 * gc * len(s), 1) if s else 0.0


def _rc(sequence: str) -> str:
    """Return the reverse complement of *sequence*."""
    complement = {"A": "T", "T": "A", "C": "G", "G": "C"}
    return "".join(complement.get(b, b) for b in reversed(sequence.upper()))


def _calc_gc(sequence: str) -> float:
    s = sequence.upper()
    return (s.count("G") + s.count("C")) / len(s) * 100 if s else 0.0


def _pick_annealing_region(
    seq: str,
    target_tm: float,
    min_len: int = 15,
    max_len: int = 35,
    from_end: bool = False,
) -> str:
    """
    Walk outward from the appropriate end of *seq* until the Tm of the
    chosen sub-sequence is within 1 deg C of *target_tm*, or until *max_len*
    is reached.
    """
    if not seq:
        return ""

    best_seq = seq[:min_len] if not from_end else seq[-min_len:]
    best_diff = abs(_calc_tm(best_seq) - target_tm)

    for length in range(min_len, min(max_len + 1, len(seq) + 1)):
        candidate = seq[:length] if not from_end else seq[-length:]
        cand_tm = _calc_tm(candidate)
        diff = abs(cand_tm - target_tm)
        if diff < best_diff:
            best_diff = diff
            best_seq = candidate
        # Stop early once Tm overshoots target by more than 2 deg C.
        if cand_tm > target_tm + 2.0:
            break

    return best_seq


def _max_3prime_complementarity(fwd: str, rev: str, max_len: int = 10) -> int:
    """Return max 3'-to-3' complementarity length between two primers."""
    a = fwd.upper()
    b = rev.upper()
    upper = min(max_len, len(a), len(b))
    for k in range(upper, 2, -1):
        if a[-k:] == _rc(b[-k:]):
            return k
    return 0


def _max_cross_complementarity(fwd: str, rev: str, min_k: int = 5, max_k: int = 10) -> int:
    """Return longest complementary k-mer between primers (global scan)."""
    a = fwd.upper()
    brc = _rc(rev.upper())
    upper = min(max_k, len(a), len(brc))
    for k in range(upper, min_k - 1, -1):
        kmers = {a[i:i + k] for i in range(0, len(a) - k + 1)}
        for j in range(0, len(brc) - k + 1):
            if brc[j:j + k] in kmers:
                return k
    return 0


def _homology_warnings(arm_seq: str, full_seq: str, label: str) -> list[str]:
    """Return warnings for weak/non-unique homology arms."""
    warnings: list[str] = []
    if not arm_seq:
        return warnings

    s = arm_seq.upper()
    gc = _calc_gc(s)
    if gc < 25.0 or gc > 75.0:
        warnings.append(f"{label} overlap GC out of preferred range ({gc:.1f}%).")

    for base in "ATCG":
        if base * 5 in s:
            warnings.append(f"{label} overlap contains poly-{base} run (>=5).")
            break

    # uniqueness in assembled construct
    if full_seq:
        occ_fwd = full_seq.count(s)
        occ_rev = full_seq.count(_rc(s))
        occ = max(occ_fwd, occ_rev)
        if occ > 1:
            warnings.append(
                f"{label} overlap may be non-unique in construct ({occ} matches)."
            )

    return warnings


def _pair_warnings(fwd_primer: str, rev_primer: str) -> list[str]:
    """Return primer-pair interaction warnings (cross-dimer / 3' complementarity)."""
    warnings: list[str] = []

    k3 = _max_3prime_complementarity(fwd_primer, rev_primer)
    if k3 >= 6:
        warnings.append(f"High 3' complementarity risk between primers ({k3} bp).")
    elif k3 >= 4:
        warnings.append(f"Moderate 3' complementarity risk between primers ({k3} bp).")

    kx = _max_cross_complementarity(fwd_primer, rev_primer)
    if kx >= 8:
        warnings.append(f"High cross-dimer risk between primers ({kx} bp complementarity).")
    elif kx >= 6:
        warnings.append(f"Moderate cross-dimer risk between primers ({kx} bp complementarity).")

    try:
        import primer3

        hd = primer3.calc_heterodimer(fwd_primer, rev_primer)
        if getattr(hd, "dg", 0) < -6000:
            warnings.append(f"Heterodimer thermodynamic risk (dG={hd.dg/1000:.1f} kcal/mol).")
    except Exception:
        pass

    return warnings


def _grade_primer_pair(
    *,
    fwd_primer: str,
    rev_primer: str,
    fwd_tm: float,
    rev_tm: float,
    target_tm: float,
    warnings: list[str],
) -> tuple[str, list[str]]:
    """Return quality grade and short reasons for one Gibson primer pair."""
    reasons: list[str] = []
    grade = "Recommended"

    high_risk_warnings = [
        warning for warning in warnings
        if any(marker in warning for marker in HIGH_RISK_WARNING_MARKERS)
    ]
    moderate_risk_warnings = [
        warning for warning in warnings
        if any(marker in warning for marker in MODERATE_RISK_WARNING_MARKERS)
    ]

    fwd_len = len(fwd_primer)
    rev_len = len(rev_primer)
    fwd_gc = _calc_gc(fwd_primer)
    rev_gc = _calc_gc(rev_primer)
    max_tm_delta = max(abs(fwd_tm - target_tm), abs(rev_tm - target_tm))
    tm_gap = abs(fwd_tm - rev_tm)

    if high_risk_warnings:
        grade = "Not Recommended"
        reasons.extend(high_risk_warnings)

    if fwd_len < 15 or rev_len < 15 or fwd_len > 45 or rev_len > 45:
        if grade != "Not Recommended":
            grade = "Not Recommended"
        reasons.append(
            f"Primer length outside hard limit (Fwd {fwd_len} bp, Rev {rev_len} bp)."
        )

    if max_tm_delta > 5.0:
        if grade != "Not Recommended":
            grade = "Not Recommended"
        reasons.append(
            f"Annealing Tm deviates strongly from target ({target_tm:.1f}°C)."
        )

    if tm_gap > 5.0:
        if grade != "Not Recommended":
            grade = "Not Recommended"
        reasons.append(f"Forward/reverse annealing Tm gap is large ({tm_gap:.1f}°C).")

    if grade == "Recommended":
        if moderate_risk_warnings:
            grade = "Usable with Risk"
            reasons.extend(moderate_risk_warnings)

        if fwd_len < 18 or rev_len < 18 or fwd_len > 40 or rev_len > 40:
            grade = "Usable with Risk"
            reasons.append(
                f"Primer length is outside preferred range (Fwd {fwd_len} bp, Rev {rev_len} bp)."
            )

        gc_out_of_range = []
        if fwd_gc < 35.0 or fwd_gc > 65.0:
            gc_out_of_range.append(f"Fwd GC {fwd_gc:.1f}%")
        if rev_gc < 35.0 or rev_gc > 65.0:
            gc_out_of_range.append(f"Rev GC {rev_gc:.1f}%")
        if gc_out_of_range:
            grade = "Usable with Risk"
            reasons.append("GC content outside preferred range (" + ", ".join(gc_out_of_range) + ").")

        if max_tm_delta > 2.0:
            grade = "Usable with Risk"
            reasons.append(
                f"Annealing Tm is slightly offset from target ({target_tm:.1f}°C)."
            )

        if tm_gap > 3.0:
            grade = "Usable with Risk"
            reasons.append(f"Forward/reverse annealing Tm gap is elevated ({tm_gap:.1f}°C).")

    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)

    if not deduped_reasons:
        deduped_reasons.append("No major warning triggered; key primer metrics are within preferred range.")

    return grade, deduped_reasons[:3]


def _iter_candidate_values(selected: int | float, lower: int | float, upper: int | float) -> list[int | float]:
    """Return centered candidate values around the selected point."""
    candidates = [selected - 2, selected, selected + 2]
    deduped: list[int | float] = []
    for value in candidates:
        clamped = max(lower, min(upper, value))
        if clamped not in deduped:
            deduped.append(clamped)
    return deduped


def _summarize_plan_quality(plan: dict) -> dict:
    """Build sortable quality metrics for a full Gibson plan."""
    primers = plan.get("primers") or []
    recommended = sum(1 for primer in primers if primer.get("Quality Grade") == "Recommended")
    usable_with_risk = sum(1 for primer in primers if primer.get("Quality Grade") == "Usable with Risk")
    not_recommended = sum(1 for primer in primers if primer.get("Quality Grade") == "Not Recommended")

    high_risk_count = 0
    moderate_risk_count = 0
    tm_delta_sum = 0.0
    tm_gap_sum = 0.0
    target_tm = float(plan.get("parameters", {}).get("target_tm", 0.0) or 0.0)

    for primer in primers:
        warnings = primer.get("Warnings") or []
        high_risk_count += sum(
            1 for warning in warnings
            if any(marker in warning for marker in HIGH_RISK_WARNING_MARKERS)
        )
        moderate_risk_count += sum(
            1 for warning in warnings
            if any(marker in warning for marker in MODERATE_RISK_WARNING_MARKERS)
        )

        fwd_tm = float(primer.get("Fwd Anneal Tm (°C)", 0.0) or 0.0)
        rev_tm = float(primer.get("Rev Anneal Tm (°C)", 0.0) or 0.0)
        tm_delta_sum += abs(fwd_tm - target_tm) + abs(rev_tm - target_tm)
        tm_gap_sum += abs(fwd_tm - rev_tm)

    return {
        "recommended": recommended,
        "usable_with_risk": usable_with_risk,
        "not_recommended": not_recommended,
        "high_risk_warning_count": high_risk_count,
        "moderate_risk_warning_count": moderate_risk_count,
        "tm_delta_sum": round(tm_delta_sum, 2),
        "tm_gap_sum": round(tm_gap_sum, 2),
    }


def _plan_sort_key(plan: dict) -> tuple:
    """Return the deterministic sort key for full-plan ranking."""
    summary = _summarize_plan_quality(plan)
    return (
        summary["not_recommended"],
        -summary["recommended"],
        summary["usable_with_risk"],
        summary["high_risk_warning_count"],
        summary["moderate_risk_warning_count"],
        summary["tm_delta_sum"],
        summary["tm_gap_sum"],
        int(plan.get("parameters", {}).get("overlap_len", 0) or 0),
        float(plan.get("parameters", {}).get("target_tm", 0.0) or 0.0),
    )


def _build_best_plan_summary(plan: dict) -> str:
    """Return a compact human-readable summary for the selected best plan."""
    summary = _summarize_plan_quality(plan)
    return (
        f"Selected the plan with {summary['not_recommended']} Not Recommended, "
        f"{summary['usable_with_risk']} Usable with Risk, and "
        f"{summary['recommended']} Recommended primer pair(s)."
    )


# ---------------------------------------------------------------------------
# Public planner
# ---------------------------------------------------------------------------

class AssemblyPlanner:
    """Cloning strategy engine for Gibson Assembly primer planning."""

    def search_best_gibson_assembly_plan(
        self,
        construct_result: dict,
        overlap_len: int = 20,
        target_tm: float = 60.0,
    ) -> dict:
        """Try nearby parameter combinations and return the current best full plan."""
        overlap_candidates = [
            int(value) for value in _iter_candidate_values(int(overlap_len), 15, 40)
        ]
        tm_candidates = [
            float(value) for value in _iter_candidate_values(float(target_tm), 55.0, 68.0)
        ]

        candidate_plans: list[dict] = []
        for overlap_candidate, tm_candidate in product(overlap_candidates, tm_candidates):
            candidate_plan = self.plan_gibson_assembly(
                construct_result=construct_result,
                overlap_len=int(overlap_candidate),
                target_tm=float(tm_candidate),
            )
            candidate_plan["quality_summary"] = _summarize_plan_quality(candidate_plan)
            candidate_plans.append(candidate_plan)

        if not candidate_plans:
            fallback_plan = self.plan_gibson_assembly(
                construct_result=construct_result,
                overlap_len=int(overlap_len),
                target_tm=float(target_tm),
            )
            fallback_plan["quality_summary"] = _summarize_plan_quality(fallback_plan)
            fallback_plan["selected_overlap_len"] = int(overlap_len)
            fallback_plan["selected_target_tm"] = float(target_tm)
            fallback_plan["tried_combinations"] = 1
            fallback_plan["best_plan_summary"] = _build_best_plan_summary(fallback_plan)
            return fallback_plan

        ranked_plans = sorted(candidate_plans, key=_plan_sort_key)
        best_plan = ranked_plans[0]
        best_plan["selected_overlap_len"] = int(best_plan.get("parameters", {}).get("overlap_len", overlap_len))
        best_plan["selected_target_tm"] = float(best_plan.get("parameters", {}).get("target_tm", target_tm))
        best_plan["tried_combinations"] = len(candidate_plans)
        best_plan["best_plan_summary"] = _build_best_plan_summary(best_plan)
        best_plan["candidate_summaries"] = [
            {
                "rank": rank,
                "overlap_len": int(plan.get("parameters", {}).get("overlap_len", overlap_len) or overlap_len),
                "target_tm": float(plan.get("parameters", {}).get("target_tm", target_tm) or target_tm),
                **(plan.get("quality_summary") or _summarize_plan_quality(plan)),
            }
            for rank, plan in enumerate(ranked_plans, start=1)
        ]
        return best_plan

    def plan_gibson_assembly(
        self,
        construct_result: dict,
        overlap_len: int = 20,
        target_tm: float = 60.0,
    ) -> dict:
        """
        Design two-region Gibson Assembly primers for a linear construct.
        """
        features = construct_result.get("features", [])
        full_seq = construct_result.get("final_sequence", "")

        plan: dict = {
            "method": "Gibson Assembly (linear)",
            "parameters": {
                "overlap_len": int(overlap_len),
                "target_tm": float(target_tm),
            },
            "primers": [],
            "warnings": [],
        }

        if len(features) < 2 or not full_seq:
            reason = "Construct requires at least 2 annotated features and a final sequence."
            plan["warnings"].append(reason)
            plan["reason"] = reason
            return plan

        for i, feat in enumerate(features):
            # Convert 1-based inclusive coordinates to 0-based Python slice
            frag_start = feat["start"] - 1          # inclusive
            frag_end = feat["end"]                  # exclusive in slice
            fragment_seq = full_seq[frag_start:frag_end]

            if not fragment_seq:
                continue

            # ------------------------------------------------------------------
            # Forward primer
            # ------------------------------------------------------------------
            fwd_anneal = _pick_annealing_region(
                fragment_seq,
                target_tm=target_tm,
                from_end=False,
            )
            fwd_anneal_tm = _calc_tm(fwd_anneal)

            if i == 0:
                fwd_arm = ""
            else:
                prev_end = features[i - 1]["end"]
                prev_start = max(features[i - 1]["start"] - 1, prev_end - overlap_len)
                fwd_arm = full_seq[prev_start:prev_end]

            fwd_primer = fwd_arm + fwd_anneal

            # ------------------------------------------------------------------
            # Reverse primer
            # ------------------------------------------------------------------
            rev_anneal_template = _pick_annealing_region(
                fragment_seq,
                target_tm=target_tm,
                from_end=True,
            )
            rev_anneal = _rc(rev_anneal_template)
            rev_anneal_tm = _calc_tm(rev_anneal_template)

            if i == len(features) - 1:
                rev_arm = ""
            else:
                next_feat = features[i + 1]
                next_start = next_feat["start"] - 1
                next_end = min(next_feat["end"], next_start + overlap_len)
                rev_arm = _rc(full_seq[next_start:next_end])

            rev_primer = rev_arm + rev_anneal

            pair_warnings = _pair_warnings(fwd_primer, rev_primer)
            pair_warnings.extend(_homology_warnings(fwd_arm, full_seq, "Forward"))
            pair_warnings.extend(_homology_warnings(_rc(rev_arm), full_seq, "Reverse"))
            quality_grade, quality_reasons = _grade_primer_pair(
                fwd_primer=fwd_primer,
                rev_primer=rev_primer,
                fwd_tm=round(fwd_anneal_tm, 1),
                rev_tm=round(rev_anneal_tm, 1),
                target_tm=float(target_tm),
                warnings=pair_warnings,
            )

            plan["primers"].append({
                "Fragment Name": feat["name"],
                "Forward Primer (5'->3')": fwd_primer,
                "Reverse Primer (5'->3')": rev_primer,
                "Fwd Arm (bp)": len(fwd_arm),
                "Rev Arm (bp)": len(rev_arm),
                "Fwd Anneal Tm (°C)": round(fwd_anneal_tm, 1),
                "Rev Anneal Tm (°C)": round(rev_anneal_tm, 1),
                "Warnings": pair_warnings,
                "Quality Grade": quality_grade,
                "Quality Reasons": quality_reasons,
            })

            if pair_warnings:
                plan["warnings"].append(
                    f"{feat['name']}: " + " | ".join(pair_warnings)
                )

        if not plan["primers"]:
            reason = "No valid fragment sequence was available to build primer pairs."
            plan["warnings"].append(reason)
            plan["reason"] = reason

        return plan
