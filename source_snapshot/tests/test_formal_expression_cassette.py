from __future__ import annotations

from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette


def _component(role: str, sequence: str, name: str | None = None) -> dict[str, object]:
    return {
        "biological_role": role,
        "display_name": name or role,
        "sequence": sequence,
        "source_kind": "library",
        "source_reference": "LOCAL:1",
        "user_edited": False,
    }


def _minimum(cds: str = "ATGAAATAA") -> list[dict[str, object]]:
    return [
        _component("promoter", "AAAA", "P1"),
        _component("cds", cds, "CDS1"),
        _component("three_prime_regulatory_region", "TTTT", "TEST_3PRIME_120bp"),
    ]


def _assessment(components: list[dict[str, object]], cds: str = "ATGAAATAA") -> dict:
    return assess_expression_cassette(
        components,
        cds_sequence=cds,
        cds_signature="cds-signature",
        order_confirmed=True,
    )


def _statuses(assessment: dict) -> set[str]:
    return {item["status"] for item in assessment["findings"]}


def test_minimal_cassette_uses_canonical_sequence_coordinates_and_precise_three_prime_role() -> None:
    assessment = _assessment(_minimum())
    assert not assessment["blocking"]
    assert "需要人工确认" in _statuses(assessment)

    generated = generate_expression_cassette(assessment, project_id="test-project")

    assert generated["cassette"]["sequence"] == "AAAAATGAAATAATTTT"
    assert generated["total_length"] == sum(item["length"] for item in generated["components"])
    assert [(item["start"], item["end"]) for item in generated["components"]] == [(1, 4), (5, 13), (14, 17)]
    assert generated["components"][-1]["biological_role"] == "three_prime_regulatory_region"
    assert generated["components"][-1]["display_name"] == "TEST_3PRIME_120bp"


def test_optional_five_prime_and_targeting_sequences_are_included_without_hidden_sequence() -> None:
    components = [
        _component("promoter", "AAAA"),
        _component("five_prime_utr", "CCCC"),
        _component("signal_peptide_coding_sequence", "ATGAAA"),
        _component("cds", "ATGAAATAA"),
        _component("terminator", "TTTT"),
    ]
    generated = generate_expression_cassette(_assessment(components), project_id="test-project")

    assert generated["cassette"]["sequence"] == "AAAACCCCATGAAAATGAAATAATTTT"
    assert [item["biological_role"] for item in generated["components"]] == [
        "promoter", "five_prime_utr", "signal_peptide_coding_sequence", "cds", "terminator"
    ]


def test_n_terminal_fusion_is_supported_and_c_terminal_stop_conflict_is_blocked() -> None:
    n_terminal = [
        _component("promoter", "AAAA"),
        _component("n_terminal_fusion_tag_coding_sequence", "ATGAAA"),
        _component("cds", "ATGAAATAA"),
        _component("terminator", "TTTT"),
    ]
    assert not _assessment(n_terminal)["blocking"]

    c_terminal = [
        _component("promoter", "AAAA"),
        _component("cds", "ATGAAATAA"),
        _component("c_terminal_fusion_tag_coding_sequence", "ATGAAA"),
        _component("terminator", "TTTT"),
    ]
    assessment = _assessment(c_terminal)
    assert assessment["blocking"]
    assert any(item["rule_id"] == "c_terminal_fusion_terminal_stop_conflict" for item in assessment["findings"])


def test_missing_stop_without_c_terminal_fusion_requires_manual_confirmation() -> None:
    assessment = _assessment(_minimum("ATGAAA"), cds="ATGAAA")
    assert not assessment["blocking"]
    assert any(item["rule_id"] == "cds_missing_terminal_stop" and item["status"] == "需要人工确认" for item in assessment["findings"])


