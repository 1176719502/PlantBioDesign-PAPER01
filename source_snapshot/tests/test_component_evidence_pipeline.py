import hashlib
import json
from pathlib import Path

import pytest

from tools.component_evidence_pipeline import EvidenceError, process


def gb(seq="AACCGGTT", feature="     regulatory       2..5\n                     /regulatory_class=\"terminator\"\n                     /note=\"nos terminator\"\n", *, topology="linear", accession="TEST0001.1", version="TEST0001.1"):
    return (f"LOCUS       TEST       {len(seq)} bp    DNA     {topology}\nACCESSION   {accession}\nVERSION     {version}\nFEATURES             Location/Qualifiers\n{feature}ORIGIN\n" + "        1 " + seq.lower() + "\n//\n").encode()


def test_raw_and_sequence_hash(tmp_path):
    src = tmp_path / "x.gb"; raw = gb(); src.write_bytes(raw)
    rec = process(src, tmp_path / "out")
    assert rec["source_artifact"]["raw_bytes"] == len(raw)
    assert rec["source_artifact"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert rec["exact_identity"]["sequence_sha256"] == hashlib.sha256(b"AACCGGTT").hexdigest()


def test_exact_and_reverse_complement_extraction(tmp_path):
    src = tmp_path / "x.gb"; src.write_bytes(gb("AACCGGTT"))
    assert process(src, tmp_path / "a", coordinates="2..5")["exact_identity"]["sequence"] == "ACCG"
    assert process(src, tmp_path / "b", coordinates="2..5", strand=-1)["exact_identity"]["sequence"] == "CGGT"


def test_terminator_preserved_and_ambiguous_review(tmp_path):
    src = tmp_path / "x.gb"; src.write_bytes(gb())
    rec = process(src, tmp_path / "out", feature_index=1)
    assert rec["role"]["deposited_feature_type"] == "regulatory"
    assert rec["role"]["regulatory_class"] == "terminator"
    assert rec["role"]["role"] == "terminator"
    ambiguous = gb(feature="     regulatory       2..5\n                     /note=\"5' regulatory region\"\n")
    src.write_bytes(ambiguous)
    rec = process(src, tmp_path / "amb", feature_index=1)
    assert rec["role"]["role_status"] == "review_required"
    assert rec["role"]["role"] is None


def test_malformed_coordinate_fails_closed(tmp_path):
    src = tmp_path / "bad.gb"; src.write_bytes(gb(feature="     regulatory       2..99\n"))
    with pytest.raises(EvidenceError):
        process(src, tmp_path / "out", feature_index=1)


def test_unrelated_partial_feature_does_not_block_source_or_valid_extraction(tmp_path):
    features = (
        "     regulatory       2..5\n"
        "                     /regulatory_class=\"terminator\"\n"
        "     gene              1..>8\n"
        "                     /gene=\"unresolved\"\n"
    )
    src = tmp_path / "mixed.gb"; src.write_bytes(gb(feature=features))
    whole = process(src, tmp_path / "whole")
    assert whole["source_artifact"]["sequence_length"] == 8
    assert whole["source_artifact"]["sequence_sha256"] == hashlib.sha256(b"AACCGGTT").hexdigest()
    assert whole["exact_identity"]["sequence"] == "AACCGGTT"
    assert len(whole["review_required_features"]) == 1
    gap = whole["review_required_features"][0]
    assert gap["location"] == "1..>8"
    assert gap["raw_location"] == "1..>8"
    assert gap["review_reason"]

    selected = process(src, tmp_path / "selected", feature_index=1)
    assert selected["exact_identity"]["sequence"] == "ACCG"


def test_selecting_partial_feature_fails_closed_without_exact_identity(tmp_path):
    features = (
        "     regulatory       2..5\n"
        "                     /regulatory_class=\"terminator\"\n"
        "     gene              1..>8\n"
    )
    src = tmp_path / "partial.gb"; src.write_bytes(gb(feature=features))
    with pytest.raises(EvidenceError):
        process(src, tmp_path / "out", feature_index=2)
    assert not (tmp_path / "out" / "evidence.json").exists()


def test_duplicate_and_deterministic_outputs(tmp_path):
    src = tmp_path / "x.gb"; src.write_bytes(gb("AACCGGTT"))
    one = process(src, tmp_path / "one", candidate_id="C1")
    two = process(src, tmp_path / "two", candidate_id="C1")
    assert one == two
    assert json.loads((tmp_path / "one" / "evidence.json").read_text()) == one
    assert one["formal_admission_status"] == "NOT_ADMITTED"
    assert one["host_eligibility_status"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("header", [
    dict(accession="", version="TEST0001.1"),
    dict(accession="TEST0001.1", version=""),
    dict(accession="TEST0001.1", version="BAD"),
    dict(accession="TEST0001.1", version="OTHER.1"),
])
def test_authoritative_accession_version_is_required(tmp_path, header):
    src = tmp_path / "identity.gb"; src.write_bytes(gb(**header))
    with pytest.raises(EvidenceError): process(src, tmp_path / "out")


@pytest.mark.parametrize("location", ["<2..5", ">2..5", "join(<1..2,3..4)", "order(1..2,3..4)"])
def test_unsupported_or_partial_locations_fail_closed(tmp_path, location):
    src = tmp_path / "bad.gb"; src.write_bytes(gb(feature=f"     regulatory       {location}\n"))
    with pytest.raises(EvidenceError): process(src, tmp_path / "out", feature_index=1)


def test_compound_strand_semantics_are_preserved(tmp_path):
    seq = "AACCGGTTCCAA"
    src = tmp_path / "compound.gb"; src.write_bytes(gb(seq, feature="     misc_feature     join(1..2,5..6)\n"))
    rec = process(src, tmp_path / "out", feature_index=1)
    assert rec["exact_identity"]["sequence"] == "AAGG"
    assert [row["strand"] for row in rec["exact_identity"]["coordinates"]] == [1, 1]

    src.write_bytes(gb(seq, feature="     misc_feature     complement(join(1..2,5..6))\n"))
    rec = process(src, tmp_path / "reverse", feature_index=1)
    assert rec["exact_identity"]["sequence"] == "CCTT"
    assert rec["exact_identity"]["strand"] == -1

    src.write_bytes(gb(seq, feature="     misc_feature     join(complement(1..2),5..6)\n"))
    with pytest.raises(EvidenceError): process(src, tmp_path / "mixed", feature_index=1)


def test_circular_origin_crossing_extracts_and_linear_crossing_rejects(tmp_path):
    src = tmp_path / "circular.gb"; src.write_bytes(gb("AACCGGTT", topology="circular", feature="     misc_feature     7..2\n"))
    assert process(src, tmp_path / "circular", feature_index=1)["exact_identity"]["sequence"] == "TTAA"
    src.write_bytes(gb("AACCGGTT", topology="linear", feature="     misc_feature     7..2\n"))
    with pytest.raises(EvidenceError): process(src, tmp_path / "linear", feature_index=1)


def test_canonical_outputs_do_not_depend_on_source_path(tmp_path):
    raw = gb("AACCGGTT")
    left = tmp_path / "left" / "same.gb"; right = tmp_path / "right" / "same.gb"
    left.parent.mkdir(); right.parent.mkdir(); left.write_bytes(raw); right.write_bytes(raw)
    process(left, tmp_path / "out-left", candidate_id="C1"); process(right, tmp_path / "out-right", candidate_id="C1")
    for name in ("evidence.json", "summary.csv", "review.md"):
        assert (tmp_path / "out-left" / name).read_bytes() == (tmp_path / "out-right" / name).read_bytes()
