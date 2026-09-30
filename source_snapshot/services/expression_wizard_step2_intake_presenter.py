from __future__ import annotations

from typing import Any


DOCUMENTATION_BOUNDARY_NOTE = (
    "Host and tag selections are documentation inputs only. They do not represent "
    "biological recommendation, validation, optimization, or build readiness."
)

TAG_POSITION_OPTIONS = [
    "N-terminal",
    "C-terminal",
    "Internal / fusion context unclear",
    "Not recorded",
]

HOST_OPTION_GROUPS: list[dict[str, Any]] = [
    {
        "group": "Bacterial expression",
        "options": [
            {
                "label": "E. coli BL21(DE3)",
                "runtime_host": "E.coli BL21(DE3)",
                "family": "bacterial",
            },
            {
                "label": "E. coli K-12 derivative / cloning strain context",
                "runtime_host": "E.coli DH5alpha",
                "family": "bacterial",
            },
            {
                "label": "E. coli expression host, custom/manual entry",
                "runtime_host": "",
                "family": "bacterial",
                "manual_entry": True,
            },
        ],
    },
    {
        "group": "Yeast expression",
        "options": [
            {
                "label": "Saccharomyces cerevisiae",
                "runtime_host": "S. cerevisiae",
                "family": "yeast",
            },
            {
                "label": "Komagataella/Pichia expression context",
                "runtime_host": "P. pastoris (K. phaffii)",
                "family": "yeast",
            },
            {
                "label": "Yeast expression host, custom/manual entry",
                "runtime_host": "",
                "family": "yeast",
                "manual_entry": True,
            },
        ],
    },
    {
        "group": "Mammalian expression",
        "options": [
            {"label": "HEK293 expression context", "runtime_host": "HEK293", "family": "mammalian"},
            {"label": "CHO expression context", "runtime_host": "CHO cells", "family": "mammalian"},
            {
                "label": "Mammalian expression host, custom/manual entry",
                "runtime_host": "",
                "family": "mammalian",
                "manual_entry": True,
            },
        ],
    },
    {
        "group": "Plant expression",
        "options": [
            {
                "label": "Nicotiana benthamiana transient expression context",
                "runtime_host": "Tobacco (N. benthamiana)",
                "family": "plant",
            },
            {
                "label": "Rice/cereal plant expression context",
                "runtime_host": "Rice (O. sativa)",
                "family": "plant",
            },
            {
                "label": "Plant expression host, custom/manual entry",
                "runtime_host": "",
                "family": "plant",
                "manual_entry": True,
            },
        ],
    },
    {
        "group": "Other / undecided",
        "options": [
            {
                "label": "Cell-free expression context",
                "runtime_host": "Cell-free (E. coli lysate)",
                "family": "other",
            },
            {
                "label": "Host not decided yet",
                "runtime_host": "",
                "family": "other",
                "manual_entry": True,
                "undecided": True,
            },
            {
                "label": "Custom host / manual documentation required",
                "runtime_host": "",
                "family": "other",
                "manual_entry": True,
            },
        ],
    },
]

