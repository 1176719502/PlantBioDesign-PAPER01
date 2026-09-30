"""Read-only output projection of persisted assisted component provenance.

No catalog lookup, admission, sequence construction, or evidence upgrade occurs
here. Missing historical verification flags stay unrecorded.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def assisted_component_provenance(selection: Mapping[str, Any]) -> dict[str, Any]:
    reference = _mapping(selection)
    resolution = _mapping(reference.get('assisted_resolution'))
    if (reference.get('source_type') != 'USER_PROVIDED'
            or resolution.get('admission_mode') != 'USER_SEQUENCE_ASSISTED'):
        return {}
    source = _mapping(resolution.get('source_provenance'))
    confirmation = _mapping(resolution.get('confirmation_contract'))
    return {
        'catalog_component_id': str(resolution.get('catalog_component_id') or ''),
        'catalog_name': str(resolution.get('catalog_name') or ''),
        'catalog_component_type': str(resolution.get('catalog_component_type') or ''),
        'source_accession': str(source.get('accession') or ''),
        'original_route': str(resolution.get('admission_mode') or ''),
        'authority': str(reference.get('source_type') or ''),
        'source_label': str(resolution.get('user_sequence_source') or ''),
        'reviewed_source_boundary': str(confirmation.get('recorded_boundary') or ''),
        'sequence_sha256': str(resolution.get('sequence_sha256') or ''),
        'project_id': str(resolution.get('project_id') or ''),
        'resolution_id': str(resolution.get('resolution_id') or ''),
        'confirmation_mode': str(confirmation.get('confirmation_mode') or ''),
        **{key: confirmation.get(key) if isinstance(confirmation.get(key), bool) else None
           for key in ('accession_verified', 'boundary_verified_by_software')},
    }


def runtime_assisted_component_provenance(runtime: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Bind provenance by canonical component ID, never display name or position."""
    records = {}
    if not runtime.get('expression_units'):
        for component in runtime.get('components') or []:
            provenance = assisted_component_provenance(_mapping(component.get('component_reference')))
            if provenance and component.get('component_id'):
                records[component['component_id']] = provenance
    for raw_unit in runtime.get('expression_units') or []:
        unit = _mapping(raw_unit)
        for value in unit.values():
            component = _mapping(value)
            component_id = str(component.get('component_id') or '')
            provenance = assisted_component_provenance(_mapping(component.get('component_reference')))
            if component_id and provenance:
                records[component_id] = provenance
    return records
