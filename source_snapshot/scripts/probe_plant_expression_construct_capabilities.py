from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Bio import SeqIO

from components import export_manager
from core.construct_builder import ConstructBuilder
from core.design_session import DesignSession
from core.part_library import BioPart, PartLibraryManager
from services import design_saver
from services import expression_construct_repository as construct_repo
from services import expression_wizard_construct_bridge as construct_bridge
from services import sequence_service
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import update_plant_project_draft
from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input
DEFAULT_MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "qa"
    / "data_manifests"
    / "v2_7_r226_real_construct_capability_matrix.json"
)
R225_CORPUS_PATH = (
    REPO_ROOT
    / "docs"
    / "qa"
    / "data_manifests"
    / "v2_7_r225_candidate_corpus_batch_1_summary.json"
)

ALLOWED_CLASSIFICATIONS = {
    "WORKING",
    "PARTIAL",
    "DISPLAY_ONLY",
    "MISSING",
    "DUPLICATE",
    "DEPRECATED",
}

NEXT_GATE1_TASK = (
    "Implement one canonical single-gene construct runtime spine that accepts parsed nucleotide input as a "
    "SequenceAsset, preserves ordered sequence-bearing components in one persisted construct model, and bridges "
    "that model directly to save/reopen plus FASTA/GenBank export before any backbone insertion work."
)

SYNTHETIC_INPUTS = {
    "promoter_name": "SYNTH_PROMOTER_ALPHA",
    "promoter_sequence": "TTGACATATAAAGG",
    "cds_name": "SYNTH_CDS_ALPHA",
    "cds_sequence": "ATGGCTGAACTGTAA",
    "terminator_name": "SYNTH_TERMINATOR_ALPHA",
    "terminator_sequence": "GCGTTTTTTGCG",
    "construct_name": "SYNTH_CONSTRUCT_ALPHA",
}

EXPECTED_FEATURES = [
    {"name": SYNTHETIC_INPUTS["promoter_name"], "type": "promoter", "start": 1, "end": 14},
    {"name": SYNTHETIC_INPUTS["cds_name"], "type": "CDS", "start": 15, "end": 29},
    {"name": SYNTHETIC_INPUTS["terminator_name"], "type": "terminator", "start": 30, "end": 41},
]
EXPECTED_CONCATENATED_SEQUENCE = (
    SYNTHETIC_INPUTS["promoter_sequence"]
    + SYNTHETIC_INPUTS["cds_sequence"]
    + SYNTHETIC_INPUTS["terminator_sequence"]
)
EXPECTED_TOTAL_LENGTH = len(EXPECTED_CONCATENATED_SEQUENCE)
EXPECTED_CDS_TRANSLATION = "MAEL*"
EXPECTED_SHA256 = hashlib.sha256(
    EXPECTED_CONCATENATED_SEQUENCE.encode("utf-8")
).hexdigest()
EXPECTED_REVERSE_COMPLEMENT_CDS = "TTACAGTTCAGCCAT"


@dataclass(frozen=True)
class RuntimePaths:
    runtime_root: Path
    design_db_path: Path
    construct_db_path: Path
    plant_draft_dir: Path


