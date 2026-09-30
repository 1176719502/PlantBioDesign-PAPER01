from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

import pytest

from services import plant_formal_route_prefill_adapter as adapter


GOAL = "Express human serum albumin protein in rice"
HOST = "rice"
CDS = " atg\n gct\t taa "
ROUTE_ID = "plant_protein_expression_review"
SOURCE_METADATA = {
    "gene_name": "HSA",
    "source_species": "Homo sapiens",
    "source_type": "user provided sequence",
    "source_reference": "USER-SUPPLIED-REFERENCE",
    "modification_status": "source sequence unchanged",
}


def _term(*parts: str) -> str:
    return "".join(parts)


def _signature(**overrides: Any) -> str:
    values = {
        "goal_text": GOAL,
        "plant_host": HOST,
        "user_provided_cds": CDS,
        "source_metadata": SOURCE_METADATA,
    }
    values.update(overrides)
    return adapter.plant_formal_route_prefill_input_signature(**values)


def _build(**overrides: Any) -> dict[str, Any]:
    values = {
        "goal_text": GOAL,
        "plant_host": HOST,
        "user_provided_cds": CDS,
        "source_metadata": SOURCE_METADATA,
        "user_selected_route_id": ROUTE_ID,
        "human_confirmed": True,
        "input_signature": _signature(),
    }
    values.update(overrides)
    return adapter.build_plant_formal_route_prefill_adapter(**values)


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for child in value.values():
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def _assert_plain(value: Any) -> None:
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for child in value.values():
            _assert_plain(child)
    elif isinstance(value, list):
        for child in value:
            _assert_plain(child)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def test_confirmed_single_gene_candidate_builds_advisory_formal_prefill() -> None:
    result = _build()

    assert result["adapter_status"] == adapter.READY_STATUS
    assert result["fail_closed"] is False
    assert result["input_signature"] == _signature()
    assert result["formal_host_value"] == "Rice (O. sativa)"
    assert result["formal_host_id"] == "rice"
    assert result["gene_cds_display_name"] == "HSA"
    assert result["raw_cds"] == CDS
    assert result["normalized_cds"] == "ATGGCTTAA"
    assert result["supplied_source_metadata"] == SOURCE_METADATA
    assert result["selected_advisory_route_id"] == ROUTE_ID
    assert result["selected_advisory_route_reasons"]
    assert result["advisory_only"] is True
    assert result["formal_authority"] is False
    assert result["persist"] is False
    assert result["project_expression_target_draft"] == {
        "project_name_draft": GOAL,
        "expression_goal": GOAL,
        "plant_host": "Rice (O. sativa)",
        "gene_cds_display_name": "HSA",
        "project_type": "single_gene",
        "design_scenario": "standard_plant_expression_vector",
    }
    assert result["component_candidate_review"]["active_component_candidate_selection"] is False
    assert result["component_candidate_review"]["candidate_component_matches_present"] is False
    assert result["component_candidate_review"]["candidate_component_count"] == 0
    _assert_plain(result)


def test_input_signature_is_stable_and_binds_goal_cds_and_supplied_metadata() -> None:
    reordered_metadata = dict(reversed(list(SOURCE_METADATA.items())))

    assert _signature(source_metadata=reordered_metadata) == _signature()
    assert _signature(goal_text=GOAL + " in seed") != _signature()
    assert _signature(user_provided_cds="ATGGCGTAA") != _signature()
    assert _signature(source_metadata={**SOURCE_METADATA, "note": "user note"}) != _signature()
    assert _signature(plant_host="Oryza sativa") == _signature(plant_host="Rice (O. sativa)")


