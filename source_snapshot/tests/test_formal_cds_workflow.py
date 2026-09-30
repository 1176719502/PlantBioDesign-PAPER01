from __future__ import annotations

from services.formal_cds_workflow import (
    analyze_formal_cds,
    gene_information_from_values,
    lifecycle_change,
)
from services.mvp_cds_input import analyze_cds_input


def _info(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "gene_name": "TEST1",
        "source_species": "Oryza sativa",
        "source_type": "用户自有序列",
        "modification_status": "未修改的来源序列",
    }
    values.update(overrides)
    return gene_information_from_values(**values)


def _rule_ids(analysis: dict[str, object]) -> set[str]:
    return {str(item["rule_id"]) for item in list(analysis["findings"])}  # type: ignore[index]


def test_pasted_single_cds_normalizes_whitespace_and_translates() -> None:
    analysis = analyze_formal_cds(" atg\n gct\t taa ", source_kind="paste", gene_information=_info())

    assert analysis["normalized_cds"] == "ATGGCTTAA"
    assert analysis["record_count"] == 1
    assert analysis["contains_only_acgt"] is True
    assert analysis["protein_translation"] == "MA*"
    assert analysis["expected_protein_length"] == 2
    assert analysis["blocking"] is False


def test_uploaded_single_fasta_retains_title_and_filename() -> None:
    analysis = analyze_formal_cds(
        ">TEST1 source\natggcttaa\n",
        source_kind="upload",
        source_name="test1.fasta",
        gene_information=_info(),
    )

    assert analysis["record_name"] == "TEST1 source"
    assert analysis["source_name"] == "test1.fasta"
    assert analysis["normalized_cds"] == "ATGGCTTAA"


def test_multiple_fasta_records_and_invalid_characters_block_without_repair() -> None:
    multi = analyze_cds_input(
        ">first\nATGGCTTAA\n>second\nATGGCTTAA\n", source_kind="upload", source_name="two.fa"
    )
    invalid = analyze_cds_input("ATG UCN-12", source_kind="paste")

    assert multi["blocking"] is True
    assert "multiple_fasta_records" in _rule_ids(multi)
    assert invalid["blocking"] is True
    assert invalid["normalized_cds"] == "ATGC"
    assert set(invalid["invalid_characters"]) == {"-", "1", "2", "N", "U"}


def test_length_and_internal_stop_block_but_non_atg_and_missing_stop_require_review() -> None:
    bad_length = analyze_cds_input("ATGGCTTA", source_kind="paste")
    internal_stop = analyze_cds_input("ATGTAAGCTTAA", source_kind="paste")
    non_atg = analyze_cds_input("GTGGCTTAA", source_kind="paste")
    missing_stop = analyze_cds_input("ATGGCTGCT", source_kind="paste")

    assert bad_length["blocking"] is True
    assert "cds_length_not_divisible_by_three" in _rule_ids(bad_length)
    assert internal_stop["blocking"] is True
    assert internal_stop["internal_stop_positions"] == [2]
    assert non_atg["blocking"] is False
    assert "cds_missing_start_codon" in _rule_ids(non_atg)
    assert missing_stop["blocking"] is False
    assert missing_stop["normalized_cds"] == "ATGGCTGCT"
    assert "cds_missing_terminal_stop_codon" in _rule_ids(missing_stop)


def test_source_and_modification_manual_review_items_are_recorded() -> None:
    analysis = analyze_formal_cds(
        "ATGGCTTAA",
        source_kind="paste",
        gene_information=_info(
            source_species="",
            source_type="公共数据库记录",
            source_reference="NM_000477.7",
            modification_status="已由外部工具或公司进行密码子优化",
            modification_note="",
            is_partial_cds=True,
        ),
    )

    rules = _rule_ids(analysis)
    assert {"source_species_missing", "accession_unverified", "external_optimization_source_missing", "partial_cds"} <= rules
    assert all(item["status"] == "需要人工确认" for item in analysis["manual_review_items"])


def test_lifecycle_only_invalidates_for_sequence_changes() -> None:
    initial = analyze_formal_cds("ATGGCTTAA", source_kind="paste", gene_information=_info())
    renamed = analyze_formal_cds("ATGGCTTAA", source_kind="paste", gene_information=_info(gene_name="DISPLAY_ONLY"))
    source_changed = analyze_formal_cds("ATGGCTTAA", source_kind="paste", gene_information=_info(source_species="Arabidopsis thaliana"))
    sequence_changed = analyze_formal_cds("ATGGCGTAA", source_kind="paste", gene_information=_info())

    assert lifecycle_change(initial, renamed) == "none"
    assert lifecycle_change(initial, source_changed) == "source_review"
    assert lifecycle_change(initial, sequence_changed) == "invalidate"