def test_missing_required_component_illegal_dna_and_frameshift_are_blocking() -> None:
    missing = _assessment([_component("promoter", "AAAA"), _component("cds", "ATGAAATAA")])
    assert missing["blocking"]
    assert any(item["rule_id"] == "missing_three_prime_regulatory_element" for item in missing["findings"])

    illegal = _assessment([_component("promoter", "AAAZ"), *_minimum()[1:]])
    assert illegal["blocking"]
    assert any(item["rule_id"] == "illegal_dna_character" for item in illegal["findings"])

    frameshift = _assessment([
        _component("promoter", "AAAA"),
        _component("signal_peptide_coding_sequence", "ATGA"),
        _component("cds", "ATGAAATAA"),
        _component("terminator", "TTTT"),
    ])
    assert frameshift["blocking"]
    assert any(item["rule_id"] == "coding_component_frameshift" for item in frameshift["findings"])


def test_component_order_and_cds_identity_are_checked() -> None:
    wrong_order = _assessment([
        _component("promoter", "AAAA"),
        _component("cds", "ATGAAATAA"),
        _component("five_prime_utr", "CCCC"),
        _component("terminator", "TTTT"),
    ])
    assert wrong_order["blocking"]
    assert any(item["rule_id"] == "unsupported_component_order" for item in wrong_order["findings"])

    mismatch = _assessment(_minimum("ATGCCCTAA"), cds="ATGAAATAA")
    assert mismatch["blocking"]
    assert any(item["rule_id"] == "cds_signature_mismatch" for item in mismatch["findings"])


def test_formal_cassette_detail_survives_existing_single_gene_save_reopen(tmp_path) -> None:
    import mvp_app
    from services.mvp_sequence_input import analyze_dna_component_input, analyze_genbank_backbone_input
    from services.mvp_single_gene_persistence import open_mvp_single_gene_design, save_mvp_single_gene_design
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    project_id = "formal-cassette-reopen"
    case = mvp_app.load_real_case()
    cds_input = mvp_app.real_case_cds_input(case)
    records = {
        "promoter": analyze_dna_component_input(case["promoter"], project_id=project_id, component_type="promoter", display_name="P", source_kind="library", source_name="case promoter"),
        "cds": mvp_app._cds_record(cds_input, display_name="CDS"),
        "terminator": analyze_dna_component_input(case["terminator"], project_id=project_id, component_type="terminator", display_name="T", source_kind="library", source_name="case three-prime"),
        "backbone": analyze_genbank_backbone_input(case["backbone"], project_id=project_id, display_name="B", source_kind="upload", source_name="case.gb"),
    }
    components = [
        _component("promoter", records["promoter"]["normalized_sequence"], "P"),
        _component("five_prime_utr", "AAAAAA", "U5"),
        _component("cds", records["cds"]["normalized_sequence"], "CDS"),
        _component("three_prime_regulatory_region", records["terminator"]["normalized_sequence"], "T"),
    ]
    assessment = assess_expression_cassette(
        components,
        cds_sequence=records["cds"]["normalized_sequence"],
        cds_signature=cds_input["normalized_cds_sha256"],
        order_confirmed=True,
    )
    assert not assessment["blocking"]
    generated = generate_expression_cassette(assessment, project_id=project_id)
    formal_detail = {key: value for key, value in generated.items() if key not in {"runtime", "cassette"}}
    result = mvp_app.generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings={"mode": "insertion", "start_coordinate": 2100, "end_coordinate": 2101},
        project_id=project_id,
        project_name="Formal cassette reopen",
        cassette_runtime=generated["runtime"],
        cassette_signature=assessment["input_signature"],
    )
    result["formal_expression_cassette"] = formal_detail
    result["formal_project_context"] = {"host_key": "Rice (O. sativa)", "current_step": 6}
    repo = PlantProjectDraftRepository(tmp_path / "projects")

    saved = save_mvp_single_gene_design(result, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert reopened["formal_expression_cassette"]["components"] == formal_detail["components"]
    assert reopened["cassette_length"] == generated["total_length"]
