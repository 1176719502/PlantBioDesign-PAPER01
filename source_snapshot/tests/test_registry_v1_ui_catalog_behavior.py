from __future__ import annotations

import hashlib
import json
import sys
from types import ModuleType
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services import plant_component_workflow_registry as registry_service
from services.plant_component_workflow_registry import (
    LEGACY_CATALOG_STATE,
    library_view_records,
    registry_record_is_admissible,
    registry_records,
    validate_saved_selection,
)
from services.registry_catalog_ui import (
    build_direct_registry_component,
    build_reference_user_provided_component,
    catalog_row_ui_state,
    catalog_state_counts,
    preserved_user_component_reference,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _synthetic_governance_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    production_resolver = registry_service._durable_governance_evidence

    def resolve(record: dict[str, object]) -> None:
        if record.get("governance_decision_source") == "synthetic-governance-record":
            attribution = record.get("attribution")
            assert isinstance(attribution, dict)
            if attribution.get("rights_caveat_reference") != "synthetic test fixture rights":
                raise registry_service.PlantComponentRegistryError(
                    "Synthetic fixture rights evidence is invalid."
                )
            return
        production_resolver(record)

    monkeypatch.setattr(registry_service, "_durable_governance_evidence", resolve)


def _governed_record(
    component_id: str,
    state: tuple[str, str, str],
    *,
    component_type: str = "cds",
) -> dict[str, object]:
    mode, availability, admission = state
    record: dict[str, object] = {
        "component_id": component_id,
        "display_name": f"Synthetic {component_id}",
        "component_type": component_type,
        "source_record": f"synthetic/{component_id}.gb",
        "accession_version": f"{component_id}.1",
        "source_organism": "Oryza sativa",
        "target_host_species": ["Oryza sativa"],
        "evidence_level": "E1",
        "primary_reference": "Synthetic UI fixture",
        "distribution_mode": mode,
        "sequence_availability": availability,
        "workflow_admission_status": admission,
        "governance_decision_source": "synthetic-governance-record",
        "governance_decision_version": "decision-r1",
        "host_applicability": {
            "status": "reviewed",
            "scope": ["Oryza sativa"],
            "evidence_source": "synthetic-host-review",
            "evidence_version": "host-r1",
            "limitation": "Synthetic fixture; no biological performance conclusion.",
        },
    }
    if mode == "bundled":
        sequence = "ATGGCCGCCTAA"
        source_digest = hashlib.sha256(
            f"synthetic source:{component_id}".encode("ascii")
        ).hexdigest()
        record.update(
            {
                "sequence": sequence,
                "sequence_length": len(sequence),
                "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                "source_sequence_length": len(sequence),
                "source_record_sha256": source_digest,
                "feature_boundary_method": {
                    "method": "synthetic exact boundary",
                    "start_one_based": 1,
                    "end_one_based_inclusive": len(sequence),
                    "strand": "+",
                },
                "rights_classification": "RIGHTS_CLEAR_FOR_CURRENT_USE",
                "review_status": "source_and_boundary_reviewed",
                "role_semantics_reviewed": True,
                "host_applicability_reviewed": True,
                "alias_collision_reviewed": True,
                "formal_export_compatible": True,
                "attribution": {
                    "source_database": "synthetic test fixture",
                    "record_locator": f"synthetic://{component_id}.1",
                    "accession_version": f"{component_id}.1",
                    "submitter_source_context": "Synthetic controlled test fixture.",
                    "publication_citations": ["Synthetic controlled test citation."],
                    "source_coordinates_one_based_inclusive": f"1..{len(sequence)}",
                    "strand": "+",
                    "feature_type": f"synthetic {component_type}",
                    "retrieval_date": "2026-09-18",
                    "source_record_sha256": source_digest,
                    "feature_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                    "rights_caveat_reference": "synthetic test fixture rights",
                    "component_contract_version": "decision-r1",
                    "required_notice": "Synthetic test fixture only.",
                },
            }
        )
    return record


def _legacy_record() -> dict[str, object]:
    sequence = "ACGT"
    return {
        "component_id": "LEGACY-CDS",
        "display_name": "Synthetic legacy CDS",
        "component_type": "cds",
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        "source_record": "synthetic/legacy.gb",
    }


def _write_catalog(tmp_path: Path) -> Path:
    payload = {
        "registry_version": "synthetic-ui-v1",
        "records": [
            _governed_record("BUNDLED-CDS", ("bundled", "local_verified", "eligible")),
            _governed_record("REFERENCE-CDS", ("reference_only", "unavailable", "requires_sequence")),
            _governed_record("DEFERRED-CDS", ("deferred", "unavailable", "blocked")),
            _legacy_record(),
        ],
    }
    path = tmp_path / "registry-ui.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_catalog_projection_exposes_authoritative_governance_facts(tmp_path: Path) -> None:
    rows = library_view_records(_write_catalog(tmp_path))
    by_id = {row["registry_component_id"]: row for row in rows}

    assert by_id["BUNDLED-CDS"]["catalog_governance_state"] == (
        "bundled",
        "local_verified",
        "eligible",
    )
    assert by_id["BUNDLED-CDS"]["formal_selectable"] is True
    assert by_id["REFERENCE-CDS"]["distribution_mode"] == "reference_only"
    assert by_id["REFERENCE-CDS"]["sequence_availability"] == "unavailable"
    assert by_id["REFERENCE-CDS"]["workflow_admission_status"] == "requires_sequence"
    assert by_id["DEFERRED-CDS"]["formal_selectable"] is False
    assert by_id["LEGACY-CDS"]["catalog_governance_state"] == LEGACY_CATALOG_STATE
    assert by_id["LEGACY-CDS"]["formal_selectable"] is False
    assert catalog_state_counts(rows) == {
        "bundled": 1,
        "reference_only": 1,
        "deferred": 1,
        "legacy": 1,
        "catalog_candidate": 0,
        "formal_selectable": 1,
    }


def test_catalog_ui_states_fail_closed_and_offer_only_reference_user_path(
    tmp_path: Path,
) -> None:
    rows = library_view_records(_write_catalog(tmp_path))
    states = {
        row["registry_component_id"]: catalog_row_ui_state(row) for row in rows
    }

    assert states["LEGACY-CDS"]["badges"] == ["旧版未分类", "正式选择不可用"]
    assert states["REFERENCE-CDS"]["formal_selectable"] is False
    assert states["REFERENCE-CDS"]["can_offer_user_sequence"] is True
    assert states["DEFERRED-CDS"]["can_offer_user_sequence"] is False
    assert states["DEFERRED-CDS"]["workflow_label"] == "正式选择不可用"
    assert states["BUNDLED-CDS"]["formal_selectable"] is True


def test_reference_sequence_uses_existing_validation_and_remains_user_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = next(
        row
        for row in library_view_records(_write_catalog(tmp_path))
        if row["registry_component_id"] == "REFERENCE-CDS"
    )
    analyzer_calls: list[str] = []
    fake_input_module = ModuleType("services.mvp_sequence_input")

    def fake_analyze(raw_text: str, **_: object) -> dict[str, object]:
        analyzer_calls.append(raw_text)
        normalized = "".join(raw_text.splitlines()[1:]) if raw_text.lstrip().startswith(">") else raw_text
        if not normalized or set(normalized.upper()) - set("ACGT"):
            raise ValueError("DNA 包含非法字符。")
        return {"normalized_sequence": normalized.upper(), "length": len(normalized)}

    fake_input_module.analyze_dna_component_input = fake_analyze  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "services.mvp_sequence_input", fake_input_module)

    with pytest.raises(ValueError, match="非法字符"):
        build_reference_user_provided_component(
            reference,
            raw_sequence="ATGN",
            display_name="User CDS",
            project_id="project-ui-test",
        )

    component = build_reference_user_provided_component(
        reference,
        raw_sequence=">user-cds\nATGGCCGCCTAA\n",
        display_name="User CDS",
        project_id="project-ui-test",
    )
    selection = component["component_reference"]
    validated = validate_saved_selection(
        selection,
        role="cds",
        sequence=component["raw_text"],
    )
    assert component["source_type"] == "paste"
    assert validated["source_type"] == "USER_PROVIDED"
    assert validated["registry_component_id"] == ""
    assert validated["accession_version"] == ""
    assert validated["reference_component_link"] == {
        "registry_component_id": "REFERENCE-CDS",
        "registry_version": "synthetic-ui-v1",
        "authority": "non_authoritative_identity_link",
    }
    assert validated["sequence_sha256"] == component["sequence_sha256"]
    assert "distribution_mode" not in validated
    assert "governance_decision_source" not in validated
    assert analyzer_calls == ["ATGN", ">user-cds\nATGGCCGCCTAA\n"]
    assert preserved_user_component_reference(
        selection,
        role="cds",
        sequence=component["raw_text"],
    )["reference_component_link"] == validated["reference_component_link"]
    assert preserved_user_component_reference(
        selection,
        role="cds",
        sequence="CCCC",
    ) == {}


