from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_wizard_step2_component_context_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE,
    build_step2_component_library_context,
)


def _record(asset_id: str, asset_type: str, display_name: str, aliases=None, tags=None) -> dict:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "aliases": aliases or [],
        "short_description": f"Metadata-only {asset_type} context record.",
        "organism_or_source_context": "recorded context for documentation review",
        "sequence_available": False,
        "sequence_hash": "",
        "sequence_hash_algorithm": "",
        "source_notes": "Source/provenance review note.",
        "provenance_status": "source review needed",
        "version_context": "test seed",
        "review_status": "human review needed",
        "human_review_notes": "Manual follow-up required.",
        "tags": tags or [],
        "documentation_boundary_note": "Documentation-only record.",
    }


def _rules() -> dict:
    return {
        "kingdom": "prokaryote",
        "promoter": "T7 Promoter",
        "rbs": "Shine-Dalgarno B0034",
        "terminator": "rrnB T1 Terminator",
        "vector_suggestion": "pET documentation context",
    }


def test_step2_component_context_presenter_builds_read_only_rows() -> None:
    presenter = build_step2_component_library_context(
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        rules=_rules(),
        elements={},
        records=[
            _record("asset-host", "host_chassis_context_note", "Bacterial chassis source note", tags=["bacterial"]),
            _record("asset-prom", "promoter", "T7 promoter source note", aliases=["T7 Promoter"]),
            _record("asset-rbs", "rbs_5utr", "B0034 translation initiation note", aliases=["B0034"]),
            _record("asset-term", "terminator", "rrnB terminator source note", aliases=["rrnB"]),
            _record("asset-tag", "tag", "His6 tag source note", aliases=["His6-tag"]),
            _record("asset-vector", "plasmid_backbone", "pET backbone source note", aliases=["pET"]),
            _record("asset-signal", "signal_peptide", "Signal peptide documentation note"),
            _record("asset-marker", "marker_metadata", "Selectable marker metadata note", tags=["marker"]),
            _record("asset-reporter", "cds_target", "Reporter gene metadata note", tags=["reporter"]),
        ],
    )

    by_key = {row["key"]: row for row in presenter["rows"]}

    assert presenter["title"] == "Component Library context"
    assert presenter["summary"]["total_rows"] >= 9
    assert presenter["summary"]["rows_with_recorded_assets"] == 9
    assert presenter["summary"]["source_provenance_review_rows"] == 9
    assert presenter["summary"]["manual_follow_up_rows"] == 2
    assert presenter["summary"]["incomplete_sequence_metadata_rows"] == 9
    assert by_key["host_context"]["asset_id"] == "asset-host"
    assert by_key["promoter"]["asset_id"] == "asset-prom"
    assert by_key["translation_initiation_context"]["asset_id"] == "asset-rbs"
    assert by_key["terminator"]["asset_id"] == "asset-term"
    assert by_key["tag"]["asset_id"] == "asset-tag"
    assert by_key["vector_backbone"]["asset_id"] == "asset-vector"
    assert by_key["signal_peptide"]["asset_id"] == "asset-signal"
    assert by_key["selectable_marker"]["asset_id"] == "asset-marker"
    assert by_key["reporter"]["asset_id"] == "asset-reporter"
    assert all("source/provenance" in row["source_provenance_review"] or row["source_provenance_review"] for row in presenter["rows"])
    assert "not a biological recommendation" in presenter["documentation_boundary_note"]


def test_missing_component_context_uses_safe_empty_state() -> None:
    presenter = build_step2_component_library_context(
        host="Unlisted host",
        tag="No tag",
        rules={},
        elements={},
        records=[],
    )

    assert presenter["rows_with_assets"] == []
    assert presenter["summary"]["manual_follow_up_rows"] == presenter["summary"]["total_rows"]
    assert presenter["summary"]["source_provenance_review_rows"] == presenter["summary"]["total_rows"]
    assert presenter["summary"]["incomplete_sequence_metadata_rows"] == presenter["summary"]["total_rows"]
    assert "No Component Library context is recorded" in presenter["empty_state"]
    assert all(row["context_state"] == "manual follow-up" for row in presenter["rows"])
    assert all(row["asset_label"] == "No recorded Component Library context" for row in presenter["rows"])


def test_step2_component_context_copy_avoids_biological_claims() -> None:
    presenter = build_step2_component_library_context(
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        rules=_rules(),
        records=[_record("asset-host", "host_chassis_context_note", "Bacterial chassis source note", tags=["bacterial"])],
    )
    rendered = "\n".join([str(presenter), DOCUMENTATION_BOUNDARY_NOTE]).lower()

    for forbidden in [
        "best host",
        "best promoter",
        "high expression",
        "optimized pathway",
        "validated construct",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "yield prediction",
    ]:
        assert forbidden not in rendered
    assert "not a biological recommendation" in rendered
    assert "manual follow-up" in rendered
