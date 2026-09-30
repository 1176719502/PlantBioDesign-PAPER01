from contextlib import nullcontext

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.i18n import t as _t
from services.legacy_snapshot_adapter import FORBIDDEN_READINESS_TERMS
from services.pathway_wizard_context import PATHWAY_WIZARD_CONTEXT_KEY
from views.DesignLibrary import (  # noqa: E402
    _compatibility_preview_rows,
    _detail_summary,
    _feature_preview_rows,
    _linked_project_context_rows,
    _load_into_wizard,
    _primer_note_detail_rows,
    _primer_review_status_display,
    _primer_status_preview_rows,
    _query_summaries,
    _render_detail,
    _render_linked_project_context,
    _render_saved_record_preview,
    _safe_detail_display_value,
    _selection_label,
    _sequence_preview_summary_rows,
    _service_sort_order,
    _service_type_filter,
    _saved_design_detail_groups,
    _saved_design_detail_rows,
    _status_display_value,
    _summary_load_key,
    _summary_table_rows,
)

BATCH_E_FORBIDDEN_VISIBLE_TERMS = [
    "biological validation",
    "experimental readiness",
    "production readiness",
    "yield prediction",
    "pathway optimization",
    "wet-lab protocols",
    "fabrication-ready",
    "execution-ready",
]


def test_design_library_status_copy_defines_saved_record_not_readiness():
    status_copy = _t("design_library.status_clarification")
    subtitle_copy = _t("design_library.subtitle")
    empty_copy = _t("design_library.empty")

    assert "Saved design records library" in subtitle_copy
    assert "Expression Wizard design record subflow" in subtitle_copy
    assert "Pathway Project context for documentation traceability only" in subtitle_copy
    assert "documentation and review only" in status_copy
    assert "saved design records" in status_copy
    assert "do not certify experimental readiness" in status_copy
    assert "do not provide validation or readiness approval" in status_copy
    assert "do not predict yield" in status_copy
    assert "do not optimize pathways" in status_copy
    assert "do not provide wet-lab protocols" in status_copy
    assert "No saved design records yet" in empty_copy
    assert "local documentation library" in empty_copy



    assert _service_sort_order("Newest first") == "desc"
    assert _service_sort_order("Oldest first") == "asc"


def test_status_display_value_does_not_infer_readiness_terms():
    assert _status_display_value(None) == "Snapshot Saved"
    assert _status_display_value("") == "Snapshot Saved"
    assert _status_display_value("saved") == "Snapshot Saved"
    assert _status_display_value("custom-review") == "Snapshot Record"


def test_type_filter_mapping_uses_service_contract():
    assert _service_type_filter("All") is None
    assert _service_type_filter("Expression Design") == "Expression Design"


def test_query_summaries_passes_search_type_and_sort_to_service(monkeypatch):
    calls = []

    def fake_query_saved_design_summaries(*, search=None, types=None, sort_by="saved_at", sort_order="desc"):
        calls.append(
            {
                "search": search,
                "types": types,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }
        )
        return []

    monkeypatch.setattr("views.DesignLibrary.query_saved_design_summaries", fake_query_saved_design_summaries)

    _query_summaries("gfp", "Expression Design", "Oldest first")

    assert calls == [
        {
            "search": "gfp",
            "types": "Expression Design",
            "sort_by": "saved_at",
            "sort_order": "asc",
        }
    ]


def test_selected_summary_uses_load_key_instead_of_name():
    summary = {
        "name": "User Facing Name",
        "load_key": "contract-load-key",
    }

    assert _summary_load_key(summary) == "contract-load-key"


def test_selected_summary_label_uses_display_saved_at_format():
    summary = {
        "name": "GFP Design",
        "saved_at": "2026-04-08T12:00:45",
    }

    assert _selection_label(summary) == "GFP Design | 2026-04-08 12:00"


