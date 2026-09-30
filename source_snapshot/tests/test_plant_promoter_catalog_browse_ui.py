# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.PlantPromoterCatalog as view
import views.tool_typography as tool_typography


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
    )


def _find_dataframe(fake_st: FakeStreamlit, columns: list[str]):
    for dataframe in fake_st.dataframes:
        if list(getattr(dataframe, "columns", [])) == columns:
            return dataframe
    raise AssertionError(f"Dataframe with columns {columns!r} not found")


def _sample_view_model() -> dict[str, object]:
    return {
        "summary_counts": {
            "profile_count": 2,
            "tissue_evidence_count": 2,
            "motif_annotation_count": 1,
            "rows_needing_review_count": 1,
            "source_database_count": 2,
            "linked_catalog_reference_count": 2,
        },
        "available_species": ["Arabidopsis thaliana (thale cress)", "Zea mays (maize)"],
        "available_evidence_types": ["literature-reported"],
        "available_curation_statuses": ["metadata reviewed", "source review needed"],
        "tissue_context_evidence_summary": {"root": 1, "No tissue context recorded": 1},
        "rows_needing_review": [
            {
                "part_id": "plant-promoter-001",
                "display_name": "Maize promoter source record",
                "tissue_context": "root",
                "curation_status": "source review needed",
                "review_note": "Needs review before use in project documentation.",
            }
        ],
        "source_evidence_labels": ["Fixture source: ROOT-001", "No source database recorded"],
        "profile_rows": [
            {
                "part_id": "plant-promoter-001",
                "display_name": "Maize promoter source record",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
            },
            {
                "part_id": "plant-promoter-002",
                "display_name": "Arabidopsis promoter source record",
                "plant_clade": "dicot",
                "species_label": "Arabidopsis thaliana (thale cress)",
            },
        ],
        "evidence_rows": [
            {
                "promoter_label": "Maize promoter source record",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
                "tissue_context": "root",
                "evidence_type": "literature-reported",
                "source_database": "Fixture source",
                "curation_status": "source review needed",
                "review_note": "Needs review before use in project documentation.",
            },
            {
                "promoter_label": "Arabidopsis promoter source record",
                "plant_clade": "dicot",
                "species_label": "Arabidopsis thaliana (thale cress)",
                "tissue_context": "",
                "evidence_type": "",
                "source_database": "",
                "curation_status": "",
                "review_note": "",
            },
        ],
        "motif_preview_rows": [
            {
                "promoter_label": "Maize promoter source record",
                "motif_name": "Fixture motif A",
                "motif_source": "Fixture motif source",
                "motif_accession": "MOTIF-FIXTURE",
                "evidence_note": "Motif evidence note needs source review.",
            }
        ],
        "context_readback_rows": [
            {
                "catalog_context": "Maize promoter source record",
                "species_or_clade_context": "Zea mays (maize); monocot",
                "tissue_evidence_context": "root; literature-reported",
                "source_review_metadata": "source context: Fixture source: ROOT-001; review metadata: source review needed; manual review note: Needs review before use in project documentation.",
                "metadata_gap": "No metadata gap recorded",
            },
            {
                "catalog_context": "Arabidopsis promoter source record",
                "species_or_clade_context": "Arabidopsis thaliana (thale cress); dicot",
                "tissue_evidence_context": "No tissue context recorded; No evidence type recorded",
                "source_review_metadata": "source context: No source database recorded; review metadata: No curation status recorded; manual review note: No manual review note recorded",
                "metadata_gap": "tissue evidence context metadata gap; source context metadata gap; review metadata gap; manual review note metadata gap",
            },
        ],
        "boundary_note": "Local curated sample records are shown as documentation-level catalog context; they are not selection advice, source verification, biological forecasts, or wet-lab use guidance.",
        "documentation_only_context_note": "Documentation-only context readback for catalog/source review. This readback does not recommend promoters, rank records, verify host compatibility, predict expression, validate use, or judge wet-lab readiness.",
        "catalog_source": "local curated sample records",
        "catalog_status_label": "bundled seed records",
        "documentation_status_label": "documentation-only reference records",
        "persistent_profile_count": 0,
        "seed_profile_count": 2,
        "represented_source_database_labels": ["Fixture source", "No source database recorded"],
        "linked_catalog_reference_labels": ["Fixture source", "No source database recorded"],
        "represented_profile_ids": ["plant-promoter-001", "plant-promoter-002"],
        "seed_metadata": {"seed_name": "V2.6 R34 Plant Promoter Catalog curated sample records", "seed_version": "v2.6-r58"},
        "seed_warnings": ["record 1 unknown field ignored: extra_field"],
    }


