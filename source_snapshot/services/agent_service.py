"""Minimal provider-neutral Agent orchestration for V1.

This service produces reviewable candidates and adoption previews only.  It
never writes Product state and never treats provider output as deterministic
sequence, provenance, host, rights, or admission authority.
"""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping
import hashlib
import secrets

from services.agent_contracts import (
    AdoptionStatus,
    AgentAdoptionPreview,
    AgentAdoptionResult,
    AgentAlternative,
    AgentCandidate,
    AgentNeedInput,
    AgentRequest,
    AgentRunState,
    AgentTraceRecord,
    AgentValidationSummary,
    ComponentRecord,
    CandidateState,
    ComponentRepository,
    ComponentTier,
    ContractError,
    DeterministicValidationStatus,
    NeedInputCode,
    candidate_state_transition,
    candidate_digest,
    request_digest,
    utc_timestamp,
)
from services.agent_provider import (
    ModelProvider,
    ProviderError,
    ProviderGenerationResponse,
    ProviderResponseStatus,
)


# These are governance facts for the current V1 catalog, not an embedded
# component inventory.  A reconciled repository remains the source of truth.
V1_COMPONENT_TIER_COUNTS = {
    ComponentTier.DIRECT_USE: 17,
    ComponentTier.USER_SEQUENCE_ASSISTED: 24,
    ComponentTier.REFERENCE_ONLY: 95 + 35,
}


def component_tier_eligibility(tier: ComponentTier | str) -> dict[str, bool]:
    """Describe what the Agent may do with a governance tier."""
    try:
        normalized = ComponentTier(tier)
    except (TypeError, ValueError) as exc:
        raise ContractError("component tier is unsupported.") from exc
    return {
        "deterministic_downstream_design": normalized is ComponentTier.DIRECT_USE,
        "recommendation_allowed": normalized in {ComponentTier.DIRECT_USE, ComponentTier.USER_SEQUENCE_ASSISTED},
        "user_sequence_required": normalized is ComponentTier.USER_SEQUENCE_ASSISTED,
        "search_or_explanation_only": normalized is ComponentTier.REFERENCE_ONLY,
        "direct_adoption_allowed": normalized is ComponentTier.DIRECT_USE,
    }


class AgentServiceError(RuntimeError):
    """Safe orchestration failure without Product mutation."""


def _trusted_enum_value_is(value: Any, expected: Enum) -> bool:
    """Match one semantic Enum member across module reload generations."""
    if not isinstance(value, Enum) or not isinstance(expected, Enum):
        return False
    value_type = type(value)
    expected_type = type(expected)
    return (
        value_type.__module__ == expected_type.__module__
        and value_type.__qualname__ == expected_type.__qualname__
        and value.name == expected.name
        and value.value == expected.value
    )


def _adoption_rejection(candidate: AgentCandidate, reason: str) -> AgentCandidate:
    """Return a blocked view for Candidate Store's fail-closed transaction."""
    current_validation = candidate.deterministic_validation
    blocked_status = next(
        (
            member
            for member in type(current_validation.status)
            if _trusted_enum_value_is(member, DeterministicValidationStatus.BLOCKED)
        ),
        DeterministicValidationStatus.BLOCKED,
    )
    validation = replace(
        current_validation,
        status=blocked_status,
        checks=tuple(
            dict.fromkeys(
                (*candidate.deterministic_validation.checks, "current_authority_revalidated")
            )
        ),
        blocking_reasons=(reason,),
        authority="formal_registry_at_adoption",
        checked_at=utc_timestamp(),
    )
    return replace(candidate, deterministic_validation=validation)


@dataclass(frozen=True)
class AgentRunResult:
    state: AgentRunState
    request: AgentRequest
    candidates: tuple[AgentCandidate, ...] = ()
    alternatives: tuple[AgentAlternative, ...] = ()
    needs_input: tuple[AgentNeedInput, ...] = ()
    interpretation: str = ""
    explanation: str = ""
    explanation_metadata: Mapping[str, Any] = field(default_factory=dict)
    trace: AgentTraceRecord | None = None
    error_code: str | None = None
    error_message: str | None = None


class InMemoryComponentRepository:
    """Small read-only adapter useful in tests and local integration setup."""

    def __init__(self, records: tuple[Any, ...] = ()) -> None:
        self._records = {record.component_id: record for record in records}

    def resolve(self, component_id: str):
        return self._records.get(component_id)


