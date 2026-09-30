from __future__ import annotations

from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
from services.formal_step3_component_authority import formal_step3_authority_findings


CDS = "ATG" + "GCT" * 23 + "TAA"
USER_PROMOTER = "ACGT" * 13
USER_THREE_PRIME = "TGCA" * 13


def _user_component(role: str, sequence: str, *, three_prime_role: str = "terminator") -> dict[str, str]:
    record = {
        "display_name": f"user-{role}",
        "normalized_sequence": sequence,
        "source_kind": "user_recorded",
        "source_input_method": "paste",
        "asset": {"nucleotide_sequence": sequence},
    }
    if role == "terminator":
        record["biological_role"] = three_prime_role
    return record


def _assessment(*, promoter: dict[str, str], three_prime: dict[str, str], order_confirmed: bool) -> dict:
    return assess_expression_cassette(
        [
            {
                "biological_role": "promoter",
                "display_name": promoter["display_name"],
                "sequence": promoter["normalized_sequence"],
                "source_kind": promoter["source_kind"],
                "source_reference": "user-provided",
                "user_edited": True,
            },
            {
                "biological_role": "cds",
                "display_name": "user-cds",
                "sequence": CDS,
                "source_kind": "user_recorded",
                "source_reference": "step-2",
                "user_edited": False,
            },
            {
                "biological_role": three_prime["biological_role"],
                "display_name": three_prime["display_name"],
                "sequence": three_prime["normalized_sequence"],
                "source_kind": three_prime["source_kind"],
                "source_reference": "user-provided",
                "user_edited": True,
            },
        ],
        cds_sequence=CDS,
        cds_signature="user-cds-75bp",
        order_confirmed=order_confirmed,
    )


def test_registry_zero_options_stay_blocking_in_registry_mode() -> None:
    findings = formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=None,
        selected_three_prime=None,
    )
    assert {item["rule_id"] for item in findings} == {
        "no_formal_promoter_component",
        "no_formal_three_prime_component",
    }


def test_valid_user_components_can_generate_without_registry_options() -> None:
    promoter = _user_component("promoter", USER_PROMOTER)
    three_prime = _user_component("terminator", USER_THREE_PRIME)
    authority = formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="用户序列",
        three_prime_mode="用户序列",
        selected_promoter=promoter,
        selected_three_prime=three_prime,
    )
    assessment = _assessment(promoter=promoter, three_prime=three_prime, order_confirmed=True)

    assert authority == []
    assert assessment["blocking"] is False
    generated = generate_expression_cassette(assessment, project_id="user-sequence-gate")
    components = {component["biological_role"]: component for component in generated["components"]}
    assert components["promoter"]["source_kind"] == "user_recorded"
    assert components["terminator"]["source_kind"] == "user_recorded"
    assert components["promoter"]["display_name"] == "user-promoter"
    assert components["terminator"]["display_name"] == "user-terminator"
    assert all(component.get("formal_selectable") is None for component in generated["components"])


def test_user_components_require_order_confirmation() -> None:
    assessment = _assessment(
        promoter=_user_component("promoter", USER_PROMOTER),
        three_prime=_user_component("terminator", USER_THREE_PRIME),
        order_confirmed=False,
    )
    assert assessment["blocking"] is True
    assert {item["rule_id"] for item in assessment["findings"]} == {"component_order_not_confirmed"}


def test_user_inputs_and_three_prime_role_fail_closed() -> None:
    valid_promoter = _user_component("promoter", USER_PROMOTER)
    valid_three_prime = _user_component("terminator", USER_THREE_PRIME)
    cases = [
        (_user_component("promoter", ""), valid_three_prime, "invalid_user_promoter_input"),
        (valid_promoter, _user_component("terminator", ""), "invalid_user_three_prime_input"),
        (valid_promoter, _user_component("terminator", USER_THREE_PRIME, three_prime_role="unsupported"), "unsupported_user_three_prime_role"),
    ]
    for promoter, three_prime, expected_rule in cases:
        findings = formal_step3_authority_findings(
            promoter_options=[],
            three_prime_options=[],
            promoter_mode="用户序列",
            three_prime_mode="用户序列",
            selected_promoter=promoter,
            selected_three_prime=three_prime,
        )
        assert expected_rule in {item["rule_id"] for item in findings}


def test_user_components_cannot_claim_registry_authority() -> None:
    promoter = {
        **_user_component("promoter", USER_PROMOTER),
        "formal_selectable": True,
    }
    findings = formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="用户序列",
        three_prime_mode="用户序列",
        selected_promoter=promoter,
        selected_three_prime=_user_component("terminator", USER_THREE_PRIME),
    )
    assert "invalid_user_promoter_authority" in {item["rule_id"] for item in findings}


def test_user_input_provenance_fields_are_preserved_in_generated_component_records() -> None:
    source = _assessment(
        promoter=_user_component("promoter", USER_PROMOTER),
        three_prime=_user_component("terminator", USER_THREE_PRIME),
        order_confirmed=True,
    )
    generated = generate_expression_cassette(source, project_id="user-sequence-provenance")
    # The cassette adapter retains normalized sequence and source kind; the
    # app-level generation hook adds source_input_method to persisted records.
    promoter = next(item for item in generated["components"] if item["biological_role"] == "promoter")
    terminator = next(item for item in generated["components"] if item["biological_role"] == "terminator")
    assert promoter["source_kind"] == "user_recorded"
    assert terminator["source_kind"] == "user_recorded"
    assert promoter["sequence"] == USER_PROMOTER
    assert terminator["sequence"] == USER_THREE_PRIME


def test_unknown_component_mode_fails_closed() -> None:
    findings = formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="unknown",
        three_prime_mode="用户序列",
        selected_promoter=None,
        selected_three_prime=_user_component("terminator", USER_THREE_PRIME),
    )
    assert "unsupported_promoter_input_mode" in {item["rule_id"] for item in findings}
