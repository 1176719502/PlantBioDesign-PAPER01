from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_wizard_step2_intake_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE,
    HOST_OPTION_GROUPS,
    HOST_REQUIRED_DOCUMENTATION_SLOTS,
    TAG_OPTION_GROUPS,
    TAG_POSITION_OPTIONS,
    build_step2_host_tag_readback,
    flatten_grouped_options,
    resolve_host_selection,
    resolve_tag_selection,
)


def _labels(groups: list[dict]) -> set[str]:
    labels: set[str] = set()
    for group in groups:
        for option in group["options"]:
            labels.add(option["label"])
    return labels


def test_step2_exposes_broader_grouped_host_system_options() -> None:
    flat, selectable = flatten_grouped_options(HOST_OPTION_GROUPS)
    labels = _labels(HOST_OPTION_GROUPS)

    for group_label in [
        "-- Bacterial expression --",
        "-- Yeast expression --",
        "-- Mammalian expression --",
        "-- Plant expression --",
        "-- Other / undecided --",
    ]:
        assert group_label in flat

    for option_label in [
        "E. coli BL21(DE3)",
        "E. coli K-12 derivative / cloning strain context",
        "Saccharomyces cerevisiae",
        "Komagataella/Pichia expression context",
        "HEK293 expression context",
        "CHO expression context",
        "Nicotiana benthamiana transient expression context",
        "Rice/cereal plant expression context",
        "Cell-free expression context",
        "Host not decided yet",
        "Custom host / manual documentation required",
    ]:
        assert option_label in labels
        assert option_label in selectable


def test_step2_exposes_broader_grouped_fusion_tag_options_and_positions() -> None:
    flat, selectable = flatten_grouped_options(TAG_OPTION_GROUPS)
    labels = _labels(TAG_OPTION_GROUPS)

    for group_label in [
        "-- No tag / undecided --",
        "-- Affinity tag --",
        "-- Solubility / folding support tag --",
        "-- Detection / reporter context --",
        "-- Localization / secretion context --",
        "-- Custom / manual --",
    ]:
        assert group_label in flat

    for option_label in [
        "No fusion tag",
        "Tag strategy not decided yet",
        "His6-tag",
        "Strep-tag",
        "FLAG-tag",
        "GST-tag",
        "MBP-tag",
        "SUMO-tag",
        "NusA-tag",
        "HA-tag",
        "Myc-tag",
        "GFP/reporter fusion context",
        "Signal peptide recorded separately",
        "Localization tag recorded separately",
        "Custom tag / manual documentation required",
    ]:
        assert option_label in labels
        assert option_label in selectable

    assert TAG_POSITION_OPTIONS == [
        "N-terminal",
        "C-terminal",
        "Internal / fusion context unclear",
        "Not recorded",
    ]


def test_host_system_selection_maps_to_required_documentation_slots() -> None:
    cases = {
        "E. coli BL21(DE3)": "bacterial",
        "Saccharomyces cerevisiae": "yeast",
        "HEK293 expression context": "mammalian",
        "Nicotiana benthamiana transient expression context": "plant",
        "Cell-free expression context": "other",
    }

    for label, family in cases.items():
        selection = resolve_host_selection(label)
        assert selection["family"] == family
        assert selection["required_slots"] == HOST_REQUIRED_DOCUMENTATION_SLOTS[family]
        assert selection["can_confirm"] is True

    bacterial_slots = resolve_host_selection("E. coli BL21(DE3)")["required_slots"]
    assert "promoter/regulatory element" in bacterial_slots
    assert "RBS / translation initiation context" in bacterial_slots
    assert "terminator" in bacterial_slots
    assert "vector/backbone source" in bacterial_slots
    assert "tag source/provenance status" in bacterial_slots


