from __future__ import annotations

import hashlib
import json
from io import StringIO
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

import services.genbank_construct_inspector as inspector_module
from services.genbank_construct_inspector import (
    INSPECTION_SCOPE,
    inspect_genbank_construct,
)


def _record_bytes(
    *,
    topology: str,
    include_cds: bool = True,
    include_compound: bool = False,
    sequence: str = "AAAATGGCTTAACCGGTTCCAAGGTTCCAA",
) -> bytes:
    record = SeqRecord(
        Seq(sequence),
        id="local_fixture",
        name="local_fixture",
        description="local structural inspection fixture",
    )
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = topology
    record.features = [
        SeqFeature(
            FeatureLocation(0, len(sequence), strand=1),
            type="source",
            qualifiers={"label": ["local record"]},
        )
    ]
    if include_cds:
        record.features.append(
            SeqFeature(
                FeatureLocation(3, 12, strand=1),
                type="CDS",
                qualifiers={"label": ["local CDS"]},
            )
        )
    if include_compound:
        record.features.append(
            SeqFeature(
                CompoundLocation(
                    [
                        FeatureLocation(len(sequence) - 4, len(sequence), strand=1),
                        FeatureLocation(0, 3, strand=1),
                    ],
                    operator="join",
                ),
                type="misc_feature",
                qualifiers={"note": ["origin-spanning local feature"]},
            )
        )
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue().encode("ascii")


def _check(result: dict, check_id: str) -> dict:
    return next(item for item in result["checks"] if item["check_id"] == check_id)


def test_valid_circular_genbank_reports_structural_metadata_and_compound_location() -> None:
    raw = _record_bytes(topology="circular", include_compound=True)

    result = inspect_genbank_construct(raw)

    assert result["status"] == "PASS"
    assert result["scope"] == INSPECTION_SCOPE
    assert result["topology"] == "circular"
    assert result["sequence_length"] == 30
    assert result["feature_count"] == 3
    assert _check(result, "feature_coordinates")["status"] == "PASS"
    compound = _check(result, "compound_locations")
    assert compound["status"] == "PASS"
    assert compound["evidence"]["compound_feature_ordinals"] == [3]
    assert compound["evidence"]["cross_origin_feature_ordinals"] == [3]


def test_valid_linear_genbank_reports_linear_topology_without_cds_assumption() -> None:
    result = inspect_genbank_construct(
        _record_bytes(topology="linear", include_cds=False)
    )

    assert result["status"] == "PASS"
    assert result["topology"] == "linear"
    assert _check(result, "topology_metadata")["status"] == "PASS"
    assert _check(result, "cds_deterministic_checks")["status"] == "NOT_APPLICABLE"


def test_reverse_strand_feature_uses_biopython_location_semantics() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    record = SeqIO.read(StringIO(raw.decode("ascii")), "genbank")
    record.features.append(
        SeqFeature(
            FeatureLocation(4, 9, strand=-1),
            type="misc_feature",
            qualifiers={"note": ["reverse-strand fixture"]},
        )
    )
    output = StringIO()
    SeqIO.write(record, output, "genbank")

    result = inspect_genbank_construct(output.getvalue())

    assert result["status"] == "PASS"
    assert _check(result, "strand_metadata")["status"] == "PASS"
    assert result["provenance"]["feature_extraction"] == "Bio.SeqFeature.extract"


def test_between_base_location_is_preserved_as_valid_zero_length() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    text = raw.decode("ascii").replace(
        "     source          1..30",
        "     source          3^4",
    )
    parsed = SeqIO.read(StringIO(text), "genbank")
    location = parsed.features[0].location

    assert location is not None
    assert int(location.start) == int(location.end) == 3
    assert len(location) == 0
    assert str(parsed.features[0].extract(parsed.seq)) == ""

    result = inspect_genbank_construct(text)

    assert result["status"] == "PASS"
    coordinate_check = _check(result, "feature_coordinates")
    assert coordinate_check["status"] == "PASS"
    assert coordinate_check["evidence"]["zero_length_locations"] == [
        {
            "feature_ordinal": 1,
            "part_index": 1,
            "position_zero_based": 3,
        }
    ]
    assert coordinate_check["evidence"]["invalid_locations"] == []


def test_malformed_or_multi_record_input_fails_without_partial_inspection() -> None:
    empty = inspect_genbank_construct(b"")
    malformed = inspect_genbank_construct(b">not-genbank\nACGT\n")
    multiple = inspect_genbank_construct(
        _record_bytes(topology="linear", include_cds=False)
        + _record_bytes(topology="linear", include_cds=False)
    )

    assert empty["status"] == "FAIL"
    assert malformed["status"] == "FAIL"
    assert multiple["status"] == "FAIL"
    assert _check(malformed, "parseability")["status"] == "FAIL"
    assert _check(malformed, "feature_coordinates")["status"] == "NOT_APPLICABLE"
    assert _check(multiple, "parseability")["status"] == "FAIL"


