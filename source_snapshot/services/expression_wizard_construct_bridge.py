from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services import expression_construct_repository as repo


DEFAULT_CONSTRUCT_LABEL = "Wizard-derived construct draft"
DEFAULT_CASSETTE_LABEL = "Wizard-derived expression cassette"
CONSTRUCT_TYPE = "documentation-only construct draft"
CASSETTE_ROLE = "wizard-derived expression cassette documentation"
SOURCE_REFERENCE = "Expression Wizard current design record"
PROVENANCE_NOTE = (
    "Created from the current single-cassette Expression Wizard state for documentation traceability."
)
PATHWAY_LINK_DEFERRED_NOTE = (
    "No pathway step context was available in the current Wizard session; pathway step linkage was deferred."
)


@dataclass(frozen=True)
class WizardConstructSaveResult:
    construct: dict[str, Any] = field(default_factory=dict)
    cassette: dict[str, Any] = field(default_factory=dict)
    cassette_parts: list[dict[str, Any]] = field(default_factory=list)
    gene_link: dict[str, Any] = field(default_factory=dict)
    pathway_step_link: dict[str, Any] = field(default_factory=dict)
    pathway_link_deferred: bool = True
    pathway_link_note: str = PATHWAY_LINK_DEFERRED_NOTE


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _get_value(state: Any, key: str, fallback: Any = "") -> Any:
    if isinstance(state, dict):
        return state.get(key, fallback)
    return getattr(state, key, fallback)


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sequence_reference(sequence: Any) -> str:
    clean = "".join(str(sequence or "").split()).upper()
    return f"{len(clean)} bp sequence recorded" if clean else "No sequence recorded"


def _role_from_part_type(part_type: Any) -> str:
    normalized = _text(part_type).lower().replace("_", " ").replace("-", " ")
    if "promoter" in normalized:
        return "promoter"
    if "rbs" in normalized or "kozak" in normalized or "utr" in normalized:
        return "rbs"
    if "cds" in normalized or "gene" in normalized:
        return "cds"
    if "terminator" in normalized:
        return "terminator"
    return "other"


def _fallback_label(role: str) -> str:
    return {
        "promoter": "No promoter label recorded",
        "rbs": "No RBS or 5' UTR label recorded",
        "cds": "No CDS or gene label recorded",
        "terminator": "No terminator label recorded",
    }.get(role, "No part label recorded")


def _part_row(
    *,
    order: int,
    role: str,
    label: Any,
    sequence: Any = "",
    field_name: str = "",
) -> dict[str, Any]:
    clean_role = role if role in repo.PART_ROLE_TERMS else "other"
    clean_label = _text(label, _fallback_label(clean_role))
    source = f"{SOURCE_REFERENCE}: {field_name}" if field_name else SOURCE_REFERENCE
    return {
        "part_order": order,
        "part_role": clean_role,
        "part_label": clean_label,
        "part_reference": _sequence_reference(sequence),
        "source_reference": source,
        "provenance_note": PROVENANCE_NOTE,
    }


def _rows_from_frame_parts(state: Any) -> list[dict[str, Any]]:
    frame = _dict_value(_get_value(state, "frame", {}))
    parts = [part for part in _list_value(frame.get("parts")) if isinstance(part, dict)]
    if not parts:
        return []

    rows: list[dict[str, Any]] = []
    for index, part in enumerate(parts, start=1):
        role = _role_from_part_type(part.get("type"))
        rows.append(
            _part_row(
                order=index,
                role=role,
                label=part.get("name"),
                sequence=part.get("seq"),
                field_name=_text(part.get("type"), "frame part"),
            )
        )
    return rows


def build_cassette_rows_from_wizard_state(wizard_state: Any) -> list[dict[str, Any]]:
    """Map the current single-cassette Wizard state into construct part rows.

    This is a documentation-level row mapping only. It does not evaluate,
    score, rank, or change the Wizard design state.
    """
    frame_rows = _rows_from_frame_parts(wizard_state)
    if frame_rows:
        return frame_rows

    elements = _dict_value(_get_value(wizard_state, "elements", {}))
    cds_sequence = (
        _get_value(wizard_state, "optimized_seq", "")
        or _get_value(wizard_state, "original_seq", "")
    )
    gene_label = _get_value(wizard_state, "gene_name", "")
    return [
        _part_row(
            order=1,
            role="promoter",
            label=elements.get("promoter_name"),
            sequence=elements.get("promoter_seq"),
            field_name="promoter_name",
        ),
        _part_row(
            order=2,
            role="rbs",
            label=elements.get("rbs_name") or elements.get("utr_name"),
            sequence=elements.get("rbs_seq") or elements.get("utr_seq"),
            field_name="rbs_name",
        ),
        _part_row(
            order=3,
            role="cds",
            label=gene_label,
            sequence=cds_sequence,
            field_name="gene_name",
        ),
        _part_row(
            order=4,
            role="terminator",
            label=elements.get("terminator_name"),
            sequence=elements.get("terminator_seq"),
            field_name="terminator_name",
        ),
    ]


def _resolve_part_label(rows: list[dict[str, Any]], role: str) -> str:
    row = next((item for item in rows if item.get("part_role") == role), {})
    return _text(row.get("part_label"))


