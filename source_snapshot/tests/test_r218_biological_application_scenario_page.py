from __future__ import annotations

from pathlib import Path

from core import module_registry
from views import ApplicationScenario


ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_application_scenario_copy_covers_biological_context() -> None:
    text = ApplicationScenario.scenario_text()

    required = [
        "Application Scenario",
        "Biological design context",
        "expression construct or synthetic biology design before an experiment or outsourcing request",
        "Synthetic biology design personnel",
        "Wet-lab students or researchers",
        "Advisors, PI, or reviewers",
        "Target protein, product, or pathway intent",
        "Host or expression system candidate",
        "Promoter",
        "CDS",
        "Tag or signal peptide",
        "Terminator",
        "Vector or backbone",
        "Marker",
        "Source and provenance notes",
        "Construct summary",
        "Component evidence table",
        "Review gap and follow-up list",
        "Design Review Package",
        "Outsourcing handoff material",
    ]
    missing = [phrase for phrase in required if phrase not in text]

    assert not missing


def test_application_scenario_includes_workflow_and_boundary_language() -> None:
    text = ApplicationScenario.scenario_text()

    for step in [
        "Target intent",
        "Expression system candidate",
        "Construct/component records",
        "Source/provenance evidence",
        "Review gaps",
        "Design Review Package",
    ]:
        assert step in text

    for boundary in [
        "Documentation/review only",
        "Documentation-only local project workspace",
        "does not guarantee expression",
        "does not optimize yield",
        "does not predict experimental success",
        "does not replace expert biological review",
        "does not provide wet-lab protocols",
        "No clinical, regulatory, or product-readiness judgment",
    ]:
        assert boundary in text


def test_application_scenario_does_not_make_positive_high_risk_claims() -> None:
    text = ApplicationScenario.scenario_text().lower()

    forbidden_positive_claims = [
        "automatic optimization",
        "guaranteed expression",
        "yield prediction",
        "clinical readiness",
        "product readiness",
        "replacement of expert review",
        "successful import",
        "project imported",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "wet-lab ready",
        "proven construct",
        "validated pathway",
    ]

    for phrase in forbidden_positive_claims:
        assert phrase not in text


def test_application_scenario_module_is_retained_and_read_only_but_not_formally_visible() -> None:
    app_source = _read(ROOT / "app.py")
    homepage_source = _read(ROOT / "views" / "Homepage.py")
    page_source = _read(ROOT / "views" / "ApplicationScenario.py")
    entry = module_registry.get_by_route_key("Application Scenario")

    assert entry is not None
    assert entry["id"] == "application_scenario"
    assert entry["layer"] == "core"
    assert entry["status"] == "active"
    assert '"Application Scenario"' not in app_source
    assert "ApplicationScenario" not in app_source
    assert '"Application Scenario",' in homepage_source
    assert 'btn_label = f"Open {m[\'name\']} ->"' in homepage_source
    assert "sqlite" not in page_source.lower()
    assert "requests" not in page_source.lower()
    assert "create_" not in page_source
    assert "update_" not in page_source
    assert "delete_" not in page_source
