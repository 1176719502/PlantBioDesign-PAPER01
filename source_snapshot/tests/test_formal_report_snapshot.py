from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from services.formal_report_snapshot import (
    FormalReportSnapshotError,
    build_formal_report_snapshot,
    build_multi_tu_snapshot,
    build_pathway_snapshot,
    build_single_gene_snapshot,
    validate_formal_report_snapshot,
)


HASH_A = "0123456789abcdef" * 4
HASH_B = "fedcba9876543210" * 4


def _snapshot() -> dict:
    return build_formal_report_snapshot(
        workflow_type="single_gene",
        freshness={"state": "current"},
        project={"project_id": "project-7", "name": "Documentation case"},
        host={"name": "Nicotiana benthamiana"},
        design_goal={"summary": "Record an expression-vector design for review."},
        component_summary={"count": 3},
        construct_summary={"canonical_length_bp": 12, "canonical_hash": HASH_A, "topology": "circular"},
        feature_summary={"feature_count": 3},
        validation_summary={"blocking_count": 0, "warning_count": 1},
        provenance_summary={"source_count": 2},
        delivery_artifacts=[{"artifact_id": "complete_fasta", "size_bytes": 24, "sha256": HASH_B}],
        route_specific_data={"route": "single_gene"},
    )


def _with_recomputed_snapshot_id(snapshot: dict) -> dict:
    resigned = dict(snapshot)
    payload = {key: value for key, value in resigned.items() if key != "snapshot_id"}
    resigned["snapshot_id"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return resigned


def test_snapshot_is_deterministic_has_stable_identity_and_validates_schema() -> None:
    first = _snapshot()
    second = _snapshot()

    assert first == second
    assert len(first["snapshot_id"]) == 64
    assert validate_formal_report_snapshot(first) == first

    changed = dict(first)
    changed["snapshot_id"] = "0" * 64
    with pytest.raises(FormalReportSnapshotError, match="Snapshot ID"):
        validate_formal_report_snapshot(changed)

    invalid_format = dict(first)
    invalid_format["snapshot_id"] = "not-a-hash"
    with pytest.raises(FormalReportSnapshotError, match="64-character hexadecimal"):
        validate_formal_report_snapshot(invalid_format)


def test_snapshot_integrity_error_precedes_component_schema_error() -> None:
    malformed = _snapshot()
    malformed["component_summary"] = {"components": "not-a-list"}

    with pytest.raises(FormalReportSnapshotError, match="Snapshot ID does not match deterministic contents"):
        validate_formal_report_snapshot(malformed)


def test_recomputed_snapshot_identity_reaches_component_schema_error() -> None:
    malformed = _snapshot()
    malformed["component_summary"] = {"components": "not-a-list"}

    with pytest.raises(FormalReportSnapshotError, match="component_summary.components.*list"):
        validate_formal_report_snapshot(_with_recomputed_snapshot_id(malformed))


@pytest.mark.parametrize(
    ("path", "value", "schema_error"),
    [
        (("freshness",), "current", "field 'freshness' must be a mapping"),
        (("validation_summary",), "ok", "field 'validation_summary' must be a mapping"),
        (("construct_summary",), None, "field 'construct_summary' must be a mapping"),
        (("component_summary",), [], "field 'component_summary' must be a mapping"),
        (("component_summary", "components"), {"source": "registry"}, "component_summary.components.*list"),
        (("component_summary", "components"), [123], "components\\[0\\] must be a mapping"),
        (("route_specific_data",), "text", "field 'route_specific_data' must be a mapping"),
        (("delivery_artifacts",), "FASTA", "delivery_artifacts.*list"),
    ],
)
def test_malformed_containers_use_integrity_before_exact_schema(
    path: tuple[str, ...], value: object, schema_error: str
) -> None:
    stale = _snapshot()
    stale_target = stale
    for key in path[:-1]:
        stale_target = stale_target[key]
    stale_target[path[-1]] = value

    with pytest.raises(FormalReportSnapshotError, match="Snapshot ID does not match deterministic contents"):
        validate_formal_report_snapshot(stale)
    with pytest.raises(FormalReportSnapshotError, match=schema_error):
        validate_formal_report_snapshot(_with_recomputed_snapshot_id(stale))


@pytest.mark.parametrize(
    "components",
    [
        "text",
        {"source": "registry"},
        1,
        None,
        [123],
        ["source"],
        [{"source": "registry"}],
    ],
)
def test_snapshot_requires_exact_typed_component_records(components: object) -> None:
    with pytest.raises(FormalReportSnapshotError, match="component_summary.components"):
        build_formal_report_snapshot(
            workflow_type="single_gene",
            component_summary={"components": components},
        )


@pytest.mark.parametrize(
    "section",
    [
        {"raw_dna": "ATGCGTATGCGT"},
        {"fasta_text": ">record\nATGCGT\n"},
        {"genbank_text": "LOCUS record"},
        {"primer_rows": [{"name": "P1"}]},
        {"session_payload": {"anything": "value"}},
        {"database_payload": {"anything": "value"}},
    ],
)
def test_snapshot_rejects_raw_sequences_exports_primers_and_arbitrary_runtime_payloads(section: dict) -> None:
    with pytest.raises(FormalReportSnapshotError):
        build_formal_report_snapshot(workflow_type="single_gene", construct_summary=section)


@pytest.mark.parametrize(
    "section_name, section",
    [
        ("construct_summary", {"canonical_hash": "ATGCGTATGCGTATGCGT"}),
        ("component_summary", {"accession": "ATGCGTATGCGT"}),
        ("component_summary", {"accession": "ATGCGTAT GCATGCAT"}),
        ("component_summary", {"accession": "ATGCGTAT\nGCATGCAT"}),
        ("component_summary", {"accession": "5'-ATGCGTATGCGT-3'"}),
        ("component_summary", {"accession": "5\u2032-ATGCGTATGCGT 3\u2032"}),
        ("component_summary", {"accession": "a t g c g t a t"}),
        ("component_summary", {"name": "ATGCGTATGCGT"}),
        ("provenance_summary", {"notes": "ATGCGTATGCGT"}),
        ("provenance_summary", {"provenance": {"detail": "ATGCGTATGCGT"}}),
        ("route_specific_data", {"nested": {"fragment": "ATGCGTATGCGT"}}),
        ("route_specific_data", {"nested": {"fragments": ["ATGCGTAT"]}}),
        ("route_specific_data", {"nested": {"fasta_body": ">record\nATGCGT"}}),
        ("route_specific_data", {"nested": {"genbank_body": "ORIGIN\n        1 atgcgt"}}),
        ("route_specific_data", {"nested": {"primer_like": "atgcgtat"}}),
    ],
)
def test_snapshot_recursively_rejects_sequence_smuggling_in_every_field(section_name: str, section: dict) -> None:
    kwargs = {section_name: section}

    with pytest.raises(FormalReportSnapshotError):
        build_formal_report_snapshot(workflow_type="single_gene", **kwargs)


def test_snapshot_rejects_non_sha256_hashes_without_treating_hash_field_names_as_safe() -> None:
    with pytest.raises(FormalReportSnapshotError, match="64-character hexadecimal"):
        build_formal_report_snapshot(
            workflow_type="single_gene",
            construct_summary={"canonical_hash": "not-a-real-hash"},
        )


def test_snapshot_retains_a_valid_acgt_only_sha256_for_local_traceability() -> None:
    nucleotide_looking_hash = "AC" * 32
    snapshot = build_formal_report_snapshot(
        workflow_type="single_gene",
        construct_summary={"canonical_hash": nucleotide_looking_hash},
    )

    assert snapshot["construct_summary"]["canonical_hash"] == nucleotide_looking_hash


def test_only_exact_snapshot_paths_may_retain_nucleotide_looking_hashes() -> None:
    nucleotide_looking_hash = "AC" * 32
    snapshot = build_formal_report_snapshot(
        workflow_type="single_gene",
        construct_summary={"canonical_hash": nucleotide_looking_hash},
        delivery_artifacts=[{"artifact_id": "fasta", "sha256": nucleotide_looking_hash}],
    )

    assert snapshot["construct_summary"]["canonical_hash"] == nucleotide_looking_hash
    assert snapshot["delivery_artifacts"][0]["sha256"] == nucleotide_looking_hash
    with pytest.raises(FormalReportSnapshotError, match="raw DNA"):
        build_formal_report_snapshot(
            workflow_type="single_gene",
            route_specific_data={"canonical_hash": nucleotide_looking_hash},
        )


def test_snapshot_module_has_no_suffix_hash_matching() -> None:
    import services.formal_report_snapshot as module

    calls = [node for node in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(node, ast.Call)]

    assert not any(isinstance(call.func, ast.Attribute) and call.func.attr == "endswith" for call in calls)


def test_snapshot_module_has_no_runtime_state_or_persistence_imports() -> None:
    import services.formal_report_snapshot as module

    imports = [node.names[0].name for node in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(node, ast.Import)]
    from_imports = [node.module or "" for node in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(node, ast.ImportFrom)]

    assert not any(name.startswith(("streamlit", "sqlite3")) for name in imports + from_imports)
    assert "st.session_state" not in inspect.getsource(module)


def test_single_gene_adapter_uses_explicit_canonical_facts_and_export_hashes_only() -> None:
    snapshot = build_single_gene_snapshot(
        result={
            "project_id": "single-1",
            "project_name": "Single gene record",
            "input_signature": "fresh-inputs",
            "exports": {"complete_plasmid_fasta": {"data": ">x\nATGCGT\n", "file_name": "complete.fasta"}},
        },
        cassette={"sequence_length": 6, "sequence_checksum": HASH_A, "components": [{"id": "p35s", "name": "CaMV 35S", "role": "promoter", "length_bp": 3}]},
        plasmid={"construct_status": "current", "sequence_length": 12, "sequence_checksum": HASH_B, "topology": "circular", "validation_summary": {"blocking_count": 0}},
    )

    assert snapshot["workflow_type"] == "single_gene"
    assert snapshot["construct_summary"]["canonical_hash"] == HASH_B
    assert snapshot["component_summary"]["components"][0]["component_id"] == "p35s"
    assert snapshot["delivery_artifacts"][0]["sha256"]
    assert "ATGCGT" not in repr(snapshot)


def test_multi_tu_adapter_keeps_order_orientation_components_and_ranges() -> None:
    snapshot = build_multi_tu_snapshot(
        multi_tu_result={
            "transcription_units": [
                {"tu_id": "TU2", "orientation": "reverse", "length_bp": 20, "components": [{"name": "Gene B", "role": "CDS", "length_bp": 9}], "ranges": [{"name": "Gene B", "start": 5, "end": 13, "strand": -1}]},
                {"tu_id": "TU1", "orientation": "forward", "length_bp": 18, "components": [{"name": "Gene A", "role": "CDS", "length_bp": 8}]},
            ],
            "canonical_construct": {"sequence_length": 100, "sequence_checksum": HASH_A, "topology": "circular"},
        }
    )

    units = snapshot["route_specific_data"]["ordered_transcription_units"]
    assert [unit["tu_id"] for unit in units] == ["TU2", "TU1"]
    assert units[0]["orientation"] == "reverse"
    assert units[0]["ranges"][0]["start"] == 5
    assert [component["name"] for component in snapshot["component_summary"]["components"]] == ["Gene B", "Gene A"]


def test_pathway_adapter_does_not_invent_a_missing_canonical_construct() -> None:
    snapshot = build_pathway_snapshot(pathway_facts={"project": {"project_id": "path-1"}, "route_specific_data": {"step_count": 3}})

    assert snapshot["workflow_type"] == "pathway"
    assert snapshot["construct_summary"]["canonical_construct_present"] is False
    assert snapshot["component_summary"]["components"] == []
