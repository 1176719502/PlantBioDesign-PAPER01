from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R308_COMMIT = "1c23c0f7"
R308_BLOCKED_PATHS = {
    "core/database.py",
    "core/unified_database.py",
    "services/project_import_service.py",
    "services/project_export_package_service.py",
    "services/project_documentation_package_importer.py",
    "services/project_documentation_package_exporter.py",
    "services/report_service.py",
}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from views.wizard_steps._shared import (  # noqa: E402
    PLANT_MVP_BOUNDARY_COPY,
    PLANT_MVP_STEP_READBACK,
    PLANT_MVP_TITLE,
    PLANT_MVP_WORKFLOW_CHECKLIST,
    build_plant_mvp_context_model,
)


def _changed_runtime_copy() -> str:
    files = [
        ROOT / "views" / "wizard_steps" / "_shared.py",
        ROOT / "views" / "wizard_steps" / "step1_gene_input.py",
        ROOT / "views" / "wizard_steps" / "step2_host_elements.py",
        ROOT / "views" / "wizard_steps" / "step3_expression_frame.py",
        ROOT / "views" / "wizard_steps" / "step4_cloning_primers.py",
        ROOT / "views" / "wizard_steps" / "step5_validation.py",
        ROOT / "views" / "wizard_steps" / "step6_export.py",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_plant_mvp_context_model_contains_required_label_and_boundary_copy() -> None:
    model = build_plant_mvp_context_model(current_step=1)
    rendered = "\n".join(
        [
            model["title"],
            model["boundary_copy"],
            model["step_note"],
            *model["workflow_checklist"],
        ]
    )

    assert "Plant recombinant protein / molecular farming" in rendered
    assert "documentation-only and pre-experiment review focused" in rendered
    assert "organize plant expression construct context, provenance, and review gaps" in rendered
    assert "does not create constructs for experimental use" in rendered
    assert "wet-lab protocols" in rendered
    assert "plant-line validation" in rendered


def test_plant_mvp_checklist_contains_expression_construct_flow_terms() -> None:
    rendered = "\n".join(PLANT_MVP_WORKFLOW_CHECKLIST)

    for required in [
        "Plant species / host context",
        "Target tissue / organ / expression compartment",
        "Expression mode",
        "Plant promoter context",
        "Signal peptide / transit peptide / subcellular targeting if applicable",
        "Selectable marker / reporter",
        "Transformation context as documentation-only context",
        "Plant Design Review Package handoff",
    ]:
        assert required in rendered


def test_plant_mvp_step_readback_maps_existing_six_step_wizard() -> None:
    rendered = "\n".join(PLANT_MVP_STEP_READBACK.values())

    for required in [
        "target product/protein and gene/CDS provenance",
        "plant species, target tissue/organ, expression mode, plant promoter, terminator, and selectable marker/reporter context",
        "read-only sequence and codon metrics; no sequence optimization output",
        "signal peptide, transit peptide, subcellular targeting, and vector/backbone documentation",
        "plant-specific evidence/provenance gaps and manual review checks",
        "Plant Design Review Package direction and readback",
    ]:
        assert required in rendered


def test_wizard_dispatcher_renders_plant_mvp_context_without_step_routing_change() -> None:
    source = (ROOT / "views" / "wizard_flow.py").read_text(encoding="utf-8")

    assert "render_plant_mvp_context(ctrl.step)" in source
    assert "PAGE_FUNCS.get(ctrl.step, PAGE_FUNCS[1])(ctrl)" in source
    assert source.index("render_plant_mvp_context(ctrl.step)") < source.index("PAGE_FUNCS.get(ctrl.step, PAGE_FUNCS[1])(ctrl)")


def test_changed_runtime_copy_avoids_unsafe_positive_claims() -> None:
    copy = "\n".join([PLANT_MVP_TITLE, PLANT_MVP_BOUNDARY_COPY, _changed_runtime_copy()]).lower()

    for forbidden in [
        "successful " + "import",
        "project " + "imported",
        "ready for " + "execution",
        "experiment-" + "ready",
        "production-" + "ready",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "plant-line validation claim",
        "phenotype guarantee",
    ]:
        assert forbidden not in copy


def _changed_paths_for_revision(revision: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", revision],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def _r308_blocked_hits(changed_paths: set[str]) -> set[str]:
    return changed_paths & R308_BLOCKED_PATHS


def test_r308_does_not_touch_persistence_schema_or_package_files() -> None:
    assert _r308_blocked_hits(_changed_paths_for_revision(R308_COMMIT)) == set()


def test_r308_scope_model_rejects_blocked_runtime_paths() -> None:
    assert _r308_blocked_hits({"views/wizard_flow.py", "core/database.py"}) == {"core/database.py"}
