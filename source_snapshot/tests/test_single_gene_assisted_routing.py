from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

from scripts.generate_component_library_v2_step3_routability import synthetic_probe_sequence
from services.component_library_v2_adoption import build_v2_canonical_inventory, v2_assisted_confirmation_contract, v2_canonical_record
from services.registry_catalog_ui import build_v2_user_provided_component
from services.single_gene_assisted_components import single_gene_assisted_role, single_gene_assisted_input, retained_assisted_fields
from services.plant_project_draft_repository import PlantProjectDraftRepository

ROOT = Path(__file__).resolve().parents[1]
ELIGIBLE = ('V2-CMP-004', 'V2-CMP-006', 'V2-CMP-099', 'V2-CMP-143', 'V2-EXT-R2-013', 'V2-EXT-R2-014')
HOST = 'Solanum lycopersicum'


@pytest.fixture
def project(tmp_path):
    repository = PlantProjectDraftRepository(tmp_path / 'projects')
    draft = repository.create_blank(project_name='TEST ONLY Single-Gene assisted')
    draft.workflow_type = 'single_gene'
    repository.save(draft)
    return repository, draft.project_id


def resolved(cid, project, **kwargs):
    row = v2_canonical_record(cid)
    confirmation = v2_assisted_confirmation_contract(row)
    args = dict(raw_sequence=synthetic_probe_sequence(row), display_name=row['name'],
                project_id=project[1], project_repository=project[0],
                user_sequence_source='TEST ONLY synthetic routing fixture; not accession DNA',
                identity_and_boundaries_confirmed=confirmation['has_reviewed_boundary'],
                project_intent_confirmed=not confirmation['has_reviewed_boundary'], explicit_user_confirmation=True)
    args.update(kwargs)
    return build_v2_user_provided_component(row, **args)


def routed(cid, project):
    return single_gene_assisted_input(resolved(cid, project), project_id=project[1], host=HOST, repository=project[0])


def full_result(project, cid='V2-CMP-004', utr_id='V2-EXT-R2-013'):
    from services.formal_single_gene_runtime import generate_complete_vector
    from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
    from tests.test_company_delivery_package import _alb_demo_result

    seed = copy.deepcopy(_alb_demo_result())
    records = seed['input_records']
    promoter = routed(cid, project)
    records['promoter'] = promoter
    utr = routed(utr_id, project)
    components = [dict(promoter, sequence=promoter['normalized_sequence']),
                  dict(utr, sequence=utr['normalized_sequence']),
                  dict(biological_role='cds', sequence=seed['cds_input']['normalized_cds'], display_name='TEST CDS', source_kind='paste', source_reference='TEST ONLY'),
                  dict(biological_role='terminator', sequence=records['terminator']['normalized_sequence'], display_name=records['terminator']['display_name'], source_kind='paste', source_reference='TEST ONLY')]
    assessment = assess_expression_cassette(components, cds_sequence=seed['cds_input']['normalized_cds'], cds_signature='test-only-cds', order_confirmed=True)
    generated = generate_expression_cassette(assessment, project_id=project[1])
    result = generate_complete_vector(cds_input=seed['cds_input'], input_records=records,
        insertion_settings=seed['insertion_settings'], project_id=project[1], project_name='TEST ONLY Single-Gene assisted',
        cassette_runtime=generated['runtime'], cassette_signature=generated['input_signature'])
    result['formal_expression_cassette'] = generated
    result['formal_project_context'] = {'host_key': HOST, 'current_step': 6}
    return result


def test_exact_semantic_eligibility_and_role_distribution():
    accepted = {}
    for row in build_v2_canonical_inventory():
        try:
            accepted[row['id']] = single_gene_assisted_role(row['id'], host=HOST)
        except ValueError:
            pass
    assert set(accepted) == set(ELIGIBLE)
    assert list(accepted.values()).count('promoter') == 4
    assert list(accepted.values()).count('five_prime_utr') == 2


@pytest.mark.parametrize('cid', ELIGIBLE)
def test_shared_resolution_to_correct_single_gene_role(project, cid):
    component = resolved(cid, project)
    record = single_gene_assisted_input(component, project_id=project[1], host=HOST, repository=project[0])
    assert record['component_reference'] == component['component_reference']
    assert record['biological_role'] == ('promoter' if cid.startswith('V2-CMP') else 'five_prime_utr')
    assert record['source_kind'] == 'user_recorded'
    assert record['source_input_method'] == 'paste'
    reference = record['component_reference']
    assert reference['source_type'] == 'USER_PROVIDED'
    assert reference['registry_component_id'] == reference['accession_version'] == ''
    c = reference['assisted_resolution']['confirmation_contract']
    assert c['accession_verified'] is c['boundary_verified_by_software'] is False


@pytest.mark.parametrize('host', ['', 'Escherichia coli', 'Nicotiana benthamiana', 'Arabidopsis thaliana'])
def test_wrong_or_unsupported_single_gene_host(project, host):
    with pytest.raises(ValueError, match='host'):
        single_gene_assisted_input(resolved('V2-CMP-004', project), project_id=project[1], host=host, repository=project[0])