def test_absent_source_metadata_stays_empty_and_does_not_fabricate_identity() -> None:
    signature = _signature(source_metadata=None)
    result = _build(source_metadata=None, input_signature=signature)

    assert result["fail_closed"] is False
    assert result["supplied_source_metadata"] == {}
    assert result["gene_cds_display_name"] == adapter.DEFAULT_USER_PROVIDED_CDS_DISPLAY_NAME
    assert result["project_expression_target_draft"]["gene_cds_display_name"] == adapter.DEFAULT_USER_PROVIDED_CDS_DISPLAY_NAME
    rendered = str(result).casefold()
    assert "accession" not in rendered
    assert "user-supplied-reference" not in rendered
    assert result["gene_cds_display_name"] not in {"human serum albumin", "HSA"}


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"user_selected_route_id": None}, "explicit_user_route_selection_required"),
        ({"human_confirmed": False}, "human_confirmation_required"),
        ({"human_confirmed": 1}, "human_confirmation_required"),
        ({"user_selected_route_id": "unknown_route"}, "unknown_route_crosswalk"),
        (
            {"user_selected_route_id": "plant_multigene_construct_review"},
            "non_single_gene_route_not_supported_in_v1",
        ),
        ({"plant_host": "Nicotiana benthamiana"}, "unsupported_formal_plant_host"),
        ({"user_provided_cds": "ATGNNNTAA"}, "invalid_cds"),
        ({"input_signature": "stale-signature"}, "input_signature_mismatch"),
        ({"input_signature": None}, "input_signature_required"),
    ],
)
def test_required_guards_fail_closed(overrides: dict[str, Any], reason: str) -> None:
    result = _build(**overrides)

    assert result == {
        "adapter_schema_version": adapter.ADAPTER_SCHEMA_VERSION,
        "adapter_status": adapter.FAIL_CLOSED_STATUS,
        "fail_closed": True,
        "fail_closed_reason": reason,
        "prefill": None,
        "advisory_only": True,
        "formal_authority": False,
        "persist": False,
    }


def test_selected_route_must_be_a_current_candidate_and_confirmation_ready() -> None:
    vague_goal = "Plant project note"
    signature = _signature(goal_text=vague_goal)
    result = _build(goal_text=vague_goal, input_signature=signature)

    assert result["fail_closed"] is True
    assert result["fail_closed_reason"] in {
        "selected_route_not_in_current_candidates",
        "route_confirmation_contract_not_satisfied",
    }


def test_fasta_title_supplies_display_name_without_source_metadata() -> None:
    cds = ">USER-CDS-NAME\natggcttaa\n"
    signature = _signature(user_provided_cds=cds, source_metadata=None)
    result = _build(user_provided_cds=cds, source_metadata=None, input_signature=signature)

    assert result["fail_closed"] is False
    assert result["gene_cds_display_name"] == "USER-CDS-NAME"
    assert result["raw_cds"] == cds


def test_payload_has_no_runtime_completion_or_persistence_authority_fields() -> None:
    result = _build()
    keys = _all_keys(result)

    assert "canonical_runtime" not in keys
    assert "step1_complete" not in keys
    assert "step2_complete" not in keys
    assert "selected_component" not in keys
    assert "final_component" not in keys
    assert result["persist"] is False


def test_adapter_stays_offline_ui_free_and_does_not_connect_to_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split(".", 1)[0] in blocked_roots:
            raise AssertionError("formal-prefill adapter must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    def _block_sqlite(*args, **kwargs):
        raise AssertionError("formal-prefill adapter must not access SQLite")

    monkeypatch.setattr(builtins, "__import__", _block_import)
    monkeypatch.setattr("sqlite3.connect", _block_sqlite)

    assert _build()["fail_closed"] is False
    importlib.reload(adapter)


def test_copy_and_scope_boundaries_remain_advisory_only() -> None:
    source = Path("services/plant_formal_route_prefill_adapter.py").read_text(encoding="utf-8").casefold()
    rendered = str(_build()).casefold()
    forbidden = (
        _term("successful ", "import"),
        _term("project ", "imported"),
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("validated ", "construct"),
        _term("optimized ", "pathway"),
        _term("yield ", "prediction"),
        _term("wet-lab ", "ready"),
    )

    for phrase in forbidden:
        assert phrase not in source
        assert phrase not in rendered
