# [DORMANT - V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
static_data.py  —  Pure-data constants for the Design module.
No Streamlit imports. No session_state access.

Exports: BIO_DB, DB_NAME, STYLE, PROMOTERS, TERMINATORS, FEATURE_LIBRARY
"""

# ── Biological database ───────────────────────────────────────────
BIO_DB = {
    "taxonomy": {
        "Plant": {
            "Model Plant (Model)": [
                "Arabidopsis thaliana Col-0",
                "Nicotiana benthamiana — preferred for transient expression",
            ],
            "Cereal Crop (Cereal)": [
                "Rice (O. sativa) Japonica — Asian staple crop",
                "Maize (Zea mays) B73 — monocot model",
                "Wheat (T. aestivum) Chinese Spring",
                "Barley (H. vulgare) Golden Promise",
            ],
            "Cash Crop": [
                "Soybean (G. max) Williams 82",
                "Cotton (G. hirsutum) TM-1",
                "Rapeseed (B. napus) Westar",
                "Tomato (S. lycopersicum) M82",
            ],
            "General Dicots": [
                "Potato (S. tuberosum)",
                "Sugar beet (B. vulgaris)",
                "Alfalfa (M. sativa)",
            ],
        },
        "Bacteria": {
            "Cloning Host (Cloning)": [
                "E. coli DH5α — high-efficiency cloning",
                "E. coli TOP10 — large plasmid stability",
                "E. coli DH10B — BAC cloning",
            ],
            "Expression Host (Expression)": [
                "E. coli BL21(DE3) — T7 expression system",
                "E. coli BL21(DE3) pLysS — stringent regulation",
                "E. coli Rosetta(DE3) — rare codon compensation",
                "E. coli SHuffle T7 — disulfide bond proteins",
            ],
            "Plant Transformation (Agrobacterium)": [
                "A. tumefaciens GV3101 — preferred for leaf disk method",
                "A. tumefaciens EHA105 — monocot/callus transformation",
                "A. tumefaciens LBA4404 — commercial standard strain",
                "A. rhizogenes K599 — hairy root induction",
            ],
            "Industrial Fermentation (Industrial)": [
                "B. subtilis 168 — Bacillus subtilis",
                "Corynebacterium glutamicum — amino acid fermentation",
                "Pseudomonas putida KT2440 — aromatic compound degradation",
            ],
        },
    },
    "vectors": {
        "Plant": [
            {"Name": "pCAMBIA1300 (dicot/monocot universal)",   "Size": 8958},
            {"Name": "pCAMBIA2300 (with NptII selection marker)", "Size": 9236},
            {"Name": "pBI121 (CaMV35S-GUS)",                     "Size": 14758},
            {"Name": "pK7WG2 (Gateway binary vector)",           "Size": 12000},
            {"Name": "pEarleyGate (Gateway + enhanced)",         "Size": 10500},
        ],
        "Bacteria": [
            {"Name": "pET-28a(+) (His-tag, T7 promoter)",        "Size": 5369},
            {"Name": "pET-21a(+) (C-terminal His-tag)",          "Size": 5443},
            {"Name": "pGEX-4T-1 (GST fusion)",                   "Size": 4969},
            {"Name": "pUC19 (high-copy cloning)",                "Size": 2686},
            {"Name": "pACYCDuet-1 (dual gene co-expression)",    "Size": 4520},
        ],
    },
    "parts": [
        {"Name": "mGFP5 (Plant Opt)",
         "Seq": "ATGAGTAAAGGAGAAGAACTTTTCACTGGAGTTGTCCCAATTCTTGTTGAATTAGATGGTGATGTTAATGGGCACAAATTTTCTGTCAGTGGAGAGGGTGAAGGTGATGCAACATACGGAAAACTTACCCTTAAATTTATTTGCACTACTGGAAAACTACCTGTTCCATGGCCAACACTTGTCACTACTTTCTCTTATGGTGTTCAATGCTTTTCCCGTTATCCGGATCATATGAAACGGCATGACTTTTTCAAGAGTGCCATGCCCGAAGGTTATGTACAGGAACGCACTATATCTTTCAAAGATGACGGGAACTACAAGACGCGTGCTGAAGTCAAGTTTGAAGGTGATACCCTTGTTAATCGTATCGAGTTAAAAGGTATTGATTTTAAAGAAGATGGAAACATTCTCGGACACAAACTCGAGTACAACTATAACTCACACAATGTATACATACGGCAGACAAACAAAAGAATGGAATCAAAGCTAACTTCAAAATTCGCCACAACATTGAAGATGGATCCGTTCAACTAGCAGACCATTATCAACAAAATACTCCAATTGGCGATGGCCCTGTCCTTTTACCAGACAACCATTACCTGTCGACACAATCTGCCCTTTCGAAAGATCCCAACGAAAAGAGAGACCACATGGTCCTTCTTGAGTTTGTAACAGCTGCTGGGATTACACATGGCATGGATGAGCTCTACAAATAA",
         "PDB": "1EMA"},
        {"Name": "Cas9 (SpCas9)",
         "Seq": "ATGGACAAGAAGTACAGCATCGGCCTGGACATCGGCACCAACTCTGTGGGCTGGGCCGTGATCACCGACGAGTACAAGGTGCCCAGCAAGAAGTTCAAGGTGCTGGGCAACACCGACCGGCACAGCATCAAGAAGAACCTGATCGGAGCCCTGCTGTTCGACAGCGGCGAAACAGCCGAGGCCACCCGGCTGAAGCTGATCAAAGAGACACTGCCCCTGAAGAAGTACCCTTCCGAGGACGCCATCCTGCAGCTGAAAGAGATCTTCAGCAAGGACGACCTGCCCAAGAACATCAACCTGATCCTGCTGCGGGAGGAGTTCGACGAGTTCGGCTCCCCTATCGACAGCCAGCTGATCAAGCGGAAGAGCTACGAGCAGGCCAACAAGGAGAAGCTGGACGCCTGGATCGAGAGCAACAAGCACTTCCTGGAGAAGCACCCCATCGACCAGTTCAAGAACCTGCACGAGATCATCAAGAAGTTCGACCGGCTGCTGCCCAACAGCTTCATCGAGCGGTTCAAGGGCCTGGAGGACGCCTTCAAGAAGCTGAACGAGCAGTTCCTGGACGAGCAGATCAACCTGATCAAAGAGCTGGACAAGTTCGACGAGAAGCTGCAGCAGATCAACATCGAGCTGGACAAGAAGCAGTGGCCCTTCGAGCAGAAGTTCAACCGGCTGCACGACATCTTCAAGGAGTACAAGAAGTTCCCCATCAAGGAGACCCCCAGCAACTTCGAGAAGATCGTGCAGACCTACAACAAGTACCTGGACGCCATCAAGGACCGGAACATCCTGGACATCTTCGACCGGTTCATGCAGCTGCCCGACAAGTTCATCAAGTACTTCAAGCGGTTCAAGCGGCAGAAGGACAAGAAGGCCGCCAAGGAGCTGAGCGAGAGCCAGAAGAAGATCCTGATCTTCCTGAAGATCATCGACGAGCAGCTGAAGGAGTTCCTGGCCAAGTTCGACAAGGAGATGGTGCACATCTACCACGAGAAGGCCAACAAGCCCATCGAGCTGATCAAGAAGATCGAGCGGAAGGACTTCGAGTTCGACAAGCAGTTCTTCGAGAAGATCCAGGAGTACAAGGAGATCTTCAAGAAGCACGACTTCCCCAAGAAGCCCAAGAAGGCCATCTGGAACATCTTCAAGCAGTTCTTCGAGGACTTCAAGAAGGACAAGGTGCTGGCCAGCCTGATCAAGAACAAGCCCTTCAAGCAGCTGGAGTTCATCAAGAAGAAGTACGACATCGCCAAGAAGGCCATCAAGGAGCTGAGCGAGAACAAGAAGGCCATCCTGAAGAACATCGACTTCTTCAAGATCATGAAGTACGAGTTCATCGACAAGGTGTTCAGCAAGTTCGAGAAGAAGATCAACGAGCAGCTGGCCGAGTTCAAGAAGATGCTGGACAAGCAGAAGGAGTTCCTGAAGAAGCAGAAGGAGCTGATCGACAAGTTCAAGAAGCTGTTCGACGAGTTCAAGAAGTTCATCGAGAAGATCAAGAAGGAGATCGAGCGGTTCAAGGAGTTCCTGAGCAAGTTCAAGAAGGAGTTCGACAAGATCCTGAAGAAGATCGAGCGGTTCAAGGAGTTCCTGAACAAGTTCAAGCAGTTCCTGAAGAAGTTCGACAAGATCAAGAAGGAGATCGAGCGGTTCAAGGAGTTCCTGAAGCAGTTCAAGAAGGAGTTCGACAAGATCAAGAAGGAGAAGTAA",
         "PDB": "4CMP"},
        {"Name": "RFP (DsRed)",
         "Seq": "ATGGCCTCCTCCGAGGACGTCATCAAGGAGTTCATGCGCTTCAAGGTGCGCATGGAGGGCTCCGTGAACGGCCACGAGTTCGAGATCGAGGGCGAGGGCGAGGGCCGCCCCTACGAGGGCACCCAGACCGCCAAGCTGAAGGTGACCAAGGGCGGCCCCCTGCCCTTCGCCTGGGACATCCTGTCCCCCCAGTTCATGTACGGCTCCAAGGCCTACGTGAAGCACCCCGCCGACATCCCCGACTACAAGAAGCTGTCCTTCCCCGAGGGCTTCAAGTGGGAGCGCGTGATGAACTTCGAGGACGGCGGCGTGGTGACCGTGACCCAGGACTCCTCCCTGCAGGACGGCGAGTTCATCTACAAGGTGAAGCTGCGCGGCACCAACTTCCCCTCCGACGGCCCCGTAATGCAGAAGAAGACCATGGGCTGGGAGGCCTCCTCCGAGCGGATGTACCCCGAGGACGGCGCCCTGAAGGGCGAGATCAAGATGAGGCTGAAGCTGAAGGACGGCGGCCACTACGACGCTGAGGTCAAGACCACCTACAAGGCCAAGAAGCCCGTGCAGCTGCCCGGCGCCTACAACGTCAACATCAAGTTGGACATCACCTCCCACAACGAGGACTACACCATCGTGGAACAGTACGAGCGCGCCGAGGGCCGCCACTCCACCGGCGGCATGGACGAGCTGTACAAGTAA",
         "PDB": "1G7K"},
    ],
}

import os as _os
# Unified database path — consistent with core/unified_database.py
DB_NAME = _os.path.join("data", "biodesign_unified.db")
# ── CSS Style ─────────────────────────────────────────────────────
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
:root {
    --bg:#f5f6fa; --white:#ffffff; --border:#e5e7eb; --border2:#d1d5db;
    --blue:#2563eb; --blue-lt:#eff6ff; --blue-md:#bfdbfe;
    --green:#059669; --red:#dc2626; --orange:#d97706;
    --text:#111827; --text2:#374151; --muted:#6b7280;
    --r:8px; --font:'Inter',-apple-system,sans-serif;
}
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="block-container"]{
    background:var(--bg)!important; color:var(--text)!important; font-family:var(--font)!important;
}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],footer{display:none!important}
[data-testid="stSidebar"]{font-family:var(--font)!important}
[data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;gap:0!important;padding:0!important}
[data-baseweb="tab"]{background:transparent!important;border:none!important;border-bottom:2px solid transparent!important;
    border-radius:0!important;font-size:.85rem!important;font-weight:500!important;color:var(--muted)!important;padding:8px 18px!important}
[aria-selected="true"][data-baseweb="tab"]{color:var(--blue)!important;border-bottom-color:var(--blue)!important}
[data-testid="stTabPanel"]{padding-top:1.2rem!important;background:transparent!important}
[data-testid="stMain"] [data-testid="stTextInput"] input,
[data-testid="stMain"] [data-testid="stTextArea"] textarea,
[data-testid="stMain"] [data-testid="stNumberInput"] input{
    background:var(--white)!important;border:1px solid var(--border2)!important;
    border-radius:var(--r)!important;color:var(--text)!important;font-size:.85rem!important}
[data-testid="stMain"] [data-testid="stTextInput"] input:focus,
[data-testid="stMain"] [data-testid="stTextArea"] textarea:focus{
    border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(37,99,235,.1)!important}
[data-testid="stMain"] [data-testid="stButton"]>button{
    background:var(--blue)!important;border:none!important;color:#fff!important;
    border-radius:var(--r)!important;font-size:.83rem!important;font-weight:500!important;
    padding:7px 18px!important;transition:background .15s!important;width:100%!important}
[data-testid="stMain"] [data-testid="stButton"]>button:hover{background:#1d4ed8!important}
[data-testid="stMain"] [data-testid="stSelectbox"]>div>div{
    background:var(--white)!important;border:1px solid var(--border2)!important;
    border-radius:var(--r)!important;font-size:.85rem!important}
[data-testid="stMain"] [data-testid="stExpander"]{
    background:var(--white)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important}
[data-testid="stMain"] [data-testid="stAlert"]{border-radius:var(--r)!important;font-size:.82rem!important}
hr{border:none!important;border-top:1px solid var(--border)!important;margin:1rem 0!important}
.sec-label{display:block;font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
.info-box{background:var(--blue-lt);border:1px solid var(--blue-md);border-radius:var(--r);padding:11px 16px;margin:8px 0;font-size:.83rem;line-height:1.7;color:var(--text2)}
.info-box b{color:var(--blue)}
.warn-box{background:#fef2f2;border:1px solid #fecaca;border-radius:var(--r);padding:11px 16px;margin:8px 0;font-size:.83rem;line-height:1.7;color:var(--text2)}
.metric-grid{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.metric-item{background:var(--white);border:1px solid var(--border);border-radius:6px;padding:10px 16px;min-width:110px}
.metric-item .m-lbl{font-size:.68rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;display:block}
.metric-item .m-val{font-size:1rem;color:var(--blue);font-weight:700;display:block;margin-top:2px}
.seq-box{background:var(--white);border:1px solid var(--border);border-radius:var(--r);padding:10px 14px;
    font-family:monospace;font-size:.9rem;color:var(--text2);word-break:break-all;max-height:120px;overflow-y:auto;line-height:1.6}
/* Streamlit native elements: keep default font size, only adjust font family */
</style>
"""
# ── Expression cassette element sequences ─────────────────────────
PROMOTERS = {
    "CaMV 35S (constitutive)": (
        "AAGCTTATCGATACCGTCGACCTCGAGGGGGGGCCCGGTACCCAATTCGCCCTATAGT"
        "GAGTCGTATTACAATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCTG"
        "GCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAG"
        "CGAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGG"
        "CGCCTGATGCGGTATTTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATATGGT"
        "GCACTCTCAGTACAATCTGCTCTGATGCCGCATAGTTAAGCCAGCCCCGACACCCGCC"
        "AACACCCGCTGACGCGCCCTGACGGGCTTGTCTGCTCCCGGCATCCGCTTACAGACAA"
        "GCTGTGACCGTCTCCGGGAGCTGCATGTGTCAGAGGTTTTCACCGTCATCACCGAAAC"
        "GCGCGA"
    ),
    "ZmUbi (monocot strong promoter)": (
        "GCTAGCGGATCCGCGGCCGCTTCTAGAGCGGCCGCCACCGCGGTGGAGCTCCAGCTTTT"
        "GTTCCCTTTAGTGAGGGTTAATTGCGCGCTTGGCGTAATCATGGTCATAGCTGTTTCC"
        "TGTGTGAAATTGTTATCCGCTCACAATTCCACACAACATACGAGCCGGAAGCATAAAGT"
        "GTAAAGCCTGGGGTGCCTAATGAGTGAGCTAACTCACATTAATTGCGTTGCGCTCACT"
        "GCCCGCTTTCCAGTCGGGAAACCTGTCGTGCCAGC"
    ),
    "OsActin (rice-specific)": (
        "TCCCTCGAGGTCGACGGTATCGATAAGCTTGATATCGAATTCCTGCAGCCCGGGGGAT"
        "CCACTAGTTCTAGAGCGGCCGCCACCGCGGTGGAGCTCCAGCTTTTGTTCCCTTTAGTG"
        "AGGGTTAATTGCGCGCTTGGCGTAATCATGGTCATAGCTGTTTCCTGTGTGAAATTGT"
        "TATCCGCTCACAATTCCACACAACATACGAGCCGGAAGCATAAAGTGTAAAGCCTGGGG"
        "TGCCTAATGAGTGAGCTAACTCACATTAATTGCGTTGCGCTCACTGCCCGCTTTCCAG"
        "TCGGGAAACCTGTCGTGCCAGC"
    ),
    "Tissue-specific promoter": (
        "GCTAGCGGATCCGCGGCCGCTTCTAGAGCGGCCGCCACCGCGGTGGAGCTCCAGCTTTT"
        "GTTCCCTTTAGTGAGGGTTAATTGCGCGCTTGGCGTAATCATGGTCATAGCTGTTTCC"
        "TGTGTGAAATTGTTATCCGCTCACAATTCCACACAACATACGAGCCGGAAGCATAAAGT"
        "GTAAAGCCTGGGGTGCCTAATGAGTGAGCTAACTCACATTAATTGCGTTGCGCTCACT"
        "GCCCGCTTTCCAGTCGGGAAACCTGTCGTGCCAGC"
    ),
}

