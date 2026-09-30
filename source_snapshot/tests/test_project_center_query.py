from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from services.project_center_query import (
    PROJECT_TYPE_ALL,
    PROJECT_TYPE_MULTI_TU,
    PROJECT_TYPE_SINGLE_GENE,
    SORT_NAME_ASC,
    SORT_NAME_DESC,
    SORT_OLDEST,
    SORT_RECENT,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_UNKNOWN,
    ProjectCenterProject,
    filter_and_sort_projects,
    format_project_timestamp_for_local_display,
    normalized_lifecycle_status,
    paginate_projects,
    projects_for_lifecycle,
    project_host_values,
    project_status_values,
)


LOCAL_UTC_PLUS_8 = timezone(timedelta(hours=8))


def _project(
    project_id: str,
    name: str,
    *,
    updated_at: str = "2026-08-01T10:00:00Z",
    project_type: str = PROJECT_TYPE_SINGLE_GENE,
    status: str = "draft",
    host: str = "水稻（Oryza sativa）",
) -> ProjectCenterProject:
    return ProjectCenterProject(project_id, name, updated_at, project_type, status, host)


def test_empty_collection_and_zero_result_pagination_are_safe() -> None:
    assert filter_and_sort_projects([]) == []
    page = paginate_projects([], page=8)
    assert (page.items, page.page, page.total_pages, page.total_items) == ((), 0, 0, 0)


def test_name_search_supports_exact_partial_casefold_and_chinese() -> None:
    projects = [_project("1", "Rice ALB"), _project("2", "水稻表达项目"), _project("3", "Tomato")]

    assert [item.project_id for item in filter_and_sort_projects(projects, query=" rice alb ")] == ["1"]
    assert [item.project_id for item in filter_and_sort_projects(projects, query="ALB")] == ["1"]
    assert [item.project_id for item in filter_and_sort_projects(projects, query="水稻表")] == ["2"]
    assert len(filter_and_sort_projects(projects, query="   ")) == 3


def test_type_status_host_and_combined_filters_preserve_unknown_records_in_all() -> None:
    projects = [
        _project("single", "Single", status="draft"),
        _project("multi", "Multi", project_type="dual_tu", status="completed", host="烟草（Nicotiana benthamiana）"),
        _project("gate", "Gate", project_type="gate3_pathway_draft", status="manual_review_required"),
        _project("unknown", "Unknown", project_type="legacy_mode", status="custom", host="Custom host"),
    ]

    assert [item.project_id for item in filter_and_sort_projects(projects, project_type=PROJECT_TYPE_SINGLE_GENE)] == ["single"]
    assert [item.project_id for item in filter_and_sort_projects(projects, project_type=PROJECT_TYPE_MULTI_TU)] == ["multi", "gate"]
    assert [item.project_id for item in filter_and_sort_projects(projects, project_status="completed")] == ["multi"]
    assert [item.project_id for item in filter_and_sort_projects(projects, host="Custom host")] == ["unknown"]
    assert [item.project_id for item in filter_and_sort_projects(projects, project_type=PROJECT_TYPE_ALL, project_status="draft", host="水稻（Oryza sativa）")] == ["single"]
    assert {item.project_id for item in filter_and_sort_projects(projects)} == {"single", "multi", "gate", "unknown"}
    assert project_status_values(projects) == ["completed", "custom", "draft", "manual_review_required"]
    assert project_host_values(projects) == ["Custom host", "水稻（Oryza sativa）", "烟草（Nicotiana benthamiana）"]


def test_sorting_uses_stable_project_id_and_handles_missing_timestamps() -> None:
    projects = [
        _project("b", "beta", updated_at="2026-08-02T10:00:00Z"),
        _project("a", "Alpha", updated_at="2026-08-02T10:00:00+00:00"),
        _project("c", "Gamma", updated_at=""),
        _project("d", "delta", updated_at="not-a-date"),
    ]

    assert [item.project_id for item in filter_and_sort_projects(projects, sort=SORT_RECENT)] == ["b", "a", "d", "c"]
    assert [item.project_id for item in filter_and_sort_projects(projects, sort=SORT_OLDEST)] == ["a", "b", "c", "d"]
    assert [item.project_id for item in filter_and_sort_projects(projects, sort=SORT_NAME_ASC)] == ["a", "b", "d", "c"]
    assert [item.project_id for item in filter_and_sort_projects(projects, sort=SORT_NAME_DESC)] == ["c", "d", "b", "a"]


def test_utc_aware_timestamp_is_displayed_in_the_requested_local_timezone() -> None:
    assert (
        format_project_timestamp_for_local_display(
            "2026-08-10T04:14:39.238352Z", local_timezone=LOCAL_UTC_PLUS_8
        )
        == "2026-08-10 12:14"
    )


def test_naive_timestamp_is_explicitly_interpreted_as_utc_for_display() -> None:
    assert (
        format_project_timestamp_for_local_display(
            "2026-08-09T12:58:43.218142", local_timezone=LOCAL_UTC_PLUS_8
        )
        == "2026-08-09 20:58"
    )


