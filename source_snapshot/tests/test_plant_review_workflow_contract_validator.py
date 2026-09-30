# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from services import plant_review_workflow_scenario_fixtures as fixtures
from services import plant_review_workflow_contract_validator as validator


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
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


def _valid_result() -> dict:
    return fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW
    )


def test_valid_coherent_r77_scenario_returns_valid_contract() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.PLANT_TRANSIENT_EXPRESSION_REVIEW
    )
    report = validator.validate_plant_review_workflow_contract(result)

    assert report["validator_schema_version"] == validator.VALIDATOR_SCHEMA_VERSION
    assert report["contract_status"] == "valid"
    assert report["is_valid_for_review"] is True
    assert report["manual_review_required"] is True
    assert report["blocked"] is False
    assert report["errors"] == []
    assert report["missing_sections"] == []
    assert report["route_contract"]["route_id"] == "plant_transient_expression_review"
    assert report["presenter_contract"]["missing_presenter_sections"] == []
    _assert_plain_data(report)


def test_valid_manual_review_required_rice_scenario_keeps_contract_valid() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    )
    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "valid"
    assert report["manual_review_required"] is True
    assert report["queue_contract"]["review_item_count"] > 0
    assert report["component_contract"]["slot_count"] > 0
    assert any("absence flag" in warning for warning in report["warnings"])


def test_valid_blocked_unsupported_scenario_is_structurally_valid_but_blocked() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(fixtures.UNSUPPORTED_NON_PLANT_SCOPE)
    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "valid"
    assert report["is_valid_for_review"] is True
    assert report["blocked"] is True
    assert report["manual_review_required"] is True
    assert report["package_contract"]["package_status"] == "blocked"
    assert report["errors"] == []


def test_missing_required_section_invalidates_contract() -> None:
    result = _valid_result()
    result.pop("plant_review_package")

    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "invalid"
    assert report["is_valid_for_review"] is False
    assert "plant_review_package" in report["missing_sections"]
    assert any("plant_review_package" in error for error in report["errors"])


def test_contradictory_blocked_package_status_invalidates_contract() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(fixtures.UNSUPPORTED_NON_PLANT_SCOPE)
    result["plant_review_package"]["package_status"] = "manual_review_required"

    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "invalid"
    assert any("blocked package_status" in error for error in report["errors"])


def test_unsafe_final_component_field_invalidates_contract() -> None:
    result = _valid_result()
    result["plant_review_package"]["component_candidate_summary"]["final_component"] = {
        "component_id": "unsafe"
    }

    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "invalid"
    assert any("unsafe output field" in error for error in report["errors"])


def test_blocked_output_categories_are_accepted_only_as_boundary_metadata() -> None:
    result = _valid_result()
    valid_report = validator.validate_plant_review_workflow_contract(result)
    result["reviewer_summary"] = {"blocked_output_categories": ["protocol"]}

    invalid_report = validator.validate_plant_review_workflow_contract(result)

    assert valid_report["contract_status"] == "valid"
    assert invalid_report["contract_status"] == "invalid"
    assert any("outside boundary metadata" in error for error in invalid_report["errors"])


def test_empty_and_malformed_input_fail_safe_invalid_manual_review() -> None:
    empty_report = validator.validate_plant_review_workflow_contract({})
    malformed_report = validator.validate_plant_review_workflow_contract(["not", "a", "mapping"])  # type: ignore[arg-type]

    assert empty_report["contract_status"] == "invalid"
    assert empty_report["manual_review_required"] is True
    assert validator.REQUIRED_TOP_LEVEL_KEYS[0] in empty_report["missing_sections"]
    assert malformed_report["contract_status"] == "invalid"
    assert malformed_report["manual_review_required"] is True


def test_non_plain_traceability_ids_invalidate_contract() -> None:
    result = _valid_result()
    result["traceability"]["package_traceability"]["component_ids"] = [{"component_id": "nested"}]

    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "invalid"
    assert any("component_ids is not a plain list" in error for error in report["errors"])


def test_route_package_route_id_contradiction_invalidates_contract() -> None:
    result = _valid_result()
    result["plant_review_package"]["route_summary"]["route_id"] = "contradictory_route"

    report = validator.validate_plant_review_workflow_contract(result)

    assert report["contract_status"] == "invalid"
    assert any("contradicts package route summary" in error for error in report["errors"])


def test_validator_does_not_mutate_input() -> None:
    result = _valid_result()
    original = deepcopy(result)

    validator.validate_plant_review_workflow_contract(result)

    assert result == original


def test_validator_source_and_outputs_keep_copy_safety_boundaries() -> None:
    report_text = str(validator.validate_plant_review_workflow_contract(_valid_result())).casefold()
    source_text = Path("services/plant_review_workflow_contract_validator.py").read_text(
        encoding="utf-8"
    ).casefold()
    test_text = Path("tests/test_plant_review_workflow_contract_validator.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in report_text
        assert phrase not in source_text
        assert phrase not in test_text
