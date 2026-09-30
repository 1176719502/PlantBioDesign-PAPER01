# -*- coding: utf-8 -*-
"""
core/expression_frame_builder.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Expression frame auto-builder.

Public API
----------
  list_supported_hosts()                       -> list[str]
  get_host_rules(host)                         -> dict
  build_expression_frame(gene_seq, host, tag)  -> dict
  validate_frame(frame_dict)                   -> list[dict]

No UI dependencies - pure Python only.
"""
from __future__ import annotations
import re
from Bio.Seq import Seq
from copy import deepcopy
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Host rule database
# ---------------------------------------------------------------------------

HOST_RULES: Dict[str, Dict] = {
    # ── Bacteria ──────────────────────────────────────────────────────────────
    "E.coli BL21(DE3)": {
        "kingdom": "prokaryote",
        "promoter": "T7 Promoter",
        "promoter_seq": "TAATACGACTCACTATA",
        "promoter_note": "T7 phage promoter requires BL21(DE3) strain. IPTG inducible (0.1-1 mM). Yield can reach 30-50% of total protein.",
        "rbs": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "rbs_spacer": 7,
        "rbs_note": "Strong Shine-Dalgarno. Optimal spacing to ATG: 6-8 bp. This design: 7 bp.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "E.coli rrnB T1 Rho-independent terminator.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pET-28a or pET-21a",
        "codon_table_key": "E.coli",
        "gc_optimal": (40, 65),
    },
    "E.coli DH5alpha": {
        "kingdom": "prokaryote",
        "promoter": "tac Promoter",
        "promoter_seq": "TTGACAATTAATCATCGGCTCGTATAATGTGTGG",
        "promoter_note": "Hybrid tac (trp/lac) promoter. IPTG inducible. DH5alpha lacks T7 polymerase so use tac.",
        "rbs": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "rbs_spacer": 7,
        "rbs_note": "Strong Shine-Dalgarno. 7 bp spacer to ATG.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "rrnB T1 Rho-independent terminator.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pQE or pUC series",
        "codon_table_key": "E.coli",
        "gc_optimal": (40, 65),
    },
    "Agrobacterium GV3101": {
        "kingdom": "plant_delivery",
        "promoter": "CaMV 35S Promoter",
        "promoter_seq": "GTCAACATGGTGGAGCACGACACACTTGTCTACTCCAAAAATATCAAAGATACAGTCTCAGAAGACCAAAGGGCAATTGAGACTTTTCAACAAAGGGTAATATCCGGAAACCTCCTCGGATTCCATTGCCCAGCTATCTGTCAC",
        "promoter_note": "CaMV 35S functions inside plant cells after T-DNA integration. Standard for dicot Agrobacterium transformation.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context (GCCACC) immediately upstream of ATG. Works in plant cells post T-DNA integration.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTG",
        "terminator_note": "NOS terminator from Agrobacterium T-DNA. Standard plant expression terminator.",
        "tag_options": {"No tag": ""},
        "vector_suggestion": "pCAMBIA1301 or pGWB series binary vector",
        "codon_table_key": "Arabidopsis",
        "gc_optimal": (40, 65),
    },
    "Rice (O. sativa)": {
        "kingdom": "plant_monocot",
        "promoter": "ZmUbi Promoter",
        "promoter_seq": "TGCAGTGCTGTGTTTTGGTAGTTGAAAGATCTTCGT",
        "promoter_note": "Maize Ubiquitin-1 promoter. Strongest constitutive monocot promoter. Intron I enhances expression 5-10x. Use for rice, maize, wheat.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context (GCCACC) immediately upstream of ATG. Essential for eukaryotic translation initiation.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTG",
        "terminator_note": "NOS terminator. Standard plant cassette terminator.",
        "tag_options": {"No tag": "", "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA"},
        "vector_suggestion": "pCAMBIA1301 or pOsEn series",
        "codon_table_key": "Rice",
        "gc_optimal": (40, 65),
    },
    "Maize (Zea mays)": {
        "kingdom": "plant_monocot",
        "promoter": "ZmUbi Promoter",
        "promoter_seq": "TGCAGTGCTGTGTTTTGGTAGTTGAAAGATCTTCGT",
        "promoter_note": "ZmUbi-1 native maize promoter. Strongest constitutive monocot promoter.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context immediately upstream of ATG.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTG",
        "terminator_note": "NOS terminator. Standard plant binary vector terminator.",
        "tag_options": {"No tag": ""},
        "vector_suggestion": "pCAMBIA or pTF101 series",
        "codon_table_key": "Maize",
        "gc_optimal": (40, 65),
    },
    "Arabidopsis thaliana": {
        "kingdom": "plant_dicot",
        "promoter": "CaMV 35S Promoter",
        "promoter_seq": "GTCAACATGGTGGAGCACGACACACTTGTCTACTCCAAAAATATCAAAGATACAGTCTCAGAAGACCAAAGGGCAATTGAGACTTTTCAACAAAGGGTAATATCCGGAAACCTCCTCGGATTCCATTGCCCAGCTATCTGTCAC",
        "promoter_note": "CaMV 35S constitutive promoter. Strong in most dicot tissues. Not recommended for monocots. Dual 35S gives 2-3x higher expression.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context (GCCACC) immediately upstream of ATG.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTG",
        "terminator_note": "NOS terminator. Standard Arabidopsis transformation terminator.",
        "tag_options": {"No tag": "", "GFP fusion (C-term)": "", "His6-tag": "CACCACCACCACCACCAC"},
        "vector_suggestion": "pEarleyGate or pGWB series",
        "codon_table_key": "Arabidopsis",
        "gc_optimal": (40, 65),
    },
    "Tobacco (N. benthamiana)": {
        "kingdom": "plant_dicot",
        "promoter": "CaMV 35S Promoter",
        "promoter_seq": "GTCAACATGGTGGAGCACGACACACTTGTCTACTCCAAAAATATCAAAGATACAGTCTCAGAAGACCAAAGGGCAATTGAGACTTTTCAACAAAGGGTAATATCCGGAAACCTCCTCGGATTCCATTGCCCAGCTATCTGTCAC",
        "promoter_note": "CaMV 35S. Tobacco/N.benthamiana is the preferred transient expression host. Very high protein yield via agroinfiltration.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context immediately upstream of ATG.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTG",
        "terminator_note": "NOS terminator.",
        "tag_options": {"No tag": "", "His6-tag (C-term)": "CACCACCACCACCACCAC"},
        "vector_suggestion": "pEAQ-HT or pGWB series (agroinfiltration)",
        "codon_table_key": "Tobacco",
        "gc_optimal": (40, 65),
    },

    # ── Additional Bacteria ───────────────────────────────────────────────────
    "E.coli Rosetta(DE3)": {
        "kingdom": "prokaryote",
        "promoter": "T7 Promoter",
        "promoter_seq": "TAATACGACTCACTATA",
        "promoter_note": "T7 promoter + Rosetta strain supplies rare tRNAs (AGG, AGA, AUA, CUA, CCC, GGA). Best for eukaryotic proteins with rare E.coli codons. IPTG inducible.",
        "rbs": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "rbs_spacer": 7,
        "rbs_note": "Strong SD. Rosetta provides rare tRNAs to improve plant/eukaryotic gene expression in E.coli.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "E.coli rrnB T1 Rho-independent terminator.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pET-28a or pET-32a (Rosetta2(DE3) cells)",
        "codon_table_key": "E.coli",
        "gc_optimal": (40, 65),
    },
    "B. subtilis 168": {
        "kingdom": "prokaryote",
        "promoter": "P43 Promoter",
        "promoter_seq": "TTGAAAAAATTTTATTTGTTTGTTTGT",
        "promoter_note": "B. subtilis P43 constitutive promoter. Strong, food-grade expression. No inducer needed. Excellent for secreted enzymes.",
        "rbs": "Shine-Dalgarno (B. subtilis)",
        "rbs_seq": "AAGGAG",
        "rbs_spacer": 7,
        "rbs_note": "B. subtilis consensus SD. 7 bp spacer to ATG optimal.",
        "terminator": "amyE Terminator",
        "terminator_seq": "CCCCATAAAAAAAAGGCCCGGTTTTTTTTTGGGCCTTTTTTTT",
        "terminator_note": "B. subtilis amylase (amyE) Rho-independent terminator.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pHT01 or pHT43 (MoBiTec)",
        "codon_table_key": "B.subtilis",
        "gc_optimal": (43, 65),
    },
    "Streptomyces coelicolor": {
        "kingdom": "prokaryote",
        "promoter": "ermE* Promoter",
        "promoter_seq": "TCGTGAGCCCCGAGCCGGGCGGCCCGTCGGCGGGGCATGA",
        "promoter_note": "ermE* strong constitutive Streptomyces promoter. Used for secondary metabolite pathway engineering. High-GC host.",
        "rbs": "Shine-Dalgarno (Streptomyces)",
        "rbs_seq": "GGAG",
        "rbs_spacer": 8,
        "rbs_note": "Streptomyces consensus SD. High-GC genome. 8 bp spacer.",
        "terminator": "fd Terminator",
        "terminator_seq": "AAAAAAAACCCCGCTTCGGGGGTTTTTTT",
        "terminator_note": "Synthetic terminator adapted for Streptomyces.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pSET152 or pIJ8600 integrative vector",
        "codon_table_key": "Streptomyces",
        "gc_optimal": (65, 75),
    },

    # ── Yeast ────────────────────────────────────────────────────────────────
    "S. cerevisiae": {
        "kingdom": "yeast",
        "promoter": "GAL1 Promoter",
        "promoter_seq": "AGATCTGATCAAGAGACAGGATGAGGATCGTTTCGCATGATTGAACAAGATGGATTGCACGCAGGTTCTCCGGCCGCTTGGGTGGAGAGG",
        "promoter_note": "GAL1 inducible promoter (galactose ON / glucose OFF). High expression in S. cerevisiae. Induce with 2% galactose.",
        "rbs": "Kozak Sequence (yeast)",
        "rbs_seq": "AAAAATG",
        "rbs_spacer": 0,
        "rbs_note": "Yeast Kozak context (A/T)AAAATG for efficient ribosome scanning in Saccharomyces.",
        "terminator": "CYC1 Terminator",
        "terminator_seq": "CATGTAATTAGTTATGTCACGCTTACATTCACGCCCTCCCCACATCCGCTCTAACCAAAAAAAAAAAAAAA",
        "terminator_note": "CYC1 (Cytochrome c) terminator. Most widely used in yeast expression vectors.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA", "No tag": ""},
        "vector_suggestion": "pYES2 (Invitrogen) or pRS series 2-micron plasmid",
        "codon_table_key": "S.cerevisiae",
        "gc_optimal": (38, 60),
    },
    "P. pastoris (K. phaffii)": {
        "kingdom": "yeast",
        "promoter": "AOX1 Promoter",
        "promoter_seq": "AGATCTTTTTTTAGAAAAGATCAAACGCTTTTTTTCTGTTTCTGTTTGATTTTTTTCTGTTTCGTTTGTTT",
        "promoter_note": "AOX1 methanol-inducible promoter. Strongest yeast promoter under induction. Switch from glycerol to methanol to induce. Up to g/L protein yield.",
        "rbs": "Kozak Sequence (Pichia)",
        "rbs_seq": "AAAATG",
        "rbs_spacer": 0,
        "rbs_note": "Pichia Kozak context. Use alpha-factor signal peptide for secreted proteins.",
        "terminator": "AOX1 Terminator",
        "terminator_seq": "GCAAATTAAAGCCTTTAGCTTTTAATTTGTTTTTTTTTTTTTTTTTTTTTTTTT",
        "terminator_note": "AOX1 transcription terminator. Required for stable mRNA 3' end processing in Pichia.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "No tag": ""},
        "vector_suggestion": "pPICZ (intracellular) or pPICZalpha (secretion, Invitrogen)",
        "codon_table_key": "P.pastoris",
        "gc_optimal": (40, 62),
    },

    # ── Mammalian ────────────────────────────────────────────────────────────
    "HEK293": {
        "kingdom": "mammalian",
        "promoter": "CMV Promoter",
        "promoter_seq": "GACATTGATTATTGACTAGTTATTAATAGTAATCAATTACGGGGTCATTAGTTCATAGCCCATATATGGAGTTCCGCGTTACATAACTTACGGTAAATGGCCCGCCTGGCTGACCGCCCAACGACCCCCGCCCATTGACGTCAAT",
        "promoter_note": "CMV immediate early promoter. Strongest mammalian constitutive promoter. Active in most human/mammalian cell lines. No inducer needed.",
        "rbs": "Kozak Sequence (mammalian)",
        "rbs_seq": "GCCACCATG",
        "rbs_spacer": 0,
        "rbs_note": "Optimal Kozak consensus (GCCACCatg). Critical for efficient cap-dependent translation in mammalian cells.",
        "terminator": "BGH polyA Signal",
        "terminator_seq": "CTGTGCCTTCTAGTTGCCAGCCATCTGTTGTTTGCCCCTCCCCCGTGCCTTCCTTGACCCTGGAAGGTGCCACTCCC",
        "terminator_note": "BGH (Bovine Growth Hormone) polyadenylation signal. Standard for mammalian expression vectors.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA", "No tag": ""},
        "vector_suggestion": "pcDNA3.1 (Invitrogen) or pCMV-Tag series",
        "codon_table_key": "Human",
        "gc_optimal": (40, 65),
    },
    "CHO cells": {
        "kingdom": "mammalian",
        "promoter": "CMV Promoter",
        "promoter_seq": "GACATTGATTATTGACTAGTTATTAATAGTAATCAATTACGGGGTCATTAGTTCATAGCCCATATATGGAGTTCCGCGTTACATAACTTACGGTAAATGGCCCGCCTGGCTGACCGCCCAACGACCCCCGCCCATTGACGTCAAT",
        "promoter_note": "CMV promoter. CHO (Chinese Hamster Ovary) cells are industry standard for biopharmaceutical production. Supports complex N-glycosylation. Use for antibody/therapeutic protein manufacturing.",
        "rbs": "Kozak Sequence (mammalian)",
        "rbs_seq": "GCCACCATG",
        "rbs_spacer": 0,
        "rbs_note": "Optimal Kozak consensus (GCCACCatg) for mammalian translation initiation.",
        "terminator": "BGH polyA Signal",
        "terminator_seq": "CTGTGCCTTCTAGTTGCCAGCCATCTGTTGTTTGCCCCTCCCCCGTGCCTTCCTTGACCCTGGAAGGTGCCACTCCC",
        "terminator_note": "BGH polyadenylation signal. Standard terminator for stable CHO cell line development.",
        "tag_options": {"His6-tag (C-term)": "CACCACCACCACCACCAC", "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA", "No tag": ""},
        "vector_suggestion": "pcDNA3.1 or pCHO1.0 with DHFR/GS selection for stable lines",
        "codon_table_key": "Human",
        "gc_optimal": (40, 65),
    },

    # ── Additional Plants ─────────────────────────────────────────────────────
    "Soybean (G. max)": {
        "kingdom": "plant_dicot",
        "promoter": "CaMV 35S Promoter",
        "promoter_seq": "GTCAACATGGTGGAGCACGACACACTTGTCTACTCCAAAAATATCAAAGATACAGTCTCAGAAGACCAAAGGGCAATTGAGACTTTTCAACAAAGGGTAATATCCGGAAACCTCCTCGGATTCCATTGCCCAGCTATCTGTCAC",
        "promoter_note": "CaMV 35S constitutive promoter for soybean. Effective in dicot legumes. For seed-specific expression, use soybean beta-conglycinin promoter.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context (GCCACC) immediately upstream of ATG.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGG",
        "terminator_note": "NOS terminator. Standard plant expression cassette terminator.",
        "tag_options": {"No tag": ""},
        "vector_suggestion": "pCAMBIA series binary vector for Agrobacterium-mediated transformation",
        "codon_table_key": "Arabidopsis",
        "gc_optimal": (40, 65),
    },
    "Wheat (T. aestivum)": {
        "kingdom": "plant_monocot",
        "promoter": "ZmUbi Promoter",
        "promoter_seq": "TGCAGTGCTGTGTTTTGGTAGTTGAAAGATCTTCGT",
        "promoter_note": "ZmUbi-1 maize ubiquitin promoter. Best constitutive promoter for wheat and other monocots. Intron I required for full activity.",
        "rbs": "Kozak Sequence",
        "rbs_seq": "GCCACC",
        "rbs_spacer": 0,
        "rbs_note": "Plant Kozak context (GCCACC) immediately upstream of ATG.",
        "terminator": "NOS Terminator",
        "terminator_seq": "GCATGCACGAGATTTCGATTCCACCGCCGCCTTCTATGAAAGGTTGGGCTTCGGAATCGTTTTCCGGGACGCCGGTTCAGATGAGCTTCACTGATGCGGTATTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATCAGGTGGCACTTTTCGGGG",
        "terminator_note": "NOS terminator. Standard monocot plant cassette terminator.",
        "tag_options": {"No tag": ""},
        "vector_suggestion": "pAHC17 or pWBVec series for biolistic/Agrobacterium transformation",
        "codon_table_key": "Wheat",
        "gc_optimal": (40, 65),
    },

    # ── Insect cells ──────────────────────────────────────────────────────────
    "Sf9 (Spodoptera frugiperda)": {
        "kingdom": "insect",
        "promoter": "Polyhedrin Promoter (polh)",
        "promoter_seq": "ATGTATAAAAATAAATATAATTATTTTTAATAAATTAAT",
        "promoter_note": "Baculovirus polyhedrin promoter. Very late phase promoter — massive expression (up to 1 g/L). Requires baculovirus co-infection. Use with Bac-to-Bac or flashBAC system.",
        "rbs": "Kozak Sequence (insect)",
        "rbs_seq": "ACCATG",
        "rbs_spacer": 0,
        "rbs_note": "Insect Kozak context (ACCATG). Sf9 uses cap-dependent scanning similar to mammalian cells.",
        "terminator": "SV40 polyA Signal",
        "terminator_seq": "AACTTGTTTATTGCAGCTTATAATGGTTACAAATAAAGCAATAGCATCACAAATTTCACAAATAAAGCATTTTTTTCACTGCATTCTAGTTGTGGTTTGTCCAAACTCATCAATGTATCT",
        "terminator_note": "SV40 early polyadenylation signal. Efficient in insect baculovirus expression vectors.",
        "tag_options": {
            "No tag": "",
            "His6-tag (C-term)": "CACCACCACCACCACCAC",
            "His6-tag (N-term)": "CACCACCACCACCACCAC",
            "GST-tag (N-term)": "",
            "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA",
        },
        "vector_suggestion": "pFastBac1 (Bac-to-Bac, Thermo) or pAcSG2 (BD Biosciences)",
        "codon_table_key": "Insect",
        "gc_optimal": (38, 62),
    },
    "Hi5 (Trichoplusia ni)": {
        "kingdom": "insect",
        "promoter": "Polyhedrin Promoter (polh)",
        "promoter_seq": "ATGTATAAAAATAAATATAATTATTTTTAATAAATTAAT",
        "promoter_note": "Polyhedrin promoter. Hi5 cells give 5-10x higher secreted protein yield than Sf9. Preferred for glycoproteins and VLPs.",
        "rbs": "Kozak Sequence (insect)",
        "rbs_seq": "ACCATG",
        "rbs_spacer": 0,
        "rbs_note": "Insect Kozak context (ACCATG).",
        "terminator": "SV40 polyA Signal",
        "terminator_seq": "AACTTGTTTATTGCAGCTTATAATGGTTACAAATAAAGCAATAGCATCACAAATTTCACAAATAAAGCATTTTTTTCACTGCATTCTAGTTGTGGTTTGTCCAAACTCATCAATGTATCT",
        "terminator_note": "SV40 polyadenylation signal.",
        "tag_options": {
            "No tag": "",
            "His6-tag (C-term)": "CACCACCACCACCACCAC",
            "FLAG-tag (N-term)": "GACTACAAAGACGATGACGATAAA",
        },
        "vector_suggestion": "pFastBac1 or pAcSG2 — use with Hi5 cells for secreted proteins",
        "codon_table_key": "Insect",
        "gc_optimal": (38, 62),
    },

    # ── Cyanobacteria ─────────────────────────────────────────────────────────
    "Synechocystis sp. PCC 6803": {
        "kingdom": "prokaryote",
        "promoter": "psbA2 Promoter",
        "promoter_seq": "TAATACGAATTTCAATAAATTTGAAATTTCAATAAATTTGAAATTTCAAT",
        "promoter_note": "psbA2 light-inducible promoter. Strong in cyanobacteria under continuous light. Ideal for photosynthesis-coupled metabolite production.",
        "rbs": "Shine-Dalgarno (cyanobacteria)",
        "rbs_seq": "AGGAG",
        "rbs_spacer": 7,
        "rbs_note": "Cyanobacterial consensus SD sequence. 7 bp spacer to ATG.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "rrnB T1 terminator functions in cyanobacteria.",
        "tag_options": {
            "No tag": "",
            "His6-tag (C-term)": "CACCACCACCACCACCAC",
        },
        "vector_suggestion": "pSL2680 or RSF1010-based broad-host-range plasmid",
        "codon_table_key": "E.coli",
        "gc_optimal": (45, 68),
    },

    # ── Corynebacterium ───────────────────────────────────────────────────────
    "C. glutamicum ATCC 13032": {
        "kingdom": "prokaryote",
        "promoter": "Ptrc Promoter",
        "promoter_seq": "TTGACAATTAATCATCGGCTCGTATAATGTGTGG",
        "promoter_note": "Ptrc IPTG-inducible promoter adapted for C. glutamicum. Industry workhorse for amino acid (Lys, Glu) and vitamin production. GRAS organism.",
        "rbs": "Shine-Dalgarno (C. glutamicum)",
        "rbs_seq": "AAGGAG",
        "rbs_spacer": 7,
        "rbs_note": "C. glutamicum consensus SD. High-GC genome (53%). 7 bp spacer.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "rrnB T1 terminator active in C. glutamicum.",
        "tag_options": {
            "No tag": "",
            "His6-tag (C-term)": "CACCACCACCACCACCAC",
        },
        "vector_suggestion": "pEKEx2 (IPTG-inducible) or pCGL0040 integrative vector",
        "codon_table_key": "E.coli",
        "gc_optimal": (48, 68),
    },

    # ── Cell-free ─────────────────────────────────────────────────────────────
    "Cell-free (E. coli lysate)": {
        "kingdom": "cell_free",
        "promoter": "T7 Promoter",
        "promoter_seq": "TAATACGACTCACTATA",
        "promoter_note": "T7 promoter for cell-free transcription-translation (TXTL). Add T7 RNA polymerase to the lysate. Rapid prototyping: results in 4-8 h. No cell growth needed.",
        "rbs": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "rbs_spacer": 7,
        "rbs_note": "Strong SD for cell-free E. coli TXTL. Works with Noireaux/Pardee PURE or crude lysate systems.",
        "terminator": "T7te Terminator",
        "terminator_seq": "CTAGCATAACCCCTTGGGGCCTCTAAACGGGTCTTGAGGGGTTTTTT",
        "terminator_note": "T7 early terminator (T7te). Efficient Rho-independent terminator in cell-free TXTL systems.",
        "tag_options": {
            "No tag": "",
            "His6-tag (C-term)": "CACCACCACCACCACCAC",
            "Strep-tag II (C-term)": "TGGTCACATCCAGTTTTGAGAAA",
        },
        "vector_suggestion": "Linear DNA (PCR product) or pJL1 plasmid. Use myTXTL / PURExpress kit.",
        "codon_table_key": "E.coli",
        "gc_optimal": (40, 65),
    },
}
# ---------------------------------------------------------------------------