TAG_OPTION_GROUPS: list[dict[str, Any]] = [
    {
        "group": "No tag / undecided",
        "options": [
            {"label": "No fusion tag", "runtime_tag_candidates": ["No tag"], "default_position": "Not recorded"},
            {
                "label": "Tag strategy not decided yet",
                "runtime_tag_candidates": ["No tag"],
                "default_position": "Not recorded",
                "manual_entry": True,
                "undecided": True,
            },
        ],
    },
    {
        "group": "Affinity tag",
        "options": [
            {
                "label": "His6-tag",
                "runtime_tag_candidates": ["His6-tag (C-term)", "His6-tag", "His6-tag (N-term)"],
                "default_position": "C-terminal",
            },
            {
                "label": "Strep-tag",
                "runtime_tag_candidates": ["Strep-tag II (C-term)"],
                "default_position": "C-terminal",
            },
            {
                "label": "FLAG-tag",
                "runtime_tag_candidates": ["FLAG-tag (C-term)", "FLAG-tag (N-term)"],
                "default_position": "N-terminal",
            },
            {
                "label": "GST-tag",
                "runtime_tag_candidates": ["GST-tag (N-term)"],
                "default_position": "N-terminal",
            },
        ],
    },
    {
        "group": "Solubility / folding support tag",
        "options": [
            {"label": "MBP-tag", "runtime_tag_candidates": ["MBP-tag (N-term)"], "default_position": "N-terminal"},
            {"label": "SUMO-tag", "runtime_tag_candidates": ["SUMO-tag (N-term)"], "default_position": "N-terminal"},
            {"label": "NusA-tag", "runtime_tag_candidates": ["NusA-tag"], "default_position": "N-terminal"},
        ],
    },
    {
        "group": "Detection / reporter context",
        "options": [
            {"label": "HA-tag", "runtime_tag_candidates": ["HA-tag"], "default_position": "Internal / fusion context unclear"},
            {"label": "Myc-tag", "runtime_tag_candidates": ["Myc-tag"], "default_position": "Internal / fusion context unclear"},
            {
                "label": "GFP/reporter fusion context",
                "runtime_tag_candidates": ["GFP fusion (C-term)"],
                "default_position": "C-terminal",
            },
        ],
    },
    {
        "group": "Localization / secretion context",
        "options": [
            {
                "label": "Signal peptide recorded separately",
                "runtime_tag_candidates": ["No tag"],
                "default_position": "N-terminal",
                "manual_entry": True,
            },
            {
                "label": "Localization tag recorded separately",
                "runtime_tag_candidates": ["No tag"],
                "default_position": "Internal / fusion context unclear",
                "manual_entry": True,
            },
        ],
    },
    {
        "group": "Custom / manual",
        "options": [
            {
                "label": "Custom tag / manual documentation required",
                "runtime_tag_candidates": ["No tag"],
                "default_position": "Not recorded",
                "manual_entry": True,
            }
        ],
    },
]

HOST_REQUIRED_DOCUMENTATION_SLOTS: dict[str, list[str]] = {
    "bacterial": [
        "promoter/regulatory element",
        "RBS / translation initiation context",
        "terminator",
        "vector/backbone source",
        "tag source/provenance status",
    ],
    "yeast": [
        "promoter/regulatory element",
        "terminator",
        "selectable marker context",
        "secretion/localization status if relevant",
        "vector/backbone source",
        "tag source/provenance status",
    ],
    "mammalian": [
        "promoter/enhancer context",
        "Kozak / translation initiation context",
        "signal peptide or localization status",
        "polyA / terminator context",
        "vector/backbone source",
        "tag source/provenance status",
    ],
    "plant": [
        "promoter/regulatory element",
        "terminator context",
        "transit peptide/localization status if relevant",
        "selectable marker context",
        "vector/backbone source",
        "tag source/provenance status",
    ],
    "other": [
        "expression system source/provenance status",
        "regulatory element context if applicable",
        "translation initiation context if applicable",
        "termination/polyA context if applicable",
        "vector/backbone or reaction system source",
        "tag source/provenance status",
    ],
}


