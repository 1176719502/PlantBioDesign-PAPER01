from __future__ import annotations

from services.validation_case_package_service import build_validation_case_package


def _sample_construct_component_queue() -> dict[str, object]:
    return {
        "summary": {
            "total_component_rows": 3,
            "rows_with_source_reference_context": 2,
            "rows_missing_source_reference_context": 1,
            "rows_with_sequence_availability_note": 2,
            "rows_with_conservation_review_context": 1,
            "rows_needing_conservation_follow_up": 1,
            "rows_with_review_metadata_status": 2,
            "rows_with_review_note": 1,
            "rows_needing_manual_follow_up": 2,
        },
        "rows": [
            {
                "Construct label": "Case construct",
                "Cassette label": "Expression cassette",
                "Component label": "Signal peptide",
                "Issue type": "Needs conservation check",
                "Manual follow-up note": "Manual documentation follow-up: add conservation evidence context.",
            }
        ],
    }


def _sample_handoff_preview() -> dict[str, object]:
    return {
        "manual_follow_up_queue": [
            {
                "source_surface": "Project handoff review",
                "item_label": "Candidate source note",
                "issue_type": "Missing provenance context",
                "manual_follow_up_note": "Add source/provenance note before company review.",
            }
        ]
    }


def test_validation_case_package_includes_required_sections_and_identity() -> None:
    package = build_validation_case_package(
        case_context={
            "case_objective": "Prepare a documented mCherry expression design case for feasibility review.",
            "candidate_target": "mCherry fluorescent protein",
            "candidate_expression_systems": ["E. coli documentation option", "yeast documentation option"],
            "construct_label": "mCherry review construct",
            "construct_summary": "Promoter, coding sequence, tag, and terminator context recorded for review.",
            "review_gaps": [
                {
                    "source_surface": "Teacher review",
                    "item_label": "Company quotation context",
                    "issue_type": "External feedback needed",
                    "manual_follow_up_note": "Ask company reviewer to confirm feasibility constraints.",
                }
            ],
        },
        project={"id": 222, "name": "Teacher validation case"},
        construct_component_queue=_sample_construct_component_queue(),
        handoff_preview=_sample_handoff_preview(),
        codon_status={
            "status": "RECORDED",
            "host": "E. coli documentation option",
            "source": "Codon Usage Preview",
            "changed": False,
            "warning_count": 1,
        },
        package_identity={
            "git_tag": "v2.6-r222-validation-case-package-foundation",
            "commit": "abc1234",
        },
    )

    assert package["title"] == "Validation Case Package"
    assert package["case_objective"] == "Prepare a documented mCherry expression design case for feasibility review."
    assert package["candidate_target"] == "mCherry fluorescent protein"
    assert package["candidate_expression_systems"] == [
        "E. coli documentation option",
        "yeast documentation option",
    ]
    assert package["construct_design_summary"]["construct_label"] == "mCherry review construct"
    assert package["construct_design_summary"]["component_rows_reviewed"] == 3
    assert package["component_evidence_provenance_summary"]["source_reference_context_rows"] == 2
    assert package["codon_usage_optimization_status_summary"]["preview_provider"] == "Codon Usage Preview"
    assert package["component_conservation_review_summary"]["conservation_follow_up_rows"] == 1
    assert len(package["review_gaps_manual_follow_up_list"]) == 3
    assert "Company feasibility feedback placeholder" in package["company_feasibility_feedback_placeholder"]
    assert "Not started in BioDesign Studio" in package["experiment_status_placeholder"]
    assert "No experimental result summary recorded" in package["result_summary_placeholder"]
    assert package["software_package_identity"]["git_tag"] == "v2.6-r222-validation-case-package-foundation"
    assert package["software_package_identity"]["commit"] == "abc1234"
    assert package["software_package_identity"]["checksum_algorithm"] == "MD5"
    assert len(package["software_package_identity"]["snapshot_checksum"]) == 32
    assert package["software_package_identity"]["snapshot_id"].startswith("md5:")
    assert "BioDesign Studio validation case package identity payload" in package["qr_verification_payload_text"]

    markdown = package["markdown"]
    for expected in [
        "Case objective",
        "Candidate target protein/product/pathway",
        "Candidate expression systems",
        "Construct design summary",
        "Component evidence/provenance summary",
        "Codon usage / optimization status summary",
        "Component conservation review summary",
        "Review gaps / manual follow-up list",
        "Company feasibility feedback placeholder",
        "Experiment status placeholder",
        "Result summary placeholder",
        "Software/package identity",
    ]:
        assert expected in markdown


def test_validation_case_package_is_user_defined_not_hard_coded_to_hsa_or_gfp() -> None:
    package = build_validation_case_package(
        case_context={
            "case_objective": "Review a user-defined enzyme pathway case.",
            "candidate_target": "User-defined terpene pathway",
            "candidate_expression_systems": ["mammalian documentation option", "plant documentation option"],
        },
        construct_component_queue=_sample_construct_component_queue(),
    )

    text = str(package)
    assert "User-defined terpene pathway" in text
    assert "mammalian documentation option" in text
    assert "plant documentation option" in text
    assert "HSA" not in text
    assert "sfGFP" not in text
    assert "GFP-only" not in text


def test_validation_case_package_safety_boundaries_are_visible_without_misleading_claims() -> None:
    package = build_validation_case_package(
        case_context={
            "case_objective": "Prepare feasibility review context.",
            "candidate_target": "Custom protein case",
            "candidate_expression_systems": ["bacterial documentation option"],
        },
        construct_component_queue=_sample_construct_component_queue(),
        codon_status={"status": "RECORDED", "changed": True},
    )

    text = str(package).lower()
    for required in [
        "pre-experiment documentation and feasibility review",
        "not a wet-lab protocol",
        "does not guarantee expression",
        "does not forecast yield or experimental success",
        "does not select a preferred expression system",
        "does not replace expert/company review",
        "does not perform codon rewriting or automatic conservation classification",
        "manual/company review remains required",
        "no blast, msa, conserved-domain analysis, or automatic conservation classification",
    ]:
        assert required in text

    for forbidden in [
        "guaranteed expression",
        "yield " + "prediction",
        "wet-lab protocol package",
        "best expression system",
        "recommended expression system",
        "replacement for expert review",
        "automatic optimization",
        "automatic conservation claim",
        "validated " + "construct",
        "experiment-" + "ready",
        "production-" + "ready",
        "ready for " + "execution",
        "optimized " + "pathway",
    ]:
        assert forbidden not in text
