from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_NOTES_DOC = ROOT / "docs" / "archive" / "release_notes_v1_10_0.md"


REQUIRED_TERMS = [
    "v1.10.0 Release Candidate",
    "v1.10.0-rc-sanity-pass",
    "921 passed, 8 skipped, 2 warnings",
    "documentation-only",
    "Project export package",
    "Import package read-only preview",
    "Dry-run import plan",
    "Disabled gated import skeleton",
    "Real import execution from UI is not enabled",
    "Current decision: NO-GO",
    "No database writes are performed",
    "does not import or modify any project",
    "Create New Documentation Project is a future gated action preview only",
    "Execution is intentionally disabled in this build",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no original id restoration",
    "no wet-lab protocols",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not validate folding",
    "does not validate function",
    "does not validate expression",
    "does not certify cloning success",
    "full pytest",
    "manual UI smoke check",
    "separate explicitly approved gated execution branch",
]

FORBIDDEN_POSITIVE_CLAIMS = [
    "real import execution enabled",
    "ready to import",
    "production-ready",
    "experiment-ready",
    "validated pathway",
    "successful cloning",
    "successful PCR",
    "successful expression",
    "wet-lab protocol generated",
    "yield prediction result",
    "optimized pathway",
]

NEGATING_PREFIXES = (
    "no ",
    "not ",
    "never ",
    "without ",
    "does not ",
    "do not ",
    "must not ",
    "is not ",
    "are not ",
    "isn't ",
    "aren't ",
    "disabled ",
    "forbidden ",
    "unsupported ",
    "not recommended ",
)


def _read_release_notes() -> str:
    return RELEASE_NOTES_DOC.read_text(encoding="utf-8")


def _has_negating_context(content: str, match: re.Match[str]) -> bool:
    prefix_window = content[max(0, match.start() - 48) : match.start()].lower()
    normalized_prefix = re.sub(r"[\s\-]+", " ", prefix_window)
    return normalized_prefix.rstrip().endswith(NEGATING_PREFIXES)


def test_release_notes_doc_exists() -> None:
    assert RELEASE_NOTES_DOC.exists(), "v1.10.0 release notes should exist"


def test_release_notes_contains_required_terms() -> None:
    content = _read_release_notes()
    normalized = content.lower()

    missing_terms = [term for term in REQUIRED_TERMS if term.lower() not in normalized]

    assert not missing_terms, (
        "v1.10.0 release notes are missing required terms: "
        + ", ".join(missing_terms)
    )


def test_release_notes_do_not_make_dangerous_positive_claims() -> None:
    content = _read_release_notes()

    violations: list[str] = []
    for claim in FORBIDDEN_POSITIVE_CLAIMS:
        pattern = re.compile(re.escape(claim), re.IGNORECASE)
        for match in pattern.finditer(content):
            if not _has_negating_context(content, match):
                violations.append(claim)

    assert not violations, (
        "v1.10.0 release notes contain dangerous positive claims: "
        + ", ".join(sorted(set(violations)))
    )


def test_release_notes_scope_is_document_only() -> None:
    content = _read_release_notes().lower()

    assert "project import package preview is read-only" in content
    assert "no database writes are performed by preview" in content
    assert "preview does not import or modify any project" in content
    assert "execution is intentionally disabled in this build" in content
