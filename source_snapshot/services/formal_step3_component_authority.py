"""Formal component-authority boundary for single-gene Step 3.

This adapter exposes only selections admitted by the existing Plant Component
Registry workflow contract. It never falls back to host-rule, demo, example,
test-only, or Catalog-candidate sequence data.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from services.plant_component_workflow_registry import (
    GENERIC_MULTI_TU_WORKFLOW,
    HOST_APPLICABILITY_ADMITTED,
    REGISTRY_SOURCE_TYPE,
    ROLE_COMPONENT_TYPES,
    host_applicability_gate,
    workflow_component_options,
)


_ROLE_LABELS = {
    "promoter": "启动子",
    "3_prime_regulatory_region": "3′端调控元件",
}

_USER_INPUT_METHODS = frozenset({"paste", "upload"})
_USER_THREE_PRIME_ROLES = frozenset(
    {
        "terminator",
        "three_prime_utr",
        "three_prime_regulatory_region",
        "three_prime_processing_termination_region",
    }
)


def formal_host_species_identity(value: str) -> str:
    """Resolve a Formal host value to the Registry scientific identity."""
    from services.plant_host_registry import list_hosts

    host = str(value or "").strip()
    for record in list_hosts():
        aliases = tuple(str(item).strip() for item in (record.get("aliases") or ()))
        known_values = {
            str(record.get("host_id") or "").strip(),
            str(record.get("scientific_name") or "").strip(),
            str(record.get("common_name") or "").strip(),
            *aliases,
        }
        if host in known_values or any(alias and alias in host for alias in aliases):
            return str(record.get("scientific_name") or host).strip()
    return host


def formal_step3_component_roles() -> tuple[dict[str, Any], ...]:
    """Return the required single-gene Step 3 roles as read-only metadata."""
    return tuple(
        {
            "role": role,
            "label": label,
            "component_types": tuple(sorted(ROLE_COMPONENT_TYPES.get(role, ()))),
        }
        for role, label in _ROLE_LABELS.items()
    )


def formal_agent_component_admission(
    *, workflow_type: str, target_host_species: str
) -> dict[str, Any]:
    """Project current Formal role/options authority for Agent validation."""
    if str(workflow_type or "").strip() != "single_gene":
        return {
            "supported": False,
            "workflow_type": str(workflow_type or "").strip(),
            "required_roles": (),
            "roles": (),
        }
    resolved_host = formal_host_species_identity(target_host_species)
    roles = tuple(
        {
            **role_contract,
            "options": tuple(
                formal_step3_component_options(
                    role=str(role_contract["role"]),
                    target_host_species=resolved_host,
                )
            ),
        }
        for role_contract in formal_step3_component_roles()
    )
    return {
        "supported": True,
        "workflow_type": "single_gene",
        "required_roles": tuple(str(item["role"]) for item in roles),
        "roles": roles,
    }


def empty_formal_step3_component(role: str) -> dict[str, Any]:
    """Return a render-safe empty slot without supplying biological data."""
    if role not in _ROLE_LABELS:
        raise ValueError(f"Unsupported formal Step 3 component role: {role or '<empty>'}.")
    return {
        "name": _ROLE_LABELS[role],
        "sequence": "",
        "source": "",
        "formal_selectable": False,
        "component_reference": {},
    }


def formal_step3_component_options(
    *,
    role: str,
    target_host_species: str,
    option_provider: Callable[..., list[dict[str, Any]]] = workflow_component_options,
) -> list[dict[str, Any]]:
    """Return UI options backed by formally admitted Registry selections only."""
    if role not in _ROLE_LABELS:
        raise ValueError(f"Unsupported formal Step 3 component role: {role or '<empty>'}.")
    rows = option_provider(
        role=role,
        workflow_id=GENERIC_MULTI_TU_WORKFLOW,
        target_host_species=str(target_host_species or "").strip(),
    )
    options: list[dict[str, Any]] = []
    for row in rows:
        reference = dict(row.get("component_reference") or {})
        if (
            not row.get("formal_selectable")
            or str(reference.get("source_type") or "") != REGISTRY_SOURCE_TYPE
            or not str(reference.get("registry_component_id") or "").strip()
        ):
            continue
        options.append(
            {
                "name": str(row.get("name") or _ROLE_LABELS[role]),
                "sequence": str(row.get("sequence") or ""),
                "source": str(row.get("source") or "Plant Component Registry V1"),
                "accession": str(row.get("accession") or ""),
                "version": str(row.get("accession") or ""),
                "location": str(
                    (row.get("feature_boundary_method") or {}).get("method") or ""
                ),
                "strand": 0,
                "registry_component_id": str(row.get("registry_component_id") or ""),
                "component_type": str(row.get("component_type") or ""),
                "formal_selectable": True,
                "component_reference": reference,
            }
        )
    return options


def revalidated_formal_step3_selection(
    saved: Mapping[str, Any],
    *,
    role: str,
    target_host_species: str,
    options: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a saved Registry selection only through current admission."""
    expected_role = "3_prime_regulatory_region" if role == "terminator" else role
    reference = dict(saved.get("component_reference") or {})
    component_id = str(reference.get("registry_component_id") or "").strip()
    resolved_host = formal_host_species_identity(target_host_species)
    if (
        expected_role not in _ROLE_LABELS
        or str(reference.get("source_type") or "") != REGISTRY_SOURCE_TYPE
        or str(reference.get("tu_role") or "") != expected_role
        or str(reference.get("requested_host") or "") != resolved_host
        or host_applicability_gate(
            {"host_applicability": reference.get("host_applicability_at_selection")},
            resolved_host,
        )
        != HOST_APPLICABILITY_ADMITTED
        or not component_id
    ):
        return None
    saved_sequence = str(saved.get("normalized_sequence") or "").strip().upper()
    for option in options:
        current = dict(option)
        current_reference = dict(current.get("component_reference") or {})
        if (
            str(current.get("registry_component_id") or "").strip() == component_id
            and str(current_reference.get("registry_component_id") or "").strip() == component_id
            and str(current_reference.get("tu_role") or "") == expected_role
            and str(current_reference.get("requested_host") or "") == resolved_host
            and host_applicability_gate(
                {"host_applicability": current_reference.get("host_applicability_at_selection")},
                resolved_host,
            )
            == HOST_APPLICABILITY_ADMITTED
            and str(current.get("sequence") or "").strip().upper() == saved_sequence
        ):
            return current
    return None


