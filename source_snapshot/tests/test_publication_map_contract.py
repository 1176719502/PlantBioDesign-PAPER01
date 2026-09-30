from __future__ import annotations

import hashlib
import json
import sys
import types
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from services.publication_map_adapter import (
    AuthoritativePublicationMapSource,
    adapt_publication_map_source,
    publication_map_document_from_runtime,
)
from services.publication_map_contract import (
    AUTHORITATIVE_COORDINATE_CONVENTION,
    DISPLAY_COORDINATE_CONVENTION,
    FeatureClassificationState,
    PublicationMapContractError,
    PublicationMapTopology,
    PublicationMapViewType,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "publication_map_v1"
DENSE_FIXTURE_PATH = FIXTURE_ROOT / "dense_synthetic_plant_binary_vector.json"
LINEAR_FIXTURE_PATH = FIXTURE_ROOT / "linear_active_expression_construct.json"
ORIGIN_WRAP_FIXTURE_PATH = FIXTURE_ROOT / "standard_genbank_origin_wraps.json"


def _linear_snapshot(sequence: str = "ACGT" * 25) -> dict[str, object]:
    checksum = hashlib.sha256(sequence.encode("utf-8")).hexdigest()
    transcription_unit = {
        "tu_id": "tu:test",
        "generated_nucleotide_sequence": sequence,
        "generated_sequence_checksum": checksum,
        "revision_id": "revision:test",
        "stale": False,
        "validation_findings": [],
        "feature_coordinates": [
            {"name": "CDS", "type": "CDS", "start": 2, "end": 12, "strand": -1}
        ],
    }
    construct = {
        "construct_id": "construct:test",
        "transcription_unit_id": "tu:test",
        "construct_status": "current",
        "canonical_generated_sequence": sequence,
        "sequence_checksum": checksum,
        "current_revision": "revision:test",
        "validation_summary": {"blocking_count": 0},
    }
    runtime = {
        "schema_version": "runtime:test",
        "active_transcription_unit_id": "tu:test",
        "active_construct_id": "construct:test",
        "transcription_units": [transcription_unit],
        "constructs": [construct],
    }
    return {
        "runtime": runtime,
        "construct_id": "construct:test",
        "construct_status": "current",
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_checksum": checksum,
        "revision_id": "revision:test",
        "validation_summary": {"blocking_count": 0},
    }


def _circular_snapshot(sequence: str = "N" * 100) -> dict[str, object]:
    checksum = hashlib.sha256(sequence.encode("utf-8")).hexdigest()
    plasmid = {
        "plasmid_id": "plasmid:test",
        "construct_status": "current",
        "generated_nucleotide_sequence": sequence,
        "sequence_checksum": checksum,
        "current_revision": "revision:plasmid",
        "topology": "circular",
        "combined_feature_coordinates": [
            {"name": "Origin", "type": "rep_origin", "start": 20, "end": 40, "strand": None}
        ],
        "validation_summary": {"blocking_count": 0},
    }
    runtime = {
        "schema_version": "runtime:test",
        "active_complete_plasmid_id": "plasmid:test",
        "complete_plasmid_constructs": [plasmid],
    }
    return {
        "runtime": runtime,
        "plasmid_id": "plasmid:test",
        "construct_status": "current",
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_checksum": checksum,
        "revision_id": "revision:plasmid",
        "topology": "circular",
        "validation_summary": {"blocking_count": 0},
    }


def _source(**overrides: object) -> AuthoritativePublicationMapSource:
    sequence = "ACGT" * 25
    payload: dict[str, object] = {
        "construct_identifier": "construct:test",
        "display_name": "Test construct",
        "sequence_length": len(sequence),
        "topology": "circular",
        "sequence_checksum": hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
        "sequence": sequence,
        "features": (
            {
                "name": "Forward CDS",
                "type": "CDS",
                "component_type": "cds",
                "start": 9,
                "end": 30,
                "strand": 1,
                "qualifiers": {"gene": ["example_gene"], "note": ["review record"]},
                "provenance": {"source_asset_id": "asset:one"},
                "component_id": "component:one",
                "unit_id": "tu:one",
                "unit_order": 1,
            },
        ),
        "provenance": {
            "source_coordinate_convention": AUTHORITATIVE_COORDINATE_CONVENTION,
            "display_coordinate_convention": DISPLAY_COORDINATE_CONVENTION,
        },
        "view_type": PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
    }
    payload.update(overrides)
    return AuthoritativePublicationMapSource(**payload)  # type: ignore[arg-type]


def _adapt_features(*features: dict[str, object]):
    return adapt_publication_map_source(_source(features=features)).features


def test_coordinate_conversion_and_identity_are_exact_and_immutable() -> None:
    document = adapt_publication_map_source(_source())
    feature = document.features[0]

    assert document.sequence_length == 100
    assert document.sequence_checksum == hashlib.sha256(("ACGT" * 25).encode("utf-8")).hexdigest()
    assert feature.authoritative.start == 9
    assert feature.authoritative.end == 30
    assert feature.display.start == 10
    assert feature.display.end == 30
    assert feature.parts[0].authoritative == feature.authoritative
    assert feature.parts[0].display == feature.display
    assert dict(feature.provenance) == {
        "component_id": "component:one",
        "source_asset_id": "asset:one",
        "unit_id": "tu:one",
        "unit_order": "1",
    }
    assert document.view.authoritative_region.start == 0
    assert document.view.authoritative_region.end == 100
    assert document.view.display_region.start == 1
    assert document.view.display_region.end == 100
    with pytest.raises(FrozenInstanceError):
        feature.display_label = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "feature",
    [
        {"name": "negative", "start": -1, "end": 4, "strand": 1},
        {"name": "zero", "start": 4, "end": 4, "strand": 1},
        {"name": "reverse envelope", "start": 20, "end": 4, "strand": 1},
        {"name": "outside", "start": 90, "end": 101, "strand": 1},
    ],
)
def test_invalid_coordinates_are_rejected_without_clipping(feature: dict[str, object]) -> None:
    with pytest.raises(PublicationMapContractError):
        _adapt_features(feature)


