"""
components/design_modules
~~~~~~~~~~~~~~~~~~~~~~~~~
Sub-modules for views/Design.py.

Data / logic (no Streamlit):
    static_data      BIO_DB, STYLE, PROMOTERS, TERMINATORS
    db_utils         init_db, save_sequence, get_all_sequences, get_sequence_by_name
    bio_utils        sequence math helpers
    expert_analysis  compute_real_metrics, run_expert_analysis
    crispr_engine    scan_crispr_sites
    assembly         simulate_gibson, design_gibson_primers
    phylogenetics    run_muscle, build_nj_tree
"""
