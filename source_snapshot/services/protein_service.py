"""
services/protein_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unified protein analysis service.

Provides a single @st.cache_resource-backed entry point for
Biopython ProteinAnalysis so the class (and its lookup tables) are
loaded into RAM only once when the app starts, not on every button click.

Public API
----------
calc_properties(seq)  -> dict   MW, pI, instability, GRAVY, aromaticity,
                                 aa_percent, length, ok, error
"""
from __future__ import annotations
import logging
from typing import Any, Dict
import streamlit as st

logger = logging.getLogger(__name__)

# ── Optional Biopython ProteinAnalysis ────────────────────────────────────
try:
    from Bio.SeqUtils.ProtParam import ProteinAnalysis as _PA
    _BIO_OK = True
except ImportError as _e:
    logger.warning("Biopython ProteinAnalysis unavailable: %s", _e)
    _BIO_OK = False
    _PA = None  # type: ignore


@st.cache_resource(show_spinner=False)
def _get_protein_analyzer():
    """
    Cache the ProteinAnalysis class (and its amino-acid parameter tables)
    so they are loaded only once per app session, not on every button click.
    Returns the ProteinAnalysis class, or None when Biopython is unavailable.
    """
    if _BIO_OK and _PA is not None:
        logger.info("[protein_service] ProteinAnalysis class loaded into @st.cache_resource.")
        return _PA
    return None


# ── Public API ────────────────────────────────────────────────────────────

def calc_properties(seq: str) -> Dict[str, Any]:
    """
    Calculate physicochemical properties of a protein sequence.

    Parameters
    ----------
    seq : str
        Plain amino-acid string (or FASTA — leading >header lines stripped).

    Returns
    -------
    dict:
        length            : int
        molecular_weight  : float  (Da)
        isoelectric_point : float
        instability_index : float
        gravy             : float
        aromaticity       : float
        aa_percent        : dict[str, float]  (0-100 %)
        ok                : bool   True when Biopython succeeded
        error             : str    message when ok=False
    """
    # Strip FASTA header lines
    lines = [l for l in seq.strip().splitlines() if not l.startswith(">")]
    clean = "".join(lines).replace(" ", "").upper()

    result: Dict[str, Any] = {"length": len(clean), "ok": False, "error": ""}

    if not clean:
        result["error"] = "Empty sequence after cleaning."
        return result

    PA = _get_protein_analyzer()
    if PA is not None:
        try:
            pa = PA(clean)
            result.update({
                "molecular_weight":  round(pa.molecular_weight(), 2),
                "isoelectric_point": round(pa.isoelectric_point(), 2),
                "instability_index": round(pa.instability_index(), 2),
                "gravy":             round(pa.gravy(), 4),
                "aromaticity":       round(pa.aromaticity(), 4),
                "aa_percent":        {k: round(v * 100, 2)
                                      for k, v in pa.amino_acids_percent.items()},
                "ok": True,
            })
        except Exception as exc:
            result["error"] = str(exc)
            logger.warning("ProteinAnalysis failed: %s", exc)
    else:
        result["error"] = (
            "Biopython not installed. Run: pip install biopython"
        )

    return result
