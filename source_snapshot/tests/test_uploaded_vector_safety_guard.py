from __future__ import annotations

import copy
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from core.vector_asset_contracts_v1 import classify_vector_asset, load_vector_asset_contracts
from services.formal_t_dna_review import validate_t_dna_operation
from services import formal_single_gene_runtime, mvp_multi_tu_runtime
from services.mvp_sequence_input import analyze_genbank_backbone_input
from services.vector_asset_admission import (
    VectorAssetAdmissionError,
    assess_legacy_project_vector,
    require_vector_operation,
    validate_vector_operation,
)


ROOT = Path(__file__).resolve().parents[1]


def _contract(asset_id: str) -> dict:
    return next(row for row in load_vector_asset_contracts() if row["asset_id"] == asset_id)


def _raw(contract: dict) -> str:
    return (ROOT / contract["source_evidence"][0]["local_record_path"]).read_text(encoding="utf-8")


def _parsed(asset_id: str, *, file_name: str | None = None) -> dict:
    contract = _contract(asset_id)
    return analyze_genbank_backbone_input(
        _raw(contract),
        project_id=f"upload-{asset_id}",
        display_name=file_name or contract["display_name"],
        source_kind="upload",
        source_name=file_name or contract.get("accession_version") or contract.get("record_id"),
    )


def _unknown_raw() -> str:
    record = SeqRecord(Seq("ACGT" * 350), id="LOCAL_UNKNOWN", name="LOCAL_UNKNOWN", description="local vector")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue()


def test_uploaded_known_assets_receive_content_based_identity() -> None:
    for asset_id in (
        "pcambia1300_af234296_1",
        "pbi121_af485783_1",
        "pbin19_u09365_1",
        "r229_local_example",
    ):
        record = _parsed(asset_id, file_name="renamed-upload.gb")
        assert record["vector_asset_identity"]["identity_status"] == "EXACT_KNOWN_ASSET"
        assert record["asset_id"] == asset_id


def test_pbin19_filename_cannot_assign_pbin19_contract_to_wrong_bytes() -> None:
    raw = _raw(_contract("pbin19_u09365_1"))
    parsed = SeqIO.read(StringIO(raw), "genbank")
    sequence = str(parsed.seq).upper()
    parsed.seq = Seq(("A" if sequence[0] != "A" else "C") + sequence[1:])
    output = StringIO()
    SeqIO.write(parsed, output, "genbank")
    record = analyze_genbank_backbone_input(
        output.getvalue(),
        project_id="fake-pbin19",
        display_name="pBIN19.gb",
        source_kind="upload",
        source_name="pBIN19.gb",
    )
    assert record["vector_asset_identity"]["identity_status"] == "KNOWN_ACCESSION_SEQUENCE_MISMATCH"
    assert record["asset_id"] is None
    assert record["asset_kind"] == "unverified_uploaded_vector"


def test_unknown_uploaded_vector_is_read_only() -> None:
    record = analyze_genbank_backbone_input(
        _unknown_raw(),
        project_id="unknown",
        display_name="unknown.gb",
        source_kind="upload",
        source_name="unknown.gb",
    )
    identity = record["vector_asset_identity"]
    assert identity["identity_status"] == "UNVERIFIED_UPLOADED_VECTOR"
    assert identity["asset_kind"] == "unverified_uploaded_vector"
    assert identity["read_only"] is True
    assert not validate_vector_operation(
        record,
        workflow_id="single_gene",
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 100,
            "end_coordinate": 101,
            "insertion_orientation": "forward",
        },
    )["allowed"]


@pytest.mark.parametrize("asset_id", ["pbin19_u09365_1", "r229_local_example"])
def test_reference_and_hold_uploads_cannot_generate_modified_vectors(asset_id: str) -> None:
    record = _parsed(asset_id)
    for workflow in ("single_gene", "generic_multi_tu", "betalain_gate3"):
        assessment = validate_vector_operation(
            record,
            workflow_id=workflow,
            insertion_settings={
                "mode": "insertion",
                "start_coordinate": 2100,
                "end_coordinate": 2101,
                "insertion_orientation": "forward",
            },
        )
        assert assessment["allowed"] is False