def component_governance_needs(request: AgentRequest, repository: ComponentRepository | None) -> tuple[AgentNeedInput, ...]:
    """Derive missing requirements from deterministic component governance facts."""
    from services.plant_component_workflow_registry import (
        HOST_APPLICABILITY_NOT_PROVEN,
        HOST_APPLICABILITY_WRONG_HOST,
    )

    needs: list[AgentNeedInput] = []
    for ref in request.component_references:
        record = repository.resolve(ref.component_id) if repository is not None else None
        if record is None:
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    f"component_{ref.component_id}",
                    f"Component {ref.component_id} has no deterministic repository record.",
                    details={"component_id": ref.component_id, "tier": ref.tier.value},
                )
            )
            continue
        if record.tier is not ref.tier:
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    f"component_{ref.component_id}",
                    f"Component {ref.component_id} tier does not match the request snapshot.",
                    details={"requested_tier": ref.tier.value, "repository_tier": record.tier.value},
                )
            )
            continue
        host_status = None
        host_gate = getattr(repository, "host_applicability_status", None)
        if request.host and ref.tier is ComponentTier.DIRECT_USE and callable(host_gate):
            host_status = host_gate(ref.component_id, request.host)
        if request.host and ref.tier is ComponentTier.DIRECT_USE and host_status == HOST_APPLICABILITY_NOT_PROVEN:
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    f"component_{ref.component_id}_host_applicability",
                    f"Component {ref.component_id} has no reviewed host-applicability scope for the selected host.",
                    details={"host": request.host, "status": host_status},
                )
            )
        elif request.host and ref.tier is ComponentTier.DIRECT_USE and host_status == HOST_APPLICABILITY_WRONG_HOST:
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    f"component_{ref.component_id}",
                    f"Component {ref.component_id} is outside the selected host scope.",
                    details={"host": request.host, "status": host_status},
                )
            )
        elif request.host and ref.tier is ComponentTier.DIRECT_USE and host_status is None:
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    f"component_{ref.component_id}_host_applicability",
                    f"Component {ref.component_id} has no reviewed host-applicability scope for the selected host.",
                    details={"host": request.host, "status": HOST_APPLICABILITY_NOT_PROVEN},
                )
            )
        if ref.tier is ComponentTier.DIRECT_USE:
            if not record.sequence_available or not record.sequence_verified:
                needs.append(
                    AgentNeedInput(
                        NeedInputCode.MISSING_VERIFIED_SEQUENCE,
                        f"component_{ref.component_id}_sequence",
                        f"Direct-use component {ref.component_id} requires a verified sequence.",
                    )
                )
            if record.rights_status != "eligible" or record.admission_status != "admitted":
                needs.append(
                    AgentNeedInput(
                        NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                        f"component_{ref.component_id}_admission",
                        f"Direct-use component {ref.component_id} lacks eligible rights and admission facts.",
                    )
                )
        elif ref.tier is ComponentTier.USER_SEQUENCE_ASSISTED:
            if ref.component_id not in request.verified_sequence_references:
                needs.append(
                    AgentNeedInput(
                        NeedInputCode.ASSISTED_COMPONENT_SEQUENCE_REQUIRED,
                        f"component_{ref.component_id}_sequence",
                        f"User-sequence-assisted component {ref.component_id} requires user-provided sequence information.",
                    )
                )
        elif ref.tier is ComponentTier.REFERENCE_ONLY:
            # Reference-only context is allowed for explanation/search, but it
            # can never be silently promoted to an adoptable component.
            continue
    return tuple(needs)


class V2ComponentRepository:
    """Read-only adapter over the authoritative Component Library V2 package."""

    def __init__(self, rows: list[Mapping[str, Any]] | None = None) -> None:
        if rows is None:
            from services.component_library_v2_adoption import build_v2_canonical_inventory
            rows = build_v2_canonical_inventory()
        self._rows = {str(row.get("canonical_v2_component_id") or row.get("id")): dict(row) for row in rows}

    def list_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(self._rows[key]) for key in sorted(self._rows))

    def host_applicability_status(self, component_id: str, host: str) -> str:
        from services.plant_component_workflow_registry import (
            HOST_APPLICABILITY_NOT_PROVEN,
            host_applicability_gate,
        )

        row = self._rows.get(str(component_id))
        if row is None:
            return HOST_APPLICABILITY_NOT_PROVEN
        return host_applicability_gate(row, host)

    def resolve(self, component_id: str):
        row = self._rows.get(str(component_id))
        if row is None:
            return None
        mode = str(row.get("admission_mode") or "REFERENCE_ONLY")
        try:
            tier = ComponentTier(mode)
        except ValueError:
            tier = ComponentTier.REFERENCE_ONLY
        return ComponentRecord(
            component_id=str(row.get("canonical_v2_component_id") or component_id),
            tier=tier,
            roles=(str(row.get("role") or ""),) if row.get("role") else (),
            host_scope=(),
            sequence_available=bool(row.get("sequence")),
            sequence_verified=mode == "DIRECT_USE" and bool(row.get("sequence_sha256")),
            rights_status="eligible" if mode == "DIRECT_USE" else "user_sequence_required" if mode == "USER_SEQUENCE_ASSISTED" else "reference_only",
            admission_status="admitted" if mode == "DIRECT_USE" else "requires_sequence" if mode == "USER_SEQUENCE_ASSISTED" else "reference_only",
            evidence_references=tuple(str(item) for item in (row.get("evidence_paths") or ())),
            provenance_references=("V2_CORE",) if str(row.get("library_tier")) == "CORE" else (str(row.get("library_tier") or "REFERENCE"),),
            library_tier=str(row.get("library_tier") or "REFERENCE"),
            canonical_v2_component_id=str(row.get("canonical_v2_component_id") or component_id),
            sequence_sha256=str(row.get("sequence_sha256") or ""),
        )


