from __future__ import annotations

import ast
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from Bio import SeqIO
from Bio.Seq import Seq
import pytest

from services import mvp_multi_tu_runtime as multi_tu_runtime
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import (
    ROLE_COMPONENT_TYPES,
    registry_record,
    workflow_component_options,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


FORMAL_HOSTS = (
    "Oryza sativa",
    "Nicotiana benthamiana",
    "Zea mays",
    "Arabidopsis thaliana",
    "Solanum lycopersicum",
    "Glycine max",
)


def _unit(*, include_five_prime: bool = True, orientation: str = "forward") -> dict:
    unit = {
        "unit_id": "TU1",
        "display_name": "TU1",
        "orientation": orientation,
        "order": 1,
        "promoter": {"display_name": "P", "raw_text": "AAAA"},
        "cds": {"display_name": "C", "raw_text": "ATGAAATAA"},
        "3_prime_regulatory_region": {"display_name": "T", "raw_text": "TTTT"},
    }
    if include_five_prime:
        unit["five_prime_region"] = {"display_name": "5P", "raw_text": "CCCC"}
    return unit


def _explicit_none_unit(*, orientation: str = "forward") -> dict:
    unit = _unit(include_five_prime=False, orientation=orientation)
    unit["five_prime_region"] = {
        "absence_state": "explicit_none",
        "display_name": "不使用独立 5′ region",
        "raw_text": "",
    }
    return unit


def test_five_prime_region_uses_one_canonical_role_and_existing_component_type() -> None:
    assert tuple(ROLE_COMPONENT_TYPES)[:4] == (
        "promoter",
        "five_prime_region",
        "cds",
        "3_prime_regulatory_region",
    )
    assert ROLE_COMPONENT_TYPES["five_prime_region"] == frozenset({"five_prime_utr"})
    assert "five_prime_region" not in ROLE_COMPONENT_TYPES["promoter"]
    assert "five_prime_utr" not in ROLE_COMPONENT_TYPES["cds"]
    assert registry_record("PCLV1-PRO-35S-835")["component_type"] == "promoter"


def test_current_registry_has_no_formal_five_prime_options_for_any_supported_host() -> None:
    assert all(
        not workflow_component_options(
            role="five_prime_region", target_host_species=host
        )
        for host in FORMAL_HOSTS
    )


def test_four_role_runtime_places_five_prime_region_between_promoter_and_cds() -> None:
    result = generate_multi_tu_combined_construct(
        project_id="four-role-order",
        project_name="Four role order",
        expression_units=[_unit()],
    )
    coordinates = result["combined_construct"]["component_coordinates"]
    assert [row["biological_role"] for row in coordinates] == [
        "promoter",
        "five_prime_region",
        "cds",
        "3_prime_regulatory_region",
    ]
    assert [row["component_type"] for row in coordinates] == [
        "promoter",
        "five_prime_utr",
        "cds",
        "terminator",
    ]
    assert coordinates[0]["end"] < coordinates[1]["start"] < coordinates[2]["start"]
    assert result["combined_construct"]["dna"] == "AAAA" + "CCCC" + "ATGAAATAA" + "TTTT"
    formal_validation = result["combined_construct"]["formal_validation"]
    assert formal_validation["status"] == "four_role_review_required"
    assert formal_validation["formal_ready"] is False


def test_reverse_four_role_runtime_keeps_coordinates_in_assembly_order() -> None:
    result = generate_multi_tu_combined_construct(
        project_id="reverse-four-role-order",
        project_name="Reverse four role order",
        expression_units=[_unit(orientation="reverse")],
    )
    coordinates = result["combined_construct"]["component_coordinates"]
    assert [row["biological_role"] for row in coordinates] == [
        "3_prime_regulatory_region",
        "cds",
        "five_prime_region",
        "promoter",
    ]
    assert all(left["end"] < right["start"] for left, right in zip(coordinates, coordinates[1:]))


def test_missing_five_prime_region_is_legacy_incomplete_and_never_formal_ready() -> None:
    result = generate_multi_tu_combined_construct(
        project_id="legacy-three-role",
        project_name="Legacy three role",
        expression_units=[_unit(include_five_prime=False)],
    )
    formal_validation = result["combined_construct"]["formal_validation"]
    assert formal_validation == {
        "status": "legacy_incomplete",
        "formal_ready": False,
        "findings": [
            {"code": "MISSING_FIVE_PRIME_REGION", "blocking": True, "unit_ids": ["TU1"]}
        ],
    }
    assert "five_prime_region" not in result["original_input"]["expression_units"][0]


def test_forward_explicit_none_is_distinct_and_adds_no_bytes_or_feature() -> None:
    unit = _explicit_none_unit()
    result = generate_multi_tu_combined_construct(
        project_id="explicit-none",
        project_name="Explicit none",
        expression_units=[unit],
    )
    assert result["formal_validation"] == {
        "status": "four_role_review_required",
        "formal_ready": False,
        "findings": [
            {"code": "FORMAL_SELECTION_REVIEW_REQUIRED", "blocking": True, "unit_ids": []}
        ],
    }
    assert result["original_input"]["expression_units"][0]["five_prime_region"]["absence_state"] == "explicit_none"
    assert result["combined_construct"]["dna"] == "AAAA" + "ATGAAATAA" + "TTTT"
    assert not any(
        row.get("biological_role") == "five_prime_region"
        for row in result["combined_construct"]["component_coordinates"]
    )
    assert result["combined_construct"]["total_length"] == 4 + 9 + 4


def test_reverse_explicit_none_is_the_reverse_complement_of_three_sequence_components() -> None:
    result = generate_multi_tu_combined_construct(
        project_id="reverse-explicit-none",
        project_name="Reverse explicit none",
        expression_units=[_explicit_none_unit(orientation="reverse")],
    )
    expected = str(Seq("AAAA" + "ATGAAATAA" + "TTTT").reverse_complement())
    assert result["combined_construct"]["dna"] == expected
    assert result["expression_units"][0]["dna"] == expected
    assert not any(
        row.get("biological_role") == "five_prime_region"
        for row in result["combined_construct"]["component_coordinates"]
    )


def test_explicit_none_is_formal_ready_when_every_required_registry_selection_is_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized_roles: list[str] = []

    def confirmed_registry_selection(
        _component_input: Mapping[str, Any],
        *,
        role: str,
        sequence: str,
        workflow_id: str,
    ) -> dict[str, Any]:
        normalized_roles.append(role)
        return {
            "source_type": "REGISTRY",
            "formal_selection_confirmed": True,
            "tu_role": role,
            "selected_sequence": sequence,
            "workflow_context": workflow_id,
        }

    monkeypatch.setattr(
        multi_tu_runtime,
        "normalize_component_selection",
        confirmed_registry_selection,
    )
    result = generate_multi_tu_combined_construct(
        project_id="formal-ready-explicit-none",
        project_name="Formal ready explicit none",
        expression_units=[_explicit_none_unit()],
    )

    assert normalized_roles == ["promoter", "cds", "3_prime_regulatory_region"]
    assert result["formal_validation"] == {
        "status": "formal_ready",
        "formal_ready": True,
        "findings": [],
    }


@pytest.mark.parametrize("required_role", ["promoter", "cds", "3_prime_regulatory_region"])
def test_explicit_none_does_not_make_a_missing_required_role_optional(required_role: str) -> None:
    unit = _explicit_none_unit()
    unit[required_role] = {}
    with pytest.raises(ValueError, match=rf"requires a non-empty {required_role} sequence"):
        generate_multi_tu_combined_construct(
            project_id=f"missing-{required_role}",
            project_name="Missing required role",
            expression_units=[unit],
        )


def test_unconfigured_five_prime_region_remains_a_step_three_blocker() -> None:
    helpers = _multi_tu_completion_helpers()
    unit = _unit(include_five_prime=False)
    unit["five_prime_region"] = {}
    assert helpers["_multi_tu_overall_ready"]([unit]) is False
    assert helpers["_multi_tu_required_role_blockers"]([unit]) == [
        {"unit_label": "TU1", "role": "five_prime_region"}
    ]
    with pytest.raises(ValueError, match="five_prime_region sequence"):
        generate_multi_tu_combined_construct(
            project_id="unconfigured-five-prime",
            project_name="Unconfigured five prime",
            expression_units=[unit],
        )


def test_four_role_snapshot_round_trips_and_preserves_genbank_traceability(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "four-role-project")
    result = generate_multi_tu_combined_construct(
        project_id="four-role-round-trip",
        project_name="Four role round trip",
        expression_units=[_unit()],
    )
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)

    five_prime = reopened["original_input"]["expression_units"][0]["five_prime_region"]
    assert five_prime["raw_text"] == "CCCC"
    assert five_prime["component_reference"]["tu_role"] == "five_prime_region"
    assert five_prime["component_reference"]["component_type"] == "five_prime_utr"
    assert reopened["combined_construct"] == result["combined_construct"]
    assert reopened["exports"]["combined_construct_fasta"]["data"] == result["exports"]["combined_construct_fasta"]["data"]
    assert reopened["exports"]["combined_construct_genbank"]["data"] == result["exports"]["combined_construct_genbank"]["data"]
    assert "USER_PROVIDED:five_prime_region" in reopened["exports"]["combined_construct_fasta"]["data"]

    record = next(SeqIO.parse(StringIO(reopened["exports"]["combined_construct_genbank"]["data"]), "genbank"))
    feature = next(
        item for item in record.features
        if item.qualifiers.get("unit_id") == ["TU1"]
        and item.qualifiers.get("biological_role") == ["five_prime_region"]
    )
    assert feature.qualifiers["component_type"] == ["five_prime_utr"]
    assert feature.qualifiers["source_type"] == ["USER_PROVIDED"]
    assert int(feature.location.start) + 1 > 0
    assert int(feature.location.end) > int(feature.location.start)


