from __future__ import annotations

import ast
from collections.abc import Mapping
import hashlib
import json
import re
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

import mvp_app
from core.design_session import DesignSession
from core.i18n import translate
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.formal_cds_workflow import analyze_formal_cds, gene_information_from_values
from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
from services.mvp_cds_input import analyze_cds_input
from services.mvp_single_gene_persistence import (
    MVP_SINGLE_GENE_PERSISTENCE_KEY,
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.cas_offinder_adapter import (
    CasOffinderExecutableIdentity,
    CasOffinderRunResult,
    OffTargetComputationStatus,
    build_cas_offinder_input,
    parse_cas_offinder_v241_output,
)
from services.crispr_product_workflow import (
    CRISPR_PRODUCT_STATE_KEY,
    CrisprProductWorkflowError,
    build_product_workflow_input,
    candidate_projection,
    compute_product_workflow,
    enumerate_product_off_targets,
    installed_reference_from_fasta,
    invalidate_stale_product_result,
    open_crispr_product_workflow,
    save_crispr_product_workflow,
    select_product_candidate,
)
from services.crispr_workflow_contract import WorkflowState, to_json
from services.mvp_sequence_input import (
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.helpers.fake_streamlit import FakeStreamlit, FakeStreamlitContext


ROOT = Path(__file__).resolve().parents[1]
CRISPR_SEQUENCE = "AAA" + "ACGT" * 5 + "TGG" + "AAA"
CRISPR_EXECUTABLE = CasOffinderExecutableIdentity(
    resolved_path="C:/fixture/cas-offinder.exe",
    sha256="1" * 64,
    observed_banner="Cas-OFFinder v2.4.1 (fixture)",
)


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _crispr_input(
    tmp_path: Path,
    *,
    sequence: str = CRISPR_SEQUENCE,
    reference_version: str = "TAIR10.1",
    maximum_mismatches: int = 4,
):
    fasta_path = tmp_path / reference_version / "assembly.fa"
    fasta_path.parent.mkdir(parents=True, exist_ok=True)
    fasta_path.write_text(f">chr1\n{CRISPR_SEQUENCE}\n", encoding="utf-8")
    reference = installed_reference_from_fasta(
        fasta_path,
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version=reference_version,
        installation_provenance="product integration fixture",
    )
    return build_product_workflow_input(
        target_sequence=sequence,
        target_id="target-1",
        target_display_name="Target 1",
        reference_pack_id="tair10-reference-pack-v1",
        contig="chr1",
        reference=reference,
        reference_offset=100,
        maximum_mismatches=maximum_mismatches,
        off_target_requested=True,
        executable_path=CRISPR_EXECUTABLE.resolved_path,
        expected_executable_sha256=CRISPR_EXECUTABLE.sha256,
    )


def _computed_crispr_result(tmp_path: Path):
    workflow_input = _crispr_input(tmp_path)
    computed = compute_product_workflow(workflow_input)
    selected = select_product_candidate(
        computed,
        computed.scan.candidates[0].candidate_id,
        current_input=workflow_input,
    )

    def runner(request):
        input_text, input_sha256 = build_cas_offinder_input(request)
        output_text = f"{request.query}\tchr1\t3\t{request.spacer}TGG\t+\t0\n"
        hits = parse_cas_offinder_v241_output(
            output_text,
            request,
            executable_sha256=CRISPR_EXECUTABLE.sha256,
            input_sha256=input_sha256,
        )
        return CasOffinderRunResult(
            request=request,
            status=OffTargetComputationStatus.COMPUTED,
            hits=hits,
            input_text=input_text,
            input_sha256=input_sha256,
            output_text=output_text,
            output_sha256=hashlib.sha256(output_text.encode()).hexdigest(),
            executable=CRISPR_EXECUTABLE,
            invocation=(CRISPR_EXECUTABLE.resolved_path, "input", "C", "output"),
            exit_code=0,
            stdout="",
            stderr="",
            error_code=None,
            error_message=None,
            temporary_paths_cleaned=True,
        )

    return enumerate_product_off_targets(selected, runner=runner)


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    namespace.setdefault("_t", _zh_t)
    namespace.setdefault("_get_language", lambda: "zh-CN")
    namespace.setdefault("_display_optional_label", lambda value: value)
    namespace.setdefault("_localized_rows", lambda rows: rows)
    namespace.setdefault("_ui", lambda value: value)
    namespace.setdefault("_THREE_PRIME_ROLE_LABELS", {
        "terminator": "v1.expression.transcription_terminator",
        "three_prime_utr": "v1.expression.three_prime_utr",
        "three_prime_regulatory_region": "v1.expression.three_prime_regulatory_region",
        "three_prime_processing_termination_region": "v1.expression.three_prime_processing_termination_region",
    })
    namespace.setdefault("_SOURCE_MODE_VALUES", ("元件库", "用户序列"))
    namespace.setdefault("_SINGLE_GENE_SOURCE_MODE_VALUES", ("registry", "user_sequence"))
    namespace.setdefault("_SINGLE_GENE_SOURCE_MODE_LABELS", {"registry": "v1.common.component_library", "user_sequence": "v1.expression.user_sequence"})
    namespace.setdefault("_SOURCE_MODE_LABELS", {"元件库": "v1.common.component_library", "用户序列": "v1.expression.user_sequence"})
    namespace.setdefault("_FORMAL_STEP3_CUSTOM_INPUT_LABELS", {"paste": "v1.expression.paste_dna_fasta", "upload": "v1.expression.upload_fasta"})
    namespace.setdefault("_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL", "v1.expression.custom_sequence_source_review_required")
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    if "_render_step_3_elements" in names:
        names = (*names, "_single_gene_step3_source_mode", "_single_gene_step3_input_method", "_prepare_single_gene_step3_widget_state", "_remember_single_gene_step3_widget_state", "_normalize_three_prime_role", "_single_gene_step3_role_display_label")
        namespace.setdefault("_THREE_PRIME_ROLE_LEGACY_VALUES", {"three_prime_utr": "three_prime_utr"})
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


class _FormalStreamlit(FakeStreamlit):
    def columns(self, spec: int | list[Any] | tuple[Any, ...], **_kwargs: Any) -> list[FakeStreamlitContext]:
        count = spec if isinstance(spec, int) else len(spec)

        class _Column(FakeStreamlitContext):
            def number_input(self, label: str, value: Any = 1, **kwargs: Any) -> Any:
                assert self.fake_st is not None
                return self.fake_st.number_input(label, value=value, **kwargs)

        return [_Column(self) for _ in range(count)]

    def segmented_control(
        self, _label: str, options: Any, *, default: Any = None, key: str | None = None, **_kwargs: Any
    ) -> Any:
        option_list = list(options)
        if key in self.session_state and self.session_state[key] in option_list:
            return self.session_state[key]
        value = default if default in option_list else option_list[0]
        if key is not None:
            self.session_state[key] = value
        return value

    def selectbox(
        self, label: str, options: Any, index: int = 0, key: str | None = None, **kwargs: Any
    ) -> Any:
        option_list = list(options)
        if key in self.session_state and self.session_state[key] in option_list:
            self.selectbox_calls.append(
                {"label": label, "options": option_list, "index": index, "key": key, **kwargs}
            )
            return self.session_state[key]
        return super().selectbox(label, option_list, index=index, key=key, **kwargs)

    def checkbox(
        self, label: str, value: bool = False, key: str | None = None, **kwargs: Any
    ) -> bool:
        if key in self.session_state:
            value = bool(self.session_state[key])
        return super().checkbox(label, value=value, key=key, **kwargs)


class _Controller:
    def __init__(self) -> None:
        self.saved: DesignSession | None = None

    def save(self, ds: DesignSession) -> None:
        self.saved = ds

    def get(self) -> DesignSession:
        assert self.saved is not None
        return self.saved


def _backbone_genbank() -> str:
    record = SeqRecord(Seq("ACGT" * 450), id="TEST_BACKBONE", name="TEST_BACKBONE")
    record.annotations.update(molecule_type="DNA", topology="circular")
    feature_types = ["rep_origin", "promoter", "CDS", "terminator", "misc_feature"]
    record.features = [
        SeqFeature(
            SimpleLocation(index * 250, index * 250 + 100),
            type=feature_type,
            qualifiers={"label": [f"TEST_BACKBONE_FEATURE_{index + 1}"]},
        )
        for index, feature_type in enumerate(feature_types)
    ]
    handle = StringIO()
    SeqIO.write(record, handle, "genbank")
    return handle.getvalue()


@pytest.fixture(scope="module")
def saved_result() -> dict[str, Any]:
    project_id = "formal-single-gene-reopen"
    promoter_sequence = ("ACGT" * 37) + "AC"
    cds_sequence = "ATG" + ("GCT" * 98) + "TAA"
    terminator_sequence = ("GATTACA" * 17) + "GATT"
    cds_input = analyze_cds_input(
        cds_sequence,
        source_kind="paste",
        source_name="TEST_CDS_SOURCE",
    )
    records = {
        "promoter": analyze_dna_component_input(
            promoter_sequence,
            project_id=project_id,
            component_type="promoter",
            display_name="TEST_PROMOTER",
            source_kind="library",
            source_name="TEST_PROMOTER_SOURCE",
        ),
        "cds": mvp_app._cds_record(cds_input, display_name="TEST_CDS"),
        "terminator": analyze_dna_component_input(
            terminator_sequence,
            project_id=project_id,
            component_type="terminator",
            display_name="TEST_TERMINATOR",
            source_kind="library",
            source_name="TEST_TERMINATOR_SOURCE",
        ),
        "backbone": analyze_genbank_backbone_input(
            _backbone_genbank(),
            project_id=project_id,
            display_name="TEST_BACKBONE_1800",
            source_kind="upload",
            source_name="test_backbone_1800.gb",
        ),
    }
    settings = {
        "mode": "insertion",
        "start_coordinate": 900,
        "end_coordinate": 901,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
        "construction_strategy_confirmed": True,
        "t_dna_confirmation": {
            "status": "confirmed",
            "confirmation_source": "manual_review",
        },
        "t_dna_operation_validation": {
            "status": "confirmed",
            "allowed": True,
        },
    }
    result = mvp_app.generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name="TEST_SINGLE_GENE_PROJECT",
    )
    assessment = assess_expression_cassette(
        [
            {
                "biological_role": "promoter",
                "display_name": records["promoter"]["display_name"],
                "sequence": records["promoter"]["normalized_sequence"],
                "source_kind": "library",
                "source_reference": records["promoter"]["source_name"],
                "user_edited": False,
            },
            {
                "biological_role": "cds",
                "display_name": records["cds"]["display_name"],
                "sequence": records["cds"]["normalized_sequence"],
                "source_kind": "paste",
                "source_reference": records["cds"]["source_name"],
                "user_edited": False,
            },
            {
                "biological_role": "three_prime_regulatory_region",
                "display_name": records["terminator"]["display_name"],
                "sequence": records["terminator"]["normalized_sequence"],
                "source_kind": "library",
                "source_reference": records["terminator"]["source_name"],
                "user_edited": False,
            },
        ],
        cds_sequence=records["cds"]["normalized_sequence"],
        cds_signature=cds_input["normalized_cds_sha256"],
        order_confirmed=True,
    )
    assert assessment["blocking"] is False
    formal_cassette = generate_expression_cassette(assessment, project_id=project_id)
    result["formal_expression_cassette"] = {
        key: value for key, value in formal_cassette.items() if key not in {"runtime", "cassette"}
    }
    result["formal_project_context"] = {
        "host_key": "Rice (O. sativa)",
        "expression_target": "TEST_TARGET",
        "current_step": 6,
    }
    return result


def _restore(saved_result: dict[str, Any]) -> tuple[_FormalStreamlit, _Controller, dict[str, Any]]:
    streamlit = _FormalStreamlit()
    controller = _Controller()
    pages: list[str] = []
    restore = _app_functions(
        "_project_definition_expression_target",
        "_formal_step3_custom_input_label",
        "_is_formal_action_widget_key",
        "_restore_completed_formal_state",
        "_restored_formal_project_context",
        "_restore_mvp_result",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "st": streamlit,
            "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
                "paste": "粘贴 DNA/FASTA",
                "upload": "上传 FASTA",
            },
            "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PAGE_RESULTS_EXPORT": "results",
            "_controller": lambda: controller,
            "_change_page": pages.append,
        },
    )["_restore_mvp_result"]
    restore(deepcopy(saved_result), "Rice (O. sativa)")
    assert pages == ["results"]
    assert controller.saved is not None
    return streamlit, controller, streamlit.session_state


