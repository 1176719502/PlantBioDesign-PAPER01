from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest

from services.publication_map_adapter import (
    AuthoritativePublicationMapSource,
    adapt_publication_map_source,
    publication_map_document_from_runtime,
)
from services.publication_map_contract import (
    PUBLICATION_MAP_REVISION_PROVENANCE_FIELD,
    PUBLICATION_MAP_SCHEMA_VERSION,
    PublicationMapContractError,
    PublicationMapTopology,
    PublicationMapViewType,
)
from services.publication_map_renderer import (
    PUBLICATION_MAP_RENDERER_VERSION,
    PublicationMapRenderOptions,
    _circular_feature_lanes,
    publication_map_svg_digest,
    render_publication_map_svg,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "publication_map_v1"
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def _document_from_fixture(name: str):
    payload = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    sequence = payload.get("sequence")
    if sequence is None and "sequence_fixture" in payload:
        sequence = "N" * payload["sequence_length"]
    return adapt_publication_map_source(
        AuthoritativePublicationMapSource(
            construct_identifier=payload["construct_identifier"],
            display_name=payload["display_name"],
            sequence_length=payload["sequence_length"],
            topology=payload["topology"],
            sequence_checksum=payload["sequence_checksum"],
            sequence=sequence,
            features=tuple(payload["features"]),
            provenance=payload["provenance"],
            view_type=PublicationMapViewType(payload["view_type"]),
        )
    )


def _source_document(
    *features: dict[str, object],
    topology: str = "circular",
    name: str = "Renderer test",
    length: int = 100,
):
    view = (
        PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID
        if topology == "circular"
        else PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT
    )
    return adapt_publication_map_source(
        AuthoritativePublicationMapSource(
            construct_identifier="fixture:renderer-test",
            display_name=name,
            sequence_length=length,
            topology=topology,
            sequence_checksum=hashlib.sha256(("N" * length).encode("utf-8")).hexdigest(),
            sequence="N" * length,
            features=tuple(features),
            provenance={
                PUBLICATION_MAP_REVISION_PROVENANCE_FIELD: "revision:renderer-test"
            },
            view_type=view,
        )
    )


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _feature_groups(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//svg:g[@class='map-feature']", SVG_NS)


def _circular_feature_arc_length(
    group: ET.Element,
    feature_span: int,
    sequence_length: int,
) -> float:
    arc = group.find("svg:path[@class='feature-arc']", SVG_NS)
    assert arc is not None
    match = re.search(r" A ([^ ]+) ([^ ]+) ", arc.attrib["d"])
    assert match is not None
    radius_x, radius_y = (float(value) for value in match.groups())
    assert radius_x == radius_y
    return 2 * math.pi * radius_x * feature_span / sequence_length


def _arrow_tangent_extent(
    arrow: ET.Element,
    coordinate: int,
    strand: int,
    sequence_length: int,
) -> float:
    angle = -math.pi / 2 + (coordinate / sequence_length) * 2 * math.pi
    tangent_x, tangent_y = -math.sin(angle) * strand, math.cos(angle) * strand
    points = [tuple(map(float, pair.split(","))) for pair in arrow.attrib["points"].split()]
    projections = [x * tangent_x + y * tangent_y for x, y in points]
    return max(projections) - min(projections)


def _assert_declared_text_bounds_inside_viewbox(root: ET.Element) -> None:
    _, _, width, height = (float(value) for value in root.attrib["viewBox"].split())
    bounded_text = root.findall(".//svg:text[@data-layout-bounds]", SVG_NS)
    assert bounded_text
    for text_element in bounded_text:
        left, top, right, bottom = (
            float(value) for value in text_element.attrib["data-layout-bounds"].split(",")
        )
        assert 0 <= left <= right <= width
        assert 0 <= top <= bottom <= height


def _feature_label_bounds(root: ET.Element) -> list[tuple[float, float, float, float]]:
    return [
        tuple(float(value) for value in label.attrib["data-layout-bounds"].split(","))
        for label in root.findall(".//svg:text[@data-label-for]", SVG_NS)
    ]


def _assert_no_feature_label_bounds_overlap(root: ET.Element) -> None:
    bounds = _feature_label_bounds(root)
    for index, (left, top, right, bottom) in enumerate(bounds):
        for other_left, other_top, other_right, other_bottom in bounds[index + 1 :]:
            assert right <= other_left or other_right <= left or bottom <= other_top or other_bottom <= top


def _coincident_features(count: int, *, label: str = "Coincident feature") -> list[dict[str, object]]:
    return [
        {
            "name": f"{label} {index:02d}",
            "type": "misc_feature",
            "start": 45,
            "end": 55,
            "strand": 1 if index % 2 else -1,
        }
        for index in range(1, count + 1)
    ]


def _coincident_circular_features(
    count: int,
    *,
    label: str = "Repeated circular label",
) -> list[dict[str, object]]:
    return [
        {
            "name": label,
            "type": "misc_feature",
            "start": 49,
            "end": 50,
            "strand": 1 if index % 2 else -1,
        }
        for index in range(1, count + 1)
    ]


def test_deterministic_svg_is_byte_identical_and_digest_is_stable() -> None:
    document = _document_from_fixture("dense_synthetic_plant_binary_vector.json")
    first = render_publication_map_svg(document)
    second = render_publication_map_svg(document)

    assert first == second
    assert publication_map_svg_digest(first) == publication_map_svg_digest(second)
    assert re.fullmatch(r"[0-9a-f]{64}", publication_map_svg_digest(first))


def test_circular_label_rail_accepts_exact_capacity_without_overlap() -> None:
    document = _source_document(
        *_coincident_circular_features(
            21,
            label="Repeated very long circular publication label " * 8,
        )
    )
    root = _root(render_publication_map_svg(document))

    assert len(_feature_label_bounds(root)) == 21
    _assert_declared_text_bounds_inside_viewbox(root)
    _assert_no_feature_label_bounds_overlap(root)


def test_circular_label_rail_fails_closed_one_over_capacity() -> None:
    document = _source_document(*_coincident_circular_features(22))

    with pytest.raises(PublicationMapContractError, match="label_capacity_exceeded"):
        render_publication_map_svg(document)


def test_dense_60_feature_circular_capacity_failure_is_deterministic() -> None:
    document = _source_document(*_coincident_circular_features(60))
    failures: list[str] = []

    for _ in range(3):
        with pytest.raises(PublicationMapContractError) as exc_info:
            render_publication_map_svg(document)
        failures.append(str(exc_info.value))

    assert len(set(failures)) == 1
    assert failures[0].startswith("label_capacity_exceeded:")


def test_standard_circular_svg_is_valid_and_traceable() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 4, "end": 22, "strand": 1},
        {"name": "Reverse CDS", "type": "CDS", "start": 30, "end": 61, "strand": -1},
        {"name": "Origin", "type": "rep_origin", "start": 68, "end": 90, "strand": None},
    )
    svg = render_publication_map_svg(document)
    root = _root(svg)

    assert root.attrib["width"] == "1200"
    assert root.attrib["height"] == "960"
    assert root.attrib["viewBox"] == "0 0 1200 960"
    assert {group.attrib["data-feature-id"] for group in _feature_groups(root)} == {
        feature.feature_id for feature in document.features
    }
    metadata = json.loads(root.find("svg:metadata", SVG_NS).text or "")
    assert metadata == {
        "checksum_algorithm": "sha256",
        "construct_identifier": document.construct_identifier,
        "renderer_version": PUBLICATION_MAP_RENDERER_VERSION,
        "revision": "revision:renderer-test",
        "schema_version": PUBLICATION_MAP_SCHEMA_VERSION,
        "sequence_checksum": document.sequence_checksum,
        "sequence_length": 100,
        "topology": "circular",
        "view_type": "complete_circular_plasmid",
    }