def test_custom_manual_and_undecided_options_are_available_without_schema_change() -> None:
    custom_host = resolve_host_selection("Custom host / manual documentation required")
    undecided_host = resolve_host_selection("Host not decided yet")
    custom_tag = resolve_tag_selection("Custom tag / manual documentation required", ["No tag"])
    undecided_tag = resolve_tag_selection("Tag strategy not decided yet", ["No tag"])

    assert custom_host["requires_manual_entry"] is True
    assert custom_host["runtime_host"] == ""
    assert custom_host["can_confirm"] is False
    assert undecided_host["is_undecided"] is True
    assert undecided_host["can_confirm"] is False
    assert custom_tag["requires_manual_entry"] is True
    assert custom_tag["runtime_tag"] == "No tag"
    assert undecided_tag["is_undecided"] is True


def test_tag_selection_maps_only_to_supported_runtime_tag_options() -> None:
    his_for_ecoli = resolve_tag_selection("His6-tag", ["His6-tag (C-term)", "No tag"])
    strep_for_ecoli = resolve_tag_selection("Strep-tag", ["His6-tag (C-term)", "No tag"])
    flag_for_hek = resolve_tag_selection("FLAG-tag", ["His6-tag (C-term)", "FLAG-tag (N-term)", "No tag"])

    assert his_for_ecoli["runtime_tag"] == "His6-tag (C-term)"
    assert his_for_ecoli["directly_mapped"] is True
    assert strep_for_ecoli["runtime_tag"] == "No tag"
    assert strep_for_ecoli["directly_mapped"] is False
    assert "review only" in strep_for_ecoli["documentation_status"]
    assert flag_for_hek["runtime_tag"] == "FLAG-tag (N-term)"
    assert flag_for_hek["directly_mapped"] is True


def test_host_tag_readback_is_documentation_only_and_lists_review_fields() -> None:
    host_selection = resolve_host_selection("HEK293 expression context")
    tag_selection = resolve_tag_selection("HA-tag", ["His6-tag (C-term)", "FLAG-tag (N-term)", "No tag"])

    readback = build_step2_host_tag_readback(
        host_selection=host_selection,
        tag_selection=tag_selection,
        tag_position="Internal / fusion context unclear",
        manual_source_note="Record source follow-up.",
    )

    assert readback["selected_host_system"] == "HEK293 expression context"
    assert readback["selected_tag_strategy"] == "HA-tag"
    assert readback["tag_position"] == "Internal / fusion context unclear"
    assert "promoter/enhancer context" in readback["required_manual_review_fields"]
    assert "Kozak / translation initiation context" in readback["required_manual_review_fields"]
    assert "tag source/provenance status" in readback["required_manual_review_fields"]
    assert "manual tag label/source/provenance note" in readback["required_manual_review_fields"]
    assert readback["boundary_note"] == DOCUMENTATION_BOUNDARY_NOTE
    assert "documentation inputs only" in readback["boundary_note"]


def test_step2_host_tag_intake_copy_avoids_forbidden_claims() -> None:
    rendered = "\n".join(
        [
            str(HOST_OPTION_GROUPS),
            str(TAG_OPTION_GROUPS),
            str(HOST_REQUIRED_DOCUMENTATION_SLOTS),
            DOCUMENTATION_BOUNDARY_NOTE,
            str(resolve_host_selection("Custom host / manual documentation required")),
            str(resolve_tag_selection("Strep-tag", ["No tag"])),
        ]
    ).lower()

    for forbidden in [
        "best host",
        "best promoter",
        "best tag",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "generated construct output",
    ]:
        assert forbidden not in rendered

    assert "biological recommendation" in rendered
    assert "validation" in rendered
    assert "optimization" in rendered
    assert "build readiness" in rendered


def test_component_library_context_remains_compact_by_default() -> None:
    source = (Path(ROOT) / "views" / "wizard_steps" / "step2_host_elements.py").read_text(encoding="utf-8")

    assert "Additional context records are hidden by default to keep Step 2 readable." in source
    assert 'st.expander("Review all linked component context records", expanded=False)' in source
