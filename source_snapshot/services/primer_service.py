from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

from core.primer_utils import (
    calc_gc,
    calc_tm,
    check_primer_issues,
    design_outer_primers,
    design_primers,
    _load_primer3_backend,
    get_primer3_backend_status,
)


DEFAULT_NUM_DESIGNS = 5
PRIMER_BACKEND_UNAVAILABLE_MESSAGE = (
    "Primer design engine is unavailable in this environment. You can continue reviewing documentation fields."
)


@dataclass(frozen=True)
class DesignParameters:
    target_tm: float
    tm_tolerance: float
    min_length: int
    max_length: int


def _clean_sequence(sequence: str) -> str:
    return "".join(base for base in str(sequence or "").upper() if base in "ATCG")


def _normalize_dg(dg_value: Any) -> float | None:
    if dg_value is None:
        return None
    try:
        value = float(dg_value)
    except (TypeError, ValueError):
        return None
    if abs(value) > 100:
        value = value / 1000.0
    return round(value, 2)


def _risk_from_dg(dg_value: float | None, *, high_cutoff: float, moderate_cutoff: float) -> str:
    if dg_value is None:
        return "Unknown"
    if dg_value <= high_cutoff:
        return "High"
    if dg_value <= moderate_cutoff:
        return "Moderate"
    return "Low"


def _structure_metrics(sequence: str) -> dict[str, Any]:
    metrics = {
        "tm": calc_tm(sequence),
        "gc_content": round(calc_gc(sequence), 1),
        "length": len(sequence),
        "hairpin": {"dg_kcal_mol": None, "risk": "Unknown"},
        "self_dimer": {"dg_kcal_mol": None, "risk": "Unknown"},
        "warnings": check_primer_issues(sequence),
    }

    primer3 = _load_primer3_backend()
    if primer3 is not None:
        try:
            hairpin = primer3.calc_hairpin(sequence)
            hairpin_dg = _normalize_dg(getattr(hairpin, "dg", None))
            metrics["hairpin"] = {
                "dg_kcal_mol": hairpin_dg,
                "risk": _risk_from_dg(hairpin_dg, high_cutoff=-4.0, moderate_cutoff=-2.0),
            }

            self_dimer = primer3.calc_homodimer(sequence)
            self_dimer_dg = _normalize_dg(getattr(self_dimer, "dg", None))
            metrics["self_dimer"] = {
                "dg_kcal_mol": self_dimer_dg,
                "risk": _risk_from_dg(self_dimer_dg, high_cutoff=-6.0, moderate_cutoff=-3.0),
            }
        except Exception:
            pass

    return metrics


def _heterodimer_metrics(forward_sequence: str, reverse_sequence: str) -> dict[str, Any]:
    result = {"dg_kcal_mol": None, "risk": "Unknown"}
    primer3 = _load_primer3_backend()
    if primer3 is None:
        return result
    try:
        heterodimer = primer3.calc_heterodimer(forward_sequence, reverse_sequence)
        dg_value = _normalize_dg(getattr(heterodimer, "dg", None))
        result = {
            "dg_kcal_mol": dg_value,
            "risk": _risk_from_dg(dg_value, high_cutoff=-6.0, moderate_cutoff=-3.0),
        }
    except Exception:
        return result
    return result


def _build_primer_entry(name: str, sequence: str, *, role: str, target_tm: float) -> dict[str, Any]:
    metrics = _structure_metrics(sequence)
    tm_deviation = round(abs(metrics["tm"] - target_tm), 2)
    gc_in_range = 40.0 <= metrics["gc_content"] <= 60.0
    return {
        "name": name,
        "role": role,
        "sequence": sequence,
        "tm": metrics["tm"],
        "tm_deviation": tm_deviation,
        "gc_content": metrics["gc_content"],
        "gc_in_range": gc_in_range,
        "length": metrics["length"],
        "hairpin_risk": metrics["hairpin"]["risk"],
        "hairpin_dg_kcal_mol": metrics["hairpin"]["dg_kcal_mol"],
        "self_dimer_risk": metrics["self_dimer"]["risk"],
        "self_dimer_dg_kcal_mol": metrics["self_dimer"]["dg_kcal_mol"],
        "issues": metrics["warnings"],
    }


