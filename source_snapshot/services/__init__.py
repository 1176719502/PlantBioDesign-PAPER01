"""
services/
~~~~~~~~~
Unified business-logic layer for BioDesign Studio.

All views and components should call these services instead of
importing from core/ or components/design_modules/ directly.
This ensures a single implementation path for every algorithm.

Available services
------------------
sequence_service   -- GC, Tm, ORF, RC, translate, clean, BLAST
primer_service     -- Primer3-based primer design and quality assessment
codon_service      -- codon optimize / analyze / compare
protein_service    -- ProteinAnalysis properties (cached)
crispr_service     -- CRISPR site scan + ML efficiency prediction
"""