def test_same_input_produces_identical_ordered_output() -> None:
    raw = _record_bytes(topology="circular", include_compound=True)

    first = inspect_genbank_construct(raw)
    second = inspect_genbank_construct(raw)

    assert first == second
    assert [item["check_id"] for item in first["checks"]] == [
        "parseability",
        "sequence_integrity",
        "topology_metadata",
        "feature_coordinates",
        "strand_metadata",
        "compound_locations",
        "canonical_intake_consistency",
        "cds_deterministic_checks",
        "qualifier_structure",
    ]


def test_out_of_bounds_feature_is_a_structural_failure() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    text = raw.decode("ascii").replace("     source          1..30", "     source          1..45")

    result = inspect_genbank_construct(text)

    assert result["status"] == "FAIL"
    coordinate_check = _check(result, "feature_coordinates")
    assert coordinate_check["status"] == "FAIL"
    assert coordinate_check["evidence"]["invalid_locations"][0] == {
        "feature_ordinal": 1,
        "part_index": 1,
        "start_zero_based": 0,
        "end_zero_based_exclusive": 45,
    }


def test_malformed_feature_location_is_a_deterministic_parse_failure() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    text = raw.decode("ascii").replace(
        "     source          1..30",
        "     source          30..1",
    )

    first = inspect_genbank_construct(text)
    second = inspect_genbank_construct(text)

    assert first == second
    assert first["status"] == "FAIL"
    parseability = _check(first, "parseability")
    assert parseability["status"] == "FAIL"
    assert parseability["evidence"]["reason_code"] == "genbank_parser_failed"
    assert _check(first, "feature_coordinates")["status"] == "NOT_APPLICABLE"
    assert "AttributeError" not in json.dumps(first, sort_keys=True)


def test_existing_canonical_intake_and_cds_validator_are_called(monkeypatch) -> None:
    calls = {"canonical": 0, "cds": 0}
    original_canonical = inspector_module.create_sequence_asset
    original_cds = inspector_module.analyze_cds_input

    def tracked_canonical(**kwargs):
        calls["canonical"] += 1
        return original_canonical(**kwargs)

    def tracked_cds(raw_text, **kwargs):
        calls["cds"] += 1
        return original_cds(raw_text, **kwargs)

    monkeypatch.setattr(inspector_module, "create_sequence_asset", tracked_canonical)
    monkeypatch.setattr(inspector_module, "analyze_cds_input", tracked_cds)

    result = inspect_genbank_construct(_record_bytes(topology="circular"))

    assert result["status"] == "PASS"
    assert calls == {"canonical": 1, "cds": 1}
    assert _check(result, "canonical_intake_consistency")["status"] == "PASS"
    assert _check(result, "cds_deterministic_checks")["status"] == "PASS"


def test_canonical_intake_exception_is_a_deterministic_failure(monkeypatch) -> None:
    def fail_canonical(**kwargs):
        raise RuntimeError("unstable canonical detail")

    monkeypatch.setattr(inspector_module, "create_sequence_asset", fail_canonical)

    result = inspect_genbank_construct(
        _record_bytes(topology="linear", include_cds=False)
    )

    assert result["status"] == "FAIL"
    canonical = _check(result, "canonical_intake_consistency")
    assert canonical["status"] == "FAIL"
    assert canonical["evidence"] == {"reason_code": "canonical_intake_failed"}
    assert "unstable canonical detail" not in json.dumps(result, sort_keys=True)


def test_cds_analyzer_exception_is_a_deterministic_failure(monkeypatch) -> None:
    def fail_cds(*args, **kwargs):
        raise RuntimeError("unstable analyzer detail")

    monkeypatch.setattr(inspector_module, "analyze_cds_input", fail_cds)
    raw = _record_bytes(topology="linear")

    first = inspect_genbank_construct(raw)
    second = inspect_genbank_construct(raw)

    assert first == second
    assert first["status"] == "FAIL"
    cds = _check(first, "cds_deterministic_checks")
    assert cds["status"] == "FAIL"
    assert cds["evidence"]["reason_code"] == "cds_analyzer_failed"
    assert cds["evidence"]["feature_ordinal"] == 2
    assert "unstable analyzer detail" not in json.dumps(first, sort_keys=True)


