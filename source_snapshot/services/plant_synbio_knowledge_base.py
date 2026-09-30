from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "plant_synbio_knowledge"
GOAL_TYPE_FILE = "goal_type_templates_v1.jsonl"
ROUTE_TEMPLATE_FILE = "route_templates_v1.jsonl"
COMPONENT_SLOT_FILE = "component_slot_templates_v1.jsonl"
EVIDENCE_SOURCE_FILE = "evidence_sources_v1.jsonl"

DOCUMENTATION_BOUNDARY = (
    "Plant synbio intake is documentation-only. It organizes evidence gaps for manual review "
    "and does not validate biology, predict yield, optimize a pathway, or judge wet-lab readiness."
)
ROUTE_BLOCKED_STATUS = "route_generation_blocked"
ROUTE_ALLOWED_STATUS = "candidate_route_template_available_for_review"

SUGARCANE_TERMS = (
    "sugarcane",
    "saccharum",
    "\u7518\u8517",
)
HEALTHY_SUGAR_TERMS = (
    "healthy sugar",
    "\u5065\u5eb7\u7cd6",
    "rare sugar",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path.name} at line {line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object in {path.name} at line {line_number}")
            rows.append(value)
    return rows


def load_plant_synbio_knowledge_base(
    knowledge_dir: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load plant synbio JSONL templates from disk."""
    base_dir = Path(knowledge_dir) if knowledge_dir is not None else KNOWLEDGE_DIR
    return {
        "goal_type_templates": _read_jsonl(base_dir / GOAL_TYPE_FILE),
        "route_templates": _read_jsonl(base_dir / ROUTE_TEMPLATE_FILE),
        "component_slot_templates": _read_jsonl(base_dir / COMPONENT_SLOT_FILE),
        "evidence_sources": _read_jsonl(base_dir / EVIDENCE_SOURCE_FILE),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_text(value: Any) -> str:
    return _text(value).casefold()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    normalized = text.casefold()
    return any(term.casefold() in normalized for term in terms)


def _goal_score(goal_text: str, template: Mapping[str, Any]) -> int:
    score = 0
    for keyword in _as_list(template.get("keywords")):
        if keyword.casefold() in goal_text:
            score += 2
    if _contains_any(goal_text, SUGARCANE_TERMS) and template.get("goal_type_id") == (
        "plant_metabolic_engineering_sugar_metabolism"
    ):
        score += 3
    if _contains_any(goal_text, HEALTHY_SUGAR_TERMS) and template.get("goal_type_id") == (
        "plant_metabolic_engineering_sugar_metabolism"
    ):
        score += 3
    return score


def match_plant_goal_type(
    plant_goal: str,
    knowledge_base: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Return the best plant goal type match and transparent match signals."""
    kb = dict(knowledge_base or load_plant_synbio_knowledge_base())
    goal_text = _normalized_text(plant_goal)
    candidates = []
    for template in kb.get("goal_type_templates", []):
        score = _goal_score(goal_text, template)
        if score <= 0:
            continue
        candidates.append(
            {
                "goal_type_id": template.get("goal_type_id", ""),
                "label": template.get("label", ""),
                "score": score,
                "template": template,
            }
        )
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["goal_type_id"])))
    if not candidates:
        return {
            "matched": False,
            "goal_type_id": "",
            "label": "No plant goal type matched",
            "score": 0,
            "template": {},
            "match_signals": [],
        }
    selected = candidates[0]
    return {
        "matched": True,
        "goal_type_id": selected["goal_type_id"],
        "label": selected["label"],
        "score": selected["score"],
        "template": selected["template"],
        "match_signals": _match_signals(goal_text),
    }


def _match_signals(goal_text: str) -> list[str]:
    signals: list[str] = []
    if _contains_any(goal_text, SUGARCANE_TERMS):
        signals.append("sugarcane / Saccharum context detected")
    if _contains_any(goal_text, HEALTHY_SUGAR_TERMS):
        signals.append("healthy sugar / rare sugar intent needs exact target definition")
    if "sugar" in goal_text or "\u7cd6" in goal_text:
        signals.append("sugar metabolism wording detected")
    return signals


def _recorded_input_values(user_context: Mapping[str, Any] | None) -> dict[str, str]:
    if not user_context:
        return {}
    return {str(key): _text(value) for key, value in user_context.items() if _text(value)}


def _matched_route_templates(
    goal_type_id: str,
    knowledge_base: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        dict(template)
        for template in knowledge_base.get("route_templates", [])
        if template.get("goal_type_id") == goal_type_id
    ]


def _required_inputs(goal_template: Mapping[str, Any], route_templates: Sequence[Mapping[str, Any]]) -> list[str]:
    required: list[str] = []
    for value in _as_list(goal_template.get("required_inputs")):
        if value not in required:
            required.append(value)
    for route in route_templates:
        for value in _as_list(route.get("required_inputs")):
            if value not in required:
                required.append(value)
    return required


def _evidence_needed(goal_template: Mapping[str, Any], route_templates: Sequence[Mapping[str, Any]]) -> list[str]:
    needed: list[str] = []
    for value in _as_list(goal_template.get("evidence_needed")):
        if value not in needed:
            needed.append(value)
    for route in route_templates:
        for value in _as_list(route.get("evidence_needed")):
            if value not in needed:
                needed.append(value)
    return needed


def _evidence_discovery_plan(goal_type_id: str, evidence_needed: Sequence[str]) -> list[dict[str, str]]:
    return [
        {
            "task_id": f"{goal_type_id}-gap-{index:02d}",
            "task": task,
            "status": "manual_review_required",
        }
        for index, task in enumerate(evidence_needed, start=1)
    ]


def build_plant_goal_evidence_intake(
    plant_goal: str,
    user_context: Mapping[str, Any] | None = None,
    *,
    knowledge_base: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Match a plant goal to templates and expose evidence gaps before any route work."""
    kb = dict(knowledge_base or load_plant_synbio_knowledge_base())
    match = match_plant_goal_type(plant_goal, kb)
    route_templates = _matched_route_templates(match["goal_type_id"], kb) if match["matched"] else []
    required_inputs = _required_inputs(match.get("template", {}), route_templates)
    recorded_inputs = _recorded_input_values(user_context)
    missing_information = [key for key in required_inputs if not recorded_inputs.get(key)]
    evidence_needed = _evidence_needed(match.get("template", {}), route_templates)
    can_generate_candidate_route = bool(match["matched"] and not missing_information)
    route_generation_status = ROUTE_ALLOWED_STATUS if can_generate_candidate_route else ROUTE_BLOCKED_STATUS

    return {
        "plant_goal": _text(plant_goal),
        "matched_goal_type": {
            "matched": match["matched"],
            "goal_type_id": match["goal_type_id"],
            "label": match["label"],
            "score": match["score"],
            "match_signals": match["match_signals"],
        },
        "matched_route_templates": route_templates,
        "required_inputs": required_inputs,
        "recorded_inputs": recorded_inputs,
        "evidence_needed": evidence_needed,
        "missing_information": missing_information,
        "can_generate_candidate_route": can_generate_candidate_route,
        "route_generation_status": route_generation_status,
        "evidence_discovery_plan": []
        if can_generate_candidate_route
        else _evidence_discovery_plan(match["goal_type_id"] or "unmatched-plant-goal", evidence_needed),
        "evidence_sources": list(kb.get("evidence_sources", [])),
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
    }
