from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import services.formal_results_report_contract as canonical_contract
from services.formal_report_pdf import (
    PDF_TRANSPORT_CONTRACT_VERSION,
    _CJK_FONT_NAME,
    _CJK_FONT_PATH,
    _build_story,
    _styles,
    render_formal_report_pdf,
)
from services.formal_results_report_contract import FormalResultsReportContractError
from services.formal_single_gene_final_review import (
    STATUS_AVAILABLE,
    STATUS_BLOCKED,
    STATUS_REVIEW_REQUIRED,
    _delivery_evidence_identity,
    build_final_review_report,
    persisted_multi_tu_report_eligible,
    render_formal_report_markdown,
    validate_formal_report_delivery,
)
from tests.test_formal_results_report_contract import GENBANK, INPUT_SIGNATURE, _record, _state


ROOT = Path(__file__).resolve().parents[1]
NOTO_SANS_SC_SHA256 = (
    "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"
)


def _rehash_projection(report: dict) -> None:
    report["data"] = report["markdown"].encode("utf-8")
    report["sha256"] = hashlib.sha256(report["data"]).hexdigest()
    report["content_identity"] = f"sha256:{report['sha256']}"


def _rebind_delivery_evidence(report: dict) -> None:
    previous = report["delivery_evidence_identity"]
    current = _delivery_evidence_identity(report["delivery_evidence"])
    report["delivery_evidence_identity"] = current
    report["markdown"] = report["markdown"].replace(
        f"Delivery evidence identity: {previous}",
        f"Delivery evidence identity: {current}",
    )
    _rehash_projection(report)


def _assert_delivery_rejected(report: dict) -> None:
    with pytest.raises(ValueError):
        render_formal_report_markdown(report)
    with pytest.raises(ValueError):
        render_formal_report_pdf(report)


def _record_with_complete_plasmid(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workflow_type: str = "single_gene",
    warnings: int = 0,
    blockers: int = 0,
    construct_status: str = "current",
) -> dict:
    record = _record()
    runtime, cassette, plasmid = _state()
    plasmid["construct_status"] = construct_status
    plasmid["validation_summary"] = {
        "blocking_count": blockers,
        "warning_count": warnings,
        "info_count": 0,
    }
    record["runtime"] = runtime
    record["runtime"]["has_complete_plasmid"] = True
    record["exports"] = {
        "fasta": {
            "data": record["exports"]["combined_construct_fasta"]["data"],
            "file_name": "canonical.fasta",
            "mime": "text/plain",
        },
        "genbank": {
            "data": GENBANK,
            "file_name": "canonical.gb",
            "mime": "text/plain",
        },
    }
    if workflow_type == "multi_tu":
        record["project_type"] = "dual_tu"
        record["runtime"]["project_type"] = "multi_tu"
        record["runtime"].update(
            expression_units=[
                {
                    "unit_id": "tu1",
                    "orientation": "forward",
                    "length": 10,
                    "input_signature": INPUT_SIGNATURE,
                },
                {
                    "unit_id": "tu2",
                    "orientation": "reverse",
                    "length": 10,
                    "input_signature": INPUT_SIGNATURE,
                },
            ],
            unit_order=["tu1", "tu2"],
        )

    monkeypatch.setattr(
        canonical_contract,
        "_read_canonical_runtime",
        lambda runtime_value: (
            {**copy.deepcopy(cassette), "runtime": copy.deepcopy(runtime_value)},
            {**copy.deepcopy(plasmid), "runtime": copy.deepcopy(runtime_value)},
        ),
    )
    return record


def test_formal_step_six_projection_invokes_canonical_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch)
    calls: list[dict] = []
    real_builder = canonical_contract.build_formal_results_report_contract

    def _spy(project_record):
        calls.append(project_record)
        return real_builder(project_record)

    monkeypatch.setattr(canonical_contract, "build_formal_results_report_contract", _spy)
    report = build_final_review_report(record)

    assert calls == [record]
    assert report["status"] == STATUS_AVAILABLE
    assert report["report_snapshot_id"] in report["markdown"]
    assert report["artifact_manifest_id"] in report["markdown"]
    assert report["content_identity"] == f"sha256:{report['sha256']}"


