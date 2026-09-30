"""Official-source rice HSA/ALB construct case and authenticity gate."""
from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path
import re
from typing import Any

from Bio import SeqIO
from Bio.SeqFeature import CompoundLocation
from core.pcambia1300_exact_insertion_contract import (
    exact_insertion_contract,
    fixed_insertion_settings,
)


CASE_RAW_DIR = Path(__file__).resolve().parents[1] / "case_inputs" / "rice_hsa" / "raw"
ALB_GENBANK = CASE_RAW_DIR / "NM_000477.7.gb"
ALB_FASTA = CASE_RAW_DIR / "NM_000477.7.fasta"
BACKBONE_GENBANK = CASE_RAW_DIR / "AF234296.1.gb"
BACKBONE_FASTA = CASE_RAW_DIR / "AF234296.1.fasta"


class RiceHsaNcbiCaseError(ValueError):
    """Raised when the local NCBI case inputs fail deterministic validation."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_record(path: Path, fmt: str):
    try:
        return SeqIO.read(path, fmt)
    except Exception as exc:  # pragma: no cover - defensive wrapper for clearer tests
        raise RiceHsaNcbiCaseError(f"Unable to parse {path.name} as {fmt}.") from exc


def _location_text(feature: Any) -> str:
    location = feature.location
    if isinstance(location, CompoundLocation):
        parts = []
        for part in location.parts:
            start = int(part.start) + 1
            end = int(part.end)
            text = f"{start}..{end}"
            parts.append(f"complement({text})" if int(part.strand or 1) == -1 else text)
        joined = ",".join(parts)
        return f"{location.operator}({joined})"
    start = int(location.start) + 1
    end = int(location.end)
    text = f"{start}..{end}"
    return f"complement({text})" if int(location.strand or 1) == -1 else text


def _feature_label(feature: Any) -> str:
    qualifiers = feature.qualifiers
    for key in ("label", "note", "product", "regulatory_class"):
        values = qualifiers.get(key)
        if values:
            return str(values[0])
    return feature.type


REAL_CASE_PROJECT_NAME = "水稻表达人血清白蛋白（HSA/ALB）真实数据案例"
REAL_CASE_STATUS = "精确插入合同已应用｜仍需专业审查"
INCOMPLETE_REAL_CASE_NAME = REAL_CASE_STATUS
DEMO_PROJECT_NAME = "水稻 ALB 演示项目"
DEMO_BOUNDARY_NOTE = "仅用于软件功能和交付格式测试，不可用于正式构建。"
REAL_CASE_BOUNDARY_NOTE = (
    "该结果属于计算机辅助设计，不代表已经完成湿实验验证，"
    "不保证人血清白蛋白能够在水稻中成功、稳定或高水平表达。"
)
EXPECTED_FILE_SHA256 = {
    "NM_000477.7.gb": "759e73aede380efa713a55f7b1a60302e3c6ac00282a5ecf766af6d12e58c788",
    "NM_000477.7.fasta": "89799dbacaac16d0e873a5fd4b99e041f081f7bdc4415b843ce70bf8e4a54079",
    "AF234296.1.gb": "7fbadcf1bb92d69d38a553bcfaedf4f12349706c4db5fb0f508f2e2c831c9d95",
    "AF234296.1.fasta": "fdb3a8bbc8b34fa3935f68a0c32e24d61ab50d114cbea176457fb3a828f5fc44",
}
EXPECTED_SEQUENCE_SHA256 = {
    "alb_mrna": "7f056d548bc32f8ab89a70aa6e4a032fe96a0cbf62ec23016c39dec6c9d50491",
    "cds": "9ddcd40a33c631ae5de17aa79bf91938d4841968030f8928fa0cbb415b4f541a",
    "backbone": "83c7d28d071a9ff167dbe78817b2b20a5e285dcc6e1637e7392adb9f7be89de6",
    "promoter": "c1e6f43ff881497688661df8a9b76b66ca04f315248442666a128a1241d02a6a",
    "terminator": "f55fad52922a7f47baf2c912b1741847266f06fde06eeb5f88129ccaf2315d0d",
}
REAL_CASE_INSERTION = {
    **fixed_insertion_settings(),
    "workflow_id": "rice_alb_single_gene",
}
_FORBIDDEN_REAL_ASSET_RE = re.compile(r"synthetic|demo|placeholder|(?:^|[_-])r\d{2,}(?:[_-]|$)", re.IGNORECASE)

def _sequence_sha256(value: Any) -> str:
    return hashlib.sha256(str(value).upper().encode("ascii")).hexdigest()

def _official_feature_row(feature: Any) -> dict[str, Any]:
    parts = [{"start": int(part.start) + 1, "end": int(part.end), "strand": int(part.strand or feature.location.strand or 1)} for part in list(getattr(feature.location, "parts", None) or [feature.location])]
    return {"type": str(feature.type), "location": _location_text(feature), "strand": int(feature.location.strand or 1), "label": _feature_label(feature), "parts": parts, "qualifiers": {str(k): [str(v) for v in vals] for k, vals in dict(feature.qualifiers or {}).items()}}

def _one_feature(record: Any, predicate, label: str):
    matches = [feature for feature in record.features if predicate(feature)]
    if len(matches) != 1:
        raise RiceHsaNcbiCaseError(f"Expected exactly one {label} feature; found {len(matches)}.")
    return matches[0]

def _official_asset(*, role: str, record: Any, feature: Any | None, path: Path, rationale: str) -> dict[str, Any]:
    sequence = str(feature.extract(record.seq) if feature is not None else record.seq).upper()
    return {"role": role, "accession_version": str(record.id), "record_name": str(record.name), "definition": str(record.description), "record_length": len(record.seq), "used_location": _location_text(feature) if feature is not None else f"1..{len(record.seq)}", "strand": int(feature.location.strand or 1) if feature is not None else 1, "used_length": len(sequence), "sequence": sequence, "sequence_sha256": _sequence_sha256(sequence), "raw_file": path.name, "raw_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "feature_type": str(feature.type) if feature is not None else "source_record", "qualifiers": {str(k): [str(v) for v in vals] for k, vals in dict(feature.qualifiers or {}).items()} if feature is not None else {}, "rationale": rationale}

def load_rice_hsa_ncbi_case() -> dict[str, Any]:
    """Load and validate the official records and all four used assets."""
    alb_gb, alb_fasta = _read_record(ALB_GENBANK, "genbank"), _read_record(ALB_FASTA, "fasta")
    backbone_gb, backbone_fasta = _read_record(BACKBONE_GENBANK, "genbank"), _read_record(BACKBONE_FASTA, "fasta")
    for path in (ALB_GENBANK, ALB_FASTA, BACKBONE_GENBANK, BACKBONE_FASTA):
        if _sha256_file(path) != EXPECTED_FILE_SHA256[path.name]:
            raise RiceHsaNcbiCaseError(f"Official snapshot checksum mismatch: {path.name}.")
    if str(alb_gb.seq).upper() != str(alb_fasta.seq).upper() or str(backbone_gb.seq).upper() != str(backbone_fasta.seq).upper():
        raise RiceHsaNcbiCaseError("Official FASTA and GenBank sequences differ.")
    if str(alb_gb.id) != "NM_000477.7" or len(alb_gb.seq) != 2285 or str(backbone_gb.id) != "AF234296.1" or len(backbone_gb.seq) != 8958:
        raise RiceHsaNcbiCaseError("Unexpected official accession or record length.")
    if str(backbone_gb.annotations.get("topology") or "").lower() != "circular":
        raise RiceHsaNcbiCaseError("AF234296.1 is not annotated as circular.")
    cds = _one_feature(alb_gb, lambda f: f.type == "CDS" and "albumin" in " ".join(f.qualifiers.get("product", [])).lower(), "ALB CDS")
    promoter = _one_feature(backbone_gb, lambda f: f.type == "regulatory" and f.qualifiers.get("regulatory_class") == ["promoter"] and "camv35s" in " ".join(f.qualifiers.get("note", [])).lower(), "CaMV35S promoter")
    terminator = _one_feature(backbone_gb, lambda f: f.type == "misc_feature" and "polya signal" in " ".join(f.qualifiers.get("note", [])).lower(), "CaMV 3'UTR/polyA signal")
    cds_sequence, translation = str(cds.extract(alb_gb.seq)).upper(), str((cds.qualifiers.get("translation") or [""])[0])
    if _location_text(cds) != "42..1871" or len(cds_sequence) != 1830 or not cds_sequence.startswith("ATG") or not cds_sequence.endswith(("TAA", "TAG", "TGA")) or str(cds.extract(alb_gb.seq).translate(cds=True)) != translation or len(translation) != 609:
        raise RiceHsaNcbiCaseError("ALB CDS coordinates, codons, or translation are invalid.")
    assets = {
        "cds": _official_asset(role="cds", record=alb_gb, feature=cds, path=ALB_GENBANK, rationale="The official NM_000477.7 CDS feature identifies the ALB coding sequence."),
        "promoter": _official_asset(role="promoter", record=backbone_gb, feature=promoter, path=BACKBONE_GENBANK, rationale="The AF234296.1 regulatory feature is explicitly qualified as promoter / CaMV35S."),
        "terminator": _official_asset(role="terminator", record=backbone_gb, feature=terminator, path=BACKBONE_GENBANK, rationale="The AF234296.1 feature note identifies a CaMV 3'UTR polyadenylation signal; it is recorded as the transcription-termination region for this documentation case."),
        "backbone": _official_asset(role="backbone", record=backbone_gb, feature=None, path=BACKBONE_GENBANK, rationale="The complete AF234296.1 circular record is the pCAMBIA-1300 backbone snapshot."),
    }
    observed = {role: asset["sequence_sha256"] for role, asset in assets.items()}
    observed["alb_mrna"] = _sequence_sha256(alb_gb.seq)
    if observed != EXPECTED_SEQUENCE_SHA256:
        raise RiceHsaNcbiCaseError("Official sequence checksum mismatch.")
    lacz = _one_feature(backbone_gb, lambda f: f.type == "CDS" and "lacz alpha" in " ".join(f.qualifiers.get("product", [])).lower(), "LacZ alpha")
    mcs = _one_feature(backbone_gb, lambda f: f.type == "misc_feature" and "polylinker" in " ".join(f.qualifiers.get("note", [])).lower(), "pUC18 MCS")
    contract = exact_insertion_contract()
    return {
        "case_id": "rice_hsa_official_public_data",
        "project_name": REAL_CASE_PROJECT_NAME,
        "assets": assets,
        "alb": {
            **assets["cds"],
            "mrna_length": len(alb_gb.seq),
            "mrna_sha256": _sequence_sha256(alb_gb.seq),
            "start_codon": cds_sequence[:3],
            "stop_codon": cds_sequence[-3:],
            "translation_length": len(translation),
            "translation_sha256": _sequence_sha256(translation),
        },
        "backbone": {
            **assets["backbone"],
            "display_name": "pCAMBIA-1300",
            "asset_id": contract["asset_id"],
            "asset_kind": contract["asset_kind"],
            "requires_exact_insertion": True,
            "topology": "circular",
            "features": [_official_feature_row(f) for f in backbone_gb.features],
        },
        "insertion": {
            **REAL_CASE_INSERTION,
            "orientation": "forward",
            "coordinate_convention": "1-based adjacent cut boundary; normalized to 0-based insertion index 27",
            "exact_cut_external": "27|28",
            "exact_cut_internal": 27,
            "source_feature": _official_feature_row(mcs),
            "disrupted_feature": _official_feature_row(lacz),
            "overlap_expected": True,
            "selection_basis": "Immutable exact-insertion contract for the XbaI site at 27..32 within the official pUC18 MCS annotation.",
            "manual_review": "Professional review remains required; the insertion coordinate is not user-editable.",
        },
        "raw_file_sha256": dict(EXPECTED_FILE_SHA256),
        "boundary_note": REAL_CASE_BOUNDARY_NOTE,
    }


def _provenance_fields(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_reference": asset["accession_version"],
        "source_accession_version": asset["accession_version"],
        "source_record_name": asset["record_name"],
        "source_definition": asset["definition"],
        "source_location": asset["used_location"],
        "source_strand": asset["strand"],
        "source_record_length": asset["record_length"],
        "source_file_name": asset["raw_file"],
        "source_file_sha256": asset["raw_file_sha256"],
        "extracted_sequence_sha256": asset["sequence_sha256"],
        "source_feature_type": asset["feature_type"],
        "source_feature_qualifiers": asset["qualifiers"],
        "source_rationale": asset["rationale"],
    }


def build_rice_hsa_real_input_records(project_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build runtime records directly from the official snapshot."""
    from services.mvp_cds_input import analyze_cds_input
    from services.mvp_sequence_input import analyze_dna_component_input, analyze_genbank_backbone_input

    case = load_rice_hsa_ncbi_case()
    assets = case["assets"]
    cds_input = analyze_cds_input(assets["cds"]["sequence"], source_kind="library", source_name="NM_000477.7")
    if cds_input.get("blocking"):
        raise RiceHsaNcbiCaseError("Official ALB CDS did not pass the existing CDS input checks.")
    records = {
        "promoter": analyze_dna_component_input(assets["promoter"]["sequence"], project_id=project_id, component_type="promoter", display_name="CaMV35S promoter", source_kind="library", source_name="AF234296.1"),
        "cds": {"role": "cds", "source_kind": "library", "source_name": "NM_000477.7", "source_format": str(cds_input.get("source_format") or "plain"), "display_name": "ALB CDS", "original_text": str(cds_input.get("original_text") or ""), "normalized_sequence": str(cds_input.get("normalized_cds") or ""), "length": int(cds_input.get("normalized_length") or 0)},
        "terminator": analyze_dna_component_input(assets["terminator"]["sequence"], project_id=project_id, component_type="terminator", display_name="CaMV 3'UTR (polyA signal)", source_kind="library", source_name="AF234296.1"),
        "backbone": analyze_genbank_backbone_input(BACKBONE_GENBANK.read_text(encoding="utf-8"), project_id=project_id, display_name="pCAMBIA-1300", source_kind="library", source_name="AF234296.1"),
    }
    for role, record in records.items():
        record.update(_provenance_fields(assets[role]))
    records["cds"]["source_mrna_sha256"] = case["alb"]["mrna_sha256"]
    records["cds"]["translation_length"] = case["alb"]["translation_length"]
    return cds_input, records


