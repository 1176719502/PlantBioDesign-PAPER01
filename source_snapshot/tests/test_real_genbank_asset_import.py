from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from services.real_genbank_asset_import import (
    PBI121_ACCESSION,
    PBI121_EXPECTED_LENGTH,
    PBI121_SOURCE_RECORD,
    RealGenBankAssetError,
    build_pbi121_asset_bundle,
    load_library_state,
    parse_genbank_bytes,
    save_library_state,
)


def test_pbi121_official_record_identity_and_immutable_source_hash() -> None:
    raw = PBI121_SOURCE_RECORD.read_bytes()
    audit = parse_genbank_bytes(raw)

    assert audit["accession"] == PBI121_ACCESSION
    assert audit["record_name"] == "pBI121"
    assert audit["length"] == PBI121_EXPECTED_LENGTH
    assert audit["topology"] == "circular"
    assert audit["source_record_sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(audit["features"]) == 21
    assert {row["type"] for row in audit["features"]} == {"source", "misc_feature", "rep_origin", "regulatory", "gene", "CDS"}


def test_feature_audit_preserves_locations_qualifiers_strands_and_sequence_hashes() -> None:
    audit = parse_genbank_bytes(PBI121_SOURCE_RECORD.read_bytes())
    promoter = next(row for row in audit["features"] if row["biological_role"] == "CaMV 35S promoter")
    left_border = next(row for row in audit["features"] if row["asset_type"] == "left_border")

    assert promoter["location_expression"] == "[4973:5808](+)"
    assert promoter["start_one_based"] == 4974
    assert promoter["end_one_based_inclusive"] == 5808
    assert promoter["strand"] == 1
    assert promoter["qualifiers"] == {"regulatory_class": ["promoter"], "note": ["CaMV 35S"]}
    assert len(promoter["sequence_sha256"]) == 64
    assert left_border["location_expression"] == "[8620:8646](-)"
    assert left_border["strand"] == -1


def test_only_explicit_features_become_registered_real_assets() -> None:
    bundle = build_pbi121_asset_bundle()
    vector = bundle["vector"]
    asset_types = [asset["asset_type"] for asset in bundle["components"]]

    assert vector["asset_type"] == "complete_binary_vector"
    assert vector["length"] == PBI121_EXPECTED_LENGTH
    assert vector["topology"] == "circular"
    assert vector["non_empty_t_dna"] is True
    assert vector["provenance_status"] == "verified_source"
    assert vector["verification_status"] == "exact_replacement_contract_verified"
    assert vector["asset_kind"] == "tDNA_replacement_source"
    assert vector["requires_exact_replacement"] is True
    assert vector["direct_insert_allowed"] is False
    assert vector["reference_access"] is True
    assert vector["eligible_for_construct_use"] is True
    assert vector["replaceable_region"] == {
        "start": 4974,
        "end": 7979,
        "coordinate_system": "1-based-inclusive",
    }
    assert asset_types.count("promoter") == 1
    assert asset_types.count("three_prime_regulatory_region") == 2
    assert "left_border" in asset_types and "right_border" in asset_types
    assert "selectable_marker_cassette" in asset_types
    assert "reporter_cassette" in asset_types
    assert all(asset["exact_sequence"] for asset in bundle["components"])
    assert all("other_feature" not in asset_types for asset in bundle["components"])


def test_unclassified_features_remain_other_feature_without_inference() -> None:
    audit = parse_genbank_bytes(PBI121_SOURCE_RECORD.read_bytes())
    feature = next(row for row in audit["features"] if row["type"] == "rep_origin")

    assert feature["asset_type"] == "other_feature"
    assert feature["provenance_status"] == "needs_feature_review"
    assert feature["registerable_component"] is False


def test_uploaded_source_uses_same_parser_and_rejects_non_genbank() -> None:
    raw = PBI121_SOURCE_RECORD.read_bytes()
    assert parse_genbank_bytes(raw) == parse_genbank_bytes(raw)
    with pytest.raises(RealGenBankAssetError):
        parse_genbank_bytes(b">not-a-genbank\nACGT\n")


def test_compound_mixed_strand_and_origin_spanning_locations_are_retained() -> None:
    record = SeqRecord(Seq("A" * 20), id="synthetic.1", name="synthetic", description="location support")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"
    record.features = [
        SeqFeature(
            CompoundLocation([FeatureLocation(15, 20, strand=1), FeatureLocation(0, 5, strand=1)]),
            type="misc_feature",
            qualifiers={"note": ["origin spanning"]},
        ),
        SeqFeature(
            CompoundLocation([FeatureLocation(2, 4, strand=1), FeatureLocation(8, 10, strand=-1)]),
            type="misc_feature",
            qualifiers={"note": ["mixed strand"]},
        ),
    ]
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    audit = parse_genbank_bytes(output.getvalue().encode("ascii"))
    origin_spanning, mixed = audit["features"]

    assert origin_spanning["location_operator"] == "join"
    assert origin_spanning["crosses_origin"] is True
    assert origin_spanning["location_parts"] == [
        {"start_zero_based": 15, "end_zero_based_exclusive": 20, "start_one_based": 16, "end_one_based_inclusive": 20, "strand": 1},
        {"start_zero_based": 0, "end_zero_based_exclusive": 5, "start_one_based": 1, "end_one_based_inclusive": 5, "strand": 1},
    ]
    assert mixed["mixed_strand"] is True
    assert mixed["strand"] is None
    assert len(mixed["sequence_sha256"]) == 64


def test_manual_border_review_state_survives_cold_start(tmp_path: Path) -> None:
    saved = save_library_state(
        left_border_confirmed=True,
        right_border_confirmed=True,
        t_dna_direction_confirmation="LB_to_RB",
        runtime_root=tmp_path,
    )
    reopened = load_library_state(runtime_root=tmp_path)

    assert saved["asset_saved"] is True
    assert reopened["left_border_confirmed"] is True
    assert reopened["right_border_confirmed"] is True
    assert reopened["t_dna_direction_confirmation"] == "LB_to_RB"
    assert reopened["source_record_sha256"] == build_pbi121_asset_bundle()["audit"]["source_record_sha256"]
