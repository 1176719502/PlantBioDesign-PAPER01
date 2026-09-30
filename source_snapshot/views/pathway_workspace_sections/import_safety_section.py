from __future__ import annotations

from typing import Any

import streamlit as st

from services.project_import_package_safety_checker import (
    STATUS_NOT_EVALUATED,
    STATUS_PASS,
    STATUS_USER_SUMMARIES,
)


def _render_import_preview_list(title: str, values: list[Any], empty_message: str) -> None:
    st.markdown(f"**{title}**")
    if not values:
        st.info(empty_message)
        return
    for value in values[:50]:
        st.markdown(f"- {value}")
    if len(values) > 50:
        st.caption(f"Showing 50 of {len(values)} entries.")


def render_import_safety_section(report: dict[str, Any]) -> None:
    st.markdown("**Import Package Safety Check Report**")
    overall_status = str(report.get("overall_status") or STATUS_NOT_EVALUATED)
    st.caption(f"overall_status: {overall_status}")
    st.caption(str(report.get("safe_user_summary") or STATUS_USER_SUMMARIES.get(overall_status, STATUS_USER_SUMMARIES[STATUS_NOT_EVALUATED])))
    st.caption("This is a read-only safety check.")
    st.caption("This report is documentation-only.")
    st.caption("This report does not import or modify any project.")
    st.caption("No database writes are performed.")
    st.caption("Blocked / NO-GO safety states stop the separate gated create-as-new action.")
    st.caption(
        "This report never creates a project. If all gates later pass, only a separate local documentation-only "
        "project creation action may run."
    )
    st.caption("This report does not certify experimental readiness.")
    st.caption("This report does not predict yield.")
    st.caption("This report does not optimize pathways.")
    st.caption("This report does not provide wet-lab instructions.")
    st.caption(STATUS_USER_SUMMARIES[STATUS_PASS])
    st.caption(STATUS_USER_SUMMARIES["WARNING"])
    st.caption(STATUS_USER_SUMMARIES["BLOCKED"])
    st.caption(STATUS_USER_SUMMARIES[STATUS_NOT_EVALUATED])

    identity = report.get("package_identity") if isinstance(report.get("package_identity"), dict) else {}
    st.markdown("**Package identity**")
    for key in ("project_id", "project_name", "package_version", "exported_at", "app_context", "calculated_package_sha256"):
        st.caption(f"- {key}: {identity.get(key) or 'Not available'}")

    _render_import_preview_list("Blocking issues", list(report.get("blocking_issues") or []), "No blocking issues found.")
    _render_import_preview_list("Warnings", list(report.get("warnings") or []), "No warnings found.")

    st.markdown("**Check items**")
    for item in report.get("check_items") or []:
        if not isinstance(item, dict):
            continue
        st.caption(
            f"- {item.get('status')}: {item.get('label')} — {item.get('summary')} "
            f"Detail: {item.get('detail')} Guidance: {item.get('user_guidance')}"
        )

    _render_import_preview_list("Next steps", list(report.get("next_steps") or []), "No next steps available.")