class ProductComponentRepository(V2ComponentRepository):
    """Resolve V2 candidates plus already-admitted Formal Registry identities."""

    @staticmethod
    def component_admission_contract(*, workflow_type: str, host: str) -> dict[str, Any]:
        from services.formal_step3_component_authority import formal_agent_component_admission

        return formal_agent_component_admission(
            workflow_type=workflow_type, target_host_species=host
        )

    def resolve(self, component_id: str):
        record = super().resolve(component_id)
        if record is not None:
            return record
        from services.plant_component_workflow_registry import (
            ROLE_COMPONENT_TYPES,
            PlantComponentRegistryError,
            registry_record,
            registry_record_is_admissible,
        )

        try:
            row = registry_record(str(component_id))
        except PlantComponentRegistryError:
            return None
        if not registry_record_is_admissible(row):
            return None
        component_type = str(row.get("component_type") or "")
        roles = tuple(
            role
            for role, allowed_types in ROLE_COMPONENT_TYPES.items()
            if component_type in allowed_types
        )
        return ComponentRecord(
            component_id=str(row.get("component_id") or component_id),
            tier=ComponentTier.DIRECT_USE,
            roles=roles,
            host_scope=(),
            sequence_available=bool(row.get("sequence")),
            sequence_verified=bool(row.get("sequence_sha256")),
            rights_status="eligible",
            admission_status="admitted",
            evidence_references=tuple(str(item) for item in (row.get("primary_reference"),) if item),
            provenance_references=tuple(str(item) for item in (row.get("source_record"),) if item) or ("PLANT_COMPONENT_REGISTRY_V1",),
            library_tier="CORE",
            canonical_v2_component_id=str(row.get("component_id") or component_id),
            sequence_sha256=str(row.get("sequence_sha256") or ""),
        )

    def host_applicability_status(self, component_id: str, host: str) -> str:
        if str(component_id) in self._rows:
            return super().host_applicability_status(component_id, host)
        from services.plant_component_workflow_registry import (
            HOST_APPLICABILITY_NOT_PROVEN,
            PlantComponentRegistryError,
            host_applicability_gate,
            registry_record,
        )

        try:
            row = registry_record(str(component_id))
        except PlantComponentRegistryError:
            return HOST_APPLICABILITY_NOT_PROVEN
        return host_applicability_gate(row, host)


