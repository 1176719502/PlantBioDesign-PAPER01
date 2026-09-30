# -*- coding: utf-8 -*-
"""V2.6-R16 read-only multi-gene construct presenter tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_presenter as presenter


def _profile(**overrides) -> dict:
    data = {
        "construct_id": "construct-001",
        "construct_label": "Carotenoid documentation construct",
        "construct_type": "multi-cassette plasmid record",
        "plasmid_backbone": "pBIO-Doc-01",
        "host_context_note": "Host context tracked as documentation only.",
        "source_reference": "Notebook-EC-12",
        "provenance_note": "Source notes collected for traceability review.",
        "review_status": "documentation review pending",
        "documentation_scope_note": "Documentation-only construct record.",
    }
    data.update(overrides)
    return data


def _cassette(**overrides) -> dict:
    data = {
        "cassette_id": "cassette-001",
        "construct_id": "construct-001",
        "cassette_label": "Cassette A",
        "cassette_role": "expression cassette",
        "cassette_order": 1,
        "promoter_label": "P-Doc-A",
        "gene_label": "crtI",
        "terminator_label": "T-Doc-A",
        "source_reference": "Notebook-1",
        "provenance_note": "Traceability note 1",
    }
    data.update(overrides)
    return data


def _part(**overrides) -> dict:
    data = {
        "cassette_id": "cassette-001",
        "part_order": 1,
        "part_role": "promoter",
        "part_label": "P-Doc-A",
        "part_reference": "part-ref-1",
        "source_reference": "source-1",
        "source_catalog": "Plant Promoter Catalog",
        "source_record_id": "plant-promoter-001",
        "source_record_label": "Maize promoter source record",
        "evidence_context_note": "monocot | Zea mays (maize) | root | literature-reported | Fixture source",
        "provenance_note": "note-1",
    }
    data.update(overrides)
    return data


def _gene_link(**overrides) -> dict:
    data = {
        "gene_label": "crtI",
        "gene_reference": "crtI-ref",
        "source_reference": "Pathway notebook",
        "provenance_note": "Linked from project notes.",
    }
    data.update(overrides)
    return data


def _pathway_link(**overrides) -> dict:
    data = {
        "pathway_step_id": "step-1",
        "pathway_step_label": "Precursor supply",
        "source_reference": "Project map",
        "provenance_note": "Linked from pathway review notes.",
    }
    data.update(overrides)
    return data


def _patch_repo(
    monkeypatch,
    *,
    profiles=None,
    profile=None,
    cassettes=None,
    parts_by_cassette=None,
    gene_links=None,
    pathway_links=None,
    project_links=None,
):
    monkeypatch.setattr(presenter.repo, "list_construct_profiles", lambda: profiles or [])
    monkeypatch.setattr(presenter.repo, "list_construct_profiles_for_project", lambda project_id: profiles or [])
    monkeypatch.setattr(presenter.repo, "get_construct_profile", lambda construct_id: profile or {})
    monkeypatch.setattr(presenter.repo, "list_construct_cassettes", lambda construct_id: cassettes or [])
    monkeypatch.setattr(
        presenter.repo,
        "list_construct_cassette_parts",
        lambda cassette_id: (parts_by_cassette or {}).get(cassette_id, []),
    )
    monkeypatch.setattr(presenter.repo, "list_construct_gene_links", lambda construct_id: gene_links or [])
    monkeypatch.setattr(
        presenter.repo,
        "list_construct_pathway_step_links",
        lambda construct_id: pathway_links or [],
    )
    monkeypatch.setattr(
        presenter.repo,
        "list_construct_project_links",
        lambda **kwargs: project_links or [],
    )


def test_presenter_empty_state(monkeypatch):
    _patch_repo(monkeypatch, profiles=[])

    view_model = presenter.build_expression_construct_presenter()

    assert view_model["summary_counts"] == {
        "construct_profile_count": 0,
        "cassette_count": 0,
        "cassette_part_count": 0,
        "gene_link_count": 0,
        "pathway_step_link_count": 0,
        "project_link_count": 0,
        "review_gap_count": 0,
    }
    assert view_model["construct_profile_rows"] == []
    assert view_model["review_gap_rows"] == []
    assert view_model["boundary_copy"] == presenter.BOUNDARY_COPY


def test_presenter_summary_counts_and_rows(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile(), _profile(construct_id="construct-002", construct_label="Empty documentation construct")],
        profile=_profile(),
        cassettes=[_cassette(), _cassette(cassette_id="cassette-002", cassette_label="Cassette B", cassette_order=2, gene_label="crtB")],
        parts_by_cassette={
            "cassette-001": [_part(), _part(part_order=2, part_role="cds", part_label="crtI CDS")],
            "cassette-002": [_part(cassette_id="cassette-002", part_order=1, part_label="P-Doc-B")],
        },
        gene_links=[_gene_link(), _gene_link(gene_label="crtB", gene_reference="crtB-ref")],
        pathway_links=[_pathway_link(), _pathway_link(pathway_step_id="step-2", pathway_step_label="Cyclization")],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["summary_counts"] == {
        "construct_profile_count": 2,
        "cassette_count": 2,
        "cassette_part_count": 3,
        "gene_link_count": 2,
        "pathway_step_link_count": 2,
        "project_link_count": 0,
        "review_gap_count": 0,
    }
    assert [row["cassette_label"] for row in view_model["cassette_rows"]] == ["Cassette A", "Cassette B"]
    assert [row["part_role"] for row in view_model["cassette_part_rows"]] == ["promoter", "cds", "promoter"]
    assert view_model["cassette_part_rows"][0]["source_record_label"] == "Maize promoter source record"
    assert "Fixture source" in view_model["cassette_part_rows"][0]["evidence_context_note"]
    assert view_model["construct_component_rows"][0]["component_label"] == "P-Doc-A"
    assert view_model["construct_component_rows"][0]["component_category"] == "promoter"
    assert view_model["construct_component_rows"][0]["component_reference_label"] == "Maize promoter source record"
    assert view_model["construct_component_rows"][0]["sequence_availability_status"] == presenter.SEQUENCE_STATUS_LINKED_REFERENCE
    assert "source catalog: Plant Promoter Catalog" in view_model["construct_component_rows"][0]["conservation_review_evidence"]
    assert view_model["construct_component_rows"][0]["conservation_follow_up_cue"] == (
        presenter.CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS
    )
    assert view_model["construct_component_rows"][0]["review_metadata_status"] == presenter.COMPONENT_METADATA_RECORDED_STATUS
    assert view_model["construct_component_review_summary"] == {
        "total_component_rows": 3,
        "rows_with_source_reference_context": 3,
        "rows_missing_source_reference_context": 0,
        "rows_with_sequence_availability_note": 3,
        "rows_with_conservation_review_context": 3,
        "rows_needing_conservation_follow_up": 0,
        "rows_with_review_metadata_status": 3,
        "rows_with_review_note": 3,
        "rows_needing_manual_follow_up": 0,
    }
    assert view_model["construct_component_gap_queue"] == []
    assert view_model["part_role_counts"] == {"promoter": 2, "cds": 1}
    assert view_model["supported_component_vocabulary"] == [
        "promoter",
        "5' UTR",
        "RBS",
        "signal peptide",
        "coding sequence",
        "terminator",
        "other documented component",
    ]


def test_presenter_builds_expression_construct_display_table_rows() -> None:
    profile_rows = [
        _profile(
            host_context_note="Nicotiana benthamiana documentation context",
            documentation_scope_note="Local review note.",
        )
    ]
    cassette_rows = [_cassette()]
    part_rows = [_part()]
    gene_rows = [_gene_link()]
    pathway_rows = [_pathway_link(construct_id="construct-001")]
    project_link_rows = [
        {
            "project_id": "project-001",
            "construct_id": "construct-001",
            "construct_label": "Carotenoid documentation construct",
            "link_label": "Pathway construct context",
            "link_note": "Project documentation link.",
            "source_context": "Local project note",
            "curation_status": "draft documentation review",
            "review_note": "Traceability review note.",
        }
    ]
    gap_rows = [{"Gap type": "cassette parts", "Label": "Cassette A", "Review gap note": "No ordered part rows recorded."}]

    assert list(presenter.construct_profile_table_rows(profile_rows)[0]) == presenter.TABLE_COLUMNS
    assert presenter.construct_profile_table_rows(profile_rows)[0] == {
        "Construct label": "Carotenoid documentation construct",
        "Construct type": "multi-cassette plasmid record",
        "Organism / species context": "Nicotiana benthamiana documentation context",
        "Curation status": "documentation review pending",
        "Source / provenance": "Notebook-EC-12 / Source notes collected for traceability review.",
        "Review note": "Local review note.",
    }
    assert presenter.cassette_table_rows(cassette_rows)[0] == {
        "Cassette label": "Cassette A",
        "Construct label / construct id": "construct-001",
        "Cassette order": "1",
        "Cassette type": "expression cassette",
        "Curation status": "Notebook-1",
        "Review note": "Traceability note 1",
    }
    assert presenter.cassette_part_table_rows(part_rows)[0]["Promoter source record"] == (
        "Plant Promoter Catalog / Maize promoter source record / plant-promoter-001"
    )
    component_rows = [
        {
            "component_label": "P-Doc-A",
            "component_category": "promoter",
            "component_reference_label": "Maize promoter source record",
            "sequence_availability_status": presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
            "conservation_review_evidence": (
                "source catalog: Plant Promoter Catalog; sequence/source record: Maize promoter source record; "
                "source context: source-1; component reference: part-ref-1; literature/database or conservation "
                "note: monocot | Zea mays (maize) | root | literature-reported | Fixture source; manual "
                "reviewer note: note-1"
            ),
            "conservation_follow_up_cue": presenter.CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS,
            "review_metadata_status": presenter.COMPONENT_METADATA_RECORDED_STATUS,
            "review_note": "Source notes collected for traceability review.",
            "cassette_label": "Cassette A",
        },
        {
            "component_label": "",
            "component_category": "",
            "component_reference_label": "",
            "sequence_availability_status": "",
            "review_metadata_status": "",
            "review_note": "",
            "cassette_label": "",
        },
    ]
    assert list(presenter.construct_component_table_rows(component_rows)[0]) == presenter.COMPONENT_COLUMNS
    assert presenter.construct_component_table_rows(component_rows)[0] == {
        "Component label": "P-Doc-A",
        "Component category": "promoter",
        "Cassette label": "Cassette A",
        "Source/reference context": "Maize promoter source record",
        "Sequence availability note": presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
        "Conservation review evidence": (
            "source catalog: Plant Promoter Catalog; sequence/source record: Maize promoter source record; "
            "source context: source-1; component reference: part-ref-1; literature/database or conservation "
            "note: monocot | Zea mays (maize) | root | literature-reported | Fixture source; manual "
            "reviewer note: note-1"
        ),
        "Conservation follow-up cue": presenter.CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS,
        "Record review status": presenter.COMPONENT_METADATA_RECORDED_STATUS,
        "Review note": "Source notes collected for traceability review.",
    }
    assert presenter.construct_component_table_rows(component_rows)[1] == {
        "Component label": presenter.NO_PART_LABEL,
        "Component category": presenter.NO_COMPONENT_CATEGORY_LABEL,
        "Cassette label": presenter.DEFAULT_CASSETTE_LABEL,
        "Source/reference context": presenter.NO_COMPONENT_REFERENCE_LABEL,
        "Sequence availability note": presenter.SEQUENCE_STATUS_NOT_RECORDED,
        "Conservation review evidence": presenter.NO_CONSERVATION_EVIDENCE_LABEL,
        "Conservation follow-up cue": presenter.CONSERVATION_REVIEW_NEEDED_STATUS,
        "Record review status": presenter.COMPONENT_METADATA_GAP_STATUS,
        "Review note": presenter.NO_REVIEW_NOTE_LABEL,
    }
    queue_rows = [
        {
            "Construct label": "Carotenoid documentation construct",
            "Cassette label": "Cassette A",
            "Component label": "P-Doc-A",
            "Component category": "promoter",
            "Issue type": "Missing source/reference context",
            "Issue detail": "No source note recorded.",
            "Manual follow-up note": "Add source context for documentation review.",
        }
    ]
    assert list(presenter.construct_component_gap_queue_table_rows(queue_rows)[0]) == presenter.COMPONENT_GAP_QUEUE_COLUMNS
    assert presenter.construct_component_gap_queue_table_rows(queue_rows)[0]["Issue type"] == "Missing source/reference context"
    assert presenter.linked_gene_table_rows(gene_rows)[0]["Gene reference"] == "crtI-ref"
    assert presenter.linked_pathway_step_table_rows(pathway_rows)[0]["Step label"] == "Precursor supply"
    assert presenter.project_link_table_rows(project_link_rows)[0]["Construct label / construct id"] == (
        "Carotenoid documentation construct / construct-001"
    )
    assert presenter.review_gap_table_rows(gap_rows)[0] == gap_rows[0]
    assert presenter.COMPONENT_REVIEW_SUMMARY_LABELS == {
        "total_component_rows": "Component rows reviewed",
        "rows_with_source_reference_context": "Source/reference context",
        "rows_missing_source_reference_context": "Missing source/reference context",
        "rows_with_sequence_availability_note": "Sequence availability note",
        "rows_with_conservation_review_context": "Conservation review context",
        "rows_needing_conservation_follow_up": "Conservation follow-up",
        "rows_with_review_metadata_status": "Record review status",
        "rows_with_review_note": "Review note context",
        "rows_needing_manual_follow_up": "Documentation follow-up",
    }


def test_presenter_display_filters_preserve_view_filter_behavior() -> None:
    profile_rows = [
        _profile(construct_id="construct-001", construct_type="type-a", review_status="status-a"),
        _profile(construct_id="construct-002", construct_label="Second construct", construct_type="type-b", review_status="status-b"),
    ]
    cassette_rows = [
        _cassette(cassette_id="cassette-001", construct_id="construct-001", cassette_label="Cassette A"),
        _cassette(cassette_id="cassette-002", construct_id="construct-002", cassette_label="Cassette B"),
    ]
    part_rows = [
        _part(cassette_id="cassette-001", part_label="Part A"),
        _part(cassette_id="cassette-002", part_label="Part B"),
    ]
    gene_rows = [_gene_link(construct_id="construct-001"), _gene_link(construct_id="construct-002", gene_label="crtB")]
    pathway_rows = [
        _pathway_link(construct_id="construct-001", pathway_step_id="step-1"),
        _pathway_link(construct_id="construct-002", pathway_step_id="step-2"),
    ]
    gap_rows = [{"Gap type": "review", "Label": "construct-001", "Review gap note": "Review gap remains visible."}]

    filtered = presenter.filter_expression_construct_display_rows(
        profile_rows,
        cassette_rows,
        part_rows,
        gene_rows,
        pathway_rows,
        gap_rows,
        construct_type="type-a",
        construct_status="status-a",
        cassette_label="Cassette A",
        pathway_ref="step-1",
    )

    filtered_profiles, filtered_cassettes, filtered_parts, filtered_genes, filtered_pathways, filtered_gaps = filtered
    assert [row["construct_id"] for row in filtered_profiles] == ["construct-001"]
    assert [row["cassette_id"] for row in filtered_cassettes] == ["cassette-001"]
    assert [row["part_label"] for row in filtered_parts] == ["Part A"]
    assert [row["construct_id"] for row in filtered_genes] == ["construct-001"]
    assert [row["pathway_step_id"] for row in filtered_pathways] == ["step-1"]
    assert filtered_gaps == gap_rows
    assert presenter.construct_type_options(profile_rows) == ["all", "type-a", "type-b"]
    assert presenter.construct_status_options(profile_rows) == ["all", "status-a", "status-b"]
    assert presenter.cassette_label_options(cassette_rows) == ["all", "Cassette A", "Cassette B"]
    assert presenter.pathway_reference_options(pathway_rows) == ["all", "step-1", "step-2"]


def test_presenter_report_views_returns_one_view_per_construct(monkeypatch):
    calls = []

    _patch_repo(
        monkeypatch,
        profiles=[
            _profile(construct_id="construct-001"),
            _profile(construct_id="construct-002", construct_label="Second construct"),
        ],
    )

    def _fake_presenter(construct_id, **kwargs):
        calls.append(construct_id)
        return {"construct_profile_rows": [{"construct_id": construct_id}]}

    monkeypatch.setattr(presenter, "build_expression_construct_presenter", _fake_presenter)

    views = presenter.build_expression_construct_report_views()

    assert calls == ["construct-001", "construct-002"]
    assert [view["construct_profile_rows"][0]["construct_id"] for view in views] == [
        "construct-001",
        "construct-002",
    ]


def test_presenter_reports_missing_construct_id_defensively(monkeypatch):
    _patch_repo(monkeypatch, profiles=[_profile()])

    view_model = presenter.build_expression_construct_presenter("missing-construct")

    assert view_model["construct_profile_rows"] == []
    assert view_model["cassette_rows"] == []
    assert view_model["linked_gene_rows"] == []
    assert view_model["linked_pathway_step_rows"] == []
    assert [row["Gap type"] for row in view_model["review_gap_rows"]] == [
        "construct profile",
        "cassettes",
        "gene links",
        "pathway step links",
    ]


def test_presenter_reports_review_gaps_for_missing_parts_and_links(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={"cassette-001": []},
        gene_links=[],
        pathway_links=[],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["summary_counts"]["review_gap_count"] == 3
    assert [row["Gap type"] for row in view_model["review_gap_rows"]] == [
        "cassette parts",
        "gene links",
        "pathway step links",
    ]


def test_presenter_uses_fallback_labels_for_missing_source_and_provenance(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile(source_reference="", provenance_note="")],
        profile=_profile(source_reference="", provenance_note=""),
        cassettes=[_cassette(source_reference="", provenance_note="")],
        parts_by_cassette={
            "cassette-001": [
                _part(
                    part_label="",
                    part_reference="",
                    source_reference="",
                    source_catalog="",
                    source_record_id="",
                    source_record_label="",
                    evidence_context_note="",
                    provenance_note="",
                )
            ]
        },
        gene_links=[_gene_link(gene_label="", source_reference="", provenance_note="")],
        pathway_links=[_pathway_link(pathway_step_label="", source_reference="", provenance_note="")],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["construct_profile_rows"][0]["source_reference"] == presenter.NO_SOURCE_LABEL
    assert view_model["cassette_rows"][0]["provenance_note"] == presenter.NO_PROVENANCE_LABEL
    assert view_model["cassette_part_rows"][0]["part_label"] == presenter.NO_PART_LABEL
    assert view_model["construct_component_rows"][0]["component_reference_label"] == presenter.NO_COMPONENT_REFERENCE_LABEL
    assert view_model["construct_component_rows"][0]["sequence_availability_status"] == presenter.SEQUENCE_STATUS_NOT_RECORDED
    assert view_model["construct_component_rows"][0]["conservation_review_evidence"] == presenter.NO_CONSERVATION_EVIDENCE_LABEL
    assert view_model["construct_component_rows"][0]["conservation_follow_up_cue"] == presenter.CONSERVATION_REVIEW_NEEDED_STATUS
    assert view_model["construct_component_rows"][0]["review_metadata_status"] == presenter.COMPONENT_METADATA_GAP_STATUS
    assert view_model["construct_component_review_summary"] == {
        "total_component_rows": 1,
        "rows_with_source_reference_context": 0,
        "rows_missing_source_reference_context": 1,
        "rows_with_sequence_availability_note": 0,
        "rows_with_conservation_review_context": 0,
        "rows_needing_conservation_follow_up": 1,
        "rows_with_review_metadata_status": 1,
        "rows_with_review_note": 0,
        "rows_needing_manual_follow_up": 1,
    }
    assert [row["Issue type"] for row in view_model["construct_component_gap_queue"]] == [
        "Missing source/reference context",
        "Missing provenance context",
        "Missing sequence availability note",
        presenter.CONSERVATION_REVIEW_ISSUE_TYPE,
    ]
    assert view_model["construct_component_gap_queue"][0]["Manual follow-up note"] == (
        "Add documentation source or reference context before using this row in project review documentation."
    )
    assert view_model["linked_gene_rows"][0]["gene_label"] == presenter.NO_GENE_LABEL
    assert view_model["linked_pathway_step_rows"][0]["pathway_step_label"] == presenter.NO_PATHWAY_STEP_LABEL
    assert [row["Gap type"] for row in view_model["review_gap_rows"]] == [
        "part provenance",
        "promoter source context",
        "construct provenance",
        "cassette provenance",
        "gene link provenance",
        "pathway link provenance",
    ]


def test_presenter_reports_missing_promoter_source_context(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={"cassette-001": [_part(source_record_id="", source_record_label="", evidence_context_note="")]},
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["cassette_part_rows"][0]["source_record_label"] == presenter.NO_SOURCE_RECORD_LABEL
    assert view_model["cassette_part_rows"][0]["evidence_context_note"] == presenter.NO_EVIDENCE_CONTEXT_LABEL
    assert [row["Gap type"] for row in view_model["review_gap_rows"]] == [
        "promoter source context",
    ]


def test_presenter_component_gap_queue_keeps_documentation_only_copy(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={
            "cassette-001": [
                _part(
                    part_label="Documented CDS",
                    part_role="cds",
                    source_record_id="",
                    source_record_label="",
                    part_reference="cds-ref",
                    source_reference="Notebook source",
                    provenance_note="Manual review note.",
                ),
                _part(
                    part_order=2,
                    part_label="Undocumented part",
                    part_role="terminator",
                    part_reference="",
                    source_reference="",
                    source_record_id="",
                    source_record_label="",
                    provenance_note="",
                ),
            ]
        },
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert [row["Component label"] for row in view_model["construct_component_gap_queue"]] == [
        "Undocumented part",
        "Undocumented part",
        "Undocumented part",
    ]
    assert view_model["construct_component_review_summary"]["rows_needing_manual_follow_up"] == 1
    assert view_model["construct_component_review_summary"]["rows_missing_source_reference_context"] == 1
    combined = "\n".join(
        " ".join(row.values()) for row in view_model["construct_component_gap_queue"]
    ).lower()
    forbidden = [
        "best promoter",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_presenter_adds_component_conservation_review_readback_and_manual_follow_up(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={
            "cassette-001": [
                _part(
                    part_label="Native signal peptide context",
                    part_role="signal peptide",
                    part_reference="sequence source: local signal peptide record",
                    source_reference="source organism/source context: Oryza sativa seed context",
                    source_catalog="Manual literature note",
                    source_record_label="signal peptide sequence source record",
                    evidence_context_note=(
                        "literature/database evidence and conservation note recorded for manual reviewer review"
                    ),
                    provenance_note="manual reviewer note: conservation evidence still needs expert review.",
                ),
                _part(
                    part_order=2,
                    part_label="Terminator missing conservation note",
                    part_role="terminator",
                    part_reference="",
                    source_reference="",
                    source_catalog="",
                    source_record_id="",
                    source_record_label="",
                    evidence_context_note="",
                    provenance_note="",
                ),
            ]
        },
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")
    component_rows = view_model["construct_component_rows"]
    signal_row = component_rows[0]
    missing_row = component_rows[1]

    assert signal_row["component_category"] == "signal peptide"
    assert "source catalog: Manual literature note" in signal_row["conservation_review_evidence"]
    assert "sequence/source record: signal peptide sequence source record" in signal_row["conservation_review_evidence"]
    assert "source organism/source context: Oryza sativa seed context" in signal_row["conservation_review_evidence"]
    assert "literature/database or conservation note" in signal_row["conservation_review_evidence"]
    assert "manual reviewer note" in signal_row["conservation_review_evidence"]
    assert signal_row["conservation_follow_up_cue"] == presenter.CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS
    assert missing_row["conservation_review_evidence"] == presenter.NO_CONSERVATION_EVIDENCE_LABEL
    assert missing_row["conservation_follow_up_cue"] == presenter.CONSERVATION_REVIEW_NEEDED_STATUS
    assert view_model["construct_component_review_summary"]["rows_with_conservation_review_context"] == 1
    assert view_model["construct_component_review_summary"]["rows_needing_conservation_follow_up"] == 1

    conservation_rows = [
        row
        for row in view_model["construct_component_gap_queue"]
        if row["Issue type"] == presenter.CONSERVATION_REVIEW_ISSUE_TYPE
    ]
    assert len(conservation_rows) == 1
    assert conservation_rows[0]["Component label"] == "Terminator missing conservation note"
    assert "No source organism/source context" in conservation_rows[0]["Issue detail"]
    assert "literature or database evidence" in conservation_rows[0]["Issue detail"]
    assert "Manual documentation follow-up" in conservation_rows[0]["Manual follow-up note"]

    combined = f"{signal_row}\n{missing_row}\n{conservation_rows}\n{presenter.CONSERVATION_REVIEW_BOUNDARY_NOTE}".lower()
    forbidden = [
        "automatically conserved",
        "conserved component",
        "non-conserved component",
        "best component",
        "component recommendation",
        "expression prediction",
        "yield " + "prediction",
        "guaranteed success",
        "replace expert review",
        "wet-lab " + "readiness",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []
    for safe_phrase in ["without blast", "msa", "manual conservation review only"]:
        assert safe_phrase in combined


def test_presenter_adds_manual_follow_up_for_ambiguous_component_role(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={
            "cassette-001": [
                _part(
                    part_label="Manual component row",
                    part_role="other",
                    part_reference="manual-ref",
                    source_reference="Manual source note",
                    source_record_id="",
                    source_record_label="",
                    provenance_note="Manual provenance note.",
                )
            ]
        },
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["construct_component_rows"][0]["component_category"] == presenter.NO_COMPONENT_CATEGORY_LABEL
    assert [row["Issue type"] for row in view_model["construct_component_gap_queue"]] == [
        presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
    ]
    row = view_model["construct_component_gap_queue"][0]
    assert row["Issue detail"] == (
        "Component role is missing or recorded as other documented component in this documentation view."
    )
    assert row["Manual follow-up note"] == (
        "Manual documentation follow-up: review the component role label for traceability clarity."
    )
    assert view_model["construct_component_review_summary"]["rows_needing_manual_follow_up"] == 1


def test_presenter_adds_deterministic_manual_follow_up_for_duplicate_component_labels(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[
            _cassette(cassette_id="cassette-b", cassette_label="Cassette B", cassette_order=2),
            _cassette(cassette_id="cassette-a", cassette_label="Cassette A", cassette_order=1),
        ],
        parts_by_cassette={
            "cassette-b": [
                _part(cassette_id="cassette-b", part_order=2, part_label="Shared Label", part_role="cds"),
                _part(cassette_id="cassette-b", part_order=1, part_label="Shared Label", part_role="promoter"),
            ],
            "cassette-a": [
                _part(cassette_id="cassette-a", part_order=2, part_label="Alpha Label", part_role="terminator"),
                _part(cassette_id="cassette-a", part_order=1, part_label="Alpha Label", part_role="terminator"),
            ],
        },
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    duplicate_rows = [
        row
        for row in view_model["construct_component_gap_queue"]
        if row["Issue type"] == presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE
    ]
    assert [(row["Cassette label"], row["Component label"], row["Component category"]) for row in duplicate_rows] == [
        ("Cassette A", "Alpha Label", "terminator"),
        ("Cassette B", "Shared Label", "multiple documented component categories"),
    ]
    assert duplicate_rows[0]["Issue detail"] == (
        "The same visible component label appears more than once in this construct/cassette documentation context."
    )
    assert duplicate_rows[0]["Manual follow-up note"] == (
        "Manual documentation follow-up: review duplicate component labels for traceability clarity."
    )
    assert view_model["construct_component_review_summary"]["rows_needing_manual_follow_up"] == 2


def test_presenter_component_ambiguity_follow_up_copy_stays_documentation_only(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile()],
        profile=_profile(),
        cassettes=[_cassette()],
        parts_by_cassette={
            "cassette-001": [
                _part(
                    part_order=1,
                    part_label="Repeat label",
                    part_role="other",
                    source_reference="Manual source note",
                    source_record_id="",
                    source_record_label="",
                    provenance_note="Manual provenance note.",
                ),
                _part(
                    part_order=2,
                    part_label="Repeat label",
                    part_role="other",
                    source_reference="Manual source note",
                    source_record_id="",
                    source_record_label="",
                    provenance_note="Manual provenance note.",
                ),
            ]
        },
        gene_links=[_gene_link()],
        pathway_links=[_pathway_link()],
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")
    combined = "\n".join(
        " ".join(row.values()) for row in view_model["construct_component_gap_queue"]
    ).lower()

    assert "manual documentation follow-up" in combined
    forbidden = [
        "biological recommendation",
        "compatibility proof",
        "experiment validation",
        "readiness claim",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "wet-lab " + "readiness",
        "scoring",
        "ranking",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_project_construct_component_review_queue_aggregates_project_views(monkeypatch):
    def fake_report_views(project_id=None):
        assert project_id == "project-174"
        return [
            {
                "construct_profile_rows": [_profile()],
                "construct_component_rows": [
                    {
                        "construct_label": "Construct Alpha",
                        "component_label": "Part with source",
                        "component_category": "promoter",
                        "component_reference_label": "Source record A",
                        "sequence_availability_status": presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
                        "review_metadata_status": presenter.COMPONENT_METADATA_RECORDED_STATUS,
                        "review_note": "Reviewed for documentation traceability.",
                        "cassette_label": "Cassette A",
                    },
                    {
                        "construct_label": "Construct Alpha",
                        "component_label": "Missing source part",
                        "component_category": "terminator",
                        "component_reference_label": presenter.NO_COMPONENT_REFERENCE_LABEL,
                        "sequence_availability_status": presenter.SEQUENCE_STATUS_NOT_RECORDED,
                        "review_metadata_status": presenter.COMPONENT_METADATA_GAP_STATUS,
                        "review_note": presenter.NO_PROVENANCE_LABEL,
                        "cassette_label": "Cassette A",
                    },
                ],
                "construct_component_gap_queue": [
                    {
                        "Construct label": "Construct Alpha",
                        "Cassette label": "Cassette A",
                        "Component label": "Missing source part",
                        "Component category": "terminator",
                        "Issue type": "Missing source/reference context",
                        "Issue detail": "No source record, component reference, or source note is recorded.",
                        "Manual follow-up note": "Add documentation source/reference context.",
                    },
                    {
                        "Construct label": "Construct Alpha",
                        "Cassette label": "Cassette A",
                        "Component label": "Missing source part",
                        "Component category": "terminator",
                        "Issue type": "Missing provenance context",
                        "Issue detail": "No provenance or review note is recorded.",
                        "Manual follow-up note": "Add manual provenance/review context.",
                    },
                ],
            }
        ]

    monkeypatch.setattr(presenter, "build_expression_construct_report_views", fake_report_views)

    queue = presenter.build_project_construct_component_review_queue(project_id="project-174")

    assert queue["section_title"] == "Expression construct documentation follow-up"
    assert queue["status"] == "AVAILABLE"
    assert queue["summary"] == {
        "total_component_rows": 2,
        "rows_with_source_reference_context": 1,
        "rows_missing_source_reference_context": 1,
        "rows_with_sequence_availability_note": 1,
        "rows_with_conservation_review_context": 0,
        "rows_needing_conservation_follow_up": 0,
        "rows_with_review_metadata_status": 2,
        "rows_with_review_note": 1,
        "rows_needing_manual_follow_up": 1,
        "construct_count": 1,
    }
    assert queue["total_rows_available"] == 2
    assert queue["rows"][0]["Issue type"] == "Missing source/reference context"
    assert "Expression Constructs" in queue["caption"]
    assert any("read-only project review context" in note for note in queue["boundary_notes"])


def test_project_construct_component_review_queue_empty_state(monkeypatch):
    monkeypatch.setattr(presenter, "build_expression_construct_report_views", lambda project_id=None: [])

    queue = presenter.build_project_construct_component_review_queue(project_id="project-empty")

    assert queue["status"] == "NOT_AVAILABLE"
    assert queue["summary"]["total_component_rows"] == 0
    assert queue["summary"]["rows_needing_manual_follow_up"] == 0
    assert queue["summary"]["construct_count"] == 0
    assert queue["rows"] == []
    assert "No Expression Construct component documentation follow-up items" in queue["empty_state_message"]


def test_presenter_copy_avoids_unsafe_product_claims():
    combined = "\n".join(
        [
            presenter.BOUNDARY_COPY,
            presenter.NO_SOURCE_LABEL,
            presenter.NO_PROVENANCE_LABEL,
            presenter.NO_PART_LABEL,
            presenter.NO_GENE_LABEL,
            presenter.NO_PATHWAY_STEP_LABEL,
            presenter.NO_PROJECT_LINK_LABEL,
            presenter.NO_PROJECT_LINK_NOTE_LABEL,
            presenter.NO_SOURCE_CATALOG_LABEL,
            presenter.NO_SOURCE_RECORD_LABEL,
            presenter.NO_EVIDENCE_CONTEXT_LABEL,
            presenter.NO_COMPONENT_CATEGORY_LABEL,
            presenter.NO_COMPONENT_REFERENCE_LABEL,
            presenter.SEQUENCE_STATUS_LINKED_REFERENCE,
            presenter.SEQUENCE_STATUS_NOT_RECORDED,
            presenter.SEQUENCE_STATUS_NOT_DISPLAYED,
            presenter.COMPONENT_METADATA_GAP_STATUS,
            presenter.COMPONENT_METADATA_RECORDED_STATUS,
            presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
            presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
            "\n".join(presenter.COMPONENT_GAP_QUEUE_COLUMNS),
            "\n".join(presenter.COMPONENT_REVIEW_SUMMARY_LABELS.values()),
            "\n".join(presenter.SUPPORTED_COMPONENT_VOCABULARY),
        ]
    ).lower()
    forbidden = [
        "recommend" + "ation",
        "recommend" + "ed",
        "best " + "promoter",
        "scor" + "ing",
        "rank" + "ing",
        "optim" + "ization",
        "optim" + "ized",
        "valid" + "ation",
        "valid" + "ated",
        "host " + "compatibility",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "transformation " + "protocol",
        "experimentally " + "confirmed",
        "expression " + "prediction",
        "yield " + "improvement",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_presenter_exposes_draft_defaults_and_empty_states(monkeypatch):
    _patch_repo(monkeypatch, profiles=[_profile()], profile=_profile(), cassettes=[])

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["draft_defaults"]["construct_label"] == presenter.DEFAULT_CONSTRUCT_LABEL
    assert view_model["draft_defaults"]["cassette_role"] == presenter.DEFAULT_CASSETTE_TYPE
    assert "construct draft" in view_model["empty_states"]["constructs"].lower()
    assert "cassette rows" in view_model["empty_states"]["cassettes"].lower()
    assert "cassette part rows" in view_model["empty_states"]["parts"].lower()
    assert "project-level construct links" in view_model["empty_states"]["project_links"].lower()


def test_step2_component_context_readback_builds_documentation_rows() -> None:
    readback = presenter.build_step2_component_context_readback(
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        rules={
            "kingdom": "prokaryote",
            "promoter": "T7 Promoter",
            "rbs": "Shine-Dalgarno B0034",
            "terminator": "rrnB T1 Terminator",
            "vector_suggestion": "pET documentation context",
        },
        records=[
            {
                "asset_id": "asset-prom",
                "asset_type": "promoter",
                "display_name": "T7 promoter source note",
                "aliases": ["T7 Promoter"],
                "short_description": "Metadata-only promoter context record.",
                "organism_or_source_context": "recorded Component Library context",
                "sequence_available": True,
                "source_notes": "Source/provenance review note.",
                "provenance_status": "source review needed",
                "version_context": "test seed",
                "review_status": "record review pending",
                "tags": [],
            }
        ],
    )

    rows = presenter.step2_component_context_table_rows(readback["rows"])

    assert readback["title"] == presenter.STEP2_CONTEXT_READBACK_TITLE
    assert readback["summary"]["rows_with_recorded_assets"] == 1
    assert rows[0]["Step 2 context category"] == "host/context"
    assert any(row["Step 2 context category"] == "promoter" for row in rows)
    promoter_row = next(row for row in rows if row["Step 2 context category"] == "promoter")
    assert promoter_row["Step 2 recorded value"] == "T7 Promoter"
    assert promoter_row["Component Library asset"] == "T7 promoter source note / asset-prom"
    assert promoter_row["Source/provenance review"] == "source review needed"
    assert promoter_row["Record review status"] == "record review pending"
    assert "not saved as construct source of truth" in readback["documentation_boundary_note"]


def test_step2_component_context_readback_missing_context_is_safe() -> None:
    readback = presenter.build_step2_component_context_readback(host="", tag="", rules={}, elements={})

    assert readback["rows"] == []
    assert readback["summary"] == {
        "total_rows": 0,
        "rows_with_recorded_assets": 0,
        "manual_follow_up_rows": 0,
    }
    assert readback["empty_state"] == presenter.STEP2_CONTEXT_EMPTY_STATE
    assert "read-only review context" in readback["documentation_boundary_note"]


def test_step2_component_context_readback_copy_avoids_claims() -> None:
    readback = presenter.build_step2_component_context_readback(host="", tag="", rules={}, elements={})
    combined = "\n".join(
        [
            presenter.STEP2_CONTEXT_READBACK_TITLE,
            presenter.STEP2_CONTEXT_READBACK_COPY,
            presenter.STEP2_CONTEXT_EMPTY_STATE,
            presenter.STEP2_CONTEXT_BOUNDARY_NOTE,
            str(readback),
        ]
    ).lower()

    forbidden = [
        "best host",
        "best promoter",
        "optimized",
        "high-expression",
        "high expression",
        "validated",
        "wet-lab ready",
        "expression improvement",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_presenter_uses_safe_default_labels_for_missing_draft_metadata(monkeypatch):
    _patch_repo(
        monkeypatch,
        profiles=[_profile(construct_label="", construct_type="", review_status="", documentation_scope_note="")],
        profile=_profile(construct_label="", construct_type="", review_status="", documentation_scope_note=""),
        cassettes=[_cassette(cassette_label="", cassette_role="")],
        parts_by_cassette={"cassette-001": []},
    )

    view_model = presenter.build_expression_construct_presenter("construct-001")

    assert view_model["construct_profile_rows"][0]["construct_label"] == presenter.DEFAULT_CONSTRUCT_LABEL
    assert view_model["construct_profile_rows"][0]["construct_type"] == presenter.DEFAULT_CONSTRUCT_TYPE
    assert view_model["construct_profile_rows"][0]["review_status"] == presenter.NO_REVIEW_STATUS_LABEL
    assert view_model["construct_profile_rows"][0]["documentation_scope_note"] == presenter.NO_REVIEW_NOTE_LABEL
    assert view_model["cassette_rows"][0]["cassette_label"] == presenter.DEFAULT_CASSETTE_LABEL
    assert view_model["cassette_rows"][0]["cassette_role"] == presenter.DEFAULT_CASSETTE_TYPE
