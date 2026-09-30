from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    export_active_complete_plasmid,
    generate_active_complete_plasmid,
    generate_active_construct,
)
from services.acceptance_fixture_identity import (
    clear_acceptance_fixture_context,
    configure_acceptance_fixture_context,
    runtime_identity,
    snapshot_active_production_database,
)
from services.mvp_multi_tu_runtime import (
    MULTI_TU_EXPRESSION_ASSEMBLY,
    MvpMultiTuRuntimeError,
    generate_multi_tu_combined_construct,
    export_multi_tu_outputs,
    generate_multi_tu_construct,
    multi_tu_snapshot,
    set_multi_tu_unit_order,
    set_multi_tu_unit_orientation,
)


DATA_PATH = Path(__file__).parent / "data" / "mvp9_multi_tu_cases.json"
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def _sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def _make_backbone_genbank() -> str:
    record = SeqRecord(Seq(DATA["backbone"]["sequence"]), id="MVP9_BACKBONE", name="MVP9_BACKBONE")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"
    for item in DATA["backbone"]["features"]:
        if item.get("parts"):
            parts = [
                SimpleLocation(int(part["start"]) - 1, int(part["end"]), strand=int(item["strand"]))
                for part in item["parts"]
            ]
            location = CompoundLocation(parts, operator="join")
        else:
            location = SimpleLocation(
                int(item["start"]) - 1,
                int(item["end"]),
                strand=int(item["strand"]),
            )
        record.features.append(
            SeqFeature(location, type=item["type"], qualifiers={"label": [item["label"]]})
        )
    buffer = StringIO()
    SeqIO.write(record, buffer, "genbank")
    return buffer.getvalue()


def _units_for_case(case: dict) -> list[dict]:
    order_index = {unit_id: index + 1 for index, unit_id in enumerate(case["unit_order"])}
    units = []
    for unit_id in ("TU1", "TU2"):
        source = DATA["components"][unit_id]
        units.append(
            {
                "unit_id": unit_id,
                "unit_name": source["unit_name"],
                "orientation": case["orientations"][unit_id],
                "order": order_index[unit_id],
                "promoter": deepcopy(source["promoter"]),
                "cds": deepcopy(source["cds"]),
                "terminator": deepcopy(source["terminator"]),
            }
        )
    return units


def _oracle(case: dict) -> dict:
    cursor = 1
    combined_parts: list[str] = []
    units: dict[str, dict] = {}
    components: list[dict] = []
    for unit_id in case["unit_order"]:
        source = DATA["components"][unit_id]
        orientation = case["orientations"][unit_id]
        strand = 1 if orientation == "forward" else -1
        roles = ("promoter", "cds", "terminator") if strand == 1 else ("terminator", "cds", "promoter")
        unit_start = cursor
        unit_fragments: list[str] = []
        for role in roles:
            raw = source[role]["sequence"]
            fragment = raw if strand == 1 else _reverse_complement(raw)
            start = cursor
            end = cursor + len(fragment) - 1
            components.append(
                {
                    "unit_id": unit_id,
                    "name": source[role]["display_name"],
                    "component_type": role,
                    "start": start,
                    "end": end,
                    "strand": strand,
                }
            )
            unit_fragments.append(fragment)
            cursor = end + 1
        unit_dna = "".join(unit_fragments)
        combined_parts.append(unit_dna)
        units[unit_id] = {
            "dna": unit_dna,
            "start": unit_start,
            "end": cursor - 1,
            "strand": strand,
        }
    combined = "".join(combined_parts)
    backbone = DATA["backbone"]["sequence"]
    if case["mode"] == "insertion":
        cut = int(case["start"])
        complete = backbone[:cut] + combined + backbone[cut:]
        cassette_start = cut + 1
    else:
        start0 = int(case["start"]) - 1
        end0 = int(case["end"])
        complete = backbone[:start0] + combined + backbone[end0:]
        cassette_start = start0 + 1
    return {
        "combined": combined,
        "complete": complete,
        "units": units,
        "components": components,
        "cassette_start": cassette_start,
        "cassette_end": cassette_start + len(combined) - 1,
    }