def formal_step3_authority_findings(
    *,
    promoter_options: list[Mapping[str, Any]],
    three_prime_options: list[Mapping[str, Any]],
    promoter_mode: str,
    three_prime_mode: str,
    selected_promoter: Mapping[str, Any] | None,
    selected_three_prime: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Return fail-closed findings for Registry and user-provided Step 3 inputs."""
    findings: list[dict[str, str]] = []
    slots = (
        (
            "promoter",
            "启动子",
            promoter_options,
            promoter_mode,
            selected_promoter,
        ),
        (
            "three_prime",
            "3′端调控元件",
            three_prime_options,
            three_prime_mode,
            selected_three_prime,
        ),
    )
    for key, label, options, mode, selected in slots:
        selected = dict(selected or {})
        if mode == "元件库" and not options:
            findings.append(
                {
                    "rule_id": f"no_formal_{key}_component",
                    "status": "阻断",
                    "message": (
                        f"当前植物宿主没有已获 Registry 正式选择资格的{label}；"
                        "Step 3 不会使用演示、示例、测试或目录候选记录替代。"
                    ),
                }
            )
            continue
        if mode == "用户序列":
            findings.extend(
                _user_provided_component_findings(
                    key=key,
                    label=label,
                    selected=selected,
                )
            )
            continue
        if mode != "元件库":
            findings.append(
                {
                    "rule_id": f"unsupported_{key}_input_mode",
                    "status": "阻断",
                    "message": f"当前{label}来源模式不受支持。",
                }
            )
            continue
        reference = dict(selected.get("component_reference") or {})
        if (
            not selected.get("formal_selectable")
            or str(reference.get("source_type") or "") != REGISTRY_SOURCE_TYPE
            or not str(reference.get("registry_component_id") or "").strip()
        ):
            findings.append(
                {
                    "rule_id": f"ineligible_formal_{key}_component",
                    "status": "阻断",
                    "message": f"当前{label}不是已获 Registry 正式选择资格的记录。",
                }
            )
            continue
        if key == "three_prime":
            component_type = str(selected.get("component_type") or "").strip().lower()
            if component_type not in {"terminator", "three_prime_regulatory_region"}:
                findings.append(
                    {
                        "rule_id": "unsupported_formal_three_prime_component_type",
                        "status": "阻断",
                        "message": "当前 Registry 3′端记录的元件类型不受支持，无法生成表达盒；请重新选择记录。",
                    }
                )
    return findings


def _user_provided_component_findings(
    *,
    key: str,
    label: str,
    selected: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Verify analyzed user input without granting it Registry authority."""
    findings: list[dict[str, str]] = []
    source_kind = str(selected.get("source_kind") or "").strip().lower()
    input_method = str(selected.get("source_input_method") or "").strip().lower()
    sequence = str(selected.get("normalized_sequence") or "").strip().upper()
    display_name = str(selected.get("display_name") or selected.get("name") or "").strip()
    component_reference = dict(selected.get("component_reference") or {})
    analyzed_asset = selected.get("asset")
    analyzed_sequence = (
        str(analyzed_asset.get("nucleotide_sequence") or "").strip().upper()
        if isinstance(analyzed_asset, Mapping)
        else ""
    )
    assisted_valid = False
    if component_reference.get("assisted_resolution"):
        from services.single_gene_assisted_components import validate_single_gene_assisted_reference

        try:
            validate_single_gene_assisted_reference(
                component_reference, sequence=sequence,
                role="promoter" if key == "promoter" else "three_prime_regulatory_region",
                project_id=str(selected.get("project_id") or ""),
                host=str(selected.get("assisted_project_host") or ""),
            )
            assisted_valid = True
        except ValueError:
            pass
    if selected.get("formal_selectable") or source_kind in {"registry", "registry_record"} or (component_reference and not assisted_valid):
        findings.append(
            {
                "rule_id": f"invalid_user_{key}_authority",
                "status": "阻断",
                "message": f"当前{label}未保持为用户提供记录，不能按用户序列路径生成。",
            }
        )
    if source_kind != "user_recorded" or input_method not in _USER_INPUT_METHODS:
        findings.append(
            {
                "rule_id": f"incomplete_user_{key}_provenance",
                "status": "阻断",
                "message": f"当前{label}的用户输入来源尚未完整记录。",
            }
        )
    if not display_name or not sequence or sequence != analyzed_sequence:
        findings.append(
            {
                "rule_id": f"invalid_user_{key}_input",
                "status": "阻断",
                "message": f"当前{label}需要名称和与分析结果一致的非空 DNA 序列。",
            }
        )
    if key == "three_prime":
        role = str(selected.get("biological_role") or "").strip().lower()
        if role not in _USER_THREE_PRIME_ROLES:
            findings.append(
                {
                    "rule_id": "unsupported_user_three_prime_role",
                    "status": "阻断",
                    "message": "当前用户提供的 3′端元件生物学角色不受支持。",
                }
            )
    return findings
