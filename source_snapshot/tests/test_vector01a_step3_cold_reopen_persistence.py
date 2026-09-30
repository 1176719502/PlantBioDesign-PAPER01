from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.design_session import DesignSession
from services.formal_expression_cassette import (
    assess_expression_cassette,
    generate_expression_cassette,
)
from services.formal_project_persistence import (
    formal_draft_snapshot,
    save_formal_project_draft,
)
from services.formal_step3_gate import step3_can_continue_to_backbone
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


class _Streamlit:
    def __init__(self, state: dict[str, Any]) -> None:
        self.session_state = state


def _restore_generated_result(state: dict[str, Any]) -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_restore_formal_step3_generated_result"
    )
    namespace = {"Any": Any, "Mapping": Mapping, "st": _Streamlit(state)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_PATH), "exec"), namespace)
    namespace["_restore_formal_step3_generated_result"]()


def _component(role: str, sequence: str) -> dict[str, object]:
    return {
        "biological_role": role,
        "display_name": role,
        "sequence": sequence,
        "source_kind": "library",
        "source_reference": "LOCAL:review",
        "user_edited": False,
    }


def _generated_result(project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    components = [
        _component("promoter", "AAAA"),
        _component("cds", "ATGAAATAA"),
        _component("three_prime_regulatory_region", "TTTT"),
    ]
    assessment = assess_expression_cassette(
        components,
        cds_sequence="ATGAAATAA",
        cds_signature="cds-current",
        order_confirmed=True,
    )
    assert assessment["blocking"] is False
    generated = generate_expression_cassette(assessment, project_id=project_id)
    generated["cassette_input_signature"] = assessment["input_signature"]
    generated["manual_confirmation_items"] = [
        {"rule_id": "review-one", "status": "manual_review"},
        {"rule_id": "review-two", "status": "manual_review"},
    ]
    generated["findings"] = list(generated["manual_confirmation_items"])
    return generated, assessment


def test_step3_generated_result_survives_real_draft_cold_reopen_and_invalidates_on_input_change(
    tmp_path: Path,
) -> None:
    project_id = "cold-reopen-step3"
    generated, assessment = _generated_result(project_id)
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    saved = save_formal_project_draft(
        project_name="Cold reopen Step 3",
        project_id=project_id,
        workflow_type="single_gene",
        current_step=3,
        design_session=DesignSession(step=3, host="Rice"),
        formal_state={
            "formal_expression_cassette": generated,
            "formal_step3_order_confirmation_recorded": True,
        },
        project_definition={"project_name": "Cold reopen Step 3", "plant_host": "Rice"},
        repository=repository,
    )

    # Simulate a fresh process: reload persisted bytes into an empty session.
    snapshot = formal_draft_snapshot(PlantProjectDraftRepository(repository.storage_dir).load(saved.project_id))
    state: dict[str, Any] = {}
    state.update(snapshot["formal_state"])
    _restore_generated_result(state)

    restored = state["formal_cassette_result"]
    current_signature = assessment["input_signature"]
    assert state["formal_cassette_input_signature"] == current_signature
    assert restored["cassette_input_signature"] == current_signature
    assert step3_can_continue_to_backbone(
        cassette_result=restored,
        current_input_signature=current_signature,
        findings=state["formal_expression_cassette"]["findings"],
        order_confirmed=state["formal_step3_order_confirmation_recorded"],
    ) is True

    changed = assess_expression_cassette(
        [_component("promoter", "AAAT"), *_generated_components()],
        cds_sequence="ATGAAATAA",
        cds_signature="cds-current",
        order_confirmed=True,
    )
    assert changed["input_signature"] != current_signature
    assert step3_can_continue_to_backbone(
        cassette_result=restored,
        current_input_signature=changed["input_signature"],
        findings=state["formal_expression_cassette"]["findings"],
        order_confirmed=state["formal_step3_order_confirmation_recorded"],
    ) is False


def _generated_components() -> list[dict[str, object]]:
    return [
        _component("cds", "ATGAAATAA"),
        _component("three_prime_regulatory_region", "TTTT"),
    ]
