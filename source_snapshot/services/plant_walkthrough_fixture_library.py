from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


FIXTURE_SCOPE_PLANT_REVIEW = "plant_expression_route_review_fixture"
FIXTURE_SCOPE_OUT_OF_SCOPE_GUARD = "out_of_scope_manual_review_guard_fixture"

FIXTURE_FIELDS: tuple[str, ...] = (
    "fixture_id",
    "fixture_name",
    "fixture_scope",
    "user_intent",
    "component_records",
    "expected_route_context",
    "expected_missing_fields",
    "expected_manual_review_focus",
    "expected_blocked_claims",
    "boundary_note",
)

BOUNDARY_NOTE = (
    "Documentation-only plant walkthrough review fixture. It records representative user intent, "
    "component-style source metadata, expected route context, expected gaps, and blocked output "
    "families for deterministic software workflow review; it is not a final construct design, "
    "component selection, sequence output, experiment procedure, outcome claim, or lab-use judgment."
)

EXPECTED_BLOCKED_CLAIMS: tuple[str, ...] = (
    "biological recommendation",
    "final component selection",
    "sequence generation",
    "pathway optimization",
    "feasibility scoring",
    "yield prediction",
    "experiment procedure generation",
    "wet-lab readiness judgment",
)


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return str(value or "").strip()


def _fixture(
    *,
    fixture_id: str,
    fixture_name: str,
    fixture_scope: str,
    user_intent: Mapping[str, Any],
    component_records: Sequence[Mapping[str, Any]],
    expected_route_context: Mapping[str, Any],
    expected_missing_fields: Sequence[str],
    expected_manual_review_focus: Sequence[str],
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "fixture_name": fixture_name,
        "fixture_scope": fixture_scope,
        "user_intent": _plain_value(user_intent),
        "component_records": _plain_value(component_records),
        "expected_route_context": _plain_value(expected_route_context),
        "expected_missing_fields": list(expected_missing_fields),
        "expected_manual_review_focus": list(expected_manual_review_focus),
        "expected_blocked_claims": list(EXPECTED_BLOCKED_CLAIMS),
        "boundary_note": BOUNDARY_NOTE,
    }


def rice_albumin_expression_review_fixture() -> dict[str, Any]:
    return _fixture(
        fixture_id="rice_albumin_expression_review",
        fixture_name="Rice albumin expression review fixture",
        fixture_scope=FIXTURE_SCOPE_PLANT_REVIEW,
        user_intent={
            "target_name": "rice albumin source record",
            "target_type": "plant protein documentation target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local route review record",
            "known_cds_source": "SRC-RICE-ALB-CDS",
            "known_component_ids": {
                "promoter": "SRC-RICE-SEED-PROMOTER",
                "terminator": "SRC-RICE-TERMINATOR",
            },
            "known_vector_or_backbone": "SRC-RICE-BACKBONE",
            "localization_context": "source note mentions seed storage protein context",
            "evidence_sources": {
                "SRC-RICE-ALB-CASE": "rice albumin case source pointer",
                "SRC-RICE-HOST": "rice host context source pointer",
            },
            "notes": "Representative plant-only route review input; source labels are metadata only.",
        },
        component_records=[
            {
                "component_id": "COMP-RICE-SEED-PROMOTER",
                "component_name": "Rice seed promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-RICE-SEED-PROMOTER",
                "source_label": "promoter source metadata",
                "review_status": "manual review pending",
            },
            {
                "component_id": "COMP-RICE-TERMINATOR",
                "component_name": "Rice terminator source record",
                "component_type": "terminator_slot",
                "slot_type": "terminator_slot",
                "plant_context": "rice expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-RICE-TERMINATOR",
                "source_label": "terminator source metadata",
                "review_status": "manual review pending",
            },
        ],
        expected_route_context={
            "route_id": "rice_seed_protein_expression",
            "scope_status": "plant_scope_review",
            "plant_context": "rice_expression_vector",
        },
        expected_missing_fields=("promoter_source_reference", "terminator_source_reference"),
        expected_manual_review_focus=(
            "promoter and terminator source reference review",
            "rice host/context source review",
            "package snapshot readback review",
        ),
    )


