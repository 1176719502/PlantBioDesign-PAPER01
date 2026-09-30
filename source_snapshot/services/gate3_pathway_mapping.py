"""Manual pathway-step to transcription-unit mapping for the formal plant workflow.

This service stores documentation state and verifies the relationship between a
user-entered pathway step, its CDS, and an existing multi-TU unit.  It never
constructs canonical DNA or makes biological recommendations.
"""
from __future__ import annotations

import copy
from hashlib import sha256
from typing import Any
from uuid import uuid4

from services.mvp_cds_input import analyze_cds_input


SCENARIO_STANDARD = "standard_plant_expression_vector"
SCENARIO_PATHWAY_MULTI_TU = "metabolic_pathway_multi_tu_vector"
VALID_SCENARIOS = frozenset({SCENARIO_STANDARD, SCENARIO_PATHWAY_MULTI_TU})

CDS_SOURCE_TYPES = (
    "public_database",
    "upload_file",
    "user_provided",
    "test_only_asset",
)

_STEP_TEXT_FIELDS = (
    "step_name",
    "substrate_name",
    "product_name",
    "enzyme_name",
    "enzyme_gene_name",
    "ec_number",
    "enzyme_source_organism",
    "notes",
    "cds_source_type",
    "cds_source_reference",
    "mapped_unit_id",
    "mapping_status",
    "manual_review_notes",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(sequence: str) -> str:
    return sha256(sequence.upper().encode("ascii")).hexdigest()


def normalize_design_scenario(value: Any) -> str:
    """Map absent legacy state deterministically to the standard scenario."""
    scenario = _text(value)
    return scenario if scenario in VALID_SCENARIOS else SCENARIO_STANDARD


def analyze_pathway_cds(
    raw_text: Any,
    *,
    source_type: Any = "user_provided",
    source_reference: Any = "",
) -> dict[str, Any]:
    """Reuse the existing strict CDS analyzer for pathway CDS input."""
    resolved_type = _text(source_type) or "user_provided"
    if resolved_type not in CDS_SOURCE_TYPES:
        resolved_type = "user_provided"
    analysis = analyze_cds_input(
        str(raw_text or ""),
        source_kind=resolved_type,
        source_name=_text(source_reference),
    )
    sequence = _text(analysis.get("normalized_cds")).upper()
    return {
        "cds_sequence": sequence,
        "cds_source_type": resolved_type,
        "cds_source_reference": _text(source_reference),
        "cds_sequence_sha256": _sha256(sequence),
        "cds_analysis": copy.deepcopy(analysis),
    }


def new_pathway_step(*, step_id: str | None = None) -> dict[str, Any]:
    """Create one stable, blank manual pathway step."""
    return {
        "step_id": _text(step_id) or f"pathway-step-{uuid4().hex}",
        "display_order": 0,
        "step_name": "",
        "substrate_name": "",
        "product_name": "",
        "enzyme_name": "",
        "enzyme_gene_name": "",
        "ec_number": "",
        "enzyme_source_organism": "",
        "notes": "",
        "cds_sequence": "",
        "cds_source_type": "user_provided",
        "cds_source_reference": "",
        "cds_sequence_sha256": _sha256(""),
        "cds_analysis": {},
        "mapped_unit_id": "",
        "mapping_status": "not_mapped",
        "manual_review_notes": "",
        "applied_to_unit": False,
    }


def normalize_pathway_steps(value: Any) -> list[dict[str, Any]]:
    """Normalize ordered persisted steps without regenerating existing identities."""
    source = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(source, start=1):
        if not isinstance(raw, dict):
            continue
        item = new_pathway_step(step_id=_text(raw.get("step_id")))
        for field in _STEP_TEXT_FIELDS:
            item[field] = _text(raw.get(field))
        raw_mapping = raw.get("mapped_unit_id")
        if isinstance(raw_mapping, (list, tuple, set)):
            # Retain malformed persisted data long enough for validation to
            # report the forbidden one-step-to-many-TU relationship.
            item["mapped_unit_id"] = list(raw_mapping)
        item["display_order"] = index
        item["applied_to_unit"] = bool(raw.get("applied_to_unit"))
        raw_sequence = raw.get("cds_sequence")
        if raw_sequence is None and isinstance(raw.get("cds_analysis"), dict):
            raw_sequence = raw["cds_analysis"].get("normalized_cds")
        pathway_cds = analyze_pathway_cds(
            raw_sequence or "",
            source_type=item["cds_source_type"],
            source_reference=item["cds_source_reference"],
        )
        item.update(pathway_cds)
        if item["applied_to_unit"] and not item["mapped_unit_id"]:
            item["applied_to_unit"] = False
        normalized.append(item)
    return normalized


def add_pathway_step(steps: Any) -> list[dict[str, Any]]:
    return [*normalize_pathway_steps(steps), new_pathway_step()]


def move_pathway_step(steps: Any, step_id: str, offset: int) -> list[dict[str, Any]]:
    updated = normalize_pathway_steps(steps)
    current = next((index for index, item in enumerate(updated) if item["step_id"] == str(step_id)), -1)
    target = current + int(offset)
    if current >= 0 and 0 <= target < len(updated):
        updated[current], updated[target] = updated[target], updated[current]
    return normalize_pathway_steps(updated)


def delete_pathway_step(steps: Any, step_id: str) -> list[dict[str, Any]]:
    updated = normalize_pathway_steps(steps)
    if len(updated) <= 1:
        raise ValueError("At least one pathway step must remain.")
    remaining = [item for item in updated if item["step_id"] != str(step_id)]
    if len(remaining) == len(updated):
        raise ValueError("The requested pathway step does not exist.")
    return normalize_pathway_steps(remaining)


def update_pathway_step(steps: Any, step_id: str, **changes: Any) -> list[dict[str, Any]]:
    """Apply manual edits and clear application confirmation after CDS changes."""
    updated = normalize_pathway_steps(steps)
    found = False
    for item in updated:
        if item["step_id"] != str(step_id):
            continue
        found = True
        previous_sequence = item["cds_sequence"]
        previous_mapped_unit_id = item["mapped_unit_id"]
        for field in _STEP_TEXT_FIELDS:
            if field in changes:
                item[field] = _text(changes[field])
        if "cds_sequence" in changes or "cds_source_type" in changes or "cds_source_reference" in changes:
            item.update(
                analyze_pathway_cds(
                    changes.get("cds_sequence", item["cds_sequence"]),
                    source_type=item["cds_source_type"],
                    source_reference=item["cds_source_reference"],
                )
            )
        if (
            item["cds_sequence"] != previous_sequence
            or item["mapped_unit_id"] != previous_mapped_unit_id
        ):
            item["applied_to_unit"] = False
            item["mapping_status"] = "mapped_pending_application" if item["mapped_unit_id"] else "not_mapped"
        break
    if not found:
        raise ValueError("The requested pathway step does not exist.")
    return normalize_pathway_steps(updated)


def _tu_cds_sequence(unit: dict[str, Any]) -> str:
    cds = unit.get("cds") if isinstance(unit.get("cds"), dict) else {}
    analysis = cds.get("cds_analysis") if isinstance(cds.get("cds_analysis"), dict) else {}
    return _text(analysis.get("normalized_cds") or cds.get("raw_text") or cds.get("sequence")).upper()


def _blocking(step_id: str, rule_id: str, message: str) -> dict[str, str]:
    return {"step_id": step_id, "rule_id": rule_id, "message": message}


def validate_pathway_mapping(steps: Any, transcription_units: Any) -> dict[str, Any]:
    """Report structural blockers and manual-review prompts for the manual mapping."""
    normalized = normalize_pathway_steps(steps)
    units = [dict(item) for item in transcription_units if isinstance(item, dict)] if isinstance(transcription_units, list) else []
    unit_by_id = {_text(item.get("unit_id")): item for item in units if _text(item.get("unit_id"))}
    blocking: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    ids = [item["step_id"] for item in normalized]
    duplicate_ids = {step_id for step_id in ids if ids.count(step_id) > 1}
    mapped_steps: dict[str, list[dict[str, Any]]] = {}
    cds_steps: dict[str, list[dict[str, Any]]] = {}

    for item in normalized:
        step_id = item["step_id"]
        if not step_id or step_id in duplicate_ids:
            blocking.append(_blocking(step_id, "duplicate_step_id", "Pathway step identity must be unique."))
        if not item["step_name"]:
            blocking.append(_blocking(step_id, "missing_step_name", "Pathway step name is required."))
        if not item["enzyme_name"]:
            blocking.append(_blocking(step_id, "missing_enzyme_name", "Enzyme name is required."))
        analysis = item["cds_analysis"]
        if not item["cds_sequence"]:
            blocking.append(_blocking(step_id, "missing_cds", "CDS sequence is required."))
        elif bool(analysis.get("blocking")):
            blocking.append(_blocking(step_id, "invalid_cds", "CDS sequence has blocking input findings."))
        mapped = item["mapped_unit_id"]
        if isinstance(mapped, (list, tuple, set)):
            blocking.append(_blocking(step_id, "multiple_mapped_units", "One pathway step can map to only one transcription unit."))
            mapped = ""
        if not mapped:
            blocking.append(_blocking(step_id, "missing_mapped_unit", "A transcription unit must be selected."))
        elif mapped not in unit_by_id:
            blocking.append(_blocking(step_id, "dangling_mapped_unit", "The selected transcription unit no longer exists."))
        else:
            mapped_steps.setdefault(mapped, []).append(item)
            tu_sequence = _tu_cds_sequence(unit_by_id[mapped])
            if item["applied_to_unit"] and _sha256(tu_sequence) != item["cds_sequence_sha256"]:
                blocking.append(_blocking(step_id, "applied_cds_hash_mismatch", "Applied pathway CDS does not match the selected transcription-unit CDS."))
        if not item["substrate_name"] or not item["product_name"]:
            review.append(_blocking(step_id, "missing_substrate_or_product", "Substrate or product is not recorded."))
        if not item["ec_number"]:
            review.append(_blocking(step_id, "missing_ec_number", "EC number is not recorded."))
        if not item["enzyme_source_organism"]:
            review.append(_blocking(step_id, "missing_enzyme_source_organism", "Enzyme source organism is not recorded."))
        if not item["cds_source_type"] or not item["cds_source_reference"]:
            review.append(_blocking(step_id, "incomplete_cds_source", "CDS source description is incomplete."))
        if item["cds_sequence_sha256"]:
            cds_steps.setdefault(item["cds_sequence_sha256"], []).append(item)

    for unit_id, items in mapped_steps.items():
        if len(items) > 1:
            for item in items:
                shared = _blocking(
                    item["step_id"],
                    "shared_transcription_unit",
                    "This transcription unit is mapped by more than one pathway step.",
                )
                # Gate 3 records a one-to-one pathway-step/TU mapping.  Keep
                # the review row visible, but fail closed because applying a
                # second step would overwrite the first step's TU CDS.
                blocking.append(shared)
                review.append(shared)
    for items in cds_steps.values():
        if len(items) > 1:
            for item in items:
                review.append(_blocking(item["step_id"], "reused_cds", "This CDS sequence is reused by more than one pathway step."))

    blocking_ids = {item["step_id"] for item in blocking}
    result_steps: list[dict[str, Any]] = []
    for item in normalized:
        updated = dict(item)
        if updated["step_id"] in blocking_ids:
            updated["mapping_status"] = "blocked"
        elif updated["applied_to_unit"]:
            updated["mapping_status"] = "applied"
        else:
            updated["mapping_status"] = "mapped_pending_application"
        result_steps.append(updated)
    return {
        "pathway_steps": result_steps,
        "blocking_items": blocking,
        "manual_review_items": review,
        "mapping_complete": bool(result_steps) and not blocking,
    }


def apply_step_cds_to_unit(
    steps: Any,
    transcription_units: Any,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Write one validated manual CDS into the selected TU, preserving other roles."""
    validated = validate_pathway_mapping(steps, transcription_units)
    selected = next((item for item in validated["pathway_steps"] if item["step_id"] == str(step_id)), None)
    if selected is None:
        raise ValueError("The requested pathway step does not exist.")
    relevant = [item for item in validated["blocking_items"] if item["step_id"] == str(step_id)]
    if relevant:
        raise ValueError("The pathway step has blocking mapping items.")
    units = [copy.deepcopy(item) for item in transcription_units if isinstance(item, dict)] if isinstance(transcription_units, list) else []
    target = next((item for item in units if _text(item.get("unit_id")) == selected["mapped_unit_id"]), None)
    if target is None:
        raise ValueError("The selected transcription unit does not exist.")
    target["cds"] = {
        "display_name": selected["enzyme_gene_name"] or selected["step_name"],
        "raw_text": selected["cds_sequence"],
        "source_type": selected["cds_source_type"],
        "source_name": selected["cds_source_reference"],
        "source_format": str(selected["cds_analysis"].get("source_format") or "plain"),
        "cds_analysis": copy.deepcopy(selected["cds_analysis"]),
    }
    updated_steps = normalize_pathway_steps(validated["pathway_steps"])
    for item in updated_steps:
        if item["step_id"] == selected["step_id"]:
            item["applied_to_unit"] = True
            item["mapping_status"] = "applied"
    return normalize_pathway_steps(updated_steps), units


def build_pathway_traceability_rows(steps: Any, transcription_units: Any) -> list[dict[str, Any]]:
    """Return public result-page rows without stable internal identities or hashes."""
    validation = validate_pathway_mapping(steps, transcription_units)
    units = {
        _text(unit.get("unit_id")): unit
        for unit in transcription_units
        if isinstance(unit, dict) and _text(unit.get("unit_id"))
    } if isinstance(transcription_units, list) else {}
    review_by_step: dict[str, list[str]] = {}
    for item in validation["manual_review_items"]:
        review_by_step.setdefault(item["step_id"], []).append(item["message"])
    blocking_by_step: dict[str, list[str]] = {}
    for item in validation["blocking_items"]:
        blocking_by_step.setdefault(item["step_id"], []).append(item["message"])
    rows: list[dict[str, Any]] = []
    for step in validation["pathway_steps"]:
        unit = units.get(step["mapped_unit_id"], {})
        rows.append(
            {
                "step_order": step["display_order"],
                "step_name": step["step_name"] or "--",
                "conversion": f"{step['substrate_name'] or '--'} -> {step['product_name'] or '--'}",
                "enzyme_name": step["enzyme_name"] or "--",
                "cds_length": len(step["cds_sequence"]),
                "transcription_unit": str(unit.get("display_name") or "--") if unit else "--",
                "transcription_unit_order": int(unit.get("order") or 0) if unit else 0,
                "orientation": "reverse" if str(unit.get("orientation")) == "reverse" else "forward",
                "mapping_status": step["mapping_status"],
                "manual_review": review_by_step.get(step["step_id"], []) + blocking_by_step.get(step["step_id"], []),
            }
        )
    return rows


def test_only_three_step_fixture() -> list[dict[str, Any]]:
    """TEST_ONLY fixture for focused tests; it carries no accession or validation claim."""
    records = (
        ("Step 1", "Substrate 1", "Product 1", "Enzyme 1", "ATGGCTGCTTAA", "TU1"),
        ("Step 2", "Substrate 2", "Product 2", "Enzyme 2", "ATGAAGAAATAA", "TU2"),
        ("Step 3", "Substrate 3", "Product 3", "Enzyme 3", "ATGTTCTTCTAA", "TU3"),
    )
    steps: list[dict[str, Any]] = []
    for step_name, substrate, product, enzyme, sequence, unit_id in records:
        step = new_pathway_step()
        step.update(
            {
                "step_name": step_name,
                "substrate_name": substrate,
                "product_name": product,
                "enzyme_name": enzyme,
                "enzyme_source_organism": "TEST_ONLY",
                "ec_number": "TEST_ONLY",
                "cds_source_type": "test_only_asset",
                "cds_source_reference": "TEST_ONLY local fixture; no accession; no validation claim",
                "mapped_unit_id": unit_id,
            }
        )
        step.update(analyze_pathway_cds(sequence, source_type="test_only_asset", source_reference=step["cds_source_reference"]))
        steps.append(step)
    return normalize_pathway_steps(steps)


test_only_three_step_fixture.__test__ = False
