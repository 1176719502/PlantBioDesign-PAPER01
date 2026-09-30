from __future__ import annotations

import csv
import html
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

import mvp_app
from services.betalain_multi_tu_professional_review_package import (
    PACKAGE_FILES,
    BetalainMultiTuProfessionalReviewPackageError,
    REPEATED_REGULATORY_WARNING,
    WET_LAB_READINESS,
    assess_betalain_multi_tu_professional_review_package,
    build_betalain_multi_tu_professional_review_package,
    validate_betalain_multi_tu_professional_review_package_bytes,
)
from services.betalain_pbi121_canonical_construct import generate_betalain_pbi121_canonical_construct
from services.betalain_three_enzyme_gate3_case import PROJECT_NAME
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.pbi121_replacement_strategy import new_strategy, save_strategy, source_audit, update_strategy
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
EXPECTED_PACKAGE_SHA256 = "c1782eccf81a9b79fde155758bab269e8b1ed679a0b4b4d62df585e389cc9bbf"
EXPECTED_COMPLETE_SHA256 = "cdeb4ea329322b942472b38c44fcad9c11216cd1e3fd4b9540e28a37826e2dc7"


def _ready_strategy(root: Path) -> None:
    audit = source_audit()
    lb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "left_border")
    rb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "right_border")
    save_strategy(
        update_strategy(
            new_strategy(),
            confirmed_left_border=lb,
            confirmed_right_border=rb,
            t_dna_direction="RB_to_LB",
            replacement_start=4974,
            replacement_end=7979,
            insertion_orientation="forward",
            insertion_orientation_relative_to_t_dna="forward",
            normalized_canonical_orientation="forward",
            reviewed_key_features={"gus": True, "nptii": True},
        ),
        runtime_root=root,
    )


def _generate_result(tmp_path: Path, *, project_id: str = "betalain-multi-tu-review") -> dict:
    strategy_root = tmp_path / "strategy"
    _ready_strategy(strategy_root)
    return generate_betalain_pbi121_canonical_construct(
        project_id=project_id,
        project_name=PROJECT_NAME,
        repeated_regulatory_confirmed=True,
        strategy_root=strategy_root,
    )


def _unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        assert archive.namelist() == list(PACKAGE_FILES)
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.fixture
def fake_st(monkeypatch: pytest.MonkeyPatch) -> FakeStreamlit:
    fake = FakeStreamlit()
    monkeypatch.setattr(mvp_app, "st", fake)
    return fake


