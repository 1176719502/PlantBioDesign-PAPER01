# -*- coding: utf-8 -*-
"""
views/ModuleOverview.py
~~~~~~~~~~~~~~~~~~~~~~~
Module Center — registry-driven catalog of all BioDesign Studio modules.

Reads from core.module_registry (single source of truth).
Groups modules by layer: core (6) / tool (4) / hidden (2).
Route key stays "Module Overview" — no change to app.py routing.

Batch 1 scope (V1.2):
  - Registry-driven card grid (this file).
  - Visibility toggles: deferred to Step 5.
  - Homepage sync:       deferred to Step 3.
  - Sidebar sync:        deferred to Step 4.
"""
from __future__ import annotations

import streamlit as st

from core.module_registry import MODULE_REGISTRY, list_by_layer


# ---------------------------------------------------------------------------
# Layer display config
# ---------------------------------------------------------------------------

_LAYER_META: dict[str, dict] = {
    "core": {
        "label": "核心",
        "heading": "核心模块",
        "badge_bg": "#dcfce7",
        "badge_fg": "#15803d",
        "dot": "#16a34a",
        "legend": "始终启用的基础页面。",
    },
    "tool": {
        "label": "工具",
        "heading": "工具模块",
        "badge_bg": "#eff6ff",
        "badge_fg": "#1d4ed8",
        "dot": "#3b82f6",
        "legend": "当前版本提供的功能模块。",
    },
    "hidden": {
        "label": "隐藏",
        "heading": "隐藏模块",
        "badge_bg": "#f3f4f6",
        "badge_fg": "#6b7280",
        "dot": "#9ca3af",
        "legend": "当前不在导航中显示的保留页面。",
    },
}

_CATEGORY_CHIP: dict[str, str] = {
    "system": "#e0f2fe",
    "workflow": "#fef9c3",
    "data": "#fce7f3",
    "tools": "#f3e8ff",
    "experimental": "#fee2e2",
}

