from __future__ import annotations

import csv
import json
import re
from io import BytesIO
from io import StringIO
from zipfile import ZipFile

import pytest
from Bio import SeqIO

from core.expression_frame_builder import get_host_rules
from mvp_app import _cds_record, generate_complete_vector, generation_input_signature, load_real_case
from services.company_delivery_package import (
    PACKAGE_FILES,
    CompanyDeliveryPackageError,
    _feature_conflict_result,
    build_company_delivery_package,
)
from services.mvp_cds_input import analyze_cds_input
from services.mvp_sequence_input import analyze_dna_component_input, analyze_genbank_backbone_input
from services.plant_project_draft_schema import new_project_id
from services.rice_hsa_ncbi_mvp10_case import ALB_GENBANK
from services.rice_hsa_ncbi_mvp10_case import (
    DEMO_BOUNDARY_NOTE,
    REAL_CASE_BOUNDARY_NOTE,
    REAL_CASE_PROJECT_NAME,
    build_rice_hsa_real_case,
)
from services.canonical_construct_runtime import export_active_construct
from services.canonical_construct_runtime import active_complete_plasmid_snapshot, active_construct_snapshot


def _alb_demo_result() -> dict:
    project_id = new_project_id()
    rules = get_host_rules("Rice (O. sativa)")
    record = SeqIO.read(ALB_GENBANK, "genbank")
    alb_feature = next(feature for feature in record.features if feature.type == "CDS")
    cds_input = analyze_cds_input(
        str(alb_feature.extract(record.seq)), source_kind="wizard_step_1", source_name="NM_000477.7"
    )
    records = {
        "promoter": analyze_dna_component_input(
            str(rules["promoter_seq"]), project_id=project_id, component_type="promoter",
            display_name="ZmUbi 启动子演示片段", source_kind="wizard_step_2", source_name="内置植物元件记录",
        ),
        "cds": _cds_record(cds_input, display_name="ALB CDS"),
        "terminator": analyze_dna_component_input(
            str(rules["terminator_seq"]), project_id=project_id, component_type="terminator",
            display_name="NOS 终止子演示片段", source_kind="wizard_step_2", source_name="内置植物元件记录",
        ),
        "backbone": analyze_genbank_backbone_input(
            load_real_case()["backbone"], project_id=project_id, display_name="植物载体骨架",
            source_kind="example", source_name="内置示例骨架",
        ),
    }
    settings = {"mode": "insertion", "start_coordinate": 2100, "end_coordinate": 2101, "expected_removed_sequence": "", "topology_confirmation": False}
    signature = generation_input_signature(records, settings, project_name="水稻 ALB 演示项目")
    result = generate_complete_vector(
        cds_input=cds_input, input_records=records, insertion_settings=settings, project_id=project_id,
        project_name="水稻 ALB 演示项目", input_signature=signature,
    )
    result["cassette_exports"] = export_active_construct(result["runtime"], project_name=result["project_name"])
    return result


def test_company_delivery_package_reuses_runtime_export_bytes_and_lists_required_files() -> None:
    result = _alb_demo_result()

    package = build_company_delivery_package(
        result,
        current_input_signature=str(result["input_signature"]),
    )

    assert package["file_name"] == "水稻 ALB 演示项目_公司交付包.zip"
    assert package["files"] == list(PACKAGE_FILES)
    with ZipFile(BytesIO(package["data"])) as archive:
        assert archive.namelist() == list(PACKAGE_FILES)
        assert archive.read("02_完整质粒.gb") == result["exports"]["genbank"]["data"].encode("utf-8")
        assert archive.read("03_完整质粒.fasta") == result["exports"]["fasta"]["data"].encode("utf-8")
        report = archive.read("01_设计交付说明.html").decode("utf-8")
        assert DEMO_BOUNDARY_NOTE in report
        coordinate_csv = archive.read("05_元件与坐标清单.csv").decode("utf-8-sig")
        assert "所属表达单元" in coordinate_csv
        assert "transcription_unit" not in coordinate_csv
        assert "完整质粒长度：6,248 bp" in report
        assert "ALB CDS</td><td>1,830 bp" in report
        assert "已执行完整 feature 冲突分析：未发现与原有 feature 的重叠冲突。" in report
        assert "完整质粒 6,248 bp" in report
        assert "复制起点（ORI_ALPHA）" in report
        assert "上游位点（UPSTREAM_SITE）" in report
        assert "筛选标记（SELECT_MARK）" in report
        assert "末端审计区（TAIL_AUDIT）" in report


def test_company_delivery_package_rejects_stale_input_signature() -> None:
    result = _alb_demo_result()

    with pytest.raises(CompanyDeliveryPackageError, match="已过期"):
        build_company_delivery_package(result, current_input_signature="stale")


