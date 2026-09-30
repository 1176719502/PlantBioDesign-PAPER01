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

from services.multi_tu_professional_review_package import (
    CHECKSUM_FILES,
    COMPONENT_INVENTORY_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    PACKAGE_FILES,
    PROVENANCE_REVIEW_COLUMNS,
    REVIEW_BLOCKED,
    REVIEW_NEEDS_PROVENANCE,
    MultiTuProfessionalReviewPackageError,
    assess_multi_tu_professional_review_package,
    build_multi_tu_professional_review_package,
    validate_multi_tu_professional_review_package_bytes,
)
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_gate2_formal_multi_tu_workflow import _generate_three_tu


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _archive_files(package: dict) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(package["data"]), "r") as archive:
        assert archive.namelist() == list(PACKAGE_FILES)
        return {name: archive.read(name) for name in archive.namelist()}


def test_generic_three_tu_review_package_contains_canonical_exports_and_review_records() -> None:
    result = _generate_three_tu()
    package = build_multi_tu_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    files = _archive_files(package)

    assert package["review_status"] == REVIEW_NEEDS_PROVENANCE
    assert package["wet_lab_readiness"] == "not_assessed"
    assert package["files"] == list(PACKAGE_FILES)
    assert len(package["files"]) == 12
    assert package["verification"]["verified"] is True
    assert validate_multi_tu_professional_review_package_bytes(package["data"])["verified"] is True

    readme = files["README.md"].decode("utf-8")
    for forbidden in (
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
    ):
        assert forbidden not in readme.lower()
    assert "documentation-only design and review record" in readme

    complete_fasta = next(SeqIO.parse(StringIO(files["complete_plasmid.fasta"].decode("utf-8")), "fasta"))
    complete_genbank = next(SeqIO.parse(StringIO(files["complete_plasmid.gb"].decode("utf-8")), "genbank"))
    multi_tu_fasta = next(SeqIO.parse(StringIO(files["multi_tu_region.fasta"].decode("utf-8")), "fasta"))
    assert str(complete_fasta.seq).upper() == str(complete_genbank.seq).upper() == result["complete_plasmid"]["dna"]
    assert str(multi_tu_fasta.seq).upper() == result["combined_construct"]["dna"]

    unit_fastas = json.loads(files["unit_fastas.json"].decode("utf-8"))
    assert unit_fastas["unit_count"] == 3
    for unit in result["expression_units"]:
        unit_payload = unit_fastas["records"][unit["unit_id"]]
        unit_record = next(SeqIO.parse(StringIO(unit_payload["fasta"]), "fasta"))
        assert str(unit_record.seq).upper() == unit["dna"]
        assert unit_payload["length_bp"] == unit["length"]
        assert unit_payload["sequence_sha256"] == unit["sequence_sha256"]

    inventory = list(csv.DictReader(StringIO(files["component_inventory.csv"].decode("utf-8"))))
    provenance = list(csv.DictReader(StringIO(files["provenance_review.csv"].decode("utf-8"))))
    manual = list(csv.DictReader(StringIO(files["manual_review_items.csv"].decode("utf-8"))))
    assert tuple(inventory[0]) == COMPONENT_INVENTORY_COLUMNS
    assert tuple(provenance[0]) == PROVENANCE_REVIEW_COLUMNS
    assert tuple(manual[0]) == MANUAL_REVIEW_COLUMNS
    assert {row["unit_id"] for row in inventory if row["unit_id"]} == {
        "unit-alb-target",
        "unit-plant-selection",
        "unit-reporter",
    }
    reporter_rows = [row for row in inventory if row["unit_id"] == "unit-reporter"]
    assert reporter_rows
    assert {row["strand"] for row in reporter_rows} == {"-1"}
    assert any(row["biological_role"] == "3_prime_regulatory_region" for row in inventory)
    assert len(provenance) >= 10
    assert len(manual) == package["manual_review_count"]

    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert manifest["package_file_order"] == list(PACKAGE_FILES)
    assert manifest["unit_count"] == 3
    assert manifest["wet_lab_readiness"] == "not_assessed"
    assert manifest["complete_plasmid"]["sequence_sha256"] == result["complete_plasmid"]["sequence_sha256"]
    assert manifest["multi_tu_region"]["sequence_sha256"] == result["combined_construct"]["sequence_sha256"]
    for entry in manifest["payload_files"]:
        assert entry["size_bytes"] == len(files[entry["name"]])
        assert entry["sha256"] == _sha256(files[entry["name"]])
    checksum_rows = [line.split("  ", 1) for line in files["checksums.sha256"].decode("utf-8").splitlines()]
    assert [name for _checksum, name in checksum_rows] == list(CHECKSUM_FILES)
    assert all(checksum == _sha256(files[name]) for checksum, name in checksum_rows)


