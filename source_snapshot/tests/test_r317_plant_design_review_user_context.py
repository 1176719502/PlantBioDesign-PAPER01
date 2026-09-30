from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.plant_design_review_user_context import (
    build_plant_design_review_markdown_draft,
    build_plant_design_review_user_context_preview,
)


def _complete_context() -> dict[str, str]:
    return {
        "project_name": "Manual plant review context",
        "target_product": "Albumin documentation target",
        "plant_species": "Oryza sativa review context",
        "target_tissue": "seed documentation context",
        "expression_mode": "plant molecular farming documentation context",
        "gene_cds_source": "local CDS source record and reviewer note",
        "plant_promoter": "seed promoter source record",
        "utr_kozak": "5' UTR review note",
        "signal_transit_targeting": "signal peptide review note",
        "terminator": "terminator source record",
        "selectable_marker_reporter": "marker documentation note",
        "vector_backbone": "backbone source record",
        "transformation_context": "transformation context recorded for documentation only",
        "evidence_provenance_notes": "source/provenance notes recorded for human review",
        "manual_follow_up_notes": "review source records before handoff",
    }


def test_user_context_preview_complete_context_produces_readback_identity_and_sections() -> None:
    preview = build_plant_design_review_user_context_preview(
        _complete_context(),
        generated_at="2026-06-30T13:14:15+00:00",
    )
    package = preview["package"]
    identity = package["identity"]
    field_readback = {row["field_label"]: row["readback"] for row in preview["field_readback"]}
    section_readback = {row["title"]: row["readback"] for row in package["sections"]}

    assert preview["status"] == "RUNTIME_PREVIEW_ONLY"
    assert preview["documentation_only_copy"] == (
        "Plant Design Review Package preview is documentation-only and review-only."
    )
    assert field_readback["Project name"] == "Manual plant review context"
    assert field_readback["Gene / CDS source provenance"] == "local CDS source record and reviewer note"
    assert section_readback["Target product / protein"] == "Albumin documentation target"
    assert section_readback["Plant species / host context"] == "Oryza sativa review context"
    assert section_readback["Plant promoter context"] == "seed promoter source record"
    assert section_readback["Terminator"] == "terminator source record"
    assert identity["snapshot_id"] == "BDS-PLANT-R310-20260630-131415"
    assert re.fullmatch(r"[0-9a-f]{32}", identity["md5_checksum"])
    assert identity["qr_payload"] == (
        "BioDesignStudioPlant|PlantDesignReviewPackage|"
        f"snapshot={identity['snapshot_id']}|md5={identity['md5_checksum']}"
    )
    assert preview["markdown_draft"].startswith("# Plant Design Review Package Draft")
    assert "Plant Design Review Package preview is documentation-only and review-only." in preview["markdown_draft"]
    assert "Manual follow-up notes: review source records before handoff" in preview["markdown_draft"]


def test_user_context_preview_missing_placeholder_fields_produce_review_gaps() -> None:
    preview = build_plant_design_review_user_context_preview(
        {
            "project_name": "Plant review context",
            "target_product": "Albumin documentation target",
            "plant_species": "TBD",
            "gene_cds_source": "not recorded",
            "plant_promoter": "",
            "manual_follow_up_notes": "Review source records.",
        },
        generated_at="2026-06-30T13:14:15+00:00",
    )
    gaps = preview["source_provenance_gaps"]
    gap_fields = {gap["field_label"] for gap in gaps}
    package_summary = preview["package"]["summary"]

    assert "Plant species / host context" in gap_fields
    assert "Gene / CDS source provenance" in gap_fields
    assert "Plant promoter context" in gap_fields
    assert "Project name" not in gap_fields
    assert "Target product / protein" not in gap_fields
    assert package_summary["not_available_count"] >= 1
    assert any("source/provenance" in gap["issue"].lower() for gap in gaps)
    assert "## Source/provenance gaps" in preview["markdown_draft"]
    assert "Plant promoter context: Missing or placeholder source/provenance context." in preview["markdown_draft"]


def test_user_context_preview_md5_is_stable_for_same_normalized_content() -> None:
    first = build_plant_design_review_user_context_preview(
        _complete_context(),
        generated_at="2026-06-30T13:14:15+00:00",
    )
    second = build_plant_design_review_user_context_preview(
        _complete_context(),
        generated_at="2026-06-30T13:14:15+00:00",
    )

    assert first["package"]["identity"]["md5_checksum"] == second["package"]["identity"]["md5_checksum"]


def test_markdown_draft_complete_context_renders_required_sections_identity_and_copy() -> None:
    draft = build_plant_design_review_markdown_draft(
        _complete_context(),
        generated_at="2026-06-30T13:14:15+00:00",
    )

    for expected in [
        "# Plant Design Review Package Draft",
        "## Documentation-only boundary",
        "Project name: Manual plant review context",
        "Project direction: Plant recombinant protein / molecular farming",
        "Target product / protein: Albumin documentation target",
        "Plant species / host context: Oryza sativa review context",
        "Target tissue / organ / expression compartment: seed documentation context",
        "Expression mode: plant molecular farming documentation context",
        "Gene / CDS source provenance: local CDS source record and reviewer note",
        "Plant promoter context: seed promoter source record",
        "5' UTR / Kozak-like context if applicable: 5' UTR review note",
        "Signal peptide / transit peptide / subcellular targeting if applicable: signal peptide review note",
        "Terminator: terminator source record",
        "Selectable marker / reporter: marker documentation note",
        "Vector / backbone context: backbone source record",
        "Transformation context as documentation-only context: transformation context recorded for documentation only",
        "Evidence / provenance notes: source/provenance notes recorded for human review",
        "Manual follow-up notes: review source records before handoff",
        "## Source/provenance gaps",
        "No source/provenance gaps were detected from the runtime manual context fields.",
        "## Package identity",
        "Snapshot ID: BDS-PLANT-R310-20260630-131415",
        "BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=BDS-PLANT-R310-20260630-131415|md5=",
        "QR/MD5 verifies package identity only.",
        "QR/MD5 verifies only Plant Design Review Package preview identity, not biological validity.",
    ]:
        assert expected in draft

    md5_match = re.search(r"MD5 checksum: ([0-9a-f]{32})", draft)
    assert md5_match


def test_markdown_draft_missing_context_renders_review_gaps_not_recommendations() -> None:
    draft = build_plant_design_review_markdown_draft(
        {
            "project_name": "Plant review context",
            "target_product": "Albumin documentation target",
            "plant_species": "TBD",
            "gene_cds_source": "not recorded",
            "plant_promoter": "",
            "manual_follow_up_notes": "Review source records.",
        },
        generated_at="2026-06-30T13:14:15+00:00",
    )

    assert "Plant species / host context: Missing or placeholder source/provenance context." in draft
    assert "Gene / CDS source provenance: Missing or placeholder source/provenance context." in draft
    assert "Plant promoter context: Missing or placeholder source/provenance context." in draft
    assert "Manual follow-up: Record plant promoter source/provenance context." in draft
    assert "Manual follow-up notes: Review source records." in draft
    assert "recommend" not in draft.lower().replace("does not recommend", "")


def test_user_context_preview_identity_copy_is_not_biological_validation() -> None:
    preview = build_plant_design_review_user_context_preview(
        _complete_context(),
        generated_at="2026-06-30T13:14:15+00:00",
    )
    text = str(preview).lower()

    assert "qr/md5 verifies only plant design review package preview identity" in text
    assert "not biological validity" in text
    for forbidden in [
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
        "construct is ready",
        "biological validation",
        "experiment outcomes are verified",
    ]:
        assert forbidden not in text
