# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
# -*- coding: utf-8 -*-
"""DeepCodon - Deep learning codon optimization model"""
import math
from typing import Dict, List, Optional

# CODON_TABLES is defined in core/codon_optimizer.py (single source of truth).
# Import it here to avoid duplicating ~300 lines of codon frequency data.
try:
    from core.codon_optimizer import CODON_TABLES
except ImportError:
    # Minimal fallback so the module still loads without the full core package
    CODON_TABLES = {}  # type: ignore

HOST_ALIAS = {
    "e.coli": "E.coli", "ecoli": "E.coli",
    "yeast": "Yeast", "s. cerevisiae": "Yeast",
    "human": "Human",
    "rice": "Rice", "o. sativa": "Rice",
    "maize": "Maize", "corn": "Maize", "zea mays": "Maize",
    "arabidopsis": "Arabidopsis", "a. thaliana": "Arabidopsis",
    "tobacco": "Tobacco", "n. benthamiana": "Tobacco", "nicotiana": "Tobacco",
    "agrobacterium": "Agrobacterium", "a. tumefaciens": "Agrobacterium",
}

AA_TO_CODONS = {
    "F": ["TTT", "TTC"],
    "L": ["TTA", "TTG", "CTT", "CTC", "CTA", "CTG"],
    "I": ["ATT", "ATC", "ATA"],
    "M": ["ATG"],
    "V": ["GTT", "GTC", "GTA", "GTG"],
    "S": ["TCT", "TCC", "TCA", "TCG", "AGT", "AGC"],
    "P": ["CCT", "CCC", "CCA", "CCG"],
    "T": ["ACT", "ACC", "ACA", "ACG"],
    "A": ["GCT", "GCC", "GCA", "GCG"],
    "Y": ["TAT", "TAC"],
    "*": ["TAA", "TAG", "TGA"],
    "H": ["CAT", "CAC"],
    "Q": ["CAA", "CAG"],
    "N": ["AAT", "AAC"],
    "K": ["AAA", "AAG"],
    "D": ["GAT", "GAC"],
    "E": ["GAA", "GAG"],
    "C": ["TGT", "TGC"],
    "W": ["TGG"],
    "R": ["CGT", "CGC", "CGA", "CGG", "AGA", "AGG"],
    "G": ["GGT", "GGC", "GGA", "GGG"],
}

_TT = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


class DeepCodonOptimizer:
    """DeepCodon - Optimize sequences by host codon preference."""

    VERSION = "1.0.0"
    SUPPORTED_HOSTS = list(CODON_TABLES.keys()) if CODON_TABLES else [
        "E.coli", "Yeast", "Human", "Rice",
        "Maize", "Arabidopsis", "Tobacco", "Agrobacterium",
    ]

    def resolve_host(self, name: str) -> str:
        key = name.lower().strip()
        if key in HOST_ALIAS:
            return HOST_ALIAS[key]
        for a, h in HOST_ALIAS.items():
            if a in key or key in a:
                return h
        # Partial match against known table keys
        for k in CODON_TABLES:
            if k.lower() in key or key in k.lower():
                return k
        return "E.coli"

    def _translate(self, dna: str) -> str:
        dna = dna.upper().replace(" ", "").replace("\n", "")
        dna = dna[: len(dna) - len(dna) % 3]
        try:
            from Bio.Seq import Seq
            return str(Seq(dna).translate(to_stop=False))
        except Exception:
            return "".join(_TT.get(dna[i: i + 3], "?") for i in range(0, len(dna) - 2, 3))

    def calculate_cai(self, dna: str, host: str) -> float:
        import math as _m
        resolved = self.resolve_host(host)
        table = CODON_TABLES.get(resolved, CODON_TABLES.get("E.coli", {}))
        dna = dna.upper().replace(" ", "").replace("\n", "")
        dna = dna[: len(dna) - len(dna) % 3]
        aa_max = {
            aa: max(table.get(c, 0.001) for c in cs)
            for aa, cs in AA_TO_CODONS.items()
        }
        logs, n = [], 0
        for i in range(0, len(dna) - 2, 3):
            codon = dna[i: i + 3]
            aa = _TT.get(codon)
            if aa and aa != "*" and aa_max.get(aa, 0) > 0:
                logs.append(_m.log(table.get(codon, 0.001) / aa_max[aa]))
                n += 1
        return round(_m.exp(sum(logs) / n), 4) if n else 0.0

    def calculate_gc(self, dna: str) -> float:
        dna = dna.upper()
        return round((dna.count("G") + dna.count("C")) / len(dna) * 100, 2) if dna else 0.0

    def find_rare_codons(self, dna: str, host: str, threshold: float = 5.0) -> list:
        resolved = self.resolve_host(host)
        table = CODON_TABLES.get(resolved, CODON_TABLES.get("E.coli", {}))
        dna = dna.upper().replace(" ", "").replace("\n", "")
        rare = []
        for i in range(0, len(dna) - 2, 3):
            c = dna[i: i + 3]
            if len(c) == 3 and table.get(c, 0) < threshold and c not in ("TAA", "TAG", "TGA"):
                rare.append({"pos": i // 3 + 1, "codon": c, "freq": table.get(c, 0)})
        return rare

    def optimize(
        self,
        sequence: str,
        host: str,
        input_type: str = "auto",
        smoothing: bool = True,
        mode: str = "deterministic",
    ) -> dict:
        # mode: "deterministic" or "stochastic" (weighted-random by codon freq)
        self._stochastic_mode = (mode == "stochastic")
        host_key = self.resolve_host(host)
        # Safe fallback if host still not in tables
        if host_key not in CODON_TABLES:
            host_key = "E.coli"
        table = CODON_TABLES[host_key]

        seq = sequence.upper().replace(" ", "").replace("\n", "")
        if input_type == "auto":
            input_type = "dna" if all(c in "ATCGN" for c in seq) else "protein"
        original_dna = None
        if input_type == "dna":
            seq = seq[: len(seq) - len(seq) % 3]
            original_dna = seq
            seq = self._translate(seq)
        if not seq:
            return {
                "success": False,
                "error": "Unable to parse input sequence. Please provide a valid DNA or protein sequence.",
            }
        opt, rep = [], []
        for pos, aa in enumerate(seq):
            cs = AA_TO_CODONS.get(aa)
            if not cs:
                continue
            if getattr(self, '_stochastic_mode', False) and len(cs) > 1:
                import random as _rnd
                freqs = [table.get(c, 0.1) for c in cs]
                total = sum(freqs)
                r, cumul, best = _rnd.random() * total, 0.0, cs[0]
                for c, f in zip(cs, freqs):
                    cumul += f
                    if r <= cumul:
                        best = c
                        break
            elif smoothing and pos % 5 == 0 and len(cs) > 1:
                best = sorted(cs, key=lambda c: table.get(c, 0), reverse=True)[1]
            else:
                best = max(cs, key=lambda c: table.get(c, 0))
            opt.append(best)
            rep.append({"pos": pos + 1, "aa": aa, "codon": best, "freq": table.get(best, 0)})
        od = "".join(opt)
        return {
            "success": True,
            "host": host_key,
            "original_dna": original_dna,
            "optimized_dna": od,
            "protein": seq,
            "length": len(od),
            "original_cai": self.calculate_cai(original_dna, host_key) if original_dna else 0.0,
            "optimized_cai": self.calculate_cai(od, host_key),
            "gc_content": self.calculate_gc(od),
            "rare_codons": self.find_rare_codons(od, host_key),
            "codon_report": rep,
        }