def test_sequence_length_and_checksum_must_match_sequence_when_available() -> None:
    with pytest.raises(PublicationMapContractError, match="sequence_length"):
        adapt_publication_map_source(_source(sequence_length=99))
    with pytest.raises(PublicationMapContractError, match="sequence_checksum"):
        adapt_publication_map_source(_source(sequence_checksum="b" * 64))
    with pytest.raises(PublicationMapContractError, match="lowercase SHA-256"):
        adapt_publication_map_source(_source(sequence_checksum=_source().sequence_checksum.upper()))
    with pytest.raises(PublicationMapContractError, match="construct_identifier"):
        adapt_publication_map_source(_source(construct_identifier=""))


def test_forward_reverse_unknown_and_legacy_zero_strands_are_preserved() -> None:
    features = _adapt_features(
        {"name": "forward", "start": 0, "end": 10, "strand": 1},
        {"name": "reverse", "start": 10, "end": 20, "strand": -1},
        {"name": "unknown", "start": 20, "end": 30, "strand": None},
        {"name": "legacy unknown", "start": 30, "end": 40, "strand": 0},
    )
    assert {feature.display_label: feature.strand for feature in features} == {
        "forward": 1,
        "reverse": -1,
        "unknown": None,
        "legacy unknown": None,
    }
    with pytest.raises(PublicationMapContractError, match="strand"):
        _adapt_features({"name": "invalid", "start": 0, "end": 5, "strand": 2})