def _calc_gc(seq: str) -> float:
    s = seq.upper()
    return (s.count('G') + s.count('C')) / len(s) * 100 if s else 0.0


def _find_polyt(seq: str, n: int = 5) -> List[int]:
    """Find 1-based positions of poly-T runs (premature terminators in plants)."""
    positions, start = [], 0
    pattern = 'T' * n
    while True:
        idx = seq.upper().find(pattern, start)
        if idx == -1:
            break
        positions.append(idx + 1)
        start = idx + 1
    return positions


def _has_internal_stop(cds: str) -> List[int]:
    """Return 1-based codon positions of premature stop codons (excluding last)."""
    stops, s = [], cds.upper()
    # Fix: use len(s) - 3 to exclude only the terminal stop codon.
    # The previous len(s) - 5 incorrectly skipped the penultimate codon.
    for i in range(0, len(s) - 3, 3):
        if s[i:i+3] in ('TAA', 'TAG', 'TGA'):
            stops.append(i // 3 + 1)
    return stops


def _has_terminal_stop(seq: str) -> bool:
    """Return True when *seq* ends with a canonical stop codon."""
    s = seq.upper()
    return len(s) >= 3 and s[-3:] in ('TAA', 'TAG', 'TGA')


def _translate_cds(seq: str) -> str:
    """Translate a CDS-like DNA string, trimming incomplete trailing bases."""
    s = re.sub(r'[^ATCGatcg]', '', seq).upper()
    s = s[:len(s) - (len(s) % 3)]
    if not s:
        return ''
    return str(Seq(s).translate())


_HOST_COPY_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\b[Bb]est\b", "default"),
    (r"\b[Ss]trongest\b", "commonly used"),
    (r"\b[Ss]trong\b", "documented"),
    (r"\b[Pp]referred\b", "commonly documented"),
    (r"\b[Rr]ecommended\b", "listed"),
    (r"\b[Oo]ptimal\b", "typical"),
    (r"\b[Ee]xcellent\b", "documented"),
    (r"\b[Ii]deal\b", "documented"),
    (r"\b[Mm]assive\b", "substantial documented"),
    (r"\byield can reach\b", "documentation may note"),
    (r"\bprotein yield\b", "protein output context"),
    (r"\bhigher expression\b", "documented expression context"),
    (r"\bhigh expression\b", "documented expression context"),
    (r"\benhances expression\b", "adds documented expression context"),
)


