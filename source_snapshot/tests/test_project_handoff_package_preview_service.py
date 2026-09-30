from __future__ import annotations

from services.project_handoff_package_preview_service import (
    build_project_handoff_package_preview,
    handoff_workspace_markdown,
    handoff_workspace_nav_rows,
    handoff_workspace_summary,
)


def _sample_handoff_center() -> dict[str, object]:
    return {
        "summary": {
            "total_follow_up_items": 3,
            "expression_construct_documentation_follow_up_count": 1,
            "candidate_evidence_follow_up_count": 1,
            "promoter_source_review_follow_up_count": 0,
            "host_context_documentation_follow_up_count": 1,
            "report_markdown_available": True,
        },
        "checklist": [
            {
                "label": "source/reference context reviewed",
                "status": "Follow-up visible",
                "note": "Review source records before handoff.",
            },
            {
                "label": "report markdown reviewed",
                "status": "Review available",
                "note": "Markdown summary available for copy/review only.",
            },
        ],
        "follow_up_rows": [
            {
                "source_surface": "Expression Construct documentation",
                "item_label": "Promoter A",
                "issue_type": "Missing source/reference context",
                "manual_follow_up_note": "Add documentation source context.",
                "where_to_review_next": "Review next: Expression Constructs",
            },
            {
                "source_surface": "Host / chassis documentation context",
                "item_label": "Host / chassis context",
                "issue_type": "Host/context documentation not recorded",
                "manual_follow_up_note": "Add or confirm host/context documentation notes.",
                "where_to_review_next": "Review next: Host / Chassis Context Summary",
            },
        ],
    }


