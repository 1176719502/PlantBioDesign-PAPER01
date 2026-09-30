import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from services.agent_contracts import AgentRequest
from services.agent_product_adapter import AgentProductAdapter
from services.agent_service import AgentService
from services.formal_expression_cassette import (
    assess_expression_cassette,
    generate_expression_cassette as generate_formal_cassette,
)
from services.formal_single_gene_runtime import (
    generate_expression_cassette,
    generate_complete_vector,
    load_real_case,
)
from services.formal_step3_component_authority import (
    formal_agent_component_admission,
    formal_step3_authority_findings,
    formal_step3_component_options,
    revalidated_formal_step3_selection,
)
from services.mvp_single_gene_persistence import (
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.mvp_sequence_input import (
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
)
from services.mvp_cds_input import analyze_cds_input
from services.plant_component_workflow_registry import build_registry_selection
from services.plant_host_registry import (
    GENERIC_MULTI_TU_ASSEMBLY,
    SINGLE_GENE_COMPLETE_VECTOR,
    hosts_for_workflow,
    list_hosts,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]
TOMATO = "Solanum lycopersicum"
E8 = "PCLV1-PRO-E8-2164"
HSP = "PCLV1-TER-HSP18-2-250"


def _production_tomato_inputs(project_id: str) -> tuple[dict, dict]:
    case = load_real_case()
    cds_input = analyze_cds_input(
        "ATGGCCGCCTAA",
        source_kind="paste",
        source_name="user-provided CDS",
    )
    e8 = build_registry_selection(E8, role="promoter", requested_host=TOMATO)
    hsp = build_registry_selection(
        HSP, role="3_prime_regulatory_region", requested_host=TOMATO
    )
    records = {
        "promoter": analyze_dna_component_input(
            e8["selected_sequence"],
            project_id=project_id,
            component_type="promoter",
            display_name=e8["display_name"],
            source_kind="library",
            source_name=e8["accession_version"],
        ),
        "cds": {
            "role": "cds",
            "source_kind": str(cds_input["source_kind"]),
            "source_name": str(cds_input["source_name"]),
            "source_format": str(cds_input["source_format"]),
            "display_name": "User CDS",
            "original_text": str(cds_input["original_text"]),
            "normalized_sequence": str(cds_input["normalized_cds"]),
            "length": int(cds_input["normalized_length"]),
        },
        "terminator": analyze_dna_component_input(
            hsp["selected_sequence"],
            project_id=project_id,
            component_type="terminator",
            display_name=hsp["display_name"],
            source_kind="library",
            source_name=hsp["accession_version"],
        ),
        "backbone": analyze_genbank_backbone_input(
            case["backbone"],
            project_id=project_id,
            display_name="BACKBONE_SYNTH_R229",
            source_kind="example",
            source_name="r229_backbone.gb",
        ),
    }
    records["promoter"]["component_reference"] = e8
    records["terminator"]["component_reference"] = hsp
    return cds_input, records


def _production_tomato_result(project_id: str = "tomato-single-gene-r1") -> dict:
    cds_input, records = _production_tomato_inputs(project_id)
    cassette = generate_expression_cassette(
        cds_input=cds_input,
        input_records=records,
        project_id=project_id,
        project_name="Tomato single-gene eligibility R1",
    )
    formal_components = [
        {
            "biological_role": "promoter",
            "display_name": records["promoter"]["display_name"],
            "sequence": records["promoter"]["normalized_sequence"],
            "source_kind": "library",
            "source_reference": records["promoter"]["source_name"],
            "user_edited": False,
        },
        {
            "biological_role": "cds",
            "display_name": records["cds"]["display_name"],
            "sequence": records["cds"]["normalized_sequence"],
            "source_kind": records["cds"]["source_kind"],
            "source_reference": records["cds"]["source_name"],
            "user_edited": False,
        },
        {
            "biological_role": "three_prime_regulatory_region",
            "display_name": records["terminator"]["display_name"],
            "sequence": records["terminator"]["normalized_sequence"],
            "source_kind": "library",
            "source_reference": records["terminator"]["source_name"],
            "user_edited": False,
        },
    ]
    assessment = assess_expression_cassette(
        formal_components,
        cds_sequence=str(cds_input["normalized_cds"]),
        cds_signature=hashlib.sha256(
            str(cds_input["normalized_cds"]).encode("ascii")
        ).hexdigest(),
        order_confirmed=True,
    )
    assert not assessment["blocking"]
    formal_cassette = generate_formal_cassette(assessment, project_id=project_id)
    result = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        cassette_runtime=cassette["runtime"],
        cassette_signature=cassette["input_signature"],
        project_id=project_id,
        project_name="Tomato single-gene eligibility R1",
    )
    result["formal_expression_cassette"] = formal_cassette
    result["formal_project_context"] = {
        "host_key": TOMATO,
        "current_step": 6,
        "construct_review_status": "current",
        "cds_source_review_status": "current",
    }
    return result


