from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import normalize_generated_output_claims
from services.placeholder_review_value import clean_review_value, has_recorded_review_value
from services.plant_design_review_package_service import build_plant_design_review_package


USER_CONTEXT_FIELD_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "project_name",
        "label": "Project name",
        "gap": "Record a project name for the plant review package preview.",
    },
    {
        "key": "target_product",
        "label": "Target product / protein",
        "gap": "Record the target product or protein context.",
    },
    {
        "key": "plant_species",
        "label": "Plant species / host context",
        "gap": "Record the plant species or host context.",
    },
    {
        "key": "target_tissue",
        "label": "Target tissue / organ / expression compartment",
        "gap": "Record tissue, organ, or expression-compartment context when relevant.",
    },
    {
        "key": "expression_mode",
        "label": "Expression mode",
        "gap": "Record expression-mode context as documentation only.",
    },
    {
        "key": "gene_cds_source",
        "label": "Gene / CDS source provenance",
        "gap": "Record gene or CDS source/provenance context.",
    },
    {
        "key": "plant_promoter",
        "label": "Plant promoter context",
        "gap": "Record plant promoter source/provenance context.",
    },
    {
        "key": "utr_kozak",
        "label": "5' UTR / Kozak-like context if applicable",
        "gap": "Record 5' UTR or Kozak-like context, or note why it is not applicable.",
    },
    {
        "key": "signal_transit_targeting",
        "label": "Signal peptide / transit peptide / subcellular targeting if applicable",
        "gap": "Record signal, transit, or subcellular targeting context, or note why it is not applicable.",
    },
    {
        "key": "terminator",
        "label": "Terminator",
        "gap": "Record terminator source/provenance context.",
    },
    {
        "key": "selectable_marker_reporter",
        "label": "Selectable marker / reporter",
        "gap": "Record selectable marker or reporter documentation context, or note why it is not applicable.",
    },
    {
        "key": "vector_backbone",
        "label": "Vector / backbone context",
        "gap": "Record vector or backbone source/provenance context.",
    },
    {
        "key": "transformation_context",
        "label": "Transformation context as documentation-only context",
        "gap": "Record transformation context only as documentation context; no procedure is generated.",
    },
    {
        "key": "evidence_provenance_notes",
        "label": "Evidence / provenance notes",
        "gap": "Record evidence/provenance notes or unresolved source questions.",
    },
    {
        "key": "manual_follow_up_notes",
        "label": "Manual follow-up notes",
        "gap": "Record manual follow-up notes for human review.",
    },
)

IDENTITY_ONLY_COPY = (
    "QR/MD5 verifies only Plant Design Review Package preview identity, not biological validity."
)
DOCUMENTATION_ONLY_COPY = (
    "Plant Design Review Package preview is documentation-only and review-only."
)


def _field_label(key: str) -> str:
    for spec in USER_CONTEXT_FIELD_SPECS:
        if spec["key"] == key:
            return spec["label"]
    return key.replace("_", " ").title()


def _recorded_text(value: Any) -> str:
    return clean_review_value(value, "")


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _markdown_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return _recorded_text(value) or fallback


def _stable_generated_at(normalized_context: Mapping[str, str]) -> str:
    digest = hashlib.md5(_canonical_json(normalized_context).encode("utf-8")).hexdigest()
    hour = int(digest[0:2], 16) % 24
    minute = int(digest[2:4], 16) % 60
    second = int(digest[4:6], 16) % 60
    return f"2026-06-30T{hour:02d}:{minute:02d}:{second:02d}+00:00"