def _sanitize_host_copy(text: str) -> str:
    sanitized = str(text or "").strip()
    if not sanitized:
        return ""
    for pattern, replacement in _HOST_COPY_REPLACEMENTS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _sanitize_host_rules(rules: Dict) -> Dict:
    sanitized = deepcopy(rules)
    for key, value in list(sanitized.items()):
        if isinstance(value, str) and (key.endswith("_note") or key == "vector_suggestion"):
            sanitized[key] = _sanitize_host_copy(value)
    return sanitized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_supported_hosts() -> List[str]:
    return list(HOST_RULES.keys())


def get_host_groups() -> Dict[str, List[str]]:
    """
    Return hosts grouped by kingdom for UI display.
    Order within each group reflects recommended usage priority.
    """
    groups: Dict[str, List[str]] = {
        "Bacteria":      [],
        "Yeast":         [],
        "Insect Cells":  [],
        "Mammalian":     [],
        "Plants":        [],
        "Cell-free":     [],
    }
    _kingdom_map = {
        "prokaryote":      "Bacteria",
        "plant_delivery":  "Plants",
        "plant_dicot":     "Plants",
        "plant_monocot":   "Plants",
        "yeast":           "Yeast",
        "insect":          "Insect Cells",
        "mammalian":       "Mammalian",
        "cell_free":       "Cell-free",
    }
    for host, rules in HOST_RULES.items():
        grp = _kingdom_map.get(rules["kingdom"], "Bacteria")
        groups[grp].append(host)
    # Remove empty groups
    return {k: v for k, v in groups.items() if v}


