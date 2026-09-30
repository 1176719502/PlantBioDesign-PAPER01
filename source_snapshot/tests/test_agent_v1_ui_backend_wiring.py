from __future__ import annotations

import ast
from dataclasses import replace
from enum import Enum
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from typing import Mapping
from unittest.mock import Mock

import pytest

from services.agent_candidate_store import CandidateStore, CandidateStoreError
from services.agent_contracts import (
    AdoptionRequest,
    AgentNeedInput,
    AgentRequest,
    AgentRunState,
    CandidateState,
    DeterministicValidationStatus,
    NeedInputCode,
    candidate_digest,
)
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider
from services.agent_product_adapter import AgentProductAdapter
from services.agent_service import AgentService
from services.agent_service import (
    AgentBackend,
    AgentServiceError,
    ProductComponentRepository,
    _trusted_enum_value_is,
)
from services.plant_host_registry import SINGLE_GENE_COMPLETE_VECTOR, hosts_for_workflow
from views import AgentWorkspace as workspace
from services.plant_project_draft_repository import PlantProjectDraftRepository
from core.i18n import translate
from views.AgentWorkspace import (
    _bind_created_project,
    _capture_request_form,
    _candidate_review_ready,
    _host_values_for_workflow,
    _load_adopted_readback,
    _needs_input_presentation,
    _project_requires_recovery,
    _request_signature,
    _result_state_is,
    _restore_request_form,
    _safe_error_message,
    create_agent_formal_draft,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
VIEW_SOURCE = (ROOT / "views" / "AgentWorkspace.py").read_text(encoding="utf-8")


def _reloaded_enum_member(expected: Enum) -> Enum:
    """Build the class identity produced by reload with stable family metadata."""
    expected_type = type(expected)
    reloaded_type = Enum(
        expected_type.__name__,
        {name: member.value for name, member in expected_type.__members__.items()},
        type=str,
        module=expected_type.__module__,
        qualname=expected_type.__qualname__,
    )
    return reloaded_type[expected.name]


def _backend(tmp_path: Path, project_id: str = "agent-ui-project") -> AgentBackend:
    repository = PlantProjectDraftRepository(tmp_path / "formal")
    draft = repository.create_blank(project_name="Agent UI project")
    draft.project_id = project_id
    repository.save(draft)
    provider = QwenProvider(
        config=QwenConfig(model="agent-ui-test-model"),
        transport=FakeQwenTransport(),
    )
    return AgentBackend(
        provider,
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=repository,
    )


def _request(project_id: str = "agent-ui-project") -> AgentRequest:
    return AgentRequest(
        workflow_type="single_gene",
        host="Oryza sativa",
        user_intent="Prepare a project-bound design candidate for review.",
        cds_or_reference_input="ATGAAATAG",
        project_id=project_id,
        context={"project_id": project_id},
    )


def test_formal_app_registers_one_agent_route_and_renderer() -> None:
    tree = ast.parse(APP_SOURCE)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("PAGE_")
    }
    assert constants["PAGE_AGENT_WORKSPACE"] == "Agent V1 Workspace"
    assert APP_SOURCE.count("render_agent_workspace(") == 1
    assert 'PAGE_AGENT_WORKSPACE: "智能设计"' in APP_SOURCE


def test_ui_uses_adopted_backend_boundaries_and_has_no_direct_formal_write() -> None:
    assert "backend.generate_and_validate(request)" in VIEW_SOURCE
    assert "backend.service.build_adoption_preview(candidate)" in VIEW_SOURCE
    assert "backend.service.confirm_candidate(" in VIEW_SOURCE
    assert "backend.adopt(" in VIEW_SOURCE
    assert "_result_state_is(result, AgentRunState.ALTERNATIVES)" in VIEW_SOURCE
    assert "result.state is AgentRunState" not in VIEW_SOURCE
    assert "receipt_is_authoritative" in VIEW_SOURCE
    assert "formal_repository.save(" not in VIEW_SOURCE
    assert '"component_selection_required"' not in VIEW_SOURCE
    assert '"required_component_roles"' not in VIEW_SOURCE
    assert "extra_fields[\"agent_adoption\"]" not in VIEW_SOURCE
    assert "FakeQwenTransport" not in VIEW_SOURCE


class _RenderRerun(BaseException):
    pass


class _RenderUI:
    """Capture actual rendering and stop reruns at the Streamlit boundary."""

    def __init__(self, *, confirm: bool = False):
        self.output: list[str] = []
        self.confirm = confirm

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def container(self, **kwargs):
        return self

    def columns(self, spec):
        return [self] * (spec if isinstance(spec, int) else len(spec))

    def markdown(self, text, **kwargs):
        self.output.append(str(text))

    title = caption = write = warning = error = markdown

    def checkbox(self, *args, **kwargs):
        return self.confirm

    def button(self, *args, key=None, **kwargs):
        return self.confirm and key == "agent_confirm_adoption"

    def rerun(self):
        raise _RenderRerun()


class _NeedsInputRenderUI(_RenderUI):
    def __init__(self, state: Mapping[str, object], *, click_generate: bool):
        super().__init__()
        self.state = state
        self.click_generate = click_generate

    def text_area(self, label, *, key=None, **kwargs):
        self.output.append(str(label))
        return str(self.state.get(str(key), "") or "")

    def selectbox(self, label, *args, key=None, **kwargs):
        self.output.append(str(label))
        return self.state.get(str(key))

    def button(self, label, *args, key=None, **kwargs):
        self.output.append(str(label))
        if key == "agent_generate_candidate_design" and self.click_generate:
            self.click_generate = False
            return True
        return False

    def status(self, label, **kwargs):
        self.output.append(str(label))
        return self

    def update(self, **kwargs):
        self.output.append(str(kwargs.get("label") or ""))

    def info(self, text, **kwargs):
        self.output.append(str(text))


def _render_project(backend, state):
    workspace.render_agent_workspace(
        project_id="agent-ui-project", project_name="Agent UI project",
        backend=backend, state=state,
    )


def _adopt_for_render(backend):
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(candidate, confirmation_id="render-confirm", preview=preview)
    return backend.adopt(AdoptionRequest(
        confirmed.candidate_id, "agent-ui-project", candidate_digest(confirmed), "render-confirm",
    ))


def _reopen_backend(tmp_path):
    return AgentBackend(
        QwenProvider(config=QwenConfig(model="agent-ui-test-model"), transport=FakeQwenTransport()),
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=PlantProjectDraftRepository(tmp_path / "formal"),
    )


@pytest.mark.parametrize("cold", [False, True], ids=["session", "cold-reopen"])
@pytest.mark.parametrize("recovery", ["none", "other-transaction", "same-transaction", "journal"])
def test_p1_recovery_authority_precedes_any_adopted_render(tmp_path, monkeypatch, cold, recovery):
    backend = _backend(tmp_path)
    receipt = _adopt_for_render(backend)
    if recovery in {"other-transaction", "same-transaction"}:
        backend.store.write_recovery_marker(
            receipt.transaction_id if recovery == "same-transaction" else "adopt-other-unresolved",
            {"project_id": "agent-ui-project", "candidate_id": receipt.candidate_id},
        )
    elif recovery == "journal":
        backend.store.write_journal("adopt-other-in-progress", {
            "project_id": "agent-ui-project", "candidate_id": receipt.candidate_id, "status": "IN_PROGRESS",
        })
    if cold:
        backend = _reopen_backend(tmp_path)
    assert backend.store.receipt_is_authoritative(receipt.receipt_id) is (recovery != "same-transaction")
    readback = Mock(wraps=workspace._load_adopted_readback)
    monkeypatch.setattr(workspace, "_load_adopted_readback", readback)
    ui = _RenderUI()
    monkeypatch.setattr(workspace, "st", ui)
    state = {} if cold else {"agent_v1_ui_backend_project_id": "agent-ui-project", "agent_v1_ui_screen": "adopted"}
    _render_project(backend, state)
    rendered = "\n".join(ui.output)
    if recovery == "none":
        assert "USER_ADOPTED" in rendered
        assert "RECOVERY_REQUIRED" not in rendered
        readback.assert_called_once_with(backend, "agent-ui-project")
    else:
        assert "RECOVERY_REQUIRED" in rendered
        assert "USER_ADOPTED" not in rendered
        assert state["agent_v1_ui_screen"] == "recovery"
        readback.assert_not_called()


