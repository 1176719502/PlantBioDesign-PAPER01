"""
Documentation-only helpers for Protein Structure Analysis.

This module intentionally limits outputs to sequence-derived protein
properties and source-state validation for selected/uploaded PDB structures.
It does not predict or validate folding, function, expression success, or
experimental readiness.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict

from services.tool_artifact_service import TOOL_ARTIFACT_BOUNDARY_LABEL

VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")
_AMINO_ACID_WEIGHTS = {
    "A": 89.09,
    "R": 174.20,
    "N": 132.12,
    "D": 133.10,
    "C": 121.15,
    "E": 147.13,
    "Q": 146.15,
    "G": 75.07,
    "H": 155.16,
    "I": 131.17,
    "L": 131.17,
    "K": 146.19,
    "M": 149.21,
    "F": 165.19,
    "P": 115.13,
    "S": 105.09,
    "T": 119.12,
    "W": 204.23,
    "Y": 181.19,
    "V": 117.15,
}
_WATER_MASS = 18.015
_PDB_ID_RE = re.compile(r"^[A-Za-z0-9]{4}$")
_PDB_RECORD_PREFIXES = (
    "ATOM",
    "HETATM",
    "HEADER",
    "TITLE",
    "COMPND",
    "SOURCE",
    "MODEL",
    "CRYST1",
)

BOUNDARY_COPY = (
    "These tools create computational previews and documentation artifacts only. "
    "They do not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab protocols. "
    "Structure Analysis does not validate folding, function, expression, or experimental readiness. "
    "Use Expression Wizard Step 6 for construct export review. "
    "This module is documentation-only and review-only."
)


def clean_protein_sequence(raw_sequence: str) -> str:
    """Remove FASTA headers and whitespace, preserving non-whitespace residues for validation."""
    lines = []
    for line in (raw_sequence or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        lines.append(stripped)
    return re.sub(r"\s+", "", "".join(lines)).upper()


def invalid_residues(sequence: str) -> list[str]:
    """Return sorted residue symbols outside the standard 20 amino-acid alphabet."""
    return sorted({residue for residue in sequence if residue not in VALID_AA})


def fallback_molecular_weight(sequence: str) -> float:
    """Estimate molecular weight in Da from residue masses minus peptide-bond water loss."""
    if not sequence:
        return 0.0
    total = sum(_AMINO_ACID_WEIGHTS[residue] for residue in sequence)
    if len(sequence) > 1:
        total -= (len(sequence) - 1) * _WATER_MASS
    return round(total, 2)


def calculate_documentation_properties(raw_sequence: str) -> Dict[str, Any]:
    """Calculate review-only, sequence-derived protein properties."""
    clean = clean_protein_sequence(raw_sequence)
    result: Dict[str, Any] = {
        "ok": False,
        "sequence": clean,
        "length": len(clean),
        "aa_counts": dict(Counter(clean)),
        "invalid_residues": invalid_residues(clean),
        "error": "",
    }

    if not clean:
        result["error"] = "Enter an amino acid sequence or FASTA record."
        return result

    if result["invalid_residues"]:
        result["error"] = "Sequence contains unsupported amino acid symbols."
        return result

    result["molecular_weight"] = fallback_molecular_weight(clean)

    try:
        from services.protein_service import calc_properties

        biopython_props = calc_properties(clean)
        if biopython_props.get("ok"):
            for key in (
                "molecular_weight",
                "isoelectric_point",
                "instability_index",
                "gravy",
                "aromaticity",
                "aa_percent",
            ):
                if key in biopython_props:
                    result[key] = biopython_props[key]
    except Exception:
        pass

    result["ok"] = True
    return result


def pdb_id_source_state(pdb_id: str) -> Dict[str, str]:
    """Validate a selected RCSB PDB ID and describe its documentation source."""
    pid = (pdb_id or "").strip().upper()
    if not pid:
        return {"ok": "false", "pdb_id": "", "source": "RCSB PDB", "message": "Enter a 4-character PDB ID."}
    if not _PDB_ID_RE.match(pid):
        return {"ok": "false", "pdb_id": pid, "source": "RCSB PDB", "message": "PDB ID must be 4 alphanumeric characters."}
    return {"ok": "true", "pdb_id": pid, "source": "RCSB PDB", "message": "Structure source = RCSB PDB."}


def uploaded_pdb_source_state(pdb_text: str) -> Dict[str, str]:
    """Validate an uploaded PDB text blob without sending it to an external service."""
    text = pdb_text or ""
    if not text.strip():
        return {"ok": "false", "source": "uploaded PDB file", "message": "Uploaded PDB file is empty."}
    has_pdb_record = any(line.startswith(_PDB_RECORD_PREFIXES) for line in text.splitlines())
    if not has_pdb_record:
        return {"ok": "false", "source": "uploaded PDB file", "message": "Uploaded file does not look like a supported PDB text file."}
    return {"ok": "true", "source": "uploaded PDB file", "message": "Structure source = uploaded PDB file."}


def structure_analysis_artifact_payload(
    *,
    protein_sequence: str,
    structure_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a documentation-only artifact payload for the current structure preview."""
    properties = calculate_documentation_properties(protein_sequence or "")
    source = dict(structure_source) if isinstance(structure_source, dict) else {}
    if not properties.get("ok") and not source:
        return {}
    source_label = str(source.get("source") or "structure source not selected").strip()
    length = properties.get("length", 0)
    summary_parts = []
    if properties.get("ok"):
        summary_parts.append(f"Sequence-derived protein property review for {length} aa.")
    if source_label:
        summary_parts.append(f"Structure source: {source_label}.")
    return {
        "artifact_type": "protein_structure_analysis",
        "title": "Protein Structure Analysis Review Record",
        "source_module": "Structure Analysis",
        "summary": " ".join(summary_parts).strip() or "Protein structure analysis documentation review record.",
        "sequence_properties": properties,
        "structure_source": source,
        "boundary_copy": BOUNDARY_COPY,
        "boundary_label": TOOL_ARTIFACT_BOUNDARY_LABEL,
    }
