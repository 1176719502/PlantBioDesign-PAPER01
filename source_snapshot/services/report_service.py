from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import re
from typing import Any, Dict, List

from services.assembly_plan_summary_service import build_assembly_plan_summary
from services.export_recommendation_service import build_export_recommendation
from services.report_identity_presenter import (
    build_report_identity_block,
    build_report_visual_narrative,
    format_report_identity_markdown,
    format_report_visual_narrative_markdown,
)
from services.validation_summary_service import (
    build_primer_risk_summary,
    build_validation_conclusion,
    build_validation_run_state,
)


EXPORT_FORMAT_DETAILS = {
    "markdown": {
        "label": "Markdown Report (.md)",
        "extension": ".md",
        "mime": "text/markdown",
        "category": "report",
        "use_case": "Share the full Step 4–6 report for review and documentation."
    },
    "fasta": {
        "label": "FASTA Sequence (.fasta)",
        "extension": ".fasta",
        "mime": "text/plain",
        "category": "sequence",
        "use_case": "Use for documentation review, sequence traceability, and non-executing reference workflows.",
    },
    "genbank": {
        "label": "GenBank Record (.gb)",
        "extension": ".gb",
        "mime": "text/plain",
        "category": "sequence_annotation",
        "use_case": "Use when annotated biological features must be preserved in Benchling, SnapGene, or Geneious.",
    },
    "png": {
        "label": "Construct/cassette map preview PNG",
        "extension": ".png",
        "mime": "image/png",
        "category": "visual",
        "use_case": "Documentation map preview image for construct/cassette structure review and handoff communication; not sequence validation or cloning feasibility verification.",
    },
}


def _na(value: Any, fallback: str = "Not set") -> str:
    return fallback if value in (None, "", 0) else str(value)


SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE = "No sequence verification result was attached to this report."
SEQUENCE_VERIFICATION_STALE_REPORT_MESSAGE = "Sequence verification result was not included because it does not match the current sequence."
SEQUENCE_VERIFICATION_BLAST_NO_HITS_MESSAGE = "No valid BLAST hits were parsed from the imported TSV."
SEQUENCE_VERIFICATION_LOCAL_NO_HITS_MESSAGE = "No local similarity or containment hits were found by the selected verification source."
SEQUENCE_VERIFICATION_UNAVAILABLE_MESSAGE = "The selected verification source is unavailable or the imported TSV could not be parsed. No external lookup was attempted."
SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY = "seq_tools_verification_result"


