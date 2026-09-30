from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

from services.project_import_dry_run_planner import build_project_import_dry_run_plan
from services.project_import_execution_gate_service import (
    IMPORT_EXECUTION_PREFLIGHT_INTRO_COPY,
    build_project_import_execution_gate_state,
)
from services.project_import_execution_result_presenter import present_import_execution_result
from services.pathway_repository import list_pathway_documentation_snapshots, list_pathway_projects
from services.project_import_package_safety_checker import STATUS_BLOCKED, build_import_package_safety_check_report
from services.project_import_package_validator import validate_project_import_package
from services.project_import_service import execute_project_import_as_new_project
from views.pathway_workspace_sections.import_safety_section import render_import_safety_section
from views.pathway_workspace_sections.project_documentation_package_section import (
    render_project_documentation_package_import_panel,
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


def _render_import_validation_report(report: dict[str, Any]) -> None:
    st.markdown("**Validation status**")
    if report.get("is_valid"):
        st.success("Valid package")
    else:
        st.error("Invalid package")

    st.markdown("**Package metadata**")
    st.markdown(f"- package_version: {report.get('package_version') or 'Not available'}")
    st.markdown(f"- project_name: {report.get('project_name') or 'Not available'}")
    st.markdown(f"- boundary_confirmed: {bool(report.get('boundary_confirmed'))}")
    st.markdown(f"- json_files_valid: {bool(report.get('json_files_valid'))}")

    with st.expander("Included files", expanded=False):
        _render_import_preview_list(
            "Included files",
            list(report.get("included_files") or []),
            "No included files detected.",
        )
    _render_import_preview_list("Errors", list(report.get("errors") or []), "No validation errors found.")
    _render_import_preview_list("Warnings", list(report.get("warnings") or []), "No validation warnings found.")
    _render_import_preview_list("Unsafe files", list(report.get("unsafe_files") or []), "No unsafe files detected.")


def _format_import_mode(value: Any) -> str:
    mode = str(value or "import_as_new_project_only")
    return mode.replace("_", " ")


def _render_import_dry_run_plan(plan: dict[str, Any]) -> None:
    st.markdown("**Dry-run import plan**")
    st.caption(
        "Read-only dry-run summary. It does not import, create, overwrite, combine, or modify any project. "
        "No database writes are performed."
    )

    if not plan.get("is_plan_available"):
        st.caption("Validation-only preview: dry-run create counts are not available for this package.")
        return

    st.caption(
        f"Source: {plan.get('source_project_name') or 'Not available'} | "
        f"Proposed: {plan.get('proposed_project_name') or 'Not available'} | "
        f"Mode: {_format_import_mode(plan.get('import_mode'))} | "
        f"Read-only: {'yes' if plan.get('read_only') else 'no'} | "
        f"Database writes performed: {str(bool(plan.get('database_writes_performed'))).lower()}"
    )

    would_create = plan.get("would_create") if isinstance(plan.get("would_create"), dict) else {}
    st.caption(
        "Would create preview: "
        f"Project {would_create.get('project', 0)}, "
        f"Pathway steps {would_create.get('pathway_steps', 0)}, "
        f"Test record summaries {would_create.get('test_record_summaries', 0)}, "
        f"Linked expression references {would_create.get('linked_expression_design_references', 0)}, "
        f"Linked tool artifact summaries {would_create.get('linked_tool_artifact_summaries', 0)}."
    )

    id_remapping = plan.get("id_remapping_required") if isinstance(plan.get("id_remapping_required"), dict) else {}
    remapping_keys = [
        key
        for key in ("project_id", "pathway_step_ids", "linked_tool_artifact_ids", "test_record_ids")
        if id_remapping.get(key)
    ]
    if remapping_keys:
        st.caption(f"ID remapping required: {', '.join(remapping_keys)}.")

    with st.expander("Boundary statement", expanded=False):
        for boundary_line in [
            "documentation-only",
            "does not certify experimental readiness",
            "does not predict yield",
            "does not optimize pathways",
            "does not provide wet-lab protocols",
            "linked artifacts remain computational previews / review records only",
        ]:
            st.caption(f"- {boundary_line}")


def _render_import_execution_preflight_panel(gate_state: dict[str, Any]) -> None:
    if not gate_state.get("preflight_panel_available"):
        return

    with st.container(border=True):
        st.markdown("**Import Execution Preflight Review**")
        for line in gate_state.get("preflight_intro_copy") or IMPORT_EXECUTION_PREFLIGHT_INTRO_COPY:
            st.caption(line)
        for section_title, section_items in gate_state.get("preflight_items") or []:
            st.markdown(f"**{section_title}**")
            for item in section_items:
                st.caption(f"- {item}")
        st.caption(
            "Final confirmation status: explicit confirmation checkbox is required before creation. "
            "Creation is enabled only when validation, safety, dry-run, and final confirmation gates pass."
        )
        st.caption(f"Create action enabled: {str(bool(gate_state['can_enable_create_action'])).lower()}")


def _package_fingerprint(zip_bytes: bytes) -> str:
    return hashlib.sha256(zip_bytes).hexdigest()


def _stable_source_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _source_identity_from_plan(dry_run_plan: dict[str, Any], validation_report: dict[str, Any], package_fingerprint: str) -> dict[str, str]:
    source_project_name = _stable_source_text(
        dry_run_plan.get("source_project_name") or validation_report.get("project_name")
    )
    source_project_id = _stable_source_text(
        dry_run_plan.get("source_project_id")
        or dry_run_plan.get("project_id")
        or validation_report.get("source_project_id")
        or validation_report.get("project_id")
    )
    return {
        "source_project_name": source_project_name,
        "source_project_id": source_project_id,
        "package_fingerprint": _stable_source_text(package_fingerprint),
    }


def _snapshot_payload_source_identity(snapshot: dict[str, Any]) -> dict[str, str]:
    payload = snapshot.get("snapshot_payload") if isinstance(snapshot, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    id_summary = payload.get("id_remapping_summary") if isinstance(payload.get("id_remapping_summary"), dict) else {}
    project_id_summary = id_summary.get("project_id") if isinstance(id_summary.get("project_id"), dict) else {}
    return {
        "source_project_name": _stable_source_text(payload.get("source_project_name")),
        "source_project_id": _stable_source_text(payload.get("source_project_id") or project_id_summary.get("source_id")),
        "package_fingerprint": _stable_source_text(payload.get("package_fingerprint")),
    }


def _source_identity_matches(candidate: dict[str, str], expected: dict[str, str]) -> bool:
    for key in ("package_fingerprint", "source_project_id"):
        if expected.get(key) and candidate.get(key) and expected[key] == candidate[key]:
            return True
    return False


def _project_name_matches_source_package(project: dict[str, Any], dry_run_plan: dict[str, Any]) -> bool:
    project_name = _stable_source_text(project.get("name"))
    proposed_name = _stable_source_text(dry_run_plan.get("proposed_project_name"))
    if not project_name or not proposed_name:
        return False
    return project_name == proposed_name or project_name.startswith(f"{proposed_name} (")


def _existing_documentation_project_result(
    project: dict[str, Any],
    source_identity: dict[str, str] | None = None,
    match_reason: str = "source identity",
) -> dict[str, Any]:
    return {
        "project_id": project.get("id"),
        "project_name": project.get("name") or "Not available",
        "matched_source_project_name": (source_identity or {}).get("source_project_name"),
        "matched_source_project_id": (source_identity or {}).get("source_project_id"),
        "match_reason": match_reason,
    }


def _find_existing_documentation_project_from_same_package(
    dry_run_plan: dict[str, Any],
    validation_report: dict[str, Any],
    package_fingerprint: str,
) -> dict[str, Any] | None:
    expected_identity = _source_identity_from_plan(dry_run_plan, validation_report, package_fingerprint)
    for project in list_pathway_projects():
        project_id = project.get("id")
        if not project_id:
            continue
        for snapshot in list_pathway_documentation_snapshots(project_id):
            payload = snapshot.get("snapshot_payload") if isinstance(snapshot, dict) else {}
            if not isinstance(payload, dict) or payload.get("raw_payload_restored") is not False:
                continue
            source_identity = _snapshot_payload_source_identity(snapshot)
            if _source_identity_matches(source_identity, expected_identity):
                return _existing_documentation_project_result(project, source_identity, "import audit payload")
    return None


def _is_completed_creation_result(result: dict[str, Any]) -> bool:
    return bool(
        result.get("created_project_id")
        and (result.get("execution_status") == "completed" or result.get("executed") is True)
    )


def _format_created_counts_summary(created_counts: Any) -> str:
    if not isinstance(created_counts, dict) or not created_counts:
        return "No created count details available."
    return ", ".join(f"{key}: {value}" for key, value in created_counts.items())


def _build_import_preview_creation_state_model(
    gate_state: dict[str, Any],
    *,
    safety_blocked: bool,
    already_created_from_package: bool,
    existing_documentation_project: dict[str, Any] | None,
    duplicate_copy_confirmed: bool,
) -> dict[str, Any]:
    disabled_reasons = list(gate_state.get("disabled_reasons") or [])
    can_create = bool(gate_state.get("can_enable_create_action"))

    if safety_blocked:
        can_create = False
        disabled_reasons.append("Preview/review blocked: safety review is blocked, so no local documentation project will be created.")
    if already_created_from_package:
        can_create = False
        disabled_reasons.append("A documentation project was already created from this package in this session.")
    if existing_documentation_project and not duplicate_copy_confirmed:
        can_create = False
        disabled_reasons.append(
            "A documentation-only project from this package appears to already exist; confirm another documentation-only copy before creation."
        )

    if can_create:
        status_label = "Local documentation project creation allowed after explicit confirmation."
        status_caption = (
            "This action can create a local documentation-only project from the reviewed package. "
            "It is not biological execution, validation, optimization, recommendation, or a wet-lab readiness judgment."
        )
    else:
        status_label = "Preview/review blocked for local documentation project creation."
        status_caption = (
            "You can still inspect the package preview, validation report, safety review, and dry-run plan, "
            "but local documentation project creation is unavailable in the current state."
        )

    return {
        "can_create": can_create,
        "disabled_reasons": disabled_reasons,
        "status_label": status_label,
        "status_caption": status_caption,
    }


def _remember_created_documentation_project(result: dict[str, Any], package_fingerprint: str | None = None) -> None:
    created_project_id = result.get("created_project_id")
    if not created_project_id:
        return
    st.session_state["pathway_current_project_id"] = created_project_id
    st.session_state["project_import_create_result"] = result
    st.session_state["project_import_execution_last_result"] = result
    st.session_state["project_import_execution_created_project_id"] = created_project_id
    st.session_state["project_import_execution_imported_project_name"] = result.get("imported_project_name")
    if package_fingerprint:
        st.session_state["project_import_create_last_package_fingerprint"] = package_fingerprint
        created_by_package = st.session_state.setdefault("project_import_create_created_by_package", {})
        if isinstance(created_by_package, dict):
            created_by_package[package_fingerprint] = created_project_id


def _render_import_execution_result_summary(result: dict[str, Any], package_fingerprint: str | None = None) -> None:
    status = result.get("execution_status")
    presenter_status = "success" if status == "completed" else status
    model = present_import_execution_result({**result, "execution_status": presenter_status})
    is_complete_success = model.get("execution_status") == "success"

    with st.container(border=True):
        st.markdown("**Import Execution Result Summary**")
        st.caption("Documentation project creation summary only. This does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab protocols.")
        st.caption(f"execution_status: {result.get('execution_status')}")
        st.caption(f"status_label: {model['status_label']}")
        st.caption(f"created_project_id: {model.get('created_project_id') or 'None'}")
        st.caption(f"imported_project_name: {model.get('imported_project_name') or 'Not available'}")
        st.caption(f"created_counts: {_format_created_counts_summary(model.get('created_counts'))}")
        if is_complete_success and model.get("created_project_id"):
            _remember_created_documentation_project(result, package_fingerprint)
            st.success("Documentation project created.")
            st.caption(f"New documentation project name: {model.get('imported_project_name') or 'Not available'}")
            st.caption(f"New documentation project ID: {model.get('created_project_id')}")
            st.caption(f"Created count summary: {_format_created_counts_summary(model.get('created_counts'))}")
            st.info("The new documentation-only project is now available in Pathway Projects / Pathway Workspace.")
            if st.button(
                "Open created documentation project in Pathway Workspace",
                key="project_import_open_created_documentation_project_in_pathway_workspace",
                use_container_width=True,
            ):
                st.session_state["pathway_current_project_id"] = model["created_project_id"]
                if hasattr(st, "rerun"):
                    st.rerun()
        warnings = list(model.get("warnings") or [])
        if warnings:
            st.markdown("**Warnings**")
            for warning in warnings:
                st.caption(f"- {warning}")
        errors = list(model.get("errors") or [])
        if errors:
            st.markdown("**Errors or blocking reasons**")
            for error in errors:
                st.caption(f"- {error}")
        st.caption(model["limited_rollback_note"])
        st.caption(model["documentation_only_boundary"])
        st.caption(model["no_readiness_or_evidence_boost_statement"])
        st.caption("Linked artifacts remain computational previews / review records only.")


def _render_import_execution_gated_skeleton(
    validation_report: dict[str, Any],
    dry_run_plan: dict[str, Any],
    zip_bytes: bytes,
    safety_report: dict[str, Any],
) -> None:
    safety_blocked = safety_report.get("overall_status") == STATUS_BLOCKED
    package_fingerprint = _package_fingerprint(zip_bytes)
    created_by_package = st.session_state.get("project_import_create_created_by_package")
    created_project_for_package = (
        created_by_package.get(package_fingerprint) if isinstance(created_by_package, dict) else None
    )
    already_created_from_package = bool(created_project_for_package)
    existing_documentation_project = _find_existing_documentation_project_from_same_package(
        dry_run_plan,
        validation_report,
        package_fingerprint,
    )
    duplicate_copy_confirmed = False
    if existing_documentation_project:
        st.warning("A documentation-only project from this package appears to already exist.")
        st.caption(f"Existing project name: {existing_documentation_project.get('project_name') or 'Not available'}")
        st.caption(f"Existing project ID: {existing_documentation_project.get('project_id') or 'Not available'}")
        st.caption(f"Existing package match: {existing_documentation_project.get('match_reason') or 'source identity'}")
        st.info("Review note: open the existing documentation-only project instead of creating another copy.")
        duplicate_copy_confirmed = st.checkbox(
            "Create another documentation-only copy anyway.",
            value=False,
            key="project_import_create_another_documentation_copy_confirmation",
            help="Required only when a documentation-only project from the same package already exists.",
        )
    confirmation_checked = st.checkbox(
        "I understand this creates a new documentation-only project and does not certify experimental readiness",
        value=False,
        key="project_import_create_new_documentation_project_confirmation",
        help=(
            "Required final confirmation. The package creates a new documentation project only; no overwrite, "
            "no merge, no raw payload_json restoration, and no wet-lab success claim."
        ),
    )
    st.caption(
        "Final confirmation is required before creating a new documentation project. This action does not overwrite, merge, certify readiness, predict yield, optimize pathways, or provide wet-lab protocols."
    )
    gate_state = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=confirmation_checked and not safety_blocked,
    )
    if not gate_state["can_show_gated_block"]:
        return

    creation_state = _build_import_preview_creation_state_model(
        gate_state,
        safety_blocked=safety_blocked,
        already_created_from_package=already_created_from_package,
        existing_documentation_project=existing_documentation_project,
        duplicate_copy_confirmed=duplicate_copy_confirmed,
    )

    _render_import_execution_preflight_panel(gate_state)

    with st.container(border=True):
        st.markdown("**Create New Documentation Project**")
        st.caption(creation_state["status_label"])
        st.caption(creation_state["status_caption"])
        st.caption("Creates a new documentation-only Pathway project from this import package after all gates pass.")
        st.caption(
            "Documentation-only, import as new project only, no overwrite, no merge, no raw payload_json restoration. "
            "This does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab instructions."
        )
        st.caption("Linked artifacts remain computational previews / review records only.")
        st.caption(f"Create action enabled: {str(bool(creation_state['can_create'])).lower()}")
        if already_created_from_package:
            st.info("A documentation project was already created from this package in this session.")
            st.caption(f"Existing documentation project ID for this package: {created_project_for_package}")
        for reason in creation_state["disabled_reasons"]:
            st.caption(f"- {reason}")
        if st.button(
            "Create New Documentation Project",
            key="project_import_execute_create_new_documentation_project",
            disabled=not creation_state["can_create"],
            use_container_width=True,
        ):
            if not creation_state["can_create"]:
                st.error("Local documentation project creation is blocked in the current state. No database write was performed.")
            else:
                result = execute_project_import_as_new_project(zip_bytes, enable_database_write=True)
                st.session_state["project_import_create_result"] = result
                st.session_state["project_import_execution_last_result"] = result
                if _is_completed_creation_result(result):
                    _remember_created_documentation_project(result, package_fingerprint)

    last_result = st.session_state.get("project_import_create_result") or st.session_state.get("project_import_execution_last_result")
    if isinstance(last_result, dict):
        _render_import_execution_result_summary(last_result, package_fingerprint)


def render_import_preview_section() -> None:
    st.markdown("**Project Import Package Preview**")
    st.caption(
        "You are in Pathway Workspace > Project Outputs > Import Preview. Review import package here before any "
        "gated import-as-new action."
    )
    st.caption(
        "Import Preview is documentation-only package inspection for validation and dry-run planning. "
        "The preview step itself does not create a project, overwrite, merge, restore, import, or modify existing projects."
    )
    st.caption("Preview only: no database writes, no project creation, no overwrite, no merge, and no restore.")
    st.caption("No database writes are performed. This preview does not import or modify any project.")
    st.caption(
        "Boundary: this preview does not import or modify any project, certify experimental readiness, predict yield, "
        "optimize pathways, or provide wet-lab protocols."
    )
    st.caption(
        "If a blocked state is shown below, it applies only to the separate gated create-as-new action and not to "
        "this read-only preview itself."
    )
    st.caption("It validates package structure and shows a dry-run import plan.")
    st.caption(
        "A separate gated action below may create a local documentation-only project only after package validation, safety review, dry-run planning, and explicit final confirmation."
    )
    st.caption(
        "If creation becomes allowed, it creates a local documentation-only project only; it does not overwrite, merge, certify readiness, predict yield, optimize pathways, or provide wet-lab instructions."
    )
    render_project_documentation_package_import_panel()
    st.markdown("---")
    # Source-only compatibility anchors for regression tests: import package preview; read-only preview; preview only;
    # no database writes; no project creation; No database writes are performed.; This preview does not import or modify any project.;
    # does not provide wet-lab protocols.
    uploaded_file = st.file_uploader(
        "Upload Project Export Package (.zip)",
        type=["zip"],
        key="project_import_package_preview_zip",
    )
    if uploaded_file is None:
        return

    zip_bytes = uploaded_file.getvalue()
    report = validate_project_import_package(zip_bytes)
    safety_report = build_import_package_safety_check_report(zip_bytes, local_project_reader=list_pathway_projects)
    _render_import_validation_report(report)
    render_import_safety_section(safety_report)
    if report.get("is_valid"):
        dry_run_plan = build_project_import_dry_run_plan(zip_bytes)
        _render_import_dry_run_plan(dry_run_plan)
        _render_import_execution_gated_skeleton(report, dry_run_plan, zip_bytes, safety_report)
