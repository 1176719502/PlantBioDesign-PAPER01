"""Agent-facing adapter for deterministic Product services and V2 catalog."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from services.agent_contracts import ComponentReference, ComponentTier, ToolCallRequest, ToolCallResult
from services.agent_service import ProductComponentRepository


class AgentProductAdapter:
    def __init__(self, *, project_repository: Any | None = None, component_repository: Any | None = None) -> None:
        self.project_repository = project_repository
        self.component_repository = component_repository or ProductComponentRepository()

    def read_project_context(self, project_id: str) -> dict[str, Any]:
        if self.project_repository is None:
            return {"project_id": project_id, "available": False}
        from services.formal_project_persistence import formal_agent_project_projection

        projection = formal_agent_project_projection(
            project_id, repository=self.project_repository
        )
        workflow_type = str(projection.get("workflow_type") or "")
        from services.formal_step3_component_authority import formal_host_species_identity

        host = formal_host_species_identity(str(projection.get("host") or ""))
        existing_components: list[dict[str, Any]] = []
        limitations: list[str] = []
        for selected in projection.pop("component_selections", ()):
            try:
                existing_components.append(
                    self._admit_formal_selection(
                        selected,
                        workflow_type=workflow_type,
                        host=host,
                    )
                )
            except (ValueError, TypeError, KeyError):
                limitations.append(
                    f"Formal selection {selected.get('state_key') or '<unknown>'} could not be projected through current component admission."
                )
        return {
            **projection,
            "available": True,
            "existing_components": existing_components,
            "limitations": limitations,
        }

    def component_shortlist(
        self,
        *,
        workflow_type: str,
        host: str,
        existing_components: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return options projected from Formal's current admission result."""
        from services.formal_step3_component_authority import (
            formal_agent_component_admission,
        )
        from services.plant_component_workflow_registry import GENERIC_MULTI_TU_WORKFLOW

        contract = formal_agent_component_admission(
            workflow_type=workflow_type,
            target_host_species=host,
        )
        if not contract.get("supported"):
            return {"supported": False, "roles": (), "workflow_id": ""}
        role_groups = []
        for role_contract in tuple(contract.get("roles") or ()):
            role = str(role_contract["role"])
            options = tuple(
                {
                    "component_id": str(row.get("registry_component_id") or ""),
                    "name": str(row.get("name") or row.get("registry_component_id") or ""),
                    "role": role,
                    "role_label": str(role_contract["label"]),
                    "tier": ComponentTier.DIRECT_USE.value,
                    "selectable": True,
                    "sequence_required": False,
                    "source": str(row.get("source") or "Plant Component Registry V1"),
                    "accession": str(row.get("accession") or ""),
                }
                for row in tuple(role_contract.get("options") or ())
            )
            allowed_ids = {str(item["component_id"]) for item in options}
            existing = next(
                (
                    dict(item)
                    for item in (existing_components or ())
                    if str(item.get("role") or "") == role
                    and str(item.get("component_id") or "") in allowed_ids
                    and isinstance(item.get("reference"), ComponentReference)
                    and item["reference"].role == role
                    and item["reference"].component_id == str(item.get("component_id") or "")
                ),
                None,
            )
            role_groups.append(
                {
                    **{key: value for key, value in dict(role_contract).items() if key != "options"},
                    "existing": existing,
                    "options": () if existing is not None else options,
                }
            )
        return {
            "supported": True,
            "roles": tuple(role_groups),
            "workflow_id": GENERIC_MULTI_TU_WORKFLOW,
        }

    def resolve_component_references(
        self,
        component_ids: list[str] | tuple[str, ...],
        *,
        workflow_type: str,
        host: str,
        existing_components: list[Mapping[str, Any]] | None = None,
    ) -> tuple[ComponentReference, ...]:
        """Resolve human selections only after current shortlist admission."""
        shortlist = self.component_shortlist(
            workflow_type=workflow_type,
            host=host,
            existing_components=existing_components,
        )
        allowed = {
            str(option["component_id"]): str(role["role"])
            for role in shortlist["roles"]
            for option in role["options"]
            if option["selectable"]
        }
        existing_refs = {
            str(group["existing"].get("component_id") or ""): group["existing"].get("reference")
            for group in shortlist["roles"]
            if isinstance(group.get("existing"), Mapping)
            and isinstance(group["existing"].get("reference"), ComponentReference)
        }
        ordered_ids = tuple(dict.fromkeys(str(item).strip() for item in component_ids if str(item).strip()))
        references = []
        for component_id in ordered_ids:
            if component_id in existing_refs:
                references.append(existing_refs[component_id])
                continue
            if component_id not in allowed:
                raise ValueError("component selection is not in the current eligible shortlist")
            record = self.component_repository.resolve(component_id)
            if record is None or record.tier is not ComponentTier.DIRECT_USE:
                raise ValueError("component selection did not resolve through current admission")
            references.append(self._component_reference(record, role=allowed[component_id]))
        return tuple(references)

    def lookup_components(self, component_ids: list[str] | None = None, *, query: str = "") -> list[dict[str, Any]]:
        ids = component_ids or []
        if ids:
            records = [self.component_repository.resolve(item) for item in ids]
            return [self._record_dict(record) for record in records if record is not None and record.library_tier != "RETIRED"]
        from services.component_library_v2_adoption import build_v2_canonical_inventory
        needle = query.casefold().strip()
        rows = [row for row in build_v2_canonical_inventory() if row.get("library_tier") != "RETIRED"]
        if needle:
            rows = [row for row in rows if needle in str(row.get("name") or "").casefold() or needle in str(row.get("role") or "").casefold()]
        return rows

    def select_components(
        self,
        component_ids: list[str],
        *,
        workflow_type: str,
        host: str,
    ) -> dict[str, Any]:
        shortlist = self.component_shortlist(workflow_type=workflow_type, host=host)
        allowed_ids = {
            str(option.get("component_id") or "")
            for role in tuple(shortlist.get("roles") or ())
            for option in tuple(role.get("options") or ())
            if option.get("selectable")
        }
        if not component_ids or any(component_id not in allowed_ids for component_id in component_ids):
            raise ValueError("component is not in the current eligible shortlist")
        selected = self.lookup_components(component_ids)
        if len(selected) != len(component_ids):
            raise ValueError("unknown component identity")
        if any(str(item.get("admission_mode") or "REFERENCE_ONLY") != "DIRECT_USE" for item in selected):
            raise ValueError("component is not currently admitted for direct use")
        return {"components": selected, "canonical_ids": [str(item.get("canonical_v2_component_id")) for item in selected], "admission_modes": [str(item.get("admission_mode") or "REFERENCE_ONLY") for item in selected]}

    def _admit_formal_selection(
        self,
        selected: Mapping[str, Any],
        *,
        workflow_type: str,
        host: str,
    ) -> dict[str, Any]:
        from services.formal_step3_component_authority import (
            formal_agent_component_admission,
            formal_host_species_identity,
        )
        from services.plant_component_workflow_registry import (
            GENERIC_MULTI_TU_WORKFLOW,
            REGISTRY_SOURCE_TYPE,
            admit_registry_selection,
        )

        selection = dict(selected.get("component_reference") or {})
        role = str(selection.get("tu_role") or "")
        sequence = str(selected.get("sequence") or selection.get("selected_sequence") or "")
        source_type = str(selection.get("source_type") or "")
        if source_type != REGISTRY_SOURCE_TYPE or workflow_type != "single_gene":
            raise ValueError("Formal selection has no reusable canonical component identity")
        admitted = admit_registry_selection(
            selection,
            role=role,
            sequence=sequence,
            workflow_id=GENERIC_MULTI_TU_WORKFLOW,
        )
        resolved_host = formal_host_species_identity(host)
        if str(admitted.get("requested_host") or "") != resolved_host:
            raise ValueError("Formal selection host does not match the current project host")
        component_id = str(admitted.get("registry_component_id") or "")
        contract = formal_agent_component_admission(
            workflow_type=workflow_type,
            target_host_species=resolved_host,
        )
        admitted_ids = {
            str(option.get("registry_component_id") or "")
            for group in tuple(contract.get("roles") or ())
            if str(group.get("role") or "") == role
            for option in tuple(group.get("options") or ())
        }
        if component_id not in admitted_ids:
            raise ValueError("Formal selection is not admitted for the current host and role")
        record = self.component_repository.resolve(component_id)
        if record is None or record.tier is not ComponentTier.DIRECT_USE:
            raise ValueError("Formal selection is not currently admitted")
        return {
            "component_id": component_id,
            "name": str(admitted.get("display_name") or selected.get("display_name") or component_id),
            "role": role,
            "tier": record.tier.value,
            "source": source_type,
            "reference": self._component_reference(record, role=role),
        }

    @staticmethod
    def _component_reference(record: Any, *, role: str = "") -> ComponentReference:
        return ComponentReference(
            component_id=record.component_id,
            role=role or (record.roles[0] if record.roles else ""),
            tier=record.tier,
            evidence_references=record.evidence_references,
            provenance_references=record.provenance_references,
            library_tier=record.library_tier,
            canonical_v2_component_id=record.canonical_v2_component_id,
            sequence_sha256=record.sequence_sha256,
        )

    def build_single_gene(self, **kwargs: Any) -> dict[str, Any]:
        from services.formal_single_gene_runtime import generate_complete_vector
        return generate_complete_vector(**kwargs)

    @staticmethod
    def validate_artifacts(artifacts: Mapping[str, Any], input_signature: str) -> dict[str, Any]:
        result = {}
        for name, artifact in artifacts.items():
            if not isinstance(artifact, Mapping):
                result[name] = {"fresh": False}; continue
            data = str(artifact.get("data") or "").encode("utf-8")
            result[name] = {"fresh": str(artifact.get("input_signature") or input_signature) == input_signature, "sha256": hashlib.sha256(data).hexdigest()}
        return result

    @staticmethod
    def _record_dict(record: Any) -> dict[str, Any]:
        tier = getattr(getattr(record, "tier", None), "value", getattr(record, "tier", ""))
        return {
            name: getattr(record, name)
            for name in (
                "component_id",
                "library_tier",
                "canonical_v2_component_id",
                "sequence_sha256",
                "sequence_available",
                "sequence_verified",
                "rights_status",
                "admission_status",
            )
            if hasattr(record, name)
        } | {"tier": tier, "admission_mode": tier}