def test_handoff_package_preview_is_deterministic_and_complete() -> None:
    first = build_project_handoff_package_preview(_sample_handoff_center(), project_label="Project Alpha")
    second = build_project_handoff_package_preview(_sample_handoff_center(), project_label="Project Alpha")

    assert first == second
    assert first["title"] == "Project handoff package preview"
    assert first["snapshot_title"] == "Project handoff package preview"
    assert first["snapshot_checksum_algorithm"] == "MD5"
    assert len(first["snapshot_checksum"]) == 32
    assert first["snapshot_id"] == f"md5:{first['snapshot_checksum']}"
    assert first["snapshot_included_surface_count"] == 5
    assert first["snapshot_section_count"] >= 5
    assert first["snapshot_content_length"] > 100
    assert first["snapshot_review_card"]["snapshot_checksum"] == first["snapshot_checksum"]
    assert first["snapshot_review_card"]["snapshot_manual_follow_up_count"] == 3
    assert first["snapshot_review_card"]["snapshot_included_surface_count"] == 5
    assert first["snapshot_review_card"]["snapshot_section_count"] == first["snapshot_section_count"]
    assert "preview matching only" in first["snapshot_review_card"]["boundary_note"]
    assert "not a security signature or certification" in first["snapshot_review_card"]["boundary_note"]
    assert first["qr_verification_title"] == "Handoff QR verification preview"
    assert first["qr_verification_payload"] == second["qr_verification_payload"]
    assert first["qr_verification_payload_text"] == second["qr_verification_payload_text"]
    assert first["qr_verification_payload_markdown"] == second["qr_verification_payload_markdown"]
    assert first["qr_verification_payload"]["snapshot_title"] == "Project handoff package preview"
    assert first["qr_verification_payload"]["project_label"] == "Project Alpha"
    assert first["qr_verification_payload"]["snapshot_id"] == first["snapshot_id"]
    assert first["qr_verification_payload"]["checksum_algorithm"] == "MD5"
    assert first["qr_verification_payload"]["snapshot_checksum"] == first["snapshot_checksum"]
    assert first["qr_verification_payload"]["included_surfaces_count"] == 5
    assert first["qr_verification_payload"]["manual_follow_up_count"] == 3
    assert "BioDesign Studio handoff QR verification payload" in first["qr_verification_payload_text"]
    assert "Checksum algorithm: MD5" in first["qr_verification_payload_text"]
    assert "MD5 preview checksum" in first["qr_verification_payload_text"]
    assert first["snapshot_checksum"] in first["qr_verification_payload_text"]
    assert "Included surfaces count: 5" in first["qr_verification_payload_text"]
    assert "Manual follow-up count: 3" in first["qr_verification_payload_text"]
    assert "No export package is created here." in first["qr_verification_payload_text"]
    assert "No file or download is created here." in first["qr_verification_payload_text"]
    assert "not a security signature or certification" in first["qr_verification_payload_text"]
    assert "### Handoff QR verification preview" in first["qr_verification_payload_markdown"]
    assert first["handoff_cover_summary"] == {
        "project_label": "Project Alpha",
        "total_manual_follow_up_items": 3,
        "documentation_surfaces_included": [
            "construct/component documentation summary",
            "evidence follow-up summary",
            "Component Library promoter asset source/review gap summary",
            "host/context documentation summary",
            "project review report summary",
        ],
    }
    assert len(first["included_documentation_preview"]) == 5
    assert first["handoff_checklist"]
    assert len(first["manual_follow_up_queue"]) == 2
    panel = first["expression_construct_review_action_panel"]
    assert panel["title"] == "Expression construct review action panel"
    assert panel["source_presenter"] == (
        "services.expression_construct_review_action_panel_presenter."
        "build_expression_construct_review_action_panel"
    )
    assert panel["summary"]["row_count"] == 4
    assert [row["label"] for row in panel["rows"]] == [
        "Missing documentation",
        "Needs manual follow-up",
        "Source/provenance review",
        "Boundary note",
    ]
    assert panel["action_summary"] == {
        "title": "Action summary",
        "row_count": 4,
        "readback_note": (
            "Consolidated readback for package preview, review sheet, and traceability review."
        ),
        "rows": [
            {
                "label": row["label"],
                "summary": (
                    f"{row['status']}; count {row['count']}; "
                    f"{row['review_action']}; boundary: {row['boundary_note']}"
                ),
                "traceability_context": (
                    f"{row['label']}: {row['status']}; count {row['count']}; "
                    f"{row['review_action']}"
                ),
            }
            for row in panel["rows"]
        ],
    }
    assert "read-only handoff readback reused" in panel["note"].lower()
    assert "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment" in panel["boundary_note"]
    assert "## Project handoff package preview" in first["markdown_handoff_preview"]
    assert first["output_sections_overview"]["title"] == "Output sections overview"
    assert first["output_sections_overview"]["section_count"] == 7
    assert any(
        row["section_name"] == "Handoff Review / package preview"
        for row in first["output_sections_overview"]["rows"]
    )
    assert "## Output sections overview" in first["markdown_handoff_preview"]
    assert "| Section | Status | Count | Inspect next |" in first["markdown_handoff_preview"]
    assert "### Included documentation preview" in first["markdown_handoff_preview"]
    assert "### Handoff checklist" in first["markdown_handoff_preview"]
    assert "### Manual follow-up queue" in first["markdown_handoff_preview"]
    assert "### Expression construct review action panel" in first["markdown_handoff_preview"]
    assert "- Action summary: 4 review-framed row(s)." in first["markdown_handoff_preview"]
    assert "Consolidated readback for package preview, review sheet, and traceability review." in first[
        "markdown_handoff_preview"
    ]
    assert "| Action row | Status | Count | Review action | Boundary |" in first["markdown_handoff_preview"]
    assert "### Handoff snapshot review card" in first["markdown_handoff_preview"]
    assert "Checksum algorithm: MD5" in first["markdown_handoff_preview"]
    assert first["snapshot_checksum"] in first["markdown_handoff_preview"]
    assert "No export package is created here." in first["markdown_handoff_preview"]
    assert first["review_sheet_boundary_note"] == (
        "Read-only review sheet copy view for documentation handoff review; "
        "no export package is created here and no file is generated here."
    )
    assert [section["key"] for section in first["review_sheet_sections"]] == [
        "snapshot_review_card",
        "handoff_summary",
        "handoff_checklist",
        "manual_follow_up_queue",
        "expression_construct_review_action_panel",
        "traceability_matrix",
        "qr_verification_preview",
        "markdown_copy_view",
        "plain_text_copy_view",
    ]
    assert first["traceability_matrix_rows"] == second["traceability_matrix_rows"]
    assert first["traceability_matrix_summary"] == second["traceability_matrix_summary"]
    assert first["traceability_matrix_markdown"] == second["traceability_matrix_markdown"]
    assert first["traceability_matrix_plain_text"] == second["traceability_matrix_plain_text"]
    assert first["traceability_matrix_summary"]["row_count"] == len(first["traceability_matrix_rows"])
    assert first["traceability_matrix_summary"]["included_in_review_sheet_count"] == len(
        first["traceability_matrix_rows"]
    )
    assert first["traceability_matrix_summary"]["by_source_surface"]["Expression Constructs"] >= 1
    assert first["traceability_matrix_summary"]["by_source_surface"]["Host/context documentation"] >= 1
    assert first["traceability_matrix_summary"]["by_source_surface"]["Handoff Review Sheet"] >= 1
    assert any(row["item_label"] == "Missing documentation" for row in first["traceability_matrix_rows"])
    assert any(
        row["included_in_review_sheet"] == "Yes - included in review sheet expression construct action panel"
        for row in first["traceability_matrix_rows"]
    )
    matrix_row = first["traceability_matrix_rows"][0]
    assert set(matrix_row) == {
        "source_surface",
        "item_label",
        "documentation_context",
        "source_reference_context",
        "provenance_review_context",
        "manual_follow_up_status",
        "where_to_review_next",
        "included_in_review_sheet",
    }
    assert any(row["where_to_review_next"] == "Review next: Expression Constructs" for row in first["traceability_matrix_rows"])
    assert any("review sheet" in row["included_in_review_sheet"].lower() for row in first["traceability_matrix_rows"])
    assert first["review_sheet_markdown"] == second["review_sheet_markdown"]
    assert first["review_sheet_plain_text"] == second["review_sheet_plain_text"]
    assert "## Project handoff review sheet" in first["review_sheet_markdown"]
    assert "### Snapshot review card" in first["review_sheet_markdown"]
    assert "### Handoff summary" in first["review_sheet_markdown"]
    assert "### Handoff checklist" in first["review_sheet_markdown"]
    assert "### Manual follow-up queue" in first["review_sheet_markdown"]
    assert "### Expression construct review action panel" in first["review_sheet_markdown"]
    assert "### Project handoff traceability matrix" in first["review_sheet_markdown"]
    assert "### Handoff QR verification preview" in first["review_sheet_markdown"]
    assert "### Copy view boundary" in first["review_sheet_markdown"]
    assert "Project handoff review sheet" in first["review_sheet_plain_text"]
    assert "Snapshot review card" in first["review_sheet_plain_text"]
    assert "Handoff summary" in first["review_sheet_plain_text"]
    assert "Handoff checklist" in first["review_sheet_plain_text"]
    assert "Manual follow-up queue" in first["review_sheet_plain_text"]
    assert "Expression construct review action panel" in first["review_sheet_plain_text"]
    assert "Action summary: 4 review-framed row(s)." in first["review_sheet_plain_text"]
    assert "Project handoff traceability matrix" in first["review_sheet_plain_text"]
    assert "Handoff QR verification preview" in first["review_sheet_plain_text"]
    assert "Copy view boundary" in first["review_sheet_plain_text"]
    assert first["snapshot_checksum"] in first["review_sheet_markdown"]
    assert first["snapshot_checksum"] in first["review_sheet_plain_text"]
    assert "construct/component documentation summary" in first["review_sheet_markdown"]
    assert "construct/component documentation summary" in first["review_sheet_plain_text"]
    assert "Current manual follow-up item count: 3" in first["review_sheet_markdown"]
    assert "Current manual follow-up item count: 3" in first["review_sheet_plain_text"]
    assert "source/reference context reviewed" in first["review_sheet_markdown"]
    assert "source/reference context reviewed" in first["review_sheet_plain_text"]
    assert "| Source surface | Item label | Documentation context | Source/reference context | Provenance/review context | Manual follow-up status | Review next | Included in review sheet |" in first["traceability_matrix_markdown"]
    assert "Manual documentation follow-up" in first["traceability_matrix_markdown"]
    assert (
        "Missing documentation: No missing documentation count visible in current payload; count 0"
        in first["traceability_matrix_markdown"]
    )
    assert "Included in review sheet" in first["traceability_matrix_plain_text"]
    assert "No export package is created here." in first["review_sheet_markdown"]
    assert "No file is generated here." in first["review_sheet_markdown"]
    assert "No export package is created here." in first["review_sheet_plain_text"]
    assert "No file is generated here." in first["review_sheet_plain_text"]
    assert first["handoff_workspace_nav_rows"] == second["handoff_workspace_nav_rows"]
    assert first["handoff_workspace_summary"] == second["handoff_workspace_summary"]
    assert first["handoff_workspace_markdown"] == second["handoff_workspace_markdown"]
    assert first["handoff_workspace_nav_rows"] == handoff_workspace_nav_rows(first)
    assert first["handoff_workspace_summary"] == handoff_workspace_summary(first)
    assert first["handoff_workspace_markdown"] == handoff_workspace_markdown(first)
    assert first["handoff_workspace_summary"] == {
        "title": "Project handoff review workspace",
        "status": "AVAILABLE",
        "workspace_area_count": 6,
        "total_manual_follow_up_items": 3,
        "included_documentation_surface_count": 5,
        "traceability_matrix_row_count": len(first["traceability_matrix_rows"]),
        "snapshot_checksum": first["snapshot_checksum"],
        "qr_payload_status": "AVAILABLE",
        "boundary_note": (
            "This workspace organizes local, read-only, documentation-only review surfaces for manual review. "
            "It does not create files, packages, exports, biology-use recommendations, validation claims, "
            "optimization claims, or wet-lab use judgments."
        ),
    }
    workspace_rows = first["handoff_workspace_nav_rows"]
    assert [row["workspace_area"] for row in workspace_rows] == [
        "Handoff Center",
        "Package Preview",
        "Snapshot / MD5 / QR Payload",
        "Review Sheet Copy View",
        "Traceability Matrix",
        "Project Review Report Markdown",
    ]
    for row in workspace_rows:
        assert set(row) == {
            "workspace_area",
            "current_status",
            "key_count_or_identity",
            "review_surface",
            "where_to_inspect_next",
            "boundary_note",
        }
        assert row["current_status"]
        assert row["key_count_or_identity"]
        assert row["review_surface"]
        assert row["where_to_inspect_next"]
        assert row["boundary_note"]
    assert "3 manual follow-up item(s)" in workspace_rows[0]["key_count_or_identity"]
    assert "5 included documentation surface(s)" in workspace_rows[1]["key_count_or_identity"]
    assert first["snapshot_checksum"] in workspace_rows[2]["key_count_or_identity"]
    assert first["snapshot_id"] in workspace_rows[2]["key_count_or_identity"]
    assert "QR payload preview available" in workspace_rows[2]["current_status"]
    assert "Markdown copy view available" in workspace_rows[3]["current_status"]
    assert "Plain-text copy view available" in workspace_rows[3]["current_status"]
    assert f"{len(first['traceability_matrix_rows'])} matrix row(s)" in workspace_rows[4]["key_count_or_identity"]
    assert "Markdown available" in workspace_rows[5]["current_status"]
    assert "## Project handoff review workspace" in first["handoff_workspace_markdown"]
    assert "| Workspace area | Current status | Key count or identity | Review surface | Where to inspect next | Boundary note |" in first["handoff_workspace_markdown"]
    assert "Handoff Center" in first["handoff_workspace_markdown"]
    assert "Package Preview" in first["handoff_workspace_markdown"]
    assert "Snapshot / MD5 / QR Payload" in first["handoff_workspace_markdown"]
    assert "Review Sheet Copy View" in first["handoff_workspace_markdown"]
    assert "Traceability Matrix" in first["handoff_workspace_markdown"]
    assert "Project Review Report Markdown" in first["handoff_workspace_markdown"]
    assert first["snapshot_checksum"] in first["handoff_workspace_markdown"]
    assert "MD5/QR payload for preview matching only" in first["handoff_workspace_markdown"]
    assert "no export package is created here" in first["handoff_workspace_markdown"].lower()
    assert "no file or download is created here" in first["handoff_workspace_markdown"].lower()


