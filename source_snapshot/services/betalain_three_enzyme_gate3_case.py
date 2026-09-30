"""Official-record Gate 3 case for three betalain-pathway enzyme CDSs.

This module keeps source-record validation separate from canonical construct
generation.  The bundled case intentionally stops after CDS-to-TU mapping
when real-source regulatory elements and a binary backbone are unavailable.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq

from services.gate3_pathway_mapping import (
    SCENARIO_PATHWAY_MULTI_TU,
    analyze_pathway_cds,
    new_pathway_step,
    normalize_pathway_steps,
    validate_pathway_mapping,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository, require_active_project
from services.plant_project_draft_schema import PlantDesignProjectDraft


CASE_ID = "betalain_three_enzyme_official_public_cds"
PROJECT_NAME = "甜菜红素三酶真实来源计算设计验收"
CASE_ROOT = Path(__file__).resolve().parents[1] / "data" / "real_cases" / "betalain_three_enzyme"
SOURCE_RECORDS_DIR = CASE_ROOT / "source_records"
EXTRACTED_CDS_DIR = CASE_ROOT / "extracted_cds"
PROVENANCE_DIR = CASE_ROOT / "provenance"
MANIFEST_PATH = PROVENANCE_DIR / "source_manifest.json"
SAVED_STATE_KEY = "betalain_three_enzyme_gate3_case"
FETCHED_FROM = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
FETCHED_DATE = "2026-07-17"

BOUNDARY_NOTE = (
    "This case uses public CDS records and public functional evidence. The vector context is a "
    "software design record, not the original paper vector and not a claim of experimental expression."
)
NONENZYMATIC_REVIEW_NOTE = (
    "The subsequent condensation of betalamic acid and cyclo-DOPA 5-O-glucoside to betanin is "
    "non-enzymatic in this case record; no fourth transcription unit is created."
)

_EXPECTED: dict[str, dict[str, str]] = {
    "HQ656023.1": {
        "file": "HQ656023.1.gb",
        "fasta": "HQ656023.1_CYP76AD1_cds.fasta",
        "organism": "Beta vulgaris",
        "title": "Beta vulgaris cultivar W357B CYP76AD1 mRNA, complete cds",
        "gene": "CYP76AD1",
        "product": "CYP76AD1",
        "coordinates": "259..1752",
        "cds_sha256": "79c7ffaaa7ad20dbfc1903619d14208160be9b0af48851a85b89a19eeb43a27c",
        "record_sha256": "b541b6b132fba98ba7b9ee6ed56f37aafd1565c44e138a87116b7198efe16590",
    },
    "HQ656027.1": {
        "file": "HQ656027.1.gb",
        "fasta": "HQ656027.1_DODA1_cds.fasta",
        "organism": "Beta vulgaris",
        "title": "Beta vulgaris cultivar W357B 4,5-DOPA dioxygenase extradiol (DODA1) mRNA, complete cds",
        "gene": "DODA1",
        "product": "4,5-DOPA dioxygenase extradiol",
        "coordinates": "60..887",
        "cds_sha256": "cbdd9b4070de50ff2a863c361a1e6791adde5707b55abe8227dcb47b607654f7",
        "record_sha256": "7be76a1ec62db527aacd9d3719b57cee46d8eabe84dfc871c579e9f1bb04fecc",
    },
    "AB182643.1": {
        "file": "AB182643.1.gb",
        "fasta": "AB182643.1_cDOPA5GT_cds.fasta",
        "organism": "Mirabilis jalapa",
        "title": "Mirabilis jalapa cDOPA5GT mRNA for cyclo-DOPA 5-O-glucosyltransferase, complete cds",
        "gene": "cDOPA5GT",
        "product": "cyclo-DOPA 5-O-glucosyltransferase",
        "coordinates": "22..1524",
        "cds_sha256": "47cdcd7083868df23861ad31837b674b0a7390ad72e4a7649807715b7f85e522",
        "record_sha256": "00181b8cb48e2f9d19cedd7f3fe9055425f7e930a39ae7e62ee617531014b927",
    },
}

_STEP_DEFINITIONS = (
    ("L-tyrosine to L-DOPA/cyclo-DOPA conversion", "L-tyrosine", "L-DOPA / cyclo-DOPA", "CYP76AD1", "CYP76AD1", "Beta vulgaris", "HQ656023.1"),
    ("L-DOPA to betalamic acid conversion", "L-DOPA", "betalamic acid", "4,5-DOPA dioxygenase extradiol 1", "DODA1", "Beta vulgaris", "HQ656027.1"),
    ("cyclo-DOPA glycosylation", "cyclo-DOPA", "cyclo-DOPA 5-O-glucoside", "cyclo-DOPA 5-O-glucosyltransferase", "cDOPA5GT", "Mirabilis jalapa", "AB182643.1"),
)


class BetalainThreeEnzymeCaseError(ValueError):
    """Raised when an official source asset is absent or does not verify exactly."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_dna(value: str) -> str:
    return hashlib.sha256(value.upper().encode("ascii")).hexdigest()


