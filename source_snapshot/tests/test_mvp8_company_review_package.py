from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections import Counter
from copy import deepcopy
from io import BytesIO
from pathlib import Path, PurePosixPath

import pytest
from Bio import SeqIO

import mvp_app
from services.canonical_construct_runtime import export_active_construct
from services.mvp_cds_input import analyze_cds_input
from services.mvp_company_review_package import (
    ALLOWED_SOURCE_KINDS,
    BOUNDARY_TEXT,
    CHECKSUM_FILE_ORDER,
    PACKAGE_FILE_ORDER,
    MvpCompanyReviewPackageError,
    build_company_review_package,
    safe_project_directory_name,
)
from services.mvp_sequence_input import (
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
)
from tests.mvp7_single_gene_test_support import (
    backbone_text_for_case,
    build_production_result,
    case_by_id,
)


EXPECTED_FASTA_SHA256 = "bff837583dad749f5b7e84c40750e3d479770ac534bcf4e9a1b0d2149b1577a3"
EXPECTED_GENBANK_SHA256 = "718a9dc01e371d6ee8e92b6f26d3f046d2de67749967a3ed458926014f23723b"
EXPECTED_SEQUENCE_SHA256 = "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _feature_tuple(feature) -> tuple[str, str, int, int, int, int]:
    qualifiers = feature.qualifiers or {}
    label = str((qualifiers.get("label") or [""])[0])
    parts = list(getattr(feature.location, "parts", None) or [feature.location])
    starts = [int(part.start) + 1 for part in parts]
    ends = [int(part.end) for part in parts]
    length = sum(int(part.end) - int(part.start) for part in parts)
    return (
        label,
        str(feature.type),
        int(feature.location.strand or 1),
        min(starts),
        max(ends),
        length,
    )


def _csv_tuple(row: dict[str, str]) -> tuple[str, str, int, int, int, int]:
    return (
        row["component_name"],
        row["component_type"],
        int(row["strand"]),
        int(row["start_1_based"]),
        int(row["end_1_based"]),
        int(row["length_bp"]),
    )


