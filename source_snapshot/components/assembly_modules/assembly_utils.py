"""
components/assembly_modules/assembly_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared utility functions for all assembly/cloning modules.
No Streamlit UI calls in this file.
"""
from __future__ import annotations
import io
import re
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── Optional scientific libraries ─────────────────────────────────
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _MPL_OK = True
except ImportError:
    _MPL_OK = False

try:
    from core.primer_utils import calc_tm as _p3_tm, calc_gc as _p3_gc
    _P3_OK = True
except ImportError:
    _P3_OK = False

try:
    from Bio.Seq import Seq
    from Bio.SeqUtils import MeltingTemp as mt
    _BIO_OK = True
except ImportError:
    _BIO_OK = False

# Re-export canonical implementations from utils.sequence_utils
# so callers that import rc/gc/tm/clean_dna from this module keep working.
from utils.sequence_utils import rc, gc, tm, clean_dna, validate_sequence as _base_validate_sequence  # noqa: E402


# ── REBASE restriction enzyme database ───────────────────────────
def _build_rebase() -> dict:
    """Load from Biopython REBASE or fall back to built-in set."""
    try:
        from Bio.Restriction import CommOnly
        db = {}
        for enz in CommOnly:
            try:
                site = str(enz.site)
                ovhg = getattr(enz, 'ovhg', 0)
                db[enz.__name__] = {
                    'site': site,
                    'ovhg': ovhg,
                    'cut_twice': False,
                }
            except Exception:
                continue
        if db:
            return db
    except Exception:
        pass
    # Built-in fallback
    return {
        'EcoRI':   {'site': 'GAATTC',   'ovhg': 4,  'cut_twice': False},
        'BamHI':   {'site': 'GGATCC',   'ovhg': 4,  'cut_twice': False},
        'HindIII': {'site': 'AAGCTT',   'ovhg': 4,  'cut_twice': False},
        'NotI':    {'site': 'GCGGCCGC', 'ovhg': 4,  'cut_twice': False},
        'XhoI':    {'site': 'CTCGAG',   'ovhg': 4,  'cut_twice': False},
        'NcoI':    {'site': 'CCATGG',   'ovhg': 4,  'cut_twice': False},
        'NdeI':    {'site': 'CATATG',   'ovhg': 4,  'cut_twice': False},
        'SalI':    {'site': 'GTCGAC',   'ovhg': 4,  'cut_twice': False},
        'XbaI':    {'site': 'TCTAGA',   'ovhg': 4,  'cut_twice': False},
        'KpnI':    {'site': 'GGTACC',   'ovhg': -4, 'cut_twice': False},
        'SacI':    {'site': 'GAGCTC',   'ovhg': -4, 'cut_twice': False},
        'PstI':    {'site': 'CTGCAG',   'ovhg': -4, 'cut_twice': False},
        'SmaI':    {'site': 'CCCGGG',   'ovhg': 0,  'cut_twice': False},
        'EcoRV':   {'site': 'GATATC',   'ovhg': 0,  'cut_twice': False},
        'NheI':    {'site': 'GCTAGC',   'ovhg': 4,  'cut_twice': False},
        'SpeI':    {'site': 'ACTAGT',   'ovhg': 4,  'cut_twice': False},
        'ClaI':    {'site': 'ATCGAT',   'ovhg': 2,  'cut_twice': False},
        'SphI':    {'site': 'GCATGC',   'ovhg': -4, 'cut_twice': False},
        'ApaI':    {'site': 'GGGCCC',   'ovhg': -4, 'cut_twice': False},
        'MluI':    {'site': 'ACGCGT',   'ovhg': 4,  'cut_twice': False},
    }

REBASE_DB: dict = _build_rebase()


# ── DNA utilities ─────────────────────────────────────────────────
# rc, gc, tm, clean_dna are imported from utils.sequence_utils above.


def validate_sequence(seq: str) -> Tuple[bool, str]:
    """Return (valid, message) for a DNA sequence."""
    valid, message = _base_validate_sequence(seq)
    if not valid:
        if message == "Sequence must not be empty.":
            return False, "Sequence is empty"
        if message.startswith("Invalid characters:"):
            invalid = set(seq.upper()) - set('ATCGN')
            return False, f"Invalid characters: {', '.join(sorted(invalid))}"
        return False, message
    if len(seq) < 20:
        return False, f"Sequence too short ({len(seq)} bp, minimum 20 bp)"
    return True, "Sequence valid"


def sequence_stats(seq: str) -> Dict:
    """Return basic sequence statistics dict."""
    s = seq.upper()
    gc_val = gc(seq)
    return {
        'length':     len(s),
        'gc_content': round(gc_val, 2),
        'at_content': round(100 - gc_val, 2),
        'a_count': s.count('A'),
        't_count': s.count('T'),
        'g_count': s.count('G'),
        'c_count': s.count('C'),
        'n_count': s.count('N'),
        'tm':      round(tm(seq[:500]), 1) if len(seq) >= 20 else 0.0,
    }


def quality_warnings(seq: str) -> List[str]:
    """Return list of quality warning strings for a DNA sequence."""
    warnings = []
    s = seq.upper()
    gc_val = gc(seq)
    if gc_val < 20:
        warnings.append(f"GC content too low ({gc_val:.1f}% < 20%)")
    elif gc_val > 80:
        warnings.append(f"GC content too high ({gc_val:.1f}% > 80%)")
    for base in 'ATCG':
        run = max((len(m.group()) for m in re.finditer(base + '+', s)), default=0)
        if run > 8:
            warnings.append(f"Long homopolymer: {base}x{run} — may affect synthesis")
    n_pct = s.count('N') / len(s) * 100 if s else 0
    if n_pct > 5:
        warnings.append(f"N content too high ({n_pct:.1f}%)")
    return warnings


def scan_restriction_sites(seq: str, enzyme_names: List[str] = None) -> List[Dict]:
    """Scan sequence for restriction sites. Returns list of hit dicts."""
    results = []
    seq_u = seq.upper()
    enzymes = enzyme_names or list(REBASE_DB.keys())
    for ename in enzymes:
        info = REBASE_DB.get(ename)
        if not info:
            continue
        site = info['site']
        try:
            for m in re.finditer(site, seq_u):
                results.append({
                    'enzyme': ename, 'site': site,
                    'position': m.start() + 1, 'strand': '+',
                    'ovhg': info.get('ovhg', 0),
                })
            for m in re.finditer(site, rc(seq_u)):
                results.append({
                    'enzyme': ename, 'site': site,
                    'position': len(seq) - m.end() + 1, 'strand': '-',
                    'ovhg': info.get('ovhg', 0),
                })
        except re.error:
            continue
    results.sort(key=lambda x: x['position'])
    return results


def select_orthogonal_overhangs(n: int) -> List[str]:
    """Return n+1 orthogonal 4-nt overhangs for Golden Gate assembly."""
    pool = [
        'AAAC','AACG','AAGC','AATG','ACAA','ACAC','ACAG','ACAT',
        'ACCA','ACGA','ACTA','AGAC','AGCA','AGGA','AGTA','ATAC',
        'ATCA','ATGA','CAAC','CACA','CAGA','CATA','CCAA','CGAA',
        'CTAA','GAAC','GACA','GAGA','GATA','GCAA','GGAA','GTAA',
        'TAAC','TACA','TAGA','TATA','TCAA','TGAA','TTAC','TTCA',
    ]
    return pool[:max(n + 1, 1)]


def fig_to_buf(fig) -> Optional[io.BytesIO]:
    """Convert matplotlib figure to PNG bytes buffer."""
    if not _MPL_OK:
        return None
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf
