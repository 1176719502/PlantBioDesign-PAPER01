from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "scripts" / "probe_plant_expression_construct_capabilities.py"
COMMITTED_MANIFEST_PATH = (
    ROOT / "docs" / "qa" / "data_manifests" / "v2_7_r226_real_construct_capability_matrix.json"
)


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("r226_probe_module", PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capability_by_name(manifest: dict, name: str) -> dict:
    return next(item for item in manifest["capabilities"] if item["capability"] == name)


def test_synthetic_reference_values_are_exact_and_stable() -> None:
    probe = _load_probe_module()
    inputs = probe.synthetic_inputs()

    expected_sequence = (
        inputs["promoter_sequence"] + inputs["cds_sequence"] + inputs["terminator_sequence"]
    )
    expected_features = [
        {"name": inputs["promoter_name"], "type": "promoter", "start": 1, "end": 14},
        {"name": inputs["cds_name"], "type": "CDS", "start": 15, "end": 29},
        {"name": inputs["terminator_name"], "type": "terminator", "start": 30, "end": 41},
    ]
    expected_translation = "MAEL*"
    expected_sha256 = hashlib.sha256(expected_sequence.encode("utf-8")).hexdigest()

    assert inputs["expected_concatenated_sequence"] == expected_sequence
    assert inputs["expected_features"] == expected_features
    assert inputs["expected_total_length"] == 41
    assert inputs["expected_cds_translation"] == expected_translation
    assert inputs["expected_sha256"] == expected_sha256


def test_probe_reports_expected_construct_sequence_coordinates_translation_and_checksum(tmp_path: Path) -> None:
    probe = _load_probe_module()
    manifest = probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="test-head",
        runtime_root=tmp_path / "runtime",
    )
    inputs = probe.synthetic_inputs()

    assembled = _capability_by_name(manifest, "Generated concatenated DNA")
    coordinates = _capability_by_name(manifest, "Deterministic feature coordinates")
    translation = _capability_by_name(manifest, "CDS translation")
    checksum = _capability_by_name(manifest, "Sequence checksum")

    assert assembled["classification"] == "WORKING"
    assert assembled["observed_result"]["final_sequence"] == inputs["expected_concatenated_sequence"]
    assert assembled["observed_result"]["total_length"] == inputs["expected_total_length"]
    assert coordinates["classification"] == "WORKING"
    assert coordinates["observed_result"]["features"] == inputs["expected_features"]
    assert translation["classification"] == "WORKING"
    assert translation["observed_result"]["translation"] == inputs["expected_cds_translation"]
    assert checksum["classification"] == "WORKING"
    assert checksum["observed_result"]["sha256"] == inputs["expected_sha256"]


def test_manifest_schema_is_stable_and_writable(tmp_path: Path) -> None:
    probe = _load_probe_module()
    output_path = tmp_path / "manifest.json"
    manifest = probe.write_manifest(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="schema-head",
        runtime_root=tmp_path / "runtime",
        manifest_path=output_path,
    )

    probe.validate_manifest_schema(manifest)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    probe.validate_manifest_schema(saved)

    assert saved["repository_head"] == "schema-head"
    assert saved["schema_version"] == "v2.7.r226.real_construct_capability_matrix.v1"
    assert isinstance(saved["capabilities"], list)
    assert len(saved["capabilities"]) >= 20


def test_committed_manifest_matches_current_probe_output(tmp_path: Path) -> None:
    probe = _load_probe_module()
    committed = json.loads(COMMITTED_MANIFEST_PATH.read_text(encoding="utf-8"))
    generated = probe.run_probe(
        audit_timestamp=committed["audit_timestamp"],
        repo_head=committed["repository_head"],
        runtime_root=tmp_path / "runtime",
    )

    probe.validate_manifest_schema(committed)

    assert committed["schema_version"] == generated["schema_version"]
    assert committed["probe_script_requested_path"] == generated["probe_script_requested_path"]
    assert committed["probe_script_actual_path"] == generated["probe_script_actual_path"]
    assert committed["synthetic_reference_input"] == generated["synthetic_reference_input"]
    assert committed["probe_runtime_paths"] == generated["probe_runtime_paths"]
    assert committed["asset_inventory"] == generated["asset_inventory"]
    assert committed["implementation_inventory"] == generated["implementation_inventory"]
    assert committed["capabilities"] == generated["capabilities"]
    assert committed["single_nearest_product_breakpoint"] == generated["single_nearest_product_breakpoint"]
    assert committed["recommended_gate1_task"] == generated["recommended_gate1_task"]
    assert committed["summary"] == generated["summary"]


def test_missing_and_display_only_capabilities_are_reported_honestly(tmp_path: Path) -> None:
    probe = _load_probe_module()
    manifest = probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="truth-head",
        runtime_root=tmp_path / "runtime",
    )

    assert _capability_by_name(manifest, "Backbone insertion")["classification"] == "MISSING"
    assert _capability_by_name(manifest, "Runtime UI construct editing")["classification"] == "DISPLAY_ONLY"
    assert _capability_by_name(manifest, "Canonical SequenceAsset")["classification"] == "MISSING"
    assert _capability_by_name(manifest, "Annotated GenBank export")["classification"] == "PARTIAL"


def test_probe_does_not_touch_r224_user_data_or_r225_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe_module()
    user_data_dir = tmp_path / "user_r224_data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    sentinel = user_data_dir / "existing_user_draft.json"
    sentinel.write_text('{"keep":"original"}\n', encoding="utf-8")
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(user_data_dir))

    corpus_before = probe.R225_CORPUS_PATH.read_text(encoding="utf-8")
    sentinel_before = sentinel.read_text(encoding="utf-8")

    probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="data-guard-head",
        runtime_root=tmp_path / "runtime",
    )

    assert sentinel.read_text(encoding="utf-8") == sentinel_before
    assert probe.R225_CORPUS_PATH.read_text(encoding="utf-8") == corpus_before


def test_probe_does_not_access_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe_module()

    def _deny(*_args, **_kwargs):
        raise AssertionError("network access is not allowed during the probe")

    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(socket.socket, "connect", _deny, raising=False)

    manifest = probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="network-head",
        runtime_root=tmp_path / "runtime",
    )

    assert _capability_by_name(manifest, "Generated concatenated DNA")["classification"] == "WORKING"


def test_probe_output_is_deterministic_across_two_runs(tmp_path: Path) -> None:
    probe = _load_probe_module()
    first = probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="deterministic-head",
        runtime_root=tmp_path / "runtime_one",
    )
    second = probe.run_probe(
        audit_timestamp="2026-07-10T12:00:00Z",
        repo_head="deterministic-head",
        runtime_root=tmp_path / "runtime_two",
    )

    assert first == second
