from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.export_recommendation_service import build_export_recommendation
from services.validation_summary_service import PRIMER_HIGH_RISK_CODE, PRIMER_REVIEW_CODE


def test_export_recommendation_blocks_without_sequence():
    result = build_export_recommendation([], [], "")

    assert result["recommendation"] == "Review blocked by unresolved risk signals"
    assert result["tone"] == "warn"


def test_export_recommendation_blocks_with_critical_issue():
    result = build_export_recommendation(
        [{"severity": "critical", "code": "FRAME_ERROR"}],
        [],
        "ATGGCCTAA",
    )

    assert result["recommendation"] == "Review blocked by unresolved risk signals"
    assert result["critical_count"] == 1


def test_export_recommendation_requires_review_for_warning_and_risky_primer():
    result = build_export_recommendation(
        [{"severity": "warning", "code": PRIMER_REVIEW_CODE}],
        [{"Fragment Name": "FragRisk", "Quality Grade": "Usable with Risk"}],
        "ATGGCCTAA",
    )

    assert result["recommendation"] == "Export with Review Required"
    assert result["primer_review_count"] == 1
    assert result["affected_fragments"] == ["FragRisk"]


def test_export_recommendation_blocks_high_risk_primer():
    result = build_export_recommendation(
        [{"severity": "warning", "code": PRIMER_HIGH_RISK_CODE}],
        [{"Fragment Name": "FragHigh", "Quality Grade": "Not Recommended"}],
        "ATGGCCTAA",
    )

    assert result["recommendation"] == "Review blocked by unresolved risk signals"
    assert result["primer_high_risk_count"] == 1
    assert result["affected_fragments"] == ["FragHigh"]


def test_export_recommendation_marks_ready_when_validation_passes():
    result = build_export_recommendation(
        [{"severity": "info", "code": "PASS"}],
        [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}],
        "ATGGCCTAA",
    )

    assert result["recommendation"] == "Documentation Export Available"
    assert result["tone"] == "ready"
    assert "construct/cassette map preview PNG" in result["action"]
    assert "plasmid map" not in result["action"].lower()
