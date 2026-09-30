from __future__ import annotations

from typing import Any


ARTEMISININ_PRECURSOR_GENES = ["ADS", "CYP71AV1", "CPR", "ADH1", "DBR2", "ALDH1"]
BOUNDARY_NOTE = (
    "Documentation-only construct design draft for review and traceability; "
    "not biological advice, not a claim that expression will occur, "
    "not an experimental validation, and not a downstream use judgment."
)
PATHWAY_BOUNDARY_NOTE = (
    "Documentation-only pathway construct design draft for review and traceability; "
    "not a production, yield, wet-lab, optimization, or experimental validation claim."
)
UNRESOLVED_BOUNDARY_NOTE = (
    "Documentation-only target clarification draft; the target is not construct-ready until "
    "a route, source context, and review notes are selected by the user."
)

COMMON_REQUIRED_PARTS = [
    "host context documentation row",
    "promoter documentation row",
    "CDS documentation row",
    "terminator documentation row",
    "vector backbone documentation row",
]

FORBIDDEN_ROUTE_CUES = [
    "protocol",
    "execute",
    "execution",
    "yield",
    "purity",
    "therapeutic",
    "clinical",
    "regulatory",
    "approval",
    "guarantee",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower_text(*values: Any) -> str:
    return " ".join(_text(value).lower() for value in values if _text(value))


def _clean_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    return [_text(value) for value in values if _text(value)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def _has_any(text: str, cues: list[str] | tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def _is_hsa_target(target_name: str) -> bool:
    normalized = target_name.casefold()
    return normalized in {"hsa", "human serum albumin", "albumin"} or "human serum albumin" in normalized


def _is_artemisinin_precursor_target(target_name: str) -> bool:
    normalized = target_name.casefold()
    return any(cue in normalized for cue in ["artemisinin precursor", "artemisinic acid", "dhaa"])


def _is_sugarcane_healthy_sugar_target(target_name: str, target_type: str, combined: str) -> bool:
    return (
        "sugarcane" in combined
        and "healthy sugar" in combined
    ) or target_type.casefold() in {"trait", "phenotype"}


def _is_generic_single_gene_target(target_name: str, target_type: str, route_hint: str, gene_list: list[str]) -> bool:
    combined = _lower_text(target_name, target_type, route_hint)
    if target_name.casefold() in {"goi", "generic goi"}:
        return True
    if target_type.casefold() in {"gene", "single gene"}:
        return True
    if "single gene" in combined or "goi" in combined:
        return True
    return len(gene_list) == 1 and not _has_any(combined, ["pathway", "trait", "phenotype", "product"])


def _normalized_target(target_name: str, aliases: list[str] | None = None, notes: str = "") -> dict[str, Any]:
    return {
        "label": target_name or "Unresolved target",
        "aliases": aliases or [],
        "notes": notes,
    }


def _construct_template(template_id: str, template_label: str, description: str, structure: list[str]) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "template_label": template_label,
        "description": description,
        "structure": structure,
    }


def _gene_slot(label: str, *, source_hint: str = "") -> dict[str, str]:
    return {
        "gene_label": label,
        "slot_role": "CDS",
        "source_requirement": source_hint or f"{label} CDS source/provenance required",
        "review_status": "source review needed",
    }


def _cassette_slot(label: str, gene_label: str, *, include_signal_peptide: bool = False) -> dict[str, Any]:
    parts = [
        {"part_role": "promoter", "part_label": "user-defined promoter", "source_status": "source review needed"},
    ]
    if include_signal_peptide:
        parts.append(
            {
                "part_role": "signal peptide",
                "part_label": "optional signal peptide context",
                "source_status": "source review needed",
            }
        )
    parts.extend(
        [
            {"part_role": "CDS", "part_label": gene_label, "source_status": "source review needed"},
            {"part_role": "terminator", "part_label": "user-defined terminator", "source_status": "source review needed"},
        ]
    )
    return {
        "cassette_label": label,
        "cassette_role": "documentation-only expression cassette draft",
        "gene_label": gene_label,
        "parts": parts,
    }


def _base_missing_fields(
    *,
    target_name: str,
    host_category: str,
    specific_host: str,
    gene_label: str | None = None,
    include_specific_host: bool = True,
) -> list[str]:
    missing: list[str] = []
    if not target_name:
        missing.append("target_name")
    if not host_category:
        missing.append("host_category")
    if include_specific_host and not specific_host:
        missing.append("specific_host")
    if gene_label is not None and not gene_label:
        missing.append("gene_or_CDS_identity")
    missing.extend(
        [
            "promoter_label",
            "promoter_source",
            "CDS_source",
            "terminator_label",
            "terminator_source",
            "vector_backbone",
            "source_or_reference_confirmation",
        ]
    )
    return _dedupe(missing)


def _base_source_requirements(target_label: str, source_hint: str) -> list[str]:
    requirements = [
        f"{target_label} target identity source/provenance",
        "host context source/provenance",
        "promoter source/provenance",
        "CDS source/provenance",
        "terminator source/provenance",
        "vector backbone source/provenance",
    ]
    if source_hint:
        requirements.append(f"user source hint to review: {source_hint}")
    return requirements


def _status_for_single_or_protein(host_category: str, source_hint: str, specific_host: str) -> str:
    return "supported" if host_category and specific_host and source_hint else "needs_review"


def _single_gene_output(
    *,
    target_name: str,
    host_category: str,
    specific_host: str,
    expression_purpose: str,
    gene_list: list[str],
    source_hint: str,
    user_notes: str,
) -> dict[str, Any]:
    gene_label = gene_list[0] if gene_list else (target_name or "GOI")
    return {
        "normalized_target": _normalized_target(target_name or gene_label, notes=user_notes),
        "target_class": "single_gene",
        "design_route": "single_goi_expression",
        "construct_template": _construct_template(
            "single_goi_expression",
            "Single GOI expression construct draft",
            "Promoter + CDS + terminator documentation skeleton.",
            ["promoter", "CDS", "terminator"],
        ),
        "gene_slots": [_gene_slot(gene_label, source_hint=source_hint)],
        "cassette_slots": [_cassette_slot("single GOI cassette draft", gene_label)],
        "required_parts": COMMON_REQUIRED_PARTS[:],
        "missing_fields": _base_missing_fields(
            target_name=target_name,
            host_category=host_category,
            specific_host=specific_host,
            gene_label=gene_label,
        ),
        "source_requirements": _base_source_requirements(gene_label, source_hint),
        "review_notes": _dedupe(
            [
                "Review host context as documentation context only.",
                "Confirm promoter, CDS, terminator, vector backbone, and source records before treating the draft as complete documentation.",
                expression_purpose and f"User purpose note preserved for review: {expression_purpose}",
            ]
        ),
        "support_status": _status_for_single_or_protein(host_category, source_hint, specific_host),
        "boundary_note": BOUNDARY_NOTE,
    }


def _hsa_output(
    *,
    target_name: str,
    host_category: str,
    specific_host: str,
    expression_purpose: str,
    route_hint: str,
    source_hint: str,
    user_notes: str,
) -> dict[str, Any]:
    combined = _lower_text(target_name, expression_purpose, route_hint, user_notes)
    include_signal_peptide = _has_any(combined, ["secret", "signal peptide"])
    route = "secreted_protein_expression" if include_signal_peptide else "protein_expression"
    structure = ["promoter", "optional signal peptide", "HSA CDS", "terminator"]
    return {
        "normalized_target": _normalized_target("HSA", aliases=["human serum albumin", "albumin"], notes=user_notes),
        "target_class": "protein_expression",
        "design_route": route,
        "construct_template": _construct_template(
            route,
            "HSA protein expression construct draft",
            "Promoter + optional/needs-review signal peptide + HSA CDS + terminator documentation skeleton.",
            structure,
        ),
        "gene_slots": [_gene_slot("HSA", source_hint=source_hint)],
        "cassette_slots": [_cassette_slot("HSA cassette draft", "HSA", include_signal_peptide=include_signal_peptide)],
        "required_parts": COMMON_REQUIRED_PARTS[:],
        "missing_fields": _dedupe(
            _base_missing_fields(
                target_name=target_name,
                host_category=host_category,
                specific_host=specific_host,
                gene_label="HSA",
            )
            + (["signal_peptide_source"] if include_signal_peptide else [])
        ),
        "source_requirements": _base_source_requirements("HSA", source_hint)
        + ["HSA CDS source/provenance", "part source/provenance for every cassette slot"],
        "review_notes": _dedupe(
            [
                "Confirm the HSA CDS source and all part source records.",
                "Confirm whether the signal peptide slot is only a route hint or a user-confirmed documentation field.",
                "No yield, purity, activity, therapeutic, production, or success claim is made.",
                expression_purpose and f"User purpose note preserved for review: {expression_purpose}",
            ]
        ),
        "support_status": _status_for_single_or_protein(host_category, source_hint, specific_host),
        "boundary_note": BOUNDARY_NOTE,
    }


def _artemisinin_output(
    *,
    target_name: str,
    host_category: str,
    specific_host: str,
    source_hint: str,
    user_notes: str,
) -> dict[str, Any]:
    gene_slots = [_gene_slot(gene, source_hint=source_hint) for gene in ARTEMISININ_PRECURSOR_GENES]
    cassette_slots = [
        _cassette_slot(f"{gene} cassette draft", gene)
        for gene in ARTEMISININ_PRECURSOR_GENES
    ]
    missing_fields = _dedupe(
        [
            "host",
            "promoter_choices",
            "CDS_sources",
            "terminators",
            "vector_backbone",
            "source_or_reference_confirmation",
            "pathway_step_mapping",
            "cassette_grouping_review",
        ]
        + ([] if host_category else ["host_category"])
        + ([] if specific_host else ["specific_host"])
    )
    return {
        "normalized_target": _normalized_target(target_name or "artemisinin precursor", aliases=["artemisinic acid", "DHAA"], notes=user_notes),
        "target_class": "multi_gene_pathway",
        "design_route": "multi_gene_pathway_expression",
        "construct_template": _construct_template(
            "multi_gene_pathway_expression",
            "Multi-gene pathway construct draft",
            "One promoter + gene/CDS + terminator documentation cassette slot per pathway gene.",
            ["promoter", "gene/CDS", "terminator"],
        ),
        "gene_slots": gene_slots,
        "cassette_slots": cassette_slots,
        "required_parts": [
            "host context documentation row",
            "promoter documentation row per cassette",
            "gene/CDS documentation row per cassette",
            "terminator documentation row per cassette",
            "vector backbone documentation row",
            "pathway step link documentation row",
        ],
        "missing_fields": missing_fields,
        "source_requirements": [
            "source/provenance for each pathway gene",
            "pathway source/reference notes",
            "host context source/provenance",
            "promoter source/provenance for each cassette",
            "terminator source/provenance for each cassette",
            "vector backbone source/provenance",
        ]
        + ([f"user source hint to review: {source_hint}"] if source_hint else []),
        "review_notes": [
            "This is a multi-gene pathway documentation skeleton with human review required.",
            "Confirm each gene slot, source record, pathway step link, promoter context, terminator context, and vector backbone.",
            "The output does not predict biological output, improve pathway behavior, or confirm downstream use.",
        ],
        "support_status": "partially_supported" if host_category or specific_host else "needs_review",
        "boundary_note": PATHWAY_BOUNDARY_NOTE,
    }


def _sugarcane_output(
    *,
    target_name: str,
    host_category: str,
    specific_host: str,
    source_hint: str,
    user_notes: str,
) -> dict[str, Any]:
    return {
        "normalized_target": _normalized_target(target_name or "sugarcane healthy sugar", notes=user_notes),
        "target_class": "trait_or_phenotype",
        "design_route": "needs_target_clarification",
        "construct_template": _construct_template(
            "needs_target_clarification",
            "Target clarification draft",
            "No construct template is created until the target mechanism and documentation route are selected.",
            [],
        ),
        "gene_slots": [],
        "cassette_slots": [],
        "required_parts": [],
        "missing_fields": _dedupe(
            [
                "target_mechanism",
                "gene_or_pathway_identity",
                "source_or_reference_confirmation",
                "documentation_route_selection",
            ]
            + ([] if host_category else ["host_category"])
            + ([] if specific_host else ["specific_host"])
        ),
        "source_requirements": [
            "source/provenance for the selected route",
            "source/provenance for any future gene, enzyme, protein, or pathway slot",
        ]
        + ([f"user source hint to review: {source_hint}"] if source_hint else []),
        "review_notes": [
            "Choose one documentation route before a construct draft is prepared: sweet protein expression.",
            "Choose one documentation route before a construct draft is prepared: rare sugar enzyme expression.",
            "Choose one documentation route before a construct draft is prepared: steviol glycoside pathway.",
            "Choose one documentation route before a construct draft is prepared: sugar metabolism modification.",
            "Sugarcane host context can be recorded, but it does not make this target construct-ready.",
        ],
        "support_status": "unresolved",
        "boundary_note": UNRESOLVED_BOUNDARY_NOTE,
    }


def _unknown_output(
    *,
    target_name: str,
    target_type: str,
    host_category: str,
    specific_host: str,
    source_hint: str,
    user_notes: str,
    unsupported: bool = False,
) -> dict[str, Any]:
    status = "unsupported" if unsupported else "unresolved"
    route = "unsupported" if unsupported else "needs_target_clarification"
    target_class = "unsupported_or_out_of_scope" if unsupported else "unresolved_target"
    review_notes = [
        "Clarify target type and documentation route before any construct draft is prepared.",
        "Provide gene, protein, enzyme, reporter, pathway, or trait mechanism context if available.",
    ]
    if unsupported:
        review_notes.insert(0, "This request is outside the documentation-only router boundary.")
    return {
        "normalized_target": _normalized_target(target_name or "Unresolved target", notes=user_notes),
        "target_class": target_class,
        "design_route": route,
        "construct_template": _construct_template(
            route,
            "Target clarification draft",
            "No construct template is created until the target type and documentation route are clarified.",
            [],
        ),
        "gene_slots": [],
        "cassette_slots": [],
        "required_parts": [],
        "missing_fields": _dedupe(
            [
                "target_type" if not target_type else "",
                "design_route_clarification",
                "gene_or_pathway_identity",
                "source_or_reference_confirmation",
            ]
            + ([] if host_category else ["host_category"])
            + ([] if specific_host else ["specific_host"])
        ),
        "source_requirements": [
            "source/provenance for the selected target identity",
            "source/provenance for the selected documentation route",
        ]
        + ([f"user source hint to review: {source_hint}"] if source_hint else []),
        "review_notes": review_notes,
        "support_status": status,
        "boundary_note": UNRESOLVED_BOUNDARY_NOTE,
    }


def route_target_design(
    target_name: str,
    target_type: str | None = None,
    host_category: str | None = None,
    specific_host: str | None = None,
    expression_purpose: str | None = None,
    gene_list: list[str] | None = None,
    route_hint: str | None = None,
    source_hint: str | None = None,
    user_notes: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic documentation-only target design route draft."""
    clean_target_name = _text(target_name)
    clean_target_type = _text(target_type)
    clean_host_category = _text(host_category)
    clean_specific_host = _text(specific_host)
    clean_expression_purpose = _text(expression_purpose)
    clean_gene_list = _clean_list(gene_list)
    clean_route_hint = _text(route_hint)
    clean_source_hint = _text(source_hint)
    clean_user_notes = _text(user_notes)
    combined = _lower_text(
        clean_target_name,
        clean_target_type,
        clean_host_category,
        clean_specific_host,
        clean_expression_purpose,
        " ".join(clean_gene_list),
        clean_route_hint,
        clean_source_hint,
        clean_user_notes,
    )

    if _has_any(combined, FORBIDDEN_ROUTE_CUES):
        return _unknown_output(
            target_name=clean_target_name,
            target_type=clean_target_type,
            host_category=clean_host_category,
            specific_host=clean_specific_host,
            source_hint=clean_source_hint,
            user_notes=clean_user_notes,
            unsupported=True,
        )
    if _is_artemisinin_precursor_target(clean_target_name) or (
        len(clean_gene_list) > 1 and _has_any(combined, ["artemisinin", "pathway"])
    ):
        return _artemisinin_output(
            target_name=clean_target_name,
            host_category=clean_host_category,
            specific_host=clean_specific_host,
            source_hint=clean_source_hint,
            user_notes=clean_user_notes,
        )
    if _is_sugarcane_healthy_sugar_target(clean_target_name, clean_target_type, combined):
        return _sugarcane_output(
            target_name=clean_target_name,
            host_category=clean_host_category,
            specific_host=clean_specific_host,
            source_hint=clean_source_hint,
            user_notes=clean_user_notes,
        )
    if _is_hsa_target(clean_target_name):
        return _hsa_output(
            target_name=clean_target_name,
            host_category=clean_host_category,
            specific_host=clean_specific_host,
            expression_purpose=clean_expression_purpose,
            route_hint=clean_route_hint,
            source_hint=clean_source_hint,
            user_notes=clean_user_notes,
        )
    if _is_generic_single_gene_target(clean_target_name, clean_target_type, clean_route_hint, clean_gene_list):
        return _single_gene_output(
            target_name=clean_target_name,
            host_category=clean_host_category,
            specific_host=clean_specific_host,
            expression_purpose=clean_expression_purpose,
            gene_list=clean_gene_list,
            source_hint=clean_source_hint,
            user_notes=clean_user_notes,
        )
    return _unknown_output(
        target_name=clean_target_name,
        target_type=clean_target_type,
        host_category=clean_host_category,
        specific_host=clean_specific_host,
        source_hint=clean_source_hint,
        user_notes=clean_user_notes,
    )
