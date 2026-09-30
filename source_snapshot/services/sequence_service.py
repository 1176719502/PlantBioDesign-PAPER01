"""
services/sequence_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unified sequence analysis service.
All algorithms delegated to existing core modules — no new logic here.

Public API
----------
clean(seq)              -> (str, list[str])
gc_content(seq)         -> float
get_tm(seq)             -> float  (Nearest-Neighbour via Biopython)
find_orfs(seq, min_len) -> pd.DataFrame
reverse_complement(seq) -> str
translate(seq)          -> str
six_frame(seq)          -> dict[str, str]
blast(seq, db, ...)     -> dict  {success, data, error, rid}

Note: NCBI Entrez fetch (fetch_by_accession) has been removed.
      Use local file upload or Parts Registry import instead.
"""
from __future__ import annotations
import logging
import re
from typing import Dict, List, Tuple
import pandas as pd

from services.dna_sequence_analysis import normalize_sequence_text

logger = logging.getLogger(__name__)

# ── Sequence utilities (components/design_modules/bio_utils) ──────────────
try:
    from components.design_modules.bio_utils import (
        gc_content as _gc,
        get_tm as _tm,
        find_orfs as _find_orfs,
        reverse_complement as _rc,
        translate_seq as _translate,
        six_frame_translation as _six_frame,
    )
    _SEQ_OK = True
except ImportError as _e:
    logger.warning("bio_utils unavailable: %s", _e)
    _SEQ_OK = False

try:
    from core.assembly_utils import clean_dna_sequence as _clean
    _CLEAN_OK = True
except ImportError:
    _CLEAN_OK = False

# BLAST integration is intentionally dormant in V1 reset mode.
_BLAST_OK = False


def clean(seq: str) -> Tuple[str, List[str]]:
    """Clean a raw DNA string. Returns (cleaned_seq, warnings)."""
    if not seq:
        return "", ["Input is empty."]

    cleaned = re.sub(r"[^ATCGNatcgn]", "", seq).upper()
    warnings: List[str] = []
    removed = len(seq) - len(cleaned)
    if removed > 0:
        warnings.append(f"{removed} non-DNA character(s) removed")
    if not cleaned:
        warnings.append("Sequence is empty after cleaning.")
    return cleaned, warnings


def gc_content(seq: str) -> float:
    """Return GC% (0-100) for a DNA sequence."""
    if _SEQ_OK:
        return _gc(seq)
    s = seq.upper()
    return (s.count("G") + s.count("C")) / len(s) * 100 if s else 0.0


def get_tm(seq: str) -> float:
    """Return Nearest-Neighbour Tm (degC). Falls back to Wallace formula."""
    if _SEQ_OK:
        return _tm(seq)
    s = seq.upper()
    gc = s.count("G") + s.count("C")
    return float(64.9 + 41 * (gc - 16.4) / len(s)) if s else 0.0


def find_orfs(seq: str, min_len: int = 30) -> pd.DataFrame:
    """Return DataFrame of ORFs in the forward strand."""
    if _SEQ_OK:
        return _find_orfs(seq, min_len)
    return pd.DataFrame(columns=["Frame", "Start", "End", "Length (bp)"])


def reverse_complement(seq: str) -> str:
    """Return reverse complement of a DNA sequence."""
    if _SEQ_OK:
        return _rc(seq)
    comp = str.maketrans("ATCGatcg", "TAGCtagc")
    return seq.translate(comp)[::-1]


def translate(seq: str) -> str:
    """Translate a DNA sequence to amino acids."""
    if _SEQ_OK:
        return _translate(seq)
    try:
        from Bio.Seq import Seq
        s = Seq(seq)
        return str(s[: len(s) - len(s) % 3].translate())
    except Exception as exc:
        return f"Translation error: {exc}"


def translate_frame(
    seq: str,
    strand: str = "+",
    frame: int = 1,
    stop_rule: str = "include",
) -> str:
    """Translate one explicitly selected strand/frame via the shared service."""
    normalized = normalize_sequence_text(seq)
    if strand not in {"+", "-", "forward", "reverse"}:
        raise ValueError("strand must be '+'/'forward' or '-'/'reverse'")
    if frame not in (1, 2, 3):
        raise ValueError("frame must be 1, 2, or 3")
    if stop_rule not in {"include", "trim_terminal"}:
        raise ValueError("stop_rule must be 'include' or 'trim_terminal'")
    oriented = normalized if strand in {"+", "forward"} else reverse_complement(normalized)
    translated = translate(oriented[frame - 1 :])
    if stop_rule == "trim_terminal" and translated.endswith("*"):
        return translated[:-1]
    return translated


def normalized_orfs(seq: str, min_len: int = 30) -> pd.DataFrame:
    """Expose only stable forward ORF fields from the existing ORF service."""
    normalized = normalize_sequence_text(seq)
    source = find_orfs(normalized, min_len=min_len)
    if source.empty:
        return pd.DataFrame(columns=[
            "strand", "frame", "nucleotide_start", "nucleotide_end",
            "nucleotide_length", "amino_acid_length",
        ])
    rows = []
    for record in source.to_dict("records"):
        length = int(record["Length (bp)"])
        rows.append({
            "strand": "+",
            "frame": int(record["Frame"]),
            "nucleotide_start": int(record["Start"]),
            "nucleotide_end": int(record["End"]),
            "nucleotide_length": length,
            "amino_acid_length": max(0, length // 3 - 1),
        })
    return pd.DataFrame(rows)


def six_frame(seq: str) -> Dict[str, str]:
    """Return all six reading-frame translations as {'+1' ... '-3': aa_str}."""
    if _SEQ_OK:
        return _six_frame(seq)
    return {}


def seq_hash(seq: str) -> str:
    """Return a stable SHA-256 hex digest for a DNA sequence string.
    Used by wizard steps to detect upstream sequence changes.
    Returns empty string for empty input.
    """
    if not seq:
        return ""
    import hashlib
    return hashlib.sha256(seq.encode("utf-8")).hexdigest()


def primer_gc(seq: str) -> float:
    """Return GC% of a primer sequence (ignores non-ATCG characters)."""
    if not seq:
        return 0.0
    s = seq.upper()
    gc = s.count("G") + s.count("C")
    atcg = sum(s.count(b) for b in "ATCG")
    return gc / atcg * 100 if atcg else 0.0


_OFFLINE_MSG = (
    "BLAST requires a network connection. "
    "core.bio_tools could not be imported — "
    "install requests: pip install requests"
)


def blast(
    sequence: str,
    database: str = "nr",
    program: str = "blastp",
    max_hits: int = 10,
    timeout: int = 120,
) -> Dict:
    """
    Run NCBI BLAST and return results dict.

    Parameters
    ----------
    sequence : str
        Query sequence.
    database : str
        NCBI database display label or raw name (e.g. 'NCBI nr (non-redundant)', 'nt').
    program : str
        'blastp' for protein-vs-protein, 'blastn' for DNA-vs-DNA.
    max_hits : int
        Maximum hits to return.
    timeout : int
        Polling timeout in seconds.

    Returns
    -------
    dict:
        success : bool
        data    : pd.DataFrame  (Accession, Description, Identity %, E-value,
                                 Bit Score, Align Length)
        error   : str           (empty on success)
        rid     : str           (NCBI Request ID)
    """
    if not _BLAST_OK:
        logger.info("BLAST is dormant in current V1 reset mode.")
        return {"success": False, "data": pd.DataFrame(),
                "error": _OFFLINE_MSG, "rid": ""}
    return {"success": False, "data": pd.DataFrame(),
            "error": _OFFLINE_MSG, "rid": ""}
