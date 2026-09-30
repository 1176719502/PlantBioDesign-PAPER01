from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from uuid import uuid4

from Bio import SeqIO
import pytest

from services.canonical_construct_runtime import active_complete_plasmid_snapshot, active_construct_snapshot
from services.mvp_multi_tu_persistence import (
    MVP_MULTI_TU_PERSISTENCE_KEY,
    MvpMultiTuPersistenceError,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import (
    MULTI_TU_EXPRESSION_ASSEMBLY,
    generate_multi_tu_combined_construct,
    generate_multi_tu_construct,
    set_multi_tu_unit_order,
    set_multi_tu_unit_orientation,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_mvp9_multi_tu_runtime import DATA, _make_backbone_genbank, _reverse_complement, _units_for_case


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _three_units() -> list[dict[str, Any]]:
    units = _units_for_case(DATA["cases"][0])
    units[0].update(
        {
            "unit_id": "unit-alb-target",
            "display_name": "ALB target gene expression unit",
            "unit_name": "ALB target gene expression unit",
            "order": 1,
            "3_prime_regulatory_region": units[0].pop("terminator"),
            "linker": {
                "display_name": "Traceable test linker fixture",
                "sequence": "GGTGGT",
                "source_type": "test_fixture",
                "source_name": "tests/test_gate2_formal_multi_tu_workflow.py",
            },
        }
    )
    units[1].update(
        {
            "unit_id": "unit-plant-selection",
            "display_name": "Plant selection marker expression unit",
            "unit_name": "Plant selection marker expression unit",
            "order": 2,
            "3_prime_regulatory_region": units[1].pop("terminator"),
        }
    )
    units.append(
        {
            "unit_id": "unit-reporter",
            "display_name": "Reporter expression unit",
            "unit_name": "Reporter expression unit",
            "order": 3,
            "orientation": "reverse",
            "promoter": {
                "display_name": "Reporter promoter test fixture",
                "sequence": "TTGCAACC",
                "source_type": "test_fixture",
                "source_name": "tests/test_gate2_formal_multi_tu_workflow.py",
            },
            "targeting_sequence": {
                "display_name": "Reporter targeting test fixture",
                "sequence": "ATGAAA",
                "source_type": "test_fixture",
                "source_name": "tests/test_gate2_formal_multi_tu_workflow.py",
            },
            "cds": {
                "display_name": "Reporter CDS test fixture",
                "sequence": "ATGGTGAAATAA",
                "source_type": "test_fixture",
                "source_name": "tests/test_gate2_formal_multi_tu_workflow.py",
            },
            "3_prime_regulatory_region": {
                "display_name": "Reporter 3-prime regulatory test fixture",
                "sequence": "GCGTAT",
                "source_type": "test_fixture",
                "source_name": "tests/test_gate2_formal_multi_tu_workflow.py",
            },
        }
    )
    return units


def _generate_three_tu() -> dict[str, Any]:
    return _generate_three_tu_with_ids(
        ["unit-alb-target", "unit-plant-selection", "unit-reporter"]
    )


def _generate_three_tu_with_ids(
    unit_ids: list[str],
    *,
    unit_order: list[int] | None = None,
    reporter_orientation: str = "reverse",
) -> dict[str, Any]:
    units = _three_units()
    for index, (unit, unit_id) in enumerate(zip(units, unit_ids, strict=True)):
        unit["unit_id"] = unit_id
        unit["order"] = (unit_order or [1, 2, 3])[index]
    units[2]["orientation"] = reporter_orientation
    result = generate_multi_tu_construct(
        project_id="gate2-three-tu-fixed-fixture",
        project_name="Gate 2 three-TU fixed test fixture",
        expression_units=units,
        backbone={
            "display_name": "MVP9_BACKBONE test fixture",
            "raw_text": _make_backbone_genbank(),
            "source_format": "genbank",
            "source_type": "test_fixture",
            "source_name": "tests/data/mvp9_multi_tu_cases.json",
        },
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 40,
            "end_coordinate": 41,
            "insertion_orientation": "forward",
            "user_confirmation": True,
        },
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "project_type": "dual_tu",
        "host_key": "Rice (O. sativa)",
        "expression_target": "Three-TU software acceptance fixture; not a biological validation claim",
        "current_step": 6,
    }
    return result


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def test_three_tu_canonical_sequence_reverse_coordinates_and_non_overlap() -> None:
    result = _generate_three_tu()
    units = result["expression_units"]
    assert len(units) == 3
    assert result["unit_order"] == ["unit-alb-target", "unit-plant-selection", "unit-reporter"]
    reporter_forward = "TTGCAACC" + "ATGAAA" + "ATGGTGAAATAA" + "GCGTAT"
    assert units[2]["dna"] == _reverse_complement(reporter_forward)
    assert units[2]["range"]["strand"] == -1
    assert {row["strand"] for row in units[2]["components"]} == {-1}
    assert {row["biological_role"] for row in units[2]["components"]} == {
        "promoter",
        "targeting_sequence",
        "cds",
        "3_prime_regulatory_region",
    }
    ranges = [unit["range"] for unit in units]
    assert ranges[0]["end"] < ranges[1]["start"]
    assert ranges[1]["end"] < ranges[2]["start"]
    assert all(1 <= row["start"] <= row["end"] <= result["combined_construct"]["total_length"] for row in result["combined_construct"]["component_coordinates"])


def test_three_tu_fasta_genbank_and_unit_fastas_share_canonical_sequences() -> None:
    result = _generate_three_tu()
    exports = result["exports"]
    complete_fasta = next(SeqIO.parse(StringIO(exports["complete_plasmid_fasta"]["data"]), "fasta"))
    complete_genbank = next(SeqIO.parse(StringIO(exports["complete_plasmid_genbank"]["data"]), "genbank"))
    combined_fasta = next(SeqIO.parse(StringIO(exports["combined_construct_fasta"]["data"]), "fasta"))
    assert str(complete_fasta.seq).upper() == str(complete_genbank.seq).upper() == result["complete_plasmid"]["dna"]
    assert str(combined_fasta.seq).upper() == result["combined_construct"]["dna"]
    for unit in result["expression_units"]:
        unit_fasta = next(SeqIO.parse(StringIO(exports["unit_fastas"][unit["unit_id"]]["data"]), "fasta"))
        assert str(unit_fasta.seq).upper() == unit["dna"]


def test_three_tu_genbank_features_keep_unit_id_role_and_strand() -> None:
    result = _generate_three_tu()
    record = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    reporter_features = [
        feature
        for feature in record.features
        if (feature.qualifiers.get("unit_order") or [""])[0] == "3"
    ]
    assert len(reporter_features) == 5
    reporter_export_ids = {
        (feature.qualifiers.get("unit_id") or [""])[0]
        for feature in reporter_features
    }
    assert reporter_export_ids == {"unit-reporter"}
    assert all(int(feature.location.strand or 1) == -1 for feature in reporter_features)
    component_roles = {
        (feature.qualifiers.get("biological_role") or [""])[0]
        for feature in reporter_features
        if feature.qualifiers.get("biological_role")
    }
    assert component_roles == {"promoter", "targeting_sequence", "cds", "3_prime_regulatory_region"}


def test_independent_equivalent_three_tu_builds_have_stable_genbank_bytes_and_traceability(
    tmp_path: Path,
) -> None:
    first_runtime_ids = [f"tu-{uuid4().hex}" for _ in range(3)]
    second_runtime_ids = [f"tu-{uuid4().hex}" for _ in range(3)]
    first = _generate_three_tu_with_ids(first_runtime_ids)
    second = _generate_three_tu_with_ids(second_runtime_ids)

    assert first_runtime_ids != second_runtime_ids
    assert [unit["unit_id"] for unit in first["expression_units"]] == first_runtime_ids
    assert [unit["unit_id"] for unit in second["expression_units"]] == second_runtime_ids
    assert first["complete_plasmid"]["dna"] == second["complete_plasmid"]["dna"]

    semantic_keys = ("feature_type", "name", "start", "end", "strand")
    first_feature_semantics = [
        tuple(feature.get(key) for key in semantic_keys)
        for feature in first["complete_plasmid"]["feature_coordinates"]
    ]
    second_feature_semantics = [
        tuple(feature.get(key) for key in semantic_keys)
        for feature in second["complete_plasmid"]["feature_coordinates"]
    ]
    assert first_feature_semantics == second_feature_semantics

    first_genbank = first["exports"]["complete_plasmid_genbank"]["data"]
    second_genbank = second["exports"]["complete_plasmid_genbank"]["data"]
    assert first_genbank.encode("utf-8") == second_genbank.encode("utf-8")
    first_hash = hashlib.sha256(first_genbank.encode("utf-8")).hexdigest()
    assert first_hash == hashlib.sha256(second_genbank.encode("utf-8")).hexdigest()
    assert all(runtime_id not in first_genbank for runtime_id in first_runtime_ids)
    assert all(runtime_id not in second_genbank for runtime_id in second_runtime_ids)

    first_record = SeqIO.read(StringIO(first_genbank), "genbank")
    second_record = SeqIO.read(StringIO(second_genbank), "genbank")
    stable_ids_by_order: dict[str, set[str]] = {}
    for feature in first_record.features:
        unit_order_value = (feature.qualifiers.get("unit_order") or [""])[0]
        stable_unit_id = (feature.qualifiers.get("unit_id") or [""])[0]
        if unit_order_value and stable_unit_id:
            stable_ids_by_order.setdefault(unit_order_value, set()).add(stable_unit_id)
    assert set(stable_ids_by_order) == {"1", "2", "3"}
    assert all(len(values) == 1 for values in stable_ids_by_order.values())
    stable_unit_ids = {next(iter(values)) for values in stable_ids_by_order.values()}
    assert len(stable_unit_ids) == 3
    assert all(re.fullmatch(r"tu-\d{3}-[0-9a-f]{16}", value) for value in stable_unit_ids)
    assert [feature.qualifiers for feature in first_record.features] == [
        feature.qualifiers for feature in second_record.features
    ]

    reordered = _generate_three_tu_with_ids(
        [f"tu-{uuid4().hex}" for _ in range(3)],
        unit_order=[2, 1, 3],
    )
    reoriented = _generate_three_tu_with_ids(
        [f"tu-{uuid4().hex}" for _ in range(3)],
        reporter_orientation="forward",
    )
    assert reordered["exports"]["complete_plasmid_genbank"]["data"] != first_genbank
    assert reoriented["exports"]["complete_plasmid_genbank"]["data"] != first_genbank

    storage = tmp_path / "stable-genbank-cold-start"
    repository = PlantProjectDraftRepository(storage)
    saved = save_mvp_multi_tu_design(first, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert reopened["exports"]["complete_plasmid_genbank"]["data"].encode("utf-8") == first_genbank.encode("utf-8")
    command = (
        "import hashlib; "
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "print(hashlib.sha256(r['exports']['complete_plasmid_genbank']['data'].encode('utf-8')).hexdigest())"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(storage)},
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == first_hash


def test_three_tu_order_and_orientation_changes_make_both_outputs_stale() -> None:
    result = _generate_three_tu()
    reordered = set_multi_tu_unit_order(
        result["runtime"],
        ["unit-reporter", "unit-alb-target", "unit-plant-selection"],
    )
    assert active_construct_snapshot(reordered)["construct_status"] == "stale"
    assert active_complete_plasmid_snapshot(reordered)["construct_status"] == "stale"
    reoriented = set_multi_tu_unit_orientation(
        result["runtime"],
        unit_id="unit-plant-selection",
        orientation="reverse",
    )
    assert active_construct_snapshot(reoriented)["construct_status"] == "stale"
    assert active_complete_plasmid_snapshot(reoriented)["construct_status"] == "stale"


def test_dynamic_state_add_move_delete_preserves_surviving_unit_ids() -> None:
    class _Streamlit:
        session_state = {
            "formal_transcription_units": [
                {"unit_id": "stable-a", "display_name": "A", "order": 1},
                {"unit_id": "stable-b", "display_name": "B", "order": 2},
                {"unit_id": "stable-c", "display_name": "C", "order": 3},
            ],
            "formal_dual_tu_combined_result": {"dna": "old"},
            "mvp_vector_result": {"dna": "old-complete"},
        }

    names = (
        "_default_transcription_unit_display_name",
        "_new_transcription_unit",
        "_normalize_transcription_units",
        "_store_transcription_units",
        "_transcription_units",
        "_dual_tu_order",
        "_invalidate_dual_tu_outputs",
        "_invalidate_dual_tu_unit",
        "_add_transcription_unit",
        "_delete_transcription_unit",
        "_move_transcription_unit",
    )
    functions = _app_functions(*names, namespace={"Any": Any, "st": _Streamlit(), "uuid4": uuid4})
    functions["_move_transcription_unit"]("stable-c", -1)
    assert functions["_dual_tu_order"]() == ["stable-a", "stable-c", "stable-b"]
    functions["_delete_transcription_unit"]("stable-b")
    assert functions["_dual_tu_order"]() == ["stable-a", "stable-c"]
    added_id = functions["_add_transcription_unit"]()
    assert added_id not in {"stable-a", "stable-b", "stable-c"}
    assert functions["_dual_tu_order"]()[:2] == ["stable-a", "stable-c"]
    assert "formal_dual_tu_combined_result" not in _Streamlit.session_state
    assert "mvp_vector_result" not in _Streamlit.session_state
    assert _Streamlit.session_state["mvp_inputs_stale"] is True


def test_legacy_dual_dict_maps_deterministically_to_ordered_list() -> None:
    functions = _app_functions(
        "_default_transcription_unit_display_name",
        "_new_transcription_unit",
        "_normalize_transcription_units",
        namespace={"Any": Any, "uuid4": uuid4},
    )
    legacy = {
        "TU1": {"unit_id": "TU1", "unit_name": "Legacy target", "terminator": {"raw_text": "AAA"}},
        "TU2": {"unit_id": "TU2", "unit_name": "Legacy marker", "terminator": {"raw_text": "CCC"}},
    }
    units = functions["_normalize_transcription_units"](legacy, ["TU2", "TU1"])
    assert [unit["unit_id"] for unit in units] == ["TU2", "TU1"]
    assert [unit["order"] for unit in units] == [1, 2]
    assert units[0]["3_prime_regulatory_region"]["raw_text"] == "CCC"


def test_dynamic_state_rejects_duplicate_stable_unit_ids() -> None:
    functions = _app_functions(
        "_default_transcription_unit_display_name",
        "_new_transcription_unit",
        "_normalize_transcription_units",
        namespace={"Any": Any, "uuid4": uuid4},
    )
    with pytest.raises(ValueError, match="Duplicate transcription-unit unit_id"):
        functions["_normalize_transcription_units"](
            [
                {"unit_id": "stable-duplicate", "order": 1},
                {"unit_id": "stable-duplicate", "order": 2},
            ]
        )


def test_formal_tu_management_stays_in_step2_and_step3_is_read_only() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step2 = source.split("def _render_dual_tu_step_2", 1)[1].split(
        "def _render_step_2_cds", 1
    )[0]
    step3 = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _optional_input", 1
    )[0]

    assert "formal_multi_tu_add" in step2
    assert "formal_{unit_id}_delete_confirm" in step2
    assert "formal_{unit_id}_delete_cancel" in step2
    assert "_move_transcription_unit" in step2
    assert "v1.expression.save_tu_plan_continue" in step2

    assert "`{unit_id}`" not in step3
    assert "formal_multi_tu_add" not in step3
    assert "formal_{unit_id}_delete_confirm" not in step3
    assert "formal_{unit_id}_delete_cancel" not in step3
    assert "_move_transcription_unit" not in step3


def test_default_transcription_unit_names_are_chinese_and_stable_for_existing_values() -> None:
    functions = _app_functions(
        "_default_transcription_unit_display_name",
        "_blank_dual_tu_units",
        "_normalize_transcription_units",
        "_new_transcription_unit",
        namespace={"Any": Any, "uuid4": uuid4},
    )
    defaults = [functions["_default_transcription_unit_display_name"](index) for index in range(1, 6)]
    assert defaults[:3] == ["目标基因表达单元", "植物选择标记表达单元", "报告基因表达单元"]
    assert defaults[3:] == ["转录单元 4", "转录单元 5"]
    blank = functions["_blank_dual_tu_units"]()
    assert [unit["display_name"] for unit in blank] == ["目标基因表达单元", "植物选择标记表达单元"]
    preserved = functions["_normalize_transcription_units"](
        [
            {"unit_id": "preserved-a", "display_name": "Legacy English A", "order": 1},
            {"unit_id": "preserved-b", "unit_name": "Legacy English B", "order": 2},
            {"unit_id": "preserved-c", "order": 3},
            {"unit_id": "preserved-d", "order": 4},
        ]
    )
    assert [unit["display_name"] for unit in preserved] == [
        "Legacy English A",
        "Legacy English B",
        "报告基因表达单元",
        "转录单元 4",
    ]


def test_three_tu_expression_assembly_preserves_order_boundaries_and_has_no_vector() -> None:
    result = generate_multi_tu_combined_construct(
        project_id="formal-three-tu-assembly",
        project_name="Formal three TU assembly",
        expression_units=_three_units(),
    )

    assert result["result_kind"] == MULTI_TU_EXPRESSION_ASSEMBLY
    assert result["contains_vector"] is False
    assert result["unit_order"] == ["unit-alb-target", "unit-plant-selection", "unit-reporter"]
    assert len(result["expression_units"]) == 3
    ranges = [unit["range"] for unit in result["expression_units"]]
    assert ranges[0]["start"] == 1
    assert ranges[0]["end"] < ranges[1]["start"] <= ranges[1]["end"] < ranges[2]["start"]
    assert ranges[2]["end"] == result["combined_construct"]["total_length"]
    assert result["combined_construct"]["sequence_sha256"] == hashlib.sha256(
        result["combined_construct"]["dna"].encode("ascii")
    ).hexdigest()
    assert "complete_plasmid" not in result
    assert "complete_plasmid_fasta" not in result["exports"]


def test_formal_generic_multi_tu_routes_around_vector_upload_and_exposes_assembly_results() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step4 = source.split("def _render_step_4_backbone", 1)[1].split("def _generate_dual_tu_complete_plasmid", 1)[0]
    assert step4.index("if _is_generic_multi_tu_workflow():") < step4.index("上传 GenBank")
    assert "_render_generic_multi_tu_step_4(ds)" in step4
    assert "MULTI_TU_EXPRESSION_ASSEMBLY" in source
    assert "v1.results_final_report.canonical_fasta_label" in source
    assert "v1.results_final_report.canonical_genbank_label" in source
    assembly_results = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_results_export_content", 1
    )[0]
    assert "build_multi_tu_professional_review_package" not in assembly_results
    assert '"专业审查包 ZIP"' not in assembly_results
    results_route = source.split("def _render_results_export_content", 1)[1].split(
        "def _render_plant_parts_library", 1
    )[0]
    assert "save_design=save_mvp_multi_tu_design" in results_route
    assert "build_multi_tu_professional_review_package" not in results_route


