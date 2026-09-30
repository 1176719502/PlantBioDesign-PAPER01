"""
core/primer_utils.py
~~~~~~~~~~~~~~~~~~~~
Professional primer design utilities.

Backends (in priority order):
  1. primer3-py  — industry standard, SantaLucia 1998 NN thermodynamics
  2. Biopython MeltingTemp — fallback
  3. Wallace rule — final fallback

Exports:
    calc_tm(seq, na_mm, mg_mm, dntp_mm, dna_conc_nm) -> float
    calc_gc(seq) -> float
    check_primer_issues(seq) -> list
    design_primers(template, target_tm, tm_tol, min_len, max_len) -> dict
    design_outer_primers(template, target_tm, tm_tol, min_len, max_len) -> dict
    get_restriction_enzymes() -> dict
"""
from __future__ import annotations
import importlib
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType
from typing import Optional

from utils.sequence_utils import compute_gc

logger = logging.getLogger(__name__)

_PRIMER3_BACKEND: ModuleType | None = None
_PRIMER3_BACKEND_ERROR = ""


@dataclass(frozen=True)
class Primer3BackendStatus:
    available: bool
    reason: str


def _native_primer3_import_enabled() -> bool:
    value = os.environ.get("BIODESIGN_ENABLE_NATIVE_PRIMER3", "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if os.name == "nt":
        return False
    return value not in {"0", "false", "no", "off"}


def _load_primer3_backend() -> ModuleType | None:
    global _PRIMER3_BACKEND, _PRIMER3_BACKEND_ERROR
    if _PRIMER3_BACKEND is not None:
        return _PRIMER3_BACKEND
    if not _native_primer3_import_enabled():
        _PRIMER3_BACKEND_ERROR = (
            "Native primer3 import is disabled in this Windows environment."
        )
        return None
    try:
        _PRIMER3_BACKEND = importlib.import_module("primer3")
        _PRIMER3_BACKEND_ERROR = ""
        return _PRIMER3_BACKEND
    except Exception as exc:
        _PRIMER3_BACKEND_ERROR = str(exc) or exc.__class__.__name__
        return None


def get_primer3_backend_status(*, probe: bool = False) -> Primer3BackendStatus:
    """Return primer3 backend status without importing it unless probe=True."""
    if _PRIMER3_BACKEND is not None:
        return Primer3BackendStatus(True, "")
    if not _native_primer3_import_enabled():
        return Primer3BackendStatus(
            False,
            "Primer design engine is unavailable in this environment. You can continue reviewing documentation fields.",
        )
    if not probe:
        return Primer3BackendStatus(
            True,
            "Primer design engine has not been loaded for this page render.",
        )
    backend = _load_primer3_backend()
    if backend is not None:
        return Primer3BackendStatus(True, "")
    return Primer3BackendStatus(
        False,
        _PRIMER3_BACKEND_ERROR
        or "Primer design engine is unavailable in this environment. You can continue reviewing documentation fields.",
    )

try:
    from Bio.SeqUtils.MeltingTemp import Tm_NN
    _BIO_OK = True
except ImportError:
    _BIO_OK = False


def calc_gc(seq: str) -> float:
    return compute_gc(seq.upper().replace(" ", ""))


def calc_tm(
    seq: str,
    na_mm: float = 50.0,
    mg_mm: float = 2.0,
    dntp_mm: float = 0.2,
    dna_conc_nm: float = 250.0,
) -> float:
    """Calculate melting temperature using primer3-py > Biopython > Wallace rule."""
    s = "".join(c for c in seq.upper() if c in "ATCG")
    if len(s) < 5:
        return 0.0

    primer3 = _load_primer3_backend()
    if primer3 is not None:
        try:
            tm = primer3.calc_tm(
                s, mv_conc=na_mm, dv_conc=mg_mm,
                dntp_conc=dntp_mm, dna_conc=dna_conc_nm,
            )
            return round(float(tm), 1)
        except Exception:
            pass

    if _BIO_OK:
        try:
            from Bio.Seq import Seq
            tm = Tm_NN(Seq(s), Na=na_mm, Mg=mg_mm, dNTPs=dntp_mm,
                       dnac1=dna_conc_nm, dnac2=0)
            return round(float(tm), 1)
        except Exception:
            pass

    # Wallace rule fallback
    gc = calc_gc(s)
    return round(2 * ((100 - gc) * len(s) / 100) + 4 * (gc * len(s) / 100), 1)


def check_primer_issues(seq: str) -> list:
    """Return list of warning strings for common primer design problems."""
    s = seq.upper().replace(" ", "")
    issues = []
    if len(s) < 15:
        issues.append(f"Too short ({len(s)} bp, recommended >= 18 bp)")
    elif len(s) > 35:
        issues.append(f"Too long ({len(s)} bp, recommended <= 30 bp)")
    gc = calc_gc(s)
    if gc < 35:
        issues.append(f"Low GC ({gc:.1f}%, recommended 40-60%)")
    elif gc > 65:
        issues.append(f"High GC ({gc:.1f}%, recommended 40-60%)")
    tail_gc = s[-5:].count("G") + s[-5:].count("C")
    if tail_gc == 0:
        issues.append("No G/C at 3' end — weak extension")
    elif tail_gc >= 4:
        issues.append("Strong GC clamp (>=4 G/C in last 5 bp) — mispriming risk")
    for base in "ATCG":
        if base * 4 in s:
            issues.append(f"Poly-{base} run (>=4) — slippage risk")
    primer3 = _load_primer3_backend()
    if primer3 is not None and len(s) >= 10:
        try:
            hp = primer3.calc_hairpin(s)
            if hp.dg < -2000:
                issues.append(f"Hairpin structure risk (dG={hp.dg/1000:.1f} kcal/mol)")
        except Exception:
            pass
        try:
            sd = primer3.calc_homodimer(s)
            if sd.dg < -6000:
                issues.append(f"Self-dimerization risk (dG={sd.dg/1000:.1f} kcal/mol)")
        except Exception:
            pass
    return issues


def _reverse_complement(seq: str) -> str:
    return seq.translate(str.maketrans("ATCG", "TAGC"))[::-1]


def _normalize_primer3_dg(dg_value) -> float | None:
    if dg_value is None:
        return None
    try:
        value = float(dg_value)
    except (TypeError, ValueError):
        return None
    if abs(value) > 100:
        value = value / 1000.0
    return round(value, 2)


def _risk_penalty_for_dg(dg_value: float | None, *, high_cutoff: float, moderate_cutoff: float) -> int:
    if dg_value is None:
        return 8
    if dg_value <= high_cutoff:
        return 30
    if dg_value <= moderate_cutoff:
        return 15
    return 0


@lru_cache(maxsize=512)
def _cached_primer_structure_penalty(seq: str) -> int:
    penalty = 0
    primer3 = _load_primer3_backend()
    if primer3 is not None and len(seq) >= 10:
        try:
            hp = primer3.calc_hairpin(seq)
            penalty += _risk_penalty_for_dg(
                _normalize_primer3_dg(getattr(hp, "dg", None)),
                high_cutoff=-4.0,
                moderate_cutoff=-2.0,
            )
        except Exception:
            penalty += 8
        try:
            sd = primer3.calc_homodimer(seq)
            penalty += _risk_penalty_for_dg(
                _normalize_primer3_dg(getattr(sd, "dg", None)),
                high_cutoff=-6.0,
                moderate_cutoff=-3.0,
            )
        except Exception:
            penalty += 8
    return penalty


def _primer_structure_penalty(seq: str) -> int:
    return _cached_primer_structure_penalty(seq)


@lru_cache(maxsize=2048)
def _cached_heterodimer_structure_penalty(fwd_seq: str, rev_seq: str) -> int:
    primer3 = _load_primer3_backend()
    if primer3 is None:
        return 0
    try:
        hd = primer3.calc_heterodimer(fwd_seq, rev_seq)
        return _risk_penalty_for_dg(
            _normalize_primer3_dg(getattr(hd, "dg", None)),
            high_cutoff=-6.0,
            moderate_cutoff=-3.0,
        )
    except Exception:
        return 8


def _heterodimer_structure_penalty(fwd_seq: str, rev_seq: str) -> int:
    return _cached_heterodimer_structure_penalty(fwd_seq, rev_seq)


def _gc_preferred_distance(seq: str) -> float:
    gc = calc_gc(seq)
    if 40.0 <= gc <= 60.0:
        return 0.0
    if gc < 40.0:
        return round(40.0 - gc, 2)
    return round(gc - 60.0, 2)


def _candidate_issue_count(candidate: dict) -> int:
    return len(candidate.get("issues") or check_primer_issues(candidate["seq"]))


def _gc_soft_penalty(seq: str) -> float:
    gc = calc_gc(seq)
    if gc < 30.0:
        return round((30.0 - gc) * 2.0 + 10.0, 2)
    if gc < 35.0:
        return round(35.0 - gc, 2)
    if gc > 70.0:
        return round((gc - 70.0) * 2.0 + 10.0, 2)
    if gc > 65.0:
        return round(gc - 65.0, 2)
    return 0.0


def _candidate_rank_metrics(pair: dict, target_tm: float, include_thermodynamics: bool = True) -> dict:
    fwd = pair["forward"]
    rev = pair["reverse"]
    fwd_seq = fwd["seq"]
    rev_seq = rev["seq"]
    fwd_tm = float(fwd.get("tm", calc_tm(fwd_seq)) or 0.0)
    rev_tm = float(rev.get("tm", calc_tm(rev_seq)) or 0.0)
    fwd_gc = float(fwd.get("gc", calc_gc(fwd_seq)) or 0.0)
    rev_gc = float(rev.get("gc", calc_gc(rev_seq)) or 0.0)
    fwd_issues = fwd.get("issues") or check_primer_issues(fwd_seq)
    rev_issues = rev.get("issues") or check_primer_issues(rev_seq)
    warnings = pair.get("warnings") or []
    max_tm_deviation = max(abs(fwd_tm - target_tm), abs(rev_tm - target_tm))
    tm_gap = abs(fwd_tm - rev_tm)
    gc_distance = _gc_preferred_distance(fwd_seq) + _gc_preferred_distance(rev_seq)
    gc_balance_gap = abs(fwd_gc - rev_gc)
    structure_penalty = 0
    if include_thermodynamics:
        structure_penalty = (
            _primer_structure_penalty(fwd_seq)
            + _primer_structure_penalty(rev_seq)
            + _heterodimer_structure_penalty(fwd_seq, rev_seq)
        )
    issue_count = len(fwd_issues) + len(rev_issues) + len(warnings)
    total_length = len(fwd_seq) + len(rev_seq)
    length_balance_gap = abs(len(fwd_seq) - len(rev_seq))
    return {
        "max_tm_deviation": round(max_tm_deviation, 2),
        "tm_gap": round(tm_gap, 2),
        "gc_distance": round(gc_distance, 2),
        "gc_balance_gap": round(gc_balance_gap, 2),
        "gc_soft_penalty": round(_gc_soft_penalty(fwd_seq) + _gc_soft_penalty(rev_seq), 2),
        "structure_penalty": structure_penalty,
        "issue_count": issue_count,
        "total_length": total_length,
        "length_balance_gap": length_balance_gap,
    }


def _outer_pair_rank_key(pair: dict, target_tm: float, include_thermodynamics: bool = True) -> tuple:
    metrics = _candidate_rank_metrics(pair, target_tm, include_thermodynamics=include_thermodynamics)
    return (
        metrics["max_tm_deviation"],
        metrics["tm_gap"],
        metrics["gc_distance"],
        metrics["gc_balance_gap"],
        metrics["gc_soft_penalty"],
        metrics["issue_count"],
        metrics["structure_penalty"],
        metrics["length_balance_gap"],
        metrics["total_length"],
    )


def _make_primer_candidate(seq: str) -> dict:
    return {
        "seq": seq,
        "tm": calc_tm(seq),
        "gc": round(calc_gc(seq), 1),
        "length": len(seq),
        "issues": check_primer_issues(seq),
    }


def _build_outer_pair(
    *,
    fwd: dict,
    rev: dict,
    product_size: int,
    backend: str,
    warnings: list[str] | None = None,
) -> dict:
    rev_len = len(rev["seq"])
    pair_warnings = list(warnings or [])
    tm_gap = abs(float(fwd.get("tm", 0.0) or 0.0) - float(rev.get("tm", 0.0) or 0.0))
    if tm_gap > 5:
        pair_warnings.append(f"Large Tm difference ({tm_gap:.1f}°C)")
    return {
        "forward": fwd,
        "reverse": rev,
        "product_size": product_size,
        "forward_start": 0,
        "reverse_start": product_size - rev_len,
        "product_start": 0,
        "product_end": product_size,
        "warnings": list(dict.fromkeys(pair_warnings)),
        "backend": backend,
    }


def _outer_pair_quality_warnings(pair: dict, target_tm: float) -> list[str]:
    fwd = pair["forward"]
    rev = pair["reverse"]
    warnings = list(pair.get("warnings") or [])
    max_tm_deviation = max(
        abs(float(fwd.get("tm", 0.0) or 0.0) - target_tm),
        abs(float(rev.get("tm", 0.0) or 0.0) - target_tm),
    )
    tm_gap = abs(float(fwd.get("tm", 0.0) or 0.0) - float(rev.get("tm", 0.0) or 0.0))
    gc_gap = abs(float(fwd.get("gc", 0.0) or 0.0) - float(rev.get("gc", 0.0) or 0.0))

    if max_tm_deviation > 3.0:
        warnings.append(f"Primer Tm deviates from target by {max_tm_deviation:.1f}°C.")
    if tm_gap > 3.0:
        warnings.append(f"Forward/reverse Tm gap is {tm_gap:.1f}°C.")
    if gc_gap > 20.0:
        warnings.append(f"Forward/reverse GC balance gap is {gc_gap:.1f}%.")
    for label, primer in (("Forward", fwd), ("Reverse", rev)):
        gc = float(primer.get("gc", 0.0) or 0.0)
        if gc < 35.0:
            warnings.append(f"{label} primer has low GC content ({gc:.1f}%).")
        elif gc > 65.0:
            warnings.append(f"{label} primer has high GC content ({gc:.1f}%).")
    return list(dict.fromkeys(warnings))


def _annotate_outer_pair(pair: dict, target_tm: float) -> dict:
    annotated = dict(pair)
    annotated["warnings"] = _outer_pair_quality_warnings(annotated, target_tm)
    annotated["rank_metrics"] = _candidate_rank_metrics(annotated, target_tm, include_thermodynamics=True)
    return annotated


def _manual_outer_primers(
    s: str,
    *,
    target_tm: float,
    min_len: int,
    max_len: int,
) -> dict:
    product_size = len(s)
    bounded_max_len = min(max_len, product_size)
    if product_size <= 120:
        search_max_len = min(product_size, max(bounded_max_len, min_len + 18, 42))
    else:
        search_max_len = min(product_size, max(bounded_max_len, min_len + 10, 34))
    search_min_len = min(min_len, search_max_len)

    forward_candidates = [
        _make_primer_candidate(s[:length])
        for length in range(search_min_len, search_max_len + 1)
    ]
    reverse_source = _reverse_complement(s)
    reverse_candidates = [
        _make_primer_candidate(reverse_source[:length])
        for length in range(search_min_len, search_max_len + 1)
    ]

    pair_candidates = [
        _annotate_outer_pair(
            _build_outer_pair(
                fwd=fwd,
                rev=rev,
                product_size=product_size,
                backend="edge-window",
            ),
            target_tm,
        )
        for fwd in forward_candidates
        for rev in reverse_candidates
    ]
    if not pair_candidates:
        return {"error": "Could not design full-cassette outer primers"}

    pair_candidates.sort(key=lambda pair: _outer_pair_rank_key(pair, target_tm, include_thermodynamics=False))
    finalist_count = min(16 if product_size <= 120 else 12, len(pair_candidates))
    finalists = pair_candidates[:finalist_count]
    finalists.sort(key=lambda pair: _outer_pair_rank_key(pair, target_tm, include_thermodynamics=True))
    return finalists[0]


def _primer3_outer_pair_from_result(result: dict, pair_index: int, product_size: int) -> dict | None:
    left_key = f"PRIMER_LEFT_{pair_index}"
    right_key = f"PRIMER_RIGHT_{pair_index}"
    pair_size_key = f"PRIMER_PAIR_{pair_index}_PRODUCT_SIZE"
    fwd_seq_key = f"PRIMER_LEFT_{pair_index}_SEQUENCE"
    rev_seq_key = f"PRIMER_RIGHT_{pair_index}_SEQUENCE"
    fwd_tm_key = f"PRIMER_LEFT_{pair_index}_TM"
    rev_tm_key = f"PRIMER_RIGHT_{pair_index}_TM"
    fwd_gc_key = f"PRIMER_LEFT_{pair_index}_GC_PERCENT"
    rev_gc_key = f"PRIMER_RIGHT_{pair_index}_GC_PERCENT"

    if fwd_seq_key not in result or rev_seq_key not in result:
        return None

    fwd_seq = result[fwd_seq_key]
    rev_seq = result[rev_seq_key]
    left = result.get(left_key, [0, len(fwd_seq)])
    right = result.get(right_key, [product_size - 1, len(rev_seq)])
    forward_start = int(left[0])
    reverse_end = int(right[0]) + 1
    reverse_start = reverse_end - len(rev_seq)
    reported_size = int(result.get(pair_size_key, 0) or 0)
    product_start = forward_start
    product_end = reverse_end

    if reported_size != product_size:
        return None
    if product_start != 0 or product_end != product_size:
        return None
    if forward_start != 0 or reverse_start != product_size - len(rev_seq):
        return None

    fwd = {
        "seq": fwd_seq,
        "tm": round(float(result.get(fwd_tm_key, calc_tm(fwd_seq))), 1),
        "gc": round(float(result.get(fwd_gc_key, calc_gc(fwd_seq))), 1),
        "length": len(fwd_seq),
        "issues": check_primer_issues(fwd_seq),
    }
    rev = {
        "seq": rev_seq,
        "tm": round(float(result.get(rev_tm_key, calc_tm(rev_seq))), 1),
        "gc": round(float(result.get(rev_gc_key, calc_gc(rev_seq))), 1),
        "length": len(rev_seq),
        "issues": check_primer_issues(rev_seq),
    }
    return {
        "forward": fwd,
        "reverse": rev,
        "product_size": reported_size,
        "forward_start": forward_start,
        "reverse_start": reverse_start,
        "product_start": product_start,
        "product_end": product_end,
        "warnings": [],
        "backend": "primer3-py-outer",
    }


def design_outer_primers(
    template: str,
    target_tm: float = 60.0,
    tm_tol: float = 2.0,
    min_len: int = 18,
    max_len: int = 30,
) -> dict:
    """Design edge-anchored primers for the complete template sequence."""
    s = "".join(c for c in template.upper() if c in "ATCG")
    if len(s) < 40:
        return {"error": "Template too short (minimum 40 bp)"}

    primer3 = _load_primer3_backend()
    if primer3 is not None and len(s) >= 100:
        try:
            product_size = len(s)
            result = primer3.design_primers(
                seq_args={
                    "SEQUENCE_ID": "full_cassette_template",
                    "SEQUENCE_TEMPLATE": s,
                    "SEQUENCE_INCLUDED_REGION": [0, product_size],
                },
                global_args={
                    "PRIMER_OPT_TM": target_tm,
                    "PRIMER_MIN_TM": target_tm - tm_tol,
                    "PRIMER_MAX_TM": target_tm + tm_tol,
                    "PRIMER_MIN_SIZE": min_len,
                    "PRIMER_MAX_SIZE": max_len,
                    "PRIMER_OPT_SIZE": 20,
                    "PRIMER_MIN_GC": 35.0,
                    "PRIMER_MAX_GC": 65.0,
                    "PRIMER_MAX_POLY_X": 3,
                    "PRIMER_PRODUCT_SIZE_RANGE": [[product_size, product_size]],
                    "PRIMER_NUM_RETURN": 5,
                },
            )
            pair_count = int(result.get("PRIMER_PAIR_NUM_RETURNED", 0) or 0)
            primer3_candidates = [
                candidate
                for index in range(pair_count)
                if (candidate := _primer3_outer_pair_from_result(result, index, product_size)) is not None
            ]
            if primer3_candidates:
                primer3_candidates = [
                    _annotate_outer_pair(candidate, target_tm)
                    for candidate in primer3_candidates
                ]
                primer3_candidates.sort(key=lambda pair: _outer_pair_rank_key(pair, target_tm))
                return primer3_candidates[0]
        except Exception as e:
            logger.debug("primer3 design_outer_primers failed: %s", e)

    return _manual_outer_primers(s, target_tm=target_tm, min_len=min_len, max_len=max_len)


def design_primers(
    template: str,
    target_tm: float = 60.0,
    tm_tol: float = 2.0,
    min_len: int = 18,
    max_len: int = 30,
) -> dict:
    """Design forward and reverse primers for a template sequence."""
    s = "".join(c for c in template.upper() if c in "ATCG")
    if len(s) < 40:
        return {"error": "Template too short (minimum 40 bp)"}

    # Use primer3-py full design when possible
    primer3 = _load_primer3_backend()
    if primer3 is not None and len(s) >= 100:
        try:
            result = primer3.design_primers(
                seq_args={
                    "SEQUENCE_ID": "template",
                    "SEQUENCE_TEMPLATE": s,
                    "SEQUENCE_INCLUDED_REGION": [0, len(s)],
                },
                global_args={
                    "PRIMER_OPT_TM": target_tm,
                    "PRIMER_MIN_TM": target_tm - tm_tol,
                    "PRIMER_MAX_TM": target_tm + tm_tol,
                    "PRIMER_MIN_SIZE": min_len,
                    "PRIMER_MAX_SIZE": max_len,
                    "PRIMER_OPT_SIZE": 20,
                    "PRIMER_MIN_GC": 35.0,
                    "PRIMER_MAX_GC": 65.0,
                    "PRIMER_MAX_POLY_X": 3,
                    "PRIMER_NUM_RETURN": 3,
                },
            )
            if result.get("PRIMER_PAIR_NUM_RETURNED", 0) > 0:
                fwd_seq = result["PRIMER_LEFT_0_SEQUENCE"]
                rev_seq = result["PRIMER_RIGHT_0_SEQUENCE"]
                return {
                    "forward": {
                        "seq": fwd_seq,
                        "tm": round(result["PRIMER_LEFT_0_TM"], 1),
                        "gc": round(result["PRIMER_LEFT_0_GC_PERCENT"], 1),
                        "length": len(fwd_seq),
                        "issues": check_primer_issues(fwd_seq),
                    },
                    "reverse": {
                        "seq": rev_seq,
                        "tm": round(result["PRIMER_RIGHT_0_TM"], 1),
                        "gc": round(result["PRIMER_RIGHT_0_GC_PERCENT"], 1),
                        "length": len(rev_seq),
                        "issues": check_primer_issues(rev_seq),
                    },
                    "product_size": result.get("PRIMER_PAIR_0_PRODUCT_SIZE", len(s)),
                    "warnings": [],
                    "backend": "primer3-py",
                }
        except Exception as e:
            logger.debug("primer3 design_primers failed: %s", e)

    # Fallback: sliding window
    def _pick(region, fwd):
        seq_s = region if fwd else _reverse_complement(region)
        best, best_diff = None, 999
        for length in range(min_len, min(max_len + 1, len(seq_s) + 1)):
            cand = seq_s[:length]
            diff = abs(calc_tm(cand) - target_tm)
            if diff < best_diff:
                best_diff = diff
                best = {"seq": cand, "tm": calc_tm(cand),
                        "gc": round(calc_gc(cand), 1), "length": length}
        return best

    fwd = _pick(s[:60], True)
    rev = _pick(s[-60:], False)
    if not fwd or not rev:
        return {"error": "Could not design primers"}
    fwd["issues"] = check_primer_issues(fwd["seq"])
    rev["issues"] = check_primer_issues(rev["seq"])
    warnings = []
    if abs(fwd["tm"] - rev["tm"]) > 5:
        warnings.append(f"Large Tm difference ({abs(fwd['tm']-rev['tm']):.1f}°C)")
    return {"forward": fwd, "reverse": rev,
            "product_size": len(s), "warnings": warnings, "backend": "sliding-window"}


def get_restriction_enzymes() -> dict:
    """Return restriction enzyme dict from Biopython REBASE or built-in fallback."""
    if _BIO_OK:
        try:
            from Bio.Restriction import CommOnly
            enzymes = {}
            for enz in CommOnly:
                try:
                    site = str(enz.site)
                    ovhg = getattr(enz, 'ovhg', 0)
                    if ovhg > 0:   ends = f"{ovhg}-nt 5' overhang"
                    elif ovhg < 0: ends = f"{abs(ovhg)}-nt 3' overhang"
                    else:           ends = "Blunt"
                    enzymes[enz.__name__] = {"site": site, "ends": ends}
                except Exception:
                    continue
            if enzymes:
                logger.info("Loaded %d enzymes from Biopython REBASE", len(enzymes))
                return enzymes
        except Exception as e:
            logger.debug("Biopython restriction failed: %s", e)

    # Built-in fallback
    return {
        "EcoRI":   {"site": "GAATTC",   "ends": "4-nt 5' overhang"},
        "BamHI":   {"site": "GGATCC",   "ends": "4-nt 5' overhang"},
        "HindIII": {"site": "AAGCTT",   "ends": "4-nt 5' overhang"},
        "NotI":    {"site": "GCGGCCGC", "ends": "4-nt 5' overhang"},
        "XhoI":    {"site": "CTCGAG",   "ends": "4-nt 5' overhang"},
        "NcoI":    {"site": "CCATGG",   "ends": "4-nt 5' overhang"},
        "NdeI":    {"site": "CATATG",   "ends": "4-nt 5' overhang"},
        "SalI":    {"site": "GTCGAC",   "ends": "4-nt 5' overhang"},
        "XbaI":    {"site": "TCTAGA",   "ends": "4-nt 5' overhang"},
        "KpnI":    {"site": "GGTACC",   "ends": "4-nt 3' overhang"},
        "SacI":    {"site": "GAGCTC",   "ends": "4-nt 3' overhang"},
        "PstI":    {"site": "CTGCAG",   "ends": "4-nt 3' overhang"},
        "SmaI":    {"site": "CCCGGG",   "ends": "Blunt"},
        "EcoRV":   {"site": "GATATC",   "ends": "Blunt"},
        "NheI":    {"site": "GCTAGC",   "ends": "4-nt 5' overhang"},
        "SpeI":    {"site": "ACTAGT",   "ends": "4-nt 5' overhang"},
        "ClaI":    {"site": "ATCGAT",   "ends": "2-nt 5' overhang"},
        "SphI":    {"site": "GCATGC",   "ends": "4-nt 3' overhang"},
        "ApaI":    {"site": "GGGCCC",   "ends": "4-nt 3' overhang"},
        "MluI":    {"site": "ACGCGT",   "ends": "4-nt 5' overhang"},
    }