def artemisinin_precursor_plant_pathway_review_fixture() -> dict[str, Any]:
    return _fixture(
        fixture_id="artemisinin_precursor_plant_pathway_review",
        fixture_name="Artemisinin precursor plant pathway review fixture",
        fixture_scope=FIXTURE_SCOPE_PLANT_REVIEW,
        user_intent={
            "target_name": "artemisinin precursor pathway source record",
            "target_type": "plant pathway documentation target",
            "plant_host": "Artemisia annua plant context",
            "plant_context": "plant pathway documentation review context",
            "expression_purpose": "route planning record for plant documentation review",
            "known_cds_source": "SRC-ARTEMISIA-CDS-GROUP",
            "known_component_ids": {
                "promoter": "SRC-ARTEMISIA-PROMOTER",
                "coding_sequence": "SRC-ARTEMISIA-CDS-GROUP",
                "terminator": "SRC-ARTEMISIA-TERMINATOR",
            },
            "known_vector_or_backbone": "",
            "localization_context": "source notes mention plant pathway context only",
            "evidence_sources": {
                "SRC-ARTEMISIA-CASE": "plant pathway case source pointer",
                "SRC-ARTEMISIA-HOST": "Artemisia host context source pointer",
            },
            "notes": "Planning-oriented plant review input; it must remain a documentation record.",
        },
        component_records=[
            {
                "component_id": "COMP-ARTEMISIA-PROMOTER",
                "component_name": "Artemisia promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "Artemisia annua plant context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-ARTEMISIA-PROMOTER",
                "source_label": "promoter source metadata",
                "review_status": "manual review pending",
            },
            {
                "component_id": "COMP-ARTEMISIA-CDS",
                "component_name": "Artemisia CDS group source record",
                "component_type": "coding_sequence_slot",
                "slot_type": "coding_sequence_slot",
                "plant_context": "Artemisia annua plant context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-ARTEMISIA-CDS-GROUP",
                "source_label": "CDS group source metadata",
                "review_status": "manual review pending",
            },
        ],
        expected_route_context={
            "route_id": "plant_expression_vector",
            "scope_status": "plant_scope_review",
            "plant_context": "generic_plant_expression_vector",
        },
        expected_missing_fields=("backbone_label",),
        expected_manual_review_focus=(
            "plant pathway source context review",
            "backbone source gap review",
            "manual review of pathway terminology as documentation only",
        ),
    )


def n_benthamiana_expression_context_review_fixture() -> dict[str, Any]:
    return _fixture(
        fixture_id="n_benthamiana_expression_context_review",
        fixture_name="N. benthamiana expression context review fixture",
        fixture_scope=FIXTURE_SCOPE_PLANT_REVIEW,
        user_intent={
            "target_name": "N. benthamiana leaf expression source record",
            "target_type": "plant expression documentation target",
            "plant_host": "N. benthamiana",
            "plant_context": "leaf transient expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-NB-CDS",
            "known_component_ids": {
                "promoter": "SRC-NB-PROMOTER",
                "coding_sequence": "SRC-NB-CDS",
                "terminator": "SRC-NB-TERMINATOR",
            },
            "known_vector_or_backbone": "SRC-NB-BACKBONE",
            "localization_context": "source note mentions leaf expression context",
            "evidence_sources": {
                "SRC-NB-CASE": "N. benthamiana case source pointer",
                "SRC-NB-HOST": "host context source pointer",
            },
            "notes": "Representative plant expression context readback input.",
        },
        component_records=[
            {
                "component_id": "COMP-NB-PROMOTER",
                "component_name": "N. benthamiana promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "leaf transient expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-NB-PROMOTER",
                "source_label": "promoter source metadata",
                "review_status": "manual review pending",
            },
            {
                "component_id": "COMP-NB-CDS",
                "component_name": "N. benthamiana CDS source record",
                "component_type": "coding_sequence_slot",
                "slot_type": "coding_sequence_slot",
                "plant_context": "leaf transient expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-NB-CDS",
                "source_label": "CDS source metadata",
                "review_status": "manual review pending",
            },
            {
                "component_id": "COMP-NB-TERMINATOR",
                "component_name": "N. benthamiana terminator source record",
                "component_type": "terminator_slot",
                "slot_type": "terminator_slot",
                "plant_context": "leaf transient expression documentation context",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-NB-TERMINATOR",
                "source_label": "terminator source metadata",
                "review_status": "manual review pending",
            },
        ],
        expected_route_context={
            "route_id": "plant_transient_expression_review",
            "scope_status": "plant_scope_review",
            "plant_context": "n_benthamiana_expression_vector",
        },
        expected_missing_fields=(),
        expected_manual_review_focus=(
            "host/context source review",
            "cassette slot provenance review",
            "manual review of source labels",
        ),
    )


