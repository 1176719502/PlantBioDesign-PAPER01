from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_vector_design_package_adapter import build_expression_vector_design_package_preview
from services.expression_vector_design_package_markdown_formatter import (
    format_expression_vector_design_package_preview_markdown,
)


def _sample_preview() -> dict:
    return build_expression_vector_design_package_preview(
        package_title="crtI expression vector documentation preview",
        source_commit_or_version="r270-test",
        target_record={
            "target_name": "crtI",
            "cds_or_protein_value": "crtI CDS record",
            "source_reference": "Target source notebook",
            "review_status": "documented",
        },
        sequence_source_record={
            "source_reference": "Sequence provenance note",
            "review_status": "documented",
        },
        host_record={
            "host_system": "E. coli BL21(DE3) documentation context",
            "source_reference": "Host notebook",
            "review_status": "documented",
        },
        vector_backbone_record={
            "backbone_name": "pET backbone context",
            "source_reference": "Backbone source note",
            "review_status": "documented",
        },
        cassette_rows=[
            {
                "promoter_label": "T7 promoter context",
                "gene_label": "crtI insert context",
                "terminator_label": "T7 terminator context",
                "source_reference": "Cassette notebook",
                "review_status": "documented",
            }
        ],
        cassette_part_rows=[
            {
                "part_role": "tag",
                "part_label": "His6 tag context",
                "source_reference": "Tag source note",
                "review_status": "documented",
            }
        ],
        sequence_basic_checks=[
            {
                "check_name": "Length",
                "recorded_value": "1482 bp",
                "review_status": "documented",
                "notes": "Read-only sequence check row.",
            }
        ],
        gap_follow_up_records=[
            {
                "section": "Manual source review",
                "recorded_value": "Backbone citation needs reviewer initials",
                "review_status": "needs review",
                "manual_follow_up": "Add reviewer initials in the existing review record.",
            }
        ],
    )


def test_formatter_renders_all_major_sections() -> None:
    markdown = format_expression_vector_design_package_preview_markdown(_sample_preview())

    expected_sections = [
        "# crtI expression vector documentation preview",
        "## Package Identity",
        "## Target Gene / CDS / Protein",
        "## Host / Expression System",
        "## Expression Cassette Slot Review",
        "## Vector / Backbone",
        "## Sequence Basic Checks",
        "## Source / Provenance Summary",
        "## Gap / Manual Follow-up Review",
        "## Package Limitations",
    ]

    for section in expected_sections:
        assert section in markdown


def test_formatter_includes_cassette_slot_rows_from_adapter() -> None:
    markdown = format_expression_vector_design_package_preview_markdown(_sample_preview())

    assert "| Slot | Group | Recorded value | Source / provenance | Review status | Gap / follow-up |" in markdown
    assert "T7 promoter context" in markdown
    assert "crtI insert context" in markdown
    assert "T7 terminator context" in markdown
    assert "His6 tag context" in markdown
    assert "Expression cassette slot rows" in markdown


def test_formatter_renders_source_provenance_and_manual_follow_up_gaps() -> None:
    preview = build_expression_vector_design_package_preview(
        target_record={
            "target_name": "Target from local note",
            "review_status": "documented",
        },
        cassette_part_rows=[
            {
                "part_role": "promoter",
                "part_label": "Promoter label without source",
                "review_status": "documented",
            }
        ],
        gap_follow_up_records=[
            {
                "section": "Source review",
                "recorded_value": "Promoter source missing",
                "review_status": "needs review",
                "manual_follow_up": "Record source/provenance context in the existing review surface.",
            }
        ],
    )
    markdown = format_expression_vector_design_package_preview_markdown(preview)

    assert "Needs source" in markdown or "needs source" in markdown
    assert "Promoter label without source" in markdown
    assert "Record source/provenance context" in markdown
    assert "## Source / Provenance Summary" in markdown
    assert "## Gap / Manual Follow-up Review" in markdown


def test_formatter_includes_deterministic_package_identity_and_md5() -> None:
    preview = _sample_preview()
    markdown = format_expression_vector_design_package_preview_markdown(preview)
    md5 = preview["package_identity"]["md5"]

    assert "| Package ID | md5:" in markdown
    assert f"| MD5 | {md5} |" in markdown
    assert re.search(r"\b[a-f0-9]{32}\b", markdown)
    assert "r270-test" in markdown


def test_formatter_handles_minimal_empty_preview_safely() -> None:
    markdown = format_expression_vector_design_package_preview_markdown({})

    assert "# Expression Vector Design Package Preview" in markdown
    assert "Missing" in markdown
    assert "Needs source" in markdown
    assert "Needs review" in markdown
    assert "Not provided" in markdown
    assert "## Package Limitations" in markdown


def test_formatter_does_not_emit_unsafe_positive_claims() -> None:
    markdown = format_expression_vector_design_package_preview_markdown(_sample_preview()).casefold()
    forbidden = [
        "recommended",
        "best promoter",
        "best host",
        "best vector",
        "validated construct",
        "build-ready",
        "ready-to-clone",
        "ready for execution",
        "wet-lab protocol",
        "cloning protocol",
        "yield prediction",
        "experimentally validated",
        "experiment-ready",
        "production-ready",
        "final vector generated",
        "generated final vector",
    ]

    assert [phrase for phrase in forbidden if phrase in markdown] == []


def test_formatter_output_stays_documentation_only_and_read_only() -> None:
    markdown = format_expression_vector_design_package_preview_markdown(_sample_preview()).casefold()

    assert "documentation-only" in markdown
    assert "read-only" in markdown
    assert "human review" in markdown
    assert "does not generate a final vector sequence" in markdown
    assert "does not provide protocol steps" in markdown