def test_circular_primary_map_uses_canvas_and_marks_feature_hierarchy() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 4, "end": 22, "strand": 1},
        {"name": "Backbone note", "type": "misc_feature", "start": 30, "end": 61, "strand": None},
    )
    root = _root(render_publication_map_svg(document))
    backbone = root.find("svg:circle[@class='backbone']", SVG_NS)

    assert backbone is not None
    assert float(backbone.attrib["r"]) >= 300
    groups = _feature_groups(root)
    assert [group.attrib["data-priority"] for group in groups] == ["key", "secondary"]
    assert groups[0].find("svg:polygon[@class='direction-arrow']", SVG_NS) is not None
    assert groups[1].find("svg:polygon[@class='direction-arrow']", SVG_NS) is None


def test_circular_output_has_explicit_visible_geometry_and_responsive_embedding() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 4, "end": 22, "strand": 1},
        {"name": "Coding sequence", "type": "CDS", "start": 30, "end": 61, "strand": 1},
        {"name": "3' regulatory region", "type": "terminator", "start": 68, "end": 90, "strand": 1},
        {"name": "Replication origin", "type": "rep_origin", "start": 92, "end": 99, "strand": None},
    )
    root = _root(render_publication_map_svg(document))

    assert "max-width:100%" in root.attrib["style"]
    assert "height:auto" in root.attrib["style"]
    backbone = root.find("svg:circle[@class='backbone']", SVG_NS)
    assert backbone is not None
    assert float(backbone.attrib["stroke-width"]) == pytest.approx(2.5)
    assert backbone.attrib["stroke-opacity"] == "1"
    assert backbone.attrib["vector-effect"] == "non-scaling-stroke"

    arcs = root.findall(".//svg:path[@class='feature-arc']", SVG_NS)
    assert len(arcs) == 4
    assert {arc.attrib["stroke"] for arc in arcs}.isdisjoint({"", "#FFFFFF", "white"})
    assert [float(arc.attrib["stroke-width"]) for arc in arcs] == [9.0, 9.0, 9.0, 9.0]
    assert 2.0 <= float(backbone.attrib["stroke-width"]) <= 3.0
    assert all(8.0 <= float(arc.attrib["stroke-width"]) <= 10.0 for arc in arcs)
    assert all(float(arc.attrib["opacity"]) > 0 for arc in arcs)
    assert all(arc.attrib["fill"] == "none" for arc in arcs)


def test_circular_leader_anchor_is_immediately_outside_feature_band() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 4, "end": 22, "strand": 1}
    )
    root = _root(render_publication_map_svg(document))
    leader = root.find(
        f".//svg:path[@class='leader'][@data-leader-for='{document.features[0].feature_id}']",
        SVG_NS,
    )
    assert leader is not None
    match = re.match(r"M ([^ ]+) ([^ ]+)", leader.attrib["d"])
    assert match is not None
    start_x, start_y = (float(value) for value in match.groups())
    cx, cy = 600.0, 437.5
    anchor_radius = math.hypot(start_x - cx, start_y - cy)
    assert anchor_radius == pytest.approx(326.4 + 10.0 + 9.0 / 2 + 0.75, abs=0.01)
    assert float(leader.attrib["stroke-width"]) == pytest.approx(0.85)
    assert leader.attrib["stroke"] == "#929CA5"


