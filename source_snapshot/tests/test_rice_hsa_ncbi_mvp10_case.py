from __future__ import annotations

from services.rice_hsa_ncbi_mvp10_case import (
    EXPECTED_FILE_SHA256,
    EXPECTED_SEQUENCE_SHA256,
    REAL_CASE_PROJECT_NAME,
    REAL_CASE_STATUS,
    build_rice_hsa_real_case,
    build_rice_hsa_pending_construct_preview,
    evaluate_real_case_authenticity,
    load_rice_hsa_ncbi_case,
)
from services.canonical_construct_runtime import active_complete_plasmid_snapshot, active_construct_snapshot
from services import formal_single_gene_runtime
from services.formal_single_gene_runtime import generation_input_signature
from services.mvp_single_gene_persistence import open_mvp_single_gene_design, save_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository


def test_rice_hsa_ncbi_case_reads_alb_cds_from_genbank_annotation() -> None:
    case = load_rice_hsa_ncbi_case()

    assert case["alb"]["accession_version"] == "NM_000477.7"
    assert case["alb"]["used_location"] == "42..1871"
    assert case["alb"]["used_length"] == 1830
    assert case["alb"]["start_codon"] == "ATG"
    assert case["alb"]["stop_codon"] == "TAA"
    assert case["alb"]["translation_length"] == 609


def test_rice_hsa_ncbi_case_preserves_full_backbone_features() -> None:
    case = load_rice_hsa_ncbi_case()
    backbone = case["backbone"]

    assert backbone["accession_version"] == "AF234296.1"
    assert backbone["record_length"] == 8958
    assert backbone["topology"] == "circular"
    assert [(row["type"], row["location"], row["label"]) for row in backbone["features"]] == [
        ("source", "1..8958", "source"),
        ("CDS", "join(8944..8958,1..219)", "LacZ alpha fragment"),
        ("misc_feature", "28..78", "pUC18 MCS; polylinker"),
        ("misc_feature", "298..323", "right border T-DNA repeat"),
        ("misc_feature", "complement(1364..2364)", "STA region from pVS1 plasmid"),
        ("rep_origin", "complement(2957..3957)", "pVS1-REP; replication origin from pVS1"),
        ("misc_feature", "complement(4367..4627)", "bom site from pBR322"),
        ("rep_origin", "complement(4767..5047)", "pBR322 origin of replication"),
        ("CDS", "complement(5338..6132)", "aadA (kanamycin resistance) gene amplified from pIG121Hm"),
        ("misc_feature", "6557..6582", "left border repeat from C58 T-DNA"),
        ("misc_feature", "6649..6857", "CaMV 3'UTR (polyA signal)"),
        ("CDS", "complement(6873..7898)", "hptII (hygromycin resistance) gene"),
        ("regulatory", "complement(7934..8714)", "CaMV35S; 35S promoter from CaMV"),
        ("regulatory", "8862..8916", "PlacZ; lacZ promoter"),
    ]


def test_rice_hsa_ncbi_case_records_regulatory_sources_and_exact_boundary() -> None:
    case = load_rice_hsa_ncbi_case()

    promoter = case["assets"]["promoter"]
    terminator = case["assets"]["terminator"]
    assert (promoter["accession_version"], promoter["used_location"], promoter["strand"], promoter["used_length"]) == ("AF234296.1", "complement(7934..8714)", -1, 781)
    assert (terminator["accession_version"], terminator["used_location"], terminator["strand"], terminator["used_length"]) == ("AF234296.1", "6649..6857", 1, 209)
    assert case["insertion"]["exact_cut_external"] == "27|28"
    assert case["insertion"]["exact_cut_internal"] == 27
    assert case["insertion"]["source_feature"]["location"] == "28..78"
    assert case["insertion"]["disrupted_feature"]["location"] == "join(8944..8958,1..219)"
    assert "XbaI" in case["insertion"]["selection_basis"]


def test_rice_hsa_ncbi_case_records_raw_file_sha256_values() -> None:
    case = load_rice_hsa_ncbi_case()

    assert case["raw_file_sha256"] == EXPECTED_FILE_SHA256
    assert case["alb"]["mrna_sha256"] == EXPECTED_SEQUENCE_SHA256["alb_mrna"]
    for role in ("cds", "promoter", "terminator", "backbone"):
        assert case["assets"][role]["sequence_sha256"] == EXPECTED_SEQUENCE_SHA256[role]


