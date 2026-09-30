from __future__ import annotations

import hashlib
import time
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    create_component,
    create_insertion_site,
    create_sequence_asset,
    export_active_complete_plasmid,
    generate_active_complete_plasmid,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_insertion_site,
    upsert_sequence_asset,
    validate_active_runtime,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import PlantDesignProjectDraft, update_plant_project_draft


PROMOTER_SEQUENCE = "TTGACATATAAAGG"
CDS_SEQUENCE = "ATGGCTGAACTGTAA"
TERMINATOR_SEQUENCE = "GCGTTTTTTGCG"
CASSETTE_SEQUENCE = PROMOTER_SEQUENCE + CDS_SEQUENCE + TERMINATOR_SEQUENCE
CASSETTE_CHECKSUM = hashlib.sha256(CASSETTE_SEQUENCE.encode("utf-8")).hexdigest()

BACKBONE_SEQUENCE = "AAAACCCCGGGGTTTTAAAACCCCGGGGTTTT"
INSERTION_EXPECTED_SEQUENCE = BACKBONE_SEQUENCE[:16] + CASSETTE_SEQUENCE + BACKBONE_SEQUENCE[16:]
REPLACEMENT_EXPECTED_SEQUENCE = BACKBONE_SEQUENCE[:12] + CASSETTE_SEQUENCE + BACKBONE_SEQUENCE[16:]


def _sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def _make_genbank(sequence: str, *, topology: str = "circular", features: list[dict] | None = None, name: str = "SYNTHBONE") -> str:
    record = SeqRecord(
        Seq(sequence),
        id=name,
        name=name[:16],
        description=f"Synthetic backbone {name}",
    )
    record.annotations["molecule_type"] = "DNA"
    if topology:
        record.annotations["topology"] = topology

    bio_features: list[SeqFeature] = []
    for feature in features or []:
        location = SimpleLocation(int(feature["start"]) - 1, int(feature["end"]), strand=int(feature.get("strand", 1)))
        qualifiers = {"label": [str(feature["label"])]}
        for key, value in (feature.get("qualifiers") or {}).items():
            qualifiers[str(key)] = [str(item) for item in value]
        bio_features.append(SeqFeature(location=location, type=str(feature["type"]), qualifiers=qualifiers))
    record.features = bio_features
    buffer = StringIO()
    SeqIO.write(record, buffer, "genbank")
    return buffer.getvalue()


def _build_r227_runtime(project_id: str = "plant-draft-r228") -> dict:
    runtime = {"project_id": project_id}
    ordered_ids: list[str] = []
    for component_type, display_name, sequence in (
        ("promoter", "SYNTH_PROMOTER_ALPHA", PROMOTER_SEQUENCE),
        ("cds", "SYNTH_CDS_ALPHA", CDS_SEQUENCE),
        ("terminator", "SYNTH_TERMINATOR_ALPHA", TERMINATOR_SEQUENCE),
    ):
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=display_name,
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
            asset_role="construct_component",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id=project_id,
            component_type=component_type,
            display_name=display_name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        ordered_ids.append(component["component_id"])
    runtime = set_active_component_order(runtime, ordered_ids)
    return generate_active_construct(runtime)


def _positive_backbone_text(topology: str = "circular") -> str:
    return _make_genbank(
        BACKBONE_SEQUENCE,
        topology=topology,
        features=[
            {"label": "ORI_LEFT", "type": "rep_origin", "start": 1, "end": 4, "strand": 1},
            {"label": "UPSTREAM_MARKER", "type": "misc_feature", "start": 9, "end": 12, "strand": 1},
            {"label": "TAIL_TAG", "type": "misc_feature", "start": 25, "end": 28, "strand": -1},
            {"label": "TAIL_ORIGIN", "type": "rep_origin", "start": 29, "end": 32, "strand": 1},
        ],
    )


def _overlap_backbone_text() -> str:
    return _make_genbank(
        BACKBONE_SEQUENCE,
        topology="circular",
        features=[
            {"label": "ORI_LEFT", "type": "rep_origin", "start": 1, "end": 4, "strand": 1},
            {"label": "OVERLAP_CUT", "type": "misc_feature", "start": 14, "end": 18, "strand": 1},
            {"label": "TAIL_TAG", "type": "misc_feature", "start": 25, "end": 28, "strand": -1},
        ],
    )