def _generate(case: dict) -> dict:
    expected_removed = ""
    if case["mode"] == "replacement":
        expected_removed = DATA["backbone"]["sequence"][int(case["start"]) - 1 : int(case["end"])]
    return generate_multi_tu_construct(
        project_id=f"mvp9-{case['case_id']}",
        project_name=case["case_id"],
        expression_units=_units_for_case(case),
        backbone={
            "display_name": "MVP9_BACKBONE",
            "raw_text": _make_backbone_genbank(),
            "source_format": "genbank",
            "source_type": "upload",
            "source_name": "mvp9_backbone.gb",
        },
        insertion_settings={
            "mode": case["mode"],
            "start_coordinate": case["start"],
            "end_coordinate": case["end"],
            "expected_removed_sequence": expected_removed,
            "user_confirmation": True,
        },
    )


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: case["case_id"])
def test_eight_fixed_cases_match_independent_basewise_oracle(case: dict) -> None:
    result = _generate(case)
    expected = _oracle(case)

    assert result["project_type"] == "multi_tu"
    assert result["unit_order"] == case["unit_order"]
    assert result["combined_construct"]["dna"] == expected["combined"]
    assert result["complete_plasmid"]["dna"] == expected["complete"]
    assert result["combined_construct"]["total_length"] == len(expected["combined"])
    assert result["complete_plasmid"]["total_length"] == len(expected["complete"])
    assert result["combined_construct"]["sequence_sha256"] == _sha256(expected["combined"])
    assert result["complete_plasmid"]["sequence_sha256"] == _sha256(expected["complete"])
    assert result["complete_plasmid"]["cassette_coordinates"] == {
        "start": expected["cassette_start"],
        "end": expected["cassette_end"],
    }

    actual_units = {unit["unit_id"]: unit for unit in result["expression_units"]}
    for unit_id, expected_unit in expected["units"].items():
        actual = actual_units[unit_id]
        assert actual["dna"] == expected_unit["dna"]
        assert actual["length"] == len(expected_unit["dna"])
        assert actual["sequence_sha256"] == _sha256(expected_unit["dna"])
        assert actual["range"] == {
            "start": expected_unit["start"],
            "end": expected_unit["end"],
            "strand": expected_unit["strand"],
        }

    actual_components = [
        {
            key: row[key]
            for key in ("unit_id", "name", "component_type", "start", "end", "strand")
        }
        for row in result["combined_construct"]["component_coordinates"]
    ]
    assert actual_components == expected["components"]
    assert result["combined_construct"]["validation_status"] == "current"
    assert result["complete_plasmid"]["validation_status"] == "current"

    record = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    assert str(record.seq).upper() == expected["complete"]
    by_label = {
        str((feature.qualifiers.get("label") or [""])[0]): feature
        for feature in record.features
    }
    for component in expected["components"]:
        feature = by_label[component["name"]]
        assert int(feature.location.start) + 1 == expected["cassette_start"] + component["start"] - 1
        assert int(feature.location.end) == expected["cassette_start"] + component["end"] - 1
        assert int(feature.location.strand or 1) == component["strand"]
    for unit_id, expected_unit in expected["units"].items():
        label = DATA["components"][unit_id]["unit_name"]
        feature = by_label[label]
        assert int(feature.location.start) + 1 == expected["cassette_start"] + expected_unit["start"] - 1
        assert int(feature.location.end) == expected["cassette_start"] + expected_unit["end"] - 1
        assert int(feature.location.strand or 1) == expected_unit["strand"]


def test_compound_location_and_backbone_feature_strands_survive_insertion_and_replacement() -> None:
    for case_id in ("case_07_circular_boundary_insertion", "case_08_replacement_compound_location"):
        case = next(item for item in DATA["cases"] if item["case_id"] == case_id)
        result = _generate(case)
        record = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
        cross_origin = next(
            feature
            for feature in record.features
            if (feature.qualifiers.get("label") or [""])[0] == "CROSS_ORIGIN"
        )
        negative_marker = next(
            feature
            for feature in record.features
            if (feature.qualifiers.get("label") or [""])[0] == "NEG_MARKER"
        )
        assert isinstance(cross_origin.location, CompoundLocation)
        assert len(cross_origin.location.parts) == 2
        assert all(int(part.strand or 1) == -1 for part in cross_origin.location.parts)
        assert int(negative_marker.location.strand or 1) == -1