def _score_penalty_for_risk(risk: str) -> int:
    return {
        "High": 30,
        "Moderate": 15,
        "Low": 0,
        "Unknown": 8,
    }.get(risk, 8)


def _build_quality_summary(
    *,
    primer_pair: dict[str, Any],
    forward_entry: dict[str, Any],
    reverse_entry: dict[str, Any],
    heterodimer: dict[str, Any],
    target_tm: float,
) -> tuple[str, int, list[str]]:
    pair_warnings = list(primer_pair.get("warnings") or [])
    score = 100
    reasons: list[str] = []

    tm_gap = round(abs(forward_entry["tm"] - reverse_entry["tm"]), 2)
    max_tm_deviation = max(forward_entry["tm_deviation"], reverse_entry["tm_deviation"])
    if max_tm_deviation > 3.0:
        score -= 18
        reasons.append(f"Tm deviation exceeds preferred range ({max_tm_deviation:.2f}°C).")
    elif max_tm_deviation > 1.5:
        score -= 8
        reasons.append(f"Tm deviation is moderate ({max_tm_deviation:.2f}°C).")

    if tm_gap > 3.0:
        if tm_gap > 5.0:
            score -= 18
        else:
            score -= 12
        reasons.append(f"Forward/reverse Tm gap is elevated ({tm_gap:.2f}°C).")

    gc_balance_gap = round(abs(forward_entry["gc_content"] - reverse_entry["gc_content"]), 2)
    if gc_balance_gap > 20.0:
        score -= 10
        reasons.append(f"Forward/reverse GC balance gap is elevated ({gc_balance_gap:.1f}%).")
    elif gc_balance_gap > 12.0:
        score -= 4
        reasons.append(f"Forward/reverse GC balance gap is moderate ({gc_balance_gap:.1f}%).")

    gc_flags = []
    if not forward_entry["gc_in_range"]:
        penalty = 14 if forward_entry["gc_content"] < 35.0 or forward_entry["gc_content"] > 65.0 else 8
        score -= penalty
        gc_flags.append(f"Forward GC {forward_entry['gc_content']:.1f}%")
    if not reverse_entry["gc_in_range"]:
        penalty = 14 if reverse_entry["gc_content"] < 35.0 or reverse_entry["gc_content"] > 65.0 else 8
        score -= penalty
        gc_flags.append(f"Reverse GC {reverse_entry['gc_content']:.1f}%")
    if gc_flags:
        reasons.append("GC content outside preferred 40-60% range (" + ", ".join(gc_flags) + ").")

    for primer in (forward_entry, reverse_entry):
        score -= min(len(primer["issues"]) * 4, 16)
        reasons.extend(primer["issues"])
        score -= _score_penalty_for_risk(primer["hairpin_risk"])
        score -= _score_penalty_for_risk(primer["self_dimer_risk"])

    hetero_risk = heterodimer["risk"]
    score -= _score_penalty_for_risk(hetero_risk)
    if hetero_risk in {"Moderate", "High"}:
        reasons.append(f"Heterodimer risk is {hetero_risk.lower()}.")

    if pair_warnings:
        score -= min(len(pair_warnings) * 6, 18)
        reasons.extend(pair_warnings)

    score = max(0, min(100, score))
    deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))

    if score >= 85:
        grade = "Recommended"
    elif score >= 60:
        grade = "Usable with Risk"
    else:
        grade = "Not Recommended"

    if not deduped_reasons:
        deduped_reasons.append(f"Primer metrics are aligned with target Tm {target_tm:.1f}°C.")

    return grade, score, deduped_reasons[:6]


def _candidate_parameter_sets(
    *,
    target_tm: float,
    tm_tolerance: float,
    min_length: int,
    max_length: int,
) -> list[DesignParameters]:
    tm_values = sorted({round(target_tm + delta, 1) for delta in (-2.0, -1.0, 0.0, 1.0, 2.0)})
    tolerance_values = sorted({round(max(0.5, tm_tolerance + delta), 1) for delta in (0.0, 1.0)})
    min_values = sorted({max(16, min_length + delta) for delta in (-2, 0, 2)})
    max_values = sorted({
        max(min_value + 2, candidate)
        for min_value in min_values
        for candidate in (max_length, 32, 34)
    })

    candidates: list[DesignParameters] = []
    for tm_value, tolerance_value, min_value, max_value in product(tm_values, tolerance_values, min_values, max_values):
        if min_value >= max_value:
            continue
        params = DesignParameters(
            target_tm=tm_value,
            tm_tolerance=tolerance_value,
            min_length=min_value,
            max_length=max_value,
        )
        if params not in candidates:
            candidates.append(params)
    return candidates


