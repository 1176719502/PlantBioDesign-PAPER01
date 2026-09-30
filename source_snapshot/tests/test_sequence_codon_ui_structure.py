from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE_PAGE = ROOT / "views" / "SequenceTools.py"
CODON_PAGE = ROOT / "views" / "CodonOptimizer.py"
LOCALE = ROOT / "locales" / "en.py"
STEP3_SOURCE = ROOT / "views" / "wizard_steps" / "step3_expression_frame.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _literal_values(path: Path) -> list[str]:
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            static_parts = [
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
            if static_parts:
                values.append("".join(static_parts))
    return values


def _combined_sequence_copy() -> str:
    return _read(SEQUENCE_PAGE) + "\n" + _read(LOCALE)


def _combined_codon_copy() -> str:
    return _read(CODON_PAGE)


def _combined_step3_copy() -> str:
    return _read(STEP3_SOURCE)


def _visible_sequence_codon_literals() -> str:
    sequence_locale_lines = [
        line for line in _read(LOCALE).splitlines() if '"sequence_tools.' in line
    ]
    sequence_locale_copy = "\n".join(sequence_locale_lines)
    return "\n".join(_literal_values(SEQUENCE_PAGE) + _literal_values(CODON_PAGE) + [sequence_locale_copy])


def _offenders(haystack: str, phrases: list[str]) -> list[str]:
    lower = haystack.lower()
    return [phrase for phrase in phrases if phrase.lower() in lower]


def test_sequence_tools_boundary_copy_exists() -> None:
    combined = _combined_sequence_copy()

    required = [
        "documentation / inspection / sequence review helper",
        "local sequence inspection summary",
        "documentation-only review notes",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not a wet-lab protocol",
        "computational previews",
        "documentation notes",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "Review outputs before using them as design support",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []


def test_sequence_tools_result_structure_exists() -> None:
    combined = _combined_sequence_copy()

    required = [
        "Preview summary",
        "Sequence review notes",
        "Sequence metrics preview",
        "Generate Preview",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert ("Preview generated" in combined) or ("Generate Preview" in combined)


def test_codon_usage_preview_boundary_copy_exists() -> None:
    combined = _combined_codon_copy()

    required = [
        "Codon Usage Preview is a documentation-only preview/status helper.",
        "It is not automatic codon optimization",
        "codon usage preview",
        "candidate sequence documentation review helper",
        "local computational preview",
        "documentation review report",
        "documentation-only review context",
        "not an expression/yield optimization engine",
        "not expression optimization",
        "not prediction",
        "not recommendation",
        "not validation",
        "not readiness approval",
        "not a wet-lab protocol",
        "does not predict expression",
        "does not predict yield",
        "does not optimize yield",
        "does not optimize pathways",
        "does not certify experimental readiness",
        "does not provide wet-lab protocols",
        "Current software status: codon usage preview and codon status documentation only.",
        "original CDS source",
        "host context",
        "preview provider",
        "manual/company review cue",
        "does not automatically optimize expression",
        "choose a best sequence",
        "guarantee expression",
        "replace expert/company review",
        "Review outputs before using them as design support",
        "Detailed boundary and limitations",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []


def test_codon_usage_preview_top_level_readability_copy_is_concise() -> None:
    combined = _combined_codon_copy()

    required = [
        "Preview workflow",
        "DNA CDS input",
        "Host table",
        "Generate preview",
        "Preview/readback output",
        "Workflow: DNA CDS input -> host table -> generate preview -> preview/readback output.",
        "Preview generated for documentation review.",
        "Status readback records the CDS source, host context, preview provider, documentation-check status, and manual/company review cue.",
        "Codon draft metrics",
        "review metrics only",
        "codon usage review",
        "preview-only",
        "manual review required",
        "not a sequence rewrite",
        "not an expression prediction",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []


def test_codon_usage_preview_empty_state_uses_compact_native_rows() -> None:
    source = _combined_codon_copy()
    empty_state = source[source.index("def _render_codon_empty_state"):source.index("def _render_codon_error_state")]

    required = [
        "No codon usage preview yet. Enter a sequence to generate a preview.",
        "Input length",
        "Selected host table",
        "Preview status",
        "Not generated",
        "_render_compact_review_rows",
    ]

    assert [phrase for phrase in required if phrase not in empty_state] == []
    assert "st.metric" not in empty_state
    assert "unsafe_allow_html=True" not in empty_state


def test_codon_usage_preview_runtime_layout_avoids_large_metric_html_patterns() -> None:
    source = _combined_codon_copy()

    assert "st.metric" not in source
    assert "unsafe_allow_html=True" not in source
    assert "inject_tool_typography_css" not in source
    assert "render_tool_header" not in source
    assert "render_tool_intro" not in source
    assert "render_boundary_note" not in source
    assert "tool-summary-value" not in source
    assert "Preview Length\", f\"{len(opt_seq)} bp\" if opt_seq else \"n/a\"" in source
    assert "windows with GC outside the configured review range" in source


def test_codon_usage_preview_long_boundary_copy_is_not_repeated_in_main_render() -> None:
    source = _combined_codon_copy()
    render_body = source[source.index("def render("):]

    assert "CODON_USAGE_PREVIEW_CONTEXT_COPY" not in render_body
    assert "CODON_USAGE_STATUS_RECORD_COPY" not in render_body
    assert "Result scope:" not in source
    assert "st.caption(CODON_USAGE_PREVIEW_CONTEXT_COPY)" not in source
    assert source.count("CODON_USAGE_PREVIEW_CONTEXT_COPY") <= 4
    assert source.count("CODON_USAGE_STATUS_RECORD_COPY") <= 3


def test_codon_usage_preview_result_structure_exists() -> None:
    combined = _combined_codon_copy()

    required = [
        "Codon draft metrics",
        "CODON_DRAFT_METRICS_HELPER_COPY",
        "_build_codon_draft_metrics_payload",
        "_codon_draft_metrics_rows",
        "_render_codon_draft_metrics_readback",
        "Metrics-only status",
        "Nucleotide length",
        "Codon count",
        "Multiple-of-3 status",
        "Start codon status",
        "Terminal stop codon status",
        "Internal stop codon count",
        "Invalid/ambiguous base count",
        "GC percentage",
        "Rare codon count",
        "Rare codon cluster count",
        "Codon table provenance/source status",
        "CDS entry state",
        "no CDS entered",
        "invalid/ambiguous CDS",
        "no codon table selected",
        "codon table provenance unavailable",
        "Preview summary",
        "Codon usage review notes",
        "Candidate sequence preview",
        "Generate Codon Usage Preview",
        "Download Preview",
        "No codon usage preview yet",
        "Review-context error detail",
        "No Wizard state, saved design snapshot, or project documentation record was changed.",
        "CAI review-note category",
        "Constraint review-note category",
        "Rare-codon review note",
        "Review Metric Before",
        "Review Metric After",
        "Codon status readback",
        "Original CDS source",
        "Codon optimized?",
        "Not claimed by BioDesign Studio",
        "Preview sequence provider",
        "Local Codon Usage Preview",
        "Target expression system / host context for review",
        "Sequence verification status",
        "Documentation checks only; not experimental validation",
        "Manual/company review cue",
        "Required before downstream biological decisions",
        "Codon table provenance readback",
        "Selected table metadata is shown for documentation review only.",
        "Source/provenance note",
        "Provenance status",
        "Future rewrite draft status",
        "Limitation note",
        "Documentation review note",
        "Manual review required",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert ("Download Preview" in combined) or ("Copy Preview Sequence" in combined)


def test_codon_draft_metrics_readback_does_not_render_sequence_output_fields() -> None:
    source = _combined_codon_copy()
    section = source[source.index("def _build_codon_draft_metrics_payload"):source.index("def _wizard_seq")]

    required = [
        "build_codon_draft_metrics",
        "review metrics only; preview-only; manual review required",
        "not a sequence rewrite",
        "not an expression prediction",
        "_render_compact_review_rows",
    ]
    for phrase in required:
        assert phrase in section

    forbidden = [
        "optimized_sequence",
        "candidate_sequence",
        "input_sequence",
        "st.code",
        "download_button",
        "send_codon_step3_candidate",
        "_optimize(",
        "optimize_cds_sequence",
    ]
    assert _offenders(section, forbidden) == []


def test_sequence_and_codon_unsafe_wording_is_absent_from_visible_copy() -> None:
    visible_copy = _visible_sequence_codon_literals()
    disallowed = [
        "optimized sequence",
        "optimization complete",
        "best codon",
        "recommended sequence",
        "expression improvement",
        "yield improvement",
        "wet-lab ready",
        "validated sequence",
        "expression improved",
        "yield optimized",
        "sequence validated",
        "validation result",
        "successful analysis",
        "automatically optimizes expression",
        "automatic codon optimization available",
        "automatic optimization enabled",
        "best sequence selected",
        "guaranteed expression",
        "yield prediction result",
        "experimental success predicted",
        "wet-lab protocol generated",
        "replaces expert/company review",
        "expert review replaced",
        "company review replaced",
        "experiment-ready",
        "ready for experiment",
        "Download optimized sequence",
    ]

    assert _offenders(visible_copy, disallowed) == []


def test_codon_usage_preview_does_not_add_artifact_or_project_link_entrypoints() -> None:
    combined = _combined_codon_copy()
    forbidden = [
        "create_tool_artifact",
        "Save Documentation Artifact",
        "Optional Pathway Project link",
        "list_pathway_projects",
        "project_id=",
    ]

    assert _offenders(combined, forbidden) == []


def test_step3_candidate_boundary_copy_uses_documentation_context() -> None:
    combined = _combined_step3_copy()

    required = [
        "Step 3 is metrics/readback only, not automatic optimization.",
        "Primary action: preview codon metrics and the expression frame.",
        "The original CDS is preserved; the preview CDS is not a generated optimized sequence.",
        "Computational synonymous recoding candidates will be handled separately as review drafts when enabled.",
        "Original CDS preserved in preview",
        "Step 3 has not generated a synonymous recoding candidate.",
        "After you run the metrics preview, the CDS readback appears here. It is not a generated optimized sequence.",
        "Draft source: Codon Usage Preview. This external draft has not been applied yet.",
        "Step 3 itself does not generate synonymous recoding candidates in this batch.",
        "Select it only if you want to use it for the next manual Step 3 expression-frame preview.",
        "Please select a matching Step 3 draft again.",
        "Preview metric before:",
        "Preview metric after:",
        "These are codon-usage preview metrics for documentation review and manual review context",
        "Codon status is recorded for documentation review only.",
        "metrics/readiness check status",
        "the original CDS is preserved",
        "The preview CDS is not a generated optimized sequence",
        "computational synonymous recoding draft for documentation review only",
        "It is not a biological recommendation, not experimentally validated, not optimization proof",
        "and not build-ready.",
        "Codon candidate draft review",
        "Preview computational codon candidate draft",
        "page-session documentation review draft only",
        "It does not replace the original CDS, change saved records, or route to Step 4.",
        "Generating codon candidate draft for documentation review",
        "Original length",
        "Candidate length",
        "Original GC%",
        "Candidate GC%",
        "Original rare codon count",
        "Candidate rare codon count",
        "Original rare codon clusters",
        "Candidate rare codon clusters",
        "Translation preserved status",
        "Validation/review flags",
        "Review codon candidate draft sequence",
        "Codon status readback",
        "Original CDS source",
        "Step 1 confirmed CDS",
        "Original CDS preservation",
        "Preserved; Step 3 records preview/readback separately",
        "Preview CDS status",
        "Original CDS readback only; no generated optimized sequence",
        "Synonymous recoding draft status",
        "Separate page-session draft preview only after explicit user action",
        "Preview sequence provider",
        "Target expression system / host context for review",
        "Sequence verification status",
        "Documentation checks only; not experimental validation",
        "Manual/company review cue",
        "Required before downstream biological decisions",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert "compatible candidate" not in combined.lower()
    assert "host compatible" not in combined.lower()

    boundary_required = [
        "has not been applied yet",
        "manual Step 3 expression-frame preview",
        "current Step 3 host context",
    ]

    assert [phrase for phrase in boundary_required if phrase not in combined] == []

    forbidden = [
        "Codon optimized?",
        "recommended candidate",
        "validated candidate",
        "ready for wet lab",
        "cai before:",
        "cai after:",
        "Use Candidate for Step 3 Build",
        "Run codon usage preview and assemble expression frame",
        "build-ready expression frame",
        "validated expression sequence",
        "recommended CDS",
    ]

    assert _offenders(combined, forbidden) == []


def test_step3_current_batch_does_not_expose_candidate_generation_ui() -> None:
    combined = _combined_step3_copy()

    required = [
        "no synonymous recoding candidate is generated unless you explicitly preview the separate draft below",
        "Step 3 itself does not generate synonymous recoding candidates in this batch.",
        "Computational synonymous recoding candidates will be handled separately as review drafts when enabled.",
        "Preview computational codon candidate draft",
        "Codon candidate draft review",
        "Review codon candidate draft sequence",
        "not a biological recommendation",
        "not experimentally validated",
        "not optimization proof",
        "not build-ready",
    ]
    forbidden = [
        "Generate optimized sequence",
        "Generate synonymous recoding candidate button",
        "Generate recommended CDS",
        "Create codon candidate",
        "Draft generator enabled",
        "Use codon candidate draft for Step 4",
        "Apply codon candidate draft",
        "Replace original CDS",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert _offenders(combined, forbidden) == []


def test_codon_preview_copy_avoids_optimizer_and_scoring_labels_in_user_visible_surfaces() -> None:
    codon_copy = _combined_codon_copy()
    step3_copy = _combined_step3_copy()
    combined = codon_copy + "\n" + step3_copy

    required = [
        '"origin_page": "Codon Usage Preview"',
    ]
    assert [phrase for phrase in required if phrase not in combined] == []

    assert "Score Before" not in codon_copy
    assert "Score After" not in codon_copy
    assert "Primarily CAI-Driven" not in codon_copy
    assert "Likely Constraint-Driven" not in codon_copy
    assert "Rare-Codon Relief" not in codon_copy
    assert '"origin_page": "Codon Optimizer"' not in codon_copy