@pytest.mark.parametrize("failure", ["store", "service", "digest", "context", "reload"])
def test_p1_confirmation_errors_fail_closed_without_receipt(tmp_path, monkeypatch, failure):
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    raw_error = "PRIVATE_PROVIDER_BODY token=internal-token path=C:/private digest=internal-digest"
    if failure in {"store", "service"}:
        exception_type = CandidateStoreError if failure == "store" else AgentServiceError
        monkeypatch.setattr(backend.service, "confirm_candidate", Mock(side_effect=exception_type(raw_error)))
    elif failure == "digest":
        candidate = replace(candidate, rationale="Changed since preview")
    elif failure == "context":
        backend.service.build_adoption_preview(candidate)
    elif failure == "reload":
        backend = _reopen_backend(tmp_path)
    before = backend.adoption.formal_repository.load("agent-ui-project").to_dict()
    adopt = Mock(wraps=backend.adopt)
    monkeypatch.setattr(backend, "adopt", adopt)
    ui = _RenderUI(confirm=True)
    monkeypatch.setattr(workspace, "st", ui)
    state = {
        "agent_v1_ui_backend_project_id": "agent-ui-project",
        "agent_v1_ui_entry_mode": "current", "agent_v1_ui_adoption_preview": preview,
    }
    with pytest.raises(_RenderRerun):
        workspace._render_adoption(candidate, backend, "agent-ui-project", state)
    assert state["agent_v1_ui_screen"] == "error"
    assert "agent_v1_ui_adoption_receipt" not in state
    adopt.assert_not_called()
    assert backend.adoption.formal_repository.load("agent-ui-project").to_dict() == before
    assert not list(backend.store.receipts_dir.glob("*.json"))
    assert workspace._load_adopted_readback(backend, "agent-ui-project") is None
    ui.output.clear()
    _render_project(backend, state)
    rendered = "\n".join(ui.output)
    assert translate(
        "v1.ai_assisted_design.adoption_not_completed_check_revision",
        language="en",
    ) in rendered
    assert "USER_ADOPTED" not in rendered
    assert all(secret not in rendered for secret in (raw_error, "Traceback", "internal-token", "internal-digest", "C:/private"))


