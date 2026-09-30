from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from core.i18n import translate

import pytest

from core.design_session import DesignSession
from services.agent_candidate_store import CandidateStore
from services.agent_contracts import (
    AgentRequest,
    AgentRunState,
    ComponentReference,
    ProviderCandidateDraft,
)
from services.agent_product_adapter import AgentProductAdapter
from services.agent_provider import (
    FakeQwenTransport,
    ProviderExplanationMetadata,
    ProviderGenerationResponse,
    ProviderMetadata,
    ProviderResponseStatus,
    QwenConfig,
    QwenProvider,
)
from services.agent_service import AgentBackend, ProductComponentRepository
from services.component_library_v2_adoption import (
    build_v2_canonical_inventory,
    build_v2_direct_selection,
    v2_canonical_record,
)
from services.formal_step3_component_authority import (
    formal_agent_component_admission,
    formal_step3_component_options,
)
from services.formal_project_persistence import save_formal_project_draft
from services import plant_component_workflow_registry as registry
from services.plant_component_workflow_registry import build_registry_selection
from services.plant_project_draft_repository import PlantProjectDraftRepository


RICE_HOST = "Rice (O. sativa)"
RICE_SCIENTIFIC_NAME = "Oryza sativa"
EGFP_720_NT = "ATG" + "A" * 714 + "TAA"
RICE_PROMOTER = "TEST-RICE-PROMOTER"
RICE_THREE_PRIME = "TEST-RICE-3REG"
TOMATO_PROMOTER = "TEST-TOMATO-PROMOTER"


def _registry_record(component_id: str, component_type: str, hosts: list[str]) -> dict:
    alphabet = "ACGT"
    sequence = "".join(alphabet[value % 4] for value in hashlib.sha256(component_id.encode("ascii")).digest())
    source_digest = hashlib.sha256(
        f"controlled source:{component_id}".encode("ascii")
    ).hexdigest()
    return {
        "component_id": component_id,
        "display_name": component_id.replace("TEST-", "Controlled ").replace("-", " "),
        "component_type": component_type,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        "accession_version": f"{component_id}.1",
        "source_sequence_length": len(sequence),
        "source_record": f"controlled/{component_id}.gb",
        "source_record_sha256": source_digest,
        "feature_boundary_method": {
            "method": "controlled exact boundary",
            "start_one_based": 1,
            "end_one_based_inclusive": len(sequence),
            "strand": "+",
        },
        "distribution_mode": "bundled",
        "sequence_availability": "local_verified",
        "workflow_admission_status": "eligible",
        "target_host_species": hosts,
        "governance_decision_source": "controlled-test-governance",
        "governance_decision_version": "r2",
        "rights_classification": "RIGHTS_CLEAR_FOR_CURRENT_USE",
        "review_status": "source_and_boundary_reviewed",
        "role_semantics_reviewed": True,
        "host_applicability_reviewed": True,
        "alias_collision_reviewed": True,
        "formal_export_compatible": True,
        "host_applicability": {
            "status": "reviewed",
            "scope": hosts,
            "evidence_source": "controlled-test-host-scope",
            "evidence_version": "r2",
            "limitation": "Controlled software fixture; no biological performance conclusion.",
        },
        "attribution": {
            "source_database": "controlled test fixture",
            "record_locator": f"synthetic://{component_id}.1",
            "accession_version": f"{component_id}.1",
            "submitter_source_context": "Controlled software test fixture.",
            "publication_citations": ["Controlled software test citation."],
            "source_coordinates_one_based_inclusive": f"1..{len(sequence)}",
            "strand": "+",
            "feature_type": f"controlled {component_type}",
            "retrieval_date": "2026-09-18",
            "source_record_sha256": source_digest,
            "feature_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
            "rights_caveat_reference": "controlled test fixture rights",
            "component_contract_version": "r2",
            "required_notice": "Controlled software test fixture only.",
        },
    }