def _resolve_gene_label(wizard_state: Any, rows: list[dict[str, Any]]) -> str:
    return _text(_get_value(wizard_state, "gene_name")) or _resolve_part_label(rows, "cds")


def _resolve_gene_reference(wizard_state: Any) -> str:
    saved_id = _text(_get_value(wizard_state, "source_saved_design_id"))
    sequence = _get_value(wizard_state, "optimized_seq", "") or _get_value(wizard_state, "original_seq", "")
    if saved_id:
        return f"Saved design id: {saved_id}"
    return _sequence_reference(sequence)


def _resolve_pathway_context(pathway_context: dict[str, Any] | None) -> tuple[str, str]:
    context = pathway_context if isinstance(pathway_context, dict) else {}
    if context.get("source") != "pathway_workspace":
        return "", ""
    step_id = _text(context.get("step_id"))
    step_label = (
        _text(context.get("step_name"))
        or _text(context.get("reaction_name"))
        or _text(context.get("step_order"))
    )
    return step_id, step_label


def _next_cassette_order(construct_id: str) -> int:
    rows = repo.list_construct_cassettes(construct_id)
    orders = []
    for row in rows:
        try:
            orders.append(int(row.get("cassette_order") or 0))
        except (TypeError, ValueError):
            continue
    return (max(orders) + 1) if orders else 1


def save_wizard_draft_to_construct(
    wizard_state: Any,
    *,
    construct_id: str = "",
    cassette_label: str = "",
    create_new_construct: bool = False,
    new_construct_label: str = "",
    pathway_context: dict[str, Any] | None = None,
) -> WizardConstructSaveResult:
    rows = build_cassette_rows_from_wizard_state(wizard_state)

    clean_construct_id = _text(construct_id)
    if create_new_construct or not clean_construct_id:
        construct = repo.create_construct_profile(
            construct_label=_text(new_construct_label, DEFAULT_CONSTRUCT_LABEL),
            construct_type=CONSTRUCT_TYPE,
            host_context_note=_text(_get_value(wizard_state, "host")),
            source_reference=SOURCE_REFERENCE,
            provenance_note=PROVENANCE_NOTE,
            review_status="draft documentation review",
            documentation_scope_note="Documentation-only construct draft created from one Wizard expression cassette.",
        )
        clean_construct_id = _text(construct.get("construct_id"))
    else:
        construct = repo.get_construct_profile(clean_construct_id)

    if not clean_construct_id or not construct:
        return WizardConstructSaveResult(pathway_link_deferred=True)

    gene_label = _resolve_gene_label(wizard_state, rows)
    cassette = repo.create_construct_cassette(
        clean_construct_id,
        cassette_label=_text(cassette_label, DEFAULT_CASSETTE_LABEL),
        cassette_role=CASSETTE_ROLE,
        cassette_order=_next_cassette_order(clean_construct_id),
        promoter_label=_resolve_part_label(rows, "promoter"),
        gene_label=gene_label,
        terminator_label=_resolve_part_label(rows, "terminator"),
        source_reference=SOURCE_REFERENCE,
        provenance_note=PROVENANCE_NOTE,
    )
    cassette_id = _text(cassette.get("cassette_id"))
    saved_parts = [
        repo.add_construct_cassette_part(
            cassette_id,
            part_order=int(row.get("part_order") or 0),
            part_role=_text(row.get("part_role"), "other"),
            part_label=_text(row.get("part_label")),
            part_reference=_text(row.get("part_reference")),
            source_reference=_text(row.get("source_reference"), SOURCE_REFERENCE),
            provenance_note=_text(row.get("provenance_note"), PROVENANCE_NOTE),
        )
        for row in rows
        if cassette_id
    ]

    gene_link = {}
    if _text(gene_label) and gene_label != _fallback_label("cds"):
        gene_link = repo.add_construct_gene_link(
            clean_construct_id,
            gene_label=gene_label,
            gene_reference=_resolve_gene_reference(wizard_state),
            source_reference=SOURCE_REFERENCE,
            provenance_note=PROVENANCE_NOTE,
        )

    pathway_step_id, pathway_step_label = _resolve_pathway_context(pathway_context)
    pathway_step_link = {}
    pathway_deferred = True
    pathway_note = PATHWAY_LINK_DEFERRED_NOTE
    if pathway_step_id or pathway_step_label:
        pathway_step_link = repo.add_construct_pathway_step_link(
            clean_construct_id,
            pathway_step_id=pathway_step_id,
            pathway_step_label=pathway_step_label,
            source_reference=SOURCE_REFERENCE,
            provenance_note=PROVENANCE_NOTE,
        )
        pathway_deferred = False
        pathway_note = "Pathway step context was recorded from the active Wizard session."

    readback_parts = repo.list_construct_cassette_parts(cassette_id) if cassette_id else []
    return WizardConstructSaveResult(
        construct=repo.get_construct_profile(clean_construct_id),
        cassette=next(
            (
                row
                for row in repo.list_construct_cassettes(clean_construct_id)
                if row.get("cassette_id") == cassette_id
            ),
            cassette,
        ),
        cassette_parts=readback_parts or [part for part in saved_parts if part],
        gene_link=gene_link,
        pathway_step_link=pathway_step_link,
        pathway_link_deferred=pathway_deferred,
        pathway_link_note=pathway_note,
    )
