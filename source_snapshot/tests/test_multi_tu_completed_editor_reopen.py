from __future__ import annotations

import ast
import copy
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.mvp_multi_tu_persistence import (
    ASSEMBLY_NO_VECTOR_STATUS,
    MVP_MULTI_TU_PERSISTENCE_KEY,
    MvpMultiTuPersistenceError,
    linear_multi_tu_completed_editor_vector_state,
    multi_tu_formal_editor_restore_reason,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDENTITIES = {
    2: "44bbe5e33d5493086c878d78ae9bead45f5c397ddee1a67988e19d362a38cc82",
    3: "f6378751d8516a35bd5f7582a37905594dcc24923088d29ff72218b37aa1986f",
}
UNIT_INPUTS = (
    {
        "unit_id": "TU1",
        "display_name": "Selection-marker",
        "orientation": "forward",
        "order": 1,
        "promoter": {"display_name": "PROMOTER_BETA", "raw_text": "GGTTAACC"},
        "five_prime_region": {"display_name": "FIVE_PRIME_BETA", "raw_text": "GCTA"},
        "cds": {"display_name": "CDS_BETA", "raw_text": "ATGAAACCCGGGTAG"},
        "3_prime_regulatory_region": {
            "display_name": "THREE_PRIME_BETA",
            "raw_text": "CCGGTTAA",
        },
    },
    {
        "unit_id": "TU2",
        "display_name": "target",
        "orientation": "reverse",
        "order": 2,
        "promoter": {"display_name": "PROMOTER_ALPHA", "raw_text": "AACCGGTT"},
        "five_prime_region": {"display_name": "FIVE_PRIME_ALPHA", "raw_text": "ATGC"},
        "cds": {"display_name": "CDS_ALPHA", "raw_text": "ATGGCTGCTTAA"},
        "3_prime_regulatory_region": {
            "display_name": "THREE_PRIME_ALPHA",
            "raw_text": "TTGCAACC",
        },
    },
    {
        "unit_id": "TU3",
        "display_name": "reporter",
        "orientation": "forward",
        "order": 3,
        "promoter": {"display_name": "REPORTER_PROMOTER", "raw_text": "TTGCAACC"},
        "five_prime_region": {"display_name": "REPORTER_FIVE_PRIME", "raw_text": "AGTC"},
        "cds": {"display_name": "REPORTER_CDS", "raw_text": "ATGGTGAAATAA"},
        "3_prime_regulatory_region": {
            "display_name": "REPORTER_3PRIME",
            "raw_text": "GCGTAT",
        },
    },
)


def _initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE project_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "project_name TEXT, version INTEGER, chassis TEXT, design_data TEXT, "
            "created_at TEXT, creator TEXT, status TEXT)"
        )


def _result(unit_count: int) -> dict[str, Any]:
    result = generate_multi_tu_combined_construct(
        project_id=f"completed-editor-{unit_count}-tu",
        project_name=f"Completed editor {unit_count} TU",
        expression_units=copy.deepcopy(list(UNIT_INPUTS[:unit_count])),
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "host_key": "Tobacco / Nicotiana benthamiana",
        "design_scenario": "standard_plant_expression_vector",
        "current_step": 6,
    }
    return result


def _bind_completed_state(result: dict[str, Any]) -> dict[str, Any]:
    definition = {
        "project_name": result["project_name"],
        "plant_host": "Tobacco / Nicotiana benthamiana",
    }
    state = {
        "formal_project_type": "dual_tu",
        "formal_design_scenario": "standard_plant_expression_vector",
        "formal_project_definition": copy.deepcopy(definition),
        "formal_transcription_units": copy.deepcopy(
            result["original_input"]["expression_units"]
        ),
        "formal_dual_tu_combined_result": copy.deepcopy(result),
        "mvp_project_id": result["project_id"],
        "mvp_current_input_signature": result["input_signature"],
        "mvp_inputs_stale": False,
    }
    for index, unit in enumerate(state["formal_transcription_units"], start=1):
        unit["unit_id"] = f"planning-unit-{index}"
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    node = next(
        item
        for item in ast.parse(source).body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_bind_completed_formal_state"
    )
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "json": json,
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "_is_multi_tu_expression_assembly": lambda value: (
            value.get("result_kind") == "MULTI_TU_EXPRESSION_ASSEMBLY"
        ),
        "_refresh_formal_strategy_confirmation_state": lambda _result: None,
        "_formal_state_snapshot": lambda: copy.deepcopy(state),
        "_formal_project_definition": lambda: copy.deepcopy(definition),
        "_multi_tu_step2_planning_signature": lambda units: "canonical-plan-signature",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_bind_completed_formal_state"](result)