def test_compound_and_circular_wraparound_parts_preserve_authoritative_order() -> None:
    feature = _adapt_features(
        {
            "name": "wrap",
            "type": "misc_feature",
            "start": 0,
            "end": 100,
            "strand": -1,
            "location_operator": "join",
            "location_parts": [
                {"start": 90, "end": 100, "strand": -1},
                {"start": 0, "end": 8, "strand": -1},
            ],
        }
    )[0]
    assert [(part.authoritative.start, part.authoritative.end) for part in feature.parts] == [(90, 100), (0, 8)]
    assert [(part.display.start, part.display.end) for part in feature.parts] == [(91, 100), (1, 8)]
    assert feature.location_operator == "join"
    assert feature.wraps_origin is True


def test_standard_genbank_forward_and_reverse_origin_crossings_are_topological_wraps() -> None:
    payload = json.loads(ORIGIN_WRAP_FIXTURE_PATH.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        feature = _adapt_features(
            {
                "name": case["case_id"],
                "type": "misc_feature",
                "start": 0,
                "end": payload["sequence_length"],
                "strand": case["strand"],
                "location_operator": "join",
                "location_parts": case["location_parts"],
                "qualifiers": {"genbank_location": [case["genbank_location"]]},
            }
        )[0]
        assert feature.wraps_origin is case["expected_wraps_origin"]
        assert [
            (part.authoritative.start, part.authoritative.end, part.strand)
            for part in feature.parts
        ] == [
            (part["start"], part["end"], part["strand"])
            for part in case["location_parts"]
        ]


@pytest.mark.parametrize(
    ("location_parts", "expected_message"),
    [
        (
            [
                {"start": 0, "end": 8, "strand": 1},
                {"start": 90, "end": 100, "strand": 1},
                {"start": 0, "end": 8, "strand": 1},
            ],
            "coordinate-distinct",
        ),
        (
            [
                {"start": 0, "end": 100, "strand": 1},
                {"start": 20, "end": 30, "strand": 1},
            ],
            "full-sequence part",
        ),
        (
            [
                {"start": 0, "end": 0, "strand": 1},
                {"start": 90, "end": 100, "strand": 1},
            ],
            "non-empty",
        ),
        (
            [
                {"start": 0, "end": 8, "strand": 1},
                {"start": 90, "end": 101, "strand": 1},
            ],
            "exceeds the authoritative sequence length",
        ),
    ],
)
def test_malformed_origin_wrap_parts_are_rejected_by_adapter(
    location_parts: list[dict[str, int]],
    expected_message: str,
) -> None:
    with pytest.raises(PublicationMapContractError, match=expected_message):
        _adapt_features(
            {
                "name": "malformed wrap",
                "type": "misc_feature",
                "start": 0,
                "end": 100,
                "strand": 1,
                "location_operator": "join",
                "location_parts": location_parts,
            }
        )


@pytest.mark.parametrize("strand", [1, -1])
def test_origin_wrap_adapter_round_trip_preserves_semantics_and_identity(strand: int) -> None:
    parts = (
        [
            {"start": 90, "end": 100, "strand": strand},
            {"start": 0, "end": 8, "strand": strand},
        ]
        if strand == 1
        else [
            {"start": 0, "end": 8, "strand": strand},
            {"start": 90, "end": 100, "strand": strand},
        ]
    )
    raw = {
        "name": f"wrap {strand}",
        "type": "misc_feature",
        "start": 0,
        "end": 100,
        "strand": strand,
        "location_operator": "join",
        "location_parts": parts,
    }
    first = _adapt_features(raw)[0]
    second = _adapt_features(deepcopy(raw))[0]

    assert first == second
    assert first.feature_id == second.feature_id
    assert (first.authoritative.start, first.authoritative.end) == (0, 100)
    assert first.strand == strand
    assert first.wraps_origin is True
    assert [
        (part.authoritative.start, part.authoritative.end, part.strand)
        for part in first.parts
    ] == [
        (part["start"], part["end"], part["strand"])
        for part in parts
    ]


def test_decreasing_compound_part_starts_do_not_alone_imply_origin_crossing() -> None:
    feature = _adapt_features(
        {
            "name": "internal compound",
            "type": "misc_feature",
            "start": 10,
            "end": 60,
            "strand": 1,
            "location_operator": "join",
            "location_parts": [
                {"start": 50, "end": 60, "strand": 1},
                {"start": 10, "end": 20, "strand": 1},
            ],
        }
    )[0]
    assert feature.wraps_origin is False


def test_mixed_strand_compound_location_is_rejected_in_v1() -> None:
    with pytest.raises(PublicationMapContractError, match="Mixed-strand"):
        _adapt_features(
            {
                "name": "mixed",
                "start": 0,
                "end": 20,
                "strand": 1,
                "location_parts": [
                    {"start": 0, "end": 5, "strand": 1},
                    {"start": 15, "end": 20, "strand": -1},
                ],
            }
        )


def test_qualifiers_and_provenance_are_preserved_without_mutable_references() -> None:
    raw = {
        "name": "Feature",
        "type": "misc_feature",
        "start": 0,
        "end": 5,
        "strand": None,
        "qualifiers": {"note": ["one", "two"], "gene": ["g1"]},
        "provenance": {"source_id": "source:1", "record_id": "record:1"},
    }
    feature = _adapt_features(raw)[0]
    raw["qualifiers"]["note"].append("mutated")  # type: ignore[index,union-attr]
    assert feature.qualifiers == (("gene", ("g1",)), ("note", ("one", "two")))
    assert feature.provenance == (("record_id", "record:1"), ("source_id", "source:1"))


def test_unknown_features_remain_unclassified_and_labels_never_infer_roles() -> None:
    feature = _adapt_features(
        {
            "name": "Looks like promoter selectable marker LB RB enhancer",
            "start": 0,
            "end": 10,
            "strand": None,
            "qualifiers": {"note": ["Contains role-like words only"]},
        }
    )[0]
    assert feature.authoritative_type is None
    assert feature.component_type is None
    assert feature.biological_role is None
    assert feature.classification_state is FeatureClassificationState.UNCLASSIFIED
    assert feature.display_category == "unclassified"


def test_declared_unknown_type_is_preserved_but_not_mapped_to_known_display_semantics() -> None:
    feature = _adapt_features(
        {"name": "Unknown", "type": "future_feature_class", "start": 0, "end": 5, "strand": 1}
    )[0]
    assert feature.authoritative_type == "future_feature_class"
    assert feature.classification_state is FeatureClassificationState.AUTHORITATIVE
    assert feature.display_category == "unclassified"


def test_order_and_ids_are_stable_and_duplicate_ids_are_disambiguated() -> None:
    first = {"name": "A", "type": "misc_feature", "start": 20, "end": 30, "strand": 1}
    second = {"name": "B", "type": "CDS", "start": 0, "end": 10, "strand": -1}
    duplicate = {"name": "D", "type": "misc_feature", "start": 40, "end": 50, "strand": None}
    forward = _adapt_features(first, duplicate, second, duplicate)
    reordered = _adapt_features(duplicate, second, duplicate, first)
    assert forward == reordered
    assert [item.display_label for item in forward] == ["B", "A", "D", "D"]
    assert forward[2].feature_id.endswith("-001")
    assert forward[3].feature_id.endswith("-002")


def test_feature_ids_do_not_depend_on_transient_runtime_provenance() -> None:
    first = _adapt_features(
        {
            "name": "CDS",
            "type": "CDS",
            "start": 0,
            "end": 10,
            "strand": 1,
            "component_id": "component:runtime-one",
        }
    )[0]
    second = _adapt_features(
        {
            "name": "CDS",
            "type": "CDS",
            "start": 0,
            "end": 10,
            "strand": 1,
            "component_id": "component:runtime-two",
        }
    )[0]
    assert first.feature_id == second.feature_id
    assert first.provenance != second.provenance


def test_complete_circular_and_linear_active_construct_views_are_explicit() -> None:
    circular = adapt_publication_map_source(_source())
    assert circular.topology is PublicationMapTopology.CIRCULAR
    assert circular.view.view_type is PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID

    linear = adapt_publication_map_source(
        _source(
            topology="linear",
            view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
        )
    )
    assert linear.topology is PublicationMapTopology.LINEAR
    assert linear.view.view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
    with pytest.raises(PublicationMapContractError, match="requires"):
        adapt_publication_map_source(_source(topology="linear"))


def test_linear_active_expression_construct_fixture_is_deterministic() -> None:
    payload = json.loads(LINEAR_FIXTURE_PATH.read_text(encoding="utf-8"))
    document = adapt_publication_map_source(
        AuthoritativePublicationMapSource(
            construct_identifier=payload["construct_identifier"],
            display_name=payload["display_name"],
            sequence_length=payload["sequence_length"],
            topology=payload["topology"],
            sequence_checksum=payload["sequence_checksum"],
            sequence=payload["sequence"],
            features=tuple(payload["features"]),
            provenance=payload["provenance"],
            view_type=PublicationMapViewType(payload["view_type"]),
        )
    )
    assert document.view.view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
    assert document.sequence_length == 21
    assert document.sequence_checksum == payload["sequence_checksum"]
    assert [feature.component_type for feature in document.features] == [
        "promoter",
        "cds",
        "terminator",
    ]
    assert [
        (feature.authoritative.start, feature.authoritative.end)
        for feature in document.features
    ] == [(0, 6), (6, 15), (15, 21)]


def test_runtime_bridge_consumes_only_snapshot_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _linear_snapshot()
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)
    document = publication_map_document_from_runtime(
        {"ignored": "session state is not read"},
        view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
    )
    assert document.construct_identifier == "construct:test"
    assert document.features[0].strand == -1
    assert dict(document.provenance)["runtime_revision_id"] == "revision:test"