def test_p1_valid_confirmation_renders_authenticated_adoption(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    ui = _RenderUI(confirm=True)
    monkeypatch.setattr(workspace, "st", ui)
    state = {"agent_v1_ui_adoption_preview": preview}
    with pytest.raises(_RenderRerun):
        workspace._render_adoption(candidate, backend, "agent-ui-project", state)
    assert state["agent_v1_ui_screen"] == "adopted"
    receipt = state["agent_v1_ui_adoption_receipt"]
    assert backend.store.receipt_is_authoritative(receipt.receipt_id)
    ui.confirm = False
    _render_project(_reopen_backend(tmp_path), {})
    assert "USER_ADOPTED" in "\n".join(ui.output)


def test_p1_backend_completed_rollback_allows_fresh_confirmation(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    ui = _RenderUI(confirm=True)
    monkeypatch.setattr(workspace, "st", ui)
    state = {"agent_v1_ui_adoption_preview": backend.service.build_adoption_preview(candidate)}
    save_receipt = backend.store.save_receipt
    monkeypatch.setattr(backend.store, "save_receipt", Mock(side_effect=OSError("controlled write fault")))
    before = backend.adoption.formal_repository.load("agent-ui-project").to_dict()
    with pytest.raises(_RenderRerun):
        workspace._render_adoption(candidate, backend, "agent-ui-project", state)
    assert state["agent_v1_ui_screen"] == "error"
    assert backend.store.list_journal()[-1]["status"] == "FAILED_ROLLED_BACK"
    assert backend.adoption.formal_repository.load("agent-ui-project").to_dict() == before
    assert not workspace._project_requires_recovery(backend, "agent-ui-project")
    assert not list(backend.store.receipts_dir.glob("*.json"))
    monkeypatch.setattr(backend.store, "save_receipt", save_receipt)
    candidate = backend.store.load(candidate.candidate_id)
    state["agent_v1_ui_adoption_preview"] = backend.service.build_adoption_preview(candidate)
    with pytest.raises(_RenderRerun):
        workspace._render_adoption(candidate, backend, "agent-ui-project", state)
    receipt = state["agent_v1_ui_adoption_receipt"]
    assert backend.store.receipt_is_authoritative(receipt.receipt_id)
    ui.confirm = False
    _render_project(_reopen_backend(tmp_path), {})
    assert "USER_ADOPTED" in "\n".join(ui.output)


def test_p1_backend_transaction_completion_releases_recovery_view(tmp_path, monkeypatch):
    backend = _backend(tmp_path)
    ui = _RenderUI()
    monkeypatch.setattr(workspace, "st", ui)
    state = {}
    save_receipt = backend.store.save_receipt

    def observe_in_progress(receipt):
        saved = save_receipt(receipt)
        _render_project(_reopen_backend(tmp_path), state)
        assert state["agent_v1_ui_screen"] == "recovery"
        assert "RECOVERY_REQUIRED" in "\n".join(ui.output)
        assert "USER_ADOPTED" not in "\n".join(ui.output)
        return saved

    monkeypatch.setattr(backend.store, "save_receipt", observe_in_progress)
    receipt = _adopt_for_render(backend)
    assert backend.store.receipt_is_authoritative(receipt.receipt_id)
    assert backend.store.list_journal()[-1]["status"] == "COMMITTED"
    ui.output.clear()
    _render_project(_reopen_backend(tmp_path), state)
    assert "USER_ADOPTED" in "\n".join(ui.output)
    assert "RECOVERY_REQUIRED" not in "\n".join(ui.output)


def test_generation_does_not_mutate_formal_and_adoption_cold_readback_is_authoritative(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    before = backend.adoption.formal_repository.load("agent-ui-project").to_dict()
    candidate = backend.generate_and_validate(_request()).candidates[0]

    assert candidate.state.value == "VALIDATED_CANDIDATE"
    assert backend.adoption.formal_repository.load("agent-ui-project").to_dict() == before

    preview = backend.service.build_adoption_preview(candidate)
    token = "agent-ui-confirmation"
    confirmed = backend.service.confirm_candidate(candidate, confirmation_id=token, preview=preview)
    receipt = backend.adopt(
        AdoptionRequest(
            candidate_id=confirmed.candidate_id,
            project_id="agent-ui-project",
            candidate_digest=candidate_digest(confirmed),
            confirmation_token=token,
        )
    )

    reopened = AgentBackend(
        QwenProvider(
            config=QwenConfig(model="agent-ui-test-model"),
            transport=FakeQwenTransport(),
        ),
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=PlantProjectDraftRepository(tmp_path / "formal"),
    )
    readback = _load_adopted_readback(reopened, "agent-ui-project")
    assert readback is not None
    assert readback[0].state.value == "USER_ADOPTED"
    assert readback[1].receipt_id == receipt.receipt_id


def test_adopted_readback_is_project_scoped(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(candidate, confirmation_id="bound-token", preview=preview)
    backend.adopt(
        AdoptionRequest(
            confirmed.candidate_id,
            "agent-ui-project",
            candidate_digest(confirmed),
            "bound-token",
        )
    )
    assert _load_adopted_readback(backend, "different-project") is None


def test_adopted_readback_rejects_current_formal_authority_drift(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    repository = backend.adoption.formal_repository
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(
        candidate,
        confirmation_id="authority-bound-token",
        preview=preview,
    )
    backend.adopt(
        AdoptionRequest(
            confirmed.candidate_id,
            "agent-ui-project",
            candidate_digest(confirmed),
            "authority-bound-token",
        )
    )

    changed = repository.load("agent-ui-project")
    changed.workflow_type = "gate3_pathway"
    repository.save(changed)
    reopened = AgentBackend(
        QwenProvider(
            config=QwenConfig(model="agent-ui-test-model"),
            transport=FakeQwenTransport(),
        ),
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=PlantProjectDraftRepository(tmp_path / "formal"),
    )

    assert _load_adopted_readback(reopened, "agent-ui-project") is None


def test_project_recovery_marker_prevents_success_presentation(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.store.write_recovery_marker(
        "adopt-agent-ui-recovery",
        {
            "candidate_id": "candidate-agent-ui-recovery",
            "project_id": "agent-ui-project",
            "error": "ControlledFailure",
        },
    )
    assert _project_requires_recovery(backend, "agent-ui-project") is True
    assert _project_requires_recovery(backend, "different-project") is False


def test_input_signature_binds_candidate_to_project_and_revision_inputs() -> None:
    base = {
        "project_id": "project-a",
        "workflow": "single_gene",
        "host": "Oryza sativa",
        "user_intent": "review candidate",
        "cds": "ATG",
    }
    assert _request_signature(base) == _request_signature(dict(base))
    assert _request_signature(base) != _request_signature({**base, "project_id": "project-b"})
    assert _request_signature(base) != _request_signature({**base, "cds": "ATGAAA"})


def test_provider_errors_are_safe_and_do_not_expose_raw_diagnostics() -> None:
    message = _safe_error_message("provider_timeout", "secret response id: raw-123")
    assert message == translate(
        "v1.ai_assisted_design.provider_timeout_candidate_not_generated_retry",
        language="en",
    )
    assert "raw-123" not in message
    assert "traceback" not in VIEW_SOURCE.casefold()


def test_agent_copy_keeps_candidate_state_distinct_from_biological_claims() -> None:
    lowered = VIEW_SOURCE.casefold()
    forbidden = (
        "successful import",
        "project imported",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
    )
    assert all(term not in lowered for term in forbidden)
    assert "VALIDATED_CANDIDATE" in VIEW_SOURCE
    assert "USER_ADOPTED" in VIEW_SOURCE
    assert "RECOVERY_REQUIRED" in VIEW_SOURCE


def test_intelligent_design_uses_real_formal_draft_boundary_and_cold_reopens(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "formal")
    draft = create_agent_formal_draft(
        project_name="新建智能设计项目",
        host="Oryza sativa",
        workflow_type="single_gene",
        design_goal="在水稻中记录一个蛋白表达设计目标",
        repository=repository,
    )
    assert draft.project_id.startswith("plant-draft-")
    reopened = repository.load(draft.project_id)
    assert reopened.project_id == draft.project_id
    assert reopened.workflow_type == "single_gene"
    assert reopened.host_context == "Rice (O. sativa)"
    assert reopened.manual_review_state["formal_project_workflow_v1"]["project_definition"]["expression_target"] == "在水稻中记录一个蛋白表达设计目标"


def test_intelligent_design_respects_host_registry_governance(tmp_path: Path) -> None:
    expected_hosts = tuple(
        str(record["scientific_name"])
        for record in hosts_for_workflow(SINGLE_GENE_COMPLETE_VECTOR)
    )
    assert _host_values_for_workflow("single_gene") == expected_hosts
    assert "Solanum lycopersicum" in expected_hosts
    assert "Arabidopsis thaliana" in _host_values_for_workflow("multi_tu")
    with pytest.raises(ValueError):
        create_agent_formal_draft(
            project_name="不应创建",
            host="Arabidopsis thaliana",
            workflow_type="single_gene",
            design_goal="review",
            repository=PlantProjectDraftRepository(tmp_path / "formal"),
        )


def test_intelligent_design_tomato_registry_route_is_deterministic_and_non_adopting() -> None:
    adapter = AgentProductAdapter()
    references = adapter.resolve_component_references(
        ["PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"],
        workflow_type="single_gene",
        host="Solanum lycopersicum",
    )
    transport = FakeQwenTransport()
    service = AgentService(
        QwenProvider(config=QwenConfig(model="agent-ui-test-model"), transport=transport),
        component_repository=adapter.component_repository,
    )
    needs = service.inspect_request(
        AgentRequest(
            workflow_type="single_gene",
            host="Solanum lycopersicum",
            user_intent="Review a tomato single-gene design record.",
            cds_or_reference_input="ATGGCCGCCTAA",
            component_references=references,
        )
    )
    assert needs == ()
    assert transport.calls == []


def test_new_intelligent_design_binding_does_not_leak_previous_project() -> None:
    state = {
        "mvp_project_id": "old-project",
        "formal_project_name": "旧项目",
        "agent_v1_ui_entry_mode": "new",
        "agent_v1_ui_user_intent": "new goal",
    }
    class Draft:
        project_id = "plant-draft-new"
        project_name = "新项目"
        workflow_type = "single_gene"
        host_context = "Oryza sativa"
        manual_review_state = {}
    _bind_created_project(state, Draft(), "new goal")
    assert state["mvp_project_id"] == "plant-draft-new"
    assert state["formal_project_name"] == "新项目"
    assert state["formal_step1_host"] == "Oryza sativa"
    assert state["mvp_project_id"] != "old-project"


def test_expression_design_retires_duplicate_ai_prefill_entry_but_keeps_manual_workspace() -> None:
    tree = ast.parse(APP_SOURCE)
    renderer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_render_design_workspace")
    source = ast.get_source_segment(APP_SOURCE, renderer) or ""
    assert "_render_formal_ai_route_entry" not in source
    assert "_formal_ai_route_prefill_eligible" not in source
    assert 'st.title("表达设计")' in source
    assert "_render_step_1_project" in source
    assert "_render_step_2_cds" in source
    assert 'PAGE_AGENT_WORKSPACE: "智能设计"' in APP_SOURCE


def test_agent_project_selection_return_is_explicit_one_shot_and_project_bound() -> None:
    tree = ast.parse(APP_SOURCE)
    function_names = {
        "_request_agent_project_selection",
        "_consume_agent_project_selection_return",
    }
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in function_names
    ]
    state: dict[str, object] = {}
    namespace = {
        "Mapping": Mapping,
        "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
        "PAGE_PROJECT_HOME": "Project Home",
        "st": SimpleNamespace(session_state=state),
        "_change_page": Mock(),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)

    namespace["_request_agent_project_selection"]()
    assert state["agent_project_selection_return"] == {
        "origin": "Agent V1 Workspace",
        "return_to": "Agent V1 Workspace",
        "purpose": "select_current_formal_project",
    }
    namespace["_change_page"].assert_called_once_with("Project Home")

    state["mvp_project_id"] = "selected-project"
    destination = namespace["_consume_agent_project_selection_return"](
        "selected-project", opened=True
    )
    assert destination == "Agent V1 Workspace"
    assert state["agent_v1_ui_entry_mode"] == "current"
    assert "agent_project_selection_return" not in state
    assert namespace["_consume_agent_project_selection_return"](
        "selected-project", opened=True
    ) is None


@pytest.mark.parametrize(
    ("opened", "current_project_id", "selected_project_id"),
    ((False, "", "missing"), (True, "other-project", "missing")),
)
def test_failed_or_mismatched_agent_project_selection_consumes_stale_return(
    opened: bool, current_project_id: str, selected_project_id: str
) -> None:
    tree = ast.parse(APP_SOURCE)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_consume_agent_project_selection_return"
    )
    state: dict[str, object] = {
        "agent_project_selection_return": {
            "origin": "Agent V1 Workspace",
            "return_to": "Agent V1 Workspace",
            "purpose": "select_current_formal_project",
        },
        "mvp_project_id": current_project_id,
    }
    namespace = {
        "Mapping": Mapping,
        "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
        "st": SimpleNamespace(session_state=state),
    }
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)
    assert namespace["_consume_agent_project_selection_return"](
        selected_project_id, opened=opened
    ) is None
    assert "agent_project_selection_return" not in state
    assert "agent_v1_ui_entry_mode" not in state


def test_project_center_open_routes_only_agent_origin_back_to_agent() -> None:
    tree = ast.parse(APP_SOURCE)
    home = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_project_home"
    )
    router = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_change_page"
    )
    home_source = ast.get_source_segment(APP_SOURCE, home) or ""
    router_source = ast.get_source_segment(APP_SOURCE, router) or ""
    assert "_consume_agent_project_selection_return" in home_source
    assert "_opened_project_destination" in home_source
    assert 'st.session_state.pop("agent_project_selection_return", None)' in home_source
    assert 'previous_page == PAGE_PROJECT_HOME' in router_source
    assert 'not st.session_state.get("project_center_open_callback_in_progress")' in router_source


def test_project_resume_priority_and_surface_recording_are_wired() -> None:
    tree = ast.parse(APP_SOURCE)
    functions = {
        node.name: ast.get_source_segment(APP_SOURCE, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    resume = functions["_project_resume_destination"]
    opened = functions["_opened_project_destination"]
    record = functions["_record_current_project_surface"]
    expression = functions["_render_design_workspace"]
    assert "formal_project_last_active_surface" in resume
    assert "_product_surface_route" in resume
    assert "return PAGE_DESIGN_WORKSPACE" in resume
    assert "if explicit_return == PAGE_AGENT_WORKSPACE" in opened
    assert "record_formal_project_active_surface" in record
    assert "_route_product_surface(destination)" in record
    assert 'st.session_state.get("mvp_project_id")' in record
    assert "_record_current_project_surface(PAGE_DESIGN_WORKSPACE)" in expression
    assert "record_active_surface=_record_current_project_surface" in APP_SOURCE


def test_product_surface_labels_map_to_internal_routes_without_injection() -> None:
    tree = ast.parse(APP_SOURCE)
    helpers = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_product_surface_route", "_route_product_surface"}
    ]
    namespace = {
        "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
        "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
    }
    exec(
        compile(ast.Module(body=helpers, type_ignores=[]), str(ROOT / "app.py"), "exec"),
        namespace,
    )

    assert namespace["_product_surface_route"]("Agent V1 Workspace") == "Agent V1 Workspace"
    assert namespace["_product_surface_route"]("Expression Design") == "Six-Step Design Workspace"
    assert namespace["_product_surface_route"]("../../Injected Route") == "Six-Step Design Workspace"
    assert namespace["_route_product_surface"]("Agent V1 Workspace") == "Agent V1 Workspace"
    assert namespace["_route_product_surface"]("Six-Step Design Workspace") == "Expression Design"
    assert namespace["_route_product_surface"]("Project Home") is None


def test_explicit_agent_return_precedes_persisted_project_surface() -> None:
    tree = ast.parse(APP_SOURCE)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_opened_project_destination"
    )
    persisted = Mock(return_value="Expression Design")
    namespace = {
        "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
        "_project_resume_destination": persisted,
    }
    exec(
        compile(ast.Module(body=[helper], type_ignores=[]), str(ROOT / "app.py"), "exec"),
        namespace,
    )

    assert namespace["_opened_project_destination"](
        "project-b", "single_gene", "Agent V1 Workspace"
    ) == "Agent V1 Workspace"
    persisted.assert_not_called()
    assert namespace["_opened_project_destination"](
        "project-b", "single_gene", None
    ) == "Expression Design"
    persisted.assert_called_once_with("project-b", "single_gene")


def test_agent_records_surface_only_for_repository_backed_active_project(tmp_path, monkeypatch) -> None:
    backend = _backend(tmp_path)
    ui = _RenderUI()
    monkeypatch.setattr(workspace, "st", ui)
    record = Mock()

    workspace.render_agent_workspace(
        project_id="agent-ui-project",
        project_name="Agent UI project",
        backend=backend,
        state={},
        record_active_surface=record,
    )
    record.assert_called_once_with("Agent V1 Workspace")

    record.reset_mock()
    workspace.render_agent_workspace(
        project_id="",
        project_name="",
        backend=None,
        state={},
        record_active_surface=record,
    )
    record.assert_not_called()


def test_hydrated_non_first_host_does_not_receive_competing_selectbox_index() -> None:
    tree = ast.parse(APP_SOURCE)
    renderer = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_step_1_project"
    )
    source = ast.get_source_segment(APP_SOURCE, renderer) or ""
    host_call = source.split('host = right.selectbox(', 1)[1].split('\n        )', 1)[0]
    assert '**_formal_widget_initial_kwargs(\n                "formal_step1_host"' in host_call
    assert 'key="formal_step1_host"' in host_call
    assert source.index('if unknown_host and "formal_step1_host" in st.session_state') < source.index(
        'host = right.selectbox('
    )
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_formal_widget_initial_kwargs"
    )
    namespace = {"Any": object, "st": SimpleNamespace(session_state={"formal_step1_host": "Arabidopsis (A. thaliana)"})}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)
    assert namespace["_formal_widget_initial_kwargs"]("formal_step1_host", index=3) == {}