def _sample_detail_view_model() -> dict[str, object]:
    return {
        "status": "available",
        "profile_summary": {
            "part_id": "plant-promoter-001",
            "promoter_label": "Maize promoter source record",
            "alias": "Zm fixture locus",
            "plant_clade": "monocot",
            "species_label": "Zea mays (maize)",
            "promoter_type": "source-recorded promoter context",
            "sequence_availability": "metadata-only sequence context",
            "tissue_context_count": 1,
            "evidence_row_count": 1,
            "motif_annotation_count": 1,
        },
        "evidence_rows": [
            {
                "tissue_context": "root",
                "plant_ontology_id": "PO:fixture",
                "development_stage": "source-recorded stage",
                "expression_context_label": "root context",
                "evidence_type": "literature-reported",
                "evidence_summary": "Root evidence captured as documentation context.",
                "source_label": "Fixture source: ROOT-001",
                "publication_reference": "Fixture publication reference",
                "curation_status": "source review needed",
                "review_note": "Needs review before use in project documentation.",
            }
        ],
        "motif_annotation_rows": [
            {
                "motif_name": "Fixture motif A",
                "motif_source": "Fixture motif source",
                "motif_accession": "MOTIF-FIXTURE",
                "motif_sequence_or_consensus": "NNNN",
                "motif_position_note": "Source-recorded position context.",
                "associated_function_note": "Function note is documentation context.",
                "evidence_note": "Motif evidence note needs source review.",
            }
        ],
        "source_review_metadata_rows": [
            {"metadata_group": "Source labels", "metadata_value": "Fixture source: ROOT-001"},
            {"metadata_group": "Missing metadata count", "metadata_value": "0"},
        ],
        "boundary_note": "Read-only Plant Promoter Catalog reference. Documentation-level context only.",
        "limitation_note": "Linked plant promoter profiles preserve catalog metadata snapshots only.",
    }


def _stub_detail(monkeypatch) -> None:
    monkeypatch.setattr(
        view.workspace_presenter,
        "build_profile_detail_view_model",
        lambda part_id: _sample_detail_view_model(),
    )


