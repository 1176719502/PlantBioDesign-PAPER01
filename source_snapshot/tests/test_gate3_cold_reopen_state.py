from __future__ import annotations

import ast
from collections.abc import Mapping
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from core.design_session import DesignSession
from services.formal_project_persistence import WORKFLOW_GATE3_PATHWAY, save_formal_project_draft
from services.gate3_pathway_mapping import apply_step_cds_to_unit, test_only_three_step_fixture
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATHWAY_MULTI_TU = "metabolic_pathway_multi_tu_vector"


def _load_app_functions(*names: str, state: dict) -> tuple[dict, SimpleNamespace]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    required_names = {*names, "_restore_formal_step3_generated_result"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in required_names
    ]
    st = SimpleNamespace(session_state=state)
    namespace = {
        "Any": object,
        "Mapping": Mapping,
        "re": re,
        "st": st,
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace, st


def _gate3_state() -> tuple[list[dict], list[dict], dict[str, str]]:
    steps = test_only_three_step_fixture()
    units = [
        {"unit_id": "TU1", "display_name": "TU 1", "order": 1, "orientation": "forward", "cds": {}},
        {"unit_id": "TU2", "display_name": "TU 2", "order": 2, "orientation": "reverse", "cds": {}},
        {"unit_id": "TU3", "display_name": "TU 3", "order": 3, "orientation": "forward", "cds": {}},
    ]
    for step in list(steps):
        steps, units = apply_step_cds_to_unit(steps, units, step["step_id"])
    definition = {
        "project_name": "Gate 3 legacy action-state draft",
        "plant_host": "Rice (O. sativa)",
        "material": "",
        "application_mode": "尚未确定",
        "expression_target": "",
    }
    return steps, units, definition


def test_gate3_action_widget_keys_are_classified_without_hiding_editable_state() -> None:
    functions, _ = _load_app_functions(
        "_is_formal_action_widget_key",
        "_formal_widget_initial_kwargs",
        state={"formal_pathway_pathway-step-stable-id_name": "Restored step"},
    )
    is_action_key = functions["_is_formal_action_widget_key"]
    initial_kwargs = functions["_formal_widget_initial_kwargs"]
    prefix = "formal_pathway_pathway-step-stable-id"

    for suffix in ("up", "down", "delete", "confirm_delete", "cancel_delete", "save", "apply"):
        assert is_action_key(f"{prefix}_{suffix}") is True
    for suffix in ("name", "enzyme", "substrate", "product", "source_type", "unit", "cds"):
        assert is_action_key(f"{prefix}_{suffix}") is False
    assert initial_kwargs(f"{prefix}_name", value="Default step") == {}
    assert initial_kwargs(f"{prefix}_enzyme", value="Default enzyme") == {"value": "Default enzyme"}

    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    renderer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_pathway_mapping_step_2"
    )
    renderer_source = ast.get_source_segment(source, renderer) or ""
    assert renderer_source.count("_formal_widget_initial_kwargs(") == 13


