import hashlib
import json
import re
from pathlib import Path

import pytest

from tools.component_evidence_pipeline import EvidenceError, process


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = Path("D:/UBD-evidence/VLAD-2019-RICE-STEP3")
PACKAGE = ROOT / "audit_reports" / "vlad2019_rice_step3_exact_evidence"

RAW_EXPECTED = {
    "12870_2019_2038_MOESM2_ESM.gb": (45576, "6dcd728799bec23c70f4bd360b26d7bcb4d6594e6e45cf2b845ec1417e2c60a4", 16907, "Lvl_2_EC17203"),
    "12870_2019_2038_MOESM3_ESM.gb": (46078, "fd7925e77e4fd204d41e699a057295d42c92bb9cdcbde946e1c78ecca33c6a75", 17879, "New_DNA"),
    "12870_2019_2038_MOESM4_ESM.gb": (48363, "a15ff0338ffb2ef1b45a4ea87ff2159ffe9c3f5c6a3239c5270ae6eab5a27297", 17713, "EC17613"),
}
NOS_SHA = "e195e224e4b00353173edde4d0255f5d4ea5a67710a32c4a4fd24d905bbff9b3"
P35S_SHA = "eeca8f64206dbdd7d874bd1ff63b6051a0087097826939f2817e62773d570909"


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ATCG", "TAGC"))[::-1]


def _record(path: Path) -> tuple[str, str, list[dict[str, str]]]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    locus = lines[0]
    sequence = "".join(
        re.findall(r"[ACGTN]", raw.split("ORIGIN", 1)[1].split("//", 1)[0], re.I)
    ).upper()
    features: list[dict[str, str]] = []
    in_features = False
    for index, line in enumerate(lines):
        if line.startswith("FEATURES"):
            in_features = True
            continue
        if line.startswith("ORIGIN"):
            break
        if not in_features or len(line) < 21:
            continue
        feature_type = line[5:21].strip()
        if feature_type not in {"promoter", "terminator"}:
            continue
        location = line[21:].strip()
        block_lines = [line]
        cursor = index + 1
        while cursor < len(lines):
            next_line = lines[cursor]
            if len(next_line) >= 21 and next_line[5:21].strip():
                break
            if next_line.startswith("ORIGIN"):
                break
            block_lines.append(next_line)
            cursor += 1
        block = "\n".join(block_lines)
        match = re.fullmatch(r"complement\((\d+)\.\.(\d+)\)", location)
        strand = -1 if match else 1
        if not match:
            match = re.fullmatch(r"(\d+)\.\.(\d+)", location)
        if not match:
            continue
        start, end = (int(value) for value in match.groups())
        extracted = sequence[start - 1 : end]
        if strand == -1:
            extracted = _reverse_complement(extracted)
        labels = re.findall(r"/(?:label|locus_tag)=([^\r\n]+)", block)
        features.append(
            {
                "type": feature_type,
                "location": location,
                "strand": str(strand),
                "start": str(start),
                "end": str(end),
                "sequence": extracted,
                "sha256": hashlib.sha256(extracted.encode("ascii")).hexdigest(),
                "labels": "|".join(labels),
            }
        )
    return locus, sequence, features


def test_raw_artifacts_are_pinned_and_parse_as_circular_constructs():
    governance = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    pinned = {item["filename"]: item for item in governance["source_retrieval"]["supplementary_files"]}
    assert set(pinned) == set(RAW_EXPECTED)
    for filename, (byte_count, raw_sha, sequence_length, locus_name) in RAW_EXPECTED.items():
        path = EXTERNAL / filename
        raw = path.read_bytes()
        locus, sequence, _ = _record(path)
        assert len(raw) == byte_count
        assert hashlib.sha256(raw).hexdigest() == raw_sha
        assert len(sequence) == sequence_length
        assert locus_name in locus
        assert "circular" in locus.lower()
        assert pinned[filename]["sha256"] == raw_sha
        assert pinned[filename]["whole_construct_length"] == sequence_length


def test_pipeline_fails_closed_and_direct_extraction_is_repeatable():
    source = EXTERNAL / "12870_2019_2038_MOESM2_ESM.gb"
    with pytest.raises(EvidenceError, match="ACCESSION"):
        process(source, ROOT / ".pytest_tmp" / "pipeline-incompatible")

    first = _record(source)
    second = _record(source)
    assert first == second
    p35s = next(feature for feature in first[2] if feature["location"] == "complement(1506..1930)")
    assert p35s["type"] == "promoter"
    assert p35s["strand"] == "-1"
    assert p35s["start"] == "1506"
    assert p35s["end"] == "1930"
    assert p35s["labels"] == r"p35S\(short)"
    assert len(p35s["sequence"]) == 425
    assert p35s["sha256"] == P35S_SHA
    assert _reverse_complement(_reverse_complement(p35s["sequence"])) == p35s["sequence"]


