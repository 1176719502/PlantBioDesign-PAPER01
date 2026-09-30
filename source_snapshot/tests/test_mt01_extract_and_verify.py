from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import pytest

from tools.real_case_contracts import mt01_extract_and_verify as mt01


ROOT = Path(__file__).resolve().parents[1]


def _write_record(path: Path, *, record_id: str, sequence: str, topology: str = "circular") -> None:
    record = SeqRecord(Seq(sequence), id=record_id, name=record_id.split(".")[0])
    record.annotations.update({"molecule_type": "DNA", "topology": topology})
    SeqIO.write(record, path, "genbank")


def _contracts_for_raw_file(path: Path) -> dict:
    contracts = copy.deepcopy(mt01.load_contracts())
    raw = path.read_bytes()
    contracts["expected_hashes"]["raw_source_file_sha256"] = hashlib.sha256(raw).hexdigest()
    contracts["source_contract"]["expected_response"]["raw_file_size_bytes"] = len(raw)
    return contracts


def test_reverse_tu_input_model_has_exactly_one_whole_unit_reverse_complement() -> None:
    three_prime_physical = "AACCGG"
    cds_physical = "ATGCCCTAA"
    promoter_physical = "GGTTAACC"
    promoter_input = mt01._reverse_complement(promoter_physical)
    cds_input = mt01._reverse_complement(cds_physical)
    three_prime_input = mt01._reverse_complement(three_prime_physical)

    reconstructed = mt01._reverse_complement(
        promoter_input + cds_input + three_prime_input
    )
    assert reconstructed == three_prime_physical + cds_physical + promoter_physical
    assert reconstructed != promoter_input + cds_input + three_prime_input


def test_forward_tu_input_model_is_identity_concatenation() -> None:
    promoter = "AACCGG"
    cds = "ATGCCCTAA"
    three_prime = "GGTTAACC"
    assert promoter + cds + three_prime == "AACCGGATGCCCTAAGGTTAACC"


def test_off_by_one_coordinate_contract_is_rejected() -> None:
    contracts = copy.deepcopy(mt01.load_contracts())
    contracts["extraction_contract"]["extraction"]["source_interval"][
        "external_1_based_inclusive"
    ]["start"] = 570
    with pytest.raises(mt01.Mt01VerificationError, match="off-by-one"):
        mt01.verify_contract_consistency(contracts)


def test_partition_gap_and_overlap_are_rejected() -> None:
    contracts = copy.deepcopy(mt01.load_contracts())
    contracts["extraction_contract"]["transcription_units"][1]["source_interval"][
        "internal_0_based_half_open"
    ]["start"] = 2324
    contracts["extraction_contract"]["transcription_units"][1]["source_interval"][
        "external_1_based_inclusive"
    ]["start"] = 2325
    contracts["extraction_contract"]["transcription_units"][1]["source_interval"][
        "length_bp"
    ] = 2325
    with pytest.raises(mt01.Mt01VerificationError, match="Partition gap"):
        mt01.verify_contract_consistency(contracts)


def test_missing_source_file_has_actionable_error(tmp_path: Path) -> None:
    missing = tmp_path / "KX758647.1.gb"
    with pytest.raises(mt01.Mt01VerificationError, match="Provide a local KX758647.1"):
        mt01.verify_source_file(missing)


def test_wrong_raw_file_is_rejected_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "KX758647.1.gb"
    path.write_text("not a GenBank record", encoding="ascii")
    with pytest.raises(mt01.Mt01VerificationError, match="Raw source file SHA-256"):
        mt01.verify_source_file(path)


def test_wrong_accession_version_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wrong-version.gb"
    _write_record(path, record_id="KX758647.2", sequence="A" * 20)
    contracts = _contracts_for_raw_file(path)
    monkeypatch.setattr(mt01, "load_contracts", lambda _path=mt01.DEFAULT_CONTRACT_DIR: contracts)
    with pytest.raises(mt01.Mt01VerificationError, match="version mismatch"):
        mt01.verify_source_file(path)


def test_wrong_source_length_is_upstream_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wrong-length.gb"
    _write_record(path, record_id="KX758647.1", sequence="A" * 20)
    contracts = _contracts_for_raw_file(path)
    monkeypatch.setattr(mt01, "load_contracts", lambda _path=mt01.DEFAULT_CONTRACT_DIR: contracts)
    with pytest.raises(mt01.Mt01VerificationError, match=mt01.UPSTREAM_MISMATCH):
        mt01.verify_source_file(path)