def generic_plant_expression_missing_fields_fixture() -> dict[str, Any]:
    return _fixture(
        fixture_id="generic_plant_expression_missing_fields",
        fixture_name="Generic plant expression missing fields fixture",
        fixture_scope=FIXTURE_SCOPE_PLANT_REVIEW,
        user_intent={
            "target_name": "partial plant route source record",
            "target_type": "plant expression documentation target",
            "plant_host": "unlisted plant host",
            "plant_context": "plant expression vector documentation",
            "expression_purpose": "manual route draft review",
            "known_cds_source": "",
            "known_component_ids": {"promoter": "SRC-GENERIC-PROMOTER"},
            "known_vector_or_backbone": "",
            "localization_context": "",
            "evidence_sources": ["SRC-GENERIC-CASE"],
            "notes": "Intentional gap fixture for manual review queue coverage.",
        },
        component_records=[
            {
                "component_id": "COMP-GENERIC-PROMOTER",
                "component_name": "Generic plant promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "plant expression vector documentation",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-GENERIC-PROMOTER",
                "source_label": "promoter source metadata",
                "review_status": "manual review pending",
            }
        ],
        expected_route_context={
            "route_id": "plant_expression_vector",
            "scope_status": "plant_scope_review",
            "plant_context": "generic_plant_expression_vector",
        },
        expected_missing_fields=(
            "cds_label",
            "coding_sequence_slot",
            "terminator_slot",
            "backbone_label",
        ),
        expected_manual_review_focus=(
            "missing CDS source review",
            "missing cassette slot source review",
            "missing backbone source review",
        ),
    )


def non_plant_out_of_scope_guard_fixture() -> dict[str, Any]:
    return _fixture(
        fixture_id="non_plant_out_of_scope_guard",
        fixture_name="Non-plant out-of-scope guard fixture",
        fixture_scope=FIXTURE_SCOPE_OUT_OF_SCOPE_GUARD,
        user_intent={
            "target_name": "bacterial host source record",
            "target_type": "non-plant expression documentation target",
            "plant_host": "E. coli bacterial host",
            "plant_context": "microbial fermentation context",
            "expression_purpose": "scope guard review",
            "known_cds_source": "SRC-NONPLANT-CDS",
            "known_component_ids": {"promoter": "SRC-NONPLANT-PROMOTER"},
            "known_vector_or_backbone": "SRC-NONPLANT-BACKBONE",
            "localization_context": "",
            "evidence_sources": ["SRC-NONPLANT-CASE"],
            "notes": "Out-of-scope guard input for plant-only workflow boundary review.",
        },
        component_records=[
            {
                "component_id": "COMP-NONPLANT-PROMOTER",
                "component_name": "Bacterial promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "host_context": "E. coli bacterial host",
                "evidence_status": "source pointer recorded",
                "source_id": "SRC-NONPLANT-PROMOTER",
                "source_label": "non-plant source metadata",
                "review_status": "manual review pending",
            }
        ],
        expected_route_context={
            "route_id": "unsupported_non_plant_expression_context",
            "scope_status": "mixed_scope_manual_review",
            "plant_context": "",
        },
        expected_missing_fields=(
            "plant_context",
            "documentation_goal",
            "plant_species",
            "coding_sequence_slot",
            "terminator_slot",
            "source_reference",
        ),
        expected_manual_review_focus=(
            "plant-only scope guard review",
            "out-of-scope component record review",
            "manual review before any plant route reuse",
        ),
    )


_FIXTURE_BUILDERS = (
    rice_albumin_expression_review_fixture,
    artemisinin_precursor_plant_pathway_review_fixture,
    n_benthamiana_expression_context_review_fixture,
    generic_plant_expression_missing_fields_fixture,
    non_plant_out_of_scope_guard_fixture,
)


def get_all_plant_walkthrough_review_fixtures() -> list[dict[str, Any]]:
    return [builder() for builder in _FIXTURE_BUILDERS]


def get_plant_walkthrough_review_fixture_by_id(fixture_id: str) -> dict[str, Any] | None:
    fixture_id_text = str(fixture_id or "").strip()
    if not fixture_id_text:
        return None
    for fixture in get_all_plant_walkthrough_review_fixtures():
        if fixture["fixture_id"] == fixture_id_text:
            return fixture
    return None


def get_plant_walkthrough_fixture_library_summary() -> dict[str, Any]:
    fixtures = get_all_plant_walkthrough_review_fixtures()
    return {
        "total_fixtures": len(fixtures),
        "fixture_ids": [fixture["fixture_id"] for fixture in fixtures],
        "fixture_scopes": sorted({fixture["fixture_scope"] for fixture in fixtures}),
        "boundary_note": BOUNDARY_NOTE,
    }