def test_delete_target_helpers_are_single_selection_and_clearable() -> None:
    class _Streamlit:
        session_state = {"formal_dual_tu_delete_target": "unit-a"}

    functions = _app_functions(
        "_dual_tu_delete_target",
        "_set_dual_tu_delete_target",
        "_clear_dual_tu_delete_target",
        namespace={"Any": Any, "st": _Streamlit()},
    )
    assert functions["_dual_tu_delete_target"]() == "unit-a"
    functions["_set_dual_tu_delete_target"]("unit-b")
    assert functions["_dual_tu_delete_target"]() == "unit-b"
    functions["_clear_dual_tu_delete_target"]()
    assert functions["_dual_tu_delete_target"]() == ""


def test_three_tu_save_reopen_and_fresh_process_keep_ids_order_and_sequence(monkeypatch, tmp_path: Path) -> None:
    storage = tmp_path / "three-tu-cold-start"
    repository = PlantProjectDraftRepository(storage)
    result = _generate_three_tu()
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert [unit["unit_id"] for unit in reopened["expression_units"]] == [
        "unit-alb-target",
        "unit-plant-selection",
        "unit-reporter",
    ]
    assert reopened["runtime"] == result["runtime"]
    assert reopened["complete_plasmid"]["sequence_sha256"] == result["complete_plasmid"]["sequence_sha256"]

    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(storage))
    command = (
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "import json; print(json.dumps({'ids':[u['unit_id'] for u in r['expression_units']],"
        "'order':r['unit_order'],'sha':r['complete_plasmid']['sequence_sha256']}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(storage)},
        check=True,
        capture_output=True,
        text=True,
    )
    cold = json.loads(completed.stdout.strip())
    assert cold["ids"] == ["unit-alb-target", "unit-plant-selection", "unit-reporter"]
    assert cold["order"] == ["unit-alb-target", "unit-plant-selection", "unit-reporter"]
    assert cold["sha"] == result["complete_plasmid"]["sequence_sha256"]