@pytest.mark.parametrize(
    ("workflow_type", "heading"),
    [
        ("single_gene", "# Single-Gene Final Review and Delivery Record"),
        ("multi_tu", "# Multi-TU Final Review and Delivery Record"),
    ],
)
def test_admitted_workflows_use_same_canonical_projection(
    monkeypatch: pytest.MonkeyPatch,
    workflow_type: str,
    heading: str,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch, workflow_type=workflow_type)
    if workflow_type == "multi_tu":
        record["formal_project_context"] = {
            "design_scenario": "metabolic_pathway_multi_tu_vector",
            "record_kind": "gate3_pathway",
        }

    first = build_final_review_report(record)
    second = build_final_review_report(copy.deepcopy(record))

    assert first == second
    assert first["workflow_type"] == workflow_type
    assert heading in first["markdown"]
    assert first["data"] == first["markdown"].encode("utf-8")
    assert first["sha256"] == hashlib.sha256(first["data"]).hexdigest()
    assert first["canonical_sha256"] in first["markdown"]
    assert all(
        row["canonical_sha256"] == first["canonical_sha256"]
        for row in first["artifacts"]
        if row["available"]
    )
    assert all(row["unavailable_reason"] for row in first["artifacts"] if not row["available"])
    assert "## Component Identity and Provenance" in first["markdown"]
    assert "## Vector Strategy" in first["markdown"]
    assert [row["artifact_id"] for row in first["artifacts"]] == [
        "fasta",
        "genbank",
        "plasmid_map",
    ]


def test_warning_is_downloadable_and_blocker_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_report = build_final_review_report(
        _record_with_complete_plasmid(monkeypatch, warnings=2)
    )
    assert warning_report["status"] == STATUS_REVIEW_REQUIRED
    assert warning_report["delivery_record_available"] is True
    assert "manual review is required" in warning_report["markdown"].lower()
    assert validate_formal_report_delivery(warning_report).eligible is True
    assert render_formal_report_markdown(warning_report) == warning_report["data"]

    blocked_report = build_final_review_report(
        _record_with_complete_plasmid(monkeypatch, blockers=1)
    )
    assert blocked_report["status"] == STATUS_BLOCKED
    assert blocked_report["delivery_record_available"] is False
    assert validate_formal_report_delivery(blocked_report).eligible is False
    with pytest.raises(ValueError, match="delivery is blocked"):
        render_formal_report_markdown(blocked_report)
    with pytest.raises(ValueError, match="delivery is blocked"):
        render_formal_report_pdf(blocked_report)


@pytest.mark.parametrize(
    "attack",
    [
        "blocked_availability_flag",
        "blocked_altered_status",
        "blocker_count_contradiction",
        "blocker_list_contradiction",
        "follow_up_reason_contradiction",
        "unsupported_status",
        "unsupported_report_version",
        "malformed_canonical_identity",
        "ready_with_blocking_evidence",
    ],
)
def test_delivery_transports_fail_closed_for_adversarial_projection_changes(
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    if attack == "ready_with_blocking_evidence":
        report = build_final_review_report(_record_with_complete_plasmid(monkeypatch))
        report["blocking_reasons"] = ["Forged blocking evidence."]
        report["delivery_evidence"]["blocking_reasons"] = ["Forged blocking evidence."]
        _rebind_delivery_evidence(report)
    elif attack == "follow_up_reason_contradiction":
        report = build_final_review_report(
            _record_with_complete_plasmid(monkeypatch),
            delivery_policy_blockers=("Original policy blocker.",),
        )
        report["blocking_reasons"] = ["Altered policy blocker."]
        report["delivery_evidence"]["blocking_reasons"] = ["Altered policy blocker."]
        _rebind_delivery_evidence(report)
    else:
        report = build_final_review_report(
            _record_with_complete_plasmid(monkeypatch, blockers=1)
        )
        if attack == "blocked_availability_flag":
            report["delivery_record_available"] = True
        elif attack == "blocked_altered_status":
            report["status"] = STATUS_AVAILABLE
        elif attack == "blocker_count_contradiction":
            report["blocking_count"] = 0
        elif attack == "blocker_list_contradiction":
            report["blocking_reasons"] = []
        elif attack == "unsupported_status":
            report["status"] = "documentation_delivery_unknown"
        elif attack == "unsupported_report_version":
            report["version"] = "2.0"
        elif attack == "malformed_canonical_identity":
            old_hash = report["canonical_sha256"]
            report["canonical_sha256"] = "not-a-sha256"
            report["delivery_evidence"]["canonical_sha256"] = "not-a-sha256"
            report["markdown"] = report["markdown"].replace(
                f"Canonical SHA-256: {old_hash}",
                "Canonical SHA-256: not-a-sha256",
            )
            _rebind_delivery_evidence(report)

    _assert_delivery_rejected(report)


def test_stale_canonical_result_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch, construct_status="stale")
    with pytest.raises(FormalResultsReportContractError, match="must be current"):
        build_final_review_report(record)


