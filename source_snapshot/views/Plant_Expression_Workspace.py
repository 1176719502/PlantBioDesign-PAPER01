from __future__ import annotations

import html
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from services.canonical_construct_runtime import (
    COMPONENT_TYPE_ORDER,
    DISPLAY_COMPONENT_LABELS,
    CanonicalConstructRuntimeError,
    active_construct_snapshot,
    active_complete_plasmid_snapshot,
    component_rows,
    create_component,
    create_insertion_site,
    create_sequence_asset,
    ensure_runtime,
    export_active_construct,
    export_active_complete_plasmid,
    generate_active_construct,
    generate_active_complete_plasmid,
    set_active_component_order,
    upsert_insertion_site,
    upsert_component,
    upsert_sequence_asset,
)
from services.plant_expression_workspace_prototype_presenter import (
    build_plant_expression_workspace_prototype_presenter,
)
from services.plant_project_draft_controller import PlantProjectDraftController
from views.pathway_workspace_sections.plant_review_workflow_section import (
    render_plant_project_draft_persistence_panel,
)


STATUS_CLASS = {
    "Recorded": "recorded",
    "Needs documentation": "pending",
    "Manual review needed": "review",
}
R227_BOUNDARY_COPY = (
    "Canonical single-gene construct runtime is documentation-only local project data. "
    "It assembles exact user-provided nucleotide records, coordinates, checksums, and exports "
    "for review traceability without biological recommendation, experiment validation claim, "
    "optimization claim, or wet-lab readiness judgment."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _inject_css() -> None:
    st.markdown(
        """
<style>
.pew-shell{max-width:1180px;margin:0 auto;color:#111827}
.pew-kicker{display:flex;gap:.5rem;align-items:center;font-size:.78rem;font-weight:700;color:#4b5563;margin-bottom:.2rem}
.pew-badge{border:1px solid #d1d5db;border-radius:999px;padding:.08rem .45rem;background:#f9fafb;color:#374151;font-size:.72rem}
.pew-title{font-size:1.55rem;font-weight:700;line-height:1.15;margin:.1rem 0 .3rem 0;color:#111827}
.pew-subtitle{font-size:.94rem;color:#4b5563;line-height:1.45;margin:0 0 .85rem 0;max-width:860px}
.pew-header{border:1px solid #e5e7eb;border-radius:8px;background:#fff;padding:1rem;margin:.75rem 0 1rem 0}
.pew-header-grid{display:grid;grid-template-columns:1.4fr .9fr .9fr .9fr;gap:.8rem;align-items:start}
.pew-label{font-size:.68rem;text-transform:uppercase;font-weight:800;color:#6b7280;letter-spacing:.04em;margin-bottom:.16rem}
.pew-value{font-size:.94rem;font-weight:650;color:#111827;line-height:1.35;overflow-wrap:anywhere}
.pew-muted{font-size:.82rem;color:#4b5563;line-height:1.42;overflow-wrap:anywhere}
.pew-progress{height:8px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin:.42rem 0 .25rem 0}
.pew-progress-fill{height:100%;background:#16a34a;border-radius:999px}
.pew-section-title{font-size:1rem;font-weight:700;color:#111827;margin:1rem 0 .55rem 0}
.pew-construct{border:1px solid #e5e7eb;border-radius:8px;background:#fff;padding:.85rem;margin-bottom:1rem}
.pew-flow{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.55rem;align-items:stretch}
.pew-component{border:1px solid #e5e7eb;border-radius:8px;background:#fbfcfd;padding:.68rem;min-width:0}
.pew-component-title{font-size:.86rem;font-weight:800;color:#111827;line-height:1.25;margin-bottom:.3rem;overflow-wrap:anywhere}
.pew-component-name{font-size:.82rem;color:#1f2937;line-height:1.35;min-height:2.2rem;overflow-wrap:anywhere}
.pew-status{display:inline-block;border-radius:999px;padding:.13rem .45rem;font-size:.7rem;font-weight:800;margin:.45rem 0 .35rem 0;border:1px solid #d1d5db}
.pew-status.recorded{background:#f0fdf4;color:#166534;border-color:#bbf7d0}
.pew-status.pending{background:#fff7ed;color:#9a3412;border-color:#fed7aa}
.pew-status.review{background:#f8fafc;color:#334155;border-color:#cbd5e1}
.pew-component-note{font-size:.76rem;color:#4b5563;line-height:1.38;overflow-wrap:anywhere}
.pew-gaps{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.42fr);gap:.8rem;margin-bottom:1rem}
.pew-gap-list,.pew-next{border:1px solid #e5e7eb;border-radius:8px;background:#fff;padding:.85rem}
.pew-gap{border-bottom:1px solid #eef2f7;padding:.5rem 0}
.pew-gap:last-child{border-bottom:0}
.pew-gap-title{font-size:.88rem;font-weight:750;color:#111827;line-height:1.3}
.pew-gap-body{font-size:.78rem;color:#4b5563;line-height:1.42;margin-top:.16rem}
.pew-next-copy{font-size:.92rem;line-height:1.45;color:#1f2937}
.pew-boundary{border-left:3px solid #64748b;background:#f8fafc;padding:.55rem .7rem;margin:.65rem 0;color:#334155;font-size:.8rem;line-height:1.42}
.pew-detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.55rem;margin:.3rem 0 .75rem 0}
.pew-detail-row{border:1px solid #e5e7eb;border-radius:8px;background:#fff;padding:.6rem;min-width:0}
.pew-detail-row div{font-size:.78rem;line-height:1.35;color:#374151;overflow-wrap:anywhere}
@media (max-width: 980px){
  .pew-header-grid{grid-template-columns:1fr 1fr}
  .pew-flow{grid-template-columns:1fr 1fr}
  .pew-gaps{grid-template-columns:1fr}
}
@media (max-width: 640px){
  .pew-header-grid,.pew-flow{grid-template-columns:1fr}
  .pew-title{font-size:1.28rem}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _safe(value: Any) -> str:
    return html.escape(_text(value, "Not recorded"))


def _render_header(presenter: Mapping[str, Any]) -> None:
    summary = presenter.get("workspace_summary") if isinstance(presenter.get("workspace_summary"), Mapping) else {}
    progress = max(0, min(100, int(summary.get("progress_percent") or 0)))
    st.markdown(
        "<div class='pew-shell'>"
        "<div class='pew-kicker'>"
        "<span>Plant expression review</span>"
        f"<span class='pew-badge'>{_safe(presenter.get('page_badge'))}</span>"
        "</div>"
        f"<div class='pew-title'>{_safe(presenter.get('page_title'))}</div>"
        f"<div class='pew-subtitle'>{_safe(presenter.get('subtitle'))}</div>"
        "<div class='pew-header'>"
        "<div class='pew-header-grid'>"
        "<div>"
        "<div class='pew-label'>Project / Case</div>"
        f"<div class='pew-value'>{_safe(summary.get('project_name'))}</div>"
        f"<div class='pew-muted'>{_safe(summary.get('design_purpose'))}</div>"
        "</div>"
        "<div>"
        "<div class='pew-label'>Target product</div>"
        f"<div class='pew-value'>{_safe(summary.get('target_product'))}</div>"
        "<div class='pew-label' style='margin-top:.55rem'>Plant host</div>"
        f"<div class='pew-value'>{_safe(summary.get('plant_host'))}</div>"
        "</div>"
        "<div>"
        "<div class='pew-label'>Current stage</div>"
        f"<div class='pew-value'>{_safe(summary.get('current_stage'))}</div>"
        "<div class='pew-label' style='margin-top:.55rem'>Route</div>"
        f"<div class='pew-muted'>{_safe(summary.get('route_label'))}</div>"
        "</div>"
        "<div>"
        "<div class='pew-label'>Overall status</div>"
        f"<div class='pew-value'>{_safe(summary.get('overall_status'))}</div>"
        "<div class='pew-progress'>"
        f"<div class='pew-progress-fill' style='width:{progress}%'></div>"
        "</div>"
        f"<div class='pew-muted'>{_safe(summary.get('completion_label'))}</div>"
        "</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_construct_overview(presenter: Mapping[str, Any]) -> None:
    rows = _mapping_list(presenter.get("construct_components"))
    st.markdown("<div class='pew-section-title'>Expression Construct Overview</div>", unsafe_allow_html=True)
    if not rows:
        st.caption("No construct component rows are available for this workspace.")
        return
    cells: list[str] = []
    for row in rows:
        status = _text(row.get("status"), "Needs documentation")
        status_class = STATUS_CLASS.get(status, "pending")
        cells.append(
            "<div class='pew-component'>"
            f"<div class='pew-component-title'>{_safe(row.get('label'))}</div>"
            f"<div class='pew-component-name'>{_safe(row.get('name'))}</div>"
            f"<span class='pew-status {status_class}'>{_safe(status)}</span>"
            f"<div class='pew-component-note'>{_safe(row.get('note'))}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='pew-construct'><div class='pew-flow'>"
        + "".join(cells)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def _render_gaps_and_next_action(presenter: Mapping[str, Any]) -> None:
    gaps = _mapping_list(presenter.get("gaps"))
    if gaps:
        gap_html = "".join(
            "<div class='pew-gap'>"
            f"<div class='pew-gap-title'>{_safe(row.get('title'))}</div>"
            f"<div class='pew-gap-body'>{_safe(row.get('description'))}</div>"
            "</div>"
            for row in gaps
        )
    else:
        gap_html = "<div class='pew-gap-body'>No high-priority documentation gaps are shown for this prototype payload.</div>"
    st.markdown(
        "<div class='pew-section-title'>Current Gaps and Next Action</div>"
        "<div class='pew-gaps'>"
        "<div class='pew-gap-list'>"
        "<div class='pew-label'>Top open gaps</div>"
        f"{gap_html}"
        "</div>"
        "<div class='pew-next'>"
        "<div class='pew-label'>Next action</div>"
        f"<div class='pew-next-copy'>{_safe(presenter.get('next_action'))}</div>"
        f"<div class='pew-boundary'>{_safe(presenter.get('boundary_notice'))}</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_detail_rows(rows: Sequence[Mapping[str, Any]], empty_message: str) -> None:
    row_list = _mapping_list(rows)
    if not row_list:
        st.caption(empty_message)
        return
    cards: list[str] = []
    for row in row_list[:12]:
        fields = []
        for key, value in row.items():
            if not _text(value):
                continue
            fields.append(f"<div><strong>{html.escape(str(key).replace('_', ' ').title())}:</strong> {_safe(value)}</div>")
        if fields:
            cards.append("<div class='pew-detail-row'>" + "".join(fields) + "</div>")
    if cards:
        st.markdown("<div class='pew-detail-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
    else:
        st.caption(empty_message)


def _render_advanced_details(presenter: Mapping[str, Any]) -> None:
    st.markdown("<div class='pew-section-title'>Detailed Review</div>", unsafe_allow_html=True)
    with st.expander("Advanced details", expanded=False):
        for group in _mapping_list(presenter.get("advanced_details")):
            st.markdown(f"**{_safe(group.get('label'))}**", unsafe_allow_html=True)
            _render_detail_rows(_mapping_list(group.get("rows")), _text(group.get("empty_message"), "No rows are available."))


def _runtime_status_label(status: str) -> str:
    mapping = {
        "draft": "Draft",
        "current": "Current",
        "stale": "Stale",
        "blocking_invalid": "Blocking review findings",
    }
    return mapping.get(_text(status), _text(status, "Draft"))


def _asset_option_map(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {"Create new asset": {}}
    for asset in list(runtime.get("sequence_assets") or []):
        label = f"{_text(asset.get('display_name'))} | {_text(asset.get('molecule_type')).upper()} | {int(asset.get('length', 0) or 0)} bp"
        options[label] = asset
    return options


def _component_option_map(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {"Create new component": {}}
    for row in component_rows(runtime):
        label = f"{row['display_name']} | {row['component_type']} | {row['orientation']}"
        options[label] = row
    return options


def _component_asset_id(component: Mapping[str, Any]) -> str:
    return _text(component.get("sequence_asset_id"))


def _backbone_asset_options(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {"No backbone selected": {}}
    for asset in list(runtime.get("sequence_assets") or []):
        if _text(asset.get("molecule_type")).lower() != "dna":
            continue
        imported_feature_count = len(list(asset.get("imported_feature_records") or []))
        role = _text(asset.get("asset_role"), "generic")
        label = (
            f"{_text(asset.get('display_name'))} | {int(asset.get('length', 0) or 0)} bp | "
            f"{_text(asset.get('topology'), 'unspecified') or 'unspecified'} | "
            f"{imported_feature_count} feature(s) | role={role}"
        )
        options[label] = asset
    return options


def _slice_interval_preview(sequence: str, start: int, end: int) -> str:
    if not sequence:
        return ""
    normalized_start = max(1, int(start or 1))
    normalized_end = max(normalized_start, int(end or normalized_start))
    return sequence[normalized_start - 1:normalized_end]


def _render_backbone_summary(backbone_asset: Mapping[str, Any]) -> None:
    if not backbone_asset:
        st.info("Upload or select a nucleotide GenBank backbone to inspect length, topology, checksum, and features.")
        return
    imported_features = list(backbone_asset.get("imported_feature_records") or [])
    st.markdown(
        f"**Backbone length:** {int(backbone_asset.get('length', 0) or 0)} bp  \n"
        f"**Topology:** {_text(backbone_asset.get('topology')) or 'unspecified'}  \n"
        f"**Sequence SHA-256:** `{_text(backbone_asset.get('sequence_checksum')) or 'not available'}`  \n"
        f"**Source checksum:** `{_text(backbone_asset.get('source_file_checksum')) or 'not recorded'}`  \n"
        f"**Imported features:** {len(imported_features)}"
    )
    warnings = list(backbone_asset.get("warnings") or [])
    if warnings:
        st.caption("Backbone import warnings: " + " | ".join(str(item) for item in warnings))
    if imported_features:
        st.markdown("**Imported backbone features**")
        st.table(
            [
                {
                    "name": _text(feature.get("name") or feature.get("label")),
                    "type": _text(feature.get("type")),
                    "start": int(feature.get("start", 0) or 0) + 1 if not bool(feature.get("unsupported_location")) else "",
                    "end": int(feature.get("end", 0) or 0) if not bool(feature.get("unsupported_location")) else "",
                    "strand": int(feature.get("strand", 1) or 1),
                    "location": _text(feature.get("location_text")),
                    "unsupported_location": "yes" if bool(feature.get("unsupported_location")) else "no",
                }
                for feature in imported_features
            ]
        )


def _render_runtime_asset_editor(controller: PlantProjectDraftController, draft, runtime: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    st.markdown("### SequenceAsset intake")
    st.caption(
        "Paste or upload one real sequence-bearing record at a time. Intake preserves exact nucleotide content "
        "after whitespace/case normalization only; unsupported symbols are rejected instead of being silently rewritten."
    )
    asset_options = _asset_option_map(runtime)
    selected_asset_label = st.selectbox(
        "SequenceAsset editor target",
        list(asset_options.keys()),
        key=f"r227_asset_editor_target_{draft.project_id}",
    )
    existing_asset = asset_options.get(selected_asset_label, {})
    molecule_type = st.selectbox(
        "SequenceAsset molecule type",
        ["dna", "protein"],
        index=0 if _text(existing_asset.get("molecule_type"), "dna") == "dna" else 1,
        key=f"r227_asset_molecule_type_{draft.project_id}",
    )
    source_type = st.selectbox(
        "SequenceAsset source",
        ["paste", "upload"],
        index=0,
        key=f"r227_asset_source_type_{draft.project_id}",
    )
    source_format = st.selectbox(
        "Input format",
        ["plain", "fasta", "genbank"],
        index=0,
        key=f"r227_asset_source_format_{draft.project_id}",
    )
    asset_role = st.selectbox(
        "SequenceAsset role",
        ["generic", "construct_component", "backbone"],
        index=["generic", "construct_component", "backbone"].index(_text(existing_asset.get("asset_role"), "generic"))
        if _text(existing_asset.get("asset_role"), "generic") in {"generic", "construct_component", "backbone"}
        else 0,
        key=f"r227_asset_role_{draft.project_id}",
    )
    asset_name = st.text_input(
        "SequenceAsset display name",
        value=_text(existing_asset.get("display_name")),
        key=f"r227_asset_name_{draft.project_id}",
    )
    source_name = st.text_input(
        "Source label / filename",
        value=_text(existing_asset.get("source_name")),
        key=f"r227_asset_source_name_{draft.project_id}",
    )
    provenance_reference = st.text_input(
        "Provenance reference",
        value=_text(existing_asset.get("provenance_reference")),
        key=f"r227_asset_provenance_{draft.project_id}",
    )
    source_description = st.text_area(
        "Source description",
        value=_text(existing_asset.get("source_description")),
        height=72,
        key=f"r227_asset_source_description_{draft.project_id}",
    )
    raw_text = ""
    source_file_checksum = ""
    if source_type == "upload":
        uploaded = st.file_uploader(
            "Upload one sequence record",
            type=["txt", "fasta", "fa", "gb", "gbk"],
            key=f"r227_asset_upload_{draft.project_id}",
        )
        if uploaded is not None:
            content = uploaded.read()
            raw_text = content.decode("utf-8", errors="ignore")
            source_file_checksum = hashlib.sha256(content).hexdigest() if content else ""
            if not source_name:
                source_name = _text(getattr(uploaded, "name", "uploaded-record"))
    else:
        raw_text = st.text_area(
            "Raw sequence input",
            value=_text(existing_asset.get("nucleotide_sequence")),
            height=140,
            key=f"r227_asset_raw_text_{draft.project_id}",
        )
    if st.button("Add or update SequenceAsset", key=f"r227_asset_save_{draft.project_id}", use_container_width=True):
        try:
            asset = create_sequence_asset(
                project_id=draft.project_id,
                display_name=asset_name,
                raw_text=raw_text,
                molecule_type=molecule_type,
                source_type=source_type,
                source_format=source_format,
                source_name=source_name,
                source_description=source_description,
                provenance_reference=provenance_reference,
                source_file_checksum=source_file_checksum,
                asset_role=asset_role,
                asset_id=_text(existing_asset.get("asset_id")) or None,
                created_at=_text(existing_asset.get("created_at")) or None,
            )
            runtime = upsert_sequence_asset(runtime, asset)
            result = controller.update_active(canonical_construct_runtime=runtime)
            if result.ok and result.draft is not None:
                draft = result.draft
                runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
            st.success("SequenceAsset recorded in the active draft session.")
        except CanonicalConstructRuntimeError as exc:
            st.error(str(exc))
    return draft, runtime


def _render_runtime_component_editor(controller: PlantProjectDraftController, draft, runtime: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    st.markdown("### Component assignment")
    st.caption(
        "Map a real SequenceAsset to one construct role. Components without nucleotide DNA stay visible in the draft "
        "but are blocked from canonical transcription-unit assembly."
    )
    asset_labels = ["Select a SequenceAsset"]
    asset_map: dict[str, str] = {}
    for asset in list(runtime.get("sequence_assets") or []):
        label = f"{_text(asset.get('display_name'))} | {_text(asset.get('molecule_type')).upper()} | {int(asset.get('length', 0) or 0)} bp"
        asset_labels.append(label)
        asset_map[label] = _text(asset.get("asset_id"))
    component_options = _component_option_map(runtime)
    selected_component_label = st.selectbox(
        "Component editor target",
        list(component_options.keys()),
        key=f"r227_component_editor_target_{draft.project_id}",
    )
    existing_component = component_options.get(selected_component_label, {})
    type_options = list(COMPONENT_TYPE_ORDER)
    existing_type = _text(existing_component.get("component_type"), type_options[0])
    type_index = type_options.index(existing_type) if existing_type in type_options else 0
    component_type = st.selectbox(
        "Component type",
        type_options,
        index=type_index,
        format_func=lambda key: DISPLAY_COMPONENT_LABELS.get(key, key),
        key=f"r227_component_type_{draft.project_id}",
    )
    component_name = st.text_input(
        "Component display name",
        value=_text(existing_component.get("display_name")),
        key=f"r227_component_name_{draft.project_id}",
    )
    orientation = st.selectbox(
        "Orientation",
        ["forward", "reverse"],
        index=0 if _text(existing_component.get("orientation"), "forward") == "forward" else 1,
        key=f"r227_component_orientation_{draft.project_id}",
    )
    provenance_reference = st.text_input(
        "Component provenance reference",
        value=_text(existing_component.get("provenance_reference")),
        key=f"r227_component_provenance_{draft.project_id}",
    )
    existing_asset_id = _component_asset_id(existing_component)
    asset_index_for_existing = next((index for index, label in enumerate(asset_labels) if asset_map.get(label) == existing_asset_id), 0)
    asset_label = st.selectbox(
        "Linked SequenceAsset",
        asset_labels,
        index=asset_index_for_existing,
        key=f"r227_component_asset_{draft.project_id}",
    )
    if st.button("Add or update Component", key=f"r227_component_save_{draft.project_id}", use_container_width=True):
        selected_asset_id = _text(asset_map.get(asset_label))
        if not selected_asset_id:
            st.error("Select a SequenceAsset before recording the Component.")
        else:
            try:
                component = create_component(
                    project_id=draft.project_id,
                    component_type=component_type,
                    display_name=component_name,
                    sequence_asset_id=selected_asset_id,
                    orientation=orientation,
                    provenance_reference=provenance_reference,
                    component_id=_text(existing_component.get("component_id")) or None,
                    created_at=_text(existing_component.get("created_at")) or None,
                )
                runtime = upsert_component(runtime, component)
                result = controller.update_active(canonical_construct_runtime=runtime)
                if result.ok and result.draft is not None:
                    draft = result.draft
                    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
                st.success("Component recorded in the active draft session.")
            except CanonicalConstructRuntimeError as exc:
                st.error(str(exc))
    return draft, runtime


def _component_label_map(runtime: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    labels: list[str] = []
    label_to_id: dict[str, str] = {}
    for row in component_rows(runtime):
        label = f"{row['display_name']} | {DISPLAY_COMPONENT_LABELS.get(row['component_type'], row['component_type'])} | {row['orientation']}"
        labels.append(label)
        label_to_id[label] = row["component_id"]
    return labels, label_to_id


def _render_runtime_assembly_editor(controller: PlantProjectDraftController, draft, runtime: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    st.markdown("### TranscriptionUnit assembly")
    st.caption(
        "Select the active component order, generate the exact DNA, and then save the project draft above to preserve "
        "the same sequence, coordinates, checksum, and validation state across reopen."
    )
    labels, label_to_id = _component_label_map(runtime)
    snapshot = active_construct_snapshot(runtime)
    current_order = list(snapshot.get("ordered_component_ids") or [])
    current_label_order = [label for label in labels if label_to_id.get(label) in current_order]
    default_selection = current_label_order or labels
    selected_labels = st.multiselect(
        "Ordered components in the active transcription unit",
        labels,
        default=default_selection,
        key=f"r227_component_order_{draft.project_id}",
        help="The order of the selected labels is used as the canonical single-gene transcription-unit order.",
    )
    order_columns = st.columns(2)
    with order_columns[0]:
        if st.button("Apply component order", key=f"r227_component_order_apply_{draft.project_id}", use_container_width=True):
            ordered_ids = [label_to_id[label] for label in selected_labels if label in label_to_id]
            runtime = set_active_component_order(runtime, ordered_ids)
            result = controller.update_active(canonical_construct_runtime=runtime)
            if result.ok and result.draft is not None:
                draft = result.draft
                runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
            st.success("Active transcription-unit order updated in session.")
    with order_columns[1]:
        if st.button("Generate canonical construct", key=f"r227_generate_construct_{draft.project_id}", type="primary", use_container_width=True):
            ordered_ids = [label_to_id[label] for label in selected_labels if label in label_to_id]
            try:
                runtime = set_active_component_order(runtime, ordered_ids)
                runtime = generate_active_construct(runtime)
                result = controller.update_active(canonical_construct_runtime=runtime)
                if result.ok and result.draft is not None:
                    draft = result.draft
                    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
                st.success("Canonical single-gene construct regenerated from the active component order.")
            except CanonicalConstructRuntimeError as exc:
                st.error(str(exc))
    return draft, runtime


def _render_backbone_editor(controller: PlantProjectDraftController, draft, runtime: dict[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    st.markdown("### Backbone intake")
    st.caption(
        "Upload one GenBank backbone or select an existing nucleotide SequenceAsset. Backbone intake preserves the exact "
        "sequence, imported topology, checksum, and feature rows for documentation-only complete plasmid generation."
    )
    options = _backbone_asset_options(runtime)
    selected_label = st.selectbox(
        "Active backbone asset",
        list(options.keys()),
        key=f"r228_backbone_asset_{draft.project_id}",
    )
    selected_backbone = options.get(selected_label, {})
    upload_name = st.text_input(
        "Backbone display name",
        value=_text(selected_backbone.get("display_name")),
        key=f"r228_backbone_name_{draft.project_id}",
    )
    upload_provenance = st.text_input(
        "Backbone provenance reference",
        value=_text(selected_backbone.get("provenance_reference")),
        key=f"r228_backbone_provenance_{draft.project_id}",
    )
    upload_file = st.file_uploader(
        "Upload backbone GenBank",
        type=["gb", "gbk", "genbank", "txt"],
        key=f"r228_backbone_upload_{draft.project_id}",
    )
    if st.button("Import or update backbone", key=f"r228_backbone_save_{draft.project_id}", use_container_width=True):
        if upload_file is None and not selected_backbone:
            st.error("Upload a GenBank backbone or select an existing nucleotide SequenceAsset first.")
        else:
            try:
                if upload_file is not None:
                    content = upload_file.read()
                    raw_text = content.decode("utf-8", errors="ignore")
                    backbone_asset = create_sequence_asset(
                        project_id=draft.project_id,
                        display_name=upload_name,
                        raw_text=raw_text,
                        molecule_type="dna",
                        source_type="upload",
                        source_format="genbank",
                        source_name=_text(getattr(upload_file, "name", "uploaded-backbone.gb")),
                        provenance_reference=upload_provenance,
                        source_file_checksum=hashlib.sha256(content).hexdigest() if content else "",
                        asset_role="backbone",
                        asset_id=_text(selected_backbone.get("asset_id")) or None,
                        created_at=_text(selected_backbone.get("created_at")) or None,
                    )
                else:
                    backbone_asset = create_sequence_asset(
                        project_id=draft.project_id,
                        display_name=upload_name or _text(selected_backbone.get("display_name")),
                        raw_text=_text(selected_backbone.get("nucleotide_sequence")),
                        molecule_type="dna",
                        source_type=_text(selected_backbone.get("source_type"), "paste"),
                        source_format="plain",
                        source_name=_text(selected_backbone.get("source_name")),
                        provenance_reference=upload_provenance or _text(selected_backbone.get("provenance_reference")),
                        topology=_text(selected_backbone.get("topology")),
                        source_file_checksum=_text(selected_backbone.get("source_file_checksum")),
                        asset_role="backbone",
                        asset_id=_text(selected_backbone.get("asset_id")) or None,
                        created_at=_text(selected_backbone.get("created_at")) or None,
                    )
                    backbone_asset["imported_feature_records"] = list(selected_backbone.get("imported_feature_records") or [])
                runtime = upsert_sequence_asset(runtime, backbone_asset)
                result = controller.update_active(canonical_construct_runtime=runtime)
                if result.ok and result.draft is not None:
                    draft = result.draft
                    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
                    options = _backbone_asset_options(runtime)
                    selected_backbone = next(
                        (asset for asset in options.values() if _text(asset.get("asset_id")) == _text(backbone_asset.get("asset_id"))),
                        {},
                    )
                st.success("Backbone asset recorded in the active draft session.")
            except CanonicalConstructRuntimeError as exc:
                st.error(str(exc))

    _render_backbone_summary(selected_backbone)
    return draft, runtime, selected_backbone


def _render_complete_plasmid_editor(
    controller: PlantProjectDraftController,
    draft,
    runtime: dict[str, Any],
    selected_backbone: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    st.markdown("### Complete plasmid generation")
    st.caption(
        "Choose direct insertion or replacement coordinates on the selected backbone, preview the affected interval, "
        "and generate one canonical complete circular plasmid sequence shared by UI, persistence, validation, and export."
    )
    backbone_options = _backbone_asset_options(runtime)
    active_backbone_id = _text(selected_backbone.get("asset_id"))
    active_backbone_label = next(
        (label for label, asset in backbone_options.items() if _text(asset.get("asset_id")) == active_backbone_id),
        list(backbone_options.keys())[0],
    )
    selected_backbone_label = st.selectbox(
        "Backbone used for plasmid generation",
        list(backbone_options.keys()),
        index=list(backbone_options.keys()).index(active_backbone_label) if active_backbone_label in backbone_options else 0,
        key=f"r228_plasmid_backbone_select_{draft.project_id}",
    )
    active_backbone = backbone_options.get(selected_backbone_label, {})
    mode = st.selectbox(
        "Insertion mode",
        ["insertion", "replacement"],
        key=f"r228_insertion_mode_{draft.project_id}",
    )
    backbone_length = int(active_backbone.get("length", 0) or 0)
    default_start = 1 if backbone_length else 0
    default_end = 2 if backbone_length > 1 else (1 if backbone_length else 0)
    start_coordinate = int(
        st.number_input(
            "Start coordinate",
            min_value=0,
            max_value=max(backbone_length, 1),
            value=default_start,
            step=1,
            key=f"r228_insertion_start_{draft.project_id}",
        )
    )
    end_coordinate = int(
        st.number_input(
            "End coordinate",
            min_value=0,
            max_value=max(backbone_length, 1),
            value=default_end,
            step=1,
            key=f"r228_insertion_end_{draft.project_id}",
        )
    )
    expected_removed_sequence = st.text_input(
        "Expected removed sequence (replacement mode only)",
        key=f"r228_expected_removed_{draft.project_id}",
    )
    topology_confirmation = st.checkbox(
        "Treat topology-unspecified backbone as circular for documentation-only complete plasmid generation",
        value=False,
        key=f"r228_topology_confirm_{draft.project_id}",
    )
    coordinate_confirmation = st.checkbox(
        "I confirm the selected backbone coordinates and understand this generates digital-design-only plasmid output.",
        value=False,
        key=f"r228_coordinate_confirm_{draft.project_id}",
    )

    preview_sequence = ""
    if active_backbone and mode == "replacement":
        preview_sequence = _slice_interval_preview(_text(active_backbone.get("nucleotide_sequence")), start_coordinate, end_coordinate)
    elif active_backbone and mode == "insertion":
        sequence = _text(active_backbone.get("nucleotide_sequence"))
        if sequence and start_coordinate >= 1 and start_coordinate <= len(sequence):
            left = sequence[max(0, start_coordinate - 6):start_coordinate]
            right = sequence[start_coordinate:min(len(sequence), start_coordinate + 6)]
            preview_sequence = f"{left}|{right}"
    if preview_sequence:
        st.markdown("**Backbone interval preview**")
        st.code(preview_sequence, language="text")

    action_columns = st.columns(2)
    with action_columns[0]:
        if st.button("Record insertion site", key=f"r228_record_site_{draft.project_id}", use_container_width=True):
            try:
                site = create_insertion_site(
                    project_id=draft.project_id,
                    backbone_asset_id=_text(active_backbone.get("asset_id")),
                    start_coordinate=start_coordinate,
                    end_coordinate=end_coordinate,
                    mode=mode,
                    expected_removed_sequence=expected_removed_sequence,
                    user_confirmation=coordinate_confirmation,
                    topology_confirmation=topology_confirmation,
                )
                runtime = upsert_insertion_site(runtime, site)
                result = controller.update_active(canonical_construct_runtime=runtime)
                if result.ok and result.draft is not None:
                    draft = result.draft
                    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
                st.success("Insertion-site definition recorded in the active draft session.")
            except CanonicalConstructRuntimeError as exc:
                st.error(str(exc))
    with action_columns[1]:
        if st.button("Generate complete plasmid", key=f"r228_generate_complete_plasmid_{draft.project_id}", type="primary", use_container_width=True):
            try:
                site = create_insertion_site(
                    project_id=draft.project_id,
                    backbone_asset_id=_text(active_backbone.get("asset_id")),
                    start_coordinate=start_coordinate,
                    end_coordinate=end_coordinate,
                    mode=mode,
                    expected_removed_sequence=expected_removed_sequence,
                    user_confirmation=coordinate_confirmation,
                    topology_confirmation=topology_confirmation,
                )
                runtime = upsert_insertion_site(runtime, site)
                runtime = generate_active_complete_plasmid(runtime)
                result = controller.update_active(canonical_construct_runtime=runtime)
                if result.ok and result.draft is not None:
                    draft = result.draft
                    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
                st.success("Canonical complete plasmid regenerated from the active backbone and insertion site.")
            except CanonicalConstructRuntimeError as exc:
                st.error(str(exc))
    return draft, runtime


def _render_runtime_snapshot(draft, runtime: dict[str, Any]) -> dict[str, Any]:
    snapshot = active_construct_snapshot(runtime)
    st.markdown("### Canonical construct output")
    st.caption(R227_BOUNDARY_COPY)
    summary = snapshot.get("validation_summary") if isinstance(snapshot.get("validation_summary"), dict) else {}
    st.markdown(
        f"**Status:** {_runtime_status_label(_text(snapshot.get('construct_status')))}  \n"
        f"**Sequence length:** {int(snapshot.get('sequence_length', 0) or 0)} bp  \n"
        f"**SHA-256:** `{_text(snapshot.get('sequence_checksum')) or 'not generated'}`  \n"
        f"**Revision:** `{_text(snapshot.get('revision_id')) or 'not generated'}`  \n"
        f"**Blocking findings:** {int(summary.get('blocking_count', 0) or 0)}  \n"
        f"**Warnings:** {int(summary.get('warning_count', 0) or 0)}"
    )
    if _text(snapshot.get("translation")):
        st.caption(f"CDS translation: {_text(snapshot.get('translation'))}")
    if _text(snapshot.get("sequence")):
        st.code(_text(snapshot.get("sequence")), language="text")
    else:
        st.info("Generate the canonical construct to populate sequence output, coordinates, checksum, and export files.")

    feature_rows = list(snapshot.get("feature_rows") or [])
    if feature_rows:
        st.markdown("**Deterministic component-coordinate table**")
        st.table(feature_rows)
    findings = list(snapshot.get("validation_findings") or [])
    if findings:
        st.markdown("**Validation findings**")
        st.table(
            [
                {
                    "rule_id": _text(item.get("rule_id")),
                    "severity": _text(item.get("severity")),
                    "blocking": "yes" if bool(item.get("blocking")) else "no",
                    "affected_object": _text(item.get("affected_object")),
                    "explanation": _text(item.get("explanation")),
                }
                for item in findings
            ]
        )
    try:
        export_payloads = export_active_construct(runtime, project_name=draft.project_name or snapshot.get("construct_id", "construct"))
    except CanonicalConstructRuntimeError as exc:
        st.info(f"Canonical export files remain unavailable: {exc}")
        export_payloads = {}
    if export_payloads:
        st.markdown("**Documentation-only export files**")
        export_columns = st.columns(2)
        fasta = export_payloads["fasta"]
        export_columns[0].download_button(
            fasta["label"],
            data=fasta["data"],
            file_name=fasta["file_name"],
            mime=fasta["mime"],
            use_container_width=True,
        )
        genbank = export_payloads["genbank"]
        export_columns[1].download_button(
            genbank["label"],
            data=genbank["data"],
            file_name=genbank["file_name"],
            mime=genbank["mime"],
            use_container_width=True,
        )
    st.caption("Use the save control in the draft persistence panel above to persist the current canonical runtime.")
    return snapshot


def _render_complete_plasmid_snapshot(draft, runtime: dict[str, Any]) -> dict[str, Any]:
    snapshot = active_complete_plasmid_snapshot(runtime)
    st.markdown("### Complete plasmid output")
    st.caption(
        "Complete plasmid output is documentation-only local project data. It preserves exact backbone and cassette "
        "sequence composition, coordinates, checksums, and annotations without biological recommendation, experiment "
        "validation claim, optimization claim, or wet-lab readiness judgment."
    )
    summary = snapshot.get("validation_summary") if isinstance(snapshot.get("validation_summary"), dict) else {}
    cassette_coordinates = snapshot.get("cassette_coordinates") if isinstance(snapshot.get("cassette_coordinates"), dict) else {}
    cassette_label = (
        f"{int(cassette_coordinates.get('start', 0) or 0)}-{int(cassette_coordinates.get('end', 0) or 0)}"
        if cassette_coordinates
        else "not generated"
    )
    st.markdown(
        f"**Status:** {_runtime_status_label(_text(snapshot.get('construct_status')))}  \n"
        f"**Sequence length:** {int(snapshot.get('sequence_length', 0) or 0)} bp  \n"
        f"**Topology:** {_text(snapshot.get('topology')) or 'circular'}  \n"
        f"**SHA-256:** `{_text(snapshot.get('sequence_checksum')) or 'not generated'}`  \n"
        f"**Revision:** `{_text(snapshot.get('revision_id')) or 'not generated'}`  \n"
        f"**Cassette coordinates:** {cassette_label}  \n"
        f"**Blocking findings:** {int(summary.get('blocking_count', 0) or 0)}  \n"
        f"**Warnings:** {int(summary.get('warning_count', 0) or 0)}"
    )
    if _text(snapshot.get("sequence")):
        st.code(_text(snapshot.get("sequence")), language="text")
    else:
        st.info("Generate the complete plasmid to populate sequence output, topology, shifted features, and export files.")

    feature_rows = list(snapshot.get("feature_rows") or [])
    if feature_rows:
        st.markdown("**Combined backbone and cassette feature-coordinate table**")
        st.table(feature_rows)

    findings = list(snapshot.get("validation_findings") or [])
    if findings:
        st.markdown("**Complete plasmid validation findings**")
        st.table(
            [
                {
                    "rule_id": _text(item.get("rule_id")),
                    "severity": _text(item.get("severity")),
                    "blocking": "yes" if bool(item.get("blocking")) else "no",
                    "affected_object": _text(item.get("affected_object")),
                    "explanation": _text(item.get("explanation")),
                }
                for item in findings
            ]
        )
    try:
        export_payloads = export_active_complete_plasmid(
            runtime,
            project_name=(draft.project_name or snapshot.get("plasmid_id") or "complete_plasmid"),
        )
    except CanonicalConstructRuntimeError as exc:
        st.info(f"Complete plasmid export files remain unavailable: {exc}")
        export_payloads = {}
    if export_payloads:
        st.markdown("**Documentation-only complete plasmid export files**")
        export_columns = st.columns(2)
        fasta = export_payloads["fasta"]
        export_columns[0].download_button(
            fasta["label"],
            data=fasta["data"],
            file_name=fasta["file_name"],
            mime=fasta["mime"],
            use_container_width=True,
        )
        genbank = export_payloads["genbank"]
        export_columns[1].download_button(
            genbank["label"],
            data=genbank["data"],
            file_name=genbank["file_name"],
            mime=genbank["mime"],
            use_container_width=True,
        )
    return snapshot


def render(_change_page=None) -> dict[str, Any]:
    del _change_page
    source_mode = st.radio(
        "Workspace source",
        ("Current user draft", "Example read-only demonstration"),
        index=0,
        key="r224_plant_expression_workspace_source_mode",
        help=(
            "Current user draft reads and updates local saved project data. "
            "Example mode stays read-only and does not use user data."
        ),
    )
    _inject_css()
    if source_mode == "Example read-only demonstration":
        st.caption("Example / Demonstration / Read-only / Not user data.")
        presenter = build_plant_expression_workspace_prototype_presenter(use_default_fixture=True)
        _render_header(presenter)
        _render_construct_overview(presenter)
        _render_gaps_and_next_action(presenter)
        _render_advanced_details(presenter)
        st.markdown("</div>", unsafe_allow_html=True)
        return presenter

    persistence_state = render_plant_project_draft_persistence_panel()
    controller = PlantProjectDraftController(session_state=st.session_state)
    draft = controller.active_draft()
    presenter = build_plant_expression_workspace_prototype_presenter(
        project_draft=draft.to_dict() if draft is not None else None,
        use_default_fixture=False,
    )
    if draft is None:
        st.title(_text(presenter.get("page_title"), "Plant Expression Workspace"))
        st.info("Create or open a local plant project draft above to start the canonical construct runtime flow.")
        return {
            **presenter,
            "persistence_state": persistence_state,
            "runtime_state": {},
        }

    runtime = ensure_runtime(draft.project_id, draft.canonical_construct_runtime)
    _render_header(presenter)
    st.markdown("## Canonical single-gene construct runtime")
    st.caption(R227_BOUNDARY_COPY)
    draft, runtime = _render_runtime_asset_editor(controller, draft, runtime)
    draft, runtime = _render_runtime_component_editor(controller, draft, runtime)
    draft, runtime = _render_runtime_assembly_editor(controller, draft, runtime)
    runtime_snapshot = _render_runtime_snapshot(draft, runtime)
    draft, runtime, selected_backbone = _render_backbone_editor(controller, draft, runtime)
    draft, runtime = _render_complete_plasmid_editor(controller, draft, runtime, selected_backbone)
    complete_plasmid_snapshot = _render_complete_plasmid_snapshot(draft, runtime)
    _render_construct_overview(presenter)
    _render_gaps_and_next_action(presenter)
    _render_advanced_details(presenter)
    st.markdown("</div>", unsafe_allow_html=True)
    return {
        **presenter,
        "persistence_state": persistence_state,
        "runtime_state": runtime_snapshot,
        "complete_plasmid_state": complete_plasmid_snapshot,
    }
