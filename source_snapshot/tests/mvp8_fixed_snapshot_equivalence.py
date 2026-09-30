"""Generate a fixed MVP8 company-package snapshot for cross-worktree comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import zipfile
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch


FIXED_PROJECT_ID = "plant-draft-mvp8-equivalence-fixed"
FIXED_PROJECT_NAME = "MVP8 Fixed Snapshot Equivalence"
FIXED_TIMESTAMP = "2026-01-01T00:00:00.000000Z"
FIXED_CASSETTE_REVISION = "rev-mvp8-fixed-cassette-v1"
FIXED_PLASMID_REVISION = "rev-mvp8-fixed-plasmid-v1"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_feature(feature: Any) -> dict[str, Any]:
    qualifiers = {
        str(key): [str(item) for item in values]
        for key, values in sorted((feature.qualifiers or {}).items())
    }
    parts = list(getattr(feature.location, "parts", None) or [feature.location])
    return {
        "type": str(feature.type),
        "strand": int(feature.location.strand or 1),
        "parts": [
            {
                "start_1_based": int(part.start) + 1,
                "end_1_based": int(part.end),
                "strand": int(part.strand or feature.location.strand or 1),
            }
            for part in parts
        ],
        "qualifiers": qualifiers,
    }


def _configure_import_root(repo_root: Path) -> None:
    resolved = str(repo_root.resolve())
    os.chdir(resolved)
    sys.path = [resolved, *[item for item in sys.path if item and Path(item).resolve() != repo_root.resolve()]]


def _fixed_id_factory():
    counts: defaultdict[str, int] = defaultdict(int)

    def _fixed_id(prefix: str) -> str:
        counts[prefix] += 1
        return f"{prefix}-mvp8-fixed-{counts[prefix]:02d}"

    return _fixed_id


def _fixed_revision_factory():
    revisions = iter((FIXED_CASSETTE_REVISION, FIXED_PLASMID_REVISION))

    def _fixed_revision(_sequence_checksum: str, _input_signature: str) -> str:
        return next(revisions)

    return _fixed_revision


def generate_snapshot(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    _configure_import_root(repo_root)

    import mvp_app
    import services.canonical_construct_runtime as canonical
    from Bio import SeqIO
    from services.mvp_company_review_package import (
        CHECKSUM_FILE_ORDER,
        PACKAGE_FILE_ORDER,
        normalized_source_provenance,
    )

    fixed_ids = _fixed_id_factory()
    fixed_revisions = _fixed_revision_factory()
    with (
        patch.object(canonical, "_new_id", side_effect=fixed_ids),
        patch.object(canonical, "_revision_id", side_effect=fixed_revisions),
        patch.object(canonical, "_timestamp", return_value=FIXED_TIMESTAMP),
    ):
        result = mvp_app.generate_complete_vector(
            mvp_app.load_real_case(),
            project_id=FIXED_PROJECT_ID,
            project_name=FIXED_PROJECT_NAME,
        )

    runtime = result["runtime"]
    construct = runtime["constructs"][0]
    transcription_unit = runtime["transcription_units"][0]
    complete_plasmid = runtime["complete_plasmid_constructs"][0]
    assert construct["construct_id"] == "construct-mvp8-fixed-01"
    assert transcription_unit["revision_id"] == FIXED_CASSETTE_REVISION
    assert complete_plasmid["current_revision"] == FIXED_PLASMID_REVISION

    output_dir.mkdir(parents=True, exist_ok=True)
    package = result["company_review_package"]
    package_bytes = package["data"]
    (output_dir / "company_review_package.zip").write_bytes(package_bytes)
    (output_dir / "existing_complete_plasmid.fasta").write_bytes(
        result["exports"]["fasta"]["data"].encode("utf-8")
    )
    (output_dir / "existing_complete_plasmid.gb").write_bytes(
        result["exports"]["genbank"]["data"].encode("utf-8")
    )

    with zipfile.ZipFile(output_dir / "company_review_package.zip", "r") as archive:
        archive_names = archive.namelist()
        root_name = archive_names[0].split("/", 1)[0]
        relative_names = [name.split("/", 1)[1] for name in archive_names]
        files = {
            relative_name: archive.read(f"{root_name}/{relative_name}")
            for relative_name in relative_names
        }

    complete_fasta = next(SeqIO.parse(StringIO(files["complete_plasmid.fasta"].decode("utf-8")), "fasta"))
    cassette_fasta = next(SeqIO.parse(StringIO(files["expression_cassette.fasta"].decode("utf-8")), "fasta"))
    genbank = next(SeqIO.parse(StringIO(files["complete_plasmid.gb"].decode("utf-8")), "genbank"))
    coordinate_rows = list(csv.DictReader(StringIO(files["component_coordinates.csv"].decode("utf-8"))))
    validation_json = json.loads(files["validation_summary.json"].decode("utf-8"))
    construct_json = json.loads(files["construct_manifest.json"].decode("utf-8"))
    checksums_text = files["checksums.sha256"].decode("utf-8")

    expected_checksum_lines = [
        f"{_sha256(files[name])}  {name}"
        for name in CHECKSUM_FILE_ORDER
    ]
    assert checksums_text.splitlines() == expected_checksum_lines
    assert relative_names == list(PACKAGE_FILE_ORDER)

    manifest = {
        "fixture": {
            "project_id": result["project_id"],
            "project_name": result["project_name"],
            "construct_id": construct["construct_id"],
            "cassette_revision_id": transcription_unit["revision_id"],
            "plasmid_revision_id": complete_plasmid["current_revision"],
            "promoter": result["source_inputs"]["promoter"],
            "cds": result["source_inputs"]["cds"],
            "terminator": result["source_inputs"]["terminator"],
            "backbone": result["source_inputs"]["backbone"],
            "insertion_settings": result["insertion_settings"],
            "source_provenance": {
                role: normalized_source_provenance(result["input_records"][role])
                for role in ("promoter", "cds", "terminator", "backbone")
            },
            "existing_fasta_sha256": _sha256(result["exports"]["fasta"]["data"].encode("utf-8")),
            "existing_genbank_sha256": _sha256(result["exports"]["genbank"]["data"].encode("utf-8")),
        },
        "zip": {
            "sha256": _sha256(package_bytes),
            "root_name": root_name,
            "file_order": relative_names,
            "file_sha256": {name: _sha256(files[name]) for name in relative_names},
        },
        "checksums_sha256_text": checksums_text,
        "complete_fasta_dna": str(complete_fasta.seq).upper(),
        "cassette_fasta_dna": str(cassette_fasta.seq).upper(),
        "genbank_dna": str(genbank.seq).upper(),
        "genbank_features": [_normalize_feature(feature) for feature in genbank.features],
        "coordinate_rows": coordinate_rows,
        "validation_json": validation_json,
        "construct_json": construct_json,
    }
    (output_dir / "snapshot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def compare_outputs(left_dir: Path, right_dir: Path) -> dict[str, Any]:
    left_zip = (left_dir / "company_review_package.zip").read_bytes()
    right_zip = (right_dir / "company_review_package.zip").read_bytes()
    left_manifest = json.loads((left_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    right_manifest = json.loads((right_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    return {
        "zip_bytes_equal": left_zip == right_zip,
        "zip_sha256_equal": _sha256(left_zip) == _sha256(right_zip),
        "manifest_equal": left_manifest == right_manifest,
        "existing_fasta_bytes_equal": (
            left_dir / "existing_complete_plasmid.fasta"
        ).read_bytes() == (right_dir / "existing_complete_plasmid.fasta").read_bytes(),
        "existing_genbank_bytes_equal": (
            left_dir / "existing_complete_plasmid.gb"
        ).read_bytes() == (right_dir / "existing_complete_plasmid.gb").read_bytes(),
        "zip_sha256": _sha256(left_zip),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compare-left", type=Path)
    args = parser.parse_args()
    manifest = generate_snapshot(args.repo_root, args.output_dir)
    print(json.dumps({"generated_zip_sha256": manifest["zip"]["sha256"]}, sort_keys=True))
    if args.compare_left:
        comparison = compare_outputs(args.compare_left, args.output_dir)
        print(json.dumps(comparison, sort_keys=True))
        if not all(
            comparison[key]
            for key in (
                "zip_bytes_equal",
                "zip_sha256_equal",
                "manifest_equal",
                "existing_fasta_bytes_equal",
                "existing_genbank_bytes_equal",
            )
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