def test_ec15030_record_binds_the_exact_promoter_to_hyg_and_registry_check():
    governance = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    candidate = governance["candidates"]["EC15030"]
    feature = candidate["genbank_feature"]
    _, _, features = _record(EXTERNAL / "12870_2019_2038_MOESM2_ESM.gb")
    extracted = next(item for item in features if item["location"] == feature["location"])
    assert extracted["sha256"] == feature["component_sha256"]
    assert feature["length"] == len(extracted["sequence"]) == 425
    assert candidate["hyg_transcriptional_unit_context"] == {
        "hyg_cds": "complement(289..1504)",
        "p35S_promoter": "complement(1506..1930)",
        "nos_terminator": "complement(1956..2218)",
        "context_statement": "The deposited feature order and article construct design place the p35S promoter in the HYG selection transcriptional unit of construct 17203.",
    }
    registry = json.loads((ROOT / "data/plant_component_registry_v1/registry.batch1.json").read_text(encoding="utf-8"))
    hashes = {row["sequence_sha256"] for row in registry["records"]}
    assert feature["component_sha256"] not in hashes
    assert _reverse_complement(extracted["sequence"]) not in {
        row["sequence"] for row in registry["records"]
    }


def test_ec41421_all_tnos_occurrences_are_identical_and_not_registry_duplicates():
    governance = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    candidate = governance["candidates"]["EC41421"]
    observed = []
    for filename in RAW_EXPECTED:
        _, _, features = _record(EXTERNAL / filename)
        observed.extend(feature for feature in features if feature["type"] == "terminator")
    assert len(observed) == 12
    assert {item["sha256"] for item in observed} == {NOS_SHA}
    assert {len(item["sequence"]) for item in observed} == {263}
    assert candidate["all_occurrences_identical"] is True
    assert len(candidate["occurrences"]) == len(observed)
    assert candidate["exact_identity"]["component_sha256"] == observed[0]["sha256"] == NOS_SHA

    registry = json.loads((ROOT / "data/plant_component_registry_v1/registry.batch1.json").read_text(encoding="utf-8"))
    rows = {row["component_id"]: row for row in registry["records"]}
    assert rows["PCLV1-3REG-NOS-253"]["sequence_sha256"] != NOS_SHA
    assert rows["PCLV1-3REG-NOS-256"]["sequence_sha256"] != NOS_SHA
    registry_hashes = {row["sequence_sha256"] for row in registry["records"]}
    assert NOS_SHA not in registry_hashes
    assert all(
        _reverse_complement(item["sequence"]) not in {
            row["sequence"] for row in registry["records"]
        }
        for item in observed
    )


def test_candidate_artifacts_do_not_embed_reconstructable_component_sequences():
    governance = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    assert "sequence" not in governance["candidates"]["EC15030"]["genbank_feature"]
    assert "sequence" not in governance["candidates"]["EC41421"]["exact_identity"]
    external_sequences = []
    for filename in RAW_EXPECTED:
        _, _, features = _record(EXTERNAL / filename)
        external_sequences.extend(
            item["sequence"]
            for item in features
            if item["type"] in {"promoter", "terminator"}
            and len(item["sequence"]) in {425, 263}
        )
    for artifact in (PACKAGE / "GOVERNANCE_RECORD.json", PACKAGE / "REVIEW_PACKAGE.md"):
        text = artifact.read_text(encoding="utf-8")
        assert all(sequence not in text for sequence in external_sequences)


def test_rights_scope_and_two_slot_decision_are_pinned():
    governance = json.loads((PACKAGE / "GOVERNANCE_RECORD.json").read_text(encoding="utf-8"))
    rights = governance["rights"]
    assert rights["article_license"] == "CC BY 4.0"
    assert rights["article_data_license"] == "CC0 unless otherwise stated"
    assert rights["supplementary_files_are_article_data"] is True
    assert rights["decision"] == "CONDITIONAL"
    xml = (EXTERNAL / "article_fullTextXML_PMC6794914.xml").read_text(encoding="utf-8")
    assert "Creative Commons Attribution 4.0 International License" in xml
    assert "Creative Commons Public Domain Dedication waiver" in xml
    assert "Data Availability Statement" in xml
    assert governance["final_verdict"] == "VLAD2019_RICE_STEP3_EVIDENCE_R2_READY_FOR_REVIEW"
    assert "head" not in governance["sync"]
    assert governance["task"]["formal_base"] == "23975e5eb5b0f7e9be8fefea42b092be292b0498"
    assert governance["sync"]["original_candidate_reviewed"] == "aea5fc6d3c7b2c9c69a6e9beb1a75bf4a93183eb"
    for candidate_id in ("EC15030", "EC41421"):
        candidate = governance["candidates"][candidate_id]
        assert candidate["step3_compatibility"] == "PASS"
        assert candidate["formal_admit"].startswith("NO_GO pending donor-specific rights clearance")
