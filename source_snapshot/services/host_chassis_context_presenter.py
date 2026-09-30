from __future__ import annotations

import re
from typing import Any

from services.placeholder_review_value import is_placeholder_review_value

HOST_CHASSIS_CONTEXT_ASSET_TYPE = "host_chassis_context_note"

SUPPORTED_HOST_CONTEXTS = (
    "bacterial",
    "yeast",
    "mammalian",
    "plant",
    "generic / unspecified",
)

HOST_CHASSIS_CONTEXT_BOUNDARY_NOTE = (
    "Host / chassis context is documentation-only review context. "
    "It does not choose a host, certify biology, validate biology, tune a design, "
    "or provide wet-lab use decisions."
)
HOST_CHASSIS_CONTEXT_LIMITATION_NOTE = (
    "Linked host / chassis context records preserve local documentation context only. "
    "Plant and Nicotiana examples may appear as examples, not as default or preferred contexts."
)
HOST_CHASSIS_CONTEXT_SAFE_REPLACEMENTS = (
    ("host compatibility", "host context documentation"),
    ("compatible host", "documented host context"),
    ("compatibility proof", "documentation context note"),
    ("host readiness", "host context review notes"),
    ("ready host", "documented host context"),
    ("validated host", "reviewed host context record"),
    ("recommended host", "host context record"),
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _safe_host_context_text(value: Any, fallback: str = "") -> str:
    clean = _text(value, fallback)
    if is_placeholder_review_value(clean):
        clean = fallback
    for unsafe, replacement in HOST_CHASSIS_CONTEXT_SAFE_REPLACEMENTS:
        clean = re.sub(re.escape(unsafe), replacement, clean, flags=re.IGNORECASE)
    return clean


def _combined_text(link: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "asset_display_name",
        "asset_label",
        "asset_id",
        "documentation_note",
        "organism_or_source_context",
    ):
        parts.append(_text(link.get(key)))
    source_snapshot = link.get("source_context_snapshot")
    if isinstance(source_snapshot, dict):
        for key in (
            "project_documentation_context",
            "host_context",
            "chassis_context",
            "organism_or_source_context",
            "source_label",
            "source_labels",
            "catalog",
            "version_context",
        ):
            parts.append(_text(source_snapshot.get(key)))
    asset_snapshot = link.get("asset_snapshot")
    if isinstance(asset_snapshot, dict):
        for key in (
            "asset_label",
            "display_name",
            "source_label",
            "limitation_note",
        ):
            parts.append(_text(asset_snapshot.get(key)))
    review_snapshot = link.get("review_status_snapshot")
    if isinstance(review_snapshot, dict):
        for key in ("review_status", "human_review_note", "review_notes"):
            parts.append(_text(review_snapshot.get(key)))
    raw_tags = link.get("tags")
    if isinstance(raw_tags, list):
        parts.extend(_text(tag) for tag in raw_tags)
    return " ".join(part for part in parts if part).casefold()


def classify_host_context(link: dict[str, Any]) -> str:
    blob = _combined_text(link)
    if any(term in blob for term in ("bacterial", "bacteria", "e. coli", "ecoli", "microbial")):
        return "bacterial"
    if any(term in blob for term in ("yeast", "s. cerevisiae", "saccharomyces", "pichia", "komagataella")):
        return "yeast"
    if any(term in blob for term in ("mammalian", "cho", "hek", "cell culture")):
        return "mammalian"
    if any(term in blob for term in ("plant", "nicotiana", "arabidopsis", "viridiplantae")):
        return "plant"
    return "generic / unspecified"


def _classify_project_host_context(project: dict[str, Any] | None) -> str:
    project = project if isinstance(project, dict) else {}
    blob = " ".join(
        _text(project.get(key))
        for key in ("host", "chassis", "organism", "organism_source", "description")
    ).casefold()
    if any(term in blob for term in ("bacterial", "bacteria", "e. coli", "ecoli", "microbial")):
        return "bacterial"
    if any(term in blob for term in ("yeast", "s. cerevisiae", "saccharomyces", "pichia", "komagataella")):
        return "yeast"
    if any(term in blob for term in ("mammalian", "cho", "hek", "cell culture", "human")):
        return "mammalian"
    if any(term in blob for term in ("plant", "nicotiana", "arabidopsis", "viridiplantae", "rice", "maize")):
        return "plant"
    return "generic / unspecified"


def _label(context: str) -> str:
    return {
        "bacterial": "Bacterial",
        "yeast": "Yeast",
        "mammalian": "Mammalian",
        "plant": "Plant",
        "generic / unspecified": "Generic / unspecified",
    }.get(context, "Generic / unspecified")


def host_chassis_context_label(context: Any) -> str:
    return _label(_text(context, "generic / unspecified"))


def summarize_asset_host_chassis_context(record: dict[str, Any] | None) -> dict[str, str]:
    asset = record if isinstance(record, dict) else {}
    source_value = _safe_host_context_text(
        asset.get("organism_or_source_context")
        or asset.get("host_context")
        or asset.get("chassis_context"),
        "Not recorded",
    )
    normalized_context = (
        "generic / unspecified"
        if source_value == "Not recorded"
        else classify_host_context(asset)
    )
    return {
        "source_value": source_value,
        "normalized_context": normalized_context,
        "normalized_context_label": _label(normalized_context),
        "readback": (
            "Recorded host / chassis context only: "
            f"{source_value}; normalized review context: {_label(normalized_context)}. "
            "This is source/readback context, not compatibility evidence."
        ),
    }


def summarize_linked_host_chassis_contexts(
    linked_catalog_assets: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    links = [
        dict(link)
        for link in linked_catalog_assets or []
        if isinstance(link, dict) and _text(link.get("asset_type")) == HOST_CHASSIS_CONTEXT_ASSET_TYPE
    ]
    references: list[dict[str, Any]] = []
    counts = {context: 0 for context in SUPPORTED_HOST_CONTEXTS}
    for link in links:
        normalized_context = classify_host_context(link)
        counts[normalized_context] += 1
        source_snapshot = (
            dict(link.get("source_context_snapshot"))
            if isinstance(link.get("source_context_snapshot"), dict)
            else {}
        )
        review_snapshot = (
            dict(link.get("review_status_snapshot"))
            if isinstance(link.get("review_status_snapshot"), dict)
            else {}
        )
        references.append(
            {
                "asset_id": _text(link.get("asset_id")),
                "asset_display_name": _safe_host_context_text(
                    link.get("asset_display_name")
                    or link.get("asset_label")
                    or link.get("asset_id"),
                    "Unknown host / chassis context record",
                ),
                "normalized_context": normalized_context,
                "project_documentation_context": _safe_host_context_text(
                    source_snapshot.get("project_documentation_context"),
                    "No project documentation context recorded",
                ),
                "source_value": _safe_host_context_text(
                    source_snapshot.get("host_context")
                    or source_snapshot.get("chassis_context")
                    or source_snapshot.get("organism_or_source_context")
                    or link.get("organism_or_source_context"),
                    "No recorded host / chassis context",
                ),
                "source_status": _safe_host_context_text(
                    source_snapshot.get("source_provenance_status")
                    or source_snapshot.get("source_review_status")
                    or link.get("source_label"),
                    "No source status recorded",
                ),
                "review_status": _safe_host_context_text(
                    review_snapshot.get("review_status")
                    or review_snapshot.get("human_review_status")
                    or review_snapshot.get("curation_statuses"),
                    "No review status recorded",
                ),
                "documentation_note": _safe_host_context_text(
                    link.get("documentation_note"),
                    "No documentation note recorded",
                ),
            }
        )
    present_contexts = [context for context, count in counts.items() if count]
    plant_count = counts["plant"]
    return {
        "reference_count": len(references),
        "context_counts": counts,
        "supported_contexts": list(SUPPORTED_HOST_CONTEXTS),
        "supported_contexts_present": present_contexts,
        "non_plant_context_count": sum(count for context, count in counts.items() if context != "plant"),
        "plant_reference_count": plant_count,
        "plant_is_only_supported_context": bool(references) and len(present_contexts) == 1 and plant_count > 0,
        "references": sorted(
            references,
            key=lambda row: (
                _text(row.get("normalized_context")).casefold(),
                _text(row.get("asset_display_name")).casefold(),
                _text(row.get("asset_id")).casefold(),
            ),
        ),
        "boundary_note": HOST_CHASSIS_CONTEXT_BOUNDARY_NOTE,
        "limitation_note": HOST_CHASSIS_CONTEXT_LIMITATION_NOTE,
        "empty_state_message": (
            "No host / chassis context references are linked yet. "
            "This project remains chassis-neutral unless documentation-only context references are added."
        ),
    }


def build_host_chassis_context_summary(
    project: dict[str, Any] | list[dict[str, Any]] | None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if linked_catalog_assets is None and isinstance(project, list):
        linked_catalog_assets = project
        project = {}

    project_data = project if isinstance(project, dict) else {}
    linked_summary = summarize_linked_host_chassis_contexts(linked_catalog_assets)
    project_context = _classify_project_host_context(project_data)

    context_counts = dict(linked_summary["context_counts"])
    context_counts[project_context] += 1
    contexts_present = [context for context in SUPPORTED_HOST_CONTEXTS if context_counts.get(context, 0) > 0]
    rows = [
        {
            "source_label": "Active project host field",
            "source_value": _safe_host_context_text(project_data.get("host"), "Not set"),
            "normalized_context": project_context,
            "normalized_context_label": _label(project_context),
            "asset_display_name": _safe_host_context_text(
                project_data.get("name") or project_data.get("target_product"),
                "Active project",
            ),
        }
    ]
    rows.extend(
        [
            {
                "source_label": "Linked host / chassis context reference",
                "source_value": _safe_host_context_text(
                    row.get("source_value"),
                    "No recorded host / chassis context",
                ),
                "normalized_context": row.get("normalized_context", "generic / unspecified"),
                "normalized_context_label": _label(row.get("normalized_context", "generic / unspecified")),
                "asset_display_name": _safe_host_context_text(
                    row.get("asset_display_name"),
                    "Unknown host / chassis context record",
                ),
            }
            for row in linked_summary["references"]
        ]
    )

    return {
        **linked_summary,
        "project_context": project_context,
        "project_context_label": _label(project_context),
        "supported_context_labels": [_label(context) for context in SUPPORTED_HOST_CONTEXTS],
        "contexts_present": contexts_present,
        "contexts_present_labels": [_label(context) for context in contexts_present],
        "context_count": len(rows),
        "rows": rows,
        "plant_is_supported_example_only": True,
    }