def test_manual_t_dna_confirmation_no_longer_unlocks_unknown_vector() -> None:
    record = analyze_genbank_backbone_input(
        _unknown_raw(),
        project_id="manual-bypass",
        display_name="manual.gb",
        source_kind="upload",
        source_name="manual.gb",
    )
    forged_confirmation = {
        "status": "confirmed",
        "backbone_sequence_signature": "forged",
        "backbone_length": record["length"],
        "topology": "circular",
        "region": {"start": 1, "end": record["length"], "crosses_origin": False},
        "lb": {"start": 1, "end": 10},
        "rb": {"start": record["length"] - 10, "end": record["length"]},
    }
    operation = validate_t_dna_operation(
        record,
        confirmation=forged_confirmation,
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 100,
            "end_coordinate": 101,
            "insertion_orientation": "forward",
        },
        workflow_id="single_gene",
    )
    assert operation["allowed"] is False
    assert operation["status"] == "vector_asset_contract_blocked"


def test_session_state_and_project_json_contract_snapshots_are_ignored() -> None:
    unknown = analyze_genbank_backbone_input(
        _unknown_raw(),
        project_id="tamper",
        display_name="AF234296.1",
        source_kind="upload",
        source_name="AF234296.1.gb",
    )
    for forged in (
        {**unknown, "asset_id": "pcambia1300_af234296_1", "asset_kind": "exact_insertion_source"},
        {**copy.deepcopy(unknown), "vector_asset_identity": _parsed("pcambia1300_af234296_1")["vector_asset_identity"]},
    ):
        assessment = validate_vector_operation(
            forged,
            workflow_id="single_gene_rice_alb",
            insertion_settings={
                "mode": "insertion",
                "start_coordinate": 27,
                "end_coordinate": 28,
                "insertion_orientation": "forward",
            },
        )
        assert assessment["allowed"] is False
        assert assessment["identity"]["asset_id"] is None


def test_legacy_unsafe_project_remains_read_only_after_json_round_trip() -> None:
    record = _parsed("r229_local_example")
    serialized = copy.deepcopy(record)
    assessment = assess_legacy_project_vector(
        serialized,
        workflow_id="single_gene",
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 2100,
            "end_coordinate": 2101,
            "insertion_orientation": "forward",
        },
    )
    assert assessment["legacy_project_read_only"] is True
    assert assessment["completed_design_allowed"] is False
    assert assessment["modified_vector_export_allowed"] is False


def test_service_layer_rejects_outside_ui_without_traceback() -> None:
    record = _parsed("pbin19_u09365_1")
    with pytest.raises(VectorAssetAdmissionError) as caught:
        require_vector_operation(
            record,
            workflow_id="single_gene",
            insertion_settings={
                "mode": "replacement",
                "start_coordinate": 6191,
                "end_coordinate": 9259,
                "insertion_orientation": "forward",
            },
        )
    message = str(caught.value)
    assert "Traceback" not in message
    assert 'File "' not in message


def test_formal_single_gene_generator_blocks_before_legacy_composer(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _parsed("pbin19_u09365_1")
    called = False

    def _legacy_composer(**kwargs):
        nonlocal called
        called = True
        return kwargs

    monkeypatch.setattr(formal_single_gene_runtime, "generate_complete_vector", _legacy_composer)
    with pytest.raises(VectorAssetAdmissionError):
        formal_single_gene_runtime.generate_admitted_complete_vector(
            input_records={"backbone": record},
            insertion_settings={
                "mode": "insertion",
                "start_coordinate": 2100,
                "end_coordinate": 2101,
                "insertion_orientation": "forward",
            },
            workflow_id="single_gene",
        )
    assert called is False


def test_formal_multi_tu_generator_blocks_before_legacy_composer(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _parsed("r229_local_example")
    called = False

    def _legacy_composer(*args, **kwargs):
        nonlocal called
        called = True
        return {"args": args, "kwargs": kwargs}

    monkeypatch.setattr(mvp_multi_tu_runtime, "generate_multi_tu_complete_plasmid", _legacy_composer)
    with pytest.raises(VectorAssetAdmissionError):
        mvp_multi_tu_runtime.generate_admitted_multi_tu_complete_plasmid(
            {"project_type": "multi_tu"},
            backbone=record,
            insertion_settings={
                "mode": "insertion",
                "start_coordinate": 2100,
                "end_coordinate": 2101,
                "insertion_orientation": "forward",
            },
            workflow_id="generic_multi_tu",
        )
    assert called is False


def test_empty_input_is_not_a_vector_asset() -> None:
    identity = classify_vector_asset({"normalized_sequence": "", "topology": "circular"})
    assert identity["identity_status"] == "NOT_A_VECTOR_ASSET"
    assert identity["read_only"] is True