def test_runtime_revision_identity_is_bound_through_adapter_to_svg_metadata() -> None:
    from services.canonical_construct_runtime import (
        active_construct_snapshot,
        blank_runtime,
        create_component,
        create_sequence_asset,
        generate_active_construct,
        set_active_component_order,
        upsert_component,
        upsert_sequence_asset,
    )

    runtime = blank_runtime("publication-map-revision-binding")
    component_ids: list[str] = []
    for component_type, name, sequence in (
        ("promoter", "Synthetic promoter", "AACCGG"),
        ("cds", "Synthetic CDS", "ATGGCTTAA"),
        ("terminator", "Synthetic 3' regulatory region", "TTTTGG"),
    ):
        asset = create_sequence_asset(
            project_id="publication-map-revision-binding",
            display_name=name,
            raw_text=sequence,
            source_format="plain",
            provenance_reference=f"fixture:{component_type}",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="publication-map-revision-binding",
            component_type=component_type,
            display_name=name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        component_ids.append(component["component_id"])
    runtime = generate_active_construct(
        set_active_component_order(runtime, component_ids)
    )
    runtime_revision = active_construct_snapshot(runtime)["revision_id"]

    document = publication_map_document_from_runtime(
        runtime,
        view_type=PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
    )
    metadata = json.loads(
        _root(render_publication_map_svg(document)).find("svg:metadata", SVG_NS).text
        or ""
    )
    provenance = dict(document.provenance)

    assert runtime_revision
    assert provenance[PUBLICATION_MAP_REVISION_PROVENANCE_FIELD] == runtime_revision
    assert {"revision_id", "current_revision", "canonical_revision"}.isdisjoint(provenance)
    assert metadata["revision"] == runtime_revision
    assert metadata["revision"] is not None


def test_dense_circular_fixture_renders_every_feature_without_invalid_geometry() -> None:
    document = _document_from_fixture("dense_synthetic_plant_binary_vector.json")
    svg = render_publication_map_svg(document)
    root = _root(svg)
    groups = _feature_groups(root)

    assert len(document.features) == 30
    assert len(groups) == 30
    assert len({group.attrib["data-feature-id"] for group in groups}) == 30
    assert float(root.attrib["width"]) > 0
    assert float(root.attrib["height"]) > 0
    assert root.find(".//svg:g[@id='map-legend']", SVG_NS) is not None


def test_full_length_circular_feature_uses_two_visible_half_arcs() -> None:
    document = _source_document(
        {"name": "Whole sequence feature", "type": "misc_feature", "start": 0, "end": 100, "strand": None}
    )
    path = _feature_groups(_root(render_publication_map_svg(document)))[0].find(
        "svg:path[@class='feature-arc']", SVG_NS
    )

    assert path is not None
    assert path.attrib["d"].count(" A ") == 2


def test_full_length_source_metadata_is_preserved_but_suppressed_from_circular_drawing() -> None:
    document = _source_document(
        {"name": "source 1..100 bp", "type": "source", "start": 0, "end": 100, "strand": None},
        {"name": "Expression CDS", "type": "CDS", "start": 20, "end": 50, "strand": 1},
    )

    root = _root(render_publication_map_svg(document))

    assert len(document.features) == 2
    source = document.features[0]
    assert source.authoritative_type == "source"
    assert source.authoritative.start == 0
    assert source.authoritative.end == 100
    assert source.feature_id not in {group.attrib["data-feature-id"] for group in _feature_groups(root)}
    assert len(_feature_groups(root)) == 1
    assert root.find(f".//svg:text[@data-label-for='{source.feature_id}']", SVG_NS) is None


def test_full_length_biological_feature_is_not_hidden_by_source_policy() -> None:
    document = _source_document(
        {"name": "Full-length CDS", "type": "CDS", "start": 0, "end": 100, "strand": 1}
    )

    root = _root(render_publication_map_svg(document))

    assert len(_feature_groups(root)) == 1
    assert _feature_groups(root)[0].attrib["data-category"] == "cds"
    assert root.find(".//svg:path[@class='feature-arc']", SVG_NS) is not None


def test_container_annotation_is_context_priority_thin_and_has_no_direction_arrow() -> None:
    document = _source_document(
        {"name": "Inserted single-gene transcription unit", "type": "misc_feature", "component_type": "insertion_region", "start": 10, "end": 80, "strand": 1},
        {"name": "Primary promoter", "type": "promoter", "start": 20, "end": 35, "strand": 1},
    )

    groups = _feature_groups(_root(render_publication_map_svg(document)))
    context, primary = groups

    assert context.attrib["data-priority"] == "context"
    assert context.find("svg:polygon[@class='direction-arrow']", SVG_NS) is None
    assert float(context.find("svg:path[@class='feature-arc']", SVG_NS).attrib["stroke-width"]) == pytest.approx(3.5)
    assert primary.attrib["data-priority"] == "key"
    assert document.features[0].display_category == "insertion_region"


def test_circular_lane_count_reduces_when_full_length_source_metadata_is_suppressed() -> None:
    with_source = _source_document(
        {"name": "source", "type": "source", "start": 0, "end": 100, "strand": None},
        {"name": "Outer", "type": "misc_feature", "start": 10, "end": 60, "strand": 1},
        {"name": "Inner", "type": "misc_feature", "start": 20, "end": 40, "strand": 1},
    )
    without_source = _source_document(
        {"name": "Outer", "type": "misc_feature", "start": 10, "end": 60, "strand": 1},
        {"name": "Inner", "type": "misc_feature", "start": 20, "end": 40, "strand": 1},
    )

    with_source_root = _root(render_publication_map_svg(with_source))
    without_source_root = _root(render_publication_map_svg(without_source))
    with_source_lanes = {int(group.attrib["data-lane"]) for group in _feature_groups(with_source_root)}
    without_source_lanes = {int(group.attrib["data-lane"]) for group in _feature_groups(without_source_root)}

    assert max(_circular_feature_lanes(with_source.features).values()) == 2
    assert max(with_source_lanes) == max(without_source_lanes) == 1
    assert [int(group.attrib["data-lane"]) for group in _feature_groups(without_source_root)] == [0, 1]
    assert with_source.features[0].authoritative_type == "source"


def test_visual_category_uses_authoritative_type_even_when_label_contains_promoter() -> None:
    document = _source_document(
        {"name": "not actually a promoter label", "type": "misc_feature", "start": 10, "end": 30, "strand": None}
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]

    assert "promoter" in document.features[0].display_label
    assert document.features[0].authoritative_type == "misc_feature"
    assert group.attrib["data-category"] == "unclassified"
    assert group.attrib["data-style-role"] == "Other / unclassified"


def test_promoter_label_is_complete_when_rail_can_compress_it_and_keeps_full_title() -> None:
    label = "AF234296.1 inserted cassette source"
    document = _source_document({"name": label, "type": "promoter", "start": 10, "end": 30, "strand": 1})
    visible = _root(render_publication_map_svg(document)).find(
        f".//svg:text[@data-label-for='{document.features[0].feature_id}']", SVG_NS
    )

    assert visible is not None
    assert visible.text == label
    assert visible.attrib["textLength"]
    assert visible.find("svg:title", SVG_NS).text == label


@pytest.mark.parametrize(
    ("strand", "direction", "arrow_count"),
    [(1, "forward", 1), (-1, "reverse", 1), (None, "neutral", 0)],
)
def test_circular_strand_direction_is_explicit_without_false_neutral_arrow(
    strand: int | None,
    direction: str,
    arrow_count: int,
) -> None:
    document = _source_document(
        {"name": f"Feature {direction}", "type": "misc_feature", "start": 15, "end": 45, "strand": strand}
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]

    assert group.attrib["data-direction"] == direction
    assert len(group.findall("svg:polygon[@class='direction-arrow']", SVG_NS)) == arrow_count
    if strand is None:
        assert group.find("svg:path[@stroke-dasharray='5 3']", SVG_NS) is not None
    else:
        arc = group.find("svg:path[@class='feature-arc']", SVG_NS)
        arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)
        assert arc is not None
        assert arrow is not None
        assert arc.attrib["stroke-linecap"] == "butt"
        assert arrow.attrib["data-integrated"] == "true"
        assert arrow.attrib["stroke"] == "none"
        assert arrow.attrib["fill"] == arc.attrib["stroke"]
        coordinate = int(arrow.attrib["data-coordinate"])
        base_coordinate = float(arrow.attrib["data-base-coordinate"])
        assert base_coordinate < coordinate if strand == 1 else base_coordinate > coordinate