def test_legacy_dual_snapshot_without_unit_fastas_reopens_from_canonical_runtime(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "legacy-dual-no-unit-fastas")
    result = generate_multi_tu_construct(
        project_id="legacy-dual-no-unit-fastas",
        project_name="Legacy dual-TU compatibility fixture",
        expression_units=_units_for_case(DATA["cases"][0]),
        backbone={
            "display_name": "MVP9_BACKBONE test fixture",
            "raw_text": _make_backbone_genbank(),
            "source_format": "genbank",
            "source_type": "test_fixture",
            "source_name": "tests/data/mvp9_multi_tu_cases.json",
        },
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 40,
            "end_coordinate": 41,
            "insertion_orientation": "forward",
            "user_confirmation": True,
        },
    )
    result["project_type"] = "dual_tu"
    saved = save_mvp_multi_tu_design(result, repository=repository)
    draft = repository.load(saved.project_id)
    payload = draft.manual_review_state[MVP_MULTI_TU_PERSISTENCE_KEY]
    payload["exports"].pop("unit_fastas")
    repository.save(draft)

    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)

    assert set(reopened["exports"]["unit_fastas"]) == {"TU1", "TU2"}
    for unit in reopened["expression_units"]:
        record = next(
            SeqIO.parse(StringIO(reopened["exports"]["unit_fastas"][unit["unit_id"]]["data"]), "fasta")
        )
        assert str(record.seq).upper() == unit["dna"]


def test_formal_app_uses_one_dynamic_multi_tu_model_and_t_dna_gate() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    assert 'st.session_state["formal_transcription_units"]' in source
    assert "_add_transcription_unit" in source
    assert "_delete_transcription_unit" in source
    assert "_move_transcription_unit" in source
    assert "validate_t_dna_operation" in ast.get_source_segment(
        source,
        next(
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_generate_dual_tu_complete_plasmid"
        ),
    )
    assert "triple_tu" not in source


def test_persistence_blocks_tampered_fasta_before_save(tmp_path: Path) -> None:
    result = _generate_three_tu()
    tampered = deepcopy(result)
    fasta = tampered["exports"]["complete_plasmid_fasta"]["data"]
    header, sequence = fasta.split("\n", 1)
    replacement = "A" if sequence[0] != "A" else "T"
    tampered["exports"]["complete_plasmid_fasta"]["data"] = header + "\n" + replacement + sequence[1:]
    with pytest.raises(MvpMultiTuPersistenceError, match="does not match the canonical sequence"):
        save_mvp_multi_tu_design(
            tampered,
            repository=PlantProjectDraftRepository(tmp_path / "tampered-export"),
        )
