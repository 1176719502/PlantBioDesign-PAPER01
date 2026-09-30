"""views/Dashboard.py -- Saved Designs, BioDesign Studio."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core.i18n import t as _t
from core.session_keys import SK
from services.design_saver import format_saved_at_display, get_saved_design_rows


TYPE_LABEL_MAP = {
    "Vector": _t("dashboard.type.vector"),
    "Expression Design": _t("dashboard.type.expression_design"),
    "Design": _t("dashboard.type.design"),
    "Sequence": _t("dashboard.type.sequence"),
}


def _default_saved_design_filters() -> dict[str, str]:
    return {
        "pw_search_query": "",
        "pw_type_filter": "All",
        "pw_sort_order": "Newest first",
    }


def _clear_saved_design_filters() -> None:
    for key, value in _default_saved_design_filters().items():
        st.session_state[key] = value


def _build_result_count_text(visible: int, total: int) -> str:
    return _t("dashboard.results_count", visible=visible, total=total)


def _inject_css() -> None:
    st.markdown(
        """
<style>
.pw-header{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0 18px 0;border-bottom:2px solid #e3e8ef;margin-bottom:24px;flex-wrap:wrap;}
.pw-logo-row{display:flex;align-items:center;gap:14px;}
.pw-logo-icon{width:44px;height:44px;background:linear-gradient(135deg,#00875a 0%,#005c3c 100%);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0;}
.pw-title{font-size:24px;font-weight:700;color:#1a1f2e;letter-spacing:0;line-height:1.2;}
.pw-subtitle{font-size:15px;color:#6b7280;margin-top:4px;line-height:1.45;max-width:78ch;}
.pw-header-right{display:flex;align-items:center;gap:10px;}
.pw-pill{background:#f0fdf4;border:1px solid #bbf7d0;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;color:#15803d;}
.pw-clock{font-family:'IBM Plex Mono',monospace;font-size:13px;color:#9ca3af;}
.pw-sec{font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.8px;padding-bottom:8px;margin-bottom:14px;border-bottom:1px solid #e3e8ef;}
.pw-empty{text-align:center;padding:52px 24px;background:#fafafa;border:1px dashed #d1d5db;border-radius:10px;color:#9ca3af;}
.pw-empty-icon{font-size:38px;margin-bottom:12px;}
.pw-empty-title{font-size:15px;font-weight:600;color:#6b7280;margin-bottom:6px;}
.pw-empty-sub{font-size:14px;line-height:1.5;}
.pw-preview{background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-top:10px;}
.pw-preview-title{font-size:.84rem;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.4px;margin-bottom:10px;}
.pw-prow{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:.92rem;line-height:1.45;flex-wrap:wrap;}
.pw-prow:last-child{border-bottom:none;}
.pw-plabel{color:#6b7280;min-width:130px;flex-shrink:0;}
.pw-pval{color:#111827;font-weight:500;overflow-wrap:anywhere;}
.pw-footer{border-top:1px solid #e3e8ef;padding:14px 0 0 0;margin-top:32px;display:flex;justify-content:space-between;gap:10px;font-size:13px;line-height:1.45;color:#9ca3af;flex-wrap:wrap;}
[data-testid="stDataFrame"]{border-radius:8px;overflow:hidden;}
@media (max-width: 760px){
  .pw-logo-row{align-items:flex-start}
  .pw-logo-icon{width:38px;height:38px;font-size:20px}
  .pw-title{font-size:20px}
  .pw-subtitle{font-size:14px}
  .pw-header-right{width:100%;justify-content:flex-start;flex-wrap:wrap}
  .pw-plabel{min-width:110px}
  .pw-preview{padding:14px}
}
</style>
""",
        unsafe_allow_html=True,
    )


def _get_projects_from_db(
    search: str | None = None,
    type_filter: str = "All",
    sort_order: str = "Newest first",
) -> list[dict]:
    types = None if type_filter == "All" else type_filter
    service_sort_order = "asc" if sort_order == "Oldest first" else "desc"
    return get_saved_design_rows(search=search, types=types, sort_order=service_sort_order)


def _normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def _matches_search(project: dict, query: str) -> bool:
    query_norm = _normalize_text(query)
    if not query_norm:
        return True
    values = [project.get("Name"), project.get("Gene"), project.get("Host"), project.get("_gene"), project.get("_host")]
    return any(query_norm in _normalize_text(value) for value in values)


def _filter_and_sort_projects(projects: list[dict], search_query: str, type_filter: str, sort_order: str) -> list[dict]:
    filtered = [project for project in projects if _matches_search(project, search_query)]
    if type_filter != "All":
        filtered = [project for project in filtered if project.get("Type") == type_filter]
    reverse = sort_order != "Oldest first"
    return sorted(filtered, key=lambda project: _normalize_text(project.get("Saved")), reverse=reverse)


def _display_saved_value(project: dict) -> str:
    return format_saved_at_display(project.get("Saved"))


def _display_project(project: dict) -> dict:
    return {**project, "Saved": _display_saved_value(project)}


def _display_projects(projects: list[dict]) -> list[dict]:
    return [_display_project(project) for project in projects]


def _saved_design_option_key(project: dict) -> str:
    return str(project.get("_load_key") or project.get("_design_id") or project.get("Name") or "")


def _saved_design_option_label(project: dict) -> str:
    return str(project.get("Name") or project.get("_load_key") or "")


def _preview_card(proj: dict) -> None:
    def _r(label: str, val) -> str:
        value = str(val) if val not in (None, "", "--", 0) else f"<span style='color:#9ca3af'>{_t('dashboard.not_recorded')}</span>"
        return f"<div class='pw-prow'><span class='pw-plabel'>{label}</span><span class='pw-pval'>{value}</span></div>"

    step = proj.get("_step")
    step_str = _t("dashboard.step_progress", step=step) if step else None
    seq_len = proj["Length (bp)"]
    n_primers = proj.get("_n_primers")
    n_issues = proj.get("_n_issues")
    rows_html = (
        _r(_t("dashboard.preview.gene_construct"), proj.get("_gene") or proj["Name"])
        + _r(_t("dashboard.preview.host"), proj.get("_host"))
        + _r(_t("dashboard.preview.cloning_method"), proj.get("_cloning"))
        + _r(_t("dashboard.preview.vector_suggestion"), proj.get("_vector"))
        + _r(_t("dashboard.preview.sequence_length"), f"{seq_len} bp" if seq_len else None)
        + _r(_t("dashboard.preview.gc_content"), proj["GC%"] if proj["GC%"] != "--" else None)
        + _r(_t("dashboard.preview.primer_count"), str(n_primers) if n_primers is not None else None)
        + _r(_t("dashboard.preview.validation_issue_count"), str(n_issues) if n_issues is not None else None)
        + _r(_t("dashboard.preview.wizard_progress"), step_str)
        + _r(_t("dashboard.preview.saved_time"), proj["Saved"])
    )
    st.markdown(
        f"<div class='pw-preview'><div class='pw-preview-title'>{_t('dashboard.preview.title')}</div>{rows_html}</div>",
        unsafe_allow_html=True,
    )
    st.caption(_t("dashboard.preview.status_clarification"))


def render(change_page) -> None:  # noqa: C901
    _inject_css()
    now = datetime.now()
    try:
        from components.design_modules.db_utils import init_db

        init_db()
    except Exception:
        pass

    st.markdown(
        f"""
    <div class="pw-header">
      <div class="pw-logo-row">
        <div class="pw-logo-icon">BD</div>
        <div>
          <div class="pw-title">{_t('dashboard.title')}</div>
          <div class="pw-subtitle">{_t('dashboard.subtitle')}</div>
        </div>
      </div>
      <div class="pw-header-right">
        <span class="pw-pill">{_t('dashboard.ready')}</span>
        <span class="pw-clock">{now.strftime('%Y-%m-%d &nbsp; %H:%M')}</span>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    all_projects = _get_projects_from_db()
    filtered_projects = all_projects
    visible_projects = _display_projects(filtered_projects)
    st.markdown(f'<div class="pw-sec">{_t("dashboard.saved_designs")}</div>', unsafe_allow_html=True)
    st.caption(_t("dashboard.saved_snapshot_clarification"))

    if not all_projects:
        st.markdown(
            f"<div class='pw-empty'><div class='pw-empty-icon'>🧬</div><div class='pw-empty-title'>{_t('dashboard.empty_title')}</div><div class='pw-empty-sub'>{_t('dashboard.empty_body')}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        search_col, filter_col, sort_col, clear_col = st.columns([2.2, 1.15, 1.15, 0.9], gap="small")
        with search_col:
            search_query = st.text_input(_t("dashboard.search_label"), key="pw_search_query", placeholder=_t("dashboard.search_placeholder"))
        with filter_col:
            available_types = sorted({p.get("Type", "") for p in all_projects if p.get("Type")})
            type_filter = st.selectbox(
                _t("dashboard.filter_label"),
                options=["All", *available_types],
                key="pw_type_filter",
                format_func=lambda value: _t("dashboard.filter_all") if value == "All" else TYPE_LABEL_MAP.get(value, value),
            )
        with sort_col:
            sort_order = st.selectbox(_t("dashboard.sort_label"), options=["Newest first", "Oldest first"], key="pw_sort_order")
        with clear_col:
            st.write("")
            if st.button(_t("dashboard.clear_filters"), key="pw_clear_filters_btn", use_container_width=True):
                _clear_saved_design_filters()
                st.rerun()

        filtered_projects = _get_projects_from_db(search_query, type_filter, sort_order)
        visible_projects = _display_projects(filtered_projects)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.caption(_build_result_count_text(len(filtered_projects), len(all_projects)))

        if not filtered_projects:
            st.info(_t("dashboard.no_match"))
        else:
            df_display = pd.DataFrame(
                [
                    {
                        "Name": p["Name"],
                        "Gene": p["Gene"],
                        "Host": p["Host"],
                        "Length (bp)": p["Length (bp)"],
                        "GC%": p["GC%"],
                        "Type": TYPE_LABEL_MAP.get(p["Type"], p["Type"]),
                        "Saved": _display_saved_value(p),
                    }
                    for p in filtered_projects
                ]
            )
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Name": st.column_config.TextColumn(_t("dashboard.table.name"), width="large"),
                    "Gene": st.column_config.TextColumn(_t("dashboard.table.gene"), width="small"),
                    "Host": st.column_config.TextColumn(_t("dashboard.table.host"), width="medium"),
                    "Length (bp)": st.column_config.NumberColumn(_t("dashboard.table.length"), width="small", format="%d bp"),
                    "GC%": st.column_config.TextColumn("GC%", width="small"),
                    "Type": st.column_config.TextColumn(_t("dashboard.table.type"), width="small"),
                    "Saved": st.column_config.TextColumn(_t("dashboard.table.saved"), width="medium"),
                },
            )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown(f'<div class="pw-sec">{_t("dashboard.load_selected")}</div>', unsafe_allow_html=True)
    st.caption(_t("dashboard.load_snapshot_clarification"))

    with st.container(border=True):
        if not all_projects:
            st.info(_t("dashboard.no_available_designs"))
        elif not filtered_projects:
            st.info(_t("dashboard.no_loadable_with_filters"))
        else:
            project_options = {_saved_design_option_key(p): p for p in visible_projects}
            project_keys = list(project_options.keys())
            current_selection = st.session_state.get("pw_project_select")
            selected_index = project_keys.index(current_selection) if current_selection in project_keys else 0
            col_select, col_load, col_new, col_del = st.columns([3, 1, 1, 1], gap="small")

            with col_select:
                selected_key = st.selectbox(
                    _t("dashboard.select_design"),
                    options=project_keys,
                    index=selected_index,
                    key="pw_project_select",
                    label_visibility="collapsed",
                    placeholder=_t("dashboard.select_placeholder"),
                    help=_t("dashboard.select_help"),
                    format_func=lambda key: _saved_design_option_label(project_options.get(key, {})),
                )
                selected_name = _saved_design_option_label(project_options.get(selected_key, {}))
            with col_load:
                load_clicked = st.button(_t("dashboard.load_button"), key="pw_load_btn", type="primary", use_container_width=True)
            with col_new:
                if st.button(_t("dashboard.new_button"), key="pw_new_btn", use_container_width=True):
                    from services.pathway_wizard_context import clear_pathway_context_for_independent_wizard_entry
                    from services.wizard_state_service import reset_wizard_for_new_design

                    clear_pathway_context_for_independent_wizard_entry()
                    st.session_state.pop("design_session", None)
                    reset_wizard_for_new_design(st.session_state)
                    for key in [SK.ACTIVE_SEQ, SK.ACTIVE_HOST, SK.ACTIVE_FEATURES, SK.ACTIVE_NAME, SK.DASHBOARD_PROJECT]:
                        st.session_state.pop(key, None)
                    change_page("Expression Wizard")
            with col_del:
                confirm_key = "pw_confirm_delete"
                armed = st.session_state.get(confirm_key) == selected_key
                if armed:
                    if st.button(_t("dashboard.confirm_delete_button"), key="pw_del_confirm_btn", type="primary", use_container_width=True):
                        try:
                            from services.design_saver import delete_wizard_design

                            ok, msg = delete_wizard_design(selected_key)
                            if ok:
                                st.session_state.pop(confirm_key, None)
                                st.success(_t("dashboard.delete_success", name=selected_name))
                                st.rerun()
                            else:
                                st.error(_t("dashboard.delete_failed", message=msg))
                        except Exception as exc:
                            st.error(_t("dashboard.delete_error", error=exc))
                else:
                    if st.button(_t("dashboard.delete_button"), key="pw_del_btn", use_container_width=True):
                        st.session_state[confirm_key] = selected_key
                        st.rerun()

            selected_project = project_options.get(selected_key)
            if selected_project:
                _preview_card(_display_project(selected_project))

            if load_clicked and selected_project:
                try:
                    from core.design_session import SessionController
                    from services.design_saver import load_wizard_design
                    from services.pathway_wizard_context import clear_pathway_context_for_independent_wizard_entry
                    from services.wizard_state_service import (
                        prepare_loaded_design_session,
                        sync_global_context_from_design_session,
                    )

                    ok, result = load_wizard_design(selected_key)
                    if ok:
                        clear_pathway_context_for_independent_wizard_entry()
                        ctrl = SessionController()
                        ctrl.save(result)
                        prepare_loaded_design_session(st.session_state, result)
                        sync_global_context_from_design_session(st.session_state, result, active_name=selected_name)
                        st.session_state[SK.DASHBOARD_PROJECT] = selected_key
                        st.success(_t("dashboard.load_success", name=selected_name, length=selected_project["Length (bp)"]))
                        change_page("Expression Wizard")
                    else:
                        st.error(_t("dashboard.load_failed", result=result))
                except Exception as exc:
                    st.error(_t("dashboard.load_error", error=exc))

        if all_projects:
            st.caption(_t("dashboard.bottom_help"))

    st.markdown(
        f"""
    <div class="pw-footer">
      <span>{_t('dashboard.footer.disclaimer')}</span>
      <span>{_t('dashboard.footer.local_mode')} &nbsp;&middot;&nbsp; {now.strftime('%H:%M')} &nbsp;&middot;&nbsp; &copy; 2026 BioDesign Studio</span>
    </div>
    """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Saved Designs", page_icon="BD")
    render(lambda page: st.toast(f"-> {page}"))
