from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

from mvp_app import generate_complete_vector, generation_input_signature
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    export_active_construct,
)
from services.formal_t_dna_review import validate_t_dna_operation
from services.mvp_single_gene_persistence import (
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.mvp_sequence_input import analyze_genbank_backbone_input
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.professional_review_delivery_package import (
    CHECKSUM_FILES,
    COMPONENT_INVENTORY_COLUMNS,
    PACKAGE_FILES,
    PROVENANCE_REVIEW_COLUMNS,
    REVIEW_BLOCKED,
    REVIEW_NEEDS_PROVENANCE,
    REVIEW_READY,
    ProfessionalReviewPackageError,
    assess_professional_review_package,
    build_professional_review_package,
    validate_professional_review_package_bytes,
)
from tests.test_company_delivery_package import _alb_demo_result
from services.rice_hsa_ncbi_mvp10_case import BACKBONE_GENBANK


PROJECT_NAME = "水稻 ALB pCAMBIA-1300 单基因闭环验收"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _review_result(*, complete_provenance: bool = False) -> dict:
    seed = _alb_demo_result()
    records = deepcopy(seed["input_records"])
    records["promoter"].update(source_kind="library")
    records["cds"].update(source_kind="user_uploaded")
    records["terminator"].update(source_kind="library")
    project_id = "professional-review-ready" if complete_provenance else "professional-review-pcambia"
    records["backbone"] = analyze_genbank_backbone_input(
        BACKBONE_GENBANK.read_text(encoding="utf-8"),
        project_id=project_id,
        display_name="pCAMBIA-1300 / AF234296.1",
        source_kind="user_uploaded",
        source_name="AF234296.1.gb",
    )
    if complete_provenance:
        records["promoter"].update(
            display_name="ZmUbi promoter record",
            source_name="plant_component_registry",
            source_reference="registry:promoter:ZmUbi:v1",
        )
        records["cds"].update(source_accession_version="NM_000477.7")
        records["terminator"].update(
            display_name="NOS 3prime record",
            source_name="plant_component_registry",
            source_reference="registry:three_prime:NOS:v1",
        )
    backbone = records["backbone"]
    settings = {
        "mode": "insertion",
        "start_coordinate": 27,
        "end_coordinate": 28,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
        "insertion_orientation": "forward",
        "construction_strategy_confirmed": True,
        "workflow_id": "rice_alb_single_gene",
    }
    settings["t_dna_operation_validation"] = validate_t_dna_operation(
        backbone,
        confirmation={},
        insertion_settings=settings,
        workflow_id="rice_alb_single_gene",
    )
    cds_input = deepcopy(seed["cds_input"])
    cds_input["source_review_basis"] = {
        "source_type": "公共数据库记录",
        "source_reference": "NM_000477.7",
        "source_species": "Homo sapiens",
        "modification_status": "未修改的来源序列",
        "modification_note": "",
        "is_partial_cds": False,
    }
    cds_input["manual_review_items"] = [] if complete_provenance else [
        {
            "rule_id": "accession_unverified",
            "status": "需要人工确认",
            "blocking": False,
            "message": "accession 尚未联网核实；请人工确认来源记录。",
        },
        {
            "rule_id": "gene_name_fasta_title_mismatch",
            "status": "需要人工确认",
            "blocking": False,
            "message": "目标基因名称与 FASTA 标题不一致。",
        },
    ]
    signature = generation_input_signature(records, settings, project_name=PROJECT_NAME)
    result = generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=PROJECT_NAME,
        input_signature=signature,
        workflow_id="rice_alb_single_gene",
    )
    result["cds_input"] = cds_input
    result["cassette_exports"] = export_active_construct(
        result["runtime"], project_name=result["project_name"]
    )
    result["formal_project_context"] = {
        "host_key": "Rice (O. sativa)",
        "expression_target": "文档记录目标",
        "current_step": 6,
        "construct_review_status": "current",
        "cds_source_review_status": "current",
        "project_definition": {
            "project_name": PROJECT_NAME,
            "plant_host": "Rice (O. sativa)",
            "material": "",
            "application_mode": "尚未确定",
            "transient_expression_system": "尚未确定",
            "tissue_specificity_requirement": "尚未确定",
            "tissue_target": "",
            "inducibility_requirement": "尚未确定",
            "induction_notes": "",
            "localization_target": "",
        },
    }
    return result


def _archive_files(package: dict) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(package["data"]), "r") as archive:
        assert archive.namelist() == list(PACKAGE_FILES)
        return {name: archive.read(name) for name in archive.namelist()}