def test_page_renders_boundary_copy_filters_and_tables(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_view_model())
    _stub_detail(monkeypatch)

    view.render()
    rendered = _rendered_text(fake_st)

    assert "Promoter Assets - Plant Domain" in rendered
    assert "Component Library detail surface for plant promoter profile rows" in rendered
    assert "Local curated sample records are shown as documentation-level catalog context" in rendered
    assert "Persistent promoter profile tables are currently empty" in rendered
    assert "Source family: Plant Promoter Catalog." in rendered
    assert "Record scope: profile rows plus child evidence and review rows." in rendered
    assert "Profile rows" in rendered
    assert "Filtered table rows" in rendered
    assert "Child tissue evidence rows" in rendered
    assert "Showing 2 tissue evidence rows across 2 of 2 profile rows." in rendered
    assert "Tissue evidence metadata summary: No tissue context recorded: 1, root: 1" in rendered
    assert "Source evidence context labels: Fixture source: ROOT-001; No source database recorded" in rendered
    assert "Source database groups represented: Fixture source, No source database recorded" in rendered
    assert "Read-only evidence gap review queue for documentation review and human curation only." in rendered
    assert "Counts by category:" in rendered
    assert "Does not recommend, rank, validate, optimize, or confirm promoter suitability." in rendered
    assert "Host/tissue readback rows" in rendered
    assert "source-recorded species, clade, tissue evidence metadata, and review gaps" in rendered
    assert "not host compatibility proof, not a promoter recommendation, and not a wet-lab readiness judgment" in rendered
    assert "Catalog context readback rows" in rendered
    assert "Documentation-only context readback for catalog/source review." in rendered
    assert "catalog context, tissue evidence context, source context, review metadata, and metadata gaps visible for manual review" in rendered
    assert "Review-needed rows" in rendered
    assert "not a biological recommendation, host compatibility proof, or wet-lab use guidance" in rendered
    assert "Read-only documentation detail surface for Plant Promoter Catalog profile rows and child evidence rows." in rendered
    assert "does not provide selection advice, record ordering, behavior forecasts, source verification" in rendered
    assert [call["label"] for call in fake_st.selectbox_calls] == [
        "Plant clade",
        "Species",
        "Tissue context",
        "Evidence type",
        "Curation status",
        "Plant promoter profile for project reference",
        "Promoter profile detail",
    ]
    assert list(_find_dataframe(fake_st, view.EVIDENCE_GAP_QUEUE_COLUMNS).columns) == view.EVIDENCE_GAP_QUEUE_COLUMNS
    assert _find_dataframe(fake_st, view.EVIDENCE_GAP_QUEUE_COLUMNS).iloc[0]["Category"] == "source_provenance_gap"
    host_tissue_table = _find_dataframe(fake_st, view.HOST_TISSUE_READBACK_COLUMNS)
    assert host_tissue_table.iloc[0]["Species context"] == "Arabidopsis thaliana (thale cress)"
    assert host_tissue_table.iloc[0]["Tissue evidence metadata"] == view.presenter.NO_TISSUE_LABEL
    assert host_tissue_table.iloc[1]["Species context"] == "Zea mays (maize)"
    assert host_tissue_table.iloc[1]["Review gaps"] == "1 review-needed rows"
    context_table = _find_dataframe(fake_st, view.CONTEXT_READBACK_COLUMNS)
    assert context_table.iloc[1]["Metadata gap"] == "tissue evidence context metadata gap; source context metadata gap; review metadata gap; manual review note metadata gap"
    assert list(_find_dataframe(fake_st, view.TABLE_COLUMNS).columns) == view.TABLE_COLUMNS
    review_needed_table = _find_dataframe(fake_st, [
        "Promoter / part label",
        "Tissue context",
        "Curation status",
        "Review-needed source/review context",
    ])
    assert list(review_needed_table.columns) == [
        "Promoter / part label",
        "Tissue context",
        "Curation status",
        "Review-needed source/review context",
    ]
    motif_table = _find_dataframe(fake_st, [
        "Promoter / part label",
        "Motif",
        "Motif source context",
        "Accession",
        "Evidence note",
    ])
    assert list(motif_table.columns) == [
        "Promoter / part label",
        "Motif",
        "Motif source context",
        "Accession",
        "Evidence note",
    ]
    assert list(_find_dataframe(fake_st, view.PROFILE_COLUMNS).columns) == view.PROFILE_COLUMNS
    assert list(_find_dataframe(fake_st, view.DETAIL_EVIDENCE_COLUMNS).columns) == view.DETAIL_EVIDENCE_COLUMNS
    assert list(_find_dataframe(fake_st, view.DETAIL_MOTIF_COLUMNS).columns) == view.DETAIL_MOTIF_COLUMNS
    source_review_table = _find_dataframe(fake_st, view.SOURCE_REVIEW_COLUMNS)
    assert source_review_table.iloc[0]["Metadata context"] == "Source context labels"
    assert source_review_table.iloc[1]["Metadata context"] == "Metadata gap count"
    expander_labels = {call["label"]: call for call in fake_st.expander_calls}
    assert "Plant Promoter Evidence Gap Review Queue" in expander_labels
    assert "Promoter asset rows and review readback" in expander_labels
    assert "Promoter project reference rows" in expander_labels
    assert "Selected promoter profile row detail" in expander_labels
    assert expander_labels["Plant Promoter Evidence Gap Review Queue"]["expanded"] is False
    assert expander_labels["Promoter asset rows and review readback"]["expanded"] is False
    assert expander_labels["Promoter project reference rows"]["expanded"] is False
    assert expander_labels["Selected promoter profile row detail"]["expanded"] is False