@pytest.mark.parametrize('override', [
    {'raw_sequence':'ACGT'}, {'raw_sequence':'ACGT!'},
    {'identity_and_boundaries_confirmed':False}, {'explicit_user_confirmation':False},
    {'project_repository':None}, {'project_id':'not-persisted'}, {'user_sequence_source':''},
])
def test_shared_resolution_negative_contracts(project, override):
    with pytest.raises(ValueError):
        resolved('V2-CMP-004', project, **override)


@pytest.mark.parametrize('cid', ['V2-EXT-R2-013', 'V2-EXT-R2-014'])
def test_unknown_boundary_requires_project_intent(project, cid):
    with pytest.raises(ValueError, match='project_intent_confirmed'):
        resolved(cid, project, project_intent_confirmed=False, identity_and_boundaries_confirmed=True)


def test_cds_injection_and_reference_retired_fail_closed(project):
    for row in build_v2_canonical_inventory():
        if row['library_tier'] in {'REFERENCE', 'RETIRED'} or row.get('component_type') == 'cds':
            with pytest.raises(ValueError):
                single_gene_assisted_role(row['id'], host=HOST)
    cds = resolved('V2-CMP-129', project)
    cds['role'] = 'promoter'
    with pytest.raises(ValueError):
        single_gene_assisted_input(cds, project_id=project[1], host=HOST, repository=project[0])


@pytest.mark.parametrize('change', ['sequence','role','host','project','resolution'])
def test_stale_reference_cannot_silently_become_plain_input(project, change):
    record = routed('V2-CMP-004', project)
    args = dict(sequence=record['normalized_sequence'], role='promoter', project_id=project[1], host=HOST)
    if change == 'sequence': args['sequence'] += 'A'
    if change == 'role': args['role'] = 'five_prime_utr'
    if change == 'host': args['host'] = 'Oryza sativa'
    if change == 'project': args['project_id'] = 'wrong-project'
    if change == 'resolution': record['component_reference']['assisted_resolution']['resolution_id'] = '0'*64
    with pytest.raises(ValueError):
        retained_assisted_fields(record, **args)