@pytest.mark.parametrize("project_id", ("plant-draft-new", "existing-formal-project"))
def test_needs_input_round_trip_restores_exact_form_values_for_same_project(project_id: str) -> None:
    state: dict[str, object] = {}
    original = {
        "project_id": project_id,
        "workflow_type": "single_gene",
        "host": "Oryza sativa",
        "user_intent": "  保留原始设计请求与首尾空格  ",
        "cds": " partial-reference:ABC-123 ",
        "component_ids": "V2-CMP-001, V2-CMP-042",
    }
    snapshot = _capture_request_form(state, **original)
    state["agent_v1_ui_restore_form_pending"] = True
    for field in ("user_intent", "host", "workflow", "cds", "component_ids"):
        state.pop(f"agent_v1_ui_{field}", None)

    assert _restore_request_form(
        state, project_id=project_id, workflow_type="single_gene"
    ) is True
    assert state["agent_v1_ui_user_intent"] == original["user_intent"]
    assert state["agent_v1_ui_host"] == original["host"]
    assert state["agent_v1_ui_workflow"] == original["workflow_type"]
    assert state["agent_v1_ui_cds"] == original["cds"]
    assert state["agent_v1_ui_component_ids"] == original["component_ids"]
    assert snapshot["project_id"] == project_id


def test_needs_input_snapshot_cannot_cross_project_or_design_type() -> None:
    state: dict[str, object] = {}
    _capture_request_form(
        state,
        project_id="project-a",
        workflow_type="single_gene",
        host="Oryza sativa",
        user_intent="project A request",
        cds="ATG",
        component_ids="",
    )
    state["agent_v1_ui_restore_form_pending"] = True

    assert _restore_request_form(
        state, project_id="project-b", workflow_type="single_gene"
    ) is False
    assert "agent_v1_ui_form_snapshot" not in state
    assert "agent_v1_ui_user_intent" not in state


def test_needs_input_reason_maps_to_localized_copy_and_attention_field() -> None:
    need = AgentNeedInput(
        NeedInputCode.MISSING_CDS_OR_REFERENCE,
        "cds_or_reference_input",
        "A CDS or reference input is required.",
    )
    presentation = _needs_input_presentation((need,))
    rendered = " ".join(
        (presentation["title"], presentation["status"], *presentation["messages"])
    )

    assert presentation["title"] == translate(
        "v1.ai_assisted_design.candidate_not_ready_title", language="en"
    )
    assert presentation["fields"] == ("cds",)
    assert translate(
        "v1.ai_assisted_design.complete_following_information_no_project_changes",
        language="en",
    ) in rendered
    assert "cds_or_reference_input" not in rendered
    assert "A CDS or reference input is required." not in rendered
    assert 'st.warning(f"{need.field}: {need.message}")' not in VIEW_SOURCE


def test_needs_input_missing_roles_render_actionable_product_copy() -> None:
    need = AgentNeedInput(
        NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
        "component_references",
        "raw internal component reason",
        details={"missing_roles": ["promoter", "3_prime_regulatory_region"]},
    )

    presentation = _needs_input_presentation((need,))
    rendered = " ".join(presentation["messages"])

    assert translate("v1.ai_assisted_design.missing_promoter_candidate", language="en") in rendered
    assert translate("v1.ai_assisted_design.missing_three_prime_candidate", language="en") in rendered
    assert translate("v1.ai_assisted_design.complete_following_information_no_project_changes", language="en") not in rendered
    assert "raw internal component reason" not in rendered
    assert presentation["fields"] == ("component_choices",)


def test_needs_input_state_classification_survives_enum_class_reload() -> None:
    reloaded_state = _reloaded_enum_member(AgentRunState.NEEDS_INPUT)
    result = SimpleNamespace(state=reloaded_state)

    assert result.state is not AgentRunState.NEEDS_INPUT
    assert _result_state_is(result, AgentRunState.NEEDS_INPUT) is True