def _result_signature(result_payload: dict[str, Any]) -> tuple[str, str]:
    primers = result_payload.get("primers") or []
    if len(primers) < 2:
        return ("", "")
    return primers[0].get("sequence", ""), primers[1].get("sequence", "")


def _build_result_payload(cleaned_sequence: str, primer_pair: dict[str, Any], params: DesignParameters) -> dict[str, Any]:
    forward_sequence = primer_pair["forward"]["seq"]
    reverse_sequence = primer_pair["reverse"]["seq"]

    forward_entry = _build_primer_entry("Forward Primer", forward_sequence, role="forward", target_tm=params.target_tm)
    reverse_entry = _build_primer_entry("Reverse Primer", reverse_sequence, role="reverse", target_tm=params.target_tm)
    heterodimer = _heterodimer_metrics(forward_sequence, reverse_sequence)
    quality_grade, quality_score, quality_reasons = _build_quality_summary(
        primer_pair=primer_pair,
        forward_entry=forward_entry,
        reverse_entry=reverse_entry,
        heterodimer=heterodimer,
        target_tm=params.target_tm,
    )

    payload = {
        "template_length": len(cleaned_sequence),
        "product_size": primer_pair.get("product_size"),
        "backend": primer_pair.get("backend", "unknown"),
        "quality_grade": quality_grade,
        "quality_score": quality_score,
        "quality_reasons": quality_reasons,
        "hetero_dimer_risk": heterodimer["risk"],
        "hetero_dimer_dg_kcal_mol": heterodimer["dg_kcal_mol"],
        "pair_warnings": primer_pair.get("warnings") or [],
        "target_tm": params.target_tm,
        "tm_tolerance": params.tm_tolerance,
        "min_length": params.min_length,
        "max_length": params.max_length,
        "tm_gap": round(abs(forward_entry["tm"] - reverse_entry["tm"]), 2),
        "gc_balance_gap": round(abs(forward_entry["gc_content"] - reverse_entry["gc_content"]), 2),
        "max_tm_deviation": max(forward_entry["tm_deviation"], reverse_entry["tm_deviation"]),
        "issue_count": len(forward_entry["issues"]) + len(reverse_entry["issues"]) + len(primer_pair.get("warnings") or []),
        "rank_metrics": primer_pair.get("rank_metrics") or {},
        "primers": [forward_entry, reverse_entry],
    }
    for key in ("forward_start", "reverse_start", "product_start", "product_end"):
        if key in primer_pair:
            payload[key] = primer_pair[key]
    return payload


def _is_full_cassette_outer_product(primer_pair: dict[str, Any], sequence_length: int) -> bool:
    if primer_pair.get("product_size") != sequence_length:
        return False
    product_start = primer_pair.get("product_start")
    product_end = primer_pair.get("product_end")
    if product_start is not None and int(product_start) != 0:
        return False
    if product_end is not None and int(product_end) != sequence_length:
        return False
    forward_start = primer_pair.get("forward_start")
    reverse_start = primer_pair.get("reverse_start")
    reverse_seq = ((primer_pair.get("reverse") or {}).get("seq") or "")
    if forward_start is not None and int(forward_start) != 0:
        return False
    if reverse_start is not None and reverse_seq and int(reverse_start) != sequence_length - len(reverse_seq):
        return False
    return True


def _rank_candidate_payloads(
    candidate_payloads: list[dict[str, Any]],
    *,
    target_tm: float,
    num_designs: int,
) -> list[dict[str, Any]]:
    candidate_payloads.sort(
        key=lambda item: (
            -item["quality_score"],
            item.get("max_tm_deviation", 999.0),
            item["tm_gap"],
            sum(
                0.0 if 40.0 <= primer.get("gc_content", 0.0) <= 60.0
                else min(abs(primer.get("gc_content", 0.0) - 50.0), 50.0)
                for primer in item.get("primers", [])
            ),
            item.get("gc_balance_gap", 999.0),
            item.get("issue_count", 999),
            item.get("hetero_dimer_risk") == "High",
            item.get("hetero_dimer_risk") == "Moderate",
            sum(primer.get("length", 0) for primer in item.get("primers", [])),
            abs(item["target_tm"] - target_tm),
        )
    )
    return candidate_payloads[: max(1, num_designs)]