_CATEGORY_LABEL: dict[str, str] = {
    "system": "系统",
    "workflow": "工作流",
    "data": "数据",
    "tools": "工具",
    "experimental": "实验性",
}


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
/* ── Module Overview shell ─────────────────────────────────────── */
.mc-hero {
    background: linear-gradient(120deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-radius: 12px;
    padding: 22px 28px;
    margin-bottom: 20px;
}
.mc-hero-eyebrow {
    font-size: .68rem; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; color: #0284c7; margin-bottom: 6px;
}
.mc-hero-title {
    font-size: 1.2rem; font-weight: 700; color: #0c4a6e;
    letter-spacing: -.3px; margin-bottom: 6px;
}
.mc-hero-body {
    font-size: .84rem; color: #334155; line-height: 1.6;
}
.mc-stats {
    display: flex; gap: 16px; flex-wrap: wrap;
    margin-top: 14px;
}
.mc-stat {
    background: #fff; border: 1px solid #bae6fd; border-radius: 8px;
    padding: 8px 16px; text-align: center;
}
.mc-stat-num { font-size: 1.1rem; font-weight: 700; color: #0c4a6e; }
.mc-stat-lbl { font-size: .68rem; color: #6b7280; margin-top: 1px; }

/* ── Legend ─────────────────────────────────────────────────── */
.mc-legend {
    display: flex; gap: 20px; flex-wrap: wrap;
    padding: 12px 16px;
    background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
    margin-bottom: 20px;
}
.mc-legend-item { display: flex; align-items: center; gap: 7px; font-size: .78rem; color: #374151; }
.mc-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }

/* ── Section header ─────────────────────────────────────────── */
.mc-sec {
    font-size: .68rem; font-weight: 700; letter-spacing: 1.1px;
    text-transform: uppercase; color: #6b7280;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 6px; margin: 24px 0 12px 0;
    display: flex; align-items: center; gap: 8px;
}
.mc-sec-count {
    background: #f3f4f6; color: #6b7280;
    border-radius: 10px; padding: 1px 7px;
    font-size: .65rem; font-weight: 600;
}

/* ── Module card ─────────────────────────────────────────────── */
.mc-card {
    display: flex; align-items: flex-start; gap: 14px;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 8px;
    transition: border-color .15s, box-shadow .15s;
}
.mc-card:hover { border-color: #bfdbfe; box-shadow: 0 2px 8px rgba(37,99,235,.07); }
.mc-body  { flex: 1; min-width: 0; }
.mc-name  { font-size: .92rem; font-weight: 700; color: #111827; margin-bottom: 2px; }
.mc-meta  { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; flex-wrap: wrap; }
.mc-ver   { font-size: .68rem; color: #9ca3af; font-family: monospace; }
.mc-cat   {
    font-size: .65rem; font-weight: 600; padding: 1px 7px;
    border-radius: 8px; text-transform: uppercase; letter-spacing: .3px;
}
.mc-desc  { font-size: .80rem; color: #374151; line-height: 1.45; }
.mc-badge {
    flex-shrink: 0;
    font-size: .66rem; font-weight: 700;
    padding: 3px 10px; border-radius: 20px;
    letter-spacing: .4px; text-transform: uppercase;
    white-space: nowrap; align-self: flex-start; margin-top: 2px;
}

/* ── Footer ─────────────────────────────────────────────────── */
.mc-footer {
    margin-top: 32px; padding-top: 14px;
    border-top: 1px solid #e5e7eb;
    font-size: .72rem; color: #9ca3af;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;
}
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _badge_html(layer: str) -> str:
    meta = _LAYER_META.get(layer, _LAYER_META["hidden"])
    return (
        f"<span class='mc-badge' "
        f"style='background:{meta['badge_bg']};color:{meta['badge_fg']}'>"
        f"{meta['label']}</span>"
    )


def _cat_chip_html(category: str) -> str:
    bg = _CATEGORY_CHIP.get(category, "#f3f4f6")
    cat_label = _CATEGORY_LABEL.get(category, category)
    return (
        f"<span class='mc-cat' style='background:{bg};color:#374151'>"
        f"{cat_label}</span>"
    )


def _legend_html() -> str:
    items = []
    for layer, meta in _LAYER_META.items():
        items.append(
            f"<div class='mc-legend-item'>"
            f"<div class='mc-dot' style='background:{meta['dot']}'></div>"
            f"<span><b>{meta['label']}</b> \u2014 {meta['legend']}</span>"
            f"</div>"
        )
    return "<div class='mc-legend'>" + "".join(items) + "</div>"


def _card_html(m: dict) -> str:
    badge = _badge_html(m["layer"])
    cat_chip = _cat_chip_html(m["category"])
    ver = m.get("version", "")
    return (
        f"<div class='mc-card'>"
        f"<div class='mc-body'>"
        f"<div class='mc-name'>{m['name']}</div>"
        f"<div class='mc-meta'>{cat_chip}<span class='mc-ver'>v{ver}</span></div>"
        f"<div class='mc-desc'>{m['description']}</div>"
        f"</div>"
        f"{badge}"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(change_page=None) -> None:  # noqa: D401
    """Render the Module Center page (registry-driven)."""
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Compute summary counts ───────────────────────────────────────────────
    core_mods = list_by_layer("core")
    tool_mods = list_by_layer("tool")
    hidden_mods = list_by_layer("hidden")
    total = len(MODULE_REGISTRY)

    # ── Hero ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="mc-hero">
            <div class="mc-hero-eyebrow">模块概览 &nbsp;&mdash;&nbsp; V1.2</div>
            <div class="mc-hero-title">生物设计工作室 &mdash; 当前模块列表</div>
            <div class="mc-hero-body">
                本页面列出生物设计工作室当前版本中的已注册模块，
                并按层级与类别展示页面组成。
                可用于查看当前可见模块与保留模块的划分。
            </div>
            <div class="mc-stats">
                <div class="mc-stat">
                    <div class="mc-stat-num">{total}</div>
                    <div class="mc-stat-lbl">模块总数</div>
                </div>
                <div class="mc-stat">
                    <div class="mc-stat-num">{len(core_mods)}</div>
                    <div class="mc-stat-lbl">核心</div>
                </div>
                <div class="mc-stat">
                    <div class="mc-stat-num">{len(tool_mods)}</div>
                    <div class="mc-stat-lbl">工具</div>
                </div>
                <div class="mc-stat">
                    <div class="mc-stat-num">{len(hidden_mods)}</div>
                    <div class="mc-stat-lbl">隐藏</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Legend ───────────────────────────────────────────────────────────────
    st.markdown(_legend_html(), unsafe_allow_html=True)

    # ── Module groups ────────────────────────────────────────────────────────
    groups = [
        ("core", core_mods),
        ("tool", tool_mods),
        ("hidden", hidden_mods),
    ]

    for layer_key, modules in groups:
        if not modules:
            continue
        meta = _LAYER_META[layer_key]
        heading = meta["heading"]
        count = len(modules)

        st.markdown(
            f"<div class='mc-sec'>"
            f"{heading}"
            f"<span class='mc-sec-count'>{count}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        for m in modules:
            st.markdown(_card_html(m), unsafe_allow_html=True)

    # ── Footer ───────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='mc-footer'>"
        "<span>生物设计工作室 v8.0.0 &nbsp;&middot;&nbsp; 模块概览 V1.2</span>"
        "<span>注册表：core/module_registry.py &nbsp;&middot;&nbsp; &copy; 2026 生物设计公司</span>"
        "</div>",
        unsafe_allow_html=True,
    )