def test_pcambia_review_draft_contains_exact_ten_files_and_canonical_bytes() -> None:
    result = _review_result()
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    package = build_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    files = _archive_files(package)

    assert package["review_status"] == REVIEW_NEEDS_PROVENANCE
    assert package["wet_lab_readiness"] == "not_assessed"
    assert len(package["files"]) == 10
    readme = files["README.md"].decode("utf-8")
    assert "当前软件用于植物表达载体的计算设计、计算校验、项目保存和文件导出；尚未经过湿实验验证，不代表实际表达成功或湿实验就绪。" in readme
    assert "实验验证通过" not in readme
    assert "可直接实验" not in readme
    assert "自动优化完成" not in readme
    assert files["complete_plasmid.fasta"] == result["exports"]["fasta"]["data"].encode("utf-8")
    assert files["complete_plasmid.gb"] == result["exports"]["genbank"]["data"].encode("utf-8")
    assert cassette["sequence_length"] == 2048
    assert plasmid["sequence_length"] == 11006
    fasta = SeqIO.read(StringIO(files["complete_plasmid.fasta"].decode("utf-8")), "fasta")
    genbank = SeqIO.read(StringIO(files["complete_plasmid.gb"].decode("utf-8")), "genbank")
    cassette_fasta = SeqIO.read(StringIO(files["expression_cassette.fasta"].decode("utf-8")), "fasta")
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == plasmid["sequence"]
    assert len(fasta.seq) == len(genbank.seq) == 11006
    assert len(cassette_fasta.seq) == 2048


def test_inventory_summary_provenance_manifest_and_checksums_are_exact() -> None:
    result = _review_result()
    package = build_professional_review_package(result, current_input_signature=result["input_signature"])
    files = _archive_files(package)
    inventory = list(csv.DictReader(StringIO(files["component_inventory.csv"].decode("utf-8"))))
    assert tuple(inventory[0]) == COMPONENT_INVENTORY_COLUMNS
    by_role = {
        row["biological_role"].lower(): row
        for row in inventory
        if row["expression_cassette"] == "TU1"
    }
    assert (by_role["promoter"]["start_1_based"], by_role["promoter"]["end_1_based"], by_role["promoter"]["length_bp"], by_role["promoter"]["strand"]) == ("28", "63", "36", "1")
    assert (by_role["cds"]["start_1_based"], by_role["cds"]["end_1_based"], by_role["cds"]["length_bp"], by_role["cds"]["strand"]) == ("64", "1893", "1830", "1")
    assert (by_role["terminator"]["start_1_based"], by_role["terminator"]["end_1_based"], by_role["terminator"]["length_bp"], by_role["terminator"]["strand"]) == ("1894", "2075", "182", "1")

    provenance = list(csv.DictReader(StringIO(files["provenance_review.csv"].decode("utf-8"))))
    assert tuple(provenance[0]) == PROVENANCE_REVIEW_COLUMNS
    provenance_by_role = {row["biological_role"]: row for row in provenance}
    assert "缺少可追溯的具体来源引用" in provenance_by_role["promoter"]["missing_information"]
    assert "accession 尚未联网核实" in provenance_by_role["cds"]["missing_information"]
    assert "缺少可追溯的具体来源引用" in provenance_by_role["terminator"]["missing_information"]
    assert provenance_by_role["backbone"]["review_status"] == "recorded"

    summary = json.loads(files["construct_summary.json"])
    assert summary["cds_summary"]["length_bp"] == 1830
    assert summary["expression_cassette_summary"]["length_bp"] == 2048
    assert summary["backbone_summary"]["length_bp"] == 8958
    assert summary["complete_construct"]["length_bp"] == 11006
    assert summary["insertion_operation"] == {
        "end_1_based": 28,
        "expected_removed_sequence": "",
        "mode": "insertion",
        "orientation": "forward",
        "start_1_based": 27,
    }

    manifest = json.loads(files["manifest.json"])
    assert manifest["review_status"] == REVIEW_NEEDS_PROVENANCE
    assert manifest["wet_lab_readiness"] == "not_assessed"
    assert manifest["complete_plasmid"] == {"length_bp": 11006, "topology": "circular"}
    for entry in manifest["payload_files"]:
        assert entry["size_bytes"] == len(files[entry["name"]])
        assert entry["sha256"] == _sha256(files[entry["name"]])
    checksum_rows = [line.split("  ", 1) for line in files["checksums.sha256"].decode("utf-8").splitlines()]
    assert [name for _checksum, name in checksum_rows] == list(CHECKSUM_FILES)
    assert all(checksum == _sha256(files[name]) for checksum, name in checksum_rows)
    assert validate_professional_review_package_bytes(package["data"])["verified"] is True


def test_same_snapshot_and_cold_reopen_generate_identical_package(tmp_path: Path) -> None:
    result = _review_result()
    first = build_professional_review_package(result, current_input_signature=result["input_signature"])
    second = build_professional_review_package(result, current_input_signature=result["input_signature"])
    assert first["data"] == second["data"]
    assert first["manifest"] == second["manifest"]
    assert first["file_checksums"] == second["file_checksums"]

    repository = PlantProjectDraftRepository(tmp_path / "plant_drafts")
    saved = save_mvp_single_gene_design(result, repository=repository)
    reopened = open_mvp_single_gene_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    cold = build_professional_review_package(
        reopened,
        current_input_signature=reopened["input_signature"],
    )
    assert cold["review_status"] == first["review_status"]
    assert cold["provenance_gap_count"] == first["provenance_gap_count"]
    assert cold["manifest"] == first["manifest"]
    assert cold["file_checksums"] == first["file_checksums"]
    assert cold["data"] == first["data"]


