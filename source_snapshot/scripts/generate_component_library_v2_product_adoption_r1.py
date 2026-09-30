from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.component_library_v2_adoption import (
    V2_BLOCKED_IDS,
    build_v2_canonical_inventory,
    v2_adoption_summary,
)
from services.plant_component_workflow_registry import catalog_library_view_records


QA_PATH = ROOT / "docs" / "qa" / "V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_20260927.md"
MAPPING_PATH = ROOT / "docs" / "qa" / "V1_COMPONENT_LIBRARY_V2_PRODUCT_ADOPTION_R1_MAPPING_20260927.json"
VERDICT = "PARTIALLY_SAFE_WITH_EXPLICIT_EXCLUSIONS"
FORMALLY_ADMITTED_V2_IDS = ("V2-CMP-138", "V2-CMP-144")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": _text(row.get("canonical_v2_component_id")),
        "component_name": _text(row.get("name")),
        "component_type": _text(row.get("component_type")),
        "library_tier": _text(row.get("library_tier")),
        "admission_mode": _text(row.get("admission_mode")),
        "accession": _text(row.get("accession")),
        "source_coordinates": row.get("source_coordinates")
        or row.get("recorded_boundary_context")
        or "",
        "sequence_available": bool(_text(row.get("sequence"))),
        "sequence_length": int(row.get("length") or 0),
        "current_product_identity": _text(row.get("current_product_identity")),
        "current_product_state": _text(row.get("current_product_state")),
        "current_selector_visibility": bool(row.get("current_selector_visibility")),
        "current_agent_visibility": bool(row.get("current_agent_visibility")),
        "required_target_state": _text(row.get("required_target_state")),
        "evidence_preventing_adoption": list(row.get("adoption_blockers") or []),
        "legacy_component_ids": list(row.get("legacy_component_ids") or []),
    }