def _independently_extract_and_validate(
    package_bytes: bytes, extract_root: Path
) -> dict[str, object]:
    archive_path = extract_root / "review-package.zip"
    archive_path.write_bytes(package_bytes)
    unpack_root = extract_root / "unpacked"
    unpack_root.mkdir()

    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        assert len(names) == len(PACKAGE_FILE_ORDER)
        roots: set[str] = set()
        for name in names:
            relative = PurePosixPath(name)
            assert not relative.is_absolute()
            assert ".." not in relative.parts
            assert len(relative.parts) == 2
            roots.add(relative.parts[0])
            destination = (unpack_root / Path(*relative.parts)).resolve()
            assert destination.is_relative_to(unpack_root.resolve())
        assert len(roots) == 1
        root_name = next(iter(roots))
        assert names == [f"{root_name}/{name}" for name in PACKAGE_FILE_ORDER]
        archive.extractall(unpack_root)

    project_root = unpack_root / root_name
    actual_files = sorted(
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if path.is_file()
    )
    assert actual_files == sorted(PACKAGE_FILE_ORDER)

    checksum_lines = (project_root / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    assert len(checksum_lines) == len(CHECKSUM_FILE_ORDER)
    for line, relative_name in zip(checksum_lines, CHECKSUM_FILE_ORDER, strict=True):
        expected = f"{_sha256((project_root / relative_name).read_bytes())}  {relative_name}"
        assert line == expected

    with (project_root / "complete_plasmid.fasta").open("r", encoding="utf-8") as handle:
        complete_fasta_records = list(SeqIO.parse(handle, "fasta"))
    with (project_root / "expression_cassette.fasta").open("r", encoding="utf-8") as handle:
        cassette_records = list(SeqIO.parse(handle, "fasta"))
    with (project_root / "complete_plasmid.gb").open("r", encoding="utf-8") as handle:
        genbank_records = list(SeqIO.parse(handle, "genbank"))
    assert len(complete_fasta_records) == len(cassette_records) == len(genbank_records) == 1
    complete_sequence = str(complete_fasta_records[0].seq).upper()
    genbank_sequence = str(genbank_records[0].seq).upper()
    assert complete_sequence == genbank_sequence

    with (project_root / "component_coordinates.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
            "component_name",
            "component_type",
            "start_1_based",
            "end_1_based",
            "strand",
            "length_bp",
            "source_kind",
            "source_reference",
            "notes",
        ]
        coordinate_rows = list(reader)
    assert {row["component_type"].lower() for row in coordinate_rows}.issuperset(
        {"promoter", "cds", "terminator"}
    )
    assert Counter(map(_csv_tuple, coordinate_rows)) == Counter(
        _feature_tuple(feature) for feature in genbank_records[0].features
    )

    validation = json.loads((project_root / "validation_summary.json").read_text(encoding="utf-8"))
    assert validation["validation_scope"] == "software_sequence_and_structure_validation"
    assert isinstance(validation["overall_status"], str)
    assert isinstance(validation["errors"], list)
    assert isinstance(validation["warnings"], list)
    assert isinstance(validation["checks"], list)
    assert validation["accuracy_validation_reference"] == "v2.7-mvp7-single-gene-accuracy-validation"
    assert validation["wet_lab_validated"] is False
    assert validation["experimental_success_guaranteed"] is False
    assert "不代表湿实验成功" in validation["status_meaning_cn"]
    assert "不代表表达效果保证" in validation["status_meaning_cn"]

    manifest = json.loads((project_root / "construct_manifest.json").read_text(encoding="utf-8"))
    required_manifest_types = {
        "package_schema_version": str,
        "project_schema_version": str,
        "project_type": str,
        "project_name": str,
        "generated_by": str,
        "construct_topology": str,
        "cassette_length_bp": int,
        "backbone_length_bp": int,
        "complete_plasmid_length_bp": int,
        "insertion_mode": str,
        "insertion_coordinates": dict,
        "components": list,
        "files": list,
        "limitations": list,
    }
    for key, expected_type in required_manifest_types.items():
        assert isinstance(manifest[key], expected_type)
    assert manifest["package_schema_version"] == "1.0.0"
    assert manifest["project_schema_version"] == "1.0.0"
    assert manifest["project_type"] == "single_gene"
    assert [item["relative_path"] for item in manifest["files"]] == list(PACKAGE_FILE_ORDER)
    for component in manifest["components"]:
        for key in (
            "name",
            "type",
            "length_bp",
            "strand",
            "start_1_based",
            "end_1_based",
            "source_kind",
            "source_reference",
        ):
            assert key in component
        assert component["source_kind"] in ALLOWED_SOURCE_KINDS

    summary = (project_root / "construct_summary.txt").read_text(encoding="utf-8")
    assert BOUNDARY_TEXT in summary
    assert "设计类型：植物单基因表达载体" in summary
    return {
        "root": root_name,
        "project_root": project_root,
        "complete_sequence": complete_sequence,
        "cassette_sequence": str(cassette_records[0].seq).upper(),
        "genbank_record": genbank_records[0],
        "coordinate_rows": coordinate_rows,
        "manifest": manifest,
        "summary": summary,
    }


def _user_component_result(
    *, case_id: str, project_name: str, uploaded_backbone: bool
) -> dict:
    case = case_by_id(case_id)
    project_id = f"mvp8-{case_id}"
    records: dict[str, dict] = {}
    for role in ("promoter", "terminator"):
        records[role] = analyze_dna_component_input(
            str(case[f"{role}_sequence"]),
            project_id=project_id,
            component_type=role,
            display_name=str(case["component_names"][role]),
            source_kind="user_pasted",
            source_name=f"pasted-{role}",
        )
    cds_input = analyze_cds_input(
        str(case["cds_sequence"]),
        source_kind="user_pasted",
        source_name="pasted-cds",
    )
    records["cds"] = mvp_app._cds_record(
        cds_input,
        display_name=str(case["component_names"]["cds"]),
    )
    if uploaded_backbone:
        records["backbone"] = analyze_genbank_backbone_input(
            backbone_text_for_case(case),
            project_id=project_id,
            display_name=f"BACKBONE_{case_id}",
            source_kind="user_uploaded",
            source_name="../uploads/customer_backbone.gb",
        )
        coordinates = case["insertion_coordinates"]
        settings = {
            "mode": str(case["insertion_mode"]),
            "start_coordinate": int(coordinates["start"]),
            "end_coordinate": int(coordinates["end"]),
            "expected_removed_sequence": str(case["expected_removed_sequence"]),
            "topology_confirmation": False,
        }
    else:
        fixture = mvp_app.load_real_case()
        records["backbone"] = mvp_app._backbone_record_from_example(
            project_id=project_id,
            case=fixture,
        )
        settings = {
            "mode": "insertion",
            "start_coordinate": 2100,
            "end_coordinate": 2101,
            "expected_removed_sequence": "",
            "topology_confirmation": False,
        }
    signature = mvp_app.generation_input_signature(records, settings, project_name=project_name)
    return mvp_app.generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=project_name,
        input_signature=signature,
    )


def test_stable_example_package_is_independently_valid_and_identical_five_times(
    tmp_path: Path,
) -> None:
    result = mvp_app.generate_complete_vector(mvp_app.load_real_case())
    packages = [build_company_review_package(result) for _ in range(5)]

    assert len({package["sha256"] for package in packages}) == 1
    assert all(package["data"] == packages[0]["data"] for package in packages)
    assert _sha256(result["exports"]["fasta"]["data"].encode("utf-8")) == EXPECTED_FASTA_SHA256
    assert _sha256(result["exports"]["genbank"]["data"].encode("utf-8")) == EXPECTED_GENBANK_SHA256
    assert result["plasmid_sha256"] == EXPECTED_SEQUENCE_SHA256

    inspected = _independently_extract_and_validate(packages[0]["data"], tmp_path)
    assert _sha256(str(inspected["complete_sequence"]).encode("ascii")) == EXPECTED_SEQUENCE_SHA256
    root = Path(inspected["project_root"])
    assert (root / "complete_plasmid.fasta").read_bytes() == result["exports"]["fasta"]["data"].encode("utf-8")
    assert (root / "complete_plasmid.gb").read_bytes() == result["exports"]["genbank"]["data"].encode("utf-8")
    cassette_export = export_active_construct(result["runtime"], project_name=result["project_name"])
    assert (root / "expression_cassette.fasta").read_bytes() == cassette_export["fasta"]["data"].encode("utf-8")