def test_detail_formatting_counts_primers_validation_issues_and_load_warnings():
    detail = {
        "name": "GFP Design",
        "source": "project_history",
        "summary": {
            "name": "GFP Design",
            "gene": "GFP",
            "host": "E.coli BL21(DE3)",
            "type": "Expression Design",
            "sequence_length": 1200,
            "saved_at": "2026-04-08T12:00:00",
            "source": "project_history",
            "status": "saved",
        },
        "primers": [
            {"name": "Fwd", "sequence": "ATGAAA"},
            {"name": "Rev", "sequence": "TTTCAA"},
        ],
        "validation_results": [
            {"severity": "warn", "message": "Low GC"},
        ],
        "load_warnings": ["Sequence-only fallback; full design metadata is unavailable."],
    }

    formatted = _detail_summary(detail)

    assert formatted["name"] == "GFP Design"
    assert formatted["gene"] == "GFP"
    assert formatted["host"] == "E.coli BL21(DE3)"
    assert formatted["type"] == "Expression Design"
    assert formatted["sequence_length"] == 1200
    assert formatted["saved_at"] == "2026-04-08 12:00"
    assert formatted["source"] == "project_history"
    assert formatted["status"] == "Snapshot Saved"
    assert formatted["primers_count"] == 2
    assert formatted["validation_issues_count"] == 1
    assert formatted["load_warnings"] == ["Sequence-only fallback; full design metadata is unavailable."]


def test_summary_table_rows_display_saved_as_snapshot_saved_without_mutating_source_value():
    summaries = [
        {
            "name": "GFP Design",
            "gene": "GFP",
            "host": "E.coli BL21(DE3)",
            "type": "Expression Design",
            "sequence_length": 1200,
            "saved_at": "2026-04-08T12:00:00",
            "source": "project_history",
            "status": "saved",
        },
        {
            "name": "Sequence Only Design",
            "gene": "mGFP5",
            "host": "",
            "type": "Sequence Only",
            "sequence_length": 714,
            "saved_at": "2026-04-08T12:05:00",
            "source": "library",
            "status": "",
        },
        {
            "name": "Missing Status Design",
            "gene": "Cas9",
            "host": "",
            "type": "Sequence Only",
            "sequence_length": 4104,
            "saved_at": "2026-04-08T12:10:00",
            "source": "library",
        },
    ]

    rows = _summary_table_rows(summaries)

    assert rows[0]["Saved At"] == "2026-04-08 12:00"
    assert rows[1]["Saved At"] == "2026-04-08 12:05"
    assert rows[2]["Saved At"] == "2026-04-08 12:10"
    assert rows[0]["Status"] == "Snapshot Saved"
    assert rows[1]["Status"] == "Snapshot Saved"
    assert rows[2]["Status"] == "Snapshot Saved"
    assert summaries[0]["status"] == "saved"
    assert summaries[1]["status"] == ""
    assert "status" not in summaries[2]


def test_detail_formatting_falls_back_to_metadata_counts():
    detail = {
        "summary": {
            "name": "Legacy Design",
            "sequence_length": 90,
        },
        "metadata": {
            "n_primers": 3,
            "n_issues": 2,
        },
    }

    formatted = _detail_summary(detail)

    assert formatted["primers_count"] == 3
    assert formatted["validation_issues_count"] == 2
    assert formatted["load_warnings"] == []


def test_safe_detail_display_value_converts_complex_values_to_strings():
    value = {"nested": ["alpha", None, {"beta": 2}]}

    rendered = _safe_detail_display_value(value)

    assert isinstance(rendered, str)
    assert '"nested"' in rendered
    assert "alpha" in rendered
    assert "beta" in rendered


def test_safe_detail_display_value_uses_bounded_placeholder_for_missing_values():
    assert _safe_detail_display_value(None) == _t("design_library.not_recorded")
    assert _safe_detail_display_value("") == _t("design_library.not_recorded")
    assert _safe_detail_display_value("   ") == _t("design_library.not_recorded")
    assert _safe_detail_display_value(None, placeholder="No saved value") == "No saved value"


