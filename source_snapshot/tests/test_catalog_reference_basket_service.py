from __future__ import annotations

from services import catalog_reference_basket_service as basket_service


def _entry(
    *,
    project_id: str = "project-1",
    asset_id: str = "asset-1",
    linkage_role: str = "project_reference",
    context: str = "Pathway Workspace linked catalog assets",
) -> dict[str, object]:
    return basket_service.build_catalog_reference_basket_entry(
        project_id=project_id,
        link_payload={
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_display_name": f"Asset {asset_id}",
            "asset_type": "promoter",
            "linkage_role": linkage_role,
            "documentation_note": "Documentation-only reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Local Design Asset Catalog",
                "project_documentation_context": context,
            },
            "review_status_snapshot": {
                "review_status": "human review needed",
            },
            "human_review_required": True,
            "linked_at": "session",
        },
        project_documentation_context=context,
        documentation_note="Documentation-only reference for project traceability.",
    )


def test_add_list_and_find_basket_entry() -> None:
    session_state: dict[str, object] = {}
    entry = _entry()

    added, stored = basket_service.add_catalog_reference_basket_entry(session_state, entry)
    listed = basket_service.list_catalog_reference_basket(session_state, project_id="project-1")
    found = basket_service.find_catalog_reference_basket_entry(
        session_state,
        project_id="project-1",
        asset_id="asset-1",
        linkage_role="project_reference",
    )

    assert added is True
    assert stored["asset_id"] == "asset-1"
    assert len(listed) == 1
    assert found["asset_id"] == "asset-1"
    assert found["project_documentation_context"] == "Pathway Workspace linked catalog assets"


def test_duplicate_stage_guard_returns_existing_row() -> None:
    session_state: dict[str, object] = {}
    first = _entry()
    second = _entry()

    first_added, first_row = basket_service.add_catalog_reference_basket_entry(session_state, first)
    second_added, second_row = basket_service.add_catalog_reference_basket_entry(session_state, second)

    assert first_added is True
    assert second_added is False
    assert second_row["basket_id"] == first_row["basket_id"]
    assert len(basket_service.list_catalog_reference_basket(session_state, project_id="project-1")) == 1


def test_remove_and_clear_basket_entries() -> None:
    session_state: dict[str, object] = {}
    first = _entry(asset_id="asset-1")
    second = _entry(asset_id="asset-2", linkage_role="report_context")
    basket_service.add_catalog_reference_basket_entry(session_state, first)
    _, second_row = basket_service.add_catalog_reference_basket_entry(session_state, second)

    removed = basket_service.remove_catalog_reference_basket_entry(
        session_state,
        project_id="project-1",
        basket_id=second_row["basket_id"],
    )
    remaining = basket_service.list_catalog_reference_basket(session_state, project_id="project-1")
    basket_service.clear_catalog_reference_basket(session_state, project_id="project-1")

    assert removed is True
    assert [row["asset_id"] for row in remaining] == ["asset-1"]
    assert basket_service.list_catalog_reference_basket(session_state, project_id="project-1") == []
