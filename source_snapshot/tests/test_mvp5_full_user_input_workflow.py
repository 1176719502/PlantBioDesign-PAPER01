from __future__ import annotations

from copy import deepcopy
import hashlib
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from mvp_app import (
    COMPONENT_NAMES,
    cassette_input_signature,
    construct_input_signature,
    generate_expression_cassette,
    generate_complete_vector,
    generation_input_signature,
    load_real_case,
)
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.mvp_cds_input import analyze_cds_input
from services.mvp_sequence_input import (
    DNA_FILE_SUFFIXES,
    GENBANK_FILE_SUFFIXES,
    MvpSequenceInputError,
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
    decode_uploaded_text,
)
from services.mvp_single_gene_persistence import (
    list_mvp_single_gene_designs,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


def _genbank_text(sequence: str, *, record_id: str = "user_backbone") -> str:
    record = SeqRecord(Seq(sequence), id=record_id, name=record_id, description="User backbone")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"
    record.features = [
        SeqFeature(FeatureLocation(800, 850), type="misc_feature", qualifiers={"label": ["user_feature"]})
    ]
    handle = StringIO()
    SeqIO.write(record, handle, "genbank")
    return handle.getvalue()


def _component(
    role: str,
    sequence: str,
    *,
    project_id: str = "plant-draft-mvp5-test",
    source_kind: str = "paste",
    source_name: str = "pasted-input",
) -> dict:
    return analyze_dna_component_input(
        sequence,
        project_id=project_id,
        component_type=role,
        display_name=COMPONENT_NAMES[role],
        source_kind=source_kind,
        source_name=source_name,
    )


def _user_inputs(*, backbone_text: str | None = None) -> tuple[dict, dict, dict]:
    project_id = "plant-draft-mvp5-user-inputs"
    cds_input = analyze_cds_input(
        "ATG" + ("GCT" * 4) + "TAA",
        source_kind="paste",
        source_name="user-cds",
    )
    records = {
        "promoter": _component("promoter", "AACCGGTTAACC", project_id=project_id),
        "cds": {
            "role": "cds",
            "source_kind": "paste",
            "source_name": "user-cds",
            "source_format": "plain",
            "display_name": COMPONENT_NAMES["cds"],
            "original_text": cds_input["original_text"],
            "normalized_sequence": cds_input["normalized_cds"],
            "length": cds_input["normalized_length"],
        },
        "terminator": _component("terminator", "TTGGAATTCC", project_id=project_id),
    }
    backbone_raw = backbone_text or load_real_case()["backbone"]
    records["backbone"] = analyze_genbank_backbone_input(
        backbone_raw,
        project_id=project_id,
        display_name="USER_BACKBONE",
        source_kind="upload" if backbone_text else "example",
        source_name="user_backbone.gbk" if backbone_text else "r229_backbone.gb",
    )
    settings = {
        "mode": "insertion",
        "start_coordinate": 600 if backbone_text else 2100,
        "end_coordinate": 601 if backbone_text else 2101,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
    }
    return cds_input, records, settings


def test_promoter_and_terminator_plain_and_fasta_inputs_delegate_to_r227_without_cds_rules() -> None:
    promoter = _component("promoter", "a t\ng c")
    terminator = _component("terminator", ">user_terminator\nTTTTT\n", source_kind="upload", source_name="term.fa")

    assert promoter["normalized_sequence"] == "ATGC"
    assert promoter["length"] == 4
    assert terminator["normalized_sequence"] == "TTTTT"
    assert terminator["length"] == 5


def test_component_upload_validation_covers_empty_encoding_suffix_illegal_and_multiple_fasta() -> None:
    assert decode_uploaded_text(b">p\nATGC\n", file_name="p.fasta", allowed_suffixes=DNA_FILE_SUFFIXES)
    for data, name, message in (
        (b"", "empty.fa", "上传文件为空"),
        (b"ATGC", "wrong.gb", "文件类型不支持"),
        (b"\xff\xfe", "bad.txt", "无法按 UTF-8 解码"),
    ):
        with pytest.raises(MvpSequenceInputError, match=message):
            decode_uploaded_text(data, file_name=name, allowed_suffixes=DNA_FILE_SUFFIXES)
    with pytest.raises(MvpSequenceInputError, match="非法字符"):
        _component("promoter", "ATGX")
    with pytest.raises(MvpSequenceInputError, match="多条记录"):
        _component("terminator", ">one\nAAAA\n>two\nTTTT\n")
    with pytest.raises(MvpSequenceInputError, match="没有可用记录"):
        _component("promoter", ">empty\n")


def test_user_genbank_backbone_parses_one_record_and_rejects_empty_broken_or_multiple_records() -> None:
    text = _genbank_text("ACGT" * 300)
    decoded = decode_uploaded_text(text.encode(), file_name="vector.genbank", allowed_suffixes=GENBANK_FILE_SUFFIXES)
    record = analyze_genbank_backbone_input(
        decoded,
        project_id="plant-draft-backbone-test",
        display_name="User vector",
        source_kind="upload",
        source_name="vector.genbank",
    )
    assert record["length"] == 1200
    assert record["topology"] == "circular"
    assert record["imported_feature_records"]

    with pytest.raises(MvpSequenceInputError, match="骨架为空"):
        analyze_genbank_backbone_input(
            "",
            project_id="plant-draft-backbone-test",
            display_name="Empty",
            source_kind="upload",
            source_name="empty.gb",
        )
    with pytest.raises(MvpSequenceInputError, match="GenBank 文件无法解析"):
        analyze_genbank_backbone_input(
            "not genbank",
            project_id="plant-draft-backbone-test",
            display_name="Broken",
            source_kind="upload",
            source_name="broken.gb",
        )
    with pytest.raises(MvpSequenceInputError, match="多条记录"):
        analyze_genbank_backbone_input(
            text + _genbank_text("TGCA" * 300, record_id="second"),
            project_id="plant-draft-backbone-test",
            display_name="Multiple",
            source_kind="upload",
            source_name="multiple.gbk",
        )


def test_user_three_sequences_with_example_backbone_have_exact_cassette_coordinates_and_sequence() -> None:
    cds_input, records, settings = _user_inputs()
    signature = generation_input_signature(records, settings, project_name="User example backbone")
    result = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id="plant-draft-user-example-backbone",
        project_name="User example backbone",
        input_signature=signature,
    )
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    expected_cassette = "AACCGGTTAACC" + cds_input["normalized_cds"] + "TTGGAATTCC"
    backbone = records["backbone"]["normalized_sequence"]

    assert cassette["sequence"] == expected_cassette
    assert cassette["sequence_length"] == len(expected_cassette)
    assert cassette["feature_rows"][0]["start"] == 1
    assert cassette["feature_rows"][-1]["end"] == len(expected_cassette)
    assert plasmid["sequence"] == backbone[:2100] + expected_cassette + backbone[2100:]
    assert plasmid["cassette_coordinates"] == {"start": 2101, "end": 2100 + len(expected_cassette)}
    assert result["plasmid_length"] == len(backbone) + len(expected_cassette)