def test_saved_design_detail_rows_are_fixed_safe_string_rows_for_selected_record():
    long_name = "Duplicate Value " * 20
    detail = {
        "name": long_name,
        "source": {"kind": "local", "records": ["duplicate", "duplicate"]},
        "summary": {
            "name": long_name,
            "gene": None,
            "host": "",
            "type": ["Expression Design", "Duplicate"],
            "sequence_length": "not-a-number",
            "saved_at": None,
            "status": "saved",
        },
        "metadata": {
            "n_primers": "2",
            "n_issues": None,
        },
        "load_warnings": [{"warning": "nested warning"}, "duplicate warning"],
    }

    rows = _saved_design_detail_rows(detail)

    assert [label for label, _ in rows] == [
        _t("design_library.field.name"),
        _t("design_library.field.gene"),
        _t("design_library.field.host"),
        _t("design_library.field.type"),
        _t("design_library.field.sequence_length"),
        _t("design_library.field.saved_at"),
        _t("design_library.field.source"),
        _t("design_library.field.status"),
        _t("design_library.metric.primers"),
        _t("design_library.metric.validation_issues"),
        _t("design_library.field.load_warnings"),
    ]
    assert all(isinstance(value, str) for _, value in rows)
    assert (_t("design_library.field.gene"), _t("design_library.not_recorded")) in rows
    assert (_t("design_library.field.host"), _t("design_library.not_recorded")) in rows
    assert (_t("design_library.field.sequence_length"), "0 bp") in rows
    assert (_t("design_library.metric.primers"), "2") in rows
    assert (_t("design_library.metric.validation_issues"), "0") in rows
    rendered = "\n".join(value for _, value in rows)
    assert "Duplicate Value" in rendered
    assert "Expression Design" in rendered
    assert '"kind": "local"' in rendered
    assert "{'warning': 'nested warning'}" in rendered


def test_saved_design_detail_groups_make_metadata_scannable_without_dropping_values():
    detail = {
        "name": "Grouped Design",
        "source": "project_history",
        "summary": {
            "name": "Grouped Design",
            "gene": "GFP",
            "host": "E.coli BL21(DE3)",
            "type": "Expression Design",
            "sequence_length": 1200,
            "saved_at": "2026-04-08T12:00:00",
            "status": "saved",
        },
        "load_warnings": ["Sequence-only fallback; full design metadata is unavailable."],
    }

    groups = _saved_design_detail_groups(detail)
    rendered = "\n".join(f"{group}: {rows}" for group, rows in groups)

    assert [group for group, _ in groups] == ["Record Summary", "Saved Context"]
    assert "Grouped Design" in rendered
    assert "GFP" in rendered
    assert "project_history" in rendered
    assert "Sequence-only fallback" in rendered


def test_primer_review_status_display_reframes_recommendation_like_saved_values():
    assert _primer_review_status_display("Not Recommended") == "Manual Review Needed"
    assert _primer_review_status_display("Review recommended") == "Documentation Review Needed"
    assert _primer_review_status_display("Recommended") == "Saved Primer Review Note"
    assert _primer_review_status_display("Usable with Risk") == "Manual Follow-up"


