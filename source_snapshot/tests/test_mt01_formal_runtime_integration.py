from __future__ import annotations

import copy
import json
import os
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SimpleLocation

from services.mt01_formal_runtime import (
    MT01_ACCESSION_VERSION,
    MT01_CASE_ID,
    Mt01RuntimeError,
    admit_mt01_source,
    build_mt01_result,
    is_mt01_claim,
    validate_mt01_result,
)
from services.mvp_multi_tu_persistence import (
    MvpMultiTuPersistenceError,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.plant_component_workflow_registry import (
    DETERMINISTIC_ACCESSION_DERIVATION,
    REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import new_project_id


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "data" / "real_case_contracts_v1" / "mt01_pgrdl_sp"
EXPECTED_CANONICAL_SHA = "1847b411bd0592e0927db433bfc88f8eec3a9f8c30620af97aba5dae465c3104"


def _external_source_path() -> Path:
    configured = os.environ.get("MT01_SOURCE_GENBANK", "").strip()
    if not configured:
        pytest.skip("Set MT01_SOURCE_GENBANK to the repository-external KX758647.1 GenBank file.")
    path = Path(configured)
    if not path.is_file():
        pytest.skip(f"MT01_SOURCE_GENBANK does not exist: {path}")
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return path
    pytest.fail("MT01_SOURCE_GENBANK must remain outside the Git worktree.")


@pytest.fixture(scope="module")
def source_bytes() -> bytes:
    return _external_source_path().read_bytes()


@pytest.fixture(scope="module")
def mt01_result(source_bytes: bytes) -> dict:
    return build_mt01_result(
        source_bytes,
        project_id="plant-proj-mt01-tests",
        project_name="MT-01 test project",
    )


def _record_from_bytes(source_bytes: bytes):
    return next(SeqIO.parse(StringIO(source_bytes.decode("ascii")), "genbank"))


def _record_bytes(record) -> bytes:
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue().encode("ascii")


def test_formal_app_exposes_mt01_entry_and_region_limit() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "MT-01：pGrDL_SP 双报告基因 2-TU 真实案例" in source
    assert "v1.project_center.source_kx758647_1_reconstructed_region_571_4649" in source
    assert "v1.project_center.verify_source_load_mt_01" in source
    assert "formal_mt01_source_file" in source


def test_mt01_runtime_is_in_packaging_closure() -> None:
    manifest = json.loads((ROOT / "packaging" / "resource_manifest.json").read_text(encoding="utf-8"))
    assert "services/mt01_formal_runtime.py" in manifest["runtime_python_modules"]


def test_exact_external_source_is_admitted(source_bytes: bytes) -> None:
    report = admit_mt01_source(source_bytes)
    assert report["status"] == "pass"
    assert report["record_id"] == MT01_ACCESSION_VERSION
    assert report["source_length_bp"] == 7086
    assert report["source_topology"] == "circular"
    assert report["region_length_bp"] == 4079
    assert report["region_sequence_sha256"] == EXPECTED_CANONICAL_SHA


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("record_id", "record ID mismatch"),
        ("unversioned_accession", "record ID mismatch"),
        ("source_length", "source length mismatch"),
        ("topology", "source topology mismatch"),
        ("source_sequence", "source sequence SHA-256 mismatch"),
        ("feature_boundary", "source feature boundary/strand/qualifier mismatch"),
    ],
)
def test_source_admission_rejects_named_mismatches(
    source_bytes: bytes, mutation: str, message: str
) -> None:
    record = _record_from_bytes(source_bytes)
    if mutation == "record_id":
        record.id = "OTHER.1"
        record.name = "OTHER"
    elif mutation == "unversioned_accession":
        record.id = "KX758647"
        record.name = "KX758647"
    elif mutation == "source_length":
        record.seq = record.seq[:-1]
    elif mutation == "topology":
        record.annotations["topology"] = "linear"
    elif mutation == "source_sequence":
        sequence = list(str(record.seq))
        sequence[0] = "A" if sequence[0].upper() != "A" else "C"
        record.seq = Seq("".join(sequence))
    elif mutation == "feature_boundary":
        feature = next(item for item in record.features if item.type == "CDS")
        feature.location = SimpleLocation(
            int(feature.location.start) + 1,
            int(feature.location.end),
            strand=feature.location.strand,
        )
    with pytest.raises(Mt01RuntimeError, match=message):
        admit_mt01_source(_record_bytes(record))


def test_source_admission_rejects_raw_file_byte_drift(source_bytes: bytes) -> None:
    with pytest.raises(Mt01RuntimeError, match="raw source size mismatch"):
        admit_mt01_source(source_bytes + b"\n")


