from __future__ import annotations

from datetime import datetime
from typing import Any

import os

import pandas as pd
import streamlit as st

from services.pathway_repository import (
    create_pathway_project,
    create_pathway_step,
    delete_pathway_project,
    get_pathway_project,
    list_pathway_projects,
    list_pathway_steps,
)
from services.project_catalog_reference_overview_presenter import build_project_catalog_reference_overview
from views.tool_typography import inject_tool_typography_css, render_compact_summary_cards, render_help_text

CURRENT_PROJECT_KEY = "pathway_current_project_id"
DELETE_CONFIRM_KEY = "pathway_delete_confirm_id"
_JUST_CREATED_KEY = "pathway_just_created_project"
_DEMO_STATUS_KEY = "pathway_demo_seed_status"
_DEBUG_FLAG_KEY = "pathway_debug_enabled"
_ACTIVE_PROJECT_CHOICE_KEY = "pathway_active_project_choice"
_PROJECT_SEARCH_KEY = "pathway_project_search_query"
_PROJECT_PREVIEW_SELECT_KEY = "pathway_project_preview_select"

_PATHWAY_TRANSIENT_KEYS = (
    DELETE_CONFIRM_KEY,
    _JUST_CREATED_KEY,
)


_DEMO_PROJECT = {
    "name": "Nicotiana benthamiana artemisinin precursor documentation case",
    "target_product": "Artemisinin precursor documentation context",
    "host": "Nicotiana benthamiana documentation context",
    "description": (
        "Documentation-only example project for candidate pathway genes, regulatory context, source and provenance "
        "records, traceability, review signals, and documentation-only exports in Nicotiana benthamiana context. "
        "It does not recommend promoters, optimize expression, validate constructs, predict yield, or make "
        "wet-lab use judgments."
    ),
}

_DEMO_STEPS = [
    {
        "step_order": 1,
        "step_name": "FPP precursor supply context",
        "substrate": "Precursor supply notes for isoprenoid pathway context",
        "product": "FPP / Farnesyl diphosphate documentation context",
        "enzyme_name": "Precursor supply record",
        "gene_name": "FPS / FPPS",
        "notes": (
            "Precursor supply record for FPS / FPPS pathway context. Use this step to document source review, "
            "traceability, and candidate-part references only."
        ),
    },
    {
        "step_order": 2,
        "step_name": "ADS pathway gene record",
        "substrate": "FPP / Farnesyl diphosphate documentation context",
        "product": "Amorpha-4,11-diene pathway documentation context",
        "enzyme_name": "Pathway gene record",
        "gene_name": "AaADS / amorpha-4,11-diene synthase",
        "notes": (
            "Pathway gene record for AaADS in Artemisia annua source context. This is a documentation-only "
            "candidate record and not a biological performance claim."
        ),
    },
    {
        "step_order": 3,
        "step_name": "CYP71AV1 + CPR oxidation context",
        "substrate": "Amorpha-4,11-diene pathway documentation context",
        "product": "Oxidation pathway documentation context",
        "enzyme_name": "Enzyme context record",
        "gene_name": "AaCYP71AV1 + CPR",
        "notes": (
            "Enzyme context record for AaCYP71AV1 and CPR source-traceability review. This step documents "
            "oxidation context only and does not predict host compatibility or pathway output."
        ),
    },
    {
        "step_order": 4,
        "step_name": "DBR2 optional downstream context",
        "substrate": "Oxidation pathway documentation context",
        "product": "Optional downstream pathway context",
        "enzyme_name": "Optional downstream pathway context",
        "gene_name": "AaDBR2",
        "notes": (
            "Optional downstream pathway context for AaDBR2. Preserve candidate/source-recorded wording and "
            "review status only."
        ),
    },
    {
        "step_order": 5,
        "step_name": "ALDH1 optional downstream context",
        "substrate": "Optional downstream pathway context",
        "product": "Optional downstream pathway context",
        "enzyme_name": "Optional downstream pathway context",
        "gene_name": "AaALDH1",
        "notes": (
            "Optional downstream pathway context for AaALDH1. This documentation step captures source review, "
            "manual review notes, and traceability context only."
        ),
    },
    {
        "step_order": 6,
        "step_name": "Final chemistry note",
        "substrate": "Recorded pathway context",
        "product": "Artemisinin formation downstream chemistry context",
        "enzyme_name": "Not software prediction",
        "gene_name": "Downstream chemistry / light / oxygen context",
        "notes": (
            "Final chemistry note: artemisinin formation requires downstream chemistry, light, and oxygen context. "
            "This software records documentation only and does not make a chemistry or readiness prediction."
        ),
    },
]

