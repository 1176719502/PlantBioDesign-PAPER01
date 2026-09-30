from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from io import StringIO

from services.mvp_multi_tu_persistence import (
    list_mvp_multi_tu_designs,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import (
    generate_multi_tu_combined_construct,
    generate_multi_tu_complete_plasmid,
    set_multi_tu_unit_orientation,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_mvp9_multi_tu_runtime import (
    DATA,
    _generate,
    _make_backbone_genbank,
    _reverse_complement,
    _units_for_case,
)


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _formal_result(case_index: int = 0) -> dict[str, Any]:
    result = _generate(DATA["cases"][case_index])
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "project_type": "dual_tu",
        "host_key": "Rice (O. sativa)",
        "expression_target": "Gate 2 deterministic dual TU case",
        "current_step": 6,
    }
    return result


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def test_formal_app_keeps_four_pages_six_steps_and_adds_dual_tu_mode() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    steps = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "_FORMAL_STEPS"
    )

    assert len(steps) == 6
    assert source.count("PAGE_") > 0
    assert 'PROJECT_TYPE_DUAL_TU = "dual_tu"' in source
    assert "v1.project_center.new_multi_tu_project" in source
    assert "v1.project_center.new_multi_tu_project" in source
    assert "generate_multi_tu_combined_construct" in source
    assert "generate_admitted_multi_tu_complete_plasmid" in source
    assert "result = generate_multi_tu_complete_plasmid(" not in source
    assert "from prototypes" not in source
    assert "v1.expression.topology_position_overall_orientation" in source
    assert "v1.results_final_report.tu_order_backbone_insertion_orientation" in source
    assert "v1.expression.full_plasmid_sha_256" in source


def test_tu_inputs_have_independent_signatures_and_deterministic_lengths() -> None:
    combined = generate_multi_tu_combined_construct(
        project_id="gate2-signatures",
        project_name="Gate 2 signatures",
        expression_units=_units_for_case(DATA["cases"][0]),
    )

    by_unit = {unit["unit_id"]: unit for unit in combined["expression_units"]}
    assert by_unit["TU1"]["length"] == 28
    assert by_unit["TU2"]["length"] == 31
    assert combined["combined_construct"]["total_length"] == 59
    assert set(combined["unit_input_signatures"]) == {"TU1", "TU2"}
    assert combined["unit_input_signatures"]["TU1"] != combined["unit_input_signatures"]["TU2"]
    assert all(len(value) == 64 for value in combined["unit_input_signatures"].values())
    assert len(combined["combined_construct"]["input_signature"]) == 64

    reordered = generate_multi_tu_combined_construct(
        project_id="gate2-signatures-reordered",
        project_name="Gate 2 signatures reordered",
        expression_units=_units_for_case(DATA["cases"][5]),
    )
    assert combined["unit_input_signatures"] == reordered["unit_input_signatures"]

    changed_runtime = set_multi_tu_unit_orientation(
        combined["runtime"], unit_id="TU2", orientation="reverse"
    )
    changed_signatures = {
        unit["unit_id"]: unit["input_signature"]
        for unit in changed_runtime["expression_units"]
    }
    assert changed_signatures["TU1"] == combined["unit_input_signatures"]["TU1"]
    assert changed_signatures["TU2"] != combined["unit_input_signatures"]["TU2"]


def test_overall_reverse_insertion_is_separate_from_each_tu_orientation() -> None:
    case = DATA["cases"][0]
    combined = generate_multi_tu_combined_construct(
        project_id="gate2-overall-reverse",
        project_name="Gate 2 overall reverse",
        expression_units=_units_for_case(case),
    )
    complete = generate_multi_tu_complete_plasmid(
        combined,
        backbone={
            "display_name": "MVP9_BACKBONE",
            "raw_text": _make_backbone_genbank(),
            "source_format": "genbank",
            "source_type": "upload",
            "source_name": "mvp9_backbone.gb",
        },
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 40,
            "end_coordinate": 41,
            "insertion_orientation": "reverse",
            "user_confirmation": True,
        },
    )

    backbone = DATA["backbone"]["sequence"]
    expected = backbone[:40] + _reverse_complement(combined["combined_construct"]["dna"]) + backbone[40:]
    assert complete["complete_plasmid"]["dna"] == expected
    assert [unit["orientation"] for unit in complete["expression_units"]] == ["forward", "forward"]
    assert complete["original_input"]["insertion_settings"]["insertion_orientation"] == "reverse"