def test_source_admission_rejects_region_hash_contract_drift(
    source_bytes: bytes, tmp_path: Path
) -> None:
    contract_copy = tmp_path / "contracts"
    contract_copy.mkdir()
    for path in CONTRACT_DIR.glob("*.json"):
        (contract_copy / path.name).write_bytes(path.read_bytes())
    hashes_path = contract_copy / "expected_hashes.json"
    hashes = json.loads(hashes_path.read_text(encoding="utf-8"))
    hashes["extracted_sequence_sha256"] = "0" * 64
    hashes_path.write_text(json.dumps(hashes), encoding="utf-8")
    with pytest.raises(Mt01RuntimeError, match="region SHA-256 mismatch"):
        admit_mt01_source(source_bytes, contract_dir=contract_copy)


def test_canonical_orientation_partition_and_provenance_are_exact(mt01_result: dict) -> None:
    assessment = validate_mt01_result(mt01_result)
    assert assessment == {
        "status": "pass",
        "case_id": "MT-01",
        "contract_version": "1.0.0",
        "canonical_length_bp": 4079,
        "canonical_sequence_sha256": EXPECTED_CANONICAL_SHA,
        "tu_count": 2,
        "unannotated_interval_count": 5,
        "unannotated_length_bp": 326,
        "contains_vector": False,
        "topology": "linear",
    }
    units = mt01_result["expression_units"]
    assert [unit["orientation"] for unit in units] == ["reverse", "forward"]
    assert [unit["range"] for unit in units] == [
        {"start": 1, "end": 1753, "strand": -1},
        {"start": 1754, "end": 4079, "strand": 1},
    ]
    assert mt01_result["unit_order"] == ["TU1", "TU2"]
    assert mt01_result["case_provenance"]["source_type"] == REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
    assert mt01_result["case_provenance"]["case_evidence_class"] == DETERMINISTIC_ACCESSION_DERIVATION


def test_reverse_tu_is_complemented_exactly_once(mt01_result: dict) -> None:
    unit = mt01_result["original_input"]["expression_units"][0]
    biological_input = (
        unit["promoter"]["raw_text"]
        + unit["cds"]["raw_text"]
        + unit["3_prime_regulatory_region"]["raw_text"]
    )
    physical = biological_input.translate(str.maketrans("ACGT", "TGCA"))[::-1]
    assert physical == mt01_result["combined_construct"]["dna"][:1753]
    assert physical == mt01_result["expression_units"][0]["dna"]


def test_all_components_are_accession_derived_not_registry_or_user_input(mt01_result: dict) -> None:
    references = []
    for unit in mt01_result["original_input"]["expression_units"]:
        for role in ("promoter", "cds", "3_prime_regulatory_region"):
            references.append(unit[role]["component_reference"])
    assert len(references) == 6
    assert {item["source_type"] for item in references} == {
        REAL_CASE_ACCESSION_DERIVED_SOURCE_TYPE
    }
    assert all(not item["registry_component_id"] for item in references)
    assert all(item["accession_version"] == MT01_ACCESSION_VERSION for item in references)
    assert all(item["component_snapshot"]["case_id"] == MT01_CASE_ID for item in references)


def test_five_unannotated_intervals_are_preserved_byte_for_byte(mt01_result: dict) -> None:
    canonical = mt01_result["combined_construct"]["dna"]
    intervals = mt01_result["case_snapshot"]["unannotated_intervals"]
    assert len(intervals) == 5
    assert sum(item["local_interval"]["length_bp"] for item in intervals) == 326
    for item in intervals:
        start = item["local_interval"]["internal_0_based_half_open"]["start"]
        end = item["local_interval"]["internal_0_based_half_open"]["end"]
        assert item["sequence"] == canonical[start:end]


