"""Pure in-memory query helpers for the Project Center project browser."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from math import ceil
from typing import Iterable, Literal

from services.plant_project_draft_repository import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_UNKNOWN,
    normalized_project_lifecycle_status as normalized_lifecycle_status,
)


PROJECT_TYPE_ALL = "all"
PROJECT_TYPE_SINGLE_GENE = "single_gene"
PROJECT_TYPE_MULTI_TU = "multi_tu"
SORT_RECENT = "recent"
SORT_OLDEST = "oldest"
SORT_NAME_ASC = "name_asc"
SORT_NAME_DESC = "name_desc"
PAGE_SIZE = 20
ProjectTypeFilter = Literal["all", "single_gene", "multi_tu"]
ProjectSort = Literal["recent", "oldest", "name_asc", "name_desc"]


@dataclass(frozen=True)
class ProjectCenterProject:
    """Display metadata assembled by Project Home after its existing validation."""

    project_id: str
    project_name: str
    updated_at: str
    project_type: str
    project_status: str
    host: str
    lifecycle_status: str = LIFECYCLE_ACTIVE
    archived_at: str = ""


@dataclass(frozen=True)
class ProjectCenterPage:
    """A bounded page of queried project records."""

    items: tuple[ProjectCenterProject, ...]
    page: int
    total_pages: int
    total_items: int
    start_item: int
    end_item: int


def normalized_project_type(project_type: object) -> str:
    """Map only known persisted workflow types to the browser's two filters."""
    value = _text(project_type)
    if value == PROJECT_TYPE_SINGLE_GENE:
        return PROJECT_TYPE_SINGLE_GENE
    if value in {PROJECT_TYPE_MULTI_TU, "dual_tu", "gate3_pathway_draft", "gate3_pathway"}:
        return PROJECT_TYPE_MULTI_TU
    return value


def filter_and_sort_projects(
    projects: Iterable[ProjectCenterProject],
    *,
    query: object = "",
    project_type: ProjectTypeFilter = PROJECT_TYPE_ALL,
    project_status: object = "",
    host: object = "",
    sort: ProjectSort = SORT_RECENT,
) -> list[ProjectCenterProject]:
    """Return a new filtered and stably sorted project list without mutation."""
    search = _text(query).casefold()
    wanted_status = _text(project_status)
    wanted_host = _text(host)
    filtered = [
        project
        for project in projects
        if (not search or search in _text(project.project_name).casefold())
        and (project_type == PROJECT_TYPE_ALL or normalized_project_type(project.project_type) == project_type)
        and (not wanted_status or _text(project.project_status) == wanted_status)
        and (not wanted_host or _text(project.host) == wanted_host)
    ]
    return sorted(filtered, key=_sort_key(sort), reverse=sort in {SORT_RECENT, SORT_NAME_DESC})


def projects_for_lifecycle(
    projects: Iterable[ProjectCenterProject], *, lifecycle_status: str
) -> list[ProjectCenterProject]:
    """Return a new lifecycle collection without changing its source iterable."""
    requested = _text(lifecycle_status).casefold()
    if requested == LIFECYCLE_ACTIVE:
        return [
            project
            for project in projects
            if normalized_lifecycle_status(project.lifecycle_status) == LIFECYCLE_ACTIVE
        ]
    if requested == LIFECYCLE_ARCHIVED:
        return [
            project
            for project in projects
            if normalized_lifecycle_status(project.lifecycle_status) == LIFECYCLE_ARCHIVED
        ]
    if requested == "non_archived":
        return [
            project
            for project in projects
            if normalized_lifecycle_status(project.lifecycle_status) != LIFECYCLE_ARCHIVED
        ]
    raise ValueError("unsupported lifecycle status")


def paginate_projects(
    projects: Iterable[ProjectCenterProject], *, page: int, page_size: int = PAGE_SIZE
) -> ProjectCenterPage:
    """Return one clamped in-memory page. Empty results intentionally have no page."""
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    items = list(projects)
    total_items = len(items)
    total_pages = ceil(total_items / page_size) if total_items else 0
    if not total_pages:
        return ProjectCenterPage((), 0, 0, 0, 0, 0)
    resolved_page = min(max(int(page or 1), 1), total_pages)
    start = (resolved_page - 1) * page_size
    end = min(start + page_size, total_items)
    return ProjectCenterPage(tuple(items[start:end]), resolved_page, total_pages, total_items, start + 1, end)


def project_status_values(projects: Iterable[ProjectCenterProject]) -> list[str]:
    """Return non-empty persisted statuses in predictable display order."""
    return sorted({_text(project.project_status) for project in projects if _text(project.project_status)}, key=str.casefold)


def project_host_values(projects: Iterable[ProjectCenterProject]) -> list[str]:
    """Return non-empty display hosts in predictable display order."""
    return sorted({_text(project.host) for project in projects if _text(project.host)}, key=str.casefold)


def format_project_timestamp_for_local_display(
    value: object, *, local_timezone: tzinfo | None = None
) -> str:
    """Format a persisted project timestamp in the machine's local timezone."""
    text = _text(value)
    if not text:
        return "--"
    normalized = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone(local_timezone) if local_timezone is not None else parsed.astimezone()
    except (OSError, OverflowError, ValueError):
        return "--"
    return local.strftime("%Y-%m-%d %H:%M")


def _sort_key(sort: ProjectSort):
    if sort == SORT_OLDEST:
        return _oldest_key
    if sort in {SORT_NAME_ASC, SORT_NAME_DESC}:
        return lambda project: (_text(project.project_name).casefold(), _text(project.project_id))
    return _recent_key


def _recent_key(project: ProjectCenterProject) -> tuple[bool, datetime, str]:
    timestamp = _parsed_timestamp(project.updated_at)
    return (timestamp is not None, timestamp or datetime.min, _text(project.project_id))


def _oldest_key(project: ProjectCenterProject) -> tuple[bool, datetime, str]:
    timestamp = _parsed_timestamp(project.updated_at)
    return (timestamp is None, timestamp or datetime.max, _text(project.project_id))


def _parsed_timestamp(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value or "").strip()
