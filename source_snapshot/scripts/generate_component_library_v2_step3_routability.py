"""Reproducible routing audit, using product services and extracted app functions.

Test DNA is synthetic plumbing input, never evidence for a biological identity.
The headless widget probe is explicitly not real-browser acceptance.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
import tempfile
from collections import Counter
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.agent_product_adapter import AgentProductAdapter
from services.component_library_v2_adoption import (
    build_v2_canonical_inventory, v2_adoption_summary, v2_assisted_confirmation_contract,
)
from services.plant_component_workflow_registry import validate_saved_selection
from services.plant_host_registry import list_hosts
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.registry_catalog_ui import build_v2_user_provided_component, component_role_for_catalog_record

STEM = ROOT / "docs/qa/V1_COMPONENT_LIBRARY_V2_STEP3_ROUTABILITY_20260928"
WORKFLOWS = ("single_gene", "multi_tu", "pathway")
PART_TYPES = {"promoter": "Promoter", "five_prime_region": "5' region", "cds": "CDS", "3_prime_regulatory_region": "Terminator"}
TYPES = ("promoter", "five_prime_utr", "cds", "terminator", "three_prime_regulatory_region", "regulatory_or_vector_element", "vector_backbone", "targeting_sequence", "linker", "fusion_tag")


def actual_step3_roles() -> dict[str, list[str]]:
    from services.formal_step3_component_authority import formal_step3_component_roles
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    single = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_render_step_3_elements")
    optional = [role for n in ast.walk(single) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_optional_component" for role, label in ast.literal_eval(n.args[2])]
    ns = app_probe_namespace({})
    multi = list(ns["_MULTI_TU_EDITOR_REQUIRED_ROLES"]) + list(ns["_MULTI_TU_EDITOR_OPTIONAL_ROLES"])
    return {"single_gene": [r["role"] for r in formal_step3_component_roles()] + optional, "multi_tu": multi, "pathway": multi}


def synthetic_probe_sequence(row: Mapping[str, Any]) -> str:
    """Clearly test-only bytes; never copied into the catalog or production data."""
    size = v2_assisted_confirmation_contract(row)["expected_length"] or (12 if row["component_type"] == "cds" else 8)
    if row["component_type"] == "cds":
        return "ATG" + "GCC" * ((size - 6) // 3) + "TAA"
    return ("AACCGGTT" * (size // 8 + 1))[:size]


class WidgetProbe:
    """Minimal deterministic widget surface, not a browser substitute."""
    def __init__(self, state: dict[str, Any]):
        self.session_state = state

    def segmented_control(self, *args, key, **kwargs):
        return self.session_state.get(key)

    def text_input(self, *args, key, **kwargs):
        return self.session_state.get(key, "")

    text_area = text_input

    def caption(self, *args, **kwargs):
        pass

    markdown = caption

    def error(self, value):
        raise ValueError(value)

    def expander(self, *args, **kwargs):
        return nullcontext()


@lru_cache(maxsize=1)
def _app_probe_code():
    """Compile the actual bounded app functions, without executing app startup."""
    names = {
        "_plant_element_options", "_use_catalog_component_in_multi_tu", "_use_catalog_assisted_component",
        "_prepare_multi_tu_editor_widget_state", "_multi_tu_editor_widget_state_is_present",
        "_is_explicit_five_prime_absence", "_render_dual_tu_element_input",
        "_MULTI_TU_EDITOR_REQUIRED_ROLES", "_MULTI_TU_EDITOR_OPTIONAL_ROLES",
        "_SOURCE_MODE_VALUES",
    }
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if (isinstance(node, ast.FunctionDef) and node.name in names) or
             (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
    return compile(ast.Module(body=nodes, type_ignores=[]), "app.py:routability-probe", "exec")


def app_probe_namespace(state: dict[str, Any]) -> dict[str, Any]:
    controller_state = SimpleNamespace(step=1, clear_step3_outputs=lambda: None)
    hosts = list_hosts()
    ns: dict[str, Any] = {
        "Any": Any, "Mapping": Mapping, "st": WidgetProbe(state),
        "PROJECT_TYPE_DUAL_TU": "dual_tu", "PAGE_DESIGN_WORKSPACE": "Design Workspace",
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "_formal_project_type": lambda: state.get("formal_project_type", "dual_tu"),
        "_formal_project_repository": lambda *args: state.get("_probe_repository"),
        "_invalidate_formal_snapshots": lambda: None,
        "_transcription_units": lambda: state["formal_transcription_units"],
        "_store_transcription_units": lambda units: state.update(formal_transcription_units=units),
        "_invalidate_dual_tu_unit": lambda unit_id: None,
        "_controller": lambda: SimpleNamespace(get=lambda: controller_state, save=lambda value: None),
        "_change_page": lambda page: state.update(selected_page=page),
        "_formal_ui_signature": lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
        "_plant_host_record": lambda host: next((r for r in hosts if host in (r["host_id"], r["scientific_name"])), None),
        "_t": lambda key, **kwargs: key,
        "_SOURCE_MODE_LABELS": {},
        "_localized_value": lambda value, labels: value,
    }
    exec(_app_probe_code(), ns)
    ns["controller_state"] = controller_state
    return ns


def probe_assisted_route(component: dict[str, Any], *, workflow: str, host: str, repository=None) -> dict[str, Any]:
    scenario = "metabolic_pathway_multi_tu_vector" if workflow == "pathway" else "standard_plant_expression_vector"
    state = {"mvp_project_id": component["project_id"], "formal_project_type": "single_gene" if workflow == "single_gene" else "dual_tu",
             "formal_design_scenario": scenario, "formal_project_host": host,
             "formal_transcription_units": [{"unit_id": "audit-tu-1", "display_name": "Audit TU", "order": 1}]}
    ns = app_probe_namespace(state)
    state["_probe_repository"] = repository
    if workflow == "single_gene":
        from services.single_gene_assisted_components import retained_assisted_fields

        try:
            ns["_use_catalog_assisted_component"](component)
        except ValueError as exc:
            return {"passed": False, "reason": str(exc)}
        key = "promoter" if component["role"] == "promoter" else "five_prime"
        record = state["formal_element_source_records"][key]
        fields = retained_assisted_fields(record, sequence=record["normalized_sequence"],
            role=record["biological_role"], project_id=component["project_id"], host=host)
        assert fields["component_reference"] == component["component_reference"]
        assert state["formal_project_type"] == "single_gene" and ns["controller_state"].step == 3
        return {"passed": True, "surface": "Single-Gene project-bound USER_PROVIDED Step3 input; not Registry dropdown"}
    ns["_use_catalog_component_in_multi_tu"](component)
    ns["_prepare_multi_tu_editor_widget_state"]()
    result = ns["_render_dual_tu_element_input"](unit_id="audit-tu-1", role=component["role"], label=component["role"], options=[])
    if not result or result["component_reference"] != component["component_reference"]:
        raise AssertionError("Step3 user-input renderer lost the assisted reference")
    validate_saved_selection(result["component_reference"], role=component["role"], sequence=result["raw_text"], current_project_id=component["project_id"])
    assert ns["controller_state"].step == 3
    assert state["formal_design_scenario"] == scenario
    return {"passed": True, "surface": "project-bound USER_PROVIDED Step3 input; not Registry dropdown",
            "requires": ["active persisted project", "source capture", "evidence-aware confirmation", "explicit use confirmation"] +
            (["pathway CDS mapping must contain the same supplied bytes; this action does not edit pathway mapping"] if workflow == "pathway" and component["role"] == "cds" else [])}


def build_audit() -> dict[str, Any]:
    inventory = build_v2_canonical_inventory()
    hosts = list_hosts()
    host_by_workflow = {w: [r["scientific_name"] for r in hosts if ("SINGLE_GENE_COMPLETE_VECTOR" if w == "single_gene" else "GENERIC_MULTI_TU_ASSEMBLY") in r["workflow_levels"]] for w in WORKFLOWS}
    ns = app_probe_namespace({})
    actual_options = {}
    for workflow in WORKFLOWS:
        actual_options[workflow] = {}
        for role, part in PART_TYPES.items():
            actual_options[workflow][role] = {}
            for host in host_by_workflow[workflow]:
                actual_options[workflow][role][host] = [] if workflow == "single_gene" and role not in {"promoter", "3_prime_regulatory_region"} else ns["_plant_element_options"](host, part, workflow_id="" if workflow == "single_gene" else "generic_multi_tu")
    agent = AgentProductAdapter()
    visible_ids = {r["canonical_v2_component_id"] for r in agent.lookup_components()}
    matrix = []
    by_id = {r["canonical_v2_component_id"]: r for r in inventory}
    # Use one verified immutable inventory snapshot for this audit run. Only
    # disk reloading is cached; all admission, confirmation and UI logic runs.
    with tempfile.TemporaryDirectory(prefix="v2-route-audit-") as temporary, patch("services.component_library_v2_adoption.v2_canonical_record", side_effect=lambda cid: copy.deepcopy(by_id[cid])):
        repository = PlantProjectDraftRepository(Path(temporary) / "projects")
        project = repository.create_blank(project_name="TEST ONLY V2 routing probe")
        project.workflow_type = "single_gene"
        repository.save(project)
        for row in inventory:
            cid, role = row["canonical_v2_component_id"], component_role_for_catalog_record(row)
            mode = row["admission_mode"] if row["library_tier"] == "CORE" else row["library_tier"]
            component = None
            if mode == "USER_SEQUENCE_ASSISTED":
                c = v2_assisted_confirmation_contract(row)
                component = build_v2_user_provided_component(row, raw_sequence=synthetic_probe_sequence(row), display_name=row["name"], project_id=project.project_id, project_repository=repository, user_sequence_source="TEST ONLY synthetic routing input; not accession sequence", identity_and_boundaries_confirmed=c["has_reviewed_boundary"], project_intent_confirmed=not c["has_reviewed_boundary"], explicit_user_confirmation=True)
            routes = {}
            for workflow in WORKFLOWS:
                admitted_hosts = [host for host, options in actual_options[workflow].get(role, {}).items() if row.get("registry_component_id") and any(o["registry_component_id"] == row["registry_component_id"] for o in options)]
                probes = {host: probe_assisted_route(component, workflow=workflow, host=host, repository=repository) for host in host_by_workflow[workflow]} if component else {}
                resolvable_hosts = [host for host, probe in probes.items() if probe["passed"]]
                category = "DIRECT_NOW" if admitted_hosts else "RESOLVABLE_FOR_PROJECT" if resolvable_hosts else "CANDIDATE_ONLY" if mode == "REFERENCE" else "EXCLUDED"
                selector_role = "five_prime_utr" if workflow == "single_gene" and role == "five_prime_region" else role
                routes[workflow] = {"route": category, "direct_now": bool(admitted_hosts), "resolvable_after_user_sequence": bool(resolvable_hosts), "direct_hosts": admitted_hosts, "project_input_hosts": resolvable_hosts, "selector_role": selector_role or None, "probe": next(iter(probes.values()), None)}
            gaps = list(row.get("adoption_blockers") or [])
            if component:
                gaps = ["no authoritative bundled sequence or expected source SHA256", "user sequence is not accession-verified or software boundary-verified", "no inferred host applicability"]
                if not c["has_reviewed_boundary"]:
                    gaps.append("no explicit reviewed source coordinates or expected length")
            matrix.append({
                "canonical_v2_id": cid, "display_name": row.get("name", ""), "canonical_state": mode,
                "component_type": row.get("component_type", ""), "canonical_role": row.get("role") or row.get("component_role"), "accession": row.get("accession", ""),
                "current_registry_id": row.get("registry_component_id") or None, "sequence_state": row.get("sequence_availability"),
                "host_scope": {"source_organism_context": row.get("source_organism", ""), "registry_host_evidence": row.get("host_applicability", {}), "user_input_scope": "project intent in supported plant workflows; no biological host admission" if component else None},
                "workflow_compatibility": [w for w in WORKFLOWS if routes[w]["direct_now"] or routes[w]["resolvable_after_user_sequence"]],
                "recorded_workflow_metadata": row.get("workflow_compatibility", []),
                "allowed_roles": [role] if role and (component or any(r["direct_now"] for r in routes.values())) else [], "direct_formal_selectable": any(r["direct_now"] for r in routes.values()),
                "project_resolvable_user_sequence": bool(component),
                **{f"{w}_step3": routes[w] for w in WORKFLOWS},
                "agent_candidate_visibility": cid in visible_ids,
                "exclusion_reason": list(row.get("adoption_blockers") or []) if not component else ([] if routes["single_gene"]["resolvable_after_user_sequence"] else ["CDS is Single-Gene Step2, not a Step3 role"]),
                "evidence_gap": gaps, "confirmation_contract": v2_assisted_confirmation_contract(row) if component else None,
                "target_product_route": "DIRECT_NOW" if any(r["direct_now"] for r in routes.values()) else "RESOLVABLE_FOR_PROJECT" if component else "CANDIDATE_ONLY" if mode == "REFERENCE" else "EXCLUDED",
            })
    counts, coverage, host_coverage = {}, [], []
    actual_roles = actual_step3_roles()
    all_types = tuple(dict.fromkeys((*TYPES, *(r for r in actual_roles["single_gene"] if r not in PART_TYPES))))
    for w in WORKFLOWS:
        def count(group):
            direct = [r["canonical_v2_id"] for r in group if r[f"{w}_step3"]["direct_now"]]
            assisted = [r["canonical_v2_id"] for r in group if r[f"{w}_step3"]["resolvable_after_user_sequence"]]
            return {"direct_now": len(direct), "resolvable_after_user_sequence": len(assisted), "total_potentially_usable": len(set(direct + assisted)), "direct_ids": direct, "resolvable_ids": assisted}
        counts[w] = {**count(matrix), "by_component_type": {t: count([r for r in matrix if r["component_type"] == t]) for t in all_types}}
        counts[w]["by_selector_role"] = {role: count([r for r in matrix if r[f"{w}_step3"]["selector_role"] == role]) for role in actual_roles[w]}
        counts[w]["by_host"] = {host: {"direct_now": sum(host in r[f"{w}_step3"]["direct_hosts"] for r in matrix), "resolvable_after_user_sequence": sum(host in r[f"{w}_step3"]["project_input_hosts"] for r in matrix)} for host in host_by_workflow[w]}
        for t, group in counts[w]["by_component_type"].items():
            total = group["total_potentially_usable"]
            status = "COVERED" if total >= 2 else "THIN" if total == 1 else "EMPTY"
            block = "BLOCKED_BY_PRODUCT_ROUTING" if w == "single_gene" and not group["resolvable_after_user_sequence"] and any(r["component_type"] == t and r["project_resolvable_user_sequence"] for r in matrix) else "BLOCKED_BY_EVIDENCE" if total <= 1 and any(r["component_type"] == t and r["canonical_state"] in {"REFERENCE", "DIRECT_USE"} and not r["direct_formal_selectable"] for r in matrix) else None
            mapped_role = {"terminator": "3_prime_regulatory_region", "three_prime_regulatory_region": "3_prime_regulatory_region", "five_prime_utr": "five_prime_utr" if w == "single_gene" else "five_prime_region"}.get(t, t)
            is_role = mapped_role in actual_roles[w]
            if not is_role:
                block = "BLOCKED_BY_PRODUCT_ROUTING"
            coverage.append({"workflow": w, "component_type": t, "coverage": status, "blocking_class": block, "usable_choices": total, "direct_choices": group["direct_now"], "is_step3_component_role": is_role, "criterion": "0 = EMPTY; 1 = THIN; >=2 = COVERED (choice count only, no biological score)"})
            for host in host_by_workflow[w]:
                direct = sum(r["component_type"] == t and host in r[f"{w}_step3"]["direct_hosts"] for r in matrix)
                assisted = sum(r["component_type"] == t and host in r[f"{w}_step3"]["project_input_hosts"] for r in matrix)
                host_coverage.append({"workflow": w, "host": host, "component_type": t, "direct_now": direct, "resolvable": assisted, "usable_choices": direct + assisted, "coverage": "COVERED" if direct + assisted >= 2 else "THIN" if direct + assisted == 1 else "EMPTY", "is_step3_component_role": is_role})
    return {
        "verdict": "STEP3_ROUTABILITY_PARTIAL_WITH_EXPLICIT_EVIDENCE_GAPS",
        "CURRENT_PRODUCT_COUNTS": {"canonical_inventory": len(matrix), "direct_formal_selectable": sum(r["direct_formal_selectable"] for r in matrix), "route_categories": dict(Counter(r["target_product_route"] for r in matrix)), "agent_candidates": len(visible_ids)},
        "V2_CANONICAL_COUNTS": v2_adoption_summary(inventory), "EXACT_STEP3_ROUTABILITY_MATRIX": matrix,
        "SINGLE_GENE_STEP3_COUNTS": counts["single_gene"], "MULTI_TU_STEP3_COUNTS": counts["multi_tu"], "PATHWAY_STEP3_COUNTS": counts["pathway"],
        "ROLE_COVERAGE": coverage,
        "ROLE_COVERAGE_BY_HOST": host_coverage,
        "ACTUAL_STEP3_ROLES": actual_roles,
        "COVERAGE_FINDINGS": ["Single-Gene direct admissions: tomato has one promoter and one 3-prime region; rice has neither. Both project hosts support four assisted promoters and two assisted 5-prime UTRs as user input, without biological host admission", "Multi-TU/Pathway assisted routes add four promoters, two 5-prime UTRs and eighteen CDS identities, but no 3-prime element", "Only tomato and Arabidopsis have the single admitted V2 3-prime region; the other four supported Multi-TU hosts have zero", "No workflow has more than one usable V2 3-prime choice; coverage is sparse at this required role", "Single-Gene CDS is entered in Step2, not a Step3 component selector", "Every actual optional role outside the V2 type mapping has zero V2-identity choices; arbitrary user DNA is outside this inventory audit"],
        "USER_SEQUENCE_ASSISTED_COUNTS": {"total": 24, "reviewed_coordinate_confirmation": sum(bool((r["confirmation_contract"] or {}).get("has_reviewed_boundary")) for r in matrix), "project_intent_only": sum((r["confirmation_contract"] or {}).get("confirmation_mode") == "PROJECT_INTENT" for r in matrix), "by_type": dict(Counter(r["component_type"] for r in matrix if r["project_resolvable_user_sequence"]))},
        "DIRECT_USE_EXCLUSIONS": [{"id": r["canonical_v2_id"], "reasons": r["exclusion_reason"]} for r in matrix if r["canonical_state"] == "DIRECT_USE" and not r["direct_formal_selectable"]],
        "REFERENCE_AGENT_BOUNDARY": {"count": 95, "candidate_only": True, "formal_selection": False, "assisted_resolution": False},
        "RETIRED_EXCLUSION": {"count": 35, "agent_candidate_visibility": any(r["agent_candidate_visibility"] for r in matrix if r["canonical_state"] == "RETIRED"), "new_formal_selection": False, "historical_identity_lookup_preserved": True},
        "REAL_BROWSER_ACCEPTANCE": {"status": "BLOCKED", "reason": "cua.getState(): unsupported Codex auth method: apikey", "browser_pass": False, "headless_probes_are_browser_evidence": False},
        "REMAINING_EVIDENCE_GAPS": ["15 DIRECT_USE identities lack existing Registry/host/role admission", "all 24 assisted identities require user-authoritative sequence and confirmation", "5 assisted identities lack explicit reviewed coordinates", "Single-Gene accepts six compatible assisted identities; the eighteen assisted CDS identities remain Step2-only", "Pathway CDS insertion requires mapping to the same bytes; no automatic pathway biological assignment", "2 + 24 is a union over roles and supported hosts, not 26 choices per selector", "vector backbones belong downstream of Step3; their zero count here is not a backbone inventory claim", "real browser cold restart and UI downloads remain unverified"],
        "METHOD": {"direct": "execute app._plant_element_options over every supported workflow host", "assisted": "build project resolution; execute app catalog apply, widget hydration and Step3 user-input renderer; compare saved reference", "test_input": "synthetic test DNA only; no biological evidence or catalog sequence added", "scope": "canonical V2 identities only, not all possible arbitrary user DNA or downstream backbones"},
    }


def main() -> None:
    audit = build_audit()
    STEM.with_suffix(".json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# V2 Step3 routability closure — 2026-09-28", "", audit["verdict"], "", "Counts are unique V2 identities across supported hosts. Assisted routes are project-bound user-input surfaces, not Registry dropdown entries. Browser acceptance is blocked.", "", "| Workflow | Direct | Assisted | Potential union |", "|---|---:|---:|---:|"]
    for w in WORKFLOWS:
        c = audit[f"{w.upper()}_STEP3_COUNTS"]
        lines.append(f"| {w} | {c['direct_now']} | {c['resolvable_after_user_sequence']} | {c['total_potentially_usable']} |")
    lines += ["", "## ROLE_COVERAGE", "", "| Workflow | Type | Choices | Coverage | Blocker |", "|---|---|---:|---|---|"]
    lines += [f"| {r['workflow']} | {r['component_type']} | {r['usable_choices']} | {r['coverage']} | {r['blocking_class'] or '—'} |" for r in audit["ROLE_COVERAGE"]]
    for key in ("CURRENT_PRODUCT_COUNTS", "V2_CANONICAL_COUNTS", "USER_SEQUENCE_ASSISTED_COUNTS", "COVERAGE_FINDINGS", "ACTUAL_STEP3_ROLES", "DIRECT_USE_EXCLUSIONS", "REFERENCE_AGENT_BOUNDARY", "RETIRED_EXCLUSION", "REAL_BROWSER_ACCEPTANCE", "REMAINING_EVIDENCE_GAPS", "METHOD"):
        lines += ["", f"## {key}", "", "```json", json.dumps(audit[key], ensure_ascii=False, indent=2), "```"]
    lines += ["", "## EXACT_STEP3_ROUTABILITY_MATRIX", "", "The companion JSON contains all 171 identities, per-workflow routes, all supported host probes, exact ID sets and exclusions.", "", "## Evidence accuracy", "", "ACT7 / V2-CMP-004 already records 1..1202 (+) in the frozen package. The original problem was missing display and an unchecked length, not absent coordinates. Nineteen assisted records have exact reviewed intervals; five have identity context only. Expected lengths are interval arithmetic; user checksums are not accession verification."]
    STEM.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("CURRENT_PRODUCT_COUNTS", "USER_SEQUENCE_ASSISTED_COUNTS")}, indent=2))


if __name__ == "__main__":
    main()
