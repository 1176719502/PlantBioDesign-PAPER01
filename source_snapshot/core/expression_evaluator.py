# core/expression_evaluator.py
# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
Expression construct evaluator.

Provides GC content calculation, CDS translation, and biological
logic warnings for an assembled construct dict produced by
ConstructBuilder.

All strings are strict ASCII to prevent encoding errors on any OS.
"""
from __future__ import annotations


class ExpressionEvaluator:
    """Sequence evaluation engine: GC content calculation and CDS translation."""

    # Standard genetic code (NCBI translation table 1)
    CODON_TABLE = {
        'TTT': 'F', 'TTC': 'F', 'TTA': 'L', 'TTG': 'L',
        'CTT': 'L', 'CTC': 'L', 'CTA': 'L', 'CTG': 'L',
        'ATT': 'I', 'ATC': 'I', 'ATA': 'I', 'ATG': 'M',
        'GTT': 'V', 'GTC': 'V', 'GTA': 'V', 'GTG': 'V',
        'TCT': 'S', 'TCC': 'S', 'TCA': 'S', 'TCG': 'S',
        'CCT': 'P', 'CCC': 'P', 'CCA': 'P', 'CCG': 'P',
        'ACT': 'T', 'ACC': 'T', 'ACA': 'T', 'ACG': 'T',
        'GCT': 'A', 'GCC': 'A', 'GCA': 'A', 'GCG': 'A',
        'TAT': 'Y', 'TAC': 'Y', 'TAA': '*', 'TAG': '*',
        'CAT': 'H', 'CAC': 'H', 'CAA': 'Q', 'CAG': 'Q',
        'AAT': 'N', 'AAC': 'N', 'AAA': 'K', 'AAG': 'K',
        'GAT': 'D', 'GAC': 'D', 'GAA': 'E', 'GAG': 'E',
        'TGT': 'C', 'TGC': 'C', 'TGA': '*', 'TGG': 'W',
        'CGT': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R',
        'AGT': 'S', 'AGC': 'S', 'AGA': 'R', 'AGG': 'R',
        'GGT': 'G', 'GGC': 'G', 'GGA': 'G', 'GGG': 'G',
    }

    def evaluate_construct(self, construct_result: dict) -> dict:
        """Evaluate a construct: GC content, CDS translation, and logic warnings."""
        full_seq = construct_result.get("final_sequence", "")
        features = construct_result.get("features", [])

        report = {
            "global_gc_content": self._calculate_gc(full_seq),
            "cds_translations": {},
            "warnings": []
        }

        # Translate all CDS features
        for feat in features:
            if feat.get("type", "") == "CDS":
                # start is 1-based; Python slicing is 0-based
                start_idx = feat["start"] - 1
                end_idx   = feat["end"]
                cds_seq   = full_seq[start_idx:end_idx]
                protein_seq = self._translate_dna(cds_seq)
                report["cds_translations"][feat["name"]] = protein_seq

                # Warn if no stop codon was encountered
                if not protein_seq.endswith('*'):
                    report["warnings"].append(
                        f"Warning: [{feat['name']}] no stop codon encountered "
                        "-- sequence may be incomplete."
                    )

        return report

    @staticmethod
    def _calculate_gc(sequence: str) -> float:
        """Return GC content as a percentage rounded to 2 decimal places."""
        if not sequence:
            return 0.0
        seq = sequence.upper()
        gc_count = seq.count('G') + seq.count('C')
        return round((gc_count / len(seq)) * 100, 2)

    @classmethod
    def _translate_dna(cls, sequence: str) -> str:
        """Translate a DNA sequence to amino acids. Stops at the first stop codon."""
        seq = sequence.upper()
        protein: list[str] = []
        for i in range(0, len(seq) - 2, 3):
            codon = seq[i:i + 3]
            aa = cls.CODON_TABLE.get(codon, '?')
            protein.append(aa)
            if aa == '*':
                break
        return "".join(protein)