# Tag metadata: descriptions and use-case guidance shown in UI
TAG_INFO: Dict[str, Dict[str, str]] = {
    "No tag": {
        "desc": "No affinity tag — native protein sequence.",
        "use":  "Best for in vivo functional studies, metabolic engineering, or when tag may interfere with activity.",
        "purification": "Requires activity-based or antibody purification.",
    },
    "His6-tag (C-term)": {
        "desc": "6x Histidine tag at the C-terminus.",
        "use":  "Most widely used. Purify by Ni-NTA affinity chromatography. C-terminal position avoids interference with N-terminal signal peptides.",
        "purification": "Ni-NTA resin (Qiagen), elute with 250 mM imidazole.",
    },
    "His6-tag (N-term)": {
        "desc": "6x Histidine tag at the N-terminus.",
        "use":  "Use when C-terminus is functionally important. May slightly reduce expression in some hosts.",
        "purification": "Ni-NTA resin, same protocol as C-terminal His-tag.",
    },
    "His10-tag (C-term)": {
        "desc": "10x Histidine tag — higher Ni2+ binding affinity than His6.",
        "use":  "Preferred for difficult-to-purify proteins, low-expression targets, or when high purity in one step is needed.",
        "purification": "Ni-NTA or Co2+ resin; 10xHis binds more tightly, requires higher imidazole (300-500 mM) to elute.",
    },
    "GST-tag (N-term)": {
        "desc": "Glutathione S-transferase tag (~26 kDa) at N-terminus.",
        "use":  "Promotes solubility of aggregation-prone proteins. Good for pull-down assays. Large tag — may need removal by PreScission protease.",
        "purification": "Glutathione Sepharose (Cytiva), elute with 10 mM glutathione.",
    },
    "MBP-tag (N-term)": {
        "desc": "Maltose Binding Protein tag (~42 kDa) at N-terminus.",
        "use":  "Strongest solubility enhancer. Ideal for insoluble or toxic proteins in E. coli. Large size requires proteolytic removal for structural studies.",
        "purification": "Amylose resin, elute with 10 mM maltose.",
    },
    "FLAG-tag (N-term)": {
        "desc": "DYKDDDDK octapeptide at N-terminus.",
        "use":  "Excellent for immunoprecipitation and western blot detection. Highly specific anti-FLAG M2 antibody available. Small size minimally affects protein function.",
        "purification": "Anti-FLAG M2 agarose (Sigma), elute with FLAG peptide or low pH.",
    },
    "FLAG-tag (C-term)": {
        "desc": "DYKDDDDK octapeptide at C-terminus.",
        "use":  "Same as N-term FLAG but placed at C-terminus. Use when N-terminus is critical for folding or targeting.",
        "purification": "Anti-FLAG M2 agarose, same protocol.",
    },
    "Strep-tag II (C-term)": {
        "desc": "WSHPQFEK octapeptide — high-affinity streptavidin variant (Strep-Tactin) ligand.",
        "use":  "Excellent for native-condition purification. No imidazole needed. Twin-Strep-tag doubles affinity. Ideal for sensitive complexes and in vitro assays.",
        "purification": "Strep-Tactin resin (IBA), elute with 2.5 mM desthiobiotin.",
    },
    "SUMO-tag (N-term)": {
        "desc": "Small Ubiquitin-like Modifier (~12 kDa) at N-terminus.",
        "use":  "Strongly enhances solubility and proper folding. SUMO protease cleaves leaving no extra residues on target. Ideal for challenging proteins.",
        "purification": "His6 on SUMO allows Ni-NTA capture; cleave with Ulp1/SenP2 to release native protein.",
    },
    "GFP fusion (C-term)": {
        "desc": "Green Fluorescent Protein (~27 kDa) fused at C-terminus.",
        "use":  "Real-time localization tracking in live cells. Confirms expression by fluorescence. Large tag — not suitable when protein function must be preserved.",
        "purification": "GFP-nanobody agarose or anti-GFP IP; also His6 on GFP if vector includes it.",
    },
}