def test_tomato_is_the_only_new_complete_vector_host() -> None:
    assert [record["host_id"] for record in hosts_for_workflow(SINGLE_GENE_COMPLETE_VECTOR)] == [
        "rice",
        "tomato",
    ]
    tomato = next(record for record in list_hosts() if record["host_id"] == "tomato")
    assert tomato["workflow_levels"] == [
        SINGLE_GENE_COMPLETE_VECTOR,
        GENERIC_MULTI_TU_ASSEMBLY,
    ]
    assert tomato["workflow_contracts"][SINGLE_GENE_COMPLETE_VECTOR] == {
        "contains_vector": True
    }


def test_tomato_step3_and_agent_admission_stay_authority_bound() -> None:
    promoter = formal_step3_component_options(
        role="promoter", target_host_species=TOMATO
    )
    three_prime = formal_step3_component_options(
        role="3_prime_regulatory_region", target_host_species=TOMATO
    )
    assert [row["registry_component_id"] for row in promoter] == [E8]
    assert [row["registry_component_id"] for row in three_prime] == [HSP]
    assert formal_step3_authority_findings(
        promoter_options=promoter,
        three_prime_options=three_prime,
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=promoter[0],
        selected_three_prime=three_prime[0],
    ) == []

    admission = formal_agent_component_admission(
        workflow_type="single_gene", target_host_species=TOMATO
    )
    assert {
        role["role"]: {option["registry_component_id"] for option in role["options"]}
        for role in admission["roles"]
    } == {"promoter": {E8}, "3_prime_regulatory_region": {HSP}}
    adapter = AgentProductAdapter()
    references = adapter.resolve_component_references(
        [E8, HSP], workflow_type="single_gene", host=TOMATO
    )
    needs = AgentService(object(), component_repository=adapter.component_repository).inspect_request(
        AgentRequest(
            workflow_type="single_gene",
            host=TOMATO,
            user_intent="review a tomato single-gene record",
            cds_or_reference_input="ATGGCCGCCTAA",
            component_references=references,
        )
    )
    assert needs == ()


@pytest.mark.parametrize(
    "host",
    [
        "Arabidopsis thaliana",
        "Oryza sativa",
        "Nicotiana benthamiana",
        "Zea mays",
        "Glycine max",
    ],
)
def test_non_tomato_hosts_have_no_complete_formal_agent_pair(host: str) -> None:
    admission = formal_agent_component_admission(
        workflow_type="single_gene", target_host_species=host
    )
    by_role = {
        role["role"]: tuple(role["options"])
        for role in admission["roles"]
    }
    assert not by_role["promoter"] or not by_role["3_prime_regulatory_region"]


def test_tomato_negative_component_paths_fail_closed() -> None:
    promoter_options = formal_step3_component_options(
        role="promoter", target_host_species=TOMATO
    )
    three_prime_options = formal_step3_component_options(
        role="3_prime_regulatory_region", target_host_species=TOMATO
    )
    missing_promoter = formal_step3_authority_findings(
        promoter_options=promoter_options,
        three_prime_options=three_prime_options,
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=None,
        selected_three_prime=three_prime_options[0],
    )
    missing_three_prime = formal_step3_authority_findings(
        promoter_options=promoter_options,
        three_prime_options=three_prime_options,
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=promoter_options[0],
        selected_three_prime=None,
    )
    assert any(item["status"] == "阻断" for item in missing_promoter)
    assert any(item["status"] == "阻断" for item in missing_three_prime)

    with pytest.raises(ValueError, match="requested host"):
        build_registry_selection(E8, role="promoter", requested_host="Arabidopsis thaliana")

    adapter = AgentProductAdapter()
    inventory = adapter.lookup_components(query="")
    for mode in {"REFERENCE_ONLY", "USER_SEQUENCE_ASSISTED"}:
        candidate = next(
            row for row in inventory if row.get("admission_mode") == mode
        )
        with pytest.raises(ValueError, match="eligible shortlist"):
            adapter.select_components(
                [str(candidate["canonical_v2_component_id"])],
                workflow_type="single_gene",
                host=TOMATO,
            )