def test_bundled_positive_control_still_calls_registry_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_catalog(tmp_path)
    monkeypatch.setattr(registry_service, "REGISTRY_PATH", path)
    bundled = next(
        row
        for row in library_view_records(path)
        if row["registry_component_id"] == "BUNDLED-CDS"
    )
    component = build_direct_registry_component(
        bundled,
        requested_host="Oryza sativa",
    )
    selection = component["component_reference"]
    assert component["role"] == "cds"
    assert selection["source_type"] == "REGISTRY"
    assert selection["distribution_mode"] == "bundled"
    assert selection["requested_host"] == "Oryza sativa"

    with pytest.raises(ValueError, match="not admitted"):
        build_direct_registry_component(
            next(
                row
                for row in library_view_records(path)
                if row["registry_component_id"] == "REFERENCE-CDS"
            ),
            requested_host="Oryza sativa",
        )


def test_current_expanded_records_admit_only_reviewed_e8_and_hsp18_2() -> None:
    before = registry_service.REGISTRY_PATH.read_bytes()
    records = registry_records()
    rows = library_view_records()
    assert len(records) == len(rows) == 34
    assert {
        record["component_id"]
        for record in records
        if registry_record_is_admissible(record)
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert {
        row["registry_component_id"]
        for row in rows
        if row["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert sum(
        row["catalog_governance_state"] == LEGACY_CATALOG_STATE for row in rows
    ) == 32
    assert registry_service.REGISTRY_PATH.read_bytes() == before


def test_app_catalog_copy_and_actions_use_service_presenter() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    catalog = source.split("def _render_plant_component_library", 1)[1].split(
        "# ---------------------------------------------------------------------------\n# Sidebar navigation",
        1,
    )[0]
    direct_action = source.split("def _use_plant_library_record", 1)[1].split(
        "def _reset_formal_library_page", 1
    )[0]
    multi_tu_selector = source.split("def _render_dual_tu_element_input", 1)[1].split(
        "def _render_dual_tu_step_3", 1
    )[0]

    assert "catalog_row_ui_state" in catalog
    assert "v1.component_library.catalog_identity" in catalog
    assert "v1.component_library.version_does_not_include_sequence_catalog_identity" in catalog
    assert "v1.component_library.input_sequence_will_saved_as_user_provided" in catalog
    assert "build_reference_user_provided_component" in catalog
    assert "build_direct_registry_component" in direct_action
    assert "build_registry_selection" not in direct_action
    assert "workflow_component_options" in source
    assert "_SOURCE_MODE_VALUES" in multi_tu_selector or '["元件库", "用户序列"]' in multi_tu_selector
    assert "analyze_dna_component_input" in multi_tu_selector
    assert "preserved_user_component_reference" in multi_tu_selector
    assert "saved_component_reference" in multi_tu_selector


def test_app_test_renders_all_governance_states_and_reference_action(
    tmp_path: Path,
) -> None:
    path = _write_catalog(tmp_path)
    script = f'''
import streamlit as st
from services.plant_component_workflow_registry import library_view_records
from services.registry_catalog_ui import catalog_row_ui_state, build_reference_user_provided_component

rows = library_view_records(r"{path}")
for row in rows:
    state = catalog_row_ui_state(row)
    st.write(f"{{row['registry_component_id']}} · {{state['state_label']}} · {{state['workflow_label']}}")
reference = next(row for row in rows if row["registry_component_id"] == "REFERENCE-CDS")
sequence = st.text_area("DNA / FASTA")
if st.button("作为用户提供序列用于 Multi-TU", disabled=not bool(sequence.strip())):
    try:
        component = build_reference_user_provided_component(
            reference,
            raw_sequence=sequence,
            display_name="User CDS",
            project_id="app-test-project",
        )
        st.success(component["component_reference"]["source_type"])
    except Exception as exc:
        st.error(str(exc))
'''
    app = AppTest.from_string(script).run()
    rendered = " ".join(item.value for item in app.markdown)
    assert "BUNDLED-CDS · 本地内置 · 可按服务准入用于正式工作流" in rendered
    assert "REFERENCE-CDS · 仅元数据 · 不能作为 Registry 序列直接使用；可自行提供序列" in rendered
    assert "DEFERRED-CDS · 暂缓 · 正式选择不可用" in rendered
    assert "LEGACY-CDS · 旧版未分类 · 正式选择不可用" in rendered
    assert app.button[0].disabled is True