def _location(feature: Any) -> str:
    start = int(feature.location.start) + 1
    end = int(feature.location.end)
    text = f"{start}..{end}"
    return f"complement({text})" if int(feature.location.strand or 1) == -1 else text


def _one_cds(record: Any, accession: str) -> Any:
    features = [feature for feature in record.features if feature.type == "CDS"]
    if len(features) != 1:
        raise BetalainThreeEnzymeCaseError(f"{accession} must contain exactly one CDS feature; found {len(features)}.")
    return features[0]


def _qualifier(feature: Any, key: str) -> str:
    values = feature.qualifiers.get(key, [])
    return str(values[0]).strip() if values else ""


def _validate_entry(accession: str) -> dict[str, Any]:
    expected = _EXPECTED[accession]
    path = SOURCE_RECORDS_DIR / expected["file"]
    if not path.exists():
        raise BetalainThreeEnzymeCaseError(f"Official source record is missing: {path.name}.")
    if _sha256_bytes(path.read_bytes()) != expected["record_sha256"]:
        raise BetalainThreeEnzymeCaseError(f"Official source-record SHA-256 mismatch: {path.name}.")
    try:
        record = SeqIO.read(path, "genbank")
    except Exception as exc:  # pragma: no cover - defensive error context
        raise BetalainThreeEnzymeCaseError(f"Cannot parse {path.name} as GenBank.") from exc
    if str(record.id) != accession:
        raise BetalainThreeEnzymeCaseError(f"Expected accession {accession}; found {record.id}.")
    if str(record.description).rstrip(".") != expected["title"]:
        raise BetalainThreeEnzymeCaseError(f"Unexpected official record title for {accession}.")
    if str(record.annotations.get("organism") or "") != expected["organism"]:
        raise BetalainThreeEnzymeCaseError(f"Unexpected source organism for {accession}.")
    feature = _one_cds(record, accession)
    sequence = str(feature.extract(record.seq)).upper()
    translation_qualifier = _qualifier(feature, "translation")
    local_translation = str(Seq(sequence).translate())
    gene = _qualifier(feature, "gene") or _qualifier(feature, "product")
    product = _qualifier(feature, "product")
    if _location(feature) != expected["coordinates"]:
        raise BetalainThreeEnzymeCaseError(f"Unexpected CDS coordinates for {accession}.")
    if gene != expected["gene"] or product != expected["product"]:
        raise BetalainThreeEnzymeCaseError(f"Unexpected CDS gene/product annotation for {accession}.")
    if not sequence or set(sequence) - set("ATCG"):
        raise BetalainThreeEnzymeCaseError(f"{accession} CDS is not strict DNA.")
    if not sequence.startswith("ATG") or sequence[-3:] not in {"TAA", "TAG", "TGA"}:
        raise BetalainThreeEnzymeCaseError(f"{accession} CDS start or terminal stop codon differs from the record.")
    if len(sequence) % 3:
        raise BetalainThreeEnzymeCaseError(f"{accession} CDS length is not divisible by three.")
    if "*" in local_translation[:-1]:
        raise BetalainThreeEnzymeCaseError(f"{accession} CDS contains an internal in-frame stop codon.")
    if local_translation.rstrip("*") != translation_qualifier:
        raise BetalainThreeEnzymeCaseError(f"{accession} local translation differs from the GenBank qualifier.")
    if _sha256_dna(sequence) != expected["cds_sha256"]:
        raise BetalainThreeEnzymeCaseError(f"{accession} CDS SHA-256 mismatch.")
    fasta_path = EXTRACTED_CDS_DIR / expected["fasta"]
    if not fasta_path.exists():
        raise BetalainThreeEnzymeCaseError(f"Extracted CDS FASTA is missing: {fasta_path.name}.")
    try:
        fasta = SeqIO.read(fasta_path, "fasta")
    except Exception as exc:  # pragma: no cover - defensive error context
        raise BetalainThreeEnzymeCaseError(f"Cannot parse extracted CDS FASTA: {fasta_path.name}.") from exc
    if str(fasta.seq).upper() != sequence:
        raise BetalainThreeEnzymeCaseError(f"Extracted FASTA differs from the CDS feature for {accession}.")
    return {
        "accession": accession.split(".", 1)[0],
        "version": accession,
        "accession_version": accession,
        "organism": expected["organism"],
        "record_title": expected["title"],
        "gene": gene,
        "product": product,
        "cds_coordinates": _location(feature),
        "strand": int(feature.location.strand or 1),
        "cds_length": len(sequence),
        "contains_start_codon": True,
        "start_codon": sequence[:3],
        "contains_terminal_stop_codon": True,
        "terminal_stop_codon": sequence[-3:],
        "length_multiple_of_three": True,
        "internal_stop_codon_positions": [],
        "protein_length": len(translation_qualifier),
        "translation_qualifier": translation_qualifier,
        "local_translation": local_translation.rstrip("*"),
        "translation_matches_record": True,
        "cds_sequence": sequence,
        "cds_sha256": expected["cds_sha256"],
        "source_record_sha256": expected["record_sha256"],
        "raw_record_path": str(path.relative_to(CASE_ROOT)).replace("\\", "/"),
        "extracted_fasta_path": str(fasta_path.relative_to(CASE_ROOT)).replace("\\", "/"),
        "fetched_from": f"{FETCHED_FROM}?db=nuccore&id={accession}&rettype=gb&retmode=text",
        "fetched_date": FETCHED_DATE,
        "extraction_method": "Biopython SeqFeature.extract(record.seq) from the unique CDS feature; no sequence edits.",
        "verification_status": "passed",
        "manual_review_notes": "Sequence provenance verified from the local official-record snapshot; functional interpretation remains a literature-review item.",
    }


