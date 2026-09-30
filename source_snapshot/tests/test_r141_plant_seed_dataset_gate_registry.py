# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_seed_dataset_gate_registry as gate_registry
from services import plant_seed_review_workflow as dispatcher


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_POSITIVE_COPY = (
    _term("recommend", "ation"),
    _term("recommended ", "component"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("suc", "cess"),
    _term("yield ", "pre", "diction"),
    _term("production", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("wet-lab ", "ready"),
    _term("experiment", "-ready"),
    _term("ready ", "for execution"),
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def test_r141_rice_albumin_remains_the_only_active_dispatcher_dataset() -> None:
    assert list(dispatcher.PLANT_SEED_REVIEW_DATASETS) == ["rice_albumin"]
    assert "artemisia_annua" not in dispatcher.PLANT_SEED_REVIEW_DATASETS

    unsupported = dispatcher.build_plant_seed_review_workflow(dataset_key="artemisia_annua")
    assert unsupported["workflow_status"] == dispatcher.PLANT_SEED_REVIEW_STATUS_UNSUPPORTED_DATASET
    assert unsupported["seed_intake"]["records"] == []


def test_r141_artemisia_annua_appears_only_as_blocked_gate_candidate() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("artemisia_annua")

    assert record["dataset_key"] == "artemisia_annua"
    assert record["gate_status"] == gate_registry.GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION
    assert record["conversion_allowed"] is False
    assert record["active_dataset_profile"] is False
    assert record["manual_review_required"] is True
    assert record["read_only"] is True
    assert record["plant_scope_only"] is True
    assert "artemisia_annua" not in dispatcher.PLANT_SEED_REVIEW_DATASETS
    assert not (ROOT / "data" / "plant_seed" / "artemisia_annua").exists()
    _assert_plain_data(record)


def test_r141_blocked_reasons_preserve_r140_review_findings() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("artemisia_annua")
    reasons = set(record["blocked_reasons"])

    assert "component identifiers missing" in reasons
    assert "evidence candidate 007 excluded" in reasons
    assert "evidence candidate 005 unresolved" in reasons
    assert "evidence candidate 006 background-only / cross-reference blocked" in reasons
    assert "missing PMCID gaps" in reasons
    assert "unresolved route/component/evidence cross-references" in reasons
    assert "route/evidence-only seed conversion not currently allowed" in reasons


def test_r141_manual_review_next_actions_remain_visible() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("artemisia_annua")
    actions = " ".join(record["required_next_actions"]).casefold()

    assert "component identifiers" in actions
    assert "evidence candidate 005" in actions
    assert "evidence candidate 007 excluded" in actions
    assert "evidence candidate 006" in actions
    assert "pmcid gaps" in actions
    assert "route, component, and evidence links" in actions
    assert "route/evidence-only seed conversion blocked" in actions


def test_r141_route_evidence_only_conversion_remains_blocked() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("artemisia_annua")
    combined = " ".join(record["blocked_reasons"] + record["required_next_actions"]).casefold()

    assert "route/evidence-only seed conversion not currently allowed" in combined
    assert "route/evidence-only seed conversion blocked" in combined
    assert record["conversion_allowed"] is False


def test_r141_readback_helper_returns_plain_report_rows() -> None:
    rows = gate_registry.build_plant_seed_dataset_gate_readback_rows("artemisia_annua")

    assert rows
    assert all(row["dataset_key"] == "artemisia_annua" for row in rows)
    assert any(row["field"] == "Blocked reasons" for row in rows)
    assert any(row["field"] == "Required next actions" for row in rows)
    assert all(row["conversion_allowed"] is False for row in rows)
    assert all(row["active_dataset_profile"] is False for row in rows)
    _assert_plain_data(rows)


def test_r141_unknown_dataset_gate_lookup_fails_closed() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("unknown_plant_seed")
    rows = gate_registry.build_plant_seed_dataset_gate_readback_rows("unknown_plant_seed")

    assert record["dataset_key"] == "unknown_plant_seed"
    assert record["gate_status"] == gate_registry.GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION
    assert record["conversion_allowed"] is False
    assert record["active_dataset_profile"] is False
    assert record["manual_review_required"] is True
    assert "dataset gate record is not registered" in record["blocked_reasons"]
    assert rows
    assert all(row["conversion_allowed"] is False for row in rows)


def test_r141_gate_outputs_avoid_high_risk_positive_claim_copy() -> None:
    record = gate_registry.get_plant_seed_dataset_gate_record("artemisia_annua")
    unknown = gate_registry.get_plant_seed_dataset_gate_record("unknown_plant_seed")
    rows = gate_registry.build_plant_seed_dataset_gate_readback_rows()
    rendered = f"{record}\n{unknown}\n{rows}".casefold()
    service_text = (ROOT / "services" / "plant_seed_dataset_gate_registry.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_POSITIVE_COPY:
        assert phrase not in rendered
        assert phrase not in service_text

    assert "documentation-only" in rendered
    assert "not an active seed dataset profile" in rendered