@pytest.mark.parametrize("feature_span", [1, 2, 5, 10])
def test_circular_short_feature_never_renders_an_oversized_arrow(feature_span: int) -> None:
    sequence_length = 10_000
    document = _source_document(
        {
            "name": f"Short forward feature {feature_span} bp",
            "type": "misc_feature",
            "start": 4_000,
            "end": 4_000 + feature_span,
            "strand": 1,
        },
        length=sequence_length,
    )
    root = _root(render_publication_map_svg(document))
    group = _feature_groups(root)[0]
    feature = document.features[0]
    feature_arc_length = _circular_feature_arc_length(group, feature_span, sequence_length)
    arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)

    assert feature_arc_length == pytest.approx(
        2 * math.pi * 336.4 * feature_span / sequence_length,
        rel=1e-6,
    )
    # Circular arrows are intentionally suppressed below a 4 px visible arc.
    assert feature_arc_length < 4.0
    assert arrow is None
    assert group.attrib["data-direction"] == "forward"
    assert group.find("svg:title", SVG_NS).text == f"Short forward feature {feature_span} bp"
    assert group.attrib["data-feature-id"] == feature.feature_id
    assert feature.parts[0].authoritative.start == 4_000
    assert feature.parts[0].authoritative.end == 4_000 + feature_span
    assert root.find(
        f".//svg:text[@data-label-for='{feature.feature_id}']",
        SVG_NS,
    ) is not None


@pytest.mark.parametrize(("feature_span", "expect_arrow"), [(18, False), (19, True)])
def test_circular_arrow_threshold_is_deterministic_and_bounded(
    feature_span: int,
    expect_arrow: bool,
) -> None:
    sequence_length = 10_000
    start = 4_000
    document = _source_document(
        {
            "name": "Threshold feature",
            "type": "misc_feature",
            "start": start,
            "end": start + feature_span,
            "strand": 1,
        },
        length=sequence_length,
    )
    first = render_publication_map_svg(document)
    second = render_publication_map_svg(document)
    group = _feature_groups(_root(first))[0]
    feature_arc_length = _circular_feature_arc_length(group, feature_span, sequence_length)
    arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)

    assert first == second
    assert (arrow is not None) is expect_arrow
    if arrow is not None:
        assert _arrow_tangent_extent(
            arrow,
            start + feature_span,
            1,
            sequence_length,
        ) <= feature_arc_length


@pytest.mark.parametrize(("strand", "coordinate"), [(1, 5_000), (-1, 4_000)])
def test_circular_ordinary_feature_retains_one_strand_correct_bounded_arrow(
    strand: int,
    coordinate: int,
) -> None:
    sequence_length = 10_000
    feature_span = 1_000
    document = _source_document(
        {
            "name": "Ordinary directional feature",
            "type": "misc_feature",
            "start": 4_000,
            "end": 5_000,
            "strand": strand,
        },
        length=sequence_length,
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]
    arrows = group.findall("svg:polygon[@class='direction-arrow']", SVG_NS)
    feature_arc_length = _circular_feature_arc_length(group, feature_span, sequence_length)

    assert group.attrib["data-direction"] == ("forward" if strand == 1 else "reverse")
    assert len(arrows) == 1
    assert arrows[0].attrib["data-coordinate"] == str(coordinate)
    assert arrows[0].attrib["data-integrated"] == "true"
    assert arrows[0].attrib["stroke"] == "none"
    assert _arrow_tangent_extent(
        arrows[0],
        coordinate,
        strand,
        sequence_length,
    ) <= feature_arc_length


def test_circular_leader_starts_on_feature_band_outer_edge() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 4, "end": 22, "strand": 1}
    )
    root = _root(render_publication_map_svg(document))
    leader = root.find(
        f".//svg:path[@class='leader'][@data-leader-for='{document.features[0].feature_id}']",
        SVG_NS,
    )
    assert leader is not None
    match = re.match(r"M ([^ ]+) ([^ ]+)", leader.attrib["d"])
    assert match is not None
    start_x, start_y = (float(value) for value in match.groups())
    cx, cy = 600.0, 437.5
    anchor_radius = math.hypot(start_x - cx, start_y - cy)
    assert anchor_radius == pytest.approx(326.4 + 10.0 + 9.0 / 2 + 0.75, abs=0.01)


def test_circular_overlaps_use_minimal_deterministic_lanes_without_shifting_non_overlaps() -> None:
    features = (
        {"name": "Overlap promoter", "type": "promoter", "start": 10, "end": 40, "strand": 1},
        {"name": "Nested CDS", "type": "CDS", "start": 20, "end": 35, "strand": 1},
        {"name": "Non-overlap feature", "type": "misc_feature", "start": 40, "end": 70, "strand": 1},
    )
    document = _source_document(*features)
    root = _root(render_publication_map_svg(document))
    lanes = {
        group.attrib["data-feature-id"]: int(group.attrib["data-lane"])
        for group in _feature_groups(root)
    }

    assert [lanes[feature.feature_id] for feature in document.features] == [0, 1, 0]
    assert len(set(lanes.values())) == 2

    reordered = _source_document(*reversed(features))
    reordered_lanes = {
        group.attrib["data-feature-id"]: int(group.attrib["data-lane"])
        for group in _feature_groups(_root(render_publication_map_svg(reordered)))
    }
    assert reordered_lanes == lanes


