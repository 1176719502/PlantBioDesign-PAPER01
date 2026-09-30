from __future__ import annotations

import ast
import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from services.agent_candidate_store import CandidateStore, CandidateStoreError
from services.agent_contracts import (
    AdoptionRequest,
    AgentRequest,
    ComponentRecord,
    ComponentReference,
    ComponentTier,
)
from services.agent_provider import FakeQwenTransport, QwenConfig, QwenProvider
from services.agent_service import (
    AgentBackend,
    ProductComponentRepository,
    V2ComponentRepository,
    component_governance_needs,
)
from services.component_library_v2_adoption import (
    V2AdoptionError,
    build_v2_direct_selection,
    validate_v2_direct_selection,
    v2_canonical_record,
)
from services.formal_step3_component_authority import (
    formal_step3_component_options,
    revalidated_formal_step3_selection,
)
from services.plant_component_workflow_registry import (
    HOST_APPLICABILITY_ADMITTED,
    HOST_APPLICABILITY_NOT_PROVEN,
    HOST_APPLICABILITY_WRONG_HOST,
    host_applicability_gate,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from scripts.acceptance.ui04a_acceptance_seed import build_formal_editor_completed
from tests.helpers.fake_streamlit import FakeStreamlit


RICE = "Oryza sativa"
TOMATO = "Solanum lycopersicum"
ROOT = Path(__file__).resolve().parents[1]


def _v2_row_with_scope(scope: list[str]) -> dict:
    row = copy.deepcopy(v2_canonical_record("V2-CMP-138"))
    row["host_applicability"] = {
        "status": "reviewed",
        "scope": scope,
        "evidence_source": "controlled-test",
        "evidence_version": "r1",
        "limitation": "Test fixture only.",
    }
    return row


@pytest.mark.parametrize(
    ("evidence", "host", "expected"),
    [
        ({"status": "reviewed", "scope": [RICE], "evidence_source": "x", "evidence_version": "1", "limitation": "x"}, RICE, HOST_APPLICABILITY_ADMITTED),
        ({"status": "reviewed", "scope": [RICE], "evidence_source": "x", "evidence_version": "1", "limitation": "x"}, TOMATO, HOST_APPLICABILITY_WRONG_HOST),
        ({}, RICE, HOST_APPLICABILITY_NOT_PROVEN),
        ({"status": "reviewed", "scope": [], "evidence_source": "x", "evidence_version": "1", "limitation": "x"}, RICE, HOST_APPLICABILITY_NOT_PROVEN),
        ({"status": "unreviewed", "scope": [RICE], "evidence_source": "x", "evidence_version": "1", "limitation": "x"}, RICE, HOST_APPLICABILITY_NOT_PROVEN),
    ],
)
def test_registry_and_agent_share_host_gate(evidence, host, expected):
    row = copy.deepcopy(v2_canonical_record("V2-CMP-138"))
    row["host_applicability"] = evidence
    repository = V2ComponentRepository([row])
    record = repository.resolve("V2-CMP-138")
    reference = ComponentReference(
        component_id="V2-CMP-138",
        role="promoter",
        tier=ComponentTier.DIRECT_USE,
        sequence_sha256=record.sequence_sha256,
    )
    needs = component_governance_needs(
        AgentRequest(
            workflow_type="single_gene",
            host=host,
            user_intent="parity",
            cds_or_reference_input="ATGAAATAA",
            component_references=(reference,),
        ),
        repository,
    )
    statuses = {need.details.get("status") for need in needs if need.details.get("status")}
    assert host_applicability_gate(row, host) == expected
    assert (next(iter(statuses), HOST_APPLICABILITY_ADMITTED)) == expected


def test_empty_scope_is_not_wildcard_and_formal_options_fail_closed():
    row = v2_canonical_record("V2-CMP-138")
    assert host_applicability_gate(row, RICE) == HOST_APPLICABILITY_NOT_PROVEN
    with pytest.raises(V2AdoptionError):
        build_v2_direct_selection(row, role="promoter", requested_host=RICE)
    assert formal_step3_component_options(role="promoter", target_host_species=RICE) == []
    assert formal_step3_component_options(role="3_prime_regulatory_region", target_host_species=RICE) == []


def test_reviewed_scope_and_current_selection_revalidation(monkeypatch):
    import services.component_library_v2_adoption as v2

    row = _v2_row_with_scope([RICE])
    monkeypatch.setattr(v2, "v2_canonical_record", lambda _id: copy.deepcopy(row))
    selection = build_v2_direct_selection(row, role="promoter", requested_host=RICE)
    assert validate_v2_direct_selection(selection, role="promoter", sequence=selection["selected_sequence"], requested_host=RICE) == selection
    row["host_applicability"] = {}
    with pytest.raises(V2AdoptionError):
        validate_v2_direct_selection(selection, role="promoter", sequence=selection["selected_sequence"], requested_host=RICE)
    with pytest.raises(V2AdoptionError):
        validate_v2_direct_selection(selection, role="promoter", sequence=selection["selected_sequence"], requested_host=TOMATO)


def test_generic_v2_selection_remains_hostless():
    selection = build_v2_direct_selection(v2_canonical_record("V2-CMP-138"), role="promoter")
    assert selection["workflow_context"] == "generic_multi_tu"
    assert "requested_host" not in selection


def test_formal_saved_selection_requires_current_exact_registry_evidence():
    evidence = {
        "status": "reviewed",
        "scope": [RICE],
        "evidence_source": "controlled-test",
        "evidence_version": "r1",
        "limitation": "Test fixture only.",
    }
    saved = {
        "normalized_sequence": "ACGT",
        "source_kind": "registry",
        "component_reference": {
            "source_type": "REGISTRY",
            "registry_component_id": "CURRENT-COMPONENT",
            "tu_role": "promoter",
            "requested_host": RICE,
            "host_applicability_at_selection": evidence,
        },
    }
    current = {
        "registry_component_id": "CURRENT-COMPONENT",
        "sequence": "ACGT",
        "component_reference": {
            "source_type": "REGISTRY",
            "registry_component_id": "CURRENT-COMPONENT",
            "tu_role": "promoter",
            "requested_host": RICE,
            "host_applicability_at_selection": evidence,
        },
        "formal_selectable": True,
    }
    assert revalidated_formal_step3_selection(saved, role="promoter", target_host_species=RICE, options=[current]) == current
    current["component_reference"]["host_applicability_at_selection"] = {}
    assert revalidated_formal_step3_selection(saved, role="promoter", target_host_species=RICE, options=[current]) is None


def test_product_repository_keeps_non_direct_tiers_unchanged():
    repository = ProductComponentRepository()
    rows = repository.list_rows()
    reference_id = next(row["canonical_v2_component_id"] for row in rows if row.get("admission_mode") == "REFERENCE_ONLY")
    assisted_id = next(row["canonical_v2_component_id"] for row in rows if row.get("admission_mode") == "USER_SEQUENCE_ASSISTED")
    assert repository.resolve(reference_id).tier is ComponentTier.REFERENCE_ONLY
    assert repository.resolve(assisted_id).tier is ComponentTier.USER_SEQUENCE_ASSISTED


class _AdoptionRepository:
    def __init__(self, row):
        self.row = row

    def resolve(self, component_id):
        if component_id != "V2-CMP-138":
            return None
        return ComponentRecord(
            component_id=component_id,
            tier=ComponentTier.DIRECT_USE,
            roles=("promoter",),
            sequence_available=True,
            sequence_verified=True,
            rights_status="eligible",
            admission_status="admitted",
            sequence_sha256=self.row["sequence_sha256"],
        )

    def host_applicability_status(self, component_id, host):
        return host_applicability_gate(self.row, host)


def _adoption_fixture(tmp_path, *, scope):
    formal = PlantProjectDraftRepository(tmp_path / "formal")
    draft = formal.create_blank(project_name="Host gate fixture")
    draft.project_id = "adoption-project"
    draft.workflow_type = "multi_tu"
    draft.host_context = RICE
    formal.save(draft)
    row = _v2_row_with_scope(scope)
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="host-gate-test"), transport=FakeQwenTransport()),
        candidate_store=CandidateStore(tmp_path / "agent"),
        project_repository=formal,
        component_repository=_AdoptionRepository(row),
    )
    record = backend.service.component_repository.resolve("V2-CMP-138")
    result = backend.generate_and_validate(
        AgentRequest(
            request_id="adoption-request",
            workflow_type="multi_tu",
            host=RICE,
            user_intent="review candidate",
            cds_or_reference_input="ATGAAATAA",
            component_references=(ComponentReference("V2-CMP-138", "promoter", ComponentTier.DIRECT_USE, sequence_sha256=record.sequence_sha256),),
            project_id="adoption-project",
            context={"project_id": "adoption-project"},
        )
    )
    assert result.candidates
    candidate = result.candidates[0]
    preview = backend.service.build_adoption_preview(candidate)
    confirmed = backend.service.confirm_candidate(candidate, confirmation_id="adoption-confirmation", preview=preview)
    request = AdoptionRequest(confirmed.candidate_id, "adoption-project", __import__("services.agent_contracts", fromlist=["candidate_digest"]).candidate_digest(confirmed), "adoption-confirmation")
    return backend, request, formal


