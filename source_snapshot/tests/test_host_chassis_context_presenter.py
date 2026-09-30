from __future__ import annotations

from services.host_chassis_context_presenter import (
    build_host_chassis_context_summary,
    summarize_asset_host_chassis_context,
)


def test_host_chassis_context_summary_is_chassis_neutral() -> None:
    summary = build_host_chassis_context_summary(
        {"id": 1, "name": "Neutral workspace", "host": "CHO cell line"},
        linked_catalog_assets=[
            {
                "asset_id": "host-bacterial",
                "asset_display_name": "Bacterial context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {"host_context": "E. coli chassis documentation note"},
            },
            {
                "asset_id": "host-yeast",
                "asset_display_name": "Yeast context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {"host_context": "Saccharomyces cerevisiae review context"},
            },
            {
                "asset_id": "host-plant",
                "asset_display_name": "Plant context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {"host_context": "Nicotiana benthamiana source context"},
            },
        ],
    )

    assert summary["supported_contexts"] == [
        "bacterial",
        "yeast",
        "mammalian",
        "plant",
        "generic / unspecified",
    ]
    assert summary["project_context"] == "mammalian"
    assert summary["contexts_present"] == ["bacterial", "yeast", "mammalian", "plant"]


def test_plant_is_one_supported_context_not_a_default() -> None:
    summary = build_host_chassis_context_summary({"id": 2, "name": "Generic workspace"})

    assert summary["project_context"] == "generic / unspecified"
    assert summary["project_context_label"] == "Generic / unspecified"
    assert summary["contexts_present"] == ["generic / unspecified"]
    assert summary["plant_is_supported_example_only"] is True
    assert "Plant" in summary["supported_context_labels"]


def test_host_chassis_context_summary_avoids_recommendation_validation_and_readiness_claims() -> None:
    summary = build_host_chassis_context_summary(
        {"id": 3, "name": "Safety workspace", "host": "Nicotiana benthamiana"}
    )
    text = str(summary).lower()

    forbidden_positive_claims = [
        "is recommended",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "readiness score",
        "host recommendation",
        "host compatibility proof",
    ]
    for term in forbidden_positive_claims:
        assert term not in text
    assert "documentation-only" in text


def test_host_chassis_context_summary_includes_active_project_row() -> None:
    summary = build_host_chassis_context_summary(
        {"id": 4, "name": "Active project", "host": "Saccharomyces cerevisiae documentation context"}
    )

    assert summary["context_count"] == 1
    assert summary["rows"][0]["source_label"] == "Active project host field"
    assert summary["rows"][0]["normalized_context_label"] == "Yeast"


def test_asset_host_chassis_context_summary_uses_safe_fallbacks() -> None:
    summary = summarize_asset_host_chassis_context({"display_name": "Unknown asset"})

    assert summary["source_value"] == "Not recorded"
    assert summary["normalized_context"] == "generic / unspecified"
    assert summary["normalized_context_label"] == "Generic / unspecified"
    assert "not compatibility evidence" in summary["readback"].lower()


def test_asset_host_chassis_context_summary_treats_plant_as_supported_context_not_default() -> None:
    plant_summary = summarize_asset_host_chassis_context(
        {"organism_or_source_context": "Nicotiana benthamiana plant source context"}
    )
    bacterial_summary = summarize_asset_host_chassis_context(
        {"organism_or_source_context": "E. coli bacterial source context"}
    )

    assert plant_summary["normalized_context"] == "plant"
    assert plant_summary["normalized_context_label"] == "Plant"
    assert bacterial_summary["normalized_context"] == "bacterial"
