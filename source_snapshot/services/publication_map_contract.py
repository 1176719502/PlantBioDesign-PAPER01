from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


PUBLICATION_MAP_SCHEMA_VERSION = "bds.publication_map.v1"
PUBLICATION_MAP_REVISION_PROVENANCE_FIELD = "runtime_revision_id"
AUTHORITATIVE_COORDINATE_CONVENTION = "0-based-half-open"
DISPLAY_COORDINATE_CONVENTION = "1-based-inclusive"


class PublicationMapContractError(ValueError):
    """Raised when authoritative data violates the publication-map contract."""


class PublicationMapTopology(str, Enum):
    CIRCULAR = "circular"
    LINEAR = "linear"


class PublicationMapViewType(str, Enum):
    COMPLETE_CIRCULAR_PLASMID = "complete_circular_plasmid"
    COMPLETE_LINEAR_PLASMID = "complete_linear_plasmid"
    LINEAR_ACTIVE_EXPRESSION_CONSTRUCT = "linear_active_expression_construct"


class FeatureClassificationState(str, Enum):
    AUTHORITATIVE = "authoritative"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class PublicationMapInterval:
    """A zero-based, half-open interval copied from authoritative runtime data."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class PublicationMapDisplayInterval:
    """A one-based, end-inclusive coordinate pair intended only for display."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class PublicationMapLocationPart:
    authoritative: PublicationMapInterval
    display: PublicationMapDisplayInterval
    strand: int | None


def publication_map_wraps_origin(
    parts: tuple[PublicationMapLocationPart, ...],
    topology: PublicationMapTopology,
    sequence_length: int,
) -> bool:
    """Validate compound-part boundaries and return the V1 origin-wrap state."""

    coordinates = tuple(
        (part.authoritative.start, part.authoritative.end) for part in parts
    )
    if len(set(coordinates)) != len(coordinates):
        raise PublicationMapContractError(
            "Publication map compound location parts must be coordinate-distinct."
        )
    if len(coordinates) > 1 and (0, sequence_length) in coordinates:
        raise PublicationMapContractError(
            "Publication map compound locations cannot contain a full-sequence part."
        )
    if topology is not PublicationMapTopology.CIRCULAR or len(parts) < 2:
        return False

    origin_part_indexes = {
        index for index, part in enumerate(parts) if part.authoritative.start == 0
    }
    terminus_part_indexes = {
        index
        for index, part in enumerate(parts)
        if part.authoritative.end == sequence_length
    }
    return any(
        origin_index != terminus_index
        for origin_index in origin_part_indexes
        for terminus_index in terminus_part_indexes
    )


QualifierItems = tuple[tuple[str, tuple[str, ...]], ...]
ProvenanceItems = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PublicationMapFeature:
    feature_id: str
    authoritative: PublicationMapInterval
    display: PublicationMapDisplayInterval
    strand: int | None
    parts: tuple[PublicationMapLocationPart, ...]
    location_operator: str | None
    wraps_origin: bool
    authoritative_type: str | None
    component_type: str | None
    biological_role: str | None
    regulatory_class: str | None
    display_label: str
    qualifiers: QualifierItems
    provenance: ProvenanceItems
    classification_state: FeatureClassificationState
    display_category: str


@dataclass(frozen=True, slots=True)
class PublicationMapViewDefinition:
    view_type: PublicationMapViewType
    topology: PublicationMapTopology
    authoritative_region: PublicationMapInterval
    display_region: PublicationMapDisplayInterval


@dataclass(frozen=True, slots=True)
class PublicationMapDocument:
    schema_version: str
    construct_identifier: str
    display_name: str
    sequence_length: int
    topology: PublicationMapTopology
    sequence_checksum: str
    checksum_algorithm: str
    features: tuple[PublicationMapFeature, ...]
    provenance: ProvenanceItems
    view: PublicationMapViewDefinition