def _format_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text[:16]


def _status_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "draft"


def _project_matches_search(project: dict[str, Any], query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return True
    fields = [
        project.get("name"),
        project.get("target_product"),
        project.get("host"),
        project.get("status"),
        project.get("description"),
        f"ref #{project.get('id')}",
    ]
    return any(text in str(field or "").lower() for field in fields)


def _filter_projects(projects: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return [project for project in projects if _project_matches_search(project, query)]


def _active_choice_from_state(projects: list[dict[str, Any]]) -> int | None:
    project_ids = {int(project["id"]) for project in projects}
    choice = st.session_state.get(_ACTIVE_PROJECT_CHOICE_KEY)
    try:
        selected_id = int(choice)
    except (TypeError, ValueError):
        return None
    return selected_id if selected_id in project_ids else None


def _sync_active_choice(projects: list[dict[str, Any]]) -> None:
    if not projects:
        st.session_state.pop(_ACTIVE_PROJECT_CHOICE_KEY, None)
        return
    project_ids = [int(project["id"]) for project in projects]
    selected_id = _active_choice_from_state(projects)
    if selected_id in project_ids:
        st.session_state[_ACTIVE_PROJECT_CHOICE_KEY] = selected_id
        return
    current_id = st.session_state.get(CURRENT_PROJECT_KEY)
    if current_id in project_ids:
        st.session_state[_ACTIVE_PROJECT_CHOICE_KEY] = current_id
        return
    st.session_state[_ACTIVE_PROJECT_CHOICE_KEY] = project_ids[0]


def _project_overview_records(projects: list[dict[str, Any]]) -> list[dict[str, str]]:
    current_id = st.session_state.get(CURRENT_PROJECT_KEY)
    records: list[dict[str, str]] = []
    for project in projects:
        project_id = int(project["id"])
        name = str(project.get("name") or "Untitled project").strip()
        if current_id == project_id:
            name = f"{name} (Active)"
        records.append(
            {
                "Project": name,
                "Target product": str(project.get("target_product") or "Not set"),
                "Host / context": str(project.get("host") or "Not set"),
                "Status": _status_text(project.get("status")),
                "Updated": _format_time(project.get("updated_at")) or "Not recorded",
                "Ref": f"Ref #{project_id}",
            }
        )
    return records


def _render_project_overview_rows(projects: list[dict[str, Any]]) -> None:
    if not projects:
        st.info("No pathway projects have been created yet.")
        return

    st.dataframe(
        _project_overview_records(projects),
        use_container_width=True,
        hide_index=True,
    )


def _set_current_project(project_id: int | str | None) -> None:
    try:
        st.session_state[CURRENT_PROJECT_KEY] = int(project_id) if project_id is not None else None
    except (TypeError, ValueError):
        st.session_state[CURRENT_PROJECT_KEY] = None


def _clear_pathway_transient_state() -> None:
    for key in _PATHWAY_TRANSIENT_KEYS:
        st.session_state.pop(key, None)


def _find_existing_demo(projects: list[dict[str, Any]]) -> dict[str, Any] | None:
    for project in projects:
        if project.get("name") == _DEMO_PROJECT["name"]:
            return project
    return None


def _get_demo_seed_status(projects: list[dict[str, Any]]) -> dict[str, Any]:
    demo_project = _find_existing_demo(projects)
    if not demo_project:
        return {"ready": False}

    project_id = int(demo_project["id"])
    steps = list_pathway_steps(project_id)
    return {"ready": len(steps) == 6}


def _store_demo_seed_status(*, last_action: str, created_steps_count: int) -> None:
    st.session_state[_DEMO_STATUS_KEY] = {
        "last_action": last_action,
        "last_created_steps_count": int(created_steps_count),
    }


def _ensure_demo_steps_exist(project_id: int) -> int:
    """Create missing example pathway steps for this project.

    Returns the number of newly created steps.
    """
    existing_steps = list_pathway_steps(project_id)
    existing_orders = {
        int(step.get("step_order") or 0)
        for step in existing_steps
        if int(step.get("step_order") or 0) > 0
    }
    existing_names = {
        str(step.get("step_name") or "").strip()
        for step in existing_steps
        if str(step.get("step_name") or "").strip()
    }
    created_count = 0

    for demo_step in _DEMO_STEPS:
        if demo_step["step_order"] in existing_orders or demo_step["step_name"] in existing_names:
            continue

        ok, _message, _step_id = create_pathway_step(
            project_id=project_id,
            step_order=demo_step["step_order"],
            step_name=demo_step["step_name"],
            substrate=demo_step.get("substrate", ""),
            product=demo_step.get("product", ""),
            enzyme_name=demo_step.get("enzyme_name", ""),
            gene_name=demo_step.get("gene_name", ""),
            notes=demo_step.get("notes", ""),
        )
        if ok:
            created_count += 1

    return created_count


def _load_demo_project(projects: list[dict[str, Any]], change_page) -> None:
    existing = _find_existing_demo(projects)
    if existing:
        project_id = int(existing["id"])
        created_count = _ensure_demo_steps_exist(project_id)
        _store_demo_seed_status(last_action="opened", created_steps_count=created_count)
        _set_current_project(project_id)
        _clear_pathway_transient_state()
        st.session_state[_JUST_CREATED_KEY] = project_id
        st.rerun()
    else:
        ok, message, project_id = create_pathway_project(
            name=_DEMO_PROJECT["name"],
            target_product=_DEMO_PROJECT["target_product"],
            host=_DEMO_PROJECT["host"],
            description=_DEMO_PROJECT["description"],
        )
        if ok and project_id is not None:
            created_count = _ensure_demo_steps_exist(int(project_id))
            _store_demo_seed_status(last_action="created", created_steps_count=created_count)
            _set_current_project(project_id)
            _clear_pathway_transient_state()
            st.session_state[_JUST_CREATED_KEY] = int(project_id)
            st.rerun()
        else:
            st.error(message)



def _project_summary_lines(project: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("Project name", project.get("name") or "Not set"),
        ("Ref", f"Ref #{int(project.get('id') or 0)}"),
        ("Target product", project.get("target_product") or "Not set"),
        ("Host / chassis", project.get("host") or "Not set"),
        ("Status", project.get("status") or "draft"),
        ("Last updated", _format_time(project.get("updated_at")) or "Not available"),
        ("Description", project.get("description") or "No description provided."),
    ]


def _render_selected_project_summary(project: dict[str, Any], *, is_active: bool) -> None:
    summary = dict(_project_summary_lines(project))
    with st.container(border=True):
        st.subheader("Selected Project")
        detail_left, detail_right = st.columns(2, gap="small")
        with detail_left:
            st.write(f"Project name: {summary['Project name']}")
            st.write(f"Ref: {summary['Ref']}")
            st.write(f"Target product: {summary['Target product']}")
        with detail_right:
            st.write(f"Host / context: {summary['Host / chassis']}")
            st.write(f"Status: {summary['Status']}")
            st.write(f"Updated: {summary['Last updated']}")
        if is_active:
            st.caption(f"Current active project: {summary['Project name']}")
        st.caption("This only changes the active project. It does not edit, rename, or delete records.")
        if summary["Description"] != "No description provided.":
            with st.expander("Project description", expanded=False):
                st.write(summary["Description"])


def _debug_enabled() -> bool:
    return bool(st.session_state.get(_DEBUG_FLAG_KEY, False) or os.getenv("PATHWAY_DEBUG", "").lower() in {"1", "true", "yes", "on"})



def _render_create_project_form(change_page) -> None:
    with st.container(border=True):
        st.subheader("Create New Project")
        st.caption("Start a new local documentation project workspace for pathway context and linked design records.")
        with st.form("pathway_create_project_form", clear_on_submit=True):
            name = st.text_input("Project name", placeholder="For example: Naringenin pathway design")
            target_product = st.text_input("Target product", placeholder="For example: Naringenin")
            host = st.text_input("Host / chassis", placeholder="For example: E. coli BL21(DE3)")
            description = st.text_area(
                "Description",
                placeholder="Briefly describe the pathway documentation goal and review context.",
                height=80,
            )
            submitted = st.form_submit_button("Create Project", use_container_width=True)
        if submitted:
            ok, message, project_id = create_pathway_project(
                name=name,
                target_product=target_product,
                host=host,
                description=description,
            )
            if ok and project_id is not None:
                _set_current_project(project_id)
                _clear_pathway_transient_state()
                st.session_state[_JUST_CREATED_KEY] = int(project_id)
                st.rerun()
            else:
                st.error(message)


def _render_quick_start(projects: list[dict[str, Any]], change_page) -> None:
    with st.container(border=True):
        st.subheader("Quick Start")
        demo_exists = _find_existing_demo(projects) is not None
        demo_fields = [
            ("Example name", _DEMO_PROJECT["name"]),
            ("Target", _DEMO_PROJECT["target_product"]),
            ("Host", _DEMO_PROJECT["host"]),
        ]
        for label, value in demo_fields:
            st.markdown(f"**{label}**")
            st.write(value)

        st.caption(
            "Example project path: this documentation case highlights source context, provenance context, "
            "traceability records, review prompts, and documentation package value. It is not a biological "
            "recommendation, not an experimental validation, and not a wet-lab readiness judgment."
        )
        st.caption(
            "Example project already has 6 documentation pathway steps for local review."
            if demo_exists
            else "Load a documentation-only Nicotiana example project to try the main workspace flow."
        )
        if st.button(
            "Load Nicotiana Example Project" if demo_exists else "Load Nicotiana Example Project",
            use_container_width=True,
            key="load_demo_btn",
            type="primary",
        ):
            _load_demo_project(projects, change_page)



def _render_developer_diagnostics(projects: list[dict[str, Any]]) -> None:
    if not _debug_enabled():
        return

    with st.expander("Developer diagnostics", expanded=False):
        status = _get_demo_seed_status(projects)
        st.write({"demo_ready": bool(status.get("ready"))})
        demo_project = _find_existing_demo(projects)
        st.write({"demo_project_id": demo_project.get("id") if demo_project else None})
        if demo_project:
            demo_steps = list_pathway_steps(int(demo_project["id"]))
            st.write({"current_pathway_step_count": len(demo_steps)})
            st.write({"current_step_names": [step.get("step_name") for step in demo_steps]})
        demo_state = st.session_state.get(_DEMO_STATUS_KEY)
        if demo_state:
            st.write(demo_state)


def _render_page_header() -> None:
    st.title("Pathway Projects")
    render_help_text(
        "Use Pathway Projects when expression vector design records need optional project grouping, review notes, "
        "or documentation traceability. Selecting a pathway project makes it the active project for Pathway Workspace."
    )
    with st.container(border=True):
        st.subheader("Quick start")
        st.markdown(
            "1. Start expression vector design preparation in Expression Wizard.\n"
            "2. Create or select a pathway project only when project-level grouping and traceability are needed.\n"
            "3. Open Pathway Workspace to review linked Expression Wizard design records and documentation notes.\n"
            "4. Use Project Outputs for documentation snapshots, reports, documentation-only export package review, and import preview review.\n"
            "5. To review an import package, go to **Pathway Workspace > Project Outputs > Import Preview**."
        )
        st.caption(
            "Expression Wizard is the primary expression vector design preparation path; Pathway Workspace is the optional project-level documentation workspace; "
            "Project Outputs covers documentation snapshots, reports, documentation-only export package review, and import preview review."
        )
    with st.expander("Import preview boundary", expanded=False):
        st.caption(
            "Review import package in Pathway Workspace > Project Outputs > Import Preview. Import Preview is a "
            "documentation-only package inspection for validation and dry-run planning; preview does not create a project, "
            "overwrite, or merge existing projects. Final import-as-new stays gated by the existing controls."
        )


def _render_just_created_banner(project_id: int) -> None:
    project = get_pathway_project(project_id)
    if not project:
        return
    st.success(f"Project **{project.get('name')}** is now your active project.")
    st.session_state.pop(_JUST_CREATED_KEY, None)


def _render_active_project_card(project: dict[str, Any], change_page) -> None:
    with st.container(border=True):
        st.subheader("Active Project")
        summary = dict(_project_summary_lines(project))
        render_compact_summary_cards(
            [
                ("Project", summary["Project name"], None),
                ("Target", summary["Target product"], None),
                ("Host", summary["Host / chassis"], None),
                ("Status", summary["Status"], summary["Last updated"]),
            ]
        )
        if summary["Description"] != "No description provided.":
            with st.expander("Project description", expanded=False):
                st.write(summary["Description"])
        st.caption(
            "Continue current project in Pathway Workspace to review pathway steps, linked Expression Wizard design "
            "records, traceability, review notes, and project outputs."
        )
        if st.button(
            "Open Pathway Workspace",
            key="active_open_workspace",
            type="primary",
        ):
            change_page("Pathway Workspace")
    _render_catalog_reference_overview_card(project)


def _render_catalog_reference_overview_card(project: dict[str, Any]) -> None:
    overview = build_project_catalog_reference_overview(project)
    st.subheader("Catalog Reference Overview")
    st.caption(
        "Documentation-level overview of linked catalog references, pinned snapshot context, source/provenance review, and record review gaps."
    )
    st.caption(
        "This overview is not recommendation, not validation, not readiness, and not prediction; it only summarizes recorded local documentation context."
    )
    st.caption(
        "Bridge fields keep record identifier, catalog reference context, source/provenance review, record review status, documentation note, and project documentation context visible before opening Pathway Workspace."
    )
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            st.metric("linked catalog references", overview.get("total_catalog_links", 0))
        with c2:
            st.metric("plant promoter references", overview.get("plant_promoter_link_count", 0))
        with c3:
            st.metric("pinned snapshots", overview.get("pinned_snapshot_count", 0))
        with c4:
            st.metric("review gaps", overview.get("missing_source_or_review_metadata_count", 0))
        st.caption(str(overview.get("coverage_note") or "No catalog reference context recorded."))

    rows = overview.get("linked_catalog_assets") or []
    if not rows:
        st.info("No catalog references are recorded for this project yet.")
        return

    with st.expander("Linked catalog reference rows", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Asset": row.get("asset_label", ""),
                        "Type": row.get("asset_type", ""),
                        "Record identifier": row.get("record_identifier", ""),
                        "Link role": row.get("linkage_role", ""),
                        "Reference origin": row.get("reference_origin", ""),
                        "Catalog source/status": row.get("catalog_source_status", ""),
                        "Source context readback": row.get("source_context_readback", ""),
                        "Host / chassis context readback": row.get("host_chassis_context_readback", ""),
                        "Review-needed context": row.get("review_needed_context", ""),
                        "Review gap context": row.get("metadata_gap_context", ""),
                        "Catalog reference context": row.get("catalog_reference_context", ""),
                        "Snapshot": row.get("snapshot_state", ""),
                        "Source": row.get("source_label", ""),
                        "Record review status": row.get("documentation_status", ""),
                        "Project documentation context": row.get("project_documentation_context", ""),
                        "Documentation note": row.get("documentation_note", ""),
                    }
                    for row in rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def _render_project_table(projects: list[dict[str, Any]]) -> None:
    if not projects:
        st.info("No pathway projects have been created yet.")
        return
    st.caption(
        "All Projects gives a compact overview of project, target product, host/context, status, updated time, and a small reference field."
    )
    _render_project_overview_rows(projects)


def _project_selector_label(project: dict[str, Any]) -> str:
    project_id = int(project["id"])
    name = str(project.get("name") or "Untitled project").strip()
    return f"{name} - Ref #{project_id}"


def _render_project_search_results(projects: list[dict[str, Any]], current_id: int | None) -> int | None:
    search_query = st.text_input(
        "Search existing projects",
        key=_PROJECT_SEARCH_KEY,
        placeholder="Type a project name, Ref #, target product, host, or status",
    )
    st.caption("Search filters existing records only. It does not edit, rename, or delete projects.")

    selected_project_id = _active_choice_from_state(projects) or current_id or int(projects[0]["id"])
    if search_query.strip():
        visible_projects = _filter_projects(projects, search_query)
        if not visible_projects:
            st.info("No existing projects match this search.")
            return selected_project_id
        visible_ids = {int(project["id"]) for project in visible_projects}
        if int(selected_project_id) not in visible_ids:
            selected_project_id = int(visible_projects[0]["id"])
        st.caption(f"Showing {len(visible_projects)} matching projects.")
    else:
        visible_projects = projects
        st.caption("Showing all existing projects.")

    selected_index = 0
    for index, project in enumerate(visible_projects):
        if int(project["id"]) == int(selected_project_id):
            selected_index = index
            break

    selected_project = st.selectbox(
        "Select project to preview",
        options=visible_projects,
        index=selected_index,
        key=_PROJECT_PREVIEW_SELECT_KEY,
        format_func=_project_selector_label,
    )
    st.caption("Typing filters the list only. Use Set as Active Project to change the active project.")
    if selected_project is not None:
        selected_project_id = int(selected_project["id"])
        st.session_state[_ACTIVE_PROJECT_CHOICE_KEY] = selected_project_id
    return selected_project_id


def _render_project_selector(projects: list[dict[str, Any]], change_page) -> None:
    if not projects:
        return

    current_id = st.session_state.get(CURRENT_PROJECT_KEY)
    _sync_active_choice(projects)

    with st.container(border=True):
        st.subheader("Continue a Project")
        st.caption("Search and preview an existing project, then activate it with a separate action.")
        selected_project_id = _render_project_search_results(projects, current_id)

    selected_project = next(project for project in projects if int(project["id"]) == int(selected_project_id))

    selected_id = int(selected_project["id"])
    selected_is_active = current_id == selected_id
    has_active_project = current_id is not None
    _render_selected_project_summary(selected_project, is_active=selected_is_active)
    action_spacer_left, action_left, action_right, action_spacer_right = st.columns([0.25, 1, 1.35, 0.25], gap="small")
    with action_left:
        if st.button(
            "Set as Active Project",
            key="set_active_project_btn",
            type="primary",
            disabled=selected_is_active,
        ):
            _set_current_project(selected_id)
            st.success(f"Active project set to: {selected_project.get('name', 'Untitled project')}")
            st.rerun()
    with action_right:
        if st.button(
            "Open Active Project in Pathway Workspace",
            key="open_selected_project_workspace",
            type="secondary",
            disabled=not has_active_project,
        ):
            _set_current_project(selected_id)
            change_page("Pathway Workspace")
        if not has_active_project:
            st.caption("Set a project as active first.")

    confirm_id = st.session_state.get(DELETE_CONFIRM_KEY)
    with st.expander("Project record removal", expanded=False):
        st.caption("Delete is separate from project activation and permanently removes the selected record.")
        if confirm_id == selected_id:
            st.warning(
                f"Confirm permanent deletion of '{selected_project.get('name', 'Untitled')}'. "
                "This will also delete its pathway steps and expression design links."
            )
            col_confirm, col_cancel = st.columns([1, 1], gap="small")
            with col_confirm:
                if st.button("Confirm delete", use_container_width=True, key="confirm_delete_btn"):
                    ok, message = delete_pathway_project(selected_id)
                    if ok:
                        st.session_state.pop(DELETE_CONFIRM_KEY, None)
                        st.session_state.pop(CURRENT_PROJECT_KEY, None)
                        st.session_state.pop(_ACTIVE_PROJECT_CHOICE_KEY, None)
                        st.session_state.pop(_JUST_CREATED_KEY, None)
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with col_cancel:
                if st.button("Cancel", use_container_width=True, key="cancel_delete_btn"):
                    st.session_state.pop(DELETE_CONFIRM_KEY, None)
                    st.rerun()
        elif st.button("Delete selected project", key="delete_project_btn", type="secondary"):
            st.session_state[DELETE_CONFIRM_KEY] = selected_id
            st.rerun()


def render(change_page) -> None:
    inject_tool_typography_css()
    _render_page_header()

    projects = list_pathway_projects()

    if projects:
        project_ids = [int(project["id"]) for project in projects]
        current_id = st.session_state.get(CURRENT_PROJECT_KEY)
        if current_id in project_ids:
            _set_current_project(current_id)
        elif len(projects) == 1:
            _set_current_project(project_ids[0])
        else:
            selected_id = _active_choice_from_state(projects)
            if selected_id in project_ids:
                st.session_state[_ACTIVE_PROJECT_CHOICE_KEY] = selected_id

    just_created_id = st.session_state.get(_JUST_CREATED_KEY)
    if just_created_id is not None:
        _render_just_created_banner(int(just_created_id))
        st.markdown("---")

    action_left, action_right = st.columns(2, gap="medium")
    with action_left:
        _render_create_project_form(change_page)
    with action_right:
        _render_quick_start(projects, change_page)

    st.markdown("---")

    current_id = st.session_state.get(CURRENT_PROJECT_KEY)
    current_project = get_pathway_project(current_id) if current_id else None

    if current_project:
        _render_active_project_card(current_project, change_page)
    else:
        with st.container(border=True):
            st.subheader("Active Project")
            if projects and len(projects) == 1:
                _set_current_project(int(projects[0]["id"]))
                st.info("Active project set from the available project.")
            else:
                st.info("No active project selected. Create a new project or load the example project to get started.")

    if projects:
        st.markdown("---")
        with st.expander(f"All Projects ({len(projects)})", expanded=False):
            _render_project_table(projects)
        _render_project_selector(projects, change_page)
        _render_developer_diagnostics(projects)