def test_handoff_qr_verification_payload_excludes_sequence_paths_and_secrets() -> None:
    preview = build_project_handoff_package_preview(
        _sample_handoff_center(),
        project_label="ATGCGTATGCGTATGCGTATGCGTATGCGT C:\\Users\\ASUS\\secret API key token",
    )

    payload_text = preview["qr_verification_payload_text"]

    assert "ATGCGTATGCGTATGCGTATGCGTATGCGT" not in payload_text
    assert "C:\\Users\\ASUS" not in payload_text
    assert "API key" not in payload_text
    assert "token" not in payload_text
    assert "WITHHELD_FOR_PREVIEW_METADATA_BOUNDARY" in payload_text
    assert preview["snapshot_checksum"] in payload_text
    assert "No export package is created here." in payload_text


def test_handoff_package_preview_checksum_changes_when_preview_content_changes() -> None:
    first = build_project_handoff_package_preview(_sample_handoff_center(), project_label="Project Alpha")
    changed_handoff = _sample_handoff_center()
    changed_handoff["summary"] = {
        **changed_handoff["summary"],
        "total_follow_up_items": 4,
    }
    changed_handoff["follow_up_rows"] = [
        *changed_handoff["follow_up_rows"],
        {
            "source_surface": "Candidate evidence documentation",
            "item_label": "Candidate source note",
            "issue_type": "Missing provenance context",
            "manual_follow_up_note": "Add source/provenance note for documentation review.",
            "where_to_review_next": "Review next: Candidate Evidence Review Matrix",
        },
    ]

    second = build_project_handoff_package_preview(changed_handoff, project_label="Project Alpha")

    assert first["snapshot_checksum"] != second["snapshot_checksum"]
    assert first["snapshot_id"] != second["snapshot_id"]
    assert second["snapshot_review_card"]["snapshot_manual_follow_up_count"] == 4


