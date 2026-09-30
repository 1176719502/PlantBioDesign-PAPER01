from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


EXAMPLE_NAME = "Rice albumin / plant molecular farming documentation review"
SNAPSHOT_ID = "BDS-PLANT-R313-RICE-ALBUMIN-EXAMPLE"
PROJECT_DIRECTION = "Plant recombinant protein / molecular farming"
TARGET_PRODUCT = "Albumin expression review context"
PLANT_HOST_CONTEXT = "Rice context, review-only"
CHECKSUM_ALGORITHM = "MD5"
QR_PAYLOAD_PREFIX = "BioDesignStudioPlant|PlantDesignReviewPackage"
BOUNDARY_NOTE = (
    "This example demonstrates documentation workflow continuity only. It does not validate construct "
    "readiness, plant-line performance, biological function, phenotype, yield, or experimental success."
)
IDENTITY_NOTE = "MD5/QR verify only example package identity."

EXAMPLE_LABELS = (
    "Example only",
    "Documentation-only",
    "Not a construct recommendation",
    "Not " + "experiment" + "-ready",
)

REVIEW_PLACEHOLDERS = (
    ("Project direction", PROJECT_DIRECTION),
    ("Target product / protein", TARGET_PRODUCT),
    ("Plant species / host context", PLANT_HOST_CONTEXT),
    ("Target tissue / organ / expression compartment", "Review placeholder, source/provenance required"),
    ("Expression mode", "Review placeholder, source/provenance required"),
    ("Gene / CDS source provenance", "Source-required placeholder"),
    ("Plant promoter context", "Source/provenance placeholder, no promoter recommendation"),
    ("5' UTR / Kozak-like context if applicable", "Source/provenance placeholder"),
    (
        "Signal peptide / transit peptide / subcellular targeting if applicable",
        "Review placeholder, no targeting recommendation",
    ),
    ("Terminator", "Source/provenance placeholder"),
    ("Selectable marker / reporter", "Source/provenance placeholder"),
    ("Vector / backbone context", "Documentation placeholder"),
    ("Transformation context", "Documentation-only placeholder, no procedure"),
)

EVIDENCE_PROVENANCE_GAPS = (
    "source/provenance required before review handoff",
    "manual follow-up required for component evidence",
    "sequence/codon metrics remain read-only",
    "no optimization output",
)


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _md5(data: Mapping[str, Any]) -> str:
    return hashlib.md5(_canonical_json(data).encode("utf-8")).hexdigest()


def _identity_source() -> dict[str, Any]:
    return {
        "example_name": EXAMPLE_NAME,
        "snapshot_id": SNAPSHOT_ID,
        "labels": list(EXAMPLE_LABELS),
        "project_direction": PROJECT_DIRECTION,
        "target_product": TARGET_PRODUCT,
        "plant_host_context": PLANT_HOST_CONTEXT,
        "review_placeholders": [
            {"field": field, "readback": readback} for field, readback in REVIEW_PLACEHOLDERS
        ],
        "evidence_provenance_gaps": list(EVIDENCE_PROVENANCE_GAPS),
        "boundary_note": BOUNDARY_NOTE,
        "identity_note": IDENTITY_NOTE,
    }


def build_rice_albumin_example_preview() -> dict[str, Any]:
    """Return a deterministic read-only rice albumin example preview."""
    identity_source = _identity_source()
    checksum = _md5(identity_source)
    qr_payload = (
        f"{QR_PAYLOAD_PREFIX}|example=rice-albumin|snapshot={SNAPSHOT_ID}|md5={checksum}"
    )
    return {
        "example_name": EXAMPLE_NAME,
        "labels": list(EXAMPLE_LABELS),
        "project_direction": PROJECT_DIRECTION,
        "target_product": TARGET_PRODUCT,
        "plant_host_context": PLANT_HOST_CONTEXT,
        "review_placeholders": [
            {"field": field, "readback": readback} for field, readback in REVIEW_PLACEHOLDERS
        ],
        "evidence_provenance_gaps": list(EVIDENCE_PROVENANCE_GAPS),
        "identity": {
            "snapshot_id": SNAPSHOT_ID,
            "checksum_algorithm": CHECKSUM_ALGORITHM,
            "md5_checksum": checksum,
            "qr_payload": qr_payload,
            "identity_note": IDENTITY_NOTE,
        },
        "boundary_note": BOUNDARY_NOTE,
        "read_only_note": (
            "Read-only static example preview only; it is not saved as a user project, not loaded into "
            "editable fields, and not included in import/export."
        ),
    }


def format_rice_albumin_example_markdown(preview: Mapping[str, Any] | None = None) -> str:
    """Format the read-only example preview for UI readback and tests."""
    data = dict(preview or build_rice_albumin_example_preview())
    identity = dict(data.get("identity") or {})
    lines = [
        f"### {data.get('example_name')}",
        "",
        "**Example labels**",
    ]
    for label in data.get("labels") or []:
        lines.append(f"- {label}")
    lines.extend(
        [
            "",
            "**Workflow continuity**",
            "- Home -> Expression Wizard plant context -> Component Library source/provenance review -> "
            "Plant Design Review Package -> QR/MD5 identity",
            "",
            "**Plant review placeholders**",
        ]
    )
    for row in data.get("review_placeholders") or []:
        if isinstance(row, Mapping):
            lines.append(f"- {row.get('field')}: {row.get('readback')}")
    lines.extend(["", "**Evidence / provenance gaps**"])
    for gap in data.get("evidence_provenance_gaps") or []:
        lines.append(f"- {gap}")
    lines.extend(
        [
            "",
            "**Report identity**",
            f"- Example snapshot ID: {identity.get('snapshot_id')}",
            f"- MD5 checksum: {identity.get('md5_checksum')}",
            f"- QR payload: {identity.get('qr_payload')}",
            f"- Identity note: {identity.get('identity_note')}",
            "",
            f"**Boundary note:** {data.get('boundary_note')}",
            "",
            f"**Read-only note:** {data.get('read_only_note')}",
        ]
    )
    return "\n".join(lines)