def test_tomato_single_gene_save_and_fresh_process_reopen(tmp_path: Path) -> None:
    result = _production_tomato_result()
    canonical_hashes = {
        "plasmid": result["plasmid_sha256"],
        "fasta": result["fasta_sequence_sha256"],
        "genbank": result["genbank_sequence_sha256"],
    }
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_single_gene_design(result, repository=repository)
    assert "agent_adoption" not in saved.manual_review_state
    assert "adoption_receipt" not in saved.manual_review_state
    reopened = open_mvp_single_gene_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    assert reopened["project_type"] == "single_gene"
    assert reopened["formal_project_context"]["host_key"] == TOMATO
    assert {
        "plasmid": reopened["plasmid_sha256"],
        "fasta": reopened["fasta_sequence_sha256"],
        "genbank": reopened["genbank_sequence_sha256"],
    } == canonical_hashes
    assert "agent_adoption" not in reopened
    assert "adoption_receipt" not in reopened
    assert reopened["input_records"]["promoter"]["component_reference"]["registry_component_id"] == E8
    assert reopened["input_records"]["terminator"]["component_reference"]["registry_component_id"] == HSP
    assert reopened["input_records"]["cds"]["normalized_sequence"] == result["input_records"]["cds"]["normalized_sequence"]
    assert reopened["exports"]["fasta"]["data"]
    assert reopened["exports"]["genbank"]["data"]
    assert revalidated_formal_step3_selection(
        reopened["input_records"]["promoter"],
        role="promoter",
        target_host_species=TOMATO,
        options=formal_step3_component_options(
            role="promoter", target_host_species=TOMATO
        ),
    ) is not None
    assert revalidated_formal_step3_selection(
        reopened["input_records"]["terminator"],
        role="terminator",
        target_host_species=TOMATO,
        options=formal_step3_component_options(
            role="3_prime_regulatory_region", target_host_species=TOMATO
        ),
    ) is not None

    code = """
import json
import sys
from pathlib import Path
from services.mvp_single_gene_persistence import open_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.agent_contracts import AgentRequest
from services.agent_product_adapter import AgentProductAdapter
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider
from services.agent_service import AgentService
record = open_mvp_single_gene_design(sys.argv[2], repository=PlantProjectDraftRepository(Path(sys.argv[1])))
adapter = AgentProductAdapter()
references = adapter.resolve_component_references(
    ['PCLV1-PRO-E8-2164', 'PCLV1-TER-HSP18-2-250'],
    workflow_type='single_gene',
    host='Solanum lycopersicum',
)
transport = FakeQwenTransport()
needs = AgentService(
    QwenProvider(config=QwenConfig(model='fresh-process-test'), transport=transport),
    component_repository=adapter.component_repository,
).inspect_request(AgentRequest(
    workflow_type='single_gene',
    host='Solanum lycopersicum',
    user_intent='Review a tomato single-gene design record.',
    cds_or_reference_input='ATGGCCGCCTAA',
    component_references=references,
))
print(json.dumps({
    'project_type': record['project_type'],
    'host': record['formal_project_context']['host_key'],
    'promoter': record['input_records']['promoter']['component_reference']['registry_component_id'],
    'three_prime': record['input_records']['terminator']['component_reference']['registry_component_id'],
    'plasmid_sha256': record['plasmid_sha256'],
    'fasta_sequence_sha256': record['fasta_sequence_sha256'],
    'genbank_sequence_sha256': record['genbank_sequence_sha256'],
    'agent_needs': [item.code.value for item in needs],
    'provider_calls': len(transport.calls),
    'silent_adoption_markers': [key for key in ('agent_adoption', 'adoption_receipt') if key in record],
}, ensure_ascii=False))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), env.get("PYTHONPATH", "")))
    completed = subprocess.run(
        [sys.executable, "-c", code, str(repository.storage_dir), saved.project_id],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == {
        "project_type": "single_gene",
        "host": TOMATO,
        "promoter": E8,
        "three_prime": HSP,
        "plasmid_sha256": canonical_hashes["plasmid"],
        "fasta_sequence_sha256": canonical_hashes["fasta"],
        "genbank_sequence_sha256": canonical_hashes["genbank"],
        "agent_needs": [],
        "provider_calls": 0,
        "silent_adoption_markers": [],
    }