TERMINATORS = {
    "NOS (universal)": (
        "GAATCCTGTTGCCGGTCTTGCGATGATTATCATATAATTTCTGTTGAATTACGTTAAGC"
        "ATGTAATAATTAACATGTAATGCATGACGTTATTTATGAGATGGGTTTTTATGATTAGA"
        "GTCCCGCAATTATACATTTAATACGCGATAGAAAACAAAATATAGCGCGCAAACTAGGAT"
        "AAATTATCGCGCGCGGTGTCATCTATGTTACTAGATC"
    ),
    "CaMV 35S polyA": (
        "AACTAGTGGATCCCCCGGGCTGCAGGAATTCGATATCAAGCTTATCGATACCGTCGACC"
        "TCGAGGGGGGGCCCGGTACCCAATTCGCCCTATAGTGAGTCGTATTACAATTCACTGGC"
        "CGTCGTTTTACAACGTCGTGACTGGGAAAACCCTGGCGTTACCCAACTTAATCGCCTTG"
        "CAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGCGAAGAGGCCCGCACCGATCGCCCT"
        "TCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGCCTGATGCGGTATTTTCTCCTTAC"
        "GCATCTGTGCGGTATTTCACACCGCATATGGTGCACTCTCAGTACAATCTGCTCTGATG"
        "CCGCATAGTTAAGCCAGCCCCGACACCCGCCAACACCCGCTGACGCGCCCTGACGGGCT"
        "TGTCTGCTCCCGGCATCCGCTTACAGACAAGCTGTGACCGTCTCCGGGAGCTGCATGTG"
        "TCAGAGGTTTTCACCGTCATCACCGAAACGCGCGA"
    ),
    "T7 (prokaryotic)": "CTAGCATAACCCCTTGGGGCCTCTAAACGGGTCTTGAGGGGTTTTTTGCTGAAAGGAGGAACTATATCCGGAT",
}
# ── Feature library for sequence annotation ───────────────────────
FEATURE_LIBRARY = {
    "Promoters": {
        "CaMV 35S": "CCGCACGTCTCCCCC",
        "T7": "TAATACGACTCACTATA",
        "T3": "AATTAACCCTCACTAAA",
        "SP6": "ATTTAGGTGACACTATAG",
        "lac": "AATTGTGAGCGGATAACA",
        "tac": "TTGACAATTAATCATCGGC",
    },
    "Terminators": {
        "NOS term": "GATCTAGTAACATAGATGACAC",
        "T7 term": "GCTAGTTATTGCTCAGCGG",
        "rrnB T1": "TGCCTGGCGGCAGTAGCGCG",
    },
    "RBS/Kozaks": {
        "Kozak consensus": "GCCACCATG",
        "Shine-Dalgarno": "AGGAGG",
        "Strong SD": "AAGGAGG",
    },
    "Tags": {
        "6xHis C-term": "CATCACCATCACCATCAC",
        "FLAG tag": "GACTACAAAGACCATGACGGTGATTATAAAGATCATGACATCGATTACAAGGATGACGATGACAAG",
        "HA tag": "TACCCATACGATGTTCCAGATTACGCT",
        "Myc tag": "GAACAAAAACTCATCTCAGAAGAGGATCTG",
        "GST": "ATGTCCCCTATACTAGGT",
        "MBP signal": "ATGAAAATAAAAACAGGTGCACGC",
        "GFP (short)": "ATGAGTAAAGGAGAAGAAC",
    },
    "Restriction Sites": {
        "EcoRI": "GAATTC",
        "BamHI": "GGATCC",
        "HindIII": "AAGCTT",
        "NcoI": "CCATGG",
        "NdeI": "CATATG",
        "XhoI": "CTCGAG",
        "SalI": "GTCGAC",
        "XbaI": "TCTAGA",
        "SpeI": "ACTAGT",
        "NotI": "GCGGCCGC",
        "KpnI": "GGTACC",
        "SacI": "GAGCTC",
        "ClaI": "ATCGAT",
        "SmaI": "CCCGGG",
        "PstI": "CTGCAG",
    },
}