def _edge_backbone_text() -> str:
    return _make_genbank(
        BACKBONE_SEQUENCE,
        topology="circular",
        features=[
            {"label": "EDGE_LEFT", "type": "misc_feature", "start": 5, "end": 8, "strand": 1},
            {"label": "EDGE_RIGHT", "type": "misc_feature", "start": 20, "end": 23, "strand": -1},
        ],
    )


def _build_complete_runtime(
    backbone_text: str,
    *,
    project_id: str = "plant-draft-r228",
    mode: str = "insertion",
    start_coordinate: int = 16,
    end_coordinate: int = 17,
    expected_removed_sequence: str = "",
    confirm: bool = True,
    topology_confirm: bool = False,
) -> tuple[dict, dict]:
    runtime = _build_r227_runtime(project_id=project_id)
    backbone = create_sequence_asset(
        project_id=project_id,
        display_name="SYNTH_BACKBONE_ALPHA",
        raw_text=backbone_text,
        molecule_type="dna",
        source_type="upload",
        source_format="genbank",
        source_name="synthetic_backbone.gb",
        source_file_checksum=_sha256(backbone_text),
        asset_role="backbone",
    )
    runtime = upsert_sequence_asset(runtime, backbone)
    site = create_insertion_site(
        project_id=project_id,
        backbone_asset_id=backbone["asset_id"],
        start_coordinate=start_coordinate,
        end_coordinate=end_coordinate,
        mode=mode,
        expected_removed_sequence=expected_removed_sequence,
        user_confirmation=confirm,
        topology_confirmation=topology_confirm,
    )
    runtime = upsert_insertion_site(runtime, site)
    runtime = generate_active_complete_plasmid(runtime)
    return runtime, backbone


def _critical_features(record) -> list[tuple[str, int, int, int, str]]:
    return [
        (
            str(feature.type),
            int(feature.location.start) + 1,
            int(feature.location.end),
            int(feature.location.strand or 1),
            str((feature.qualifiers or {}).get("label", [""])[0]),
        )
        for feature in list(record.features or [])
    ]


def test_exact_insertion_sequence_length_checksum_and_feature_shifts() -> None:
    runtime, _backbone = _build_complete_runtime(_positive_backbone_text())
    snapshot = active_complete_plasmid_snapshot(runtime)

    assert snapshot["sequence"] == INSERTION_EXPECTED_SEQUENCE
    assert snapshot["sequence_length"] == len(INSERTION_EXPECTED_SEQUENCE) == 73
    assert snapshot["sequence_checksum"] == _sha256(INSERTION_EXPECTED_SEQUENCE)
    assert snapshot["topology"] == "circular"
    assert snapshot["cassette_coordinates"] == {"start": 17, "end": 57}

    rows_by_name = {row["name"]: row for row in snapshot["feature_rows"]}
    assert rows_by_name["UPSTREAM_MARKER"]["start"] == 9
    assert rows_by_name["UPSTREAM_MARKER"]["end"] == 12
    assert rows_by_name["TAIL_TAG"]["start"] == 66
    assert rows_by_name["TAIL_TAG"]["end"] == 69
    assert rows_by_name["TAIL_TAG"]["strand"] == -1
    assert rows_by_name["TAIL_ORIGIN"]["start"] == 70
    assert rows_by_name["TAIL_ORIGIN"]["end"] == 73
    assert rows_by_name["SYNTH_PROMOTER_ALPHA"]["start"] == 17
    assert rows_by_name["SYNTH_CDS_ALPHA"]["start"] == 31
    assert rows_by_name["SYNTH_TERMINATOR_ALPHA"]["end"] == 57


def test_exact_replacement_sequence_length_checksum_and_feature_shifts() -> None:
    runtime, _backbone = _build_complete_runtime(
        _positive_backbone_text(),
        mode="replacement",
        start_coordinate=13,
        end_coordinate=16,
        expected_removed_sequence="TTTT",
    )
    snapshot = active_complete_plasmid_snapshot(runtime)

    assert snapshot["sequence"] == REPLACEMENT_EXPECTED_SEQUENCE
    assert snapshot["sequence_length"] == len(REPLACEMENT_EXPECTED_SEQUENCE) == 69
    assert snapshot["sequence_checksum"] == _sha256(REPLACEMENT_EXPECTED_SEQUENCE)
    assert snapshot["cassette_coordinates"] == {"start": 13, "end": 53}

    rows_by_name = {row["name"]: row for row in snapshot["feature_rows"]}
    assert rows_by_name["UPSTREAM_MARKER"]["start"] == 9
    assert rows_by_name["UPSTREAM_MARKER"]["end"] == 12
    assert rows_by_name["TAIL_TAG"]["start"] == 62
    assert rows_by_name["TAIL_TAG"]["end"] == 65
    assert rows_by_name["TAIL_ORIGIN"]["start"] == 66
    assert rows_by_name["TAIL_ORIGIN"]["end"] == 69