def build_rice_hsa_real_case(*, project_id: str | None = None) -> dict[str, Any]:
    """Generate the formal case through the existing canonical runtime only."""
    from services.canonical_construct_runtime import export_active_construct
    from services.formal_single_gene_runtime import generate_complete_vector, generation_input_signature
    from services.plant_project_draft_schema import new_project_id

    resolved_project_id = str(project_id or new_project_id())
    cds_input, records = build_rice_hsa_real_input_records(resolved_project_id)
    signature = generation_input_signature(records, REAL_CASE_INSERTION, project_name=REAL_CASE_PROJECT_NAME)
    result = generate_complete_vector(cds_input=cds_input, input_records=records, insertion_settings=dict(REAL_CASE_INSERTION), project_id=resolved_project_id, project_name=REAL_CASE_PROJECT_NAME, input_signature=signature, workflow_id="rice_alb_single_gene")
    result["host"] = "水稻（Oryza sativa）"
    result["cassette_exports"] = export_active_construct(result["runtime"], project_name=REAL_CASE_PROJECT_NAME)
    result["real_case_manifest"] = load_rice_hsa_ncbi_case()
    result["authenticity_gate"] = evaluate_real_case_authenticity(result)
    if not result["authenticity_gate"]["source_verified"]:
        raise RiceHsaNcbiCaseError("Real-case authenticity gate failed: " + "; ".join(result["authenticity_gate"]["missing_items"]))
    return result


