# -*- coding: utf-8 -*-
# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
Codon usage frequency analysis and optimization module.
Supports codon preference analysis for multiple host organisms.
"""

import re as _re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Dict, List, Tuple, Optional, Any

_RE_INLINE_WS = _re.compile(r'[ \t\r]')
from Bio.Seq import Seq
import pandas as pd

# ============================================================================
#  Codon usage frequency tables (from Codon Usage Database)
# ============================================================================

# E. coli K-12 codon usage frequencies (per thousand codons)
CODON_USAGE_ECOLI = {
    'TTT': 22.0, 'TTC': 16.0, 'TTA': 13.0, 'TTG': 13.0,
    'CTT': 11.0, 'CTC': 10.0, 'CTA':  4.0, 'CTG': 50.0,
    'ATT': 30.0, 'ATC': 25.0, 'ATA':  7.0, 'ATG': 27.0,
    'GTT': 18.0, 'GTC': 15.0, 'GTA': 11.0, 'GTG': 26.0,
    'TCT':  9.0, 'TCC':  9.0, 'TCA':  7.0, 'TCG':  9.0,
    'CCT':  7.0, 'CCC':  5.0, 'CCA':  8.0, 'CCG': 23.0,
    'ACT':  9.0, 'ACC': 23.0, 'ACA':  7.0, 'ACG': 14.0,
    'GCT': 16.0, 'GCC': 25.0, 'GCA': 21.0, 'GCG': 33.0,
    'TAT': 16.0, 'TAC': 12.0, 'TAA':  2.0, 'TAG':  0.3,
    'CAT': 13.0, 'CAC': 10.0, 'CAA': 15.0, 'CAG': 29.0,
    'AAT': 18.0, 'AAC': 22.0, 'AAA': 33.0, 'AAG': 11.0,
    'GAT': 32.0, 'GAC': 19.0, 'GAA': 40.0, 'GAG': 18.0,
    'TGT':  5.0, 'TGC':  6.0, 'TGA':  1.0, 'TGG': 15.0,
    'CGT': 21.0, 'CGC': 22.0, 'CGA':  3.0, 'CGG':  5.0,
    'AGT':  9.0, 'AGC': 16.0, 'AGA':  2.0, 'AGG':  1.0,
    'GGT': 24.0, 'GGC': 29.0, 'GGA':  8.0, 'GGG': 11.0,
}

# Yeast (S. cerevisiae) codon usage frequencies
CODON_USAGE_YEAST = {
    'TTT': 26.1, 'TTC': 18.4, 'TTA': 26.2, 'TTG': 27.2,
    'CTT': 12.3, 'CTC':  5.4, 'CTA': 13.4, 'CTG': 10.5,
    'ATT': 30.1, 'ATC': 17.2, 'ATA': 17.8, 'ATG': 20.9,
    'GTT': 22.1, 'GTC': 11.8, 'GTA': 11.8, 'GTG': 10.8,
    'TCT': 23.4, 'TCC': 14.2, 'TCA': 18.7, 'TCG':  8.6,
    'CCT': 13.5, 'CCC':  6.8, 'CCA': 18.3, 'CCG':  5.3,
    'ACT': 20.3, 'ACC': 12.7, 'ACA': 17.8, 'ACG':  8.0,
    'GCT': 21.2, 'GCC': 12.6, 'GCA': 16.2, 'GCG':  6.2,
    'TAT': 18.8, 'TAC': 14.8, 'TAA':  1.1, 'TAG':  0.5,
    'CAT': 13.6, 'CAC':  7.8, 'CAA': 27.3, 'CAG': 12.1,
    'AAT': 35.7, 'AAC': 24.8, 'AAA': 41.9, 'AAG': 30.8,
    'GAT': 37.6, 'GAC': 20.2, 'GAA': 45.6, 'GAG': 19.2,
    'TGT':  8.1, 'TGC':  4.8, 'TGA':  0.7, 'TGG': 10.4,
    'CGT':  6.4, 'CGC':  2.6, 'CGA':  3.0, 'CGG':  1.7,
    'AGT': 14.2, 'AGC':  9.8, 'AGA': 21.3, 'AGG':  9.2,
    'GGT': 23.9, 'GGC':  9.8, 'GGA': 10.9, 'GGG':  6.0,
}

# Human codon usage frequencies
CODON_USAGE_HUMAN = {
    'TTT': 17.6, 'TTC': 20.3, 'TTA':  7.7, 'TTG': 12.9,
    'CTT': 13.2, 'CTC': 19.6, 'CTA':  7.2, 'CTG': 39.6,
    'ATT': 16.0, 'ATC': 20.8, 'ATA':  7.5, 'ATG': 22.0,
    'GTT': 11.0, 'GTC': 14.5, 'GTA':  7.1, 'GTG': 28.1,
    'TCT': 15.2, 'TCC': 17.7, 'TCA': 12.2, 'TCG':  4.4,
    'CCT': 17.5, 'CCC': 19.8, 'CCA': 16.9, 'CCG':  6.9,
    'ACT': 13.1, 'ACC': 18.9, 'ACA': 15.1, 'ACG':  6.1,
    'GCT': 18.4, 'GCC': 27.7, 'GCA': 15.8, 'GCG':  7.4,
    'TAT': 12.2, 'TAC': 15.3, 'TAA':  1.0, 'TAG':  0.8,
    'CAT': 10.9, 'CAC': 15.1, 'CAA': 12.3, 'CAG': 34.2,
    'AAT': 17.0, 'AAC': 19.1, 'AAA': 24.4, 'AAG': 31.9,
    'GAT': 21.8, 'GAC': 25.1, 'GAA': 29.0, 'GAG': 39.6,
    'TGT': 10.6, 'TGC': 12.6, 'TGA':  1.6, 'TGG': 13.2,
    'CGT':  4.5, 'CGC': 10.4, 'CGA':  6.2, 'CGG': 11.4,
    'AGT': 12.1, 'AGC': 19.5, 'AGA': 12.2, 'AGG': 12.0,
    'GGT': 10.8, 'GGC': 22.2, 'GGA': 16.5, 'GGG': 16.5,
}

# Rice (O. sativa) codon usage frequencies
CODON_USAGE_RICE = {
    'TTT': 20.8, 'TTC': 24.6, 'TTA':  8.9, 'TTG': 16.2,
    'CTT': 15.3, 'CTC': 16.8, 'CTA':  7.8, 'CTG': 24.5,
    'ATT': 18.2, 'ATC': 21.5, 'ATA':  9.8, 'ATG': 24.3,
    'GTT': 14.5, 'GTC': 15.8, 'GTA':  8.9, 'GTG': 23.6,
    'TCT': 16.8, 'TCC': 15.2, 'TCA': 13.5, 'TCG':  9.8,
    'CCT': 15.6, 'CCC': 12.8, 'CCA': 14.2, 'CCG': 11.5,
    'ACT': 16.2, 'ACC': 18.5, 'ACA': 14.8, 'ACG': 10.2,
    'GCT': 20.5, 'GCC': 24.8, 'GCA': 15.2, 'GCG': 12.8,
    'TAT': 15.6, 'TAC': 18.2, 'TAA':  0.9, 'TAG':  0.6,
    'CAT': 13.2, 'CAC': 16.5, 'CAA': 15.8, 'CAG': 28.5,
    'AAT': 19.5, 'AAC': 22.8, 'AAA': 28.6, 'AAG': 32.5,
    'GAT': 24.5, 'GAC': 26.8, 'GAA': 32.5, 'GAG': 35.2,
    'TGT': 11.2, 'TGC': 13.5, 'TGA':  1.2, 'TGG': 14.5,
    'CGT':  8.5, 'CGC': 12.8, 'CGA':  7.2, 'CGG':  9.5,
    'AGT': 13.5, 'AGC': 16.8, 'AGA': 14.2, 'AGG': 13.5,
    'GGT': 15.8, 'GGC': 24.5, 'GGA': 18.2, 'GGG': 16.5,
}

# Maize (Zea mays) codon usage frequencies
CODON_USAGE_MAIZE = {
    'TTT': 17.3, 'TTC': 21.8, 'TTA':  7.2, 'TTG': 15.6,
    'CTT': 14.8, 'CTC': 18.2, 'CTA':  7.5, 'CTG': 26.3,
    'ATT': 16.5, 'ATC': 22.8, 'ATA':  8.6, 'ATG': 23.8,
    'GTT': 12.8, 'GTC': 16.5, 'GTA':  8.2, 'GTG': 25.4,
    'TCT': 14.5, 'TCC': 16.8, 'TCA': 12.2, 'TCG':  8.5,
    'CCT': 14.2, 'CCC': 14.8, 'CCA': 13.5, 'CCG': 10.2,
    'ACT': 14.8, 'ACC': 20.5, 'ACA': 13.2, 'ACG':  9.5,
    'GCT': 18.5, 'GCC': 26.2, 'GCA': 14.8, 'GCG': 11.5,
    'TAT': 13.8, 'TAC': 17.5, 'TAA':  0.8, 'TAG':  0.5,
    'CAT': 12.5, 'CAC': 15.8, 'CAA': 14.5, 'CAG': 27.2,
    'AAT': 17.2, 'AAC': 21.5, 'AAA': 25.8, 'AAG': 33.5,
    'GAT': 22.5, 'GAC': 27.2, 'GAA': 30.5, 'GAG': 36.8,
    'TGT': 10.2, 'TGC': 12.8, 'TGA':  1.0, 'TGG': 13.8,
    'CGT':  7.5, 'CGC': 11.5, 'CGA':  6.8, 'CGG':  9.2,
    'AGT': 12.2, 'AGC': 15.5, 'AGA': 13.5, 'AGG': 14.2,
    'GGT': 14.5, 'GGC': 25.8, 'GGA': 17.5, 'GGG': 15.2,
}

# Arabidopsis thaliana codon usage frequencies
CODON_USAGE_ARABIDOPSIS = {
    'TTT': 20.5, 'TTC': 21.8, 'TTA': 10.2, 'TTG': 18.5,
    'CTT': 17.8, 'CTC': 15.2, 'CTA':  9.5, 'CTG': 18.8,
    'ATT': 20.8, 'ATC': 19.5, 'ATA': 11.2, 'ATG': 23.5,
    'GTT': 16.5, 'GTC': 14.2, 'GTA': 10.5, 'GTG': 20.8,
    'TCT': 18.5, 'TCC': 14.8, 'TCA': 15.2, 'TCG':  7.5,
    'CCT': 16.8, 'CCC': 10.5, 'CCA': 16.2, 'CCG':  7.8,
    'ACT': 17.5, 'ACC': 16.8, 'ACA': 16.5, 'ACG':  8.2,
    'GCT': 22.5, 'GCC': 20.8, 'GCA': 16.5, 'GCG':  8.5,
    'TAT': 16.8, 'TAC': 17.5, 'TAA':  1.0, 'TAG':  0.5,
    'CAT': 14.5, 'CAC': 14.8, 'CAA': 18.5, 'CAG': 22.5,
    'AAT': 22.5, 'AAC': 22.8, 'AAA': 31.5, 'AAG': 34.2,
    'GAT': 27.5, 'GAC': 24.8, 'GAA': 35.2, 'GAG': 32.5,
    'TGT': 10.8, 'TGC': 11.5, 'TGA':  1.1, 'TGG': 13.5,
    'CGT':  6.8, 'CGC':  8.5, 'CGA':  6.2, 'CGG':  7.5,
    'AGT': 14.2, 'AGC': 15.8, 'AGA': 18.5, 'AGG': 16.8,
    'GGT': 17.8, 'GGC': 20.5, 'GGA': 20.2, 'GGG': 13.5,
}

# Tobacco (N. benthamiana) codon usage frequencies
CODON_USAGE_TOBACCO = {
    'TTT': 19.8, 'TTC': 20.5, 'TTA':  9.8, 'TTG': 17.2,
    'CTT': 16.5, 'CTC': 14.8, 'CTA':  9.2, 'CTG': 17.5,
    'ATT': 19.5, 'ATC': 18.8, 'ATA': 10.8, 'ATG': 22.8,
    'GTT': 15.8, 'GTC': 13.5, 'GTA':  9.8, 'GTG': 19.5,
    'TCT': 17.8, 'TCC': 14.2, 'TCA': 14.8, 'TCG':  7.2,
    'CCT': 16.2, 'CCC': 10.2, 'CCA': 15.8, 'CCG':  7.5,
    'ACT': 17.2, 'ACC': 16.2, 'ACA': 15.8, 'ACG':  7.8,
    'GCT': 21.8, 'GCC': 19.5, 'GCA': 15.8, 'GCG':  8.2,
    'TAT': 16.2, 'TAC': 17.0, 'TAA':  1.0, 'TAG':  0.5,
    'CAT': 14.0, 'CAC': 14.2, 'CAA': 17.8, 'CAG': 21.5,
    'AAT': 21.8, 'AAC': 22.2, 'AAA': 30.5, 'AAG': 33.5,
    'GAT': 26.2, 'GAC': 23.5,
    'GAA': 34.2, 'GAG': 31.5,
    'TGT': 10.2, 'TGC': 11.0, 'TGA':  1.0, 'TGG': 13.0,
    'CGT':  6.5, 'CGC':  8.2, 'CGA':  6.0, 'CGG':  7.2,
    'AGT': 13.8, 'AGC': 15.2, 'AGA': 17.8, 'AGG': 16.2,
    'GGT': 17.2, 'GGC': 19.8, 'GGA': 19.5, 'GGG': 13.0,
}

# Agrobacterium tumefaciens
CODON_USAGE_AGROBACTERIUM = {
    'TTT': 15.2, 'TTC': 22.8, 'TTA':  5.5, 'TTG': 14.8,
    'CTT':  9.5, 'CTC': 14.2, 'CTA':  3.8, 'CTG': 38.5,
    'ATT': 18.5, 'ATC': 28.5, 'ATA':  4.5, 'ATG': 22.5,
    'GTT': 10.5, 'GTC': 18.2, 'GTA':  7.8, 'GTG': 28.5,
    'TCT':  6.8, 'TCC': 12.5, 'TCA':  5.5, 'TCG': 14.8,
    'CCT':  5.8, 'CCC':  8.5, 'CCA':  6.5, 'CCG': 28.5,
    'ACT':  6.5, 'ACC': 22.8, 'ACA':  5.8, 'ACG': 18.5,
    'GCT': 12.5, 'GCC': 28.5, 'GCA': 15.8, 'GCG': 35.2,
    'TAT': 10.5, 'TAC': 18.5, 'TAA':  1.5, 'TAG':  0.5,
    'CAT':  8.5, 'CAC': 14.5, 'CAA': 10.5, 'CAG': 28.5,
    'AAT': 10.5, 'AAC': 20.5, 'AAA': 18.5, 'AAG': 16.5,
    'GAT': 18.5, 'GAC': 28.5, 'GAA': 25.5, 'GAG': 22.5,
    'TGT':  3.8, 'TGC':  8.5, 'TGA':  0.8, 'TGG': 15.5,
    'CGT': 14.5, 'CGC': 22.5, 'CGA':  4.5, 'CGG':  8.5,
    'AGT':  5.5, 'AGC': 10.5, 'AGA':  3.5, 'AGG':  2.5,
    'GGT': 16.5, 'GGC': 28.5, 'GGA':  8.5, 'GGG':  9.5,
}

# Host codon table registry
CODON_TABLES = {
    'E.coli': CODON_USAGE_ECOLI,
    'Yeast': CODON_USAGE_YEAST,
    'Human': CODON_USAGE_HUMAN,
    'Rice': CODON_USAGE_RICE,
    'Maize': CODON_USAGE_MAIZE,
    'Arabidopsis': CODON_USAGE_ARABIDOPSIS,
    'Tobacco': CODON_USAGE_TOBACCO,
    'Agrobacterium': CODON_USAGE_AGROBACTERIUM,
}

CODON_TABLE_METADATA = {
    'E.coli': {
        'table_id': 'codon_usage_ecoli_k12_local_reference',
        'host_label': 'E.coli',
        'organism_or_scope': 'Escherichia coli K-12; strain context is noted in the local table comment.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Yeast': {
        'table_id': 'codon_usage_s_cerevisiae_local_reference',
        'host_label': 'Yeast',
        'organism_or_scope': 'Saccharomyces cerevisiae; strain/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Human': {
        'table_id': 'codon_usage_human_local_reference',
        'host_label': 'Human',
        'organism_or_scope': 'Homo sapiens broad organism table; tissue, cell-line, and transcript-set scope are not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Rice': {
        'table_id': 'codon_usage_o_sativa_local_reference',
        'host_label': 'Rice',
        'organism_or_scope': 'Oryza sativa; cultivar/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Maize': {
        'table_id': 'codon_usage_z_mays_local_reference',
        'host_label': 'Maize',
        'organism_or_scope': 'Zea mays; cultivar/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Arabidopsis': {
        'table_id': 'codon_usage_a_thaliana_local_reference',
        'host_label': 'Arabidopsis',
        'organism_or_scope': 'Arabidopsis thaliana; accession/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Tobacco': {
        'table_id': 'codon_usage_n_benthamiana_local_reference',
        'host_label': 'Tobacco',
        'organism_or_scope': 'Nicotiana benthamiana; accession/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
    'Agrobacterium': {
        'table_id': 'codon_usage_a_tumefaciens_local_reference',
        'host_label': 'Agrobacterium',
        'organism_or_scope': 'Agrobacterium tumefaciens; strain/source dataset scope is not recorded.',
        'source_note': (
            'Repository-embedded local/reference table. Existing source comments mention Codon Usage Database, '
            'but table-level citation, download, and license metadata are not fully documented in this repository.'
        ),
        'version_or_date_note': 'No source version, download date, or curation date is recorded in the repository.',
        'provenance_status': 'local_reference_only',
        'draft_use_status': 'not_enabled_for_rewrite',
        'limitation_note': (
            'Use for Codon Usage Preview documentation context only; not expression or yield forecasting, '
            'biological recommendation, or wet-lab readiness judgment.'
        ),
        'documentation_review_note': (
            'Provenance review is required before using this table for any future codon adaptation draft '
            'or codon rewrite preview.'
        ),
        'manual_review_required': True,
    },
}


def get_codon_table_metadata(host='E.coli'):
    """Return structured provenance metadata for a supported codon usage table."""
    resolved_host = host if host in CODON_TABLE_METADATA else 'E.coli'
    metadata = CODON_TABLE_METADATA.get(resolved_host) or CODON_TABLE_METADATA['E.coli']
    return dict(metadata)

# Amino acid to codon mapping
AA_TO_CODONS = {
    'F': ['TTT', 'TTC'],
    'L': ['TTA', 'TTG', 'CTT', 'CTC', 'CTA', 'CTG'],
    'I': ['ATT', 'ATC', 'ATA'],
    'M': ['ATG'],
    'V': ['GTT', 'GTC', 'GTA', 'GTG'],
    'S': ['TCT', 'TCC', 'TCA', 'TCG', 'AGT', 'AGC'],
    'P': ['CCT', 'CCC', 'CCA', 'CCG'],
    'T': ['ACT', 'ACC', 'ACA', 'ACG'],
    'A': ['GCT', 'GCC', 'GCA', 'GCG'],
    'Y': ['TAT', 'TAC'],
    '*': ['TAA', 'TAG', 'TGA'],
    'H': ['CAT', 'CAC'],
    'Q': ['CAA', 'CAG'],
    'N': ['AAT', 'AAC'],
    'K': ['AAA', 'AAG'],
    'D': ['GAT', 'GAC'],
    'E': ['GAA', 'GAG'],
    'C': ['TGT', 'TGC'],
    'W': ['TGG'],
    'R': ['CGT', 'CGC', 'CGA', 'CGG', 'AGA', 'AGG'],
    'G': ['GGT', 'GGC', 'GGA', 'GGG'],
}


# ============================================================================
#  CAI Engine  - Sharp & Li (1987) relative adaptiveness w_ij algorithm
# ============================================================================

@lru_cache(maxsize=16)
def _build_relative_adaptiveness(host: str) -> dict:
    w = {}
    for aa, codons in AA_TO_CODONS.items():
        if aa == '*':
            continue
        codon_table = CODON_TABLES.get(host, CODON_USAGE_ECOLI)
        freqs = {c: codon_table.get(c, 0.0) for c in codons}
        max_f = max(freqs.values()) if freqs else 0.0
        if max_f <= 0:
            for c in codons:
                w[c] = 1.0 / len(codons)
        else:
            for c, f in freqs.items():
                w[c] = f / max_f
    return w


def calculate_cai(dna_sequence, host='E.coli'):
    import math
    seq = _normalize_dna_sequence(dna_sequence)
    seq = seq[:len(seq) - len(seq) % 3]
    if not seq:
        return 0.0
    if host not in CODON_TABLES:
        host = 'E.coli'
    w_table = _build_relative_adaptiveness(host)
    log_w_sum = 0.0
    n_codons = 0
    for i in range(0, len(seq) - 2, 3):
        codon = seq[i:i + 3]
        if codon in ('TAA', 'TAG', 'TGA'):
            continue
        if codon in w_table:
            log_w_sum += math.log(max(w_table[codon], 1e-10))
            n_codons += 1
    if n_codons == 0:
        return 0.0
    return round(math.exp(log_w_sum / n_codons), 4)


def analyze_codon_usage(dna_sequence, host='E.coli'):
    from Bio.Seq import Seq
    seq = dna_sequence.upper().replace(' ', '').replace('\n', '')
    seq = seq[:len(seq) - len(seq) % 3]
    if host not in CODON_TABLES:
        host = 'E.coli'
    codon_table = CODON_TABLES[host]
    codon_counts = {}
    total_codons = 0
    for i in range(0, len(seq), 3):
        c = seq[i:i + 3]
        if len(c) == 3:
            codon_counts[c] = codon_counts.get(c, 0) + 1
            total_codons += 1
    # Sharp & Li (1987) geometric-mean CAI
    cai = calculate_cai(seq, host)
    rare = [
        {'codon': c, 'count': n, 'frequency': codon_table.get(c, 0.0),
         'percentage': (n / total_codons) * 100 if total_codons else 0}
        for c, n in codon_counts.items()
        if codon_table.get(c, 0.0) < 5.0 and c not in ('TAA', 'TAG', 'TGA')
    ]
    aa_usage = {}
    for codon, count in codon_counts.items():
        try:
            aa = str(Seq(codon).translate())
            if aa not in aa_usage:
                aa_usage[aa] = {'total': 0, 'codons': {}}
            aa_usage[aa]['total'] += count
            aa_usage[aa]['codons'][codon] = count
        except Exception:
            pass
    return {
        'success': True, 'host': host, 'total_codons': total_codons,
        'unique_codons': len(codon_counts), 'cai': cai,
        'cai_method': 'Sharp & Li (1987) geometric mean',
        'codon_counts': codon_counts, 'rare_codons': rare, 'aa_usage': aa_usage,
    }

def optimize_codons(protein_sequence, host='E.coli'):
    protein = protein_sequence.upper().replace(' ', '').replace('\n', '')
    if host not in CODON_TABLES: host = 'E.coli'
    codon_table = CODON_TABLES[host]
    opt, warnings = [], []
    for i, aa in enumerate(protein):
        if aa not in AA_TO_CODONS:
            warnings.append(f'Position {i+1}: unknown amino acid {aa}'); continue
        opt.append(max(AA_TO_CODONS[aa], key=lambda c: codon_table.get(c, 0)))
    seq = ''.join(opt)
    analysis = analyze_codon_usage(seq, host)
    return {'success': True, 'original_protein': protein, 'optimized_dna': seq,
            'length': len(seq), 'cai': analysis.get('cai', 0),
            'warnings': warnings, 'host': host}


def compare_codon_usage(dna_sequence, hosts=None):
    import pandas as pd
    if hosts is None: hosts = list(CODON_TABLES.keys())
    results = []
    for host in hosts:
        a = analyze_codon_usage(dna_sequence, host)
        if a.get('success'):
            results.append({'Host': host, 'CAI': a['cai'],
                'Total Codons': a['total_codons'], 'Rare Codons': len(a['rare_codons']),
                'Rare %': round(sum(r['percentage'] for r in a['rare_codons']), 1)})
    return pd.DataFrame(results)


def get_optimal_codon(amino_acid, host='E.coli'):
    if amino_acid not in AA_TO_CODONS: return ''
    if host not in CODON_TABLES: host = 'E.coli'
    return max(AA_TO_CODONS[amino_acid], key=lambda c: CODON_TABLES[host].get(c, 0))


def calculate_gc_content(dna_sequence):
    seq = dna_sequence.upper()
    return (seq.count('G') + seq.count('C')) / len(seq) * 100 if seq else 0.0


def identify_problematic_regions(dna_sequence, window_size=50):
    seq = dna_sequence.upper(); problems = []
    for i in range(0, len(seq) - window_size + 1, 10):
        w = seq[i:i+window_size]; gc = calculate_gc_content(w)
        if gc > 75: problems.append({'type':'High GC','position':i,'gc_content':round(gc,1),'sequence':w[:20]+'...'})
        elif gc < 25: problems.append({'type':'Low GC','position':i,'gc_content':round(gc,1),'sequence':w[:20]+'...'})
        for base in ['A','T','G','C']:
            if base*6 in w: problems.append({'type':f'{base} repeat','position':i+w.index(base*6),'sequence':base*6})
    return problems

# ============================================================================
#  Deterministic constraint-aware CDS optimisation core
# ============================================================================

DEFAULT_FORBIDDEN_MOTIFS = [
    'GAATTC',
    'AAGCTT',
    'GGATCC',
    'GGTCTC',
    'GAGACC',
    'CGTCTC',
    'GAGACG',
]

DNA_BASES = set('ATGC')
STOP_CODONS = {'TAA', 'TAG', 'TGA'}
DEFAULT_CONSTRAINTS = {
    'forbidden_motifs': DEFAULT_FORBIDDEN_MOTIFS,
    'gc_window_size': 30,
    'gc_window_min': 30.0,
    'gc_window_max': 70.0,
    'homopolymer_limit': 6,
    'repeat_k': 9,
    'repeat_occurrence_limit': 1,
    'max_passes': 3,
}

CODON_TO_AA = {}
for _aa, _codons in AA_TO_CODONS.items():
    for _codon in _codons:
        CODON_TO_AA[_codon] = _aa

_SEQ_SCORE_CACHE_MAXSIZE = 256
_PARALLEL_MIN_CODONS = 900
_PARALLEL_MAX_WORKERS = 8


def _freeze_settings(settings):
    """Convert settings dict into an immutable tuple for caching keys."""
    frozen = []
    for key in sorted(settings.keys()):
        value = settings[key]
        if isinstance(value, list):
            value = tuple(value)
        frozen.append((key, value))
    return tuple(frozen)


def _thaw_settings(frozen_settings):
    settings = dict(frozen_settings)
    motifs = settings.get('forbidden_motifs')
    if motifs is not None and not isinstance(motifs, list):
        settings['forbidden_motifs'] = list(motifs)
    return settings



def _normalize_dna_sequence(sequence):
    if sequence is None:
        return ''
    if not isinstance(sequence, str):
        sequence = str(sequence)
    lines = [line.strip() for line in sequence.strip().splitlines() if not line.strip().startswith('>')]
    return ''.join(lines).replace(' ', '').replace('\t', '').replace('\r', '').upper()


def _resolve_host(host):
    return host if host in CODON_TABLES else 'E.coli'


def _translate_cds(sequence):
    seq = _normalize_dna_sequence(sequence)
    if not seq or len(seq) % 3 != 0:
        return ''
    protein = []
    for i in range(0, len(seq), 3):
        codon = seq[i:i + 3]
        aa = CODON_TO_AA.get(codon)
        if aa is None:
            return ''
        protein.append(aa)
    return ''.join(protein)


def _scan_forbidden_motifs(sequence, forbidden_motifs=None):
    seq = _normalize_dna_sequence(sequence)
    motifs = [_normalize_dna_sequence(m) for m in (forbidden_motifs or DEFAULT_FORBIDDEN_MOTIFS) if _normalize_dna_sequence(m)]
    hits = []
    for motif in motifs:
        start = 0
        while True:
            idx = seq.find(motif, start)
            if idx < 0:
                break
            hits.append({'motif': motif, 'start': idx, 'end': idx + len(motif)})
            start = idx + 1
    return hits


def _scan_homopolymers(sequence, limit=6):
    seq = _normalize_dna_sequence(sequence)
    if limit <= 1:
        return []
    hits = []
    run_base = None
    run_start = 0
    for i, base in enumerate(seq):
        if base != run_base:
            run_base = base
            run_start = i
            continue
        run_len = i - run_start + 1
        if run_len == limit:
            hits.append({'base': base, 'start': run_start, 'end': i + 1, 'length': run_len, 'sequence': seq[run_start:i + 1]})
        elif run_len > limit and hits and hits[-1]['start'] == run_start:
            hits[-1]['end'] = i + 1
            hits[-1]['length'] = run_len
            hits[-1]['sequence'] = seq[run_start:i + 1]
    return hits


def _scan_repeats(sequence, k=9, occurrence_limit=1):
    seq = _normalize_dna_sequence(sequence)
    if k <= 0 or len(seq) < k:
        return []
    positions = defaultdict(list)
    upper = len(seq) - k + 1
    for i in range(upper):

        positions[seq[i:i + k]].append(i)
    hits = []
    for motif, starts in positions.items():
        if len(starts) > occurrence_limit:
            hits.append({'motif': motif, 'length': k, 'count': len(starts), 'positions': starts})
    hits.sort(key=lambda item: (-item['count'], item['positions'][0], item['motif']))
    return hits


def _scan_local_gc_windows(sequence, window_size=30, gc_min=30.0, gc_max=70.0):
    seq = _normalize_dna_sequence(sequence)
    if not seq:
        return []
    window_size = max(1, min(int(window_size), len(seq)))
    hits = []
    for start in range(0, len(seq) - window_size + 1):
        window = seq[start:start + window_size]
        gc = calculate_gc_content(window)
        if gc < gc_min or gc > gc_max:
            hits.append({
                'start': start,
                'end': start + window_size,
                'gc_percent': round(gc, 2),
                'status': 'low' if gc < gc_min else 'high',
                'sequence': window,
            })
    return hits


@lru_cache(maxsize=16)
def _build_synonymous_rankings(host: str = 'E.coli') -> dict:
    host = _resolve_host(host)
    codon_table = CODON_TABLES[host]
    rankings = {}
    for aa, codons in AA_TO_CODONS.items():
        if aa == '*':
            continue
        rankings[aa] = sorted(codons, key=lambda codon: (-codon_table.get(codon, 0.0), codon))
    return rankings


def _constraint_settings(overrides=None):
    settings = dict(DEFAULT_CONSTRAINTS)
    if overrides:
        settings.update({k: v for k, v in overrides.items() if v is not None})
    settings['forbidden_motifs'] = [
        _normalize_dna_sequence(m) for m in settings.get('forbidden_motifs', DEFAULT_FORBIDDEN_MOTIFS)
        if _normalize_dna_sequence(m)
    ]
    return settings


def _sequence_issue_score(sequence, settings, host='E.coli'):
    host = _resolve_host(host)
    codon_table = CODON_TABLES[host]
    seq = _normalize_dna_sequence(sequence)
    forbidden_hits = _scan_forbidden_motifs(seq, settings['forbidden_motifs'])
    homopolymer_hits = _scan_homopolymers(seq, settings['homopolymer_limit'])
    repeat_hits = _scan_repeats(seq, settings['repeat_k'], settings['repeat_occurrence_limit'])
    gc_window_hits = _scan_local_gc_windows(seq, settings['gc_window_size'], settings['gc_window_min'], settings['gc_window_max'])
    codons = [seq[i:i + 3] for i in range(0, len(seq), 3) if len(seq[i:i + 3]) == 3]
    cai = calculate_cai(seq, host)
    codon_penalty = 0.0
    for codon in codons:
        if codon in STOP_CODONS:
            continue
        codon_penalty += max(0.0, 100.0 - codon_table.get(codon, 0.0)) / 100.0
    score = (
        len(forbidden_hits) * 1000000
        + len(homopolymer_hits) * 100000
        + len(repeat_hits) * 50000
        + len(gc_window_hits) * 10000
        + round(codon_penalty, 6)
        - cai
    )
    return score, {
        'forbidden_hits': forbidden_hits,
        'homopolymer_hits': homopolymer_hits,
        'repeat_hits': repeat_hits,
        'gc_window_hits': gc_window_hits,
        'cai': cai,
    }


def _sequence_issue_score_cached_entry(sequence, settings, host='E.coli'):
    frozen_settings = _freeze_settings(settings)
    return _sequence_issue_score_cached(_normalize_dna_sequence(sequence), _resolve_host(host), frozen_settings)


@lru_cache(maxsize=_SEQ_SCORE_CACHE_MAXSIZE)
def _sequence_issue_score_cached(sequence, host, frozen_settings):
    settings = _thaw_settings(frozen_settings)
    return _sequence_issue_score(sequence, settings, host)


def _score_candidates_parallel(base_sequence, start, original_protein, settings, host, candidate_codons):
    """Evaluate synonymous codon candidates in parallel for large CDS."""
    sequence_prefix = base_sequence[:start]
    sequence_suffix = base_sequence[start + 3:]

    def _evaluate(candidate_codon):
        candidate_seq = sequence_prefix + candidate_codon + sequence_suffix
        candidate_score, candidate_diag = _score_candidate_sequence(
            candidate_seq, original_protein, settings, host
        )
        return candidate_codon, candidate_seq, candidate_score, candidate_diag

    max_workers = min(_PARALLEL_MAX_WORKERS, max(2, len(candidate_codons)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_evaluate, candidate_codons))


def _candidate_codons_for_position(amino_acid, current_codon, rankings):
    ordered = list(rankings.get(amino_acid, [current_codon]))
    if current_codon in ordered:
        ordered.remove(current_codon)
    return [current_codon] + ordered


def _score_candidate_sequence(candidate_sequence, original_protein, settings, host='E.coli'):
    if _translate_cds(candidate_sequence) != original_protein:
        return float('inf'), {'protein_mismatch': True}
    return _sequence_issue_score_cached_entry(candidate_sequence, settings, host)


def _target_codon_indices(sequence, diagnostics, settings):
    seq_len = len(sequence)
    indices = set()
    for hit in diagnostics.get('forbidden_hits', []):
        for pos in range(hit['start'] // 3, (hit['end'] - 1) // 3 + 1):
            indices.add(pos)
    for hit in diagnostics.get('homopolymer_hits', []):
        for pos in range(hit['start'] // 3, (hit['end'] - 1) // 3 + 1):
            indices.add(pos)
    for hit in diagnostics.get('gc_window_hits', []):
        for pos in range(hit['start'] // 3, (hit['end'] - 1) // 3 + 1):
            indices.add(pos)
    for hit in diagnostics.get('repeat_hits', []):
        for start in hit.get('positions', []):
            for pos in range(start // 3, min((start + settings['repeat_k'] - 1) // 3 + 1, seq_len // 3)):
                indices.add(pos)
    return sorted(idx for idx in indices if 0 <= idx < seq_len // 3)


def _build_diagnostics_summary(sequence, host='E.coli', constraints=None):
    settings = _constraint_settings(constraints)
    seq = _normalize_dna_sequence(sequence)
    protein = _translate_cds(seq)
    score, diagnostics = _sequence_issue_score_cached_entry(seq, settings, host)
    analysis = analyze_codon_usage(seq, _resolve_host(host)) if seq and len(seq) % 3 == 0 else {
        'success': False, 'cai': 0.0, 'rare_codons': [], 'codon_counts': {}
    }
    return {
        'sequence': seq,
        'length_bp': len(seq),
        'codon_count': len(seq) // 3,
        'protein': protein[:-1] if protein.endswith('*') else protein,
        'has_terminal_stop': bool(protein.endswith('*')) if protein else False,
        'gc_percent': round(calculate_gc_content(seq), 2),
        'cai': analysis.get('cai', diagnostics.get('cai', 0.0)),
        'rare_codons': analysis.get('rare_codons', []),
        'forbidden_hits': diagnostics['forbidden_hits'],
        'homopolymer_hits': diagnostics['homopolymer_hits'],
        'repeat_hits': diagnostics['repeat_hits'],
        'gc_window_hits': diagnostics['gc_window_hits'],
        'constraint_score': score,
        'constraints_ok': not any([
            diagnostics['forbidden_hits'],
            diagnostics['homopolymer_hits'],
            diagnostics['repeat_hits'],
            diagnostics['gc_window_hits'],
        ]),
    }


def validate_cds_sequence(sequence, host='E.coli'):
    seq = _normalize_dna_sequence(sequence)
    errors = []
    warnings = []
    if not seq:
        errors.append('CDS sequence is empty.')
    invalid_bases = sorted({base for base in seq if base not in DNA_BASES})
    if invalid_bases:
        errors.append(f"CDS contains invalid DNA characters: {''.join(invalid_bases)}")
    if seq and len(seq) % 3 != 0:
        errors.append('CDS length must be divisible by 3.')
    protein = _translate_cds(seq) if not errors else ''
    if seq and not errors and not protein:
        errors.append('CDS could not be translated with the standard codon table.')
    internal_stop_positions = []
    if protein:
        for idx, aa in enumerate(protein[:-1]):
            if aa == '*':
                internal_stop_positions.append(idx + 1)
        if internal_stop_positions:
            errors.append(f'CDS contains internal stop codons at amino acid positions: {internal_stop_positions}')
        if protein.endswith('*'):
            warnings.append('CDS includes a terminal stop codon.')
    return {
        'success': len(errors) == 0,
        'valid': len(errors) == 0,
        'sequence': seq,
        'host': _resolve_host(host),
        'length_bp': len(seq),
        'protein': protein[:-1] if protein.endswith('*') else protein,
        'has_terminal_stop': bool(protein.endswith('*')) if protein else False,
        'errors': errors,
        'warnings': warnings,
    }


def analyze_sequence_constraints(sequence, host='E.coli', forbidden_motifs=None,
                                 gc_window_size=30, gc_window_min=30.0, gc_window_max=70.0,
                                 homopolymer_limit=6, repeat_k=9, repeat_occurrence_limit=1):
    validation = validate_cds_sequence(sequence, host)
    settings = _constraint_settings({
        'forbidden_motifs': forbidden_motifs if forbidden_motifs is not None else DEFAULT_FORBIDDEN_MOTIFS,
        'gc_window_size': gc_window_size,
        'gc_window_min': gc_window_min,
        'gc_window_max': gc_window_max,
        'homopolymer_limit': homopolymer_limit,
        'repeat_k': repeat_k,
        'repeat_occurrence_limit': repeat_occurrence_limit,
    })
    diagnostics = _build_diagnostics_summary(validation['sequence'], validation['host'], settings)
    return {
        'success': validation['success'],
        'valid': validation['valid'],
        'host': validation['host'],
        'sequence': validation['sequence'],
        'protein': validation['protein'],
        'errors': validation['errors'],
        'warnings': validation['warnings'],
        'constraints': settings,
        'diagnostics': diagnostics,
    }


def optimize_cds_sequence(sequence, host='E.coli', forbidden_motifs=None,
                          gc_window_size=30, gc_window_min=30.0, gc_window_max=70.0,
                          homopolymer_limit=6, repeat_k=9, repeat_occurrence_limit=1,
                          max_passes=3):
    settings = _constraint_settings({
        'forbidden_motifs': forbidden_motifs if forbidden_motifs is not None else DEFAULT_FORBIDDEN_MOTIFS,
        'gc_window_size': gc_window_size,
        'gc_window_min': gc_window_min,
        'gc_window_max': gc_window_max,
        'homopolymer_limit': homopolymer_limit,
        'repeat_k': repeat_k,
        'repeat_occurrence_limit': repeat_occurrence_limit,
        'max_passes': max_passes,
    })
    validation = validate_cds_sequence(sequence, host)
    before = _build_diagnostics_summary(validation['sequence'], validation['host'], settings)
    if not validation['success']:
        return {
            'success': False,
            'host': validation['host'],
            'input_sequence': validation['sequence'],
            'optimized_sequence': validation['sequence'],
            'protein': validation['protein'],
            'errors': validation['errors'],
            'warnings': validation['warnings'],
            'constraints': settings,
            'before': before,
            'after': before,
            'changed': False,
            'history': [],
            'result_schema_version': 'constraint_aware_cds_optimizer_v1',
        }

    original_seq = validation['sequence']
    original_protein = _translate_cds(original_seq)
    working_seq = original_seq
    rankings = _build_synonymous_rankings(validation['host'])
    history = []

    for pass_index in range(max(1, int(settings['max_passes']))):
        current_score, current_diag = _sequence_issue_score_cached_entry(working_seq, settings, validation['host'])
        target_indices = _target_codon_indices(working_seq, current_diag, settings)
        if not target_indices:
            break
        improved_this_pass = False
        for codon_index in target_indices:
            start = codon_index * 3
            current_codon = working_seq[start:start + 3]
            amino_acid = CODON_TO_AA.get(current_codon)
            if not amino_acid or amino_acid == '*':
                continue
            best_seq = working_seq
            best_score = current_score
            best_diag = current_diag
            candidate_codons = [
                c for c in _candidate_codons_for_position(amino_acid, current_codon, rankings)
                if c != current_codon
            ]
            for candidate_codon in candidate_codons:


                candidate_seq = working_seq[:start] + candidate_codon + working_seq[start + 3:]
                candidate_score, candidate_diag = _score_candidate_sequence(candidate_seq, original_protein, settings, validation['host'])
                if candidate_score < best_score - 1e-9:
                    best_seq = candidate_seq
                    best_score = candidate_score
                    best_diag = candidate_diag
            if best_seq != working_seq:
                history.append({
                    'pass': pass_index + 1,
                    'codon_index': codon_index,
                    'from_codon': current_codon,
                    'to_codon': best_seq[start:start + 3],
                    'score_before': round(current_score, 6),
                    'score_after': round(best_score, 6),
                })
                working_seq = best_seq
                current_score = best_score
                current_diag = best_diag
                improved_this_pass = True
        if not improved_this_pass:
            break

    # -- CAI-improvement sweep -----------------------------------------------
    # After constraint-repair passes, sweep every codon position once to
    # maximise host adaptation / CAI.  A candidate is accepted only when it
    # (a) preserves the protein and (b) does not introduce any new constraint
    # violation.  The existing scoring function encodes both criteria: any hard
    # violation raises the score by >= 10 000, so we reject any candidate
    # whose score is not strictly below the current sequence score.
    cai_sweep_score, _ = _sequence_issue_score_cached_entry(working_seq, settings, validation['host'])
    n_codons = len(working_seq) // 3
    for codon_index in range(n_codons):
        start = codon_index * 3
        current_codon = working_seq[start:start + 3]
        amino_acid = CODON_TO_AA.get(current_codon)
        if not amino_acid or amino_acid == '*':
            continue
        best_cai_seq = working_seq
        best_cai_score = cai_sweep_score
        candidate_codons = [c for c in rankings.get(amino_acid, []) if c != current_codon]
        for candidate_codon in candidate_codons:
            if candidate_codon == current_codon:
                continue
            candidate_seq = working_seq[:start] + candidate_codon + working_seq[start + 3:]
            candidate_score, _ = _score_candidate_sequence(
                candidate_seq, original_protein, settings, validation['host']
            )
            if candidate_score < best_cai_score - 1e-9:
                best_cai_seq = candidate_seq
                best_cai_score = candidate_score
        if best_cai_seq != working_seq:
            history.append({
                'pass': 'cai_sweep',
                'codon_index': codon_index,
                'from_codon': current_codon,
                'to_codon': best_cai_seq[start:start + 3],
                'score_before': round(cai_sweep_score, 6),
                'score_after': round(best_cai_score, 6),
            })
            working_seq = best_cai_seq
            cai_sweep_score = best_cai_score

    if _translate_cds(working_seq) != original_protein:
        return {
            'success': False,
            'host': validation['host'],
            'input_sequence': original_seq,
            'optimized_sequence': original_seq,
            'protein': validation['protein'],
            'errors': ['Post-optimization protein mismatch detected; returned original sequence safely.'],
            'warnings': validation['warnings'],
            'constraints': settings,
            'before': before,
            'after': before,
            'changed': False,
            'history': history,
            'result_schema_version': 'constraint_aware_cds_optimizer_v1',
        }

    after = _build_diagnostics_summary(working_seq, validation['host'], settings)
    return {
        'success': True,
        'host': validation['host'],
        'input_sequence': original_seq,
        'optimized_sequence': working_seq,
        'protein': validation['protein'],
        'constraints': settings,
        'before': before,
        'after': after,
        'changed': working_seq != original_seq,
        'history': history,
        'errors': [],
        'warnings': validation['warnings'],
        'result_schema_version': 'constraint_aware_cds_optimizer_v1',
    }