def test_insertion_near_beginning_middle_and_final_coordinate_are_supported_without_silent_corruption() -> None:
    beginning_runtime, _ = _build_complete_runtime(_edge_backbone_text(), start_coordinate=1, end_coordinate=2)
    middle_runtime, _ = _build_complete_runtime(_edge_backbone_text(), start_coordinate=16, end_coordinate=17, project_id="plant-draft-r228-middle")
    final_runtime, _ = _build_complete_runtime(_edge_backbone_text(), start_coordinate=32, end_coordinate=1, project_id="plant-draft-r228-final")

    beginning = active_complete_plasmid_snapshot(beginning_runtime)
    middle = active_complete_plasmid_snapshot(middle_runtime)
    final = active_complete_plasmid_snapshot(final_runtime)

    assert beginning["cassette_coordinates"] == {"start": 2, "end": 42}
    assert middle["cassette_coordinates"] == {"start": 17, "end": 57}
    assert final["cassette_coordinates"] == {"start": 33, "end": 73}
    assert beginning["sequence_length"] == middle["sequence_length"] == final["sequence_length"] == 73
    assert beginning["topology"] == middle["topology"] == final["topology"] == "circular"


def test_complete_plasmid_persists_and_reopens_exactly(tmp_path: Path) -> None:
    runtime, backbone = _build_complete_runtime(_positive_backbone_text())
    draft = update_plant_project_draft(
        PlantDesignProjectDraft.blank(project_name="R228 persistence"),
        project_name="R228 persistence",
        plant_design_goal="Document complete plasmid insertion into a synthetic backbone.",
        host_context="Synthetic host plant",
        expression_context="Synthetic single-gene expression context",
        canonical_construct_runtime=runtime,
    )
    repo = PlantProjectDraftRepository(tmp_path / "plant_runtime_drafts")
    saved = repo.save(draft)
    reopened = repo.load(saved.project_id)
    snapshot = active_complete_plasmid_snapshot(reopened.canonical_construct_runtime)

    assert snapshot["sequence"] == INSERTION_EXPECTED_SEQUENCE
    assert snapshot["sequence_checksum"] == _sha256(INSERTION_EXPECTED_SEQUENCE)
    assert snapshot["topology"] == "circular"
    assert snapshot["backbone_asset_id"] == backbone["asset_id"]
    assert snapshot["feature_rows"] == active_complete_plasmid_snapshot(runtime)["feature_rows"]


def test_complete_plasmid_fasta_and_annotated_genbank_roundtrip_match_sequence_topology_and_critical_features() -> None:
    runtime, _backbone = _build_complete_runtime(_positive_backbone_text())
    exports = export_active_complete_plasmid(runtime, project_name="SYNTH_COMPLETE_PLASMID")
    fasta_lines = exports["fasta"]["data"].strip().splitlines()
    record = next(SeqIO.parse(StringIO(exports["genbank"]["data"]), "genbank"))

    assert fasta_lines[1] == INSERTION_EXPECTED_SEQUENCE
    assert str(record.seq) == INSERTION_EXPECTED_SEQUENCE
    assert str(record.annotations.get("topology")) == "circular"
    critical = _critical_features(record)
    assert ("rep_origin", 1, 4, 1, "ORI_LEFT") in critical
    assert ("misc_feature", 9, 12, 1, "UPSTREAM_MARKER") in critical
    assert ("misc_feature", 66, 69, -1, "TAIL_TAG") in critical
    assert ("rep_origin", 70, 73, 1, "TAIL_ORIGIN") in critical
    assert ("promoter", 17, 30, 1, "SYNTH_PROMOTER_ALPHA") in critical
    assert ("cds", 31, 45, 1, "SYNTH_CDS_ALPHA") in critical
    assert ("terminator", 46, 57, 1, "SYNTH_TERMINATOR_ALPHA") in critical
    cds_feature = next(feature for feature in list(record.features or []) if (feature.qualifiers or {}).get("label", [""])[0] == "SYNTH_CDS_ALPHA")
    assert (cds_feature.qualifiers or {}).get("component_id")
    assert (cds_feature.qualifiers or {}).get("source_asset_id")


