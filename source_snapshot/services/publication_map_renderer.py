from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from html import escape
from typing import Iterable

from services.publication_map_contract import (
    PUBLICATION_MAP_REVISION_PROVENANCE_FIELD,
    PUBLICATION_MAP_SCHEMA_VERSION,
    PublicationMapContractError,
    PublicationMapDocument,
    PublicationMapFeature,
    PublicationMapLocationPart,
    PublicationMapTopology,
    PublicationMapViewType,
    publication_map_wraps_origin,
)


PUBLICATION_MAP_RENDERER_VERSION = "publication-map-svg-r3"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ROLE_STYLES = {
    "promoter": ("Promoter", "#2A6FBB"),
    "five_prime_region": ("5' region", "#4C8B76"),
    "enhancer": ("Enhancer", "#7A5195"),
    "cds": ("CDS", "#D55E00"),
    "terminator": ("Terminator", "#008F6B"),
    "selectable_marker": ("Selectable marker", "#B44E8B"),
    "origin": ("Origin", "#C98B00"),
    "left_border": ("Left border", "#347A88"),
    "right_border": ("Right border", "#735A9E"),
    "insertion_region": ("Insertion region", "#5C6670"),
    "replacement_region": ("Replacement region", "#8B6F47"),
    "regulatory_feature": ("Regulatory feature", "#567B3E"),
    "unclassified": ("Other / unclassified", "#68737D"),
}
_ROLE_ORDER = tuple(_ROLE_STYLES)
_NEUTRAL_STYLE = _ROLE_STYLES["unclassified"]
_CANVAS_MARGIN = 18.0
_FEATURE_LABEL_FONT_SIZE = 12.0
_FEATURE_LABEL_ASCENT = 12.0
_FEATURE_LABEL_DESCENT = 4.0
_ELLIPSIS = "..."
_CIRCULAR_BACKBONE_STROKE = 2.5
_CIRCULAR_FEATURE_RADIUS_OFFSET = 10.0
_CIRCULAR_KEY_FEATURE_STROKE = 9.0
_CIRCULAR_SECONDARY_FEATURE_STROKE = 6.0
_CIRCULAR_CONTEXT_FEATURE_STROKE = 3.5
_CIRCULAR_FEATURE_LANE_GAP = 2.0
_CIRCULAR_MAX_FEATURE_LANES = 3
_CIRCULAR_ARROW_MAX_LENGTH = 10.0
_CIRCULAR_ARROW_MIN_VISIBLE_ARC = 4.0
_CIRCULAR_ARROW_LENGTH_FRACTION = 0.38
_CIRCULAR_LABEL_CAPACITY = 21


@dataclass(frozen=True, slots=True)
class PublicationMapRenderOptions:
    width: int | None = None
    height: int | None = None
    show_labels: bool = True
    show_legend: bool = True


@dataclass(frozen=True, slots=True)
class _Label:
    feature: PublicationMapFeature
    anchor_x: float
    anchor_y: float
    desired_y: float
    side: str


@dataclass(frozen=True, slots=True)
class _FittedText:
    visible: str
    estimated_width: float


@dataclass(frozen=True, slots=True)
class _CircularArrow:
    points: str
    base_coordinate: float


@dataclass(frozen=True, slots=True)
class _LinearLabelLayout:
    baseline_y: float
    x: float
    fitted: _FittedText
    above_track: bool
    anchor: str = "middle"
    overflow_side: str | None = None


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise PublicationMapContractError("Renderer geometry must be finite.")
    rounded = round(value, 3)
    if abs(rounded) < 0.0005:
        rounded = 0.0
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def _text(value: object) -> str:
    return escape(str(value), quote=False)


def _attribute(value: object) -> str:
    return escape(str(value), quote=True)


def _style(category: str) -> tuple[str, str]:
    return _ROLE_STYLES.get(category, _NEUTRAL_STYLE)


_CIRCULAR_PRIMARY_CATEGORIES = frozenset(
    {"promoter", "cds", "terminator", "selectable_marker", "origin"}
)
_CIRCULAR_CONTEXT_CATEGORIES = frozenset({"insertion_region", "replacement_region"})
_SOURCE_METADATA_TYPES = frozenset({"source", "source_record", "source_feature"})