def test_circular_leader_anchor_follows_the_assigned_feature_lane() -> None:
    document = _source_document(
        {"name": "Outer promoter", "type": "promoter", "start": 10, "end": 40, "strand": 1},
        {"name": "Nested CDS", "type": "CDS", "start": 20, "end": 35, "strand": 1},
    )
    feature = document.features[1]
    root = _root(render_publication_map_svg(document))
    group = root.find(
        f".//svg:g[@class='map-feature'][@data-feature-id='{feature.feature_id}']",
        SVG_NS,
    )
    leader = root.find(
        f".//svg:path[@class='leader'][@data-leader-for='{feature.feature_id}']",
        SVG_NS,
    )

    assert group is not None
    assert leader is not None
    assert group.attrib["data-lane"] == "1"
    match = re.match(r"M ([^ ]+) ([^ ]+)", leader.attrib["d"])
    assert match is not None
    start_x, start_y = (float(value) for value in match.groups())
    anchor_radius = math.hypot(start_x - 600.0, start_y - 437.5)
    assert anchor_radius == pytest.approx(float(group.attrib["data-radius"]) + 9.0 / 2 + 0.75, abs=0.01)


def test_circular_promoter_leaders_remain_bound_to_the_exact_feature_arc() -> None:
    document = _source_document(
        {"name": "CaMV35S", "type": "promoter", "start": 8, "end": 24, "strand": 1},
        {"name": "PlacZ", "type": "promoter", "start": 16, "end": 31, "strand": -1},
    )
    root = _root(render_publication_map_svg(document))

    for feature in document.features:
        group = root.find(
            f".//svg:g[@class='map-feature'][@data-feature-id='{feature.feature_id}']",
            SVG_NS,
        )
        leader = root.find(
            f".//svg:path[@class='leader'][@data-leader-for='{feature.feature_id}']",
            SVG_NS,
        )
        label = root.find(
            f".//svg:text[@data-label-for='{feature.feature_id}']",
            SVG_NS,
        )
        assert group is not None
        assert leader is not None
        assert label is not None
        match = re.match(r"M ([^ ]+) ([^ ]+)", leader.attrib["d"])
        assert match is not None
        start_x, start_y = (float(value) for value in match.groups())
        expected_radius = float(group.attrib["data-radius"]) + 9.0 / 2 + 0.75
        midpoint = (
            feature.parts[0].authoritative.start + feature.parts[0].authoritative.end
        ) / 2
        angle = -math.pi / 2 + midpoint / document.sequence_length * 2 * math.pi
        expected_x = 600.0 + expected_radius * math.cos(angle)
        expected_y = 437.5 + expected_radius * math.sin(angle)
        assert start_x == pytest.approx(expected_x, abs=0.01)
        assert start_y == pytest.approx(expected_y, abs=0.01)


def test_circular_top_dense_labels_are_balanced_across_rails() -> None:
    document = _source_document(*_coincident_circular_features(10))
    root = _root(render_publication_map_svg(document))
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)
    left = [label for label in labels if float(label.attrib["data-label-x"]) < 600]
    right = [label for label in labels if float(label.attrib["data-label-x"]) > 600]
    assert len(left) == len(right) == 5
    assert render_publication_map_svg(document) == render_publication_map_svg(document)


@pytest.mark.parametrize(
    ("strand", "parts", "expected_coordinate"),
    [
        (1, [{"start": 90, "end": 100, "strand": 1}, {"start": 0, "end": 8, "strand": 1}], "8"),
        (-1, [{"start": 0, "end": 8, "strand": -1}, {"start": 90, "end": 100, "strand": -1}], "90"),
    ],
)
def test_origin_crossing_is_one_feature_with_strand_correct_terminal_arrow(
    strand: int,
    parts: list[dict[str, int]],
    expected_coordinate: str,
) -> None:
    document = _source_document(
        {
            "name": "Origin crossing",
            "type": "misc_feature",
            "start": 0,
            "end": 100,
            "strand": strand,
            "location_operator": "join",
            "location_parts": parts,
        }
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]

    assert group.attrib["data-wraps-origin"] == "true"
    assert len(group.findall("svg:path[@class='feature-arc']", SVG_NS)) == 2
    arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)
    assert arrow is not None
    assert arrow.attrib["data-coordinate"] == expected_coordinate


def test_renderer_rejects_duplicate_compound_parts_with_adapter_contract_error() -> None:
    document = _source_document(
        {"name": "Feature", "type": "misc_feature", "start": 10, "end": 30, "strand": 1}
    )
    feature = document.features[0]
    malformed = replace(
        feature,
        parts=(feature.parts[0], feature.parts[0]),
        location_operator="join",
    )

    with pytest.raises(PublicationMapContractError, match="coordinate-distinct"):
        render_publication_map_svg(replace(document, features=(malformed,)))


def test_renderer_rejects_full_sequence_part_inside_compound_location() -> None:
    document = _source_document(
        {"name": "Full", "type": "misc_feature", "start": 0, "end": 100, "strand": 1},
        {"name": "Internal", "type": "misc_feature", "start": 20, "end": 30, "strand": 1},
    )
    full, internal = document.features
    malformed = replace(
        full,
        parts=(full.parts[0], internal.parts[0]),
        location_operator="join",
    )

    with pytest.raises(PublicationMapContractError, match="full-sequence part"):
        render_publication_map_svg(replace(document, features=(malformed,)))


def test_linear_active_expression_fixture_has_ordered_directional_features_and_scale() -> None:
    document = _document_from_fixture("linear_active_expression_construct.json")
    svg = render_publication_map_svg(document)
    root = _root(svg)
    groups = _feature_groups(root)

    assert root.attrib["viewBox"] == "0 0 1400 640"
    assert [group.attrib["data-feature-id"] for group in groups] == [
        feature.feature_id for feature in document.features
    ]
    assert all(group.attrib["data-direction"] == "forward" for group in groups)
    assert len(root.findall(".//svg:polygon[@class='feature-block direction-arrow']", SVG_NS)) == 3
    assert "ACTIVE EXPRESSION CONSTRUCT" in "".join(root.itertext())
    assert "Position (bp)" in "".join(root.itertext())
    assert hashlib.sha256(svg.encode("utf-8")).hexdigest() == (
        "38d4e4bf8e1d8638a8a1635b126f63f0111ef670585d1e5c296fc2c74d94601c"
    )