def test_transient_fields_cannot_replace_report_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch)
    first = build_final_review_report(record)
    record["_transient"] = {
        "st.session_state": "forged facts",
        "project_name": "not authoritative",
        "canonical_sha256": "0" * 64,
    }
    assert build_final_review_report(record) == first


def test_json_reopen_preserves_report_content_pdf_and_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch, workflow_type="multi_tu")
    before = build_final_review_report(record)
    reopened = json.loads(json.dumps(record, ensure_ascii=False))
    after = build_final_review_report(reopened)

    assert after == before
    assert after["report_snapshot_id"] == before["report_snapshot_id"]
    assert after["artifact_manifest_id"] == before["artifact_manifest_id"]
    assert render_formal_report_pdf(after) == render_formal_report_pdf(before)


def test_pdf_transport_is_byte_deterministic_and_bound_to_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch)
    record["project_name"] = "\u6c34\u7a3b\u6700\u7ec8\u5ba1\u67e5"
    report = build_final_review_report(record)
    first = render_formal_report_pdf(report)
    second = render_formal_report_pdf(copy.deepcopy(report))
    assert first == second
    assert first.startswith(b"%PDF-")

    path = tmp_path / report["pdf_file_name"]
    path.write_bytes(first)
    assert path.stat().st_size == len(first)
    assert PDF_TRANSPORT_CONTRACT_VERSION.encode("ascii") in first
    assert b"/FontFile2" in first
    assert b"NotoSansSC" in first
    assert b"STSong" not in first
    assert first.rstrip().endswith(b"%%EOF")


def test_pdf_transport_is_byte_deterministic_across_python_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_with_complete_plasmid(monkeypatch)
    record["project_name"] = "\u6c34\u7a3b\u6700\u7ec8\u5ba1\u67e5"
    report = build_final_review_report(record)
    payload = copy.deepcopy(report)
    payload["data"] = payload["data"].decode("utf-8")
    script = (
        "import json,sys; "
        "from services.formal_report_pdf import render_formal_report_pdf; "
        "report=json.load(sys.stdin); "
        "report['data']=report['data'].encode('utf-8'); "
        "sys.stdout.buffer.write(render_formal_report_pdf(report))"
    )
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("ascii")

    first = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        input=encoded,
        capture_output=True,
        check=True,
    ).stdout
    second = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        input=encoded,
        capture_output=True,
        check=True,
    ).stdout

    assert first == second
    assert first.startswith(b"%PDF-")
    assert b"/FontFile2" in first


def test_pdf_uses_frozen_official_noto_sans_sc_asset() -> None:
    assert _CJK_FONT_PATH == (
        ROOT / "assets" / "fonts" / "noto_sans_sc" / "NotoSansSC-wght.ttf"
    )
    assert hashlib.sha256(_CJK_FONT_PATH.read_bytes()).hexdigest() == NOTO_SANS_SC_SHA256

    asset_directory = _CJK_FONT_PATH.parent
    provenance = (asset_directory / "PROVENANCE.md").read_text(encoding="utf-8")
    license_text = (asset_directory / "OFL.txt").read_text(encoding="utf-8")
    metadata = (asset_directory / "METADATA.pb").read_text(encoding="utf-8")
    assert "73fc2ff52147e34a74804b500cf89ca219eac55d" in provenance
    assert "Version 2.004-H2" in provenance
    assert NOTO_SANS_SC_SHA256 in provenance
    assert "SIL OPEN FONT LICENSE Version 1.1" in license_text
    assert 'name: "Noto Sans SC"' in metadata
    assert 'license: "OFL"' in metadata


