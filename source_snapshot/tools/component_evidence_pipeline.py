"""Deterministic, offline GenBank component-evidence processing CLI."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from utils.sequence_utils import reverse_complement
except ModuleNotFoundError:  # direct ``python tools/...`` invocation
    _RC = str.maketrans("ATCGatcg", "TAGCtagc")
    def reverse_complement(seq: str) -> str:
        return seq.upper().translate(_RC)[::-1]


class EvidenceError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_location_args(text: str) -> list[str]:
    depth = 0
    start = 0
    result: list[str] = []
    for index, char in enumerate(text):
        if char == "(": depth += 1
        elif char == ")": depth -= 1
        elif char == "," and depth == 0:
            result.append(text[start:index]); start = index + 1
        if depth < 0: raise EvidenceError("Malformed feature location")
    if depth: raise EvidenceError("Malformed feature location")
    result.append(text[start:])
    return result


def _parse_location(expr: str, sequence_length: int, topology: str | None = None) -> tuple[list[tuple[int, int, int, bool]], int | None]:
    text = expr.strip().replace(" ", "")
    if not text or "<" in text or ">" in text:
        raise EvidenceError(f"Partial or malformed feature location: {expr}")

    def parse(node: str, strand: int = 1) -> list[tuple[int, int, int, bool]]:
        if node.startswith("order("):
            raise EvidenceError(f"Unsupported compound location: {expr}")
        if node.startswith("complement("):
            if not node.endswith(")"): raise EvidenceError(f"Malformed feature location: {expr}")
            nested = parse(node[11:-1], -strand)
            return list(reversed(nested))
        if node.startswith("join("):
            if not node.endswith(")"): raise EvidenceError(f"Malformed feature location: {expr}")
            parts: list[tuple[int, int, int, bool]] = []
            for child in _split_location_args(node[5:-1]):
                parts.extend(parse(child, strand))
            return parts
        if "(" in node or ")" in node:
            raise EvidenceError(f"Unsupported feature location: {expr}")
        match = re.fullmatch(r"(\d+)(?:\.\.(\d+))?", node)
        if not match: raise EvidenceError(f"Ambiguous or malformed feature location: {expr}")
        start = int(match.group(1)); end = int(match.group(2) or match.group(1))
        crossing = start > end
        if crossing:
            if topology != "circular": raise EvidenceError(f"Origin crossing requires circular record: {expr}")
        elif start < 1 or end > sequence_length:
            raise EvidenceError(f"Feature location outside record: {expr}")
        if start < 1 or start > sequence_length or end < 1 or end > sequence_length:
            raise EvidenceError(f"Feature location outside record: {expr}")
        return [(start - 1, end, strand, crossing)]

    parts = parse(text)
    strands = {part[2] for part in parts}
    if len(strands) != 1:
        raise EvidenceError(f"Mixed-strand compound location is unsupported: {expr}")
    return parts, next(iter(strands))


def _extract_parts(sequence: str, parts: list[tuple[int, int, int, bool]]) -> str:
    chunks: list[str] = []
    for start, end, strand, crossing in parts:
        chunk = sequence[start:] + sequence[:end] if crossing else sequence[start:end]
        chunks.append(reverse_complement(chunk) if strand == -1 else chunk)
    return "".join(chunks)


def _parse_genbank(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceError("Source is not UTF-8 GenBank text") from exc
    lines = text.splitlines()
    locus = next((line for line in lines if line.startswith("LOCUS")), "")
    if not locus:
        raise EvidenceError("Missing LOCUS line")
    locus_tokens = locus.split()
    locus_name = locus_tokens[1] if len(locus_tokens) > 1 else ""
    topology = next((t.lower() for t in locus_tokens if t.lower() in {"linear", "circular"}), "")
    molecule_type = next((t for t in locus_tokens[3:] if t.lower() in {"dna", "rna", "mrna", "na"}), "")
    accession = ""
    for i, line in enumerate(lines):
        if line.startswith("ACCESSION"):
            accession = line[12:].strip().split()[0] if line[12:].strip() else ""
            break
    version = ""
    for line in lines:
        if line.startswith("VERSION"):
            version = line[12:].strip().split()[0] if line[12:].strip() else ""
            break
    if not re.fullmatch(r"[A-Za-z]{1,8}\d{4,}(?:\.\d+)?", accession):
        raise EvidenceError("Missing or malformed ACCESSION")
    if not re.fullmatch(r"[A-Za-z]{1,8}\d{4,}\.\d+", version):
        raise EvidenceError("Missing or malformed VERSION")
    if version.split(".", 1)[0].upper() != accession.split(".", 1)[0].upper():
        raise EvidenceError("ACCESSION and VERSION identity mismatch")
    accession_version = version
    origin_index = next((i for i, line in enumerate(lines) if line.startswith("ORIGIN")), None)
    if origin_index is None:
        raise EvidenceError("Missing ORIGIN section")
    seq_chunks = []
    for line in lines[origin_index + 1:]:
        if line.startswith("//"):
            break
        seq_chunks.append("".join(re.findall(r"[A-Za-z]", line)))
    sequence = "".join(seq_chunks).upper()
    if not sequence or re.search(r"[^ACGTN]", sequence):
        raise EvidenceError("ORIGIN sequence is empty or contains invalid bases")
    features: list[dict[str, Any]] = []
    feature_start = next((i for i, line in enumerate(lines) if line.startswith("FEATURES")), None)
    if feature_start is not None:
        i = feature_start + 1
        while i < origin_index:
            line = lines[i]
            if len(line) >= 21 and line[5:21].strip() and not line[5:21].strip().startswith("/"):
                ftype = line[5:21].strip()
                location_expr = line[21:].strip()
                i += 1
                while i < origin_index and len(lines[i]) >= 21 and lines[i][5:21].strip() == "":
                    continuation = lines[i][21:].strip()
                    if continuation.startswith("/"):
                        break
                    location_expr += continuation
                    i += 1
                qualifiers: dict[str, list[str]] = {}
                while i < origin_index:
                    qline = lines[i]
                    if len(qline) >= 22 and qline[21:].lstrip().startswith("/"):
                        q = qline[21:].strip()[1:]
                        if "=" in q:
                            key, value = q.split("=", 1)
                            value = value.strip().strip('"')
                            qualifiers.setdefault(key, []).append(value)
                        else:
                            qualifiers.setdefault(q, []).append("")
                        i += 1
                        continue
                    if len(qline) >= 21 and qline[5:21].strip():
                        break
                    i += 1
                feature_id = f"{accession_version}:feature:{len(features)+1:03d}"
                feature_base = {
                    "feature_id": feature_id,
                    "type": ftype,
                    # Keep the deposited expression verbatim, including fuzzy
                    # endpoints and unsupported operators.
                    "location": location_expr,
                    "raw_location": location_expr,
                    "qualifiers": {k: list(v) for k, v in sorted(qualifiers.items())},
                }
                try:
                    parts, strand = _parse_location(location_expr, len(sequence), topology)
                except EvidenceError as exc:
                    # A bad annotation is a review gap, not a bad source
                    # record.  It remains selectable by index only so that a
                    # caller attempting exact extraction fails closed.
                    features.append(feature_base | {
                        "review_status": "review_required",
                        "review_reason": str(exc),
                    })
                else:
                    extracted = _extract_parts(sequence, parts)
                    features.append(feature_base | {
                        "coordinates": [{"start": s + 1, "end": e, "strand": part_strand} for s, e, part_strand, _ in parts],
                        "strand": strand,
                        "sequence": extracted,
                        "sequence_length": len(extracted),
                        "sequence_sha256": sha256_bytes(extracted.encode("ascii")),
                        "review_status": "exact",
                    })
                continue
            i += 1
    return {"accession": accession_version, "locus": locus_name, "locus_metadata": locus,
            "topology": topology or None, "molecule_type": molecule_type or None,
            "sequence": sequence, "sequence_length": len(sequence), "features": features}


def _role(feature: dict[str, Any]) -> dict[str, Any]:
    classes = feature["qualifiers"].get("regulatory_class", [])
    regulatory_class = classes[0] if len(classes) == 1 else (classes[0] if classes else None)
    role_status = "review_required"
    role = None
    if feature["type"] == "regulatory" and regulatory_class in {"promoter", "terminator"} and len(classes) == 1:
        role, role_status = regulatory_class, "explicit"
    return {"deposited_feature_type": feature["type"], "regulatory_class": regulatory_class,
            "role": role, "role_status": role_status}


def _load_reference_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in [Path("data/plant_component_registry_v1/registry.batch1.json")]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for record in payload.get("records", []):
                value = str(record.get("sequence_sha256", "")).lower()
                if re.fullmatch(r"[0-9a-f]{64}", value):
                    hashes[value] = str(record.get("component_id", ""))
        except (OSError, json.JSONDecodeError):
            continue
    return hashes


def process(source: Path, output: Path, *, feature_index: int | None = None,
            coordinates: str | None = None, strand: int | None = None,
            candidate_id: str | None = None) -> dict[str, Any]:
    raw = source.read_bytes()
    parsed = _parse_genbank(raw)
    selected = None
    if feature_index is not None:
        if feature_index < 1 or feature_index > len(parsed["features"]):
            raise EvidenceError("feature-index is out of range")
        selected = parsed["features"][feature_index - 1]
        if selected.get("review_status") != "exact":
            raise EvidenceError(
                f"Selected feature requires review and cannot be extracted exactly: {selected.get('location', '')}"
            )
    elif coordinates:
        parts, use_strand = _parse_location(coordinates, parsed["sequence_length"], parsed["topology"])
        use_strand = strand if strand in {-1, 1} else use_strand
        if strand in {-1, 1}:
            parts = [(s, e, strand, crossing) for s, e, _, crossing in parts]
        seq = _extract_parts(parsed["sequence"], parts)
        matching = next((f for f in parsed["features"] if f["location"] == coordinates), None)
        selected = {"type": matching["type"] if matching else "candidate", "location": coordinates,
                    "coordinates": [{"start": s + 1, "end": e, "strand": part_strand} for s, e, part_strand, _ in parts],
                    "strand": use_strand, "qualifiers": {}, "sequence": seq,
                    "sequence_length": len(seq), "sequence_sha256": sha256_bytes(seq.encode("ascii"))}
        if matching:
            selected["qualifiers"] = matching["qualifiers"]
    selected = selected or {"type": "source_record", "location": f"1..{parsed['sequence_length']}",
                            "coordinates": [{"start": 1, "end": parsed["sequence_length"], "strand": 1}], "strand": 1,
                            "qualifiers": {}, "sequence": parsed["sequence"],
                            "sequence_length": parsed["sequence_length"],
                            "sequence_sha256": sha256_bytes(parsed["sequence"].encode("ascii"))}
    role = _role(selected)
    refs = _load_reference_hashes()
    seq_hash = selected["sequence_sha256"]
    rc_hash = sha256_bytes(reverse_complement(selected["sequence"]).encode("ascii"))
    duplicate = {"status": "exact_duplicate", "component_id": refs[seq_hash]} if seq_hash in refs else ({"status": "reverse_complement_duplicate", "component_id": refs[rc_hash]} if rc_hash in refs else {"status": "no_exact_match", "component_id": None})
    review_required_features = [
        {"feature_id": feature["feature_id"], "type": feature["type"], "location": feature["location"],
         "raw_location": feature["raw_location"],
         "qualifiers": feature["qualifiers"], "review_reason": feature["review_reason"]}
        for feature in parsed["features"] if feature.get("review_status") == "review_required"
    ]
    record = {"schema_version": "component-evidence-pipeline-v1", "candidate_id": candidate_id or source.stem,
              "source_artifact": {"path": "<source>", "accession_version": parsed["accession"], "locus": parsed["locus_metadata"], "raw_bytes": len(raw), "raw_sha256": sha256_bytes(raw), "topology": parsed["topology"], "molecule_type": parsed["molecule_type"], "sequence_length": parsed["sequence_length"], "sequence_sha256": sha256_bytes(parsed["sequence"].encode("ascii"))},
              "exact_identity": {"coordinates": selected["coordinates"], "location": selected["location"], "strand": selected["strand"], "sequence": selected["sequence"], "length": selected["sequence_length"], "sequence_sha256": seq_hash},
              "role": role, "duplicate": duplicate, "review_required_features": review_required_features,
              "evidence_gaps": ["human review required for role/admission"] + ([f"{len(review_required_features)} feature annotation(s) require location review"] if review_required_features else []),
              "formal_admission_status": "NOT_ADMITTED", "host_eligibility_status": "NOT_ESTABLISHED"}
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["candidate_id", "accession_version", "feature_type", "location", "strand", "length", "sequence_sha256", "duplicate_status", "formal_admission_status", "host_eligibility_status"])
        writer.writeheader(); writer.writerow({"candidate_id": record["candidate_id"], "accession_version": parsed["accession"], "feature_type": role["deposited_feature_type"], "location": selected["location"], "strand": selected["strand"], "length": selected["sequence_length"], "sequence_sha256": seq_hash, "duplicate_status": duplicate["status"], "formal_admission_status": "NOT_ADMITTED", "host_eligibility_status": "NOT_ESTABLISHED"})
    report = f"# Component Evidence Review\n\n- Accession: `{parsed['accession']}`\n- Raw SHA-256: `{sha256_bytes(raw)}`\n- Feature/type: `{role['deposited_feature_type']}`\n- Boundary: `{selected['location']}` strand `{selected['strand']}`\n- Sequence length: `{selected['sequence_length']}`\n- Sequence SHA-256: `{seq_hash}`\n- Duplicate status: `{duplicate['status']}`\n- Formal admission: `NOT_ADMITTED`\n- Host eligibility: `NOT_ESTABLISHED`\n\nEvidence gaps: human review required; no biological role or eligibility is inferred.\n"
    (output / "review.md").write_text(report, encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("process")
    p.add_argument("--source", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--feature-index", type=int); p.add_argument("--coordinates"); p.add_argument("--strand", type=int); p.add_argument("--candidate-id")
    args = parser.parse_args()
    try:
        process(args.source, args.output, feature_index=args.feature_index, coordinates=args.coordinates, strand=args.strand, candidate_id=args.candidate_id)
    except (OSError, EvidenceError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