@pytest.mark.parametrize("unit_count", [2, 3])
def test_completed_linear_multi_tu_binds_truthful_editor_state_and_reopens(
    tmp_path: Path, unit_count: int
) -> None:
    result = _bind_completed_state(_result(unit_count))
    context = result["formal_project_context"]
    formal_state = context["formal_state"]
    backbone, insertion = linear_multi_tu_completed_editor_vector_state(result)

    assert context["project_type"] == "dual_tu"
    assert backbone["status"] == ASSEMBLY_NO_VECTOR_STATUS
    assert backbone["record_kind"] == "no_backbone"
    assert insertion["record_kind"] == "no_insertion"
    assert insertion["mode"] == "not_applicable"
    assert insertion["start_coordinate"] is None
    assert insertion["end_coordinate"] is None
    assert formal_state["formal_backbone_record"] == backbone
    assert formal_state["formal_insertion_settings"] == insertion
    assert result["original_input"]["backbone"] == backbone
    assert result["original_input"]["insertion_settings"] == insertion
    assert [
        unit["unit_id"] for unit in formal_state["formal_transcription_units"]
    ] == [
        unit["unit_id"] for unit in result["original_input"]["expression_units"]
    ]
    assert formal_state["formal_multi_tu_step2_planning_signature"] == (
        "canonical-plan-signature"
    )

    repository = PlantProjectDraftRepository(tmp_path / "json-records")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert reopened["formal_editor_restore_reason"] == ""
    assert reopened["formal_editor_restoration_eligible"] is True
    assert reopened["contains_vector"] is False
    assert reopened["topology"] == "linear"
    canonical = reopened["combined_construct"]
    assert canonical["total_length"] == (67 if unit_count == 2 else 97)
    assert hashlib.sha256(canonical["dna"].encode("ascii")).hexdigest() == (
        EXPECTED_IDENTITIES[unit_count]
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing-project-type", "unsupported_project_type"),
        ("unsupported-project-type", "unsupported_project_type"),
        ("missing-mapping", "missing_formal_state"),
        ("forged-backbone", "state_canonical_mismatch"),
        ("inconsistent-insertion", "state_canonical_mismatch"),
        ("circular-topology", "state_canonical_mismatch"),
    ],
)
def test_invalid_completed_multi_tu_state_fails_closed(
    mutation: str, expected: str
) -> None:
    result = _bind_completed_state(_result(2))
    context = result["formal_project_context"]
    state = context["formal_state"]
    if mutation == "missing-project-type":
        context.pop("project_type")
    elif mutation == "unsupported-project-type":
        context["project_type"] = "single_gene"
    elif mutation == "missing-mapping":
        state.pop("formal_backbone_record")
    elif mutation == "forged-backbone":
        state["formal_backbone_record"]["record_kind"] = "fabricated_backbone"
    elif mutation == "inconsistent-insertion":
        state["formal_insertion_settings"]["start_coordinate"] = 1
    else:
        result["topology"] = "circular"

    assert multi_tu_formal_editor_restore_reason(result) == expected


def test_json_and_sqlite_persist_equivalent_completed_editor_state(
    tmp_path: Path,
) -> None:
    result = _bind_completed_state(_result(3))
    json_repository = PlantProjectDraftRepository(tmp_path / "json-records")
    database_path = tmp_path / "sqlite" / "biodesign.db"
    _initialize_database(database_path)
    sqlite_repository = SqlitePlantProjectDraftRepository(database_path)

    json_saved = save_mvp_multi_tu_design(
        copy.deepcopy(result), repository=json_repository
    )
    sqlite_saved = save_mvp_multi_tu_design(
        copy.deepcopy(result), repository=sqlite_repository
    )
    json_opened = open_mvp_multi_tu_design(
        json_saved.project_id, repository=json_repository
    )
    sqlite_opened = open_mvp_multi_tu_design(
        sqlite_saved.project_id, repository=sqlite_repository
    )

    assert json_opened["formal_project_context"] == sqlite_opened[
        "formal_project_context"
    ]
    assert json_opened["original_input"] == sqlite_opened["original_input"]
    assert json_opened["combined_construct"] == sqlite_opened["combined_construct"]
    assert json_opened["exports"] == sqlite_opened["exports"]
    with sqlite3.connect(database_path) as connection:
        raw = connection.execute("SELECT design_data FROM project_history").fetchone()[0]
    payload = json.loads(raw)["draft"]["manual_review_state"][
        MVP_MULTI_TU_PERSISTENCE_KEY
    ]
    assert payload["formal_project_context"] == result["formal_project_context"]


def test_no_vector_state_cannot_be_bound_to_an_invalid_result() -> None:
    result = _result(2)
    result["contains_vector"] = True

    with pytest.raises(MvpMultiTuPersistenceError, match="canonical linear"):
        linear_multi_tu_completed_editor_vector_state(result)
