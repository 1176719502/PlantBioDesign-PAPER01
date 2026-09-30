# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
assembly.py  --  Gibson Assembly simulation and primer design utilities.
No Streamlit UI. No session_state. Pure computation.

Exports:
    simulate_gibson(seq_list, min_overlap) -> str
    calculate_tm_precise(seq) -> float
    design_gibson_primers(fragments, fragment_names, overhang_len, binding_len) -> pd.DataFrame
    format_gibson_primer_display(primer_seq, overhang_len, is_forward) -> str
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from Bio.Seq import Seq
from Bio.SeqUtils import MeltingTemp as mt

from .bio_utils import reverse_complement


def calculate_tm_precise(seq: str) -> float:
    """Nearest-neighbour Tm for the specific binding region of a primer."""
    try:
        return float(mt.Tm_NN(Seq(seq)))
    except Exception:
        gc = (seq.count("G") + seq.count("C")) / len(seq) if seq else 0
        return 64.9 + 41 * (gc - 0.5)


def simulate_gibson(seq_list: List[str], min_overlap: int = 15) -> str:
    """
    Simulate Gibson Assembly by finding overlapping ends between adjacent
    fragments and merging them.
    """
    if not seq_list:
        return ""
    assembled = seq_list[0]
    for nxt in seq_list[1:]:
        overlap = 0
        for i in range(min(len(assembled), len(nxt), 60), min_overlap - 1, -1):
            if assembled[-i:].upper() == nxt[:i].upper():
                overlap = i
                break
        assembled += nxt[overlap:]
    return assembled


def design_gibson_primers(
    fragments: List[str],
    fragment_names: Optional[List[str]] = None,
    overhang_len: int = 20,
    binding_len: int = 20,
) -> pd.DataFrame:
    """
    Design Gibson Assembly primers for a list of ordered fragments.

    Convention:
        Forward primer = upstream_overhang (lowercase) + fwd_binding (UPPERCASE)
        Reverse primer = rev_binding (UPPERCASE) + downstream_overhang (lowercase)

    Tm is calculated on the binding region only.

    Args:
        fragments:      Ordered list of DNA sequences (5 to 3).
        fragment_names: Optional display names; auto-generated if None.
        overhang_len:   Homology arm length (bp). Recommended 15-40, default 20.
        binding_len:    Specific binding region length (bp). Recommended 18-25, default 20.

    Returns:
        DataFrame with columns:
            Fragment, Fragment Length (bp), Forward Primer, Forward Tm,
            Reverse Primer, Reverse Tm, Overhang Length (bp)
    """
    if not fragments:
        return pd.DataFrame()
    if fragment_names is None:
        fragment_names = [f"Fragment_{i + 1}" for i in range(len(fragments))]

    primers = []
    for i, (frag, name) in enumerate(zip(fragments, fragment_names)):
        frag_upper = frag.upper()

        # Forward primer
        fwd_overhang = (
            fragments[i - 1].upper()[-overhang_len:].lower() if i > 0 else ""
        )
        fwd_binding = frag_upper[:binding_len]
        fwd_primer  = fwd_overhang + fwd_binding
        fwd_tm      = calculate_tm_precise(fwd_binding)

        # Reverse primer
        rev_binding  = reverse_complement(frag_upper[-binding_len:]).upper()
        rev_overhang = (
            reverse_complement(fragments[i + 1].upper()[:overhang_len]).lower()
            if i < len(fragments) - 1
            else ""
        )
        rev_primer = rev_binding + rev_overhang
        rev_tm     = calculate_tm_precise(reverse_complement(rev_binding))

        primers.append({
            "Fragment":              name,
            "Fragment Length (bp)":  len(frag),
            "Forward Primer (5->3)": fwd_primer,
            "Forward Tm (C)":        round(fwd_tm, 1),
            "Reverse Primer (5->3)": rev_primer,
            "Reverse Tm (C)":        round(rev_tm, 1),
            "Overhang Length (bp)":  overhang_len,
        })
    return pd.DataFrame(primers)


def format_gibson_primer_display(
    primer_seq: str, overhang_len: int, is_forward: bool = True
) -> str:
    """
    Format primer for display: overhang in lowercase, binding region in UPPERCASE.
    """
    if is_forward:
        if len(primer_seq) > overhang_len:
            return primer_seq[:overhang_len].lower() + primer_seq[overhang_len:].upper()
        return primer_seq.upper()
    else:
        binding_len = len(primer_seq) - overhang_len if len(primer_seq) > overhang_len else len(primer_seq)
        if binding_len > 0:
            return primer_seq[:binding_len].upper() + primer_seq[binding_len:].lower()
        return primer_seq.upper()