def _semantic_token(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _is_full_length_source_metadata(
    feature: PublicationMapFeature,
    sequence_length: int,
) -> bool:
    """Identify only a complete, single-part source record envelope.

    The feature stays in the immutable document; this predicate controls
    circular display only.  A full-length feature with a biological category or
    a non-source authoritative type remains visible.
    """

    if _semantic_token(feature.authoritative_type) not in _SOURCE_METADATA_TYPES:
        return False
    if len(feature.parts) != 1:
        return False
    interval = feature.parts[0].authoritative
    return (
        interval.start == 0
        and interval.end == sequence_length
        and feature.display_category == "unclassified"
        and not any(
            _semantic_token(value)
            for value in (
                feature.component_type,
                feature.biological_role,
                feature.regulatory_class,
            )
        )
    )


def _circular_priority(feature: PublicationMapFeature) -> str:
    if feature.display_category in _CIRCULAR_PRIMARY_CATEGORIES:
        return "key"
    if feature.display_category in _CIRCULAR_CONTEXT_CATEGORIES:
        return "context"
    return "secondary"


def _fit_circular_label(value: str, max_width: float) -> tuple[_FittedText, bool]:
    """Keep moderately long publication labels whole without overflowing rails."""

    fitted = _fit_text(value, max_width, _FEATURE_LABEL_FONT_SIZE)
    full_width = _estimated_text_width(value, _FEATURE_LABEL_FONT_SIZE)
    # A modest horizontal compression keeps common construct/container names
    # readable and complete; very long labels retain the established ellipsis
    # policy and their full accessible title.
    if fitted.visible != value and full_width <= max_width * 1.45:
        return _FittedText(value, max_width), True
    return fitted, False


def _truncate(label: str, limit: int) -> str:
    if len(label) <= limit:
        return label
    return label[: max(1, limit - 3)].rstrip() + "..."


def _glyph_width_em(character: str) -> float:
    """Return a conservative, platform-independent glyph width in em units."""

    if unicodedata.combining(character):
        return 0.0
    if character.isspace():
        return 0.45
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 1.05
    if character in "ilI!|.,'`:;()[]{}":
        return 0.45
    if character in "MW@%&mw":
        return 1.05
    if ord(character) < 128:
        return 0.78
    return 0.95


def _estimated_text_width(value: str, font_size: float) -> float:
    """Estimate a safe layout width without consulting workstation font metrics."""

    return 2.0 + sum(_glyph_width_em(character) for character in value) * font_size


def _fit_text(value: str, max_width: float, font_size: float) -> _FittedText:
    if not isinstance(value, str) or not value:
        raise PublicationMapContractError("Renderer text must be a non-empty string.")
    if not math.isfinite(max_width) or max_width <= 0:
        raise PublicationMapContractError("Renderer text width must be positive and finite.")
    full_width = _estimated_text_width(value, font_size)
    if full_width <= max_width:
        return _FittedText(value, full_width)
    ellipsis_width = _estimated_text_width(_ELLIPSIS, font_size)
    budget = max_width - ellipsis_width
    visible: list[str] = []
    used = 0.0
    for character in value:
        character_width = _glyph_width_em(character) * font_size
        if used + character_width > budget:
            break
        visible.append(character)
        used += character_width
    prefix = "".join(visible).rstrip()
    if not prefix:
        prefix = value[0]
    fitted = prefix + _ELLIPSIS
    while len(prefix) > 1 and _estimated_text_width(fitted, font_size) > max_width:
        prefix = prefix[:-1].rstrip()
        fitted = prefix + _ELLIPSIS
    return _FittedText(fitted, min(max_width, _estimated_text_width(fitted, font_size)))


def _horizontal_text_bounds(x: float, width: float, anchor: str) -> tuple[float, float]:
    if anchor == "start":
        return x, x + width
    if anchor == "end":
        return x - width, x
    return x - width / 2, x + width / 2


def _label_bounds_attribute(
    x: float,
    baseline_y: float,
    width: float,
    anchor: str,
    *,
    ascent: float = _FEATURE_LABEL_ASCENT,
    descent: float = _FEATURE_LABEL_DESCENT,
) -> str:
    left, right = _horizontal_text_bounds(x, width, anchor)
    return ",".join(
        _number(value)
        for value in (
            left,
            baseline_y - ascent,
            right,
            baseline_y + descent,
        )
    )


def _display_coordinate(feature: PublicationMapFeature) -> str:
    if feature.wraps_origin:
        intervals = ", ".join(
            f"{part.display.start}-{part.display.end}" for part in feature.parts
        )
        return f"{intervals} bp"
    return f"{feature.display.start}-{feature.display.end} bp"


def _metadata(document: PublicationMapDocument) -> str:
    provenance = dict(document.provenance)
    revision = provenance.get(PUBLICATION_MAP_REVISION_PROVENANCE_FIELD) or None
    payload = {
        "checksum_algorithm": document.checksum_algorithm,
        "construct_identifier": document.construct_identifier,
        "renderer_version": PUBLICATION_MAP_RENDERER_VERSION,
        "revision": revision,
        "schema_version": document.schema_version,
        "sequence_checksum": document.sequence_checksum,
        "sequence_length": document.sequence_length,
        "topology": document.topology.value,
        "view_type": document.view.view_type.value,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _validate_document(document: PublicationMapDocument) -> None:
    if not isinstance(document, PublicationMapDocument):
        raise PublicationMapContractError(
            "Publication map renderer requires a frozen PublicationMapDocument."
        )
    if document.schema_version != PUBLICATION_MAP_SCHEMA_VERSION:
        raise PublicationMapContractError("Unsupported publication-map schema version.")
    if not document.construct_identifier.strip() or not document.display_name.strip():
        raise PublicationMapContractError("Publication map identity and display name are required.")
    if isinstance(document.sequence_length, bool) or document.sequence_length <= 0:
        raise PublicationMapContractError("Publication map sequence length must be positive.")
    if document.checksum_algorithm != "sha256" or not _SHA256_PATTERN.fullmatch(
        document.sequence_checksum
    ):
        raise PublicationMapContractError("Publication map requires a lowercase SHA-256 identity.")
    expected_views = {
        PublicationMapTopology.CIRCULAR: {PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID},
        PublicationMapTopology.LINEAR: {
            PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
            PublicationMapViewType.COMPLETE_LINEAR_PLASMID,
        },
    }.get(document.topology)
    if expected_views is None or document.view.topology is not document.topology:
        raise PublicationMapContractError("Publication map topology is inconsistent.")
    if document.view.view_type not in expected_views:
        raise PublicationMapContractError("Publication map view and topology are inconsistent.")
    region = document.view.authoritative_region
    display_region = document.view.display_region
    if (region.start, region.end) != (0, document.sequence_length):
        raise PublicationMapContractError("Publication map authoritative region must span the document.")
    if (display_region.start, display_region.end) != (1, document.sequence_length):
        raise PublicationMapContractError("Publication map display region must span the document.")
    if not isinstance(document.features, tuple):
        raise PublicationMapContractError("Publication map features must use the frozen tuple contract.")

    feature_ids: set[str] = set()
    for feature in document.features:
        if not isinstance(feature, PublicationMapFeature):
            raise PublicationMapContractError("Publication map contains a malformed feature.")
        if not feature.feature_id or feature.feature_id in feature_ids:
            raise PublicationMapContractError("Publication map feature IDs must be unique and non-empty.")
        feature_ids.add(feature.feature_id)
        if not feature.display_label:
            raise PublicationMapContractError("Publication map feature labels cannot be empty.")
        if feature.strand not in (-1, 1, None) or not feature.parts:
            raise PublicationMapContractError("Publication map feature strand or parts are invalid.")
        starts: list[int] = []
        ends: list[int] = []
        for part in feature.parts:
            interval = part.authoritative
            if (
                interval.start < 0
                or interval.end <= interval.start
                or interval.end > document.sequence_length
                or (part.display.start, part.display.end)
                != (interval.start + 1, interval.end)
                or part.strand != feature.strand
            ):
                raise PublicationMapContractError("Publication map feature part is inconsistent.")
            starts.append(interval.start)
            ends.append(interval.end)
        if (feature.authoritative.start, feature.authoritative.end) != (
            min(starts),
            max(ends),
        ):
            raise PublicationMapContractError("Publication map feature envelope is inconsistent.")
        if (feature.display.start, feature.display.end) != (
            feature.authoritative.start + 1,
            feature.authoritative.end,
        ):
            raise PublicationMapContractError("Publication map feature display interval is inconsistent.")
        calculated_wrap = publication_map_wraps_origin(
            feature.parts,
            document.topology,
            document.sequence_length,
        )
        if feature.wraps_origin != calculated_wrap:
            raise PublicationMapContractError("Publication map origin-crossing state is inconsistent.")


def _validate_options(
    document: PublicationMapDocument,
    options: PublicationMapRenderOptions | None,
) -> tuple[PublicationMapRenderOptions, int, int]:
    if options is None:
        options = PublicationMapRenderOptions()
    if not isinstance(options, PublicationMapRenderOptions):
        raise PublicationMapContractError("Renderer options must use PublicationMapRenderOptions.")
    for name, value in (("width", options.width), ("height", options.height)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise PublicationMapContractError(f"Renderer {name} must be an integer.")
        if value is not None and value <= 0:
            raise PublicationMapContractError(f"Renderer {name} must be positive.")
    if not isinstance(options.show_labels, bool) or not isinstance(options.show_legend, bool):
        raise PublicationMapContractError("Renderer visibility options must be boolean.")
    if document.topology is PublicationMapTopology.CIRCULAR:
        width = 1200 if options.width is None else options.width
        height = 960 if options.height is None else options.height
        minimum = (900, 780)
    else:
        width = 1400 if options.width is None else options.width
        if options.height is None:
            # Complete-plasmid linear views retain every canonical feature and
            # need more vertical label slots than the compact active-expression
            # canvas.  The canvas remains bounded and deterministic; feature
            # coordinates and labels are never dropped or merged.
            feature_count = len(document.features)
            height = 640
            if document.view.view_type is PublicationMapViewType.COMPLETE_LINEAR_PLASMID and feature_count > 27:
                height = min(1600, max(800, 640 + (feature_count - 27) * 24))
        else:
            height = options.height
        minimum = (900, 520)
    if width < minimum[0] or height < minimum[1] or width > 2400 or height > 2000:
        raise PublicationMapContractError(
            f"Renderer canvas must be between {minimum[0]}x{minimum[1]} and 2400x2000."
        )
    return options, width, height


def _svg_header(document: PublicationMapDocument, width: int, height: int) -> list[str]:
    title = f"{document.display_name} publication map"
    # Streamlit embeds the SVG in a narrower column than the deterministic
    # download canvas. Keep circular maps inside that column while preserving
    # their intrinsic viewBox and byte-stable geometry. Linear maps retain the
    # historical root element unchanged.
    root_layout = (
        ' style="max-width:100%;height:auto;display:block"'
        if document.topology is PublicationMapTopology.CIRCULAR
        else ""
    )
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="map-title map-description"{root_layout}>'
        ),
        f"<title id=\"map-title\">{_text(title)}</title>",
        (
            '<desc id="map-description">Deterministic vector rendering of the supplied '
            "Publication Map document.</desc>"
        ),
        f'<metadata id="publication-map-metadata">{_text(_metadata(document))}</metadata>',
        "<style>",
        (
            "text{font-family:Arial,Helvetica,sans-serif;fill:#17212B;letter-spacing:0}"
            ".map-title{font-size:20px;font-weight:700}.map-subtitle{font-size:12px;fill:#53606C}"
            ".feature-label{font-size:12px;font-weight:600}.coordinate-label{font-size:10px;fill:#66717C}"
            ".legend-label{font-size:11px}.scale-label{font-size:10px;fill:#66717C}"
            ".leader{stroke:#87919A;stroke-width:1;fill:none}.backbone{stroke:#39444E;fill:none}"
            ".tu-band{stroke:#52606B;stroke-width:1.2;fill:none}.tu-label{font-size:11px;font-weight:700;fill:#39444E}"
            f".map-feature[data-priority='secondary'] .feature-arc{{opacity:{'.82' if document.topology is PublicationMapTopology.CIRCULAR else '.62'}}}"
            ".map-feature[data-priority='key'] .feature-arc{opacity:1}"
        ),
        "</style>",
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]


def _polar(cx: float, cy: float, radius: float, coordinate: float, length: int) -> tuple[float, float]:
    angle = -math.pi / 2 + (coordinate / length) * 2 * math.pi
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _arc_path(
    cx: float,
    cy: float,
    radius: float,
    start: float,
    end: float,
    length: int,
) -> str:
    start_x, start_y = _polar(cx, cy, radius, start, length)
    end_x, end_y = _polar(cx, cy, radius, end, length)
    if end - start == length:
        middle_x, middle_y = _polar(cx, cy, radius, start + length / 2, length)
        return (
            f"M {_number(start_x)} {_number(start_y)} A {_number(radius)} {_number(radius)} "
            f"0 0 1 {_number(middle_x)} {_number(middle_y)} A {_number(radius)} "
            f"{_number(radius)} 0 0 1 {_number(end_x)} {_number(end_y)}"
        )
    large_arc = 1 if end - start > length / 2 else 0
    return (
        f"M {_number(start_x)} {_number(start_y)} A {_number(radius)} {_number(radius)} "
        f"0 {large_arc} 1 {_number(end_x)} {_number(end_y)}"
    )


def _circular_midpoint(feature: PublicationMapFeature, length: int) -> float:
    weighted_x = 0.0
    weighted_y = 0.0
    for part in feature.parts:
        interval = part.authoritative
        span = interval.end - interval.start
        angle = -math.pi / 2 + (((interval.start + interval.end) / 2) / length) * 2 * math.pi
        weighted_x += math.cos(angle) * span
        weighted_y += math.sin(angle) * span
    angle = math.atan2(weighted_y, weighted_x)
    return ((angle + math.pi / 2) % (2 * math.pi)) / (2 * math.pi) * length


def _circular_overlap_span(
    left: PublicationMapFeature,
    right: PublicationMapFeature,
) -> int:
    return sum(
        max(
            0,
            min(left_part.authoritative.end, right_part.authoritative.end)
            - max(left_part.authoritative.start, right_part.authoritative.start),
        )
        for left_part in left.parts
        for right_part in right.parts
    )


def _circular_feature_lanes(
    features: tuple[PublicationMapFeature, ...],
) -> dict[str, int]:
    """Assign the lowest deterministic lane that avoids coordinate overlap."""

    ordered = sorted(
        features,
        key=lambda feature: (
            0 if _circular_priority(feature) == "key" else 1 if _circular_priority(feature) == "secondary" else 2,
            min(part.authoritative.start for part in feature.parts),
            max(part.authoritative.end for part in feature.parts),
            feature.feature_id,
        ),
    )
    lane_features: list[list[PublicationMapFeature]] = [[]]
    assignments: dict[str, int] = {}
    for feature in ordered:
        lane = next(
            (
                index
                for index, assigned in enumerate(lane_features)
                if all(_circular_overlap_span(feature, other) == 0 for other in assigned)
            ),
            None,
        )
        if lane is None and len(lane_features) < _CIRCULAR_MAX_FEATURE_LANES:
            lane = len(lane_features)
            lane_features.append([])
        if lane is None:
            # Extremely dense synthetic or imported annotations can require
            # more rings than the publication canvas can support. Reuse the
            # least-conflicting bounded lane deterministically instead of
            # turning the figure into an unbounded multi-ring diagram.
            lane = min(
                range(len(lane_features)),
                key=lambda index: (
                    sum(_circular_overlap_span(feature, other) for other in lane_features[index]),
                    len(lane_features[index]),
                    index,
                ),
            )
        assignments[feature.feature_id] = lane
        lane_features[lane].append(feature)
    return assignments


def _circular_arrow(
    cx: float,
    cy: float,
    radius: float,
    coordinate: int,
    strand: int,
    length: int,
    terminal_start: int,
    terminal_end: int,
    stroke_width: float,
) -> _CircularArrow | None:
    # Derive both dimensions only from the available arc, and place the tip at
    # the strand terminal so the full tangential arrow interval remains inside
    # the feature geometry. Suppress arcs too short for a legible arrow rather
    # than applying a pixel floor that fabricates an oversized direction cue.
    terminal_span = terminal_end - terminal_start
    arc_length = 2 * math.pi * radius * terminal_span / length
    if arc_length < _CIRCULAR_ARROW_MIN_VISIBLE_ARC:
        return None
    arrow_length = min(
        _CIRCULAR_ARROW_MAX_LENGTH,
        arc_length * _CIRCULAR_ARROW_LENGTH_FRACTION,
    )
    arrow_half_width = min(stroke_width / 2, arrow_length * 0.75)
    coordinate_delta = arrow_length * length / (2 * math.pi * radius)
    base_coordinate = coordinate - strand * coordinate_delta
    if strand == 1:
        base_coordinate = max(float(terminal_start), min(float(coordinate), base_coordinate))
    else:
        base_coordinate = min(float(terminal_end), max(float(coordinate), base_coordinate))
    tip_x, tip_y = _polar(cx, cy, radius, coordinate, length)
    base_x, base_y = _polar(cx, cy, radius, base_coordinate, length)
    base_angle = -math.pi / 2 + (base_coordinate / length) * 2 * math.pi
    radial_x, radial_y = math.cos(base_angle), math.sin(base_angle)
    points = (
        (tip_x, tip_y),
        (base_x + arrow_half_width * radial_x, base_y + arrow_half_width * radial_y),
        (base_x - arrow_half_width * radial_x, base_y - arrow_half_width * radial_y),
    )
    return _CircularArrow(
        points=" ".join(f"{_number(x)},{_number(y)}" for x, y in points),
        base_coordinate=base_coordinate,
    )


def _direction_coordinate(feature: PublicationMapFeature, length: int) -> int:
    if feature.wraps_origin:
        if feature.strand == 1:
            return max(
                part.authoritative.end
                for part in feature.parts
                if part.authoritative.start == 0
            )
        return min(
            part.authoritative.start
            for part in feature.parts
            if part.authoritative.end == length
        )
    if feature.strand == 1:
        return max(part.authoritative.end for part in feature.parts)
    return min(part.authoritative.start for part in feature.parts)


def _terminal_part_for_direction_coordinate(
    feature: PublicationMapFeature,
    coordinate: int,
) -> PublicationMapLocationPart:
    """Return the part whose directional boundary is the authoritative tip."""

    if feature.strand == 1:
        matches = [part for part in feature.parts if part.authoritative.end == coordinate]
    else:
        matches = [part for part in feature.parts if part.authoritative.start == coordinate]
    if len(matches) != 1:
        raise PublicationMapContractError(
            "direction_coordinate must identify exactly one terminal feature part."
        )
    return matches[0]


def _spread_labels(labels: list[_Label], top: float, bottom: float, gap: float) -> list[_Label]:
    if not labels:
        return []
    ordered = sorted(labels, key=lambda item: (item.desired_y, item.feature.feature_id))
    if (len(ordered) - 1) * gap > bottom - top:
        raise PublicationMapContractError(
            "label_capacity_exceeded: Circular label density exceeds the supported collision-free rail capacity."
        )
    positions: list[float] = []
    for index, label in enumerate(ordered):
        positions.append(max(label.desired_y, top if index == 0 else positions[-1] + gap))
    overflow = positions[-1] - bottom
    if overflow > 0:
        positions = [position - overflow for position in positions]
    if positions[0] < top:
        shift = top - positions[0]
        positions = [position + shift for position in positions]
    return [
        _Label(label.feature, label.anchor_x, label.anchor_y, positions[index], label.side)
        for index, label in enumerate(ordered)
    ]


def _legend(
    document: PublicationMapDocument,
    width: int,
    y: float,
    *,
    max_rows: int = 2,
) -> list[str]:
    categories = {feature.display_category for feature in document.features}
    ordered = [category for category in _ROLE_ORDER if category in categories]
    ordered.extend(sorted(categories.difference(_ROLE_ORDER)))
    if not ordered:
        return []
    columns = min(6, math.ceil(len(ordered) / max_rows))
    rows = math.ceil(len(ordered) / columns)
    cell_width = (width - 100) / columns
    elements = [
        (
            f'<g id="map-legend" data-bounds="50,{_number(y - 18)},{width - 50},'
            f'{_number(y + rows * 28 + 6)}">'
        )
    ]
    for index, category in enumerate(ordered):
        row = index // columns
        column = index % columns
        x = 50 + column * cell_width
        item_y = y + row * 28
        label, color = _style(category)
        fitted = _fit_text(label, max(24.0, cell_width - 31.0), 11.0)
        elements.append(
            f'<rect x="{_number(x)}" y="{_number(item_y - 10)}" width="18" height="10" '
            f'rx="2" fill="{color}" stroke="#28323B" stroke-width="0.6"/>'
        )
        elements.append(
            f'<text class="legend-label" data-category="{_attribute(category)}" '
            f'data-layout-bounds="{_label_bounds_attribute(x + 25, item_y, fitted.estimated_width, "start")}" '
            f'x="{_number(x + 25)}" y="{_number(item_y)}">'
            f"{_text(fitted.visible)}<title>{_text(label)}</title></text>"
        )
    elements.append("</g>")
    return elements


def _render_circular(
    document: PublicationMapDocument,
    options: PublicationMapRenderOptions,
    width: int,
    height: int,
) -> str:
    elements = _svg_header(document, width, height)
    cx = width / 2
    cy = (height - (125 if options.show_legend else 30)) / 2 + 20
    # The circular construct is the primary visual. Keep the centre clear for
    # identity metadata while using most of the available canvas.
    radius = min(330.0, width * 0.28, height * 0.34)
    feature_radius = radius + _CIRCULAR_FEATURE_RADIUS_OFFSET
    title = _fit_text(document.display_name, max(80.0, radius * 1.55), 20.0)
    elements.append(
        f'<circle class="backbone" cx="{_number(cx)}" cy="{_number(cy)}" r="{_number(radius)}" '
        f'stroke-width="{_number(_CIRCULAR_BACKBONE_STROKE)}" stroke-opacity="1" '
        'vector-effect="non-scaling-stroke"/>'
    )

    labels: list[_Label] = []
    side_counts = {"left": 0, "right": 0}
    drawable_features = tuple(
        feature
        for feature in document.features
        if not _is_full_length_source_metadata(feature, document.sequence_length)
    )
    feature_lanes = _circular_feature_lanes(drawable_features)
    lane_step = max(_CIRCULAR_KEY_FEATURE_STROKE, _CIRCULAR_SECONDARY_FEATURE_STROKE) + _CIRCULAR_FEATURE_LANE_GAP
    for index, feature in enumerate(drawable_features, start=1):
        role_label, color = _style(feature.display_category)
        direction = "forward" if feature.strand == 1 else "reverse" if feature.strand == -1 else "neutral"
        priority = _circular_priority(feature)
        stroke_width = {
            "key": _CIRCULAR_KEY_FEATURE_STROKE,
            "secondary": _CIRCULAR_SECONDARY_FEATURE_STROKE,
            "context": _CIRCULAR_CONTEXT_FEATURE_STROKE,
        }[priority]
        lane = feature_lanes[feature.feature_id]
        lane_radius = feature_radius + lane * lane_step
        coordinate: int | None = None
        arrow_geometry: _CircularArrow | None = None
        if feature.strand is not None and priority != "context":
            coordinate = _direction_coordinate(feature, document.sequence_length)
            terminal_part = _terminal_part_for_direction_coordinate(feature, coordinate)
            arrow_geometry = _circular_arrow(
                cx,
                cy,
                lane_radius,
                coordinate,
                feature.strand,
                document.sequence_length,
                terminal_part.authoritative.start,
                terminal_part.authoritative.end,
                stroke_width,
            )
        elements.append(
            f'<g id="feature-{index:03d}" class="map-feature" data-feature-id="{_attribute(feature.feature_id)}" '
            f'data-category="{_attribute(feature.display_category)}" data-style-role="{_attribute(role_label)}" '
            f'data-direction="{direction}" data-priority="{priority}" data-lane="{lane}" '
            f'data-radius="{_number(lane_radius)}" data-wraps-origin="{str(feature.wraps_origin).lower()}">'
        )
        elements.append(f"<title>{_text(feature.display_label)}</title>")
        dash = ' stroke-dasharray="5 3"' if feature.strand is None else ""
        for part_index, part in enumerate(feature.parts, start=1):
            interval = part.authoritative
            render_start = float(interval.start)
            render_end = float(interval.end)
            terminal_part = False
            if arrow_geometry is not None and coordinate is not None:
                if feature.strand == 1 and interval.end == coordinate:
                    render_end = arrow_geometry.base_coordinate
                    terminal_part = True
                elif feature.strand == -1 and interval.start == coordinate:
                    render_start = arrow_geometry.base_coordinate
                    terminal_part = True
            elements.append(
                f'<path class="feature-arc" data-part="{part_index}" data-lane="{lane}" '
                f'data-terminal-part="{str(terminal_part).lower()}" '
                f'data-radius="{_number(lane_radius)}" '
                f'd="{_arc_path(cx, cy, lane_radius, render_start, render_end, document.sequence_length)}" '
                f'fill="none" stroke="{color}" stroke-width="{_number(stroke_width)}" stroke-opacity="1" '
                f'opacity="{"1" if priority == "key" else "0.55" if priority == "context" else "0.82"}" vector-effect="non-scaling-stroke" '
                f'stroke-linecap="{"butt" if terminal_part else "round"}"{dash}/>'
            )
        if arrow_geometry is not None and coordinate is not None:
            elements.append(
                f'<polygon class="direction-arrow" data-coordinate="{coordinate}" '
                f'data-base-coordinate="{_number(arrow_geometry.base_coordinate)}" data-integrated="true" '
                f'data-terminal-part="true" data-lane="{lane}" points="{arrow_geometry.points}" fill="{color}" stroke="none" '
                f'opacity="{"1" if priority == "key" else "0.55" if priority == "context" else "0.82"}"/>'
            )
        elements.append("</g>")

        if options.show_labels:
            midpoint = _circular_midpoint(feature, document.sequence_length)
            # Anchor leaders on the outer edge of the feature band so the
            # feature-to-label relationship remains unambiguous.
            anchor_radius = lane_radius + stroke_width / 2 + 0.75
            anchor_x, anchor_y = _polar(cx, cy, anchor_radius, midpoint, document.sequence_length)
            radial_x = (anchor_x - cx) / anchor_radius
            if abs(radial_x) < 0.22:
                side = "left" if side_counts["left"] <= side_counts["right"] else "right"
            else:
                side = "right" if radial_x > 0 else "left"
            side_counts[side] += 1
            labels.append(_Label(feature, anchor_x, anchor_y, anchor_y, side))

    desired_y_values = [label.desired_y for label in labels]
    if (
        len(labels) > _CIRCULAR_LABEL_CAPACITY
        and desired_y_values
        and max(desired_y_values) - min(desired_y_values) < 34
    ):
        raise PublicationMapContractError(
            "label_capacity_exceeded: Circular label density exceeds the supported collision-free rail capacity."
        )

    for side in ("left", "right"):
        side_labels = _spread_labels(
            [label for label in labels if label.side == side],
            78,
            height - (185 if options.show_legend else 65),
            34.5,
        )
        # Keep labels just outside the enlarged plasmid. This leaves a usable
        # rail on both sides instead of collapsing the left rail to a few px.
        text_x = cx - radius - 18 if side == "left" else cx + radius + 18
        anchor = "end" if side == "left" else "start"
        line_end_x = text_x + (8 if side == "left" else -8)
        for label_index, label in enumerate(side_labels):
            y = label.desired_y
            max_width = text_x - _CANVAS_MARGIN if side == "left" else width - _CANVAS_MARGIN - text_x
            fitted, compressed = _fit_circular_label(label.feature.display_label, max_width)
            baseline_y = y - 3
            elbow_ratio = 0.56 + (label_index % 3) * 0.08
            elbow_x = label.anchor_x + (line_end_x - label.anchor_x) * elbow_ratio
            elements.append(
                f'<path class="leader" data-leader-for="{_attribute(label.feature.feature_id)}" '
                f'd="M {_number(label.anchor_x)} {_number(label.anchor_y)} '
                f'L {_number(elbow_x)} {_number(y)} L {_number(line_end_x)} {_number(y)}" '
                'stroke="#929CA5" stroke-width="0.85" vector-effect="non-scaling-stroke"/>'
            )
            text_sizing = (
                f' textLength="{_number(max_width)}" lengthAdjust="spacingAndGlyphs"'
                if compressed
                else ""
            )
            elements.append(
                f'<text class="feature-label" data-label-for="{_attribute(label.feature.feature_id)}" '
                f'data-label-x="{_number(text_x)}" data-label-y="{_number(y - 3)}" '
                f'data-layout-bounds="{_label_bounds_attribute(text_x, baseline_y, fitted.estimated_width, anchor)}" '
                f'x="{_number(text_x)}" y="{_number(y - 3)}" text-anchor="{anchor}"{text_sizing}>'
                f"{_text(fitted.visible)}<title>{_text(label.feature.display_label)}</title></text>"
            )
            elements.append(
                f'<text class="coordinate-label" x="{_number(text_x)}" y="{_number(y + 11)}" text-anchor="{anchor}">'
                f"{_text(_display_coordinate(label.feature))}</text>"
            )

    tick_radius = radius - 18
    for fraction in (0, 0.25, 0.5, 0.75):
        coordinate = round(document.sequence_length * fraction)
        inner = _polar(cx, cy, tick_radius - 5, coordinate, document.sequence_length)
        outer = _polar(cx, cy, tick_radius + 4, coordinate, document.sequence_length)
        elements.append(
            f'<line x1="{_number(inner[0])}" y1="{_number(inner[1])}" x2="{_number(outer[0])}" y2="{_number(outer[1])}" stroke="#68737D" stroke-width="1"/>'
        )
    elements.extend(
        [
            f'<text class="map-title" data-layout-bounds="{_label_bounds_attribute(cx, cy - 13, title.estimated_width, "middle", ascent=20, descent=6)}" '
            f'x="{_number(cx)}" y="{_number(cy - 13)}" text-anchor="middle">'
            f'{_text(title.visible)}<title>{_text(document.display_name)}</title></text>',
            f'<text class="map-title" x="{_number(cx)}" y="{_number(cy + 17)}" text-anchor="middle">{document.sequence_length:,} bp</text>',
            f'<text class="map-subtitle" x="{_number(cx)}" y="{_number(cy + 42)}" text-anchor="middle">COMPLETE CIRCULAR PLASMID</text>',
            f'<text class="scale-label" x="{_number(cx)}" y="{_number(cy - radius - 34)}" text-anchor="middle">0 bp</text>',
        ]
    )
    if options.show_legend:
        elements.extend(_legend(document, width, height - 78))
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def _linear_feature_points(x1: float, x2: float, y: float, strand: int | None) -> str:
    height = 26.0
    if strand is None:
        return ""
    arrow = min(14.0, max(4.0, (x2 - x1) * 0.45))
    if strand == 1:
        points = ((x1, y - height / 2), (x2 - arrow, y - height / 2), (x2, y), (x2 - arrow, y + height / 2), (x1, y + height / 2))
    else:
        points = ((x1, y), (x1 + arrow, y - height / 2), (x2, y - height / 2), (x2, y + height / 2), (x1 + arrow, y + height / 2))
    return " ".join(f"{_number(x)},{_number(point_y)}" for x, point_y in points)


def _assign_linear_label_layers(
    features: Iterable[tuple[PublicationMapFeature, float]],
    width: int,
    height: int,
    show_legend: bool,
) -> dict[str, _LinearLabelLayout]:
    baselines = [236.0, 193.0, 150.0, 107.0]
    below_limit = height - (120.0 if show_legend else 35.0)
    baselines.extend(
        baseline
        for baseline in (425.0, 468.0, 511.0, 554.0, 597.0)
        if baseline <= below_limit
    )
    layer_ends = [-math.inf] * len(baselines)
    assignments: dict[str, _LinearLabelLayout] = {}
    occupied: list[tuple[float, float, float, float]] = []
    overflow: list[tuple[PublicationMapFeature, float]] = []
    for feature, center_x in sorted(features, key=lambda item: (item[1], item[0].feature_id)):
        fitted = _fit_text(feature.display_label, min(260.0, width - 2 * _CANVAS_MARGIN), _FEATURE_LABEL_FONT_SIZE)
        label_width = max(70.0, fitted.estimated_width)
        label_x = min(
            width - _CANVAS_MARGIN - label_width / 2,
            max(_CANVAS_MARGIN + label_width / 2, center_x),
        )
        left = label_x - label_width / 2
        right = label_x + label_width / 2
        layer = next((index for index, end in enumerate(layer_ends) if left >= end + 10), None)
        if layer is None:
            overflow.append((feature, center_x))
            continue
        baseline_y = baselines[layer]
        assignments[feature.feature_id] = _LinearLabelLayout(
            baseline_y,
            label_x,
            fitted,
            baseline_y < 310.0,
        )
        layer_ends[layer] = max(layer_ends[layer], right)
        occupied.append((left, baseline_y - _FEATURE_LABEL_ASCENT, right, baseline_y + 19.0))

    if not overflow:
        return assignments

    # Exhausted inline layers spill into bounded side rails with owned leaders.
    rail_width = min(260.0, (width - 2 * _CANVAS_MARGIN - 320.0) / 2)
    if rail_width <= 0:
        raise PublicationMapContractError(
            "Linear label density exceeds the supported collision-free canvas capacity."
        )
    rail_x = {
        "left": _CANVAS_MARGIN + rail_width,
        "right": width - _CANVAS_MARGIN - rail_width,
    }
    top_baselines = []
    baseline = 92.0
    while baseline <= 264.0:
        top_baselines.append(baseline)
        baseline += 34.0
    bottom_limit = height - (115.0 if show_legend else 30.0)
    bottom_baselines = []
    baseline = 420.0
    while baseline <= bottom_limit:
        bottom_baselines.append(baseline)
        baseline += 34.0
    rail_slots = [
        (side, baseline_y)
        for baseline_y in (*reversed(top_baselines), *bottom_baselines)
        for side in ("left", "right")
    ]

    def overlaps(candidate: tuple[float, float, float, float]) -> bool:
        left, top, right, bottom = candidate
        return any(
            not (right + 4.0 <= other_left or other_right + 4.0 <= left or bottom + 3.0 <= other_top or other_bottom + 3.0 <= top)
            for other_left, other_top, other_right, other_bottom in occupied
        )

    for feature, center_x in overflow:
        fitted = _fit_text(feature.display_label, rail_width, _FEATURE_LABEL_FONT_SIZE)
        coordinate_width = _estimated_text_width(_display_coordinate(feature), 10.0)
        content_width = max(fitted.estimated_width, coordinate_width)
        preferred_side = "left" if center_x < width / 2 else "right"
        available = sorted(
            rail_slots,
            key=lambda slot: (
                abs(slot[1] - 310.0),
                slot[0] != preferred_side,
                slot[1],
                slot[0],
            ),
        )
        selected: tuple[str, float, tuple[float, float, float, float]] | None = None
        for side, baseline_y in available:
            text_x = rail_x[side]
            if side == "left":
                bounds = (text_x - content_width, baseline_y - _FEATURE_LABEL_ASCENT, text_x, baseline_y + 19.0)
            else:
                bounds = (text_x, baseline_y - _FEATURE_LABEL_ASCENT, text_x + content_width, baseline_y + 19.0)
            if not overlaps(bounds):
                selected = side, baseline_y, bounds
                break
        if selected is None:
            raise PublicationMapContractError(
                "Linear label density exceeds the supported collision-free canvas capacity."
            )
        side, baseline_y, bounds = selected
        assignments[feature.feature_id] = _LinearLabelLayout(
            baseline_y,
            rail_x[side],
            fitted,
            baseline_y < 310.0,
            "end" if side == "left" else "start",
            side,
        )
        occupied.append(bounds)
        rail_slots.remove((side, baseline_y))
    return assignments


def _render_linear(
    document: PublicationMapDocument,
    options: PublicationMapRenderOptions,
    width: int,
    height: int,
) -> str:
    elements = _svg_header(document, width, height)
    left = 86.0
    right = width - 86.0
    span = right - left
    backbone_y = 310.0
    title = _fit_text(document.display_name, width - left - _CANVAS_MARGIN, 20.0)

    def project(coordinate: float) -> float:
        return left + (coordinate / document.sequence_length) * span

    elements.extend(
        [
            f'<text class="map-title" data-layout-bounds="{_label_bounds_attribute(left, 42, title.estimated_width, "start", ascent=20, descent=6)}" '
            f'x="{_number(left)}" y="42">{_text(title.visible)}<title>{_text(document.display_name)}</title></text>',
            f'<text class="map-subtitle" x="{_number(left)}" y="64">{"COMPLETE PLASMID (LINEAR VIEW)" if document.view.view_type is PublicationMapViewType.COMPLETE_LINEAR_PLASMID else "ACTIVE EXPRESSION CONSTRUCT"} | {document.sequence_length:,} bp</text>',
            f'<line class="backbone" x1="{_number(left)}" y1="{_number(backbone_y)}" x2="{_number(right)}" y2="{_number(backbone_y)}" stroke-width="5"/>',
            f'<line x1="{_number(left)}" y1="{_number(backbone_y - 15)}" x2="{_number(left)}" y2="{_number(backbone_y + 15)}" stroke="#17212B" stroke-width="2"/>',
            f'<line x1="{_number(right)}" y1="{_number(backbone_y - 15)}" x2="{_number(right)}" y2="{_number(backbone_y + 15)}" stroke="#17212B" stroke-width="2"/>',
        ]
    )

    projected_centers: list[tuple[PublicationMapFeature, float]] = []
    for feature in document.features:
        weighted_sum = sum(
            ((part.authoritative.start + part.authoritative.end) / 2) * part.authoritative.length
            for part in feature.parts
        )
        total_length = sum(part.authoritative.length for part in feature.parts)
        projected_centers.append((feature, project(weighted_sum / total_length)))
    label_layers = (
        _assign_linear_label_layers(
            projected_centers,
            width,
            height,
            options.show_legend,
        )
        if options.show_labels
        else {}
    )

    unit_groups: dict[str, list[tuple[PublicationMapFeature, float]]] = {}
    for feature, center_x in projected_centers:
        provenance = dict(feature.provenance)
        unit_id = str(provenance.get("unit_id") or "").strip()
        unit_order = str(provenance.get("unit_order") or "").strip()
        group_key = unit_id or (f"order:{unit_order}" if unit_order else "")
        if group_key:
            unit_groups.setdefault(group_key, []).append((feature, center_x))
    if len(unit_groups) > 1:
        group_elements = ['<g id="tu-groups" class="tu-groups" aria-label="Transcription unit groups">']
        for group_index, (group_key, members) in enumerate(
            sorted(unit_groups.items(), key=lambda item: (min(x for _, x in item[1]), item[0])),
            start=1,
        ):
            group_left = min(project(item[0].authoritative.start) for item in members)
            group_right = max(project(item[0].authoritative.end) for item in members)
            label = f"TU {group_index}"
            group_elements.extend(
                [
                    f'<path class="tu-band" data-unit-group="{_attribute(group_key)}" d="M {_number(group_left)} 278 V 286 H {_number(group_right)} V 278"/>',
                    f'<text class="tu-label" data-unit-group="{_attribute(group_key)}" x="{_number((group_left + group_right) / 2)}" y="270" text-anchor="middle">{label}</text>',
                ]
            )
        group_elements.append("</g>")
        elements.extend(group_elements)

    for index, (feature, center_x) in enumerate(projected_centers, start=1):
        role_label, color = _style(feature.display_category)
        direction = "forward" if feature.strand == 1 else "reverse" if feature.strand == -1 else "neutral"
        feature_y = backbone_y
        elements.append(
            f'<g id="feature-{index:03d}" class="map-feature" data-feature-id="{_attribute(feature.feature_id)}" '
            f'data-category="{_attribute(feature.display_category)}" data-style-role="{_attribute(role_label)}" '
            f'data-direction="{direction}" data-wraps-origin="false">'
        )
        elements.append(f"<title>{_text(feature.display_label)}</title>")
        for part_index, part in enumerate(feature.parts, start=1):
            x1 = project(part.authoritative.start)
            x2 = project(part.authoritative.end)
            if feature.strand is None:
                elements.append(
                    f'<rect class="feature-block neutral" data-part="{part_index}" x="{_number(x1)}" y="{_number(feature_y - 13)}" '
                    f'width="{_number(max(1.0, x2 - x1))}" height="26" rx="3" fill="{color}" stroke="#FFFFFF" '
                    'stroke-width="1" stroke-dasharray="5 3"/>'
                )
            else:
                elements.append(
                    f'<polygon class="feature-block direction-arrow" data-part="{part_index}" '
                    f'points="{_linear_feature_points(x1, x2, feature_y, feature.strand)}" fill="{color}" '
                    'stroke="#FFFFFF" stroke-width="1"/>'
                )
        elements.append("</g>")

        if options.show_labels:
            layout = label_layers[feature.feature_id]
            label_y = layout.baseline_y
            label_x = layout.x
            leader_start_y = feature_y - 16 if layout.above_track else feature_y + 16
            leader_end_y = label_y + 8 if layout.above_track else label_y - 14
            if layout.overflow_side is None:
                elements.append(
                    f'<path class="leader" d="M {_number(center_x)} {_number(leader_start_y)} L {_number(label_x)} {_number(leader_end_y)}"/>'
                )
                elements.append(
                    f'<text class="feature-label" data-label-for="{_attribute(feature.feature_id)}" '
                    f'data-label-x="{_number(label_x)}" data-label-y="{_number(label_y)}" '
                    f'data-layout-bounds="{_label_bounds_attribute(label_x, label_y, layout.fitted.estimated_width, "middle")}" '
                    f'x="{_number(label_x)}" y="{_number(label_y)}" text-anchor="middle">'
                    f"{_text(layout.fitted.visible)}<title>{_text(feature.display_label)}</title></text>"
                )
            else:
                inner_direction = 1.0 if layout.overflow_side == "left" else -1.0
                leader_end_x = label_x + 8.0 * inner_direction
                elbow_x = label_x + 32.0 * inner_direction
                elements.append(
                    f'<path class="leader overflow-leader" data-leader-for="{_attribute(feature.feature_id)}" '
                    f'd="M {_number(center_x)} {_number(leader_start_y)} L {_number(elbow_x)} {_number(leader_end_y)} '
                    f'L {_number(leader_end_x)} {_number(leader_end_y)}"/>'
                )
                elements.append(
                    f'<text class="feature-label overflow-label" data-label-for="{_attribute(feature.feature_id)}" '
                    f'data-label-layout="overflow-{layout.overflow_side}" '
                    f'data-label-x="{_number(label_x)}" data-label-y="{_number(label_y)}" '
                    f'data-layout-bounds="{_label_bounds_attribute(label_x, label_y, layout.fitted.estimated_width, layout.anchor)}" '
                    f'x="{_number(label_x)}" y="{_number(label_y)}" text-anchor="{layout.anchor}">'
                    f"{_text(layout.fitted.visible)}<title>{_text(feature.display_label)}</title></text>"
                )
            elements.append(
                f'<text class="coordinate-label" x="{_number(label_x)}" y="{_number(label_y + 15)}" text-anchor="{layout.anchor}">'
                f"{_text(_display_coordinate(feature))}</text>"
            )

    tick_count = 5
    for index in range(tick_count + 1):
        coordinate = round(document.sequence_length * index / tick_count)
        x = project(coordinate)
        elements.append(
            f'<line class="coordinate-tick" data-coordinate="{coordinate}" x1="{_number(x)}" y1="{_number(backbone_y + 28)}" x2="{_number(x)}" y2="{_number(backbone_y + 37)}" stroke="#68737D" stroke-width="1"/>'
        )
        elements.append(
            f'<text class="scale-label" data-coordinate="{coordinate}" x="{_number(x)}" y="{_number(backbone_y + 53)}" text-anchor="middle">{coordinate:,}</text>'
        )
    elements.append(
        f'<text class="scale-label" x="{_number((left + right) / 2)}" y="{_number(backbone_y + 74)}" text-anchor="middle">Position (bp)</text>'
    )
    if options.show_legend:
        elements.extend(_legend(document, width, height - 70))
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def render_publication_map_svg(
    document: PublicationMapDocument,
    options: PublicationMapRenderOptions | None = None,
) -> str:
    """Render a validated frozen Publication Map V1 document as deterministic SVG."""

    _validate_document(document)
    validated_options, width, height = _validate_options(document, options)
    if document.topology is PublicationMapTopology.CIRCULAR:
        svg = _render_circular(document, validated_options, width, height)
    else:
        svg = _render_linear(document, validated_options, width, height)
    return svg


def publication_map_svg_digest(svg: str) -> str:
    """Return a stable SHA-256 digest for renderer regression records."""

    if not isinstance(svg, str) or not svg.startswith('<?xml version="1.0"'):
        raise PublicationMapContractError("SVG digest input must be renderer SVG text.")
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()
