"""
components/test_modules/seq_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Core sequence utility functions — no Streamlit, no side-effects.
"""
from __future__ import annotations
import re
import random

from utils.sequence_utils import rc


def reverse_complement(seq: str) -> str:
    return rc(seq)


def translate_dna(seq: str, frame: int = 1) -> str:
    CODON_TABLE = {
        'ATA':'I','ATC':'I','ATT':'I','ATG':'M','ACA':'T','ACC':'T','ACG':'T','ACT':'T',
        'AAC':'N','AAT':'N','AAA':'K','AAG':'K','AGC':'S','AGT':'S','AGA':'R','AGG':'R',
        'CTA':'L','CTC':'L','CTG':'L','CTT':'L','CCA':'P','CCC':'P','CCG':'P','CCT':'P',
        'CAC':'H','CAT':'H','CAA':'Q','CAG':'Q','CGA':'R','CGC':'R','CGG':'R','CGT':'R',
        'GTA':'V','GTC':'V','GTG':'V','GTT':'V','GCA':'A','GCC':'A','GCG':'A','GCT':'A',
        'GAC':'D','GAT':'D','GAA':'E','GAG':'E','GGA':'G','GGC':'G','GGG':'G','GGT':'G',
        'TCA':'S','TCC':'S','TCG':'S','TCT':'S','TTC':'F','TTT':'F','TTA':'L','TTG':'L',
        'TAC':'Y','TAT':'Y','TAA':'*','TAG':'*','TGC':'C','TGT':'C','TGA':'*','TGG':'W',
    }
    seq_t  = reverse_complement(seq) if frame < 0 else seq
    offset = abs(frame) - 1
    clean  = ''.join(c for c in seq_t.upper() if c in 'ATCG')
    return ''.join(CODON_TABLE.get(clean[i:i+3], '?')
                   for i in range(offset, len(clean) - 2, 3))


def find_enzymes(seq: str) -> list:
    ENZYMES = {
        'EcoRI':('GAATTC','Sticky'),'BamHI':('GGATCC','Sticky'),
        'HindIII':('AAGCTT','Sticky'),'NotI':('GCGGCCGC','Sticky'),
        'XhoI':('CTCGAG','Sticky'),'NcoI':('CCATGG','Sticky'),
        'NdeI':('CATATG','Sticky'),'SalI':('GTCGAC','Sticky'),
        'XbaI':('TCTAGA','Sticky'),'KpnI':('GGTACC','Sticky'),
        'SacI':('GAGCTC','Sticky'),'PstI':('CTGCAG','Sticky'),
        'SmaI':('CCCGGG','Blunt'),'EcoRV':('GATATC','Blunt'),
        'NheI':('GCTAGC','Sticky'),'SpeI':('ACTAGT','Sticky'),
        'ClaI':('ATCGAT','Sticky'),'SphI':('GCATGC','Sticky'),
        'ApaI':('GGGCCC','Sticky'),'MluI':('ACGCGT','Sticky'),
        'BglII':('AGATCT','Sticky'),'StuI':('AGGCCT','Blunt'),
    }
    results = []
    s = seq.upper()
    for name, (site, etype) in ENZYMES.items():
        for m in re.finditer(site, s):
            results.append({'Enzyme': name, 'Site': site,
                            'Type': etype, 'Position': m.start() + 1})
    return sorted(results, key=lambda x: x['Position'])


def smart_annotate_sequence(seq: str) -> list:
    MOTIFS = [
        ('CaMV 35S',       'CCACTATCCTTCGCAAGACCC',  'Promoter'),
        ('T7 Promoter',    'TAATACGACTCACTATA',       'Promoter'),
        ('SP6 Promoter',   'ATTTAGGTGACACTATAG',      'Promoter'),
        ('lac Operator',   'AATTGTGAGCGGATAACA',      'Operator'),
        ('T7 Terminator',  'GCTAGCTTGGCTGCAGGTCGAC', 'Terminator'),
        ('NOS Terminator', 'GCATGCATGGATCCTCTAGAG',  'Terminator'),
        ('6xHis Tag',      'CATCACCATCACCATCAC',      'Tag'),
        ('FLAG Tag',       'GACTACAAAGACCATGACGG',    'Tag'),
        ('Kozak',          'GCCACCATG',               'RBS'),
        ('RBS (SD)',        'AGGAGGT',                 'RBS'),
        ('AmpR (partial)', 'ATGAGTATTCAACATTTCCGT',  'Resistance'),
        ('KanR (partial)', 'ATGAGCCATATTCAACGGGAA',  'Resistance'),
        ('ColE1 ori',      'CGCGCAACGCAATTAATGTGAG', 'Origin'),
        ('M13 ori',        'GTAAAACGACGGCCAGT',       'Origin'),
        ('GFP (partial)',  'ATGGTGAGCAAGGGCGAGGAG',  'CDS'),
        ('RB Border',      'TGACAGGATATATTGGCGGGT',  'Border'),
        ('LB Border',      'TGGCTTAACTATGCGGCATCAG', 'Border'),
    ]
    features = []
    s = seq.upper()
    for name, pattern, ftype in MOTIFS:
        for m in re.finditer(re.escape(pattern), s):
            features.append({'Name': name, 'Type': ftype,
                             'Start': m.start()+1, 'End': m.end()})
    for m in re.finditer(r'ATG(?:[ATCG]{3})*?(?:TAA|TAG|TGA)', s):
        if len(m.group()) >= 150:
            features.append({'Name': f'ORF@{m.start()+1}',
                             'Type': 'CDS',
                             'Start': m.start()+1, 'End': m.end()})
    return sorted(features, key=lambda x: x['Start'])


def build_demo_seq() -> str:
    random.seed(42)
    return (
        'CCACTATCCTTCGCAAGACCC'
        + 'AAAAACCCGGG'
        + 'GCCACCATG'
        + 'ATGGTGAGCAAGGGCGAGGAG'
        + ''.join(random.choices('ATCG', k=300))
        + 'GCTAGCTTGGCTGCAGGTCGAC'
        + ''.join(random.choices('ATCG', k=80))
        + 'GAATTC'
        + ''.join(random.choices('ATCG', k=50))
        + 'CTGCAG'
    )