def test_explicit_none_round_trips_without_genbank_five_prime_entry(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "explicit-none-project")
    unit = _explicit_none_unit()
    result = generate_multi_tu_combined_construct(
        project_id="explicit-none-round-trip",
        project_name="Explicit none round trip",
        expression_units=[unit],
    )
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    reopened_unit = reopened["original_input"]["expression_units"][0]
    assert reopened_unit["five_prime_region"]["absence_state"] == "explicit_none"
    assert reopened_unit["five_prime_region"]["raw_text"] == ""
    assert reopened["combined_construct"]["dna"] == result["combined_construct"]["dna"]
    fasta_record = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_fasta"]["data"]),
            "fasta",
        )
    )
    record = next(
        SeqIO.parse(
            StringIO(reopened["exports"]["combined_construct_genbank"]["data"]),
            "genbank",
        )
    )
    assert str(fasta_record.seq) == reopened["combined_construct"]["dna"]
    assert str(record.seq) == reopened["combined_construct"]["dna"]
    assert not any(
        feature.qualifiers.get("biological_role") == ["five_prime_region"]
        for feature in record.features
    )


def test_formal_multi_tu_step_three_wires_five_prime_region_input() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    normalization = source.split("def _normalize_transcription_units", 1)[1].split(
        "def _blank_dual_tu_units", 1
    )[0]
    step_three = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _render_step_3_elements", 1
    )[0]
    element_input = source.split("def _render_dual_tu_element_input", 1)[1].split(
        "def _render_dual_tu_step_3", 1
    )[0]
    structure = source.split("def _render_dual_tu_structure", 1)[1].split(
        "def _render_pcambia1300_workflow_block", 1
    )[0]

    assert '"five_prime_region"' in normalization
    assert '"5\' region"' in step_three
    assert 'role="five_prime_region"' in step_three
    assert '"five_prime_region": five_prime_region' in step_three
    assert "and five_prime_region" in step_three
    assert "v1.expression.no_formal_five_prime_region_records_user_sequence_allowed" in step_three
    assert "不使用独立 5′ region" in element_input
    assert '"absence_state": "explicit_none"' in element_input
    assert "five_prime_region" in structure