def load_betalain_three_enzyme_case() -> dict[str, Any]:
    """Validate official snapshots and return their exact CDS records."""
    entries = [_validate_entry(accession) for accession in _EXPECTED]
    if not MANIFEST_PATH.exists():
        raise BetalainThreeEnzymeCaseError("Source manifest is missing.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_entries = manifest.get("cds_records") if isinstance(manifest, dict) else None
    if not isinstance(manifest_entries, list) or [item.get("version") for item in manifest_entries] != [item["version"] for item in entries]:
        raise BetalainThreeEnzymeCaseError("Source manifest does not match the verified record order.")
    for item, expected in zip(manifest_entries, entries):
        required = {"accession", "version", "organism", "record_title", "gene", "product", "cds_coordinates", "cds_length", "protein_length", "cds_sha256", "source_record_sha256", "fetched_from", "fetched_date", "extraction_method", "verification_status", "manual_review_notes"}
        if not required <= set(item):
            raise BetalainThreeEnzymeCaseError("Source manifest has incomplete required fields.")
        if item["cds_sha256"] != expected["cds_sha256"] or item["source_record_sha256"] != expected["source_record_sha256"]:
            raise BetalainThreeEnzymeCaseError(f"Source manifest hash mismatch for {expected['version']}.")
    return {
        "case_id": CASE_ID,
        "project_name": PROJECT_NAME,
        "plant_host": "Nicotiana benthamiana",
        "design_scenario": SCENARIO_PATHWAY_MULTI_TU,
        "expression_application": "transient expression",
        "boundary_note": BOUNDARY_NOTE,
        "nonenzymatic_review_note": NONENZYMATIC_REVIEW_NOTE,
        "cds_records": entries,
        "manifest_path": str(MANIFEST_PATH.relative_to(CASE_ROOT)).replace("\\", "/"),
    }


def build_betalain_pathway_steps(unit_ids: list[str]) -> list[dict[str, Any]]:
    """Create the three fixed manual Gate 3 records for the supplied ordered TU ids."""
    case = load_betalain_three_enzyme_case()
    if len(unit_ids) < 3:
        raise BetalainThreeEnzymeCaseError("Three transcription units are required for the betalain case.")
    source_by_version = {record["version"]: record for record in case["cds_records"]}
    steps: list[dict[str, Any]] = []
    for index, definition in enumerate(_STEP_DEFINITIONS, start=1):
        step_name, substrate, product, enzyme, gene, organism, version = definition
        source = source_by_version[version]
        step = new_pathway_step(step_id=f"betalain-gate3-step-{index}")
        step.update(
            {
                "step_name": step_name,
                "substrate_name": substrate,
                "product_name": product,
                "enzyme_name": enzyme,
                "enzyme_gene_name": gene,
                "enzyme_source_organism": organism,
                "notes": "Public sequence source and pathway context are recorded for traceability; no expression outcome is asserted.",
                "cds_source_type": "public_database",
                "cds_source_reference": version,
                "mapped_unit_id": str(unit_ids[index - 1]),
                "manual_review_notes": NONENZYMATIC_REVIEW_NOTE if index == 3 else "Public record and local CDS translation checked; functional evidence remains a manual literature-review item.",
                "applied_to_unit": True,
            }
        )
        step.update(analyze_pathway_cds(source["cds_sequence"], source_type="public_database", source_reference=version))
        steps.append(step)
    return normalize_pathway_steps(steps)


def apply_betalain_case_to_units(transcription_units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Copy exact official CDS values into the first three existing TUs without changing other roles."""
    units = [copy.deepcopy(unit) for unit in transcription_units if isinstance(unit, dict)]
    if len(units) < 3:
        raise BetalainThreeEnzymeCaseError("Three transcription units are required for the betalain case.")
    steps = build_betalain_pathway_steps([str(unit.get("unit_id") or "") for unit in units[:3]])
    for step, unit in zip(steps, units[:3]):
        unit["cds"] = {
            "display_name": step["enzyme_gene_name"],
            "raw_text": step["cds_sequence"],
            "source_type": step["cds_source_type"],
            "source_name": step["cds_source_reference"],
            "source_format": str(step["cds_analysis"].get("source_format") or "plain"),
            "cds_analysis": copy.deepcopy(step["cds_analysis"]),
        }
    mapping = validate_pathway_mapping(steps, units)
    if not mapping["mapping_complete"]:
        raise BetalainThreeEnzymeCaseError("The verified CDS records could not be mapped to the requested transcription units.")
    return mapping["pathway_steps"], units, mapping


def evaluate_real_component_asset_gate() -> dict[str, Any]:
    """Report whether bundled catalog assets can legally complete this real-source case."""
    from services.local_design_asset_catalog_service import load_seed_records

    records = load_seed_records()
    required_types = {"promoter", "terminator", "plasmid_backbone"}
    usable: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for asset_type in sorted(required_types):
        candidates = [record for record in records if str(record.get("asset_type")) == asset_type]
        qualified = [
            record
            for record in candidates
            if bool(record.get("sequence_available"))
            and str(record.get("sequence_hash") or "").strip()
            and str(record.get("sequence_hash_algorithm") or "").strip()
            and str(record.get("source_notes") or "").strip()
            and "test_only" not in json.dumps(record, ensure_ascii=False).lower()
            and "placeholder" not in json.dumps(record, ensure_ascii=False).lower()
        ]
        usable.extend(copy.deepcopy(qualified))
        if not qualified:
            gaps.append(
                {
                    "asset_type": asset_type,
                    "reason": "No bundled asset has an actual DNA sequence, sequence SHA-256, and non-placeholder formal source record.",
                }
            )
    t_dna_records = [
        record
        for record in records
        if "t-dna" in json.dumps(record, ensure_ascii=False).lower()
        and bool(record.get("sequence_available"))
        and str(record.get("sequence_hash") or "").strip()
        and str(record.get("sequence_hash_algorithm") or "").strip()
        and "test_only" not in json.dumps(record, ensure_ascii=False).lower()
        and "placeholder" not in json.dumps(record, ensure_ascii=False).lower()
    ]
    usable.extend(copy.deepcopy(t_dna_records))
    if not t_dna_records:
        gaps.append(
            {
                "asset_type": "LB/RB/T-DNA record",
                "reason": "No bundled record provides real-source LB/RB/T-DNA DNA features with a sequence SHA-256 and formal provenance.",
            }
        )
    return {
        "complete_vector_allowed": not gaps,
        "usable_assets": usable,
        "missing_assets": gaps,
        "manual_review_items": [
            "No complete plasmid is generated until real-source promoter, 3' regulatory region, binary backbone, and LB/RB/T-DNA records are available.",
            "Reused regulatory sequences would require professional homology review before any later vector design.",
        ],
    }


def save_betalain_gate3_mapping(
    *,
    pathway_steps: list[dict[str, Any]],
    transcription_units: list[dict[str, Any]],
    repository: PlantProjectDraftRepository | None = None,
) -> PlantDesignProjectDraft:
    """Persist the approved partial acceptance state without claiming a complete vector."""
    case = load_betalain_three_enzyme_case()
    mapping = validate_pathway_mapping(pathway_steps, transcription_units)
    if not mapping["mapping_complete"] or not all(step.get("applied_to_unit") for step in mapping["pathway_steps"]):
        raise BetalainThreeEnzymeCaseError("Only a fully applied three-step mapping can be saved for this case.")
    gate = evaluate_real_component_asset_gate()
    if gate["complete_vector_allowed"]:
        raise BetalainThreeEnzymeCaseError("This partial-case saver is only valid while real-source vector assets remain unavailable.")
    repo = repository or PlantProjectDraftRepository()
    draft = repo.create_blank(PROJECT_NAME)
    draft.plant_design_goal = "Metabolic pathway multi-transcription-unit vector design record"
    draft.host_context = "Nicotiana benthamiana"
    draft.expression_context = "transient expression"
    draft.manual_review_state = {
        "review_state": "review-required",
        SAVED_STATE_KEY: {
            "case_id": CASE_ID,
            "design_scenario": SCENARIO_PATHWAY_MULTI_TU,
            "case_boundary_note": BOUNDARY_NOTE,
            "nonenzymatic_review_note": NONENZYMATIC_REVIEW_NOTE,
            "pathway_steps": copy.deepcopy(mapping["pathway_steps"]),
            "transcription_units": copy.deepcopy(transcription_units),
            "component_asset_gate": gate,
            "complete_vector_generated": False,
        },
    }
    return repo.save(draft)


def open_betalain_gate3_mapping(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> dict[str, Any]:
    """Reopen and revalidate the partial Gate 3 acceptance state."""
    draft = (repository or PlantProjectDraftRepository()).load(project_id)
    try:
        require_active_project(draft)
    except ValueError as exc:
        raise BetalainThreeEnzymeCaseError(str(exc)) from exc
    payload = dict(draft.manual_review_state.get(SAVED_STATE_KEY) or {})
    if payload.get("case_id") != CASE_ID:
        raise BetalainThreeEnzymeCaseError("The selected saved project is not the betalain Gate 3 case.")
    steps = normalize_pathway_steps(payload.get("pathway_steps"))
    units = [dict(unit) for unit in payload.get("transcription_units") or [] if isinstance(unit, dict)]
    mapping = validate_pathway_mapping(steps, units)
    if not mapping["mapping_complete"] or not all(step.get("applied_to_unit") for step in mapping["pathway_steps"]):
        raise BetalainThreeEnzymeCaseError("The saved Gate 3 mapping no longer verifies.")
    source_by_version = {item["version"]: item for item in load_betalain_three_enzyme_case()["cds_records"]}
    for step in mapping["pathway_steps"]:
        source = source_by_version.get(str(step.get("cds_source_reference") or ""))
        if source is None or step.get("cds_sequence") != source["cds_sequence"]:
            raise BetalainThreeEnzymeCaseError("The saved TU-mapped CDS differs from its verified official source.")
    return {
        "draft": draft,
        "pathway_steps": mapping["pathway_steps"],
        "transcription_units": units,
        "mapping": mapping,
        "component_asset_gate": dict(payload.get("component_asset_gate") or {}),
        "complete_vector_generated": False,
    }
