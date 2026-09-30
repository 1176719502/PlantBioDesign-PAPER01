from pathlib import Path


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "archive" / "feature_completeness_audit_v1_12_0.md"


def test_feature_completeness_audit_document_contains_required_terms():
    text = DOC_PATH.read_text(encoding="utf-8")

    required_terms = [
        "Feature Completeness Audit",
        "v1.11.0-stable",
        "970 passed, 8 skipped, 2 warnings",
        "Completed workflows",
        "Incomplete workflows",
        "Preview-only",
        "Skeleton-only",
        "Contract-only",
        "User confusion risks",
        "Test coverage gaps",
        "Risk classification",
        "Recommended next development order",
        "real import execution remains disabled",
        "NO-GO",
        "documentation-only",
        "no database writes by preview",
        "no wet-lab protocols",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
    ]

    missing_terms = [term for term in required_terms if term not in text]
    assert missing_terms == []


def test_feature_completeness_audit_is_documentation_only():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "does not change product code" in text
    assert "does not connect real import execution" in text
    assert "does not write database records" in text
    assert "does not create projects" in text