def test_generic_three_tu_review_package_is_deterministic_after_cold_reopen(tmp_path: Path) -> None:
    result = _generate_three_tu()
    first = build_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    second = build_multi_tu_professional_review_package(result, current_input_signature=result["input_signature"])
    assert second["data"] == first["data"]
    assert second["manifest"] == first["manifest"]
    assert second["file_checksums"] == first["file_checksums"]

    repository = PlantProjectDraftRepository(tmp_path / "multi_tu_drafts")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    cold = build_multi_tu_professional_review_package(
        reopened,
        current_input_signature=reopened["input_signature"],
    )
    assert cold["data"] == first["data"]
    assert cold["manifest"] == first["manifest"]
    assert cold["file_checksums"] == first["file_checksums"]


def test_generic_multi_tu_review_blocks_stale_signature_and_export_mismatch() -> None:
    result = _generate_three_tu()
    stale = assess_multi_tu_professional_review_package(result, current_input_signature="stale")
    assert stale["review_status"] == REVIEW_BLOCKED
    assert stale["blocking_count"] == 1
    assert "signature" in stale["blocking_reasons"][0]

    tampered = deepcopy(result)
    fasta = tampered["exports"]["complete_plasmid_fasta"]["data"]
    header, sequence = fasta.split("\n", 1)
    replacement = "A" if sequence[0] != "A" else "T"
    tampered["exports"]["complete_plasmid_fasta"]["data"] = header + "\n" + replacement + sequence[1:]
    assessment = assess_multi_tu_professional_review_package(
        tampered,
        current_input_signature=tampered["input_signature"],
    )
    assert assessment["review_status"] == REVIEW_BLOCKED
    assert "differ" in assessment["blocking_reasons"][0]
    with pytest.raises(MultiTuProfessionalReviewPackageError, match="differ"):
        build_multi_tu_professional_review_package(
            tampered,
            current_input_signature=tampered["input_signature"],
        )


def test_generic_multi_tu_review_validation_blocks_tampered_unit_fastas_json() -> None:
    result = _generate_three_tu()
    package = build_multi_tu_professional_review_package(
        result,
        current_input_signature=result["input_signature"],
    )
    files = _archive_files(package)
    unit_fastas = json.loads(files["unit_fastas.json"].decode("utf-8"))
    first_unit = next(iter(unit_fastas["records"].values()))
    first_unit["length_bp"] += 1
    files["unit_fastas.json"] = json.dumps(
        unit_fastas,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    manifest["payload_files"] = [
        {
            **entry,
            "size_bytes": len(files[entry["name"]]),
            "sha256": _sha256(files[entry["name"]]),
        }
        for entry in manifest["payload_files"]
    ]
    files["manifest.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    files["checksums.sha256"] = "".join(
        f"{_sha256(files[name])}  {name}\n" for name in CHECKSUM_FILES
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PACKAGE_FILES:
            archive.writestr(name, files[name])
    with pytest.raises(MultiTuProfessionalReviewPackageError, match="length"):
        validate_multi_tu_professional_review_package_bytes(output.getvalue())


def test_multi_tu_review_package_is_compatibility_only_not_formal_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app.py").read_text(encoding="utf-8")
    result_page = source.split("def _render_results_export_content", 1)[1].split(
        "def _plant_library_records", 1
    )[0]
    manifest = json.loads(
        (root / "packaging" / "resource_manifest.json").read_text(encoding="utf-8")
    )

    assert "build_multi_tu_professional_review_package" not in result_page
    assert "专业审查包 ZIP" not in result_page
    assert (
        "services/multi_tu_professional_review_package.py"
        not in manifest["runtime_python_modules"]
    )