def get_host_rules(host: str) -> Dict:
    rules = HOST_RULES.get(host, HOST_RULES["E.coli BL21(DE3)"])
    return _sanitize_host_rules(rules)


def build_expression_frame(
    gene_seq: str,
    host: str = "E.coli BL21(DE3)",
    tag: str = "No tag",
    include_linker: bool = True,
    custom_elements: Dict | None = None,
) -> Dict:
    """
    Assemble a complete expression cassette.

    Returns dict with keys:
        success, host, kingdom, parts, features,
        final_sequence, total_length, gc_content, gc_ok,
        promoter_name/note, rbs_name/note, terminator_name/note,
        vector_suggestion, codon_table_key, tag_applied, notes
    """
    rules = get_host_rules(host)
    kingdom = rules['kingdom']
    gene = re.sub(r'[^ATCGatcg]', '', gene_seq).upper()
    element_overrides = custom_elements or {}

    if not gene:
        return {'success': False, 'error': 'Gene sequence is empty or invalid.'}

    # Ensure ATG start
    if not gene.startswith('ATG'):
        gene = 'ATG' + gene

    # Ensure stop codon
    if gene[-3:] not in {'TAA', 'TAG', 'TGA'}:
        gene += 'TAA'

    # Apply tag -- reject unsupported tags explicitly instead of silently dropping them.
    if tag not in rules['tag_options']:
        return {
            'success': False,
            'error': (
                f"Tag '{tag}' is not supported for host '{host}'. "
                f"Supported tags: {list(rules['tag_options'].keys())}"
            ),
        }
    tag_seq = rules['tag_options'][tag]
    if tag_seq:
        if 'C-term' in tag:
            linker = 'GGTGGT' if include_linker else ''
            gene = gene[:-3] + linker + tag_seq + gene[-3:]
        elif 'N-term' in tag:
            gene = gene[:3] + tag_seq + gene[3:]


    promoter_name = element_overrides.get('promoter_name') or rules['promoter']
    promoter_seq = (element_overrides.get('promoter_seq') or rules['promoter_seq']).upper()
    rbs_name = element_overrides.get('rbs_name') or rules['rbs']
    rbs_seq = (element_overrides.get('rbs_seq') or rules['rbs_seq']).upper()
    terminator_name = element_overrides.get('terminator_name') or rules['terminator']
    terminator_seq = (element_overrides.get('terminator_seq') or rules['terminator_seq']).upper()
    spacer = 'A' * rules['rbs_spacer']

    if kingdom == 'prokaryote':
        final_seq = promoter_seq + rbs_seq + spacer + gene + terminator_seq
        parts = [
            {'name': promoter_name, 'type': 'promoter', 'seq': promoter_seq},
            {'name': rbs_name, 'type': 'RBS', 'seq': rbs_seq + spacer},
            {'name': 'Target Gene (CDS)', 'type': 'CDS',        'seq': gene},
            {'name': terminator_name, 'type': 'terminator', 'seq': terminator_seq},
        ]
    else:
        final_seq = promoter_seq + rbs_seq + gene + terminator_seq
        rbs_type = 'Kozak' if kingdom in ('plant_dicot', 'plant_monocot', 'plant_delivery', 'yeast', 'mammalian') else 'RBS'
        parts = [
            {'name': promoter_name, 'type': 'promoter', 'seq': promoter_seq},
            {'name': rbs_name, 'type': rbs_type, 'seq': rbs_seq},
            {'name': 'Target Gene (CDS)', 'type': 'CDS',        'seq': gene},
            {'name': terminator_name, 'type': 'terminator', 'seq': terminator_seq},
        ]

    # Build 1-based feature table
    features, cursor = [], 1
    for p in parts:
        length = len(p['seq'])
        features.append({
            'name': p['name'], 'type': p['type'],
            'start': cursor,   'end': cursor + length - 1,
            'length': length,
        })
        cursor += length

    gc     = round(_calc_gc(final_seq), 1)
    gc_lo, gc_hi = rules['gc_optimal']

    return {
        'success': True,
        'host': host,
        'kingdom': kingdom,
        'parts': parts,
        'features': features,
        'final_sequence': final_seq,
        'total_length': len(final_seq),
        'gc_content': gc,
        'gc_optimal_range': rules['gc_optimal'],
        'gc_ok': gc_lo <= gc <= gc_hi,
        'promoter_name': promoter_name,
        'promoter_note': rules['promoter_note'],
        'rbs_name': rbs_name,
        'rbs_note': rules['rbs_note'],
        'terminator_name': terminator_name,
        'terminator_note': rules['terminator_note'],
        'vector_suggestion': rules['vector_suggestion'],
        'codon_table_key': rules['codon_table_key'],
        'tag_applied': tag,
        'notes': [],
    }



