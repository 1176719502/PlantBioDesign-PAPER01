from __future__ import annotations

import copy
import hashlib

import pytest

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
)
from services.canonical_genbank_inspector_adapter import (
    AUTHORITATIVE_GENBANK_SOURCE,
    AUTHORITATIVE_IDENTITY_SOURCE,
    inspect_canonical_genbank_export,
)


SEQUENCES = {
    "promoter": "TTGACATATAAAGG",
    "cds": "ATGGCTGAACTGTAA",
    "terminator": "GCGTTTTTTGCG",
}


def _generated_runtime() -> dict:
    runtime = blank_runtime("canonical-inspector-adapter")
    component_ids = []
    for component_type, sequence in SEQUENCES.items():
        asset = create_sequence_asset(
            project_id="canonical-inspector-adapter",
            display_name=f"ADAPTER_{component_type.upper()}",
            raw_text=sequence,
            molecule_type="dna",
            source_type="paste",
            source_format="plain",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id="canonical-inspector-adapter",
            component_type=component_type,
            display_name=f"ADAPTER_{component_type.upper()}",
            sequence_asset_id=asset["asset_id"],
        )
        runtime = upsert_component(runtime, component)
        component_ids.append(component["component_id"])
    runtime = set_active_component_order(runtime, component_ids)
    return generate_active_construct(runtime)


def _canonical_export(runtime: dict | None = None) -> tuple[dict, dict[str, str]]:
    runtime = runtime or _generated_runtime()
    snapshot = active_construct_snapshot(runtime)
    identity = {
        "construct_id": snapshot["construct_id"],
        "revision_id": snapshot["revision_id"],
    }
    return (
        export_active_construct(runtime, project_name="CANONICAL_ADAPTER_RECORD"),
        identity,
    )


def _inspect(canonical_export: dict, identity: dict[str, str]) -> dict:
    return inspect_canonical_genbank_export(
        canonical_export,
        expected_construct_id=identity["construct_id"],
        expected_revision_id=identity["revision_id"],
    )


def _failed_check_ids(result: dict) -> set[str]:
    return {
        check["check_id"]
        for check in result["identity_binding"].get("checks", [])
        if not check["matches"]
    }


def test_existing_canonical_export_bytes_enter_inspector_with_identity_binding_and_no_mutation() -> None:
    canonical_export, identity = _canonical_export()
    before = copy.deepcopy(canonical_export)
    raw_bytes = canonical_export["genbank"]["data"].encode("utf-8")

    result = _inspect(canonical_export, identity)

    assert result["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert result["identity_binding"]["status"] == "PASS"
    assert result["inspection"] is not None
    assert result["inspection"]["sequence_sha256"] == canonical_export["metadata"]["sequence_checksum"]
    assert result["inspection"]["sequence_length"] == canonical_export["metadata"]["sequence_length"]
    assert result["inspection"]["topology"] == "linear"
    assert result["identity_binding"]["authoritative_construct_id"] == identity["construct_id"]
    assert result["identity_binding"]["authoritative_revision_id"] == identity["revision_id"]
    assert result["identity_binding"]["export_construct_id"] == canonical_export["metadata"]["construct_id"]
    assert result["identity_binding"]["export_revision_id"] == canonical_export["metadata"]["revision_id"]
    assert result["provenance"]["source_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert result["provenance"]["authoritative_genbank_source"] == AUTHORITATIVE_GENBANK_SOURCE
    assert result["provenance"]["authoritative_identity_source"] == AUTHORITATIVE_IDENTITY_SOURCE
    assert result["provenance"]["sequence_mutation"] == "none"
    assert canonical_export == before


@pytest.mark.parametrize(
    ("metadata_field", "replacement", "failed_check"),
    [
        ("sequence_length", 999, "sequence_length"),
        ("sequence_checksum", "0" * 64, "sequence_sha256"),
        ("topology", "circular", "topology"),
        ("record_id", "different_record", "record_identifier"),
    ],
)
def test_inconsistent_canonical_identity_fails_closed(
    metadata_field: str,
    replacement: object,
    failed_check: str,
) -> None:
    canonical_export, identity = _canonical_export()
    canonical_export["metadata"][metadata_field] = replacement

    result = _inspect(canonical_export, identity)

    assert result["status"] == "FAIL"
    assert result["identity_binding"]["status"] == "FAIL"
    assert failed_check in _failed_check_ids(result)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("metadata"),
        lambda payload: payload["metadata"].pop("sequence_checksum"),
        lambda payload: payload["metadata"].pop("revision_id"),
        lambda payload: payload["genbank"].update({"data": b"not a GenBank record"}),
        lambda payload: payload["genbank"].update({"data": "not a GenBank record \u00e9"}),
    ],
)
def test_malformed_or_incomplete_canonical_export_fails_closed(mutate) -> None:
    canonical_export, identity = _canonical_export()
    mutate(canonical_export)

    result = _inspect(canonical_export, identity)

    assert result["status"] == "FAIL"
    assert result["errors"]


def test_bytes_payload_is_accepted_without_changing_authoritative_content() -> None:
    canonical_export, identity = _canonical_export()
    raw_bytes = canonical_export["genbank"]["data"].encode("utf-8")
    canonical_export["genbank"]["data"] = raw_bytes

    result = _inspect(canonical_export, identity)

    assert result["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert result["provenance"]["source_kind"] == "bytes"
    assert result["provenance"]["source_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert canonical_export["genbank"]["data"] is raw_bytes


@pytest.mark.parametrize(
    ("metadata_field", "replacement", "failed_check"),
    [
        ("construct_id", "construct-" + "0" * 32, "construct_id"),
        ("revision_id", "rev-" + "0" * 16, "revision_id"),
    ],
)
def test_export_identity_tamper_fails_against_independent_runtime_authority(
    metadata_field: str,
    replacement: str,
    failed_check: str,
) -> None:
    canonical_export, identity = _canonical_export()
    original_genbank = canonical_export["genbank"]["data"]
    canonical_export["metadata"][metadata_field] = replacement

    result = _inspect(canonical_export, identity)

    assert result["status"] == "FAIL"
    assert _failed_check_ids(result) == {failed_check}
    assert canonical_export["genbank"]["data"] == original_genbank


@pytest.mark.parametrize(
    ("expected_construct_id", "expected_revision_id", "message_fragment"),
    [
        (None, "rev-" + "1" * 16, "construct identity is missing"),
        ("", "rev-" + "1" * 16, "construct identity is missing"),
        ("construct-" + "1" * 32, None, "revision identity is missing"),
        ("construct-" + "1" * 32, "", "revision identity is missing"),
    ],
)
def test_missing_expected_identity_fails_closed(
    expected_construct_id: str | None,
    expected_revision_id: str | None,
    message_fragment: str,
) -> None:
    canonical_export, _identity = _canonical_export()

    result = inspect_canonical_genbank_export(
        canonical_export,
        expected_construct_id=expected_construct_id,
        expected_revision_id=expected_revision_id,
    )

    assert result["status"] == "FAIL"
    assert result["inspection"] is None
    assert any(message_fragment in error for error in result["errors"])


@pytest.mark.parametrize(
    ("expected_construct_id", "expected_revision_id", "message_fragment"),
    [
        ("construct-not-canonical", "rev-" + "1" * 16, "construct identity is malformed"),
        ("construct-" + "1" * 32, "revision-current", "revision identity is malformed"),
    ],
)
def test_malformed_expected_identity_fails_closed(
    expected_construct_id: str,
    expected_revision_id: str,
    message_fragment: str,
) -> None:
    canonical_export, _identity = _canonical_export()

    result = inspect_canonical_genbank_export(
        canonical_export,
        expected_construct_id=expected_construct_id,
        expected_revision_id=expected_revision_id,
    )

    assert result["status"] == "FAIL"
    assert any(message_fragment in error for error in result["errors"])


@pytest.mark.parametrize(
    ("metadata_field", "replacement", "message_fragment"),
    [
        ("construct_id", None, "construct identity metadata is missing"),
        ("construct_id", "construct-not-canonical", "construct identity metadata is malformed"),
        ("revision_id", None, "revision identity metadata is missing"),
        ("revision_id", "revision-current", "revision identity metadata is malformed"),
    ],
)
def test_blank_null_or_malformed_export_identity_fails_closed(
    metadata_field: str,
    replacement: object,
    message_fragment: str,
) -> None:
    canonical_export, identity = _canonical_export()
    canonical_export["metadata"][metadata_field] = replacement

    result = _inspect(canonical_export, identity)

    assert result["status"] == "FAIL"
    assert any(message_fragment in error for error in result["errors"])


def test_stale_export_revision_fails_against_current_runtime_revision() -> None:
    runtime = _generated_runtime()
    stale_export, stale_identity = _canonical_export(runtime)
    changed_component = copy.deepcopy(runtime["components"][0])
    changed_component["orientation"] = "reverse"
    current_runtime = generate_active_construct(upsert_component(runtime, changed_component))
    current_snapshot = active_construct_snapshot(current_runtime)

    assert current_snapshot["construct_id"] == stale_identity["construct_id"]
    assert current_snapshot["revision_id"] != stale_identity["revision_id"]

    result = inspect_canonical_genbank_export(
        stale_export,
        expected_construct_id=current_snapshot["construct_id"],
        expected_revision_id=current_snapshot["revision_id"],
    )

    assert result["status"] == "FAIL"
    assert _failed_check_ids(result) == {"revision_id"}


def test_byte_identical_genbank_from_another_construct_fails_identity_binding() -> None:
    runtime = _generated_runtime()
    original_export, original_identity = _canonical_export(runtime)
    other_runtime = copy.deepcopy(runtime)
    other_construct_id = "construct-" + "f" * 32
    assert other_construct_id != original_identity["construct_id"]
    other_runtime["constructs"][0]["construct_id"] = other_construct_id
    other_runtime["constructs"][0]["persistence_identity"] = other_construct_id
    other_runtime["active_construct_id"] = other_construct_id
    other_export, other_identity = _canonical_export(other_runtime)

    assert other_export["genbank"]["data"] == original_export["genbank"]["data"]
    assert other_identity["revision_id"] == original_identity["revision_id"]

    result = _inspect(other_export, original_identity)

    assert result["status"] == "FAIL"
    assert _failed_check_ids(result) == {"construct_id"}


def test_byte_identical_genbank_with_wrong_revision_fails_identity_binding() -> None:
    canonical_export, identity = _canonical_export()
    original_genbank = canonical_export["genbank"]["data"]
    canonical_export["metadata"]["revision_id"] = "rev-" + "f" * 16

    result = _inspect(canonical_export, identity)

    assert canonical_export["genbank"]["data"] == original_genbank
    assert result["status"] == "FAIL"
    assert _failed_check_ids(result) == {"revision_id"}


def test_utf8_genbank_bytes_are_preserved_exactly_through_inspection() -> None:
    canonical_export, identity = _canonical_export()
    raw_bytes = canonical_export["genbank"]["data"].encode("utf-8")
    assert any(byte >= 0x80 for byte in raw_bytes)
    canonical_export["genbank"]["data"] = raw_bytes

    result = _inspect(canonical_export, identity)

    assert result["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert result["provenance"]["source_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert result["inspection"]["provenance"]["source_record_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert canonical_export["genbank"]["data"] is raw_bytes


def test_non_utf8_genbank_bytes_fail_closed_without_byte_repair() -> None:
    canonical_export, identity = _canonical_export()
    raw_bytes = canonical_export["genbank"]["data"].encode("utf-8")
    non_ascii_index = next(index for index, byte in enumerate(raw_bytes) if byte >= 0x80)
    invalid_bytes = raw_bytes[:non_ascii_index] + b"\xff" + raw_bytes[non_ascii_index + 1 :]
    canonical_export["genbank"]["data"] = invalid_bytes

    result = _inspect(canonical_export, identity)

    assert result["status"] == "FAIL"
    assert result["inspection"] is not None
    assert result["inspection"]["status"] == "FAIL"
    assert result["provenance"]["source_sha256"] == hashlib.sha256(invalid_bytes).hexdigest()
    assert result["inspection"]["provenance"]["source_record_sha256"] == hashlib.sha256(invalid_bytes).hexdigest()
    assert canonical_export["genbank"]["data"] is invalid_bytes