def main() -> None:
    rows = build_v2_canonical_inventory()
    counts = v2_adoption_summary(rows)
    mapping = [_mapping_row(row) for row in rows]
    formal_ids = tuple(
        row["canonical_id"] for row in mapping if row["current_selector_visibility"]
    )
    if formal_ids != FORMALLY_ADMITTED_V2_IDS:
        raise RuntimeError(f"Unexpected current Formal V2 identities: {formal_ids}")
    if len({row["canonical_id"] for row in mapping}) != 171:
        raise RuntimeError("V2 canonical IDs are not unique.")
    if not V2_BLOCKED_IDS.issubset(
        {
            row["canonical_id"]
            for row in mapping
            if row["library_tier"] == "REFERENCE"
        }
    ):
        raise RuntimeError("Blocked V2 identities left the Reference tier.")

    payload = {
        "task_id": "COMPONENT-LIBRARY-V2-PRODUCT-ADOPTION-R1",
        "generated_on": "2026-09-27",
        "verdict": VERDICT,
        "current_product_baseline": {
            "authoritative_registry_raw": 34,
            "authoritative_registry_view": 34,
            "reviewed_catalog_candidates": 122,
            "component_library_ui_total_before": len(catalog_library_view_records()),
            "formal_selectable_before": 2,
            "formal_selectable_after": len(formal_ids),
            "component_library_ui_total_after": len(mapping),
        },
        "v2_canonical_counts": counts,
        "current_formally_admitted_v2_ids": list(formal_ids),
        "blocked_reference_ids": sorted(V2_BLOCKED_IDS),
        "records": mapping,
    }
    MAPPING_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    direct_excluded = [
        row["canonical_id"]
        for row in mapping
        if row["admission_mode"] == "DIRECT_USE"
        and not row["current_selector_visibility"]
    ]
    assisted_ids = [
        row["canonical_id"]
        for row in mapping
        if row["admission_mode"] == "USER_SEQUENCE_ASSISTED"
    ]
    mapping_rel = MAPPING_PATH.relative_to(ROOT).as_posix()
    markdown = f"""# Component Library V2 Product Adoption R1

Date: 2026-09-27
Verdict: **{VERDICT}**

## CURRENT_PRODUCT_BASELINE

- Registry raw/view: 34 / 34.
- Reviewed Catalog candidates: 122.
- Component Library UI before/after: 156 / 171 canonical identities.
- Formal-selectable before/after: 2 / 2; this batch does not broaden Formal admission.

## V2_CANONICAL_COUNTS

- Canonical total: 171.
- CORE: 41 = DIRECT_USE 17 + USER_SEQUENCE_ASSISTED 24.
- REFERENCE: 95.
- RETIRED: 35.

## IDENTITY_MAPPING_SUMMARY

- Exact identity-level mapping: {mapping_rel}.
- Current admitted mappings: V2-CMP-138 -> PCLV1-PRO-E8-2164; V2-CMP-144 -> PCLV1-TER-HSP18-2-250.
- Duplicate canonical IDs: none. Blocked IDs V2-CMP-003 and V2-CMP-126 remain Reference-only.

## DIRECT_USE_ADOPTION_GAPS

- The 17 records have reviewed V2 sequence assets, but V2 qualification is not current Formal host/role admission.
- Current admitted: {', '.join(FORMALLY_ADMITTED_V2_IDS)}.
- Explicitly excluded pending current Registry/host/role evidence ({len(direct_excluded)}): {', '.join(direct_excluded)}.

## USER_SEQUENCE_ASSISTED_ROUTING_GAPS

- All 24 identities are visible but carry no bundled authoritative sequence.
- The route requires an active persisted project, strict DNA validation, source/file labeling, identity-and-boundary confirmation, explicit use confirmation, and a checksummed project-scoped resolution.
- IDs ({len(assisted_ids)}): {', '.join(assisted_ids)}.

## REFERENCE_AGENT_ROUTING_GAPS

- All 95 records remain non-formal and non-sequence-authoritative.
- They remain visible for reference/Agent discovery only and cannot create a formal selection or generic user-sequence shortcut.

## RETIRED_EXCLUSION_CHECK

- All 35 records remain excluded from new designs; historical identity mappings remain readable.

## CONFLICTS / BLOCKERS

- Fifteen DIRECT_USE assets lack current Registry identity plus reviewed host/role admission.
- V2 source-organism context is not treated as host applicability.
- No accession, boundary, rights, performance, or experimental conclusion is fabricated.

## IMPLEMENTATION_AND_TEST_EVIDENCE

- The generated mapping contains 171 unique canonical IDs; its Formal-admitted set is exactly V2-CMP-138 and V2-CMP-144.
- V2-CMP-003 and V2-CMP-126 remain `REFERENCE` / `REFERENCE_ONLY`.
- New focused adoption module: 7 passed.
- Combined Registry, Agent, Formal, and UI focused suite: 195 passed.
- Targeted compatibility, scope-guard, and failure-fix suite: 24 passed.
- Final page/UI correction suite: 8 passed.
- Final full unfiltered regression: 6124 passed, 36 skipped, 67 warnings in 681.80s (0:11:21), using `E:\\UBD-test-envs\\left-nav-ia-v1-py312\\Scripts\\python.exe` and external basetemp `E:\\UBD-pytest-temp\\component-library-v2-r1-full-final`.
- Changed Python files passed `py_compile`; the user-visible copy denylist scan passed.

## STARTUP_AND_BROWSER_ACCEPTANCE

- Formal port 8528 was already occupied by PID 42896, a system-Python Streamlit process serving a different worktree.
- Headless inspection showed that listener still exposes the previous 156-row V1 Component Library (`Showing 1–20 of 156 items`) and does not expose the Canonical V2 UI.
- The occupied listener returned healthy HTTP status and zero browser console errors, but it is not this candidate and therefore is not valid browser acceptance evidence.
- The unrelated process was not stopped or modified, and no second Formal port was created. Current-candidate cold-start and real-browser acceptance on port 8528 remain blocked until the owner frees the Formal port or runs the candidate in the authorized environment.
- The Codex computer-use browser could not be used as a fallback because its session rejected the configured API-key authentication method.

## DELIVERY_STATE

- Candidate base: `0a608bd76f6341c42c58bd3fc4cb8be61d1eb34c`.
- Candidate branch: `fix/v1-component-library-v2-product-adoption-r1-20260927`.
- All candidate changes remain unstaged and uncommitted for independent review; no commit, tag, push, merge, reset, stash, clean, or Formal-worktree mutation was performed.

## EXACT_MINIMAL_IMPLEMENTATION_PLAN

1. Replace the 156-row browse projection with the exact 171-row canonical projection.
2. Preserve the two existing Registry routes and fail closed for the other fifteen DIRECT_USE assets.
3. Add project-scoped USER_PROVIDED resolution for the 24 assisted identities.
4. Keep Reference and Retired records non-selectable.
5. Verify selection checksum, save/cold reopen, and FASTA/GenBank qualifier consistency.
"""
    QA_PATH.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
