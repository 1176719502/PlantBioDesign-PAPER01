from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.pbi121_replacement_contract import replacement_contract
from services.pbi121_replacement_strategy import (
    Pbi121ReplacementStrategyError,
    classify_features,
    interval_spans,
    load_strategy,
    new_strategy,
    save_strategy,
    source_audit,
    strategy_summary,
    update_strategy,
)


ROOT = Path(__file__).resolve().parents[1]


def _borders(audit: dict) -> tuple[str, str]:
    lb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "left_border")
    rb = next(row["feature_id"] for row in audit["features"] if row["asset_type"] == "right_border")
    return lb, rb


def test_fixed_strategy_uses_the_reviewed_source_and_contract() -> None:
    audit = source_audit()
    strategy = new_strategy()
    contract = replacement_contract()

    assert audit["accession"] == "AF485783.1"
    assert strategy["source_record_sha256"] == audit["source_record_sha256"]
    assert strategy["source_sequence_sha256"] == contract["full_sequence_sha256"]
    assert strategy["source_asset_id"] == "pbi121::complete_binary_vector"
    assert strategy["asset_kind"] == "tDNA_replacement_source"
    assert strategy["strategy_origin"] == "system_fixed_contract"
    assert strategy["editable"] is False
    assert strategy["strategy_status"] == "ready_for_construct_use"


def test_fixed_strategy_normalizes_coordinates_without_off_by_one() -> None:
    strategy = new_strategy()
    assert strategy["replacement_start"] == 4974
    assert strategy["replacement_end"] == 7979
    assert strategy["replacement_length"] == 3006
    assert strategy["coordinate_system"] == "1-based-inclusive"
    assert strategy["normalized_replacement_span"] == [4973, 7979]
    assert interval_spans(4974, 7979, 14758) == [(4973, 7979)]
    assert interval_spans(14750, 10, 14758) == [(14749, 14758), (0, 10)]


def test_fixed_region_removes_reporter_features_and_retains_selection_and_borders() -> None:
    audit = source_audit()
    lb, rb = _borders(audit)
    rows = classify_features(
        audit,
        replacement_start=4974,
        replacement_end=7979,
        protected_feature_ids={lb, rb},
    )
    relationships = {row["feature_id"]: row["relationship"] for row in rows}
    gus = next(row["feature_id"] for row in audit["features"] if row["type"] == "CDS" and row["name"] == "gusA")
    nptii = next(row["feature_id"] for row in audit["features"] if row["type"] == "CDS" and row["name"] == "nptII")
    assert relationships[gus] == "removed"
    assert relationships[nptii] == "retained"
    assert relationships[lb] == relationships[rb] == "protected"
    assert not new_strategy()["partially_overlapped_feature_ids"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("replacement_mode", "insertion"),
        ("replacement_start", 4973),
        ("replacement_end", 7980),
        ("replacement_sha256", "0" * 64),
        ("source_accession", "AF485783.2"),
    ],
)
def test_contract_fields_cannot_be_overridden(field: str, value: object, tmp_path: Path) -> None:
    changed = update_strategy(new_strategy(), **{field: value})
    assert changed["strategy_status"] == "blocked"
    assert changed["validation_blockers"]
    with pytest.raises(Pbi121ReplacementStrategyError):
        save_strategy(changed, runtime_root=tmp_path)


def test_clean_runtime_auto_creates_strategy_and_cold_loads_it(tmp_path: Path) -> None:
    path = tmp_path / "pbi121_replacement_strategy.json"
    assert not path.exists()
    loaded = load_strategy(runtime_root=tmp_path)
    assert path.exists()
    assert loaded["strategy_status"] == "ready_for_construct_use"
    assert json.loads(path.read_text(encoding="utf-8"))["strategy_id"] == loaded["strategy_id"]
    reopened = load_strategy(runtime_root=tmp_path)
    assert reopened["replacement_contract"] == replacement_contract()
    assert strategy_summary(runtime_root=tmp_path)["strategy_origin"] == "system_fixed_contract"


def test_unreadable_strategy_is_reported_as_a_user_facing_blocker(tmp_path: Path) -> None:
    (tmp_path / "pbi121_replacement_strategy.json").write_text("not json", encoding="utf-8")
    summary = strategy_summary(runtime_root=tmp_path)
    assert summary["strategy_status"] == "blocked"
    assert summary["ready_for_construct_use"] is False
    assert "Traceback" not in " ".join(summary["missing_conditions"])


def test_formal_ui_describes_a_system_created_read_only_contract() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "v1.expression.system_created_contract_read_only_users_do" in source
