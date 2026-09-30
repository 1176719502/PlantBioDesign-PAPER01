from __future__ import annotations

import copy
import ast
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO
import pytest
from core.i18n import translate

from services.component_library_v2_adoption import (
    V2AdoptionError,
    V2_BLOCKED_IDS,
    build_v2_canonical_inventory,
    build_v2_direct_component,
    validate_v2_project_resolution,
    v2_adoption_summary,
    v2_assisted_confirmation_contract,
)
from services.mvp_multi_tu_persistence import (
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
from services.plant_component_workflow_registry import validate_saved_selection
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.registry_catalog_ui import (
    build_v2_user_provided_component,
    catalog_row_ui_state,
    component_role_for_catalog_record,
)


FORMAL_V2_IDS = {"V2-CMP-138", "V2-CMP-144"}


def _repository(tmp_path: Path, name: str = "V2 assisted"):
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    project = repository.create_blank(project_name=name)
    repository.save(project)
    return repository, project.project_id


def _assisted_row(component_type: str | None = None) -> dict[str, object]:
    return next(
        row
        for row in build_v2_canonical_inventory()
        if row["admission_mode"] == "USER_SEQUENCE_ASSISTED"
        and (component_type is None or row["component_type"] == component_type)
    )


def _assisted_component(row, repository, project_id):
    contract = v2_assisted_confirmation_contract(row)
    length = contract["expected_length"] or (12 if row["component_type"] == "cds" else 8)
    # Deliberately synthetic test DNA, never accession evidence.
    sequence = "ATG" + "GCC" * ((length - 6) // 3) + "TAA" if row["component_type"] == "cds" else ("AACCGGTT" * (length // 8 + 1))[:length]
    return build_v2_user_provided_component(
        row,
        raw_sequence=sequence,
        display_name=str(row["name"]),
        project_id=project_id,
        project_repository=repository,
        user_sequence_source=f"{row['canonical_v2_component_id']}.fa",
        identity_and_boundaries_confirmed=True,
        project_intent_confirmed=True,
        explicit_user_confirmation=True,
    )


def _plain_component(name: str, sequence: str) -> dict[str, object]:
    return {
        "display_name": name,
        "raw_text": sequence,
        "source_type": "paste",
        "source_format": "plain",
        "source_name": "test input",
        "provenance_reference": "test input",
    }


def test_exact_inventory_and_current_formal_admission() -> None:
    rows = build_v2_canonical_inventory()
    assert v2_adoption_summary(rows) == {
        "canonical_total": 171,
        "core": 41,
        "direct_use": 17,
        "user_sequence_assisted": 24,
        "reference": 95,
        "retired": 35,
        "legacy_mappings": 156,
    }
    assert len({row["canonical_v2_component_id"] for row in rows}) == 171
    assert {
        row["canonical_v2_component_id"]
        for row in rows
        if row["formal_selectable"]
    } == FORMAL_V2_IDS
    assert {
        row["registry_component_id"]
        for row in rows
        if row["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}


def test_remaining_direct_use_assets_fail_closed_with_explicit_reasons() -> None:
    rows = [
        row
        for row in build_v2_canonical_inventory()
        if row["admission_mode"] == "DIRECT_USE"
        and row["canonical_v2_component_id"] not in FORMAL_V2_IDS
    ]
    assert len(rows) == 15
    for row in rows:
        state = catalog_row_ui_state(row)
        assert state["state_key"] == "qualified_direct_not_admitted"
        assert state["formal_selectable"] is False
        assert "current_host_applicability_not_proven" in row["adoption_blockers"]
        with pytest.raises(V2AdoptionError, match="lacks current Registry/host admission"):
            build_v2_direct_component(
                row, role=component_role_for_catalog_record(row)
            )


def test_all_assisted_records_require_project_source_and_two_confirmations(
    tmp_path: Path,
) -> None:
    repository, project_id = _repository(tmp_path)
    rows = [
        row
        for row in build_v2_canonical_inventory()
        if row["admission_mode"] == "USER_SEQUENCE_ASSISTED"
    ]
    assert len(rows) == 24
    for row in rows:
        assert catalog_row_ui_state(row)["can_offer_assisted_sequence"] is True
        component = _assisted_component(row, repository, project_id)
        resolution = component["resolved_component_evidence"]
        assert resolution["project_id"] == project_id
        assert resolution["catalog_component_id"] == row["canonical_v2_component_id"]
        assert resolution["sequence_source"] == "USER_SUPPLIED_CONFIRMED"
        assert all(resolution["checks"].values())
        assert validate_saved_selection(
            component["component_reference"],
            role=component_role_for_catalog_record(row),
            sequence=component["raw_text"],
            current_project_id=project_id,
            project_repository=repository,
        ) == component["component_reference"]

    row = rows[0]
    common = dict(
        record=row,
        raw_sequence="AACCGGTT",
        display_name=str(row["name"]),
        project_id=project_id,
        project_repository=repository,
    )
    with pytest.raises(ValueError, match="user_sequence_source_recorded"):
        build_v2_user_provided_component(
            **common,
            user_sequence_source="",
            identity_and_boundaries_confirmed=True,
            explicit_user_confirmation=True,
        )
    with pytest.raises(ValueError, match="identity_and_boundaries_confirmed"):
        build_v2_user_provided_component(
            **common,
            user_sequence_source="review.fa",
            identity_and_boundaries_confirmed=False,
            explicit_user_confirmation=True,
        )
    with pytest.raises(ValueError, match="explicit_user_confirmation"):
        build_v2_user_provided_component(
            **common,
            user_sequence_source="review.fa",
            identity_and_boundaries_confirmed=True,
            explicit_user_confirmation=False,
        )


def test_assisted_resolution_rejects_cross_project_and_tampering(tmp_path: Path) -> None:
    repository, project_id = _repository(tmp_path)
    other = repository.create_blank(project_name="Other")
    repository.save(other)
    component = _assisted_component(_assisted_row(), repository, project_id)
    resolution = component["resolved_component_evidence"]
    with pytest.raises(V2AdoptionError, match="another project"):
        validate_v2_project_resolution(
            resolution,
            project_id=other.project_id,
            sequence=component["raw_text"],
            repository=repository,
        )
    forged = copy.deepcopy(resolution)
    forged["sequence_sha256"] = "0" * 64
    with pytest.raises(V2AdoptionError, match="modified"):
        validate_v2_project_resolution(
            forged,
            project_id=project_id,
            sequence=component["raw_text"],
            repository=repository,
        )


def test_reference_and_retired_records_have_no_sequence_route() -> None:
    rows = build_v2_canonical_inventory()
    reference = [row for row in rows if row["library_tier"] == "REFERENCE"]
    retired = [row for row in rows if row["library_tier"] == "RETIRED"]
    assert len(reference) == 95
    assert len(retired) == 35
    assert V2_BLOCKED_IDS.issubset(
        {row["canonical_v2_component_id"] for row in reference}
    )
    assert all(
        not catalog_row_ui_state(row)["can_offer_user_sequence"] for row in reference
    )
    assert all(catalog_row_ui_state(row)["state_key"] == "retired" for row in retired)


def test_assisted_provenance_survives_canonical_exports_and_cold_reopen(
    tmp_path: Path,
) -> None:
    repository, project_id = _repository(tmp_path, "V2 assisted persistence")
    row = _assisted_row("promoter")
    promoter = _assisted_component(row, repository, project_id)
    result = generate_multi_tu_combined_construct(
        project_id=project_id,
        project_name="V2 assisted persistence",
        expression_units=[
            {
                "unit_id": "v2-assisted-tu-1",
                "display_name": "V2 assisted TU",
                "order": 1,
                "orientation": "forward",
                "promoter": promoter,
                "cds": _plain_component("User CDS", "ATGGCCGCCTAA"),
                "3_prime_regulatory_region": _plain_component(
                    "User 3-prime region", "TTTTACGT"
                ),
            }
        ],
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }
    canonical = result["combined_construct"]["dna"]
    fasta = next(
        SeqIO.parse(
            StringIO(result["exports"]["combined_construct_fasta"]["data"]),
            "fasta",
        )
    )
    genbank = next(
        SeqIO.parse(
            StringIO(result["exports"]["combined_construct_genbank"]["data"]),
            "genbank",
        )
    )
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    promoter_feature = next(
        feature
        for feature in genbank.features
        if (feature.qualifiers.get("biological_role") or [""])[0] == "promoter"
    )
    assert promoter_feature.qualifiers["catalog_component_id"] == [
        row["canonical_v2_component_id"]
    ]
    assert promoter_feature.qualifiers["admission_mode"] == [
        "USER_SEQUENCE_ASSISTED"
    ]
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    reopened_reference = reopened["expression_units"][0]["component_references"][
        "promoter"
    ]
    assert reopened_reference == promoter["component_reference"]
    assert reopened["exports"] == result["exports"]


def test_app_exposes_canonical_v2_and_explicit_assisted_confirmations() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    section = source.split("def _render_plant_component_library", 1)[1]
    assert "build_v2_canonical_inventory" in source
    assert 'v1.component_library.v2_canonical_id' in section
    assert "formal_library_user_source_" in section
    assert "formal_library_user_identity_confirm_" in section
    assert "formal_library_user_use_confirm_" in section
    assert "build_v2_user_provided_component" in section


def _component_library_label_for(language: str):
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    wanted = {
        "_COMPONENT_LIBRARY_CONTROLLED_LABEL_KEYS",
        "_component_library_label",
    }
    nodes = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef) and node.name in wanted
        )
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id in wanted
                for target in node.targets
            )
        )
    ]
    namespace: dict[str, Any] = {
        "Any": Any,
        "_t": lambda key: translate(key, language=language),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py:v2-i18n", "exec"), namespace)
    return namespace["_component_library_label"]


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_real_catalog_row_markup_keeps_full_names_badges_and_long_action_labels(language):
    from html import escape
    from html.parser import HTMLParser

    class RowText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.divs = []
            self.classes = []

        def handle_starttag(self, tag, attrs):
            if tag == "div":
                self.classes.append(dict(attrs).get("class"))
                self.divs.append([])

        def handle_data(self, data):
            self.divs[-1].append(data)

    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_render_plant_component_library")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    markup = next(node.args[0] for node in calls if isinstance(node.func, ast.Attribute)
                  and node.func.attr == "markdown" and node.args
                  and "library-name" in ast.get_source_segment(source, node.args[0]))
    action = next(node.args[0] for node in calls if isinstance(node.func, ast.Attribute)
                  and node.func.attr == "button"
                  and any(key.arg == "key" and "formal_library_use_" in ast.get_source_segment(source, key.value) for key in node.keywords))
    markup_code = compile(ast.Expression(markup), "app.py:catalog-row", "eval")
    action_code = compile(ast.Expression(action), "app.py:catalog-action", "eval")
    labels = _component_library_label_for(language)
    actions = set()
    badge_texts = set()
    longest_name = 0
    max_badges = 0
    for record in build_v2_canonical_inventory():
        state = catalog_row_ui_state(record)
        ns = {"record": record, "ui_state": state, "escape": escape,
              "_component_library_label": labels,
              "_t": lambda key: translate(key, language=language)}
        parsed = RowText()
        parsed.feed(eval(markup_code, ns))
        assert parsed.classes == ["library-name", "library-status-group"]
        assert parsed.divs[0] == [record["name"]]
        assert parsed.divs[1] == [labels(badge) for badge in state["badges"]]
        badge_texts.update(parsed.divs[1])
        max_badges = max(max_badges, len(state["badges"]))
        longest_name = max(longest_name, len(record["name"]))
        actions.add(eval(action_code, ns))
    assert longest_name > 60 and max_badges >= 3
    assert translate("v1.component_library.not_directly_usable", language=language) in actions
    assert not any("v1." in text for text in actions | badge_texts)
    if language == "en":
        assert "Not directly usable" in actions
        assert {"Reference only", "Formal selection unavailable", "Identity requires manual review",
                "User sequence required", "Available after project confirmation", "Retired",
                "Unavailable for new designs", "Boundary requires manual review"} <= badge_texts
        assert not any("\u3400" <= char <= "\u9fff" for text in actions | badge_texts for char in text)
    # Existing catalog detail format must keep its placeholder after adding Step 3 labels.
    assert "V2-CMP-004" in translate("v1.component_library.v2_canonical_id", language=language, p0="V2-CMP-004")