def test_saved_record_preview_rows_use_existing_fields_and_safe_copy():
    detail = {
        "name": "GFP Design",
        "sequence": "ATGAAATAA",
        "summary": {
            "name": "GFP Design",
            "gene": "GFP",
            "host": "E.coli BL21(DE3)",
            "type": "Expression Design",
            "sequence_length": 9,
            "saved_at": "2026-04-08T12:00:00",
            "status": "saved",
        },
        "frame": {
            "features": [
                {"name": "GFP CDS", "type": "CDS", "start": 1, "end": 9, "note": "Saved annotation"},
            ]
        },
        "primers": [
            {"name": "Fwd", "sequence": "ATGAAA", "status": "Not Recommended"},
        ],
        "validation_results": [{"severity": "warn", "message": "Review note"}],
    }

    sequence_rows = _sequence_preview_summary_rows(detail)
    feature_rows = _feature_preview_rows(detail)
    primer_rows = _primer_status_preview_rows(detail)
    rendered = "\n".join(
        [*(f"{label}: {value}" for label, value in sequence_rows), str(feature_rows), str(primer_rows)]
    )

    assert "documentation-only sequence summary" in rendered
    assert "Local documentation state" in rendered
    assert "GFP Design" in rendered
    assert "ATGAAATAA" in rendered
    assert feature_rows == [
        {
            "#": 1,
            "Feature": "GFP CDS",
            "Type": "CDS",
            "Start": 1,
            "End": 9,
            "Notes": "Saved annotation",
        }
    ]
    assert primer_rows[0]["Review Label"] == "Manual Review Needed"
    assert "Not Recommended" not in str(primer_rows)
    assert "Review recommended" not in str(primer_rows)
    assert primer_rows[0]["Length"] == 6
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in rendered


def test_saved_record_preview_uses_saved_detail_fallbacks_without_reinterpreting_status():
    detail = {
        "name": "Fallback Design",
        "summary": {"name": "Fallback Design", "sequence_length": 12, "status": "saved"},
        "design_data": {
            "frame": {
                "final_sequence": "ATGCCCTAGTAA",
                "features": [
                    {"label": "CDS fallback", "type": "CDS", "start": 1, "end": 12},
                ],
            },
            "primers": [
                {
                    "name": "Forward saved row",
                    "Forward Primer (5'->3')": "ATGCCCTA",
                    "Quality Grade": "Not Recommended",
                    "Quality Reasons": ["Saved primer note"],
                }
            ],
        },
    }

    sequence_rows = _sequence_preview_summary_rows(detail)
    feature_rows = _feature_preview_rows(detail)
    primer_rows = _primer_status_preview_rows(detail)

    assert ("Sequence length", "12 bp") in sequence_rows
    assert ("Sequence preview", "ATGCCCTAGTAA") in sequence_rows
    assert feature_rows == [
        {
            "#": 1,
            "Feature": "CDS fallback",
            "Type": "CDS",
            "Start": 1,
            "End": 12,
            "Notes": "Review only",
        }
    ]
    assert primer_rows == [
        {
            "#": 1,
            "Primer": "Forward saved row",
            "Length": 8,
            "Review Label": "Manual Review Needed",
            "Saved Review Note": "Saved review note: Saved primer note",
        }
    ]
    assert _primer_note_detail_rows(detail) == [
        {
            "#": 1,
            "Primer": "Forward saved row",
            "Saved Primer Review Note": "Saved primer note",
        }
    ]


def test_linked_project_context_rows_show_local_documentation_context(monkeypatch):
    monkeypatch.setattr(
        "views.DesignLibrary.pathway_repository.list_pathway_projects",
        lambda: [{"id": 7, "name": "Pathway Documentation Project", "status": "draft documentation"}],
    )
    monkeypatch.setattr(
        "views.DesignLibrary.pathway_repository.list_expression_design_links",
        lambda project_id: [
            {
                "project_id": project_id,
                "step_id": 3,
                "design_name": "Linked Expression Design",
                "design_snapshot_json": '{"design_id": "design-123", "display_name": "Linked Expression Design"}',
            }
        ],
    )

    rows = _linked_project_context_rows(
        {
            "design_id": "design-123",
            "name": "Linked Expression Design",
            "summary": {"name": "Linked Expression Design", "status": "saved"},
        }
    )
    rendered = "\n".join(f"{label}: {value}" for label, value in rows)

    assert ("Linked project name", "Pathway Documentation Project") in rows
    assert ("Linked project id or local reference", 7) in rows
    assert ("Linked pathway step local reference", 3) in rows
    assert ("Local documentation state", "draft documentation") in rows
    assert (
        "Documentation traceability",
        "This saved design record can be reviewed in linked Pathway Project context; the link supports documentation traceability only.",
    ) in rows
    assert "Documentation Review Needed" in rendered
    assert "Manual follow-up cue" in rendered
    assert "saved primer review state preserved" in rendered
    assert "Review recommended" not in rendered
    assert "linked Pathway Project context" in rendered
    assert "documentation traceability only" in rendered
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in rendered