def test_user_genbank_features_are_shifted_and_cassette_is_inserted_once() -> None:
    backbone_text = _genbank_text("ACGT" * 300)
    cds_input, records, settings = _user_inputs(backbone_text=backbone_text)
    result = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id="plant-draft-user-genbank",
        project_name="User GenBank backbone",
    )
    cassette = active_construct_snapshot(result["runtime"])["sequence"]
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    original_backbone = records["backbone"]["normalized_sequence"]

    assert plasmid["sequence"] == original_backbone[:600] + cassette + original_backbone[600:]
    assert plasmid["sequence"].count(cassette) == 1
    shifted = next(row for row in plasmid["feature_rows"] if row["name"] == "user_feature")
    assert shifted["start"] == 801 + len(cassette)
    assert shifted["end"] == 850 + len(cassette)
    parsed = next(SeqIO.parse(StringIO(result["exports"]["genbank"]["data"]), "genbank"))
    assert str(parsed.seq).upper() == plasmid["sequence"]


def test_non_hsa_user_case_reuses_one_canonical_cassette_and_preserves_reverse_orientation(tmp_path: Path) -> None:
    """Regression fixture only; it is not a biological design recommendation."""
    backbone_text = _genbank_text("ACGT" * 300, record_id="test_uploaded_backbone")
    cds_input, records, settings = _user_inputs(backbone_text=backbone_text)
    records["promoter"] = _component("promoter", ">test_promoter\nAACCGGTTAACC\n", source_kind="upload", source_name="test_promoter.fa")
    records["terminator"] = _component("terminator", "TTGGAATTCC", source_kind="paste", source_name="用户提供，待确认")
    settings["insertion_orientation"] = "reverse"
    project_name = "TEST CASE - non HSA user workflow"
    cassette_result = generate_expression_cassette(
        cds_input=cds_input,
        input_records={role: records[role] for role in ("promoter", "cds", "terminator")},
        project_id="test-non-hsa-workflow",
        project_name=project_name,
    )
    before = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id="test-non-hsa-workflow",
        project_name=project_name,
        cassette_runtime=cassette_result["runtime"],
    )
    cassette = active_construct_snapshot(before["runtime"])
    plasmid = active_complete_plasmid_snapshot(before["runtime"])
    assert cassette["sequence"] == active_construct_snapshot(cassette_result["runtime"])["sequence"]
    assert plasmid["insertion_site"]["insertion_orientation"] == "reverse"
    fasta = next(SeqIO.parse(StringIO(before["exports"]["fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(before["exports"]["genbank"]["data"]), "genbank"))
    assert str(fasta.seq) == str(genbank.seq) == plasmid["sequence"]
    repository = PlantProjectDraftRepository(tmp_path / "non-hsa")
    saved = save_mvp_single_gene_design(before, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)
    assert reopened["project_name"] == project_name
    assert reopened["source_inputs"] == before["source_inputs"]
    assert reopened["exports"] == before["exports"]


def test_cassette_and_construct_signatures_split_component_and_backbone_inputs() -> None:
    _, records, settings = _user_inputs()
    cassette_baseline = cassette_input_signature(records)
    construct_baseline = construct_input_signature(records, settings)
    for role in ("promoter", "cds", "terminator"):
        changed = deepcopy(records)
        changed[role]["display_name"] += " changed"
        assert cassette_input_signature(changed) != cassette_baseline
        assert construct_input_signature(changed, settings) != construct_baseline
        changed = deepcopy(records)
        changed[role]["normalized_sequence"] += "A"
        assert cassette_input_signature(changed) != cassette_baseline
        assert construct_input_signature(changed, settings) != construct_baseline

    changed = deepcopy(records)
    changed["backbone"]["normalized_sequence"] += "A"
    changed["backbone"]["original_text"] += "A"
    assert cassette_input_signature(changed) == cassette_baseline
    assert construct_input_signature(changed, settings) != construct_baseline
    changed = deepcopy(records)
    changed["backbone"]["topology"] = "linear"
    assert cassette_input_signature(changed) == cassette_baseline
    assert construct_input_signature(changed, settings) != construct_baseline
    for key, value in (
        ("mode", "replacement"),
        ("start_coordinate", 100),
        ("end_coordinate", 101),
        ("expected_removed_sequence", "AC"),
        ("insertion_orientation", "reverse"),
    ):
        changed_settings = dict(settings)
        changed_settings[key] = value
        assert cassette_input_signature(records) == cassette_baseline
        assert construct_input_signature(records, changed_settings) != construct_baseline


def test_non_hsa_step4_cassette_survives_step5_construct_changes_with_expected_lengths() -> None:
    project_id = "plant-draft-signature-regression"
    cds_sequence = "ATG" + ("GCT" * 99) + "TAA"
    cds_input = analyze_cds_input(cds_sequence, source_kind="paste", source_name="user-cds")
    records = {
        "promoter": _component("promoter", "A" * 150, project_id=project_id),
        "cds": {
            "role": "cds",
            "source_kind": "paste",
            "source_name": "user-cds",
            "source_format": "plain",
            "display_name": COMPONENT_NAMES["cds"],
            "original_text": cds_input["original_text"],
            "normalized_sequence": cds_input["normalized_cds"],
            "length": cds_input["normalized_length"],
        },
        "terminator": _component("terminator", "T" * 120, project_id=project_id),
        "backbone": analyze_genbank_backbone_input(
            _genbank_text("ACGT" * 450),
            project_id=project_id,
            display_name="USER_1800_BP_BACKBONE",
            source_kind="upload",
            source_name="user_backbone.gbk",
        ),
    }
    settings = {
        "mode": "insertion",
        "start_coordinate": 600,
        "end_coordinate": 601,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
    }
    cassette_signature = cassette_input_signature(records)
    cassette_result = generate_expression_cassette(
        cds_input=cds_input,
        input_records={role: records[role] for role in ("promoter", "cds", "terminator")},
        project_id=project_id,
        project_name="Non-HSA signature regression",
        input_signature=cassette_signature,
    )
    assert cassette_result["cassette_input_signature"] == cassette_signature
    assert cassette_result["cassette_length"] == 573

    baseline_construct_signature = construct_input_signature(
        records, settings, cassette_signature=cassette_signature
    )
    result = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name="Non-HSA signature regression",
        input_signature=baseline_construct_signature,
        cassette_runtime=cassette_result["runtime"],
    )
    assert result["cassette_input_signature"] == cassette_signature
    assert result["cassette_length"] == 573
    assert result["input_lengths"]["backbone"] == 1800
    assert result["plasmid_length"] == 2373

    for changed_settings in (
        {**settings, "start_coordinate": 601, "end_coordinate": 602},
        {**settings, "insertion_orientation": "reverse"},
    ):
        assert cassette_input_signature(records) == cassette_signature
        assert construct_input_signature(records, changed_settings) != baseline_construct_signature

    changed_backbone = deepcopy(records)
    changed_backbone["backbone"]["original_text"] += "\nCOMMENT changed file content"
    assert cassette_input_signature(changed_backbone) == cassette_signature
    assert construct_input_signature(changed_backbone, settings) != baseline_construct_signature

    for role in ("cds", "promoter", "terminator"):
        changed_component = deepcopy(records)
        changed_component[role]["normalized_sequence"] += "A"
        assert cassette_input_signature(changed_component) != cassette_signature
        assert construct_input_signature(changed_component, settings) != baseline_construct_signature



def test_generalized_save_reopen_restores_all_inputs_settings_runtime_and_exact_export_bytes(tmp_path: Path) -> None:
    cds_input, records, settings = _user_inputs(backbone_text=_genbank_text("ACGT" * 300))
    before = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id="plant-draft-generalized-save",
        project_name="Generalized user project",
    )
    repository = PlantProjectDraftRepository(tmp_path / "r224")
    saved = save_mvp_single_gene_design(before, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    assert reopened["project_id"] == "plant-draft-generalized-save"
    assert reopened["project_name"] == "Generalized user project"
    assert reopened["input_records"] == before["input_records"]
    assert reopened["insertion_settings"] == before["insertion_settings"]
    assert reopened["input_signature"] == before["input_signature"]
    assert reopened["runtime"] == before["runtime"]
    assert reopened["exports"]["fasta"]["data"].encode() == before["exports"]["fasta"]["data"].encode()
    assert reopened["exports"]["genbank"]["data"].encode() == before["exports"]["genbank"]["data"].encode()


def test_formal_non_hsa_save_list_and_reopen_preserve_the_exact_user_project(tmp_path: Path) -> None:
    project_id = "formal-non-hsa-single-gene-regression"
    raw_backbone = _genbank_text("ACGT" * 450, record_id="formal_user_backbone")
    cds_input = analyze_cds_input("ATG" + ("GCT" * 99) + "TAA", source_kind="paste", source_name="user-cds")
    records = {
        "promoter": _component("promoter", "A" * 150, project_id=project_id),
        "cds": {
            "role": "cds",
            "source_kind": "paste",
            "source_name": "user-cds",
            "source_format": "plain",
            "display_name": COMPONENT_NAMES["cds"],
            "original_text": cds_input["original_text"],
            "normalized_sequence": cds_input["normalized_cds"],
            "length": cds_input["normalized_length"],
        },
        "terminator": _component("terminator", "T" * 120, project_id=project_id),
        "backbone": analyze_genbank_backbone_input(
            raw_backbone,
            project_id=project_id,
            display_name="formal_user_backbone.gbk",
            source_kind="upload",
            source_name="formal_user_backbone.gbk",
        ),
    }
    settings = {
        "mode": "insertion",
        "start_coordinate": 700,
        "end_coordinate": 701,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
    }
    before = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name="非HSA单基因用户输入回归项目",
    )
    before["formal_project_context"] = {
        "host_key": "Arabidopsis thaliana",
        "expression_target": "用户表达目标",
        "current_step": 6,
    }

    repository = PlantProjectDraftRepository(tmp_path / "formal-user-projects")
    saved = save_mvp_single_gene_design(before, repository=repository)
    listed = list_mvp_single_gene_designs(repository=PlantProjectDraftRepository(repository.storage_dir))
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)
    cassette = active_construct_snapshot(reopened["runtime"])
    plasmid = active_complete_plasmid_snapshot(reopened["runtime"])

    assert [summary.project_id for summary in listed] == [project_id]
    assert reopened["project_name"] == "非HSA单基因用户输入回归项目"
    assert reopened["formal_project_context"] == before["formal_project_context"]
    assert reopened["input_lengths"] == {"promoter": 150, "cds": 303, "terminator": 120, "backbone": 1800}
    assert cassette["sequence_length"] == 573
    assert plasmid["sequence_length"] == 2373
    assert plasmid["topology"] == "circular"
    assert reopened["insertion_settings"] == settings
    assert reopened["input_records"]["backbone"]["original_text"] == raw_backbone
    assert reopened["source_input_sha256"]["backbone"] == hashlib.sha256(raw_backbone.encode("utf-8")).hexdigest()
    assert cassette["sequence_checksum"] == active_construct_snapshot(before["runtime"])["sequence_checksum"]
    assert reopened["plasmid_sha256"] == before["plasmid_sha256"]
    assert reopened["exports"] == before["exports"]


def test_missing_core_input_and_out_of_range_coordinate_do_not_produce_exports() -> None:
    cds_input, records, settings = _user_inputs()
    records["promoter"] = {**records["promoter"], "normalized_sequence": "", "length": 0}
    with pytest.raises(RuntimeError, match="promoter 输入为空"):
        generate_complete_vector(cds_input=cds_input, input_records=records, insertion_settings=settings)

    cds_input, records, settings = _user_inputs()
    settings["start_coordinate"] = 99999
    settings["end_coordinate"] = 100000
    with pytest.raises(RuntimeError, match="坐标无效"):
        generate_complete_vector(cds_input=cds_input, input_records=records, insertion_settings=settings)
