from __future__ import annotations

from services.project_review_handoff_center_service import build_project_review_handoff_center


def _component_record(
    asset_id: str,
    asset_type: str,
    display_name: str,
    *,
    provenance_status: str = "source reviewed",
    review_status: str = "human reviewed",
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "asset_display_name": display_name,
        "source_notes": "Recorded source/provenance note.",
        "provenance_status": provenance_status,
        "review_status": review_status,
        "documentation_boundary_note": "Documentation-only metadata record for review and traceability.",
    }


def test_handoff_center_aggregates_existing_review_queues() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={
            "summary": {
                "total_component_rows": 2,
                "rows_needing_manual_follow_up": 1,
            },
            "rows": [
                {
                    "Construct label": "Construct A",
                    "Cassette label": "Cassette A",
                    "Component label": "Promoter A",
                    "Issue type": "Missing source/reference context",
                    "Manual follow-up note": "Add documentation source context.",
                }
            ],
        },
        candidate_queue={
            "summary": {"queue_item_count": 2},
            "rows": [
                {
                    "queue_item_id": "candidate-review-001-01",
                    "candidate_label": "Candidate A",
                    "category_label": "Source/provenance gap",
                    "issue": "Missing source/provenance details",
                    "human_follow_up": "Record source context.",
                    "source_context": "Catalog / C-001",
                }
            ],
        },
        promoter_queue={
            "summary_counts": {"queue_item_count": 3},
            "rows": [
                {
                    "queue_item_id": "promoter-a::metadata_gap",
                    "promoter_label": "Promoter A",
                    "category": "metadata_gap",
                    "issue": "Metadata gap remains visible.",
                    "human_follow_up": "Complete recorded metadata fields.",
                    "source_context": "Plant Promoter Catalog",
                }
            ],
        },
        host_chassis_context={
            "rows": [
                {
                    "source_label": "Active project host field",
                    "source_value": "Not set",
                    "asset_display_name": "Project A",
                }
            ]
        },
        report_markdown_available=True,
    )

    summary = handoff["summary"]
    assert handoff["title"] == "Project review handoff center"
    assert summary["total_follow_up_items"] == 7
    assert summary["expression_construct_documentation_follow_up_count"] == 1
    assert summary["candidate_evidence_follow_up_count"] == 2
    assert summary["promoter_source_review_follow_up_count"] == 3
    assert summary["host_context_documentation_follow_up_count"] == 1
    assert summary["report_markdown_available"] is True
    assert any(row["source_surface"] == "Expression Construct documentation" for row in handoff["follow_up_rows"])
    assert any(row["source_surface"] == "Candidate Evidence Human Review Queue" for row in handoff["follow_up_rows"])
    assert any(
        row["source_surface"] == "Component Library Promoter Asset Evidence Gap Review"
        for row in handoff["follow_up_rows"]
    )
    assert any(row["source_surface"] == "Host / chassis documentation context" for row in handoff["follow_up_rows"])
    assert "## Project review handoff center" in handoff["markdown"]
    assert "| Source surface | Item label | Issue type | Manual follow-up note | Review next |" in handoff["markdown"]


def test_handoff_center_empty_state_is_read_only_and_bounded() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        report_markdown_available=False,
    )

    assert handoff["status"] == "NOT_AVAILABLE"
    assert handoff["summary"]["total_follow_up_items"] == 0
    assert handoff["follow_up_rows"] == []
    assert "No project review handoff follow-up items" in handoff["empty_state_message"]
    assert "Review next: open the Project Review Follow-up Index or the handoff review sheet" in handoff["empty_state_message"]
    text = str(handoff).lower()
    assert "documentation-only" in text
    for forbidden in [
        "recommended",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "ready for " + "execution",
        "experiment-" + "ready",
        "production-" + "ready",
        "wet-lab " + "ready",
    ]:
        assert forbidden not in text


def test_handoff_center_treats_placeholder_host_context_as_follow_up() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={
            "rows": [
                {
                    "source_label": "Active project host field",
                    "source_value": "Unknown",
                    "asset_display_name": "Placeholder project",
                },
                {
                    "source_label": "Linked host / chassis context reference",
                    "source_value": "N/A",
                    "asset_display_name": "Placeholder linked row",
                },
            ]
        },
        report_markdown_available=False,
    )

    assert handoff["summary"]["host_context_documentation_follow_up_count"] == 2
    assert handoff["summary"]["total_follow_up_items"] == 2
    assert [row["issue_type"] for row in handoff["follow_up_rows"]] == [
        "Host/context documentation not recorded",
        "Host/context documentation not recorded",
    ]


