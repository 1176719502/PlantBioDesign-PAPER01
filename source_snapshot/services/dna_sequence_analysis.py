"""Pure, deterministic DNA sequence analysis with layered validity semantics.

The analysis layer accepts the complete DNA IUPAC alphabet. Construct
eligibility is narrower and accepts only non-empty A/C/G/T sequences. Invalid
character positions are zero-based offsets in ``normalized_sequence``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


DNA_IUPAC_ANALYSIS_ALPHABET = frozenset("ACGTRYSWKMBDHVN")
DNA_CONSTRUCT_READY_ALPHABET = frozenset("ACGT")
DNA_IUPAC_AMBIGUOUS_ALPHABET = (
    DNA_IUPAC_ANALYSIS_ALPHABET - DNA_CONSTRUCT_READY_ALPHABET
)
RNA_IUPAC_ALPHABET = frozenset("ACGURYSWKMBDHVN")


class SequenceTransformMode(StrEnum):
    DNA_TO_RNA = "DNA-to-RNA"
    RNA_TO_DNA = "RNA-to-DNA"


class SequenceTransformError(ValueError):
    """An explicit sequence transform validation error."""

    def __init__(self, character: str, position: int, mode: SequenceTransformMode | str):
        self.character = character
        self.position = position
        self.mode = mode
        super().__init__(
            f"Invalid character {character!r} at zero-based normalized position {position} "
            f"for {mode}. Remove it or choose the matching transform mode."
        )


def normalize_sequence_text(raw_sequence: str) -> str:
    """Remove whitespace and uppercase ASCII sequence letters without mutation."""
    if not isinstance(raw_sequence, str):
        raise TypeError("raw_sequence must be a string")
    return "".join(character.upper() for character in raw_sequence if not character.isspace())


def transform_dna_rna(
    raw_sequence: str,
    mode: SequenceTransformMode | str,
) -> str:
    """Explicitly convert DNA/RNA IUPAC text, rejecting T/U mixing."""
    aliases = {
        "DNA → RNA": SequenceTransformMode.DNA_TO_RNA,
        "RNA → DNA": SequenceTransformMode.RNA_TO_DNA,
        "dna_to_rna": SequenceTransformMode.DNA_TO_RNA,
        "rna_to_dna": SequenceTransformMode.RNA_TO_DNA,
    }
    try:
        normalized_mode = aliases[mode] if isinstance(mode, str) and mode in aliases else SequenceTransformMode(mode)
    except ValueError as exc:
        raise ValueError("mode must be DNA-to-RNA or RNA-to-DNA") from exc
    sequence = normalize_sequence_text(raw_sequence)
    if "T" in sequence and "U" in sequence:
        first = min(index for index, char in enumerate(sequence) if char in "TU")
        raise SequenceTransformError(sequence[first], first, normalized_mode)
    alphabet = DNA_IUPAC_ANALYSIS_ALPHABET if normalized_mode is SequenceTransformMode.DNA_TO_RNA else RNA_IUPAC_ALPHABET
    forbidden = "U" if normalized_mode is SequenceTransformMode.DNA_TO_RNA else "T"
    for position, character in enumerate(sequence):
        if character == forbidden or character not in alphabet:
            raise SequenceTransformError(character, position, normalized_mode)
    return sequence.replace("T", "U") if normalized_mode is SequenceTransformMode.DNA_TO_RNA else sequence.replace("U", "T")

_IUPAC_COMPLEMENTS = str.maketrans(
    {
        "A": "T",
        "C": "G",
        "G": "C",
        "T": "A",
        "R": "Y",
        "Y": "R",
        "S": "S",
        "W": "W",
        "K": "M",
        "M": "K",
        "B": "V",
        "V": "B",
        "D": "H",
        "H": "D",
        "N": "N",
    }
)


class SequenceTopology(StrEnum):
    """Topology metadata supported by the public analysis contract."""

    UNKNOWN = "unknown"
    LINEAR = "linear"
    CIRCULAR = "circular"


class SequenceErrorCode(StrEnum):
    """Stable error codes returned by, or associated with, the contract."""

    EMPTY_SEQUENCE = "EMPTY_SEQUENCE"
    SEQUENCE_CONTAINS_URACIL = "SEQUENCE_CONTAINS_URACIL"
    INVALID_DNA_CHARACTER = "INVALID_DNA_CHARACTER"
    INVALID_TOPOLOGY = "INVALID_TOPOLOGY"


class SequenceWarningCode(StrEnum):
    """Stable warning codes returned by the contract."""

    AMBIGUOUS_BASES_PRESENT = "AMBIGUOUS_BASES_PRESENT"
    NOT_CONSTRUCT_READY = "NOT_CONSTRUCT_READY"


@dataclass(frozen=True, slots=True)
class SequenceFinding:
    """A deterministic structured error or warning."""

    code: SequenceErrorCode | SequenceWarningCode
    message: str


@dataclass(frozen=True, slots=True)
class InvalidDnaCharacter:
    """An invalid character and its zero-based normalized-text position."""

    character: str
    position: int


@dataclass(frozen=True, slots=True)
class DnaSequenceAnalysisResult:
    """Immutable result for DNA analysis and construct eligibility review."""

    raw_sequence: str
    normalized_sequence: str
    normalized_length: int
    valid_base_count: int
    sequence_length: int | None
    gc_count: int | None
    unambiguous_base_count: int | None
    ambiguous_base_count: int | None
    gc_percent_total: float | None
    gc_percent_unambiguous: float | None
    reverse_complement: str | None
    topology: SequenceTopology
    is_valid_for_analysis: bool
    is_construct_ready: bool
    invalid_characters: tuple[InvalidDnaCharacter, ...]
    errors: tuple[SequenceFinding, ...]
    warnings: tuple[SequenceFinding, ...]


class InvalidTopologyError(ValueError):
    """Raised when a caller supplies unsupported topology metadata."""

    code = SequenceErrorCode.INVALID_TOPOLOGY

    def __init__(self, topology: object) -> None:
        super().__init__(
            "topology must be one of: unknown, linear, circular; "
            f"received {topology!r}"
        )


def _normalize_topology(topology: str | SequenceTopology) -> SequenceTopology:
    if isinstance(topology, SequenceTopology):
        return topology
    if not isinstance(topology, str):
        raise InvalidTopologyError(topology)
    try:
        return SequenceTopology(topology)
    except ValueError as exc:
        raise InvalidTopologyError(topology) from exc


def _uppercase_ascii_letter(character: str) -> str:
    if "a" <= character <= "z":
        return chr(ord(character) - 32)
    return character


def _normalize_sequence(raw_sequence: str) -> str:
    return "".join(
        _uppercase_ascii_letter(character)
        for character in raw_sequence
        if not character.isspace()
    )


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_IUPAC_COMPLEMENTS)[::-1]


def analyze_dna_sequence(
    raw_sequence: str,
    topology: str | SequenceTopology = SequenceTopology.UNKNOWN,
) -> DnaSequenceAnalysisResult:
    """Analyze DNA without file, database, network, UI, or global-state access.

    Whitespace is removed, ASCII letters are uppercased, and every other
    non-whitespace character is preserved. Ordinary sequence-content problems
    are returned as findings. Invalid argument types and topology values raise
    explicit programming errors.
    """
    if not isinstance(raw_sequence, str):
        raise TypeError("raw_sequence must be a string")

    normalized_topology = _normalize_topology(topology)
    normalized_sequence = _normalize_sequence(raw_sequence)
    normalized_length = len(normalized_sequence)
    valid_base_count = sum(
        character in DNA_IUPAC_ANALYSIS_ALPHABET
        for character in normalized_sequence
    )
    invalid_characters = tuple(
        InvalidDnaCharacter(character=character, position=position)
        for position, character in enumerate(normalized_sequence)
        if character not in DNA_IUPAC_ANALYSIS_ALPHABET
    )

    errors: list[SequenceFinding] = []
    if not normalized_sequence:
        errors.append(
            SequenceFinding(
                code=SequenceErrorCode.EMPTY_SEQUENCE,
                message="No DNA sequence remains after whitespace removal.",
            )
        )

    contains_uracil = "U" in normalized_sequence
    if contains_uracil:
        errors.append(
            SequenceFinding(
                code=SequenceErrorCode.SEQUENCE_CONTAINS_URACIL,
                message=(
                    "U is not valid in this DNA analysis contract. The input "
                    "may be RNA and requires explicit user-confirmed conversion "
                    "in a separate function."
                ),
            )
        )

    contains_other_invalid = any(
        item.character != "U" for item in invalid_characters
    )
    if contains_other_invalid:
        errors.append(
            SequenceFinding(
                code=SequenceErrorCode.INVALID_DNA_CHARACTER,
                message="One or more characters are not valid DNA IUPAC symbols.",
            )
        )

    is_valid_for_analysis = bool(normalized_sequence) and not invalid_characters
    is_construct_ready = (
        is_valid_for_analysis
        and all(
            character in DNA_CONSTRUCT_READY_ALPHABET
            for character in normalized_sequence
        )
    )

    warnings: list[SequenceFinding] = []
    if is_valid_for_analysis and not is_construct_ready:
        warnings.extend(
            (
                SequenceFinding(
                    code=SequenceWarningCode.AMBIGUOUS_BASES_PRESENT,
                    message="DNA IUPAC ambiguity symbols are present.",
                ),
                SequenceFinding(
                    code=SequenceWarningCode.NOT_CONSTRUCT_READY,
                    message=(
                        "The sequence is valid for analysis but is not eligible "
                        "for deterministic construct assembly."
                    ),
                ),
            )
        )

    if not normalized_sequence:
        sequence_length: int | None = 0
        gc_count: int | None = 0
        unambiguous_base_count: int | None = 0
        ambiguous_base_count: int | None = 0
        gc_percent_total: float | None = None
        gc_percent_unambiguous: float | None = None
        reverse_complement: str | None = None
    elif not is_valid_for_analysis:
        sequence_length = None
        gc_count = None
        unambiguous_base_count = None
        ambiguous_base_count = None
        gc_percent_total = None
        gc_percent_unambiguous = None
        reverse_complement = None
    else:
        sequence_length = normalized_length
        gc_count = normalized_sequence.count("G") + normalized_sequence.count("C")
        unambiguous_base_count = sum(
            character in DNA_CONSTRUCT_READY_ALPHABET
            for character in normalized_sequence
        )
        ambiguous_base_count = sequence_length - unambiguous_base_count
        gc_percent_total = gc_count / sequence_length * 100
        gc_percent_unambiguous = (
            gc_count / unambiguous_base_count * 100
            if unambiguous_base_count
            else None
        )
        reverse_complement = _reverse_complement(normalized_sequence)

    return DnaSequenceAnalysisResult(
        raw_sequence=raw_sequence,
        normalized_sequence=normalized_sequence,
        normalized_length=normalized_length,
        valid_base_count=valid_base_count,
        sequence_length=sequence_length,
        gc_count=gc_count,
        unambiguous_base_count=unambiguous_base_count,
        ambiguous_base_count=ambiguous_base_count,
        gc_percent_total=gc_percent_total,
        gc_percent_unambiguous=gc_percent_unambiguous,
        reverse_complement=reverse_complement,
        topology=normalized_topology,
        is_valid_for_analysis=is_valid_for_analysis,
        is_construct_ready=is_construct_ready,
        invalid_characters=invalid_characters,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


__all__ = [
    "DNA_CONSTRUCT_READY_ALPHABET",
    "DNA_IUPAC_ANALYSIS_ALPHABET",
    "DnaSequenceAnalysisResult",
    "InvalidDnaCharacter",
    "InvalidTopologyError",
    "SequenceErrorCode",
    "SequenceFinding",
    "SequenceTopology",
    "SequenceWarningCode",
    "SequenceTransformError",
    "SequenceTransformMode",
    "analyze_dna_sequence",
    "normalize_sequence_text",
    "transform_dna_rna",
]