def test_completed_save_keeps_formal_state_with_the_canonical_result(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    streamlit = _FormalStreamlit()
    formal_definition = {
        "project_name": saved_result["project_name"],
        "plant_host": "Rice (O. sativa)",
    }
    streamlit.session_state.update(
        {
            "formal_project_definition": formal_definition,
            "formal_cds_input": deepcopy(saved_result["cds_input"]),
            "formal_expression_cassette": deepcopy(saved_result["formal_expression_cassette"]),
            "formal_cassette_result": {
                "runtime": deepcopy(saved_result["runtime"]),
                "cassette_input_signature": saved_result["formal_expression_cassette"]["input_signature"],
                "input_signature": saved_result["formal_expression_cassette"]["input_signature"],
            },
            "formal_cassette_input_signature": saved_result["formal_expression_cassette"]["input_signature"],
            "formal_backbone_record": deepcopy(saved_result["input_records"]["backbone"]),
            "formal_insertion_settings": deepcopy(saved_result["insertion_settings"]),
            "formal_step3_order_confirmation_recorded": True,
            "formal_construct_review_status": "current",
            "formal_cds_source_review_status": "current",
            "mvp_vector_result": deepcopy(saved_result),
            "mvp_current_input_signature": saved_result["input_signature"],
            "mvp_inputs_stale": False,
            "formal_ai_route_candidate_set": {"input_signature": "session-only"},
            "formal_ai_route_human_confirmed": True,
        }
    )
    functions = _app_functions(
        "_formal_ui_signature",
        "_clear_formal_step5_strategy_confirmation",
        "_clear_formal_step4_strategy_confirmation",
        "_formal_step4_strategy_signature",
        "_formal_step4_strategy_ready",
        "_record_formal_step4_strategy_confirmation",
        "_formal_step5_strategy_signature",
        "_formal_canonical_result_is_current",
        "_record_formal_step5_strategy_confirmation",
        "_refresh_formal_strategy_confirmation_state",
        "_is_formal_action_widget_key",
        "_formal_state_snapshot",
        "_bind_completed_formal_state",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "st": streamlit,
            "json": json,
            "re": re,
            "hashlib": hashlib,
            "_formal_project_definition": lambda: formal_definition,
        },
    )

    with pytest.raises(MvpSingleGenePersistenceError, match="missing_formal_state"):
        save_mvp_single_gene_design(
            functions["_bind_completed_formal_state"](deepcopy(saved_result)),
            repository=PlantProjectDraftRepository(tmp_path / "missing-confirmations"),
        )
    assert "formal_step4_strategy_confirmed" not in streamlit.session_state
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state

    step4_signature = functions["_formal_step4_strategy_signature"]()
    functions["_record_formal_step4_strategy_confirmation"](step4_signature)
    assert streamlit.session_state["formal_step4_strategy_confirmed"] is True
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state
    functions["_record_formal_step5_strategy_confirmation"](
        streamlit.session_state["mvp_vector_result"]
    )
    assert streamlit.session_state["formal_step5_strategy_confirmed"] is True

    saved = save_mvp_single_gene_design(
        functions["_bind_completed_formal_state"](deepcopy(saved_result)),
        repository=PlantProjectDraftRepository(tmp_path / "projects"),
    )
    reopened = open_mvp_single_gene_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(tmp_path / "projects"),
    )

    formal_state = reopened["formal_project_context"]["formal_state"]
    assert formal_state["formal_step3_order_confirmation_recorded"] is True
    assert formal_state["formal_step4_strategy_confirmed"] is True
    assert formal_state["formal_step5_strategy_confirmed"] is True
    assert not any(key.startswith("formal_ai_route_") for key in formal_state)
    assert "mvp_vector_result" not in formal_state
    assert reopened["runtime"] == saved_result["runtime"]
    assert reopened["exports"] == saved_result["exports"]

    canonical = active_complete_plasmid_snapshot(reopened["runtime"])["sequence"]
    fasta = SeqIO.read(StringIO(reopened["exports"]["fasta"]["data"]), "fasta")
    genbank = SeqIO.read(StringIO(reopened["exports"]["genbank"]["data"]), "genbank")
    assert canonical == str(fasta.seq).upper() == str(genbank.seq).upper()

    streamlit.session_state["formal_project_definition"]["project_name"] = "Changed upstream"
    assert functions["_refresh_formal_strategy_confirmation_state"](saved_result) == (False, False)
    assert "formal_step4_strategy_confirmed" not in streamlit.session_state
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state


