from __future__ import annotations

from typing import Any

from services.expression_vector_design_package_adapter import build_expression_vector_design_package_preview
from services.expression_vector_design_package_markdown_formatter import (
    format_expression_vector_design_package_preview_markdown,
)


SAMPLE_WALKTHROUGH_TITLE = "Single-gene enzyme expression vector sample walkthrough"
SAMPLE_PACKAGE_TITLE = "Single-gene enzyme expression vector sample preview"
SAMPLE_BOUNDARY_NOTE = (
    "Read-only sample data for first-time walkthrough only. It is not saved, exported, imported, "
    "or used as a biological recommendation, final vector sequence, procedure, forecast, validation, "
    "or downstream-use judgment."
)


def build_single_gene_expression_vector_sample_walkthrough() -> dict[str, Any]:
    """Build a deterministic read-only sample walkthrough for first-time users.

    The sample is intentionally incomplete so source/provenance gaps and manual
    follow-up remain visible. It does not persist data or create package output.
    """
    preview = build_expression_vector_design_package_preview(
        package_title=SAMPLE_PACKAGE_TITLE,
        source_commit_or_version="R278 read-only sample helper",
        package_status="sample / needs review",
        target_record={
            "recorded_value": "sample-enzyme-1 single-gene target record",
            "target_name": "sample-enzyme-1 single-gene target record",
            "cds_or_protein_value": "Single protein/enzyme target label recorded; sequence body not included in this sample.",
            "review_status": "documented",
            "manual_follow_up": "Manual follow-up: add the target sequence source/provenance note before review.",
            "notes": "Start in Expression Wizard with one target gene / CDS / protein record.",
        },
        sequence_source_record={
            "review_status": "needs source",
            "manual_follow_up": "Manual follow-up: record where the target sequence or protein label came from.",
            "notes": "This sample leaves provenance incomplete on purpose so the gap is visible.",
        },
        host_record={
            "recorded_value": "Host context label recorded by the user",
            "host_system": "Host context label recorded by the user",
            "review_status": "needs source",
            "manual_follow_up": "Manual follow-up: add host context source/provenance and reviewer note.",
            "notes": "The sample records that a host context exists; it does not choose a host.",
        },
        vector_backbone_record={
            "recorded_value": "Vector/backbone label recorded by the user",
            "backbone_name": "Vector/backbone label recorded by the user",
            "review_status": "needs source",
            "manual_follow_up": "Manual follow-up: add vector/backbone source, version, and limitation notes.",
            "notes": "The sample records that a vector/backbone context exists; it does not choose a backbone.",
        },
        slot_records={
            "promoter": [
                {
                    "recorded_value": "Promoter context label recorded by the user",
                    "review_status": "needs source",
                    "manual_follow_up": "Manual follow-up: record promoter source/provenance before review.",
                    "notes": "Context label only; no promoter choice is made by the helper.",
                }
            ],
            "insert": [
                {
                    "recorded_value": "sample-enzyme-1 insert label",
                    "review_status": "needs source",
                    "manual_follow_up": "Manual follow-up: record insert source/provenance and reviewer note.",
            "notes": "Insert label only; no final vector sequence is assembled.",
                }
            ],
            "terminator": [
                {
                    "recorded_value": "Terminator / PolyA context not yet recorded",
                    "review_status": "missing",
                    "manual_follow_up": "Manual follow-up: record terminator or PolyA documentation context if relevant.",
                    "notes": "Missing context is visible as a documentation follow-up item.",
                }
            ],
        },
        sequence_basic_checks=[
            {
                "check_name": "Sequence Basic Checks",
                "recorded_value": "No sequence body supplied in this read-only sample.",
                "review_status": "not assessed",
                "gap_or_follow_up": "Manual follow-up: review read-only sequence checks after a source-backed sequence is recorded.",
                "notes": "No sequence rewriting, no final vector sequence is assembled, and no codon-rewritten output is produced.",
            }
        ],
        gap_follow_up_records=[
            {
                "section": "Sample walkthrough source/provenance gap",
                "recorded_value": "Source/provenance incomplete",
                "review_status": "needs source",
                "manual_follow_up": "Manual follow-up: collect target, host, component, and vector/backbone source notes in existing review surfaces.",
            },
            {
                "section": "Package preview boundary",
                "recorded_value": "Read-only preview",
                "review_status": "needs review",
                "manual_follow_up": "Manual follow-up: explain that the preview is for documentation review and not experimental output.",
            },
        ],
    )

    return {
        "title": SAMPLE_WALKTHROUGH_TITLE,
        "start_here": "Start in Expression Wizard with one target gene / CDS / protein record.",
        "recorded_context": [
            "One sample target label for a single-gene / single-protein / single-enzyme record.",
            "Host, promoter, insert, and vector/backbone labels as user-recorded context only.",
            "Read-only package identity, MD5, cassette slot rows, and manual follow-up rows.",
        ],
        "source_provenance_gaps": [
            "Target sequence source/provenance is not recorded.",
            "Host context source/provenance is not recorded.",
            "Promoter, insert, and vector/backbone source/provenance need manual review notes.",
        ],
        "manual_follow_up": [
            "Record source/provenance notes in the existing review surfaces.",
            "Review missing cassette slots before using the preview in a handoff discussion.",
            "Use the package preview as read-only documentation review, not as experimental output.",
        ],
        "boundary_note": SAMPLE_BOUNDARY_NOTE,
        "preview": preview,
        "markdown": format_expression_vector_design_package_preview_markdown(preview),
    }
