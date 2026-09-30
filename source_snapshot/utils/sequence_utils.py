# utils/sequence_utils.py
"""
Shared sequence utility functions.

Previously ~200 lines of identical code were duplicated between
views/Design.py and views/Data.py. This module is the single source
of truth. Import from here everywhere else.

Public API
----------
clean_sequence(raw)                         -> str
validate_sequence(seq)                      -> tuple[bool, str]
compute_gc(seq)                             -> float
looks_like_sequence(text)                   -> bool
parse_fasta_bytes(raw_bytes, part_type)     -> tuple[list, list]

class ParsedRecord
"""
from __future__ import annotations

import re as _re

# Module-level compiled patterns -- built once at import time
_RE_STRIP_WS_DIGITS = _re.compile(r"[\s0-9]")
_RE_NON_ATCGN = _re.compile(r"[^ATCGatcgNn]")
_VALID_BASES: frozenset = frozenset("ATCGN")
# Reverse-complement table built once
_RC_TABLE = str.maketrans("ATCGatcg", "TAGCtagc")


import io
import re


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def clean_sequence(raw: str) -> str:
    """Strip whitespace and digits, uppercase."""
    return _RE_STRIP_WS_DIGITS.sub("", raw).upper()


def validate_sequence(seq: str) -> tuple[bool, str]:
    """
    Return (is_valid, error_message).
    Only A T C G N are accepted.
    """
    if not seq:
        return False, "Sequence must not be empty."
    invalid = sorted(set(seq) - frozenset("ATCGN"))
    if invalid:
        return False, (
            f"Invalid characters: {', '.join(invalid)}. "
            "Only A, T, C, G, N are permitted."
        )
    return True, ""


def compute_gc(seq: str) -> float:
    """Return GC percentage (0-100). Returns 0.0 for empty input."""
    if not seq:
        return 0.0
    return (seq.count("G") + seq.count("C")) / len(seq) * 100


# ---------------------------------------------------------------------------
# Low-level sequence math (single source of truth for the whole project)
# ---------------------------------------------------------------------------

