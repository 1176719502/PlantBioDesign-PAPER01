from __future__ import annotations

from services.expression_vector_package_record_input_adapter import (
    CURRENT_RECORD_SOURCE,
    EMPTY_RECORD_SOURCE,
    LEARNING_SAMPLE_SOURCE,
    SOURCE_READBACK_COLUMNS,
    build_expression_vector_package_source_readback_rows,
    build_expression_vector_package_record_input,
)


def test_record_input_adapter_uses_current_project_fields_before_sample() -> None:
    result = build_expression_vector_package_record_input(
        project={
            "name": "Carotenoid review case",
            "target_gene": "crtI documentation target",
            "source_reference": "Manual source/provenance note",
            "host": "E. coli BL21(DE3) documentation context",
            "vector_backbone": "pET backbone documentation context",
        },
        steps=[{"name": "Sequence source review"}],
        linked_catalog_assets=[],
        handoff_preview={"snapshot_review_card": {"snapshot_id": "handoff-md5:abc"}},
        expression_construct_views=[],
    )

    assert result["record_source"] == CURRENT_RECORD_SOURCE
    assert result["has_current_record"] is True
    assert result["learning_sample_source"] == LEARNING_SAMPLE_SOURCE

    preview = result["preview"]
    assert preview["target_summary"]["target_name"] == "crtI documentation target"
    assert preview["target_summary"]["source_or_provenance"] == "Manual source/provenance note"
    assert preview["host_summary"]["host_or_system"] == "E. coli BL21(DE3) documentation context"
    assert preview["vector_backbone_summary"]["vector_or_backbone_name"] == "pET backbone documentation context"
    assert preview["package_identity"]["source_commit_or_version"] == "handoff-md5:abc"
    assert "sample-enzyme-1" not in str(preview)

    rows = result["source_readback_rows"]
    assert result["source_readback_columns"] == SOURCE_READBACK_COLUMNS
    assert rows == build_expression_vector_package_source_readback_rows(result)
    assert [row["Preview field"] for row in rows] == [
        "Target Gene / CDS / Protein",
        "Expression Host",
        "Promoter",
        "CDS / Insert",
        "Vector / Backbone",
        "Sequence Basic Checks",
        "Manual Follow-up",
    ]
    target_row = rows[0]
    assert target_row["Current value"] == "crtI documentation target"
    assert target_row["Source/readback origin"] == "current record"
    assert target_row["Source/provenance status"] == "needs review"
    assert "confirm target gene / CDS / protein source" in target_row["Follow-up"]

    promoter_row = rows[2]
    assert promoter_row["Preview field"] == "Promoter"
    assert promoter_row["Current value"] == "Missing"
    assert promoter_row["Source/readback origin"] == "not provided"
    assert promoter_row["Source/provenance status"] == "missing"


def test_record_input_adapter_empty_state_when_only_project_name_exists() -> None:
    result = build_expression_vector_package_record_input(
        project={"id": 280, "name": "Only project container"},
        steps=[],
        linked_catalog_assets=[],
        handoff_preview={},
        expression_construct_views=[],
    )

    assert result["record_source"] == EMPTY_RECORD_SOURCE
    assert result["has_current_record"] is False
    assert result["preview"] is None
    assert "No current expression vector record is available yet" in result["empty_state"]
    assert "Expression Wizard" in result["next_step"]
    assert result["source_summary"]["construct_profile_rows"] == 0
    assert result["source_summary"]["cassette_part_rows"] == 0

    rows = result["source_readback_rows"]
    assert len(rows) == 7
    assert {row["Source/readback origin"] for row in rows} == {"missing"}
    assert rows[0]["Preview field"] == "Target Gene / CDS / Protein"
    assert rows[0]["Current value"] == "Missing"
    assert rows[0]["Source/provenance status"] == "missing"
    assert "Start from Expression Wizard" in rows[0]["Follow-up"]
    assert rows[-1]["Preview field"] == "Manual Follow-up"
    assert rows[-1]["Source/provenance status"] == "needs manual review"


def test_record_input_adapter_maps_construct_rows_and_keeps_source_gaps_manual() -> None:
    result = build_expression_vector_package_record_input(
        project={"name": "Construct-only project"},
        expression_construct_views=[
            {
                "construct_profile_rows": [
                    {
                        "construct_id": "construct-280",
                        "construct_label": "Construct 280",
                        "plasmid_backbone": "Backbone label from construct row",
                        "host_context_note": "Host context from construct row",
                        "source_reference": "Construct source record",
                        "provenance_note": "Reviewer note",
                    }
                ],
                "cassette_rows": [
                    {
                        "cassette_id": "cassette-280",
                        "cassette_label": "Cassette 280",
                        "promoter_label": "Promoter label",
                        "gene_label": "crtI label",
                    }
                ],
                "cassette_part_rows": [
                    {
                        "part_role": "promoter",
                        "part_label": "Promoter context without source",
                        "source_reference": "",
                        "provenance_note": "",
                    },
                    {
                        "part_role": "cds",
                        "part_label": "crtI CDS component",
                        "source_reference": "Manual CDS source note",
                        "provenance_note": "Reviewed as documentation context",
                    },
                ],
            }
        ],
    )

    assert result["record_source"] == CURRENT_RECORD_SOURCE
    preview = result["preview"]
    assert preview["host_summary"]["host_or_system"] == "Host context from construct row"
    assert preview["vector_backbone_summary"]["vector_or_backbone_name"] == "Backbone label from construct row"
    assert result["source_summary"]["cassette_part_rows"] == 2
    assert result["source_summary"]["linked_slot_rows"] == 2

    gap_text = str(preview["gap_follow_up_summary"])
    assert "Manual follow-up" in gap_text
    assert "record component source/provenance context" in gap_text
    assert "Promoter context without source" in str(preview["cassette_slot_rows"])
    assert "sample-enzyme-1" not in str(preview)

    rows = result["source_readback_rows"]
    host_row = next(row for row in rows if row["Preview field"] == "Expression Host")
    vector_row = next(row for row in rows if row["Preview field"] == "Vector / Backbone")
    promoter_row = next(row for row in rows if row["Preview field"] == "Promoter")
    insert_row = next(row for row in rows if row["Preview field"] == "CDS / Insert")
    manual_row = next(row for row in rows if row["Preview field"] == "Manual Follow-up")

    assert host_row["Current value"] == "Host context from construct row"
    assert vector_row["Current value"] == "Backbone label from construct row"
    assert promoter_row["Current value"] == "Promoter context without source"
    assert promoter_row["Source/readback origin"] == "current record cassette slot"
    assert promoter_row["Source/provenance status"] == "needs source/provenance"
    assert insert_row["Current value"] == "crtI CDS component"
    assert insert_row["Source/provenance status"] == "documented"
    assert manual_row["Current value"].endswith("follow-up row(s)")
    assert manual_row["Source/readback origin"] == "current record gap summary"