def test_linked_project_context_empty_state_preserves_saved_record_and_primer_status(monkeypatch):
    infos = []
    captions = []

    monkeypatch.setattr("views.DesignLibrary.pathway_repository.list_pathway_projects", lambda: [])
    monkeypatch.setattr("views.DesignLibrary.st.subheader", lambda text: None)
    monkeypatch.setattr("views.DesignLibrary.st.caption", lambda text: captions.append(text))
    monkeypatch.setattr("views.DesignLibrary.st.info", lambda text: infos.append(text))

    _render_linked_project_context({"name": "Unlinked Design", "summary": {"name": "Unlinked Design"}})

    rendered = "\n".join([*infos, *captions])
    assert "No linked pathway documentation project is recorded for this saved design." in rendered
    assert "Expression Wizard is the design record subflow" in rendered
    assert "not experimental validation or readiness approval" in rendered
    assert "remains available as a local documentation record" in rendered
    assert "This does not change the saved design record or primer status." in rendered
    assert "documentation traceability only" in rendered
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in rendered


def test_saved_record_preview_boundary_copy_avoids_batch_e_risky_terms(monkeypatch):
    warnings = []
    captions = []
    table_text = []

    class FakeTab:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_table(dataframe):
        table_text.append(dataframe.to_string())

    monkeypatch.setattr("views.DesignLibrary.st.subheader", lambda text: None)
    monkeypatch.setattr("views.DesignLibrary.st.caption", lambda text: captions.append(text))
    monkeypatch.setattr("views.DesignLibrary.st.table", fake_table)
    monkeypatch.setattr("views.DesignLibrary.st.info", lambda text: None)
    monkeypatch.setattr("views.DesignLibrary.st.warning", lambda text: warnings.append(text))
    monkeypatch.setattr("views.DesignLibrary.st.tabs", lambda labels: [FakeTab() for _ in labels])

    _render_saved_record_preview(
        {
            "name": "Boundary Design",
            "summary": {"name": "Boundary Design", "sequence_length": 0, "status": "saved"},
        }
    )

    rendered_copy = "\n".join([*warnings, *captions, *table_text]).lower()

    assert "documentation-only saved design record preview" in rendered_copy
    assert "existing saved design record fields" in rendered_copy
    assert "expression wizard design record subflow" in rendered_copy
    assert "loaded state preview" in rendered_copy
    assert "not experimental validation or readiness approval" in rendered_copy
    assert "local documentation state" in rendered_copy
    assert "documentation review is needed" in rendered_copy
    assert "feature summary is for review only" in rendered_copy
    assert "primer review labels summarize saved record state only" in rendered_copy
    assert "not instructions for lab work" in rendered_copy
    assert "review recommended" not in rendered_copy
    assert [term for term in BATCH_E_FORBIDDEN_VISIBLE_TERMS if term in rendered_copy] == []


def test_compatibility_preview_rows_label_historical_validation_and_primer_snapshots():
    detail = {
        "name": "Legacy Design",
        "source": "project_history",
        "design_data": {
            "sequence": "ATGAAATAA",
            "created_at": "2026-05-02T12:00:00",
            "validation_results": [{"severity": "warning", "message": "Prior issue"}],
        },
        "primers": [{"name": "forward", "sequence": "ATGAAA"}],
    }

    rows = _compatibility_preview_rows(detail)
    labels = [label for label, _ in rows]
    rendered = "\n".join(f"{label}: {value}" for label, value in rows)

    assert "Warnings" in labels
    assert "Historical validation issue count" in labels
    assert "Primer snapshot count" in labels
    assert "Historical validation data present." in rendered
    assert "Prior validation data may be historical." in rendered
    assert "Primer data is snapshot-only." in rendered
    assert "Legacy snapshot data is a historical documentation record only." in rendered
    assert "Use Expression Wizard Step 6 for current documentation/export review." in rendered
    assert "project_history" in rendered
    assert "2026-05-02T12:00:00" in rendered