def test_v2_ui_copy_reaches_english_and_chinese_without_chinese_leaks() -> None:
    expected_keys = {
        "v1.component_library.v2_inventory_caption": (
            "Plant expression design component catalog · V2 · 171 canonical identities",
            "植物表达设计元件目录 · V2 · 171 个规范身份",
        ),
        "v1.component_library.v2_governance_caption": (
            "V2 qualification, current Registry admission, and project-scoped user-sequence resolution are shown separately; catalog visibility does not grant host or workflow admission.",
            "V2 资格、当前 Registry 正式准入和项目内用户序列解析分别显示；目录可见性不自动授予主机或工作流准入。",
        ),
        "v1.component_library.v2_count_summary": (
                "Inventory: 171 total · DIRECT_USE identities 17 (2 currently formally admitted) · user-sequence assisted 24 · reference-only 95 · retired 35",
                "库存：171 条 · DIRECT_USE 身份 17 条（当前正式准入 2 条） · 用户序列辅助 24 条 · 仅供参考 95 条 · 已退役 35 条",
        ),
        "v1.component_library.v2_reference_badge": ("Reference only", "仅供参考"),
        "v1.component_library.v2_assisted_confirmed_badge": (
            "Available after project confirmation",
            "项目内确认后可用",
        ),
        "v1.component_library.v2_direct_not_admitted_distribution": (
            "V2 DIRECT_USE asset recorded",
            "V2 直接使用（DIRECT_USE）资产已记录",
        ),
        "v1.component_library.v2_new_design_unavailable_badge": (
            "Unavailable for new designs",
            "新设计不可用",
        ),
    }
    for key, (english, chinese) in expected_keys.items():
        params = (
            {"p0": 171}
            if key.endswith("v2_inventory_caption")
            else {"p0": 17, "p1": 2, "p2": 24, "p3": 95, "p4": 35}
            if key.endswith("v2_count_summary")
            else {}
        )
        assert translate(key, language="en", **params) == english
        assert translate(key, language="zh-CN", **params) == chinese
        assert not any("\u3400" <= char <= "\u9fff" for char in english)

    assert translate(
        "v1.component_library.all_sources_host_contexts", language="zh-CN"
    ) == "全部来源/宿主上下文"
    assert translate(
        "v1.component_library.source_accession",
        language="zh-CN",
        p0="AB123.1",
    ) == "来源登录号（accession）：AB123.1"

    english_label = _component_library_label_for("en")
    chinese_label = _component_library_label_for("zh-CN")
    for raw, english, chinese in (
        ("仅供参考", "Reference only", "仅供参考"),
        ("项目内确认后可用", "Available after project confirmation", "项目内确认后可用"),
        ("V2 DIRECT_USE 资产已记录", "V2 DIRECT_USE asset recorded", "V2 直接使用（DIRECT_USE）资产已记录"),
        ("新设计不可用", "Unavailable for new designs", "新设计不可用"),
    ):
        assert english_label(raw) == english
        assert chinese_label(raw) == chinese

    rows_by_state = {
        catalog_row_ui_state(row)["state_key"]: catalog_row_ui_state(row)
        for row in build_v2_canonical_inventory()
    }
    for state in rows_by_state.values():
        display_values = [
            state["state_label"],
            state["distribution_label"],
            state["sequence_label"],
            state["workflow_label"],
            *state["badges"],
        ]
        assert all(
            not any("\u3400" <= char <= "\u9fff" for char in english_label(value))
            for value in display_values
        )
        assert all(chinese_label(value) for value in display_values)

    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    section = source.split("def _render_plant_component_library", 1)[1]
    for key in (
        "v1.component_library.v2_inventory_caption",
        "v1.component_library.v2_governance_caption",
        "v1.component_library.v2_count_summary",
        "v1.component_library.v2_canonical_id",
        "v1.component_library.v2_user_sequence_source",
        "v1.component_library.v2_identity_confirmation",
        "v1.component_library.v2_use_confirmation",
    ):
        assert key in section