READ_ONLY_TOOLS = frozenset({"project_context_read", "component_library_lookup"})
CANDIDATE_ONLY_TOOLS = frozenset({"candidate_component_selection", "single_gene_candidate_build", "candidate_validate", "artifact_freshness_check"})
MUTATING_TOOLS = frozenset({"formal_project_write", "formal_candidate_adopt", "canonical_construct_write"})


class AgentToolDispatcher:
    def __init__(self, adapter: AgentProductAdapter) -> None:
        self.adapter = adapter

    def dispatch(self, request: ToolCallRequest) -> ToolCallResult:
        if request.name in MUTATING_TOOLS:
            return ToolCallResult(False, error_code="MUTATION_REQUIRES_ADOPTION", error_message="Formal mutations are available only through explicit adoption.")
        try:
            if request.name == "project_context_read": data = self.adapter.read_project_context(str(request.arguments.get("project_id") or ""))
            elif request.name == "component_library_lookup": data = {"records": self.adapter.lookup_components(request.arguments.get("component_ids"), query=str(request.arguments.get("query") or ""))}
            elif request.name == "candidate_component_selection": data = self.adapter.select_components(
                [str(x) for x in request.arguments.get("component_ids") or []],
                workflow_type=str(request.arguments.get("workflow_type") or ""),
                host=str(request.arguments.get("host") or ""),
            )
            elif request.name == "single_gene_candidate_build": data = self.adapter.build_single_gene(**dict(request.arguments))
            elif request.name == "artifact_freshness_check": data = self.adapter.validate_artifacts(dict(request.arguments.get("artifacts") or {}), str(request.arguments.get("input_signature") or ""))
            elif request.name == "candidate_validate": data = {"validated": True, "authority": "deterministic_product"}
            else: return ToolCallResult(False, error_code="TOOL_NOT_AVAILABLE", error_message="Tool is not available in V1.")
            return ToolCallResult(True, data=data)
        except Exception:
            return ToolCallResult(False, error_code="TOOL_FAILED", error_message="Tool execution failed safely.")


__all__ = ["AgentProductAdapter", "AgentToolDispatcher", "READ_ONLY_TOOLS", "CANDIDATE_ONLY_TOOLS", "MUTATING_TOOLS"]
