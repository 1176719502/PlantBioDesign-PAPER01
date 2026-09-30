from __future__ import annotations

import ast
import copy
import hashlib
from io import StringIO
from pathlib import Path

from Bio import SeqIO
import pytest

from components.export_manager import generate_genbank_string
from core.i18n import translate
from services.formal_single_gene_final_review import build_final_review_report, render_formal_report_markdown
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import selection_qualifiers
from tests.test_component_library_v2_product_adoption_r1 import _repository, _assisted_component, _plain_component
from services.component_library_v2_adoption import v2_canonical_record


@pytest.fixture
def assisted_case(tmp_path):
    repository, project_id = _repository(tmp_path, 'TEST ONLY output provenance')
    promoter = _assisted_component(v2_canonical_record('V2-CMP-004'), repository, project_id)
    unit = {
        'unit_id': 'test-output-tu', 'display_name': 'TEST ONLY TU',
        'order': 1, 'orientation': 'forward', 'promoter': promoter,
        'cds': _plain_component('TEST ONLY CDS', 'ATGGCCGCCTAA'),
        '3_prime_regulatory_region': _plain_component('TEST ONLY 3-prime', 'TTTTACGT'),
    }
    result = generate_multi_tu_combined_construct(
        project_id=project_id, project_name='TEST ONLY output provenance', expression_units=[unit],
    )
    result['project_type'] = 'dual_tu'
    result['formal_project_context'] = {'current_step': 6, 'design_scenario': 'standard_plant_expression_vector'}
    return repository, result, promoter['component_reference']