def test_pdf_font_registration_has_no_import_time_side_effect() -> None:
    script = (
        "from reportlab.pdfbase import pdfmetrics; "
        "name='NotoSansSC'; "
        "before=name in pdfmetrics.getRegisteredFontNames(); "
        "import services.formal_report_pdf; "
        "after=name in pdfmetrics.getRegisteredFontNames(); "
        "print(f'{before}:{after}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.strip() == "False:False"


def test_pdf_uses_latin_metrics_and_preserves_cjk_font_runs() -> None:
    story = _build_story(
        "# BioDesign Studio 最终报告\n\n## Review 审阅\n\nEnglish spacing 中文可读",
        "0" * 64,
        _styles(),
    )

    body = story[-1]
    fragments = [fragment for fragment in body.frags if fragment.text]
    assert any(fragment.fontName == "Helvetica" for fragment in fragments)
    assert any(fragment.fontName == _CJK_FONT_NAME for fragment in fragments)


def test_pdf_section_heading_keeps_with_first_meaningful_content() -> None:
    story = _build_story(
        "# Final Review\n\n## Review Counts\n\nBlocking items: 0",
        "0" * 64,
        _styles(),
    )

    heading_index = next(
        index
        for index, flowable in enumerate(story)
        if getattr(getattr(flowable, "style", None), "name", "")
        == "FormalReportHeading"
    )
    heading = story[heading_index]
    following = story[heading_index + 1]
    assert heading.getKeepWithNext() == 1
    assert getattr(getattr(following, "style", None), "name", "") == "FormalReportBody"


def test_pdf_rejects_tampered_content_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_final_review_report(_record_with_complete_plasmid(monkeypatch))
    report["markdown"] += "forged"
    with pytest.raises(ValueError, match="identity does not match"):
        render_formal_report_pdf(report)


def test_step_six_view_and_download_share_one_projection() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assembly_source = app_source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_persisted_result_downloads", 1
    )[0]
    renderer = app_source.split("def _render_canonical_final_review_delivery", 1)[1].split(
        "def _render_results_export_content", 1
    )[0]
    results_source = app_source.split("def _render_results_export_content", 1)[1].split(
        "def _plant_library_records", 1
    )[0]

    assert "if report_delivery_current:" in assembly_source
    assert "_build_canonical_final_review_report(result)" in assembly_source
    assert "_render_canonical_final_review_delivery(final_review_report)" in assembly_source
    preview_delivery = assembly_source.split("if result_preview_mode:", 1)[1].split(
        "return", 1
    )[0]
    assert "_render_canonical_final_review_delivery(final_review_report)" in preview_delivery
    assert "report_delivery_current = is_current" in results_source
    assert "if result_preview_mode and _is_multi_tu_expression_assembly(result):" in results_source
    assert "report_delivery_current = _persisted_multi_tu_report_eligible(" in results_source
    assert "if report_delivery_current:" in results_source
    assert "_build_canonical_final_review_report(" in results_source
    assert "_render_canonical_final_review_delivery(final_review_report)" in results_source
    assert "validate_formal_report_delivery(report)" in renderer
    assert "render_formal_report_markdown(report)" in renderer
    assert 'row.get("required") and row.get("available")' in renderer
    assert "render_formal_report_pdf(report)" in renderer
    assert 'report.get("delivery_record_available")' not in renderer
    assert 'mime="application/pdf"' in renderer
    assert "st.session_state" not in renderer


def _persisted_multi_tu_result(
    validation_status: str,
    *,
    review_status: object = "current",
    include_review_status: bool = True,
    **overrides: object,
) -> dict[str, object]:
    context: dict[str, object] = {}
    if include_review_status:
        context["construct_review_status"] = review_status
    value: dict[str, object] = {
        "project_type": "dual_tu",
        "result_kind": "MULTI_TU_EXPRESSION_ASSEMBLY",
        "formal_project_context": context,
        "combined_construct": {
            "formal_validation": {"status": validation_status},
        },
    }
    value.update(overrides)
    return value


