import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from components.assembly_modules.tab_pcr import _simulate_pcr

# Proper template: fwd primer at start, rev primer RC at end
tmpl = 'AAAA' * 5 + 'ATGCATGCATGCATGCATGC' + 'GCGC' * 50 + 'GCATGCATGCATGCATGCAT' + 'TTTT' * 5
fwd  = 'ATGCATGCATGCATGCATGC'
rev  = 'ATGCATGCATGCATGCATGC'  # same seq — rev complement on template
res  = _simulate_pcr(tmpl, fwd, rev, cycles=35)
print('success:',  res['success'])
print('amplicon:', res['amplicon_length'], 'bp')
print('tm_f:',    res['tm_f'], 'tm_r:', res['tm_r'])
print('fwd_match:', res['fwd_match'], 'rev_match:', res['rev_match'])