def test_complete_provenance_fixture_is_ready_but_wet_lab_readiness_is_not_assessed() -> None:
    result = _review_result(complete_provenance=True)
    assessment = assess_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    package = build_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_READY
    assert assessment["provenance_gap_count"] == 0
    assert assessment["manual_review_count"] == 0
    assert package["review_status"] == REVIEW_READY
    assert package["manifest"]["wet_lab_readiness"] == "not_assessed"


def test_stale_signature_asset_mismatch_parameter_change_and_export_mismatch_are_blocked() -> None:
    result = _review_result()
    stale = assess_professional_review_package(result, current_input_signature="stale")
    assert stale["review_status"] == REVIEW_BLOCKED
    assert "失效" in stale["blocking_reasons"][0]

    expired = deepcopy(result)
    expired["input_records"]["backbone"]["topology"] = "linear"
    assessment = assess_professional_review_package(
        expired,
        current_input_signature=expired["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED
    assert "门禁" in assessment["blocking_reasons"][0]

    moved = deepcopy(result)
    moved["insertion_settings"]["start_coordinate"] = 26
    assessment = assess_professional_review_package(
        moved,
        current_input_signature=moved["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED
    assert "参数已变化" in assessment["blocking_reasons"][0]

    mismatched = deepcopy(result)
    mismatched["exports"]["fasta"]["data"] = mismatched["exports"]["fasta"]["data"].replace("A", "T", 1)
    assessment = assess_professional_review_package(
        mismatched,
        current_input_signature=mismatched["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED
    assert "不一致" in assessment["blocking_reasons"][0]


def test_computational_block_missing_active_dna_and_internal_zip_tamper_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _review_result()
    from services import professional_review_delivery_package as service

    original_plasmid = service.active_complete_plasmid_snapshot

    def _blocked_plasmid(runtime: dict) -> dict:
        snapshot = original_plasmid(runtime)
        snapshot["validation_summary"] = {"blocking_count": 1}
        snapshot["validation_findings"] = [
            {
                "rule_id": "focused_test_block",
                "severity": "error",
                "blocking": True,
                "message": "Focused test computational block.",
            }
        ]
        return snapshot

    monkeypatch.setattr(service, "active_complete_plasmid_snapshot", _blocked_plasmid)
    assessment = service.assess_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED
    assert assessment["blocking_count"] == 1
    monkeypatch.setattr(service, "active_complete_plasmid_snapshot", original_plasmid)

    missing_dna = deepcopy(result)
    active_promoter_id = next(
        item["sequence_asset_id"]
        for item in missing_dna["runtime"]["components"]
        if item["component_type"] == "promoter"
    )
    next(
        item
        for item in missing_dna["runtime"]["sequence_assets"]
        if item["asset_id"] == active_promoter_id
    )["nucleotide_sequence"] = ""
    assessment = service.assess_professional_review_package(
        missing_dna,
        current_input_signature=missing_dna["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED

    package = build_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    source_files = _archive_files(package)
    source_files["README.md"] += b"tampered\n"
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PACKAGE_FILES:
            archive.writestr(name, source_files[name])
    with pytest.raises(ProfessionalReviewPackageError, match="校验失败"):
        validate_professional_review_package_bytes(output.getvalue())


def test_results_page_keeps_review_package_builder_out_of_formal_runtime() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    result_page = source.split("def _render_results_export_content", 1)[1].split(
        "def _plant_library_records", 1
    )[0]
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "packaging" / "resource_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert "assess_professional_review_package" not in result_page
    assert "build_professional_review_package" not in result_page
    assert "专业审查包 ZIP" not in result_page
    assert "services/professional_review_delivery_package.py" not in manifest["runtime_python_modules"]


def test_multi_tu_results_page_hides_unit_id_in_default_summary_table() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    overview_block = source.split("unit_rows = sorted(", 1)[1].split("order_display =", 1)[0]
    assert "_t('v1.results_final_report.order'): f\"TU{index}\"" in overview_block
    assert "_t('v1.results_final_report.name'): str(unit.get(\"display_name\") or unit.get(\"unit_name\") or unit.get(\"unit_id\") or \"--\")" in overview_block
    assert "_t('v1.common.orientation'): _t('v1.common.reverse') if unit.get(\"orientation\") == \"reverse\" else _t('v1.common.forward')" in overview_block
    assert "_t('v1.results_final_report.length'): int(unit.get(\"length\") or 0)" in overview_block
    assert '"unit_id": str(unit.get("unit_id") or "")' not in overview_block