def test_successful_candidate_review_gate_survives_enum_class_reload() -> None:
    def candidate(state, status):
        return SimpleNamespace(
            state=state,
            deterministic_validation=SimpleNamespace(status=status),
        )

    reloaded_validated = _reloaded_enum_member(CandidateState.VALIDATED_CANDIDATE)
    reloaded_auto_generated = _reloaded_enum_member(CandidateState.AUTO_GENERATED)
    reloaded_pass = _reloaded_enum_member(DeterministicValidationStatus.PASS)
    reloaded_blocked = _reloaded_enum_member(DeterministicValidationStatus.BLOCKED)

    assert reloaded_validated is not CandidateState.VALIDATED_CANDIDATE
    assert reloaded_pass is not DeterministicValidationStatus.PASS
    assert _candidate_review_ready(
        candidate(reloaded_validated, reloaded_pass)
    ) is True
    assert _candidate_review_ready(
        candidate(reloaded_validated, reloaded_blocked)
    ) is False
    assert _candidate_review_ready(
        candidate(reloaded_auto_generated, reloaded_pass)
    ) is False
    assert _candidate_review_ready(
        candidate("UNKNOWN_STATE", "UNKNOWN_STATUS")
    ) is False
    assert _candidate_review_ready(SimpleNamespace()) is False


def test_successful_candidate_hot_reload_keeps_review_content_and_action_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    class CandidateUI(_RenderUI):
        def __init__(self):
            super().__init__()
            self.buttons: list[tuple[str, str | None, bool]] = []

        def button(self, label, *args, key=None, disabled=False, **kwargs):
            self.buttons.append((str(label), key, bool(disabled)))
            return key == "agent_review_adoption" and not disabled

    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    object.__setattr__(
        candidate,
        "state",
        _reloaded_enum_member(CandidateState.VALIDATED_CANDIDATE),
    )
    object.__setattr__(
        candidate.deterministic_validation,
        "status",
        _reloaded_enum_member(DeterministicValidationStatus.PASS),
    )
    ui = CandidateUI()
    monkeypatch.setattr(workspace, "st", ui)
    state = {}

    assert _candidate_review_ready(candidate) is True
    with pytest.raises(_RenderRerun):
        workspace._render_candidate(candidate, backend, state)

    rendered = "\n".join(ui.output)
    assert candidate.candidate_id in rendered
    assert candidate.rationale in rendered
    assert translate("v1.ai_assisted_design.candidate_notes", language="en") in rendered
    assert translate("v1.ai_assisted_design.deterministic_check", language="en", value="")[:20] in rendered
    assert "PASS" in rendered
    assert translate("v1.ai_assisted_design.source_records", language="en") in rendered
    assert (translate("v1.ai_assisted_design.review_adoption", language="en"), "agent_review_adoption", False) in ui.buttons
    assert state["agent_v1_ui_adoption_preview"].candidate_id == candidate.candidate_id
    assert state["agent_v1_ui_selected_candidate_id"] == candidate.candidate_id
    assert state["agent_v1_ui_screen"] == "adoption"


def _invalid_enum_boundary_value(expected: Enum, case: str):
    if case == "raw_string":
        return expected.value
    if case == "value_like":
        return SimpleNamespace(name=expected.name, value=expected.value)
    if case == "unrelated_family":
        family = Enum(
            f"Unrelated{type(expected).__name__}",
            {expected.name: expected.value},
            type=str,
        )
        return family[expected.name]
    if case == "same_name_and_value":
        family = Enum(
            type(expected).__name__,
            {expected.name: expected.value},
            type=str,
            module="tests.enum_impostor",
            qualname=type(expected).__qualname__,
        )
        return family[expected.name]
    if case == "wrong_member":
        return next(member for member in type(expected) if member.value != expected.value)
    if case == "missing":
        return None
    if case == "malformed":
        return object()
    raise AssertionError(f"unknown boundary case: {case}")


_ENUM_NEGATIVE_CASES = (
    "raw_string",
    "value_like",
    "unrelated_family",
    "same_name_and_value",
    "wrong_member",
    "missing",
    "malformed",
)


@pytest.mark.parametrize(
    "expected",
    (AgentRunState.NEEDS_INPUT, AgentRunState.FAILED, AgentRunState.ALTERNATIVES),
)
@pytest.mark.parametrize("case", _ENUM_NEGATIVE_CASES)
def test_result_state_routing_rejects_non_family_values(
    expected: AgentRunState, case: str
) -> None:
    value = _invalid_enum_boundary_value(expected, case)

    assert _result_state_is(SimpleNamespace(state=value), expected) is False


@pytest.mark.parametrize(
    "expected",
    (CandidateState.VALIDATED_CANDIDATE, DeterministicValidationStatus.PASS),
)
@pytest.mark.parametrize("case", _ENUM_NEGATIVE_CASES)
def test_service_enum_boundary_rejects_non_family_values(
    expected: Enum, case: str
) -> None:
    value = _invalid_enum_boundary_value(expected, case)

    assert _trusted_enum_value_is(value, expected) is False


@pytest.mark.parametrize("target", ("candidate_state", "validation_status"))
@pytest.mark.parametrize("case", _ENUM_NEGATIVE_CASES)
def test_preview_and_confirmation_fail_closed_for_non_family_values(
    tmp_path: Path, target: str, case: str
) -> None:
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    if target == "candidate_state":
        value = _invalid_enum_boundary_value(
            CandidateState.VALIDATED_CANDIDATE, case
        )
        object.__setattr__(candidate, "state", value)
    else:
        value = _invalid_enum_boundary_value(
            DeterministicValidationStatus.PASS, case
        )
        object.__setattr__(candidate.deterministic_validation, "status", value)

    with pytest.raises(AgentServiceError):
        backend.service.build_adoption_preview(candidate)
    with pytest.raises(AgentServiceError):
        backend.service.confirm_candidate(
            candidate,
            confirmation_id="enum-negative-confirmation",
            preview=preview,
        )


