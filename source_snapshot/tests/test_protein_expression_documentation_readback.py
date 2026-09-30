# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_review_report_service import build_project_review_report
from tests.helpers.fake_streamlit import FakeStreamlit
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path
import views.pathway_workspace_sections.project_documentation_package_section as package_section


FORBIDDEN_PROTEIN_SECTION_TERMS = [
    "recommend",
    "recommended",
    "optimize",
    "optimized",
    "optimization",
    "validate",
    "validated",
    "validation",
    "ready",
    "readiness",
    "best",
    "preferred",
    "strongest",
    "high-expression",
    "yield",
    "productivity",
    "titer",
    "secretion success",
    "folding success",
    "glycosylation quality",
]


def _section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker)
    remaining = markdown[start + len(marker):]
    next_heading = remaining.find("\n## ")
    return marker + (remaining[:next_heading] if next_heading != -1 else remaining)


def _assert_no_forbidden_terms(text: str) -> None:
    lowered = text.lower()
    found: list[str] = []
    for term in FORBIDDEN_PROTEIN_SECTION_TERMS:
        pattern = re.escape(term)
        if term.replace("-", "").replace(" ", "").isalpha():
            pattern = rf"\b{pattern}\b"
        if re.search(pattern, lowered):
            found.append(term)
    assert found == []


def _hsa_report_view() -> dict:
    return {
        "construct_profile_rows": [
            {
                "construct_id": "construct-hsa",
                "construct_label": "HSA documentation construct",
                "construct_type": "single-protein expression documentation record",
                "plasmid_backbone": "Existing vector/backbone note from construct profile",
                "host_context_note": "Rice endosperm host context retained for documentation review.",
                "source_reference": "HSA construct notebook",
                "provenance_note": "HSA construct provenance note.",
                "review_status": "documentation review pending",
                "documentation_scope_note": "Protein expression documentation context.",
            }
        ],
        "cassette_rows": [
            {
                "cassette_id": "cassette-hsa",
                "construct_id": "construct-hsa",
                "cassette_label": "HSA expression cassette",
                "cassette_role": "protein expression cassette record",
                "cassette_order": 1,
                "promoter_label": "Seed promoter documentation row",
                "gene_label": "ALB / HSA",
                "terminator_label": "Terminator documentation row",
                "source_reference": "HSA cassette notebook",
                "provenance_note": "HSA cassette provenance note.",
            }
        ],
        "cassette_part_rows": [
            {
                "cassette_id": "cassette-hsa",
                "cassette_label": "HSA expression cassette",
                "part_order": 1,
                "part_role": "promoter",
                "part_label": "Seed promoter documentation row",
                "part_reference": "promoter-ref",
                "source_reference": "Promoter notebook",
                "source_catalog": "Plant Promoter Catalog",
                "source_record_label": "Seed promoter catalog context",
                "evidence_context_note": "Promoter source context retained for documentation review.",
                "provenance_note": "Promoter provenance note.",
            },
            {
                "cassette_id": "cassette-hsa",
                "cassette_label": "HSA expression cassette",
                "part_order": 2,
                "part_role": "cds",
                "part_label": "HSA CDS",
                "part_reference": "ALB reference",
                "source_reference": "CDS notebook",
                "source_catalog": "",
                "source_record_label": "ALB source context",
                "evidence_context_note": "CDS context retained for documentation review.",
                "provenance_note": "CDS provenance note.",
            },
            {
                "cassette_id": "cassette-hsa",
                "cassette_label": "HSA expression cassette",
                "part_order": 3,
                "part_role": "other",
                "part_label": "Native HSA signal peptide context",
                "part_reference": "signal context note",
                "source_reference": "Signal context notebook",
                "source_catalog": "",
                "source_record_label": "",
                "evidence_context_note": "Signal context retained for documentation review.",
                "provenance_note": "Signal provenance note.",
            },
            {
                "cassette_id": "cassette-hsa",
                "cassette_label": "HSA expression cassette",
                "part_order": 4,
                "part_role": "terminator",
                "part_label": "Terminator documentation row",
                "part_reference": "terminator-ref",
                "source_reference": "Terminator notebook",
                "source_catalog": "",
                "source_record_label": "",
                "evidence_context_note": "Terminator context retained for documentation review.",
                "provenance_note": "Terminator provenance note.",
            },
        ],
        "linked_gene_rows": [
            {
                "gene_label": "HSA",
                "gene_reference": "ALB gene documentation reference",
                "source_reference": "Gene source notebook",
                "provenance_note": "Gene provenance note.",
            }
        ],
        "linked_pathway_step_rows": [],
        "project_link_rows": [],
        "review_gap_rows": [
            {
                "Gap type": "catalog reference context",
                "Label": "Seed promoter catalog context",
                "Review gap note": "Source metadata needs documentation review.",
            }
        ],
        "part_role_counts": {"promoter": 1, "cds": 1, "other": 1, "terminator": 1},
        "supported_component_vocabulary": ["promoter", "coding sequence", "terminator", "other documented component"],
    }


def test_report_adds_protein_expression_readback_from_existing_construct_data(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [_hsa_report_view()],
    )
    monkeypatch.setattr(service.project_catalog_link_repo, "list_project_catalog_asset_links", lambda project_id: [])

    report = build_project_review_report(
        {
            "id": "project-hsa",
            "name": "Human serum albumin / HSA documentation project",
            "target_product": "Human serum albumin / HSA",
            "host": "Oryza sativa rice endosperm documentation context",
        }
    )

    readback = report["protein_expression_documentation_readback"]
    section = _section(report["markdown"], "Protein Expression Documentation Readback")

    assert readback["status"] == "AVAILABLE"
    assert readback["target_context"]["target_protein"] == "Human serum albumin / HSA"
    assert readback["target_context"]["linked_gene_context"] == "HSA"
    assert readback["target_context"]["cds_context"] == "HSA CDS"
    assert "HSA expression cassette" in section
    assert "Seed promoter documentation row" in section
    assert "Native HSA signal peptide context" in section
    assert "Protein expression documentation readback is documentation-only context for review and traceability." in section
    assert "pathway product" not in section.lower()
    assert "pathway design" not in section.lower()
    _assert_no_forbidden_terms(section)