def test_fasta_and_genbank_match_canonical_and_feature_contract(mt01_result: dict) -> None:
    exports = mt01_result["exports"]
    fasta = next(SeqIO.parse(StringIO(exports["combined_construct_fasta"]["data"]), "fasta"))
    genbank = next(SeqIO.parse(StringIO(exports["combined_construct_genbank"]["data"]), "genbank"))
    canonical = mt01_result["combined_construct"]["dna"]
    assert str(fasta.seq).upper() == canonical
    assert str(genbank.seq).upper() == canonical
    assert "MT-01" in fasta.description
    assert "KX758647.1" in fasta.description
    assert "source_region=571..4649" in fasta.description
    assert "contains_vector=false" in fasta.description
    assert genbank.annotations["topology"] == "linear"
    expected_features = mt01_result["case_snapshot"]["expected_features"]
    assert len(genbank.features) == len(expected_features) == 18
    assert sum(
        (feature.qualifiers.get("annotation_status") or [""])[0]
        == "UNANNOTATED_SOURCE_SEQUENCE"
        for feature in genbank.features
    ) == 5
    for feature in genbank.features:
        for qualifier in (
            "case_id",
            "contract_version",
            "source_accession_version",
            "source_construct",
            "source_external_coordinates",
            "source_type",
            "case_evidence_class",
            "role",
            "orientation",
            "sequence_sha256",
            "annotation_status",
        ):
            assert feature.qualifiers.get(qualifier), (
                (feature.qualifiers.get("feature_id") or ["unknown"])[0],
                qualifier,
            )
    exported_text = exports["combined_construct_genbank"]["data"].casefold()
    for forbidden in ("origin_of_replication", "t-dna_border", "selectable_marker"):
        assert forbidden not in exported_text


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.__setitem__("case_id", "MT-02"),
        lambda value: value["case_snapshot"]["source_admission"].__setitem__("source_sequence_sha256", "0" * 64),
        lambda value: value["case_snapshot"]["source_admission"].__setitem__("region_sequence_sha256", "0" * 64),
        lambda value: value["runtime"]["expression_units"][0].__setitem__("orientation", "forward"),
        lambda value: value.__setitem__("contains_vector", True),
        lambda value: value.__setitem__("topology", "circular"),
        lambda value: value.__setitem__("result_kind", "COMPLETE_VECTOR"),
        lambda value: value["case_snapshot"]["unannotated_intervals"].pop(),
        lambda value: value["case_snapshot"]["unannotated_intervals"][0].__setitem__("sequence", "C"),
        lambda value: value["case_snapshot"]["expected_features"][0].__setitem__("local_end", 4078),
        lambda value: value["combined_construct"].__setitem__(
            "dna",
            ("C" if value["combined_construct"]["dna"][0] != "C" else "A")
            + value["combined_construct"]["dna"][1:],
        ),
    ],
)
def test_result_and_session_tampering_is_rejected(mt01_result: dict, mutator) -> None:
    tampered = copy.deepcopy(mt01_result)
    mutator(tampered)
    with pytest.raises((Mt01RuntimeError, ValueError), match="MT01_RUNTIME_CONTRACT_MISMATCH"):
        validate_mt01_result(tampered)
    with pytest.raises(MvpMultiTuPersistenceError, match="MT01_RUNTIME_CONTRACT_MISMATCH"):
        save_mvp_multi_tu_design(
            tampered,
            repository=PlantProjectDraftRepository(),
        )


def test_generic_multi_tu_is_not_misclassified(mt01_result: dict) -> None:
    generic = copy.deepcopy(mt01_result)
    for key in (
        "case_id",
        "case_verified",
        "case_provenance",
        "case_snapshot",
        "case_snapshot_sha256",
    ):
        generic.pop(key, None)
    assert is_mt01_claim(generic) is False


def test_save_and_cold_reopen_use_snapshot_without_source_or_network(
    mt01_result: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_path = tmp_path / "projects"
    repository = PlantProjectDraftRepository(repository_path)
    result = copy.deepcopy(mt01_result)
    result["project_id"] = new_project_id()
    result["project_name"] = "Renamed MT-01 project"
    saved = save_mvp_multi_tu_design(result, repository=repository)

    def _network_forbidden(*_args, **_kwargs):
        raise AssertionError("cold reopen must not access the network")

    monkeypatch.setattr("urllib.request.urlopen", _network_forbidden)
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository_path),
    )
    assessment = validate_mt01_result(reopened)
    assert assessment["canonical_sequence_sha256"] == EXPECTED_CANONICAL_SHA
    assert reopened["project_name"] == "Renamed MT-01 project"
    assert [unit["orientation"] for unit in reopened["expression_units"]] == [
        "reverse",
        "forward",
    ]
    assert len(reopened["case_snapshot"]["unannotated_intervals"]) == 5
    assert reopened["case_provenance"] == result["case_provenance"]
    for export_key in ("combined_construct_fasta", "combined_construct_genbank"):
        assert reopened["exports"][export_key]["data"] == result["exports"][export_key]["data"]


def test_mt01_result_page_disables_direct_scientific_editing() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    function = source.split("def _render_multi_tu_assembly_results", 1)[1].split(
        "def _render_results_export", 1
    )[0]
    assert "v1.results_final_report.mt_01_scientific_input_protected" in function
    assert "disabled=True" in function
    assert "validate_mt01_result(result)" in function


def test_mt01_cold_reopen_skips_single_gene_project_review_gate() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    function = source.split("def _formal_result_needs_review", 1)[1].split(
        "def _apply_formal_cds_analysis", 1
    )[0]
    assert "from services.mt01_formal_runtime import is_mt01_claim" in function
    assert "if is_mt01_claim(candidate):\n        return False" in function
