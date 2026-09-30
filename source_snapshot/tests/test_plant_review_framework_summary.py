from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_review_framework_summary import (
    BOUNDARY_NOTICE,
    LOCKED_WORKFLOW,
    SUMMARY_KEYS,
    build_plant_review_framework_summary,
)


def _term(*parts: str) -> str:
    return "".join(parts)


def _assert_plain_dict_list(value: Any) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_dict_list(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_dict_list(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def _copy_blob(value: Any) -> str:
    values: list[str] = []

    def collect(nested: Any) -> None:
        if isinstance(nested, dict):
            for item in nested.values():
                collect(item)
        elif isinstance(nested, list):
            for item in nested:
                collect(item)
        else:
            values.append(str(nested))

    collect(value)
    return "\n".join(values).casefold()


def test_summary_reports_current_framework_layers() -> None:
    summary = build_plant_review_framework_summary()

    assert list(summary) == list(SUMMARY_KEYS)
    assert summary["title"] == "Plant Review Framework Summary"
    assert summary["workflow"] == LOCKED_WORKFLOW
    assert summary["coverage_summary"] == {  # type: ignore[index]
        "layer_count": 5,
        "implemented_layer_count": 5,
        "presenter_layer_count": 3,
        "workspace_mount_count": 3,
        "manual_review_required": True,
    }
    assert [row["layer_id"] for row in summary["layer_rows"]] == [  # type: ignore[index]
        "route_template_registry",
        "module_card_registry",
        "construct_slot_plan",
        "evidence_package_flow",
        "design_review_package",
    ]
    assert summary["empty_state"]["is_empty"] is False  # type: ignore[index]


def test_summary_preserves_current_r410_to_r416_layer_paths() -> None:
    rows = {row["layer_id"]: row for row in build_plant_review_framework_summary()["layer_rows"]}  # type: ignore[index]

    assert rows["construct_slot_plan"]["builder"] == "services/plant_construct_slot_plan_readback_builder.py"
    assert rows["construct_slot_plan"]["presenter"] == "services/plant_construct_slot_plan_presenter.py"
    assert rows["construct_slot_plan"]["ui_mount"] == "views/PlantDesignWorkspace.py"
    assert rows["evidence_package_flow"]["builder"] == "services/plant_evidence_package_flow_readback.py"
    assert rows["evidence_package_flow"]["presenter"] == "services/plant_evidence_package_flow_presenter.py"
    assert rows["evidence_package_flow"]["ui_mount"] == "views/PlantDesignWorkspace.py"


def test_custom_empty_summary_returns_safe_empty_state() -> None:
    summary = build_plant_review_framework_summary([])

    assert summary["coverage_summary"]["layer_count"] == 0  # type: ignore[index]
    assert summary["coverage_summary"]["manual_review_required"] is True  # type: ignore[index]
    assert summary["layer_rows"] == []
    assert summary["empty_state"] == {
        "is_empty": True,
        "message": "No plant review framework layers are available.",
    }


def test_summary_output_is_deterministic_and_plain_data() -> None:
    assert build_plant_review_framework_summary() == build_plant_review_framework_summary()
    _assert_plain_dict_list(build_plant_review_framework_summary())


def test_boundary_copy_is_present_without_positive_claims() -> None:
    summary = build_plant_review_framework_summary()
    blob = _copy_blob(summary)

    assert BOUNDARY_NOTICE in summary["boundary_notice"]
    assert "documentation-only" in blob
    assert "manual" in blob
    disallowed_phrases = [
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("valid", "ated ", "con", "struct"),
        _term("optimized ", "pathway"),
        _term("yield ", "pre", "diction"),
        _term("wet", "-lab ", "ready"),
        _term("recom", "mended"),
        _term("best"),
        _term("rank", "ing"),
        _term("scor", "ing"),
    ]
    for phrase in disallowed_phrases:
        assert phrase not in blob


def test_service_does_not_import_runtime_or_high_risk_surfaces() -> None:
    source = Path("services/plant_review_framework_summary.py").read_text(
        encoding="utf-8"
    ).casefold()
    disallowed_markers = [
        "streamlit",
        "sqlite",
        "project_import",
        "project_export",
        "package_export",
        "expression_wizard",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "generate_route",
        "generate_sequence",
        "recommend_component",
        "recommend_route",
        "select_promoter",
        "select_vector",
        "codon_optimization",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_markers:
        assert marker not in source