def test_complete_circular_runtime_bridge_uses_combined_authoritative_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _circular_snapshot()
    fake_module = types.SimpleNamespace(active_complete_plasmid_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)
    document = publication_map_document_from_runtime(
        {"ignored": "projection source"},
        view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
    )
    assert document.construct_identifier == "plasmid:test"
    assert document.topology is PublicationMapTopology.CIRCULAR
    assert document.features[0].display_category == "origin"
    assert document.features[0].strand is None


@pytest.mark.parametrize(
    ("view_type", "status", "status_source"),
    [
        (view_type, status, status_source)
        for view_type in (
            PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
            PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        )
        for status in ("stale", "blocking_invalid")
        for status_source in ("snapshot", "record")
    ],
)
def test_runtime_bridge_rejects_stale_and_blocking_status_disagreements(
    monkeypatch: pytest.MonkeyPatch,
    view_type: PublicationMapViewType,
    status: str,
    status_source: str,
) -> None:
    snapshot = (
        _linear_snapshot()
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else _circular_snapshot()
    )
    runtime = snapshot["runtime"]
    record_collection = (
        "constructs"
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else "complete_plasmid_constructs"
    )
    if status_source == "snapshot":
        snapshot["construct_status"] = status
    else:
        runtime[record_collection][0]["construct_status"] = status  # type: ignore[index]
    fake_module = types.SimpleNamespace(
        active_construct_snapshot=lambda payload: snapshot,
        active_complete_plasmid_snapshot=lambda payload: snapshot,
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="requires a current"):
        publication_map_document_from_runtime({}, view_type=view_type)