def test_order_change_changes_dna_signature_and_marks_previous_outputs_stale() -> None:
    case = next(item for item in DATA["cases"] if item["case_id"] == "case_05_tu1_then_tu2")
    result = _generate(case)
    old_combined = result["combined_construct"]["dna"]
    old_signature = result["combined_construct"]["input_signature"]
    runtime = set_multi_tu_unit_order(result["runtime"], ["TU2", "TU1"])

    assert active_construct_snapshot(runtime)["construct_status"] == "stale"
    assert active_complete_plasmid_snapshot(runtime)["construct_status"] == "stale"
    with pytest.raises(CanonicalConstructRuntimeError, match="Stale|Blocking-invalid"):
        export_multi_tu_outputs(runtime, project_name="stale")

    runtime = generate_active_construct(runtime)
    runtime = generate_active_complete_plasmid(runtime)
    regenerated = multi_tu_snapshot(runtime)
    assert regenerated["combined_construct"]["dna"] != old_combined
    assert regenerated["combined_construct"]["input_signature"] != old_signature
    assert regenerated["unit_order"] == ["TU2", "TU1"]


def test_orientation_change_reverse_complements_entire_unit_and_marks_outputs_stale() -> None:
    case = next(item for item in DATA["cases"] if item["case_id"] == "case_01_forward_forward")
    result = _generate(case)
    original_tu2 = next(unit for unit in result["expression_units"] if unit["unit_id"] == "TU2")["dna"]
    runtime = set_multi_tu_unit_orientation(result["runtime"], unit_id="TU2", orientation="reverse")
    assert active_construct_snapshot(runtime)["construct_status"] == "stale"
    runtime = generate_active_construct(runtime)
    runtime = generate_active_complete_plasmid(runtime)
    regenerated = multi_tu_snapshot(runtime)
    reversed_tu2 = next(unit for unit in regenerated["expression_units"] if unit["unit_id"] == "TU2")
    assert reversed_tu2["dna"] == _reverse_complement(original_tu2)
    assert reversed_tu2["range"]["strand"] == -1
    assert {row["strand"] for row in reversed_tu2["components"]} == {-1}


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda units: [], "at least one"),
        (lambda units: units + [deepcopy(units[0])], "distinct"),
        (lambda units: [units[0], {**units[1], "unit_id": "TU1"}], "distinct"),
        (lambda units: [{**units[0], "orientation": "sideways"}, units[1]], "orientation"),
        (lambda units: [{**units[0], "order": 1}, {**units[1], "order": 1}], "order"),
    ],
)
def test_structural_error_cases_are_rejected(mutator, message: str) -> None:
    case = DATA["cases"][0]
    with pytest.raises(MvpMultiTuRuntimeError, match=message):
        generate_multi_tu_construct(
            project_id="mvp9-invalid",
            project_name="invalid",
            expression_units=mutator(_units_for_case(case)),
            backbone={"raw_text": _make_backbone_genbank(), "source_format": "genbank"},
            insertion_settings={"mode": "insertion", "start_coordinate": 40, "end_coordinate": 41},
        )


@pytest.mark.parametrize("remaining_index", [0, 1], ids=["first_unit", "second_unit"])
def test_one_ordered_expression_unit_remains_structurally_valid(remaining_index: int) -> None:
    units = _units_for_case(DATA["cases"][0])
    unit = {**units[remaining_index], "order": 1}
    result = generate_multi_tu_construct(
        project_id=f"mvp9-one-unit-{remaining_index}",
        project_name="one ordered unit",
        expression_units=[unit],
        backbone={"raw_text": _make_backbone_genbank(), "source_format": "genbank"},
        insertion_settings={"mode": "insertion", "start_coordinate": 40, "end_coordinate": 41},
    )
    assert result["unit_order"] == [unit["unit_id"]]
    assert result["combined_construct"]["total_length"] == result["expression_units"][0]["length"]


