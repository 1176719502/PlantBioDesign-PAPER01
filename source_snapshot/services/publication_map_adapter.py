from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from services.publication_map_contract import (
    AUTHORITATIVE_COORDINATE_CONVENTION,
    DISPLAY_COORDINATE_CONVENTION,
    PUBLICATION_MAP_REVISION_PROVENANCE_FIELD,
    PUBLICATION_MAP_SCHEMA_VERSION,
    FeatureClassificationState,
    PublicationMapContractError,
    PublicationMapDisplayInterval,
    PublicationMapDocument,
    PublicationMapFeature,
    PublicationMapInterval,
    PublicationMapLocationPart,
    PublicationMapTopology,
    PublicationMapViewDefinition,
    PublicationMapViewType,
    publication_map_wraps_origin,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DISPLAY_CATEGORIES = {
    "promoter": "promoter",
    "five_prime_region": "five_prime_region",
    "five_prime_utr": "five_prime_region",
    "enhancer": "enhancer",
    "cds": "cds",
    "terminator": "terminator",
    "selectable_marker": "selectable_marker",
    "marker": "selectable_marker",
    "rep_origin": "origin",
    "origin": "origin",
    "left_border": "left_border",
    "lb": "left_border",
    "right_border": "right_border",
    "rb": "right_border",
    "insertion_region": "insertion_region",
    "replacement_region": "replacement_region",
}
_FEATURE_PROVENANCE_FIELDS = (
    "component_id",
    "source_asset_id",
    "backbone_feature_id",
    "source",
    "unit_id",
    "unit_order",
)


@dataclass(frozen=True, slots=True)
class AuthoritativePublicationMapSource:
    construct_identifier: str
    display_name: str
    sequence_length: int
    topology: str
    sequence_checksum: str
    features: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]
    view_type: PublicationMapViewType
    sequence: str | None = None


@dataclass(frozen=True, slots=True)
class _CanonicalPublicationProjection:
    construct_identifier: str
    sequence: str
    sequence_checksum: str
    revision_id: str
    topology: str
    features: tuple[Mapping[str, Any], ...]
    runtime_schema_version: str


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise PublicationMapContractError(f"{field_name} must be an integer, not boolean.")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicationMapContractError(f"{field_name} must be an integer.") from exc
    if isinstance(value, float) and not value.is_integer():
        raise PublicationMapContractError(f"{field_name} must be an integer.")
    return converted


