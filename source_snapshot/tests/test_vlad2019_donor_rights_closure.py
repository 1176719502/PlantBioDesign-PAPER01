import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "audit_reports" / "vlad2019_donor_rights_closure"


def test_governance_record_is_pinned_and_fail_closed():
    record = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    assert record["task"]["formal_base"] == "62838ca2d69515530b911ed61b0b00d104a410ce"
    assert record["task"]["mutation_executed"] is False
    assert record["task"]["admission_executed"] is False
    assert record["candidates"]["EC15030"]["source_sequence_comparison"]["result"] == "MISMATCH"
    assert record["candidates"]["EC15030"]["formal_admit_rights_gate"] == "OPEN"
    assert record["candidates"]["EC41421"]["source_sequence_comparison"]["result"] == "NOT_PROVEN"
    assert record["candidates"]["EC41421"]["formal_admit_rights_gate"] == "OPEN"
    assert record["final_verdict"] == "VLAD2019_DONOR_RIGHTS_REMAIN"


def test_governance_artifacts_do_not_embed_reconstructable_formal_sequences():
    dna_run = __import__("re").compile(r"[ACGT]{80,}", __import__("re").IGNORECASE)
    record = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))

    def has_sequence_key(value):
        if isinstance(value, dict):
            return any(key.lower() == "sequence" or has_sequence_key(item) for key, item in value.items())
        if isinstance(value, list):
            return any(has_sequence_key(item) for item in value)
        return False

    assert not has_sequence_key(record)
    for path in (PACKAGE / "REVIEW_PACKAGE.md", PACKAGE / "GOVERNANCE_RECORD.json"):
        assert dna_run.search(path.read_text(encoding="utf-8")) is None
