"""Immutable-source GenBank asset adapter for reviewed plant vector records.

This adapter deliberately sits beside the generic construct parser.  It preserves
the downloaded record bytes as the provenance source and emits a loss-aware
feature audit for review; it never chooses a T-DNA replacement region.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from core.config import ensure_biodesign_runtime_dir
from core.pbi121_replacement_contract import validate_pbi121_source

from Bio import SeqIO


PBI121_ACCESSION = "AF485783.1"
PBI121_RECORD_NAME = "pBI121"
PBI121_EXPECTED_LENGTH = 14758
PBI121_ROOT = Path(__file__).resolve().parents[1] / "data" / "real_assets" / "pbi121"
PBI121_SOURCE_RECORD = PBI121_ROOT / "source_records" / "AF485783.1.gb"
PBI121_EXTRACTED_FEATURES = PBI121_ROOT / "extracted_assets" / "feature_audit.json"
PBI121_MANIFEST = PBI121_ROOT / "provenance" / "source_manifest.json"
PBI121_VERIFICATION = PBI121_ROOT / "verification" / "asset_verification.json"
PBI121_STATE_NAME = "pbi121_library_state.json"


class RealGenBankAssetError(ValueError):
    """Raised when a real GenBank asset cannot be preserved and audited."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _qualifiers(feature: Any) -> dict[str, list[str]]:
    return {
        str(key): [str(item) for item in values]
        for key, values in dict(feature.qualifiers or {}).items()
    }


def _location_parts(location: Any) -> list[dict[str, Any]]:
    parts = list(getattr(location, "parts", None) or [location])
    return [
        {
            "start_zero_based": int(part.start),
            "end_zero_based_exclusive": int(part.end),
            "start_one_based": int(part.start) + 1,
            "end_one_based_inclusive": int(part.end),
            "strand": int(part.strand) if part.strand in {-1, 1} else None,
        }
        for part in parts
    ]


def _feature_name(feature_type: str, qualifiers: dict[str, list[str]], ordinal: int) -> str:
    for key in ("label", "gene", "product", "note"):
        values = qualifiers.get(key) or []
        if values:
            return values[0]
    return f"{feature_type}_{ordinal}"