class AgentService:
    def __init__(self, provider: ModelProvider, *, component_repository: ComponentRepository | None = None, candidate_store: Any | None = None, project_id: str | None = None, product_validator: Any | None = None) -> None:
        self.provider = provider
        self.component_repository = component_repository
        self.candidate_store = candidate_store
        self.project_id = project_id or ""
        self.product_validator = product_validator
        self._service_id = f"service-{secrets.token_urlsafe(12)}"
        self._adoption_previews: dict[tuple[str, str], AgentAdoptionPreview] = {}
        self._confirmation_bindings: dict[str, tuple[str, str, str, str]] = {}

    def inspect_request(self, request: AgentRequest) -> tuple[AgentNeedInput, ...]:
        needs: list[AgentNeedInput] = []
        if request.workflow_type not in {"single_gene", "multi_tu", "pathway"}:
            needs.append(AgentNeedInput(NeedInputCode.UNSUPPORTED_WORKFLOW, "workflow_type", "A supported workflow type must be selected."))
        if not request.user_intent:
            needs.append(AgentNeedInput(NeedInputCode.MISSING_CDS_OR_REFERENCE, "user_intent", "User intent is required for candidate generation."))
        if not request.host:
            needs.append(AgentNeedInput(NeedInputCode.HOST_NOT_SELECTED, "host", "Host selection is required before candidate generation."))
        if request.cds_or_reference_input is None:
            needs.append(AgentNeedInput(NeedInputCode.MISSING_CDS_OR_REFERENCE, "cds_or_reference_input", "A CDS or reference input is required."))
        admission_contract = getattr(self.component_repository, "component_admission_contract", None)
        contract = (
            admission_contract(workflow_type=request.workflow_type, host=request.host)
            if callable(admission_contract)
            else {"supported": False, "required_roles": (), "roles": ()}
        )
        admitted_by_role = {
            str(group.get("role") or ""): {
                str(option.get("registry_component_id") or "")
                for option in tuple(group.get("options") or ())
                if option.get("formal_selectable")
            }
            for group in tuple(contract.get("roles") or ())
        }
        selected_by_role: dict[str, set[str]] = {}
        for reference in request.component_references:
            selected_by_role.setdefault(reference.role, set()).add(reference.component_id)
        missing_roles = tuple(
            role for role in tuple(contract.get("required_roles") or ())
            if not (selected_by_role.get(str(role), set()) & admitted_by_role.get(str(role), set()))
        )
        unadmitted_component_ids = tuple(
            reference.component_id
            for reference in request.component_references
            if reference.component_id not in admitted_by_role.get(reference.role, set())
        )
        if contract.get("supported") and (missing_roles or unadmitted_component_ids):
            needs.append(
                AgentNeedInput(
                    NeedInputCode.COMPONENT_RIGHTS_UNRESOLVED,
                    "component_references",
                    "Current Formal component selections are required for this assisted-design request.",
                    details={"missing_roles": list(missing_roles), "unadmitted_component_ids": list(unadmitted_component_ids)},
                )
            )
        needs.extend(component_governance_needs(request, self.component_repository))
        return tuple(needs)

    def generate(self, request: AgentRequest) -> AgentRunResult:
        needs = self.inspect_request(request)
        if needs:
            trace = AgentTraceRecord(
                candidate_id=None,
                request_id=request.request_id,
                provider=self.provider.metadata.provider,
                model=self.provider.metadata.model,
                generated_at=utc_timestamp(),
                deterministic_checks=tuple(dict.fromkeys(item.code.value for item in needs)),
            )
            return AgentRunResult(state=AgentRunState.NEEDS_INPUT, request=request, needs_input=needs, trace=trace)
        try:
            response = self.provider.generate(request)
        except ProviderError as exc:
            trace = AgentTraceRecord(
                candidate_id=None,
                request_id=request.request_id,
                provider=self.provider.metadata.provider,
                model=self.provider.metadata.model,
                generated_at=utc_timestamp(),
                provider_response_id=exc.response_id,
                structured_output_validation=exc.structured_output_validation,
                deterministic_checks=(exc.code,),
            )
            return AgentRunResult(
                state=AgentRunState.FAILED,
                request=request,
                trace=trace,
                error_code=exc.code,
                error_message=exc.message,
            )
        if response.status is ProviderResponseStatus.NEEDS_INPUT:
            trace = AgentTraceRecord(
                candidate_id=None,
                request_id=request.request_id,
                provider=response.metadata.provider,
                model=response.metadata.model,
                generated_at=utc_timestamp(),
                provider_response_id=response.metadata.response_id,
                structured_output_validation=response.metadata.structured_output_validation,
                deterministic_checks=("MODEL_MISSING_INPUTS_ADAPTED",),
            )
            return AgentRunResult(
                state=AgentRunState.NEEDS_INPUT,
                request=request,
                needs_input=response.missing_inputs,
                interpretation=response.interpretation,
                explanation=response.explanation,
                explanation_metadata=response.explanation_metadata.__dict__,
                trace=trace,
            )
        try:
            candidates = tuple(self._materialize_candidate(request, response, draft) for draft in response.candidates)
        except AgentServiceError as exc:
            trace = AgentTraceRecord(
                candidate_id=None,
                request_id=request.request_id,
                provider=response.metadata.provider,
                model=response.metadata.model,
                generated_at=utc_timestamp(),
                provider_response_id=response.metadata.response_id,
                structured_output_validation=response.metadata.structured_output_validation,
                deterministic_checks=("governance_violation",),
            )
            return AgentRunResult(
                state=AgentRunState.FAILED,
                request=request,
                trace=trace,
                error_code="governance_violation",
                error_message=str(exc),
            )
        state = AgentRunState.ALTERNATIVES if len(candidates) > 1 or response.alternatives else AgentRunState.RESULT
        trace = AgentTraceRecord(
            candidate_id=candidates[0].candidate_id if candidates else None,
            request_id=request.request_id,
            provider=response.metadata.provider,
            model=response.metadata.model,
            generated_at=utc_timestamp(),
            provider_response_id=response.metadata.response_id,
            structured_output_validation=response.metadata.structured_output_validation,
            component_references=tuple(ref.component_id for ref in request.component_references),
            evidence_references=candidates[0].evidence_references if candidates else (),
            deterministic_checks=("MODEL_OUTPUT_ADAPTED",),
        )
        result = AgentRunResult(
            state=state,
            request=request,
            candidates=candidates,
            alternatives=response.alternatives,
            interpretation=response.interpretation,
            explanation=response.explanation,
            explanation_metadata=response.explanation_metadata.__dict__,
            trace=trace,
        )
        if self.candidate_store is not None:
            for candidate in result.candidates:
                self.candidate_store.save(candidate, project_id=self.project_id or request.project_id or str(request.context.get("project_id") or ""), normalized_inputs={"request_digest": request_digest(request)})
        return result

    def _materialize_candidate(self, request: AgentRequest, response: ProviderGenerationResponse, draft: Any) -> AgentCandidate:
        # The request's deterministic component snapshot is authoritative. A
        # provider cannot add, upgrade, or otherwise rewrite component tiers.
        request_refs = {ref.component_id: ref for ref in request.component_references}
        requested_ids = tuple(ref.component_id for ref in request.component_references)
        candidate_ids = tuple(ref.component_id for ref in draft.component_references)
        if candidate_ids != requested_ids:
            raise AgentServiceError("provider candidate must preserve the exact ordered request-bound component identities.")
        if not set(draft.evidence_references).issubset(set(request.evidence_references)):
            raise AgentServiceError("provider candidate evidence must remain within the authorized request evidence set.")
        refs = []
        unresolved = list(draft.unresolved_requirements)
        for ref in draft.component_references:
            original = request_refs.get(ref.component_id)
            if original is None:
                unresolved.append(f"provider_component_not_in_request:{ref.component_id}")
                continue
            if original.tier is ComponentTier.REFERENCE_ONLY:
                # Preserve reference-only status and make the boundary explicit.
                refs.append(original)
                continue
            refs.append(original)
        if len(refs) != len(draft.component_references):
            unresolved.append("provider_component_reference_mismatch")
        validation = AgentValidationSummary(
            status=DeterministicValidationStatus.NOT_RUN,
            checks=("provider_output_adapted",),
            authority="deterministic",
        )
        candidate = AgentCandidate(
            candidate_id=draft.candidate_id,
            workflow_type=request.workflow_type,
            host=request.host,
            user_intent=request.user_intent,
            cds_or_reference_input=request.cds_or_reference_input,
            component_references=tuple(refs),
            evidence_references=draft.evidence_references,
            provenance_references=tuple(dict.fromkeys(item for ref in refs for item in ref.provenance_references)),
            unresolved_requirements=tuple(dict.fromkeys(unresolved)),
            deterministic_validation=validation,
            provider_metadata=response.metadata.as_dict(),
            state=CandidateState.MODEL_GENERATED,
            rationale=draft.rationale,
            request_id=request.request_id,
        )
        return AgentCandidate(**{**candidate.__dict__, "content_digest": candidate_digest(candidate)})

    def validate_candidate(self, candidate: AgentCandidate) -> AgentCandidate:
        if candidate.state is not CandidateState.MODEL_GENERATED:
            raise AgentServiceError("only model-generated candidates can enter deterministic validation.")
        candidate_state_transition(candidate.state, CandidateState.DETERMINISTICALLY_VALIDATED)
        blocking: list[str] = list(candidate.unresolved_requirements)
        for ref in candidate.component_references:
            if ref.tier is ComponentTier.REFERENCE_ONLY:
                blocking.append(f"reference_only_component:{ref.component_id}")
        status = DeterministicValidationStatus.BLOCKED if blocking else DeterministicValidationStatus.PASS
        validation = AgentValidationSummary(
            status=status,
            checks=("component_tier_boundary", "provider_metadata_preserved", "request_identity_preserved"),
            blocking_reasons=tuple(dict.fromkeys(blocking)),
            authority="deterministic",
            checked_at=utc_timestamp(),
        )
        validated = AgentCandidate(
            **{**candidate.__dict__, "deterministic_validation": validation, "state": CandidateState.DETERMINISTICALLY_VALIDATED}
        )
        if self.product_validator is not None and validation.status is DeterministicValidationStatus.PASS:
            validated = self.product_validator(validated)
        if self.candidate_store is not None:
            payload = self.candidate_store.load_payload(validated.candidate_id)
            artifacts = dict(payload.get("artifacts") or {}) if payload else {}
            current_digest = candidate_digest(validated)
            for artifact in artifacts.values():
                if isinstance(artifact, dict) and artifact.get("input_signature") != current_digest:
                    artifact["fresh"] = False
            self.candidate_store.update(validated, state=validated.state.value, deterministic_validation={"status": validated.deterministic_validation.status.value, "checks": list(validated.deterministic_validation.checks), "blocking_reasons": list(validated.deterministic_validation.blocking_reasons), "warning_codes": list(validated.deterministic_validation.warning_codes), "authority": validated.deterministic_validation.authority, "checked_at": validated.deterministic_validation.checked_at}, content_digest=current_digest, artifacts=artifacts, updated_at=utc_timestamp())
        return validated

    def build_adoption_preview(self, candidate: AgentCandidate) -> AgentAdoptionPreview:
        if not _trusted_enum_value_is(
            getattr(candidate, "state", None),
            CandidateState.VALIDATED_CANDIDATE,
        ):
            raise AgentServiceError("adoption preview requires deterministic validation first.")
        validation = getattr(candidate, "deterministic_validation", None)
        if not _trusted_enum_value_is(
            getattr(validation, "status", None),
            DeterministicValidationStatus.PASS,
        ):
            raise AgentServiceError("blocked candidates cannot produce an adoption preview.")
        preview = AgentAdoptionPreview(
            preview_id=f"preview-{secrets.token_urlsafe(12)}",
            candidate_id=candidate.candidate_id,
            intended_project_changes=("record selected candidate reference", "record provenance and review trace"),
            deterministic_preconditions=("candidate identity unchanged", "component governance rechecked", "human confirmation bound to candidate"),
            provenance_references=candidate.provenance_references,
            request_id=candidate.request_id,
            candidate_digest=candidate_digest(candidate),
            service_id=self._service_id,
            issuance_nonce=secrets.token_urlsafe(18),
            lifecycle_state="ISSUED",
        )
        self._adoption_previews[(candidate.request_id, candidate.candidate_id)] = preview
        return preview

    def confirm_candidate(
        self,
        candidate: AgentCandidate,
        *,
        confirmation_id: str,
        preview: AgentAdoptionPreview | None = None,
    ) -> AgentCandidate:
        if not _trusted_enum_value_is(
            getattr(candidate, "state", None),
            CandidateState.VALIDATED_CANDIDATE,
        ):
            raise AgentServiceError("human confirmation requires deterministic validation first.")
        validation = getattr(candidate, "deterministic_validation", None)
        if not _trusted_enum_value_is(
            getattr(validation, "status", None),
            DeterministicValidationStatus.PASS,
        ):
            raise AgentServiceError("a blocked candidate cannot be confirmed.")
        if not confirmation_id.strip():
            raise AgentServiceError("confirmation_id is required.")
        issued_key = (candidate.request_id, candidate.candidate_id)
        issued_preview = self._adoption_previews.get(issued_key)
        bound_preview = preview or issued_preview
        if bound_preview is None:
            raise AgentServiceError("a service-issued adoption preview is required.")
        if issued_preview is None or bound_preview != issued_preview:
            raise AgentServiceError("adoption preview does not match an active service-issued candidate context.")
        if (
            bound_preview.service_id != self._service_id
            or not bound_preview.issuance_nonce
            or bound_preview.lifecycle_state != "ISSUED"
        ):
            raise AgentServiceError("adoption preview provenance or lifecycle state is invalid.")
        current_digest = candidate_digest(candidate)
        if (
            bound_preview.request_id != candidate.request_id
            or bound_preview.candidate_id != candidate.candidate_id
            or bound_preview.candidate_digest != current_digest
        ):
            raise AgentServiceError("adoption preview does not match the candidate context.")
        binding = (candidate.request_id, candidate.candidate_id, bound_preview.preview_id, current_digest)
        existing = self._confirmation_bindings.get(confirmation_id.strip())
        if existing is not None and existing != binding:
            raise AgentServiceError("confirmation_id is bound to a different candidate context.")
        self._confirmation_bindings[confirmation_id.strip()] = binding
        # Consume the issued artifact so a validated candidate cannot replay a
        # stale preview or confirmation after the first successful transition.
        self._adoption_previews.pop(issued_key, None)
        # HUMAN_CONFIRMED is a compatibility alias of VALIDATED_CANDIDATE in
        # the frozen lifecycle; confirmation is represented by the bound
        # token and persisted confirmation state below.
        confirmed = copy(candidate)
        object.__setattr__(confirmed, "human_confirmation_state", confirmation_id.strip())
        object.__setattr__(confirmed, "state", CandidateState.HUMAN_CONFIRMED)
        if self.candidate_store is not None:
            persisted = self.candidate_store.load_payload(candidate.candidate_id) or {}
            project_id = str(persisted.get("project_id") or self.project_id or "")
            self.candidate_store.update(
                confirmed,
                human_confirmation_state=confirmed.human_confirmation_state,
                state=confirmed.state.value,
                confirmation_binding={
                    "candidate_id": confirmed.candidate_id,
                    "project_id": project_id,
                    "request_id": confirmed.request_id,
                    "candidate_digest": current_digest,
                    "preview_id": bound_preview.preview_id,
                    "service_id": bound_preview.service_id,
                    "issuance_nonce": bound_preview.issuance_nonce,
                    "token_sha256": hashlib.sha256(confirmation_id.strip().encode("utf-8")).hexdigest(),
                    "status": "CONFIRMED",
                    "confirmed_at": utc_timestamp(),
                },
            )
        return confirmed

    def adoption_boundary(self, candidate: AgentCandidate) -> AgentAdoptionResult:
        """Return a fail-closed result; no Product adoption implementation exists."""
        if candidate.state is not CandidateState.HUMAN_CONFIRMED:
            return AgentAdoptionResult(candidate.candidate_id, AdoptionStatus.HUMAN_CONFIRMATION_REQUIRED, "Candidate-bound human confirmation is required before adoption.")
        return AgentAdoptionResult(candidate.candidate_id, AdoptionStatus.PREVIEW_ONLY, "Adoption boundary is prepared but Product state is not modified by this V1 backend skeleton.")

    def build_trace(self, request: AgentRequest, candidate: AgentCandidate) -> AgentTraceRecord:
        """Project a candidate lifecycle into a secret-free trace record."""
        metadata = candidate.provider_metadata
        return AgentTraceRecord(
            candidate_id=candidate.candidate_id,
            request_id=request.request_id,
            provider=str(metadata.get("provider") or "unknown"),
            model=str(metadata.get("model") or "unknown"),
            generated_at=utc_timestamp(),
            provider_response_id=metadata.get("response_id"),
            structured_output_validation=str(metadata.get("structured_output_validation") or "NOT_RUN"),
            deterministic_validation_result=candidate.deterministic_validation.status.value,
            human_confirmation_state=candidate.human_confirmation_state,
            component_references=tuple(ref.component_id for ref in candidate.component_references),
            evidence_references=candidate.evidence_references,
            deterministic_checks=candidate.deterministic_validation.checks,
            human_confirmation={"state": candidate.human_confirmation_state},
            adoption_result={"status": "NOT_RUN"},
        )