def test_production_persisted_multi_tu_guard_denies_changed_background_delivery_surfaces() -> None:
    result = _persisted_multi_tu_result(
        "formal_ready",
        review_status="needs_review",
    )

    persisted_guard = persisted_multi_tu_report_eligible(
        result,
        result_preview_mode=True,
    )

    assert persisted_guard is False
    assert {
        "markdown": persisted_guard,
        "pdf": persisted_guard,
        "ui_delivery": persisted_guard,
    } == {"markdown": False, "pdf": False, "ui_delivery": False}


@pytest.mark.parametrize(
    ("review_status", "include_review_status"),
    [
        (None, False),
        (None, True),
        ("", True),
        ("CURRENT", True),
        (" current ", True),
        ("reviewed", True),
        ("needs_review", True),
    ],
)
def test_production_persisted_multi_tu_guard_fails_closed_for_noncurrent_review_state(
    review_status: object,
    include_review_status: bool,
) -> None:
    result = _persisted_multi_tu_result(
        "formal_ready",
        review_status=review_status,
        include_review_status=include_review_status,
    )

    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=True)
        is False
    )


@pytest.mark.parametrize(
    "validation_status",
    ["formal_ready", "four_role_review_required"],
)
def test_production_persisted_multi_tu_guard_preserves_reviewed_delivery(
    validation_status: str,
) -> None:
    result = _persisted_multi_tu_result(validation_status)

    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=True)
        is True
    )
    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=False)
        is False
    )


@pytest.mark.parametrize(
    ("warnings", "validation_status", "expected_status"),
    [
        (0, "formal_ready", STATUS_AVAILABLE),
        (2, "four_role_review_required", STATUS_REVIEW_REQUIRED),
    ],
)
def test_reviewed_persisted_multi_tu_ready_and_warning_transports_remain_available(
    monkeypatch: pytest.MonkeyPatch,
    warnings: int,
    validation_status: str,
    expected_status: str,
) -> None:
    result = _record_with_complete_plasmid(
        monkeypatch,
        workflow_type="multi_tu",
        warnings=warnings,
    )
    result.update(
        result_kind="MULTI_TU_EXPRESSION_ASSEMBLY",
        formal_project_context={"construct_review_status": "current"},
        combined_construct={
            "formal_validation": {"status": validation_status},
        },
    )

    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=True)
        is True
    )
    report = build_final_review_report(result)
    assert report["status"] == expected_status
    assert render_formal_report_markdown(report) == report["data"]
    assert render_formal_report_pdf(report).startswith(b"%PDF-")


def test_changed_background_persisted_multi_tu_warning_has_no_delivery_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _record_with_complete_plasmid(
        monkeypatch,
        workflow_type="multi_tu",
        warnings=2,
    )
    result.update(
        result_kind="MULTI_TU_EXPRESSION_ASSEMBLY",
        formal_project_context={"construct_review_status": "needs_review"},
        combined_construct={
            "formal_validation": {"status": "four_role_review_required"},
        },
    )

    persisted_guard = persisted_multi_tu_report_eligible(
        result,
        result_preview_mode=True,
    )
    delivery_projection = build_final_review_report(result) if persisted_guard else None

    assert persisted_guard is False
    assert delivery_projection is None


def test_production_persisted_multi_tu_guard_ignores_stale_session_like_state() -> None:
    result = _persisted_multi_tu_result(
        "formal_ready",
        review_status="needs_review",
        formal_construct_review_status="current",
        session_state={"formal_construct_review_status": "current"},
    )

    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=True)
        is False
    )


def test_production_persisted_multi_tu_guard_does_not_admit_single_gene_records() -> None:
    result = _persisted_multi_tu_result(
        "formal_ready",
        project_type="single_gene",
        result_kind="single_gene",
    )

    assert (
        persisted_multi_tu_report_eligible(result, result_preview_mode=True)
        is False
    )


def test_navigation_state_uses_durable_design_facts() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    statuses_source = app_source.split("def _formal_step_statuses", 1)[1].split(
        "def _is_result_preview_mode", 1
    )[0]
    assert 'state.get("formal_project_definition")' in statuses_source
    assert 'state.get("formal_step1_design_dirty")' in statuses_source
    assert 'state.get("formal_step2_design_dirty")' in statuses_source
    assert "step1_widget_fields" not in statuses_source