def _normalize_sequence_for_hash(sequence: str) -> str:
    lines = []
    for line in str(sequence or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        lines.append(stripped)
    return re.sub(r"[^ATGCNatgcn]", "", "".join(lines)).upper()


def _sequence_hash(sequence: str) -> str:
    normalized = _normalize_sequence_for_hash(sequence)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _get_verification_source(result: Dict[str, Any]) -> str:
    database = result.get("database") if isinstance(result.get("database"), dict) else {}
    return str(database.get("source") or result.get("source") or "Not configured")


def _format_optional_percent(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_optional_value(value: Any) -> str:
    return "N/A" if value in (None, "") else str(value)


def _warning_texts(warnings: Any) -> List[str]:
    if not isinstance(warnings, list):
        return []
    texts: List[str] = []
    for item in warnings:
        if isinstance(item, dict):
            code = str(item.get("code") or "INFORMATIONAL_ONLY")
            message = str(item.get("message") or "Review this verification signal manually.")
            texts.append(f"{code}: {message}")
        elif item not in (None, ""):
            texts.append(str(item))
    return texts


def _verification_no_hit_message(result: Dict[str, Any]) -> str:
    source = _get_verification_source(result)
    if source == "Imported BLAST TSV":
        return SEQUENCE_VERIFICATION_BLAST_NO_HITS_MESSAGE
    if source == "Local Parts Registry":
        return SEQUENCE_VERIFICATION_LOCAL_NO_HITS_MESSAGE
    return SEQUENCE_VERIFICATION_UNAVAILABLE_MESSAGE


def _verification_signature_from_result(result: Dict[str, Any]) -> str:
    query = result.get("query") if isinstance(result.get("query"), dict) else {}
    for key in ("signature", "sequence_signature", "hash"):
        value = query.get(key) or result.get(key)
        if value:
            return str(value)
    return ""


def _build_sequence_verification_summary(
    verification_result: Dict[str, Any] | None,
    current_sequence: str,
) -> Dict[str, Any]:
    if not isinstance(verification_result, dict):
        return {
            "included": False,
            "is_stale": False,
            "message": SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE,
            "rows": [],
            "warnings": [],
        }

    result_signature = _verification_signature_from_result(verification_result)
    current_hash = _sequence_hash(current_sequence)
    current_signature = _normalize_sequence_for_hash(current_sequence)
    if result_signature and result_signature not in {current_hash, current_signature}:
        return {
            "included": False,
            "is_stale": True,
            "message": SEQUENCE_VERIFICATION_STALE_REPORT_MESSAGE,
            "rows": [],
            "warnings": [],
        }

    query = verification_result.get("query") if isinstance(verification_result.get("query"), dict) else {}
    top_hit = verification_result.get("top_hit") if isinstance(verification_result.get("top_hit"), dict) else None
    status = str(verification_result.get("status") or "not_run")
    warnings = _warning_texts(verification_result.get("warnings"))
    message = ""
    if status == "no_hits":
        message = _verification_no_hit_message(verification_result)
    elif status == "unavailable":
        message = SEQUENCE_VERIFICATION_UNAVAILABLE_MESSAGE

    rows = [
        {"label": "Verification source", "value": _get_verification_source(verification_result)},
        {"label": "Status", "value": status},
        {"label": "Query length", "value": f"{int(query.get('length') or 0):,} bp"},
        {"label": "Adapter name", "value": str(verification_result.get("adapter_name") or "Not configured")},
        {"label": "Timestamp", "value": str(verification_result.get("timestamp") or "Not available")},
        {"label": "Top hit accession", "value": _format_optional_value((top_hit or {}).get("accession"))},
        {"label": "Top hit description", "value": _format_optional_value((top_hit or {}).get("description"))},
        {"label": "Percent identity", "value": _format_optional_percent((top_hit or {}).get("percent_identity"))},
        {"label": "Coverage", "value": _format_optional_percent((top_hit or {}).get("coverage"))},
        {"label": "E-value", "value": _format_optional_value((top_hit or {}).get("e_value"))},
        {"label": "Match type", "value": _format_optional_value((top_hit or {}).get("match_type"))},
        {"label": "Warnings", "value": " | ".join(warnings) if warnings else "None"},
        {"label": "Disclaimer", "value": str(verification_result.get("disclaimer") or "Not available")},
    ]
    return {
        "included": True,
        "is_stale": False,
        "message": message,
        "rows": rows,
        "warnings": warnings,
        "status": status,
        "source": _get_verification_source(verification_result),
        "top_hit": top_hit,
        "disclaimer": str(verification_result.get("disclaimer") or ""),
    }


def _resolve_session_verification_result() -> Dict[str, Any] | None:
    try:
        import streamlit as st

        result = st.session_state.get(SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def _gc(seq: str) -> float:
    s = seq.upper()
    return round((s.count("G") + s.count("C")) / len(s) * 100, 2) if s else 0.0


def _tm_wallace(seq: str) -> float:
    p = seq.upper()
    return 2 * (p.count("A") + p.count("T")) + 4 * (p.count("G") + p.count("C"))


def _primer_tm(seq: str) -> str:
    try:
        from Bio.SeqUtils.MeltingTemp import Tm_Wallace
        return f"{Tm_Wallace(seq):.1f} °C"
    except Exception:
        return f"{_tm_wallace(seq):.1f} °C" if seq else "N/A"


def _build_elements(ds) -> List[Dict[str, Any]]:
    fr = ds.frame if isinstance(ds.frame, dict) else {}
    elems = ds.elements if isinstance(ds.elements, dict) else {}
    parts = fr.get("parts") or fr.get("components") or []
    rows: List[Dict[str, Any]] = []

    def add(part_type: str, name_key: str, seq_key: str) -> None:
        name = elems.get(name_key, "") or fr.get(name_key, "")
        seq = elems.get(seq_key, "") or fr.get(seq_key, "")
        if not name:
            for part in parts:
                if isinstance(part, dict) and part.get("type", "").lower() == part_type.lower():
                    name = part.get("name", "")
                    seq = seq or part.get("seq", "")
                    break
        rows.append({"Type": part_type, "Name": _na(name), "Length (bp)": len(seq) if seq else "—", "Source": "Registry" if elems.get(name_key) else "Host Default"})

    add("Promoter", "promoter_name", "promoter_seq")
    add("RBS / Kozak", "rbs_name", "rbs_seq")
    add("CDS", "gene_name", "optimized_seq")
    add("Terminator", "terminator_name", "terminator_seq")
    if ds.tag and ds.tag not in ("", "No tag"):
        rows.append({"Type": "Fusion Tag", "Name": ds.tag, "Length (bp)": "—", "Source": "User Selected"})
    return rows


def _build_primer_rows(ds) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in ds.primers:
        if not isinstance(p, dict):
            continue
        if "Fragment Name" in p:
            frag = p.get("Fragment Name") or "Unnamed"
            specs = [
                ("Forward", "Forward Primer (5'->3')", "Fwd Anneal Tm (°C)", "Fwd Arm (bp)", "Fwd"),
                ("Reverse", "Reverse Primer (5'->3')", "Rev Anneal Tm (°C)", "Rev Arm (bp)", "Rev"),
            ]
            for label, seq_key, tm_key, arm_key, role in specs:
                seq = str(p.get(seq_key) or "")
                if not seq:
                    continue
                tm_val = p.get(tm_key)
                rows.append({"Name": f"{frag} — {label}", "Fragment": frag, "Sequence (5'→3')": seq, "Length": f"{len(seq)} nt", "Tm": f"{tm_val} °C" if tm_val is not None else _primer_tm(seq), "Role": f"{role} (arm {p.get(arm_key, '—')} bp)"})
        else:
            seq = str(p.get("sequence") or p.get("seq") or "")
            rows.append({"Name": p.get("name") or p.get("primer_name") or "Unnamed", "Fragment": p.get("Fragment Name") or "—", "Sequence (5'→3')": seq, "Length": f"{len(seq)} nt" if seq else "—", "Tm": _primer_tm(seq) if seq else "—", "Role": p.get("role") or p.get("type") or "—"})
    return rows


def _build_validation_rows(ds) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in ds.validation_results:
        if isinstance(item, dict):
            rows.append({"Severity": str(item.get("severity", "info")).upper(), "Code": str(item.get("code", "") or ""), "Title": str(item.get("title", "") or item.get("message", "")), "Why": str(item.get("why", "") or ""), "Fix": str(item.get("fix", "") or "")})
    return rows


def _build_codon_summary(ds) -> Dict[str, Any]:
    cr = ds.codon_report if isinstance(ds.codon_report, dict) else {}
    return {"CAI (before)": _na((cr.get("before") or {}).get("cai")), "CAI (after)": _na((cr.get("after") or {}).get("cai")), "GC (before)": _na((cr.get("before") or {}).get("gc_percent")), "GC (after)": _na((cr.get("after") or {}).get("gc_percent")), "Rare codons": _na(len(((cr.get("after") or {}).get("rare_codons") or [])))}


def _build_primer_quality(ds) -> Dict[str, Any]:
    raw = [p for p in (ds.primers or []) if isinstance(p, dict)]
    counts = {"Recommended": 0, "Usable with Risk": 0, "Not Recommended": 0}
    reasons: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    for p in raw:
        grade = str(p.get("Quality Grade") or "").strip()
        if grade in counts:
            counts[grade] += 1
        for text in p.get("Quality Reasons") or []:
            text = str(text).strip()
            if text:
                reasons[text] += 1
        for text in p.get("Warnings") or []:
            text = str(text).strip()
            if text:
                warnings[text] += 1
    plan = ds.step4_plan_summary if isinstance(getattr(ds, "step4_plan_summary", None), dict) else {}
    structured = []
    for item in plan.get("structured_results") or []:
        if isinstance(item, dict):
            structured.append({"name": item.get("name") or "—", "quality_grade": item.get("quality_grade") or "—", "quality_score": item.get("quality_score"), "product_size": item.get("product_size"), "target_tm": item.get("target_tm"), "tm_gap": item.get("tm_gap"), "heterodimer_risk": item.get("hetero_dimer_risk") or "—", "quality_reasons": item.get("quality_reasons") or [], "pair_warnings": item.get("pair_warnings") or []})
    dominant = next((k for k in ("Not Recommended", "Usable with Risk", "Recommended") if counts[k] > 0), "Not set")
    return {"quality_grade": dominant, "quality_reasons": [t for t, _ in reasons.most_common(5)], "pair_warnings": [t for t, _ in warnings.most_common(5)], "risk_summary": build_primer_risk_summary(raw), "selected_overlap": plan.get("selected_overlap_len"), "selected_target_tm": plan.get("selected_target_tm"), "best_plan_summary": plan.get("best_plan_summary") or "", "structured_results": structured}


def _build_step4_assembly_plan_summary(ds) -> Dict[str, Any]:
    return build_assembly_plan_summary(ds)


def _build_validation_results(ds, validation_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    validation_state = validation_state or build_validation_run_state(ds)
    issues = validation_state["issues"]
    primer_risk = build_primer_risk_summary([p for p in (ds.primers or []) if isinstance(p, dict)])
    if validation_state["is_complete"]:
        conclusion = build_validation_conclusion(issues)
    elif validation_state["is_stale"]:
        conclusion = {
            "status": "stale",
            "title": "Stored validation result is stale",
            "summary": "The frame or primer context changed since the last validation run. Run validation again before export.",
            "tone": "warn",
            "critical_count": validation_state["critical_count"],
            "warning_count": validation_state["warning_count"],
            "info_count": validation_state["info_count"],
            "has_primer_high_risk": False,
        }
    elif validation_state["is_running"]:
        conclusion = {
            "status": "running",
            "title": "Validation is running",
            "summary": "Validation is still running. Wait for Step 5 to finish before export review.",
            "tone": "info",
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "has_primer_high_risk": False,
        }
    elif validation_state["is_failed"]:
        conclusion = {
            "status": "failed",
            "title": "Validation failed or is unavailable",
            "summary": "The validation task failed or the validation tool is unavailable. Retry validation before export.",
            "tone": "warn",
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "has_primer_high_risk": False,
        }
    else:
        conclusion = {
            "status": "not_run",
            "title": "No validation result",
            "summary": "Validation has not been run yet.",
            "tone": "info",
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "has_primer_high_risk": False,
        }
    return {"issue_list": _build_validation_rows(ds), "primer_risk_summary": {"recommended_count": primer_risk["recommended"], "usable_with_risk_count": primer_risk["usable_with_risk"], "not_recommended_count": primer_risk["not_recommended"], "affected_fragments": primer_risk["affected_fragments"], "top_risk_reasons": primer_risk["top_reasons"]}, "final_conclusion": conclusion}


def _build_summary_card_level(step_key: str, step_data: Dict[str, Any]) -> str:
    if step_key == "step4":
        assembly_plan = step_data.get("assembly_plan") or {}
        readiness_status = str(assembly_plan.get("readiness_status") or "")
        if readiness_status == "Available for review":
            return "ready"
        if readiness_status in {"Needs review", "Needs Review"}:
            return "review"
        if readiness_status == "Blocked":
            return "warn"

        primer_grade = str(step_data.get("quality_grade") or step_data.get("status") or "Not set")
        if primer_grade == "Recommended":
            return "ready"
        if primer_grade == "Usable with Risk":
            return "review"
        if primer_grade == "Not Recommended":
            return "warn"
        return "neutral"

    if step_key == "step5":
        validation_status = str(step_data.get("status") or "not_run")
        if validation_status == "passed":
            return "ready"
        if validation_status in {"review_required", "not_run", "running"}:
            return "review"
        if validation_status in {"blocking", "high_risk_primer_review", "failed", "stale"}:
            return "warn"
        return "neutral"

    export_recommendation = str(step_data.get("recommendation") or step_data.get("status") or "Not set")
    if export_recommendation == "Documentation Export Available":
        return "ready"
    if export_recommendation == "Export with Review Required":
        return "review"
    if export_recommendation == "Review blocked by unresolved risk signals":
        return "warn"
    return "neutral"



def build_report_presenter(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a reusable presenter payload for page preview and report export."""
    meta = report.get("meta") or {}
    step_alignment = report.get("step_alignment") or {}
    step4 = step_alignment.get("step4") or {}
    step5 = step_alignment.get("step5") or {}
    step6 = step_alignment.get("step6") or {}
    sequence_verification = report.get("sequence_verification") or {}

    overview_rows = [
        {"label": "Gene", "value": meta.get("Gene / Construct", "—")},
        {"label": "Host", "value": meta.get("Expression Host", "—")},
        {"label": "Tag", "value": meta.get("Protein Tag", "—")},
        {"label": "Length (bp)", "value": str(meta.get("Total Length (bp)", 0))},
        {"label": "GC (%)", "value": f"{meta.get('GC Content (%)', 0.0):.2f}"},
        {"label": "Cloning method", "value": meta.get("Cloning Method", "—")},
        {"label": "Vector suggestion", "value": meta.get("Vector Suggestion", "—")},
        {"label": "Issue count", "value": str(meta.get("Validation Issues", 0))},
    ]

    alignment_rows = []
    for step_key in ("step4", "step5", "step6"):
        step_data = step_alignment.get(step_key) or {}
        alignment_rows.append({
            "Section": step_data.get("section_title", step_key),
            "Status": step_data.get("status", "—"),
            "Details": step_data.get("summary") or step_data.get("conclusion") or step_data.get("action") or "—",
        })

    step4_risk_counts = step4.get("risk_counts") or {}
    step5_risk_counts = step5.get("risk_counts") or {}
    step6_risk_counts = step6.get("risk_counts") or {}

    step4_caption = ""
    step4_assembly_plan = step4.get("assembly_plan") or {}
    step4_readiness_reasons = step4_assembly_plan.get("readiness_reasons") or []
    if step4_readiness_reasons:
        step4_caption = "Assembly plan notes: " + " | ".join(str(reason) for reason in step4_readiness_reasons[:2])
    elif step4.get("pair_warnings"):
        step4_caption = "Risk summary: " + " | ".join(step4["pair_warnings"][:2])
    elif step4.get("quality_reasons"):
        step4_caption = "Quality notes: " + " | ".join(step4["quality_reasons"][:2])

    step5_caption = ""
    if step5.get("affected_fragments"):
        step5_caption = "Affected fragments: " + ", ".join(step5["affected_fragments"][:3])
    elif step5.get("top_risk_reasons"):
        step5_caption = "Top risk reasons: " + " | ".join(step5["top_risk_reasons"][:2])

    ready_formats = [item["format"].upper() for item in (step6.get("available_formats") or []) if item.get("available")]
    step6_caption_parts = []
    if ready_formats:
        step6_caption_parts.append("Available formats: " + ", ".join(ready_formats))
    if step6.get("action"):
        step6_caption_parts.append("Next step: " + str(step6["action"]))

    card_map = {
        "step4": {
            "step_key": "step4",
            "title": "Step 4 · Assembly plan",
            "status_text": str(step4.get("quality_grade") or step4.get("status") or "Not set"),
            "level": _build_summary_card_level("step4", step4),
            "metrics": [
                {"label": "Review status", "value": str(step4_assembly_plan.get("readiness_status") or "Not set")},
                {"label": "Assembly method", "value": str(step4_assembly_plan.get("assembly_method") or "Not set")},
                {"label": "Primer count", "value": str(step4_assembly_plan.get("primer_count") if step4_assembly_plan.get("primer_count") is not None else 0)},
                {"label": "Warnings", "value": str(step4_assembly_plan.get("warning_count") if step4_assembly_plan.get("warning_count") is not None else 0)},
            ],
            "caption": step4_caption,
        },
        "step5": {
            "step_key": "step5",
            "title": "Step 5 · Validation summary",
            "status_text": str(step5.get("status") or "not_run"),
            "level": _build_summary_card_level("step5", step5),
            "metrics": [
                {"label": "Validation status", "value": str(step5.get("status") or "not_run")},
                {"label": "Critical issues", "value": len([item for item in (step5.get("issue_list") or []) if item.get("Severity") == "CRITICAL"])},
                {"label": "Warning issues", "value": len([item for item in (step5.get("issue_list") or []) if item.get("Severity") == "WARNING"])},
                {"label": "Risky primer pairs", "value": step5_risk_counts.get("usable_with_risk", 0) + step5_risk_counts.get("not_recommended", 0)},
            ],
            "caption": step5_caption,
        },
        "step6": {
            "step_key": "step6",
            "title": "Step 6 · Export review status",
            "status_text": str(step6.get("recommendation") or step6.get("status") or "Not set"),
            "level": _build_summary_card_level("step6", step6),
            "metrics": [
                {"label": "Documentation export status", "value": str(step6.get("recommendation") or step6.get("status") or "Not set")},
                {"label": "Critical count", "value": step6_risk_counts.get("critical", 0)},
                {"label": "Primer high-risk count", "value": step6_risk_counts.get("primer_high_risk", 0)},
                {"label": "Usable-with-risk primer count", "value": step6_risk_counts.get("primer_review_required", 0)},
                {"label": "Primer action-required count", "value": step6_risk_counts.get("primer_action_required", 0)},
            ],
            "caption": " | ".join(step6_caption_parts),
        },
    }
    step_order = ["step4", "step5", "step6"]

    download_rows = []
    for item in report.get("export_formats", {}).get("available_formats") or []:
        download_rows.append({
            "Format": str(item.get("label") or item.get("format") or "—"),
            "Status": str(item.get("display_status") or item.get("status") or ("Unavailable" if not item.get("available") else "Available")),
            "File": str(item.get("filename") or "—"),
        })

    sequence = str(report.get("sequence") or "")
    sequence_preview = {}
    if sequence:
        sequence_lines = [sequence[i:i + 60] for i in range(0, min(len(sequence), 600), 60)]
        formatted_sequence = "\n".join(sequence_lines)
        if len(sequence) > 600:
            formatted_sequence += f"\n...(showing first 600 bp / total length {len(sequence):,} bp)"
        sequence_preview = {
            "heading": "Final construct sequence",
            "formatted": formatted_sequence,
            "length_bp": len(sequence),
        }

    report_download = {
        "label": "Download design report (.md)",
        "filename": f"{str(meta.get('Gene / Construct', 'construct')).replace(' ', '_')}_design_report.md",
        "mime": "text/markdown",
        "help": "Markdown report is available for review and documentation."
        if step6.get("recommendation") == "Documentation Export Available"
        else "Markdown report is available as documentation only while risks remain unresolved.",
    }

    return {
        "overview_rows": overview_rows,
        "elements": report.get("elements") or [],
        "alignment_rows": alignment_rows,
        "download_rows": download_rows,
        "sequence_verification": sequence_verification,
        "sequence_preview": sequence_preview,
        "report_download": report_download,
        "cards_by_step": card_map,
        "summary_cards": [card_map[step_key] for step_key in step_order if step_key in card_map],
    }



def _export_format_status(available: bool, export_recommendation: Dict[str, Any], ready_reason: str, unavailable_reason: str) -> Dict[str, str]:
    recommendation = str(export_recommendation.get("recommendation") or "")
    if not available:
        return {
            "status": "unavailable",
            "display_status": "Unavailable",
            "reason": unavailable_reason,
        }
    if recommendation == "Documentation Export Available":
        return {
            "status": "ready",
            "display_status": "Available for documentation",
            "reason": ready_reason,
        }
    return {
        "status": "documentation_only",
        "display_status": "Available for documentation",
        "reason": ready_reason + " This export is documentation-only while risks remain unresolved.",
    }


def _build_export_formats(export_payload: Dict[str, Any], report_markdown: str, export_recommendation: Dict[str, Any]) -> List[Dict[str, Any]]:
    sequence = str(export_payload.get("sequence") or "")
    payloads = export_payload.get("payloads") or {}
    safe_name = str(export_payload.get("safe_name") or "construct")

    formats: List[Dict[str, Any]] = []

    markdown_meta = EXPORT_FORMAT_DETAILS["markdown"]
    markdown_status = _export_format_status(
        bool(report_markdown),
        export_recommendation,
        "Full design report is available.",
        "Report content is not available.",
    )
    formats.append({
        "format": "markdown",
        **markdown_meta,
        "filename": str(export_payload.get("report_filename") or f"{safe_name}_design_report{markdown_meta['extension']}"),
        "available": bool(report_markdown),
        "sequence_required": False,
        **markdown_status,
    })

    fasta_meta = EXPORT_FORMAT_DETAILS["fasta"]
    fasta_payload = payloads.get("fasta") if isinstance(payloads, dict) else None
    fasta_status = _export_format_status(
        bool(fasta_payload),
        export_recommendation,
        "Final construct sequence is available for FASTA export.",
        "A final construct sequence is required for FASTA export.",
    )
    formats.append({
        "format": "fasta",
        **fasta_meta,
        "filename": str((fasta_payload or {}).get("file_name") or f"{safe_name}{fasta_meta['extension']}"),
        "available": bool(fasta_payload),
        "sequence_required": True,
        **fasta_status,
    })

    genbank_meta = EXPORT_FORMAT_DETAILS["genbank"]
    genbank_payload = payloads.get("genbank") if isinstance(payloads, dict) else None
    genbank_status = _export_format_status(
        bool(genbank_payload),
        export_recommendation,
        "Annotated construct features are available for GenBank export.",
        "GenBank export requires a final sequence and annotated construct features.",
    )
    formats.append({
        "format": "genbank",
        **genbank_meta,
        "filename": str((genbank_payload or {}).get("file_name") or f"{safe_name}{genbank_meta['extension']}"),
        "available": bool(genbank_payload),
        "sequence_required": True,
        **genbank_status,
    })

    png_meta = EXPORT_FORMAT_DETAILS["png"]
    png_available = bool(sequence and len(sequence) >= 30)
    png_status = _export_format_status(
        png_available,
        export_recommendation,
        "Construct length is sufficient for documentation map preview rendering.",
        "A renderable construct sequence is required for documentation map preview export.",
    )
    formats.append({
        "format": "png",
        **png_meta,
        "filename": str(export_payload.get("png_filename") or f"{safe_name}_plasmid_map{png_meta['extension']}"),
        "available": png_available,
        "sequence_required": True,
        **png_status,
    })

    ready_formats = [item["format"] for item in formats if item["available"]]
    blocked_formats = [item["format"] for item in formats if not item["available"]]
    return {
        "available_formats": formats,
        "ready_format_count": len(ready_formats),
        "blocked_format_count": len(blocked_formats),
        "ready_formats": ready_formats,
        "blocked_formats": blocked_formats,
        "recommended_primary_format": "genbank" if bool(genbank_payload) else ("fasta" if bool(fasta_payload) else "markdown"),
        "report_export_status": export_recommendation.get("recommendation") or "Not set",
    }


def _build_step_alignment(primer_quality: Dict[str, Any], validation_results: Dict[str, Any], export_recommendation: Dict[str, Any], export_formats: Dict[str, Any], assembly_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    primer_risk = validation_results.get("primer_risk_summary") or {}
    validation_conclusion = validation_results.get("final_conclusion") or {}
    return {
        "step4": {
            "section_title": "Step 4 · Primer design summary",
            "status": primer_quality.get("quality_grade") or "Not set",
            "quality_grade": primer_quality.get("quality_grade") or "Not set",
            "risk_counts": primer_quality.get("risk_summary") or {},
            "quality_reasons": primer_quality.get("quality_reasons") or [],
            "pair_warnings": primer_quality.get("pair_warnings") or [],
            "structured_results": primer_quality.get("structured_results") or [],
            "assembly_plan": assembly_plan or {},
            "readiness_status": (assembly_plan or {}).get("readiness_status", "Not set"),
            "readiness_reasons": (assembly_plan or {}).get("readiness_reasons", []),
            "warning_level": (assembly_plan or {}).get("warning_level", "none"),
        },
        "step5": {
            "section_title": "Step 5 · Validation summary",
            "status": validation_conclusion.get("status") or "not_run",
            "title": validation_conclusion.get("title") or "No validation result",
            "summary": validation_conclusion.get("summary") or "Validation has not been run yet.",
            "issue_list": validation_results.get("issue_list") or [],
            "risk_counts": {
                "recommended": primer_risk.get("recommended_count", 0),
                "usable_with_risk": primer_risk.get("usable_with_risk_count", 0),
                "not_recommended": primer_risk.get("not_recommended_count", 0),
            },
            "affected_fragments": primer_risk.get("affected_fragments") or [],
            "top_risk_reasons": primer_risk.get("top_risk_reasons") or [],
        },
        "step6": {
            "section_title": "Step 6 · Export review status",
            "status": export_recommendation.get("recommendation") or "Not set",
            "recommendation": export_recommendation.get("recommendation") or "Not set",
            "conclusion": export_recommendation.get("conclusion") or "",
            "action": export_recommendation.get("action") or "",
            "risk_counts": {
                "critical": export_recommendation.get("critical_count", 0),
                "warning": export_recommendation.get("warning_count", 0),
                "primer_high_risk": export_recommendation.get("primer_high_risk_count", 0),
                "primer_review_required": export_recommendation.get("primer_review_count", 0),
                "primer_action_required": export_recommendation.get("primer_action_required_count", 0),
            },
            "affected_fragments": export_recommendation.get("affected_fragments") or [],
            "available_formats": export_formats.get("available_formats") or [],
            "recommended_primary_format": export_formats.get("recommended_primary_format") or "markdown",
        },
    }


def _resolve_report_export_base_payload(ds) -> Dict[str, Any]:
    """Reuse canonical export payload state when available, with a minimal local fallback."""
    try:
        from components.export_manager import build_design_session_export_base_payload
        return build_design_session_export_base_payload(ds)
    except Exception:
        fr = ds.frame if isinstance(ds.frame, dict) else {}
        seq = fr.get("final_sequence") or ds.optimized_seq or ds.original_seq or ""
        project_name = str(ds.gene_name or "construct").strip() or "construct"
        safe_name = project_name.replace(" ", "_")

        parts = fr.get("parts") if isinstance(fr.get("parts"), list) else []
        features = fr.get("features") if isinstance(fr.get("features"), list) else []
        payloads = {}
        if seq:
            payloads["fasta"] = {
                "file_name": f"{safe_name}.fasta",
            }
            if parts or features:
                payloads["genbank"] = {
                    "file_name": f"{safe_name}.gb",
                }

        return {
            "sequence": seq,
            "project_name": project_name,
            "safe_name": safe_name,
            "payloads": payloads,
            "report_filename": f"{safe_name}_design_report.md",
            "png_filename": f"{safe_name}_plasmid_map.png",
            "has_sequence": bool(seq),
        }


def generate_report_content(ds, verification_result: Dict[str, Any] | None = None, include_session_verification: bool = True) -> Dict[str, Any]:
    fr = ds.frame if isinstance(ds.frame, dict) else {}
    export_payload = _resolve_report_export_base_payload(ds)
    seq = export_payload["sequence"]
    validation_state = build_validation_run_state(ds)
    meta = {"Gene / Construct": _na(ds.gene_name), "Expression Host": _na(ds.host), "Protein Tag": _na(ds.tag), "Cloning Method": _na(ds.cloning_method), "Vector Suggestion": _na(fr.get("vector_suggestion")), "Total Length (bp)": len(seq) if seq else 0, "GC Content (%)": _gc(seq), "Validation Issues": len(validation_state["issues"])}
    elements = _build_elements(ds)
    primer_quality = _build_primer_quality(ds)
    assembly_plan = _build_step4_assembly_plan_summary(ds)
    validation_results = _build_validation_results(ds, validation_state)
    export_recommendation = build_export_recommendation(ds.validation_results or [], ds.primers or [], seq, validation_complete=validation_state["is_complete"])
    sequence_verification = _build_sequence_verification_summary(
        verification_result if verification_result is not None else (_resolve_session_verification_result() if include_session_verification else None),
        seq,
    )
    placeholder_report = "Report content pending"
    export_formats = _build_export_formats(export_payload, placeholder_report, export_recommendation)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    primer_record_count = len([p for p in (ds.primers or []) if isinstance(p, dict)])
    review_stage = export_recommendation.get("recommendation") or "Documentation review status not set"
    report_identity = build_report_identity_block(
        report_title="Design Documentation Report",
        project_or_case_name=meta["Gene / Construct"],
        generated_at=generated_at,
        report_version="Expression Wizard Step 4-6 Markdown",
        software_version="BioDesign Studio",
        report_or_package_id=export_payload.get("report_filename") or "",
        purpose="Expression Wizard design record review, provenance review, and handoff communication.",
        review_stage=review_stage,
        recorded_context=(
            f"{len(elements)} construct/component element(s), {primer_record_count} primer record(s), "
            f"validation status {validation_state['status']}."
        ),
        manual_follow_up="Review primer risk, source/provenance notes, and downstream handoff questions manually or with company reviewers.",
    )
    visual_narrative = build_report_visual_narrative(
        stage=review_stage,
        recorded_context=(
            f"Construct length {len(seq) if seq else 0} bp; element records {len(elements)}; "
            f"primer records {primer_record_count}."
        ),
        manual_follow_up="Manual/company review remains responsible for source checks, unresolved primer risk, and handoff interpretation.",
    )
    report = {"meta": meta, "project_summary": meta, "construct_summary": {"final_sequence_length_bp": len(seq) if seq else 0, "gc_content_percent": _gc(seq), "vector_suggestion": _na(fr.get("vector_suggestion")), "cloning_method": _na(ds.cloning_method), "elements_count": len(elements), "primer_count": primer_record_count}, "sequence": seq, "elements": elements, "primers": _build_primer_rows(ds), "primer_quality": primer_quality, "step4_assembly_plan_summary": assembly_plan, "validation_results": validation_results, "export_recommendation": export_recommendation, "export_formats": export_formats, "sequence_verification": sequence_verification, "codon_report": _build_codon_summary(ds), "file_export_notes": {"report_format": "Markdown", "sequence_available": bool(seq), "validation_complete": validation_state["is_complete"], "validation_status": validation_state["status"], "plasmid_map_possible": bool(seq and len(seq) >= 30)}, "report_identity": report_identity, "visual_narrative": visual_narrative, "generated_at": generated_at}
    report["step_alignment"] = _build_step_alignment(primer_quality, validation_results, export_recommendation, export_formats, assembly_plan)
    report["report_presenter"] = build_report_presenter(report)
    return report


def render_markdown_report(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    seq = report["sequence"]
    primer_quality = report["primer_quality"]
    validation_results_data = report["validation_results"]
    export_summary = report["export_recommendation"]
    export_formats = report.get("export_formats") or {}
    sequence_verification = report.get("sequence_verification") or {}
    step_alignment = report.get("step_alignment") or {}
    primer_risk = validation_results_data["primer_risk_summary"]
    lines: List[str] = [f"# Design Documentation Report — {meta.get('Gene / Construct', 'Untitled')}", "", f"> **Generated:** {report['generated_at']}  ", "> **Platform:** BioDesign Studio"]
    if report.get("report_identity"):
        lines += ["", format_report_identity_markdown(report["report_identity"])]
    if report.get("visual_narrative"):
        lines += ["", format_report_visual_narrative_markdown(report["visual_narrative"])]
    lines += ["", "## 1. Project summary", "", "| Parameter | Value |", "|---|---|"]
    for k, v in meta.items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 2. Construct summary", "", f"- Final sequence length: {report['construct_summary']['final_sequence_length_bp']} bp", f"- GC content: {report['construct_summary']['gc_content_percent']:.2f}%", f"- Cloning method: {report['construct_summary']['cloning_method']}", f"- Vector suggestion: {report['construct_summary']['vector_suggestion']}", "", "| Type | Name | Length | Source |", "|---|---|---|---|"]
    for e in report["elements"]:
        lines.append(f"| {e['Type']} | {e['Name']} | {e['Length (bp)']} | {e['Source']} |")
    lines += ["", "## 3. Primer design summary", "", f"- Quality Grade: {primer_quality['quality_grade']}", f"- Selected target Tm: {_na(primer_quality['selected_target_tm'])} °C" if primer_quality['selected_target_tm'] is not None else "- Selected target Tm: Not set", f"- Review plan summary: {_na(primer_quality['best_plan_summary'])}"]
    assembly_plan = report.get("step4_assembly_plan_summary") or {}
    if assembly_plan:
        lines += [
            "",
            "### Assembly plan summary",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Assembly method | {_na(assembly_plan.get('assembly_method'))} |",
            f"| Insert length | {_na(assembly_plan.get('insert_length'), '—')} bp |" if assembly_plan.get("insert_length") is not None else "| Insert length | — |",
            f"| Expected product size | {_na(assembly_plan.get('expected_product_size'), '—')} bp |" if assembly_plan.get("expected_product_size") is not None else "| Expected product size | — |",
            f"| Final construct length | {_na(assembly_plan.get('final_construct_length'), '—')} bp |" if assembly_plan.get("final_construct_length") is not None else "| Final construct length | — |",
            f"| Host | {_na(assembly_plan.get('host'))} |",
            f"| Vector / backbone name | {_na(assembly_plan.get('vector_backbone_name') or assembly_plan.get('vector_backbone'))} |",
            f"| Backbone source | {_na(assembly_plan.get('backbone_source'), '—')} |",
            f"| Vector / backbone | {_na(assembly_plan.get('vector_backbone'))} |",
            f"| Review status | {_na(assembly_plan.get('readiness_status'), 'Not set')} |",
            f"| Warning level | {_na(assembly_plan.get('warning_level'), 'none')} |",
            f"| Review notes | {' | '.join(str(reason) for reason in (assembly_plan.get('readiness_reasons') or [])) or 'None'} |",
            f"| Primer count | {_na(assembly_plan.get('primer_count'), '0')} |",
            f"| Warning count | {_na(assembly_plan.get('warning_count'), '0')} |",
            f"| Quality summary | {_na(assembly_plan.get('quality_summary'), 'Not available')} |",
            f"| Review plan summary | {_na(assembly_plan.get('best_plan_summary'), 'Not available')} |",
        ]
    if primer_quality["quality_reasons"]:
        lines.append(f"- Quality Reasons: {' | '.join(primer_quality['quality_reasons'])}")
    if primer_quality["pair_warnings"]:
        lines.append(f"- Pair warnings / risk summary: {' | '.join(primer_quality['pair_warnings'])}")
    lines.append(f"- Primer risk counts: Recommended {primer_risk['recommended_count']}, Usable with Risk {primer_risk['usable_with_risk_count']}, Not Recommended {primer_risk['not_recommended_count']}")
    if primer_quality["structured_results"]:
        lines += ["", "### Structured primer result summary", "", "| Design | Grade | Score | Product size | Target Tm | Tm gap | Heterodimer risk |", "|---|---|---|---|---|---|---|"]
        for item in primer_quality["structured_results"]:
            lines.append(f"| {item['name']} | {item['quality_grade']} | {_na(item['quality_score'], '—')} | {_na(item['product_size'], '—')} | {_na(item['target_tm'], '—')} | {_na(item['tm_gap'], '—')} | {item['heterodimer_risk']} |")
    lines += ["", "| Name | Sequence (5'→3') | Length | Tm | Role |", "|---|---|---|---|---|"]
    if report["primers"]:
        for p in report["primers"]:
            primer_seq = p["Sequence (5'→3')"]
            lines.append(f"| {p['Name']} | `{primer_seq}` | {p['Length']} | {p['Tm']} | {p['Role']} |")
    else:
        lines.append("| — | — | — | — | — |")
    conclusion = validation_results_data["final_conclusion"]
    lines += ["", "## 4. Validation summary", "", f"- Final validation conclusion: {conclusion['title']}", f"- Validation summary: {conclusion['summary']}", f"- Primer risk counts: Recommended {primer_risk['recommended_count']}, Usable with Risk {primer_risk['usable_with_risk_count']}, Not Recommended {primer_risk['not_recommended_count']}", f"- Affected fragments: {', '.join(primer_risk['affected_fragments']) if primer_risk['affected_fragments'] else 'None'}", f"- Top risk reasons: {' | '.join(primer_risk['top_risk_reasons']) if primer_risk['top_risk_reasons'] else 'None'}", "", "| Severity | Code | Title | Why | Suggested Review Action |", "|---|---|---|---|---|"]
    if validation_results_data["issue_list"]:
        for item in validation_results_data["issue_list"]:
            lines.append(f"| {item['Severity']} | {item['Code']} | {item['Title']} | {item['Why']} | {item['Fix']} |")
    else:
        lines.append("| — | — | No validation issues recorded | — | — |")
    lines += ["", "## 5. Export review status", "", f"- Documentation export status: {export_summary['recommendation']}", f"- Why / rationale: {export_summary['conclusion']}", f"- Action / next step: {export_summary['action']}", f"- Critical count: {export_summary['critical_count']}", f"- Warning count: {export_summary['warning_count']}", f"- Primer high-risk count: {export_summary['primer_high_risk_count']}", f"- Usable-with-risk primer count: {export_summary['primer_review_count']}", f"- Primer action-required count: {export_summary.get('primer_action_required_count', export_summary['primer_high_risk_count'] + export_summary['primer_review_count'])}", f"- Affected fragments: {', '.join(export_summary['affected_fragments']) if export_summary['affected_fragments'] else 'None'}"]
    available_formats = export_formats.get("available_formats") or []
    if available_formats:
        lines += ["", "### Export formats", "", "| Format | File name | Status | Use case |", "|---|---|---|---|"]
        for item in available_formats:
            status_text = item.get('display_status') or item['status']
            lines.append(f"| {item['label']} | {item['filename']} | {status_text} | {item['use_case']} |")
        lines.append(f"- Primary documentation format: {export_formats.get('recommended_primary_format', 'markdown')}")
    if step_alignment:
        lines += ["", "## 6. Step alignment", "", "| Step | Status | Key details |", "|---|---|---|"]
        step4 = step_alignment.get("step4") or {}
        step5 = step_alignment.get("step5") or {}
        step6 = step_alignment.get("step6") or {}
        lines.append(f"| Step 4 | {step4.get('readiness_status') or step4.get('status', 'Not set')} | Reasons: {' | '.join(step4.get('readiness_reasons') or step4.get('quality_reasons') or []) or 'None'} |")
        lines.append(f"| Step 5 | {step5.get('status', 'not_run')} | Issues: {len(step5.get('issue_list') or [])}; Affected fragments: {', '.join(step5.get('affected_fragments') or []) or 'None'} |")
        lines.append(f"| Step 6 | {step6.get('status', 'Not set')} | Action: {step6.get('action', '') or 'None'} |")
    lines += ["", "## 7. Sequence Verification Summary", ""]
    if sequence_verification.get("included"):
        if sequence_verification.get("message"):
            lines.append(str(sequence_verification["message"]))
            lines.append("")
        lines += ["| Field | Value |", "|---|---|"]
        for row in sequence_verification.get("rows") or []:
            lines.append(f"| {row.get('label', 'Field')} | {row.get('value', 'N/A')} |")
    else:
        lines.append(str(sequence_verification.get("message") or SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE))
    lines += ["", "## 8. File / export notes", ""]
    for k, v in report["file_export_notes"].items():
        lines.append(f"- {k.replace('_', ' ').capitalize()}: {v}")
    lines += ["", "## 9. Codon optimisation summary", "", "| Metric | Value |", "|---|---|"]
    for k, v in report["codon_report"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 10. Final construct sequence", "", f"**Length:** {len(seq):,} bp  ", f"**GC Content:** {_gc(seq):.2f}%", "", "```"]
    for i in range(0, len(seq), 60):
        lines.append(seq[i:i + 60])
    lines += ["```", "", "---", "", f"_Report generated by BioDesign Studio · {report['generated_at']}_"]
    return "\n".join(lines)