def test_package_builds_exact_13_files_and_keeps_lengths_sha_and_source_links(tmp_path: Path) -> None:
    result = _generate_result(tmp_path)
    package = build_betalain_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    files = _unzip(package["data"])

    assert package["file_name"] == f"{PROJECT_NAME}_专业交付审查包.zip"
    assert package["sha256"] == EXPECTED_PACKAGE_SHA256
    assert package["files"] == list(PACKAGE_FILES)
    assert package["verification"]["verified"] is True
    assert validate_betalain_multi_tu_professional_review_package_bytes(package["data"])["verified"] is True

    html_text = files[PACKAGE_FILES[0]].decode("utf-8")
    assert "当前结果用于植物表达载体的计算设计、计算校验、项目保存和文件导出；尚未经过湿实验验证，不代表实际表达成功或湿实验就绪。" in html_text
    for forbidden in ("已实验验证", "保证表达成功", "可直接转化", "无需进一步审查"):
        assert forbidden not in html_text
    assert not re.search(r"[A-Za-z]:\\|/Universal_BioDesign|/tests/|\.py|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", html_text)

    complete_gb = next(SeqIO.parse(StringIO(files[PACKAGE_FILES[1]].decode("utf-8")), "genbank"))
    complete_fasta = next(SeqIO.parse(StringIO(files[PACKAGE_FILES[2]].decode("utf-8")), "fasta"))
    multi_tu_fasta = next(SeqIO.parse(StringIO(files[PACKAGE_FILES[3]].decode("utf-8")), "fasta"))
    tu_fastas = {
        "TU1": next(SeqIO.parse(StringIO(files[PACKAGE_FILES[4]].decode("utf-8")), "fasta")),
        "TU2": next(SeqIO.parse(StringIO(files[PACKAGE_FILES[5]].decode("utf-8")), "fasta")),
        "TU3": next(SeqIO.parse(StringIO(files[PACKAGE_FILES[6]].decode("utf-8")), "fasta")),
    }

    assert len(complete_gb.seq) == 18841
    assert result["complete_plasmid"]["sequence_sha256"] == EXPECTED_COMPLETE_SHA256
    assert len(complete_fasta.seq) == 18841
    assert len(multi_tu_fasta.seq) == 7089
    assert [len(record.seq) for record in tu_fastas.values()] == [2582, 1916, 2591]
    assert str(complete_gb.seq).upper() == str(complete_fasta.seq).upper() == result["complete_plasmid"]["dna"]
    assert str(multi_tu_fasta.seq).upper() == result["combined_construct"]["dna"]
    assert [str(tu_fastas[unit_id].seq).upper() for unit_id in ("TU1", "TU2", "TU3")] == [unit["dna"] for unit in result["expression_units"]]
    assert complete_gb.annotations.get("topology") == "circular"

    labels = [(feature.qualifiers.get("label") or [""])[0] for feature in complete_gb.features]
    assert "gusA" not in labels
    assert "GUS" not in labels
    assert {"TU1: CYP76AD1", "TU2: DODA1", "TU3: cDOPA5GT", "CaMV 35S promoter", "NOS 3' regulatory region", "nptII", "T-DNA left border", "T-DNA right border"} <= set(labels)

    inventory = list(csv.DictReader(StringIO(files[PACKAGE_FILES[7]].decode("utf-8"))))
    review_rows = list(csv.DictReader(StringIO(files[PACKAGE_FILES[10]].decode("utf-8"))))
    manifest = json.loads(files[PACKAGE_FILES[11]].decode("utf-8"))
    checksums = files[PACKAGE_FILES[12]].decode("utf-8").splitlines()

    assert len(inventory) == 15
    assert len(review_rows) == 8
    assert manifest["file_count"] == 13
    assert manifest["package_file_order"] == list(PACKAGE_FILES)
    assert manifest["wet_lab_readiness"] == WET_LAB_READINESS
    assert manifest["summary"]["file_count"] == 13
    assert manifest["summary"]["manual_review_count"] == 8
    assert manifest["summary"]["wet_lab_readiness"] == WET_LAB_READINESS
    assert manifest["blockers"] == []
    assert REPEATED_REGULATORY_WARNING in manifest["warnings"]
    assert REPEATED_REGULATORY_WARNING in html.unescape(html_text)
    assert REPEATED_REGULATORY_WARNING in files[PACKAGE_FILES[9]].decode("utf-8")
    assert REPEATED_REGULATORY_WARNING in files[PACKAGE_FILES[10]].decode("utf-8")
    assert len(checksums) == 12
    assert [line.split("  ", 1)[1] for line in checksums] == list(PACKAGE_FILES[:-1])
    for line in checksums:
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256(files[name]).hexdigest()

    by_item = {(row["tu_id"], row["biological_role"]): row for row in inventory}
    assert by_item[("", "complete_design_record")]["exact_length_bp"] == "18841"
    assert by_item[("", "multi_transcription_unit_region")]["exact_length_bp"] == "7089"
    assert by_item[("TU1", "promoter")]["source_accession"] == "AF485783.1"
    assert by_item[("TU1", "promoter")]["source_record_sha256"] == "7301abcf3146e14cd4826a8c8b7f44d65a0b03b0f642695f6d8277ea56d733d7"
    assert by_item[("TU1", "cds")]["source_accession"] == "HQ656023.1"
    assert by_item[("TU1", "cds")]["source_record_sha256"] == "b541b6b132fba98ba7b9ee6ed56f37aafd1565c44e138a87116b7198efe16590"
    assert by_item[("TU2", "cds")]["source_accession"] == "HQ656027.1"
    assert by_item[("TU3", "cds")]["source_accession"] == "AB182643.1"
    assert by_item[("TU1", "3_prime_regulatory_region")]["source_accession"] == "AF485783.1"
    assert by_item[("TU2", "3_prime_regulatory_region")]["source_accession"] == "AF485783.1"
    assert by_item[("TU3", "3_prime_regulatory_region")]["source_accession"] == "AF485783.1"
    assert by_item[("", "complete_design_record")]["final_end_1based"] == "18841"
    assert by_item[("", "multi_transcription_unit_region")]["final_start_1based"] == "4974"
    assert by_item[("", "multi_transcription_unit_region")]["final_end_1based"] == "12062"


