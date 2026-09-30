from __future__ import annotations

import copy
import hashlib
from io import StringIO

import pytest
from Bio import SeqIO

from core.pcambia1300_exact_insertion_contract import (
    Pcambia1300ExactInsertionContractError,
    exact_insertion_contract,
    fixed_insertion_settings,
    insert_pcambia1300_cassette,
    validate_pcambia1300_operation,
    validate_pcambia1300_source,
)
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.formal_t_dna_review import validate_t_dna_operation
from services.mvp_single_gene_persistence import (
    MVP_SINGLE_GENE_PERSISTENCE_KEY,
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.professional_review_delivery_package import (
    REVIEW_BLOCKED,
    assess_professional_review_package,
    build_professional_review_package,
)
from services.rice_hsa_ncbi_mvp10_case import (
    BACKBONE_GENBANK,
    build_rice_hsa_real_case,
    build_rice_hsa_real_input_records,
    load_rice_hsa_ncbi_case,
)


@pytest.fixture(scope="module")
def case() -> dict:
    return load_rice_hsa_ncbi_case()


@pytest.fixture(scope="module")
def generated() -> dict:
    return build_rice_hsa_real_case(project_id="pcambia1300-exact-insertion-tests")


def test_af234296_identity_length_hash_and_contract(case: dict) -> None:
    contract = exact_insertion_contract()
    source = case["backbone"]["sequence"]
    validated = validate_pcambia1300_source(
        source,
        accession_version=case["backbone"]["accession_version"],
        circular=case["backbone"]["topology"] == "circular",
    )
    assert validated == contract
    assert case["backbone"]["definition"] == "Binary vector pCAMBIA-1300, complete sequence"
    assert len(source) == 8958
    assert hashlib.sha256(source.encode("ascii")).hexdigest() == contract["full_sequence_sha256"]


def test_external_boundary_maps_to_internal_index_without_off_by_one(case: dict) -> None:
    contract = exact_insertion_contract()
    source = case["backbone"]["sequence"]
    assert contract["external_cut_boundary"] == "27|28"
    assert contract["internal_cut_index"] == 27
    assert source[26:32] == "TCTAGA"
    marker = "GATTACA"
    output = insert_pcambia1300_cassette(source, marker)
    assert output[27 : 27 + len(marker)] == marker
    assert output[:27] == source[:27]
    assert output[27 + len(marker) :] == source[27:]


def test_output_formula_and_every_source_base_are_preserved(case: dict) -> None:
    source = case["backbone"]["sequence"]
    cassette = "ATG" + "GCC" * 10 + "TAA"
    output = insert_pcambia1300_cassette(source, cassette)
    assert len(output) == 8958 + len(cassette)
    assert output[:27] + output[27 + len(cassette) :] == source


def test_hptii_borders_and_bacterial_regions_are_retained(case: dict, generated: dict) -> None:
    source = case["backbone"]["sequence"]
    cassette = active_construct_snapshot(generated["runtime"])["sequence"]
    output = active_complete_plasmid_snapshot(generated["runtime"])["sequence"]
    shift = len(cassette)
    assert output[297 + shift : 323 + shift] == source[297:323]
    assert output[6556 + shift : 6582 + shift] == source[6556:6582]
    assert output[6648 + shift : 8714 + shift] == source[6648:8714]
    assert output[1363 + shift : 6132 + shift] == source[1363:6132]
    assert all(generated["pcambia1300_validation"].values())


@pytest.mark.parametrize(
    ("mode", "start", "end", "message"),
    [
        ("replacement", 27, 28, "does not allow replacement"),
        ("insertion", 219, 220, "legacy AF234296.1 boundary 219|220"),
        ("insertion", 26, 27, "fixed at external boundary 27|28"),
        ("insertion", 28, 29, "fixed at external boundary 27|28"),
    ],
)
def test_arbitrary_legacy_and_non_27_operations_are_rejected(
    case: dict, mode: str, start: int, end: int, message: str
) -> None:
    with pytest.raises(Pcambia1300ExactInsertionContractError, match=message):
        validate_pcambia1300_operation(
            source_sequence=case["backbone"]["sequence"],
            accession_version="AF234296.1",
            circular=True,
            mode=mode,
            start_coordinate=start,
            end_coordinate=end,
            insertion_orientation="forward",
            workflow_id="rice_alb_single_gene",
        )


def test_source_length_hash_accession_and_topology_drift_are_rejected(case: dict) -> None:
    source = case["backbone"]["sequence"]
    with pytest.raises(Pcambia1300ExactInsertionContractError, match="8,958 bp"):
        validate_pcambia1300_source(source[:-1], accession_version="AF234296.1", circular=True)
    drifted = source[:500] + ("A" if source[500] != "A" else "C") + source[501:]
    with pytest.raises(Pcambia1300ExactInsertionContractError, match="SHA-256"):
        validate_pcambia1300_source(drifted, accession_version="AF234296.1", circular=True)
    with pytest.raises(Pcambia1300ExactInsertionContractError, match="accession/version"):
        validate_pcambia1300_source(source, accession_version="AF234296.2", circular=True)
    with pytest.raises(Pcambia1300ExactInsertionContractError, match="circular"):
        validate_pcambia1300_source(source, accession_version="AF234296.1", circular=False)


def test_mcs_lacz_and_xbai_features_are_explicitly_superseded(generated: dict) -> None:
    rows = active_complete_plasmid_snapshot(generated["runtime"])["feature_rows"]
    names = [str(row["name"]) for row in rows]
    assert "pUC18 MCS; polylinker" not in names
    assert "LacZ alpha fragment" not in names
    assert any("MCS / polylinker (superseded" in name for name in names)
    assert any("LacZ alpha fragment (interrupted" in name for name in names)
    assert any(name == "XbaI site (disrupted by exact insertion)" for name in names)


def test_inserted_source_components_and_tu_envelope_have_exact_coordinates(generated: dict) -> None:
    rows = active_complete_plasmid_snapshot(generated["runtime"])["feature_rows"]
    def inserted(name: str) -> dict:
        return next(
            row
            for row in rows
            if str(row["name"]) == name and str(row.get("source") or "") != "backbone"
        )

    assert (inserted("AF234296.1 inserted cassette source")["start"], inserted("AF234296.1 inserted cassette source")["end"]) == (28, 2847)
    assert (inserted("Inserted single-gene transcription unit")["start"], inserted("Inserted single-gene transcription unit")["end"]) == (28, 2847)
    assert (inserted("CaMV35S promoter")["start"], inserted("CaMV35S promoter")["end"]) == (28, 808)
    assert (inserted("ALB CDS")["start"], inserted("ALB CDS")["end"]) == (809, 2638)
    assert (inserted("CaMV 3'UTR (polyA signal)")["start"], inserted("CaMV 3'UTR (polyA signal)")["end"]) == (2639, 2847)


def test_rice_alb_single_gene_is_supported_and_uses_fixed_settings(generated: dict) -> None:
    assert generated["insertion_settings"] == {
        **fixed_insertion_settings(),
        "workflow_id": "rice_alb_single_gene",
    }
    assert generated["exact_insertion_record"]["workflow_support_status"] == "supported_rice_alb_single_gene"
    assert generated["authenticity_gate"]["passed"] is True


@pytest.mark.parametrize("workflow_id", ["generic_multi_tu", "gate3"])
def test_multi_tu_and_gate3_are_explicitly_blocked(case: dict, workflow_id: str) -> None:
    _cds_input, records = build_rice_hsa_real_input_records(f"blocked-{workflow_id}")
    operation = validate_t_dna_operation(
        records["backbone"],
        confirmation={},
        insertion_settings=fixed_insertion_settings(),
        workflow_id=workflow_id,
    )
    assert operation["allowed"] is False
    assert operation["status"] == "pcambia1300_exact_insertion_blocked"
    assert "multi-TU capacity, orientation, and promoter-interference acceptance is not complete" in operation["reason"]


def test_save_cold_reopen_preserves_contract_hashes_features_and_exports(tmp_path, generated: dict) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_single_gene_design(copy.deepcopy(generated), repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=PlantProjectDraftRepository(tmp_path / "projects"))
    before = active_complete_plasmid_snapshot(generated["runtime"])
    after = active_complete_plasmid_snapshot(reopened["runtime"])
    assert reopened["exact_insertion_contract"] == exact_insertion_contract()
    assert reopened["exact_insertion_record"] == generated["exact_insertion_record"]
    assert reopened["insertion_settings"]["start_coordinate"] == 27
    assert reopened["insertion_settings"]["end_coordinate"] == 28
    assert after["sequence"] == before["sequence"]
    assert after["feature_rows"] == before["feature_rows"]
    assert reopened["exports"] == generated["exports"]


def test_saved_legacy_219_220_project_is_blocked_without_rewrite(tmp_path, generated: dict) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "legacy-project")
    saved = save_mvp_single_gene_design(copy.deepcopy(generated), repository=repository)
    draft = repository.load(saved.project_id)
    payload = draft.manual_review_state[MVP_SINGLE_GENE_PERSISTENCE_KEY]
    payload["insertion_settings"]["start_coordinate"] = 219
    payload["insertion_settings"]["end_coordinate"] = 220
    repository.save(draft)
    with pytest.raises(MvpSingleGenePersistenceError, match=r"219\|220"):
        open_mvp_single_gene_design(saved.project_id, repository=repository)
    unchanged = repository.load(saved.project_id)
    stored = unchanged.manual_review_state[MVP_SINGLE_GENE_PERSISTENCE_KEY]["insertion_settings"]
    assert (stored["start_coordinate"], stored["end_coordinate"]) == (219, 220)