def build_step3_fidelity_summary(
    original_seq: str,
    optimized_seq: str,
    frame: Dict | None = None,
    tag: str = '',
) -> Dict:
    """Build a compact Step 3 fidelity summary for UI display."""
    original_clean = re.sub(r'[^ATCGatcg]', '', original_seq or '').upper()
    optimized_clean = re.sub(r'[^ATCGatcg]', '', optimized_seq or '').upper()
    frame_dict = frame if isinstance(frame, dict) else {}
    parts = frame_dict.get('parts', []) if isinstance(frame_dict.get('parts', []), list) else []
    cds_part = next((p for p in parts if p.get('type') == 'CDS'), {}) if parts else {}
    framed_cds = str(cds_part.get('seq', '') or '').upper()
    tag_applied = tag or str(frame_dict.get('tag_applied', '') or '')

    original_translation = _translate_cds(original_clean)
    optimized_translation = _translate_cds(optimized_clean)
    translations_match = bool(original_clean and optimized_clean and original_translation == optimized_translation)

    original_has_stop = _has_terminal_stop(original_clean)
    optimized_has_stop = _has_terminal_stop(optimized_clean)
    framed_cds_has_stop = _has_terminal_stop(framed_cds)

    original_len = len(original_clean)
    optimized_len = len(optimized_clean)
    framed_cds_len = len(framed_cds)
    full_frame_len = int(frame_dict.get('total_length', 0) or 0)

    optimization_delta_bp = optimized_len - original_len
    cds_assembly_delta_bp = framed_cds_len - optimized_len
    frame_context_delta_bp = full_frame_len - framed_cds_len

    no_tag_selected = not tag_applied or tag_applied == 'No tag'
    if cds_assembly_delta_bp == 0:
        assembly_reason = 'Expression-frame assembly did not change CDS length.'
    elif no_tag_selected:
        assembly_reason = 'Expression-frame assembly changed CDS length through automatic start/stop completion.'
    else:
        assembly_reason = f'Expression-frame assembly changed CDS length through the selected {tag_applied} tag/linker.'

    if optimization_delta_bp == 0:
        optimization_reason = 'Codon optimization did not change CDS length.'
    else:
        optimization_reason = 'Codon optimization changed CDS length before expression-frame assembly.'

    length_change_reason_summary = ' '.join([
        optimization_reason,
        assembly_reason,
        'Frame-only length beyond the CDS comes from promoter, RBS/Kozak, spacer, and terminator context.',
    ])

    return {
        'original_translation': original_translation,
        'optimized_translation': optimized_translation,
        'translations_match': translations_match,
        'original_has_stop': original_has_stop,
        'optimized_has_stop': optimized_has_stop,
        'framed_cds_has_stop': framed_cds_has_stop,
        'stop_status': bool(optimized_has_stop and (framed_cds_has_stop if framed_cds else True)),
        'original_cds_length': original_len,
        'optimized_cds_length': optimized_len,
        'framed_cds_length': framed_cds_len,
        'full_frame_length': full_frame_len,
        'optimization_delta_bp': optimization_delta_bp,
        'cds_assembly_delta_bp': cds_assembly_delta_bp,
        'frame_context_delta_bp': frame_context_delta_bp,
        'tag_applied': tag_applied,
        'length_change_reason_summary': length_change_reason_summary,
        'has_frame_cds': bool(framed_cds),
        'optimization_changed_cds': optimization_delta_bp != 0,
        'assembly_changed_cds': cds_assembly_delta_bp != 0,
    }