def test_existing_pathway_report_summary_still_renders(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(service.project_catalog_link_repo, "list_project_catalog_asset_links", lambda project_id: [])

    report = build_project_review_report(
        {
            "id": "project-artemisia",
            "name": "Artemisinin precursor documentation project",
            "target_product": "Artemisinin precursor",
            "pathway_steps": [
                {
                    "id": "step-ads",
                    "step_order": 1,
                    "step_name": "ADS documentation step",
                    "organism_source": "Artemisia annua source context",
                    "enzyme_name": "ADS",
                    "gene_name": "ADS",
                    "metabolite": "amorpha-4,11-diene",
                }
            ],
        }
    )

    assert "## Pathway steps" in report["markdown"]
    assert "ADS documentation step" in report["markdown"]
    assert report["pathway_steps_summary"]["step_count"] == 1
    assert report["protein_expression_documentation_readback"]["status"] == "NOT_AVAILABLE"


def _use_temp_db(monkeypatch) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r154_protein_expression_readback_dbs",
        "protein_expression_package.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(package_section, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.download_button_calls]
        + [call["label"] for call in fake_st.metric_calls]
        + [call["label"] for call in fake_st.expander_calls]
    )


def _seed_hsa_package_records() -> None:
    profile = repo.create_construct_profile(
        construct_id="construct-hsa",
        construct_label="HSA documentation construct",
        construct_type="single-protein expression documentation record",
        plasmid_backbone="Existing vector/backbone note from construct profile",
        host_context_note="Rice host context retained for documentation review.",
        source_reference="HSA construct notebook",
        provenance_note="HSA construct provenance note.",
        review_status="documentation review pending",
        documentation_scope_note="Protein expression documentation context.",
    )
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-hsa",
        cassette_label="HSA expression cassette",
        cassette_role="protein expression cassette record",
        cassette_order=1,
        promoter_label="Seed promoter documentation row",
        gene_label="HSA",
        terminator_label="Terminator documentation row",
        source_reference="HSA cassette notebook",
        provenance_note="HSA cassette provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Seed promoter documentation row",
        source_reference="Promoter notebook",
        source_catalog="Plant Promoter Catalog",
        source_record_label="Seed promoter catalog context",
        evidence_context_note="Promoter source context retained for documentation review.",
        provenance_note="Promoter provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=2,
        part_role="cds",
        part_label="HSA CDS",
        part_reference="ALB reference",
        source_reference="CDS notebook",
        source_record_label="ALB source context",
        evidence_context_note="CDS context retained for documentation review.",
        provenance_note="CDS provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=3,
        part_role="other",
        part_label="Native HSA signal peptide context",
        part_reference="signal context note",
        source_reference="Signal context notebook",
        evidence_context_note="Signal context retained for documentation review.",
        provenance_note="Signal provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=4,
        part_role="terminator",
        part_label="Terminator documentation row",
        source_reference="Terminator notebook",
        evidence_context_note="Terminator context retained for documentation review.",
        provenance_note="Terminator provenance note.",
    )
    repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="HSA",
        gene_reference="ALB gene documentation reference",
        source_reference="Gene source notebook",
        provenance_note="Gene provenance note.",
    )
    repo.create_construct_project_link(
        project_id="project-hsa",
        construct_id=profile["construct_id"],
        link_label="HSA project construct context",
        link_note="Connects HSA construct documentation to the local project record.",
        source_context="Protein expression documentation context.",
        curation_status="documentation review pending",
        review_note="Review source context before sharing documentation.",
    )


def test_package_panel_adds_ui_only_protein_expression_readback_without_schema_change(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_hsa_package_records()
    fake_st = _install_fake_streamlit(monkeypatch)

    package_section.render_project_documentation_package_export_panel(
        {
            "id": "project-hsa",
            "name": "Human serum albumin / HSA documentation project",
            "target_product": "Human serum albumin / HSA",
            "host": "Oryza sativa rice endosperm documentation context",
        }
    )

    rendered = _rendered_text(fake_st)
    assert "Protein Expression Documentation Readback" in rendered
    assert "Protein expression package readback is documentation-only context for review and traceability." in rendered
    assert "Target protein / linked gene / CDS context:" in rendered
    assert "Human serum albumin / HSA" in rendered
    assert "HSA CDS" in rendered
    assert "Native HSA signal peptide context" in rendered
    assert "Single-protein records are presented as protein expression documentation context." in rendered
    assert "pathway product" not in rendered.lower()

    json_call = next(call for call in fake_st.download_button_calls if call["label"] == "Export Documentation Package (.json)")
    payload = json.loads(json_call["data"])
    assert set(payload.keys()) == {
        "manifest",
        "package_metadata",
        "project_metadata",
        "project_construct_links",
        "project_catalog_asset_links",
        "construct_profiles",
        "expression_cassettes",
        "cassette_parts",
        "linked_genes",
        "linked_pathway_steps",
        "review_gaps",
        "report_references",
        "documentation_only_boundary",
        "known_limitations",
        "integrity_summary",
    }
    assert "protein_expression_documentation_readback" not in payload
