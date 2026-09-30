from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from Bio import SeqIO

import mvp_app
from services.canonical_construct_runtime import active_complete_plasmid_snapshot
from services.formal_cds_workflow import analyze_formal_cds, gene_information_from_values
from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
from services.formal_project_definition_lifecycle import construct_review_basis, normalize_project_definition
from services.formal_single_gene_runtime import construct_input_signature, generate_admitted_complete_vector
from services.mvp_sequence_input import analyze_dna_component_input
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.rice_hsa_ncbi_mvp10_case import build_rice_hsa_real_case


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "HA01-SingleGene-GFP-20260903"
CDS_SEQUENCE = "ATGGCTGACAAAGTTCCAGGTTACGAGTCTTAA"
PROMOTER_SEQUENCE = "GGTTAACC"
TERMINATOR_SEQUENCE = "CCGGTTAA"
STEP1_WIDGET_KEYS = (
    "formal_step1_application_mode",
    "formal_step1_compatibility_review_required",
    "formal_step1_host",
    "formal_step1_inducibility_requirement",
    "formal_step1_induction_notes",
    "formal_step1_legacy_application_mode",
    "formal_step1_legacy_expression_mode",
    "formal_step1_localization_target",
    "formal_step1_material",
    "formal_step1_project_name",
    "formal_step1_tissue_specificity_requirement",
    "formal_step1_tissue_target",
    "formal_step1_transient_expression_system",
)


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _definition() -> dict[str, str]:
    return normalize_project_definition(
        {
            "project_name": PROJECT_NAME,
            "plant_host": "Rice (O. sativa)",
            "material": "Nipponbare",
            "application_mode": "稳定遗传转化",
            "transient_expression_system": "尚未确定",
            "tissue_specificity_requirement": "无特定组织或器官限制",
            "tissue_target": "",
            "inducibility_requirement": "无特定诱导要求",
            "induction_notes": "",
            "localization_target": "",
        }
    )


def _ha01_result(*, project_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    definition = _definition()
    cds_input = analyze_formal_cds(
        CDS_SEQUENCE,
        source_kind="paste",
        gene_information=gene_information_from_values(
            gene_name="HA01_TEST_CDS",
            source_type="用户自有序列",
            modification_status="未修改的来源序列",
        ),
    )
    rice_case = build_rice_hsa_real_case()
    records = {
        "promoter": analyze_dna_component_input(
            PROMOTER_SEQUENCE,
            project_id=project_id,
            component_type="promoter",
            display_name="HA01_PROMOTER",
            source_kind="user_recorded",
            source_name="用户提供，待确认",
        ),
        "cds": mvp_app._cds_record(cds_input, display_name="HA01_TEST_CDS"),
        "terminator": analyze_dna_component_input(
            TERMINATOR_SEQUENCE,
            project_id=project_id,
            component_type="terminator",
            display_name="HA01_TERMINATOR",
            source_kind="user_recorded",
            source_name="用户提供，待确认",
        ),
        "backbone": deepcopy(rice_case["input_records"]["backbone"]),
    }
    declared = [
        {
            "biological_role": role,
            "display_name": records[key]["display_name"],
            "sequence": records[key]["normalized_sequence"],
            "source_kind": records[key]["source_kind"],
            "source_reference": records[key].get("source_reference") or "",
            "source_file": records[key].get("source_name") or "",
            "user_edited": False,
        }
        for key, role in (
            ("promoter", "promoter"),
            ("cds", "cds"),
            ("terminator", "three_prime_regulatory_region"),
        )
    ]
    assessment = assess_expression_cassette(
        declared,
        cds_sequence=CDS_SEQUENCE,
        cds_signature=cds_input["normalized_cds_sha256"],
        project_definition=definition,
        order_confirmed=True,
    )
    assert assessment["blocking"] is False
    formal_cassette = generate_expression_cassette(assessment, project_id=project_id)
    settings = deepcopy(rice_case["insertion_settings"])
    cassette_signature = formal_cassette["input_signature"]
    result = generate_admitted_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=PROJECT_NAME,
        input_signature=construct_input_signature(
            records,
            settings,
            cassette_signature=cassette_signature,
        ),
        cassette_runtime=formal_cassette["runtime"],
        cassette_signature=cassette_signature,
        workflow_id=settings["workflow_id"],
    )
    result["formal_expression_cassette"] = {
        key: value
        for key, value in formal_cassette.items()
        if key not in {"runtime", "cassette"}
    }
    result["formal_project_context"] = {
        "host_key": definition["plant_host"],
        "expression_target": "；".join(
            (
                definition["application_mode"],
                definition["tissue_specificity_requirement"],
                definition["inducibility_requirement"],
            )
        ),
        "project_definition": deepcopy(definition),
        "construct_review_basis": construct_review_basis(definition),
        "construct_review_status": "current",
        "cds_source_review_status": "current",
        "current_step": 6,
    }
    return result, formal_cassette, definition