def test_adoption_stale_evidence_and_host_switch_fail_before_mutation(tmp_path):
    backend, request, formal = _adoption_fixture(tmp_path, scope=[RICE])
    backend.service.component_repository.row["host_applicability"] = {}
    with pytest.raises(CandidateStoreError):
        backend.adopt(request)
    assert formal.load("adoption-project").extra_fields == {}
    assert not list(backend.store.receipts_dir.glob("*.json"))


def test_adoption_valid_current_authority_commits(tmp_path):
    backend, request, formal = _adoption_fixture(tmp_path, scope=[RICE])
    receipt = backend.adopt(request)
    assert receipt.adoption_status == "COMMITTED"
    assert formal.load("adoption-project").extra_fields["agent_adoption"]["candidate_id"] == request.candidate_id


class _RestoreController:
    def __init__(self) -> None:
        self.saved = None

    def save(self, session: Any) -> None:
        self.saved = session


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _completed_host_gate_snapshot(base_result: Mapping[str, Any], *, evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Build a completed editor snapshot with persisted Step 3 authority evidence."""
    result = copy.deepcopy(dict(base_result))
    records = result["input_records"]
    for role, authority_role, component_id in (
        ("promoter", "promoter", "REG-PROM-001"),
        ("terminator", "3_prime_regulatory_region", "REG-3PR-001"),
    ):
        record = records[role]
        record["source_kind"] = "registry"
        record["component_reference"] = {
            "source_type": "REGISTRY",
            "registry_component_id": component_id,
            "tu_role": authority_role,
            "requested_host": RICE,
            "host_applicability_at_selection": copy.deepcopy(dict(evidence)),
        }
    result["formal_cassette_result"] = {
        "runtime": copy.deepcopy(result["runtime"]),
        "cassette_input_signature": result["input_signature"],
        "input_signature": result["input_signature"],
    }
    result["formal_project_context"] = {
        "host_key": RICE,
        "expression_target": "TEST_TARGET",
        "current_step": 6,
        "project_definition": {
            "project_name": result["project_name"],
            "plant_host": RICE,
            "material": "leaf",
        },
        "construct_review_basis": {},
        "construct_review_status": "current",
        "cds_source_review_status": "current",
        "formal_state": {
            "formal_expression_cassette": copy.deepcopy(result["formal_expression_cassette"]),
            "formal_cassette_result": copy.deepcopy(result["formal_cassette_result"]),
            "formal_cassette_exports": {"fasta": "historical-export"},
            "formal_cassette_input_signature": result["input_signature"],
            "formal_step3_order_confirmed": True,
            "formal_step3_order_confirmation_recorded": True,
            "formal_step4_strategy_confirmed": True,
            "formal_step4_strategy_signature": "step4-signature",
            "formal_step5_strategy_confirmed": True,
            "formal_step5_strategy_signature": "step5-signature",
            "formal_construct_review_status": "current",
        },
    }
    result["cassette_exports"] = {"fasta": {"data": ">cassette\nACGT\n"}}
    return result


@pytest.fixture
def saved_result() -> dict[str, Any]:
    """Use the accepted formal-editor builder for a realistic completed snapshot."""
    return build_formal_editor_completed(
        project_id="host-gate-direct-reopen",
        project_name="HOST_GATE_DIRECT_REOPEN",
    )


def _run_direct_cold_reopen(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str], _RestoreController]:
    """Execute the production restore branch with a controlled current authority seam."""
    import services.formal_step3_component_authority as authority

    result = copy.deepcopy(dict(snapshot))
    records = result["input_records"]
    current_options = {
        role: {
            "registry_component_id": records[role]["component_reference"]["registry_component_id"],
            "sequence": records[role]["normalized_sequence"],
            "component_reference": copy.deepcopy(records[role]["component_reference"]),
        }
        for role in ("promoter", "terminator")
    }

    def options(*, role: str, target_host_species: str) -> list[dict[str, Any]]:
        saved_role = "terminator" if role == "3_prime_regulatory_region" else role
        return [copy.deepcopy(current_options[saved_role])]

    monkeypatch.setattr(authority, "formal_step3_component_options", options)
    streamlit = FakeStreamlit()
    controller = _RestoreController()
    events: list[str] = []
    functions = _app_functions(
        "_project_definition_expression_target",
        "_formal_step3_custom_input_label",
        "_is_formal_action_widget_key",
        "_restore_completed_formal_state",
        "_restored_formal_project_context",
        "_formal_step3_reopen_unresolved_roles",
        "_restore_mvp_result",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "re": re,
            "st": streamlit,
            "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
                "paste": "粘贴 DNA/FASTA",
                "upload": "上传 FASTA",
            },
            "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PAGE_DESIGN_WORKSPACE": "design",
            "PAGE_RESULTS_EXPORT": "results",
            "_controller": lambda: controller,
            "_change_page": events.append,
            "_establish_workflow_baseline": lambda **_kwargs: None,
        },
    )
    actual_revalidator = functions["_formal_step3_reopen_unresolved_roles"]
    actual_restore_state = functions["_restore_completed_formal_state"]

    def record_revalidation(saved_records: Mapping[str, Any], host: str) -> tuple[str, ...]:
        events.append("revalidate")
        return actual_revalidator(saved_records, host)

    def record_restore_state(context: Mapping[str, Any]) -> None:
        events.append("restore")
        actual_restore_state(context)

    functions["_restore_mvp_result"].__globals__["_formal_step3_reopen_unresolved_roles"] = record_revalidation
    functions["_restore_mvp_result"].__globals__["_restore_completed_formal_state"] = record_restore_state
    functions["_restore_mvp_result"](result, "Rice (O. sativa)")
    return result, streamlit.session_state, events, controller


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"status": "reviewed", "scope": [TOMATO], "evidence_source": "fixture", "evidence_version": "r1", "limitation": "fixture"},
    ],
    ids=["not_proven", "wrong_host"],
)
def test_direct_cold_reopen_invalid_host_gate_blocks_completed_restore(
    saved_result: Mapping[str, Any], monkeypatch: pytest.MonkeyPatch, evidence: Mapping[str, Any]
) -> None:
    snapshot = _completed_host_gate_snapshot(saved_result, evidence=evidence)
    result, state, events, controller = _run_direct_cold_reopen(monkeypatch, snapshot)

    assert events[0] == "revalidate"
    assert "restore" not in events
    assert controller.saved is not None and controller.saved.step == 3
    assert events[-1] == "design"
    assert state["formal_step3_host_applicability_unresolved"]["roles"] == ["promoter", "terminator"]
    assert state["formal_construct_review_status"] == "needs_review"
    assert state["mvp_inputs_stale"] is True
    for key in (
        "formal_expression_cassette",
        "formal_cassette_result",
        "formal_cassette_exports",
        "formal_step3_order_confirmed",
        "formal_step4_strategy_confirmed",
        "formal_step5_strategy_confirmed",
        "mvp_vector_result",
        "mvp_current_input_signature",
    ):
        assert key not in state
    assert state["formal_element_source_records"]["promoter"] == result["input_records"]["promoter"]
    assert state["formal_element_source_records"]["terminator"] == result["input_records"]["terminator"]
    assert state["formal_step3_promoter_custom_name"] == result["input_records"]["promoter"]["display_name"]
    assert state["formal_step3_terminator_custom_name"] == result["input_records"]["terminator"]["display_name"]


def test_direct_cold_reopen_valid_host_gate_restores_completed_state(
    saved_result: Mapping[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = {
        "status": "reviewed",
        "scope": [RICE],
        "evidence_source": "fixture",
        "evidence_version": "r1",
        "limitation": "fixture",
    }
    snapshot = _completed_host_gate_snapshot(saved_result, evidence=evidence)
    result, state, events, controller = _run_direct_cold_reopen(monkeypatch, snapshot)

    assert events.index("revalidate") < events.index("restore")
    assert events[-1] == "results"
    assert controller.saved is not None and controller.saved.step == 6
    assert state["formal_expression_cassette"] == result["formal_expression_cassette"]
    assert state["formal_cassette_result"]["runtime"] == result["runtime"]
    assert state["mvp_vector_result"] == result
    assert result["exports"] == snapshot["exports"]
    assert result["cassette_exports"]["fasta"]["data"].startswith(">")
    assert state["formal_step3_order_confirmation_recorded"] is True
    assert state["formal_step4_strategy_confirmed"] is True
    assert state["formal_step4_strategy_signature"] == "step4-signature"
    assert state["formal_step5_strategy_confirmed"] is True
    assert state["formal_step5_strategy_signature"] == "step5-signature"
    assert state["formal_construct_review_status"] == "current"
    assert state["mvp_inputs_stale"] is False
    assert state["formal_element_source_records"]["promoter"] == result["input_records"]["promoter"]
    assert state["formal_element_source_records"]["terminator"] == result["input_records"]["terminator"]