def test_multi_tu_step_three_widgets_have_single_session_state_owner() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    helper = source.split("def _render_dual_tu_element_input", 1)[1].split(
        "def _render_dual_tu_step_3", 1
    )[0]

    assert "_prepare_multi_tu_editor_widget_state()" in source
    assert "_formal_multi_tu_widget_state_marker" in source
    widget_default_lines = [
        line.lstrip()
        for line in helper.splitlines()
        if line.lstrip().startswith(("default=", "index=", "value="))
    ]
    assert widget_default_lines == []
    assert 'key=f"formal_{unit_id.lower()}_{role}_mode"' in helper
    assert 'key=f"formal_{unit_id.lower()}_{role}_name"' in helper
    assert 'key=f"formal_{unit_id.lower()}_{role}_text"' in helper


def test_multi_tu_shared_ui_keeps_planning_in_step_two_and_review_copy_human_readable() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    step_three = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _render_step_3_elements", 1
    )[0]
    step_five = source.split("def _render_generic_multi_tu_step_5", 1)[1].split(
        "def _step5_construct_preview_html", 1
    )[0]
    step_six = source.split("def _render_step_6_review", 1)[1].split(
        "def _render_step_6_complete", 1
    )[0]
    results = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_persisted_result_downloads", 1
    )[0]

    assert "v1.expression.step_uses_only_tu_layout_saved_step" in step_three
    assert "formal_multi_tu_add" not in step_three
    assert "_move_transcription_unit" not in step_three
    assert "_delete_transcription_unit" not in step_three
    assert '"five_prime_region",' in results
    assert "_multi_tu_source_label(" in results
    assert "_multi_tu_evidence_label(" in results
    assert "USER_PROVIDED" not in results
    assert "UNVERIFIED_USER_INPUT" not in results
    assert "v1.expression.complete_transcriptional_unit_tu_required_sequence_elements" in step_five
    assert "四角色完整 TU" not in step_five
    validation_copy = source.split("def _multi_tu_formal_validation_copy", 1)[1].split(
        "def _active_backbone_workflow_id", 1
    )[0]
    assert "v1.expression.multi_tu_validation_ready_status" in validation_copy
    assert "v1.expression.multi_tu_validation_ready_prompt" in validation_copy
    assert "四角色序列已记录" not in validation_copy
    assert "MISSING_FIVE_PRIME_REGION" in step_five
    assert "v1.expression.final_review" in step_six