def _completed_state(
    result: dict[str, Any], formal_cassette: dict[str, Any], definition: dict[str, str]
) -> dict[str, Any]:
    state = {
        "formal_project_definition": deepcopy(definition),
        "formal_project_name": definition["project_name"],
        "formal_project_host": definition["plant_host"],
        "formal_project_material": definition["material"],
        "formal_cds_input": deepcopy(result["cds_input"]),
        "formal_expression_cassette": deepcopy(formal_cassette),
        "formal_cassette_result": {
            "runtime": deepcopy(formal_cassette["runtime"]),
            "cassette_input_signature": formal_cassette["input_signature"],
            "input_signature": formal_cassette["input_signature"],
        },
        "formal_cassette_input_signature": formal_cassette["input_signature"],
        "formal_step3_order_confirmation_recorded": True,
        "formal_backbone_record": deepcopy(result["input_records"]["backbone"]),
        "formal_insertion_settings": deepcopy(result["insertion_settings"]),
        "formal_step4_strategy_confirmed": True,
        "formal_step5_strategy_confirmed": True,
        "formal_construct_review_status": "current",
        "formal_cds_source_review_status": "current",
        "mvp_current_input_signature": result["input_signature"],
        "mvp_inputs_stale": False,
    }
    state.update(
        {
            "formal_step1_project_name": definition["project_name"],
            "formal_step1_host": definition["plant_host"],
            "formal_step1_material": definition["material"],
            "formal_step1_application_mode": definition["application_mode"],
            "formal_step1_transient_expression_system": definition[
                "transient_expression_system"
            ],
            "formal_step1_tissue_specificity_requirement": definition[
                "tissue_specificity_requirement"
            ],
            "formal_step1_tissue_target": definition["tissue_target"],
            "formal_step1_inducibility_requirement": definition[
                "inducibility_requirement"
            ],
            "formal_step1_induction_notes": definition["induction_notes"],
            "formal_step1_localization_target": definition["localization_target"],
            "formal_step1_compatibility_review_required": definition[
                "compatibility_review_required"
            ],
            "formal_step1_legacy_application_mode": definition[
                "legacy_application_mode"
            ],
            "formal_step1_legacy_expression_mode": definition[
                "legacy_expression_mode"
            ],
        }
    )
    return state


def _bind_after_navigation(*, navigation: str, project_id: str) -> dict[str, Any]:
    result, formal_cassette, definition = _ha01_result(project_id=project_id)
    state = _completed_state(result, formal_cassette, definition)
    if navigation:
        for key in STEP1_WIDGET_KEYS:
            state.pop(key, None)
    streamlit = SimpleNamespace(session_state=state)
    functions = _app_functions(
        "_formal_project_definition",
        "_is_formal_action_widget_key",
        "_formal_state_snapshot",
        "_bind_completed_formal_state",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "json": json,
            "re": __import__("re"),
            "st": streamlit,
            "_refresh_formal_strategy_confirmation_state": lambda _result: (True, True),
        },
    )
    bound = functions["_bind_completed_formal_state"](result)
    context = bound["formal_project_context"]
    assert functions["_formal_project_definition"]() == definition
    assert context["project_definition"] == definition
    assert context["formal_state"]["formal_project_definition"] == definition
    return bound