def capture_source_rows(result, language='en'):
    """Execute the actual Step 6 source-table projection without page side effects."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
    renderer = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and any(isinstance(x, ast.Name) and x.id == 'source_rows' for x in ast.walk(n)))
    start = next(i for i, n in enumerate(renderer.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'original_units' for t in n.targets))
    end = next(i for i, n in enumerate(renderer.body) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'review_rows' for t in n.targets))
    ns = {'result': result, 'units': result['expression_units'],
          '_multi_tu_role_display_label': lambda x: x, '_multi_tu_source_label': lambda x: x,
          '_multi_tu_evidence_label': lambda x, **kw: x, '_ui': lambda x: x,
          '_t': lambda key, **kw: translate(key, language=language, **kw)}
    exec(compile(ast.Module(body=renderer.body[start:end], type_ignores=[]), 'app.py', 'exec'), ns)
    return ns['source_rows']


@pytest.mark.parametrize('key', ['sequence_sha256', 'user_sequence_sha256', 'resolution_id',
                                'source_asset_id', 'feature_sha256', 'source_record_sha256'])
def test_exact_qualifier_roundtrip(key):
    digest = '123456789abcdef0' * 4
    original = 'seqasset_' + digest if key == 'source_asset_id' else digest
    data = generate_genbank_string('ACGT', [{'name': 'TEST ONLY', 'start': 1, 'end': 4,
                                            'qualifiers': {key: [original]}}], 'exact-roundtrip')
    parsed = SeqIO.read(StringIO(data), 'genbank')
    assert parsed.features[0].qualifiers[key] == [original]
    if key.endswith('sha256'):
        assert len(parsed.features[0].qualifiers[key][0]) == 64


@pytest.mark.parametrize('language', ['en', 'zh-CN'])
def test_step6_assisted_source_fields(assisted_case, language):
    _, result, reference = assisted_case
    before = copy.deepcopy(result)
    rows = capture_source_rows(result, language)
    row = rows[0]
    assert row['来源 accession/version'] == 'AF308778.1'
    rendered = ' '.join(str(v) for v in row.values())
    resolution = reference['assisted_resolution']
    for expected in ('V2-CMP-004', 'ACT7; promoter', 'USER_SEQUENCE_ASSISTED', 'USER_PROVIDED',
                     resolution['user_sequence_source'], resolution['sequence_sha256'],
                     resolution['resolution_id'], resolution['project_id'], '1..1202 (+)'):
        assert expected in rendered
    assert row['accession_verified'] == 'false'
    assert row['boundary_verified_by_software'] == 'false'
    assert row['confirmation_mode'] == 'IDENTITY_AND_RECORDED_BOUNDARY'
    assert result == before


def test_assisted_genbank_full_pipeline(assisted_case):
    _, result, reference = assisted_case
    resolution = reference['assisted_resolution']
    parsed = SeqIO.read(StringIO(result['exports']['combined_construct_genbank']['data']), 'genbank')
    feature = next(f for f in parsed.features if f.qualifiers.get('catalog_component_id') == ['V2-CMP-004'])
    expected = {'accession_version': 'AF308778.1', 'source_accession': 'AF308778.1',
                'catalog_name': 'ACT7; promoter', 'sequence_authority': 'USER_PROVIDED',
                'admission_mode': 'USER_SEQUENCE_ASSISTED', 'sequence_sha256': resolution['sequence_sha256'],
                'user_sequence_sha256': resolution['sequence_sha256'],
                'user_sequence_source': resolution['user_sequence_source'],
                'reviewed_source_boundary': resolution['confirmation_contract']['recorded_boundary'],
                'resolution_id': resolution['resolution_id'], 'project_id': resolution['project_id'],
                'accession_verified': 'false', 'boundary_verified_by_software': 'false'}
    for key, value in expected.items():
        assert feature.qualifiers[key] == [value], key
    asset = result['runtime']['expression_units'][0]['promoter']['sequence_asset_id']
    assert feature.qualifiers['source_asset_id'] == [asset]
    fasta = SeqIO.read(StringIO(result['exports']['combined_construct_fasta']['data']), 'fasta')
    expected_dna = resolution['normalized_sequence'] + 'ATGGCCGCCTAA' + 'TTTTACGT'
    assert str(fasta.seq) == str(parsed.seq).upper() == result['combined_construct']['dna'] == expected_dna
    assert result['combined_construct']['sequence_sha256'] == hashlib.sha256(expected_dna.encode()).hexdigest()


@pytest.mark.parametrize('language', ['en', 'zh-CN'])
@pytest.mark.parametrize('component_id,expected_mode', [
    ('V2-CMP-004', 'IDENTITY_AND_RECORDED_BOUNDARY'),
    *[(f'V2-EXT-R2-{i:03d}', 'PROJECT_INTENT')
      for i in range(13, 18)],
])
def test_step6_confirmation_mode_preserves_recorded_semantics(
        tmp_path, language, component_id, expected_mode):
    from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design, open_mvp_multi_tu_design
    from services.registry_catalog_ui import component_role_for_catalog_record

    repository, project_id = _repository(tmp_path, 'TEST ONLY confirmation mode')
    row = v2_canonical_record(component_id)
    # Use the catalog's actual role, without reinterpreting uncertain boundaries.
    role = component_role_for_catalog_record(row)
    assisted = _assisted_component(row, repository, project_id)
    unit = {'unit_id': 'confirmation-tu', 'display_name': 'TEST ONLY TU',
            'order': 1, 'orientation': 'forward',
            'promoter': _plain_component('TEST ONLY promoter', 'AACCGGTT'),
            'cds': _plain_component('TEST ONLY CDS', 'ATGGCCGCCTAA'),
            '3_prime_regulatory_region': _plain_component('TEST ONLY 3-prime', 'TTTTACGT'),
            role: assisted}
    result = generate_multi_tu_combined_construct(
        project_id=project_id, project_name='TEST ONLY confirmation mode', expression_units=[unit])
    result['project_type'] = 'dual_tu'
    result['formal_project_context'] = {'current_step': 6, 'design_scenario': 'standard_plant_expression_vector'}
    before = copy.deepcopy(result)
    rows = capture_source_rows(result, language)
    source = next(r for r in rows if component_id in r.values())
    assert source['confirmation_mode'] == expected_mode
    assert source['accession_verified'] == source['boundary_verified_by_software'] == 'false'
    assert result == before
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert capture_source_rows(reopened, language) == rows
    assert reopened['runtime'] == before['runtime']
    assert reopened['exports'] == before['exports']
    record = SeqIO.read(StringIO(reopened['exports']['combined_construct_genbank']['data']), 'genbank')
    feature = next(f for f in record.features if f.qualifiers.get('catalog_component_id') == [component_id])
    assert feature.qualifiers['confirmation_mode'] == [expected_mode]


def test_final_report_includes_bound_assisted_provenance(assisted_case):
    _, result, reference = assisted_case
    before = copy.deepcopy(result)
    report = build_final_review_report(result)
    markdown = render_formal_report_markdown(report).decode('utf-8')
    resolution = reference['assisted_resolution']
    for expected in ('V2-CMP-004', 'ACT7; promoter', 'AF308778.1', 'USER_SEQUENCE_ASSISTED',
                     'USER_PROVIDED', resolution['user_sequence_source'], resolution['sequence_sha256'],
                     resolution['resolution_id'], resolution['project_id'], '1..1202 (+)',
                     'accession_verified=false', 'boundary_verified_by_software=false'):
        assert expected in markdown
    assert 'source=USER_PROVIDED | reference=AF308778.1' in markdown
    assert result == before


def test_exact_writer_preserves_quotes_and_normal_note_wrapping():
    from components.export_manager import write_genbank_record
    from Bio.Seq import Seq
    from Bio.SeqFeature import SeqFeature, SimpleLocation
    from Bio.SeqRecord import SeqRecord

    label = 'supplied "source"; ' + 'ABCD' * 40
    note = 'Documentation source note with ordinary words. ' * 12
    record = SeqRecord(Seq('ACGT'), id='test', annotations={'molecule_type': 'DNA'})
    record.features = [SeqFeature(SimpleLocation(0, 4), type='misc_feature',
                                  qualifiers={'user_sequence_source': [label], 'note': [note.rstrip()]})]
    before = copy.deepcopy(record.features[0].qualifiers)
    output = StringIO()
    write_genbank_record(record, output)
    parsed = SeqIO.read(StringIO(output.getvalue()), 'genbank')
    assert parsed.features[0].qualifiers == before
    assert record.features[0].qualifiers == before
    note_lines = output.getvalue().split('/note=', 1)[1].split('ORIGIN', 1)[0].splitlines()
    assert len(note_lines) > 1
    assert max(map(len, note_lines)) <= 80


def test_legacy_missing_flags_and_boundary_stay_unrecorded(assisted_case):
    from services.component_output_provenance import assisted_component_provenance

    _, result, reference = assisted_case
    legacy = copy.deepcopy(reference)
    legacy['assisted_resolution'].pop('confirmation_contract')
    projected = assisted_component_provenance(legacy)
    assert projected['accession_verified'] is None
    assert projected['boundary_verified_by_software'] is None
    assert projected['reviewed_source_boundary'] == ''
    assert legacy['assisted_resolution']['source_provenance']['source_coordinates']
    qualifiers = selection_qualifiers(legacy)
    assert qualifiers['accession_verified'] == ['not_recorded']
    assert qualifiers['boundary_verified_by_software'] == ['not_recorded']
    assert 'reviewed_source_boundary' not in qualifiers
    result['expression_units'][0]['components'][0]['component_reference'] = legacy
    for language in ('en', 'zh-CN'):
        rows = capture_source_rows(result, language)
        assert rows[0]['accession_verified'] == translate('v1.component_library.v2_verification_not_recorded', language=language)
        assert rows[0]['confirmation_mode'] == translate('v1.expression.not_recorded', language=language)


def test_plain_user_input_does_not_acquire_assisted_identity(assisted_case):
    from services.component_output_provenance import assisted_component_provenance

    _, result, _ = assisted_case
    for role in ('cds', '3_prime_regulatory_region'):
        reference = result['expression_units'][0]['component_references'][role]
        assert assisted_component_provenance(reference) == {}
        assert 'catalog_component_id' not in selection_qualifiers(reference)


def test_current_cached_export_refresh_changes_only_genbank(assisted_case):
    from services.mvp_multi_tu_runtime import project_assisted_assembly_outputs

    _, result, _ = assisted_case
    old = SeqIO.read(StringIO(result['exports']['combined_construct_genbank']['data']), 'genbank')
    for feature in old.features:
        if feature.qualifiers.get('catalog_component_id') == ['V2-CMP-004']:
            feature.qualifiers['accession_version'] = ['unavailable']
            feature.qualifiers.pop('source_accession')
    output = StringIO()
    SeqIO.write(old, output, 'genbank')
    result['exports']['combined_construct_genbank']['data'] = output.getvalue()
    before = copy.deepcopy(result)
    projected = project_assisted_assembly_outputs(result)
    assert result == before
    assert projected['runtime'] == before['runtime']
    assert projected['combined_construct'] == before['combined_construct']
    assert projected['exports']['combined_construct_fasta'] == before['exports']['combined_construct_fasta']
    assert projected['exports']['combined_construct_genbank']['data'] != output.getvalue()
    parsed = SeqIO.read(StringIO(projected['exports']['combined_construct_genbank']['data']), 'genbank')
    feature = next(f for f in parsed.features if f.qualifiers.get('catalog_component_id') == ['V2-CMP-004'])
    assert feature.qualifiers['accession_version'] == ['AF308778.1']
    assert len(feature.qualifiers['sequence_sha256'][0]) == 64
    before['exports']['combined_construct_genbank'] = projected['exports']['combined_construct_genbank']
    assert projected == before


def test_canonical_id_binding_is_independent_of_display_names(assisted_case):
    from services.component_output_provenance import runtime_assisted_component_provenance

    _, result, reference = assisted_case
    runtime = copy.deepcopy(result['runtime'])
    for component in runtime['components']:
        component['display_name'] = 'Same name'
    records = runtime_assisted_component_provenance(runtime)
    component_id = runtime['expression_units'][0]['promoter']['component_id']
    assert set(records) == {component_id}
    assert records[component_id]['resolution_id'] == reference['assisted_resolution']['resolution_id']


@pytest.mark.parametrize('field,value', [('project_id', 'another-project'), ('sequence_sha256', '0' * 64)])
def test_report_rejects_assisted_binding_that_contradicts_canonical_asset(assisted_case, field, value):
    from services.formal_results_report_contract import FormalResultsReportContractError, _component_authority

    _, result, _ = assisted_case
    runtime = copy.deepcopy(result['runtime'])
    promoter = runtime['expression_units'][0]['promoter']
    promoter['component_reference']['assisted_resolution'][field] = value
    state = {'runtime': runtime, 'cassette': {'ordered_component_ids': [promoter['component_id']]}}
    with pytest.raises(FormalResultsReportContractError, match='canonical asset/project'):
        _component_authority(state)


@pytest.mark.parametrize('component_id,role', [('V2-CMP-138', 'promoter'), ('V2-CMP-144', '3_prime_regulatory_region')])
def test_direct_use_output_authority_is_preserved(tmp_path, component_id, role):
    from services.component_library_v2_adoption import build_v2_direct_component
    from services.component_output_provenance import assisted_component_provenance
    from services.mvp_multi_tu_runtime import project_assisted_assembly_outputs

    component = build_v2_direct_component(v2_canonical_record(component_id), role=role)
    reference = component['component_reference']
    assert assisted_component_provenance(reference) == {}
    before = copy.deepcopy(reference)
    qualifiers = selection_qualifiers(reference)
    assert qualifiers['source_type'] == ['V2_CORE']
    assert qualifiers['accession_version'] == [reference['accession_version']]
    assert 'user_sequence_source' not in qualifiers
    assert 'accession_verified' not in qualifiers
    data = generate_genbank_string(component['raw_text'], [{'name': 'Direct use', 'start': 1,
                                  'end': len(component['raw_text']), 'qualifiers': qualifiers}], 'direct')
    parsed = SeqIO.read(StringIO(data), 'genbank')
    for key in ('sequence_sha256', 'feature_sha256', 'source_record_sha256'):
        if key in qualifiers:
            assert parsed.features[0].qualifiers[key] == qualifiers[key]
    assert reference == before
    result = {'runtime': {'expression_units': [{'promoter': {'component_id': 'c', 'component_reference': reference}}]},
              'exports': {'combined_construct_genbank': {'data': data}}}
    assert project_assisted_assembly_outputs(result) is result


def test_assisted_report_markdown_pdf_and_cold_reopen_share_contract(assisted_case):
    from services.formal_report_pdf import _require_projection, render_formal_report_pdf
    from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design, open_mvp_multi_tu_design

    repository, result, reference = assisted_case
    report = build_final_review_report(result)
    markdown, content_hash = _require_projection(report)
    assert markdown.encode() == render_formal_report_markdown(report)
    assert content_hash == hashlib.sha256(markdown.encode()).hexdigest()
    pdf = render_formal_report_pdf(report)
    assert pdf.startswith(b'%PDF-')
    assert pdf == render_formal_report_pdf(report)
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert reopened['runtime'] == result['runtime']
    assert reopened['exports'] == result['exports']
    reopened_report = build_final_review_report(reopened)
    assert render_formal_report_markdown(reopened_report) == markdown.encode()
    assert render_formal_report_pdf(reopened_report) == pdf


def _step6_output_and_save_functions(result):
    """Execute app.py's output preparation and actual footer save handler.

    Only visual rendering after output preparation is omitted; projection,
    canonical checks, completed-state binding and persistence are real.
    """
    from types import SimpleNamespace
    from typing import Any
    from tests.test_multi_tu_completed_editor_reopen import _bind_completed_state

    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
    functions = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    renderer = functions['_render_multi_tu_assembly_results']
    end = next(i for i, n in enumerate(renderer.body)
               if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
               and n.target.id == 'final_review_report')
    renderer.body = renderer.body[:end] + [ast.Return(value=ast.Name(id='result', ctx=ast.Load()))]
    module = ast.fix_missing_locations(ast.Module(
        body=[renderer, functions['_save_current_formal_draft']], type_ignores=[]))
    state = {'mvp_vector_result': result}
    namespace = {'Any': Any, 'st': SimpleNamespace(session_state=state),
                 '_bind_completed_formal_state': _bind_completed_state,
                 '_is_dual_tu_project': lambda: True}
    exec(compile(module, 'app.py', 'exec'), namespace)
    return state, namespace['_render_multi_tu_assembly_results'], namespace['_save_current_formal_draft']


def _replace_assisted_qualifier(result, key, value):
    from components.export_manager import write_genbank_record

    data = result['exports']['combined_construct_genbank']['data']
    record = SeqIO.read(StringIO(data), 'genbank')
    feature = next(f for f in record.features if f.qualifiers.get('catalog_component_id') == ['V2-CMP-004'])
    if value is None:
        feature.qualifiers.pop(key)
    else:
        feature.qualifiers[key] = [value]
    output = StringIO()
    write_genbank_record(record, output)
    result['exports']['combined_construct_genbank']['data'] = output.getvalue()


def test_step6_footer_saves_exact_displayed_genbank_after_cached_provenance_refresh(assisted_case):
    from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design

    repository, result, reference = assisted_case
    _replace_assisted_qualifier(result, 'accession_version', 'unavailable')
    for key in ('source_accession', 'catalog_component_type', 'sequence_authority',
                'user_sequence_source', 'reviewed_source_boundary', 'project_id',
                'confirmation_mode', 'accession_verified', 'boundary_verified_by_software'):
        _replace_assisted_qualifier(result, key, None)
    before = copy.deepcopy(result)
    state, render, save = _step6_output_and_save_functions(result)
    displayed = render(result, is_current=True, publication_map_current=True,
                       report_delivery_current=True, save_design=None, include_project_actions=False)
    assert result == before
    saved = save(current_step=6, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert reopened['exports'] == displayed['exports'] == state['mvp_vector_result']['exports']
    assert reopened['formal_editor_restoration_eligible']
    assert reopened['runtime'] == before['runtime']
    assert reopened['combined_construct'] == before['combined_construct']
    assert reopened['exports']['combined_construct_fasta'] == before['exports']['combined_construct_fasta']
    assert reopened['expression_units'][0]['component_references']['promoter'] == reference
    assert state['formal_last_saved_mvp_project_id'] == result['project_id']


@pytest.mark.parametrize('current,preview', [(False, False), (True, True)])
def test_stale_or_historical_outputs_do_not_replace_current_save_payload(assisted_case, current, preview):
    _, result, _ = assisted_case
    _replace_assisted_qualifier(result, 'accession_version', 'unavailable')
    before = copy.deepcopy(result)
    state, render, _ = _step6_output_and_save_functions(result)
    assert render(result, is_current=current, publication_map_current=current,
                  report_delivery_current=current, save_design=None, result_preview_mode=preview) is result
    assert state['mvp_vector_result'] is result
    assert result == before


@pytest.mark.parametrize('kind', ['plain_user', 'direct_registry', 'mixed_assisted_registry'])
def test_component_authority_variants_survive_genbank_save_parse_reopen(assisted_case, kind):
    from services.registry_catalog_ui import build_direct_registry_component
    from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design, open_mvp_multi_tu_design
    from services.mvp_multi_tu_runtime import multi_tu_assembly_snapshot

    repository, base, _ = assisted_case
    unit = copy.deepcopy(base['original_input']['expression_units'][0])
    if kind == 'plain_user':
        unit['promoter'] = _plain_component('TEST ONLY user promoter', 'AACCGGTT')
    else:
        unit['promoter'] = build_direct_registry_component(
            v2_canonical_record('V2-CMP-138'), requested_host='Solanum lycopersicum')
        unit['3_prime_regulatory_region'] = build_direct_registry_component(
            v2_canonical_record('V2-CMP-144'), requested_host='Solanum lycopersicum')
    unit.update(unit_id='test-direct-or-plain', order=1)
    units = [unit]
    if kind == 'mixed_assisted_registry':
        assisted_unit = copy.deepcopy(base['original_input']['expression_units'][0])
        assisted_unit['order'] = 2
        units.append(assisted_unit)
    result = generate_multi_tu_combined_construct(
        project_id=base['project_id'], project_name=base['project_name'], expression_units=units)
    before = copy.deepcopy(result)
    record = SeqIO.read(StringIO(result['exports']['combined_construct_genbank']['data']), 'genbank')
    snapshot = multi_tu_assembly_snapshot(result['runtime'])
    for active_unit in snapshot['expression_units']:
        for role, ref in active_unit['component_references'].items():
            feature = next(f for f in record.features if f.qualifiers.get('unit_id') == [active_unit['unit_id']]
                           and f.qualifiers.get('biological_role') == [role])
            for key, values in selection_qualifiers(ref).items():
                if key in {'component_contract', 'citation'}:
                    # Existing Registry contract/citation continuation behavior;
                    # all assisted provenance and identity qualifiers stay exact.
                    assert ''.join(feature.qualifiers[key]).replace(' ', '') == ''.join(values).replace(' ', '')
                else:
                    assert feature.qualifiers[key] == values, (role, key)
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert result == before
    assert reopened['runtime'] == result['runtime']
    assert reopened['exports'] == result['exports']
    assert str(record.seq).upper() == result['combined_construct']['dna']
    assert hashlib.sha256(str(record.seq).upper().encode()).hexdigest() == result['combined_construct']['sequence_sha256']


@pytest.mark.parametrize('key,wrong_value', [
    ('accession_version', 'AF308778.2'), ('source_accession', 'AF308778.2'),
    ('catalog_component_id', 'V2-CMP-005'), ('catalog_name', 'wrong catalog label'),
    ('governance_status', 'DIRECT_USE'), ('admission_mode', 'DIRECT_USE'),
    ('resolution_id', '0' * 64), ('sequence_sha256', '0' * 64),
    ('user_sequence_sha256', '0' * 64), ('source_type', 'REGISTRY'),
    ('sequence_authority', 'REGISTRY'), ('user_sequence_source', 'wrong source'),
    ('reviewed_source_boundary', '2..1203 (+)'), ('project_id', 'wrong-project'),
    ('confirmation_mode', 'wrong-mode'), ('accession_verified', 'true'),
    ('boundary_verified_by_software', 'true'), ('catalog_component_type', 'cds'),
])
@pytest.mark.parametrize('remove', [False, True])
def test_final_save_fails_closed_for_changed_or_missing_traceability(assisted_case, key, wrong_value, remove):
    from services.mvp_multi_tu_persistence import MvpMultiTuPersistenceError

    repository, result, _ = assisted_case
    state, render, save = _step6_output_and_save_functions(result)
    displayed = render(result, is_current=True, publication_map_current=True,
                       report_delivery_current=True, save_design=None, include_project_actions=False)
    # Change the emitted payload after output preparation. The actual footer
    # save must reject it, without re-exporting over the mismatch at save time.
    state['mvp_vector_result'] = displayed
    _replace_assisted_qualifier(displayed, key, None if remove else wrong_value)
    before = {p.name: p.read_bytes() for p in repository.storage_dir.glob('*.json')}
    with pytest.raises(MvpMultiTuPersistenceError, match='component traceability does not match'):
        save(current_step=6, repository=repository)
    assert {p.name: p.read_bytes() for p in repository.storage_dir.glob('*.json')} == before


def test_assisted_accession_is_provenance_not_registry_authority(assisted_case):
    from services.mvp_multi_tu_persistence import _snapshot_payload

    _, result, reference = assisted_case
    before = copy.deepcopy(reference)
    snapshot = _snapshot_payload(result)
    actual = snapshot['expression_units'][0]['component_references']['promoter']
    assert actual == reference == before
    assert actual['accession_version'] == actual['registry_component_id'] == ''
    assert actual['source_type'] == 'USER_PROVIDED'
    resolution = actual['assisted_resolution']
    assert resolution['source_provenance']['accession'] == 'AF308778.1'
    assert resolution['confirmation_contract']['accession_verified'] is False
    assert resolution['confirmation_contract']['boundary_verified_by_software'] is False
    qualifiers = selection_qualifiers(actual)
    assert qualifiers['accession_version'] == qualifiers['source_accession'] == ['AF308778.1']
    assert qualifiers['component_id'] == qualifiers['source_type'] == qualifiers['sequence_authority'] == ['USER_PROVIDED']