def test_user_components_with_example_backbone_preserve_sources_and_lengths(tmp_path: Path) -> None:
    result = _user_component_result(
        case_id="case_02_variable_user_components",
        project_name="用户三元件项目",
        uploaded_backbone=False,
    )
    inspected = _independently_extract_and_validate(
        result["company_review_package"]["data"], tmp_path
    )
    manifest = inspected["manifest"]
    components = {item["type"]: item for item in manifest["components"]}

    for role in ("promoter", "cds", "terminator"):
        assert components[role]["source_kind"] == "user_pasted"
        assert components[role]["source_reference"] == "not_provided"
        assert components[role]["length_bp"] == result["input_lengths"][role]
    assert components["backbone"]["source_kind"] == "example"
    assert manifest["cassette_length_bp"] == result["cassette_length"]
    assert manifest["complete_plasmid_length_bp"] == result["plasmid_length"]


def test_user_uploaded_genbank_backbone_uses_leaf_filename_and_preserves_features(
    tmp_path: Path,
) -> None:
    result = _user_component_result(
        case_id="case_10_complex_uploaded_genbank",
        project_name="客户上传骨架项目",
        uploaded_backbone=True,
    )
    inspected = _independently_extract_and_validate(
        result["company_review_package"]["data"], tmp_path
    )
    components = {item["type"]: item for item in inspected["manifest"]["components"]}

    assert components["backbone"]["source_kind"] == "user_uploaded"
    assert components["backbone"]["source_reference"] == "customer_backbone.gb"
    assert len(inspected["genbank_record"].features) == len(result["exports"]["metadata"]["features"])
    assert "customer_backbone.gb" in inspected["summary"]
    assert "骨架" in inspected["summary"]


def test_cross_origin_compound_location_survives_package_and_csv_remains_unambiguous(
    tmp_path: Path,
) -> None:
    result = build_production_result(case_by_id("case_09_cross_origin_feature"))
    package = build_company_review_package(result)
    inspected = _independently_extract_and_validate(package["data"], tmp_path)
    compound = next(
        feature
        for feature in inspected["genbank_record"].features
        if (feature.qualifiers.get("label") or [""])[0] == "CROSS_ORIGIN_09"
    )
    row = next(
        item
        for item in inspected["coordinate_rows"]
        if item["component_name"] == "CROSS_ORIGIN_09"
    )

    assert len(compound.location.parts) == 2
    assert int(row["length_bp"]) == sum(len(part) for part in compound.location.parts)
    assert "CompoundLocation join" in row["notes"]


@pytest.mark.parametrize(
    ("project_name", "expected_root"),
    [
        ("../", "BioDesign_Project"),
        (r"C:\outside\review", "C_outside_review"),
        ('<>:"/\\|?*', "BioDesign_Project"),
        ("中文 项目", "中文 项目"),
    ],
)
def test_project_directory_name_is_safe_and_zip_has_no_escape_paths(
    project_name: str, expected_root: str
) -> None:
    result = mvp_app.generate_complete_vector(
        mvp_app.load_real_case(),
        project_name=project_name,
    )
    package = result["company_review_package"]

    assert safe_project_directory_name(project_name) == expected_root
    assert package["root_directory"] == expected_root
    with zipfile.ZipFile(BytesIO(package["data"]), "r") as archive:
        for name in archive.namelist():
            path = PurePosixPath(name)
            assert path.parts[0] == expected_root
            assert ".." not in path.parts
            assert not path.is_absolute()


def test_missing_result_stale_result_and_missing_exports_are_blocked() -> None:
    with pytest.raises(MvpCompanyReviewPackageError, match="尚未生成"):
        build_company_review_package({})

    result = mvp_app.generate_complete_vector(mvp_app.load_real_case())
    stale = deepcopy(result)
    stale["runtime"]["complete_plasmid_constructs"][0]["construct_status"] = "stale"
    with pytest.raises(MvpCompanyReviewPackageError, match="已失效"):
        build_company_review_package(stale)

    missing_exports = deepcopy(result)
    missing_exports["exports"]["genbank"]["data"] = ""
    with pytest.raises(MvpCompanyReviewPackageError, match="FASTA 或 GenBank"):
        build_company_review_package(missing_exports)


def test_missing_source_information_is_recorded_explicitly(tmp_path: Path) -> None:
    result = mvp_app.generate_complete_vector(mvp_app.load_real_case())
    for record in result["input_records"].values():
        record["source_kind"] = ""
        record["source_name"] = ""
        record.pop("source_reference", None)
    package = build_company_review_package(result)
    inspected = _independently_extract_and_validate(package["data"], tmp_path)

    assert all(
        component["source_kind"] == "not_provided"
        and component["source_reference"] == "not_provided"
        for component in inspected["manifest"]["components"]
    )