def _record_name(record: Any) -> str:
    """Use the declared pBI121 record name rather than Biopython's locus token."""
    description = str(record.description)
    match = re.search(r"Binary vector\s+([^,]+)", description, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return str(record.name) or str(record.id)


def _classify_feature(feature: dict[str, Any]) -> tuple[str, str, bool, str]:
    """Classify only explicitly annotated records; everything else stays other_feature."""
    feature_type = str(feature["type"])
    qualifiers = feature["qualifiers"]
    note = " ".join(qualifiers.get("note") or []).casefold()
    regulatory_class = " ".join(qualifiers.get("regulatory_class") or []).casefold()
    gene = " ".join(qualifiers.get("gene") or []).casefold()

    if feature_type == "regulatory" and regulatory_class == "promoter" and "camv 35s" in note:
        return "promoter", "CaMV 35S promoter", True, "feature_table_regulatory_class_and_note"
    if feature_type == "regulatory" and regulatory_class == "terminator" and note == "nos":
        return "three_prime_regulatory_region", "NOS 3' regulatory region", True, "feature_table_regulatory_class_and_note"
    if feature_type == "misc_feature" and "t-dna left border" in note:
        return "left_border", "T-DNA left border", True, "explicit_feature_note"
    if feature_type == "misc_feature" and "t-dna right border" in note:
        return "right_border", "T-DNA right border", True, "explicit_feature_note"
    if feature_type == "CDS" and gene == "nptii":
        return "selectable_marker_cassette", "nptII selectable marker CDS", True, "feature_table_gene"
    if feature_type == "CDS" and gene == "gusa":
        return "reporter_cassette", "gusA reporter CDS", True, "feature_table_gene"
    return "other_feature", "", False, "not_reliably_classified"


def parse_genbank_bytes(raw_bytes: bytes) -> dict[str, Any]:
    """Parse one record while retaining its raw byte checksum and exact locations."""
    if not raw_bytes:
        raise RealGenBankAssetError("The GenBank source record is empty.")
    try:
        records = list(SeqIO.parse(StringIO(raw_bytes.decode("utf-8-sig")), "genbank"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RealGenBankAssetError("The source bytes are not a readable UTF-8 GenBank record.") from exc
    if len(records) != 1:
        raise RealGenBankAssetError("Real asset intake requires exactly one GenBank record.")

    record = records[0]
    record_identifier = str(record.id) or str(record.name) or "unidentified-record"
    sequence = str(record.seq).upper()
    features: list[dict[str, Any]] = []
    for ordinal, source_feature in enumerate(record.features, start=1):
        qualifiers = _qualifiers(source_feature)
        location = source_feature.location
        parts = _location_parts(location)
        strand_values = {part["strand"] for part in parts}
        feature = {
            "feature_id": f"{record_identifier}:feature:{ordinal:03d}",
            "ordinal": ordinal,
            "type": str(source_feature.type),
            "name": _feature_name(str(source_feature.type), qualifiers, ordinal),
            "location_expression": str(location),
            "location_operator": str(getattr(location, "operator", "") or "single"),
            "location_parts": parts,
            "start_zero_based": min(part["start_zero_based"] for part in parts),
            "end_zero_based_exclusive": max(part["end_zero_based_exclusive"] for part in parts),
            "start_one_based": min(part["start_one_based"] for part in parts),
            "end_one_based_inclusive": max(part["end_one_based_inclusive"] for part in parts),
            "strand": int(location.strand) if location.strand in {-1, 1} else None,
            "mixed_strand": len(strand_values) > 1,
            "crosses_origin": len(parts) > 1 and parts[0]["start_zero_based"] > parts[-1]["start_zero_based"],
            "qualifiers": qualifiers,
            "sequence_sha256": _sha256(bytes(source_feature.extract(record.seq)).upper()),
            "length": len(source_feature.extract(record.seq)),
        }
        asset_type, biological_role, registerable, extraction_method = _classify_feature(feature)
        feature.update(
            {
                "asset_type": asset_type,
                "biological_role": biological_role,
                "registerable_component": registerable,
                "extraction_method": extraction_method,
                "provenance_status": "verified_source" if registerable else "needs_feature_review",
                "verification_status": "source_feature_parsed",
                "manual_review_notes": "" if registerable else "Feature retained as other_feature; no biological role was inferred.",
            }
        )
        features.append(feature)

    accession = str(record.id)
    return {
        "accession": accession,
        "record_name": _record_name(record),
        "description": str(record.description),
        "topology": str(record.annotations.get("topology") or "").lower(),
        "length": len(sequence),
        "sequence": sequence,
        "sequence_sha256": _sha256(sequence.encode("ascii")),
        "source_record_sha256": _sha256(raw_bytes),
        "features": features,
    }


def load_pbi121_audit() -> dict[str, Any]:
    return parse_genbank_bytes(PBI121_SOURCE_RECORD.read_bytes())


def build_pbi121_asset_bundle() -> dict[str, Any]:
    audit = load_pbi121_audit()
    if audit["accession"] != PBI121_ACCESSION or audit["length"] != PBI121_EXPECTED_LENGTH:
        raise RealGenBankAssetError("The bundled source record is not AF485783.1 pBI121 at 14758 bp.")
    if audit["topology"] != "circular":
        raise RealGenBankAssetError("The bundled source record is not circular.")
    try:
        contract = validate_pbi121_source(audit["sequence"], accession_version=audit["accession"])
    except ValueError as exc:
        raise RealGenBankAssetError(str(exc)) from exc

    extracted = []
    for feature in audit["features"]:
        if not feature["registerable_component"]:
            continue
        extracted.append(
            {
                "asset_id": f"pbi121::{feature['feature_id'].rsplit(':', 1)[-1]}",
                "name": feature["biological_role"],
                "biological_role": feature["biological_role"],
                "asset_type": feature["asset_type"],
                "exact_sequence": "",
                "length": feature["length"],
                "topology": "linear_feature",
                "strand": feature["strand"],
                "source_type": "official_ncbi_genbank",
                "source_accession": audit["accession"],
                "source_record_name": audit["record_name"],
                "source_feature_type": feature["type"],
                "source_feature_location": feature["location_expression"],
                "source_feature_qualifiers": deepcopy(feature["qualifiers"]),
                "source_record_sha256": audit["source_record_sha256"],
                "sequence_sha256": feature["sequence_sha256"],
                "extraction_method": feature["extraction_method"],
                "user_edit_status": "source_immutable",
                "provenance_status": feature["provenance_status"],
                "verification_status": feature["verification_status"],
                "manual_review_notes": feature["manual_review_notes"],
                "source_version": audit["accession"],
            }
        )
    # SeqFeature.extract preserves compound joins, reverse strands, and origin-spanning locations.
    record = next(SeqIO.parse(StringIO(PBI121_SOURCE_RECORD.read_text(encoding="ascii")), "genbank"))
    by_id = {feature["feature_id"]: raw for feature, raw in zip(audit["features"], record.features)}
    for asset, feature in zip(extracted, [row for row in audit["features"] if row["registerable_component"]]):
        asset["exact_sequence"] = str(by_id[feature["feature_id"]].extract(record.seq)).upper()

    vector = {
        "asset_id": "pbi121::complete_binary_vector",
        "name": "pBI121",
        "biological_role": "complete pBI121 binary-vector exact-replacement source",
        "asset_type": "complete_binary_vector",
        "asset_kind": "tDNA_replacement_source",
        "exact_sequence": audit["sequence"],
        "length": audit["length"],
        "topology": audit["topology"],
        "strand": None,
        "source_type": "official_ncbi_genbank",
        "source_accession": audit["accession"],
        "source_record_name": audit["record_name"],
        "source_feature_type": "source_record",
        "source_feature_location": f"1..{audit['length']}",
        "source_feature_qualifiers": {},
        "source_record_sha256": audit["source_record_sha256"],
        "sequence_sha256": audit["sequence_sha256"],
        "extraction_method": "complete_record_sequence",
        "user_edit_status": "source_immutable",
        "provenance_status": "verified_source",
        "verification_status": "exact_replacement_contract_verified",
        "manual_review_notes": contract["warning_text"],
        "source_version": audit["accession"],
        "non_empty_t_dna": True,
        "requires_exact_replacement": True,
        "direct_insert_allowed": False,
        "reference_access": True,
        "eligible_for_construct_use": True,
        "replaceable_region": {
            "start": contract["replacement_start"],
            "end": contract["replacement_end"],
            "coordinate_system": contract["coordinate_system"],
        },
        "replacement_contract": contract,
    }
    return {"vector": vector, "components": extracted, "audit": audit}


def expected_asset_files() -> tuple[Path, Path, Path]:
    return PBI121_EXTRACTED_FEATURES, PBI121_MANIFEST, PBI121_VERIFICATION


def write_pbi121_reference_assets() -> dict[str, Any]:
    """Generate derived JSON without modifying the immutable source record."""
    bundle = build_pbi121_asset_bundle()
    audit = bundle["audit"]
    for path in expected_asset_files():
        path.parent.mkdir(parents=True, exist_ok=True)
    extracted_payload = {
        "record_audit": audit,
        "complete_binary_vector": bundle["vector"],
        "registered_components": bundle["components"],
        "unclassified_features": [
            row for row in audit["features"] if not row["registerable_component"]
        ],
    }
    PBI121_EXTRACTED_FEATURES.write_text(json.dumps(extracted_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "asset_family": "pBI121_real_genbank_asset",
        "source": {"provider": "NCBI Nucleotide", "accession": audit["accession"], "record_name": audit["record_name"], "file": str(PBI121_SOURCE_RECORD.relative_to(PBI121_ROOT)).replace("\\", "/"), "sha256": audit["source_record_sha256"]},
        "preservation": "source_records/AF485783.1.gb is preserved byte-for-byte as downloaded.",
        "generated_at": "source-version AF485783.1",
    }
    PBI121_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verification = {
        "accession": audit["accession"], "record_name": audit["record_name"], "topology": audit["topology"], "length": audit["length"], "source_record_sha256": audit["source_record_sha256"],
        "feature_count": len(audit["features"]), "feature_types": sorted({row["type"] for row in audit["features"]}),
        "registered_component_count": len(bundle["components"]), "complete_binary_vector": {key: bundle["vector"][key] for key in ("asset_type", "asset_kind", "topology", "length", "provenance_status", "verification_status", "non_empty_t_dna", "requires_exact_replacement", "direct_insert_allowed", "reference_access", "eligible_for_construct_use")},
    }
    PBI121_VERIFICATION.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bundle


def default_library_state() -> dict[str, Any]:
    bundle = build_pbi121_asset_bundle()
    return {
        "schema_version": "pbi121-library-state-v1",
        "source_accession": PBI121_ACCESSION,
        "source_record_sha256": bundle["audit"]["source_record_sha256"],
        "asset_saved": False,
        "left_border_confirmed": False,
        "right_border_confirmed": False,
        "t_dna_direction_confirmation": "",
        "saved_at": "",
    }


def _state_path(runtime_root: Path | None = None) -> Path:
    root = runtime_root or ensure_biodesign_runtime_dir()
    return root / PBI121_STATE_NAME


def load_library_state(runtime_root: Path | None = None) -> dict[str, Any]:
    path = _state_path(runtime_root)
    default = default_library_state()
    if not path.exists():
        return default
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RealGenBankAssetError("The saved pBI121 library state cannot be read.") from exc
    if stored.get("source_record_sha256") != default["source_record_sha256"]:
        raise RealGenBankAssetError("The saved pBI121 state does not match the immutable source record.")
    return {**default, **{key: stored[key] for key in default if key in stored}}


def save_library_state(
    *,
    left_border_confirmed: bool,
    right_border_confirmed: bool,
    t_dna_direction_confirmation: str,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    if t_dna_direction_confirmation not in {"", "LB_to_RB", "RB_to_LB"}:
        raise RealGenBankAssetError("T-DNA direction confirmation must be LB_to_RB, RB_to_LB, or empty.")
    state = default_library_state()
    state.update({
        "asset_saved": True,
        "left_border_confirmed": bool(left_border_confirmed),
        "right_border_confirmed": bool(right_border_confirmed),
        "t_dna_direction_confirmation": t_dna_direction_confirmation,
        "saved_at": _utc_now(),
    })
    path = _state_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state
