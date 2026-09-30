# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.Data as view
import views.tool_typography as tool_typography


def _sample_record(index: int, asset_type: str) -> dict[str, object]:
    return {
        "asset_id": f"asset-{index:03d}",
        "asset_type": asset_type,
        "display_name": f"{asset_type} record {index:03d}",
        "aliases": [f"{asset_type} alias {index:03d}"],
        "short_description": "Metadata-only local design asset record for documentation review.",
        "organism_or_source_context": "local source context",
        "sequence_available": False,
        "sequence_hash": "",
        "sequence_hash_algorithm": "",
        "source_notes": "Local source note.",
        "provenance_status": "source review needed",
        "version_context": "seed v2.6-r43",
        "review_status": "human review needed",
        "human_review_notes": "Documentation review needed.",
        "tags": [asset_type, "documentation"],
        "documentation_boundary_note": "Documentation-only record.",
    }


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )


def test_local_design_asset_catalog_count_scopes_are_explicit(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    records = [_sample_record(index, "promoter" if index <= 12 else "tag") for index in range(1, 50)]
    monkeypatch.setattr(
        view,
        "load_local_design_asset_seed_catalog",
        lambda: {
            "metadata": {
                "seed_name": "Fixture local design asset seed",
                "seed_version": "v2.6-r43b",
                "seed_scope": "Bundled local design asset browse fixtures",
            },
            "records": records,
        },
    )
    fake_st.selectbox_values["local_design_asset_type_filter"] = "promoter"
    fake_st.selectbox_values["local_design_asset_detail_select"] = "asset-001"

    view._render_local_design_asset_catalog()
    rendered = _rendered_text(fake_st)

    assert "Bundled asset records" in rendered
    assert "Filtered table rows" in rendered
    assert "Showing 12 of 49 bundled records." in rendered
    assert "Saved bundled asset records stay separate from filtered table rows" in rendered
    assert fake_st.dataframes
    assert len(fake_st.dataframes[0]) == 12


def test_local_design_asset_catalog_renders_host_context_readback_as_recorded_context_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    records = [
        {
            **_sample_record(1, "promoter"),
            "display_name": "Plant promoter context record",
            "organism_or_source_context": "Nicotiana benthamiana plant source context",
        },
        _sample_record(2, "origin_metadata"),
    ]
    monkeypatch.setattr(
        view,
        "load_local_design_asset_seed_catalog",
        lambda: {
            "metadata": {
                "seed_name": "Fixture local design asset seed",
                "seed_version": "v2.6-r119",
                "seed_scope": "Bundled local design asset browse fixtures",
            },
            "records": records,
        },
    )
    fake_st.selectbox_values["local_design_asset_detail_select"] = "asset-001"

    view._render_local_design_asset_catalog()
    rendered = _rendered_text(fake_st)

    assert "Host / chassis context readback" in rendered
    assert "recorded source context" in rendered
    assert "normalized review context" in rendered
    assert "Plant" in rendered
    assert "not compatibility evidence" in rendered.lower()


def test_local_design_asset_catalog_missing_detail_fields_use_readable_documentation_fallbacks(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    sparse_record = {
        "asset_id": "asset-sparse-001",
        "sequence_available": False,
    }
    monkeypatch.setattr(
        view,
        "load_local_design_asset_seed_catalog",
        lambda: {
            "metadata": {
                "seed_name": "Fixture sparse local design asset seed",
                "seed_version": "v2.6-r124",
                "seed_scope": "Fallback copy regression fixture",
            },
            "records": [sparse_record],
        },
    )
    fake_st.selectbox_values["local_design_asset_detail_select"] = "asset-sparse-001"

    view._render_local_design_asset_catalog()
    rendered = _rendered_text(fake_st)
    rendered_lower = rendered.lower()

    assert "Not recorded in this documentation view" in rendered
    assert "Documentation-only metadata record for review and traceability." in rendered
    assert "鈥" not in rendered
    assert "閳" not in rendered
    assert "�" not in rendered
    assert "not a recommendation" in rendered_lower
    assert "not a validation claim" in rendered_lower
    assert "ready for execution" not in rendered_lower
    assert "experiment-ready" not in rendered_lower
    assert "validated construct" not in rendered_lower
    assert "optimized pathway" not in rendered_lower
    assert "yield prediction" not in rendered_lower


def test_generic_component_library_asset_readback_renders_existing_records_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    records = [
        _sample_record(1, "promoter"),
        _sample_record(2, "cds_target"),
        _sample_record(3, "plasmid_backbone"),
    ]

    view._render_generic_component_library_asset_readback(records)
    rendered = _rendered_text(fake_st)
    rendered_lower = rendered.lower()

    assert "Computed Component Library readback" in rendered
    assert "summarizes Local Design Asset Catalog records as computed readback rows" in rendered
    assert "does not create a universal asset database model" in rendered
    assert "Stored route, source, provenance, package, and saved-record identifiers are preserved" in rendered
    assert "Readback asset rows" in rendered
    assert "Asset type groups" in rendered
    assert fake_st.dataframes
    table = fake_st.dataframes[0]
    assert len(table) == 3
    assert set(table["Asset type"]) == {"promoter", "CDS / gene", "vector backbone"}
    assert "Documentation context note" in table.columns
    assert set(table["Documentation context note"]) == {
        "Linked catalog documentation context is not recorded for this Local Design Asset Catalog row."
    }

    assert "ready for execution" not in rendered_lower
    assert "experiment-ready" not in rendered_lower
    assert "production-ready" not in rendered_lower
    assert "validated construct" not in rendered_lower
    assert "optimized pathway" not in rendered_lower
    assert "yield prediction" not in rendered_lower