def test_restore_rehydrates_saved_elements_backbone_and_current_signature(saved_result: dict[str, Any]) -> None:
    streamlit, controller, state = _restore(saved_result)
    ds = controller.get()

    assert ds.elements["promoter_name"] == "TEST_PROMOTER"
    assert ds.elements["promoter_seq"] == saved_result["input_records"]["promoter"]["normalized_sequence"]
    assert ds.gene_name == "TEST_CDS"
    assert ds.elements["terminator_name"] == "TEST_TERMINATOR"
    assert state["formal_element_source_records"]["promoter"] == saved_result["input_records"]["promoter"]
    assert state["formal_element_source_records"]["terminator"] == saved_result["input_records"]["terminator"]
    assert state["formal_step1_project_name"] == "TEST_SINGLE_GENE_PROJECT"
    assert state["formal_step1_host"] == "Rice (O. sativa)"
    assert state["formal_step2_gene_name"] == "TEST_CDS"
    assert state["formal_step2_cds_text"] == saved_result["cds_input"]["original_text"]
    assert state["formal_backbone_record"]["display_name"] == "TEST_BACKBONE_1800"
    assert state["formal_backbone_record"]["length"] == 1800
    assert state["formal_step5_source"] == "使用当前项目骨架"
    assert state["formal_step5_start"] == 900
    assert state["formal_step5_end"] == 901
    assert state["mvp_inputs_stale"] is False
    assert state["mvp_current_input_signature"] == saved_result["input_signature"]

    wizard_records = _app_functions(
        "_wizard_component_records",
        namespace={"Any": Any, "st": streamlit},
    )["_wizard_component_records"]
    restored_cds, restored_records = wizard_records(ds, saved_result["project_id"])
    assert restored_cds == saved_result["cds_input"]
    assert restored_records == {
        role: saved_result["input_records"][role]
        for role in ("promoter", "cds", "terminator")
    }
    assert mvp_app.cassette_input_signature(restored_records) == saved_result["cassette_input_signature"]