@pytest.mark.parametrize(
    ("bad_cds", "rule"),
    [
        ("ATGAAAXXXTAA", "invalid_dna_character"),
        ("ATGGCCTAAGGGTAA", "internal_in_frame_stop_codon"),
    ],
)
def test_invalid_or_internal_stop_cds_is_rejected(bad_cds: str, rule: str) -> None:
    units = _units_for_case(DATA["cases"][0])
    units[1]["cds"]["sequence"] = bad_cds
    with pytest.raises(MvpMultiTuRuntimeError, match=rule):
        generate_multi_tu_construct(
            project_id="mvp9-bad-cds",
            project_name="bad cds",
            expression_units=units,
            backbone={"raw_text": _make_backbone_genbank(), "source_format": "genbank"},
            insertion_settings={"mode": "insertion", "start_coordinate": 40, "end_coordinate": 41},
        )


def test_non_cds_component_with_invalid_dna_character_is_rejected() -> None:
    units = _units_for_case(DATA["cases"][0])
    units[0]["promoter"]["sequence"] = "AACCGGN"
    with pytest.raises(MvpMultiTuRuntimeError, match="promoter contains invalid DNA character"):
        generate_multi_tu_construct(
            project_id="mvp9-bad-promoter",
            project_name="bad promoter",
            expression_units=units,
            backbone={"raw_text": _make_backbone_genbank(), "source_format": "genbank"},
            insertion_settings={"mode": "insertion", "start_coordinate": 40, "end_coordinate": 41},
        )


def test_backbone_coordinates_outside_bounds_are_rejected() -> None:
    with pytest.raises(MvpMultiTuRuntimeError, match="insertion_interval_outside_backbone_bounds"):
        generate_multi_tu_construct(
            project_id="mvp9-bad-site",
            project_name="bad site",
            expression_units=_units_for_case(DATA["cases"][0]),
            backbone={"raw_text": _make_backbone_genbank(), "source_format": "genbank"},
            insertion_settings={
                "mode": "replacement",
                "start_coordinate": 121,
                "end_coordinate": 122,
                "expected_removed_sequence": "AA",
            },
        )


def test_single_gene_runtime_cannot_be_read_as_multi_tu() -> None:
    with pytest.raises(MvpMultiTuRuntimeError, match="not a multi_tu"):
        multi_tu_snapshot({"project_id": "single-gene"})