def test_wrong_source_sha_is_upstream_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wrong-source-sha.gb"
    _write_record(path, record_id="KX758647.1", sequence="A" * 7086)
    contracts = _contracts_for_raw_file(path)
    monkeypatch.setattr(mt01, "load_contracts", lambda _path=mt01.DEFAULT_CONTRACT_DIR: contracts)
    with pytest.raises(mt01.Mt01VerificationError, match="source sequence SHA-256"):
        mt01.verify_source_file(path)


def test_wrong_region_sha_is_upstream_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wrong-region-sha.gb"
    sequence = "A" * 7086
    _write_record(path, record_id="KX758647.1", sequence=sequence)
    contracts = _contracts_for_raw_file(path)
    fake_source_hash = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    contracts["expected_hashes"]["source_sequence_sha256"] = fake_source_hash
    contracts["source_contract"]["parsed_record"]["sequence_sha256"] = fake_source_hash
    contracts["source_contract"]["parsed_record"]["feature_count"] = 0
    contracts["feature_contract"]["source_feature_assertions"] = []
    monkeypatch.setattr(mt01, "load_contracts", lambda _path=mt01.DEFAULT_CONTRACT_DIR: contracts)
    with pytest.raises(mt01.Mt01VerificationError, match="extracted region SHA-256"):
        mt01.verify_source_file(path)


def test_output_and_fetch_cache_paths_must_be_outside_repository() -> None:
    with pytest.raises(mt01.Mt01VerificationError, match="outside the repository"):
        mt01._require_external_path(ROOT / "mt01-output.json", label="Verification JSON output")
    with pytest.raises(mt01.Mt01VerificationError, match="outside the repository"):
        mt01.fetch_source("KX758647.1", ROOT / "source-cache", mt01.load_contracts()["source_contract"])


def test_unversioned_or_wrong_accession_is_rejected_without_network(tmp_path: Path) -> None:
    with pytest.raises(mt01.Mt01VerificationError, match="exact accession/version"):
        mt01.fetch_source("KX758647", tmp_path / "cache", mt01.load_contracts()["source_contract"])


def test_default_contract_tests_do_not_require_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network was called")

    monkeypatch.setattr(mt01.urllib.request, "urlopen", forbidden)
    assert mt01.load_contracts()["source_contract"]["record_id"] == "KX758647.1"


@pytest.mark.skipif(
    not os.environ.get("MT01_GENBANK_PATH"),
    reason="Set MT01_GENBANK_PATH to the repository-external KX758647.1 GenBank file.",
)
def test_external_kx758647_source_full_verification_and_safe_output() -> None:
    verify_runtime = os.environ.get("MT01_VERIFY_RUNTIME") == "1"
    result = mt01.verify_source_file(
        Path(os.environ["MT01_GENBANK_PATH"]),
        verify_runtime=verify_runtime,
        runtime_timeout_seconds=30,
    )
    assert result["status"] == "pass"
    assert result["source"]["parsed_record_id"] == "KX758647.1"
    assert result["source"]["parsed_sequence_length_bp"] == 7086
    assert result["region"]["length_bp"] == 4079
    assert result["proofs"] == {
        "source_slice": "pass",
        "tu_physical_concatenation": "pass",
        "tu1_reverse_input_reconstruction": "pass",
        "tu2_forward_input_reconstruction": "pass",
        "atomic_partition": "pass",
        "all_nucleotides_known": True,
    }
    serialized = json.dumps(result, sort_keys=True)
    assert not re.search(r"[ACGT]{100,}", serialized)
    assert all("sequence" not in item or "sequence_sha256" in item for item in result["components"])
    if verify_runtime:
        assert result["runtime_verification"] == {
            "status": "pass",
            "result_kind": "MULTI_TU_EXPRESSION_ASSEMBLY",
            "topology": "linear",
            "contains_vector": False,
            "tu_count": 2,
            "canonical_length_bp": 4079,
            "canonical_sequence_sha256": "1847b411bd0592e0927db433bfc88f8eec3a9f8c30620af97aba5dae465c3104",
            "runtime_model_gap_code": None,
        }