@pytest.mark.parametrize(
    ("view_type", "blocking_source"),
    [
        (PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT, "snapshot"),
        (PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT, "record"),
        (PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID, "snapshot"),
        (PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID, "record"),
    ],
)
def test_runtime_bridge_rejects_blocking_summary_at_every_authoritative_level(
    monkeypatch: pytest.MonkeyPatch,
    view_type: PublicationMapViewType,
    blocking_source: str,
) -> None:
    snapshot = (
        _linear_snapshot()
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else _circular_snapshot()
    )
    if blocking_source == "snapshot":
        snapshot["validation_summary"] = {"blocking_count": 1}
    else:
        runtime = snapshot["runtime"]
        collection_name = (
            "constructs"
            if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
            else "complete_plasmid_constructs"
        )
        runtime[collection_name][0]["validation_summary"] = {"blocking_count": 1}  # type: ignore[index]
    fake_module = types.SimpleNamespace(
        active_construct_snapshot=lambda payload: snapshot,
        active_complete_plasmid_snapshot=lambda payload: snapshot,
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="blocking findings"):
        publication_map_document_from_runtime({}, view_type=view_type)


def test_runtime_bridge_rejects_blocking_finding_on_authoritative_plasmid_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _circular_snapshot()
    snapshot["runtime"]["complete_plasmid_constructs"][0]["validation_findings"] = [  # type: ignore[index]
        {"rule_id": "fixture:blocking", "blocking": True}
    ]
    fake_module = types.SimpleNamespace(
        active_complete_plasmid_snapshot=lambda payload: snapshot
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="validation_findings"):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID
        )


