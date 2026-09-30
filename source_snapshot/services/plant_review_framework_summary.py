from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only plant review framework summary for manual planning. It reports layer "
    "coverage and next review focus without changing runtime behavior, package export data, "
    "database schema, or downstream-use status."
)

SUMMARY_KEYS: tuple[str, ...] = (
    "title",
    "workflow",
    "layer_rows",
    "coverage_summary",
    "next_review_focus",
    "boundary_notice",
    "empty_state",
)

LOCKED_WORKFLOW = "Plant Goal -> Evidence -> Literature -> Case -> Candidate Route -> Construct Task -> Construct Draft"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _layer(
    *,
    layer_id: str,
    layer_label: str,
    status: str,
    builder: str = "",
    presenter: str = "",
    ui_mount: str = "",
    focused_tests: Sequence[str] = (),
    next_review_focus: str,
) -> dict[str, Any]:
    return {
        "layer_id": layer_id,
        "layer_label": layer_label,
        "status": status,
        "builder": builder,
        "presenter": presenter,
        "ui_mount": ui_mount,
        "focused_tests": list(focused_tests),
        "next_review_focus": next_review_focus,
        "boundary_note": BOUNDARY_NOTICE,
    }


def _default_layers() -> list[dict[str, Any]]:
    return [
        _layer(
            layer_id="route_template_registry",
            layer_label="Plant Expression Route Template Registry",
            status="implemented_read_only",
            builder="services/plant_expression_route_template_registry.py",
            focused_tests=("tests/test_plant_expression_route_template_registry.py",),
            next_review_focus="Keep route ID compatibility visible when future presenters consume templates.",
        ),
        _layer(
            layer_id="module_card_registry",
            layer_label="Plant Review Module Card Registry",
            status="implemented_read_only",
            builder="services/plant_review_module_card_registry.py",
            focused_tests=("tests/test_plant_review_module_card_registry.py",),
            next_review_focus="Keep module IDs aligned with route templates and slot plan rows.",
        ),
        _layer(
            layer_id="construct_slot_plan",
            layer_label="Construct Slot Plan",
            status="builder_presenter_workspace_mount",
            builder="services/plant_construct_slot_plan_readback_builder.py",
            presenter="services/plant_construct_slot_plan_presenter.py",
            ui_mount="views/PlantDesignWorkspace.py",
            focused_tests=(
                "tests/test_plant_construct_slot_plan_readback_builder.py",
                "tests/test_plant_construct_slot_plan_presenter.py",
                "tests/test_plant_design_workspace_ui_shell.py",
            ),
            next_review_focus="Manual screenshot/readability check for slot plan rows in Plant Design Workspace.",
        ),
        _layer(
            layer_id="evidence_package_flow",
            layer_label="Evidence / Gap / Package Flow",
            status="builder_presenter_workspace_mount",
            builder="services/plant_evidence_package_flow_readback.py",
            presenter="services/plant_evidence_package_flow_presenter.py",
            ui_mount="views/PlantDesignWorkspace.py",
            focused_tests=(
                "tests/test_plant_evidence_package_flow_readback.py",
                "tests/test_plant_evidence_package_flow_presenter.py",
                "tests/test_plant_design_workspace_ui_shell.py",
            ),
            next_review_focus="Manual screenshot/readability check for evidence, gap, package, and handoff rows.",
        ),
        _layer(
            layer_id="design_review_package",
            layer_label="Design Review Package Snapshot",
            status="implemented_read_only",
            builder="services/plant_design_review_package_snapshot.py",
            presenter="services/plant_design_review_package_markdown_readback.py",
            ui_mount="views/PlantDesignWorkspace.py",
            focused_tests=(
                "tests/test_plant_design_review_package_snapshot.py",
                "tests/test_plant_design_review_package_markdown_readback.py",
            ),
            next_review_focus="Keep package snapshot as documentation state, not package export behavior.",
        ),
    ]


def build_plant_review_framework_summary(
    layer_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable summary of the current plant review framework coverage."""
    rows = [
        dict(row)
        for row in (layer_rows if layer_rows is not None else _default_layers())
        if isinstance(row, Mapping)
    ]
    implemented = [
        row for row in rows if _text(row.get("status")) in {"implemented_read_only", "builder_presenter_workspace_mount"}
    ]
    mounted = [row for row in rows if _text(row.get("ui_mount"))]
    presenter_rows = [row for row in rows if _text(row.get("presenter"))]
    result = {
        "title": "Plant Review Framework Summary",
        "workflow": LOCKED_WORKFLOW,
        "layer_rows": [_plain_value(row) for row in rows],
        "coverage_summary": {
            "layer_count": len(rows),
            "implemented_layer_count": len(implemented),
            "presenter_layer_count": len(presenter_rows),
            "workspace_mount_count": len(mounted),
            "manual_review_required": True,
        },
        "next_review_focus": [
            _text(row.get("next_review_focus"))
            for row in rows
            if _text(row.get("next_review_focus"))
        ],
        "boundary_notice": BOUNDARY_NOTICE,
        "empty_state": {
            "is_empty": not bool(rows),
            "message": "No plant review framework layers are available." if not rows else "",
        },
    }
    return {key: _plain_value(result[key]) for key in SUMMARY_KEYS}