def is_real_case_candidate(result: dict[str, Any]) -> bool:
    if str(result.get("project_name") or "") == DEMO_PROJECT_NAME:
        return False
    records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
    accessions = {str((records.get(role) or {}).get("source_accession_version") or (records.get(role) or {}).get("source_name") or "") for role in ("promoter", "cds", "terminator", "backbone")}
    return str(result.get("project_name") or "") == REAL_CASE_PROJECT_NAME or bool({"NM_000477.7", "AF234296.1"} & accessions)


def evaluate_real_case_authenticity(result: dict[str, Any]) -> dict[str, Any]:
    """Verify that UI, save, and export inputs still point to one official snapshot."""
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError, active_complete_plasmid_snapshot, active_construct_snapshot

    missing: list[str] = []
    try:
        case = load_rice_hsa_ncbi_case()
    except RiceHsaNcbiCaseError as exc:
        return {
            "passed": False,
            "source_verified": False,
            "construction_strategy_confirmed": False,
            "status": REAL_CASE_STATUS,
            "missing_items": [str(exc)],
        }
    records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
    if str(result.get("project_name") or "") != REAL_CASE_PROJECT_NAME:
        missing.append("formal project name does not match the locked real-case name")
    for role in ("promoter", "cds", "terminator", "backbone"):
        record = records.get(role) if isinstance(records.get(role), dict) else {}
        expected = case["assets"][role]
        checks = {
            "accession": str(record.get("source_accession_version") or record.get("source_name") or "") == expected["accession_version"],
            "coordinates": str(record.get("source_location") or "") == expected["used_location"],
            "strand": int(record.get("source_strand") or 0) == int(expected["strand"]),
            "source file SHA-256": str(record.get("source_file_sha256") or "") == expected["raw_file_sha256"],
            "sequence SHA-256": str(record.get("extracted_sequence_sha256") or "") == expected["sequence_sha256"],
            "sequence": str(record.get("normalized_sequence") or "").upper() == expected["sequence"],
        }
        for label, passed in checks.items():
            if not passed:
                missing.append(f"{role} {label} is incomplete or inconsistent")
        asset_text = " ".join(str(record.get(key) or "") for key in ("display_name", "source_name", "source_file_name"))
        if _FORBIDDEN_REAL_ASSET_RE.search(asset_text):
            missing.append(f"{role} contains a synthetic/demo/placeholder/R-numbered asset marker")
    cds_record = records.get("cds") if isinstance(records.get("cds"), dict) else {}
    if str(cds_record.get("source_mrna_sha256") or "") != case["alb"]["mrna_sha256"]:
        missing.append("ALB complete mRNA SHA-256 is missing or inconsistent")
    settings = result.get("insertion_settings") if isinstance(result.get("insertion_settings"), dict) else {}
    for key in ("mode", "start_coordinate", "end_coordinate", "expected_removed_sequence", "exact_insertion_contract_version"):
        if settings.get(key) != REAL_CASE_INSERTION[key]:
            missing.append(f"candidate insertion setting {key} is inconsistent")
    try:
        cassette = active_construct_snapshot(result.get("runtime"))
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        missing.append(f"canonical runtime unavailable: {exc}")
        cassette, plasmid = {}, {}
    if cassette:
        expected_cassette = "".join(case["assets"][role]["sequence"] for role in ("promoter", "cds", "terminator"))
        if str(cassette.get("sequence") or "") != expected_cassette:
            missing.append("six-step cassette and canonical runtime sequence differ")
    if plasmid:
        if int(plasmid.get("sequence_length") or 0) != 11778:
            missing.append("final plasmid length is not 11,778 bp")
        if str(plasmid.get("topology") or "").lower() != "circular":
            missing.append("final plasmid is not circular")
        if int((plasmid.get("validation_summary") or {}).get("blocking_count") or 0):
            missing.append("canonical runtime contains blocking findings")
        if any(str(item.get("rule_id") or "") == "overlapping_backbone_feature_conflict" for item in list(plasmid.get("validation_findings") or [])):
            missing.append("exact insertion retained an unresolved backbone feature conflict")
        exports = result.get("exports") if isinstance(result.get("exports"), dict) else {}
        try:
            fasta = SeqIO.read(StringIO(str((exports.get("fasta") or {}).get("data") or "")), "fasta")
            genbank = SeqIO.read(StringIO(str((exports.get("genbank") or {}).get("data") or "")), "genbank")
            runtime_sequence = str(plasmid.get("sequence") or "")
            if str(fasta.seq).upper() != runtime_sequence or str(genbank.seq).upper() != runtime_sequence:
                missing.append("FASTA, GenBank, and canonical runtime sequences differ")
        except Exception:
            missing.append("FASTA or GenBank export cannot be parsed")
    source_verified = not missing
    return {
        "passed": source_verified,
        "source_verified": source_verified,
        "construction_strategy_confirmed": source_verified,
        "status": REAL_CASE_STATUS,
        "missing_items": missing,
        "canonical_sequence_sha256": str(plasmid.get("sequence_checksum") or "") if plasmid else "",
        "fasta_genbank_runtime_consistent": not any("FASTA" in item for item in missing),
    }


