"""First-step project-definition state for the formal plant workspace.

The values in this module stay inside the existing ``formal_project_context``
snapshot.  They are documentation context, not biological recommendations or
an independent construct persistence model.
"""
from __future__ import annotations

from typing import Any


PROJECT_DEFINITION_SOURCE = "第一步：项目定义与表达目标"
APPLICATION_MODES = ("稳定遗传转化", "瞬时表达", "尚未确定")
TRANSIENT_EXPRESSION_SYSTEMS = (
    "农杆菌介导的植物组织瞬时表达",
    "植物原生质体瞬时转染",
    "其他瞬时表达体系",
    "尚未确定",
)
TISSUE_SPECIFICITY_REQUIREMENTS = (
    "无特定组织或器官限制",
    "组织或器官特异性表达",
    "尚未确定",
)
INDUCIBILITY_REQUIREMENTS = ("无特定诱导要求", "需要诱导型表达", "尚未确定")

PROJECT_DEFINITION_FIELDS = (
    "project_name",
    "plant_host",
    "material",
    "application_mode",
    "transient_expression_system",
    "tissue_specificity_requirement",
    "tissue_target",
    "inducibility_requirement",
    "induction_notes",
    "localization_target",
)
REVIEW_BASIS_FIELDS = (
    "plant_host",
    "application_mode",
    "transient_expression_system",
    "tissue_specificity_requirement",
    "tissue_target",
    "inducibility_requirement",
    "induction_notes",
    "localization_target",
)

