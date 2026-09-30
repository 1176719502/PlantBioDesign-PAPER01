from __future__ import annotations

from typing import Any

from services import parts_registry_repository as repo


NO_VERSION_LABEL = "No version label recorded"
SEQUENCE_PRESENT_LABEL = "Sequence metadata present"
NO_SEQUENCE_LABEL = "No sequence metadata recorded"
NO_REVIEW_LABEL = "Human review needed"
NO_LINKAGE_LABEL = "No linked documentation records"
NO_LINK_VERSION_LABEL = "Part-level link"
PERSISTENT_RECORD_LABEL = "persistent records"
READ_ONLY_SCHEMA_LABEL = "read-only local registry schema"


def _latest_or_empty(records: list[dict[str, Any]]) -> dict[str, Any]:
    return records[0] if records else {}


def _version_label_by_id(versions: list[dict[str, Any]]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for version in versions:
        version_id = version.get("id")
        if version_id is None:
            continue
        labels[int(version_id)] = str(version.get("version_label") or NO_VERSION_LABEL)
    return labels


def build_linkage_display_records(
    links: list[dict[str, Any]],
    versions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    version_labels = _version_label_by_id(versions)
    rows: list[dict[str, Any]] = []
    for link in links:
        version_id = link.get("part_version_id")
        version_context = NO_LINK_VERSION_LABEL
        if version_id is not None:
            version_context = version_labels.get(int(version_id), f"Version id {version_id}")
        rows.append(
            {
                "Target type": str(link.get("target_type") or ""),
                "Target label snapshot": str(link.get("target_label") or ""),
                "Link note": str(link.get("link_note") or ""),
                "Review status": str(link.get("review_status") or ""),
                "Part version context": version_context,
                "Created at": str(link.get("created_at") or ""),
                "Updated at": str(link.get("updated_at") or ""),
            }
        )
    return rows


def build_part_browse_record(part: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only row for the local parts catalog browse panel."""
    local_id = str(part.get("local_id") or "")
    versions = repo.list_versions_for_part(local_id)
    sources = repo.list_source_records(local_id)
    annotations = repo.list_annotations(local_id)
    review_statuses = repo.list_review_status_records(local_id)
    links = repo.list_links_for_part(local_id)

    current_version = _latest_or_empty(versions)
    current_review = _latest_or_empty(review_statuses)
    sequence_present = bool(current_version.get("sequence"))
    linkage_records = build_linkage_display_records(links, versions)

    return {
        "local_id": local_id,
        "part_type": str(part.get("part_type") or ""),
        "display_name": str(part.get("display_name") or ""),
        "version_label": str(current_version.get("version_label") or NO_VERSION_LABEL),
        "sequence_metadata": SEQUENCE_PRESENT_LABEL if sequence_present else NO_SEQUENCE_LABEL,
        "source_note_count": len(sources),
        "linkage_record_count": len(linkage_records),
        "curation_status": str(current_review.get("curation_status") or "provenance review needed"),
        "human_review_status": str(current_review.get("human_review_status") or NO_REVIEW_LABEL),
        "part": dict(part),
        "versions": versions,
        "sources": sources,
        "annotations": annotations,
        "review_statuses": review_statuses,
        "linkage_records": linkage_records,
    }


def build_parts_browse_records() -> list[dict[str, Any]]:
    return [build_part_browse_record(part) for part in repo.list_parts()]


def table_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Part type": record["part_type"],
            "Display name": record["display_name"],
            "Current/version label": record["version_label"],
            "Sequence metadata": record["sequence_metadata"],
            "Source notes": record["source_note_count"],
            "Traceability links": record["linkage_record_count"],
            "Curation status": record["curation_status"],
            "Human review": record["human_review_status"],
        }
        for record in records
    ]


def build_registry_inventory_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    part_type_counts: dict[str, int] = {}
    version_count = 0
    source_note_count = 0
    annotation_count = 0
    review_status_count = 0
    linkage_count = 0
    sequence_metadata_count = 0
    for record in records:
        part_type = str(record.get("part_type") or "").strip() or "Unspecified"
        part_type_counts[part_type] = part_type_counts.get(part_type, 0) + 1
        version_count += len(record.get("versions") or [])
        source_note_count += len(record.get("sources") or [])
        annotation_count += len(record.get("annotations") or [])
        review_status_count += len(record.get("review_statuses") or [])
        linkage_count += len(record.get("linkage_records") or [])
        if str(record.get("sequence_metadata") or "") == SEQUENCE_PRESENT_LABEL:
            sequence_metadata_count += 1
    return {
        "record_source_label": PERSISTENT_RECORD_LABEL,
        "schema_status_label": READ_ONLY_SCHEMA_LABEL,
        "part_record_count": len(records),
        "part_type_count": len(part_type_counts),
        "counts_by_part_type": dict(sorted(part_type_counts.items(), key=lambda item: item[0].casefold())),
        "version_record_count": version_count,
        "source_note_count": source_note_count,
        "annotation_count": annotation_count,
        "review_status_count": review_status_count,
        "linked_traceability_count": linkage_count,
        "sequence_metadata_count": sequence_metadata_count,
    }
