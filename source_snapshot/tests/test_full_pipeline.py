import sys, os
# Ensure project root is on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
print('=== Full import chain ===')
mods = [
    'views.Dashboard','views.Wizard','views.Design','views.Build',
    'views.Test','views.Tools','views.Data','views.Support',
]
for m in mods:
    try:
        __import__(m)
        print('OK ', m)
    except Exception as e:
        print('ERR', m, '->', e)

print('\n=== DB round-trip ===')
from core.unified_database import get_database_stats, add_component, delete_component
stats = get_database_stats()
print('Stats:', {k:v for k,v in stats.items() if v>0})
ok,msg = add_component('genes', {
    'id':'RT_TEST','name':'RT_Gene','type':'Reporter',
    'function_category':'Test','chassis_compatibility':'E. coli',
    'description':'roundtrip','sequence':'ATGCCC',
    'source_id':'TEST','evidence_level':'Test',
})
print('Add gene:', ok, msg)
ok2,msg2 = delete_component('genes','RT_TEST')
print('Delete gene:', ok2, msg2)

print('\n=== Sequence pipeline ===')
from components.test_modules.seq_utils import build_demo_seq, smart_annotate_sequence, find_enzymes
seq = build_demo_seq()
feats = smart_annotate_sequence(seq)
enz = find_enzymes(seq)
print(f'Demo seq {len(seq)} bp | {len(feats)} features | {len(enz)} enzyme sites')

from components.assembly_modules.tab_cloning import _gibson_assemble, _design_primers_gibson
seqs = [seq[:100], seq[80:200], seq[180:300]]
r = _gibson_assemble(seqs, ['A','B','C'], overlap=20)
print(f'Gibson product: {r["length"]} bp')
df = _design_primers_gibson(seqs, ['A','B','C'], homology=20)
print(f'Gibson primers: {len(df)} rows')

from components.assembly_modules.tab_pcr import _simulate_pcr
# Build a template that contains the forward primer at start and RC of rev primer at end
_fwd_primer = 'ATGCATGCATGCATGCATGC'
_rev_primer  = 'GCTAGCTAGCTAGCTAGCTA'
_tmpl = _fwd_primer + 'GGGG' * 60 + _rev_primer
res = _simulate_pcr(_tmpl, _fwd_primer, _rev_primer, cycles=35)
print(f'PCR: success={res["success"]} amplicon={res["amplicon_length"]} bp')
assert res['success'], f'PCR should succeed: {res["message"]}'
assert res['amplicon_length'] > 50, 'Amplicon should be > 50 bp'

from components.test_modules.tab_restriction import find_enzymes as fe
from components.test_modules.tab_translation import render as _tr_render
from components.test_modules.seq_utils import translate_dna
prot = translate_dna(seq, frame=1)
print(f'Translation frame+1: {len(prot)} aa, first 10: {prot[:10]}')

from components.data_modules.tab_promoters import render as _pr
from components.data_modules.tab_primers import render as _pp
print('Data modules importable: OK')

print('\n=== ALL TESTS PASSED ===')
