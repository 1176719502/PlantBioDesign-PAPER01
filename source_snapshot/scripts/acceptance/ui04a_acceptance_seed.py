"""Create and safely migrate the UI-04A completed-project acceptance records.

The complete record is regenerated from the approved HSA/ALB source inputs and
the formal Step 3 cassette service.  It never infers editor widgets from a
saved ``mvp_vector_result``.  Migration accepts an existing record only when
the formally regenerated components and canonical sequence are identical to
the record being replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.formal_expression_cassette import (
    assess_expression_cassette,
    generate_expression_cassette,
)
from services.formal_project_definition_lifecycle import (
    construct_review_basis,
    normalize_project_definition,
)
from services.formal_single_gene_runtime import (
    construct_input_signature,
    generate_admitted_complete_vector,
)
from services.mvp_single_gene_persistence import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION,
    RECORD_KIND_FORMAL_EDITOR_COMPLETED,
    RECORD_KIND_RESULT_ONLY_COMPLETED,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.rice_hsa_ncbi_mvp10_case import build_rice_hsa_real_case


COMPLETE_PROJECT_ID = "ui04a-complete-project"
COMPLETE_PROJECT_NAME = "UI-04A Complete Project"
HISTORICAL_PROJECT_ID = "ui04a-historical-preview"
HISTORICAL_PROJECT_NAME = "UI-04A Historical Preview"


def _project_definition(project_name: str) -> dict[str, str]:
    return normalize_project_definition(
        {
            "project_name": project_name,
            "plant_host": "Rice (O. sativa)",
            "material": "plant expression vector design record",
            # Use the current Step 1 field vocabulary. An arbitrary legacy
            # value would correctly trigger the review lifecycle on reopen.
            "application_mode": "稳定遗传转化",
            "transient_expression_system": "尚未确定",
            "tissue_specificity_requirement": "尚未确定",
            "inducibility_requirement": "尚未确定",
        }
    )


def _step3_components(result: dict[str, Any], definition: dict[str, str]) -> dict[str, Any]:
    """Call the formal Step 3 service from preserved source records."""
    records = dict(result["input_records"])
    cds_input = dict(result["cds_input"])
    declared = []
    for role, biological_role in (
        ("promoter", "promoter"),
        ("cds", "cds"),
        ("terminator", "three_prime_regulatory_region"),
    ):
        record = dict(records[role])
        declared.append(
            {
                "biological_role": biological_role,
                "display_name": str(record["display_name"]),
                "sequence": str(record["normalized_sequence"]),
                "source_kind": str(record.get("source_kind") or "user_recorded"),
                "source_reference": str(record.get("source_reference") or record.get("source_name") or ""),
                "source_file": str(record.get("source_name") or ""),
                "user_edited": False,
            }
        )
    assessment = assess_expression_cassette(
        declared,
        cds_sequence=str(cds_input["normalized_cds"]),
        cds_signature=str(cds_input["normalized_cds_sha256"]),
        project_definition=definition,
        order_confirmed=True,
    )
    if assessment["blocking"]:
        raise RuntimeError("UI-04A source inputs cannot form a formal Step 3 cassette.")
    generated = generate_expression_cassette(assessment, project_id=str(result["project_id"]))
    components = list(generated["components"])
    reconstructed = "".join(
        str(component["sequence"]).upper()
        if str(component.get("strand") or "forward") == "forward"
        else _reverse_complement(str(component["sequence"]))
        for component in components
    )
    cassette = dict(generated["cassette"])
    if (
        reconstructed != str(cassette["sequence"]).upper()
        or int(generated["total_length"]) != len(reconstructed)
        or [int(component["order"]) for component in components] != list(range(1, len(components) + 1))
    ):
        raise RuntimeError("Generated UI-04A Step 3 components are not internally consistent.")
    return generated


def _reverse_complement(sequence: str) -> str:
    return str(sequence).upper().translate(str.maketrans("ATCG", "TAGC"))[::-1]


def build_formal_editor_completed(
    *, project_id: str = COMPLETE_PROJECT_ID, project_name: str = COMPLETE_PROJECT_NAME
) -> dict[str, Any]:
    """Build one formal-editor completed result through the formal services."""
    base = build_rice_hsa_real_case()
    base["project_id"] = project_id
    base["project_name"] = project_name
    definition = _project_definition(project_name)
    formal_cassette = _step3_components(base, definition)
    records = dict(base["input_records"])
    settings = dict(base["insertion_settings"])
    formal_signature = str(formal_cassette["input_signature"])
    result = generate_admitted_complete_vector(
        cds_input=dict(base["cds_input"]),
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=project_name,
        input_signature=construct_input_signature(
            records, settings, cassette_signature=formal_signature
        ),
        cassette_runtime=dict(formal_cassette["runtime"]),
        cassette_signature=formal_signature,
        workflow_id=str(settings.get("workflow_id") or ""),
    )
    canonical_cassette = active_construct_snapshot(result["runtime"])
    if str(canonical_cassette["sequence"]).upper() != str(formal_cassette["cassette"]["sequence"]).upper():
        raise RuntimeError("Formal Step 3 output did not match the completed canonical cassette.")
    persisted_cassette = {
        key: value
        for key, value in formal_cassette.items()
        if key not in {"runtime", "cassette"}
    }
    formal_state = {
        "formal_project_definition": definition,
        "formal_project_name": definition["project_name"],
        "formal_project_host": definition["plant_host"],
        "formal_project_material": definition["material"],
        "formal_expression_target": "HSA/ALB expression design record",
        "formal_cds_input": dict(base["cds_input"]),
        "formal_expression_cassette": formal_cassette,
        "formal_cassette_result": {
            "runtime": dict(formal_cassette["runtime"]),
            "cassette_input_signature": formal_signature,
            "input_signature": formal_signature,
        },
        "formal_cassette_input_signature": formal_signature,
        "formal_step3_order_confirmation_recorded": True,
        "formal_backbone_record": dict(records["backbone"]),
        "formal_insertion_settings": settings,
        "formal_step4_strategy_confirmed": True,
        "formal_step5_strategy_confirmed": bool(settings.get("construction_strategy_confirmed")),
        "formal_construct_review_status": "current",
        "formal_cds_source_review_status": "current",
        "mvp_current_input_signature": str(result["input_signature"]),
        "mvp_inputs_stale": False,
    }
    result["formal_expression_cassette"] = persisted_cassette
    review_basis = construct_review_basis(definition)
    result["formal_project_context"] = {
        "record_kind": RECORD_KIND_FORMAL_EDITOR_COMPLETED,
        "formal_editor_state_contract_version": FORMAL_EDITOR_STATE_CONTRACT_VERSION,
        "host_key": definition["plant_host"],
        "expression_target": "HSA/ALB expression design record",
        "project_definition": definition,
        "construct_review_basis": review_basis,
        "construct_review_status": "current",
        "cds_source_review_basis": dict(base["cds_input"].get("source_review_basis") or {}),
        "cds_source_review_status": "current",
        "current_step": 6,
        "formal_state": formal_state,
    }
    return result


def build_result_only_completed(
    *, project_id: str = HISTORICAL_PROJECT_ID, project_name: str = HISTORICAL_PROJECT_NAME
) -> dict[str, Any]:
    """Build an intentional result-only completed record for preview coverage."""
    result = build_formal_editor_completed(
        project_id=project_id,
        project_name=project_name,
    )
    result["formal_project_context"] = {
        "record_kind": RECORD_KIND_RESULT_ONLY_COMPLETED,
        "host_key": "",
        "expression_target": "",
        "current_step": 6,
    }
    result.pop("formal_expression_cassette", None)
    return result


def _assert_migration_equivalence(before: dict[str, Any], rebuilt: dict[str, Any]) -> None:
    before_cassette = active_construct_snapshot(before["runtime"])
    rebuilt_cassette = active_construct_snapshot(rebuilt["runtime"])
    before_plasmid = active_complete_plasmid_snapshot(before["runtime"])
    rebuilt_plasmid = active_complete_plasmid_snapshot(rebuilt["runtime"])
    components = list(rebuilt["formal_expression_cassette"]["components"])
    rebuilt_component_sequence = "".join(
        str(component["sequence"]).upper()
        if str(component.get("strand") or "forward") == "forward"
        else _reverse_complement(str(component["sequence"]))
        for component in components
    )
    stable_components = [
        (int(component["order"]), int(component["start"]), int(component["end"]), str(component["biological_role"]))
        for component in components
    ]
    if (
        str(before_cassette["sequence"]).upper() != str(rebuilt_cassette["sequence"]).upper()
        or str(before_cassette["sequence"]).upper() != rebuilt_component_sequence
        or str(before_plasmid["sequence"]).upper() != str(rebuilt_plasmid["sequence"]).upper()
        or hashlib.sha256(str(before_plasmid["sequence"]).upper().encode("ascii")).hexdigest()
        != hashlib.sha256(str(rebuilt_plasmid["sequence"]).upper().encode("ascii")).hexdigest()
        or [item[0] for item in stable_components] != list(range(1, len(stable_components) + 1))
        or any(end < start for _order, start, end, _role in stable_components)
    ):
        raise RuntimeError("UI-04A migration canonical or Step 3 component verification failed.")


def seed_ui04a_acceptance_environment(storage_dir: str | Path) -> None:
    """Create both UI-04A records in a fresh persistence directory."""
    repository = PlantProjectDraftRepository(storage_dir)
    save_mvp_single_gene_design(build_result_only_completed(), repository=repository)
    save_mvp_single_gene_design(build_formal_editor_completed(), repository=repository)


def migrate_ui04a_complete_project(storage_dir: str | Path) -> Path:
    """Back up, verify, then atomically replace only the UI-04A complete record."""
    repository = PlantProjectDraftRepository(storage_dir)
    target = repository._path_for(COMPLETE_PROJECT_ID)
    original_bytes = target.read_bytes()
    backup = target.with_suffix(".json.ui04a-pre-migration.bak")
    backup_index = 1
    while backup.exists():
        backup = target.with_suffix(f".json.ui04a-pre-migration.bak.{backup_index}")
        backup_index += 1
    with backup.open("xb") as handle:
        handle.write(original_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        previous = open_mvp_single_gene_design(COMPLETE_PROJECT_ID, repository=repository)
        rebuilt = build_formal_editor_completed(
            project_id=COMPLETE_PROJECT_ID,
            project_name=str(previous["project_name"]),
        )
        _assert_migration_equivalence(previous, rebuilt)
        with tempfile.TemporaryDirectory(prefix="ui04a-migration-") as staging_dir:
            staging = PlantProjectDraftRepository(Path(staging_dir) / "records")
            save_mvp_single_gene_design(rebuilt, repository=staging)
            staged = staging._path_for(COMPLETE_PROJECT_ID).read_bytes()
        temp_target = target.with_name(f".{target.stem}.ui04a-migration.tmp")
        with temp_target.open("xb") as handle:
            handle.write(staged)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_target, target)
    except Exception:
        temp_target = target.with_name(f".{target.stem}.ui04a-migration.tmp")
        temp_target.unlink(missing_ok=True)
        if target.read_bytes() != original_bytes:
            raise RuntimeError("UI-04A migration failed after modifying the original record.")
        raise
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-dir", required=True, type=Path)
    parser.add_argument("--migrate-complete-only", action="store_true")
    args = parser.parse_args()
    if args.migrate_complete_only:
        print(migrate_ui04a_complete_project(args.storage_dir))
    else:
        seed_ui04a_acceptance_environment(args.storage_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