def test_old_r224_or_r227_drafts_without_complete_plasmid_fields_remain_loadable() -> None:
    runtime = _build_r227_runtime()
    legacy_payload = PlantDesignProjectDraft.blank(project_name="Legacy R227").to_dict()
    legacy_payload["canonical_construct_runtime"] = runtime
    legacy_payload["canonical_construct_runtime"].pop("insertion_sites", None)
    legacy_payload["canonical_construct_runtime"].pop("complete_plasmid_constructs", None)
    legacy_payload["canonical_construct_runtime"].pop("active_insertion_site_id", None)
    legacy_payload["canonical_construct_runtime"].pop("active_complete_plasmid_id", None)

    draft = PlantDesignProjectDraft.from_dict(legacy_payload)
    snapshot = active_complete_plasmid_snapshot(draft.canonical_construct_runtime)

    assert snapshot["sequence"] == ""
    assert snapshot["construct_status"] == "draft"


def test_negative_no_backbone_or_missing_confirmation_block_generation() -> None:
    runtime = _build_r227_runtime()
    site = create_insertion_site(
        project_id="plant-draft-r228-negative",
        backbone_asset_id="",
        start_coordinate=16,
        end_coordinate=17,
        mode="insertion",
        user_confirmation=False,
    )
    runtime = upsert_insertion_site(runtime, site)
    runtime = generate_active_complete_plasmid(runtime)
    rule_ids = {item["rule_id"] for item in active_complete_plasmid_snapshot(runtime)["validation_findings"]}

    assert "missing_backbone" in rule_ids

    unconfirmed_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(),
        project_id="plant-draft-r228-unconfirmed",
        confirm=False,
    )
    unconfirmed_rules = {
        item["rule_id"] for item in active_complete_plasmid_snapshot(unconfirmed_runtime)["validation_findings"]
    }
    assert "missing_insertion_site_confirmation" in unconfirmed_rules


def test_negative_protein_only_backbone_is_blocked() -> None:
    runtime = _build_r227_runtime(project_id="plant-draft-r228-protein")
    backbone = create_sequence_asset(
        project_id="plant-draft-r228-protein",
        display_name="Protein backbone",
        raw_text="MPEPTIDE",
        molecule_type="protein",
        source_type="paste",
        source_format="plain",
        asset_role="backbone",
    )
    runtime = upsert_sequence_asset(runtime, backbone)
    site = create_insertion_site(
        project_id="plant-draft-r228-protein",
        backbone_asset_id=backbone["asset_id"],
        start_coordinate=1,
        end_coordinate=1,
        mode="replacement",
        expected_removed_sequence="M",
        user_confirmation=True,
    )
    runtime = upsert_insertion_site(runtime, site)
    runtime = generate_active_complete_plasmid(runtime)
    rule_ids = {item["rule_id"] for item in active_complete_plasmid_snapshot(runtime)["validation_findings"]}

    assert "protein_only_backbone" in rule_ids


def test_negative_invalid_insertion_coordinates_outside_bounds_and_end_before_start_are_blocked() -> None:
    invalid_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(),
        project_id="plant-draft-r228-invalid-insertion",
        start_coordinate=16,
        end_coordinate=20,
    )
    invalid_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(invalid_runtime)["validation_findings"]}

    outside_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(),
        project_id="plant-draft-r228-outside",
        mode="replacement",
        start_coordinate=40,
        end_coordinate=41,
        expected_removed_sequence="AA",
    )
    outside_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(outside_runtime)["validation_findings"]}

    reversed_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(),
        project_id="plant-draft-r228-reversed",
        mode="replacement",
        start_coordinate=20,
        end_coordinate=10,
        expected_removed_sequence="",
    )
    reversed_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(reversed_runtime)["validation_findings"]}

    assert "invalid_insertion_coordinate" in invalid_rules
    assert "insertion_interval_outside_backbone_bounds" in outside_rules
    assert "replacement_end_before_start" in reversed_rules


