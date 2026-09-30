"""Formal construct findings renderer shared with the compatibility entry."""
from __future__ import annotations

from typing import Any, Mapping

import streamlit as st
from core.i18n import t as _t


def direction_finding_groups(findings: list[dict[str, Any]], runtime: Mapping[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Group display notices using recorded component-to-TU references."""
    component_units = {}
    for unit in (runtime or {}).get('expression_units', []):
        for role, reference in unit.items():
            if isinstance(reference, Mapping) and reference.get('component_id'):
                component_units[str(reference['component_id'])] = str(unit.get('display_name') or unit.get('unit_name') or unit.get('unit_id'))
    groups: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if finding.get('rule_id') == 'reverse_complement_orientation_used' and not finding.get('blocking'):
            affected = str(finding.get('affected_object') or finding.get('scope') or '')
            label = component_units.get(affected.removeprefix('Component:'), affected or 'TU')
            groups.setdefault(label, []).append(finding)
    return groups


def _render_findings(findings: list[dict[str, Any]], *, runtime: Mapping[str, Any] | None = None) -> None:
    if not findings:
        st.write(_t("v1.results_findings.software_check_no_issues_requiring_display_were"))
        return
    severity_labels = {
        "error": _t("runtime.error"),
        "warning": _t("runtime.warning"),
        "info": _t("runtime.info"),
    }
    groups = direction_finding_groups(findings, runtime)
    for label, rows in groups.items():
        st.info(_t('v1.ui_closure.direction_notice', tu=label, count=len(rows)))
        with st.expander(_t('v1.common.technical_details'), expanded=False):
            st.json(rows)
    for finding in findings:
        if finding.get('rule_id') == 'reverse_complement_orientation_used' and not finding.get('blocking'):
            continue
        severity = severity_labels.get(str(finding.get("severity") or "").lower(), _t("runtime.warning"))
        message = str(finding.get("explanation") or finding.get("message") or _t("v1.common.technical_details"))
        st.write(f"{severity}: {message}")
