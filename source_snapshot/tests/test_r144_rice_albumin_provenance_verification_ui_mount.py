# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import rice_albumin_manual_provenance_verification as provenance
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_handoff_preview_section as section


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("recommended ", "component"),
    _term("best ", "component"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("suc", "cess"),
    _term("yield ", "pre", "diction"),
    _term("wet", "-lab", "-ready"),
    _term("wet-lab ", "ready"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("ready ", "for execution"),
    _term("accepted ", "evidence"),
    _term("verified", "-ID"),
    _term("verified ", "ID"),
)


def _manual_status_payload() -> dict[str, object]:
    record_ids = [
        "r131-rice-albumin-project-intent",
        "r131-rice-seed-design-context",
        "r131-route-plant-protein-expression-evidence-first",
        "r131-slot-target-product",
        "r131-slot-gene-or-cds-source",
        "r131-slot-plant-context",
        "r131-slot-tissue-context",
        "r131-slot-evidence-context",
        "r131-component-albumin-like-cds-source-placeholder",
        "r131-component-vector-backbone-context-placeholder",
        "r131-evidence-target-identity-placeholder",
        "r131-evidence-rice-seed-context-placeholder",
    ]
    missing_source_ids = {
        "r131-rice-albumin-project-intent",
        "r131-rice-seed-design-context",
        "r131-component-albumin-like-cds-source-placeholder",
        "r131-component-vector-backbone-context-placeholder",
        "r131-evidence-target-identity-placeholder",
        "r131-evidence-rice-seed-context-placeholder",
    }
    return {
        "schema_version": "rice_albumin_manual_verification.record_status.r144.test",
        "records": [
            {
                "record_id": record_id,
                "missing_source_id": record_id in missing_source_ids,
                "missing_accession": True,
                "candidate_external_source_category": ["manual source category"],
                "requires_human_lookup": record_id in missing_source_ids,
                "status": [
                    provenance.REVIEW_REQUIRED_STATUS,
                    provenance.DO_NOT_PROMOTE_STATUS,
                ],
                "must_not_be_promoted": True,
                "verified_by_local_repo_only": record_id not in missing_source_ids,
            }
            for record_id in record_ids
        ],
    }


def _write_manual_status(tmp_path: Path) -> Path:
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / provenance.MANUAL_STATUS_FILE).write_text(
        json.dumps(_manual_status_payload()),
        encoding="utf-8",
    )
    return manual_dir


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
        + [f"{call['label']}: {call['value']}" for call in fake_st.metric_calls]
    )