def test_negative_stale_cassette_and_changed_backbone_require_regeneration() -> None:
    runtime, _backbone = _build_complete_runtime(_positive_backbone_text())
    promoter_asset = next(asset for asset in runtime["sequence_assets"] if asset["display_name"] == "SYNTH_PROMOTER_ALPHA")
    updated_promoter = create_sequence_asset(
        project_id="plant-draft-r228",
        display_name=promoter_asset["display_name"],
        raw_text=PROMOTER_SEQUENCE + "AA",
        molecule_type="dna",
        source_type="paste",
        source_format="plain",
        asset_role=promoter_asset["asset_role"],
        asset_id=promoter_asset["asset_id"],
        created_at=promoter_asset["created_at"],
    )
    runtime = upsert_sequence_asset(runtime, updated_promoter)
    stale_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(validate_active_runtime(runtime))["validation_findings"]}
    assert "stale_complete_plasmid_after_source_change" in stale_rules

    runtime, backbone = _build_complete_runtime(_positive_backbone_text(), project_id="plant-draft-r228-backbone-change")
    changed_backbone = create_sequence_asset(
        project_id="plant-draft-r228-backbone-change",
        display_name=backbone["display_name"],
        raw_text=_positive_backbone_text().replace(BACKBONE_SEQUENCE, BACKBONE_SEQUENCE + "AA"),
        molecule_type="dna",
        source_type="upload",
        source_format="genbank",
        source_name=backbone["source_name"],
        source_file_checksum=backbone["source_file_checksum"],
        asset_role="backbone",
        asset_id=backbone["asset_id"],
        created_at=backbone["created_at"],
    )
    runtime = upsert_sequence_asset(runtime, changed_backbone)
    changed_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(validate_active_runtime(runtime))["validation_findings"]}
    assert "stale_complete_plasmid_after_source_change" in changed_rules


def test_negative_overlapping_feature_conflict_is_blocking() -> None:
    runtime, _ = _build_complete_runtime(_overlap_backbone_text(), project_id="plant-draft-r228-overlap")
    snapshot = active_complete_plasmid_snapshot(runtime)
    rule_ids = {item["rule_id"] for item in snapshot["validation_findings"]}

    assert "overlapping_backbone_feature_conflict" in rule_ids
    assert snapshot["construct_status"] == "blocking_invalid"


def test_negative_corrupted_coordinates_and_checksum_mismatch_are_detected() -> None:
    runtime, _ = _build_complete_runtime(_positive_backbone_text(), project_id="plant-draft-r228-corrupt")
    runtime["complete_plasmid_constructs"][0]["sequence_checksum"] = "wrong-checksum"
    runtime["complete_plasmid_constructs"][0]["combined_feature_coordinates"][0]["end"] = 999
    snapshot = active_complete_plasmid_snapshot(validate_active_runtime(runtime))
    rule_ids = {item["rule_id"] for item in snapshot["validation_findings"]}

    assert "complete_plasmid_checksum_mismatch" in rule_ids
    assert "corrupted_persisted_complete_plasmid_feature_coordinate" in rule_ids


def test_negative_blocking_invalid_plasmid_cannot_be_exported() -> None:
    runtime, _ = _build_complete_runtime(_overlap_backbone_text(), project_id="plant-draft-r228-export-block")
    with pytest.raises(Exception):
        export_active_complete_plasmid(runtime, project_name="invalid")


def test_negative_exported_genbank_sequence_mismatch_is_detected(monkeypatch) -> None:
    runtime, _ = _build_complete_runtime(_positive_backbone_text(), project_id="plant-draft-r228-export-mismatch")

    def _bad_genbank(sequence, features, project_name, topology=None):  # noqa: ANN001
        bad_record = next(SeqIO.parse(StringIO(_make_genbank("A" + sequence[1:], topology=topology or "circular", features=[])), "genbank"))
        buffer = StringIO()
        SeqIO.write(bad_record, buffer, "genbank")
        return buffer.getvalue()

    import components.export_manager as export_manager

    monkeypatch.setattr(export_manager, "generate_genbank_string", _bad_genbank)
    with pytest.raises(Exception):
        export_active_complete_plasmid(runtime, project_name="mismatch")


def test_linear_topology_is_preserved_and_missing_topology_confirmation_is_blocked() -> None:
    linear_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(topology="linear"),
        project_id="plant-draft-r228-linear",
    )
    linear_snapshot = active_complete_plasmid_snapshot(linear_runtime)
    assert linear_snapshot["topology"] == "linear"
    assert not any(item["blocking"] for item in linear_snapshot["validation_findings"])
    linear_export = export_active_complete_plasmid(linear_runtime, project_name="linear")
    linear_record = next(SeqIO.parse(StringIO(linear_export["genbank"]["data"]), "genbank"))
    assert str(linear_record.annotations.get("topology")) == "linear"

    missing_topology_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(topology=""),
        project_id="plant-draft-r228-topology-missing",
        topology_confirm=False,
    )
    missing_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(missing_topology_runtime)["validation_findings"]}
    assert "backbone_topology_requires_confirmation" in missing_rules

    confirmed_runtime, _ = _build_complete_runtime(
        _positive_backbone_text(topology=""),
        project_id="plant-draft-r228-topology-confirmed",
        topology_confirm=True,
    )
    confirmed_rules = {item["rule_id"] for item in active_complete_plasmid_snapshot(confirmed_runtime)["validation_findings"]}
    assert "backbone_topology_confirmed_by_user" in confirmed_rules


