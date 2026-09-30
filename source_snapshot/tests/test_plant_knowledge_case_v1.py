from __future__ import annotations

import json

from scripts.validate_plant_knowledge_case_v1 import CASE_PATH, validate


def test_reporter_case_manifest_validates() -> None:
    assert validate() == []


def test_case_has_exact_traceable_component_chain_without_sequence_copy() -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    assert [(row["slot"], row["registry_component_id"], row["knowledge_layer_evidence_object_id"]) for row in payload["selected_components"]] == [
        ("promoter", "PCLV1-PRO-35S-835", "PKL1-EV-PRO-35S-835"),
        ("reporter_cds", "PCLV1-CDS-GUSA", "PKL1-EV-CDS-GUSA"),
        ("vector_source", "PCLV1-VEC-PBIN19", "PKL1-EV-VEC-PBIN19"),
    ]
    assert not any(key == "sequence" for key in payload)
    assert '"sequence":' not in json.dumps(payload, sort_keys=True)
    assert all(len(row["evidence_claim_ids"]) == 3 for row in payload["selected_components"])
    assert all(
        row["engineering_context_reference"] == "knowledge_layer.engineering_context_notes"
        for row in payload["selected_components"]
    )


def test_case_is_explicitly_documentation_only_and_records_limitations() -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    assert payload["scope"] == "documentation_only_read_only_case"
    assert len(payload["known_limitations"]) >= 4
    assert "T-DNA" in " ".join(payload["known_limitations"])
    assert "experimental validation" in payload["blocked_claims"]