def rc(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""
    return seq.upper().translate(_RC_TABLE)[::-1]


def gc(seq: str) -> float:
    """Return GC content as a percentage (0-100). Returns 0.0 for empty input."""
    return compute_gc(seq)


def tm(seq: str) -> float:
    """Melting temperature (°C) using best available backend.

    Priority:
    1. core.primer_utils.calc_tm  (Nearest-Neighbor, most accurate)
    2. Biopython MeltingTemp.Tm_NN
    3. Wallace rule fallback (2*AT + 4*GC)
    """
    try:
        from core.primer_utils import calc_tm as _p3_tm
        return _p3_tm(seq)
    except Exception:
        pass
    try:
        from Bio.Seq import Seq
        from Bio.SeqUtils import MeltingTemp as _mt
        return float(_mt.Tm_NN(Seq(seq)))
    except Exception:
        pass
    # Wallace rule
    s = seq.upper()
    gc_frac = compute_gc(s) / 100
    return round(2 * (1 - gc_frac) * len(s) + 4 * gc_frac * len(s), 1)


def clean_dna(seq: str) -> tuple[str, list]:
    """Strip non-ATCG characters. Returns (cleaned_seq, warnings)."""
    cleaned = _RE_NON_ATCGN.sub("", seq).upper()
    warnings_out = []
    removed = len(seq) - len(cleaned)
    if removed > 0:
        warnings_out.append(f"{removed} non-DNA characters removed")
    return cleaned, warnings_out


def looks_like_sequence(text: str) -> bool:
    """
    Return True when text looks like a DNA fragment query:
    at least 4 characters, all ATCGN.
    """
    cleaned = re.sub(r"\s", "", text).upper()
    return len(cleaned) >= 4 and all(c in "ATCGN" for c in cleaned)


# ---------------------------------------------------------------------------
# FASTA parsing
# ---------------------------------------------------------------------------

class ParsedRecord:
    """
    Intermediate container for one FASTA record before DB commit.

    Attributes
    ----------
    index        : 1-based record index in the file
    name         : sequence id from FASTA header
    description  : rest of FASTA header after the id
    sequence     : cleaned, uppercase DNA string
    part_type    : user-supplied part type label
    length_bp    : len(sequence)
    gc_content   : GC percentage
    seq_error    : non-empty when sequence failed validation
    is_duplicate : True when name already exists in the database
    """

    __slots__ = (
        "index", "name", "description", "sequence", "part_type",
        "length_bp", "gc_content", "seq_error", "is_duplicate",
    )

    def __init__(
        self,
        index: int,
        name: str,
        description: str,
        sequence: str,
        part_type: str,
    ) -> None:
        self.index        = index
        self.name         = name
        self.description  = description
        self.sequence     = sequence
        self.part_type    = part_type
        self.length_bp    = len(sequence)
        self.gc_content   = compute_gc(sequence)
        self.seq_error    = ""
        self.is_duplicate = False


# ---------------------------------------------------------------------------
# Bio computation helpers (moved from views/Design.py)
# ---------------------------------------------------------------------------

def reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence.

    Uses the module-level _RC_TABLE -- no Biopython import needed.
    """
    return seq.upper().translate(_RC_TABLE)[::-1]


def design_primers(
    seq: str,
    overhang_f: str = "",
    overhang_r: str = "",
    tm_target: float = 60.0,
    min_len: int = 18,
    max_len: int = 30,
) -> dict:
    """Simple Tm-based primer design using the Wallace rule."""

    def _tm(s: str) -> float:
        s = s.upper()
        return 2.0 * (s.count("A") + s.count("T")) + 4.0 * (s.count("G") + s.count("C"))

    fwd_bind = seq[:min_len]
    rev_bind = reverse_complement(seq[-min_len:])

    for length in range(min_len, max_len + 1):
        if _tm(seq[:length]) >= tm_target:
            fwd_bind = seq[:length]
            break
    for length in range(min_len, max_len + 1):
        seg = seq[-length:]
        if _tm(seg) >= tm_target:
            rev_bind = reverse_complement(seg)
            break

    return {
        "forward": overhang_f + fwd_bind,
        "reverse": overhang_r + rev_bind,
        "fwd_tm": round(_tm(fwd_bind), 1),
        "rev_tm": round(_tm(rev_bind), 1),
    }


def build_expression_cassette(
    promoter: str,
    gene: str,
    terminator: str,
    add_kozak: bool = False,
    add_his_tag: bool = False,
    add_start: bool = True,
    add_stop: bool = True,
) -> str:
    """Assemble a human-readable expression cassette description string."""
    parts = [f"[{promoter}]"]
    if add_kozak:
        parts.append("[Kozak: GCCACCATG]")
    if add_start and not add_kozak:
        parts.append("[ATG]")
    if add_his_tag:
        parts.append("[6xHis: CATCACCATCACCATCAC]")
    parts.append(f"[{gene[:30]}{'...' if len(gene) > 30 else ''}]")
    if add_stop:
        parts.append("[Stop: TAA]")
    parts.append(f"[{terminator}]")
    return " → ".join(parts)


# ---------------------------------------------------------------------------
# FASTA parsing
# ---------------------------------------------------------------------------

def parse_fasta_bytes(
    raw_bytes: bytes,
    part_type: str,
) -> tuple[list[ParsedRecord], list[str]]:
    """
    Parse raw FASTA bytes using Bio.SeqIO (Biopython 1.81+).

    Returns
    -------
    records      : list[ParsedRecord]
    parse_errors : list[str]  (non-fatal warnings / hard errors)
    """
    from Bio import SeqIO  # lazy import -- Biopython optional dep

    parse_errors: list[str] = []

    # --- decode bytes ---
    try:
        file_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            file_text = raw_bytes.decode("latin-1")
            parse_errors.append(
                "File decoded as Latin-1 (not UTF-8). "
                "Non-ASCII chars in headers may appear garbled."
            )
        except Exception:
            return [], ["File encoding error: could not decode the uploaded file."]

    # --- parse FASTA ---
    handle = io.StringIO(file_text)
    try:
        bio_records = list(SeqIO.parse(handle, "fasta"))
    except Exception as exc:
        return [], [f"BioPython parsing error: {exc}"]

    if not bio_records:
        return [], ["No FASTA records found -- file may be empty or not FASTA format."]

    # --- build ParsedRecord list ---
    records: list[ParsedRecord] = []
    for idx, bio_rec in enumerate(bio_records, start=1):
        name = bio_rec.id or f"unnamed_{idx}"
        raw_desc = bio_rec.description
        if raw_desc.startswith(name):
            raw_desc = raw_desc[len(name):].strip()
        raw_seq = str(bio_rec.seq)
        if not raw_seq:
            parse_errors.append(f"Record {idx} '{name}': sequence is empty -- skipped.")
            continue
        seq_clean = clean_sequence(raw_seq)
        rec = ParsedRecord(idx, name, raw_desc, seq_clean, part_type)
        ok, err = validate_sequence(seq_clean)
        if not ok:
            rec.seq_error = f"Record {idx} '{name}': {err}"
        records.append(rec)

    return records, parse_errors
