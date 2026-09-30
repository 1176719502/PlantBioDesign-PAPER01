from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

from core.pbi121_replacement_contract import (
    Pbi121ReplacementContractError,
    is_pbi121_sequence,
    replacement_contract,
    replace_pbi121_reporter_cassette,
    validate_pbi121_operation,
    validate_pbi121_source,
)
from services.betalain_pbi121_canonical_construct import generate_betalain_pbi121_canonical_construct
from services.formal_t_dna_review import validate_t_dna_operation
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.pbi121_replacement_strategy import load_strategy
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.real_genbank_asset_import import build_pbi121_asset_bundle


@pytest.fixture(scope="module")
def bundle() -> dict:
    return build_pbi121_asset_bundle()


@pytest.fixture()
def generated(tmp_path: Path) -> dict:
    return generate_betalain_pbi121_canonical_construct(
        project_id="pbi121-exact-replacement",
        project_name="pBI121 exact replacement",
        repeated_regulatory_confirmed=True,
        strategy_root=tmp_path / "strategy",
    )


def test_af485783_identity_full_hash_and_replacement_hash(bundle: dict) -> None:
    audit = bundle["audit"]
    contract = validate_pbi121_source(audit["sequence"], accession_version=audit["accession"])
    assert audit["accession"] == "AF485783.1"
    assert audit["topology"] == "circular"
    assert len(audit["sequence"]) == 14758
    assert hashlib.sha256(audit["sequence"].encode("ascii")).hexdigest() == contract["full_sequence_sha256"]
    start, end = contract["normalized_replacement_start"], contract["normalized_replacement_end"]
    assert (start, end) == (4973, 7979)
    assert len(audit["sequence"][start:end]) == 3006
    assert hashlib.sha256(audit["sequence"][start:end].encode("ascii")).hexdigest() == contract["replacement_sha256"]


def test_insert_and_unreviewed_coordinates_are_rejected(bundle: dict) -> None:
    sequence = bundle["audit"]["sequence"]
    with pytest.raises(Pbi121ReplacementContractError, match="Direct insertion"):
        validate_pbi121_operation(
            source_sequence=sequence,
            accession_version="AF485783.1",
            mode="insertion",
            replacement_start=4974,
            replacement_end=7979,
        )
    with pytest.raises(Pbi121ReplacementContractError, match="fixed at 4974..7979"):
        validate_pbi121_operation(
            source_sequence=sequence,
            accession_version="AF485783.1",
            mode="replacement",
            replacement_start=4973,
            replacement_end=7979,
        )


def test_source_length_accession_and_region_hash_drift_are_rejected(bundle: dict) -> None:
    sequence = bundle["audit"]["sequence"]
    with pytest.raises(Pbi121ReplacementContractError, match="14,758 bp"):
        validate_pbi121_source(sequence[:-1], accession_version="AF485783.1")
    with pytest.raises(Pbi121ReplacementContractError, match="accession/version"):
        validate_pbi121_source(sequence, accession_version="AF485783.2")
    drifted = sequence[:5000] + ("A" if sequence[5000] != "A" else "C") + sequence[5001:]
    with pytest.raises(Pbi121ReplacementContractError, match="source sequence SHA-256"):
        validate_pbi121_source(drifted, accession_version="AF485783.1")


def test_general_single_gene_and_multi_tu_backbone_path_is_explicitly_blocked(bundle: dict) -> None:
    backbone = {"normalized_sequence": bundle["audit"]["sequence"]}
    operation = validate_t_dna_operation(
        backbone,
        confirmation={},
        insertion_settings={"mode": "insertion", "start_coordinate": 5000, "end_coordinate": 5001},
    )
    assert is_pbi121_sequence(backbone["normalized_sequence"])
    assert operation["allowed"] is False
    assert operation["status"] == "dedicated_exact_replacement_required"
    contract = replacement_contract()
    assert contract["supported_workflows"] == ["gate3_betalain_three_tu"]
    assert contract["blocked_workflows"] == ["formal_single_gene", "generic_multi_tu"]


def test_gate3_clean_state_auto_creates_the_fixed_strategy(tmp_path: Path) -> None:
    root = tmp_path / "clean-strategy"
    result = generate_betalain_pbi121_canonical_construct(
        project_id="clean-gate3",
        project_name="Clean Gate 3",
        repeated_regulatory_confirmed=True,
        strategy_root=root,
    )
    strategy = load_strategy(runtime_root=root)
    assert (root / "pbi121_replacement_strategy.json").exists()
    assert strategy["strategy_origin"] == "system_fixed_contract"
    assert strategy["editable"] is False
    assert result["formal_project_context"]["pbi121_replacement_contract"] == replacement_contract()


def test_exact_replacement_removes_reporter_and_retains_required_regions(bundle: dict, generated: dict) -> None:
    source = bundle["audit"]["sequence"]
    contract = replacement_contract()
    combined = generated["combined_construct"]["dna"]
    complete = generated["complete_plasmid"]["dna"]
    expected = replace_pbi121_reporter_cassette(source, combined, accession_version="AF485783.1")
    checks = generated["betalain_pbi121_validation"]["sequence_identity_checks"]

    assert complete == expected
    assert len(complete) == 14758 - 3006 + len(combined)
    assert source[4973:7979] not in complete
    assert checks["original_reporter_cassette_absent"] is True
    assert checks["nptii_selection_cassette_retained"] is True
    assert checks["right_border_retained"] is True
    assert checks["left_border_retained"] is True
    assert checks["col_e1_ori_retained"] is True
    assert checks["ori_v_retained"] is True
    assert contract["replacement_length"] == 3006


def test_fasta_genbank_and_canonical_are_identical(generated: dict) -> None:
    canonical = generated["complete_plasmid"]["dna"]
    fasta = next(SeqIO.parse(StringIO(generated["exports"]["complete_plasmid_fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(generated["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    assert generated["betalain_pbi121_validation"]["sequence_identity_checks"]["fasta_genbank_canonical_match"] is True


def test_save_and_cold_reopen_preserve_contract_and_export_identity(tmp_path: Path, generated: dict) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(generated, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    context = reopened["formal_project_context"]
    assert context["pbi121_replacement_contract"] == replacement_contract()
    assert context["betalain_pbi121_validation"]["replacement_contract"] == replacement_contract()
    assert bool(
        reopened.get("betalain_pbi121_validation")
        or context.get("betalain_pbi121_validation")
    )
    assert reopened["complete_plasmid"]["dna"] == generated["complete_plasmid"]["dna"]
    assert reopened["exports"]["complete_plasmid_fasta"]["data"] == generated["exports"]["complete_plasmid_fasta"]["data"]
    assert reopened["exports"]["complete_plasmid_genbank"]["data"] == generated["exports"]["complete_plasmid_genbank"]["data"]
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert 'vector_context.get("betalain_pbi121_validation")' in app_source
    assert 'vector_workflow = "betalain_gate3"' in app_source


def test_contract_errors_are_user_facing_and_do_not_expose_tracebacks(bundle: dict) -> None:
    with pytest.raises(Pbi121ReplacementContractError) as caught:
        validate_pbi121_operation(
            source_sequence=bundle["audit"]["sequence"],
            accession_version="AF485783.1",
            mode="insert",
            replacement_start=4974,
            replacement_end=7979,
        )
    message = str(caught.value)
    assert "Traceback" not in message
    assert "File \"" not in message