def flatten_grouped_options(groups: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    flat: list[str] = []
    selectable: list[str] = []
    for group in groups:
        flat.append(f"-- {group['group']} --")
        for option in group.get("options", []):
            label = str(option.get("label") or "")
            if label:
                flat.append(label)
                selectable.append(label)
    return flat, selectable


def _option_by_label(groups: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for group in groups:
        for option in group.get("options", []):
            if option.get("label") == label:
                return dict(option, group=group.get("group", ""))
    return {}


def _first_label_for_runtime(groups: list[dict[str, Any]], runtime_value: str, runtime_key: str) -> str:
    for group in groups:
        for option in group.get("options", []):
            if option.get(runtime_key) == runtime_value:
                return str(option.get("label") or "")
    return ""


def host_label_for_runtime(runtime_host: str) -> str:
    return _first_label_for_runtime(HOST_OPTION_GROUPS, runtime_host, "runtime_host")


def tag_label_for_runtime(runtime_tag: str) -> str:
    runtime_tag = str(runtime_tag or "")
    if runtime_tag == "No tag":
        return "No fusion tag"
    for group in TAG_OPTION_GROUPS:
        for option in group.get("options", []):
            if runtime_tag in option.get("runtime_tag_candidates", []):
                return str(option.get("label") or "")
    if runtime_tag.startswith("His6-tag") or runtime_tag == "His6-tag":
        return "His6-tag"
    if runtime_tag.startswith("FLAG-tag"):
        return "FLAG-tag"
    if runtime_tag.startswith("GST-tag"):
        return "GST-tag"
    if runtime_tag.startswith("GFP"):
        return "GFP/reporter fusion context"
    return "Custom tag / manual documentation required"


def resolve_host_selection(label: str) -> dict[str, Any]:
    option = _option_by_label(HOST_OPTION_GROUPS, label)
    if not option:
        option = _option_by_label(HOST_OPTION_GROUPS, "Host not decided yet")
    runtime_host = str(option.get("runtime_host") or "")
    family = str(option.get("family") or "other")
    slots = HOST_REQUIRED_DOCUMENTATION_SLOTS.get(family, HOST_REQUIRED_DOCUMENTATION_SLOTS["other"])
    manual_entry = bool(option.get("manual_entry"))
    return {
        "selected_label": str(option.get("label") or label or "Host not decided yet"),
        "group": str(option.get("group") or "Other / undecided"),
        "runtime_host": runtime_host,
        "family": family,
        "requires_manual_entry": manual_entry,
        "is_undecided": bool(option.get("undecided")),
        "can_confirm": bool(runtime_host),
        "required_slots": slots,
        "documentation_status": (
            "Concrete host/system mapped to the existing documentation workflow."
            if runtime_host
            else "Manual host documentation required before Step 2 can be confirmed."
        ),
    }


def resolve_tag_selection(label: str, supported_runtime_tags: list[str] | tuple[str, ...]) -> dict[str, Any]:
    option = _option_by_label(TAG_OPTION_GROUPS, label)
    if not option:
        option = _option_by_label(TAG_OPTION_GROUPS, "Custom tag / manual documentation required")
    supported = list(supported_runtime_tags or [])
    runtime_tag = ""
    for candidate in option.get("runtime_tag_candidates", []):
        if candidate in supported:
            runtime_tag = str(candidate)
            break
    if not runtime_tag and "No tag" in supported:
        runtime_tag = "No tag"
    if not runtime_tag and supported:
        runtime_tag = str(supported[0])
    directly_mapped = runtime_tag in option.get("runtime_tag_candidates", [])
    documentation_status = (
        "Tag strategy maps to the selected host's existing frame-builder tag option."
        if directly_mapped
        else "Tag strategy recorded for review only; no tag sequence is generated for this selection in this batch."
    )
    return {
        "selected_label": str(option.get("label") or label or "Custom tag / manual documentation required"),
        "group": str(option.get("group") or "Custom / manual"),
        "runtime_tag": runtime_tag,
        "directly_mapped": directly_mapped,
        "requires_manual_entry": bool(option.get("manual_entry")) or not directly_mapped,
        "is_undecided": bool(option.get("undecided")),
        "default_position": str(option.get("default_position") or "Not recorded"),
        "documentation_status": documentation_status,
    }


def build_step2_host_tag_readback(
    *,
    host_selection: dict[str, Any],
    tag_selection: dict[str, Any],
    tag_position: str,
    custom_host_label: str = "",
    custom_tag_label: str = "",
    manual_source_note: str = "",
) -> dict[str, Any]:
    required_fields = list(host_selection.get("required_slots") or [])
    if tag_selection.get("requires_manual_entry"):
        required_fields.append("manual tag label/source/provenance note")
    if host_selection.get("requires_manual_entry"):
        required_fields.append("manual host label/source/provenance note")
    if not manual_source_note.strip():
        required_fields.append("manual source/provenance note")

    return {
        "selected_host_system": custom_host_label.strip() or str(host_selection.get("selected_label") or ""),
        "selected_tag_strategy": custom_tag_label.strip() or str(tag_selection.get("selected_label") or ""),
        "tag_position": tag_position or "Not recorded",
        "documentation_status": "; ".join(
            filter(
                None,
                [
                    str(host_selection.get("documentation_status") or ""),
                    str(tag_selection.get("documentation_status") or ""),
                ],
            )
        ),
        "runtime_host": str(host_selection.get("runtime_host") or ""),
        "runtime_tag": str(tag_selection.get("runtime_tag") or ""),
        "required_manual_review_fields": list(dict.fromkeys(required_fields)),
        "manual_source_note_status": "recorded in this page session" if manual_source_note.strip() else "not recorded",
        "boundary_note": DOCUMENTATION_BOUNDARY_NOTE,
    }