def test_package_is_deterministic_across_repeat_and_cold_reopen(tmp_path: Path) -> None:
    result = _generate_result(tmp_path, project_id="betalain-multi-tu-deterministic")
    first = build_betalain_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    second = build_betalain_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    assert first["data"] == second["data"]
    assert first["sha256"] == second["sha256"]
    assert first["sha256"] == EXPECTED_PACKAGE_SHA256
    assert first["file_name"] == second["file_name"]
    assert first["manifest"] == second["manifest"]

    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    third = build_betalain_multi_tu_professional_review_package(reopened, current_input_signature=reopened["input_signature"])
    assert third["data"] == first["data"]
    assert third["sha256"] == first["sha256"]

    cold_zip = tmp_path / "cold_start_package.zip"
    command = (
        "from pathlib import Path; import json; "
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        "from services.betalain_multi_tu_professional_review_package import build_betalain_multi_tu_professional_review_package; "
        f"result = open_mvp_multi_tu_design({saved.project_id!r}); "
        f"package = build_betalain_multi_tu_professional_review_package(result, current_input_signature=result['input_signature']); "
        f"Path({str(cold_zip)!r}).write_bytes(package['data']); "
        "print(json.dumps({'sha256': package['sha256'], 'file_name': package['file_name']}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(repository.storage_dir)},
        check=True,
        capture_output=True,
        text=True,
    )
    cold_summary = json.loads(completed.stdout.strip())
    assert cold_summary["sha256"] == first["sha256"]
    assert cold_summary["file_name"] == first["file_name"]
    assert cold_zip.read_bytes() == first["data"]


def test_blockers_prevent_build_and_warning_items_remain_visible(tmp_path: Path) -> None:
    result = _generate_result(tmp_path, project_id="betalain-multi-tu-blocked")
    tampered = deepcopy(result)
    tampered["complete_plasmid"]["sequence_sha256"] = "0" * 64

    assessment = assess_betalain_multi_tu_professional_review_package(
        tampered,
        current_input_signature=tampered["input_signature"],
    )
    assert assessment["review_status"] == "blocked"
    assert assessment["blocker_count"] == 1
    assert assessment["warning_count"] == 0
    assert assessment["wet_lab_readiness"] == WET_LAB_READINESS
    assert assessment["blockers"]

    with pytest.raises(BetalainMultiTuProfessionalReviewPackageError):
        build_betalain_multi_tu_professional_review_package(
            tampered,
            current_input_signature=tampered["input_signature"],
        )

    package = build_betalain_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    review_csv = package["verification"]["manifest"]["files"]
    assert package["review_status"] == "ready_for_professional_review"
    assert package["warning_count"] >= 1
    assert package["manual_review_count"] == 8
    assert package["warnings"]
    assert REPEATED_REGULATORY_WARNING in package["warnings"]
    assert package["validation_report"]["wet_lab_readiness"] == WET_LAB_READINESS


def test_results_export_source_excludes_betalain_package_from_formal_surface() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    result_page = source.split("def _render_results_export_content", 1)[1].split(
        "def _plant_library_records", 1
    )[0]

    assert "assess_betalain_multi_tu_professional_review_package" not in result_page
    assert "build_betalain_multi_tu_professional_review_package" not in result_page
    assert "专业交付审查包 ZIP" not in result_page
    assert "专业审查包 ZIP" not in result_page


def test_betalain_review_package_is_not_in_formal_runtime_manifest() -> None:
    manifest = json.loads(
        (ROOT / "packaging" / "resource_manifest.json").read_text(encoding="utf-8")
    )

    assert (
        "services/betalain_multi_tu_professional_review_package.py"
        not in manifest["runtime_python_modules"]
    )