@pytest.mark.parametrize(
    "view_type",
    [
        PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
        PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
    ],
)
def test_runtime_bridge_rejects_blocking_finding_on_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    view_type: PublicationMapViewType,
) -> None:
    snapshot = (
        _linear_snapshot()
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else _circular_snapshot()
    )
    snapshot["validation_findings"] = [
        {"rule_id": "fixture:blocking", "blocking": True}
    ]
    fake_module = types.SimpleNamespace(
        active_construct_snapshot=lambda payload: snapshot,
        active_complete_plasmid_snapshot=lambda payload: snapshot,
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="validation_findings"):
        publication_map_document_from_runtime(
            {}, view_type=view_type
        )


def test_runtime_bridge_rejects_blocking_finding_on_authoritative_linear_construct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _linear_snapshot()
    snapshot["runtime"]["constructs"][0]["validation_findings"] = [  # type: ignore[index]
        {"rule_id": "fixture:blocking", "blocking": True}
    ]
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="validation_findings"):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


@pytest.mark.parametrize(
    "view_type",
    [
        PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
        PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
    ],
)
def test_runtime_bridge_allows_non_blocking_validation_findings(
    monkeypatch: pytest.MonkeyPatch,
    view_type: PublicationMapViewType,
) -> None:
    snapshot = (
        _linear_snapshot()
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else _circular_snapshot()
    )
    snapshot["validation_findings"] = [
        {"rule_id": "fixture:warning", "blocking": False}
    ]
    runtime = snapshot["runtime"]
    collection_name = (
        "constructs"
        if view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        else "complete_plasmid_constructs"
    )
    runtime[collection_name][0]["validation_findings"] = [  # type: ignore[index]
        {"rule_id": "fixture:warning", "blocking": False}
    ]
    fake_module = types.SimpleNamespace(
        active_construct_snapshot=lambda payload: snapshot,
        active_complete_plasmid_snapshot=lambda payload: snapshot,
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    document = publication_map_document_from_runtime({}, view_type=view_type)
    assert document.construct_identifier


def test_runtime_bridge_rejects_stale_linked_active_transcription_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _linear_snapshot()
    runtime = snapshot["runtime"]
    runtime["transcription_units"][0]["stale"] = True  # type: ignore[index]
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="active transcription unit"):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


def test_runtime_bridge_rejects_blocking_linked_active_transcription_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _linear_snapshot()
    runtime = snapshot["runtime"]
    runtime["transcription_units"][0]["validation_findings"] = [  # type: ignore[index]
        {"rule_id": "fixture:blocking", "blocking": True}
    ]
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(
        PublicationMapContractError,
        match="active transcription units with blocking findings",
    ):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