def test_timezone_aware_local_timestamp_is_not_shifted_twice() -> None:
    assert (
        format_project_timestamp_for_local_display(
            "2026-08-10T12:14:39.238352+08:00", local_timezone=LOCAL_UTC_PLUS_8
        )
        == "2026-08-10 12:14"
    )


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_missing_or_invalid_timestamp_uses_a_safe_display_fallback(value: object) -> None:
    assert format_project_timestamp_for_local_display(value, local_timezone=LOCAL_UTC_PLUS_8) == "--"


def test_display_formatting_does_not_change_the_persisted_timestamp_value() -> None:
    raw_timestamp = "2026-08-10T04:14:39.238352Z"
    project = _project("project", "Project", updated_at=raw_timestamp)

    format_project_timestamp_for_local_display(project.updated_at, local_timezone=LOCAL_UTC_PLUS_8)

    assert raw_timestamp == "2026-08-10T04:14:39.238352Z"
    assert project.updated_at == raw_timestamp


def test_pagination_is_clamped_and_never_mutates_input() -> None:
    projects = [_project(str(index), f"项目 {index:02d}") for index in range(25)]
    original = list(projects)

    first = paginate_projects(projects, page=0)
    last = paginate_projects(projects, page=9)

    assert (first.page, first.total_pages, first.start_item, first.end_item, len(first.items)) == (1, 2, 1, 20, 20)
    assert (last.page, last.total_pages, last.start_item, last.end_item, len(last.items)) == (2, 2, 21, 25, 5)
    assert projects == original


def test_search_can_find_a_project_outside_a_recent_eight_item_slice() -> None:
    projects = [
        _project(str(index), f"Project {index:02d}", updated_at=f"2026-08-{index:02d}T10:00:00Z")
        for index in range(1, 11)
    ]
    recent_eight = filter_and_sort_projects(projects, sort=SORT_RECENT)[:8]
    results = filter_and_sort_projects(projects, query="Project 01", sort=SORT_RECENT)

    assert "1" not in {project.project_id for project in recent_eight}
    assert [project.project_id for project in results] == ["1"]


def test_name_search_composes_with_type_filter_and_paginate_resets_to_first_page() -> None:
    projects = [
        _project(str(index), f"ALB {index:02d}", project_type=PROJECT_TYPE_SINGLE_GENE)
        for index in range(1, 25)
    ] + [_project("multi", "ALB Multi", project_type=PROJECT_TYPE_MULTI_TU)]

    results = filter_and_sort_projects(projects, query=" alb ", project_type=PROJECT_TYPE_MULTI_TU)
    page = paginate_projects(results, page=1)

    assert [project.project_id for project in page.items] == ["multi"]
    assert page.page == 1


def test_lifecycle_collections_keep_legacy_active_and_unknown_records_without_mutation() -> None:
    projects = [
        _project("active", "Active"),
        ProjectCenterProject("archived", "Archived", "2026-08-03T10:00:00Z", "single_gene", "draft", "Rice", "archived", "2026-08-03T10:00:00Z"),
        ProjectCenterProject("legacy", "Legacy", "2026-08-02T10:00:00Z", "single_gene", "draft", "Rice"),
        ProjectCenterProject("empty", "Empty", "2026-08-04T10:00:00Z", "single_gene", "draft", "Rice", "", ""),
        ProjectCenterProject("unknown", "Unknown", "2026-08-05T10:00:00Z", "single_gene", "draft", "Rice", "held", ""),
    ]
    original = list(projects)

    assert normalized_lifecycle_status() == LIFECYCLE_ACTIVE
    assert normalized_lifecycle_status("") == LIFECYCLE_UNKNOWN
    assert normalized_lifecycle_status("held") == "unknown"
    assert [item.project_id for item in projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ACTIVE)] == ["active", "legacy"]
    assert [item.project_id for item in projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ARCHIVED)] == ["archived"]
    assert [item.project_id for item in projects_for_lifecycle(projects, lifecycle_status="non_archived")] == ["active", "legacy", "empty", "unknown"]
    assert projects == original


@pytest.mark.parametrize("invalid_status", [None, "", 0, False, [], {}, "invalid", "deleted", "ARCHIVED", " active ", "archived "])
def test_present_invalid_lifecycle_values_are_unknown(invalid_status: object) -> None:
    assert normalized_lifecycle_status(invalid_status) == LIFECYCLE_UNKNOWN


def test_archived_queries_reuse_filters_sorting_and_clamped_twenty_item_pagination() -> None:
    archived = [
        ProjectCenterProject(
            f"archived-{index}",
            f"Archive {index:02d}",
            f"2026-08-{(index % 28) + 1:02d}T10:00:00Z",
            "multi_tu" if index % 2 else "single_gene",
            "completed" if index % 2 else "draft",
            "Rice" if index % 2 else "Tobacco",
            "archived",
            "2026-08-01T10:00:00Z",
        )
        for index in range(1, 22)
    ]
    collection = projects_for_lifecycle(archived, lifecycle_status=LIFECYCLE_ARCHIVED)
    filtered = filter_and_sort_projects(
        collection,
        query="Archive",
        project_type=PROJECT_TYPE_MULTI_TU,
        project_status="completed",
        host="Rice",
        sort=SORT_NAME_DESC,
    )
    assert len(filtered) == 11
    page = paginate_projects(collection, page=9)
    assert (page.page, page.total_pages, len(page.items)) == (2, 2, 1)