def test_linear_backbone_and_backbone_change_preserve_the_combined_construct() -> None:
    combined = generate_multi_tu_combined_construct(
        project_id="gate2-linear",
        project_name="Gate 2 linear",
        expression_units=_units_for_case(DATA["cases"][0]),
    )
    linear_record = SeqRecord(Seq("ACGT" * 60), id="GATE2_LINEAR", name="GATE2_LINEAR")
    linear_record.annotations.update({"molecule_type": "DNA", "topology": "linear"})
    buffer = StringIO()
    SeqIO.write(linear_record, buffer, "genbank")
    settings = {
        "mode": "insertion",
        "start_coordinate": 80,
        "end_coordinate": 81,
        "user_confirmation": True,
    }
    linear = generate_multi_tu_complete_plasmid(
        combined,
        backbone={
            "display_name": "GATE2_LINEAR",
            "raw_text": buffer.getvalue(),
            "source_format": "genbank",
            "source_type": "upload",
            "source_name": "gate2_linear.gb",
        },
        insertion_settings=settings,
    )
    circular = generate_multi_tu_complete_plasmid(
        combined,
        backbone={
            "display_name": "MVP9_BACKBONE",
            "raw_text": _make_backbone_genbank(),
            "source_format": "genbank",
            "source_type": "upload",
            "source_name": "mvp9_backbone.gb",
        },
        insertion_settings={**settings, "start_coordinate": 40, "end_coordinate": 41},
    )

    assert linear["complete_plasmid"]["total_length"] == 299
    assert linear["runtime"]["complete_plasmid_constructs"][0]["topology"] == "linear"
    assert linear["combined_construct"] == circular["combined_construct"] == combined["combined_construct"]
    assert linear["complete_plasmid"]["input_signature"] != circular["complete_plasmid"]["input_signature"]


def test_dual_tu_save_reopen_and_exports_use_one_shared_repository(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "formal-dual-tu")
    result = _formal_result(7)
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)

    assert reopened["project_type"] == "dual_tu"
    assert reopened["formal_project_context"] == result["formal_project_context"]
    assert reopened["unit_order"] == ["TU2", "TU1"]
    assert reopened["runtime"] == result["runtime"]
    assert reopened["complete_plasmid"]["sequence_sha256"] == result["complete_plasmid"]["sequence_sha256"]
    fasta = next(SeqIO.parse(StringIO(reopened["exports"]["complete_plasmid_fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(reopened["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == reopened["complete_plasmid"]["dna"]
    assert [item.project_id for item in list_mvp_multi_tu_designs(repository=repository)] == [saved.project_id]


def test_dual_tu_reopens_in_a_fresh_python_process(monkeypatch, tmp_path: Path) -> None:
    storage = tmp_path / "cross-process"
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(storage))
    saved = save_mvp_multi_tu_design(_formal_result(5))
    command = (
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "import json; print(json.dumps({'type':r['project_type'],'order':r['unit_order'],"
        "'sha':r['complete_plasmid']['sequence_sha256'],'length':r['complete_plasmid']['total_length']}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(storage)},
        check=True,
        capture_output=True,
        text=True,
    )
    reopened = json.loads(completed.stdout.strip())

    assert reopened == {
        "type": "dual_tu",
        "order": ["TU2", "TU1"],
        "sha": _formal_result(5)["complete_plasmid"]["sequence_sha256"],
        "length": 179,
    }


def test_dual_tu_unit_change_invalidates_outputs_without_erasing_peer_input() -> None:
    class _Streamlit:
        session_state = {
            "formal_dual_tu_units": {
                "TU1": {"cds": {"raw_text": "ATGGCTTAA"}},
                "TU2": {"cds": {"raw_text": "ATGAAATAA"}},
            },
            "formal_dual_tu_unit_snapshots": {"TU1": {"dna": "A"}, "TU2": {"dna": "T"}},
            "formal_dual_tu_combined_result": {"dna": "AT"},
            "mvp_vector_result": {"dna": "complete"},
        }

    functions = _app_functions(
        "_invalidate_dual_tu_outputs",
        "_invalidate_dual_tu_unit",
        namespace={"Any": Any, "st": _Streamlit()},
    )
    functions["_invalidate_dual_tu_unit"]("TU1")

    state = functions["_invalidate_dual_tu_unit"].__globals__["st"].session_state
    assert state["formal_dual_tu_units"]["TU2"]["cds"]["raw_text"] == "ATGAAATAA"
    assert "TU1" not in state["formal_dual_tu_unit_snapshots"]
    assert state["formal_dual_tu_unit_snapshots"]["TU2"] == {"dna": "T"}
    assert "formal_dual_tu_combined_result" not in state
    assert "mvp_vector_result" not in state
    assert state["mvp_inputs_stale"] is True


def test_navigation_only_does_not_call_any_dual_tu_invalidation_helper() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_set_formal_step"
    )
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_invalidate_dual_tu_outputs" not in called
    assert "_invalidate_dual_tu_unit" not in called
    assert "_invalidate_complete_plasmid_snapshot" not in called


def test_formal_dual_tu_management_is_step2_only_and_step3_is_read_only() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step2 = source.split("def _render_dual_tu_step_2", 1)[1].split(
        "def _render_step_2_cds", 1
    )[0]
    step3 = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _optional_input", 1
    )[0]

    assert "formal_multi_tu_add" in step2
    assert "formal_{unit_id}_delete_confirm" in step2
    assert "_move_transcription_unit" in step2
    assert "v1.expression.save_tu_plan_continue" in step2

    assert "`{unit_id}`" not in step3
    assert "unit_id" not in step3.split("st.caption", 1)[0]
    assert "formal_multi_tu_add" not in step3
    assert "formal_{unit_id}_delete_confirm" not in step3
    assert "_move_transcription_unit" not in step3