def _strand(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    converted = _integer(value, field_name)
    if converted == 0:
        return None
    if converted not in {-1, 1}:
        raise PublicationMapContractError(
            f"{field_name} must be +1, -1, None, or legacy 0."
        )
    return converted


def _interval(start: Any, end: Any, sequence_length: int, field_name: str) -> PublicationMapInterval:
    start_value = _integer(start, f"{field_name}.start")
    end_value = _integer(end, f"{field_name}.end")
    if start_value < 0 or end_value < 0:
        raise PublicationMapContractError(f"{field_name} cannot contain negative coordinates.")
    if end_value <= start_value:
        raise PublicationMapContractError(
            f"{field_name} must be non-empty and use start < end; circular wraparound requires explicit parts."
        )
    if end_value > sequence_length:
        raise PublicationMapContractError(
            f"{field_name} exceeds the authoritative sequence length; clipping is forbidden."
        )
    return PublicationMapInterval(start=start_value, end=end_value)


def _display(interval: PublicationMapInterval) -> PublicationMapDisplayInterval:
    return PublicationMapDisplayInterval(start=interval.start + 1, end=interval.end)


def _qualifiers(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise PublicationMapContractError("feature.qualifiers must be a mapping.")
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for raw_key, raw_values in value.items():
        key = _text(raw_key)
        if not key:
            raise PublicationMapContractError("Qualifier keys cannot be empty.")
        values = raw_values if isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)) else [raw_values]
        normalized.append((key, tuple(str(item) for item in values)))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _provenance(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise PublicationMapContractError("provenance must be a mapping.")
    return tuple(
        sorted(
            ((_text(key), _text(item)) for key, item in value.items() if _text(key) and _text(item)),
            key=lambda item: item[0],
        )
    )


def _feature_provenance(feature: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    supplied = dict(_provenance(feature.get("provenance")))
    for field_name in _FEATURE_PROVENANCE_FIELDS:
        value = _text(feature.get(field_name))
        if value:
            supplied[field_name] = value
    return tuple(sorted(supplied.items(), key=lambda item: item[0]))


def _feature_label(feature: Mapping[str, Any], qualifiers: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    explicit = _text(feature.get("display_label") or feature.get("name") or feature.get("label"))
    if explicit:
        return explicit
    qualifier_map = dict(qualifiers)
    for key in ("label", "gene", "note"):
        values = qualifier_map.get(key, ())
        if values and _text(values[0]):
            return _text(values[0])
    return _text(feature.get("feature_type") or feature.get("type")) or "Unclassified feature"


def _display_category(
    feature_type: str | None,
    component_type: str | None,
    biological_role: str | None,
    regulatory_class: str | None,
) -> str:
    # Exact declared semantic tokens may control styling; labels and sequence never do.
    for value in (biological_role, component_type, regulatory_class, feature_type):
        category = _DISPLAY_CATEGORIES.get(_text(value).lower())
        if category:
            return category
    return "unclassified"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _feature_identity(feature: PublicationMapFeature) -> str:
    payload = {
        "coordinates": [feature.authoritative.start, feature.authoritative.end],
        "strand": feature.strand,
        "parts": [
            [part.authoritative.start, part.authoritative.end, part.strand]
            for part in feature.parts
        ],
        "location_operator": feature.location_operator,
        "authoritative_type": feature.authoritative_type,
        "component_type": feature.component_type,
        "biological_role": feature.biological_role,
        "regulatory_class": feature.regulatory_class,
        "display_label": feature.display_label,
        "qualifiers": feature.qualifiers,
    }
    return hashlib.sha256(_canonical_json(payload).encode("ascii")).hexdigest()[:20]


def _feature_sort_key(feature: PublicationMapFeature) -> tuple[Any, ...]:
    return (
        feature.authoritative.start,
        feature.authoritative.end,
        feature.authoritative_type or "",
        feature.component_type or "",
        feature.display_label,
        -2 if feature.strand is None else feature.strand,
        _feature_identity(feature),
        _canonical_json(feature.provenance),
    )


def _normalize_feature(
    raw: Mapping[str, Any],
    *,
    sequence_length: int,
    topology: PublicationMapTopology,
) -> PublicationMapFeature:
    authoritative = _interval(raw.get("start"), raw.get("end"), sequence_length, "feature")
    strand = _strand(raw.get("strand"), "feature.strand")
    raw_parts = raw.get("location_parts") or raw.get("parts")
    if raw_parts is None:
        raw_parts = ({"start": authoritative.start, "end": authoritative.end, "strand": strand},)
    if not isinstance(raw_parts, Sequence) or isinstance(raw_parts, (str, bytes)) or not raw_parts:
        raise PublicationMapContractError("feature.location_parts must be a non-empty sequence when supplied.")
    parts: list[PublicationMapLocationPart] = []
    for index, raw_part in enumerate(raw_parts):
        if not isinstance(raw_part, Mapping):
            raise PublicationMapContractError("Each feature location part must be a mapping.")
        part_interval = _interval(
            raw_part.get("start"),
            raw_part.get("end"),
            sequence_length,
            f"feature.location_parts[{index}]",
        )
        part_strand = _strand(raw_part.get("strand", raw.get("strand")), f"feature.location_parts[{index}].strand")
        parts.append(PublicationMapLocationPart(part_interval, _display(part_interval), part_strand))
    normalized_parts = tuple(parts)
    if authoritative.start != min(part.authoritative.start for part in normalized_parts):
        raise PublicationMapContractError("feature.start must equal the minimum explicit part start.")
    if authoritative.end != max(part.authoritative.end for part in normalized_parts):
        raise PublicationMapContractError("feature.end must equal the maximum explicit part end.")
    if any(part.strand != strand for part in normalized_parts):
        raise PublicationMapContractError("Mixed-strand compound locations are outside Publication Map V1.")

    qualifiers = _qualifiers(raw.get("qualifiers"))
    feature_type = _optional_text(raw.get("feature_type") or raw.get("type"))
    component_type = _optional_text(raw.get("component_type"))
    biological_role = _optional_text(raw.get("biological_role"))
    regulatory_class = _optional_text(raw.get("regulatory_class"))
    classification = (
        FeatureClassificationState.AUTHORITATIVE
        if any((feature_type, component_type, biological_role, regulatory_class))
        else FeatureClassificationState.UNCLASSIFIED
    )
    placeholder = PublicationMapFeature(
        feature_id="",
        authoritative=authoritative,
        display=_display(authoritative),
        strand=strand,
        parts=normalized_parts,
        location_operator=_optional_text(raw.get("location_operator")) if len(normalized_parts) > 1 else None,
        wraps_origin=publication_map_wraps_origin(
            normalized_parts,
            topology,
            sequence_length,
        ),
        authoritative_type=feature_type,
        component_type=component_type,
        biological_role=biological_role,
        regulatory_class=regulatory_class,
        display_label=_feature_label(raw, qualifiers),
        qualifiers=qualifiers,
        provenance=_feature_provenance(raw),
        classification_state=classification,
        display_category=_display_category(feature_type, component_type, biological_role, regulatory_class),
    )
    return placeholder


def _with_feature_ids(features: list[PublicationMapFeature]) -> tuple[PublicationMapFeature, ...]:
    ordered = sorted(features, key=_feature_sort_key)
    digests = [_feature_identity(feature) for feature in ordered]
    totals = Counter(digests)
    occurrences: defaultdict[str, int] = defaultdict(int)
    identified: list[PublicationMapFeature] = []
    for feature, digest in zip(ordered, digests):
        occurrences[digest] += 1
        suffix = f"-{occurrences[digest]:03d}" if totals[digest] > 1 else ""
        identified.append(
            PublicationMapFeature(
                feature_id=f"publication-feature-{digest}{suffix}",
                authoritative=feature.authoritative,
                display=feature.display,
                strand=feature.strand,
                parts=feature.parts,
                location_operator=feature.location_operator,
                wraps_origin=feature.wraps_origin,
                authoritative_type=feature.authoritative_type,
                component_type=feature.component_type,
                biological_role=feature.biological_role,
                regulatory_class=feature.regulatory_class,
                display_label=feature.display_label,
                qualifiers=feature.qualifiers,
                provenance=feature.provenance,
                classification_state=feature.classification_state,
                display_category=feature.display_category,
            )
        )
    return tuple(identified)


def adapt_publication_map_source(source: AuthoritativePublicationMapSource) -> PublicationMapDocument:
    sequence_length = _integer(source.sequence_length, "sequence_length")
    if sequence_length <= 0:
        raise PublicationMapContractError("sequence_length must be positive.")
    construct_identifier = _text(source.construct_identifier)
    if not construct_identifier:
        raise PublicationMapContractError("construct_identifier cannot be empty.")
    checksum = _text(source.sequence_checksum)
    if not _SHA256_PATTERN.fullmatch(checksum):
        raise PublicationMapContractError("sequence_checksum must be a lowercase SHA-256 hex digest.")
    if source.sequence is not None:
        if len(source.sequence) != sequence_length:
            raise PublicationMapContractError("sequence_length differs from the supplied authoritative sequence.")
        actual_checksum = hashlib.sha256(source.sequence.encode("utf-8")).hexdigest()
        if actual_checksum != checksum:
            raise PublicationMapContractError("sequence_checksum differs from the supplied authoritative sequence.")
    try:
        topology = PublicationMapTopology(_text(source.topology).lower())
    except ValueError as exc:
        raise PublicationMapContractError("topology must be 'circular' or 'linear'.") from exc
    try:
        view_type = PublicationMapViewType(source.view_type)
    except ValueError as exc:
        raise PublicationMapContractError(f"Unsupported publication-map view: {source.view_type!r}") from exc
    expected_topology = (
        PublicationMapTopology.CIRCULAR
        if view_type is PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID
        else PublicationMapTopology.LINEAR
    )
    if topology is not expected_topology:
        raise PublicationMapContractError(
            f"View {view_type.value!r} requires {expected_topology.value!r} topology."
        )
    if not isinstance(source.features, Sequence) or isinstance(source.features, (str, bytes)):
        raise PublicationMapContractError("features must be a sequence of mappings.")
    normalized_features: list[PublicationMapFeature] = []
    for feature in source.features:
        if not isinstance(feature, Mapping):
            raise PublicationMapContractError("Each feature must be a mapping.")
        normalized_features.append(
            _normalize_feature(feature, sequence_length=sequence_length, topology=topology)
        )
    features = _with_feature_ids(normalized_features)
    whole = PublicationMapInterval(0, sequence_length)
    return PublicationMapDocument(
        schema_version=PUBLICATION_MAP_SCHEMA_VERSION,
        construct_identifier=construct_identifier,
        display_name=_text(source.display_name) or construct_identifier,
        sequence_length=sequence_length,
        topology=topology,
        sequence_checksum=checksum,
        checksum_algorithm="sha256",
        features=features,
        provenance=_provenance(source.provenance),
        view=PublicationMapViewDefinition(view_type, topology, whole, _display(whole)),
    )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicationMapContractError(f"{field_name} must be a mapping.")
    return value


def _unique_active_record(
    runtime: Mapping[str, Any],
    *,
    collection_name: str,
    identity_field: str,
    active_identity_field: str,
) -> tuple[str, Mapping[str, Any]]:
    active_identity = _text(runtime.get(active_identity_field))
    if not active_identity:
        raise PublicationMapContractError(
            f"{active_identity_field} is required for publication-map projection."
        )
    records = runtime.get(collection_name)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise PublicationMapContractError(f"{collection_name} must be a sequence.")
    matches: list[Mapping[str, Any]] = []
    for index, candidate in enumerate(records):
        record = _mapping(candidate, f"{collection_name}[{index}]")
        if _text(record.get(identity_field)) == active_identity:
            matches.append(record)
    if len(matches) != 1:
        raise PublicationMapContractError(
            f"{active_identity_field} must identify exactly one {collection_name} record; "
            f"found {len(matches)}."
        )
    return active_identity, matches[0]


def _require_current_nonblocking_snapshot(snapshot: Mapping[str, Any]) -> None:
    if _text(snapshot.get("construct_status")) != "current":
        raise PublicationMapContractError(
            "Publication-map projection requires a current canonical snapshot."
        )
    summary = _mapping(snapshot.get("validation_summary"), "validation_summary")
    blocking_count = _integer(summary.get("blocking_count"), "validation_summary.blocking_count")
    if blocking_count != 0:
        raise PublicationMapContractError(
            "Publication-map projection rejects canonical snapshots with blocking findings."
        )
    _reject_explicit_blocking_findings(
        snapshot.get("validation_findings"),
        field_name="canonical snapshot validation_findings",
    )


def _reject_explicit_blocking_findings(
    findings_value: Any,
    *,
    field_name: str,
) -> None:
    """Reject explicit canonical blocking findings without reinterpreting warnings."""
    if findings_value is None:
        return
    if not isinstance(findings_value, Sequence) or isinstance(findings_value, (str, bytes)):
        raise PublicationMapContractError(f"{field_name} must be a sequence when supplied.")
    for index, finding_value in enumerate(findings_value):
        finding = _mapping(finding_value, f"{field_name}[{index}]")
        if finding.get("blocking") is True:
            raise PublicationMapContractError(
                f"Publication-map projection rejects {field_name} with blocking findings."
            )


def _require_current_nonblocking_construct_record(
    record: Mapping[str, Any],
    *,
    record_name: str,
) -> None:
    if _text(record.get("construct_status")) != "current":
        raise PublicationMapContractError(
            f"Publication-map projection requires a current {record_name}."
        )
    summary = _mapping(
        record.get("validation_summary"),
        f"{record_name}.validation_summary",
    )
    blocking_count = _integer(
        summary.get("blocking_count"),
        f"{record_name}.validation_summary.blocking_count",
    )
    if blocking_count != 0:
        raise PublicationMapContractError(
            f"Publication-map projection rejects {record_name} records with blocking findings."
        )
    _reject_explicit_blocking_findings(
        record.get("validation_findings"),
        field_name=f"{record_name}.validation_findings",
    )


def _require_current_nonblocking_transcription_unit(
    transcription_unit: Mapping[str, Any],
) -> None:
    if transcription_unit.get("stale") is not False:
        raise PublicationMapContractError(
            "Publication-map projection requires a current active transcription unit."
        )
    findings = transcription_unit.get("validation_findings")
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
        raise PublicationMapContractError(
            "active transcription unit validation_findings must be a sequence."
        )
    for index, finding_value in enumerate(findings):
        finding = _mapping(
            finding_value,
            f"active transcription unit validation_findings[{index}]",
        )
        if finding.get("blocking") is True:
            raise PublicationMapContractError(
                "Publication-map projection rejects active transcription units with blocking findings."
            )


def _require_snapshot_value(
    snapshot: Mapping[str, Any],
    field_name: str,
    expected: str | int,
) -> None:
    actual: str | int
    if isinstance(expected, int):
        actual = _integer(snapshot.get(field_name), field_name)
    else:
        actual = _text(snapshot.get(field_name))
    if actual != expected:
        raise PublicationMapContractError(
            f"Canonical snapshot {field_name} does not match its uniquely bound active record."
        )


def _linear_projection(snapshot_value: Any) -> _CanonicalPublicationProjection:
    snapshot = _mapping(snapshot_value, "canonical snapshot")
    runtime = _mapping(snapshot.get("runtime"), "canonical snapshot runtime")
    transcription_unit_id, transcription_unit = _unique_active_record(
        runtime,
        collection_name="transcription_units",
        identity_field="tu_id",
        active_identity_field="active_transcription_unit_id",
    )
    construct_id, construct = _unique_active_record(
        runtime,
        collection_name="constructs",
        identity_field="construct_id",
        active_identity_field="active_construct_id",
    )
    if _text(construct.get("transcription_unit_id")) != transcription_unit_id:
        raise PublicationMapContractError(
            "The active canonical construct is not bound to the active transcription unit."
        )
    _require_current_nonblocking_snapshot(snapshot)
    _require_current_nonblocking_construct_record(
        construct,
        record_name="active construct",
    )
    _require_current_nonblocking_transcription_unit(transcription_unit)

    sequence = _text(transcription_unit.get("generated_nucleotide_sequence"))
    checksum = _text(transcription_unit.get("generated_sequence_checksum"))
    revision_id = _text(transcription_unit.get("revision_id"))
    if not sequence or not checksum or not revision_id:
        raise PublicationMapContractError(
            "Current canonical sequence, checksum, and revision identity are required."
        )
    if (
        _text(construct.get("canonical_generated_sequence")) != sequence
        or _text(construct.get("sequence_checksum")) != checksum
        or _text(construct.get("current_revision")) != revision_id
    ):
        raise PublicationMapContractError(
            "The active construct and transcription unit do not share one canonical revision."
        )
    _require_snapshot_value(snapshot, "construct_id", construct_id)
    _require_snapshot_value(snapshot, "sequence", sequence)
    _require_snapshot_value(snapshot, "sequence_length", len(sequence))
    _require_snapshot_value(snapshot, "sequence_checksum", checksum)
    _require_snapshot_value(snapshot, "revision_id", revision_id)

    features = transcription_unit.get("feature_coordinates")
    if not isinstance(features, Sequence) or isinstance(features, (str, bytes)):
        raise PublicationMapContractError("feature_coordinates must be a sequence.")
    return _CanonicalPublicationProjection(
        construct_identifier=construct_id,
        sequence=sequence,
        sequence_checksum=checksum,
        revision_id=revision_id,
        topology="linear",
        features=tuple(_mapping(item, "feature_coordinates item") for item in features),
        runtime_schema_version=_text(runtime.get("schema_version")),
    )


def _circular_projection(snapshot_value: Any) -> _CanonicalPublicationProjection:
    snapshot = _mapping(snapshot_value, "canonical snapshot")
    runtime = _mapping(snapshot.get("runtime"), "canonical snapshot runtime")
    plasmid_id, plasmid = _unique_active_record(
        runtime,
        collection_name="complete_plasmid_constructs",
        identity_field="plasmid_id",
        active_identity_field="active_complete_plasmid_id",
    )
    _require_current_nonblocking_snapshot(snapshot)
    _require_current_nonblocking_construct_record(
        plasmid,
        record_name="active complete plasmid",
    )

    sequence = _text(plasmid.get("generated_nucleotide_sequence"))
    checksum = _text(plasmid.get("sequence_checksum"))
    revision_id = _text(plasmid.get("current_revision"))
    topology = _text(plasmid.get("topology")).lower()
    if not sequence or not checksum or not revision_id or not topology:
        raise PublicationMapContractError(
            "Current canonical sequence, checksum, revision identity, and topology are required."
        )
    _require_snapshot_value(snapshot, "plasmid_id", plasmid_id)
    _require_snapshot_value(snapshot, "sequence", sequence)
    _require_snapshot_value(snapshot, "sequence_length", len(sequence))
    _require_snapshot_value(snapshot, "sequence_checksum", checksum)
    _require_snapshot_value(snapshot, "revision_id", revision_id)
    _require_snapshot_value(snapshot, "topology", topology)

    features = plasmid.get("combined_feature_coordinates")
    if not isinstance(features, Sequence) or isinstance(features, (str, bytes)):
        raise PublicationMapContractError("combined_feature_coordinates must be a sequence.")
    return _CanonicalPublicationProjection(
        construct_identifier=plasmid_id,
        sequence=sequence,
        sequence_checksum=checksum,
        revision_id=revision_id,
        topology=topology,
        features=tuple(
            _mapping(item, "combined_feature_coordinates item") for item in features
        ),
        runtime_schema_version=_text(runtime.get("schema_version")),
    )


def publication_map_document_from_runtime(
    runtime_payload: Mapping[str, Any],
    *,
    view_type: PublicationMapViewType,
    display_name: str = "",
) -> PublicationMapDocument:
    if view_type in {
        PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        PublicationMapViewType.COMPLETE_LINEAR_PLASMID,
    }:
        # Keep contract-only use independent of the full formal runtime import.
        from services.canonical_construct_runtime import active_complete_plasmid_snapshot

        projection = _circular_projection(
            active_complete_plasmid_snapshot(dict(runtime_payload))
        )
        if view_type is PublicationMapViewType.COMPLETE_LINEAR_PLASMID:
            projection = replace(projection, topology="linear")
    elif view_type is PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT:
        from services.canonical_construct_runtime import active_construct_snapshot

        projection = _linear_projection(active_construct_snapshot(dict(runtime_payload)))
    else:
        raise PublicationMapContractError(f"Unsupported publication-map view: {view_type!r}")

    return adapt_publication_map_source(
        AuthoritativePublicationMapSource(
            construct_identifier=projection.construct_identifier,
            display_name=display_name,
            sequence_length=len(projection.sequence),
            topology=projection.topology,
            sequence_checksum=projection.sequence_checksum,
            sequence=projection.sequence,
            features=projection.features,
            provenance={
                "runtime_schema_version": projection.runtime_schema_version,
                PUBLICATION_MAP_REVISION_PROVENANCE_FIELD: projection.revision_id,
                "source_coordinate_convention": AUTHORITATIVE_COORDINATE_CONVENTION,
                "display_coordinate_convention": DISPLAY_COORDINATE_CONVENTION,
                "source_view": view_type.value,
            },
            view_type=view_type,
        )
    )
