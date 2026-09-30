from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from Bio import SeqIO

import mvp_app
from core.i18n import translate
from services import formal_single_gene_runtime as runtime
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from views import formal_construct_findings as findings_view


RUNTIME_EXPORTS = (
    "_cds_record",
    "cassette_input_signature",
    "construct_input_signature",
    "generate_expression_cassette",
    "generate_complete_vector",
    "load_real_case",
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_CASSETTE_SIGNATURE = "c2382279b0536b503241539968a164d93da02ad3a42efa6c2c1fbd4079b3521a"
BASELINE_CONSTRUCT_SIGNATURE = "e3cc6c5bc57139c5e17e19be698df82fc453d41bec2dbc12f278491e76aaae01"
BASELINE_PLASMID_SHA256 = "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"
BASELINE_FASTA_BYTES_SHA256 = "bff837583dad749f5b7e84c40750e3d479770ac534bcf4e9a1b0d2149b1577a3"
BASELINE_GENBANK_BYTES_SHA256 = "718a9dc01e371d6ee8e92b6f26d3f046d2de67749967a3ed458926014f23723b"


def _zh_t(key: str, **kwargs: object) -> str:
    return translate(key, language="zh-CN", **kwargs)


def test_mvp_app_reexports_the_formal_runtime_callables() -> None:
    for name in RUNTIME_EXPORTS:
        compatibility_callable = getattr(mvp_app, name)
        formal_callable = getattr(runtime, name)
        assert compatibility_callable is formal_callable
        assert inspect.signature(compatibility_callable) == inspect.signature(formal_callable)

    assert mvp_app._render_findings is findings_view._render_findings


def test_app_imports_the_seven_helpers_only_from_formal_modules() -> None:
    source = Path("app.py").read_text(encoding="utf-8")

    assert "from mvp_app import" not in source
    assert "import mvp_app" not in source
    for name in RUNTIME_EXPORTS:
        if name in {"generate_complete_vector", "load_real_case"}:
            continue
        assert name in source
    assert "generate_admitted_complete_vector" in source
    assert "result = generate_complete_vector(" not in source
    assert "load_real_case" not in source
    assert "from views.formal_construct_findings import _render_findings" in source


def test_default_case_preserves_canonical_sequence_features_and_export_bytes() -> None:
    result = runtime.generate_complete_vector(
        project_id="phase2d-batch1-golden",
        project_name="Phase 2D Batch 1 golden",
    )
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    fasta = SeqIO.read(StringIO(result["exports"]["fasta"]["data"]), "fasta")
    genbank = SeqIO.read(StringIO(result["exports"]["genbank"]["data"]), "genbank")

    assert cassette["sequence_length"] == result["cassette_length"]
    assert plasmid["sequence_length"] == result["plasmid_length"]
    assert str(fasta.seq).upper() == plasmid["sequence"]
    assert str(genbank.seq).upper() == plasmid["sequence"]
    assert len(genbank.features) == len(plasmid["feature_rows"])
    assert [str(feature.type) for feature in genbank.features] == [
        str(feature["feature_type"]) for feature in plasmid["feature_rows"]
    ]
    assert result["plasmid_sha256"] == result["fasta_sequence_sha256"]
    assert result["plasmid_sha256"] == result["genbank_sequence_sha256"]
    assert result["cassette_input_signature"] == BASELINE_CASSETTE_SIGNATURE
    assert result["construct_input_signature"] == BASELINE_CONSTRUCT_SIGNATURE
    assert result["plasmid_sha256"] == BASELINE_PLASMID_SHA256
    assert hashlib.sha256(result["exports"]["fasta"]["data"].encode("utf-8")).hexdigest() == (
        BASELINE_FASTA_BYTES_SHA256
    )
    assert hashlib.sha256(result["exports"]["genbank"]["data"].encode("utf-8")).hexdigest() == (
        BASELINE_GENBANK_BYTES_SHA256
    )
    assert [
        (row["feature_type"], row["start"], row["end"], row.get("strand"))
        for row in plasmid["feature_rows"]
    ] == [
        ("rep_origin", 120, 380, 1),
        ("misc_feature", 1850, 1940, 1),
        ("promoter", 2101, 2740, 1),
        ("cds", 2741, 3640, 1),
        ("terminator", 3641, 3850, 1),
        ("misc_feature", 4350, 4500, -1),
        ("misc_feature", 5250, 5410, 1),
    ]
    assert list(result) == [
        "project_id",
        "project_name",
        "input_lengths",
        "cassette_length",
        "plasmid_length",
        "plasmid_sha256",
        "fasta_sequence_sha256",
        "genbank_sequence_sha256",
        "runtime",
        "source_inputs",
        "input_records",
        "cds_input",
        "insertion_settings",
        "validation_summary",
        "input_signature",
        "construct_input_signature",
        "cassette_input_signature",
        "exports",
        "vector_asset_admission",
        "company_review_package",
    ]


def test_invalid_cds_preserves_exception_type_and_text() -> None:
    with pytest.raises(RuntimeError, match="^CDS 输入未通过校验。$"):
        runtime.generate_expression_cassette(
            cds_input={"blocking": True, "normalized_cds": ""},
            project_id="phase2d-batch1-invalid",
        )


class _StreamlitRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def write(self, value: str) -> None:
        self.calls.append(("write", value))


def test_findings_renderer_preserves_streamlit_call_order(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _StreamlitRecorder()
    monkeypatch.setattr(findings_view, "st", recorder)
    monkeypatch.setattr(findings_view, "_t", _zh_t)
    findings_view._render_findings(
        [
            {"severity": "warning", "explanation": "first"},
            {"severity": "error", "message": "second"},
            {"severity": "info", "explanation": "third"},
        ]
    )

    assert recorder.calls == [
        ("write", f"{_zh_t('runtime.warning')}: first"),
        ("write", f"{_zh_t('runtime.error')}: second"),
        ("write", f"{_zh_t('runtime.info')}: third"),
    ]


def test_empty_findings_renderer_preserves_single_write(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _StreamlitRecorder()
    monkeypatch.setattr(findings_view, "st", recorder)
    monkeypatch.setattr(findings_view, "_t", _zh_t)

    findings_view._render_findings([])

    assert recorder.calls == [("write", "软件校验：未发现需要展示的问题。")]


@pytest.mark.parametrize(
    ("module_name", "allows_startup_database"),
    [
        ("services.formal_single_gene_runtime", False),
        ("views.formal_construct_findings", False),
        ("mvp_app", False),
        ("app", True),
    ],
)
def test_modules_import_in_fresh_process_without_unexpected_database_writes(
    tmp_path: Path,
    module_name: str,
    allows_startup_database: bool,
) -> None:
    module_root = tmp_path / module_name.replace(".", "_")
    database_path = module_root / "isolated.db"
    environment = {
        **os.environ,
        "BIODESIGN_DB_PATH": str(database_path),
        "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(module_root / "drafts"),
        "BIODESIGN_PYDNA_LOG_DIR": str(module_root / "pydna"),
        "pydna_log_dir": str(module_root / "pydna"),
    }
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert database_path.exists() is allows_startup_database