def test_genuine_reload_candidate_traverses_full_adoption_and_cold_readback(
    tmp_path: Path,
) -> None:
    script = textwrap.dedent(
        r"""
        import importlib
        import runpy
        import sys
        from pathlib import Path

        root = Path(sys.argv[1])
        temp_root = Path(sys.argv[2])
        helpers = runpy.run_path(str(root / "tests" / "test_agent_v1_ui_backend_wiring.py"))
        backend = helpers["_backend"](temp_root)
        candidate = backend.generate_and_validate(helpers["_request"]()).candidates[0]

        import services.agent_contracts as contracts
        import services.agent_candidate_store as candidate_store
        from views import AgentWorkspace as workspace

        reloaded = importlib.reload(contracts)
        object.__setattr__(candidate, "state", reloaded.CandidateState.VALIDATED_CANDIDATE)
        object.__setattr__(
            candidate.deterministic_validation,
            "status",
            reloaded.DeterministicValidationStatus.PASS,
        )
        assert workspace._candidate_review_ready(candidate)

        class ReviewUI(helpers["_RenderUI"]):
            def button(self, label, *args, key=None, disabled=False, **kwargs):
                return key == "agent_review_adoption" and not disabled

        state = {}
        workspace.st = ReviewUI()
        try:
            workspace._render_candidate(candidate, backend, state)
        except helpers["_RenderRerun"]:
            pass
        else:
            raise AssertionError("review action did not rerun")
        assert state["agent_v1_ui_screen"] == "adoption"
        assert state["agent_v1_ui_adoption_preview"].candidate_id == candidate.candidate_id
        assert not list(backend.store.receipts_dir.glob("*.json"))

        confirmed = backend.service.confirm_candidate(
            candidate,
            confirmation_id="genuine-reload-explicit-confirmation",
            preview=state["agent_v1_ui_adoption_preview"],
        )
        assert confirmed.human_confirmation_state == "genuine-reload-explicit-confirmation"
        assert confirmed.state.value == "VALIDATED_CANDIDATE"
        assert "agent_v1_ui_adoption_receipt" not in state
        assert not list(backend.store.receipts_dir.glob("*.json"))

        persisted = backend.store.load_payload(confirmed.candidate_id, verify=True)
        reconstructed = candidate_store.candidate_from_dict(persisted)
        assert type(reconstructed) is reloaded.AgentCandidate
        assert type(reconstructed.deterministic_validation) is reloaded.AgentValidationSummary
        assert type(reconstructed.state) is reloaded.CandidateState
        assert type(reconstructed.deterministic_validation.status) is reloaded.DeterministicValidationStatus

        digest = reloaded.candidate_digest(confirmed)
        receipt = backend.adopt(reloaded.AdoptionRequest(
            confirmed.candidate_id,
            "agent-ui-project",
            digest,
            "genuine-reload-explicit-confirmation",
        ))
        assert backend.store.receipt_is_authoritative(receipt.receipt_id)

        reopened = helpers["_reopen_backend"](temp_root)
        readback = workspace._load_adopted_readback(reopened, "agent-ui-project")
        assert readback is not None
        cold_candidate, cold_receipt = readback
        cold_payload = reopened.store.load_payload(cold_candidate.candidate_id, verify=True)
        assert cold_candidate.candidate_id == confirmed.candidate_id
        assert cold_candidate.request_id == confirmed.request_id
        assert cold_candidate.state is reloaded.CandidateState.USER_ADOPTED
        assert cold_candidate.deterministic_validation.status is reloaded.DeterministicValidationStatus.PASS
        assert cold_receipt.receipt_id == receipt.receipt_id
        assert cold_receipt.project_id == "agent-ui-project"
        assert cold_receipt.candidate_id == confirmed.candidate_id
        assert cold_receipt.candidate_digest == digest
        assert cold_receipt.candidate_revision == cold_payload["candidate_revision"]
        print("READY_PASS")
        print("PREVIEW_PASS")
        print("CONFIRMATION_PASS")
        print("ADOPTION_PASS")
        print("RECEIPT_PASS")
        print("COLD_READBACK_PASS")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    for stage in (
        "READY_PASS",
        "PREVIEW_PASS",
        "CONFIRMATION_PASS",
        "ADOPTION_PASS",
        "RECEIPT_PASS",
        "COLD_READBACK_PASS",
    ):
        assert stage in completed.stdout


def test_cross_generation_adoption_rejects_tampered_or_malformed_persistence(
    tmp_path: Path,
) -> None:
    script = textwrap.dedent(
        r"""
        import copy
        import importlib
        import runpy
        import sys
        from dataclasses import dataclass
        from enum import Enum
        from pathlib import Path
        from types import SimpleNamespace

        root = Path(sys.argv[1])
        temp_root = Path(sys.argv[2])
        helpers = runpy.run_path(str(root / "tests" / "test_agent_v1_ui_backend_wiring.py"))
        cases = {}
        for name in (
            "forged_revision",
            "changed_digest",
            "altered_validation",
            "contradictory_state",
            "malformed_payload",
        ):
            backend = helpers["_backend"](temp_root / name)
            candidate = backend.generate_and_validate(helpers["_request"]()).candidates[0]
            cases[name] = (backend, candidate)

        import services.agent_contracts as contracts
        import services.agent_candidate_store as candidate_store
        from views import AgentWorkspace as workspace

        reloaded = importlib.reload(contracts)
        for name, (backend, candidate) in cases.items():
            object.__setattr__(candidate, "state", reloaded.CandidateState.VALIDATED_CANDIDATE)
            object.__setattr__(candidate.deterministic_validation, "status", reloaded.DeterministicValidationStatus.PASS)
            preview = backend.service.build_adoption_preview(candidate)
            confirmed = backend.service.confirm_candidate(
                candidate,
                confirmation_id=f"cross-generation-{name}",
                preview=preview,
            )
            digest = reloaded.candidate_digest(confirmed)
            payload = backend.store.load_payload(confirmed.candidate_id, verify=True)
            tampered = copy.deepcopy(payload)
            if name == "forged_revision":
                tampered["candidate_revision"] = 999
            elif name == "changed_digest":
                tampered["content_digest"] = "0" * 64
            elif name == "altered_validation":
                tampered["deterministic_validation"]["status"] = "BLOCKED"
                tampered["deterministic_validation"]["blocking_reasons"] = ["tampered"]
            elif name == "contradictory_state":
                tampered["state"] = "AUTO_GENERATED"
            else:
                tampered["deterministic_validation"] = ["not", "a", "mapping"]

            if name != "forged_revision":
                tampered = backend.store._authenticated(tampered)
            backend.store._atomic(
                backend.store.candidates_dir / f"{confirmed.candidate_id}.json",
                tampered,
            )
            before = backend.adoption.formal_repository.load("agent-ui-project").to_dict()
            try:
                backend.adopt(reloaded.AdoptionRequest(
                    confirmed.candidate_id,
                    "agent-ui-project",
                    digest,
                    f"cross-generation-{name}",
                ))
            except candidate_store.CandidateStoreError:
                pass
            else:
                raise AssertionError(f"{name} did not fail closed")
            assert backend.adoption.formal_repository.load("agent-ui-project").to_dict() == before
            assert not list(backend.store.receipts_dir.glob("*.json"))
            assert backend.store.list_journal()[-1]["status"] == "FAILED"
            assert workspace._load_adopted_readback(backend, "agent-ui-project") is None

        valid_payload = cases["changed_digest"][0].store.load_payload(
            cases["changed_digest"][1].candidate_id,
            verify=True,
        )
        ForeignState = Enum(
            "CandidateState",
            {"VALIDATED_CANDIDATE": "VALIDATED_CANDIDATE"},
            type=str,
            module="unrelated.contracts",
        )

        @dataclass(frozen=True)
        class ForeignValidation:
            status: object

        rejected = 0
        for field, impostor in (
            ("state", ForeignState.VALIDATED_CANDIDATE),
            ("state", SimpleNamespace(value="VALIDATED_CANDIDATE")),
            ("deterministic_validation", ForeignValidation("PASS")),
        ):
            malformed = copy.deepcopy(valid_payload)
            malformed[field] = impostor
            try:
                candidate_store.candidate_from_dict(malformed)
            except (TypeError, ValueError):
                rejected += 1
        assert rejected == 3
        print("NEGATIVE_PERSISTENCE_MATRIX_PASS")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "NEGATIVE_PERSISTENCE_MATRIX_PASS" in completed.stdout


def test_genuine_reload_governed_component_traverses_host_gate_and_cold_readback(
    tmp_path: Path,
) -> None:
    script = textwrap.dedent(
        r"""
        import importlib
        import runpy
        import sys
        from pathlib import Path

        root = Path(sys.argv[1])
        temp_root = Path(sys.argv[2])
        helpers = runpy.run_path(
            str(root / "tests" / "test_formal_agent_host_gate_reconciliation_r1.py")
        )
        backend, request, formal = helpers["_adoption_fixture"](
            temp_root,
            scope=[helpers["RICE"]],
        )

        import services.agent_contracts as contracts
        import services.agent_candidate_store as candidate_store
        from views import AgentWorkspace as workspace

        reloaded = importlib.reload(contracts)
        payload = backend.store.load_payload(request.candidate_id, verify=True)
        reconstructed = candidate_store.candidate_from_dict(payload)
        assert type(reconstructed.component_references[0].tier) is reloaded.ComponentTier
        assert candidate_store._validator_accepts_component_generation(
            backend._revalidate_adoption_authority,
            reconstructed,
        )
        assert workspace._candidate_review_ready(reconstructed)

        host_gate_calls = []
        original_host_gate = backend.service.component_repository.host_applicability_status
        def tracked_host_gate(component_id, host):
            host_gate_calls.append((component_id, host))
            return original_host_gate(component_id, host)
        backend.service.component_repository.host_applicability_status = tracked_host_gate

        receipt = backend.adopt(reloaded.AdoptionRequest(
            request.candidate_id,
            request.project_id,
            request.candidate_digest,
            request.confirmation_token,
        ))
        assert host_gate_calls == [("V2-CMP-138", helpers["RICE"])]
        assert backend.store.receipt_is_authoritative(receipt.receipt_id)
        assert formal.load("adoption-project").extra_fields["agent_adoption"]["candidate_id"] == request.candidate_id

        reopened = helpers["AgentBackend"](
            helpers["QwenProvider"](
                config=helpers["QwenConfig"](model="host-gate-test"),
                transport=helpers["FakeQwenTransport"](),
            ),
            candidate_store=candidate_store.CandidateStore(temp_root / "agent"),
            project_repository=helpers["PlantProjectDraftRepository"](temp_root / "formal"),
            component_repository=helpers["_AdoptionRepository"](
                backend.service.component_repository.row
            ),
        )
        readback = workspace._load_adopted_readback(reopened, "adoption-project")
        assert readback is not None
        cold_candidate, cold_receipt = readback
        assert cold_candidate.state is reloaded.CandidateState.USER_ADOPTED
        assert cold_candidate.deterministic_validation.status is reloaded.DeterministicValidationStatus.PASS
        assert cold_receipt.receipt_id == receipt.receipt_id
        print("READY_PASS")
        print("PREVIEW_PASS")
        print("CONFIRMATION_PASS")
        print("HOST_GATE_PASS")
        print("ADOPTION_PASS")
        print("RECEIPT_PASS")
        print("COLD_READBACK_PASS")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    for stage in (
        "READY_PASS",
        "PREVIEW_PASS",
        "CONFIRMATION_PASS",
        "HOST_GATE_PASS",
        "ADOPTION_PASS",
        "RECEIPT_PASS",
        "COLD_READBACK_PASS",
    ):
        assert stage in completed.stdout


def test_cross_generation_component_host_gate_negative_matrix(tmp_path: Path) -> None:
    script = textwrap.dedent(
        r"""
        import copy
        import importlib
        import runpy
        import sys
        from enum import Enum
        from pathlib import Path
        from types import SimpleNamespace

        root = Path(sys.argv[1])
        temp_root = Path(sys.argv[2])
        helpers = runpy.run_path(
            str(root / "tests" / "test_formal_agent_host_gate_reconciliation_r1.py")
        )
        backend, request, formal = helpers["_adoption_fixture"](
            temp_root,
            scope=[helpers["RICE"]],
        )

        import services.agent_contracts as contracts
        import services.agent_candidate_store as candidate_store

        reloaded = importlib.reload(contracts)
        payload = backend.store.load_payload(request.candidate_id, verify=True)
        candidate = candidate_store.candidate_from_dict(payload)
        before = formal.load("adoption-project").to_dict()

        UnrelatedTier = Enum(
            "UnrelatedTier",
            {"DIRECT_USE": "DIRECT_USE"},
            type=str,
            module="tests.unrelated_tier",
        )
        LookalikeTier = Enum(
            "ComponentTier",
            {"DIRECT_USE": "DIRECT_USE"},
            type=str,
            module="tests.lookalike_tier",
            qualname="ComponentTier",
        )
        tier_cases = {
            "wrong_member": reloaded.ComponentTier.REFERENCE_ONLY,
            "reference_only": reloaded.ComponentTier.REFERENCE_ONLY,
            "user_sequence_assisted": reloaded.ComponentTier.USER_SEQUENCE_ASSISTED,
            "unrelated_same_value": UnrelatedTier.DIRECT_USE,
            "unrelated_same_name_value": LookalikeTier.DIRECT_USE,
            "raw_string": "DIRECT_USE",
            "value_like": SimpleNamespace(value="DIRECT_USE"),
            "missing": None,
            "malformed": object(),
        }
        for name, tier in tier_cases.items():
            altered = copy.deepcopy(candidate)
            reference = copy.deepcopy(altered.component_references[0])
            object.__setattr__(reference, "tier", tier)
            object.__setattr__(altered, "component_references", (reference,))
            guarded = candidate_store._validator_accepts_component_generation(
                backend._revalidate_adoption_authority,
                altered,
            )
            if name in {"wrong_member", "reference_only", "user_sequence_assisted"}:
                assert guarded
            else:
                assert not guarded
            rejected = backend._revalidate_adoption_authority(altered)
            assert rejected.deterministic_validation.status.value == "BLOCKED"
            assert rejected.deterministic_validation.blocking_reasons == (
                "component_tier_mismatch:V2-CMP-138",
            )

        wrong_host = copy.deepcopy(candidate)
        object.__setattr__(wrong_host, "host", helpers["TOMATO"])
        rejected = backend._revalidate_adoption_authority(wrong_host)
        assert rejected.deterministic_validation.blocking_reasons == (
            "HOST_APPLICABILITY_WRONG_HOST",
        )

        non_admitted = copy.deepcopy(candidate)
        reference = copy.deepcopy(non_admitted.component_references[0])
        object.__setattr__(reference, "component_id", "NOT-ADMITTED")
        object.__setattr__(non_admitted, "component_references", (reference,))
        rejected = backend._revalidate_adoption_authority(non_admitted)
        assert rejected.deterministic_validation.blocking_reasons == (
            "component_not_resolved:NOT-ADMITTED",
        )

        backend.service.component_repository.row["host_applicability"] = {}
        try:
            backend.adopt(reloaded.AdoptionRequest(
                request.candidate_id,
                request.project_id,
                request.candidate_digest,
                request.confirmation_token,
            ))
        except candidate_store.CandidateStoreError as exc:
            assert str(exc) == "deterministic_validation_failed"
        else:
            raise AssertionError("stale Host Gate evidence did not fail closed")

        assert formal.load("adoption-project").to_dict() == before
        assert not list(backend.store.receipts_dir.glob("*.json"))
        assert backend.store.list_journal()[-1]["status"] == "FAILED"
        print("NEGATIVE_HOST_GATE_MATRIX_PASS")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "NEGATIVE_HOST_GATE_MATRIX_PASS" in completed.stdout


@pytest.mark.parametrize(
    ("state_value", "validation_value"),
    (
        ("VALIDATED_CANDIDATE", "BLOCKED"),
        ("AUTO_GENERATED", "PASS"),
        ("MALFORMED", "PASS"),
        ("VALIDATED_CANDIDATE", None),
        (None, "PASS"),
        ("UNKNOWN_STATE", "PASS"),
    ),
)
def test_adoption_preview_rejects_invalid_cross_generation_states(
    tmp_path: Path,
    state_value: str | None,
    validation_value: str | None,
) -> None:
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    if state_value is None:
        object.__setattr__(candidate, "state", None)
    else:
        ReloadedCandidateState = Enum(
            "ReloadedCandidateState",
            {state_value: state_value},
            type=str,
        )
        object.__setattr__(candidate, "state", ReloadedCandidateState[state_value])
    if validation_value is None:
        object.__setattr__(candidate, "deterministic_validation", None)
    else:
        ReloadedValidationStatus = Enum(
            "ReloadedValidationStatus",
            {validation_value: validation_value},
            type=str,
        )
        object.__setattr__(
            candidate.deterministic_validation,
            "status",
            ReloadedValidationStatus[validation_value],
        )

    with pytest.raises(AgentServiceError):
        backend.service.build_adoption_preview(candidate)


def test_adoption_preview_does_not_trust_raw_state_strings(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    object.__setattr__(candidate, "state", "VALIDATED_CANDIDATE")
    object.__setattr__(candidate.deterministic_validation, "status", "PASS")

    with pytest.raises(AgentServiceError):
        backend.service.build_adoption_preview(candidate)


@pytest.mark.parametrize(
    "mutation",
    ("raw_strings", "value_like", "unrelated_enum"),
)
def test_review_action_rejects_nonsemantic_enum_values_without_partial_adoption(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    class ReviewUI(_RenderUI):
        def __init__(self):
            super().__init__()
            self.buttons: list[tuple[str, str | None, bool]] = []

        def button(self, label, *args, key=None, disabled=False, **kwargs):
            self.buttons.append((str(label), key, bool(disabled)))
            return False

    backend = _backend(tmp_path)
    candidate = backend.generate_and_validate(_request()).candidates[0]
    if mutation == "raw_strings":
        object.__setattr__(candidate, "state", "VALIDATED_CANDIDATE")
        object.__setattr__(candidate.deterministic_validation, "status", "PASS")
    elif mutation == "value_like":
        object.__setattr__(candidate, "state", SimpleNamespace(value="VALIDATED_CANDIDATE"))
        object.__setattr__(candidate.deterministic_validation, "status", SimpleNamespace(value="PASS"))
    else:
        UnrelatedCandidateState = Enum(
            "CandidateState",
            {"VALIDATED_CANDIDATE": "VALIDATED_CANDIDATE"},
            type=str,
        )
        object.__setattr__(candidate, "state", UnrelatedCandidateState.VALIDATED_CANDIDATE)

    build_preview = Mock(wraps=backend.service.build_adoption_preview)
    monkeypatch.setattr(backend.service, "build_adoption_preview", build_preview)
    ui = ReviewUI()
    monkeypatch.setattr(workspace, "st", ui)
    state = {}

    assert _candidate_review_ready(candidate) is False
    workspace._render_candidate(candidate, backend, state)

    build_preview.assert_not_called()
    assert (translate("v1.ai_assisted_design.review_adoption", language="en"), "agent_review_adoption", True) in ui.buttons
    assert "agent_v1_ui_selected_candidate_id" not in state
    assert "agent_v1_ui_adoption_preview" not in state
    assert "agent_v1_ui_adoption_receipt" not in state
    assert "agent_v1_ui_screen" not in state
    assert not list(backend.store.receipts_dir.glob("*.json"))


def test_unknown_needs_input_reason_fails_safe_without_raw_backend_text() -> None:
    need = SimpleNamespace(
        code="UNRECOGNIZED_INTERNAL_CODE",
        field="internal_validation_field",
        message="raw backend exception detail",
    )
    presentation = _needs_input_presentation((need,))
    rendered = " ".join(
        (presentation["title"], presentation["status"], *presentation["messages"])
    )

    assert presentation["title"] == translate(
        "v1.ai_assisted_design.candidate_not_ready_title", language="en"
    )
    assert presentation["fields"] == ()
    assert "internal_validation_field" not in rendered
    assert "raw backend exception detail" not in rendered


@pytest.mark.parametrize(
    ("code", "field", "attention"),
    (
        (NeedInputCode.MISSING_VERIFIED_SEQUENCE, "component_V2-CMP-001_sequence", "component_ids"),
        (NeedInputCode.ASSISTED_COMPONENT_SEQUENCE_REQUIRED, "component_V2-CMP-002_sequence", "component_ids"),
        (NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED, "component_V2-CMP-003_admission", "component_ids"),
        (NeedInputCode.PROVIDER_FAILURE, "provider_internal", None),
    ),
)
def test_known_dynamic_needs_input_codes_never_expose_internal_fields(
    code: NeedInputCode, field: str, attention: str | None
) -> None:
    presentation = _needs_input_presentation(
        (AgentNeedInput(code, field, "raw English backend reason"),)
    )
    rendered = " ".join(
        (presentation["title"], presentation["status"], *presentation["messages"])
    )

    assert presentation["fields"] == ((attention,) if attention else ())
    assert field not in rendered
    assert "raw English backend reason" not in rendered


def test_missing_cds_and_components_stay_local_and_keep_formal_project(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "formal")
    draft = repository.create_blank(project_name="Round-trip project")
    draft.project_id = "same-formal-project"
    repository.save(draft)
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(
            config=QwenConfig(model="agent-ui-test-model"),
            transport=transport,
        ),
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=repository,
        component_repository=ProductComponentRepository(),
    )
    before = repository.load(draft.project_id).to_dict()
    incomplete = AgentRequest(
        workflow_type="single_gene",
        host="Oryza sativa",
        user_intent="Preserve this exact request",
        cds_or_reference_input=None,
        project_id=draft.project_id,
        context={"project_id": draft.project_id},
    )

    needs_input = backend.generate_and_validate(incomplete)
    assert needs_input.state is AgentRunState.NEEDS_INPUT
    assert transport.calls == []
    assert repository.load(draft.project_id).to_dict() == before
    assert len(repository.list_summaries()) == 1

    completed = AgentRequest(
        workflow_type=incomplete.workflow_type,
        host=incomplete.host,
        user_intent=incomplete.user_intent,
        cds_or_reference_input="reference:ABC-123",
        project_id=incomplete.project_id,
        context=incomplete.context,
    )
    result = backend.generate_and_validate(completed)
    assert result.state is AgentRunState.NEEDS_INPUT
    assert result.candidates == ()
    assert any(need.field == "component_references" for need in result.needs_input)
    assert transport.calls == []
    assert len(repository.list_summaries()) == 1
    assert repository.load(draft.project_id).to_dict() == before


def test_needs_input_click_rerun_keeps_rice_form_and_skips_candidate_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "formal")
    draft = create_agent_formal_draft(
        project_name="Rice Agent UI project",
        host="Oryza sativa",
        workflow_type="single_gene",
        design_goal="保留这个水稻设计请求",
        repository=repository,
    )
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="agent-ui-test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent-state"),
        project_repository=repository,
        component_repository=ProductComponentRepository(),
    )
    state: dict[str, object] = {
        "agent_v1_ui_backend_project_id": draft.project_id,
        "agent_v1_ui_entry_mode": "current",
        "agent_v1_ui_user_intent": draft.plant_design_goal,
        "agent_v1_ui_host": "Oryza sativa",
        "agent_v1_ui_cds": "",
    }
    before_formal = repository.load(draft.project_id).to_dict()
    before_candidates = tuple(backend.store.candidates_dir.glob("*.json"))
    ui = _NeedsInputRenderUI(state, click_generate=True)
    monkeypatch.setattr(workspace, "st", ui)

    with pytest.raises(_RenderRerun):
        workspace.render_agent_workspace(
            project_id=draft.project_id,
            project_name=draft.project_name,
            project_type="single_gene",
            project_host=draft.host_context,
            backend=backend,
            state=state,
        )

    assert "agent_v1_ui_run_result" in state, state
    result = state["agent_v1_ui_run_result"]
    assert _result_state_is(result, AgentRunState.NEEDS_INPUT)
    assert state["agent_v1_ui_screen"] == "initial"
    assert state["agent_v1_ui_user_intent"] == draft.plant_design_goal
    assert state["agent_v1_ui_host"] == "Oryza sativa"
    assert state["agent_v1_ui_cds"] == ""
    assert transport.calls == []
    assert repository.load(draft.project_id).to_dict() == before_formal
    assert tuple(backend.store.candidates_dir.glob("*.json")) == before_candidates

    ui.output.clear()
    workspace.render_agent_workspace(
        project_id=draft.project_id,
        project_name=draft.project_name,
        project_type="single_gene",
        project_host=draft.host_context,
        backend=backend,
        state=state,
    )
    rendered = "\n".join(ui.output)

    assert "Rice Agent UI project" in rendered
    assert translate("runtime.host_rice", language="en") in rendered
    expected_copy = (
        "v1.ai_assisted_design.candidate_not_ready_title",
        "v1.ai_assisted_design.provide_cds_sequence_cite_traceable_sequence_reference",
        "v1.ai_assisted_design.missing_promoter_candidate",
        "v1.ai_assisted_design.missing_three_prime_candidate",
        "v1.ai_assisted_design.describe_plant_expression_design_review",
        "v1.ai_assisted_design.cds_traceable_sequence_reference",
        "v1.ai_assisted_design.available_components",
    )
    assert all(translate(key, language="en") in rendered for key in expected_copy)
    assert translate(
        "v1.ai_assisted_design.backend_returned_no_reviewable_candidates_no_changes",
        language="en",
    ) not in rendered
    assert "候选说明" not in rendered
    assert state["agent_v1_ui_screen"] == "initial"
    assert state["agent_v1_ui_user_intent"] == draft.plant_design_goal
    assert transport.calls == []
    assert repository.load(draft.project_id).to_dict() == before_formal
    assert tuple(backend.store.candidates_dir.glob("*.json")) == before_candidates


def test_needs_input_return_contract_preserves_recovery_and_receipt_paths() -> None:
    assert 'state[_key("restore_form_pending")] = True' in VIEW_SOURCE
    assert '_restore_request_form(state, project_id=project_id, workflow_type=workflow_type)' in VIEW_SOURCE
    assert "receipt_is_authoritative" in VIEW_SOURCE
    assert "RECOVERY_REQUIRED" in VIEW_SOURCE
