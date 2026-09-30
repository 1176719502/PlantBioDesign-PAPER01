from __future__ import annotations

from services.formal_expression_cassette import assess_expression_cassette
from services.formal_step3_component_authority import (
    empty_formal_step3_component,
    formal_step3_authority_findings,
    formal_step3_component_options,
)


def _registry_row(role: str) -> dict:
    component_type = "promoter" if role == "promoter" else "terminator"
    component_id = f"REGISTRY:{component_type}:1"
    return {
        "name": f"Formal {component_type}",
        "sequence": "ACGTACGT",
        "source": "Plant Component Registry V1",
        "accession": "TEST.1",
        "component_type": component_type,
        "registry_component_id": component_id,
        "formal_selectable": True,
        "component_reference": {
            "source_type": "REGISTRY",
            "registry_component_id": component_id,
        },
    }


def test_exact_rice_798bp_demo_reproduction_is_closed_by_formal_authority() -> None:
    cds = "ATG" + "GCT" * 264 + "TAA"
    assert len(cds) == 798
    assessment = assess_expression_cassette(
        [
            {
                "biological_role": "promoter",
                "display_name": "ZmUbi 启动子演示片段",
                "sequence": "A" * 36,
                "source_kind": "library",
                "source_reference": "内置植物元件记录",
                "user_edited": False,
            },
            {
                "biological_role": "cds",
                "display_name": "用户提供的 CDS",
                "sequence": cds,
                "source_kind": "upload",
                "source_reference": "user.fasta",
                "user_edited": False,
            },
            {
                "biological_role": "terminator",
                "display_name": "NOS 终止子演示片段",
                "sequence": "T" * 182,
                "source_kind": "library",
                "source_reference": "内置植物元件记录",
                "user_edited": False,
            },
        ],
        cds_sequence=cds,
        cds_signature="rice-user-cds-798",
        project_definition={},
        order_confirmed=True,
    )
    assert assessment["blocking"] is False

    authority = formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter={"name": "ZmUbi 启动子演示片段"},
        selected_three_prime={"name": "NOS 终止子演示片段"},
    )
    assert {finding["rule_id"] for finding in authority} == {
        "no_formal_promoter_component",
        "no_formal_three_prime_component",
    }
    assert all(finding["status"] == "阻断" for finding in authority)


def test_production_options_do_not_fall_back_to_demo_or_catalog_data() -> None:
    assert formal_step3_component_options(
        role="promoter", target_host_species="Oryza sativa"
    ) == []
    assert formal_step3_component_options(
        role="3_prime_regulatory_region", target_host_species="Oryza sativa"
    ) == []


def test_zero_option_slots_are_render_safe_without_supplying_sequence_data() -> None:
    promoter = empty_formal_step3_component("promoter")
    three_prime = empty_formal_step3_component("3_prime_regulatory_region")

    assert promoter == {
        "name": "启动子",
        "sequence": "",
        "source": "",
        "formal_selectable": False,
        "component_reference": {},
    }
    assert three_prime["name"] == "3′端调控元件"
    assert three_prime["sequence"] == ""
    assert three_prime["source"] == ""


def test_only_formally_selectable_registry_options_are_exposed() -> None:
    eligible = _registry_row("promoter")
    demo = {
        **eligible,
        "name": "demo promoter",
        "formal_selectable": False,
        "component_reference": {},
    }
    catalog = {
        **eligible,
        "name": "catalog candidate",
        "component_reference": {
            "source_type": "CATALOG_CANDIDATE",
            "registry_component_id": "",
        },
    }

    def provider(**_kwargs):
        return [demo, catalog, eligible]

    options = formal_step3_component_options(
        role="promoter",
        target_host_species="Oryza sativa",
        option_provider=provider,
    )
    assert [item["name"] for item in options] == ["Formal promoter"]
    assert options[0]["formal_selectable"] is True


def test_valid_formal_components_pass_authority_gate_but_demo_selection_does_not() -> None:
    promoter = _registry_row("promoter")
    three_prime = _registry_row("3_prime_regulatory_region")
    assert formal_step3_authority_findings(
        promoter_options=[promoter],
        three_prime_options=[three_prime],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=promoter,
        selected_three_prime=three_prime,
    ) == []

    findings = formal_step3_authority_findings(
        promoter_options=[promoter],
        three_prime_options=[three_prime],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter={"name": "demo", "sequence": "AAAA"},
        selected_three_prime=three_prime,
    )
    assert [finding["rule_id"] for finding in findings] == [
        "ineligible_formal_promoter_component"
    ]


def test_user_cds_sequence_is_not_changed_by_authority_check() -> None:
    cds = "ATG" + "GCT" * 264 + "TAA"
    before = cds
    formal_step3_authority_findings(
        promoter_options=[],
        three_prime_options=[],
        promoter_mode="元件库",
        three_prime_mode="元件库",
        selected_promoter=None,
        selected_three_prime=None,
    )
    assert cds == before
    assert len(cds) == 798
