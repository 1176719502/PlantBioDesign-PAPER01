from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from Bio import SeqIO

from services.canonical_construct_runtime import (
    active_construct_snapshot,
    blank_runtime,
    create_component,
    create_sequence_asset,
    export_active_construct,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_sequence_asset,
    validate_active_runtime,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import PlantDesignProjectDraft, update_plant_project_draft


PROMOTER_SEQUENCE = "TTGACATATAAAGG"
UTR_SEQUENCE = "GCCACC"
SIGNAL_SEQUENCE = "ATGAAA"
CDS_SEQUENCE = "ATGGCTGAACTGTAA"
TAG_SEQUENCE = "GGTGGT"
TERMINATOR_SEQUENCE = "GCGTTTTTTGCG"
EXPECTED_SEQUENCE = PROMOTER_SEQUENCE + CDS_SEQUENCE + TERMINATOR_SEQUENCE
EXPECTED_OPTIONAL_SEQUENCE = (
    PROMOTER_SEQUENCE + UTR_SEQUENCE + SIGNAL_SEQUENCE + CDS_SEQUENCE + TAG_SEQUENCE + TERMINATOR_SEQUENCE
)
EXPECTED_CHECKSUM = "7babd54d5f11513c180a356232a516966d63f9f4245bf57213c548f8ad890bfe"


def _base_runtime() -> tuple[dict, dict[str, str]]:
    runtime = blank_runtime("plant-draft-r227")
    ids: dict[str, str] = {}
    for key, name, sequence, component_type in (
        ("promoter", "SYNTH_PROMOTER_ALPHA", PROMOTER_SEQUENCE, "promoter"),
        ("cds", "SYNTH_CDS_ALPHA", CDS_SEQUENCE, "cds"),
        ("terminator", "SYNTH_TERMINATOR_ALPHA", TERMINATOR_SEQUENCE, "terminator"),
    ):
        asset = create_sequence_asset(
            project_id="plant-draft-r227",
            display_name=name,
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="plant-draft-r227",
            component_type=component_type,
            display_name=name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        ids[f"asset_{key}"] = asset["asset_id"]
        ids[f"component_{key}"] = component["component_id"]
    runtime = set_active_component_order(
        runtime,
        [ids["component_promoter"], ids["component_cds"], ids["component_terminator"]],
    )
    return runtime, ids


def _generated_base_runtime() -> tuple[dict, dict[str, str]]:
    runtime, ids = _base_runtime()
    return generate_active_construct(runtime), ids


def test_exact_promoter_cds_terminator_assembly_coordinates_translation_and_checksum() -> None:
    runtime, _ids = _generated_base_runtime()
    snapshot = active_construct_snapshot(runtime)

    assert snapshot["sequence"] == EXPECTED_SEQUENCE
    assert snapshot["sequence_length"] == 41
    assert snapshot["sequence_checksum"] == EXPECTED_CHECKSUM
    assert snapshot["translation"] == "MAEL*"
    assert snapshot["feature_rows"] == [
        {
            "name": "SYNTH_PROMOTER_ALPHA",
            "component_type": "promoter",
            "start": 1,
            "end": 14,
            "strand": 1,
            "source_asset_id": snapshot["runtime"]["sequence_assets"][0]["asset_id"],
            "component_id": snapshot["runtime"]["components"][0]["component_id"],
        },
        {
            "name": "SYNTH_CDS_ALPHA",
            "component_type": "cds",
            "start": 15,
            "end": 29,
            "strand": 1,
            "source_asset_id": snapshot["runtime"]["sequence_assets"][1]["asset_id"],
            "component_id": snapshot["runtime"]["components"][1]["component_id"],
        },
        {
            "name": "SYNTH_TERMINATOR_ALPHA",
            "component_type": "terminator",
            "start": 30,
            "end": 41,
            "strand": 1,
            "source_asset_id": snapshot["runtime"]["sequence_assets"][2]["asset_id"],
            "component_id": snapshot["runtime"]["components"][2]["component_id"],
        },
    ]


def test_optional_component_assembly_and_supported_reorder_produce_exact_sequence() -> None:
    runtime, ids = _generated_base_runtime()
    for key, name, sequence, component_type in (
        ("utr", "SYNTH_UTR_ALPHA", UTR_SEQUENCE, "five_prime_utr"),
        ("signal", "SYNTH_SIGNAL_ALPHA", SIGNAL_SEQUENCE, "signal_targeting_coding_sequence"),
        ("tag", "SYNTH_TAG_ALPHA", TAG_SEQUENCE, "tag"),
    ):
        asset = create_sequence_asset(
            project_id="plant-draft-r227",
            display_name=name,
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="plant-draft-r227",
            component_type=component_type,
            display_name=name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        ids[f"asset_{key}"] = asset["asset_id"]
        ids[f"component_{key}"] = component["component_id"]

    runtime = set_active_component_order(
        runtime,
        [
            ids["component_promoter"],
            ids["component_utr"],
            ids["component_signal"],
            ids["component_cds"],
            ids["component_tag"],
            ids["component_terminator"],
        ],
    )
    runtime = generate_active_construct(runtime)
    snapshot = active_construct_snapshot(runtime)

    assert snapshot["sequence"] == EXPECTED_OPTIONAL_SEQUENCE
    assert snapshot["sequence_length"] == len(EXPECTED_OPTIONAL_SEQUENCE)
    assert [row["component_type"] for row in snapshot["feature_rows"]] == [
        "promoter",
        "five_prime_utr",
        "signal_targeting_coding_sequence",
        "cds",
        "tag",
        "terminator",
    ]


def test_reverse_orientation_is_applied_deterministically() -> None:
    runtime, ids = _generated_base_runtime()
    terminator_component = next(
        component for component in runtime["components"] if component["component_id"] == ids["component_terminator"]
    )
    terminator_component["orientation"] = "reverse"

    runtime = generate_active_construct(runtime)
    snapshot = active_construct_snapshot(runtime)

    assert snapshot["sequence"] == EXPECTED_SEQUENCE[:29] + "CGCAAAAAACGC"
    assert snapshot["feature_rows"][-1]["strand"] == -1
    assert any(item["rule_id"] == "reverse_complement_orientation_used" for item in snapshot["validation_findings"])


def test_save_and_reopen_preserve_exact_runtime_sequence_coordinates_and_checksum(tmp_path: Path) -> None:
    runtime, _ids = _generated_base_runtime()
    draft = update_plant_project_draft(
        PlantDesignProjectDraft.blank(project_name="R227 runtime persistence"),
        project_name="R227 runtime persistence",
        plant_design_goal="Document a synthetic single-gene construct runtime.",
        host_context="Synthetic host plant",
        expression_context="Synthetic expression context",
        canonical_construct_runtime=runtime,
    )
    repo = PlantProjectDraftRepository(tmp_path / "plant_runtime_drafts")
    saved = repo.save(draft)
    reopened = repo.load(saved.project_id)
    snapshot = active_construct_snapshot(reopened.canonical_construct_runtime)

    assert snapshot["sequence"] == EXPECTED_SEQUENCE
    assert snapshot["sequence_checksum"] == EXPECTED_CHECKSUM
    assert [(row["start"], row["end"]) for row in snapshot["feature_rows"]] == [(1, 14), (15, 29), (30, 41)]


def test_deterministic_output_across_repeated_generation_runs() -> None:
    runtime, _ids = _generated_base_runtime()
    first = active_construct_snapshot(runtime)
    second = active_construct_snapshot(generate_active_construct(runtime))

    assert first["sequence"] == second["sequence"]
    assert first["sequence_checksum"] == second["sequence_checksum"]
    assert first["feature_rows"] == second["feature_rows"]
    assert first["revision_id"] == second["revision_id"]


def test_fasta_and_genbank_exports_match_canonical_sequence_and_features() -> None:
    runtime, _ids = _generated_base_runtime()
    exports = export_active_construct(runtime, project_name="SYNTH_CONSTRUCT_ALPHA")

    fasta_lines = exports["fasta"]["data"].strip().splitlines()
    assert fasta_lines[1] == EXPECTED_SEQUENCE
    gb_record = next(SeqIO.parse(StringIO(exports["genbank"]["data"]), "genbank"))
    assert str(gb_record.seq) == EXPECTED_SEQUENCE
    assert [(feature.type, int(feature.location.start) + 1, int(feature.location.end)) for feature in gb_record.features] == [
        ("promoter", 1, 14),
        ("cds", 15, 29),
        ("terminator", 30, 41),
    ]


def test_backward_safe_loading_of_existing_r224_payload_without_runtime_field() -> None:
    legacy_payload = PlantDesignProjectDraft.blank(project_name="Legacy R224").to_dict()
    legacy_payload.pop("canonical_construct_runtime", None)
    reloaded = PlantDesignProjectDraft.from_dict(legacy_payload)

    assert reloaded.project_name == "Legacy R224"
    assert reloaded.canonical_construct_runtime == {}


def test_missing_required_components_produce_blocking_findings() -> None:
    runtime = blank_runtime("plant-draft-r227-missing")
    asset = create_sequence_asset(
        project_id="plant-draft-r227-missing",
        display_name="CDS only",
        raw_text=CDS_SEQUENCE,
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, asset)
    component = create_component(
        project_id="plant-draft-r227-missing",
        component_type="cds",
        display_name="CDS only",
        sequence_asset_id=asset["asset_id"],
    )
    runtime = upsert_component(runtime, component)
    runtime = set_active_component_order(runtime, [component["component_id"]])
    runtime = generate_active_construct(runtime)
    rule_ids = {item["rule_id"] for item in active_construct_snapshot(runtime)["validation_findings"]}

    assert {"missing_promoter", "missing_terminator"} <= rule_ids


def test_component_without_dna_sequence_and_protein_only_asset_are_blocked() -> None:
    runtime = blank_runtime("plant-draft-r227-protein")
    protein_asset = create_sequence_asset(
        project_id="plant-draft-r227-protein",
        display_name="Protein only",
        raw_text="MPEPTIDE",
        molecule_type="protein",
        source_type="paste",
        source_format="plain",
    )
    empty_asset = create_sequence_asset(
        project_id="plant-draft-r227-protein",
        display_name="Empty DNA",
        raw_text="",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, protein_asset)
    runtime = upsert_sequence_asset(runtime, empty_asset)
    protein_component = create_component(
        project_id="plant-draft-r227-protein",
        component_type="cds",
        display_name="Protein component",
        sequence_asset_id=protein_asset["asset_id"],
    )
    empty_component = create_component(
        project_id="plant-draft-r227-protein",
        component_type="promoter",
        display_name="Empty component",
        sequence_asset_id=empty_asset["asset_id"],
    )
    runtime = upsert_component(runtime, protein_component)
    runtime = upsert_component(runtime, empty_component)
    runtime = set_active_component_order(runtime, [empty_component["component_id"], protein_component["component_id"]])
    runtime = generate_active_construct(runtime)
    rule_ids = {item["rule_id"] for item in active_construct_snapshot(runtime)["validation_findings"]}

    assert "component_has_no_nucleotide_sequence" in rule_ids
    assert "protein_only_asset_used_as_dna" in rule_ids


def test_illegal_dna_symbol_and_bad_cds_content_are_reported() -> None:
    runtime = blank_runtime("plant-draft-r227-illegal")
    promoter_asset = create_sequence_asset(
        project_id="plant-draft-r227-illegal",
        display_name="Promoter",
        raw_text=PROMOTER_SEQUENCE,
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    bad_cds_asset = create_sequence_asset(
        project_id="plant-draft-r227-illegal",
        display_name="Bad CDS",
        raw_text="AUGTAGGAATAA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    terminator_asset = create_sequence_asset(
        project_id="plant-draft-r227-illegal",
        display_name="Terminator",
        raw_text=TERMINATOR_SEQUENCE,
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, promoter_asset)
    runtime = upsert_sequence_asset(runtime, bad_cds_asset)
    runtime = upsert_sequence_asset(runtime, terminator_asset)
    promoter = create_component(
        project_id="plant-draft-r227-illegal",
        component_type="promoter",
        display_name="Promoter",
        sequence_asset_id=promoter_asset["asset_id"],
    )
    cds = create_component(
        project_id="plant-draft-r227-illegal",
        component_type="cds",
        display_name="Bad CDS",
        sequence_asset_id=bad_cds_asset["asset_id"],
    )
    terminator = create_component(
        project_id="plant-draft-r227-illegal",
        component_type="terminator",
        display_name="Terminator",
        sequence_asset_id=terminator_asset["asset_id"],
    )
    runtime = upsert_component(runtime, promoter)
    runtime = upsert_component(runtime, cds)
    runtime = upsert_component(runtime, terminator)
    runtime = set_active_component_order(runtime, [promoter["component_id"], cds["component_id"], terminator["component_id"]])
    runtime = generate_active_construct(runtime)
    rule_ids = {item["rule_id"] for item in active_construct_snapshot(runtime)["validation_findings"]}

    assert "illegal_nucleotide_symbol" in rule_ids

    divisible_asset = create_sequence_asset(
        project_id="plant-draft-r227-illegal",
        display_name="Divisible CDS",
        raw_text="ATGTAGGAATAA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, divisible_asset)
    cds["sequence_asset_id"] = divisible_asset["asset_id"]
    runtime = upsert_component(runtime, cds)
    runtime = generate_active_construct(runtime)
    rule_ids = {item["rule_id"] for item in active_construct_snapshot(runtime)["validation_findings"]}

    assert "internal_in_frame_stop_codon" in rule_ids


def test_cds_length_not_divisible_by_three_is_blocking() -> None:
    runtime, ids = _base_runtime()
    bad_cds_asset = create_sequence_asset(
        project_id="plant-draft-r227",
        display_name="Bad length CDS",
        raw_text="ATGGCTA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
    )
    runtime = upsert_sequence_asset(runtime, bad_cds_asset)
    cds_component = next(component for component in runtime["components"] if component["component_id"] == ids["component_cds"])
    cds_component["sequence_asset_id"] = bad_cds_asset["asset_id"]
    runtime = upsert_component(runtime, cds_component)
    runtime = generate_active_construct(runtime)
    rule_ids = {item["rule_id"] for item in active_construct_snapshot(runtime)["validation_findings"]}

    assert "cds_length_not_divisible_by_three" in rule_ids


def test_checksum_mismatch_and_corrupted_coordinate_are_detected() -> None:
    runtime, _ids = _generated_base_runtime()
    runtime["transcription_units"][0]["generated_sequence_checksum"] = "wrong-checksum"
    runtime["transcription_units"][0]["feature_coordinates"][0]["end"] = 999
    snapshot = active_construct_snapshot(validate_active_runtime(runtime))
    rule_ids = {item["rule_id"] for item in snapshot["validation_findings"]}

    assert "persisted_checksum_differs_from_regenerated_checksum" in rule_ids
    assert "corrupted_persisted_coordinate" in rule_ids


def test_source_sequence_change_and_orientation_change_mark_output_stale_until_regenerated() -> None:
    runtime, ids = _generated_base_runtime()
    promoter_asset = next(asset for asset in runtime["sequence_assets"] if asset["asset_id"] == ids["asset_promoter"])
    updated_asset = create_sequence_asset(
        project_id="plant-draft-r227",
        display_name=promoter_asset["display_name"],
        raw_text=PROMOTER_SEQUENCE + "AA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
        asset_id=promoter_asset["asset_id"],
        created_at=promoter_asset["created_at"],
    )
    runtime = upsert_sequence_asset(runtime, updated_asset)
    stale_rules = {item["rule_id"] for item in active_construct_snapshot(validate_active_runtime(runtime))["validation_findings"]}
    assert "stale_generated_output_after_source_sequence_modification" in stale_rules

    runtime, ids = _generated_base_runtime()
    cds_component = next(component for component in runtime["components"] if component["component_id"] == ids["component_cds"])
    cds_component["orientation"] = "reverse"
    runtime = upsert_component(runtime, cds_component)
    stale_rules = {item["rule_id"] for item in active_construct_snapshot(validate_active_runtime(runtime))["validation_findings"]}
    assert "stale_generated_output_after_source_sequence_modification" in stale_rules


def test_invalid_component_reference_and_duplicate_construct_identity_are_detected() -> None:
    runtime, _ids = _generated_base_runtime()
    runtime = set_active_component_order(runtime, ["missing-component-id"])
    runtime["constructs"].append(json.loads(json.dumps(runtime["constructs"][0])))
    snapshot = active_construct_snapshot(validate_active_runtime(runtime))
    rule_ids = {item["rule_id"] for item in snapshot["validation_findings"]}

    assert "invalid_component_reference" in rule_ids
    assert "duplicate_authoritative_construct_identity" in rule_ids


def test_blocking_invalid_construct_cannot_be_exported() -> None:
    runtime = blank_runtime("plant-draft-r227-export")
    with_exception = False
    try:
        export_active_construct(runtime, project_name="Blocking invalid runtime")
    except Exception:
        with_exception = True

    assert with_exception is True
