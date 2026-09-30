# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services import expression_construct_repository as repo
from services import expression_wizard_construct_bridge as bridge


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_wizard_construct_bridge.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _wizard_state(**overrides) -> DesignSession:
    data = {
        "gene_name": "crtI",
        "original_seq": "ATGAAATTTTAA",
        "optimized_seq": "ATGAAATTTTAA",
        "host": "E.coli BL21(DE3)",
        "elements": {
            "promoter_name": "T7 Promoter",
            "promoter_seq": "TAATACGACTCACTATA",
            "rbs_name": "B0034 RBS",
            "rbs_seq": "AAAGAGGAGAAA",
            "terminator_name": "rrnB T1",
            "terminator_seq": "TGCCTGGCGGCAGTAG",
        },
    }
    data.update(overrides)
    return DesignSession(**data)


def test_bridge_maps_wizard_fields_to_ordered_cassette_part_rows():
    rows = bridge.build_cassette_rows_from_wizard_state(_wizard_state())

    assert [row["part_order"] for row in rows] == [1, 2, 3, 4]
    assert [row["part_role"] for row in rows] == ["promoter", "rbs", "cds", "terminator"]
    assert [row["part_label"] for row in rows] == [
        "T7 Promoter",
        "B0034 RBS",
        "crtI",
        "rrnB T1",
    ]
    assert all(row["source_reference"].startswith("Expression Wizard current design record") for row in rows)


def test_bridge_prefers_frame_parts_when_present():
    ds = _wizard_state(
        frame={
            "success": True,
            "parts": [
                {"name": "Pdoc", "type": "promoter", "seq": "AAA"},
                {"name": "Kozak", "type": "Kozak", "seq": "CCC"},
                {"name": "Target Gene (CDS)", "type": "CDS", "seq": "ATGTAA"},
                {"name": "Tdoc", "type": "terminator", "seq": "GGG"},
            ],
        }
    )

    rows = bridge.build_cassette_rows_from_wizard_state(ds)

    assert [row["part_role"] for row in rows] == ["promoter", "rbs", "cds", "terminator"]
    assert [row["part_label"] for row in rows] == ["Pdoc", "Kozak", "Target Gene (CDS)", "Tdoc"]


def test_blank_wizard_fields_are_safe_documentation_rows():
    rows = bridge.build_cassette_rows_from_wizard_state(DesignSession())

    assert [row["part_role"] for row in rows] == ["promoter", "rbs", "cds", "terminator"]
    assert rows[0]["part_label"] == "No promoter label recorded"
    assert rows[1]["part_label"] == "No RBS or 5' UTR label recorded"
    assert rows[2]["part_label"] == "No CDS or gene label recorded"
    assert rows[3]["part_label"] == "No terminator label recorded"


def test_save_wizard_draft_into_existing_construct_reads_back_cassette(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = repo.create_construct_profile(construct_label="Existing construct")

    result = bridge.save_wizard_draft_to_construct(
        _wizard_state(),
        construct_id=profile["construct_id"],
        cassette_label="crtI cassette",
    )

    cassettes = repo.list_construct_cassettes(profile["construct_id"])
    parts = repo.list_construct_cassette_parts(result.cassette["cassette_id"])

    assert result.construct["construct_id"] == profile["construct_id"]
    assert result.cassette["cassette_label"] == "crtI cassette"
    assert [row["cassette_id"] for row in cassettes] == [result.cassette["cassette_id"]]
    assert [row["part_role"] for row in parts] == ["promoter", "rbs", "cds", "terminator"]
    assert parts[0]["source_catalog"] == ""
    assert parts[0]["source_record_id"] == ""
    assert parts[0]["source_record_label"] == ""


def test_create_new_construct_from_wizard_draft(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    result = bridge.save_wizard_draft_to_construct(
        _wizard_state(),
        create_new_construct=True,
        new_construct_label="Wizard construct",
        cassette_label="Wizard cassette",
    )

    assert result.construct["construct_label"] == "Wizard construct"
    assert result.cassette["construct_id"] == result.construct["construct_id"]
    assert result.cassette["cassette_label"] == "Wizard cassette"
    assert len(result.cassette_parts) == 4


def test_gene_link_is_created_only_when_gene_label_exists(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    with_gene = bridge.save_wizard_draft_to_construct(
        _wizard_state(gene_name="crtI"),
        create_new_construct=True,
        cassette_label="With gene",
    )
    without_gene = bridge.save_wizard_draft_to_construct(
        DesignSession(elements={}),
        create_new_construct=True,
        cassette_label="Without gene",
    )

    assert with_gene.gene_link["gene_label"] == "crtI"
    assert without_gene.gene_link == {}
    assert repo.list_construct_gene_links(with_gene.construct["construct_id"])
    assert repo.list_construct_gene_links(without_gene.construct["construct_id"]) == []


def test_pathway_step_link_is_deferred_without_context(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    result = bridge.save_wizard_draft_to_construct(
        _wizard_state(),
        create_new_construct=True,
        cassette_label="Deferred pathway cassette",
    )

    assert result.pathway_link_deferred is True
    assert "deferred" in result.pathway_link_note.lower()
    assert repo.list_construct_pathway_step_links(result.construct["construct_id"]) == []


def test_pathway_step_link_records_existing_context(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    result = bridge.save_wizard_draft_to_construct(
        _wizard_state(),
        create_new_construct=True,
        cassette_label="Pathway context cassette",
        pathway_context={
            "source": "pathway_workspace",
            "step_id": 42,
            "step_name": "Precursor supply",
        },
    )

    pathway_links = repo.list_construct_pathway_step_links(result.construct["construct_id"])
    assert result.pathway_link_deferred is False
    assert pathway_links[0]["pathway_step_id"] == "42"
    assert pathway_links[0]["pathway_step_label"] == "Precursor supply"


def test_bridge_copy_stays_documentation_only():
    combined = "\n".join(
        [
            bridge.CONSTRUCT_TYPE,
            bridge.CASSETTE_ROLE,
            bridge.SOURCE_REFERENCE,
            bridge.PROVENANCE_NOTE,
            bridge.PATHWAY_LINK_DEFERRED_NOTE,
        ]
    ).lower()
    forbidden = [
        "best promoter",
        "scoring",
        "ranking",
        "validated",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_expression_wizard_page_imports_and_bridge_ui_labels_exist():
    import views.ExpressionWizard as expression_wizard_page
    import views.wizard_steps.step6_export as step6

    source = open(step6.__file__, encoding="utf-8").read()

    assert hasattr(expression_wizard_page, "render")
    assert "Save to Expression Construct" in source
    assert "Save cassette documentation to construct" in source
    assert "Cassette label" in source