@pytest.fixture
def controlled_registry(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "controlled-registry.json"
    path.write_text(
        json.dumps(
            {
                "registry_version": "agent-product-semantics-r2-controlled",
                "records": [
                    _registry_record(RICE_PROMOTER, "promoter", [RICE_SCIENTIFIC_NAME]),
                    _registry_record(
                        RICE_THREE_PRIME,
                        "three_prime_regulatory_region",
                        [RICE_SCIENTIFIC_NAME],
                    ),
                    _registry_record(TOMATO_PROMOTER, "promoter", ["Solanum lycopersicum"]),
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    production_resolver = registry._durable_governance_evidence

    def resolve(record: dict[str, object]) -> None:
        if record.get("governance_decision_source") == "controlled-test-governance":
            attribution = record.get("attribution")
            assert isinstance(attribution, dict)
            if attribution.get("rights_caveat_reference") != "controlled test fixture rights":
                raise registry.PlantComponentRegistryError(
                    "Controlled fixture rights evidence is invalid."
                )
            return
        production_resolver(record)

    monkeypatch.setattr(registry, "_durable_governance_evidence", resolve)
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    return path


def _formal_component(component_id: str, role: str, *, host: str = RICE_SCIENTIFIC_NAME) -> dict:
    selection = build_registry_selection(
        component_id,
        role=role,
        requested_host=host,
    )
    return {
        "name": selection["display_name"],
        "sequence": selection["selected_sequence"],
        "component_reference": selection,
    }


def _project_repository(
    tmp_path,
    *,
    include_cds: bool = True,
    include_components: bool = False,
    promoter_id: str = RICE_PROMOTER,
    promoter_host: str = RICE_SCIENTIFIC_NAME,
):
    repository = PlantProjectDraftRepository(tmp_path / "formal")
    formal_state = {
        "formal_project_name": "Rice EGFP design",
        "formal_project_host": RICE_HOST,
    }
    if include_cds:
        formal_state["formal_cds_input"] = {
            "normalized_cds": EGFP_720_NT,
            "blocking": False,
            "source_name": "EGFP test input",
        }
    if include_components:
        formal_state.update(
            {
                "formal_step3_promoter": _formal_component(
                    promoter_id,
                    "promoter",
                    host=promoter_host,
                ),
                "formal_step3_terminator": _formal_component(
                    RICE_THREE_PRIME, "3_prime_regulatory_region"
                ),
            }
        )
    draft = save_formal_project_draft(
        project_name="Rice EGFP design",
        project_id="rice-egfp-project",
        workflow_type="single_gene",
        current_step=3 if include_components else 2,
        design_session=DesignSession(step=2, host=RICE_HOST, tag="No tag"),
        formal_state=formal_state,
        project_definition={
            "project_name": "Rice EGFP design",
            "plant_host": RICE_HOST,
            "expression_target": "为水稻设计一个用于组成型表达 GFP 的单基因植物表达候选方案。",
        },
        repository=repository,
    )
    return repository, draft


def _adapter(repository=None) -> AgentProductAdapter:
    return AgentProductAdapter(
        project_repository=repository,
        component_repository=ProductComponentRepository(),
    )


def _selected_references(adapter: AgentProductAdapter) -> tuple[ComponentReference, ...]:
    shortlist = adapter.component_shortlist(
        workflow_type="single_gene", host=RICE_SCIENTIFIC_NAME
    )
    selected = [
        next(option["component_id"] for option in role["options"] if option["selectable"])
        for role in shortlist["roles"]
    ]
    return adapter.resolve_component_references(
        selected,
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
    )


def test_current_formal_project_identity_workflow_host_and_cds_are_projected(tmp_path) -> None:
    repository, draft = _project_repository(tmp_path)

    context = _adapter(repository).read_project_context(draft.project_id)

    assert context["available"] is True
    assert context["project_id"] == "rice-egfp-project"
    assert context["project_name"] == "Rice EGFP design"
    assert context["workflow_type"] == "single_gene"
    assert context["host"] == RICE_HOST
    assert context["user_intent"].startswith("为水稻设计")
    assert context["cds"] == {
        "value": EGFP_720_NT,
        "source": "formal_project",
        "source_name": "EGFP test input",
    }


def test_missing_formal_cds_is_not_invented_and_keeps_needs_input(
    tmp_path, controlled_registry
) -> None:
    repository, draft = _project_repository(tmp_path, include_cds=False)
    adapter = _adapter(repository)
    context = adapter.read_project_context(draft.project_id)
    references = _selected_references(adapter)
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        project_repository=repository,
        component_repository=adapter.component_repository,
    )

    result = backend.generate_and_validate(
        AgentRequest(
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
            user_intent=context["user_intent"],
            cds_or_reference_input=None,
            component_references=references,
            project_id=draft.project_id,
            context={"project_id": draft.project_id},
        )
    )

    assert context["cds"] is None
    assert result.state is AgentRunState.NEEDS_INPUT
    assert any(need.field == "cds_or_reference_input" for need in result.needs_input)
    assert transport.calls == []


def test_shortlist_is_exactly_the_current_formal_host_admission(
    controlled_registry,
) -> None:
    shortlist = _adapter().component_shortlist(
        workflow_type="single_gene", host=RICE_SCIENTIFIC_NAME
    )
    options = [option for role in shortlist["roles"] for option in role["options"]]
    formal = formal_agent_component_admission(
        workflow_type="single_gene",
        target_host_species=RICE_SCIENTIFIC_NAME,
    )
    formal_ids = {
        str(option["registry_component_id"])
        for role in formal["roles"]
        for option in role["options"]
    }

    assert shortlist["supported"] is True
    assert {role["role"] for role in shortlist["roles"]} == {
        "promoter",
        "3_prime_regulatory_region",
    }
    assert {option["component_id"] for option in options} == formal_ids == {
        RICE_PROMOTER,
        RICE_THREE_PRIME,
    }
    assert all(option["tier"] == "DIRECT_USE" for option in options)
    assert all(option["selectable"] is True for option in options)
    assert TOMATO_PROMOTER not in formal_ids


def test_production_rice_shortlist_does_not_promote_empty_host_v2_scope() -> None:
    shortlist = _adapter().component_shortlist(
        workflow_type="single_gene", host=RICE_SCIENTIFIC_NAME
    )
    shortlist_ids = {
        option["component_id"]
        for role in shortlist["roles"]
        for option in role["options"]
    }
    direct_v2_ids = {
        row["canonical_v2_component_id"]
        for row in build_v2_canonical_inventory()
        if row.get("admission_mode") == "DIRECT_USE"
    }

    assert shortlist_ids == set()
    assert shortlist_ids.isdisjoint(direct_v2_ids)
    assert "V2-CMP-138" not in shortlist_ids
    assert "V2-CMP-144" not in shortlist_ids


def test_existing_formal_components_are_preserved_and_only_missing_roles_get_options(
    tmp_path, controlled_registry
) -> None:
    repository, draft = _project_repository(tmp_path, include_components=True)
    adapter = _adapter(repository)
    context = adapter.read_project_context(draft.project_id)
    existing = context["existing_components"]
    shortlist = adapter.component_shortlist(
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
        existing_components=existing,
    )
    ids = [item["component_id"] for item in existing]
    resolved = adapter.resolve_component_references(
        ids,
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
        existing_components=existing,
    )

    assert ids == [RICE_PROMOTER, RICE_THREE_PRIME]
    assert [reference.component_id for reference in resolved] == ids
    assert [reference.role for reference in resolved] == [
        "promoter",
        "3_prime_regulatory_region",
    ]
    assert all(role["existing"] is not None and role["options"] == () for role in shortlist["roles"])


def test_wrong_host_saved_formal_selection_is_not_reused(
    tmp_path, controlled_registry
) -> None:
    repository, draft = _project_repository(
        tmp_path,
        include_components=True,
        promoter_id=TOMATO_PROMOTER,
        promoter_host="Solanum lycopersicum",
    )
    adapter = _adapter(repository)

    context = adapter.read_project_context(draft.project_id)
    shortlist = adapter.component_shortlist(
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
        existing_components=context["existing_components"],
    )
    promoter = next(group for group in shortlist["roles"] if group["role"] == "promoter")

    assert [item["component_id"] for item in context["existing_components"]] == [
        RICE_THREE_PRIME
    ]
    assert len(context["limitations"]) == 1
    assert promoter["existing"] is None
    assert [option["component_id"] for option in promoter["options"]] == [RICE_PROMOTER]


def test_saved_v2_direct_use_selection_without_host_scope_is_not_reused(
    controlled_registry,
) -> None:
    row = v2_canonical_record("V2-CMP-138")
    selection = build_v2_direct_selection(row, role="promoter")
    selected = {
        "name": selection["display_name"],
        "sequence": selection["selected_sequence"],
        "component_reference": selection,
    }

    with pytest.raises(ValueError, match="no reusable canonical component identity"):
        _adapter()._admit_formal_selection(
            selected,
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
        )


def test_user_selected_ids_resolve_to_request_authoritative_component_references(
    controlled_registry,
) -> None:
    adapter = _adapter()
    references = _selected_references(adapter)

    assert [reference.role for reference in references] == [
        "promoter",
        "3_prime_regulatory_region",
    ]
    assert all(reference.tier.value == "DIRECT_USE" for reference in references)
    assert all(reference.sequence_sha256 for reference in references)
    try:
        adapter.resolve_component_references(
            ["V2-CMP-003"],
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("blocked component entered the authoritative request snapshot")

    tomato_record = adapter.component_repository.resolve(TOMATO_PROMOTER)
    assert tomato_record is not None
    injected = {
        "component_id": TOMATO_PROMOTER,
        "role": "promoter",
        "reference": adapter._component_reference(tomato_record, role="promoter"),
    }
    with pytest.raises(ValueError, match="current eligible shortlist"):
        adapter.resolve_component_references(
            [TOMATO_PROMOTER],
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
            existing_components=[injected],
        )


def test_reference_only_retired_and_user_sequence_assisted_never_enter_shortlist(
    controlled_registry,
) -> None:
    adapter = _adapter()
    shortlist_ids = {
        option["component_id"]
        for group in adapter.component_shortlist(
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
        )["roles"]
        for option in group["options"]
    }
    inventory = build_v2_canonical_inventory()
    excluded = {
        str(row["canonical_v2_component_id"])
        for row in inventory
        if row.get("admission_mode") in {"REFERENCE_ONLY", "USER_SEQUENCE_ASSISTED"}
        or row.get("library_tier") == "RETIRED"
        or row.get("workflow_admission_status") == "blocked"
    }

    assert excluded
    assert shortlist_ids.isdisjoint(excluded)


def test_legacy_component_selection_tool_uses_the_same_formal_admission(
    controlled_registry,
) -> None:
    adapter = _adapter()

    selected = adapter.select_components(
        [RICE_PROMOTER],
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
    )

    assert selected["admission_modes"] == ["DIRECT_USE"]
    assert selected["components"][0]["admission_mode"] == "DIRECT_USE"
    try:
        adapter.select_components(
            ["V2-CMP-003"],
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("reference-only component entered the legacy selection path")


def test_assisted_ui_uses_named_selectors_and_exposes_project_authority_boundaries() -> None:
    source = (Path(__file__).parents[1] / "views" / "AgentWorkspace.py").read_text(
        encoding="utf-8"
    )

    assert "Component Library V2 标识（逗号分隔）" not in source
    assert '_t("v1.ai_assisted_design.candidates_come_components_available_project_bound_request")' in source
    assert "st.selectbox(" in source and '_t("v1.ai_assisted_design.select_candidate"' in source
    assert '_t("v1.ai_assisted_design.review_component_candidates_here_confirm_vector_backbone")' in source
    assert translate("v1.ai_assisted_design.reused_project", language="zh-CN")
    assert translate("v1.ai_assisted_design.confirmed_project", language="zh-CN")
    assert translate(
        "v1.ai_assisted_design.some_existing_components_project_not_passed_eligibility",
        language="zh-CN",
    )


@pytest.mark.parametrize(
    "context",
    [
        {},
        {
            "component_selection_required": False,
            "required_component_roles": [],
        },
    ],
)
def test_required_zero_component_path_is_authoritative_and_cannot_be_disabled(
    tmp_path, controlled_registry, context
) -> None:
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        component_repository=ProductComponentRepository(),
    )
    request = AgentRequest(
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
        user_intent="review a rice GFP candidate",
        cds_or_reference_input=EGFP_720_NT,
        context=context,
    )

    result = backend.generate_and_validate(request)

    assert result.state is AgentRunState.NEEDS_INPUT
    assert result.candidates == ()
    assert any(need.field == "component_references" for need in result.needs_input)
    assert transport.calls == []


def test_partial_authoritative_component_selection_stays_local(
    tmp_path, controlled_registry
) -> None:
    adapter = _adapter()
    references = _selected_references(adapter)
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        component_repository=adapter.component_repository,
    )

    result = backend.generate_and_validate(
        AgentRequest(
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
            user_intent="review a rice GFP candidate",
            cds_or_reference_input=EGFP_720_NT,
            component_references=references[:1],
        )
    )

    assert result.state is AgentRunState.NEEDS_INPUT
    assert result.candidates == ()
    assert result.needs_input[0].details["missing_roles"] == [
        "3_prime_regulatory_region"
    ]
    assert transport.calls == []


def test_all_authoritative_roles_allow_provider_path(
    tmp_path, controlled_registry
) -> None:
    adapter = _adapter()
    references = _selected_references(adapter)
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        component_repository=adapter.component_repository,
    )

    result = backend.generate_and_validate(
        AgentRequest(
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
            user_intent="review a rice GFP candidate",
            cds_or_reference_input=EGFP_720_NT,
            component_references=references,
        )
    )

    assert result.state in {AgentRunState.RESULT, AgentRunState.ALTERNATIVES}
    assert transport.calls


def test_unadmitted_extra_component_cannot_ride_with_complete_required_roles(
    tmp_path, controlled_registry
) -> None:
    adapter = _adapter()
    references = _selected_references(adapter)
    extra_record = adapter.component_repository.resolve("V2-CMP-138")
    assert extra_record is not None
    extra = adapter._component_reference(extra_record, role="promoter")
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        component_repository=adapter.component_repository,
    )

    result = backend.generate_and_validate(
        AgentRequest(
            workflow_type="single_gene",
            host=RICE_SCIENTIFIC_NAME,
            user_intent="review a rice GFP candidate",
            cds_or_reference_input=EGFP_720_NT,
            component_references=(*references, extra),
        )
    )

    assert result.state is AgentRunState.NEEDS_INPUT
    assert result.candidates == ()
    assert result.needs_input[0].details["unadmitted_component_ids"] == ["V2-CMP-138"]
    assert transport.calls == []


def test_component_requirement_is_not_invented_for_unrelated_workflow(tmp_path) -> None:
    transport = FakeQwenTransport()
    backend = AgentBackend(
        QwenProvider(config=QwenConfig(model="test-model"), transport=transport),
        candidate_store=CandidateStore(tmp_path / "agent"),
        component_repository=ProductComponentRepository(),
    )

    result = backend.generate_and_validate(
        AgentRequest(
            workflow_type="multi_tu",
            host=RICE_SCIENTIFIC_NAME,
            user_intent="review a multi-TU record",
            cds_or_reference_input="reference:controlled",
        )
    )

    assert not any(need.field == "component_references" for need in result.needs_input)
    assert transport.calls


class _ControlledDraftProvider:
    def __init__(self, *, evidence=("ev-1",), extra_component: ComponentReference | None = None):
        self.selected_evidence = evidence
        self.extra_component = extra_component
        self._metadata = ProviderMetadata(
            "controlled", "controlled-model", "", "controlled-schema", "controlled"
        )

    @property
    def metadata(self):
        return self._metadata

    def generate(self, request: AgentRequest) -> ProviderGenerationResponse:
        references = request.component_references
        if self.extra_component is not None:
            references = references + (self.extra_component,)
        draft = ProviderCandidateDraft(
            candidate_id="controlled-candidate",
            workflow_type=request.workflow_type,
            host=request.host,
            user_intent=request.user_intent,
            cds_or_reference_input=request.cds_or_reference_input,
            component_references=references,
            evidence_references=self.selected_evidence,
            rationale="controlled advisory rationale",
        )
        metadata = replace(self._metadata, request_id=request.request_id)
        return ProviderGenerationResponse(
            ProviderResponseStatus.CANDIDATES,
            "controlled interpretation",
            (),
            (draft,),
            (),
            "controlled explanation",
            ProviderExplanationMetadata(),
            metadata,
        )


def _authorized_request(references: tuple[ComponentReference, ...]) -> AgentRequest:
    return AgentRequest(
        workflow_type="single_gene",
        host=RICE_SCIENTIFIC_NAME,
        user_intent="review a rice GFP candidate",
        cds_or_reference_input=EGFP_720_NT,
        component_references=references,
        evidence_references=("ev-1", "ev-2"),
    )


def test_provider_selected_evidence_subset_is_preserved_in_candidate_trace_and_store(
    tmp_path, controlled_registry
) -> None:
    references = _selected_references(_adapter())
    store = CandidateStore(tmp_path / "agent")
    backend = AgentBackend(
        _ControlledDraftProvider(evidence=("ev-1",)),
        candidate_store=store,
        component_repository=ProductComponentRepository(),
    )

    result = backend.generate_and_validate(_authorized_request(references))
    candidate = result.candidates[0]

    assert candidate.evidence_references == ("ev-1",)
    assert result.trace.evidence_references == ("ev-1",)
    assert store.load(candidate.candidate_id).evidence_references == ("ev-1",)


def test_provider_cannot_add_component_or_evidence_outside_request_snapshot(
    tmp_path, controlled_registry
) -> None:
    references = _selected_references(_adapter())
    invented_component = replace(references[0], component_id="invented-component")

    component_result = AgentBackend(
        _ControlledDraftProvider(extra_component=invented_component),
        candidate_store=CandidateStore(tmp_path / "component-agent"),
        component_repository=ProductComponentRepository(),
    ).generate_and_validate(_authorized_request(references))
    evidence_result = AgentBackend(
        _ControlledDraftProvider(evidence=("ev-x",)),
        candidate_store=CandidateStore(tmp_path / "evidence-agent"),
        component_repository=ProductComponentRepository(),
    ).generate_and_validate(_authorized_request(references))

    assert component_result.state is AgentRunState.FAILED
    assert component_result.candidates == ()
    assert evidence_result.state is AgentRunState.FAILED
    assert evidence_result.candidates == ()