def normalize_plant_review_user_context(user_context: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize manual plant review context fields without inventing values."""
    source = dict(user_context or {})
    normalized: dict[str, str] = {}
    for spec in USER_CONTEXT_FIELD_SPECS:
        normalized[spec["key"]] = _recorded_text(source.get(spec["key"]))
    return normalized


def plant_review_context_gaps(normalized_context: Mapping[str, str]) -> list[dict[str, str]]:
    """Return documentation review gaps for missing or placeholder user fields."""
    gaps: list[dict[str, str]] = []
    for spec in USER_CONTEXT_FIELD_SPECS:
        value = normalized_context.get(spec["key"])
        if not has_recorded_review_value(value):
            gaps.append(
                {
                    "field_key": spec["key"],
                    "field_label": spec["label"],
                    "issue": "Missing or placeholder source/provenance context.",
                    "manual_follow_up": spec["gap"],
                }
            )
    return gaps


def _package_inputs(normalized_context: Mapping[str, str], gaps: list[dict[str, str]]) -> dict[str, Any]:
    project = {
        "name": normalized_context.get("project_name"),
        "target_product": normalized_context.get("target_product"),
        "plant_species": normalized_context.get("plant_species"),
        "target_tissue": normalized_context.get("target_tissue"),
        "expression_mode": normalized_context.get("expression_mode"),
        "vector_backbone": normalized_context.get("vector_backbone"),
        "transformation_context": normalized_context.get("transformation_context"),
        "manual_follow_up": normalized_context.get("manual_follow_up_notes"),
        "review_notes": normalized_context.get("evidence_provenance_notes"),
    }
    construct_documentation = {
        "cassette_rows": [
            {
                "promoter_label": normalized_context.get("plant_promoter"),
                "terminator_label": normalized_context.get("terminator"),
            }
        ],
        "cassette_part_rows": [
            {"part_role": "5' UTR / Kozak-like", "part_label": normalized_context.get("utr_kozak")},
            {
                "part_role": "signal peptide / transit peptide / subcellular targeting",
                "part_label": normalized_context.get("signal_transit_targeting"),
            },
            {
                "part_role": "selectable marker / reporter",
                "part_label": normalized_context.get("selectable_marker_reporter"),
            },
            {"part_role": "vector backbone", "part_label": normalized_context.get("vector_backbone")},
        ],
        "linked_gene_rows": [
            {
                "gene_label": normalized_context.get("target_product"),
                "source_reference": normalized_context.get("gene_cds_source"),
                "provenance_note": normalized_context.get("evidence_provenance_notes"),
            }
        ],
        "review_gap_rows": gaps,
        "construct_component_gap_queue": gaps,
    }
    linked_catalog_assets = {
        "total_linked_assets": 0,
        "linked_plant_promoter_count": 1 if has_recorded_review_value(normalized_context.get("plant_promoter")) else 0,
        "missing_source_or_review_metadata_count": len(gaps),
    }
    return {
        "project": project,
        "construct_documentation": construct_documentation,
        "linked_catalog_assets": linked_catalog_assets,
    }


def _preview_parts(
    user_context: Mapping[str, Any] | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_context = normalize_plant_review_user_context(user_context)
    gaps = plant_review_context_gaps(normalized_context)
    package_inputs = _package_inputs(normalized_context, gaps)
    package = build_plant_design_review_package(
        project=package_inputs["project"],
        construct_documentation=package_inputs["construct_documentation"],
        linked_catalog_assets=package_inputs["linked_catalog_assets"],
        generated_at=generated_at or _stable_generated_at(normalized_context),
    )

    field_readback = [
        {
            "field_key": spec["key"],
            "field_label": spec["label"],
            "readback": normalized_context.get(spec["key"]) or "NOT_AVAILABLE",
        }
        for spec in USER_CONTEXT_FIELD_SPECS
    ]
    return {
        "normalized_context": normalized_context,
        "source_provenance_gaps": gaps,
        "field_readback": field_readback,
        "manual_follow_up_reminders": [
            gap["manual_follow_up"] for gap in gaps
        ]
        or ["Manual review should confirm source/provenance context before handoff."],
        "package": package,
    }


def _format_markdown_draft(parts: Mapping[str, Any]) -> str:
    normalized_context = dict(parts.get("normalized_context") or {})
    package = dict(parts.get("package") or {})
    identity = dict(package.get("identity") or {})
    field_readback = [
        row for row in (parts.get("field_readback") or []) if isinstance(row, Mapping)
    ]
    gaps = [
        gap for gap in (parts.get("source_provenance_gaps") or []) if isinstance(gap, Mapping)
    ]
    manual_follow_up_reminders = [
        str(note) for note in (parts.get("manual_follow_up_reminders") or []) if str(note).strip()
    ]
    lines = [
        "# Plant Design Review Package Draft",
        "",
        "## Documentation-only boundary",
        f"- {DOCUMENTATION_ONLY_COPY}",
        "- This runtime Markdown draft is copyable review text only; it is not saved to the database or added to export packages.",
        "- The draft records user-entered context and documentation review gaps only.",
        "- It does not recommend biological components, optimize sequences, provide protocols, or judge construct use state.",
        "",
        "## Project context",
        f"- Project name: {_markdown_value(normalized_context.get('project_name'))}",
        f"- Project direction: {_markdown_value(identity.get('project_direction'))}",
        f"- Target product / protein: {_markdown_value(normalized_context.get('target_product'))}",
        f"- Plant species / host context: {_markdown_value(normalized_context.get('plant_species'))}",
        f"- Target tissue / organ / expression compartment: {_markdown_value(normalized_context.get('target_tissue'))}",
        f"- Expression mode: {_markdown_value(normalized_context.get('expression_mode'))}",
        "",
        "## Construct and component context",
        f"- Gene / CDS source provenance: {_markdown_value(normalized_context.get('gene_cds_source'))}",
        f"- Plant promoter context: {_markdown_value(normalized_context.get('plant_promoter'))}",
        f"- 5' UTR / Kozak-like context if applicable: {_markdown_value(normalized_context.get('utr_kozak'))}",
        "- Signal peptide / transit peptide / subcellular targeting if applicable: "
        f"{_markdown_value(normalized_context.get('signal_transit_targeting'))}",
        f"- Terminator: {_markdown_value(normalized_context.get('terminator'))}",
        f"- Selectable marker / reporter: {_markdown_value(normalized_context.get('selectable_marker_reporter'))}",
        f"- Vector / backbone context: {_markdown_value(normalized_context.get('vector_backbone'))}",
        "- Transformation context as documentation-only context: "
        f"{_markdown_value(normalized_context.get('transformation_context'))}",
        "",
        "## Evidence and manual review",
        f"- Evidence / provenance notes: {_markdown_value(normalized_context.get('evidence_provenance_notes'))}",
        f"- Manual follow-up notes: {_markdown_value(normalized_context.get('manual_follow_up_notes'))}",
        "",
        "## Source/provenance gaps",
    ]
    if gaps:
        for gap in gaps:
            lines.append(
                "- "
                f"{_markdown_value(gap.get('field_label'))}: "
                f"{_markdown_value(gap.get('issue'))} "
                f"Manual follow-up: {_markdown_value(gap.get('manual_follow_up'))}"
            )
    else:
        lines.append("- No source/provenance gaps were detected from the runtime manual context fields.")

    lines += [
        "",
        "## Manual follow-up reminders",
    ]
    for reminder in manual_follow_up_reminders:
        lines.append(f"- {reminder}")

    lines += [
        "",
        "## Field readback",
    ]
    for row in field_readback:
        lines.append(f"- {_markdown_value(row.get('field_label'))}: {_markdown_value(row.get('readback'))}")

    lines += [
        "",
        "## Package identity",
        f"- Snapshot ID: {_markdown_value(identity.get('snapshot_id'))}",
        f"- MD5 checksum: {_markdown_value(identity.get('md5_checksum'))}",
        f"- QR payload: {_markdown_value(identity.get('qr_payload'))}",
        "",
        "## QR/MD5 identity-only warning",
        "- QR/MD5 verifies package identity only. It does not verify biological function, plant-line state, construct use state, yield, or experiment outcomes.",
        f"- {IDENTITY_ONLY_COPY}",
    ]
    return "\n".join(lines)


def build_plant_design_review_markdown_draft(
    user_context: Mapping[str, Any] | None,
    *,
    generated_at: str | None = None,
) -> str:
    """Build a runtime-only, copyable Plant Design Review Markdown draft."""
    parts = _preview_parts(user_context, generated_at=generated_at)
    return normalize_generated_output_claims(_format_markdown_draft(parts))


def build_plant_design_review_user_context_preview(
    user_context: Mapping[str, Any] | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a runtime-only Plant Design Review Package preview from manual user context."""
    parts = _preview_parts(user_context, generated_at=generated_at)
    preview = {
        "title": "Plant Design Review Package preview",
        "status": "RUNTIME_PREVIEW_ONLY",
        "documentation_only_copy": DOCUMENTATION_ONLY_COPY,
        "identity_only_copy": IDENTITY_ONLY_COPY,
        "field_readback": parts["field_readback"],
        "source_provenance_gaps": parts["source_provenance_gaps"],
        "manual_follow_up_reminders": parts["manual_follow_up_reminders"],
        "markdown_draft": _format_markdown_draft(parts),
        "package": parts["package"],
    }
    return normalize_generated_output_claims(preview)


def plant_review_user_context_field_label(key: str) -> str:
    return _field_label(key)
