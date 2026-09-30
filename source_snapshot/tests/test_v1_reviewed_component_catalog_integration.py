from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from services import plant_component_workflow_registry as registry_service
from services.plant_component_workflow_registry import (
    CATALOG_CANDIDATE_STATE,
    CATALOG_CANDIDATE_STATUS,
    REVIEWED_CATALOG_RECORD_COUNT,
    REVIEWED_CATALOG_SHA256,
    PlantComponentRegistryError,
    build_registry_selection,
    catalog_library_view_records,
    catalog_search_records,
    exact_registry_evidence,
    library_view_records,
    load_reviewed_catalog_candidates,
    registry_record_is_admissible,
    registry_records,
    reviewed_catalog_candidate_view_records,
    workflow_component_options,
)
from services.registry_catalog_ui import catalog_row_ui_state, catalog_state_counts


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
EXPECTED_REGISTRY_CLEAN_SHA256 = (
    "108f43f7914e0cd14de94a2ea7773ac2d04e4d1c53e7ec7bb4b721bbcb3ab5cb"
)


def _casefolded_candidate_text(record: dict[str, str]) -> str:
    return " ".join(
        record[field]
        for field in (
            "candidate_id",
            "display_name",
            "normalized_component_family",
            "component_type",
            "exact_variant",
            "organism_source_context",
            "host_context",
            "accession_record_identifier",
        )
    ).casefold()


def test_reviewed_candidate_blob_count_and_exact_identities_are_preserved() -> None:
    raw_bytes = registry_service.REVIEWED_CATALOG_PATH.read_bytes().replace(b"\r\n", b"\n")
    records = load_reviewed_catalog_candidates()

    assert hashlib.sha256(raw_bytes).hexdigest() == REVIEWED_CATALOG_SHA256
    assert len(records) == REVIEWED_CATALOG_RECORD_COUNT == 122
    assert len({record["candidate_id"] for record in records}) == 122
    assert len({record["sha256"] for record in records}) == 122
    assert {record["workflow_status"] for record in records} == {
        CATALOG_CANDIDATE_STATUS
    }
    for record in records:
        sequence = record["sequence"]
        assert int(record["length"]) == len(sequence)
        assert hashlib.sha256(sequence.encode("ascii")).hexdigest() == record["sha256"]
        assert record["exact_variant"]
        assert record["accession_record_identifier"]
        assert record["source_coordinates_or_feature_identity"]
        assert record["organism_source_context"]
        assert record["source_database"]
        assert record["evidence_publication_reference"]


def test_same_name_different_sequence_variants_remain_distinct() -> None:
    records = load_reviewed_catalog_candidates()
    egfp = [
        record
        for record in records
        if record["display_name"] == "egfp; enhanced green fluorescent protein"
    ]

    assert len(egfp) == 2
    assert len({record["candidate_id"] for record in egfp}) == 2
    assert len({record["sha256"] for record in egfp}) == 2
    assert len({record["exact_variant"] for record in egfp}) == 2
    assert {record["accession_record_identifier"] for record in egfp} == {
        "U55762.1",
        "U55763.1",
    }