@pytest.mark.parametrize('cid', ELIGIBLE[:4])
@pytest.mark.parametrize('utr_id', ELIGIBLE[4:])
def test_complete_vector_save_cold_reopen_report_and_exact_exports(project, cid, utr_id):
    from services.mvp_single_gene_persistence import save_mvp_single_gene_design, open_mvp_single_gene_design
    from services.formal_single_gene_final_review import build_final_review_report, render_formal_report_markdown

    result = full_result(project, cid, utr_id)
    saved = save_mvp_single_gene_design(result, repository=project[0])
    reopened = open_mvp_single_gene_design(saved.project_id, repository=project[0])
    assert reopened['runtime'] == result['runtime']
    assert reopened['exports'] == result['exports']
    fasta = SeqIO.read(StringIO(reopened['exports']['fasta']['data']), 'fasta')
    gb = SeqIO.read(StringIO(reopened['exports']['genbank']['data']), 'genbank')
    from services.canonical_construct_runtime import active_complete_plasmid_snapshot
    assert str(fasta.seq).upper() == str(gb.seq).upper() == active_complete_plasmid_snapshot(reopened['runtime'])['sequence']
    markdown = render_formal_report_markdown(build_final_review_report(reopened)).decode()
    for component_id in [cid, utr_id]:
        feature = next(f for f in gb.features if f.qualifiers.get('catalog_component_id') == [component_id])
        assert feature.qualifiers['sequence_authority'] == ['USER_PROVIDED']
        assert feature.qualifiers['accession_verified'] == feature.qualifiers['boundary_verified_by_software'] == ['false']
        assert component_id in markdown
        assert feature.qualifiers['resolution_id'][0] in markdown
    script = '''
import json, sys
from services.mvp_single_gene_persistence import open_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.formal_single_gene_final_review import build_final_review_report, render_formal_report_markdown
r = open_mvp_single_gene_design(sys.argv[2], repository=PlantProjectDraftRepository(sys.argv[1]))
print(json.dumps({'exports':r['exports'],'runtime':r['runtime'],'markdown':render_formal_report_markdown(build_final_review_report(r)).decode()}))
'''
    process = subprocess.run([sys.executable, '-c', script, str(project[0].storage_dir), project[1]], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr
    cold = json.loads(process.stdout.strip().splitlines()[-1])
    assert cold['exports'] == result['exports']
    assert cold['runtime'] == result['runtime']
    assert cold['markdown'] == markdown


@pytest.mark.parametrize('field', ['catalog_component_id','confirmation_mode','sequence_authority','source_accession','resolution_id','accession_verified'])
def test_save_refuses_modified_export_provenance(project, field):
    from components.export_manager import write_genbank_record
    from services.mvp_single_gene_persistence import save_mvp_single_gene_design
    result = full_result(project)
    record = SeqIO.read(StringIO(result['exports']['genbank']['data']), 'genbank')
    feature = next(f for f in record.features if f.qualifiers.get('catalog_component_id') == ['V2-CMP-004'])
    feature.qualifiers[field] = ['modified']
    out = StringIO(); write_genbank_record(record, out)
    result['exports']['genbank']['data'] = out.getvalue()
    before = {p.name:p.read_bytes() for p in project[0].storage_dir.glob('*.json')}
    with pytest.raises(ValueError, match='traceability'):
        save_mvp_single_gene_design(result, repository=project[0])
    assert before == {p.name:p.read_bytes() for p in project[0].storage_dir.glob('*.json')}


@pytest.mark.parametrize('workflow', ['', 'multi_tu', 'gate3_pathway'])
def test_persisted_project_must_be_single_gene(project, workflow):
    component = resolved('V2-CMP-004', project)
    draft = project[0].load(project[1])
    draft.workflow_type = workflow
    project[0].save(draft)
    with pytest.raises(ValueError, match='persisted Single-Gene'):
        single_gene_assisted_input(component, project_id=project[1], host=HOST, repository=project[0])


def test_save_refuses_erased_canonical_reference(project):
    from services.mvp_single_gene_persistence import save_mvp_single_gene_design
    result = full_result(project)
    for component in result['runtime']['components']:
        component.pop('component_reference', None)
    with pytest.raises(ValueError, match='traceability'):
        save_mvp_single_gene_design(result, repository=project[0])


def test_assisted_reference_changes_invalidate_cassette_signature(project):
    from services.formal_expression_cassette import assess_expression_cassette
    record = routed('V2-EXT-R2-013', project)
    component = dict(record, sequence=record['normalized_sequence'])
    def signature(value):
        return assess_expression_cassette([value], cds_sequence='', cds_signature='', order_confirmed=True)['input_signature']
    old = signature(component)
    component['component_reference']['assisted_resolution']['resolution_id'] = '0'*64
    assert signature(component) != old


@pytest.mark.parametrize('cid', ELIGIBLE)
def test_incomplete_draft_preserves_reference_in_independent_process(project, cid):
    from core.design_session import DesignSession
    from services.formal_project_persistence import save_formal_project_draft

    record = routed(cid, project)
    save_formal_project_draft(
        project_name='TEST ONLY assisted draft', project_id=project[1], workflow_type='single_gene',
        current_step=3, design_session=DesignSession(step=3, host=HOST),
        formal_state={'formal_element_source_records': {record['biological_role']:record}},
        project_definition={'project_name':'TEST ONLY assisted draft','plant_host':HOST}, repository=project[0],
    )
    script = '''
import json,sys
from services.formal_project_persistence import formal_draft_snapshot
from services.plant_project_draft_repository import PlantProjectDraftRepository
s=formal_draft_snapshot(PlantProjectDraftRepository(sys.argv[1]).load(sys.argv[2]))
print(json.dumps(s['formal_state']['formal_element_source_records']))
'''
    cold = subprocess.run([sys.executable,'-c',script,str(project[0].storage_dir),project[1]],cwd=ROOT,text=True,capture_output=True,timeout=60)
    assert cold.returncode == 0, cold.stderr
    assert json.loads(cold.stdout.strip().splitlines()[-1]) == {record['biological_role']:record}


@pytest.mark.parametrize('source', ['promoter','cassette','project_host'])
def test_save_refuses_divergent_editor_provenance(project, source):
    from services.mvp_single_gene_persistence import save_mvp_single_gene_design
    result = full_result(project)
    if source == 'promoter': result['input_records']['promoter'].pop('component_reference')
    if source == 'cassette': result['formal_expression_cassette']['components'][1].pop('component_reference')
    if source == 'project_host': result['formal_project_context']['host_key'] = 'Oryza sativa'
    with pytest.raises(ValueError):
        save_mvp_single_gene_design(result, repository=project[0])


def test_canonical_algorithms_and_shared_resolution_remain_frozen():
    baseline = '795a5f27f609d8be729c9d7004ec2a7c4551fe2b'
    def original(path):
        return subprocess.check_output(['git','show',baseline+':'+path],cwd=ROOT).decode('utf-8')
    def functions(source):
        return {n.name:ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
    for path in ['services/component_library_v2_adoption.py','services/registry_catalog_ui.py',
                 'services/plant_component_workflow_registry.py','services/mvp_multi_tu_runtime.py',
                 'services/mvp_multi_tu_persistence.py']:
        assert (ROOT/path).read_text(encoding='utf-8') == original(path)
    path='services/canonical_construct_runtime.py'
    before,after=functions(original(path)),functions((ROOT/path).read_text(encoding='utf-8'))
    assert {name for name in before if before[name]!=after[name]} == {'export_active_construct','export_active_complete_plasmid'}
    before,after=functions(original('app.py')),functions((ROOT/'app.py').read_text(encoding='utf-8'))
    for name in ['_use_catalog_component_in_multi_tu','_render_dual_tu_step_3','_render_dual_tu_element_input','_use_plant_library_record']:
        assert before[name] == after[name]
    assert subprocess.check_output(['git','diff',baseline,'--','data/component_library_v2_qualified_core_r2','data/plant_component_registry_v1'],cwd=ROOT)==b''
