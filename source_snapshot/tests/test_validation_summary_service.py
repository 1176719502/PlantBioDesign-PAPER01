from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.validation_summary_service import (
    PRIMER_HIGH_RISK_CODE,
    PRIMER_REVIEW_CODE,
    build_primer_risk_summary,
    build_validation_conclusion,
    merge_validation_with_primer_risk,
)


def test_build_primer_risk_summary_returns_no_issue_for_recommended_pairs():
    primers = [
        {"Fragment Name": "FragA", "Quality Grade": "Recommended", "Quality Reasons": ["No warning triggered."]},
        {"Fragment Name": "FragB", "Quality Grade": "Recommended", "Quality Reasons": ["No warning triggered."]},
    ]

    summary = build_primer_risk_summary(primers)

    assert summary["recommended"] == 2
    assert summary["usable_with_risk"] == 0
    assert summary["not_recommended"] == 0
    assert summary["issue"] is None


def test_build_primer_risk_summary_returns_review_issue():
    primers = [
        {
            "Fragment Name": "FragRisk",
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Annealing Tm is slightly offset from target (60.0°C)."],
        }
    ]

    summary = build_primer_risk_summary(primers)

    assert summary["usable_with_risk"] == 1
    assert summary["issue"]["code"] == PRIMER_REVIEW_CODE
    assert "FragRisk" in summary["issue"]["why"]


def test_build_primer_risk_summary_returns_high_risk_issue():
    primers = [
        {
            "Fragment Name": "FragHigh",
            "Quality Grade": "Not Recommended",
            "Quality Reasons": ["High cross-dimer risk between primers (8 bp complementarity)."],
        }
    ]

    summary = build_primer_risk_summary(primers)

    assert summary["not_recommended"] == 1
    assert summary["issue"]["code"] == PRIMER_HIGH_RISK_CODE
    assert "FragHigh" in summary["issue"]["why"]


def test_merge_validation_with_primer_risk_removes_pass_issue_when_primer_risk_exists():
    base_issues = [
        {"severity": "info", "code": "PASS", "title": "All validation checks passed"}
    ]
    primers = [
        {"Fragment Name": "FragA", "Quality Grade": "Not Recommended", "Quality Reasons": ["High risk"]}
    ]

    merged, summary = merge_validation_with_primer_risk(base_issues, primers)

    assert summary["not_recommended"] == 1
    assert [issue["code"] for issue in merged] == [PRIMER_HIGH_RISK_CODE]


def test_merge_validation_without_primer_risk_keeps_pass_issue():
    base_issues = [
        {"severity": "info", "code": "PASS", "title": "All validation checks passed"}
    ]
    primers = [
        {"Fragment Name": "FragA", "Quality Grade": "Recommended", "Quality Reasons": ["No warning triggered."]}
    ]

    merged, summary = merge_validation_with_primer_risk(base_issues, primers)

    assert summary["recommended"] == 1
    assert [issue["code"] for issue in merged] == ["PASS"]


def test_build_validation_conclusion_handles_blocking_review_and_pass_states():
    blocking = build_validation_conclusion([
        {"severity": "critical", "code": "FRAME_ERROR"},
    ])
    review = build_validation_conclusion([
        {"severity": "warning", "code": PRIMER_REVIEW_CODE},
    ])
    high_risk = build_validation_conclusion([
        {"severity": "warning", "code": PRIMER_HIGH_RISK_CODE},
    ])
    passed = build_validation_conclusion([
        {"severity": "info", "code": "PASS"},
    ])

    assert blocking["status"] == "blocking"
    assert review["status"] == "review_required"
    assert high_risk["status"] == "high_risk_primer_review"
    assert passed["status"] == "passed"
