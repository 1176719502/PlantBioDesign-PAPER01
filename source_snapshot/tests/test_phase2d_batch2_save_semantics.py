from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.design_session import DesignSession, SessionController
from services.formal_project_persistence import (
    FORMAL_DRAFT_STATE_KEY,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    WORKFLOW_GATE3_PATHWAY,
    WORKFLOW_MULTI_TU,
    WORKFLOW_SINGLE_GENE,
    formal_draft_snapshot,
    mark_formal_project_completed,
    restore_design_session,
    save_formal_project_draft,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import PlantProjectDraftError


ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> PlantProjectDraftRepository:
    return PlantProjectDraftRepository(tmp_path / "formal-projects")


def _save_draft(
    repo: PlantProjectDraftRepository,
    *,
    workflow_type: str,
    project_id: str = "",
    project_name: str = "Draft project",
):
    return save_formal_project_draft(
        project_name=project_name,
        project_id=project_id,
        workflow_type=workflow_type,
        current_step=2,
        design_session=DesignSession(step=2, gene_name="draft-gene", original_seq="ATGAAATAA"),
        formal_state={
            "formal_project_name": project_name,
            "formal_project_type": "dual_tu" if workflow_type != WORKFLOW_SINGLE_GENE else "single_gene",
            "formal_transcription_units": [] if workflow_type != WORKFLOW_SINGLE_GENE else None,
        },
        project_definition={
            "project_name": project_name,
            "plant_host": "Rice (O. sativa)",
            "application_mode": "stable transformation",
            "expression_target": "User-recorded expression design goal",
        },
        repository=repo,
    )


@pytest.mark.parametrize("workflow_type", [WORKFLOW_SINGLE_GENE, WORKFLOW_MULTI_TU])
def test_incomplete_single_and_multi_tu_save_as_json_drafts_and_cold_reopen(
    tmp_path: Path, workflow_type: str
) -> None:
    repo = _repo(tmp_path)
    saved = _save_draft(repo, workflow_type=workflow_type)

    assert saved.draft_status == STATUS_DRAFT
    assert saved.workflow_type == workflow_type
    assert saved.canonical_available is False
    assert saved.canonical_construct_runtime == {}
    assert len(list(repo.storage_dir.glob("*.json"))) == 1

    cold_repo = PlantProjectDraftRepository(repo.storage_dir)
    reopened = cold_repo.load(saved.project_id)
    snapshot = formal_draft_snapshot(reopened)
    session = restore_design_session(snapshot["design_session"])

    assert session.step == 2
    assert session.gene_name == "draft-gene"
    assert snapshot["formal_state"]["formal_project_name"] == "Draft project"


def test_gate3_draft_uses_the_same_repository_contract(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saved = _save_draft(repo, workflow_type=WORKFLOW_GATE3_PATHWAY, project_name="Gate 3 draft")
    payload = json.loads((repo.storage_dir / f"{saved.project_id}.json").read_text(encoding="utf-8"))

    assert payload["workflow_type"] == WORKFLOW_GATE3_PATHWAY
    assert payload["draft_status"] == STATUS_DRAFT
    assert FORMAL_DRAFT_STATE_KEY in payload["manual_review_state"]


def test_repeated_draft_save_is_idempotent_and_distinct_new_projects_do_not_collide(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _save_draft(repo, workflow_type=WORKFLOW_SINGLE_GENE)
    updated = _save_draft(
        repo,
        workflow_type=WORKFLOW_SINGLE_GENE,
        project_id=first.project_id,
        project_name="Renamed draft",
    )
    second_project = _save_draft(repo, workflow_type=WORKFLOW_SINGLE_GENE, project_name="Second draft")

    assert updated.project_id == first.project_id
    assert second_project.project_id != first.project_id
    assert len(repo.list_summaries()) == 2


def test_completed_status_requires_canonical_and_cannot_be_downgraded_to_draft(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    draft = _save_draft(repo, workflow_type=WORKFLOW_SINGLE_GENE)
    with pytest.raises(PlantProjectDraftError, match="canonical"):
        mark_formal_project_completed(draft, workflow_type=WORKFLOW_SINGLE_GENE)

    draft.canonical_construct_runtime = {"project_id": draft.project_id, "transcription_units": [{}]}
    completed = repo.save(mark_formal_project_completed(draft, workflow_type=WORKFLOW_SINGLE_GENE))
    assert completed.draft_status == STATUS_COMPLETED
    assert completed.canonical_available is True
    with pytest.raises(PlantProjectDraftError, match="completed project"):
        _save_draft(repo, workflow_type=WORKFLOW_SINGLE_GENE, project_id=completed.project_id)


def test_old_json_without_new_fields_is_readable_and_unknown_fields_survive_update(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    draft = repo.create_blank(project_name="Older JSON")
    payload = draft.to_dict()
    payload.pop("workflow_type")
    payload.pop("canonical_available")
    payload["future_extension"] = {"owner": "external-compatible-reader", "value": 7}
    repo.storage_dir.mkdir(parents=True)
    path = repo.storage_dir / f"{draft.project_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = repo.load(draft.project_id)
    assert loaded.workflow_type == ""
    assert loaded.canonical_available is False
    loaded.project_name = "Older JSON updated"
    repo.save(loaded)
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    assert rewritten["future_extension"] == payload["future_extension"]


def test_invalid_non_json_workflow_data_fails_before_any_file_is_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(PlantProjectDraftError, match="JSON-compatible"):
        save_formal_project_draft(
            project_name="Invalid draft",
            project_id="",
            workflow_type=WORKFLOW_SINGLE_GENE,
            current_step=1,
            design_session=DesignSession(),
            formal_state={"bad": object()},
            repository=repo,
        )
    assert not repo.storage_dir.exists()


def test_formal_json_save_does_not_add_legacy_sqlite_rows(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy-saved-designs.sqlite"
    connection = sqlite3.connect(legacy_db)
    connection.executescript(
        "CREATE TABLE sequences (id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE project_history (id INTEGER PRIMARY KEY, project_name TEXT);"
        "INSERT INTO sequences (name) VALUES ('historical sequence');"
        "INSERT INTO project_history (project_name) VALUES ('historical design');"
    )
    connection.commit()
    before = tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("sequences", "project_history")
    )
    connection.close()

    _save_draft(_repo(tmp_path), workflow_type=WORKFLOW_SINGLE_GENE)

    connection = sqlite3.connect(legacy_db)
    after = tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("sequences", "project_history")
    )
    connection.close()
    assert before == after == (1, 1)


def test_atomic_replace_failure_preserves_existing_json_and_cleans_temp_file(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    saved = _save_draft(repo, workflow_type=WORKFLOW_SINGLE_GENE)
    target = repo.storage_dir / f"{saved.project_id}.json"
    original_bytes = target.read_bytes()

    def fail_replace(_source: str, _target: Path) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("services.plant_project_draft_repository.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        _save_draft(
            repo,
            workflow_type=WORKFLOW_SINGLE_GENE,
            project_id=saved.project_id,
            project_name="Write must not land",
        )

    assert target.read_bytes() == original_bytes
    assert not list(repo.storage_dir.glob("*.tmp"))


def test_formal_app_has_no_legacy_sqlite_save_call_and_labels_session_save_accurately() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(app_source)
    navigation_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_step_navigation"
    )
    navigation = ast.get_source_segment(app_source, navigation_node) or ""
    save_helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_save_current_formal_draft"
    )
    save_helper = ast.get_source_segment(app_source, save_helper_node) or ""
    snapshot_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_formal_state_snapshot"
    )
    snapshot_helper = ast.get_source_segment(app_source, snapshot_node) or ""
    session_source = (ROOT / "core" / "design_session.py").read_text(encoding="utf-8")

    assert "save_wizard_design" not in app_source
    assert "save_betalain_gate3_mapping" not in app_source
    assert "_save_current_formal_draft(current_step=current_step)" in navigation
    assert "save_formal_project_draft" in save_helper
    assert "_save_gate3_pathway_draft()" in navigation
    assert 'key=f"formal_step_{current_step}_save_draft"' in navigation
    assert "_t('v1.common.save_project') if current_step == 6 else _t('v1.common.save_draft')" in navigation
    assert 'st.session_state["mvp_project_id"] = project_id' in app_source
    assert "if enzyme_widget_key in st.session_state" in app_source
    assert 'st.session_state.get("formal_step1_project_name")' in save_helper
    assert '"formal_step1_project_name",' in snapshot_helper
    assert "v1.common.project_draft_saved_can_reopened_project_center" in navigation
    assert "Store *ds* in the current Streamlit session only." in session_source
    assert "def save_wizard_design" in (ROOT / "services" / "design_saver.py").read_text(encoding="utf-8")
    assert "query_saved_design_summaries" in (ROOT / "services" / "design_saver.py").read_text(encoding="utf-8")


def test_formal_state_snapshot_excludes_streamlit_action_widget_keys() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_is_formal_action_widget_key", "_formal_state_snapshot"}
    ]
    step_id = "pathway-step-stable-reopen-id"
    state = {
        "formal_project_name": "Gate 3 draft",
        "formal_betalain_gate3_case": True,
        f"formal_pathway_{step_id}_name": "Step 1 restored input",
        f"formal_pathway_{step_id}_unit": "TU1",
        "formal_pathway_add_step": False,
        "formal_pathway_add_tu": False,
        f"formal_pathway_{step_id}_up": False,
        f"formal_pathway_{step_id}_down": False,
        f"formal_pathway_{step_id}_delete": False,
        f"formal_pathway_{step_id}_confirm_delete": False,
        f"formal_pathway_{step_id}_cancel_delete": False,
        f"formal_pathway_{step_id}_save": True,
        f"formal_pathway_{step_id}_apply": False,
        "formal_betalain_save_mapping": True,
        "formal_betalain_save_enzyme_edit": False,
        "formal_step_2_save_draft": True,
        "formal_TU1_delete_confirm": True,
    }
    namespace = {
        "Any": object,
        "json": json,
        "re": re,
        "st": SimpleNamespace(session_state=state),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)

    snapshot = namespace["_formal_state_snapshot"]()

    assert snapshot == {
        "formal_project_name": "Gate 3 draft",
        "formal_betalain_gate3_case": True,
        f"formal_pathway_{step_id}_name": "Step 1 restored input",
        f"formal_pathway_{step_id}_unit": "TU1",
    }


def test_session_controller_save_remains_session_only(monkeypatch) -> None:
    class FakeStreamlit:
        session_state: dict[str, object] = {}

    import sys
    import types

    monkeypatch.setitem(sys.modules, "streamlit", types.SimpleNamespace(session_state=FakeStreamlit.session_state))
    session = DesignSession(step=3, gene_name="session-only")
    SessionController().save(session)
    assert FakeStreamlit.session_state["design_session"] is session
