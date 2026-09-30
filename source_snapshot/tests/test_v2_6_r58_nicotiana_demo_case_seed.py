from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayProjects as pathway_projects


def test_demo_project_definition_matches_nicotiana_documentation_case() -> None:
    demo = pathway_projects._DEMO_PROJECT
    steps = pathway_projects._DEMO_STEPS

    assert demo["name"] == "Nicotiana benthamiana artemisinin precursor documentation case"
    assert demo["target_product"] == "Artemisinin precursor documentation context"
    assert demo["host"] == "Nicotiana benthamiana documentation context"
    assert "documentation-only" in demo["description"].lower()
    assert "predict yield" in demo["description"].lower()

    assert [step["step_order"] for step in steps] == [1, 2, 3, 4, 5, 6]
    assert steps[0]["step_name"] == "FPP precursor supply context"
    assert steps[1]["step_name"] == "ADS pathway gene record"
    assert steps[2]["step_name"] == "CYP71AV1 + CPR oxidation context"
    assert steps[3]["step_name"] == "DBR2 optional downstream context"
    assert steps[4]["step_name"] == "ALDH1 optional downstream context"
    assert steps[5]["step_name"] == "Final chemistry note"
    assert steps[5]["enzyme_name"] == "Not software prediction"


def test_demo_seed_status_requires_six_steps(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_projects, "st", fake_st)
    monkeypatch.setattr(
        pathway_projects,
        "_find_existing_demo",
        lambda projects: {"id": 42, "name": pathway_projects._DEMO_PROJECT["name"]},
    )
    monkeypatch.setattr(pathway_projects, "list_pathway_steps", lambda project_id: [{"step_order": i} for i in range(1, 7)])

    status = pathway_projects._get_demo_seed_status([{"id": 42}])
    assert status == {"ready": True}
