"""Conservative DNA/CDS preflight checks for Sequence Tools and Wizard Step 1."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PreflightStatus = Literal["Ready for Wizard", "Needs Review", "Invalid Sequence"]

_ALLOWED_BASES = frozenset("ATGCN")
_STRONG_BASES = frozenset("ATGC")
_STOP_CODONS = frozenset(("TAA", "TAG", "TGA"))
WIZARD_MINIMUM_SEQUENCE_LENGTH = 30

_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


@dataclass(frozen=True)
class InvalidCharacter:
    """Invalid input character summary."""

    character: str
    count: int


@dataclass(frozen=True)
class SequenceInspectionResult:
    """Result of conservative DNA/CDS preflight checks."""

    original_length: int
    sequence: str
    length: int
    valid_bases: bool
    invalid_characters: list[InvalidCharacter]
    gc_percentage: float
    length_divisible_by_3: bool
    starts_with_atg: bool
    ends_with_stop_codon: bool
    stop_codon: str
    has_internal_stop_codon: bool
    internal_stop_positions: list[int]
    translated_protein_length: int | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: PreflightStatus = "Invalid Sequence"

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _sequence_lines(raw: str) -> list[str]:
    return [line.strip() for line in str(raw or "").splitlines() if not line.strip().startswith(">")]


def _normalize_sequence(raw: str) -> tuple[str, int, list[InvalidCharacter]]:
    text = str(raw or "")
    counts: dict[str, int] = {}
    bases: list[str] = []

    for line in _sequence_lines(text):
        for char in line:
            if char.isspace():
                continue
            upper = char.upper()
            if upper in _ALLOWED_BASES:
                bases.append(upper)
            else:
                counts[char] = counts.get(char, 0) + 1

    invalid = [InvalidCharacter(character=char, count=counts[char]) for char in sorted(counts)]
    return "".join(bases), len(text), invalid


def _gc_percentage(seq: str) -> float:
    strong_base_count = sum(seq.count(base) for base in _STRONG_BASES)
    if strong_base_count == 0:
        return 0.0
    return (seq.count("G") + seq.count("C")) / strong_base_count * 100


def _internal_stop_positions(seq: str) -> list[int]:
    positions: list[int] = []
    if len(seq) < 6 or len(seq) % 3 != 0 or "N" in seq:
        return positions
    for offset in range(3, len(seq) - 3, 3):
        if seq[offset:offset + 3] in _STOP_CODONS:
            positions.append(offset + 1)
    return positions


def _has_simple_repeat(seq: str) -> bool:
    if not seq:
        return False

    for base in _ALLOWED_BASES:
        if base * 10 in seq:
            return True

    for size, min_units in ((2, 8), (3, 6), (4, 5)):
        for offset in range(0, max(len(seq) - size + 1, 0)):
            motif = seq[offset:offset + size]
            if len(set(motif)) <= 1:
                continue
            if motif * min_units in seq:
                return True

    return False


def _translated_protein_length(seq: str, internal_stops: list[int]) -> int | None:
    if (
        not seq
        or "N" in seq
        or len(seq) % 3 != 0
        or not seq.startswith("ATG")
        or seq[-3:] not in _STOP_CODONS
        or internal_stops
    ):
        return None

    translated = [_CODON_TABLE.get(seq[index:index + 3], "X") for index in range(0, len(seq) - 3, 3)]
    if "X" in translated or "*" in translated:
        return None
    return len(translated)


def inspect_sequence(raw: str) -> SequenceInspectionResult:
    """Inspect a DNA sequence for basic conservative CDS readiness."""
    seq, original_length, invalid_characters = _normalize_sequence(raw)
    invalid_symbols = ", ".join(item.character for item in invalid_characters)
    gc = _gc_percentage(seq)
    length_divisible_by_3 = bool(seq) and len(seq) % 3 == 0
    starts_with_atg = seq.startswith("ATG")
    stop_codon = seq[-3:] if len(seq) >= 3 else ""
    ends_with_stop_codon = stop_codon in _STOP_CODONS
    internal_stops = _internal_stop_positions(seq)

    errors: list[str] = []
    warnings: list[str] = []

    if not seq:
        errors.append("No DNA bases were detected.")
    if invalid_characters:
        errors.append(f"Invalid character(s) detected: {invalid_symbols}.")
    if seq and len(seq) < 6:
        warnings.append("Sequence is very short for a complete CDS.")
    if seq and len(seq) < WIZARD_MINIMUM_SEQUENCE_LENGTH:
        warnings.append(
            f"Sequence is below the Wizard minimum length of {WIZARD_MINIMUM_SEQUENCE_LENGTH} bp."
        )
    if seq and not length_divisible_by_3:
        warnings.append("CDS length is not divisible by 3.")
    if seq and "N" in seq:
        warnings.append("Sequence contains N bases; ambiguous bases require review before wizard use.")
    if seq and not starts_with_atg:
        warnings.append("CDS does not start with ATG.")
    if seq and not ends_with_stop_codon:
        warnings.append("CDS does not end with TAA, TAG, or TGA.")
    if internal_stops:
        warnings.append("Internal in-frame stop codon(s) detected.")
    if seq and gc < 30.0:
        warnings.append("Low GC content detected (<30%).")
    if seq and gc > 70.0:
        warnings.append("High GC content detected (>70%).")
    if _has_simple_repeat(seq):
        warnings.append("Simple repeat or long homopolymer pattern detected.")

    protein_length = _translated_protein_length(seq, internal_stops)

    if errors:
        status: PreflightStatus = "Invalid Sequence"
    elif warnings or protein_length is None:
        status = "Needs Review"
    else:
        status = "Ready for Wizard"

    return SequenceInspectionResult(
        original_length=original_length,
        sequence=seq,
        length=len(seq),
        valid_bases=not invalid_characters,
        invalid_characters=invalid_characters,
        gc_percentage=round(gc, 1),
        length_divisible_by_3=length_divisible_by_3,
        starts_with_atg=starts_with_atg,
        ends_with_stop_codon=ends_with_stop_codon,
        stop_codon=stop_codon,
        has_internal_stop_codon=bool(internal_stops),
        internal_stop_positions=internal_stops,
        translated_protein_length=protein_length,
        warnings=warnings,
        errors=errors,
        status=status,
    )
