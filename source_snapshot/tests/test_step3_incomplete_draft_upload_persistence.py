from __future__ import annotations

from pathlib import Path

from core.design_session import DesignSession
from services.formal_project_persistence import formal_draft_snapshot, save_formal_project_draft
from services.mvp_sequence_input import analyze_dna_component_input
from services.plant_project_draft_repository import PlantProjectDraftRepository


def test_incomplete_step3_draft_roundtrips_analyzed_three_prime_upload(tmp_path: Path) -> None:
    sequence = "ACGT" * 23 + "AA"
    record = analyze_dna_component_input(
        sequence,
        project_id="step3-upload-draft",
        component_type="terminator",
        display_name="threeprime-upload-real-repro",
        source_kind="user_recorded",
        source_name="threeprime-upload-real-repro.fasta",
    )
    assert record["role"] == "terminator"
    record["source_kind"] = "user_recorded"
    record["source_input_method"] = "upload"
    record["biological_role"] = record["role"]
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    saved = save_formal_project_draft(
        project_name="Incomplete Step 3 upload",
        project_id="step3-upload-draft",
        workflow_type="single_gene",
        current_step=3,
        design_session=DesignSession(step=3, host="Rice"),
        formal_state={
            "formal_step3_terminator_mode": "用户序列",
            "formal_step3_terminator_custom_input": "上传 FASTA",
            "formal_step3_terminator_custom_name": "threeprime-upload-real-repro",
            "formal_element_source_records": {"terminator": record},
        },
        project_definition={"project_name": "Incomplete Step 3 upload", "plant_host": "Rice"},
        repository=repository,
    )

    reopened = formal_draft_snapshot(
        PlantProjectDraftRepository(repository.storage_dir).load(saved.project_id)
    )
    restored = reopened["formal_state"]["formal_element_source_records"]["terminator"]
    assert restored["display_name"] == "threeprime-upload-real-repro"
    assert restored["source_kind"] == "user_recorded"
    assert restored["source_input_method"] == "upload"
    assert restored["role"] == "terminator"
    assert restored["biological_role"] == "terminator"
    assert restored["normalized_sequence"] == sequence
    assert "uploaded" not in repr(restored).lower()
