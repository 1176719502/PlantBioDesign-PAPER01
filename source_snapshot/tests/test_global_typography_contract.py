from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
GLOBAL_CSS = APP_SOURCE.split("<style>", 1)[1].split("</style>", 1)[0]


def _tokens() -> dict[str, str]:
    root = re.search(r":root\s*\{(?P<body>.*?)\}", GLOBAL_CSS, re.DOTALL)
    assert root is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root.group("body")))


def _rules() -> dict[str, dict[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", GLOBAL_CSS, flags=re.DOTALL)
    parsed: dict[str, dict[str, str]] = {}
    for rule in re.finditer(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", css):
        declarations = {
            name: re.sub(r"\s*!important\s*$", "", value.strip())
            for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+);", rule.group("body"))
        }
        if not declarations:
            continue
        for selector in rule.group("selectors").split(","):
            normalized = selector.strip()
            if normalized and not normalized.startswith("@"):
                parsed.setdefault(normalized, {}).update(declarations)
    return parsed


def _declarations(selector: str) -> dict[str, str]:
    declarations = _rules().get(selector)
    assert declarations is not None, f"missing typography selector: {selector}"
    return declarations


def test_global_typography_declares_governed_font_stacks_and_semantic_tokens() -> None:
    tokens = _tokens()
    assert tokens["--font-ui"] == (
        '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", '
        '"PingFang SC", Arial, sans-serif'
    )
    assert tokens["--font-mono"] == '"Cascadia Mono", Consolas, "Courier New", monospace'

    for token in (
        "--type-page-title",
        "--type-page-description",
        "--type-section-title",
        "--type-subsection-title",
        "--type-body",
        "--type-control",
        "--type-support",
        "--type-caption",
        "--type-micro",
        "--type-metric",
        "--type-sequence-code",
        "--weight-regular",
        "--weight-medium",
        "--weight-semibold",
        "--weight-bold",
        "--line-body",
        "--line-heading",
        "--line-compact",
    ):
        assert token in tokens


def test_global_typography_keeps_existing_token_compatibility_aliases() -> None:
    tokens = _tokens()
    expected_aliases = {
        "--font": "var(--font-ui)",
        "--mono": "var(--font-mono)",
        "--type-metric-value": "var(--type-metric)",
        "--weight-title": "var(--weight-bold)",
        "--weight-card-title": "var(--weight-semibold)",
        "--weight-control-primary": "var(--weight-semibold)",
        "--weight-control-secondary": "var(--weight-medium)",
        "--leading-title": "var(--line-heading)",
        "--leading-body": "var(--line-body)",
        "--leading-control": "var(--line-compact)",
        "--leading-micro": "var(--line-compact)",
    }
    assert {name: tokens[name] for name in expected_aliases} == expected_aliases


def test_base_text_roles_apply_semantic_typography_tokens() -> None:
    role_expectations = {
        "body": {"font-family": "var(--font-ui)"},
        "h1": {
            "font-family": "var(--font-ui)",
            "font-size": "var(--type-page-title)",
        },
        "p": {"font-family": "var(--font-ui)", "font-size": "var(--type-body)"},
        "label": {"font-family": "var(--font-ui)", "font-size": "var(--type-control)"},
        "input": {"font-family": "var(--font-ui)", "font-size": "var(--type-control)"},
        "textarea": {"font-family": "var(--font-ui)", "font-size": "var(--type-control)"},
        "select": {"font-family": "var(--font-ui)", "font-size": "var(--type-control)"},
        '[data-testid="stCaptionContainer"]': {
            "font-family": "var(--font-ui)",
            "font-size": "var(--type-caption)",
        },
        '[data-testid="stMarkdownContainer"]': {"font-family": "var(--font-ui)"},
        '[data-testid="stMain"] [data-testid="stButton"] > button': {
            "font-family": "var(--font-ui)",
            "font-size": "var(--type-control)",
        },
        '[data-testid="stTable"] table': {
            "font-family": "var(--font-ui)",
            "font-size": "var(--type-body)",
        },
        '[data-testid="stMetricValue"]': {
            "font-family": "var(--font-ui)",
            "font-size": "var(--type-metric)",
        },
        '[data-testid="stExpander"] summary': {"font-size": "var(--type-control)"},
    }
    for selector, expected in role_expectations.items():
        declarations = _declarations(selector)
        assert {name: declarations[name] for name in expected} == expected


def test_library_and_sequence_roles_use_support_micro_and_monospace_tokens() -> None:
    library_head = _declarations(".library-head")
    assert library_head["color"] == "var(--text-support)"
    assert library_head["font-size"] == "var(--type-micro)"
    assert _declarations(".library-cell")["font-size"] == "var(--type-control)"
    assert _declarations(".library-badge")["font-size"] == "var(--type-micro)"

    for selector in ("code", "pre", '[data-testid="stCodeBlock"]', ".library-accession"):
        declarations = _declarations(selector)
        assert declarations["font-family"] == "var(--font-mono)"
        assert declarations["font-size"] == "var(--type-sequence-code)"


def test_formal_global_css_has_no_remote_or_competing_font_family() -> None:
    assert "@import" not in GLOBAL_CSS.casefold()
    assert "@font-face" not in GLOBAL_CSS.casefold()
    assert "fonts.googleapis.com" not in GLOBAL_CSS.casefold()

    family_values = set(re.findall(r"font-family\s*:\s*([^;]+);", GLOBAL_CSS))
    assert family_values == {"var(--font-ui) !important", "var(--font-mono) !important"}
    assert not re.search(r"(?:^|,)\s*\*\s*(?:,|\{)", GLOBAL_CSS)
    assert not re.search(r"svg[^{}]*\{[^{}]*font-family", GLOBAL_CSS, re.DOTALL)