def test_company_delivery_package_rejects_default_case_relabelled_as_alb() -> None:
    result = generate_complete_vector(project_name="水稻 ALB 演示项目")
    result["input_records"]["cds"]["display_name"] = "ALB CDS"
    result["input_records"]["cds"]["source_name"] = "NM_000477.7"
    result["cassette_exports"] = export_active_construct(result["runtime"], project_name=result["project_name"])

    with pytest.raises(CompanyDeliveryPackageError, match="canonical snapshot"):
        build_company_delivery_package(result, current_input_signature=str(result["input_signature"]))


def test_alb_delivery_artifacts_share_one_6248_bp_canonical_snapshot() -> None:
    result = _alb_demo_result()
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    package = build_company_delivery_package(result, current_input_signature=result["input_signature"])

    assert cassette["sequence_length"] == 2048
    assert result["input_lengths"]["backbone"] == 4200
    assert plasmid["sequence_length"] == result["plasmid_length"] == 6248
    assert len(plasmid["sequence"]) == 6248
    assert len("".join(line for line in result["exports"]["fasta"]["data"].splitlines() if not line.startswith(">"))) == 6248

    with ZipFile(BytesIO(package["data"])) as archive:
        genbank_text = archive.read("02_完整质粒.gb").decode("utf-8")
        genbank = next(SeqIO.parse(StringIO(genbank_text), "genbank"))
        assert re.search(r"^LOCUS\s+\S+\s+6248 bp", genbank_text, flags=re.MULTILINE)
        assert len(genbank.seq) == 6248
        report = archive.read("01_设计交付说明.html").decode("utf-8")
        assert "表达盒总长度：2,048 bp" in report
        assert "完整质粒长度：6,248 bp" in report
        assert "ALB CDS</td><td>1,830 bp" in report
        expected_summary = plasmid["validation_summary"]
        assert f"警告数：{expected_summary['warning_count']}；阻断数：{expected_summary['blocking_count']}；" in report
        coordinate_rows = list(csv.DictReader(StringIO(archive.read("05_元件与坐标清单.csv").decode("utf-8-sig"))))
        assert max(int(row["终点"]) for row in coordinate_rows) == max(
            int(row["end"]) for row in plasmid["feature_rows"]
        ) == 5708
        backup = json.loads(archive.read("09_项目备份.json").decode("utf-8"))
        backup_snapshot = active_complete_plasmid_snapshot(backup["runtime"])
        assert backup_snapshot["sequence_length"] == 6248

    assert package["file_checksums"]["02_完整质粒.gb"] == __import__("hashlib").sha256(result["exports"]["genbank"]["data"].encode("utf-8")).hexdigest()
    assert package["file_checksums"]["03_完整质粒.fasta"] == __import__("hashlib").sha256(result["exports"]["fasta"]["data"].encode("utf-8")).hexdigest()

    with ZipFile(BytesIO(package["data"])) as archive:
        recorded_checksums = dict(
            line.split("  ", 1)
            for line in archive.read("08_SHA256校验值.txt").decode("utf-8").splitlines()
            if line
        )
        assert set(recorded_checksums) == set(package["file_checksums"].values())
        for file_name, checksum in package["file_checksums"].items():
            assert __import__("hashlib").sha256(archive.read(file_name)).hexdigest() == checksum
            assert recorded_checksums[checksum] == file_name


def test_real_case_delivery_uses_the_reviewed_exact_insertion_contract() -> None:
    result = build_rice_hsa_real_case()
    package = build_company_delivery_package(
        result, current_input_signature=result["input_signature"]
    )
    assert package["data"]
    assert result["authenticity_gate"]["passed"] is True
    assert result["insertion_settings"]["exact_insertion_contract_version"]


def test_real_case_delivery_is_blocked_when_provenance_is_incomplete() -> None:
    result = build_rice_hsa_real_case()
    result["input_records"]["terminator"].pop("source_file_sha256")

    with pytest.raises(CompanyDeliveryPackageError, match="禁止公司交付包"):
        build_company_delivery_package(result, current_input_signature=result["input_signature"])


def test_feature_conflict_result_is_explicit_when_analysis_is_unavailable_or_finds_a_conflict() -> None:
    not_executed = {
        "sequence": "ACTG",
        "validation_summary": {"blocking_count": 1},
        "validation_findings": [
            {"rule_id": "missing_backbone", "severity": "error", "blocking": True, "message": "Backbone is missing."}
        ],
    }
    conflict = {
        "sequence": "ACTG",
        "validation_summary": {"blocking_count": 1},
        "validation_findings": [
            {
                "rule_id": "overlapping_backbone_feature_conflict",
                "severity": "error",
                "blocking": True,
                "message": "Backbone feature 'ORI_ALPHA' overlaps the selected insertion boundary.",
            }
        ],
    }

    assert _feature_conflict_result(not_executed) == "未执行完整 feature 冲突分析，需要人工复核。"
    assert _feature_conflict_result(conflict) == (
        "已执行完整 feature 冲突分析：发现与原有 feature 的冲突："
        "Backbone feature 'ORI_ALPHA' overlaps the selected insertion boundary."
    )
