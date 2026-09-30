"""Documentation-only helpers for Lab Tools computational previews.

The functions in this module intentionally produce summaries and text artifacts only.
They do not provide wet-lab protocols, certify experimental readiness, predict yield,
or optimize pathways.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.tool_artifact_service import TOOL_ARTIFACT_BOUNDARY_LABEL


BOUNDARY_COPY = (
    "These tools create computational previews and documentation artifacts only.\n"
    "They do not certify experimental readiness.\n"
    "They do not predict yield.\n"
    "They do not optimize pathways.\n"
    "They do not provide wet-lab protocols.\n"
    "They do not certify cloning, PCR, gel, or expression success.\n"
    "Review primer and export decisions in Expression Wizard Step 5/Step 6. "
    "Boundary phrases: does not certify experimental readiness; does not predict yield; "
    "does not optimize pathways; does not provide wet-lab protocols; "
    "does not certify cloning, PCR, gel, or expression success."
)

_VALID_DNA = set("ACGTN")


@dataclass(frozen=True)
class LabPreview:
    """Structured result for a Lab Tools preview."""

    title: str
    status: str
    summary: dict[str, object]
    boundary: str = BOUNDARY_COPY


def clean_preview_sequence(sequence: str | None) -> str:
    """Return uppercase DNA-like characters used for computational previews."""
    return "".join(ch for ch in str(sequence or "").upper() if ch in _VALID_DNA)


def cloning_preview_summary(
    *,
    insert_sequence: str | None,
    vector_name: str | None = "Vector/backbone not specified",
    assembly_method: str | None = "Assembly method not specified",
    insert_name: str | None = "Insert",
) -> LabPreview:
    insert = clean_preview_sequence(insert_sequence)
    method = (assembly_method or "Assembly method not specified").strip() or "Assembly method not specified"
    vector = (vector_name or "Vector/backbone not specified").strip() or "Vector/backbone not specified"
    name = (insert_name or "Insert").strip() or "Insert"
    if not insert:
        return LabPreview(
            title="Cloning Preview",
            status="invalid_input",
            summary={
                "message": "No valid insert sequence was provided.",
                "assembly_method": method,
                "insert_name": name,
                "insert_length_bp": 0,
                "vector": vector,
                "preview_type": "computational preview only",
            },
        )
    return LabPreview(
        title="Cloning Simulation Preview",
        status="ok",
        summary={
            "input_summary": f"{name}: {len(insert)} bp insert; vector: {vector}; method: {method}",
            "insert_name": name,
            "insert_length_bp": len(insert),
            "vector": vector,
            "assembly_method": method,
            "preview_type": "computational preview only",
        },
    )


def pcr_preview_summary(
    *,
    template_sequence: str | None,
    forward_primer: str | None,
    reverse_primer: str | None,
    forward_name: str | None = "Forward primer",
    reverse_name: str | None = "Reverse primer",
    expected_amplicon_length: int | None = None,
) -> LabPreview:
    template = clean_preview_sequence(template_sequence)
    fwd = clean_preview_sequence(forward_primer)
    rev = clean_preview_sequence(reverse_primer)
    if not template or not fwd or not rev:
        return LabPreview(
            title="PCR Preview",
            status="invalid_input",
            summary={
                "message": "Template, forward primer, and reverse primer are required for a PCR preview.",
                "target_length_bp": len(template),
                "forward_primer_name": forward_name or "Forward primer",
                "reverse_primer_name": reverse_name or "Reverse primer",
                "preview_type": "primer-target preview only",
            },
        )
    amplicon = int(expected_amplicon_length or 0)
    if amplicon <= 0:
        amplicon = len(template)
    return LabPreview(
        title="PCR Simulation Preview",
        status="ok",
        summary={
            "forward_primer_name": forward_name or "Forward primer",
            "reverse_primer_name": reverse_name or "Reverse primer",
            "forward_primer_length_bp": len(fwd),
            "reverse_primer_length_bp": len(rev),
            "target_length_bp": len(template),
            "expected_amplicon_summary": f"Expected amplicon preview: {amplicon} bp if both primers map as shown.",
            "does_not_certify": "This preview does not certify PCR or expression success and does not replace Expression Wizard Step 5 primer review checks.",
            "preview_type": "primer-target preview only",
        },
    )


def virtual_gel_fragment_summary(fragments_bp: Iterable[int | str] | None) -> LabPreview:
    sizes: list[int] = []
    for value in fragments_bp or []:
        try:
            size = int(value)
        except (TypeError, ValueError):
            continue
        if size > 0:
            sizes.append(size)
    if not sizes:
        return LabPreview(
            title="Virtual Gel Preview",
            status="invalid_input",
            summary={
                "message": "At least one positive fragment size is required.",
                "fragment_count": 0,
                "preview_type": "fragment size visualization preview only",
            },
        )
    ordered = sorted(sizes, reverse=True)
    return LabPreview(
        title="Virtual Gel Preview",
        status="ok",
        summary={
            "fragment_count": len(ordered),
            "fragment_sizes_bp": ordered,
            "fragment_table": [{"Fragment": idx + 1, "Size (bp)": bp} for idx, bp in enumerate(ordered)],
            "textual_gel_preview": " | ".join(f"{bp} bp" for bp in ordered),
            "preview_type": "fragment size visualization preview only",
        },
    )


def sequence_export_preview(
    *,
    sequence: str | None,
    name: str | None = "sequence_preview",
    fmt: str | None = "FASTA",
) -> LabPreview:
    seq = clean_preview_sequence(sequence)
    label = (name or "sequence_preview").strip() or "sequence_preview"
    normalized_fmt = (fmt or "FASTA").strip().lower()
    if not seq:
        return LabPreview(
            title="Sequence Export Preview",
            status="invalid_input",
            summary={
                "message": "A valid sequence is required before preparing an export preview.",
                "format": fmt or "FASTA",
                "preview_type": "documentation artifact",
            },
        )
    if normalized_fmt == "fasta":
        artifact = f">{label}\n" + "\n".join(seq[i : i + 60] for i in range(0, len(seq), 60))
    elif "genbank" in normalized_fmt or normalized_fmt in {"gb", "gbk"}:
        artifact = f"LOCUS       {label[:16]:<16} {len(seq):>7} bp    DNA     linear\nORIGIN\n        1 {seq.lower()}\n//"
    else:
        artifact = seq
    return LabPreview(
        title="Sequence Export Preview",
        status="ok",
        summary={
            "sequence_name": label,
            "sequence_length_bp": len(seq),
            "format": fmt or "FASTA",
            "artifact_preview": artifact,
            "does_not_bypass": "This documentation artifact does not bypass Expression Wizard Step 6 export review rules.",
            "preview_type": "documentation artifact",
        },
    )


_LAB_ARTIFACT_TYPES = {
    "cloning": "lab_tools_cloning_preview",
    "pcr": "lab_tools_pcr_preview",
    "virtual_gel": "lab_tools_virtual_gel_preview",
    "sequence_export": "lab_tools_sequence_export_preview",
}


def lab_preview_artifact_payload(preview: LabPreview, *, preview_kind: str, inputs: dict[str, object] | None = None) -> dict[str, object]:
    """Build a documentation-only artifact payload from a Lab Tools preview."""
    artifact_type = _LAB_ARTIFACT_TYPES.get(str(preview_kind or "").strip())
    if not artifact_type:
        return {}
    summary = preview.summary if isinstance(preview.summary, dict) else {}
    if not summary:
        return {}
    return {
        "artifact_type": artifact_type,
        "title": preview.title,
        "source_module": "Lab Tools",
        "summary": summary,
        "inputs": inputs if isinstance(inputs, dict) else {},
        "preview_status": preview.status,
        "boundary_copy": preview.boundary,
        "boundary_label": TOOL_ARTIFACT_BOUNDARY_LABEL,
    }