def test_rice_hsa_preview_exposes_fixed_exact_insertion_contract() -> None:
    preview = build_rice_hsa_pending_construct_preview()

    assert preview["alb"] == {
        "accession_version": "NM_000477.7",
        "cds_location": "42..1871",
        "cds_length": 1830,
        "translation_length": 609,
        "translation_validation": "pass",
        "translation_note": "ALB CDS translation matches the GenBank qualifier.",
    }
    assert preview["backbone"]["accession_version"] == "AF234296.1"
    assert preview["backbone"]["candidate_mcs_location"] == "28..78"
    assert preview["pending_decisions"] == []
    assert preview["backbone"]["asset_kind"] == "exact_insertion_source"
    assert preview["backbone"]["exact_insertion_boundary"] == "27|28"
    assert preview["backbone"]["internal_cut_index"] == 27
    locked_actions = "\n".join(preview["locked_actions"])
    assert "without a user-editable coordinate" in locked_actions
    assert "No codon optimization is applied" in locked_actions
    assert "No experimental validation claim" in locked_actions


def test_formal_real_case_uses_one_11778_bp_canonical_snapshot() -> None:
    result = build_rice_hsa_real_case()
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])

    assert result["project_name"] == REAL_CASE_PROJECT_NAME
    assert result["input_lengths"] == {"promoter": 781, "cds": 1830, "terminator": 209, "backbone": 8958}
    assert cassette["sequence_length"] == 2820
    assert plasmid["sequence_length"] == result["plasmid_length"] == 11778
    assert plasmid["topology"] == "circular"
    assert result["plasmid_sha256"] == result["fasta_sequence_sha256"] == result["genbank_sequence_sha256"]
    assert result["authenticity_gate"]["passed"] is True
    assert result["authenticity_gate"]["source_verified"] is True
    assert result["authenticity_gate"]["status"] == REAL_CASE_STATUS
    assert result["authenticity_gate"]["construction_strategy_confirmed"] is True


def test_formal_real_case_does_not_read_r229_compatibility_fixture(monkeypatch) -> None:
    def fail_if_called() -> dict[str, str]:
        raise AssertionError("formal HSA/ALB construction must not read the r229 compatibility fixture")

    monkeypatch.setattr(formal_single_gene_runtime, "load_real_case", fail_if_called)

    result = build_rice_hsa_real_case(project_id="hsa-without-r229")

    assert result["plasmid_length"] == 11778
    assert result["authenticity_gate"]["source_verified"] is True


def test_authenticity_gate_blocks_missing_provenance_without_fallback() -> None:
    result = build_rice_hsa_real_case()
    result["input_records"]["promoter"].pop("source_location")
    gate = evaluate_real_case_authenticity(result)

    assert gate["passed"] is False
    assert gate["status"] == REAL_CASE_STATUS
    assert gate["source_verified"] is False
    assert any("promoter coordinates" in item for item in gate["missing_items"])


def test_provenance_change_invalidates_the_previous_input_signature() -> None:
    result = build_rice_hsa_real_case()
    changed_records = {role: dict(record) for role, record in result["input_records"].items()}
    changed_records["terminator"]["source_location"] = "6650..6857"

    changed_signature = generation_input_signature(
        changed_records,
        result["insertion_settings"],
        project_name=result["project_name"],
    )
    assert changed_signature != result["input_signature"]


def test_real_case_save_reopen_preserves_sequence_features_and_exports(tmp_path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "real-case-drafts")
    before = build_rice_hsa_real_case()
    saved = save_mvp_single_gene_design(before, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    before_snapshot = active_complete_plasmid_snapshot(before["runtime"])
    reopened_snapshot = active_complete_plasmid_snapshot(reopened["runtime"])
    assert reopened_snapshot["sequence"] == before_snapshot["sequence"]
    assert reopened_snapshot["feature_rows"] == before_snapshot["feature_rows"]
    assert reopened["exports"] == before["exports"]
    assert evaluate_real_case_authenticity(reopened)["source_verified"] is True