def test_mtu_step6_i18n_presentation_contract_localizes_system_labels_and_formats_review_status() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    results = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_persisted_result_downloads", 1
    )[0]
    assert "_t('v1.expression.final_review')" in source
    assert "_t('v1.common.yes' if bool(combined.get('contains_vector')) else 'v1.common.no')" in results
    assert '"组件角色"' in results
    assert '"来源 accession/version"' in results
    assert '"来源物种"' in results
    assert '"目标宿主元数据"' in results
    assert "_ui(\"不适用\")" in results
    assert "_t(\"v1.expression.pending_human_review\", p0=review_detail)" in source


def test_mtu_step6_review_status_placeholder_is_filled_in_both_locales() -> None:
    from core.i18n import translate

    for language, expected_prefix in (("en", "Pending human review: "), ("zh-CN", "待人工复核事项：")):
        rendered = translate(
            "v1.expression.pending_human_review",
            language=language,
            p0="User-provided source",
        )
        assert rendered.startswith(expected_prefix)
        assert "{...}" not in rendered
        assert "{" not in rendered and "}" not in rendered


def test_mtu_step6_source_detail_system_headers_round_trip_by_locale() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"_CONTROLLED_UI_LABELS", "_ui", "_localized_rows"}
    nodes = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted for target in node.targets
        ))
    ]
    language = "en"
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "_get_language": lambda: language,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py:r3", "exec"), namespace)
    row = {"组件角色": "启动子", "来源": "用户提供", "边界": "1..8", "不适用": "不适用"}
    assert set(namespace["_localized_rows"](row)) == {
        "Component role", "Source", "Boundary", "Not applicable"
    }
    language = "zh-CN"
    assert set(namespace["_localized_rows"](row)) == set(row)


def test_multi_tu_feature_level_table_uses_display_labels_only() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    step_four = source.split("def _render_generic_multi_tu_step_4", 1)[1].split(
        "def _render_dual_tu_step_4", 1
    )[0]

    assert "_t('v1.results_final_report.role')" in step_four
    assert "_t('v1.results_final_report.component')" in step_four
    assert "_t('v1.common.orientation')" in step_four
    assert "_t('v1.common.reverse') if strand < 0 else _t('v1.common.forward')" in step_four
    assert '"promoter": "启动子"' in source
    assert '"five_prime_region": "5′ region / 5′ UTR"' in source
    assert '"cds": "CDS"' in source
    assert '"3_prime_regulatory_region": "3′ 调控区"' in source


def test_formal_multi_tu_step_two_uses_only_the_approved_plan_editor_and_gate() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    step_two = source.split("def _render_dual_tu_step_2", 1)[1].split(
        "def _render_step_2_cds", 1
    )[0]
    statuses = source.split("def _formal_step_statuses", 1)[1].split(
        "def _is_result_preview_mode", 1
    )[0]
    route = source.split("def _render_step_2_cds", 1)[1].split(
        "def _render_dual_tu_element_input", 1
    )[0]

    assert "if _is_pathway_multi_tu_project()" in step_two
    assert "st.tabs(" not in step_two
    assert "TU{index} 规划" not in step_two
    assert "v1.expression.tu_name" in step_two
    assert "v1.common.orientation" in step_two
    assert '"stable ID"' in step_two
    assert "st.selectbox(" in step_two
    assert "v1.expression.save_tu_plan_continue" in step_two
    assert 'next_action=save_tu_plan_and_continue' in step_two
    assert 'st.button("保存 TU 规划并继续"' not in step_two
    assert 'state.get("formal_multi_tu_step2_planning_signature")' in statuses
    assert "_multi_tu_step2_planning_signature(planned_units)" in statuses
    assert "_render_dual_tu_step_2(ds)" in route


