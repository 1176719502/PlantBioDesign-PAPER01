from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "qa" / "UBD_PLANT_PROMOTER_3PRIME_AUTHORITY_CLOSURE_R1.md"
REGISTRY = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
V2 = (
    ROOT
    / "data"
    / "component_library_v2_qualified_core_r2"
    / "V2_QUALIFIED_CORE_R2_CANONICAL_SET.json"
)
CATALOG = (
    ROOT
    / "data"
    / "plant_component_registry_v1"
    / "intake_20260827"
    / "candidate_inventory.csv"
)
SEEDS = ROOT / "data" / "plant_promoter_catalog_seed.json"

HOSTS = (
    "Oryza sativa",
    "Arabidopsis thaliana",
    "Nicotiana benthamiana",
    "Zea mays",
    "Solanum lycopersicum",
    "Glycine max",
)
DIRECT_IDS = {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
ASSISTED_IDS = {"PCLV1-PRO-UBQ10"}
V2_FORMAL_BRIDGES = {
    "V2-CMP-138": "PCLV1-PRO-E8-2164",
    "V2-CMP-144": "PCLV1-TER-HSP18-2-250",
}
CATALOG_ASSISTED = {
    "INTAKE-ACTIN-FAMILY-5D605D80266B": "V2-CMP-004",
    "INTAKE-ACTIN-FAMILY-B81D7A810410": "V2-CMP-006",
    "INTAKE-RBCS-FAMILY-B71C26CFADA5": "V2-CMP-099",
}


def cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", "/").replace("\n", " ").strip()


def table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    result = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    result.extend("| " + " | ".join(cell(item) for item in row) + " |" for row in rows)
    return "\n".join(result)


def registry_rows() -> list[tuple[Any, ...]]:
    records = json.loads(REGISTRY.read_text(encoding="utf-8"))["records"]
    rows = []
    for record in records:
        if record["component_type"] not in {
            "promoter",
            "terminator",
            "three_prime_regulatory_region",
        }:
            continue
        component_id = record["component_id"]
        boundary = record["feature_boundary_method"]
        coordinates = (
            f"{boundary['start_one_based']}..{boundary['end_one_based_inclusive']} "
            f"({boundary['strand']})"
        )
        if component_id == "PCLV1-PRO-E8-2164":
            history = "fa5c7943 V1 DIRECT_USE"
            blocker = "none"
            classification = "DIRECT_USE_READY"
        elif component_id == "PCLV1-TER-HSP18-2-250":
            history = "fa5c7943 DIRECT_USE; eff14afd Tomato exact-sequence host scope"
            blocker = "none"
            classification = "DIRECT_USE_READY"
        elif component_id in ASSISTED_IDS:
            history = "V1 usability; V2-CMP-143 assisted"
            blocker = "bundled sequence not admitted; exact user sequence and confirmation required"
            classification = "USER_SEQUENCE_ASSISTED"
        else:
            history = "V1 usability: REFERENCE_ONLY"
            blocker = "rights/governance, reviewed host applicability, and admission"
            classification = "REFERENCE_ONLY"
        reviewed = (record.get("host_applicability") or {}).get("scope") or []
        rights = record.get("rights_classification") or record["redistribution_status"]
        admission = record.get("workflow_admission_status") or "not admitted"
        rows.append(
            (
                component_id,
                record["component_type"],
                record["display_name"],
                f"yes; {record['sequence_length']}; {record['sequence_sha256']}",
                f"{record['accession_version']}; {coordinates}",
                f"{record['evidence_level']}; {record['primary_reference']}; {record['review_status']}",
                f"{rights}; {admission}",
                f"recorded={cell(record['target_host_species'])}; reviewed={cell(reviewed) or 'none'}",
                f"{record['limitations']} Historical: {history}",
                blocker,
                classification,
            )
        )
    return rows


def v2_rows() -> list[tuple[Any, ...]]:
    records = json.loads(V2.read_text(encoding="utf-8"))["records"]
    rows = []
    for record in records:
        if record["role"] not in {"promoter", "terminator_3prime_regulatory_region"}:
            continue
        component_id = record["canonical_v2_component_id"]
        asset = record.get("sequence_asset_reference") or {}
        sequence = (
            f"yes; {asset.get('length')}; {asset.get('sequence_sha256')}"
            if asset
            else "no bundled authoritative sequence in assisted package"
        )
        boundary = asset.get("exact_boundary") or "user sequence and boundary required"
        if component_id in V2_FORMAL_BRIDGES:
            reviewed = (
                "Solanum lycopersicum"
                if component_id == "V2-CMP-138"
                else "Arabidopsis thaliana, Solanum lycopersicum"
            )
            blocker = "none through exact Registry V1 bridge"
            classification = "DIRECT_USE_READY"
            history = f"exact bridge to {V2_FORMAL_BRIDGES[component_id]}"
        elif record["admission_mode"] == "USER_SEQUENCE_ASSISTED":
            reviewed = "none"
            blocker = "user exact sequence, confirmation, current Formal admission, reviewed host applicability"
            classification = "USER_SEQUENCE_ASSISTED"
            history = "V2 assisted review confirmed"
        else:
            reviewed = "none"
            blocker = "reviewed component-use host applicability and Formal Registry adoption"
            classification = "NEEDS_HOST_APPLICABILITY_EVIDENCE"
            history = "e3f4e4a3 content reconciliation preserves V2 status only"
        rows.append(
            (
                component_id,
                record["role"],
                record["canonical_name"],
                sequence,
                f"{record.get('accession_or_source_record') or record.get('source_record')}; {boundary}",
                f"{record.get('evidence_maturity')}; {record.get('primary_citation')}; {record.get('independent_review_status')}",
                f"{record['library_tier']}; {record['admission_mode']}",
                f"source={record.get('source_organism')}; reviewed={reviewed}",
                f"{record.get('evidence_caveat') or 'Assisted identity only.'} Historical: {history}",
                blocker,
                classification,
            )
        )
    return rows


def catalog_rows() -> list[tuple[Any, ...]]:
    v2_records = json.loads(V2.read_text(encoding="utf-8"))["records"]
    lifecycle_by_legacy = {
        legacy: record["admission_mode"]
        for record in v2_records
        for legacy in record.get("legacy_component_ids", [])
    }
    rows = []
    with CATALOG.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            if record["component_type"] not in {
                "promoter",
                "terminator",
                "three_prime_regulatory_region",
            }:
                continue
            component_id = record["candidate_id"]
            if lifecycle_by_legacy.get(component_id) == "USER_SEQUENCE_ASSISTED":
                blocker = "user exact sequence/confirmation plus Formal host and admission authority"
                classification = "USER_SEQUENCE_ASSISTED"
                history = f"mapped to {CATALOG_ASSISTED[component_id]}"
            else:
                blocker = "record-specific redistribution/governance, reviewed host applicability, Registry admission"
                classification = "NEEDS_RIGHTS_GOVERNANCE"
                history = "reviewed Catalog candidate only"
            rows.append(
                (
                    component_id,
                    record["component_type"],
                    record["display_name"],
                    f"yes; {record['length']}; {record['sha256']}",
                    f"{record['accession_record_identifier']}; {record['source_coordinates_or_feature_identity']}",
                    f"{record['evidence_tier_proposal']}; {record['evidence_publication_reference']}; exact intake bytes",
                    f"Catalog candidate; {record['license_redistribution_note']}; not admitted",
                    f"context={record['host_context']}; reviewed=none",
                    f"{record['confidence_issues']}; {record['duplicate_equivalence_notes']}; Historical: {history}",
                    blocker,
                    classification,
                )
            )
    return rows


def seed_rows() -> list[tuple[Any, ...]]:
    records = json.loads(SEEDS.read_text(encoding="utf-8"))["records"]
    return [
        (
            record["promoter_id"],
            "promoter",
            record["promoter_name"],
            "no; metadata-only",
            "no accession/boundary authority",
            f"source review needed; {cell(record['source_labels'])}; not exact",
            "reference seed; no sequence rights decision; not admitted",
            f"source context={record['species']['scientific_name']}; reviewed=none",
            f"{cell(record['limitation_notes'])}; historical seed metadata only",
            "exact identity, sequence provenance, rights, host applicability, governance, admission",
            "NEEDS_NEW_CURATION",
        )
        for record in records
    ]


def historical_rows() -> list[tuple[Any, ...]]:
    # These are reviewed audit-only objects not represented by current Registry,
    # V2, Catalog intake, or promoter seed IDs.
    items = (
        ("VLAD-EC15030", "promoter", "Vlad 2019 p35S(short)", "425; eeca8f64206dbdd7d874bd1ff63b6051a0087097826939f2817e62773d570909", "external supplementary GenBank:1506..1930 (-)", "Rice exact-variant use", "donor-specific redistribution clearance and admission", "NEEDS_RIGHTS_GOVERNANCE"),
        ("VLAD-EC41421", "terminator", "Vlad 2019 tNOS", "263; e195e224e4b00353173edde4d0255f5d4ea5a67710a32c4a4fd24d905bbff9b3", "external supplementary GenBank; 12 identical features", "Rice exact-variant use", "donor-specific redistribution clearance and admission", "NEEDS_RIGHTS_GOVERNANCE"),
        ("TOMATO-SCR-01", "3_prime_regulatory_region", "Sl ATPase module", "not acquired", "Addgene 50344", "Tomato donor identity only", "sequence, boundary, rights, host governance", "NEEDS_NEW_CURATION"),
        ("TOMATO-SCR-02", "3_prime_regulatory_region", "Sl RbcS3C module", "not acquired", "Addgene 50345", "Tomato donor identity only", "sequence, boundary, rights, host governance", "NEEDS_NEW_CURATION"),
        ("TOMATO-SCR-03", "terminator", "HSP18.2 name-level route", "250; f64cc0a9ffd000d281dc8d75163b072d42ec8184ad216470461941a4e61dfd1d", "PP558908.1:852..1101 (+)", "superseded by eff14afd exact bridge", "none through PCLV1-TER-HSP18-2-250", "DIRECT_USE_READY"),
        ("TOMATO-SCR-04", "terminator", "pea3At module", "not acquired", "Addgene 210536", "Tomato use; identity conflict retained", "sequence, rights, exact identity", "REJECT"),
        ("TOMATO-SCR-05", "3_prime_regulatory_region", "Populus psbC plastid 3-prime UTR", "178; b788a46c3febabf56a73887823f2ca574a5ba24854e63aa960566eb4126a9a75", "NC_008235.1 complement(34875..35052)", "Tomato plastid context only", "wrong architecture for nuclear route; rights", "REJECT"),
        ("TOMATO-SCR-06", "terminator", "Populus rbcL plastid terminator", "233; 6c89eb16786fecb4649a8029ecf4c46efbde10763454f3f552ad95140f4f65fc", "NC_008235.1:56790..57022 (+)", "Tomato plastid context only", "wrong architecture for nuclear route; rights", "REJECT"),
        ("RICE-SCR-01", "3_prime_regulatory_region", "SBG51 AT-rich downstream element", "not closed", "article/supplement candidate", "no Rice evidence", "exact sequence, Rice evidence, rights", "REJECT"),
        ("RICE-SCR-02", "3_prime_regulatory_region", "Rice Act1 genomic 3-prime flank", "source record only", "X15865.1; boundary absent", "Rice source identity only", "component boundary, role, rights", "NEEDS_NEW_CURATION"),
        ("RICE-SCR-03", "3_prime_regulatory_region", "alphaAmy3-associated object", "not recovered", "article case", "Rice context only", "standalone sequence, boundary, role, rights", "NEEDS_NEW_CURATION"),
        ("RICE-SCR-04", "3_prime_regulatory_region", "alphaAmy3/alphaAmy8 donor context", "not recovered", "article case", "Rice context only", "standalone sequence, boundary, role, rights", "NEEDS_NEW_CURATION"),
        ("RICE-SCR-05", "3_prime_regulatory_region", "VRT-A2 native 3-prime UTR", "not acquired", "Addgene 163703", "wheat context", "wrong host, boundary, export rights", "REJECT"),
        ("RICE-SCR-06", "3_prime_regulatory_region", "generic plant 3-prime review sources", "none", "review only", "no exact object", "identity, sequence, boundary, donor rights", "REJECT"),
    )
    return [
        (
            item[0], item[1], item[2], item[3], item[4],
            f"historical reviewed audit; {item[5]}",
            "audit-only; not admitted",
            f"reviewed context={item[5]}; Formal scope=none unless bridged",
            "Historical audits 883429d7, 32e193d6, aea5fc6d as applicable",
            item[6], item[7],
        )
        for item in items
    ]


def main() -> None:
    headers = (
        "Component ID / source",
        "Role",
        "Name",
        "Sequence / length / SHA-256",
        "Accession / coordinates",
        "Evidence / exactness",
        "Current tier / rights / admission",
        "Host metadata / reviewed applicability",
        "Limitations / historical authority",
        "Current blocker",
        "Proposed classification",
    )
    registry = registry_rows()
    v2 = v2_rows()
    catalog = catalog_rows()
    seeds = seed_rows()
    historical = historical_rows()
    all_rows = registry + v2 + catalog + seeds + historical
    promoter_count = sum(row[1] == "promoter" for row in all_rows)
    three_prime_count = len(all_rows) - promoter_count

    coverage_rows = [
        ("Oryza sativa", 0, 0, 0, "NO_FORMAL_PAIR", "Act2 remains assisted; exact Rice candidates retain rights/admission gaps"),
        ("Arabidopsis thaliana", 0, 1, 0, "3PRIME_ONLY", "HSP18.2 only; V2 promoters lack Formal reviewed host applicability"),
        ("Nicotiana benthamiana", 0, 0, 0, "NO_FORMAL_PAIR", "rbcS remains assisted; generic plant context is not host authority"),
        ("Zea mays", 0, 0, 0, "NO_FORMAL_PAIR", "ZmUbi1 is reference-only with context and governance gaps"),
        ("Solanum lycopersicum", 1, 1, 1, "FULL_MINIMAL_DESIGN_COVERAGE", "E8 promoter plus exact HSP18.2 250 bp identity"),
        ("Glycine max", 0, 0, 0, "NO_FORMAL_PAIR", "catalog source context only; no reviewed Formal pair"),
    ]
    agent_rows = [
        (
            host,
            "YES" if host == "Solanum lycopersicum" else "NO",
            "PCLV1-PRO-E8-2164" if host == "Solanum lycopersicum" else "none",
            "PCLV1-TER-HSP18-2-250" if host == "Solanum lycopersicum" else "none",
            1 if host == "Solanum lycopersicum" else 0,
        )
        for host in HOSTS
    ]

    document = f"""# UBD Plant Promoter and 3-Prime Regulatory Authority Closure R1

## Sync

- Base/HEAD at task start: `bf198f3e1de602e6898d571a260dc5c0e61500e9`.
- Branch: `mvp/gate2-dual-tu-formal-workflow`.
- Pre-governance-correction candidate state: dirty (`16 modified`, `3 untracked`, nothing staged); this was the existing 19-file Biological Authority candidate.
- Final governance-corrected candidate state: dirty (`16 modified`, `7 untracked`, nothing staged); this is the 23-path candidate returned for final condition closure.
- Historical commits are evidence inputs, not ancestors of HEAD; no branch was cherry-picked.
- The final candidate remains unstaged and uncommitted. The worktree was not clean, and Qwen was not called.

## Total Records Reviewed

- Promoter source records: **{promoter_count}**.
- 3-prime/terminator source records: **{three_prime_count}**.
- Total source records: **{len(all_rows)}**.
- Current Registry identities: 16; V2 canonical records: 13; reviewed Catalog candidates: 45; metadata promoter seeds: 8; historical-only audit objects: 14.
- Counts are source-record counts, not claims of independent biological diversity. V1/V2/Catalog duplicates are retained explicitly in the matrix.

## Host Coverage Before

At the requested base, all six hosts had zero admitted promoter plus 3-prime pairs. The two historically reviewed V1 direct-use records were not present in this HEAD, and their different original host scopes did not form a pair.

## Contract And Decision Rule

Formal direct use requires exact sequence identity, length and SHA-256; role and workflow compatibility; `bundled/local_verified/eligible`; durably resolvable versioned governance with sealed file digests and component-identity binding; reviewed non-empty species scope with evidence and limitation; current rights eligibility; admission; selection-time snapshot binding; and cold-reopen revalidation. Source-organism identity, aliases, generic plant use, Catalog host context, or a V2 qualification label alone never grant host authority.

`DIRECT_USE_READY` here means software authority for the exact reviewed component and host scope. It does not assert experimental validation, expression magnitude, host portability beyond scope, downstream biological suitability, or freedom to operate.

## Host-By-Host Result

{table(('Host', 'Promoter admitted', '3-prime admitted', 'Valid pairs', 'Coverage', 'Remaining gaps'), coverage_rows)}

## Master Evidence Matrix

The following compact columns cover the requested identity, provenance, exactness, tier, rights, admission, host, limitation, historical-authority, blocker and classification fields.

### Registry V1 (16)

{table(headers, registry)}

### Component Library V2 (13)

V2 `DIRECT_USE` is a qualified content-package lifecycle, not Formal Registry admission. Only the two exact V1 bridges below receive current Formal authority.

{table(headers, v2)}

### Reviewed Catalog Candidates (45)

All rows carry exact intake sequence bytes, but their shared rights note requires redistribution review and none has reviewed Formal host applicability or Registry admission. Three rows retain V2 user-sequence-assisted handling.

{table(headers, catalog)}

### Historical Promoter Seeds (8)

{table(headers, seeds)}

### Historical-Only Reviewed Objects (14)

{table(headers, historical)}

## Historical Authority Reconciliation

- `fa5c7943`: E8 and HSP18.2 identity, rights, governance, attribution and initial host facts remain valid. Ported record-by-record.
- `eff14afd`: the exact HSP18.2 250 bp source-object bridge to Tomato remains valid. Ported as a bounded Tomato host-scope extension.
- `e3f4e4a3`: V2 content reconciliation remains valid for V2 lifecycle and identity, but grants no Formal host applicability or Product admission.
- `37ce090b` and `bdd33dca`: selection-marker role authority work is outside promoter/3-prime roles; no facts were ported.
- `9e7c98ad`: E8 140 bp 3-prime record remains reference-only because the complete role-compatible boundary, rights and host governance are not closed.
- `1b4eaf4d`, `dccaad57`, `6a73320b`, `dfe57587`, `dd07870f`, `32e193d6`, and the Vlad 2019 evidence package do not authorize Rice promotion. Exact objects remain blocked by rights, boundary or admission gaps.
- `883429d7`: HSP18.2 was the only viable existing Tomato route; its later exact bridge at `eff14afd` supersedes the earlier name-level gap.

## Records Promoted To DIRECT_USE

1. `PCLV1-PRO-E8-2164`: promoter; exact `KJ561284.1:1..2164 (+)`; Tomato only.
2. `PCLV1-TER-HSP18-2-250`: terminator-compatible 3-prime slot record; exact `PP558908.1:852..1101 (+)`; Arabidopsis and Tomato only.

The patch does not add a new production identity. V2 E8/HSP18.2 rows and historical HSP18.2 SCR-03 are duplicate authority views of these Registry identities.

## Records Kept Assisted

`PCLV1-PRO-UBQ10`; V2 `V2-CMP-004`, `V2-CMP-006`, `V2-CMP-099`, `V2-CMP-143`; and their three mapped Catalog intake rows remain user-sequence-assisted. This does not grant bundled-sequence or Formal selection authority.

## Records Kept Reference-Only Or Requiring Curation

All non-promoted Registry records remain reference-only. Non-bridged V2 direct-content records require reviewed host applicability and controlled Registry adoption. Unmapped reviewed Catalog rows require rights/governance and host review. Metadata seeds and incomplete historical objects require new curation; architecture-incompatible or identity-conflicted historical objects are rejected.

## Registry / Host Gate

The Registry service now validates the full direct-use contract before `formal_selectable=True`, freezes attribution into the component snapshot, requires exact requested-host membership, and rechecks the current record plus sealed governance evidence on reopen. Empty, missing, malformed, altered, ungoverned, wrong-identity, stale, or digest-mismatched evidence locators fail closed. Wrong host, wrong role, wrong sequence hash, assisted/reference-only, malformed attribution, non-admitted, and host-scope mismatch also remain fail-closed.

## Durable Governance Evidence

The current tree contains the exact sealed B2B rights decision, B2B attribution contract, B2C product-admission dossier, and HSP18.2 Tomato host-scope dossier used by the two direct-use decisions. Their repository-relative locators and SHA-256 digests are fixed in the admission policy. The B2B/B2C records are bound to component ID, accession/version, source coordinates, strand, source-record hash, feature hash, rights classification, admission verdict, and attribution identities. The HSP18.2 extension is additionally bound to its exact two-host scope and retains the explicit no-FTO caveat.

- `COMPONENT_LIBRARY_V1_B2B_RIGHTS_GOVERNANCE.json`: `823f2171ef2da03815a4a00d2b1ee3e7923b2c5701c607748fbce7d8268b656e`.
- `COMPONENT_LIBRARY_V1_B2B_ATTRIBUTION_CONTRACT.md`: `3367dc5113deb69a8b9582b7b47548abb8914ab29b64567c0c01a8fa98593fa7`.
- `COMPONENT_LIBRARY_V1_B2C_PRODUCT_ADMISSION.json`: `b1aa980b0aaadfd368db306668b367ac44c325ce70ebf834d38dd887c319e6a9`.
- `V1_TOMATO_HSP18_2_HOST_SCOPE_EXTENSION_R1_20260909.json`: `3822e8aaa84f6951c865439350fab830868d341b8f6f8ec2cf8173223b76acfa`.

## Agent Eligibility Coverage

{table(('Host', 'Can reach provider gate', 'Promoter options', '3-prime options', 'Valid combinations'), agent_rows)}

No provider call was made. A `YES` means only that the deterministic Formal prerequisite gate has one admitted option for each required role.

## Canonical / Export

The representative Tomato pair builds through the existing canonical runtime. Save and cold reopen retain both exact component snapshots. FASTA and GenBank parse back to the same canonical DNA, and GenBank features retain component ID, accession/version, source coordinates, feature/source hashes, contract version and citations. No canonical construction algorithm or export/package schema changed.

## Test Results

- The following condition-closure tests were run for this candidate: evidence-byte mutation, stale expected digest, Windows drive-qualified locator, Windows backslash locator, Windows-separator traversal, wrong sealed-document identity on fresh-process reopen, and the existing authority/persistence tests.
- The prior governance review results (`341 passed`, `95 passed, 27 skipped, 4 warnings`, and `5 passed`) are historical review evidence, not newly run results for this correction.
- The prior full-regression result (`6050 passed, 36 skipped, 67 warnings`) is historical review evidence and was not rerun for this P2-only correction.
- Changed-file compilation: run for this correction.
- Registry validator and `git diff --check`: run for this correction.
- Browser click-through acceptance was not run and remains a separate Product UI evidence gap; HTTP health is not browser acceptance.

## Condition Closure

- QA generator and checked report are generated from the same deterministic source; repeated generation is byte-identical.
- Pre-correction candidate state is preserved as `16 modified / 3 untracked`.
- Final governance-corrected candidate state is recorded as `16 modified / 7 untracked`.
- No staging, commit, browser acceptance, or unrun regression result is claimed.

## Changed Files

The candidate contains the original 19 authority files plus four exact sealed governance evidence files. No file was staged or committed.

## Commit

No commit was created. The user did not authorize staging or committing.

## Final Verdict

`PLANT_PROMOTER_3PRIME_AUTHORITY_CLOSURE_R1_CONDITIONS_READY_FOR_FINAL_CHECK`

The remaining condition closure is complete without changing the reviewed biological conclusions. The candidate still provides one Formal pair for Tomato and a 3-prime-only option for Arabidopsis; four supported hosts still have no Formal pair.

## Next Action

Recommend one final read-only condition verification only. Do not recommend Qwen Product E2E until the candidate is committed and formally adopted.
"""
    OUTPUT.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