def test_complete_genbank_has_two_unit_ranges_and_six_component_features() -> None:
    result = _generate(DATA["cases"][1])
    record = next(SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank"))
    labels = [(feature.qualifiers.get("label") or [""])[0] for feature in record.features]
    assert labels.count("DUAL_UNIT_ALPHA") == 1
    assert labels.count("DUAL_UNIT_BETA") == 1
    assert sum(label.startswith("PROMOTER_") for label in labels) == 2
    assert sum(label.startswith("CDS_") for label in labels) == 2
    assert sum(label.startswith("TERMINATOR_") for label in labels) == 2
    assert export_active_complete_plasmid(result["runtime"], project_name="repeat")["genbank"]["data"] == result["exports"]["complete_plasmid_genbank"]["data"]


def test_two_tu_assembly_contract_exports_only_the_linear_canonical_sequence() -> None:
    case = DATA["cases"][1]
    result = generate_multi_tu_combined_construct(
        project_id="two-tu-assembly-contract",
        project_name="Two TU assembly contract",
        expression_units=_units_for_case(case),
    )

    assert result["result_kind"] == MULTI_TU_EXPRESSION_ASSEMBLY
    assert result["workflow_kind"] == "generic_multi_tu"
    assert result["contains_vector"] is False
    assert "complete_plasmid" not in result
    assert set(result["exports"]) == {
        "unit_fastas",
        "combined_construct_fasta",
        "combined_construct_genbank",
        "metadata",
    }

    fasta = next(
        SeqIO.parse(StringIO(result["exports"]["combined_construct_fasta"]["data"]), "fasta")
    )
    genbank = next(
        SeqIO.parse(StringIO(result["exports"]["combined_construct_genbank"]["data"]), "genbank")
    )
    canonical = result["combined_construct"]["dna"]
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    assert "workflow=Multi-TU" in fasta.description
    assert "tu_count=2" in fasta.description
    assert f"result_kind={MULTI_TU_EXPRESSION_ASSEMBLY}" in fasta.description
    assert "contains_vector=false" in fasta.description
    assert genbank.annotations["topology"] == "linear"
    assert MULTI_TU_EXPRESSION_ASSEMBLY in str(genbank.annotations.get("comment") or "")
    feature_types = {feature.type for feature in genbank.features}
    assert sum("unit_id" in feature.qualifiers for feature in genbank.features) == 8
    assert sum(feature.type == "misc_feature" for feature in genbank.features) == 2
    assert sum(feature.type == "promoter" for feature in genbank.features) == 2
    assert sum(feature.type == "cds" for feature in genbank.features) == 2
    assert sum(feature.type == "terminator" for feature in genbank.features) == 2
    component_features = [
        feature for feature in genbank.features if feature.type != "misc_feature"
    ]
    assert all(feature.qualifiers.get("component_id") for feature in component_features)
    assert all(feature.qualifiers.get("source_asset_id") for feature in component_features)
    assert not feature_types.intersection({"rep_origin", "oriT", "T-DNA", "selectable_marker"})


def test_release_fixture_seed_keeps_multi_tu_exports_equal_across_fresh_projects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seed = "v1-formal-multi-tu-blank-fixture-v1"
    case = DATA["cases"][1]
    run_root = tmp_path / "acceptance-run"
    run_root.mkdir()
    for name in (
        "BIODESIGN_ACCEPTANCE_FIXTURE_ID",
        "BIODESIGN_ACCEPTANCE_FIXTURE_MODE",
        "BIODESIGN_ACCEPTANCE_RUN_ROOT",
        "BIODESIGN_ACCEPTANCE_FIXTURE_CAPABILITY_FILE",
        "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_HANDLE",
        "BIODESIGN_ACCEPTANCE_FIXTURE_AUTHORITY_ID",
        "BIODESIGN_ACCEPTANCE_PRE_PRODUCTION_DB_PATH",
        "BIODESIGN_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    configure_acceptance_fixture_context(
        seed=seed,
        run_root=run_root,
        database_path=run_root / "isolated" / "biodesign_unified.db",
        pre_acceptance_production_database_path=snapshot_active_production_database(),
    )
    first = generate_multi_tu_combined_construct(
        project_id="run-a-project-instance",
        project_name="V1 formal Multi-TU blank fixture",
        expression_units=deepcopy(_units_for_case(case)),
    )
    second = generate_multi_tu_combined_construct(
        project_id="run-b-project-instance",
        project_name="V1 formal Multi-TU blank fixture",
        expression_units=deepcopy(_units_for_case(case)),
    )

    assert first["project_id"] != second["project_id"]
    assert first["combined_construct"]["dna"] == second["combined_construct"]["dna"]
    assert [
        asset["asset_id"] for asset in first["runtime"]["sequence_assets"]
    ] == [asset["asset_id"] for asset in second["runtime"]["sequence_assets"]]
    assert first["exports"]["combined_construct_fasta"]["data"] == second["exports"]["combined_construct_fasta"]["data"]
    assert first["exports"]["combined_construct_genbank"]["data"] == second["exports"]["combined_construct_genbank"]["data"]
    clear_acceptance_fixture_context()
    os.environ.pop("BIODESIGN_DB_PATH", None)


def test_release_fixture_identity_provider_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BIODESIGN_ACCEPTANCE_FIXTURE_ID", raising=False)
    assert runtime_identity("tu") != runtime_identity("tu")


@pytest.mark.parametrize(
    ("role", "message"),
    [
        ("promoter", "promoter"),
        ("cds", "cds"),
        ("terminator", "3_prime_regulatory_region"),
    ],
)
def test_assembly_rejects_each_missing_required_component(role: str, message: str) -> None:
    units = _units_for_case(DATA["cases"][0])
    units[0][role] = {}
    with pytest.raises(MvpMultiTuRuntimeError, match=message):
        generate_multi_tu_combined_construct(
            project_id=f"missing-{role}",
            project_name="Missing required component",
            expression_units=units,
        )
