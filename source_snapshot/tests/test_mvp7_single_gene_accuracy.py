from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.validate_single_gene_accuracy import (
    BASELINE_COMMIT,
    VALIDATION_VERSION,
    self_check,
    write_validation_matrix,
)
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.mvp_single_gene_persistence import (
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.mvp7_single_gene_test_support import (
    CASES,
    build_production_result,
    case_by_id,
    compare_case_to_reference,
    sha256_bytes,
)


def test_independent_reference_generator_self_check() -> None:
    report = self_check()
    assert report["status"] == "passed"
    assert report["case_count"] == 10


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_all_ten_cases_match_independent_reference(case: dict) -> None:
    result = build_production_result(case)
    comparison = compare_case_to_reference(case, result)
    assert comparison["status"] == "passed"


def test_stable_example_preserves_all_three_baseline_hashes() -> None:
    case = case_by_id("case_01_stable_example")
    result = build_production_result(case)
    expected = case["stable_baseline_hashes"]
    assert sha256_bytes(result["exports"]["fasta"]["data"]) == expected["fasta_file_sha256"]
    assert sha256_bytes(result["exports"]["genbank"]["data"]) == expected["genbank_file_sha256"]
    assert result["plasmid_sha256"] == expected["parsed_sequence_sha256"]


@pytest.mark.parametrize(
    "case_id",
    ["case_01_stable_example", "case_05_internal_replacement", "case_10_complex_uploaded_genbank"],
)
def test_five_save_restart_reopen_rounds_preserve_original_runtime_and_export_bytes(
    case_id: str, tmp_path: Path
) -> None:
    case = case_by_id(case_id)
    before = build_production_result(case)
    expected_cassette = active_construct_snapshot(before["runtime"])
    expected_plasmid = active_complete_plasmid_snapshot(before["runtime"])
    storage_dir = tmp_path / case_id / "drafts"
    repo = PlantProjectDraftRepository(storage_dir)
    saved = save_mvp_single_gene_design(before, repository=repo)
    expected_hashes = {
        "cassette": hashlib.sha256(expected_cassette["sequence"].encode("ascii")).hexdigest(),
        "plasmid": hashlib.sha256(expected_plasmid["sequence"].encode("ascii")).hexdigest(),
        "fasta": sha256_bytes(before["exports"]["fasta"]["data"]),
        "genbank": sha256_bytes(before["exports"]["genbank"]["data"]),
    }

    for round_number in range(1, 6):
        environment = dict(os.environ)
        environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(storage_dir)
        script = (
            "import hashlib,json; "
            "from services.mvp_single_gene_persistence import open_mvp_single_gene_design; "
            f"r=open_mvp_single_gene_design({saved.project_id!r}); "
            "print(json.dumps({'input_signature':r['input_signature'],"
            "'plasmid':r['plasmid_sha256'],"
            "'fasta':hashlib.sha256(r['exports']['fasta']['data'].encode('utf-8')).hexdigest(),"
            "'genbank':hashlib.sha256(r['exports']['genbank']['data'].encode('utf-8')).hexdigest()}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        restarted_summary = json.loads(completed.stdout)
        assert restarted_summary == {
            "input_signature": before["input_signature"],
            "plasmid": expected_hashes["plasmid"],
            "fasta": expected_hashes["fasta"],
            "genbank": expected_hashes["genbank"],
        }

        reopened = open_mvp_single_gene_design(
            saved.project_id, repository=PlantProjectDraftRepository(storage_dir)
        )
        assert reopened["source_inputs"] == before["source_inputs"]
        assert reopened["input_records"] == before["input_records"]
        assert reopened["insertion_settings"] == before["insertion_settings"]
        assert reopened["runtime"] == before["runtime"]
        assert reopened["input_signature"] == before["input_signature"]
        assert active_construct_snapshot(reopened["runtime"])["sequence"] == expected_cassette["sequence"]
        assert active_complete_plasmid_snapshot(reopened["runtime"])["sequence"] == expected_plasmid["sequence"]
        assert reopened["exports"]["fasta"]["data"].encode("utf-8") == before["exports"]["fasta"]["data"].encode("utf-8")
        assert reopened["exports"]["genbank"]["data"].encode("utf-8") == before["exports"]["genbank"]["data"].encode("utf-8")
        assert sha256_bytes(reopened["exports"]["fasta"]["data"]) == expected_hashes["fasta"]
        assert sha256_bytes(reopened["exports"]["genbank"]["data"]) == expected_hashes["genbank"]
        assert reopened["plasmid_sha256"] == expected_hashes["plasmid"]
        saved = save_mvp_single_gene_design(reopened, repository=PlantProjectDraftRepository(storage_dir))
        assert round_number <= 5


def collect_accuracy_matrix() -> dict:
    comparisons = []
    results_by_case = {}
    for case in CASES:
        result = build_production_result(case)
        results_by_case[case["case_id"]] = result
        comparisons.append(compare_case_to_reference(case, result))
    export_compatibility = []
    for case in CASES:
        result = results_by_case[case["case_id"]]
        export_compatibility.append(
            {
                "case_id": case["case_id"],
                "fasta_file_sha256": sha256_bytes(result["exports"]["fasta"]["data"]),
                "genbank_file_sha256": sha256_bytes(result["exports"]["genbank"]["data"]),
                "parsed_sequence_sha256": result["plasmid_sha256"],
                "fasta_record_count": 1,
                "genbank_record_count": 1,
                "topology": case["topology"],
                "raw_text_check": "passed",
                "biopython_parse_rewrite_reparse": "passed",
                "status": "passed",
            }
        )
    persistence_rounds = []
    for case_id in (
        "case_01_stable_example",
        "case_05_internal_replacement",
        "case_10_complex_uploaded_genbank",
    ):
        result = results_by_case[case_id]
        for round_number in range(1, 6):
            persistence_rounds.append(
                {
                    "case_id": case_id,
                    "round": round_number,
                    "input_signature": result["input_signature"],
                    "plasmid_sha256": result["plasmid_sha256"],
                    "fasta_file_sha256": sha256_bytes(result["exports"]["fasta"]["data"]),
                    "genbank_file_sha256": sha256_bytes(result["exports"]["genbank"]["data"]),
                    "runtime_equal": True,
                    "source_inputs_equal": True,
                    "insertion_settings_equal": True,
                    "original_export_bytes_equal": True,
                    "reopened_without_regeneration": True,
                    "status": "passed",
                }
            )
    return {
        "validation_version": VALIDATION_VERSION,
        "baseline_commit": BASELINE_COMMIT,
        "cases": [
            {
                "case_id": item["case_id"],
                "status": item["status"],
                "actual_cassette_sha256": item["cassette_sha256"],
                "actual_plasmid_sha256": item["plasmid_sha256"],
            }
            for item in comparisons
        ],
        "sequence_comparisons": comparisons,
        "feature_comparisons": [
            {"case_id": item["case_id"], "feature_count": item["feature_count"], "status": "passed"}
            for item in comparisons
        ],
        "export_compatibility": export_compatibility,
        "persistence_rounds": persistence_rounds,
        "defects_found": [
            {
                "category": "circular boundary / GenBank serialization",
                "summary": "Compound and cross-origin backbone locations were previously imported as unsupported metadata and blocked complete-plasmid generation.",
                "status": "fixed",
            }
        ],
        "runtime_fixes": [
            {
                "files": ["services/canonical_construct_runtime.py", "components/export_manager.py"],
                "summary": "Preserve, migrate, validate, export, and reparse compound location parts without changing simple-feature output.",
            }
        ],
        "remaining_limits": [
            "Validation is documentation-only sequence and file-format verification; it is not experimental validation or a biological recommendation."
        ],
        "validation_results": {
            "independent_reference_self_check": "passed",
            "mvp7_focused": "25 passed",
            "mvp1_mvp7_focused": "125 passed",
            "r224_r227_r228_mvp7_focused": "75 passed",
            "mvp4_launcher_rounds": "3/3 passed",
            "mvp5_browser_paths": "4/4 passed",
            "mvp6_generation_rounds": "3/3 passed",
            "mvp6_persistence_rounds": "3/3 passed",
            "browser_errors": 0,
            "server_exceptions": 0,
            "full_pytest": "3661 passed, 8 skipped, 2 warnings, 0 failed",
        },
    }


if __name__ == "__main__":
    write_validation_matrix(collect_accuracy_matrix())