class _SessionState:
    def __init__(self, state: dict[str, Any]) -> None:
        self.session_state = state


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _four_role_units() -> list[dict[str, Any]]:
    def unit(unit_id: str) -> dict[str, Any]:
        return {
            "unit_id": unit_id,
            "display_name": unit_id,
            "promoter": {"raw_text": "AAAA"},
            "five_prime_region": {"raw_text": "CCCC"},
            "cds": {"raw_text": "ATGAAATAA"},
            "3_prime_regulatory_region": {"raw_text": "TTTT"},
        }

    return [unit("TU1"), unit("TU2")]


def _multi_tu_completion_helpers() -> dict[str, Any]:
    return _app_functions(
        "_multi_tu_required_role_blockers",
        "_multi_tu_overall_ready",
        "_is_explicit_five_prime_absence",
        "_multi_tu_generation_error_message",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "re": __import__("re"),
            "_MULTI_TU_EDITOR_REQUIRED_ROLES": (
                "promoter",
                "five_prime_region",
                "cds",
                "3_prime_regulatory_region",
            ),
            "_MULTI_TU_ROLE_LABELS": {
                "promoter": "启动子",
                "five_prime_region": "5′ region / 5′ UTR",
                "cds": "CDS",
                "3_prime_regulatory_region": "3′ 调控区",
            },
        },
    )


def test_multi_tu_overall_ready_uses_all_units_required_roles_not_active_tab() -> None:
    helpers = _multi_tu_completion_helpers()
    units = _four_role_units()

    assert helpers["_multi_tu_overall_ready"](units) is True
    assert helpers["_multi_tu_overall_ready"](list(reversed(units))) is True
    assert helpers["_multi_tu_overall_ready"](
        [{**unit, "targeting_sequence": {}, "linker": {}, "fusion_tag": {}} for unit in units]
    ) is True


def test_multi_tu_overall_ready_identifies_the_missing_required_role() -> None:
    helpers = _multi_tu_completion_helpers()
    units = _four_role_units()
    units[1]["five_prime_region"] = {}

    assert helpers["_multi_tu_overall_ready"](units) is False
    assert helpers["_multi_tu_required_role_blockers"](units) == [
        {"unit_label": "TU2", "role": "five_prime_region"}
    ]
    assert "TU2" in helpers["_multi_tu_generation_error_message"](ValueError(""), units)
    assert "5′ region / 5′ UTR" in helpers["_multi_tu_generation_error_message"](ValueError(""), units)


def test_generated_multi_tu_marks_step_three_complete_and_step_four_reachable() -> None:
    helpers = _multi_tu_completion_helpers()
    units = _four_role_units()
    state = {
        "formal_project_definition": {"project_name": "Current Multi-TU", "plant_host": "Rice"},
        "formal_transcription_units": units,
        "formal_multi_tu_step2_planning_signature": "saved-plan",
        "mvp_vector_result": {"result_kind": "multi_tu_expression_assembly", "input_signature": "current"},
        "mvp_current_input_signature": "current",
        "mvp_inputs_stale": False,
        "formal_multi_tu_active_tab": "TU2",
    }
    functions = _app_functions(
        "_formal_step_statuses",
        "_normalize_formal_current_step",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "st": _SessionState(state),
            "_host_supports_project_type": lambda *_args: True,
            "_formal_project_type": lambda: "dual_tu",
            "_is_pathway_multi_tu_project": lambda: False,
            "_is_generic_multi_tu_workflow": lambda: True,
            "_multi_tu_step2_planned_units": lambda value: value,
            "_multi_tu_step2_planning_signature": lambda _value: "saved-plan",
            "_multi_tu_overall_ready": helpers["_multi_tu_overall_ready"],
            "_is_multi_tu_expression_assembly": lambda result: result.get("result_kind") == "multi_tu_expression_assembly",
            "_formal_ui_signature": lambda _value: "unused",
        },
    )

    statuses = functions["_formal_step_statuses"]()
    assert [status["done"] for status in statuses[:6]] == [True, True, True, False, False, False]
    assert functions["_normalize_formal_current_step"](4, statuses=statuses) == 4

    state["formal_multi_tu_step4_confirmation_signature"] = "unused"
    confirmed_statuses = functions["_formal_step_statuses"]()
    assert [status["done"] for status in confirmed_statuses[:6]] == [True, True, True, True, False, False]