def validate_frame(frame: Dict) -> List[Dict]:
    """
    Biological validation of a built expression frame.

    Each issue dict has:
        severity : 'critical' | 'warning' | 'info'
        code, title, why, fix
    """
    issues: List[Dict] = []
    if not frame.get('success'):
        return [{'severity': 'critical', 'code': 'BUILD_FAILED',
                 'title': 'Frame build failed',
                 'why': frame.get('error', 'Unknown error.'),
                 'fix': 'Check gene sequence input.'}]

    seq     = frame.get('final_sequence', '')
    gc      = frame.get('gc_content', 0.0)
    gc_lo, gc_hi = frame.get('gc_optimal_range', (40, 65))
    kingdom = frame.get('kingdom', '')

    # GC content
    if gc < gc_lo:
        issues.append({
            'severity': 'warning', 'code': 'LOW_GC',
            'title': f'Low GC content ({gc}%)',
            'why': f'GC below {gc_lo}% can reduce DNA stability and transcription efficiency.',
            'fix': 'Consider codon optimization to increase GC or choose a different expression host.',
        })
    elif gc > gc_hi:
        issues.append({
            'severity': 'warning', 'code': 'HIGH_GC',
            'title': f'High GC content ({gc}%)',
            'why': f'GC above {gc_hi}% promotes secondary structures that hinder polymerase processivity.',
            'fix': 'Run codon optimization targeting lower GC, or add a GC-reducing linker.',
        })

    # Find CDS feature
    cds_feat = next((f for f in frame.get('features', []) if f['type'] == 'CDS'), None)
    if cds_feat:
        cds_seq = seq[cds_feat['start'] - 1: cds_feat['end']]
        # Internal stops
        int_stops = _has_internal_stop(cds_seq)
        if int_stops:
            issues.append({
                'severity': 'critical', 'code': 'INTERNAL_STOP',
                'title': f'Premature stop codon(s) at position(s): {int_stops}',
                'why': 'Internal stop codons terminate translation early, producing truncated non-functional protein.',
                'fix': 'Re-check reading frame. Ensure CDS starts at correct ATG and is in-frame.',
            })
        # Poly-T in plant
        if kingdom.startswith('plant'):
            polyt_pos = _find_polyt(cds_seq, n=5)
            if polyt_pos:
                issues.append({
                    'severity': 'warning', 'code': 'POLY_T',
                    'title': f'Poly-T run(s) detected in CDS (positions: {polyt_pos[:3]})',
                    'why': 'Poly-T (>=5T) acts as a plant Pol III terminator signal, causing premature transcript termination.',
                    'fix': 'Use codon optimization to break poly-T runs while preserving amino acid sequence.',
                })

    # RBS/Kozak check
    rbs_name = frame.get('rbs_name', '')
    if kingdom == 'prokaryote' and 'Shine' not in rbs_name and 'SD' not in rbs_name.upper():
        issues.append({
            'severity': 'warning', 'code': 'NO_SD',
            'title': 'Shine-Dalgarno sequence not confirmed',
            'why': 'Prokaryotic ribosomes require a Shine-Dalgarno sequence 6-8 bp upstream of ATG for translation initiation.',
            'fix': 'Ensure RBS contains consensus AGGAGG or similar sequence at correct spacing.',
        })
    if kingdom.startswith('plant') and 'Kozak' not in rbs_name:
        issues.append({
            'severity': 'warning', 'code': 'NO_KOZAK',
            'title': 'Kozak sequence not confirmed',
            'why': 'Plant/eukaryotic ribosomes rely on Kozak context (GCCACC immediately before ATG) for efficient translation.',
            'fix': 'Add GCCACC immediately upstream of the ATG start codon.',
        })
    if kingdom == 'yeast' and 'Kozak' not in rbs_name:
        issues.append({
            'severity': 'warning', 'code': 'NO_KOZAK_YEAST',
            'title': 'Yeast Kozak context not confirmed',
            'why': 'Yeast ribosomes use scanning mechanism; (A/T)AAAATG context improves translation initiation efficiency.',
            'fix': 'Add yeast Kozak sequence (AAAAATG) upstream of the ATG start codon.',
        })
    if kingdom == 'mammalian' and 'Kozak' not in rbs_name:
        issues.append({
            'severity': 'warning', 'code': 'NO_KOZAK_MAMMALIAN',
            'title': 'Mammalian Kozak sequence not confirmed',
            'why': 'Mammalian cap-dependent translation requires optimal Kozak context (GCCACCatg) for efficient initiation.',
            'fix': 'Add GCCACC immediately upstream of the ATG start codon.',
        })
    # Poly-T check: also relevant for yeast
    if kingdom == 'yeast' and cds_feat:
        cds_seq_y = seq[cds_feat['start'] - 1: cds_feat['end']]
        polyt_pos_y = _find_polyt(cds_seq_y, n=5)
        if polyt_pos_y:
            issues.append({
                'severity': 'warning', 'code': 'POLY_T_YEAST',
                'title': f'Poly-T run(s) detected in CDS (positions: {polyt_pos_y[:3]})',
                'why': 'Poly-T (>=5T) can cause premature transcription termination in yeast (Pol II terminator signal).',
                'fix': 'Use codon optimization to break poly-T runs while preserving amino acid sequence.',
            })

    if not issues:
        issues.append({
            'severity': 'info', 'code': 'PASS',
            'title': 'All validation checks passed',
            'why': 'No biological logic errors detected.',
            'fix': 'Proceed to primer design and cloning strategy.',
        })

    return issues


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    test_gene = 'ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA'
    for h in list_supported_hosts():
        result = build_expression_frame(test_gene, h)
        issues = validate_frame(result)
        print(f"{h:30s} | {result['total_length']:5d} bp | GC {result['gc_content']:.1f}% | issues: {len(issues)}")