_APPLICATION_MODE_MAP = {
    "稳定转化": "稳定遗传转化",
    "稳定转化记录": "稳定遗传转化",
    "稳定遗传转化": "稳定遗传转化",
    "瞬时": "瞬时表达",
    "瞬时表达": "瞬时表达",
    "瞬时表达记录": "瞬时表达",
    "原生质体": "瞬时表达",
    "原生质体表达记录": "瞬时表达",
}
_EXPRESSION_MODE_MAP = {
    "组成型表达": ("无特定组织或器官限制", "无特定诱导要求"),
    "组织或器官特异表达": ("组织或器官特异性表达", "尚未确定"),
    "组织或器官特异性表达": ("组织或器官特异性表达", "尚未确定"),
    "诱导型表达": ("尚未确定", "需要诱导型表达"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _option(value: Any, options: tuple[str, ...], default: str) -> str:
    text = _text(value)
    return text if text in options else default


def _legacy_mapping(source: dict[str, Any]) -> dict[str, str]:
    """Map one legacy two-axis record without discarding its raw values."""
    raw_application = _text(source.get("application_mode"))
    raw_expression = _text(source.get("expression_mode"))
    application_mode = _APPLICATION_MODE_MAP.get(raw_application, "尚未确定")
    transient_system = "植物原生质体瞬时转染" if raw_application in {"原生质体", "原生质体表达记录"} else "尚未确定"
    tissue_requirement, inducibility_requirement = _EXPRESSION_MODE_MAP.get(
        raw_expression,
        ("尚未确定", "尚未确定"),
    )
    requires_review = bool(
        (raw_application and raw_application not in _APPLICATION_MODE_MAP)
        or (raw_expression and raw_expression not in _EXPRESSION_MODE_MAP)
    )
    return {
        "application_mode": application_mode,
        "transient_expression_system": transient_system,
        "tissue_specificity_requirement": tissue_requirement,
        "inducibility_requirement": inducibility_requirement,
        "compatibility_review_required": "true" if requires_review else "false",
        "legacy_application_mode": raw_application,
        "legacy_expression_mode": raw_expression,
    }


def normalize_project_definition(
    value: dict[str, Any] | None,
    *,
    fallback_host: str = "",
) -> dict[str, str]:
    """Return the current field model while reading legacy two-axis records."""
    source = dict(value) if isinstance(value, dict) else {}
    uses_current_model = any(
        key in source
        for key in (
            "transient_expression_system",
            "tissue_specificity_requirement",
            "inducibility_requirement",
            "induction_notes",
        )
    )
    legacy = _legacy_mapping(source) if not uses_current_model else {}
    application_mode = _option(
        source.get("application_mode") if uses_current_model else legacy.get("application_mode"),
        APPLICATION_MODES,
        "尚未确定",
    )
    transient_system = _option(
        source.get("transient_expression_system") if uses_current_model else legacy.get("transient_expression_system"),
        TRANSIENT_EXPRESSION_SYSTEMS,
        "尚未确定",
    )
    tissue_requirement = _option(
        source.get("tissue_specificity_requirement") if uses_current_model else legacy.get("tissue_specificity_requirement"),
        TISSUE_SPECIFICITY_REQUIREMENTS,
        "尚未确定",
    )
    inducibility_requirement = _option(
        source.get("inducibility_requirement") if uses_current_model else legacy.get("inducibility_requirement"),
        INDUCIBILITY_REQUIREMENTS,
        "尚未确定",
    )
    return {
        "project_name": _text(source.get("project_name")),
        "plant_host": _text(source.get("plant_host") or source.get("host_key") or fallback_host),
        "material": _text(source.get("material")),
        "application_mode": application_mode,
        "transient_expression_system": transient_system,
        "tissue_specificity_requirement": tissue_requirement,
        # Keep a hidden historical target for review; callers decide when active.
        "tissue_target": _text(source.get("tissue_target")),
        "inducibility_requirement": inducibility_requirement,
        "induction_notes": _text(source.get("induction_notes")),
        "localization_target": _text(source.get("localization_target")),
        "compatibility_review_required": _text(
            source.get("compatibility_review_required") or legacy.get("compatibility_review_required")
        ) or "false",
        "legacy_application_mode": _text(source.get("legacy_application_mode") or legacy.get("legacy_application_mode")),
        "legacy_expression_mode": _text(source.get("legacy_expression_mode") or legacy.get("legacy_expression_mode")),
        "data_source": _text(source.get("data_source")) or PROJECT_DEFINITION_SOURCE,
    }


def is_tissue_target_active(definition: dict[str, Any] | None) -> bool:
    return normalize_project_definition(definition)["tissue_specificity_requirement"] == "组织或器官特异性表达"


def is_transient_system_active(definition: dict[str, Any] | None) -> bool:
    return normalize_project_definition(definition)["application_mode"] == "瞬时表达"


def is_induction_notes_active(definition: dict[str, Any] | None) -> bool:
    return normalize_project_definition(definition)["inducibility_requirement"] == "需要诱导型表达"


def active_project_definition_summary(definition: dict[str, Any] | None) -> list[str]:
    """Return only fields active under the selected conditional requirements."""
    normalized = normalize_project_definition(definition)
    parts = [normalized["application_mode"]]
    if is_transient_system_active(normalized):
        parts.append(normalized["transient_expression_system"])
    parts.append(normalized["tissue_specificity_requirement"])
    if is_tissue_target_active(normalized) and normalized["tissue_target"]:
        parts.append(normalized["tissue_target"])
    parts.append(normalized["inducibility_requirement"])
    if is_induction_notes_active(normalized) and normalized["induction_notes"]:
        parts.append(normalized["induction_notes"])
    if normalized["localization_target"]:
        parts.append(normalized["localization_target"])
    return parts


def construct_review_basis(definition: dict[str, Any] | None) -> dict[str, str]:
    """Select only background fields that require downstream review."""
    normalized = normalize_project_definition(definition)
    return {field: normalized[field] for field in REVIEW_BASIS_FIELDS}


def requires_construct_review(
    definition: dict[str, Any] | None,
    saved_basis: dict[str, Any] | None,
) -> bool:
    """Compare current project background with the construct's saved basis."""
    normalized = normalize_project_definition(definition)
    saved = normalize_project_definition(saved_basis)
    return (
        normalized["compatibility_review_required"] == "true"
        or construct_review_basis(normalized) != construct_review_basis(saved)
    )


def project_definition_from_context(
    context: dict[str, Any] | None,
    *,
    fallback_host: str = "",
    fallback_project_name: str = "",
) -> dict[str, str]:
    """Read new and legacy formal contexts without requiring a migration."""
    source = dict(context) if isinstance(context, dict) else {}
    nested = source.get("project_definition")
    definition = dict(nested) if isinstance(nested, dict) else {}
    definition.setdefault("plant_host", source.get("host_key") or fallback_host)
    definition.setdefault("project_name", fallback_project_name)
    return normalize_project_definition(definition, fallback_host=fallback_host)
