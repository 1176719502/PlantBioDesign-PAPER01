from __future__ import annotations

from io import StringIO
from pathlib import Path

from Bio import SeqIO

from mvp_app import generate_complete_vector, load_real_case, real_case_cds_input
from services.canonical_construct_runtime import active_complete_plasmid_snapshot
from services.mvp_cds_input import analyze_cds_input
from services.mvp_single_gene_persistence import open_mvp_single_gene_design, save_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository


def _rule_ids(result: dict) -> set[str]:
    return {item["rule_id"] for item in result["findings"]}


def test_plain_and_fasta_cds_inputs_preserve_original_text_and_normalize_dna() -> None:
    plain = analyze_cds_input("atg gct\nTAA", source_kind="paste")
    fasta = analyze_cds_input(">example\nATGGCTTAA\n", source_kind="upload", source_name="example.fasta")

    assert plain["original_text"] == "atg gct\nTAA"
    assert plain["normalized_cds"] == "ATGGCTTAA"
    assert plain["normalized_length"] == 9
    assert not plain["blocking"]
    assert fasta["source_format"] == "fasta"
    assert fasta["record_name"] == "example"
    assert fasta["normalized_cds"] == plain["normalized_cds"]


def test_formatting_is_removed_but_illegal_dna_letters_are_not_silently_discarded() -> None:
    result = analyze_cds_input("1 atg- gct. x taA", source_kind="paste")

    assert result["normalized_cds"] == "ATGGCTTAA"
    assert result["blocking"]
    assert "invalid_dna_character" in _rule_ids(result)


def test_empty_invalid_and_broken_fasta_are_blocked() -> None:
    assert "empty_cds" in _rule_ids(analyze_cds_input(" 123 - ", source_kind="paste"))
    assert "invalid_dna_character" in _rule_ids(analyze_cds_input("ATGBCTAA", source_kind="paste"))
    assert "invalid_fasta" in _rule_ids(analyze_cds_input("ATGGCT\n>late\nTAA", source_kind="upload"))


def test_multiple_fasta_records_are_not_silently_selected() -> None:
    result = analyze_cds_input(">first\nATGGCTTAA\n>second\nATGGCTTAA\n", source_kind="upload")

    assert result["blocking"]
    assert result["record_count"] == 2
    assert _rule_ids(result) == {"multiple_fasta_records"}


def test_r227_length_start_stop_and_internal_stop_rules_are_reported() -> None:
    not_divisible = analyze_cds_input("ATGGCTTA", source_kind="paste")
    missing_start_stop = analyze_cds_input("GCTGCTGCT", source_kind="paste")
    internal_stop = analyze_cds_input("ATGTAATAA", source_kind="paste")

    assert not_divisible["blocking"]
    assert "cds_length_not_divisible_by_three" in _rule_ids(not_divisible)
    assert not missing_start_stop["blocking"]
    assert {"cds_missing_start_codon", "cds_missing_terminal_stop_codon"} <= _rule_ids(missing_start_stop)
    assert internal_stop["blocking"]
    assert "internal_in_frame_stop_codon" in _rule_ids(internal_stop)


def test_three_different_valid_cds_values_build_expected_complete_plasmid_lengths() -> None:
    fixture_case = load_real_case()
    alternate_cds = "ATG" + ("GCT" * 98) + "TAA"
    formatted_cds = "atg " + ("gct\n" * 99) + "taa"
    inputs = [
        real_case_cds_input(fixture_case),
        analyze_cds_input(alternate_cds, source_kind="paste", source_name="alternate"),
        analyze_cds_input(formatted_cds, source_kind="paste", source_name="formatted"),
    ]

    assert [item["normalized_length"] for item in inputs] == [900, 300, 303]
    for cds_input in inputs:
        result = generate_complete_vector(fixture_case, cds_input=cds_input)
        expected_plasmid_length = 640 + cds_input["normalized_length"] + 210 + 4200
        fasta_record = next(SeqIO.parse(StringIO(result["exports"]["fasta"]["data"]), "fasta"))
        genbank_record = next(SeqIO.parse(StringIO(result["exports"]["genbank"]["data"]), "genbank"))

        assert result["input_lengths"]["cds"] == cds_input["normalized_length"]
        assert result["plasmid_length"] == expected_plasmid_length
        assert str(fasta_record.seq) == str(genbank_record.seq) == active_complete_plasmid_snapshot(result["runtime"])["sequence"]


def test_user_cds_save_reopen_preserves_source_normalization_runtime_and_export_bytes(tmp_path: Path) -> None:
    raw_cds = " \natg " + ("gct\n" * 98) + "taa \n"
    cds_input = analyze_cds_input(raw_cds, source_kind="upload", source_name="formatted.fasta")
    before = generate_complete_vector(load_real_case(), cds_input=cds_input)
    repository = PlantProjectDraftRepository(tmp_path / "shared_r224_drafts")
    saved = save_mvp_single_gene_design(before, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    assert reopened["cds_input"]["source_kind"] == "upload"
    assert reopened["cds_input"]["source_name"] == "formatted.fasta"
    assert reopened["cds_input"]["original_text"] == raw_cds
    assert reopened["cds_input"]["normalized_cds"] == cds_input["normalized_cds"]
    assert reopened["plasmid_length"] == 5350
    assert reopened["runtime"] == before["runtime"]
    assert reopened["exports"]["fasta"]["data"].encode("utf-8") == before["exports"]["fasta"]["data"].encode("utf-8")
    assert reopened["exports"]["genbank"]["data"].encode("utf-8") == before["exports"]["genbank"]["data"].encode("utf-8")