class AgentBackend:
    """Stable Product-facing service boundary (no HTTP server required)."""
    def __init__(self, provider: ModelProvider, *, candidate_store: Any, project_repository: Any | None = None, component_repository: ComponentRepository | None = None) -> None:
        from services.agent_candidate_store import AdoptionService
        self.store = candidate_store
        self.project_repository = project_repository
        self.service = AgentService(provider, component_repository=component_repository or V2ComponentRepository(), candidate_store=candidate_store)
        self.adoption = AdoptionService(
            candidate_store,
            formal_repository=project_repository,
            validator=self._revalidate_adoption_authority,
        )

    @staticmethod
    def _project_authority(project: Any) -> dict[str, str]:
        if isinstance(project, Mapping):
            workflow = str(project.get("workflow_type") or "").strip()
            host = str(project.get("host_context") or project.get("host") or "").strip()
            project_id = str(project.get("project_id") or "").strip()
            review_state = project.get("manual_review_state")
        else:
            workflow = str(getattr(project, "workflow_type", "") or "").strip()
            host = str(getattr(project, "host_context", "") or "").strip()
            project_id = str(getattr(project, "project_id", "") or "").strip()
            review_state = getattr(project, "manual_review_state", None)
        snapshot = review_state.get("formal_project_workflow_v1") if isinstance(review_state, Mapping) else None
        if isinstance(snapshot, Mapping):
            workflow = str(snapshot.get("workflow_type") or workflow).strip()
            definition = snapshot.get("project_definition")
            if isinstance(definition, Mapping):
                host = str(definition.get("plant_host") or host).strip()
        return {"project_id": project_id, "workflow_type": workflow, "host": host}

    def _revalidate_adoption_authority(self, candidate: AgentCandidate) -> AgentCandidate:
        """Revalidate current Formal/Registry authority before any mutation."""
        if self.project_repository is None:
            return candidate
        try:
            payload = self.store.load_payload(candidate.candidate_id, verify=True) or {}
            project_id = str(payload.get("project_id") or "").strip()
            if not project_id:
                return _adoption_rejection(candidate, "project_identity_missing")
            authority = self._project_authority(self.project_repository.load(project_id))
        except Exception:
            return _adoption_rejection(candidate, "project_authority_unavailable")
        if authority["project_id"] and authority["project_id"] != project_id:
            return _adoption_rejection(candidate, "project_identity_mismatch")

        aliases = {"pathway": "gate3_pathway"}
        current_workflow = aliases.get(authority["workflow_type"], authority["workflow_type"])
        candidate_workflow = aliases.get(candidate.workflow_type, candidate.workflow_type)
        if current_workflow and current_workflow != candidate_workflow:
            return _adoption_rejection(candidate, "workflow_identity_mismatch")
        if not current_workflow and (authority["host"] or candidate.component_references):
            return _adoption_rejection(candidate, "workflow_identity_missing")

        from services.formal_step3_component_authority import (
            formal_agent_component_admission,
            formal_host_species_identity,
        )
        from services.plant_component_workflow_registry import HOST_APPLICABILITY_ADMITTED

        current_host = formal_host_species_identity(authority["host"])
        candidate_host = formal_host_species_identity(candidate.host or "")
        direct_refs = tuple(
            ref
            for ref in candidate.component_references
            if _trusted_enum_value_is(ref.tier, ComponentTier.DIRECT_USE)
        )
        if candidate_host and (current_host or direct_refs) and candidate_host != current_host:
            return _adoption_rejection(candidate, "HOST_APPLICABILITY_WRONG_HOST")
        if direct_refs and candidate_host and not current_host:
            return _adoption_rejection(candidate, "HOST_APPLICABILITY_NOT_PROVEN")

        repository = self.service.component_repository
        host_gate = getattr(repository, "host_applicability_status", None)
        for ref in candidate.component_references:
            record = repository.resolve(ref.component_id) if repository is not None else None
            if record is None:
                return _adoption_rejection(candidate, f"component_not_resolved:{ref.component_id}")
            if ref.role and record.roles and ref.role not in record.roles:
                return _adoption_rejection(candidate, f"component_role_mismatch:{ref.component_id}")
            reference_tier = next(
                (
                    member
                    for member in ComponentTier
                    if _trusted_enum_value_is(ref.tier, member)
                ),
                None,
            )
            record_tier = next(
                (
                    member
                    for member in ComponentTier
                    if _trusted_enum_value_is(record.tier, member)
                ),
                None,
            )
            if reference_tier is None or record_tier is None or reference_tier is not record_tier:
                return _adoption_rejection(candidate, f"component_tier_mismatch:{ref.component_id}")
            if reference_tier is ComponentTier.DIRECT_USE and current_host:
                if not callable(host_gate):
                    return _adoption_rejection(candidate, "HOST_APPLICABILITY_NOT_PROVEN")
                status = host_gate(ref.component_id, current_host)
                if status != HOST_APPLICABILITY_ADMITTED:
                    return _adoption_rejection(candidate, str(status))

        if current_host and candidate.workflow_type == "single_gene":
            admission = formal_agent_component_admission(
                workflow_type=candidate.workflow_type,
                target_host_species=current_host,
            )
            admitted_by_role = {
                str(group.get("role") or ""): {
                    str(option.get("registry_component_id") or "")
                    for option in tuple(group.get("options") or ())
                    if option.get("formal_selectable")
                }
                for group in tuple(admission.get("roles") or ())
            }
            for role in tuple(admission.get("required_roles") or ()):
                selected = {ref.component_id for ref in candidate.component_references if ref.role == role}
                if not selected or not selected.issubset(admitted_by_role.get(str(role), set())):
                    return _adoption_rejection(candidate, f"component_admission_mismatch:{role}")
        return candidate

    def handle(self, request: AgentRequest) -> AgentRunResult:
        """Generate candidates; no Formal mutation occurs in this method."""
        if isinstance(self.service.component_repository, V2ComponentRepository) and request.component_references:
            bound = []
            for ref in request.component_references:
                record = self.service.component_repository.resolve(ref.component_id)
                if record is not None:
                    bound.append(replace(ref, tier=record.tier, library_tier=record.library_tier, canonical_v2_component_id=record.canonical_v2_component_id, sequence_sha256=record.sequence_sha256, provenance_references=record.provenance_references))
                else:
                    bound.append(ref)
            request = replace(request, component_references=tuple(bound))
        return self.service.generate(request)

    def generate_and_validate(self, request: AgentRequest) -> AgentRunResult:
        result = self.handle(request)
        if result.candidates:
            validated = tuple(self.service.validate_candidate(candidate) for candidate in result.candidates)
            return AgentRunResult(**{**result.__dict__, "candidates": validated})
        return result

    def validate(self, candidate_id: str) -> AgentCandidate:
        candidate = self.store.load(candidate_id)
        return self.service.validate_candidate(candidate)

    def adopt(self, request: Any):
        return self.adoption.adopt(request)


__all__ = [
    "AgentRunResult",
    "AgentService",
    "AgentServiceError",
    "InMemoryComponentRepository",
    "component_governance_needs",
    "component_tier_eligibility",
    "V1_COMPONENT_TIER_COUNTS",
    "V2ComponentRepository",
    "ProductComponentRepository",
    "AgentBackend",
]