@pytest.mark.parametrize(
    ("strand", "parts", "expected_coordinate", "expected_terminal_part"),
    [
        (1, [{"start": 0, "end": 1, "strand": 1}, {"start": 900, "end": 1000, "strand": 1}], 1, 1),
        (-1, [{"start": 0, "end": 100, "strand": -1}, {"start": 999, "end": 1000, "strand": -1}], 999, 2),
    ],
)
def test_circular_origin_crossing_arrow_tip_base_and_path_share_authoritative_terminal_part(
    strand: int, parts: list[dict[str, int]], expected_coordinate: int, expected_terminal_part: int
) -> None:
    document = _source_document(
        {"name": "Origin crossing terminal identity", "type": "misc_feature", "start": 0, "end": 1000,
         "strand": strand, "location_operator": "join", "location_parts": parts}, length=1000
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]
    arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)
    terminal_paths = [path for path in group.findall("svg:path[@class='feature-arc']", SVG_NS)
                      if path.attrib["data-terminal-part"] == "true"]
    assert arrow is None
    assert terminal_paths == []


@pytest.mark.parametrize(
    ("strand", "parts", "expected_coordinate", "expected_terminal_part"),
    [
        (1, [{"start": 0, "end": 80, "strand": 1}, {"start": 900, "end": 1000, "strand": 1}], 80, 1),
        (-1, [{"start": 0, "end": 100, "strand": -1}, {"start": 900, "end": 1000, "strand": -1}], 900, 2),
    ],
)
def test_circular_origin_crossing_long_terminal_renders_one_bounded_arrow(
    strand: int, parts: list[dict[str, int]], expected_coordinate: int, expected_terminal_part: int
) -> None:
    document = _source_document(
        {"name": "Long origin terminal", "type": "misc_feature", "start": 0, "end": 1000,
         "strand": strand, "location_operator": "join", "location_parts": parts}, length=1000
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]
    arrow = group.find("svg:polygon[@class='direction-arrow']", SVG_NS)
    assert arrow is not None and int(arrow.attrib["data-coordinate"]) == expected_coordinate
    paths = [path for path in group.findall("svg:path[@class='feature-arc']", SVG_NS)
             if path.attrib["data-terminal-part"] == "true"]
    assert [int(path.attrib["data-part"]) for path in paths] == [expected_terminal_part]
    terminal = parts[expected_terminal_part - 1]
    assert terminal["start"] <= float(arrow.attrib["data-base-coordinate"]) <= terminal["end"]


def test_circular_origin_crossing_short_true_terminal_suppresses_arrowhead() -> None:
    document = _source_document(
        {"name": "Short origin terminal", "type": "misc_feature", "start": 0, "end": 1000, "strand": 1,
         "location_operator": "join", "location_parts": [{"start": 0, "end": 1, "strand": 1},
         {"start": 900, "end": 1000, "strand": 1}]}, length=1000
    )
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]
    assert group.find("svg:polygon[@class='direction-arrow']", SVG_NS) is None


def test_circular_non_origin_compound_and_single_part_arrows_remain_bounded() -> None:
    document = _source_document(
        {"name": "Non-origin compound", "type": "misc_feature", "start": 100, "end": 400, "strand": 1,
         "location_operator": "join", "location_parts": [{"start": 100, "end": 180, "strand": 1},
         {"start": 300, "end": 400, "strand": 1}]},
        {"name": "Single reverse", "type": "misc_feature", "start": 600, "end": 800, "strand": -1}, length=1000
    )
    groups = _feature_groups(_root(render_publication_map_svg(document)))
    assert float(groups[0].find("svg:polygon[@class='direction-arrow']", SVG_NS).attrib["data-base-coordinate"]) >= 300
    assert float(groups[1].find("svg:polygon[@class='direction-arrow']", SVG_NS).attrib["data-base-coordinate"]) >= 600


def test_linear_map_keeps_one_physical_axis_and_separates_tu_group_bands() -> None:
    document = _source_document(
        {"name": "TU1 promoter", "type": "promoter", "start": 0, "end": 20, "strand": 1, "unit_id": "tu:one", "unit_order": 1},
        {"name": "TU1 CDS", "type": "CDS", "start": 20, "end": 45, "strand": 1, "unit_id": "tu:one", "unit_order": 1},
        {"name": "TU2 CDS", "type": "CDS", "start": 55, "end": 80, "strand": -1, "unit_id": "tu:two", "unit_order": 2},
        topology="linear",
    )
    root = _root(render_publication_map_svg(document))
    polygons = root.findall(".//svg:polygon[@class='feature-block direction-arrow']", SVG_NS)
    polygon_centers = {
        round(sum(float(point.split(",")[1]) for point in polygon.attrib["points"].split()) / 5, 3)
        for polygon in polygons
    }
    bands = root.findall(".//svg:path[@class='tu-band']", SVG_NS)
    labels = root.findall(".//svg:text[@class='tu-label']", SVG_NS)

    assert len(bands) == 2
    assert len(labels) == 2
    assert polygon_centers == {310.0}
    assert [tick.attrib["data-coordinate"] for tick in root.findall(".//svg:line[@class='coordinate-tick']", SVG_NS)] == ["0", "20", "40", "60", "80", "100"]


@pytest.mark.parametrize(
    ("fixture", "width", "height"),
    [
        ("dense_synthetic_plant_binary_vector.json", 1200, 960),
        ("linear_active_expression_construct.json", 1400, 640),
    ],
)
def test_renderer_label_and_legend_layout_contract_stays_inside_viewbox(
    fixture: str,
    width: int,
    height: int,
) -> None:
    root = _root(render_publication_map_svg(_document_from_fixture(fixture)))
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)
    assert labels
    for label in labels:
        x = float(label.attrib["data-label-x"])
        y = float(label.attrib["data-label-y"])
        assert 0 <= x <= width
        assert 0 <= y <= height
    _assert_declared_text_bounds_inside_viewbox(root)
    legend = root.find(".//svg:g[@id='map-legend']", SVG_NS)
    assert legend is not None
    x1, y1, x2, y2 = (float(value) for value in legend.attrib["data-bounds"].split(","))
    assert 0 <= x1 <= x2 <= width
    assert 0 <= y1 <= y2 <= height