def test_handoff_package_preview_normalizes_generated_boundary_claims_before_checksum() -> None:
    unsafe_handoff = _sample_handoff_center()
    unsafe_handoff["follow_up_rows"] = [
        *unsafe_handoff["follow_up_rows"],
        {
            "source_surface": "Host compatibility readback",
            "item_label": "Compatible host note",
            "issue_type": "Compatibility proof",
            "manual_follow_up_note": "Host readiness review.",
            "where_to_review_next": "Review next: Host compatibility report",
        },
    ]

    first = build_project_handoff_package_preview(unsafe_handoff, project_label="Recommended host project")
    second = build_project_handoff_package_preview(unsafe_handoff, project_label="Recommended host project")
    text = str(first).lower()

    assert first == second
    assert first["snapshot_checksum"] == second["snapshot_checksum"]
    for unsafe in [
        "host compatibility",
        "compatible host",
        "compatibility proof",
        "host readiness",
        "recommended host",
    ]:
        assert unsafe not in text
    assert "host/context documentation" in text
    assert "host context note" in text


def test_handoff_package_preview_frames_missing_documentation_as_manual_follow_up() -> None:
    preview = build_project_handoff_package_preview(_sample_handoff_center(), project_label="")

    assert preview["handoff_cover_summary"]["project_label"] == "Active pathway documentation project"
    queue_text = str(preview["manual_follow_up_queue"]).lower()
    assert "missing source/reference context" in queue_text
    assert "host/context documentation not recorded" in queue_text
    assert "manual follow-up" in preview["markdown_handoff_preview"].lower()
    assert "manual documentation follow-up" in preview["traceability_matrix_markdown"].lower()


