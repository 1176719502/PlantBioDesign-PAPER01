from __future__ import annotations

from io import StringIO

import pytest
from Bio import SeqIO
from Bio.SeqFeature import CompoundLocation

from scripts.validation.validate_single_gene_accuracy import (
    DNA_ALPHABET,
    assert_sequences_equal,
    inspect_raw_genbank,
    parse_fasta_text,
    sha256_sequence,
)
from tests.mvp7_single_gene_test_support import (
    CASES,
    build_production_result,
    normalize_expected_features,
)


def _parsed_genbank_features(record) -> list[dict]:  # noqa: ANN001
    features = []
    for feature in record.features:
        qualifiers = feature.qualifiers or {}
        name = str((qualifiers.get("label") or qualifiers.get("gene") or [feature.type])[0])
        parts = list(getattr(feature.location, "parts", None) or [feature.location])
        features.append(
            {
                "name": name,
                "feature_type": str(feature.type),
                "strand": int(feature.location.strand or 1),
                "parts_0_based_half_open": sorted(
                    [
                        {
                            "start": int(part.start),
                            "end": int(part.end),
                            "strand": int(part.strand or feature.location.strand or 1),
                        }
                        for part in parts
                    ],
                    key=lambda part: (part["start"], part["end"], part["strand"]),
                ),
                "compound": isinstance(feature.location, CompoundLocation),
            }
        )
    return sorted(
        features,
        key=lambda item: (
            min(part["start"] for part in item["parts_0_based_half_open"]),
            max(part["end"] for part in item["parts_0_based_half_open"]),
            item["name"],
        ),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_fasta_and_genbank_exports_are_independently_compatible(case: dict) -> None:
    result = build_production_result(case)
    expected = case["expected"]
    fasta_text = result["exports"]["fasta"]["data"]
    genbank_text = result["exports"]["genbank"]["data"]

    stdlib_fasta = parse_fasta_text(fasta_text)
    assert len(stdlib_fasta) == 1
    assert_sequences_equal(expected["plasmid_sequence"], stdlib_fasta[0]["sequence"], label=f"{case['case_id']} stdlib FASTA")
    assert set(stdlib_fasta[0]["sequence"]) <= DNA_ALPHABET

    biopython_fasta = list(SeqIO.parse(StringIO(fasta_text), "fasta"))
    assert len(biopython_fasta) == 1
    assert str(biopython_fasta[0].seq).upper() == expected["plasmid_sequence"]
    retitled = ">title-does-not-change-sequence\n" + "\n".join(fasta_text.splitlines()[1:]) + "\n"
    assert parse_fasta_text(retitled)[0]["sequence"] == expected["plasmid_sequence"]
    assert parse_fasta_text(fasta_text.replace("\n", "\r\n"))[0]["sequence"] == expected["plasmid_sequence"]

    records = list(SeqIO.parse(StringIO(genbank_text), "genbank"))
    assert len(records) == 1
    record = records[0]
    assert str(record.seq).upper() == expected["plasmid_sequence"]
    assert len(record.seq) == expected["plasmid_length"]
    assert str(record.annotations.get("topology") or "").lower() == case["topology"]
    assert sha256_sequence(str(record.seq)) == expected["plasmid_sha256"]

    parsed_features = _parsed_genbank_features(record)
    expected_features = [
        {
            "name": feature["name"],
            "feature_type": feature["feature_type"],
            "strand": feature["strand"],
            "parts_0_based_half_open": feature["parts_0_based_half_open"],
        }
        for feature in normalize_expected_features(case)
    ]
    comparable_parsed = [
        {
            "name": feature["name"],
            "feature_type": feature["feature_type"],
            "strand": feature["strand"],
            "parts_0_based_half_open": feature["parts_0_based_half_open"],
        }
        for feature in parsed_features
    ]
    assert comparable_parsed == expected_features

    component_names = set(case["component_names"].values())
    assert component_names <= {feature["name"] for feature in parsed_features}
    for feature in parsed_features:
        assert feature["strand"] == case["expected"]["expected_strands"][feature["name"]]

    if case["case_id"] in {"case_09_cross_origin_feature", "case_10_complex_uploaded_genbank"}:
        cross_origin = next(feature for feature in parsed_features if "CROSS" in feature["name"] or "CROSS_ORIGIN" in feature["name"])
        assert cross_origin["compound"] is True
        assert len(cross_origin["parts_0_based_half_open"]) == 2
    if case["case_id"] == "case_08_reverse_strand_feature":
        reverse = next(feature for feature in parsed_features if feature["name"] == "REVERSE_08")
        assert reverse["strand"] == -1

    raw = inspect_raw_genbank(genbank_text)
    assert raw == {
        "has_locus": True,
        "topology": case["topology"],
        "has_features": True,
        "has_origin": True,
        "terminated": True,
        "declared_length": expected["plasmid_length"],
        "actual_sequence_length": expected["plasmid_length"],
        "origin_sequence": expected["plasmid_sequence"],
    }

    rewritten = StringIO()
    SeqIO.write(record, rewritten, "genbank")
    reparsed = next(SeqIO.parse(StringIO(rewritten.getvalue()), "genbank"))
    assert str(reparsed.seq).upper() == expected["plasmid_sequence"]
