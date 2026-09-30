from __future__ import annotations

import subprocess

import pytest

from tests import component_library_v2_scope as scope


def test_complete_formal_candidate_path_set_has_explicit_coverage():
    audit = scope.audit_candidate_scope()
    actual = scope._committed_paths(scope.ROOT, scope.FORMAL_BASELINE, 'HEAD')
    assert set(audit['committed']) == actual
    assert len(scope.R1_RULES) == 28
    assert actual
    assert set(audit['effective']) == set(audit['coverage'])
    assert not any('*' in path or '?' in path for path in scope.RULES)


def test_clean_committed_candidate_still_audits_complete_range(tmp_path):
    # Clone existing commits; no commit/stage/branch change in the source.
    # Sparse checkout keeps the fixture small while git diff sees every tree.
    clone = tmp_path / 'clean-candidate'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--sparse', str(scope.ROOT), str(clone)],
                   check=True, capture_output=True)
    assert scope._git(clone, 'status', '--porcelain', '--untracked-files=all') == b''
    audit = scope.audit_candidate_scope(clone)
    expected = scope._committed_paths(clone, scope.FORMAL_BASELINE, 'HEAD')
    assert set(audit['committed']) == expected
    assert set(scope.R1_RULES) <= set(audit['history'])
    assert len(expected) >= 28
    assert not audit['staged'] and not audit['unstaged'] and not audit['untracked']
    assert 'services/component_output_provenance.py' in audit['coverage']
    assert 'services/formal_results_report_contract.py' in audit['coverage']
    assert 'services/formal_single_gene_final_review.py' in audit['coverage']
    assert scope._git(clone, 'status', '--porcelain') == b''


@pytest.mark.parametrize('path', [
    'services/unapproved_production.py', 'services/project_import_service.py',
    'components/unapproved_export.py', 'tests/unexpected_scope.py',
    'docs/qa/unapproved.md', 'services/name with spaces.py',
])
def test_unauthorized_committed_path_fails_even_with_empty_live_state(monkeypatch, path):
    original = scope._committed_paths
    calls = []

    def injected(root, base, head):
        paths = original(root, base, head)
        calls.append((base, head))
        # First call verifies immutable R1; second reads Formal -> HEAD.
        return paths | {path} if len(calls) == 2 else paths

    monkeypatch.setattr(scope, '_committed_paths', injected)
    monkeypatch.setattr(scope, '_live_paths', lambda root: {'staged': set(), 'unstaged': set(), 'untracked': set()})
    with pytest.raises(scope.ScopeViolation, match='Formal..HEAD: unauthorized'):
        scope.audit_candidate_scope()
    assert len(calls) == 2


@pytest.mark.parametrize('layer', ['staged', 'unstaged', 'untracked'])
def test_live_unauthorized_path_fails_in_each_layer(monkeypatch, layer):
    live = {'staged': set(), 'unstaged': set(), 'untracked': set()}
    live[layer].add('services/project_export_package_service.py')
    monkeypatch.setattr(scope, '_live_paths', lambda root: live)
    with pytest.raises(scope.ScopeViolation, match='R1..R2 including live state: unauthorized'):
        scope.audit_candidate_scope()


def test_reverted_unauthorized_committed_path_is_not_hidden(monkeypatch):
    original = scope._history_paths
    monkeypatch.setattr(scope, '_history_paths', lambda root, base, head:
                        original(root, base, head) | {'services/reverted_unauthorized.py'})
    with pytest.raises(scope.ScopeViolation, match='reverted_unauthorized'):
        scope.audit_candidate_scope(include_live=False)


@pytest.mark.parametrize('layer', ['committed', 'live'])
def test_r1_authorization_does_not_authorize_new_r2_report_edits(monkeypatch, layer):
    path = 'services/formal_results_report_contract.py'
    if layer == 'live':
        monkeypatch.setattr(scope, '_live_paths', lambda root: {'unstaged': {path}})
    else:
        original = scope._history_paths
        monkeypatch.setattr(scope, '_history_paths', lambda root, base, head:
                            original(root, base, head) | ({path} if base == scope.R1_CANDIDATE else set()))
    with pytest.raises(scope.ScopeViolation, match='R1..R2 including live state: unauthorized'):
        scope.audit_candidate_scope()