def test_legacy_gate3_action_state_is_removed_before_route_and_in_cold_subprocess(tmp_path: Path) -> None:
    steps, units, definition = _gate3_state()
    prefix = f"formal_pathway_{steps[0]['step_id']}"
    action_keys = {
        f"{prefix}_up",
        f"{prefix}_down",
        f"{prefix}_delete",
        f"{prefix}_confirm_delete",
        f"{prefix}_cancel_delete",
        f"{prefix}_save",
        f"{prefix}_apply",
    }
    editable_key = f"{prefix}_name"
    formal_state = {
        "formal_project_type": "dual_tu",
        "formal_design_scenario": SCENARIO_PATHWAY_MULTI_TU,
        "formal_project_definition": definition,
        "formal_project_name": definition["project_name"],
        "formal_project_host": definition["plant_host"],
        "formal_pathway_steps": steps,
        "formal_transcription_units": units,
        editable_key: steps[0]["step_name"],
        **{key: False for key in action_keys},
    }
    repository = PlantProjectDraftRepository(tmp_path / "legacy-action-state")
    saved = save_formal_project_draft(
        project_name=definition["project_name"],
        project_id="gate3-legacy-action-state",
        workflow_type=WORKFLOW_GATE3_PATHWAY,
        current_step=2,
        design_session=DesignSession(step=2, host=definition["plant_host"], tag="No tag"),
        formal_state=formal_state,
        project_definition=definition,
        manual_state_updates={
            "gate3_pathway_draft": {
                "schema_version": "v1",
                "project_type": "dual_tu",
                "design_scenario": SCENARIO_PATHWAY_MULTI_TU,
                "project_definition": definition,
                "pathway_steps": steps,
                "transcription_units": units,
                "unknown_future_field": {"preserved": True},
            }
        },
        repository=repository,
    )
    draft_path = next(repository.storage_dir.glob("*.json"))
    persisted_before = draft_path.read_bytes()

    functions, st = _load_app_functions(
        "_is_formal_action_widget_key",
        "_restore_formal_workflow_draft",
        state={f"{prefix}_up": True, "formal_stale_value": "remove"},
    )
    controller_state: list[object] = []
    page_state: list[tuple[str, dict]] = []
    functions.update(
        {
            "_controller": lambda: SimpleNamespace(save=controller_state.append),
            "_change_page": lambda page: page_state.append((page, dict(st.session_state))),
        }
    )
    functions["_restore_formal_workflow_draft"](saved.project_id, repository)

    restored = st.session_state
    assert action_keys.isdisjoint(restored)
    assert restored[editable_key] == steps[0]["step_name"]
    assert len(restored["formal_pathway_steps"]) == 3
    assert [step["mapped_unit_id"] for step in restored["formal_pathway_steps"]] == ["TU1", "TU2", "TU3"]
    assert restored["formal_design_scenario"] == SCENARIO_PATHWAY_MULTI_TU
    assert restored["mvp_project_id"] == saved.project_id
    assert controller_state[0].step == 2
    assert page_state[0][0] == "Six-Step Design Workspace"
    assert action_keys.isdisjoint(page_state[0][1])
    assert draft_path.read_bytes() == persisted_before
    assert len(list(repository.storage_dir.glob("*.json"))) == 1

    probe = r'''
import ast
import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

from services.formal_project_persistence import formal_draft_snapshot
from services.plant_project_draft_repository import PlantProjectDraftRepository

tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
names = {
    "_is_formal_action_widget_key",
    "_restore_formal_step3_generated_result",
    "_restore_formal_workflow_draft",
}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
st = SimpleNamespace(session_state={})
namespace = {
    "Any": object,
    "Mapping": Mapping,
    "re": re,
    "st": st,
    "PROJECT_TYPE_DUAL_TU": "dual_tu",
    "PROJECT_TYPE_SINGLE_GENE": "single_gene",
    "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
}
exec(compile(ast.Module(body=selected, type_ignores=[]), "app.py", "exec"), namespace)
pages = []
namespace["_controller"] = lambda: SimpleNamespace(save=lambda value: None)
namespace["_change_page"] = pages.append
namespace["_restore_formal_workflow_draft"]("gate3-legacy-action-state")
draft = PlantProjectDraftRepository().load("gate3-legacy-action-state")
snapshot = formal_draft_snapshot(draft)
steps = st.session_state["formal_pathway_steps"]
print(json.dumps({
    "workflow_type": snapshot["workflow_type"],
    "status": draft.draft_status,
    "step_count": len(steps),
    "mapped_units": [step["mapped_unit_id"] for step in steps],
    "action_keys": sorted(key for key in st.session_state if key.endswith(("_up", "_down", "_save", "_apply"))),
    "editable_name": st.session_state.get("__EDITABLE_KEY__"),
    "page": pages,
}))
'''.replace("__EDITABLE_KEY__", editable_key)
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(repository.storage_dir)},
        check=True,
        capture_output=True,
        text=True,
    )
    cold = json.loads(completed.stdout.strip().splitlines()[-1])
    assert cold == {
        "workflow_type": WORKFLOW_GATE3_PATHWAY,
        "status": "draft",
        "step_count": 3,
        "mapped_units": ["TU1", "TU2", "TU3"],
        "action_keys": [],
        "editable_name": steps[0]["step_name"],
        "page": ["Six-Step Design Workspace"],
    }
    assert draft_path.read_bytes() == persisted_before
