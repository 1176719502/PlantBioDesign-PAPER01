from __future__ import annotations

import hashlib
from io import StringIO

import pytest
from Bio import SeqIO

from mvp_app import generate_complete_vector, load_real_case


def test_real_fixture_builds_and_reparses_complete_circular_plasmid() -> None:
    result = generate_complete_vector(load_real_case())

    assert result["input_lengths"] == {
        "promoter": 640,
        "cds": 900,
        "terminator": 210,
        "backbone": 4200,
    }
    assert result["cassette_length"] == 1750
    assert result["plasmid_length"] == 5950
    assert result["plasmid_sha256"] == "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"
    assert result["fasta_sequence_sha256"] == result["plasmid_sha256"]
    assert result["genbank_sequence_sha256"] == result["plasmid_sha256"]


def test_invalid_cds_is_blocked_before_complete_vector_export() -> None:
    case = load_real_case()
    case["cds"] = ">invalid_cds\nATGTAATAA\n"

    with pytest.raises(RuntimeError, match="CDS 输入未通过校验"):
        generate_complete_vector(case)


def _parsed_feature_signature(genbank_text: str) -> list[tuple[object, ...]]:
    record = next(SeqIO.parse(StringIO(genbank_text), "genbank"))
    return [
        (
            feature.type,
            int(feature.location.start) + 1,
            int(feature.location.end),
            int(feature.location.strand or 1),
            tuple(
                (key, tuple(values))
                for key, values in sorted((feature.qualifiers or {}).items())
            ),
        )
        for feature in record.features
    ]


def test_independent_real_case_exports_are_byte_identical_and_keep_circular_feature_semantics() -> None:
    first = generate_complete_vector(load_real_case())
    second = generate_complete_vector(load_real_case())

    first_fasta = first["exports"]["fasta"]["data"]
    second_fasta = second["exports"]["fasta"]["data"]
    first_genbank = first["exports"]["genbank"]["data"]
    second_genbank = second["exports"]["genbank"]["data"]
    assert first_fasta == second_fasta
    assert first_genbank == second_genbank
    assert hashlib.sha256(first_fasta.encode("utf-8")).hexdigest() == hashlib.sha256(second_fasta.encode("utf-8")).hexdigest()
    assert hashlib.sha256(first_genbank.encode("utf-8")).hexdigest() == hashlib.sha256(second_genbank.encode("utf-8")).hexdigest()

    first_fasta_record = next(SeqIO.parse(StringIO(first_fasta), "fasta"))
    first_genbank_record = next(SeqIO.parse(StringIO(first_genbank), "genbank"))
    second_genbank_record = next(SeqIO.parse(StringIO(second_genbank), "genbank"))
    assert len(first_fasta_record.seq) == 5950
    assert len(first_genbank_record.seq) == 5950
    assert str(first_fasta_record.seq) == str(first_genbank_record.seq) == str(second_genbank_record.seq)
    assert str(first_genbank_record.annotations.get("topology", "")).lower() == "circular"
    assert _parsed_feature_signature(first_genbank) == _parsed_feature_signature(second_genbank)
    assert [(item[0], item[1], item[2]) for item in _parsed_feature_signature(first_genbank)] == [
        ("rep_origin", 120, 380),
        ("misc_feature", 1850, 1940),
        ("promoter", 2101, 2740),
        ("cds", 2741, 3640),
        ("terminator", 3641, 3850),
        ("misc_feature", 4350, 4500),
        ("misc_feature", 5250, 5410),
    ]
    assert "plasmid-" not in first_fasta
    assert "rev=" not in first_fasta
    assert "gbfeature-" not in first_genbank