def test_authoritative_registry_bytes_inventory_and_admission_remain_unchanged() -> None:
    registry_bytes = registry_service.REGISTRY_PATH.read_bytes().replace(b"\r\n", b"\n")
    registry = registry_records()
    registry_rows = library_view_records()
    catalog_rows = catalog_library_view_records()
    candidate_rows = reviewed_catalog_candidate_view_records()

    assert hashlib.sha256(registry_bytes).hexdigest() == EXPECTED_REGISTRY_CLEAN_SHA256
    assert len(registry) == len(registry_rows) == 34
    assert len(candidate_rows) == 122
    assert len(catalog_rows) == 156
    assert catalog_rows[:34] == registry_rows
    assert {
        record["component_id"]
        for record in registry
        if registry_record_is_admissible(record)
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert {
        row["registry_component_id"]
        for row in catalog_rows
        if row["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert all(row["formal_selectable"] is False for row in candidate_rows)
    assert all(row["workflow_admission_status"] == "not_admitted" for row in candidate_rows)
    assert all(row["registry_component_id"] == "" for row in candidate_rows)
    assert workflow_component_options(role="promoter") == []


def test_candidates_cannot_enter_registry_selection_or_automatic_exact_evidence() -> None:
    candidate = reviewed_catalog_candidate_view_records()[0]

    with pytest.raises(PlantComponentRegistryError, match="does not exist"):
        build_registry_selection(candidate["candidate_id"], role="cds")
    assert exact_registry_evidence(
        sequence=candidate["sequence"],
        component_types={candidate["component_type"]},
    ) == []
    assert candidate["workflow_compatibility"] == []
    state = catalog_row_ui_state(candidate)
    assert candidate["catalog_governance_state"] == CATALOG_CANDIDATE_STATE
    assert state["state_key"] == "catalog_candidate"
    assert state["formal_selectable"] is False
    assert state["can_offer_user_sequence"] is False
    assert state["badges"][:2] == ["目录候选", "正式选择不可用"]


def test_catalog_counts_keep_registry_candidates_and_formal_selection_distinct() -> None:
    counts = catalog_state_counts(catalog_library_view_records())

    assert counts == {
        "bundled": 2,
        "reference_only": 0,
        "deferred": 0,
        "legacy": 32,
        "catalog_candidate": 122,
        "formal_selectable": 2,
    }


def test_catalog_search_is_token_aware_and_prioritizes_component_identity() -> None:
    rows = catalog_library_view_records()
    pat = catalog_search_records(rows, "pat")
    assert pat
    assert all("patent" not in str(row.get("name", "")).casefold() for row in pat)
    assert all(row["search_match_kind"] == "direct" for row in pat)
    gfp = catalog_search_records(rows, "GFP")
    assert gfp and gfp[0]["search_match_kind"] == "direct"
    related = catalog_search_records(rows, "constitutive")
    assert related
    assert all(row["search_match_kind"] in {"direct", "related"} for row in related)


def test_ruby_search_discovers_existing_authoritative_modules_without_synthetic_ruby() -> None:
    rows = catalog_search_records(catalog_library_view_records(), "RUBY")
    names = {row["name"] for row in rows}
    assert {"CYP76AD1 CDS", "DODA1 CDS", "cDOPA5GT CDS"} <= names
    assert not any("RUBY CDS" in name for name in names)


def test_ambiguous_identity_and_boundary_statuses_are_explicit() -> None:
    rows = catalog_library_view_records()
    ambiguous = [row for row in rows if row.get("identity_review_status") == "human_review"]
    assert ambiguous
    assert all("身份待人工复核" in catalog_row_ui_state(row)["badges"] for row in ambiguous)
    boundary = [row for row in rows if row.get("boundary_review_status") == "human_review"]
    assert boundary
    assert all("边界待人工复核" in catalog_row_ui_state(row)["badges"] for row in boundary)


def test_catalog_projection_cannot_contain_project_center_records() -> None:
    catalog_rows = catalog_library_view_records()

    assert len(catalog_rows) == 156
    assert {row["record_authority"] for row in catalog_rows} == {
        "authoritative_registry",
        "reviewed_catalog_candidate",
    }
    assert all("project_id" not in row and "project_name" not in row for row in catalog_rows)
    assert all(
        "Rice-OsSWEET11-vector-test" not in str(row)
        for row in catalog_rows
    )


def test_representative_reviewed_catalog_families_are_browseable() -> None:
    records = load_reviewed_catalog_candidates()

    def matches(term: str) -> list[dict[str, str]]:
        folded = term.casefold()
        return [record for record in records if folded in _casefolded_candidate_text(record)]

    assert matches("GFP-family")
    assert len(matches("EGFP")) >= 2
    assert matches("GUSPlus")
    assert matches("firefly luciferase")
    assert matches("Renilla luciferase")
    assert any(record["component_type"] == "promoter" for record in records)
    assert any(record["component_type"] == "terminator" for record in records)
    assert matches("bar/pat")
    assert matches("hpt/hptII")
    assert any(record["component_type"] == "vector_backbone" for record in records)


def test_ruby_related_exact_components_remain_authoritative_registry_records() -> None:
    by_id = {record["component_id"]: record for record in registry_records()}

    assert {
        "PCLV1-CDS-CYP76AD1",
        "PCLV1-CDS-DODA1",
        "PCLV1-CDS-CDOPA5GT",
    }.issubset(by_id)
    assert not any(
        any(term in _casefolded_candidate_text(record) for term in ("cyp76ad1", "doda", "cdopa5gt"))
        for record in load_reviewed_catalog_candidates()
    )


def test_formal_catalog_ui_uses_browse_only_rows_and_prioritized_details() -> None:
    catalog = APP_SOURCE.split("def _render_plant_component_library", 1)[1].split(
        "# ---------------------------------------------------------------------------\n# Sidebar navigation",
        1,
    )[0]
    loader = APP_SOURCE.split("def _plant_library_records", 1)[1].split(
        "def _formal_library_display_records",
        1,
    )[0]

    assert "build_v2_canonical_inventory" in loader
    assert "return build_v2_canonical_inventory()" in loader
    assert "v1.component_library.v2_canonical_id" in catalog
    assert "formal_library_user_identity_confirm_" in catalog
    assert "权威 Registry" in catalog
    assert "经复核目录候选" in catalog
    assert "仅供目录浏览" in catalog
    assert 'disabled=not ui_state["formal_selectable"]' in catalog
    for label in (
        "显示名称：",
        "元件类型：",
        "精确变体：",
        "来源 accession：",
        "来源记录 / 上下文：",
        "序列长度：",
        "证据记录：",
        "目录身份：",
        "正式准入/可选状态：",
    ):
        assert label in catalog
    assert 'with st.expander("技术与来源详情", expanded=False):' in catalog
    assert "序列 SHA-256：" in catalog
    assert "内部 provenance：" in catalog


def test_ambiguous_duplicate_report_is_not_adopted_into_runtime_data() -> None:
    assert not (
        registry_service.REVIEWED_CATALOG_PATH.parent / "duplicate_equivalence_report.csv"
    ).exists()