@pytest.mark.parametrize(
    ("label", "feature_type"),
    [
        ("A" * 240, "promoter"),
        ("超长植物表达元件标签" * 24, "five_prime_utr"),
        ("Custom role " * 35, "future_feature_class"),
        ('A&B <review> "quoted"\' apostrophe ' * 16, "misc_feature"),
    ],
)
def test_circular_adversarial_labels_are_fitted_with_full_title_preserved(
    label: str,
    feature_type: str,
) -> None:
    document = _source_document(
        {"name": label, "type": feature_type, "start": 4, "end": 22, "strand": 1},
        {"name": "Opposite feature", "type": "CDS", "start": 54, "end": 75, "strand": -1},
    )
    root = _root(render_publication_map_svg(document))
    visible_label = root.find(
        f".//svg:text[@data-label-for='{document.features[0].feature_id}']", SVG_NS
    )

    assert visible_label is not None
    assert visible_label.find("svg:title", SVG_NS).text == document.features[0].display_label
    assert (visible_label.text or "").endswith("...")
    _assert_declared_text_bounds_inside_viewbox(root)


def test_linear_endpoint_labels_and_short_features_remain_inside_canvas() -> None:
    start_label = "Start endpoint feature " * 24
    end_label = "终点宽字符标签" * 30
    document = _source_document(
        {"name": start_label, "type": "promoter", "start": 0, "end": 1, "strand": 1},
        {"name": end_label, "type": "terminator", "start": 99, "end": 100, "strand": -1},
        topology="linear",
    )
    root = _root(render_publication_map_svg(document))
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)
    feature_blocks = root.findall(".//svg:polygon[@class='feature-block direction-arrow']", SVG_NS)

    assert len(labels) == 2
    assert [label.find("svg:title", SVG_NS).text for label in labels] == [
        feature.display_label for feature in document.features
    ]
    _assert_declared_text_bounds_inside_viewbox(root)
    for block in feature_blocks:
        points = [tuple(map(float, pair.split(","))) for pair in block.attrib["points"].split()]
        assert all(0 <= x <= 1400 and 0 <= y <= 640 for x, y in points)
    groups = _feature_groups(root)
    assert [group.attrib["data-direction"] for group in groups] == ["forward", "reverse"]


def test_overlapping_linear_features_use_non_overlapping_above_and_below_layers() -> None:
    features = [
        {
            "name": f"Overlapping feature {index}",
            "type": "misc_feature",
            "start": 45,
            "end": 55,
            "strand": 1 if index % 2 else -1,
        }
        for index in range(1, 7)
    ]
    root = _root(render_publication_map_svg(_source_document(*features, topology="linear")))
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)
    bounds = [
        tuple(float(value) for value in label.attrib["data-layout-bounds"].split(","))
        for label in labels
    ]

    assert any(float(label.attrib["data-label-y"]) < 310 for label in labels)
    assert any(float(label.attrib["data-label-y"]) > 310 for label in labels)
    for index, (left, top, right, bottom) in enumerate(bounds):
        for other_left, other_top, other_right, other_bottom in bounds[index + 1 :]:
            assert right <= other_left or other_right <= left or bottom <= other_top or other_bottom <= top
    _assert_declared_text_bounds_inside_viewbox(root)


@pytest.mark.parametrize("count", [8, 10, 12])
def test_coincident_linear_features_use_bounded_collision_free_overflow_rails(count: int) -> None:
    document = _source_document(*_coincident_features(count), topology="linear")
    first = render_publication_map_svg(document)
    second = render_publication_map_svg(document)
    root = _root(first)
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)
    overflow_labels = root.findall(".//svg:text[@data-label-layout]", SVG_NS)
    overflow_leaders = root.findall(".//svg:path[@data-leader-for]", SVG_NS)

    assert first == second
    assert len(_feature_groups(root)) == count
    assert len(labels) == count
    assert len({label.attrib["data-label-for"] for label in labels}) == count
    assert len(overflow_labels) == max(0, count - 7)
    assert {label.attrib["data-label-for"] for label in overflow_labels} == {
        leader.attrib["data-leader-for"] for leader in overflow_leaders
    }
    assert [label.find("svg:title", SVG_NS).text for label in labels] == [
        feature.display_label for feature in document.features
    ]
    _assert_declared_text_bounds_inside_viewbox(root)
    _assert_no_feature_label_bounds_overlap(root)


@pytest.mark.parametrize(
    "label",
    [
        "Long coincident plant expression feature label " * 12,
        "重合植物表达元件标签" * 28,
    ],
)
def test_long_and_unicode_coincident_linear_labels_preserve_full_titles(label: str) -> None:
    document = _source_document(*_coincident_features(12, label=label), topology="linear")
    root = _root(render_publication_map_svg(document))
    labels = root.findall(".//svg:text[@data-label-for]", SVG_NS)

    assert len(labels) == 12
    assert all((visible.text or "").endswith("...") for visible in labels)
    assert [visible.find("svg:title", SVG_NS).text for visible in labels] == [
        feature.display_label for feature in document.features
    ]
    _assert_declared_text_bounds_inside_viewbox(root)
    _assert_no_feature_label_bounds_overlap(root)


def test_nearby_dense_linear_features_have_collision_free_deterministic_layout() -> None:
    features = [
        {
            "name": f"Nearby feature {index:02d}",
            "type": "misc_feature",
            "start": 42 + index % 4,
            "end": 54 + index % 4,
            "strand": 1 if index % 2 else -1,
        }
        for index in range(12)
    ]
    document = _source_document(*features, topology="linear")
    root = _root(render_publication_map_svg(document))

    assert len(_feature_groups(root)) == 12
    assert len(root.findall(".//svg:text[@data-label-for]", SVG_NS)) == 12
    _assert_declared_text_bounds_inside_viewbox(root)
    _assert_no_feature_label_bounds_overlap(root)


def test_dense_linear_svg_is_independent_of_permitted_source_feature_order() -> None:
    features = _coincident_features(12)
    forward = _source_document(*features, topology="linear")
    reordered = _source_document(*reversed(features), topology="linear")

    assert forward == reordered
    assert render_publication_map_svg(forward) == render_publication_map_svg(reordered)


def test_over_capacity_linear_labels_fail_closed_instead_of_overlapping() -> None:
    document = _source_document(*_coincident_features(28), topology="linear")

    with pytest.raises(
        PublicationMapContractError,
        match="collision-free canvas capacity",
    ):
        render_publication_map_svg(document)