@pytest.mark.parametrize(
    ("target", "key", "value", "message"),
    [
        ("top_level", "internal_cut_index", 219, "top-level exact-insertion contract"),
        ("settings", "exact_insertion_contract_version", "legacy", "contract version"),
        ("settings", "workflow_id", "gate3", "rice/ALB single-gene workflow"),
        ("settings", "workflow_support_status", "blocked", "workflow support status"),
    ],
)
def test_saved_contract_and_workflow_fields_cannot_override_fixed_policy(
    tmp_path,
    generated: dict,
    target: str,
    key: str,
    value: object,
    message: str,
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / f"tampered-{key}")
    saved = save_mvp_single_gene_design(copy.deepcopy(generated), repository=repository)
    draft = repository.load(saved.project_id)
    payload = draft.manual_review_state[MVP_SINGLE_GENE_PERSISTENCE_KEY]
    if target == "top_level":
        payload["exact_insertion_contract"][key] = value
    else:
        payload["insertion_settings"][key] = value
    repository.save(draft)

    with pytest.raises(MvpSingleGenePersistenceError, match=message):
        open_mvp_single_gene_design(saved.project_id, repository=repository)


def test_fasta_genbank_and_canonical_are_identical_with_remapped_features(generated: dict) -> None:
    canonical = active_complete_plasmid_snapshot(generated["runtime"])["sequence"]
    fasta = SeqIO.read(StringIO(generated["exports"]["fasta"]["data"]), "fasta")
    genbank = SeqIO.read(StringIO(generated["exports"]["genbank"]["data"]), "genbank")
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    labels = [str((feature.qualifiers.get("label") or [""])[0]) for feature in genbank.features]
    assert any("MCS / polylinker (superseded" in label for label in labels)
    assert any("LacZ alpha fragment (interrupted" in label for label in labels)


def test_professional_review_delivery_accepts_the_saved_workflow_identity(generated: dict) -> None:
    assessment = assess_professional_review_package(
        generated,
        current_input_signature=generated["input_signature"],
    )
    assert assessment["review_status"] != REVIEW_BLOCKED
    package = build_professional_review_package(
        generated,
        current_input_signature=generated["input_signature"],
    )
    assert package["data"]


def test_contract_errors_are_user_facing_without_traceback(case: dict) -> None:
    with pytest.raises(Pcambia1300ExactInsertionContractError) as caught:
        validate_pcambia1300_operation(
            source_sequence=case["backbone"]["sequence"],
            accession_version="AF234296.1",
            circular=True,
            mode="insertion",
            start_coordinate=219,
            end_coordinate=220,
            insertion_orientation="forward",
            workflow_id="rice_alb_single_gene",
        )
    message = str(caught.value)
    assert "Traceback" not in message
    assert 'File "' not in message


def test_source_assets_are_read_only_inputs() -> None:
    assert BACKBONE_GENBANK.name == "AF234296.1.gb"
    assert BACKBONE_GENBANK.exists()