def test_selected_profile_without_source_review_rows_renders_metadata_gap(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_view_model())
    detail = _sample_detail_view_model()
    detail["source_review_metadata_rows"] = []
    monkeypatch.setattr(view.workspace_presenter, "build_profile_detail_view_model", lambda part_id: detail)

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No source/review metadata rows are recorded for the selected promoter profile" in rendered
    assert "metadata gap for documentation review" in rendered


def test_empty_profile_state_renders_safe_copy(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(
        view.presenter,
        "build_plant_promoter_catalog_view_model",
        lambda **kwargs: {
            "summary_counts": {},
            "available_species": [],
            "available_evidence_types": [],
            "available_curation_statuses": [],
            "profile_rows": [],
            "evidence_rows": [],
            "motif_preview_rows": [],
        },
    )

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No promoter profiles are present for the current local documentation scope." in rendered
    assert "documentation scope" in rendered


def test_filter_empty_state_renders_when_no_rows_match(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    calls = {"count": 0}

    def _fake_view_model(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _sample_view_model()
        return {
            "summary_counts": {
                "profile_count": 1,
                "tissue_evidence_count": 0,
                "motif_annotation_count": 0,
                "rows_needing_review_count": 0,
                "source_database_count": 0,
            },
            "available_species": ["Zea mays (maize)"],
            "available_evidence_types": ["literature-reported"],
            "available_curation_statuses": ["source review needed"],
            "profile_rows": [{"part_id": "plant-promoter-001", "display_name": "Maize promoter source record"}],
            "evidence_rows": [],
            "motif_preview_rows": [],
        }

    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", _fake_view_model)
    fake_st.selectbox_values["plant_promoter_catalog_tissue"] = "seed"

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No tissue evidence rows match the current filters." in rendered


def test_missing_values_use_fallback_labels(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_view_model())
    _stub_detail(monkeypatch)

    view.render()

    table = _find_dataframe(fake_st, view.TABLE_COLUMNS)
    assert table.iloc[1]["Tissue context"] == view.presenter.NO_TISSUE_LABEL
    assert table.iloc[1]["Source context"] == view.presenter.NO_SOURCE_LABEL
    assert table.iloc[1]["Evidence type"] == view.presenter.NO_EVIDENCE_TYPE_LABEL
    assert table.iloc[1]["Curation status"] == view.presenter.NO_CURATION_STATUS_LABEL


def test_seed_backed_view_renders_catalog_source_and_limitation_notes(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_view_model())
    _stub_detail(monkeypatch)

    view.render()
    rendered = _rendered_text(fake_st)

    assert "Local curated sample records are shown as documentation-level catalog context." in rendered
    assert "Seed metadata: V2.6 R34 Plant Promoter Catalog curated sample records v2.6-r58" in rendered
    assert "does not provide selection advice, certification, or behavior forecasts" in rendered


def test_presenter_output_is_consumed_defensively(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(
        view.presenter,
        "build_plant_promoter_catalog_view_model",
        lambda **kwargs: {
            "summary_counts": {"profile_count": "2"},
            "profile_rows": ["bad-row"],
            "evidence_rows": [None, {"promoter_label": "Fallback promoter"}],
            "motif_preview_rows": "not-a-list",
            "available_species": "not-a-list",
            "available_evidence_types": None,
            "available_curation_statuses": [],
        },
    )

    view.render()
    rendered = _rendered_text(fake_st)

    assert "No promoter profiles are present for the current local documentation scope." in rendered


def test_page_copy_denylist_stays_bounded(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(view.presenter, "build_plant_promoter_catalog_view_model", lambda **kwargs: _sample_view_model())
    _stub_detail(monkeypatch)

    view.render()
    combined = _rendered_text(fake_st).lower()
    forbidden = [
        "recommend" + "ed",
        "best promoter",
        "optimal",
        "valid" + "ated",
        "approv" + "ed",
        "safe for " + "use",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "experimentally " + "confirmed",
        "host " + "compatible",
        "predic" + "tion",
        "optimiza" + "tion",
        "rank" + "ing",
        "scor" + "ing",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