def test_compatibility_preview_rows_do_not_emit_forbidden_readiness_terms():
    detail = {
        "name": "Legacy Design",
        "design_data": {
            "sequence": "ATGAAATAA",
            "validation_results": [{"severity": "info"}],
        },
        "primers": [{"name": "forward"}],
    }

    rendered = "\n".join(f"{label}: {value}" for label, value in _compatibility_preview_rows(detail))

    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in rendered


def test_detail_panel_can_render_compatibility_preview(monkeypatch):
    calls = []

    class FakeColumn:
        def metric(self, label, value):
            calls.append(("metric", label, value))

    class FakeExpander:
        def __enter__(self):
            calls.append(("expander_enter",))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("expander_exit",))
            return False

    class FakeTab:
        def __enter__(self):
            calls.append(("tab_enter",))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("tab_exit",))
            return False

    def fake_table(dataframe):
        calls.append(("table", dataframe.to_string()))

    def fake_expander(title):
        calls.append(("expander", title))
        return FakeExpander()

    def fake_tabs(labels):
        calls.append(("tabs", labels))
        return [FakeTab() for _ in labels]

    monkeypatch.setattr("views.DesignLibrary.st.subheader", lambda text: calls.append(("subheader", text)))
    monkeypatch.setattr("views.DesignLibrary.st.caption", lambda text: calls.append(("caption", text)))
    monkeypatch.setattr("views.DesignLibrary.st.info", lambda text: calls.append(("info", text)))
    monkeypatch.setattr("views.DesignLibrary.st.warning", lambda text: calls.append(("warning", text)))
    monkeypatch.setattr("views.DesignLibrary.st.columns", lambda count: [FakeColumn() for _ in range(count)])
    monkeypatch.setattr("views.DesignLibrary.st.table", fake_table)
    monkeypatch.setattr("views.DesignLibrary.st.expander", fake_expander)
    monkeypatch.setattr("views.DesignLibrary.st.tabs", fake_tabs)

    _render_detail(
        {
            "name": "Legacy Design",
            "source": "project_history",
            "summary": {"name": "Legacy Design", "sequence_length": 9, "status": "saved"},
            "design_data": {
                "sequence": "ATGAAATAA",
                "validation_results": [{"severity": "warning"}],
            },
            "primers": [{"name": "forward"}],
        }
    )

    rendered = "\n".join(str(call) for call in calls)

    assert ("expander", "Legacy Snapshot Compatibility") in calls
    assert "Historical validation data present." in rendered
    assert "Primer data is snapshot-only." in rendered
    assert "Historical validation issue count" in rendered
    assert "Primer snapshot count" in rendered


