"""Pinned R1/R2 path audit, independent of worktree cleanliness.

This is scope authorization with named regression obligations, not a claim
that a historical full-suite run covered subsequently changed product code.
See docs/qa/V1_COMPONENT_LIBRARY_V2_R2_REVIEW_BLOCKER_CLOSURE_20260928.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FORMAL_BASELINE = '0a608bd76f6341c42c58bd3fc4cb8be61d1eb34c'
R1_CANDIDATE = 'ae7fe1325920d2aec94a11d14b25849f8c86a864'
OUTPUT_TEST = 'tests/test_component_library_v2_output_provenance.py'
ADOPTION_TEST = 'tests/test_component_library_v2_product_adoption_r1.py'
ROUTING_TEST = 'tests/test_component_library_v2_step3_routability.py'
RANGE_TEST = 'tests/test_component_library_v2_committed_scope.py'
QA_RECORD = 'docs/qa/V1_COMPONENT_LIBRARY_V2_R2_REVIEW_BLOCKER_CLOSURE_20260928.md'


@dataclass(frozen=True)
class ScopeRule:
    reason: str
    regressions: tuple[str, ...]


# Exact paths only. Do not infer authorization from the candidate diff, task
# prose, file extensions, directory prefixes, or broad historical allowlists.
R1_RULES = {
    'CURRENT_TASK.md': ScopeRule('R1 task and acceptance record', (RANGE_TEST,)),
    'app.py': ScopeRule('R1 library, Step 3 and Step 6 presentation/save binding', (OUTPUT_TEST, ADOPTION_TEST, ROUTING_TEST)),
    'components/export_manager.py': ScopeRule('R1 exact-value GenBank qualifier serialization', (OUTPUT_TEST,)),
    'docs/qa/V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_20260927.md': ScopeRule('R1 inventory/adoption evidence', (ADOPTION_TEST,)),
    'docs/qa/V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_MAPPING_20260927.json': ScopeRule('R1 171-identity mapping evidence', (ADOPTION_TEST,)),
    'docs/qa/V1_COMPONENT_LIBRARY_V2_STEP3_ROUTABILITY_20260928.json': ScopeRule('R1 routing evidence', (ROUTING_TEST,)),
    'docs/qa/V1_COMPONENT_LIBRARY_V2_STEP3_ROUTABILITY_20260928.md': ScopeRule('R1 routing evidence', (ROUTING_TEST,)),
    'locales/en.py': ScopeRule('R1 English component copy', (OUTPUT_TEST, ADOPTION_TEST, ROUTING_TEST)),
    'locales/zh_cn.py': ScopeRule('R1 Chinese component copy', (OUTPUT_TEST, ADOPTION_TEST, ROUTING_TEST)),
    'scripts/generate_component_library_v2_product_adoption_r1.py': ScopeRule('R1 adoption evidence generator', (ADOPTION_TEST,)),
    'scripts/generate_component_library_v2_step3_routability.py': ScopeRule('R1 routing evidence generator', (ROUTING_TEST,)),
    'services/agent_product_adapter.py': ScopeRule('R1 agent routing without additional admissions', (ROUTING_TEST,)),
    'services/component_library_v2_adoption.py': ScopeRule('R1 assisted confirmation and inventory', (ADOPTION_TEST, ROUTING_TEST)),
    'services/component_output_provenance.py': ScopeRule('R1 persisted assisted provenance projection', (OUTPUT_TEST,)),
    'services/formal_results_report_contract.py': ScopeRule('R1 canonical-bound report provenance', (OUTPUT_TEST, 'tests/test_formal_results_report_contract.py')),
    'services/formal_single_gene_final_review.py': ScopeRule('R1 shared final-report provenance rendering', (OUTPUT_TEST, 'tests/test_formal_single_gene_final_review.py')),
    'services/mvp_multi_tu_persistence.py': ScopeRule('R1 persisted assisted project binding', (ADOPTION_TEST, OUTPUT_TEST)),
    'services/mvp_multi_tu_runtime.py': ScopeRule('R1 assisted output projection, unchanged canonical DNA', (ADOPTION_TEST, OUTPUT_TEST)),
    'services/plant_component_workflow_registry.py': ScopeRule('R1 USER_PROVIDED traceability qualifiers', (ADOPTION_TEST, OUTPUT_TEST)),
    'services/registry_catalog_ui.py': ScopeRule('R1 catalog and assisted component construction', (ADOPTION_TEST, ROUTING_TEST)),
    OUTPUT_TEST: ScopeRule('R1 output/save/reopen/exact-value regressions', (OUTPUT_TEST,)),
    ADOPTION_TEST: ScopeRule('R1 inventory/admission regressions', (ADOPTION_TEST,)),
    ROUTING_TEST: ScopeRule('R1 Single-Gene/Multi-TU/Pathway routing regressions', (ROUTING_TEST,)),
    'tests/test_formal_hsa_ui_regression.py': ScopeRule('R1 formal UI compatibility', ('tests/test_formal_hsa_ui_regression.py',)),
    'tests/test_page_consistency_contract.py': ScopeRule('R1 page contract compatibility', ('tests/test_page_consistency_contract.py',)),
    'tests/test_v1_reviewed_component_catalog_integration.py': ScopeRule('R1 reviewed catalog compatibility', ('tests/test_v1_reviewed_component_catalog_integration.py',)),
    'tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py': ScopeRule('R1 inventory guard integration', (RANGE_TEST,)),
    'tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py': ScopeRule('R1 regression scope integration', (RANGE_TEST,)),
}
R2_NEW_RULES = {
    'tests/component_library_v2_scope.py': ScopeRule('R2 pinned range audit and exact coverage rules', (RANGE_TEST,)),
    RANGE_TEST: ScopeRule('R2 clean committed and negative audit tests', (RANGE_TEST,)),
    QA_RECORD: ScopeRule('R2 blocker closure evidence and complete path manifest', (RANGE_TEST,)),
}
RULES = R1_RULES | R2_NEW_RULES
R2_EDIT_PATHS = frozenset({
    'CURRENT_TASK.md', 'app.py', OUTPUT_TEST,
    'docs/qa/V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_20260927.md',
    'scripts/generate_component_library_v2_product_adoption_r1.py',
    'tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py',
    'tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py',
    *R2_NEW_RULES,
})


class ScopeViolation(AssertionError):
    pass


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True).stdout


def _paths(root: Path, *args: str) -> set[str]:
    return {part.decode('utf-8') for part in _git(root, *args).split(b'\0') if part}


def _committed_paths(root: Path, base: str, head: str) -> set[str]:
    # --no-renames retains BOTH endpoints of renames; -z preserves spaces.
    return _paths(root, 'diff', '--name-only', '--no-renames', '-z', base, head, '--')


def _history_paths(root: Path, base: str, head: str) -> set[str]:
    # Also retain transient/reverted paths and merge-parent differences.
    commits = _git(root, 'rev-list', f'{base}..{head}').decode().splitlines()
    paths: set[str] = set()
    for commit in commits:
        paths |= _paths(root, 'diff-tree', '--root', '-m', '--no-commit-id',
                        '--name-only', '--no-renames', '-r', '-z', commit, '--')
    return paths


def _live_paths(root: Path) -> dict[str, set[str]]:
    return {
        'staged': _paths(root, 'diff', '--cached', '--name-only', '--no-renames', '-z', '--'),
        'unstaged': _paths(root, 'diff', '--name-only', '--no-renames', '-z', '--'),
        'untracked': _paths(root, 'ls-files', '--others', '--exclude-standard', '-z'),
    }


def _require_allowed(paths: set[str], allowed: set[str] | frozenset[str], label: str) -> None:
    unexpected = sorted(paths - allowed)
    if unexpected:
        raise ScopeViolation(f'{label}: unauthorized paths: {unexpected}')


def audit_candidate_scope(root: Path = ROOT, *, include_live: bool = True) -> dict:
    """Audit pinned Formal -> HEAD plus optional live R2 paths; Git errors raise.

    R1 authorization cannot authorize fresh R2 edits to an R1-only file.
    Every caller uses the same rules, including the historical guard modules.
    """
    head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    _git(root, 'merge-base', '--is-ancestor', FORMAL_BASELINE, R1_CANDIDATE)
    _git(root, 'merge-base', '--is-ancestor', R1_CANDIDATE, head)
    reviewed = _committed_paths(root, FORMAL_BASELINE, R1_CANDIDATE)
    if reviewed != set(R1_RULES):
        raise ScopeViolation(f'Pinned R1 inventory mismatch: missing={sorted(set(R1_RULES)-reviewed)}, unexpected={sorted(reviewed-set(R1_RULES))}')
    committed = _committed_paths(root, FORMAL_BASELINE, head)
    history = _history_paths(root, FORMAL_BASELINE, head)
    if not committed or not set(R1_RULES) <= (committed | history):
        raise ScopeViolation('Empty or incomplete Formal-to-candidate audit')
    _require_allowed(committed | history, set(RULES), 'Formal..HEAD')
    r2_committed = _committed_paths(root, R1_CANDIDATE, head)
    r2_history = _history_paths(root, R1_CANDIDATE, head)
    live = _live_paths(root) if include_live else {}
    live_paths = set().union(*live.values())
    _require_allowed(r2_committed | r2_history | live_paths, R2_EDIT_PATHS, 'R1..R2 including live state')
    effective = committed | history | live_paths
    for path in effective:
        rule = RULES[path]
        if not rule.reason or not rule.regressions:
            raise ScopeViolation(f'Missing regression obligation: {path}')
        for test_path in rule.regressions:
            if not (ROOT / test_path).is_file():
                raise ScopeViolation(f'Missing regression module: {path}: {test_path}')
    return {
        'formal': FORMAL_BASELINE, 'r1': R1_CANDIDATE, 'head': head,
        'committed': sorted(committed), 'history': sorted(history),
        'r2_committed': sorted(r2_committed), 'r2_history': sorted(r2_history),
        **{key: sorted(value) for key, value in live.items()},
        'effective': sorted(effective),
        'coverage': {path: {'reason': RULES[path].reason, 'regressions': RULES[path].regressions}
                     for path in sorted(effective)},
    }