def test_realistic_scale_exercise_reports_roundtrip_metrics(tmp_path: Path) -> None:
    large_promoter = "A" * 120
    large_cds = "ATG" + ("GCT" * 198) + "TAA"
    large_terminator = "C" * 90
    large_backbone_sequence = ("ACGT" * 900) + "TTAA"
    large_backbone_text = _make_genbank(
        large_backbone_sequence,
        topology="circular",
        features=[
            {"label": "LARGE_ORI", "type": "rep_origin", "start": 100, "end": 260, "strand": 1},
            {"label": "LARGE_MARKER", "type": "misc_feature", "start": 1200, "end": 1450, "strand": -1},
            {"label": "LARGE_TAIL", "type": "misc_feature", "start": 2500, "end": 2800, "strand": 1},
        ],
        name="LARGEBONE",
    )
    runtime = {"project_id": "plant-draft-r228-large"}
    ordered_ids: list[str] = []
    for component_type, display_name, sequence in (
        ("promoter", "LARGE_PROMOTER", large_promoter),
        ("cds", "LARGE_CDS", large_cds),
        ("terminator", "LARGE_TERMINATOR", large_terminator),
    ):
        asset = create_sequence_asset(
            project_id="plant-draft-r228-large",
            display_name=display_name,
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
            asset_role="construct_component",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="plant-draft-r228-large",
            component_type=component_type,
            display_name=display_name,
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        ordered_ids.append(component["component_id"])
    runtime = set_active_component_order(runtime, ordered_ids)
    runtime = generate_active_construct(runtime)

    backbone = create_sequence_asset(
        project_id="plant-draft-r228-large",
        display_name="LARGE_BACKBONE",
        raw_text=large_backbone_text,
        molecule_type="dna",
        source_type="upload",
        source_format="genbank",
        source_name="large_backbone.gb",
        source_file_checksum=_sha256(large_backbone_text),
        asset_role="backbone",
    )
    runtime = upsert_sequence_asset(runtime, backbone)
    site = create_insertion_site(
        project_id="plant-draft-r228-large",
        backbone_asset_id=backbone["asset_id"],
        start_coordinate=1800,
        end_coordinate=1801,
        mode="insertion",
        user_confirmation=True,
    )
    runtime = upsert_insertion_site(runtime, site)

    started = time.perf_counter()
    runtime = generate_active_complete_plasmid(runtime)
    generation_seconds = time.perf_counter() - started
    snapshot = active_complete_plasmid_snapshot(runtime)

    repo = PlantProjectDraftRepository(tmp_path / "large_runtime_drafts")
    saved = repo.save(
        update_plant_project_draft(
            PlantDesignProjectDraft.blank(project_name="R228 large"),
            project_name="R228 large",
            plant_design_goal="Large synthetic complete plasmid exercise.",
            host_context="Synthetic plant host",
            expression_context="Synthetic large expression context",
            canonical_construct_runtime=runtime,
        )
    )
    reopened = repo.load(saved.project_id)
    reopened_snapshot = active_complete_plasmid_snapshot(reopened.canonical_construct_runtime)
    exports = export_active_complete_plasmid(runtime, project_name="R228_LARGE")
    record = next(SeqIO.parse(StringIO(exports["genbank"]["data"]), "genbank"))
    export_size = len(exports["genbank"]["data"].encode("utf-8"))

    print(
        f"R228 large exercise: import_success=yes generation_seconds={generation_seconds:.6f} "
        f"save_reopen=yes export_size_bytes={export_size} genbank_reopen=yes "
        f"sequence_checksum={snapshot['sequence_checksum']}"
    )

    assert len(backbone["nucleotide_sequence"]) > 3000
    assert len(runtime["transcription_units"][0]["generated_nucleotide_sequence"]) > 700
    assert generation_seconds >= 0
    assert snapshot["sequence"] == reopened_snapshot["sequence"]
    assert snapshot["sequence_checksum"] == reopened_snapshot["sequence_checksum"]
    assert str(record.seq) == snapshot["sequence"]
    assert str(record.annotations.get("topology")) == "circular"
