from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.plant_design_review_package_service import build_plant_design_review_package
from services.project_review_report_service import build_project_review_report


def _assert_md5(value: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{32}", value)


def test_plant_design_review_package_identity_and_sections_are_bounded() -> None:
    package = build_plant_design_review_package(
        project={
            "id": 310,
            "name": "Rice albumin review context",
            "target_product": "rice albumin documentation target",
            "host": "Oryza sativa",
            "target_tissue": "seed documentation context",
            "expression_mode": "plant molecular farming context",
            "transformation_context": "recorded documentation context only",
            "manual_follow_up": "Review source/provenance records.",
        },
        construct_documentation={
            "cassette_rows": [
                {
                    "cassette_label": "cassette documentation row",
                    "promoter_label": "seed promoter documentation record",
                    "gene_label": "albumin CDS record",
                    "terminator_label": "terminator documentation record",
                }
            ],
            "cassette_part_rows": [
                {"part_role": "5' UTR", "part_label": "UTR documentation row"},
                {"part_role": "signal peptide", "part_label": "signal peptide documentation row"},
                {"part_role": "selectable marker", "part_label": "marker documentation row"},
                {"part_role": "vector backbone", "part_label": "backbone documentation row"},
            ],
            "linked_gene_rows": [
                {
                    "gene_label": "albumin CDS",
                    "gene_reference": "local source record",
                    "source_reference": "source review needed",
                }
            ],
            "construct_component_gap_queue": [{"Issue type": "Source/provenance review"}],
        },
        linked_catalog_assets={
            "total_linked_assets": 2,
            "linked_plant_promoter_count": 1,
            "missing_source_or_review_metadata_count": 1,
        },
        generated_at="2026-06-30T12:34:56+00:00",
    )

    identity = package["identity"]
    _assert_md5(identity["md5_checksum"])
    assert identity["package_type"] == "Plant Design Review Package"
    assert identity["project_direction"] == "Plant recombinant protein / molecular farming"
    assert identity["report_scope"] == "Documentation-only pre-experiment design review"
    assert identity["snapshot_id"] == "BDS-PLANT-R310-20260630-123456"
    assert identity["qr_payload"] == (
        "BioDesignStudioPlant|PlantDesignReviewPackage|"
        f"snapshot={identity['snapshot_id']}|md5={identity['md5_checksum']}"
    )

    titles = {section["title"] for section in package["sections"]}
    for expected in [
        "Project direction",
        "Target product / protein",
        "Plant species / host context",
        "Target tissue / organ / expression compartment",
        "Expression mode",
        "Gene / CDS source provenance",
        "Plant promoter context",
        "5' UTR / Kozak-like context if applicable",
        "Signal peptide / transit peptide / subcellular targeting if applicable",
        "Terminator",
        "Selectable marker / reporter",
        "Vector / backbone context",
        "Transformation context as documentation-only context",
        "Component source / provenance review",
        "Evidence / provenance gaps",
        "Manual follow-up",
        "Report handoff notes",
    ]:
        assert expected in titles

    combined = f"{package}".lower()
    for expected in [
        "qr/md5 verifies only the report/package snapshot identity",
        "qr/md5 does not validate construct readiness",
        "qr/md5 does not validate plant lines",
        "qr/md5 does not prove biological function",
        "qr/md5 does not predict yield",
        "qr/md5 does not certify experiment success",
    ]:
        assert expected in combined
    for forbidden in [
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
    ]:
        assert forbidden not in combined


def test_plant_design_review_package_includes_documentation_review_summary_readback() -> None:
    package = build_plant_design_review_package(
        project={"id": 311, "name": "Summary reuse report"},
        construct_documentation={
            "construct_component_rows": [
                {"component_label": "Promoter row"},
                {"component_label": "CDS row"},
            ],
            "construct_component_review_summary": {
                "total_component_rows": 2,
                "rows_with_source_reference_context": 1,
                "rows_needing_manual_follow_up": 1,
            },
            "construct_component_manual_follow_up_readback": {
                "total_manual_follow_up_items": 1,
            },
        },
    )

    summary = package["documentation_review_summary"]
    action_panel = package["review_action_panel"]
    markdown = build_plant_design_review_package.__globals__["format_plant_design_review_package_markdown"](package)

    assert summary["review_summary_status"] == "Needs manual follow-up"
    assert summary["documented_slots_count"] == 2
    assert summary["missing_slots_count"] == 1
    assert summary["manual_follow_up_count"] == 1
    assert "### Documentation review summary" in markdown
    assert "- Review status: Needs manual follow-up" in markdown
    assert "- Documented slots: 2" in markdown
    assert "- Missing slots: 1" in markdown
    assert "- Manual follow-up: 1" in markdown
    assert "- Source/provenance coverage: 1" in markdown
    assert "Review-only documentation handoff review; not a downstream-use assessment." in markdown
    assert action_panel["summary"]["row_count"] == 4
    assert [row["label"] for row in action_panel["rows"]] == [
        "Missing documentation",
        "Needs manual follow-up",
        "Source/provenance review",
        "Boundary note",
    ]
    assert "### Review action panel" in markdown
    assert "| Action row | Status | Count | Review action | Source | Boundary |" in markdown
    assert "Missing documentation" in markdown
    assert "Needs manual follow-up" in markdown
    assert "Source/provenance review" in markdown
    assert "Review actions are documentation follow-up cues only" in markdown


def test_project_review_report_includes_plant_design_review_package_markdown(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [
                    {
                        "construct_label": "plant construct documentation record",
                        "source_reference": "local source record",
                    }
                ],
                "cassette_rows": [
                    {
                        "promoter_label": "plant promoter documentation row",
                        "gene_label": "albumin CDS",
                        "terminator_label": "plant terminator documentation row",
                    }
                ],
                "cassette_part_rows": [
                    {"part_role": "signal peptide", "part_label": "signal peptide row"},
                    {"part_role": "reporter", "part_label": "reporter row"},
                ],
                "linked_gene_rows": [{"gene_label": "albumin CDS", "source_reference": "source review needed"}],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "construct_component_rows": [],
                "construct_component_gap_queue": [],
                "part_role_counts": {},
                "supported_component_vocabulary": [],
            }
        ],
    )

    report = build_project_review_report(
        {
            "id": 310,
            "name": "Plant package report",
            "target_product": "albumin documentation target",
            "host": "Nicotiana benthamiana",
            "target_tissue": "leaf documentation context",
            "expression_mode": "transient expression documentation context",
        }
    )

    markdown = report["markdown"]
    draft_markdown = report["detailed_documentation_report_draft"]["markdown"]
    identity = report["plant_design_review_package"]["identity"]
    _assert_md5(identity["md5_checksum"])
    for text in [
        "Plant Design Review Package",
        "Report Identity / Verification",
        "MD5 checksum",
        "QR payload",
        "BioDesignStudioPlant",
        "PlantDesignReviewPackage",
        "Target product / protein",
        "Plant species / host context",
        "Target tissue / organ / expression compartment",
        "Expression mode",
        "Gene / CDS source provenance",
        "Plant promoter context",
        "Signal peptide / transit peptide / subcellular targeting if applicable",
        "Selectable marker / reporter",
        "Vector / backbone context",
        "Transformation context as documentation-only context",
        "Evidence / provenance gaps",
        "Manual follow-up",
        "Review action panel",
        "Missing documentation",
        "Needs manual follow-up",
        "Source/provenance review",
        "QR/MD5 verifies only the report/package snapshot identity.",
        "QR/MD5 does not prove biological function.",
    ]:
        assert text in markdown
        assert text in draft_markdown