def test_feature_extraction_exception_is_a_deterministic_failure(monkeypatch) -> None:
    raw = _record_bytes(topology="linear")
    audit = inspector_module.parse_genbank_bytes(raw)
    original_extract = SeqFeature.extract

    monkeypatch.setattr(inspector_module, "parse_genbank_bytes", lambda _raw: audit)
    monkeypatch.setattr(
        inspector_module,
        "create_sequence_asset",
        lambda **kwargs: {
            "nucleotide_sequence": audit["sequence"],
            "length": audit["length"],
            "topology": audit["topology"],
            "imported_feature_records": [{} for _item in audit["features"]],
            "warnings": [],
        },
    )

    def fail_cds_extract(self, parent_sequence, references=None):
        if str(self.type).upper() == "CDS":
            raise RuntimeError("unstable extraction detail")
        return original_extract(self, parent_sequence, references)

    monkeypatch.setattr(SeqFeature, "extract", fail_cds_extract)

    result = inspect_genbank_construct(raw)

    assert result["status"] == "FAIL"
    cds = _check(result, "cds_deterministic_checks")
    assert cds["status"] == "FAIL"
    assert cds["evidence"]["reason_code"] == "feature_extraction_failed"
    assert cds["evidence"]["feature_ordinal"] == 2
    assert "unstable extraction detail" not in json.dumps(result, sort_keys=True)


def test_nonblocking_cds_findings_remain_review_warnings_without_claims() -> None:
    raw = _record_bytes(
        topology="circular",
        sequence="AAACCCGCTAAACCGGTTCCAAGGTTCCAAA",
    )

    result = inspect_genbank_construct(raw)
    rendered = json.dumps(result, sort_keys=True).casefold()

    assert result["status"] == "PASS_WITH_WARNINGS"
    assert _check(result, "cds_deterministic_checks")["status"] == "WARN"
    for forbidden in (
        "biological design is correct",
        "expression will succeed",
        "wet-lab ready",
        "promoter is optimal",
        "experimental success",
        "production readiness",
    ):
        assert forbidden not in rendered


def test_path_input_preserves_source_bytes_and_semantic_sequence(tmp_path: Path) -> None:
    raw = _record_bytes(topology="circular", include_compound=True)
    source = tmp_path / "local_construct.gb"
    source.write_bytes(raw)
    before = source.read_bytes()
    parsed_before = str(SeqIO.read(StringIO(raw.decode("ascii")), "genbank").seq).upper()

    result = inspect_genbank_construct(source)

    assert source.read_bytes() == before
    assert result["provenance"]["source_record_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["sequence_sha256"] == hashlib.sha256(parsed_before.encode("ascii")).hexdigest()
    assert result["provenance"]["sequence_mutation"] == "none"


def test_mixed_strand_is_a_structural_warning() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    record = SeqIO.read(StringIO(raw.decode("ascii")), "genbank")
    record.features.append(
        SeqFeature(
            CompoundLocation(
                [
                    FeatureLocation(2, 5, strand=1),
                    FeatureLocation(8, 11, strand=-1),
                ],
                operator="join",
            ),
            type="misc_feature",
            qualifiers={"label": ["mixed-strand fixture"]},
        )
    )
    output = StringIO()
    SeqIO.write(record, output, "genbank")

    result = inspect_genbank_construct(output.getvalue())

    assert result["status"] == "PASS_WITH_WARNINGS"
    assert _check(result, "strand_metadata")["status"] == "WARN"
    assert _check(result, "qualifier_structure")["status"] == "PASS"


def test_legal_valueless_and_unknown_qualifiers_are_structurally_valid() -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    record = SeqIO.read(StringIO(raw.decode("ascii")), "genbank")
    record.features[0].qualifiers = {
        "pseudo": [""],
        "custom_flag": ["retained value"],
    }
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    text = output.getvalue().replace('/pseudo=""', "/pseudo")

    reparsed = SeqIO.read(StringIO(text), "genbank")
    assert reparsed.features[0].qualifiers["pseudo"] == [""]
    assert reparsed.features[0].qualifiers["custom_flag"] == ["retained value"]

    result = inspect_genbank_construct(text)

    assert result["status"] == "PASS"
    assert _check(result, "qualifier_structure") == {
        "check_id": "qualifier_structure",
        "status": "PASS",
        "message": "Parsed qualifier keys and list-valued entries retain GenBank structural semantics.",
        "evidence": {"issue_count": 0},
    }


def test_malformed_qualifier_structure_is_reported_deterministically(monkeypatch) -> None:
    raw = _record_bytes(topology="linear", include_cds=False)
    audit = inspector_module.parse_genbank_bytes(raw)
    audit["features"][0]["qualifiers"] = {"broken": "not-a-list"}
    monkeypatch.setattr(inspector_module, "parse_genbank_bytes", lambda _raw: audit)

    first = inspect_genbank_construct(raw)
    second = inspect_genbank_construct(raw)

    assert first == second
    assert first["status"] == "PASS_WITH_WARNINGS"
    qualifier = _check(first, "qualifier_structure")
    assert qualifier["status"] == "WARN"
    assert qualifier["evidence"] == {
        "issues": [
            {
                "feature_ordinal": 1,
                "qualifier": "broken",
                "issue": "malformed_qualifier_values",
            }
        ],
        "issue_count": 1,
    }