def build_rice_hsa_pending_construct_preview() -> dict[str, Any]:
    """Return a read-only official-source preview with the immutable contract."""
    case = load_rice_hsa_ncbi_case()
    return {
        "example_name": REAL_CASE_PROJECT_NAME,
        "labels": ["Documentation-only", "Official public records", "Fixed exact-insertion contract"],
        "pending_decisions": [],
        "alb": {"accession_version": case["alb"]["accession_version"], "cds_location": case["alb"]["used_location"], "cds_length": case["alb"]["used_length"], "translation_length": case["alb"]["translation_length"], "translation_validation": "pass", "translation_note": "ALB CDS translation matches the GenBank qualifier."},
        "backbone": {"accession_version": case["backbone"]["accession_version"], "asset_kind": "exact_insertion_source", "record_length": case["backbone"]["record_length"], "topology": case["backbone"]["topology"], "source_note": "AF234296.1 official GenBank/FASTA snapshot", "candidate_mcs_location": "28..78", "candidate_mcs_label": "pUC18 MCS; polylinker", "exact_insertion_boundary": "27|28", "internal_cut_index": 27},
        "boundary_note": REAL_CASE_BOUNDARY_NOTE,
        "locked_actions": ["The reviewed exact-insertion contract is applied without a user-editable coordinate.", "No codon optimization is applied.", "No experimental validation claim is made."],
    }