def test_handoff_package_preview_does_not_copy_placeholder_status_as_recorded_context() -> None:
    handoff = _sample_handoff_center()
    handoff["summary"] = {
        **handoff["summary"],
        "total_follow_up_items": 1,
        "expression_construct_documentation_follow_up_count": 0,
        "candidate_evidence_follow_up_count": 0,
        "host_context_documentation_follow_up_count": 1,
    }
    handoff["follow_up_rows"] = [
        {
            "source_surface": "Host / chassis documentation context",
            "item_label": "Host placeholder",
            "issue_type": "Host/context documentation not recorded",
            "manual_follow_up_note": "TBD",
            "where_to_review_next": "Review next: Host / Chassis Context Summary",
        }
    ]

    preview = build_project_handoff_package_preview(handoff, project_label="N/A")

    assert preview["handoff_cover_summary"]["project_label"] == "Active pathway documentation project"
    host_rows = [
        row for row in preview["traceability_matrix_rows"] if row["item_label"] == "Host placeholder"
    ]
    assert host_rows
    assert host_rows[0]["manual_follow_up_status"] == (
        "Manual documentation follow-up is visible for this item."
    )
    assert "TBD" not in preview["traceability_matrix_markdown"]
    assert "Project label: Active pathway documentation project" in preview["qr_verification_payload_text"]


def test_handoff_package_preview_copy_stays_read_only_and_bounded() -> None:
    text = str(build_project_handoff_package_preview(_sample_handoff_center())).lower()

    assert "read-only preview" in text
    assert "read-only review sheet copy view" in text
    assert "read-only qr verification payload" in text
    assert "package preview only" in text
    assert "no export package is created here" in text
    assert "no file is generated here" in text
    assert "no file or download is created here" in text
    assert "md5 code" not in text or "preview matching only" in text
    assert "not a security signature or certification" in text
    assert "review-only documentation handoff review; not a downstream-use assessment" in text
    assert "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment" in text
    for forbidden in [
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "wet-lab ready",
        "build-ready",
        "recommended package",
        "best construct",
        "protocol package",
        "build package",
    ]:
        assert forbidden not in text