def test_reopened_canonical_fasta_and_genbank_remain_2373_bp_with_eight_features(
    saved_result: dict[str, Any],
) -> None:
    streamlit, _controller, state = _restore(saved_result)
    restored = state["mvp_vector_result"]
    cassette = active_construct_snapshot(restored["runtime"])
    plasmid = active_complete_plasmid_snapshot(restored["runtime"])
    fasta = SeqIO.read(StringIO(restored["exports"]["fasta"]["data"]), "fasta")
    genbank = SeqIO.read(StringIO(restored["exports"]["genbank"]["data"]), "genbank")

    assert cassette["sequence_length"] == 573
    assert plasmid["sequence_length"] == len(fasta.seq) == len(genbank.seq) == 2373
    assert str(plasmid["sequence"]) == str(fasta.seq).upper() == str(genbank.seq).upper()
    assert len(plasmid["feature_rows"]) == len(genbank.features) == 8
    assert restored["runtime"] == saved_result["runtime"]


def test_cold_reopen_step6_renders_the_persisted_export_payload_without_regeneration(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_single_gene_design(deepcopy(saved_result), repository=repository)
    reopened = open_mvp_single_gene_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    streamlit, controller, state = _restore(reopened)
    rendered: list[dict[str, Any]] = []
    navigation_calls: list[dict[str, Any]] = []
    render_step6 = _app_functions(
        "_render_step_6_review",
        namespace={
            "Any": Any,
            "st": streamlit,
            "_is_generic_multi_tu_workflow": lambda: False,
            "_active_backbone_workflow_id": lambda: "rice_alb_single_gene",
            "_render_results_export_content": lambda **kwargs: rendered.append(
                {"result": state["mvp_vector_result"], **kwargs}
            ),
            "_render_step_navigation": lambda **kwargs: navigation_calls.append(kwargs),
        },
    )["_render_step_6_review"]

    render_step6(controller.get())

    assert controller.get().step == 6
    assert all(
        state.get(key)
        for key in (
            "formal_project_definition",
            "formal_cds_input",
            "formal_expression_cassette",
            "formal_cassette_result",
            "formal_backbone_record",
            "formal_insertion_settings",
        )
    )
    assert state["formal_step3_order_confirmation_recorded"] is True
    state["formal_last_saved_mvp_project_id"] = saved.project_id
    status_function = _app_functions(
        "_formal_step_statuses",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "st": streamlit,
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PROJECT_TYPE_DUAL_TU": "multi_tu",
            "_host_supports_project_type": lambda host, _project_type: bool(host),
            "_formal_project_type": lambda: "single_gene",
            "_is_pathway_multi_tu_project": lambda: False,
            "_is_generic_multi_tu_workflow": lambda: False,
            "_is_multi_tu_expression_assembly": lambda _result: False,
            "_formal_ui_signature": lambda value: repr(value),
        },
    )["_formal_step_statuses"]
    statuses = status_function()
    assert statuses == [{"done": True, "review": False}] * 6
    assert len(rendered) == 1
    assert rendered[0]["include_project_actions"] is False
    assert rendered[0]["result"]["exports"] == reopened["exports"]
    assert rendered[0]["result"]["exports"]["fasta"]["data"] == reopened["exports"]["fasta"]["data"]
    assert rendered[0]["result"]["exports"]["genbank"]["data"] == reopened["exports"]["genbank"]["data"]
    assert navigation_calls == [{"current_step": 6, "next_enabled": False}]