def test_handoff_center_normalizes_generated_host_context_follow_up_rows() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        follow_up_index={
            "summary": {"source_section_counts": {"candidate_evidence": 0, "plant_promoter_catalog": 0}},
            "rows": [
                {
                    "source_section": "host_context",
                    "source_title": "Host compatibility notes",
                    "item_label": "Compatible host row",
                    "category": "Compatibility proof",
                    "human_follow_up": "Review host readiness wording.",
                }
            ],
        },
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        report_markdown_available=True,
    )

    text = str(handoff).lower()
    assert "host compatibility" not in text
    assert "compatible host" not in text
    assert "compatibility proof" not in text
    assert "host readiness" not in text
    assert "host/context documentation" in text


def test_handoff_center_includes_step2_component_context_appendix_without_counting_it_as_gap() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        step2_component_context_appendix={
            "status": "AVAILABLE",
            "rows": [
                {
                    "Step 2 context category": "promoter",
                    "Step 2 recorded value": "T7 promoter review label",
                    "Component Library asset": "T7 promoter documentation record / promoter-r242",
                    "Source/provenance review": "source review needed",
                    "Record review status": "record review pending",
                    "Sequence metadata": "sequence metadata recorded",
                    "Manual follow-up": "Review source/provenance review before citing in project notes.",
                }
            ],
            "summary": {
                "total_rows": 1,
                "rows_with_recorded_assets": 1,
                "manual_follow_up_rows": 0,
            },
            "total_rows_available": 1,
            "documentation_boundary_note": (
                "Read-only review appendix; not saved as construct evidence and not a biological recommendation."
            ),
        },
        report_markdown_available=False,
    )

    assert handoff["summary"]["total_follow_up_items"] == 0
    assert handoff["step2_component_context_appendix"]["status"] == "AVAILABLE"
    assert "Step 2 recorded Component Library context appendix" in handoff["markdown"]
    assert "Read-only review appendix" in handoff["markdown"]
    assert "T7 promoter documentation record / promoter-r242" in handoff["markdown"]


def test_handoff_center_includes_component_library_source_provenance_readback() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        component_library_records=[
            _component_record(
                "prom-r304",
                "promoter",
                "R304 promoter component record",
                provenance_status="",
                review_status="human review needed",
            ),
            _component_record(
                "backbone-r304",
                "plasmid_backbone",
                "R304 vector backbone record",
            ),
        ],
        report_markdown_available=False,
    )

    readback = handoff["component_library_source_provenance_readback"]
    assert readback["title"] == "Component Library source/provenance readback"
    assert readback["reused_presenter"].endswith("build_component_library_slot_browse_presenter")
    assert readback["summary"]["slot_rows_with_records"] >= 2
    assert readback["summary"]["source_follow_up_slot_count"] >= 1
    assert readback["summary"]["manual_follow_up_slot_count"] >= 1
    assert any(row["Slot"] == "Plant promoter context" for row in readback["rows"])
    assert any(row["Slot"] == "Vector / backbone context" for row in readback["rows"])
    assert any(row["Slot"] == "Manual Follow-up" for row in readback["rows"])
    assert any("R304 promoter component record" in row["Records"] for row in readback["rows"])
    assert any("Source/provenance missing" in row["Source/provenance status"] for row in readback["rows"])
    assert any("Manual follow-up needed" in row["Manual follow-up"] for row in readback["rows"])
    assert "This section does not choose components or validate the design." in readback["intro"]
    assert "Component Library source/provenance readback" in handoff["markdown"]
    assert "R304 vector backbone record" in handoff["markdown"]
    text = str(readback).casefold()
    for forbidden in [
        "best promoter",
        "best host",
        "best vector",
        "optimized sequence",
        "ready-to-clone",
        "cloning protocol",
        "yield prediction",
        "experimentally validated",
    ]:
        assert forbidden not in text


def test_handoff_center_component_library_readback_empty_state_is_read_only() -> None:
    handoff = build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        component_library_records=[],
        report_markdown_available=False,
    )

    readback = handoff["component_library_source_provenance_readback"]
    assert readback["status"] == "NOT_AVAILABLE"
    assert readback["rows"] == []
    assert "No Component Library records are available for Handoff Review yet." in readback["empty_state"]
    assert "read-only source/provenance readback" in readback["empty_state"]
    assert readback["summary"] == {
        "slot_row_count": 0,
        "slot_rows_with_records": 0,
        "source_follow_up_slot_count": 0,
        "manual_follow_up_slot_count": 0,
    }
    assert "No Component Library records are available for Handoff Review yet." in handoff["markdown"]