@pytest.mark.parametrize(
    "missing_material",
    ["revision", "sequence", "checksum", "active_transcription_unit", "active_construct"],
)
def test_runtime_bridge_requires_complete_current_linear_identity_material(
    monkeypatch: pytest.MonkeyPatch,
    missing_material: str,
) -> None:
    snapshot = _linear_snapshot()
    runtime = snapshot["runtime"]
    transcription_unit = runtime["transcription_units"][0]  # type: ignore[index]
    construct = runtime["constructs"][0]  # type: ignore[index]
    if missing_material == "revision":
        snapshot["revision_id"] = ""
        transcription_unit["revision_id"] = ""
        construct["current_revision"] = ""
    elif missing_material == "sequence":
        snapshot["sequence"] = ""
        snapshot["sequence_length"] = 0
        transcription_unit["generated_nucleotide_sequence"] = ""
        construct["canonical_generated_sequence"] = ""
    elif missing_material == "checksum":
        snapshot["sequence_checksum"] = ""
        transcription_unit["generated_sequence_checksum"] = ""
        construct["sequence_checksum"] = ""
    elif missing_material == "active_transcription_unit":
        runtime["active_transcription_unit_id"] = ""  # type: ignore[index]
    else:
        runtime["active_construct_id"] = ""  # type: ignore[index]
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


@pytest.mark.parametrize("adversarial_order", ["authoritative-first", "conflicting-first"])
def test_duplicate_active_transcription_unit_identity_is_order_independent(
    monkeypatch: pytest.MonkeyPatch,
    adversarial_order: str,
) -> None:
    snapshot = _linear_snapshot()
    runtime = snapshot["runtime"]
    authoritative = runtime["transcription_units"][0]  # type: ignore[index]
    conflicting = deepcopy(authoritative)
    conflicting["generated_nucleotide_sequence"] = "A" * 100
    conflicting["generated_sequence_checksum"] = hashlib.sha256(
        ("A" * 100).encode("utf-8")
    ).hexdigest()
    conflicting["revision_id"] = "revision:conflicting"
    conflicting["feature_coordinates"] = [
        {"name": "Conflicting feature", "start": 80, "end": 90, "strand": 1}
    ]
    runtime["transcription_units"] = (  # type: ignore[index]
        [authoritative, conflicting]
        if adversarial_order == "authoritative-first"
        else [conflicting, authoritative]
    )
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="exactly one transcription_units"):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


@pytest.mark.parametrize("adversarial_order", ["authoritative-first", "conflicting-first"])
def test_duplicate_active_construct_identity_is_order_independent(
    monkeypatch: pytest.MonkeyPatch,
    adversarial_order: str,
) -> None:
    snapshot = _linear_snapshot()
    runtime = snapshot["runtime"]
    authoritative = runtime["constructs"][0]  # type: ignore[index]
    conflicting = deepcopy(authoritative)
    conflicting["current_revision"] = "revision:conflicting"
    runtime["constructs"] = (  # type: ignore[index]
        [authoritative, conflicting]
        if adversarial_order == "authoritative-first"
        else [conflicting, authoritative]
    )
    fake_module = types.SimpleNamespace(active_construct_snapshot=lambda payload: snapshot)
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError, match="exactly one constructs"):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
        )


@pytest.mark.parametrize("adversarial_order", ["authoritative-first", "conflicting-first"])
def test_duplicate_active_plasmid_identity_is_order_independent(
    monkeypatch: pytest.MonkeyPatch,
    adversarial_order: str,
) -> None:
    snapshot = _circular_snapshot()
    runtime = snapshot["runtime"]
    authoritative = runtime["complete_plasmid_constructs"][0]  # type: ignore[index]
    conflicting = deepcopy(authoritative)
    conflicting["current_revision"] = "revision:conflicting"
    runtime["complete_plasmid_constructs"] = (  # type: ignore[index]
        [authoritative, conflicting]
        if adversarial_order == "authoritative-first"
        else [conflicting, authoritative]
    )
    fake_module = types.SimpleNamespace(
        active_complete_plasmid_snapshot=lambda payload: snapshot
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(
        PublicationMapContractError,
        match="exactly one complete_plasmid_constructs",
    ):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID
        )