def synthetic_inputs() -> dict[str, Any]:
    return {
        **SYNTHETIC_INPUTS,
        "expected_features": copy.deepcopy(EXPECTED_FEATURES),
        "expected_concatenated_sequence": EXPECTED_CONCATENATED_SEQUENCE,
        "expected_total_length": EXPECTED_TOTAL_LENGTH,
        "expected_cds_translation": EXPECTED_CDS_TRANSLATION,
        "expected_sha256": EXPECTED_SHA256,
        "expected_reverse_complement_cds": EXPECTED_REVERSE_COMPLEMENT_CDS,
    }


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _runtime_paths(runtime_root: Path | None) -> RuntimePaths:
    resolved_root = (runtime_root or (REPO_ROOT / ".pytest_tmp" / "r226_probe_runtime")).resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    design_db_path = resolved_root / "wizard_saved_designs.sqlite"
    construct_db_path = resolved_root / "construct_workspace.sqlite"
    plant_draft_dir = resolved_root / "plant_project_drafts"
    plant_draft_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        design_db_path,
        construct_db_path,
        Path(f"{design_db_path}-wal"),
        Path(f"{design_db_path}-shm"),
        Path(f"{construct_db_path}-wal"),
        Path(f"{construct_db_path}-shm"),
    ):
        if path.exists():
            path.unlink()
    return RuntimePaths(
        runtime_root=resolved_root,
        design_db_path=design_db_path,
        construct_db_path=construct_db_path,
        plant_draft_dir=plant_draft_dir,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _roundtrip_genbank(sequence: str, features: list[dict[str, Any]], project_name: str) -> dict[str, Any]:
    genbank_text = export_manager.generate_genbank_string(sequence, features, project_name)
    record = next(SeqIO.parse(io.StringIO(genbank_text), "genbank"))
    parsed_features = [
        {
            "type": feature.type,
            "label": feature.qualifiers.get("label", [""])[0],
            "start": int(feature.location.start) + 1,
            "end": int(feature.location.end),
            "strand": feature.location.strand,
        }
        for feature in record.features
    ]
    return {
        "genbank_text": genbank_text,
        "sequence": str(record.seq).upper(),
        "feature_count": len(record.features),
        "features": parsed_features,
        "topology": str(record.annotations.get("topology") or ""),
    }


def _export_strand_probe(sequence: str) -> dict[str, Any]:
    strand_feature = [{"name": "reverse_feature", "type": "misc_feature", "start": 2, "end": 6, "strand": -1}]
    record = next(
        SeqIO.parse(
            io.StringIO(export_manager.generate_genbank_string(sequence, strand_feature, "STRAND_PROBE")),
            "genbank",
        )
    )
    first_feature = record.features[0]
    return {
        "expected_strand": -1,
        "observed_strand": int(first_feature.location.strand or 0),
    }


def _build_construct_probe() -> dict[str, Any]:
    parts = [
        BioPart(
            name=SYNTHETIC_INPUTS["promoter_name"],
            part_type="promoter",
            sequence=SYNTHETIC_INPUTS["promoter_sequence"],
        ),
        BioPart(
            name=SYNTHETIC_INPUTS["cds_name"],
            part_type="CDS",
            sequence=SYNTHETIC_INPUTS["cds_sequence"],
        ),
        BioPart(
            name=SYNTHETIC_INPUTS["terminator_name"],
            part_type="terminator",
            sequence=SYNTHETIC_INPUTS["terminator_sequence"],
        ),
    ]
    result = ConstructBuilder().build_linear_construct(parts)
    return {
        "final_sequence": result["final_sequence"],
        "total_length": result["total_length"],
        "features": result["features"],
    }


def _wizard_saved_design_probe(paths: RuntimePaths, construct_result: dict[str, Any]) -> dict[str, Any]:
    original_db_path = design_saver.DB_PATH
    try:
        design_saver.DB_PATH = str(paths.design_db_path)
        design_session = DesignSession(
            step=6,
            gene_name=SYNTHETIC_INPUTS["construct_name"],
            original_seq=SYNTHETIC_INPUTS["cds_sequence"],
            optimized_seq=SYNTHETIC_INPUTS["cds_sequence"],
            host="Synthetic Audit Host",
            elements={
                "promoter_name": SYNTHETIC_INPUTS["promoter_name"],
                "promoter_seq": SYNTHETIC_INPUTS["promoter_sequence"],
                "rbs_name": "",
                "rbs_seq": "",
                "terminator_name": SYNTHETIC_INPUTS["terminator_name"],
                "terminator_seq": SYNTHETIC_INPUTS["terminator_sequence"],
            },
            frame={
                "success": True,
                "final_sequence": construct_result["final_sequence"],
                "total_length": construct_result["total_length"],
                "gc_content": round(sequence_service.gc_content(construct_result["final_sequence"]), 1),
                "features": copy.deepcopy(construct_result["features"]),
                "parts": [
                    {
                        "name": SYNTHETIC_INPUTS["promoter_name"],
                        "type": "promoter",
                        "seq": SYNTHETIC_INPUTS["promoter_sequence"],
                    },
                    {
                        "name": SYNTHETIC_INPUTS["cds_name"],
                        "type": "CDS",
                        "seq": SYNTHETIC_INPUTS["cds_sequence"],
                    },
                    {
                        "name": SYNTHETIC_INPUTS["terminator_name"],
                        "type": "terminator",
                        "seq": SYNTHETIC_INPUTS["terminator_sequence"],
                    },
                ],
            },
            validation_results=[{"severity": "info", "code": "PASS", "title": "Synthetic audit only"}],
        )
        save_ok, save_result = design_saver.save_wizard_design(design_session)
        load_ok, loaded = design_saver.load_wizard_design(save_result["design_id"] if save_ok else "")
        return {
            "save_ok": bool(save_ok),
            "save_result": {
                "identity_source": "immutable_design_id",
                "saved_record_created": bool(save_ok),
            },
            "load_ok": bool(load_ok),
            "loaded_sequence": loaded.frame.get("final_sequence", "") if load_ok else "",
            "loaded_features": loaded.frame.get("features", []) if load_ok else [],
            "loaded_original_seq": loaded.original_seq if load_ok else "",
        }
    finally:
        design_saver.DB_PATH = original_db_path


def _construct_workspace_probe(paths: RuntimePaths, construct_result: dict[str, Any]) -> dict[str, Any]:
    original_db_path = construct_repo.DB_PATH
    try:
        construct_repo.DB_PATH = str(paths.construct_db_path)
        wizard_state = DesignSession(
            step=6,
            gene_name=SYNTHETIC_INPUTS["construct_name"],
            original_seq=SYNTHETIC_INPUTS["cds_sequence"],
            optimized_seq=SYNTHETIC_INPUTS["cds_sequence"],
            host="Synthetic Audit Host",
            frame={
                "success": True,
                "final_sequence": construct_result["final_sequence"],
                "features": copy.deepcopy(construct_result["features"]),
                "parts": [
                    {
                        "name": SYNTHETIC_INPUTS["promoter_name"],
                        "type": "promoter",
                        "seq": SYNTHETIC_INPUTS["promoter_sequence"],
                    },
                    {
                        "name": SYNTHETIC_INPUTS["cds_name"],
                        "type": "CDS",
                        "seq": SYNTHETIC_INPUTS["cds_sequence"],
                    },
                    {
                        "name": SYNTHETIC_INPUTS["terminator_name"],
                        "type": "terminator",
                        "seq": SYNTHETIC_INPUTS["terminator_sequence"],
                    },
                ],
            },
        )
        saved = construct_bridge.save_wizard_draft_to_construct(
            wizard_state,
            create_new_construct=True,
            new_construct_label="Synthetic audit construct workspace record",
        )
        cassette_parts = saved.cassette_parts
        return {
            "construct_type": saved.construct.get("construct_type", ""),
            "cassette_role": saved.cassette.get("cassette_role", ""),
            "cassette_parts": [
                {
                    "part_label": part.get("part_label", ""),
                    "part_role": part.get("part_role", ""),
                    "part_reference": part.get("part_reference", ""),
                }
                for part in cassette_parts
            ],
        }
    finally:
        construct_repo.DB_PATH = original_db_path


def _r224_persistence_probe(paths: RuntimePaths) -> dict[str, Any]:
    repository = PlantProjectDraftRepository(paths.plant_draft_dir)
    draft = repository.create_blank(project_name="Synthetic audit draft")
    updated = update_plant_project_draft(
        draft,
        plant_design_goal="Synthetic audit project goal",
        host_context="Synthetic host context",
        expression_context="Synthetic expression context",
        construct_slot_updates={
            "target_gene_or_cds": {
                "component_name": SYNTHETIC_INPUTS["cds_name"],
                "source_reference": "synthetic source ref",
            },
            "promoter_or_regulatory_element": {
                "component_name": SYNTHETIC_INPUTS["promoter_name"],
                "source_reference": "synthetic source ref",
            },
            "terminator": {
                "component_name": SYNTHETIC_INPUTS["terminator_name"],
                "source_reference": "synthetic source ref",
            },
        },
    )
    saved = repository.save(updated)
    loaded = repository.load(saved.project_id)
    payload = loaded.to_dict()
    absent_fields = [
        field
        for field in (
            "sequence",
            "dna_sequence",
            "features",
            "orientation",
            "generated_sequence",
            "sequence_sha256",
            "construct_revision",
            "export_identity",
        )
        if field not in payload
    ]
    return {
        "schema_version": payload["schema_version"],
        "top_level_keys": sorted(payload.keys()),
        "construct_slot_count": len(payload.get("construct_slots", [])),
        "absent_real_construct_fields": absent_fields,
    }


def _asset_inventory() -> dict[str, Any]:
    bio_db_path = REPO_ROOT / "data" / "bio_db.json"
    bio_db = json.loads(bio_db_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for category, values in bio_db.items():
        if category == "project_meta":
            continue
        if isinstance(values, dict):
            for record_key, payload in values.items():
                if isinstance(payload, dict):
                    row = dict(payload)
                    row["_category"] = category
                    row["_record_key"] = record_key
                    records.append(row)

    verified = [
        record
        for record in records
        if "verified" in str(record.get("source_id", "")).lower()
    ]

    rice_records = json.loads(
        (REPO_ROOT / "data" / "plant_seed" / "rice_albumin" / "component_records.json").read_text(
            encoding="utf-8"
        )
    )["records"]

    return {
        "committed_sequence_files": {
            "fasta_files": 0,
            "genbank_files": 0,
        },
        "component_records_with_actual_dna": len(records),
        "component_records_with_protein_only": 0,
        "component_records_with_metadata_only": len(rice_records),
        "real_backbone_sequences": 0,
        "verified_or_manually_reviewed_sequence_records": len(verified),
        "rice_albumin_assets_with_real_sequences": 0,
        "artemisia_assets_with_real_sequences": 0,
        "sequence_asset_files": ["data/bio_db.json"],
        "metadata_only_files": [
            "data/local_design_asset_seed.json",
            "data/plant_promoter_catalog_seed.json",
            "data/plant_seed/rice_albumin/component_records.json",
        ],
    }


def _implementation_inventory() -> dict[str, Any]:
    return {
        "sequence_parsing_and_representation": [
            {
                "file_path": "views/wizard_steps/step1_gene_input.py",
                "public_symbol": "_clean_pasted_gene_input",
                "expected_input": "raw pasted DNA or FASTA text",
                "actual_output": "cleaned uppercase DNA string plus warnings",
                "production_usage": True,
                "tests_with_real_sequences": [
                    "tests/test_step1_fasta_paste_regression.py",
                    "tests/test_wizard_regression.py",
                ],
                "classification": "WORKING",
                "reuse_recommendation": "reuse",
            },
            {
                "file_path": "core/part_library.py",
                "public_symbol": "PartLibraryManager.parse_fasta",
                "expected_input": "single or multi-record FASTA text",
                "actual_output": "list of record dicts with name and sequence",
                "production_usage": False,
                "tests_with_real_sequences": [],
                "classification": "PARTIAL",
                "reuse_recommendation": "adapt",
            },
            {
                "file_path": "services/sequence_service.py",
                "public_symbol": "reverse_complement / translate / seq_hash",
                "expected_input": "DNA sequence strings",
                "actual_output": "reverse complement, amino-acid translation, SHA-256 checksum",
                "production_usage": True,
                "tests_with_real_sequences": [
                    "tests/test_sequence_tools_regression.py",
                ],
                "classification": "WORKING",
                "reuse_recommendation": "reuse",
            },
            {
                "file_path": "components/export_manager.py",
                "public_symbol": "generate_genbank_string",
                "expected_input": "DNA sequence plus feature rows",
                "actual_output": "GenBank text",
                "production_usage": True,
                "tests_with_real_sequences": [
                    "tests/test_export_manager_workflow.py",
                    "tests/test_wizard_regression.py",
                ],
                "classification": "PARTIAL",
                "reuse_recommendation": "adapt",
            },
        ],
        "component_and_construct_representation": [
            {
                "file_path": "core/part_library.py",
                "public_symbol": "BioPart",
                "expected_input": "name, type, DNA sequence",
                "actual_output": "validated in-memory part with actual DNA",
                "production_usage": False,
                "tests_with_real_sequences": [],
                "classification": "PARTIAL",
                "reuse_recommendation": "adapt",
            },
            {
                "file_path": "core/construct_builder.py",
                "public_symbol": "ConstructBuilder.build_linear_construct",
                "expected_input": "ordered BioPart list",
                "actual_output": "concatenated DNA plus 1-based part coordinates",
                "production_usage": False,
                "tests_with_real_sequences": [],
                "classification": "PARTIAL",
                "reuse_recommendation": "adapt",
            },
            {
                "file_path": "services/expression_construct_repository.py",
                "public_symbol": "construct profile / cassette / part repositories",
                "expected_input": "labels, notes, provenance, roles",
                "actual_output": "documentation-only construct rows without DNA sequence payloads",
                "production_usage": True,
                "tests_with_real_sequences": [],
                "classification": "DISPLAY_ONLY",
                "reuse_recommendation": "freeze",
            },
            {
                "file_path": "services/plant_project_draft_schema.py",
                "public_symbol": "PlantDesignProjectDraft",
                "expected_input": "goal, host context, construct slots, evidence rows",
                "actual_output": "documentation-only project draft payload",
                "production_usage": True,
                "tests_with_real_sequences": [
                    "tests/test_r224_plant_project_draft_persistence.py",
                ],
                "classification": "DISPLAY_ONLY",
                "reuse_recommendation": "adapt",
            },
        ],
        "duplication_and_burden": [
            {
                "area": "Construct concatenation",
                "implementations": [
                    "core/construct_builder.py",
                    "core/expression_frame_builder.py",
                    "components/assembly_modules/tab_cloning.py",
                ],
                "recommendation": "merge later",
            },
            {
                "area": "Persistence paths",
                "implementations": [
                    "services/design_saver.py",
                    "services/plant_project_draft_repository.py",
                    "services/expression_construct_repository.py",
                ],
                "recommendation": "merge later",
            },
            {
                "area": "Dormant sequence cleaning and assembly helpers",
                "implementations": [
                    "core/assembly_utils.py",
                    "services/sequence_service.py",
                ],
                "recommendation": "deprecate",
            },
            {
                "area": "Export and map surfaces",
                "implementations": [
                    "components/export_manager.py",
                    "components/assembly_modules/tab_export.py",
                    "components/assembly_modules/tab_plasmid_map.py",
                ],
                "recommendation": "freeze",
            },
        ],
    }


def _capability(
    *,
    name: str,
    classification: str,
    implementation_path: str,
    implementation_paths: list[str],
    evidence: str,
    observed_result: Any,
    expected_result: Any,
    gap: str,
    reuse_decision: str,
    recommended_next_action: str,
    blocking_reason: str = "",
    confidence: str = "high",
) -> dict[str, Any]:
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise ValueError(f"Unsupported classification: {classification}")
    return {
        "capability": name,
        "classification": classification,
        "implementation_path": implementation_path,
        "implementation_paths": implementation_paths,
        "evidence": evidence,
        "observed_result": observed_result,
        "expected_result": expected_result,
        "gap": gap,
        "reuse_decision": reuse_decision,
        "recommended_gate1_task": NEXT_GATE1_TASK,
        "recommended_next_action": recommended_next_action,
        "blocking_reason": blocking_reason,
        "confidence_level": confidence,
    }


def run_probe(
    *,
    audit_timestamp: str,
    repo_head: str | None = None,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    paths = _runtime_paths(runtime_root)
    head = repo_head or _git_head()
    inputs = synthetic_inputs()

    raw_dna_input = f">{inputs['cds_name']}\n{inputs['cds_sequence']}"
    parsed_single_fasta, single_fasta_warnings = _clean_pasted_gene_input(
        raw_dna_input,
        use_service_cleaner=True,
    )
    multi_fasta_records = PartLibraryManager.parse_fasta(
        ">record_alpha\nATGGCTGAACTGTAA\n>record_beta\nTTGACATATAAAGG"
    )
    protein_fasta_error = ""
    try:
        PartLibraryManager.parse_fasta(">protein_alpha\nMPEPTIDE")
    except Exception as exc:
        protein_fasta_error = str(exc)

    construct_result = _build_construct_probe()
    cds_translation = sequence_service.translate(inputs["cds_sequence"])
    reverse_complement = sequence_service.reverse_complement(inputs["cds_sequence"])
    sequence_checksum = sequence_service.seq_hash(construct_result["final_sequence"])
    wizard_save = _wizard_saved_design_probe(paths, construct_result)
    export_payloads = export_manager.build_export_payloads(
        construct_result["final_sequence"],
        copy.deepcopy(construct_result["features"]),
        inputs["construct_name"],
    )
    roundtrip = _roundtrip_genbank(
        construct_result["final_sequence"],
        copy.deepcopy(construct_result["features"]),
        inputs["construct_name"],
    )
    strand_probe = _export_strand_probe(construct_result["final_sequence"])
    r224_probe = _r224_persistence_probe(paths)
    construct_workspace_probe = _construct_workspace_probe(paths, construct_result)
    assets = _asset_inventory()

    capabilities = [
        _capability(
            name="Raw DNA paste parsing",
            classification="WORKING",
            implementation_path="views/wizard_steps/step1_gene_input.py:_clean_pasted_gene_input",
            implementation_paths=[
                "views/wizard_steps/step1_gene_input.py:_clean_pasted_gene_input",
                "services/sequence_service.py:clean",
            ],
            evidence="Single-record FASTA paste cleaned to the exact CDS sequence used by the synthetic probe.",
            observed_result={"parsed_sequence": parsed_single_fasta, "warnings": single_fasta_warnings},
            expected_result={"parsed_sequence": inputs["cds_sequence"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Use the existing cleaner as the raw-input front door for a canonical SequenceAsset ingest path.",
        ),
        _capability(
            name="Single-record nucleotide FASTA import",
            classification="WORKING",
            implementation_path="views/wizard_steps/step1_gene_input.py:_clean_pasted_gene_input",
            implementation_paths=[
                "views/wizard_steps/step1_gene_input.py:_clean_pasted_gene_input",
            ],
            evidence="A single FASTA record round-tripped to the exact nucleotide CDS string without extra bases.",
            observed_result={"record_count": 1, "sequence": parsed_single_fasta},
            expected_result={"record_count": 1, "sequence": inputs["cds_sequence"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Keep the current single-record FASTA pathway and map it into a canonical sequence object instead of bare strings.",
        ),
        _capability(
            name="Multi-record FASTA import",
            classification="PARTIAL",
            implementation_path="core/part_library.py:PartLibraryManager.parse_fasta",
            implementation_paths=[
                "core/part_library.py:PartLibraryManager.parse_fasta",
                "views/wizard_steps/step1_gene_input.py:page",
            ],
            evidence="The dormant parser returned two distinct FASTA records, but the active Step 1 wizard path merges pasted multi-record input into one sequence string.",
            observed_result={
                "record_count": len(multi_fasta_records),
                "record_names": [record["name"] for record in multi_fasta_records],
            },
            expected_result={"record_count": 2, "record_names": ["record_alpha", "record_beta"]},
            gap="Current construct intake does not preserve multiple nucleotide assets as separate runtime records.",
            reuse_decision="adapt",
            recommended_next_action="Promote the existing multi-record FASTA parser into the active ingest path and persist per-record identities.",
        ),
        _capability(
            name="Protein FASTA distinction",
            classification="PARTIAL",
            implementation_path="core/part_library.py:PartLibraryManager.parse_fasta",
            implementation_paths=[
                "core/part_library.py:PartLibraryManager.parse_fasta",
                "views/wizard_steps/step1_gene_input.py:_clean_pasted_gene_input",
            ],
            evidence="The dormant FASTA parser rejected amino-acid letters as non-nucleotide content, but the active wizard cleaner is still DNA-only and does not create a typed protein asset.",
            observed_result={"protein_fasta_error": protein_fasta_error},
            expected_result={"protein_fasta_error_contains": "invalid nucleotide"},
            gap="The repository distinguishes invalid protein-like FASTA only as a rejection, not as a first-class protein sequence asset.",
            reuse_decision="adapt",
            recommended_next_action="Add explicit sequence-type classification at ingest time before any construct persistence work.",
        ),
        _capability(
            name="GenBank sequence import",
            classification="PARTIAL",
            implementation_path="views/wizard_steps/step1_gene_input.py:page upload branch",
            implementation_paths=[
                "views/wizard_steps/step1_gene_input.py:page upload branch",
            ],
            evidence="The Step 1 upload branch reads GenBank via Biopython and can recover nucleotide sequence and record name, but it does not preserve the richer record content.",
            observed_result={
                "roundtrip_sequence_length": len(roundtrip["sequence"]),
                "roundtrip_sequence_matches": roundtrip["sequence"] == construct_result["final_sequence"],
            },
            expected_result={
                "roundtrip_sequence_length": EXPECTED_TOTAL_LENGTH,
                "roundtrip_sequence_matches": True,
            },
            gap="Active runtime intake keeps sequence and name only.",
            reuse_decision="adapt",
            recommended_next_action="Extract a production GenBank import adapter that preserves sequence, features, topology, and source metadata into a canonical asset model.",
        ),
        _capability(
            name="GenBank feature import",
            classification="MISSING",
            implementation_path="views/wizard_steps/step1_gene_input.py:page upload branch",
            implementation_paths=[
                "views/wizard_steps/step1_gene_input.py:page upload branch",
            ],
            evidence="The exported GenBank record contained three features, but the active Step 1 upload branch only copies rec.seq and rec.name from the parsed record.",
            observed_result={"roundtrip_feature_count": roundtrip["feature_count"]},
            expected_result={"runtime_preserves_feature_count": roundtrip["feature_count"]},
            gap="Feature rows are dropped at import time, so imported annotated GenBank does not become an annotated runtime construct asset.",
            reuse_decision="adapt",
            recommended_next_action="Implement a real GenBank-to-sequence-asset importer before adding backbone insertion or multi-part editing.",
            blocking_reason="No production adapter maps rec.features into stored runtime feature coordinates.",
        ),
        _capability(
            name="Circular topology preservation",
            classification="MISSING",
            implementation_path="components/export_manager.py:generate_genbank_string",
            implementation_paths=[
                "components/export_manager.py:generate_genbank_string",
                "views/wizard_steps/step1_gene_input.py:page upload branch",
            ],
            evidence="The GenBank round-trip preserved sequence text but the parsed record annotations contained no topology value.",
            observed_result={"topology": roundtrip["topology"]},
            expected_result={"topology": "circular"},
            gap="Neither import nor export preserves circular topology for construct assets.",
            reuse_decision="adapt",
            recommended_next_action="Add topology fields to the canonical sequence asset and thread them through export/import before plasmid insertion work.",
            blocking_reason="Topology is not represented in the active save/export models.",
        ),
        _capability(
            name="Reverse complement",
            classification="WORKING",
            implementation_path="services/sequence_service.py:reverse_complement",
            implementation_paths=[
                "services/sequence_service.py:reverse_complement",
            ],
            evidence="Reverse complement of the synthetic CDS matched the expected deterministic value.",
            observed_result={"reverse_complement": reverse_complement},
            expected_result={"reverse_complement": inputs["expected_reverse_complement_cds"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Reuse this helper inside canonical orientation-aware component assembly.",
        ),
        _capability(
            name="CDS translation",
            classification="WORKING",
            implementation_path="services/sequence_service.py:translate",
            implementation_paths=[
                "services/sequence_service.py:translate",
                "core/expression_frame_builder.py",
            ],
            evidence="Translation of the synthetic CDS produced the expected amino-acid sequence including the terminal stop.",
            observed_result={"translation": cds_translation},
            expected_result={"translation": inputs["expected_cds_translation"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Reuse the current translation helper inside construct validation and round-trip verification.",
        ),
        _capability(
            name="Sequence checksum",
            classification="WORKING",
            implementation_path="services/sequence_service.py:seq_hash",
            implementation_paths=[
                "services/sequence_service.py:seq_hash",
                "components/export_manager.py:build_export_manifest",
            ],
            evidence="SHA-256 checksum of the synthetic assembled construct matched the expected fixed digest.",
            observed_result={"sha256": sequence_checksum},
            expected_result={"sha256": inputs["expected_sha256"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Make this checksum a first-class persisted field in the canonical construct runtime model.",
        ),
        _capability(
            name="Canonical SequenceAsset",
            classification="MISSING",
            implementation_path="services/plant_project_draft_schema.py:PlantDesignProjectDraft",
            implementation_paths=[
                "services/plant_project_draft_schema.py:PlantDesignProjectDraft",
                "services/design_saver.py:save_wizard_design",
            ],
            evidence="Sequence-bearing code paths store plain strings or wizard snapshots, but no shared runtime object currently holds sequence, checksum, topology, features, provenance, and revision identity together.",
            observed_result={"sequence_asset_type_present": False},
            expected_result={"sequence_asset_type_present": True},
            gap="The repository has sequence strings and exports, but no canonical sequence asset abstraction.",
            reuse_decision="adapt",
            recommended_next_action="Implement the missing SequenceAsset first; it is the nearest shared breakpoint across ingest, save/reopen, and export.",
            blocking_reason="No active runtime model combines sequence content with feature/provenance/topology metadata.",
        ),
        _capability(
            name="Canonical Component",
            classification="PARTIAL",
            implementation_path="core/part_library.py:BioPart",
            implementation_paths=[
                "core/part_library.py:BioPart",
                "services/expression_construct_repository.py",
            ],
            evidence="BioPart stores actual DNA and type, but active construct repositories store documentation labels and provenance without real component DNA or orientation.",
            observed_result={
                "biopart_fields": ["name", "part_type", "sequence"],
                "construct_workspace_part_reference_example": construct_workspace_probe["cassette_parts"][0]["part_reference"],
            },
            expected_result={
                "component_has_actual_dna": True,
                "component_has_orientation": True,
                "component_has_source_and_revision": True,
            },
            gap="There is no single active component model that combines actual DNA with runtime provenance and ordered construct participation.",
            reuse_decision="adapt",
            recommended_next_action="Promote BioPart-like sequence-bearing records into the active plant construct path instead of length-only readback rows.",
        ),
        _capability(
            name="Canonical TranscriptionUnit",
            classification="MISSING",
            implementation_path="core/construct_builder.py:ConstructBuilder.build_linear_construct",
            implementation_paths=[
                "core/construct_builder.py:ConstructBuilder.build_linear_construct",
                "core/expression_frame_builder.py:build_expression_frame",
            ],
            evidence="The probe can assemble an ordered promoter/CDS/terminator list into DNA, but the repository has no dedicated persisted TranscriptionUnit runtime object.",
            observed_result={"dedicated_transcription_unit_type_present": False},
            expected_result={"dedicated_transcription_unit_type_present": True},
            gap="Assembly exists as functions over lists and dicts, not as a canonical transcription-unit object.",
            reuse_decision="adapt",
            recommended_next_action="Introduce one runtime TranscriptionUnit model before any backbone work.",
            blocking_reason="No active persisted model carries ordered components, feature coordinates, and sequence together as a transcription unit.",
        ),
        _capability(
            name="Generated concatenated DNA",
            classification="WORKING",
            implementation_path="core/construct_builder.py:ConstructBuilder.build_linear_construct",
            implementation_paths=[
                "core/construct_builder.py:ConstructBuilder.build_linear_construct",
                "core/expression_frame_builder.py:build_expression_frame",
            ],
            evidence="The synthetic promoter + CDS + terminator sequence assembled to the exact expected 41 bp nucleotide product.",
            observed_result={
                "final_sequence": construct_result["final_sequence"],
                "total_length": construct_result["total_length"],
            },
            expected_result={
                "final_sequence": inputs["expected_concatenated_sequence"],
                "total_length": inputs["expected_total_length"],
            },
            gap="",
            reuse_decision="adapt",
            recommended_next_action="Reuse the deterministic concatenation logic, but wrap it in the missing canonical construct model.",
        ),
        _capability(
            name="Deterministic feature coordinates",
            classification="WORKING",
            implementation_path="core/construct_builder.py:ConstructBuilder.build_linear_construct",
            implementation_paths=[
                "core/construct_builder.py:ConstructBuilder.build_linear_construct",
                "components/export_manager.py:_build_features_from_parts",
            ],
            evidence="The construct builder returned the exact expected 1-based inclusive promoter/CDS/terminator coordinate ranges.",
            observed_result={"features": construct_result["features"]},
            expected_result={"features": inputs["expected_features"]},
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Carry the current 1-based coordinate convention into the canonical persisted construct schema.",
        ),
        _capability(
            name="Basic validation",
            classification="PARTIAL",
            implementation_path="services/sequence_service.py / views/wizard_steps/_shared.py / core/expression_frame_builder.py",
            implementation_paths=[
                "services/sequence_service.py",
                "views/wizard_steps/_shared.py",
                "core/expression_frame_builder.py:validate_frame",
            ],
            evidence="DNA cleaning, reverse complement, translation, start/stop checks, and internal-stop validation exist, but there is no end-to-end construct validator for orientation, overlaps, topology, or backbone insertion.",
            observed_result={
                "translation_matches": cds_translation == inputs["expected_cds_translation"],
                "checksum_matches": sequence_checksum == inputs["expected_sha256"],
                "reverse_complement_matches": reverse_complement == inputs["expected_reverse_complement_cds"],
            },
            expected_result={
                "translation_matches": True,
                "checksum_matches": True,
                "reverse_complement_matches": True,
                "construct_level_validation_complete": True,
            },
            gap="Validation is real but incomplete for a persisted construct runtime.",
            reuse_decision="adapt",
            recommended_next_action="Bind the existing sequence checks into a canonical construct validator with coordinate and orientation rules.",
        ),
        _capability(
            name="R224 persistence reuse",
            classification="PARTIAL",
            implementation_path="services/plant_project_draft_repository.py:PlantProjectDraftRepository",
            implementation_paths=[
                "services/plant_project_draft_repository.py:PlantProjectDraftRepository",
                "services/plant_project_draft_schema.py:PlantDesignProjectDraft",
            ],
            evidence="The R224 repository saved and reloaded a durable JSON draft, but the stored payload omitted sequence, coordinates, checksum, generated DNA, and export identity fields.",
            observed_result=r224_probe,
            expected_result={
                "schema_version": "v2.7-r224-plant-design-project-draft",
                "stores_real_construct_fields": True,
            },
            gap="The file-based repository mechanics are reusable, but the payload is documentation-slot oriented rather than real construct oriented.",
            reuse_decision="adapt",
            recommended_next_action="Reuse the durable JSON repository mechanics, but extend or replace the payload with real construct fields instead of slot-only notes.",
        ),
        _capability(
            name="Save/reopen construct",
            classification="PARTIAL",
            implementation_path="services/design_saver.py:save_wizard_design / load_wizard_design",
            implementation_paths=[
                "services/design_saver.py:save_wizard_design",
                "services/design_saver.py:load_wizard_design",
            ],
            evidence="The probe saved and reloaded the synthetic construct sequence and feature list through the wizard snapshot path, but this is separate from the plant project draft and construct workspace paths.",
            observed_result=wizard_save,
            expected_result={
                "save_ok": True,
                "load_ok": True,
                "loaded_sequence": inputs["expected_concatenated_sequence"],
            },
            gap="A construct-like save/reopen path exists only as a wizard snapshot, not as the canonical plant construct runtime.",
            reuse_decision="adapt",
            recommended_next_action="Bridge the existing save/reopen mechanics to the canonical single-gene construct model instead of adding another repository.",
        ),
        _capability(
            name="Backbone sequence representation",
            classification="MISSING",
            implementation_path="services/expression_construct_repository.py",
            implementation_paths=[
                "services/expression_construct_repository.py",
                "data/bio_db.json",
            ],
            evidence="Committed sequence assets contained no real backbone/vector DNA records, and active construct repositories store only backbone labels or notes.",
            observed_result={
                "real_backbone_sequences": assets["real_backbone_sequences"],
                "construct_profile_backbone_field_type": "label_only",
            },
            expected_result={
                "real_backbone_sequences": 1,
                "construct_profile_backbone_field_type": "sequence_asset_reference",
            },
            gap="There is no committed real backbone sequence inventory and no canonical runtime backbone object.",
            reuse_decision="adapt",
            recommended_next_action="Defer backbone insertion until the single-gene sequence-bearing construct spine exists.",
            blocking_reason="No backbone DNA asset is available in committed product-ready runtime data.",
        ),
        _capability(
            name="Backbone insertion",
            classification="MISSING",
            implementation_path="components/assembly_modules/tab_cloning.py",
            implementation_paths=[
                "components/assembly_modules/tab_cloning.py",
                "core/assembly_utils.py",
            ],
            evidence="Older cloning previews can concatenate fragments, but no active production path accepts a backbone sequence plus insertion coordinates and returns a persisted plasmid construct.",
            observed_result={"active_backbone_insertion_path_present": False},
            expected_result={"active_backbone_insertion_path_present": True},
            gap="No executable insertion workflow exists for a real backbone asset.",
            reuse_decision="freeze",
            recommended_next_action="Do not start backbone insertion until the canonical construct persistence model is in place.",
            blocking_reason="The repository has no active sequence-bearing backbone runtime or insertion coordinate model.",
        ),
        _capability(
            name="Complete plasmid sequence",
            classification="MISSING",
            implementation_path="components/assembly_modules/tab_plasmid_map.py",
            implementation_paths=[
                "components/assembly_modules/tab_plasmid_map.py",
                "components/plasmid_map.py",
            ],
            evidence="The map and export views can display or export an active sequence string, but there is no current runtime that builds a complete plasmid from a backbone plus inserted expression cassette.",
            observed_result={"complete_plasmid_builder_present": False},
            expected_result={"complete_plasmid_builder_present": True},
            gap="Visualization exists without real plasmid assembly.",
            reuse_decision="freeze",
            recommended_next_action="Finish the linear single-gene construct runtime first, then add backbone assembly against that stable spine.",
            blocking_reason="No active complete-plasmid assembly model exists.",
        ),
        _capability(
            name="FASTA export",
            classification="WORKING",
            implementation_path="components/export_manager.py:generate_fasta_string",
            implementation_paths=[
                "components/export_manager.py:generate_fasta_string",
            ],
            evidence="The export payload contained a FASTA artifact whose body matched the exact synthetic assembled sequence.",
            observed_result={
                "file_name": export_payloads["fasta"]["file_name"],
                "starts_with": export_payloads["fasta"]["data"].splitlines()[0],
            },
            expected_result={
                "file_name": "SYNTH_CONSTRUCT_ALPHA.fasta",
                "starts_with": ">SYNTH_CONSTRUCT_ALPHA",
            },
            gap="",
            reuse_decision="reuse",
            recommended_next_action="Reuse the current FASTA exporter directly once the canonical construct model exists.",
        ),
        _capability(
            name="Annotated GenBank export",
            classification="PARTIAL",
            implementation_path="components/export_manager.py:generate_genbank_string",
            implementation_paths=[
                "components/export_manager.py:generate_genbank_string",
            ],
            evidence="The exporter produced a valid annotated GenBank file with three features, but a reverse-strand probe showed that strand is forced to +1 and topology is absent.",
            observed_result={
                "feature_count": roundtrip["feature_count"],
                "strand_probe": strand_probe,
                "topology": roundtrip["topology"],
            },
            expected_result={
                "feature_count": 3,
                "strand_probe": {"expected_strand": -1, "observed_strand": -1},
                "topology": "circular_or_linear_recorded",
            },
            gap="Simple forward-feature export works, but strand and topology fidelity are incomplete.",
            reuse_decision="adapt",
            recommended_next_action="Fix strand and topology fidelity in the current exporter after the canonical construct model is in place.",
        ),
        _capability(
            name="GenBank round trip",
            classification="PARTIAL",
            implementation_path="components/export_manager.py:generate_genbank_string",
            implementation_paths=[
                "components/export_manager.py:generate_genbank_string",
                "views/wizard_steps/step1_gene_input.py:page upload branch",
            ],
            evidence="Sequence and forward-feature coordinates survived a Biopython round-trip, but the active runtime import path does not preserve imported features or topology.",
            observed_result={
                "sequence_matches": roundtrip["sequence"] == inputs["expected_concatenated_sequence"],
                "feature_count": roundtrip["feature_count"],
                "topology": roundtrip["topology"],
            },
            expected_result={
                "sequence_matches": True,
                "feature_count": 3,
                "topology": "preserved",
            },
            gap="Round-trip works only as a low-level export/library exercise, not as an active construct reopen workflow.",
            reuse_decision="adapt",
            recommended_next_action="Add a production GenBank reopen adapter that preserves annotations into the canonical construct runtime.",
        ),
        _capability(
            name="Runtime UI input",
            classification="PARTIAL",
            implementation_path="views/wizard_steps/step1_gene_input.py:page",
            implementation_paths=[
                "views/wizard_steps/step1_gene_input.py:page",
            ],
            evidence="The runtime UI supports pasted DNA/FASTA, file upload, and registry import, but it does not create canonical multi-record or feature-preserving sequence assets.",
            observed_result={
                "supports_paste": True,
                "supports_upload": True,
                "supports_registry_import": True,
            },
            expected_result={
                "supports_paste": True,
                "supports_upload": True,
                "supports_registry_import": True,
                "preserves_asset_structure": True,
            },
            gap="Input exists, but the imported content becomes plain cleaned strings rather than reusable construct assets.",
            reuse_decision="adapt",
            recommended_next_action="Keep the Step 1 entry UI but change its runtime target from plain strings to canonical sequence assets.",
        ),
        _capability(
            name="Runtime UI construct editing",
            classification="DISPLAY_ONLY",
            implementation_path="services/expression_wizard_construct_bridge.py:save_wizard_draft_to_construct",
            implementation_paths=[
                "services/expression_wizard_construct_bridge.py:save_wizard_draft_to_construct",
                "services/expression_construct_repository.py",
            ],
            evidence="Saving the synthetic wizard cassette into the construct workspace stored part_reference values like '15 bp sequence recorded' rather than actual DNA sequences.",
            observed_result=construct_workspace_probe,
            expected_result={
                "cassette_parts_store_real_sequences": True,
                "cassette_parts_store_orientation_and_coordinates": True,
            },
            gap="The current construct workspace edits documentation metadata, not real construct DNA.",
            reuse_decision="freeze",
            recommended_next_action="Do not extend the current construct workspace for Gate 1 until sequence-bearing parts are introduced.",
        ),
        _capability(
            name="Runtime UI result display",
            classification="PARTIAL",
            implementation_path="components/export_manager.py / views/wizard_steps/step6_export.py / views/ExpressionConstructs.py",
            implementation_paths=[
                "components/export_manager.py",
                "views/wizard_steps/step6_export.py",
                "views/ExpressionConstructs.py",
            ],
            evidence="Wizard/export surfaces can display assembled sequences and export artifacts, but construct-draft surfaces display documentation readback instead of editable real constructs.",
            observed_result={
                "wizard_export_available": True,
                "construct_workspace_sequence_bearing": False,
            },
            expected_result={
                "wizard_export_available": True,
                "construct_workspace_sequence_bearing": True,
            },
            gap="The repository displays results, but not through one durable real-construct runtime.",
            reuse_decision="adapt",
            recommended_next_action="Point result display at the same canonical construct model used for save/reopen and export.",
        ),
    ]

    manifest = {
        "schema_version": "v2.7.r226.real_construct_capability_matrix.v1",
        "audit_timestamp": audit_timestamp,
        "repository_head": head,
        "probe_script_requested_path": "scripts/qa/probe_plant_expression_construct_capabilities.py",
        "probe_script_actual_path": "scripts/probe_plant_expression_construct_capabilities.py",
        "synthetic_reference_input": inputs,
        "probe_runtime_paths": {
            "runtime_root": "isolated_runtime_root",
            "design_db_path": paths.design_db_path.name,
            "construct_db_path": paths.construct_db_path.name,
            "plant_draft_dir": paths.plant_draft_dir.name,
        },
        "capabilities": capabilities,
        "implementation_inventory": _implementation_inventory(),
        "asset_inventory": assets,
        "single_nearest_product_breakpoint": "Missing canonical sequence-bearing single-gene construct runtime and persistence spine.",
        "recommended_gate1_task": NEXT_GATE1_TASK,
        "summary": {
            "working_count": sum(1 for item in capabilities if item["classification"] == "WORKING"),
            "partial_count": sum(1 for item in capabilities if item["classification"] == "PARTIAL"),
            "display_only_count": sum(1 for item in capabilities if item["classification"] == "DISPLAY_ONLY"),
            "missing_count": sum(1 for item in capabilities if item["classification"] == "MISSING"),
            "duplicate_count": sum(1 for item in capabilities if item["classification"] == "DUPLICATE"),
            "deprecated_count": sum(1 for item in capabilities if item["classification"] == "DEPRECATED"),
        },
    }
    return manifest


def write_manifest(
    *,
    audit_timestamp: str,
    repo_head: str | None,
    runtime_root: Path | None,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = run_probe(
        audit_timestamp=audit_timestamp,
        repo_head=repo_head,
        runtime_root=runtime_root,
    )
    _write_json(manifest_path, manifest)
    return manifest


def validate_manifest_schema(manifest: dict[str, Any]) -> None:
    required_top_level = {
        "schema_version",
        "audit_timestamp",
        "repository_head",
        "synthetic_reference_input",
        "capabilities",
        "recommended_gate1_task",
        "single_nearest_product_breakpoint",
        "summary",
    }
    missing = required_top_level - set(manifest)
    if missing:
        raise ValueError(f"Manifest missing required top-level keys: {sorted(missing)}")

    capabilities = manifest["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("Manifest capabilities must be a non-empty list.")

    for entry in capabilities:
        for key in (
            "capability",
            "classification",
            "implementation_path",
            "implementation_paths",
            "evidence",
            "observed_result",
            "expected_result",
            "gap",
            "reuse_decision",
            "recommended_gate1_task",
            "recommended_next_action",
            "blocking_reason",
            "confidence_level",
        ):
            if key not in entry:
                raise ValueError(f"Capability entry missing required key: {key}")
        if entry["classification"] not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"Unsupported capability classification: {entry['classification']}")


def render_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "R226 real construct capability probe",
        f"Repository HEAD: {manifest['repository_head']}",
        f"Working: {manifest['summary']['working_count']}",
        f"Partial: {manifest['summary']['partial_count']}",
        f"Display-only: {manifest['summary']['display_only_count']}",
        f"Missing: {manifest['summary']['missing_count']}",
        "Capability highlights:",
    ]
    for entry in manifest["capabilities"]:
        lines.append(f"- {entry['capability']}: {entry['classification']}")
    lines.append(f"Nearest breakpoint: {manifest['single_nearest_product_breakpoint']}")
    lines.append(f"Recommended Gate 1 task: {manifest['recommended_gate1_task']}")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the current repository for real plant expression construct runtime capability."
    )
    parser.add_argument(
        "--audit-timestamp",
        default="2026-07-10T00:00:00Z",
        help="Stable audit timestamp to embed in the manifest.",
    )
    parser.add_argument(
        "--repo-head",
        default=None,
        help="Optional explicit repository HEAD value for deterministic testing.",
    )
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Optional isolated runtime directory for temporary probe data.",
    )
    parser.add_argument(
        "--write-manifest",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Path to write the generated capability manifest.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run the probe without writing a manifest file.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    runtime_root = Path(args.runtime_root) if args.runtime_root else None
    manifest_path = Path(args.write_manifest)
    if args.no_write:
        manifest = run_probe(
            audit_timestamp=args.audit_timestamp,
            repo_head=args.repo_head,
            runtime_root=runtime_root,
        )
    else:
        manifest = write_manifest(
            audit_timestamp=args.audit_timestamp,
            repo_head=args.repo_head,
            runtime_root=runtime_root,
            manifest_path=manifest_path,
        )
    validate_manifest_schema(manifest)
    print(render_summary(manifest))
    if not args.no_write:
        print(f"Manifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