def test_default_canvas_supports_documented_27_coincident_label_capacity() -> None:
    document = _source_document(*_coincident_features(27), topology="linear")
    root = _root(render_publication_map_svg(document))

    assert len(_feature_groups(root)) == 27
    assert len(root.findall(".//svg:text[@data-label-for]", SVG_NS)) == 27
    assert len(root.findall(".//svg:text[@data-label-layout]", SVG_NS)) == 20
    _assert_declared_text_bounds_inside_viewbox(root)
    _assert_no_feature_label_bounds_overlap(root)


def test_over_capacity_document_renders_when_labels_are_hidden() -> None:
    document = _source_document(*_coincident_features(30), topology="linear")
    root = _root(
        render_publication_map_svg(
            document,
            PublicationMapRenderOptions(width=900, height=520, show_labels=False),
        )
    )

    assert len(_feature_groups(root)) == 30
    assert root.findall(".//svg:text[@data-label-for]", SVG_NS) == []


def test_legend_uses_only_present_scientific_roles_without_merged_terms() -> None:
    document = _source_document(
        {"name": "Promoter", "type": "promoter", "start": 0, "end": 10, "strand": 1},
        {"name": "5 prime region", "type": "five_prime_utr", "start": 10, "end": 20, "strand": 1},
        {"name": "Enhancer", "type": "enhancer", "start": 20, "end": 30, "strand": 1},
        {"name": "Terminator", "type": "terminator", "start": 30, "end": 40, "strand": 1},
        {"name": "Custom", "type": "future_feature_class", "start": 40, "end": 50, "strand": None},
    )
    root = _root(render_publication_map_svg(document))
    legend = root.find(".//svg:g[@id='map-legend']", SVG_NS)
    entries = legend.findall("svg:text[@class='legend-label']", SVG_NS)

    assert [entry.attrib["data-category"] for entry in entries] == [
        "promoter",
        "five_prime_region",
        "enhancer",
        "terminator",
        "unclassified",
    ]
    assert [(entry.text or "") for entry in entries] == [
        "Promoter",
        "5' region",
        "Enhancer",
        "Terminator",
        "Other / unclassified",
    ]
    assert "3' region / terminator" not in "".join(root.itertext())


def test_unknown_role_uses_neutral_fallback_without_reclassification() -> None:
    document = _source_document(
        {"name": "Custom role", "type": "future_feature_class", "start": 10, "end": 30, "strand": None}
    )
    feature = document.features[0]
    group = _feature_groups(_root(render_publication_map_svg(document)))[0]

    assert feature.display_category == "unclassified"
    assert group.attrib["data-category"] == "unclassified"
    assert group.attrib["data-style-role"] == "Other / unclassified"


def test_special_characters_are_escaped_and_round_trip_as_text() -> None:
    label = 'A&B <review> "quoted"'
    document = _source_document(
        {"name": label, "type": "misc_feature", "start": 10, "end": 30, "strand": 1},
        name="Construct & review <map>",
    )
    svg = render_publication_map_svg(document)
    root = _root(svg)

    assert "A&amp;B &lt;review&gt;" in svg
    assert label in "".join(root.itertext())
    assert "Construct & review <map>" in "".join(root.itertext())


@pytest.mark.parametrize(
    "mutator",
    [
        lambda document: replace(document, schema_version="future.schema"),
        lambda document: replace(document, sequence_length=0),
        lambda document: replace(document, construct_identifier=""),
        lambda document: replace(document, sequence_checksum="not-a-checksum"),
        lambda document: replace(document, topology=PublicationMapTopology.LINEAR),
        lambda document: replace(document, features=(document.features[0], document.features[0])),
    ],
)
def test_invalid_renderer_input_fails_closed(mutator) -> None:
    document = _source_document(
        {"name": "Feature", "type": "misc_feature", "start": 10, "end": 30, "strand": 1}
    )
    with pytest.raises(PublicationMapContractError):
        render_publication_map_svg(mutator(document))


@pytest.mark.parametrize(
    "options",
    [
        PublicationMapRenderOptions(width=0),
        PublicationMapRenderOptions(height=0),
        PublicationMapRenderOptions(width=-1),
        PublicationMapRenderOptions(height=-1),
        PublicationMapRenderOptions(width=899),
        PublicationMapRenderOptions(height=2001),
        PublicationMapRenderOptions(width=True),
        PublicationMapRenderOptions(width="1200"),
        PublicationMapRenderOptions(height=math.nan),
        PublicationMapRenderOptions(width=math.inf),
        PublicationMapRenderOptions(show_labels=1),
    ],
)
def test_invalid_render_options_fail_predictably(options: PublicationMapRenderOptions) -> None:
    document = _source_document(
        {"name": "Feature", "type": "misc_feature", "start": 10, "end": 30, "strand": 1}
    )
    with pytest.raises(PublicationMapContractError):
        render_publication_map_svg(document, options)


@pytest.mark.parametrize(
    ("topology", "expected_width", "expected_height"),
    [("circular", "1200", "960"), ("linear", "1400", "640")],
)
def test_omitted_or_none_dimensions_use_documented_defaults(
    topology: str,
    expected_width: str,
    expected_height: str,
) -> None:
    document = _source_document(
        {"name": "Feature", "type": "misc_feature", "start": 10, "end": 30, "strand": 1},
        topology=topology,
    )

    omitted = _root(render_publication_map_svg(document))
    explicit_none = _root(
        render_publication_map_svg(
            document,
            PublicationMapRenderOptions(width=None, height=None),
        )
    )

    assert (omitted.attrib["width"], omitted.attrib["height"]) == (
        expected_width,
        expected_height,
    )
    assert (explicit_none.attrib["width"], explicit_none.attrib["height"]) == (
        expected_width,
        expected_height,
    )


def test_renderer_does_not_mutate_frozen_dto() -> None:
    document = _document_from_fixture("dense_synthetic_plant_binary_vector.json")
    before = repr(document)
    first_ids = tuple(id(feature) for feature in document.features)

    render_publication_map_svg(document, PublicationMapRenderOptions(show_legend=False))

    assert repr(document) == before
    assert tuple(id(feature) for feature in document.features) == first_ids


def test_geometry_numbers_are_finite() -> None:
    document = _document_from_fixture("dense_synthetic_plant_binary_vector.json")
    svg = render_publication_map_svg(document)
    numeric_tokens = re.findall(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?', svg)
    assert numeric_tokens
    assert all(math.isfinite(float(token)) for token in numeric_tokens)