def test_completed_project_resave_keeps_the_canonical_result_and_exports(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    first_save = save_mvp_single_gene_design(deepcopy(saved_result), repository=repository)
    reopened = open_mvp_single_gene_design(
        first_save.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )

    second_save = save_mvp_single_gene_design(reopened, repository=repository)
    cold_reopened = open_mvp_single_gene_design(
        second_save.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    _streamlit, controller, state = _restore(cold_reopened)

    assert second_save.project_id == first_save.project_id
    assert controller.get().step == 6
    assert state["mvp_vector_result"]["runtime"] == reopened["runtime"]
    assert state["mvp_vector_result"]["exports"] == reopened["exports"]


def test_formal_save_crispr_save_resave_and_cold_reopen_preserve_exact_state(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    first_save = save_mvp_single_gene_design(deepcopy(saved_result), repository=repository)
    before_crispr = open_mvp_single_gene_design(
        first_save.project_id,
        repository=repository,
    )
    before_runtime = deepcopy(before_crispr["runtime"])
    before_exports = deepcopy(before_crispr["exports"])
    before_expression_state = deepcopy(
        repository.load(first_save.project_id).manual_review_state[
            MVP_SINGLE_GENE_PERSISTENCE_KEY
        ]
    )
    completed = _computed_crispr_result(tmp_path)

    save_crispr_product_workflow(
        first_save.project_id,
        completed,
        repository=repository,
    )
    with_extension = repository.load(first_save.project_id)
    with_extension.manual_review_state["fixture_extension_v1"] = {
        "owner": "independent-extension",
        "value": 7,
    }
    repository.save(with_extension)
    assert CRISPR_PRODUCT_STATE_KEY in repository.load(
        first_save.project_id
    ).manual_review_state
    after_crispr = open_mvp_single_gene_design(
        first_save.project_id,
        repository=repository,
    )
    assert after_crispr["runtime"] == before_runtime
    assert after_crispr["exports"] == before_exports
    assert (
        repository.load(first_save.project_id).manual_review_state[
            MVP_SINGLE_GENE_PERSISTENCE_KEY
        ]
        == before_expression_state
    )

    reopened_formal = open_mvp_single_gene_design(
        first_save.project_id,
        repository=repository,
    )
    second_save = save_mvp_single_gene_design(reopened_formal, repository=repository)
    assert second_save.project_id == first_save.project_id

    del with_extension, reopened_formal, repository
    cold_repository = PlantProjectDraftRepository(tmp_path / "projects")
    cold_draft = cold_repository.load(first_save.project_id)
    cold_reopened = open_crispr_product_workflow(
        first_save.project_id,
        trusted_executable=CRISPR_EXECUTABLE,
        repository=cold_repository,
    )

    assert set(cold_draft.manual_review_state) >= {
        MVP_SINGLE_GENE_PERSISTENCE_KEY,
        CRISPR_PRODUCT_STATE_KEY,
        "fixture_extension_v1",
    }
    assert cold_draft.manual_review_state["fixture_extension_v1"] == {
        "owner": "independent-extension",
        "value": 7,
    }
    assert to_json(cold_reopened) == to_json(completed)
    assert cold_reopened.workflow_input.target == completed.workflow_input.target
    assert cold_reopened.workflow_input.reference_hash == completed.workflow_input.reference_hash
    assert cold_reopened.workflow_input.configuration == completed.workflow_input.configuration
    assert [row["candidate_id"] for row in candidate_projection(cold_reopened)] == [
        row["candidate_id"] for row in candidate_projection(completed)
    ]
    assert cold_reopened.selection == completed.selection
    assert cold_reopened.off_target_state is WorkflowState.COMPUTED
    assert cold_reopened.off_target == completed.off_target

    for changed_input in (
        _crispr_input(tmp_path, sequence="T" + CRISPR_SEQUENCE[1:]),
        _crispr_input(tmp_path, reference_version="TAIR10.2"),
        _crispr_input(tmp_path, maximum_mismatches=2),
    ):
        invalidated = invalidate_stale_product_result(cold_reopened, changed_input)
        assert invalidated.selection is None
        assert invalidated.off_target is None
        assert invalidated.off_target_state is WorkflowState.NOT_RUN


def test_crispr_entry_action_is_not_persisted_into_reopened_widget_state() -> None:
    streamlit = _FormalStreamlit()
    streamlit.session_state.update(
        {
            "formal_open_crispr_product_workflow": True,
            "formal_project_name": "R2 project",
        }
    )
    functions = _app_functions(
        "_is_formal_action_widget_key",
        "_formal_state_snapshot",
        namespace={"Any": Any, "st": streamlit, "json": json, "re": re},
    )

    assert functions["_is_formal_action_widget_key"](
        "formal_open_crispr_product_workflow"
    ) is True
    assert functions["_formal_state_snapshot"]() == {
        "formal_project_name": "R2 project"
    }


@pytest.mark.parametrize(
    "existing_state",
    [
        None,
        {},
        {"review_state": "review-required"},
        {"legacy_extension_v1": {"preserve": True}},
    ],
)
def test_single_gene_save_preserves_contractual_extension_state_and_legacy_inputs(
    saved_result: dict[str, Any], tmp_path: Path, existing_state: dict[str, Any] | None
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    first_save = save_mvp_single_gene_design(deepcopy(saved_result), repository=repository)
    path = repository.storage_dir / f"{first_save.project_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if existing_state is None:
        payload.pop("manual_review_state")
    else:
        payload["manual_review_state"] = existing_state
    path.write_text(json.dumps(payload), encoding="utf-8")

    resave_result = deepcopy(saved_result)
    resave_result["project_id"] = first_save.project_id
    resave_result["project_name"] = first_save.project_name
    save_mvp_single_gene_design(resave_result, repository=repository)
    persisted = repository.load(first_save.project_id).manual_review_state

    assert MVP_SINGLE_GENE_PERSISTENCE_KEY in persisted
    for key, value in (existing_state or {}).items():
        assert persisted[key] == value
    assert CRISPR_PRODUCT_STATE_KEY not in persisted


def test_malformed_crispr_state_survives_resave_but_open_fails_closed(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    first_save = save_mvp_single_gene_design(deepcopy(saved_result), repository=repository)
    draft = repository.load(first_save.project_id)
    draft.manual_review_state[CRISPR_PRODUCT_STATE_KEY] = {"malformed": True}
    repository.save(draft)

    reopened = open_mvp_single_gene_design(first_save.project_id, repository=repository)
    save_mvp_single_gene_design(reopened, repository=repository)
    persisted = repository.load(first_save.project_id).manual_review_state

    assert persisted[CRISPR_PRODUCT_STATE_KEY] == {"malformed": True}
    with pytest.raises(CrisprProductWorkflowError, match="incompatible"):
        open_crispr_product_workflow(first_save.project_id, repository=repository)


def test_step3_restore_preserves_saved_backbone_without_legacy_coordinate_editor(saved_result: dict[str, Any]) -> None:
    streamlit, controller, state = _restore(saved_result)
    ds = controller.get()
    saved_options = {
        role: [
            {
                "name": f"DEFAULT_{role.upper()}",
                "sequence": "A",
                "source": "default",
                "component_type": role,
            },
            {
                "name": record["display_name"],
                "sequence": record["normalized_sequence"],
                "source": record["source_name"],
                "component_type": record.get("component_type") or role,
            },
        ]
        for role, record in state["formal_element_source_records"].items()
    }
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "st": streamlit,
        "_is_dual_tu_project": lambda: False,
        "_plant_element_options": lambda _host, part_type: saved_options[
            "promoter" if part_type == "Promoter" else "terminator"
        ],
        "_invalidate_formal_snapshots": lambda: None,
        "_clear_complete_plasmid_state": lambda: None,
        "_controller": lambda: controller,
        "_render_step_navigation": lambda **_kwargs: None,
    }
    render_step3 = _app_functions(
        "_formal_three_prime_registry_role",
        "_formal_step3_custom_input_label",
        "_formal_cds_signature",
        "_render_step_3_elements",
        namespace={
            **namespace,
            "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
                "paste": "粘贴 DNA/FASTA",
                "upload": "上传 FASTA",
            },
            "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
        },
    )["_render_step_3_elements"]
    render_step3(ds)

    assert state["formal_step3_promoter"]["name"] == "TEST_PROMOTER"
    assert state["formal_step3_terminator"]["name"] == "TEST_TERMINATOR"
    assert "_formal_restore_step3_pending" not in state

    assert state["formal_backbone_record"]["length"] == 1800
    assert state["formal_backbone_record"]["asset_kind"] == "unverified_uploaded_vector"
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _render_step_5_backbone" not in app_source
    assert "操作起始坐标（1-based）" not in app_source


def test_step3_real_reopen_reuses_persisted_upload_sequence_without_file_object(
    saved_result: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = deepcopy(saved_result)
    persisted_sequence = str(candidate["input_records"]["terminator"]["normalized_sequence"])
    candidate["input_records"]["terminator"].update(
        {
            "source_kind": "user_recorded",
            "source_input_method": "upload",
            "source_name": "saved-three-prime.fasta",
        }
    )
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_single_gene_design(candidate, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)
    streamlit, controller, state = _restore(reopened)
    promoter_record = state["formal_element_source_records"]["promoter"]
    assessments: list[dict[str, Any]] = []
    analyzed_inputs: list[str] = []

    import services.formal_expression_cassette as cassette_module
    import services.mvp_sequence_input as input_module

    original_assess = cassette_module.assess_expression_cassette
    original_analyze = input_module.analyze_dna_component_input

    def capture_assessment(components: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        assessment = original_assess(components, **kwargs)
        assessments.append(deepcopy(assessment))
        return assessment

    def capture_analyze(raw_text: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("component_type") == "terminator":
            analyzed_inputs.append(str(raw_text or ""))
        return original_analyze(raw_text, **kwargs)

    monkeypatch.setattr(cassette_module, "assess_expression_cassette", capture_assessment)
    monkeypatch.setattr(input_module, "analyze_dna_component_input", capture_analyze)
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "st": streamlit,
        "_is_dual_tu_project": lambda: False,
        "_plant_element_options": lambda _host, part_type: (
            [
                {
                    "name": promoter_record["display_name"],
                    "sequence": promoter_record["normalized_sequence"],
                    "source": promoter_record["source_name"],
                }
            ]
            if part_type == "Promoter"
            else []
        ),
        "_invalidate_formal_snapshots": lambda: None,
        "_clear_complete_plasmid_state": lambda: None,
        "_controller": lambda: controller,
        "_render_step_navigation": lambda **_kwargs: None,
        "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
            "paste": "粘贴 DNA/FASTA",
            "upload": "上传 FASTA",
        },
        "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
    }
    render = _app_functions(
        "_formal_three_prime_registry_role",
        "_formal_step3_custom_input_label",
        "_formal_cds_signature",
        "_render_step_3_elements",
        namespace=namespace,
    )["_render_step_3_elements"]

    render(controller.get())
    render(controller.get())

    assert streamlit.file_uploader_value is None
    assert state["formal_step3_terminator_custom_input"] == "upload"
    assert analyzed_inputs == [persisted_sequence, persisted_sequence]
    assert len(assessments) == 2
    for assessment in assessments:
        three_prime = next(
            component
            for component in assessment["components"]
            if component["biological_role"] == "three_prime_regulatory_region"
        )
        assert three_prime["sequence"] == persisted_sequence
        assert three_prime["length"] == len(persisted_sequence)
        assert not any(
            finding["rule_id"] == "empty_component_sequence"
            and "TEST_TERMINATOR" in finding["message"]
            for finding in assessment["findings"]
        )
    assert state["formal_element_source_records"]["terminator"]["source_input_method"] == "upload"


def test_step3_hydration_keeps_current_edit_across_widget_cleanup_and_locale_cycle() -> None:
    streamlit = _FormalStreamlit()
    state = streamlit.session_state
    state["mvp_project_id"] = "r6-step3-editor"
    state["formal_element_source_records"] = {
        "promoter": {"source_kind": "user_recorded", "display_name": "Project", "normalized_sequence": "ACGTACGT"},
        "terminator": {"source_kind": "user_recorded", "display_name": "Status", "normalized_sequence": "TTTTAAAA", "source_input_method": "paste", "biological_role": "three_prime_utr"},
    }
    namespace = {"Any": Any, "Mapping": Mapping, "st": streamlit, "_THREE_PRIME_ROLE_LEGACY_VALUES": {"three_prime_utr": "three_prime_utr"}}
    functions = _app_functions(
        "_formal_step3_custom_input_label", "_normalize_three_prime_role",
        "_single_gene_step3_source_mode", "_single_gene_step3_input_method",
        "_prepare_single_gene_step3_widget_state", "_remember_single_gene_step3_widget_state",
        namespace=namespace,
    )
    prepare = functions["_prepare_single_gene_step3_widget_state"]
    remember = functions["_remember_single_gene_step3_widget_state"]
    namespace["_get_language"] = lambda: "zh-CN"
    prepare()
    assert state["formal_step3_promoter_mode"] == "user_sequence"
    assert state["formal_step3_terminator_mode"] == "user_sequence"
    assert state["formal_step3_three_prime_role"] == "three_prime_utr"
    state["formal_step3_promoter_custom_name"] = "forward"
    remember()
    for role in ("promoter", "terminator"):
        for suffix in ("mode", "custom_name", "custom_text", "custom_input"):
            state.pop(f"formal_step3_{role}_{suffix}", None)
    state.pop("formal_step3_three_prime_role", None)
    namespace["_get_language"] = lambda: "en"
    prepare()
    assert state["formal_step3_promoter_custom_name"] == "forward"
    assert state["formal_step3_terminator_custom_name"] == "Status"
    assert state["formal_step3_promoter_custom_text"] == "ACGTACGT"
    assert state["formal_step3_terminator_custom_text"] == "TTTTAAAA"
    assert state["formal_step3_three_prime_role"] == "three_prime_utr"
    state["formal_step3_promoter_custom_name"] = "Project"
    remember()
    prepare()
    assert state["formal_step3_promoter_custom_name"] == "Project"
    namespace["_get_language"] = lambda: "zh-CN"
    prepare()
    assert state["formal_step3_promoter_custom_name"] == "Project"


def test_step6_has_mutually_exclusive_current_and_stale_states(saved_result: dict[str, Any]) -> None:
    streamlit, controller, state = _restore(saved_result)
    navigation_calls: list[dict[str, Any]] = []
    result_preview_calls: list[dict[str, Any]] = []
    helpers = _app_functions(
        "_wizard_component_records",
        "_canonical_cassette_length",
        namespace={"Any": Any, "st": streamlit},
    )
    namespace = {
        "Any": Any,
        "escape": __import__("html").escape,
        "st": streamlit,
        "_is_dual_tu_project": lambda: False,
        "_wizard_component_records": helpers["_wizard_component_records"],
        "_canonical_cassette_length": helpers["_canonical_cassette_length"],
        "_topology_label": lambda value: "环状" if value == "circular" else str(value),
        "_formal_element_display_name": lambda name, _role: str(name),
        "_generate_complete_plasmid": lambda _ds: pytest.fail("render must not regenerate"),
        "_change_page": lambda _page: None,
        "_render_step_navigation": lambda **kwargs: navigation_calls.append(kwargs),
        "_render_results_export_content": lambda **kwargs: result_preview_calls.append(kwargs),
    }
    render_step6 = _app_functions("_render_step_6_complete", namespace=namespace)["_render_step_6_complete"]

    render_step6(controller.get())
    assert not streamlit.error_messages
    assert any("完整质粒生成成功" in str(call["body"]) for call in streamlit.markdown_calls)
    assert navigation_calls[-1]["current_step"] == 6

    streamlit.markdown_calls.clear()
    streamlit.error_messages.clear()
    streamlit.button_calls.clear()
    state["mvp_inputs_stale"] = True
    render_step6(controller.get())
    assert not streamlit.error_messages
    assert result_preview_calls[-1] == {
        "include_project_actions": False,
        "result_preview_mode": True,
    }
    assert not any("完整质粒生成成功" in str(call["body"]) for call in streamlit.markdown_calls)
    assert navigation_calls[-1]["current_step"] == 6


def test_upstream_change_invalidates_restored_result(saved_result: dict[str, Any]) -> None:
    streamlit, _controller, state = _restore(saved_result)
    functions = _app_functions(
        "_clear_complete_plasmid_state",
        "_invalidate_formal_snapshots",
        namespace={"Any": Any, "st": streamlit},
    )

    functions["_invalidate_formal_snapshots"]()

    assert "mvp_vector_result" not in state
    assert "mvp_current_input_signature" not in state
    assert "formal_cassette_result" not in state
    assert state["mvp_inputs_stale"] is True


def test_formal_cds_metadata_survives_save_reopen_and_widget_restore(
    saved_result: dict[str, Any], tmp_path: Path
) -> None:
    result = deepcopy(saved_result)
    analysis = analyze_formal_cds(
        str(result["source_inputs"]["cds"]),
        source_kind="upload",
        source_name="test1.fasta",
        gene_information=gene_information_from_values(
            gene_name="TEST1",
            gene_symbol="T1",
            source_species="Oryza sativa",
            source_type="上传的 FASTA 文件",
            source_reference="local archive test1",
            modification_status="用户手动编辑",
            modification_note="documented local edit",
            is_partial_cds=True,
            note="display-only note",
        ),
    )
    result["cds_input"] = analysis
    result["input_records"]["cds"].update(
        source_kind="upload",
        source_name="test1.fasta",
        display_name="TEST1",
    )
    result["formal_project_context"] = {
        "host_key": "Rice (O. sativa)",
        "expression_target": "TEST_TARGET",
        "current_step": 6,
        "cds_source_review_basis": dict(analysis["source_review_basis"]),
        "cds_source_review_status": "current",
    }
    repository = PlantProjectDraftRepository(tmp_path / "projects")

    saved = save_mvp_single_gene_design(result, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=PlantProjectDraftRepository(repository.storage_dir))
    streamlit, _controller, state = _restore(reopened)

    assert reopened["cds_input"]["gene_information"] == analysis["gene_information"]
    assert reopened["cds_input"]["manual_review_items"] == analysis["manual_review_items"]
    assert reopened["formal_project_context"]["cds_source_review_basis"] == analysis["source_review_basis"]
    assert state["formal_step2_gene_symbol"] == "T1"
    assert state["formal_step2_source_species"] == "Oryza sativa"
    assert state["formal_step2_source_type"] == "上传的 FASTA 文件"
    assert state["formal_step2_modification_status"] == "用户手动编辑"
    assert state["formal_step2_partial_cds"] is True
    assert streamlit.session_state["formal_step2_cds_text"] == result["source_inputs"]["cds"]