def test_r144_handoff_preview_surface_mounts_manual_provenance_readback(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    calls: list[str] = []

    def _render_mount() -> dict[str, object]:
        calls.append("mounted")
        fake_st.markdown("**Rice albumin manual provenance verification**")
        return {"read_only": True}

    monkeypatch.setattr(section, "render_rice_albumin_manual_provenance_verification_readback", _render_mount)

    section.render_plant_review_handoff_preview_section({})

    rendered = _rendered_text(fake_st)
    assert calls == ["mounted"]
    assert "Handoff preview" in rendered
    assert "Rice albumin manual provenance verification" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_r144_manual_provenance_readback_renders_r143_rows_and_gap_status(tmp_path: Path, monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )

    mount = section.render_rice_albumin_manual_provenance_verification_readback(payload)
    rendered = _rendered_text(fake_st)

    assert len(mount["manual_provenance_rows"]) == 12
    assert payload["summary"]["all_expected_records_present"] is True
    assert "Rice albumin manual provenance verification" in rendered
    assert "Manual provenance review" in rendered
    assert "Source/accession gaps" in rendered
    assert "local seed data" in rendered
    assert "documentation-only" in rendered
    assert "needs manual review" in rendered
    assert "source/accession gaps visible" in rendered
    assert "not promoted" in rendered
    assert "Seed records represented" in rendered
    assert "Expected R131 seed records" in rendered
    assert "Missing source IDs" in rendered
    assert "Missing accessions" in rendered
    assert "needs_manual_review" in rendered
    assert "missing_source_id" in rendered
    assert "missing_accession" in rendered
    assert provenance.DO_NOT_PROMOTE_STATUS in rendered
    assert "r131-rice-albumin-project-intent" in rendered
    assert "r131-route-plant-protein-expression-evidence-first" in rendered
    assert "r131-component-albumin-like-cds-source-placeholder" in rendered
    assert "r131-evidence-rice-seed-context-placeholder" in rendered
    assert "Readback rows: 12" in rendered
    assert "Missing source IDs: 6" in rendered
    assert "Missing accessions: 12" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_r144_ui_consumes_r143_readback_rows_without_local_provenance_logic(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    sentinel_rows = [
        {
            "record_id": "r144-sentinel-row",
            "record_type": "SentinelRecord",
            "review_status": "needs_manual_review",
            "provenance_status": "missing",
            "source_type": "local_seed_data",
            "source_id": "missing",
            "missing_source_id": True,
            "missing_accession": True,
            "review_categories": ["missing_source_id", provenance.DO_NOT_PROMOTE_STATUS],
            "manual_action": "manual lookup required",
            "do_not_promote_status": provenance.DO_NOT_PROMOTE_STATUS,
            "manual_review_note": "needs manual review",
        }
    ]

    def _readback_rows(payload: object) -> list[dict[str, object]]:
        assert payload == {"workflow_status": provenance.MANUAL_PROVENANCE_STATUS_READY, "summary": {}}
        return sentinel_rows

    monkeypatch.setattr(section, "build_rice_albumin_manual_provenance_readback_rows", _readback_rows)

    mount = section.render_rice_albumin_manual_provenance_verification_readback(
        {"workflow_status": provenance.MANUAL_PROVENANCE_STATUS_READY, "summary": {}}
    )
    rendered = _rendered_text(fake_st)
    source = (
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py"
    ).read_text(encoding="utf-8")

    assert mount["manual_provenance_rows"] == sentinel_rows
    assert "r144-sentinel-row" in rendered
    assert "build_rice_albumin_manual_provenance_readback_rows" in source
    assert "_missing_source_id" not in source
    assert "_missing_accession" not in source
    assert "_review_categories" not in source
    assert "SAFE_REVIEW_CATEGORIES" not in source


def test_r144_empty_or_malformed_provenance_payload_renders_safe_read_only_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    mount = section.render_rice_albumin_manual_provenance_verification_readback(
        {
            "workflow_status": "unexpected_external_status",
            "summary": "malformed",
            "records": "malformed",
            "warnings": ["malformed provenance payload fixture"],
        }
    )
    rendered = _rendered_text(fake_st)

    assert mount["read_only"] is True
    assert mount["manual_provenance_rows"] == []
    assert "Read-only: yes" in rendered
    assert "Readback rows: 0" in rendered
    assert "manual provenance review fail closed" in rendered
    assert "No manual provenance rows are available" in rendered
    assert "malformed provenance payload fixture" in rendered
    assert "Source/accession gaps" in rendered
    assert "local seed data remains documentation-only and needs manual review" in rendered
    assert provenance.DO_NOT_PROMOTE_STATUS in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_r144_changed_ui_copy_has_no_positive_or_downstream_wording(tmp_path: Path, monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )

    section.render_rice_albumin_manual_provenance_verification_readback(payload)
    rendered = _rendered_text(fake_st).casefold()
    source_text = "\n".join(
        [
            (
                ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py"
            ).read_text(encoding="utf-8"),
            (ROOT / "tests" / "test_r144_rice_albumin_provenance_verification_ui_mount.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase.casefold() not in rendered
        assert phrase.casefold() not in source_text
    assert "documentation-only" in rendered
    assert "needs manual review" in rendered
    assert "not promoted" in rendered