def test_detail_panel_renders_selected_record_details_without_top_level_table(monkeypatch):
    calls = []

    class FakeColumn:
        def metric(self, label, value):
            calls.append(("metric", label, value))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("top-level detail table should not be rendered with st.table")

    monkeypatch.setattr("views.DesignLibrary.st.subheader", lambda text: calls.append(("subheader", text)))
    monkeypatch.setattr("views.DesignLibrary.st.caption", lambda text: calls.append(("caption", text)))
    monkeypatch.setattr("views.DesignLibrary.st.columns", lambda count: [FakeColumn() for _ in range(count)])
    monkeypatch.setattr("views.DesignLibrary.st.container", lambda **kwargs: nullcontext())
    monkeypatch.setattr("views.DesignLibrary.st.markdown", lambda text, *args, **kwargs: calls.append(("markdown", text)))
    monkeypatch.setattr("views.DesignLibrary.st.table", fail_if_called)
    monkeypatch.setattr("views.DesignLibrary._render_saved_record_preview", lambda detail: None)
    monkeypatch.setattr("views.DesignLibrary._render_compatibility_preview", lambda detail: None)

    _render_detail(
        {
            "name": "Safe Render Design",
            "source": "project_history",
            "summary": {
                "name": "Safe Render Design",
                "gene": "GFP",
                "host": "E.coli BL21(DE3)",
                "type": "Expression Design",
                "sequence_length": 1200,
                "saved_at": "2026-04-08T12:00:00",
                "status": "saved",
            },
            "primers": [{"name": "Fwd"}, {"name": "Rev"}],
            "validation_results": [{"severity": "warn"}],
        }
    )

    rendered = "\n".join(call[1] for call in calls if call[0] in {"caption", "markdown"})
    all_rendered = "\n".join(str(call) for call in calls)
    assert all_rendered.count("Saved Design Record Details") == 1
    assert "Selected saved design record. Values are displayed for documentation review and traceability." in rendered
    assert "Record Summary" in rendered
    assert "Saved Context" in rendered
    assert f"**{_t('design_library.field.name')}:** Safe Render Design" in rendered
    assert f"**{_t('design_library.field.gene')}:** GFP" in rendered
    assert f"**{_t('design_library.field.host')}:** E.coli BL21(DE3)" in rendered
    assert f"**{_t('design_library.field.type')}:** Expression Design" in rendered
    assert f"**{_t('design_library.field.sequence_length')}:** 1200 bp" in rendered
    assert _t("design_library.metric.primers") in all_rendered
    assert "Saved primer rows" in all_rendered
    assert _t("design_library.metric.validation_issues") in all_rendered
    assert "Saved review notes" in all_rendered


def test_load_into_wizard_still_calls_load_service_with_original_load_key(monkeypatch):
    calls = []

    class FakeDesignSession:
        host = "Rice"
        optimized_seq = ""
        original_seq = "ATGAAATAA"
        frame = {"final_sequence": "ATGAAATAA", "features": []}

    class FakeController:
        def save(self, result):
            calls.append(("controller_save", result))

    def fake_load_wizard_design(load_key):
        calls.append(("load", load_key))
        return True, FakeDesignSession()

    def fake_success(message):
        calls.append(("success", message))

    pages = []

    monkeypatch.setattr("views.DesignLibrary.load_wizard_design", fake_load_wizard_design)
    monkeypatch.setattr("core.design_session.SessionController", lambda: FakeController())
    monkeypatch.setattr("views.DesignLibrary.st.success", fake_success)
    monkeypatch.setattr("views.DesignLibrary.st.session_state", {})

    _load_into_wizard("contract-load-key", "Display Name", pages.append)

    assert calls[0] == ("load", "contract-load-key")
    assert calls[1][0] == "controller_save"
    assert pages == ["Expression Wizard"]


def test_load_into_wizard_clears_stale_pathway_context(monkeypatch):
    class FakeDesignSession:
        host = "Rice"
        optimized_seq = ""
        original_seq = "ATGAAATAA"
        frame = {"final_sequence": "ATGAAATAA", "features": []}

    class FakeController:
        def save(self, result):
            return None

    session_state = {
        PATHWAY_WIZARD_CONTEXT_KEY: {
            "source": "pathway_workspace",
            "status": "active",
            "project_id": 1,
            "step_id": 2,
        }
    }
    pages = []

    monkeypatch.setattr("views.DesignLibrary.load_wizard_design", lambda load_key: (True, FakeDesignSession()))
    monkeypatch.setattr("core.design_session.SessionController", lambda: FakeController())
    monkeypatch.setattr("views.DesignLibrary.st.success", lambda message: None)
    monkeypatch.setattr("views.DesignLibrary.st.session_state", session_state)

    _load_into_wizard("contract-load-key", "Display Name", pages.append)

    assert PATHWAY_WIZARD_CONTEXT_KEY not in session_state
    assert pages == ["Expression Wizard"]