def test_git_failure_cannot_be_interpreted_as_an_empty_clean_result(monkeypatch):
    def fail(*args):
        raise subprocess.CalledProcessError(128, ['git', 'diff'])
    monkeypatch.setattr(scope, '_git', fail)
    with pytest.raises(subprocess.CalledProcessError):
        scope.audit_candidate_scope()


def test_missing_pinned_path_or_empty_range_fails_closed(monkeypatch):
    monkeypatch.setattr(scope, '_committed_paths', lambda *args: set())
    with pytest.raises(scope.ScopeViolation, match='Pinned R1 inventory mismatch'):
        scope.audit_candidate_scope()


def test_empty_candidate_diff_cannot_pass_after_valid_pinned_inventory(monkeypatch):
    original = scope._committed_paths
    calls = []
    def empty_candidate(root, base, head):
        calls.append((base, head))
        return original(root, base, head) if len(calls) == 1 else set()
    monkeypatch.setattr(scope, '_committed_paths', empty_candidate)
    with pytest.raises(scope.ScopeViolation, match='Empty or incomplete'):
        scope.audit_candidate_scope(include_live=False)


@pytest.mark.parametrize('module_name,test_name', [
    ('test_v2_7_r10_r30_live_worktree_inventory_guard', 'test_r31_live_worktree_contains_only_allowed_inventory_paths'),
    ('test_v2_7_r10_r30_live_worktree_inventory_guard', 'test_r31_live_worktree_excludes_protected_areas'),
    ('test_v2_7_r20_r31_post_full_regression_scope_guard', 'test_live_tracked_product_diff_stays_within_full_regression_covered_paths'),
    ('test_v2_7_r20_r31_post_full_regression_scope_guard', 'test_live_untracked_product_files_are_expected_extracted_sections_only'),
    ('test_v2_7_r20_r31_post_full_regression_scope_guard', 'test_live_worktree_has_no_protected_runtime_paths_after_full_regression'),
])
def test_existing_guard_entrypoints_reject_committed_unauthorized_paths(monkeypatch, module_name, test_name):
    import importlib
    original = scope._history_paths
    monkeypatch.setattr(scope, '_history_paths', lambda root, base, head:
                        original(root, base, head) | {'services/unauthorized_committed.py'})
    monkeypatch.setattr(scope, '_live_paths', lambda root: {'staged': set(), 'unstaged': set(), 'untracked': set()})
    with pytest.raises(scope.ScopeViolation, match='unauthorized_committed'):
        getattr(importlib.import_module('tests.' + module_name), test_name)()


def test_missing_regression_obligation_fails_closed(monkeypatch):
    monkeypatch.setitem(scope.RULES, 'app.py', scope.ScopeRule('test fault injection', ()))
    with pytest.raises(scope.ScopeViolation, match='Missing regression obligation'):
        scope.audit_candidate_scope()


def test_nul_paths_and_both_rename_endpoints_are_preserved(monkeypatch):
    calls = []
    def output(root, *args):
        calls.append(args)
        return b'services/old name.py\0services/new name.py\0'
    monkeypatch.setattr(scope, '_git', output)
    assert scope._committed_paths(scope.ROOT, 'base', 'head') == {
        'services/old name.py', 'services/new name.py'}
    assert '--no-renames' in calls[0] and '-z' in calls[0]


def test_previously_missing_paths_have_explicit_regression_obligations():
    for path in ('components/export_manager.py', 'services/component_output_provenance.py',
                 'services/formal_results_report_contract.py',
                 'services/formal_single_gene_final_review.py', scope.OUTPUT_TEST):
        assert path in scope.R1_RULES
        assert scope.OUTPUT_TEST in scope.RULES[path].regressions


def test_qa_records_every_exact_covered_path():
    text = (scope.ROOT / scope.QA_RECORD).read_text(encoding='utf-8')
    for path in scope.RULES:
        assert f'`{path}`' in text, path
