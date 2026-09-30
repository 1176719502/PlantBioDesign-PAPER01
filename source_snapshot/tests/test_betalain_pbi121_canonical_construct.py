from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

from services.betalain_pbi121_canonical_construct import (
    BetalainPbi121CanonicalConstructError,
    REPEATED_REGULATORY_WARNING,
    evaluate_betalain_pbi121_prerequisites,
    generate_betalain_pbi121_canonical_construct,
)
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.pbi121_replacement_strategy import new_strategy, save_strategy, source_audit, update_strategy
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]


def _ready_strategy(root: Path) -> None:
    audit = source_audit()
    lb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "left_border")
    rb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "right_border")
    save_strategy(
        update_strategy(
            new_strategy(), confirmed_left_border=lb, confirmed_right_border=rb,
            t_dna_direction="RB_to_LB", replacement_start=4974, replacement_end=7979,
            insertion_orientation="forward", insertion_orientation_relative_to_t_dna="forward",
            normalized_canonical_orientation="forward", reviewed_key_features={"gus": True, "nptii": True},
        ),
        runtime_root=root,
    )


def _generate(tmp_path: Path) -> dict:
    root = tmp_path / "strategy"
    _ready_strategy(root)
    return generate_betalain_pbi121_canonical_construct(
        project_id="betalain-pbi121-test", project_name="Betalain pBI121 test",
        repeated_regulatory_confirmed=True, strategy_root=root,
    )


def test_unconfirmed_repeated_regulatory_assets_block_generation(tmp_path: Path) -> None:
    root = tmp_path / "strategy"
    _ready_strategy(root)
    assessment = evaluate_betalain_pbi121_prerequisites(repeated_regulatory_confirmed=False, strategy_root=root)
    assert assessment["blockers"]
    with pytest.raises(BetalainPbi121CanonicalConstructError, match="Explicit confirmation"):
        generate_betalain_pbi121_canonical_construct(
            project_id="blocked", project_name="blocked", repeated_regulatory_confirmed=False, strategy_root=root,
        )


def test_three_tu_pbi121_replacement_is_exact_and_exportable(tmp_path: Path) -> None:
    result = _generate(tmp_path)
    combined = result["combined_construct"]
    complete = result["complete_plasmid"]
    report = result["betalain_pbi121_validation"]
    assert result["unit_order"] == ["TU1", "TU2", "TU3"]
    assert [unit["length"] for unit in result["expression_units"]] == [2582, 1916, 2591]
    assert combined["total_length"] == sum(unit["length"] for unit in result["expression_units"])
    assert complete["total_length"] == 14758 - 3006 + combined["total_length"]
    assert result["original_input"]["backbone"]["length"] == 14758
    assert result["input_lengths"]["backbone"] == 14758
    assert result["formal_project_context"]["source_backbone_length"] == 14758
    assert report["blockers"] == []
    assert report["warnings"] == [REPEATED_REGULATORY_WARNING]
    assert report["wet_lab_readiness"] == "not_assessed"
    assert report["sequence_identity_checks"]["final_length_formula_matches"] is True
    assert report["sequence_identity_checks"]["complete_sequence_sha256"] == hashlib.sha256(complete["dna"].encode("ascii")).hexdigest()
    source_record = next(SeqIO.parse(StringIO(result["original_input"]["backbone"]["raw_text"]), "genbank"))
    source_sequence = str(source_record.seq).upper()
    assert complete["dna"][:4973] == source_sequence[:4973]
    assert complete["dna"][4973 + combined["total_length"]:] == source_sequence[7979:]

    fasta = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == complete["dna"]
    labels = [(feature.qualifiers.get("label") or [""])[0] for feature in genbank.features]
    assert "gusA" not in labels
    assert "nptII" in labels
    assert "T-DNA left border" in labels and "T-DNA right border" in labels
    assert {"TU1: CYP76AD1", "TU2: DODA1", "TU3: cDOPA5GT"} <= set(labels)
    assert {"CaMV 35S promoter", "NOS 3' regulatory region", "CYP76AD1", "DODA1", "cDOPA5GT"} <= set(labels)


def test_canonical_result_preserves_three_enzyme_pathway_traceability_without_sequence_drift(
    tmp_path: Path,
) -> None:
    result = _generate(tmp_path)
    steps = result["formal_project_context"]["pathway_steps"]
    units = list(result["original_input"]["expression_units"])
    expected = [
        ("CYP76AD1", "HQ656023.1", "TU1"),
        ("DODA1", "HQ656027.1", "TU2"),
        ("cDOPA5GT", "AB182643.1", "TU3"),
    ]

    assert [
        (step["enzyme_gene_name"], step["cds_source_reference"], step["mapped_unit_id"])
        for step in steps
    ] == expected
    assert all(step["enzyme_name"] for step in steps)
    assert [step["cds_sequence"] for step in steps] == [
        unit["cds"]["raw_text"] for unit in units
    ]
    assert all(step["applied_to_unit"] and step["mapping_status"] == "applied" for step in steps)
    assert result["formal_project_context"]["pathway_mapping"]["mapping_complete"] is True

    complete = result["complete_plasmid"]
    assert complete["total_length"] == 18841
    assert hashlib.sha256(complete["dna"].encode("ascii")).hexdigest() == (
        "cdeb4ea329322b942472b38c44fcad9c11216cd1e3fd4b9540e28a37826e2dc7"
    )
    assert hashlib.sha256(
        result["exports"]["complete_plasmid_fasta"]["data"].encode("utf-8")
    ).hexdigest() == "0b405c517c0d59f81e616ba6426b05aca35c246860cabde3a1bc300bde0c7706"
    assert hashlib.sha256(
        result["exports"]["complete_plasmid_genbank"]["data"].encode("utf-8")
    ).hexdigest() == "360dc60a109d1741a141bdcd63cc28990b515b838ba2be4cfe4b598c4721bd10"


def test_saved_result_cold_reopens_without_sequence_drift(tmp_path: Path) -> None:
    result = _generate(tmp_path)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    assert reopened["complete_plasmid"]["sequence_sha256"] == result["complete_plasmid"]["sequence_sha256"]
    assert reopened["formal_project_context"]["repeated_regulatory_confirmed"] is True
    assert reopened["formal_project_context"]["betalain_pbi121_validation"]["wet_lab_readiness"] == "not_assessed"
    command = (
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; import json; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "print(json.dumps({'sha':r['complete_plasmid']['sequence_sha256'],'order':r['unit_order']}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command], cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(repository.storage_dir)},
        check=True, capture_output=True, text=True,
    )
    assert json.loads(completed.stdout) == {"sha": result["complete_plasmid"]["sequence_sha256"], "order": ["TU1", "TU2", "TU3"]}
