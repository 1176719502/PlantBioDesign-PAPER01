"""Regression coverage for the R3 locale/state and report-preview blockers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from core.i18n import translate
from services.formal_expression_cassette import assess_expression_cassette


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _load_app_helpers(*names: str, language: str = "zh-CN") -> dict[str, Any]:
    assignment_names = {
        "_CONTROLLED_UI_LABELS",
        "_THREE_PRIME_ROLE_LABELS",
        "_THREE_PRIME_ROLE_LEGACY_VALUES",
        "_FORMAL_STEP3_CUSTOM_INPUT_DISPLAY_LABELS",
        "_FORMAL_STEP3_CUSTOM_INPUT_LABELS",
        "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL",
        "_FORMAL_REPORT_PREVIEW_COPY",
        "_MULTI_TU_ROLE_LABELS",
        "_MULTI_TU_ROLE_LABEL_KEYS",
    }
    assignments = {
        target.id: node
        for node in TREE.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in assignment_names
    }
    functions = {
        node.name: node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    }
    body = [assignments[name] for name in assignments if name in {
        "_CONTROLLED_UI_LABELS",
        "_THREE_PRIME_ROLE_LABELS",
        "_THREE_PRIME_ROLE_LEGACY_VALUES",
        "_FORMAL_STEP3_CUSTOM_INPUT_DISPLAY_LABELS",
        "_FORMAL_STEP3_CUSTOM_INPUT_LABELS",
        "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL",
        "_FORMAL_REPORT_PREVIEW_COPY",
        "_MULTI_TU_ROLE_LABELS",
        "_MULTI_TU_ROLE_LABEL_KEYS",
    }]
    body.extend(functions[name] for name in names)
    namespace: dict[str, Any] = {
        "Any": Any,
        "_get_language": lambda: language,
        "_t": lambda key, **params: translate(key, language=language, **params),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


def test_three_prime_role_identity_survives_both_locale_cycles() -> None:
    namespace = _load_app_helpers("_normalize_three_prime_role")
    role = "three_prime_utr"
    role_key = namespace["_THREE_PRIME_ROLE_LABELS"][role]

    for cycle in (("zh-CN", "en", "zh-CN"), ("en", "zh-CN", "en")):
        for language in cycle:
            namespace["_get_language"] = lambda language=language: language
            namespace["_t"] = lambda key, language=language, **params: translate(
                key, language=language, **params
            )
            displayed = translate(role_key, language=language)
            assert namespace["_normalize_three_prime_role"](role) == role
            assert namespace["_normalize_three_prime_role"](displayed) == role
            assert displayed == translate(role_key, language=language)


def test_three_prime_utr_remains_a_valid_generated_cassette_role() -> None:
    assessment = assess_expression_cassette(
        [
            {
                "biological_role": "promoter",
                "display_name": "P",
                "sequence": "AAAA",
                "source_kind": "library",
                "source_reference": "P-1",
            },
            {
                "biological_role": "cds",
                "display_name": "C",
                "sequence": "ATGTAA",
                "source_kind": "paste",
                "source_reference": "C-1",
            },
            {
                "biological_role": "three_prime_utr",
                "display_name": "3-prime UTR",
                "sequence": "TTTT",
                "source_kind": "paste",
                "source_reference": "U-1",
            },
        ],
        cds_sequence="ATGTAA",
        cds_signature="cds-signature",
        order_confirmed=True,
    )
    assert assessment["blocking"] is False
    assert assessment["components"][-1]["biological_role"] == "three_prime_utr"
    assert assessment["components"][-1]["component_type"] == "terminator"


def test_report_preview_preserves_collision_values_and_localizes_only_structure() -> None:
    namespace = _load_app_helpers("_localized_formal_report_preview", language="zh-CN")
    report = "\n".join(
        [
            "# Single-Gene Final Review and Delivery Record",
            "Project: Project",
            "Project: Status",
            "Component: forward",
            "Project name: Status",
            "User sequence source / file label: forward",
            "Target: Stable genetic transformation; Transient expression",
            "- Project | promoter | source: Project | reference: forward | length: 4",
            "Canonical SHA-256: abc123",
        ]
    )
    localized = namespace["_localized_formal_report_preview"](report)
    assert "项目：Project" in localized
    assert "项目：Status" in localized
    assert "Component: forward" in localized
    assert "Project name: Status" in localized
    assert "用户序列来源 / 文件标签：forward" in localized
    assert "目标：稳定遗传转化；瞬时表达" in localized
    assert "- Project | promoter | 来源：Project | 参考：forward | 长度：4" in localized
    assert "Canonical SHA-256：abc123" in localized

    namespace["_get_language"] = lambda: "en"
    assert namespace["_localized_formal_report_preview"](localized).count("Project") >= 2
    assert "forward" in namespace["_localized_formal_report_preview"](localized)


def test_remaining_controlled_copy_renderers_use_locale_labels() -> None:
    namespace = _load_app_helpers(
        "_ui",
        "_multi_tu_role_display_label",
        "_formal_step3_custom_input_display_label",
        language="en",
    )
    assert namespace["_multi_tu_role_display_label"]("3_prime_regulatory_region") == (
        "3′ regulatory region"
    )
    assert namespace["_ui"]("启动子") == "Promoter"
    assert namespace["_formal_step3_custom_input_display_label"]("粘贴 DNA/FASTA") == (
        "Paste DNA/FASTA"
    )

    namespace["_get_language"] = lambda: "zh-CN"
    namespace["_t"] = lambda key, **params: translate(key, language="zh-CN", **params)
    assert namespace["_multi_tu_role_display_label"]("3_prime_regulatory_region") == translate(
        "v1.expression.three_prime_regulatory_region", language="zh-CN"
    )
    assert namespace["_ui"]("启动子") == "启动子"


def test_report_target_summary_has_no_chinese_controlled_copy_in_english() -> None:
    namespace = _load_app_helpers("_localized_formal_report_preview", language="en")
    report = "Target: 稳定遗传转化；瞬时表达"
    localized = namespace["_localized_formal_report_preview"](report)
    assert "Target: Stable genetic transformation; Transient expression" in localized
    assert "稳定遗传转化" not in localized
    assert "瞬时表达" not in localized


def test_r4_report_preview_keeps_collision_values_and_identities_exact() -> None:
    namespace = _load_app_helpers("_localized_formal_report_preview", language="zh-CN")
    values = ("Project", "forward", "Status", "Component", "Sequence", "Promoter")
    sha = "ab" * 32
    sequence = "ATGCCCTAA"
    source = "\n".join([
        "# Single-Gene Final Review and Delivery Record",
        *values,
        *(f"Project: {value}" for value in values),
        *(f"- {value} | promoter | source: USER_PROVIDED | reference: AF234296.1" for value in values),
        "Status: Status",
        "  - User sequence source / file label: forward",
        "  - Source accession: AF234296.1",
        "  - Sequence SHA-256: " + sha,
        "Canonical SHA-256: " + sha,
        "Sequence: " + sequence,
    ])
    chinese = namespace["_localized_formal_report_preview"](source)
    for value in values:
        assert value in chinese.splitlines()
        assert f"项目：{value}" in chinese
        assert f"- {value} | promoter | 来源：USER_PROVIDED | 参考：AF234296.1" in chinese
    assert "状态：Status" in chinese
    assert "用户序列来源 / 文件标签：forward" in chinese
    assert "来源 accession：AF234296.1" in chinese
    assert sha in chinese and sequence in chinese

    namespace["_get_language"] = lambda: "en"
    english = namespace["_localized_formal_report_preview"](source)
    for value in values:
        assert value in english.splitlines()
        assert f"Project: {value}" in english
    assert "AF234296.1" in english and sha in english and sequence in english


def test_r4_single_gene_step3_labels_come_from_semantic_roles() -> None:
    namespace = _load_app_helpers("_single_gene_step3_role_display_label")
    label = namespace["_single_gene_step3_role_display_label"]
    for language in ("en", "zh-CN"):
        namespace["_t"] = lambda key, language=language, **params: translate(
            key, language=language, **params
        )
        assert label("promoter") == translate("v1.ai_assisted_design.promoter", language=language)
        for role, key in namespace["_THREE_PRIME_ROLE_LABELS"].items():
            assert label(role) == translate(key, language=language)
    assert 'display = _single_gene_step3_role_display_label(semantic_role)' in SOURCE
    assert '_user_element("promoter", "启动子"' not in SOURCE


def test_r4_report_fixed_copy_and_coordinates_follow_locale() -> None:
    namespace = _load_app_helpers("_localized_formal_report_preview", language="en")
    source = "\n".join([
        "- CDS: 12..20（1-based 闭区间），链 -1",
        "- No additional canonical review blockers are recorded in this snapshot.",
        "This documentation-only design review record does not establish experimental validation, wet-lab readiness, expression outcome.",
    ])
    english = namespace["_localized_formal_report_preview"](source)
    assert "- CDS: 12..20 (1-based inclusive), strand -1" in english
    assert "No additional canonical review blockers" in english
    assert "实验验证" not in english
    namespace["_get_language"] = lambda: "zh-CN"
    chinese = namespace["_localized_formal_report_preview"](english)
    assert "- CDS: 12..20（1-based 闭区间），链 -1" in chinese
    assert "当前快照未记录其他 Canonical 审查阻断项。" in chinese
    assert "No additional canonical review blockers" not in chinese
    assert "实验验证、湿实验就绪状态或表达结果" in chinese


def test_r4_generated_single_gene_and_multi_tu_report_previews(monkeypatch) -> None:
    from services.formal_single_gene_final_review import (
        build_final_review_report,
        render_formal_report_markdown,
        validate_formal_report_delivery,
    )
    from tests.test_formal_single_gene_final_review import _record_with_complete_plasmid

    for workflow_type in ("single_gene", "multi_tu"):
        record = _record_with_complete_plasmid(monkeypatch, workflow_type=workflow_type)
        report = build_final_review_report(record)
        decision = validate_formal_report_delivery(report)
        source = decision.markdown
        assert render_formal_report_markdown(report).decode("utf-8") == source
        for language in ("en", "zh-CN"):
            namespace = _load_app_helpers("_localized_formal_report_preview", language=language)
            preview = namespace["_localized_formal_report_preview"](source)
            for value in (
                report["report_snapshot_id"],
                report["artifact_manifest_id"],
                report["canonical_sha256"],
                report["delivery_evidence_identity"],
            ):
                assert value in preview
            if language == "en":
                for fragment in (
                    "（1-based 闭区间），链", "当前快照未记录其他 Canonical 审查阻断项。",
                    "这份仅用于文档记录的设计审查记录", "警告级信号仍需人工审查。",
                    "1-based 闭区间", "USER_PROVIDED 序列；accession 与来源边界",
                ):
                    assert fragment not in preview
            else:
                for fragment in (
                    "(1-based inclusive), strand", "No additional canonical review blockers are recorded",
                    "This documentation-only design review record", "Manual review remains required",
                    "Original insertion interval (1-based inclusive)",
                ):
                    assert fragment not in preview