def test_ha01_step1_widgets_rehydrate_after_streamlit_page_cleanup() -> None:
    definition = _definition()
    state: dict[str, Any] = {"formal_project_definition": deepcopy(definition)}
    streamlit = SimpleNamespace(session_state=state)
    hydrate = _app_functions(
        "_hydrate_formal_step1_widgets",
        namespace={"st": streamlit},
    )["_hydrate_formal_step1_widgets"]

    hydrate()

    assert {key: state[key] for key in STEP1_WIDGET_KEYS} == {
        "formal_step1_project_name": definition["project_name"],
        "formal_step1_host": definition["plant_host"],
        "formal_step1_material": definition["material"],
        "formal_step1_application_mode": definition["application_mode"],
        "formal_step1_transient_expression_system": definition[
            "transient_expression_system"
        ],
        "formal_step1_tissue_specificity_requirement": definition[
            "tissue_specificity_requirement"
        ],
        "formal_step1_tissue_target": definition["tissue_target"],
        "formal_step1_inducibility_requirement": definition[
            "inducibility_requirement"
        ],
        "formal_step1_induction_notes": definition["induction_notes"],
        "formal_step1_localization_target": definition["localization_target"],
        "formal_step1_compatibility_review_required": definition[
            "compatibility_review_required"
        ],
        "formal_step1_legacy_application_mode": definition[
            "legacy_application_mode"
        ],
        "formal_step1_legacy_expression_mode": definition[
            "legacy_expression_mode"
        ],
    }


@pytest.mark.parametrize(
    "navigation",
    ["", "step6-step1-step6", "step6-step2-step6"],
    ids=["straight-through", "step6-step1-step6", "step6-step2-step6"],
)
def test_ha01_completed_save_and_cold_reopen_preserve_canonical_state(
    tmp_path: Path, navigation: str
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "records")
    result = _bind_after_navigation(
        navigation=navigation,
        project_id=f"ha01-{navigation or 'straight'}",
    )

    saved = save_mvp_single_gene_design(result, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    definition = reopened["formal_project_context"]["project_definition"]
    formal_state = reopened["formal_project_context"]["formal_state"]
    plasmid = active_complete_plasmid_snapshot(reopened["runtime"])
    fasta = SeqIO.read(StringIO(reopened["exports"]["fasta"]["data"]), "fasta")
    genbank = SeqIO.read(StringIO(reopened["exports"]["genbank"]["data"]), "genbank")
    assert reopened["formal_editor_restore_reason"] == ""
    assert definition == _definition()
    assert formal_state["formal_project_definition"] == definition
    assert formal_state["formal_cds_input"]["gene_information"]["gene_name"] == "HA01_TEST_CDS"
    assert [
        component["display_name"]
        for component in formal_state["formal_expression_cassette"]["components"]
    ] == ["HA01_PROMOTER", "HA01_TEST_CDS", "HA01_TERMINATOR"]
    assert formal_state["formal_backbone_record"]["length"] == 8958
    assert reopened["cassette_length"] == 49
    assert reopened["plasmid_length"] == 9007
    assert reopened["validation_summary"] == {
        "blocking_count": 0,
        "warning_count": 0,
        "info_count": 0,
    }
    assert str(plasmid["sequence"]).upper() == str(fasta.seq).upper() == str(genbank.seq).upper()


@pytest.mark.parametrize("mutation", ["missing", "stale", "forged-definition"])
def test_ha01_incomplete_or_stale_completed_state_still_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    result = _bind_after_navigation(
        navigation="step6-step1-step6", project_id=f"ha01-{mutation}"
    )
    state = result["formal_project_context"]["formal_state"]
    if mutation == "missing":
        state.pop("formal_backbone_record")
        expected = "missing_formal_state"
    elif mutation == "stale":
        state["formal_backbone_record"]["normalized_sequence"] = "A"
        expected = "state_canonical_mismatch"
    else:
        result["formal_project_context"]["project_definition"][
            "application_mode"
        ] = "尚未确定"
        expected = "state_canonical_mismatch"

    with pytest.raises(MvpSingleGenePersistenceError, match=expected):
        save_mvp_single_gene_design(
            result,
            repository=PlantProjectDraftRepository(tmp_path / "records"),
        )


def test_ha01_fixture_identity_is_exact() -> None:
    result, _formal_cassette, _definition_record = _ha01_result(project_id="ha01-identity")

    assert hashlib.sha256(CDS_SEQUENCE.encode("ascii")).hexdigest() == result["cds_input"][
        "normalized_cds_sha256"
    ]
    assert result["input_records"]["promoter"]["normalized_sequence"] == PROMOTER_SEQUENCE
    assert result["input_records"]["terminator"]["normalized_sequence"] == TERMINATOR_SEQUENCE
    assert result["input_records"]["backbone"]["source_accession_version"] == "AF234296.1"
    assert result["input_lengths"] == {
        "promoter": 8,
        "cds": 33,
        "terminator": 8,
        "backbone": 8958,
    }
    assert result["cassette_length"] == 49
    assert result["plasmid_length"] == 9007
