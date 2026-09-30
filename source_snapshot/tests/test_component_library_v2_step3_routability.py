from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.generate_component_library_v2_step3_routability import build_audit, synthetic_probe_sequence, app_probe_namespace
from services.agent_product_adapter import AgentProductAdapter
from services.component_library_v2_adoption import (
    V2AdoptionError, v2_canonical_record, v2_assisted_confirmation_contract,
    resolve_v2_user_sequence_for_project, validate_v2_project_resolution,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from core.i18n import translate


@pytest.fixture(scope="module")
def audit():
    return build_audit()


@pytest.fixture
def project(tmp_path):
    repo = PlantProjectDraftRepository(tmp_path / "projects")
    draft = repo.create_blank(project_name="Test-only V2 contract")
    repo.save(draft)
    return repo, draft.project_id


def resolve(cid, project, **kwargs):
    repo, pid = project
    row = v2_canonical_record(cid)
    return resolve_v2_user_sequence_for_project(row, kwargs.pop("sequence", synthetic_probe_sequence(row)), project_id=pid, repository=repo, user_sequence_source="TEST ONLY synthetic input, no biological evidence", explicit_user_confirmation=True, **kwargs)


def test_exact_matrix_and_identity_partition(audit):
    rows = audit["EXACT_STEP3_ROUTABILITY_MATRIX"]
    assert len(rows) == len({r["canonical_v2_id"] for r in rows}) == 171
    assert audit["CURRENT_PRODUCT_COUNTS"]["route_categories"] == {"DIRECT_NOW": 2, "RESOLVABLE_FOR_PROJECT": 24, "CANDIDATE_ONLY": 95, "EXCLUDED": 50}
    assert len(audit["DIRECT_USE_EXCLUSIONS"]) == 15
    assert audit["USER_SEQUENCE_ASSISTED_COUNTS"]["reviewed_coordinate_confirmation"] == 19
    assert audit["USER_SEQUENCE_ASSISTED_COUNTS"]["project_intent_only"] == 5


@pytest.mark.parametrize("workflow,assisted", [("SINGLE_GENE", 6), ("MULTI_TU", 24), ("PATHWAY", 24)])
def test_exact_workflow_admission(audit, workflow, assisted):
    counts = audit[f"{workflow}_STEP3_COUNTS"]
    assert counts["direct_ids"] == ["V2-CMP-138", "V2-CMP-144"]
    assert counts["resolvable_after_user_sequence"] == assisted
    assert counts["total_potentially_usable"] == 2 + assisted
    by_type = counts["by_component_type"]
    assert by_type["promoter"]["total_potentially_usable"] == (5 if assisted else 1)
    assert by_type["three_prime_regulatory_region"]["total_potentially_usable"] == 1
    assert by_type["terminator"]["total_potentially_usable"] == 0
    assert by_type["five_prime_utr"]["total_potentially_usable"] == (2 if assisted else 0)
    assert by_type["cds"]["total_potentially_usable"] == (0 if workflow == "SINGLE_GENE" else 18)
    assert counts["by_host"]["Solanum lycopersicum"]["direct_now"] == 2
    assert counts["by_host"]["Oryza sativa"]["direct_now"] == 0
    if workflow != "SINGLE_GENE":
        assert counts["by_host"]["Arabidopsis thaliana"]["direct_now"] == 1
        assert counts["by_host"]["Nicotiana benthamiana"]["direct_now"] == 0


def test_act7_displays_existing_boundary_and_enforces_length(project):
    row = v2_canonical_record("V2-CMP-004")
    c = v2_assisted_confirmation_contract(row)
    assert c["recorded_boundary"] == "1..1202 (+); regulatory: ACT7; promoter"
    assert c["expected_length"] == 1202
    with pytest.raises(V2AdoptionError, match="expected_length_match"):
        resolve(row["id"], project, sequence="ACGT", identity_and_boundaries_confirmed=True)
    with pytest.raises(V2AdoptionError, match="identity_and_boundaries_confirmed"):
        resolve(row["id"], project, project_intent_confirmed=True)
    result = resolve(row["id"], project, identity_and_boundaries_confirmed=True)
    assert result["checks"]["expected_length_match"]
    assert result["confirmation_contract"]["accession_verified"] is False


@pytest.mark.parametrize("cid", [f"V2-EXT-R2-{i:03d}" for i in range(13, 18)])
def test_unbounded_identity_requires_project_intent(cid, project):
    c = v2_assisted_confirmation_contract(v2_canonical_record(cid))
    assert c["has_reviewed_boundary"] is False
    assert c["expected_length"] is None
    assert c["recorded_boundary"] is None
    with pytest.raises(V2AdoptionError, match="project_intent_confirmed"):
        resolve(cid, project, identity_and_boundaries_confirmed=True)
    evidence = resolve(cid, project, project_intent_confirmed=True)
    assert "identity_and_boundaries_confirmed" not in evidence["checks"]
    assert evidence["confirmation_contract"]["sequence_authority"] == "USER_PROVIDED"
    assert evidence["confirmation_contract"]["boundary_verified_by_software"] is False
    assert validate_v2_project_resolution(evidence, project_id=project[1], sequence=evidence["normalized_sequence"], repository=project[0]) == evidence


def test_unreviewed_and_ambiguous_coordinates_never_create_a_boundary():
    row = v2_canonical_record("V2-CMP-004")
    row["v2_assisted_contract"]["independent_review_status"] = "PENDING"
    assert not v2_assisted_confirmation_contract(row)["has_reviewed_boundary"]
    row["v2_assisted_contract"]["independent_review_status"] = "USER_SEQUENCE_ASSISTED_CONFIRMED"
    row["v2_assisted_contract"]["recorded_boundary_context"] = "1..20 (+); segment | 30..45 (-); other"
    assert not v2_assisted_confirmation_contract(row)["has_reviewed_boundary"]


def test_confirmation_tampering_fails_closed(project):
    result = resolve("V2-EXT-R2-013", project, project_intent_confirmed=True)
    result["checks"]["project_intent_confirmed"] = False
    with pytest.raises(V2AdoptionError, match="project_intent_confirmed"):
        validate_v2_project_resolution(result, project_id=project[1], sequence=result["normalized_sequence"])


def test_reference_and_retired_cannot_bypass_resolution(project):
    agent = AgentProductAdapter()
    for cid in ("V2-CMP-003", "V2-CMP-126"):
        assert agent.lookup_components([cid])[0]["library_tier"] == "REFERENCE"
        with pytest.raises(ValueError, match="eligible shortlist"):
            agent.select_components([cid], workflow_type="single_gene", host="Solanum lycopersicum")
        with pytest.raises(ValueError, match="Only V2 USER_SEQUENCE_ASSISTED"):
            resolve(cid, project, sequence="ACGT", project_intent_confirmed=True, identity_and_boundaries_confirmed=True)
    from services.component_library_v2_adoption import build_v2_canonical_inventory
    retired = [r for r in build_v2_canonical_inventory() if r["library_tier"] == "RETIRED"]
    assert len(retired) == 35
    assert len(agent.lookup_components()) == 136
    assert agent.lookup_components([r["id"] for r in retired]) == []
    assert agent.component_repository.resolve(retired[0]["id"]) is not None  # historical lookup
    with pytest.raises(ValueError, match="Only V2 USER_SEQUENCE_ASSISTED"):
        resolve(retired[0]["id"], project, sequence="ACGT", project_intent_confirmed=True)


def test_existing_r1_snapshot_stays_user_provided_without_upgrade(project):
    evidence = resolve("V2-CMP-004", project, identity_and_boundaries_confirmed=True)
    evidence.pop("confirmation_contract")
    evidence["checks"].pop("expected_length_match")
    evidence["normalized_sequence"] = "AACCGGTT"
    evidence["sequence_length"] = 8
    evidence["sequence_sha256"] = hashlib.sha256(b"AACCGGTT").hexdigest()
    evidence.pop("resolution_id")
    evidence["resolution_id"] = hashlib.sha256(json.dumps(evidence, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    validated = validate_v2_project_resolution(evidence, project_id=project[1], sequence="AACCGGTT", repository=project[0])
    assert validated == evidence
    assert "confirmation_contract" not in validated
    from services.plant_component_workflow_registry import build_user_provided_selection
    reference = build_user_provided_selection(
        role="promoter", display_name="Historical ACT7", sequence="AACCGGTT",
        workflow_id="generic_multi_tu", assisted_resolution=validated,
    )
    component = {"display_name": "Historical ACT7", "raw_text": "AACCGGTT",
                 "source_type": "paste", "component_reference": reference}
    output, rendered = capture_step3_render(component, project[1])
    assert rendered["component_reference"] == reference
    assert (
        f"{translate('v1.results_final_report.accession_verified', language='en')}: "
        f"{translate('v1.component_library.v2_verification_not_recorded', language='en')}"
    ) in output
    assert (
        f"{translate('v1.results_final_report.boundary_verified_by_software', language='en')}: "
        f"{translate('v1.component_library.v2_verification_not_recorded', language='en')}"
    ) in output
    assert "Reviewed source boundary" not in "\n".join(output)
    forged = copy.deepcopy(evidence)
    forged["source_provenance"]["accession"] = "invented"
    with pytest.raises(ValueError, match="modified"):
        validate_v2_project_resolution(forged, project_id=project[1], sequence="AACCGGTT")


def test_step3_user_reference_uses_current_project_identity(project):
    from services.registry_catalog_ui import build_v2_user_provided_component
    row = v2_canonical_record("V2-EXT-R2-013")
    component = build_v2_user_provided_component(row, raw_sequence="ACGT", display_name=row["name"], project_id=project[1], project_repository=project[0], user_sequence_source="test only", project_intent_confirmed=True, explicit_user_confirmation=True)
    state = {"mvp_project_id": "different-project", "formal_transcription_units": [{"unit_id": "test-tu", "five_prime_region": component}]}
    ns = app_probe_namespace(state)
    ns["_prepare_multi_tu_editor_widget_state"]()
    result = ns["_render_dual_tu_element_input"](unit_id="test-tu", role="five_prime_region", label="5' UTR", options=[])
    assert result["component_reference"] == {}


def test_pathway_cds_route_requires_matching_existing_mapping(project):
    from services.gate3_pathway_mapping import new_pathway_step, update_pathway_step, validate_pathway_mapping
    from services.registry_catalog_ui import build_v2_user_provided_component
    row = v2_canonical_record("V2-CMP-129")
    component = build_v2_user_provided_component(row, raw_sequence=synthetic_probe_sequence(row), display_name=row["name"], project_id=project[1], project_repository=project[0], user_sequence_source="TEST ONLY synthetic pathway input", identity_and_boundaries_confirmed=True, explicit_user_confirmation=True)
    step = new_pathway_step(step_id="test-step")
    steps = update_pathway_step([step], "test-step", step_name="Test mapping", enzyme_name="User-recorded test name", enzyme_gene_name="Test CDS", cds_sequence=component["raw_text"], mapped_unit_id="test-tu")
    steps[0]["applied_to_unit"] = True
    state = {"mvp_project_id": project[1], "formal_project_type": "dual_tu", "formal_design_scenario": "metabolic_pathway_multi_tu_vector", "formal_transcription_units": [{"unit_id": "test-tu", "cds": {"raw_text": component["raw_text"]}}]}
    ns = app_probe_namespace(state)
    ns["_use_catalog_component_in_multi_tu"](component)
    assert validate_pathway_mapping(steps, state["formal_transcription_units"])["mapping_complete"]
    state["formal_transcription_units"][0]["cds"]["raw_text"] = "ATGGCCGCCTAA"
    blocked = validate_pathway_mapping(steps, state["formal_transcription_units"])
    assert not blocked["mapping_complete"]
    assert "applied_cds_hash_mismatch" in {r["rule_id"] for r in blocked["blocking_items"]}


def test_bilingual_evidence_aware_copy():
    from core.i18n import translate
    for language in ("en", "zh-CN"):
        assert "1202" in translate("v1.component_library.v2_expected_length", language=language, p0=1202)
        assert "USER_PROVIDED" in translate("v1.component_library.v2_user_authority_notice", language=language)
        assert "v1." not in translate("v1.component_library.v2_project_intent_confirmation", language=language)


def capture_step3_render(component, project_id, *, language="en", role="promoter", options=None):
    """Execute the real Step 3 renderer and capture visible copy, without a browser."""
    from core.i18n import translate
    from scripts.generate_component_library_v2_step3_routability import WidgetProbe

    class RenderProbe(WidgetProbe):
        def caption(self, value, **kwargs):
            output.append(str(value))

        markdown = caption

        def selectbox(self, label, choices, **kwargs):
            return choices[0] if choices else None

        def code(self, *args, **kwargs):
            pass

    output = []
    state = {
        "mvp_project_id": project_id,
        "formal_transcription_units": [{"unit_id": "render-tu", role: copy.deepcopy(component)}],
    }
    ns = app_probe_namespace(state)
    ns["st"] = RenderProbe(state)
    ns["_t"] = lambda key, **params: translate(key, language=language, **params)
    ns["_prepare_multi_tu_editor_widget_state"]()
    result = ns["_render_dual_tu_element_input"](
        unit_id="render-tu", role=role, label=role, options=options or [],
    )
    return output, result


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_step3_uses_analysis_asset_checksum_and_renders_assisted_evidence(project, monkeypatch, language):
    from core.i18n import translate
    from services.registry_catalog_ui import build_v2_user_provided_component
    from services import mvp_sequence_input

    row = v2_canonical_record("V2-CMP-004")
    component = build_v2_user_provided_component(
        row, raw_sequence=synthetic_probe_sequence(row), display_name=row["name"],
        project_id=project[1], project_repository=project[0],
        user_sequence_source="TEST ONLY ACT7 input.fa",
        identity_and_boundaries_confirmed=True, explicit_user_confirmation=True,
    )
    before = copy.deepcopy(component)
    analyze = mvp_sequence_input.analyze_dna_component_input

    def with_stale_top_level_hash(*args, **kwargs):
        record = analyze(*args, **kwargs)
        record["sequence_sha256"] = "stale-top-level-field-must-not-render"
        return record

    monkeypatch.setattr(mvp_sequence_input, "analyze_dna_component_input", with_stale_top_level_hash)
    output, result = capture_step3_render(component, project[1], language=language)
    text = "\n".join(output)
    resolution = component["component_reference"]["assisted_resolution"]
    assert f"**SHA-256**：`{hashlib.sha256(component['raw_text'].encode()).hexdigest()}`" in output
    assert "stale-top-level" not in text
    for expected in (
        "V2-CMP-004", "ACT7", "AF308778.1", "USER_SEQUENCE_ASSISTED",
        "USER_PROVIDED", "1,202 bp", "TEST ONLY ACT7 input.fa",
        "1..1202 (+); regulatory: ACT7; promoter", project[1], resolution["resolution_id"],
        f"{translate('v1.results_final_report.accession_verified', language=language)}: false",
        f"{translate('v1.results_final_report.boundary_verified_by_software', language=language)}: false",
    ):
        assert expected in text
    for label in (
        "v2_canonical_id_label", "v2_catalog_identity", "v2_source_accession",
        "v2_original_route", "v2_sequence_authority", "v2_sequence_length",
        "v2_user_sequence_source", "v2_project_binding", "v2_resolution_identity",
    ):
        key = "v1.component_library." + label
        localized = translate(key, language=language)
        assert localized != key and localized in text
    assert translate("v1.component_library.v2_user_authority_notice", language=language) in text
    assert result["component_reference"] == component["component_reference"]
    assert component == before  # rendering never rewrites the persisted snapshot


@pytest.mark.parametrize("language", ["en", "zh-CN"])
@pytest.mark.parametrize("role,part_type", [("promoter", "Promoter"), ("3_prime_regulatory_region", "Terminator")])
def test_step3_direct_use_rendering_retains_selection_and_checksum(language, role, part_type):
    ns = app_probe_namespace({})
    options = ns["_plant_element_options"](
        "Solanum lycopersicum", part_type, workflow_id="generic_multi_tu",
    )
    assert len(options) == 1
    option = options[0]
    component = {
        "source_type": "library", "raw_text": option["sequence"],
        "display_name": option["name"], "component_reference": option["component_reference"],
    }
    output, result = capture_step3_render(component, "direct-render-test", language=language, role=role, options=options)
    assert result["component_reference"] == option["component_reference"]
    assert result["raw_text"] == option["sequence"]
    assert result["source_type"] == "library"
    assert f"**SHA-256**：`{hashlib.sha256(option['sequence'].encode()).hexdigest()}`" in output
    assert "USER_SEQUENCE_ASSISTED" not in "\n".join(output)
    assert "accession_verified:" not in "\n".join(output)


def test_step3_project_intent_does_not_invent_reviewed_boundary(project):
    from services.registry_catalog_ui import build_v2_user_provided_component
    row = v2_canonical_record("V2-EXT-R2-013")
    component = build_v2_user_provided_component(
        row, raw_sequence="ACGT", display_name=row["name"], project_id=project[1],
        project_repository=project[0], user_sequence_source="TEST ONLY",
        project_intent_confirmed=True, explicit_user_confirmation=True,
    )
    output, result = capture_step3_render(component, project[1], role="five_prime_region")
    text = "\n".join(output)
    assert "Reviewed source boundary" not in text
    assert f"{translate('v1.results_final_report.boundary_verified_by_software', language='en')}: false" in text
    assert result["component_reference"]["source_type"] == "USER_PROVIDED"


def test_assisted_cold_process_preserves_exports_provenance_and_report(project, tmp_path):
    import subprocess
    import sys
    from services.registry_catalog_ui import build_v2_user_provided_component
    from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
    from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design

    row = v2_canonical_record("V2-CMP-004")
    promoter = build_v2_user_provided_component(row, raw_sequence=synthetic_probe_sequence(row), display_name=row["name"], project_id=project[1], project_repository=project[0], user_sequence_source="TEST ONLY synthetic ACT7 plumbing fixture; not accession DNA", identity_and_boundaries_confirmed=True, explicit_user_confirmation=True)
    def plain(name, sequence):
        return {"display_name": name, "raw_text": sequence, "source_type": "paste", "source_format": "plain", "source_name": "TEST ONLY"}
    result = generate_multi_tu_combined_construct(project_id=project[1], project_name="TEST ONLY cold reopen", expression_units=[{"unit_id": "closure-tu-1", "display_name": "Test TU", "order": 1, "orientation": "forward", "promoter": promoter, "cds": plain("Test CDS", "ATGGCCGCCTAA"), "3_prime_regulatory_region": plain("Test 3-prime", "TTTTACGT")}])
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {"current_step": 6, "design_scenario": "standard_plant_expression_vector"}
    saved = save_mvp_multi_tu_design(result, repository=project[0])
    expected = {"reference": promoter["component_reference"], "exports": result["exports"], "dna": result["combined_construct"]["dna"]}
    script = r'''
import json, sys
from io import StringIO
from Bio import SeqIO
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design
from services.formal_single_gene_final_review import build_final_review_report, render_formal_report_markdown
expected = json.load(sys.stdin)
r = open_mvp_multi_tu_design(sys.argv[2], repository=PlantProjectDraftRepository(sys.argv[1]))
ref = r['expression_units'][0]['component_references']['promoter']
assert ref == expected['reference']
assert ref['catalog_component_id'] == 'V2-CMP-004'
assert ref['assisted_resolution']['source_provenance']['accession'] == 'AF308778.1'
assert ref['assisted_resolution']['confirmation_contract']['accession_verified'] is False
from tests.test_component_library_v2_step3_routability import capture_step3_render
from core.i18n import translate
component = r['original_input']['expression_units'][0]['promoter']
for language in ('en', 'zh-CN'):
    output, rendered = capture_step3_render(component, sys.argv[2], language=language)
    text = '\n'.join(output)
    resolution = ref['assisted_resolution']
    for value in ('V2-CMP-004', 'ACT7', 'AF308778.1', 'USER_SEQUENCE_ASSISTED', 'USER_PROVIDED',
                  resolution['user_sequence_source'], resolution['sequence_sha256'],
                  resolution['project_id'], resolution['resolution_id'], '1,202 bp',
                  '1..1202 (+); regulatory: ACT7; promoter',
                  f"{translate('v1.results_final_report.accession_verified', language=language)}: false",
                  f"{translate('v1.results_final_report.boundary_verified_by_software', language=language)}: false"):
        assert value in text, (language, value, text)
    assert rendered['component_reference'] == ref
    assert translate('v1.component_library.v2_user_authority_notice', language=language) in text
assert r['exports'] == expected['exports']
fasta = next(SeqIO.parse(StringIO(r['exports']['combined_construct_fasta']['data']), 'fasta'))
gb = next(SeqIO.parse(StringIO(r['exports']['combined_construct_genbank']['data']), 'genbank'))
assert str(fasta.seq).upper() == str(gb.seq).upper() == expected['dna']
feature = next(f for f in gb.features if f.qualifiers.get('catalog_component_id') == ['V2-CMP-004'])
assert feature.qualifiers['admission_mode'] == ['USER_SEQUENCE_ASSISTED']
report = build_final_review_report(r)
markdown = render_formal_report_markdown(report).decode('utf-8')
assert 'ACT7' in markdown
print(json.dumps({'canonical_exports_equal': True, 'provenance_equal': True, 'report_generated': True, 'report_contains_assisted_name': True, 'report_bytes': len(markdown)}))
'''
    cold = subprocess.run([sys.executable, "-c", script, str(project[0].storage_dir), saved.project_id], input=json.dumps(expected), text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert cold.returncode == 0, cold.stdout + cold.stderr
    outcome = json.loads(cold.stdout.strip().splitlines()[-1])
    assert outcome["canonical_exports_equal"] and outcome["provenance_equal"] and outcome["report_generated"]