def design_and_evaluate_primers(
    sequence: str,
    *,
    target_tm: float = 60.0,
    tm_tolerance: float = 2.0,
    min_length: int = 18,
    max_length: int = 30,
    num_designs: int = DEFAULT_NUM_DESIGNS,
) -> dict[str, Any]:
    cleaned_sequence = _clean_sequence(sequence)
    if len(cleaned_sequence) < 40:
        return {
            "success": False,
            "error": "Template too short (minimum 40 bp)",
            "input_length": len(cleaned_sequence),
            "results": [],
        }

    candidate_payloads: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()

    for params in _candidate_parameter_sets(
        target_tm=target_tm,
        tm_tolerance=tm_tolerance,
        min_length=min_length,
        max_length=max_length,
    ):
        primer_pair = design_primers(
            cleaned_sequence,
            target_tm=params.target_tm,
            tm_tol=params.tm_tolerance,
            min_len=params.min_length,
            max_len=params.max_length,
        )
        if primer_pair.get("error"):
            continue

        payload = _build_result_payload(cleaned_sequence, primer_pair, params)
        signature = _result_signature(payload)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidate_payloads.append(payload)

    if not candidate_payloads:
        return {
            "success": False,
            "error": "No valid primer design candidates were generated.",
            "input_length": len(cleaned_sequence),
            "results": [],
        }

    return {
        "success": True,
        "error": "",
        "input_length": len(cleaned_sequence),
        "results": _rank_candidate_payloads(
            candidate_payloads,
            target_tm=target_tm,
            num_designs=num_designs,
        ),
    }


def design_outer_primers_for_cassette(
    sequence: str,
    *,
    target_tm: float = 60.0,
    tm_tolerance: float = 2.0,
    min_length: int = 18,
    max_length: int = 30,
    num_designs: int = DEFAULT_NUM_DESIGNS,
) -> dict[str, Any]:
    cleaned_sequence = _clean_sequence(sequence)
    if len(cleaned_sequence) < 40:
        return {
            "success": False,
            "error": "Template too short (minimum 40 bp)",
            "input_length": len(cleaned_sequence),
            "results": [],
        }

    candidate_payloads: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()

    for params in _candidate_parameter_sets(
        target_tm=target_tm,
        tm_tolerance=tm_tolerance,
        min_length=min_length,
        max_length=max_length,
    ):
        primer_pair = design_outer_primers(
            cleaned_sequence,
            target_tm=params.target_tm,
            tm_tol=params.tm_tolerance,
            min_len=params.min_length,
            max_len=params.max_length,
        )
        if primer_pair.get("error"):
            continue
        if not _is_full_cassette_outer_product(primer_pair, len(cleaned_sequence)):
            continue

        payload = _build_result_payload(cleaned_sequence, primer_pair, params)
        payload["design_scope"] = "expression_cassette"
        payload["name"] = "Expression cassette"
        signature = _result_signature(payload)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidate_payloads.append(payload)

    if not candidate_payloads:
        return {
            "success": False,
            "error": "No valid full-cassette outer-primer candidates were generated.",
            "input_length": len(cleaned_sequence),
            "results": [],
        }

    return {
        "success": True,
        "error": "",
        "input_length": len(cleaned_sequence),
        "design_scope": "expression_cassette",
        "results": _rank_candidate_payloads(
            candidate_payloads,
            target_tm=target_tm,
            num_designs=num_designs,
        ),
    }


def design_primers_if_available(sequence: str, **kwargs: Any) -> dict[str, Any]:
    status = get_primer3_backend_status(probe=False)
    cleaned_sequence = _clean_sequence(sequence)
    if not status.available:
        return {
            "success": False,
            "unavailable": True,
            "error": status.reason or PRIMER_BACKEND_UNAVAILABLE_MESSAGE,
            "input_length": len(cleaned_sequence),
            "results": [],
        }
    return design_outer_primers_for_cassette(sequence, **kwargs)
