from __future__ import annotations

from pathlib import Path

from services.formal_expression_cassette import assess_expression_cassette
from services.formal_step3_component_authority import formal_step3_authority_findings


ROOT = Path(__file__).resolve().parents[1]


def test_registry_three_prime_role_is_bound_to_component_type() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper = source.split("def _formal_three_prime_registry_role", 1)[1].split(
        "def _render_dual_tu_element_input", 1
    )[0]
    assert '"terminator": "terminator"' in helper
    assert '"three_prime_regulatory_region": "three_prime_regulatory_region"' in helper
    assert "component_role" not in helper


def test_registry_role_survives_cassette_assessment_even_with_conflicting_ui_value() -> None:
    cds = "ATG" + "GCT" * 4 + "TAA"
    assessment = assess_expression_cassette(
        [
            {
                "biological_role": "promoter",
                "display_name": "Registry promoter",
                "sequence": "A" * 6,
                "source_kind": "registry",
                "source_reference": "REGISTRY:PROM:1",
            },
            {
                "biological_role": "cds",
                "display_name": "User CDS",
                "sequence": cds,
                "source_kind": "paste",
                "source_reference": "user.fasta",
            },
            {
                "biological_role": "terminator",
                "display_name": "Registry terminator",
                "sequence": "T" * 6,
                "source_kind": "registry",
                "source_reference": "REGISTRY:TER:1",
            },
        ],
        cds_sequence=cds,
        cds_signature="cds-signature",
        order_confirmed=True,
    )
    assert assessment["components"][-1]["biological_role"] == "terminator"


def test_step3_role_control_is_read_only_for_registry_and_user_declared_for_custom() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    step3 = source.split("def _render_step_3_elements", 1)[1]
    assert "v1.expression.biological_role_3_regulatory_element_registry_authoritative" in step3
    assert "disabled=True" in step3
    assert "v1.expression.biological_role_3_regulatory_element_user_declared" in step3
    assert 'three_prime_role = "terminator"' in step3
    assert 'elif terminator_mode != "user_sequence" and terminator_record' in step3
    assert 'mode != "registry"' in step3
    assert 'if terminator_mode == "registry" and authoritative_three_prime_role' in step3


def test_user_three_prime_input_records_user_provenance_separately_from_input_method() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    user_element = source.split("def _user_element", 1)[1].split(
        "def _component_status_html", 1
    )[0]
    assert 'source_kind="user_recorded"' in user_element
    assert 'record["source_input_method"] = input_method' in user_element
    assert 'preserved["source_kind"] = "user_recorded"' in user_element


def test_unknown_registry_three_prime_type_fails_closed() -> None:
    findings = formal_step3_authority_findings(
        promoter_options=[{"formal_selectable": True, "component_reference": {"source_type": "REGISTRY", "registry_component_id": "P"}}],
        three_prime_options=[{"formal_selectable": True, "component_reference": {"source_type": "REGISTRY", "registry_component_id": "T"}}],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter={"formal_selectable": True, "component_reference": {"source_type": "REGISTRY", "registry_component_id": "P"}},
        selected_three_prime={"formal_selectable": True, "component_type": "unknown", "component_reference": {"source_type": "REGISTRY", "registry_component_id": "T"}},
    )
    assert [item["rule_id"] for item in findings] == [
        "unsupported_formal_three_prime_component_type"
    ]
    assert findings[0]["status"] == "阻断"


def test_registry_three_prime_type_mappings_remain_supported() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper = source.split("def _formal_three_prime_registry_role", 1)[1].split(
        "def _render_dual_tu_element_input", 1
    )[0]
    assert '"terminator": "terminator"' in helper
    assert '"three_prime_regulatory_region": "three_prime_regulatory_region"' in helper
