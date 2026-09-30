# -*- coding: utf-8 -*-
"""
Focused smoke coverage for localized Gibson usability helpers.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from components.assembly_modules import tab_cloning


class TestGibsonUsabilityHelpers:
    def test_fragment_boundary_table_exposes_coordinates_and_edges(self):
        table = tab_cloning._build_gibson_fragment_boundary_table(
            names=['FragA', 'FragB'],
            seqs=['ATGCGTAA', 'CCGGTTAA'],
            overlap=4,
        )

        assert list(table['Fragment']) == ['FragA', 'FragB']
        assert list(table['Start']) == [1, 9]
        assert list(table['End']) == [8, 16]
        assert list(table["5' Boundary"]) == ['ATGC', 'CCGG']
        assert list(table["3' Boundary"]) == ['GTAA', 'TTAA']

    def test_primer_review_table_surfaces_fragment_warnings(self):
        plan = {
            'primers': [
                {
                    'Fragment Name': 'FragA',
                    'Fwd Arm (bp)': 20,
                    'Rev Arm (bp)': 18,
                    'Fwd Anneal Tm (°C)': 60.5,
                    'Rev Anneal Tm (°C)': 61.2,
                    'Warnings': ['High cross-dimer risk between primers (8 bp complementarity).'],
                },
                {
                    'Fragment Name': 'FragB',
                    'Fwd Arm (bp)': 20,
                    'Rev Arm (bp)': 0,
                    'Fwd Anneal Tm (°C)': 59.8,
                    'Rev Anneal Tm (°C)': 60.1,
                    'Warnings': [],
                },
            ]
        }

        table = tab_cloning._build_gibson_primer_review_table(plan, overlap=20)

        assert list(table['Fragment']) == ['FragA', 'FragB']
        assert table.loc[0, 'Warnings'].startswith('High cross-dimer risk')
        assert table.loc[1, 'Warnings'] == 'None'