@pytest.mark.parametrize(
    "missing_material",
    ["sequence", "checksum", "revision", "active_plasmid"],
)
def test_runtime_bridge_requires_complete_current_circular_identity_material(
    monkeypatch: pytest.MonkeyPatch,
    missing_material: str,
) -> None:
    snapshot = _circular_snapshot()
    runtime = snapshot["runtime"]
    plasmid = runtime["complete_plasmid_constructs"][0]  # type: ignore[index]
    if missing_material == "sequence":
        plasmid["generated_nucleotide_sequence"] = ""
    elif missing_material == "checksum":
        plasmid["sequence_checksum"] = ""
    elif missing_material == "revision":
        plasmid["current_revision"] = ""
    else:
        runtime["active_complete_plasmid_id"] = ""  # type: ignore[index]
    fake_module = types.SimpleNamespace(
        active_complete_plasmid_snapshot=lambda payload: snapshot
    )
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_module)

    with pytest.raises(PublicationMapContractError):
        publication_map_document_from_runtime(
            {}, view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID
        )


def test_real_canonical_runtime_adapts_to_linear_document_without_reassembly() -> None:
    from services.canonical_construct_runtime import (
        blank_runtime,
        create_component,
        create_sequence_asset,
        generate_active_construct,
        set_active_component_order,
        upsert_component,
        upsert_sequence_asset,
    )

    runtime = blank_runtime("publication-map-integration")
    component_ids: list[str] = []
    for component_type, name, sequence in (
        ("promoter", "Synthetic promoter", "AACCGG"),
        ("cds", "Synthetic CDS", "ATGGCTTAA"),
        ("terminator", "Synthetic 3' regulatory region", "TTTTGG"),
    ):
        asset = create_sequence_asset(
            project_id="publication-map-integration",
            display_name=name,
            raw_text=sequence,
            source_format="plain",
            provenance_reference=f"fixture:{component_type}",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="publication-map-integration",
            component_type=component_type,
            display_name=name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        component_ids.append(component["component_id"])
    runtime = generate_active_construct(set_active_component_order(runtime, component_ids))

    document = publication_map_document_from_runtime(
        runtime,
        view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
        display_name="Synthetic expression construct",
    )
    assert document.sequence_length == 21
    assert [feature.component_type for feature in document.features] == ["promoter", "cds", "terminator"]
    assert [(feature.authoritative.start, feature.authoritative.end) for feature in document.features] == [
        (0, 6),
        (6, 15),
        (15, 21),
    ]
    assert all(feature.strand == 1 for feature in document.features)
    assert [dict(feature.provenance)["component_id"] for feature in document.features] == component_ids


def test_dense_synthetic_plant_binary_vector_fixture_covers_required_semantics() -> None:
    payload = json.loads(DENSE_FIXTURE_PATH.read_text(encoding="utf-8"))
    document = adapt_publication_map_source(
        AuthoritativePublicationMapSource(
            construct_identifier=payload["construct_identifier"],
            display_name=payload["display_name"],
            sequence_length=payload["sequence_length"],
            topology=payload["topology"],
            sequence_checksum=payload["sequence_checksum"],
            sequence="N" * payload["sequence_length"],
            features=tuple(payload["features"]),
            provenance=payload["provenance"],
            view_type=PublicationMapViewType(payload["view_type"]),
        )
    )
    categories = {feature.display_category for feature in document.features}
    assert len(document.features) == 30
    assert {
        "promoter",
        "five_prime_region",
        "enhancer",
        "cds",
        "terminator",
        "selectable_marker",
        "origin",
        "left_border",
        "right_border",
        "insertion_region",
        "replacement_region",
        "unclassified",
    } <= categories
    assert any(feature.strand == -1 for feature in document.features)
    assert any(feature.strand is None for feature in document.features)
    assert any(len(feature.parts) > 1 for feature in document.features)
    assert any(feature.wraps_origin for feature in document.features)
    assert any(feature.authoritative.length == 1 for feature in document.features)
    assert any(feature.authoritative.length >= 2000 for feature in document.features)
    assert any(len(feature.display_label) > 80 for feature in document.features)
