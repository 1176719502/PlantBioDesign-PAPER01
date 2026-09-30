from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import types
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree

import pytest

from core.i18n import translate

from services.publication_map_contract import (
    PublicationMapContractError,
    PublicationMapViewType,
)
from services.publication_map_product import (
    _build_publication_map_converted_exports,
    build_publication_map_export_artifact,
    build_publication_map_svg_artifact,
)
from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _snapshot_result() -> dict[str, Any]:
    linear_sequence = "ACGT" * 25
    circular_sequence = "AACCGGTT" * 20
    linear_checksum = hashlib.sha256(linear_sequence.encode("ascii")).hexdigest()
    circular_checksum = hashlib.sha256(circular_sequence.encode("ascii")).hexdigest()
    transcription_unit = {
        "tu_id": "tu:product",
        "generated_nucleotide_sequence": linear_sequence,
        "generated_sequence_checksum": linear_checksum,
        "revision_id": "revision:linear",
        "stale": False,
        "validation_findings": [],
        "feature_coordinates": [
            {"name": "CDS", "type": "CDS", "start": 8, "end": 40, "strand": 1}
        ],
    }
    construct = {
        "construct_id": "construct:product",
        "transcription_unit_id": "tu:product",
        "construct_status": "current",
        "canonical_generated_sequence": linear_sequence,
        "sequence_checksum": linear_checksum,
        "current_revision": "revision:linear",
        "validation_summary": {"blocking_count": 0},
        "validation_findings": [],
    }
    plasmid = {
        "plasmid_id": "plasmid:product",
        "construct_status": "current",
        "generated_nucleotide_sequence": circular_sequence,
        "sequence_checksum": circular_checksum,
        "current_revision": "revision:circular",
        "topology": "circular",
        "combined_feature_coordinates": [
            {"name": "Origin", "type": "rep_origin", "start": 20, "end": 60, "strand": None}
        ],
        "validation_summary": {"blocking_count": 0},
        "validation_findings": [],
    }
    runtime = {
        "schema_version": "runtime:product",
        "active_transcription_unit_id": "tu:product",
        "active_construct_id": "construct:product",
        "active_complete_plasmid_id": "plasmid:product",
        "transcription_units": [transcription_unit],
        "constructs": [construct],
        "complete_plasmid_constructs": [plasmid],
    }
    return {
        "runtime": runtime,
        "exports": {
            "complete_plasmid_fasta": {"data": ">plasmid:product\n" + circular_sequence},
            "complete_plasmid_genbank": {"data": "LOCUS       plasmid:product"},
        },
    }


def _geometry_fidelity_result() -> dict[str, Any]:
    sequence = "ACGT" * 2525
    checksum = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    plasmid = {
        "plasmid_id": "fixture:publication-map-export-geometry-10100",
        "construct_status": "current",
        "generated_nucleotide_sequence": sequence,
        "sequence_checksum": checksum,
        "current_revision": "revision:geometry-fidelity-10100",
        "topology": "circular",
        "combined_feature_coordinates": [
            {"name": "Promoter A", "type": "promoter", "start": 120, "end": 560, "strand": 1},
            {"name": "5' region A", "type": "five_prime_utr", "start": 560, "end": 800, "strand": 1},
            {"name": "CDS A", "type": "CDS", "start": 800, "end": 2900, "strand": 1},
            {"name": "3' regulatory region A", "type": "terminator", "start": 2900, "end": 3300, "strand": 1},
            {"name": "Insertion region", "type": "misc_feature", "component_type": "insertion_region", "start": 100, "end": 3700, "strand": 1},
            {"name": "Left border", "type": "misc_feature", "component_type": "left_border", "start": 3900, "end": 3925, "strand": 1},
            {"name": "Selectable marker", "type": "CDS", "component_type": "selectable_marker", "start": 4200, "end": 5600, "strand": -1},
            {"name": "Right border", "type": "misc_feature", "component_type": "right_border", "start": 6000, "end": 6025, "strand": 1},
            {"name": "Replication origin", "type": "rep_origin", "start": 6500, "end": 7600, "strand": None},
            {"name": "Reverse promoter", "type": "promoter", "start": 7800, "end": 8200, "strand": -1},
            {"name": "Reverse CDS", "type": "CDS", "start": 8200, "end": 9800, "strand": -1},
            {"name": "Long context feature", "type": "misc_feature", "start": 1200, "end": 7500, "strand": None},
        ],
        "validation_summary": {"blocking_count": 0},
        "validation_findings": [],
    }
    return {
        "runtime": {
            "schema_version": "runtime:geometry-fidelity",
            "active_complete_plasmid_id": plasmid["plasmid_id"],
            "complete_plasmid_constructs": [plasmid],
        }
    }


def _patched_linear_snapshot(runtime: dict[str, Any]) -> dict[str, Any]:
    unit = next(item for item in runtime["transcription_units"] if item["tu_id"] == runtime["active_transcription_unit_id"])
    construct = next(item for item in runtime["constructs"] if item["construct_id"] == runtime["active_construct_id"])
    return {
        "runtime": runtime,
        "construct_id": construct["construct_id"],
        "construct_status": construct["construct_status"],
        "sequence": unit["generated_nucleotide_sequence"],
        "sequence_length": len(unit["generated_nucleotide_sequence"]),
        "sequence_checksum": construct["sequence_checksum"],
        "revision_id": runtime.get("_snapshot_linear_revision", unit["revision_id"]),
        "validation_findings": list(construct.get("validation_findings") or []),
        "validation_summary": dict(construct.get("validation_summary") or {}),
    }


def _patched_complete_snapshot(runtime: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in runtime["complete_plasmid_constructs"] if item["plasmid_id"] == runtime["active_complete_plasmid_id"]]
    plasmid = matches[0]
    return {
        "runtime": runtime,
        "plasmid_id": plasmid["plasmid_id"],
        "construct_status": plasmid["construct_status"],
        "sequence": plasmid["generated_nucleotide_sequence"],
        "sequence_length": len(plasmid["generated_nucleotide_sequence"]),
        "sequence_checksum": plasmid["sequence_checksum"],
        "revision_id": runtime.get("_snapshot_circular_revision", plasmid["current_revision"]),
        "topology": plasmid["topology"],
        "validation_findings": list(plasmid.get("validation_findings") or []),
        "validation_summary": dict(plasmid.get("validation_summary") or {}),
    }


@pytest.fixture
def production_result(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fake_runtime = types.ModuleType("services.canonical_construct_runtime")
    fake_runtime.CanonicalConstructRuntimeError = type(
        "CanonicalConstructRuntimeError", (ValueError,), {}
    )
    fake_runtime.active_construct_snapshot = _patched_linear_snapshot
    fake_runtime.active_complete_plasmid_snapshot = _patched_complete_snapshot
    monkeypatch.setitem(sys.modules, "services.canonical_construct_runtime", fake_runtime)
    return _snapshot_result()


def _metadata(artifact: Any) -> dict[str, Any]:
    root = ElementTree.fromstring(artifact.svg_bytes)
    metadata = root.find("svg:metadata", SVG_NS)
    assert metadata is not None and metadata.text
    return json.loads(metadata.text)


def _poppler_tool(name: str) -> str:
    executable = shutil.which(name)
    assert executable, f"{name} is required for Publication Map geometry-fidelity tests"
    return executable


def _render_source_svg_reference(svg_bytes: bytes, output_path: Path) -> Any:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    svg_path = output_path.with_suffix(".svg")
    svg_path.write_bytes(svg_bytes)
    root = ElementTree.fromstring(svg_bytes)
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(svg_path.resolve().as_uri(), wait_until="load")
        page.screenshot(path=str(output_path))
        browser.close()
    with Image.open(output_path) as image:
        image.load()
        return image.convert("RGB")


def _visual_similarity(reference: Any, candidate: Any) -> tuple[float, float]:
    import numpy as np
    from PIL import Image

    comparison_size = (900, 600)
    reference = reference.convert("RGB").resize(comparison_size, Image.Resampling.LANCZOS)
    candidate = candidate.convert("RGB").resize(comparison_size, Image.Resampling.LANCZOS)
    reference_pixels = np.asarray(reference, dtype=np.int16)
    candidate_pixels = np.asarray(candidate, dtype=np.int16)
    normalized_mae = float(np.abs(reference_pixels - candidate_pixels).mean() / 255)
    reference_ink = np.asarray(reference.convert("L")) < 245
    candidate_ink = np.asarray(candidate.convert("L")) < 245
    union = np.logical_or(reference_ink, candidate_ink).sum()
    ink_iou = float(np.logical_and(reference_ink, candidate_ink).sum() / union)
    return normalized_mae, ink_iou


def _app_function(name: str, *, namespace: dict[str, Any]) -> Any:
    namespace.setdefault("_t", _zh_t)
    namespace.setdefault("_ui", lambda value: value)
    namespace.setdefault("re", re)
    namespace.setdefault("components", types.SimpleNamespace(html=lambda body, **kwargs: namespace["st"].markdown(body)))
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize(
    ("view_type", "snapshot_factory"),
    [
        (
            PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
            _patched_complete_snapshot,
        ),
        (
            PublicationMapViewType.LINEAR_ACTIVE_EXPRESSION_CONSTRUCT,
            _patched_linear_snapshot,
        ),
        (PublicationMapViewType.COMPLETE_LINEAR_PLASMID, _patched_complete_snapshot),
    ],
)
def test_product_artifact_binds_current_canonical_identity_revision_and_sequence(
    production_result: dict[str, Any],
    view_type: PublicationMapViewType,
    snapshot_factory: Any,
) -> None:
    snapshot = snapshot_factory(production_result["runtime"])
    artifact = build_publication_map_svg_artifact(
        production_result["runtime"],
        view_type=view_type,
        display_name="Production canonical record",
    )
    metadata = _metadata(artifact)
    expected_identifier = snapshot.get("plasmid_id") or snapshot.get("construct_id")

    assert artifact.construct_identifier == expected_identifier
    assert artifact.revision_id == snapshot["revision_id"]
    assert artifact.sequence_checksum == snapshot["sequence_checksum"]
    assert metadata["construct_identifier"] == expected_identifier
    assert metadata["revision"] == snapshot["revision_id"]
    assert metadata["sequence_checksum"] == snapshot["sequence_checksum"]
    assert metadata["sequence_length"] == snapshot["sequence_length"]
    assert artifact.file_name.endswith(".svg")
    assert artifact.mime == "image/svg+xml"


def test_preview_and_download_share_exact_svg_bytes(
    production_result: dict[str, Any],
) -> None:
    fake_st = FakeStreamlit()
    render = _app_function(
        "_render_publication_map_svg",
        namespace={"Any": Any, "Mapping": Mapping, "st": fake_st},
    )

    assert render(
        production_result,
        view_type="complete_circular_plasmid",
        display_name="Production canonical record",
        download_key="publication_map_test_download",
    )

    preview_text = next(
        call["body"]
        for call in fake_st.markdown_calls
        if 'class="map-viewer-stage"' in str(call["body"])
    )
    download = fake_st.download_button_calls[0]
    assert download["data"].decode("utf-8") in preview_text
    assert download["mime"] == "image/svg+xml"
    assert download["file_name"].endswith(".svg")
    assert download["key"] == "publication_map_test_download"


def test_publication_map_export_formats_are_valid_high_resolution_and_deterministic(
    production_result: dict[str, Any],
) -> None:
    _build_publication_map_converted_exports.cache_clear()
    first = build_publication_map_export_artifact(
        production_result["runtime"],
        view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        display_name="Production canonical record",
    )
    _build_publication_map_converted_exports.cache_clear()
    second = build_publication_map_export_artifact(
        production_result["runtime"],
        view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        display_name="Production canonical record",
    )

    assert first.svg_bytes == second.svg_bytes
    assert first.pdf_bytes == second.pdf_bytes
    assert first.png_bytes == second.png_bytes
    assert first.file_name.endswith(".svg")
    assert first.pdf_file_name.endswith(".pdf")
    assert first.png_file_name.endswith(".png")
    assert first.pdf_bytes.startswith(b"%PDF-")
    assert first.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    from PIL import Image

    with Image.open(BytesIO(first.png_bytes)) as image:
        assert image.width >= 3000
        assert image.info["dpi"][0] >= 299
        assert image.info["dpi"][1] >= 299

    svg_root = ElementTree.fromstring(first.svg_bytes)
    svg_visible_labels = {
        (node.text or "").strip()
        for node in svg_root.findall(".//svg:text[@data-label-for]", SVG_NS)
    }
    assert "Origin" in svg_visible_labels
    assert "..." not in "".join(svg_visible_labels)
    assert first.construct_identifier in svg_root.find("svg:metadata", SVG_NS).text
    assert first.revision_id in svg_root.find("svg:metadata", SVG_NS).text


def test_circular_pdf_and_png_match_the_exact_10100_bp_svg_geometry(
    production_result: dict[str, Any],
    tmp_path: Path,
) -> None:
    from PIL import Image

    result = _geometry_fidelity_result()
    artifact = build_publication_map_export_artifact(
        result["runtime"],
        view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        display_name="Geometry fidelity fixture",
    )
    svg_root = ElementTree.fromstring(artifact.svg_bytes)
    assert svg_root.attrib["width"] == "1800"
    assert svg_root.attrib["height"] == "1200"
    assert svg_root.attrib["viewBox"] == "0 0 1800 1200"
    visible_labels = {
        (node.text or "").strip()
        for node in svg_root.findall(".//svg:text[@data-label-for]", SVG_NS)
    }
    major_labels = {"Promoter A", "CDS A", "Replication origin", "Reverse CDS"}
    assert major_labels <= visible_labels
    assert "..." not in "".join(visible_labels)
    svg_metadata = _metadata(artifact)
    assert svg_metadata["construct_identifier"] == artifact.construct_identifier
    assert svg_metadata["revision"] == artifact.revision_id
    assert svg_metadata["sequence_length"] == 10_100

    reference = _render_source_svg_reference(
        artifact.svg_bytes, tmp_path / "source-svg-reference.png"
    )
    assert reference.size == (1800, 1200)

    with Image.open(BytesIO(artifact.png_bytes)) as png_image:
        png_image.load()
        assert png_image.size == (3000, 2000)
        assert png_image.mode == "RGB"
        assert png_image.getpixel((0, 0)) == (255, 255, 255)
        assert png_image.info["dpi"][0] == pytest.approx(300, abs=0.1)
        assert png_image.info["dpi"][1] == pytest.approx(300, abs=0.1)
        assert png_image.info["Construct"] == artifact.construct_identifier
        assert png_image.info["Revision"] == artifact.revision_id
        assert png_image.info["Sequence-Length"] == "10100"
        png_mae, png_ink_iou = _visual_similarity(reference, png_image)
    assert png_mae <= 0.01, png_mae
    assert png_ink_iou >= 0.78, png_ink_iou

    pdf_path = tmp_path / artifact.pdf_file_name
    pdf_path.write_bytes(artifact.pdf_bytes)
    pdf_render_prefix = tmp_path / "pdf-rendered"
    subprocess.run(
        [
            _poppler_tool("pdftoppm"),
            "-f",
            "1",
            "-singlefile",
            "-r",
            "96",
            "-png",
            str(pdf_path),
            str(pdf_render_prefix),
        ],
        check=True,
        capture_output=True,
    )
    with Image.open(pdf_render_prefix.with_suffix(".png")) as pdf_image:
        pdf_image.load()
        assert pdf_image.size == (1800, 1200)
        pdf_mae, pdf_ink_iou = _visual_similarity(reference, pdf_image)
    assert pdf_mae <= 0.01, pdf_mae
    assert pdf_ink_iou >= 0.78, pdf_ink_iou

    pdf_info = subprocess.run(
        [_poppler_tool("pdfinfo"), str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    assert re.search(r"^Pages:\s+1$", pdf_info, re.MULTILINE)
    assert re.search(r"^Page size:\s+1350 x 900 pts", pdf_info, re.MULTILINE)
    assert artifact.construct_identifier in pdf_info
    assert artifact.revision_id in pdf_info
    assert "length=10100 bp" in pdf_info


def test_publication_map_export_ui_exposes_three_map_specific_downloads(
    production_result: dict[str, Any],
) -> None:
    fake_st = FakeStreamlit()
    render = _app_function(
        "_render_publication_map_svg",
        namespace={"Any": Any, "Mapping": Mapping, "st": fake_st},
    )
    assert render(
        production_result,
        view_type="complete_circular_plasmid",
        display_name="Production canonical record",
        download_key="publication_map_export_test",
    )
    assert [call["label"] for call in fake_st.download_button_calls] == [
        "下载 Publication Map SVG",
        "下载 Publication Map PDF",
        "下载 Publication Map PNG",
    ]
    assert [call["mime"] for call in fake_st.download_button_calls] == [
        "image/svg+xml",
        "application/pdf",
        "image/png",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "stale",
        "blocking",
        "ambiguous",
        "revision_mismatch",
    ],
)
def test_product_wiring_fails_closed_for_non_current_or_ambiguous_constructs(
    production_result: dict[str, Any],
    mutation: str,
) -> None:
    runtime = deepcopy(production_result["runtime"])
    active_id = runtime["active_complete_plasmid_id"]
    record = next(
        item
        for item in runtime["complete_plasmid_constructs"]
        if item["plasmid_id"] == active_id
    )
    if mutation == "stale":
        record["construct_status"] = "stale"
    elif mutation == "blocking":
        record["validation_summary"] = {"blocking_count": 1}
    elif mutation == "ambiguous":
        runtime["complete_plasmid_constructs"].append(deepcopy(record))
    else:
        runtime["_snapshot_circular_revision"] = "revision:forged"

    with pytest.raises(PublicationMapContractError):
        build_publication_map_svg_artifact(
            runtime,
            view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
        )


def test_svg_projection_does_not_change_fasta_or_genbank_identity(
    production_result: dict[str, Any],
) -> None:
    exports_before = deepcopy(production_result["exports"])
    plasmid_before = _patched_complete_snapshot(production_result["runtime"])

    build_publication_map_svg_artifact(
        production_result["runtime"],
        view_type=PublicationMapViewType.COMPLETE_CIRCULAR_PLASMID,
    )

    assert production_result["exports"] == exports_before
    plasmid_after = _patched_complete_snapshot(production_result["runtime"])
    assert plasmid_after["sequence"] == plasmid_before["sequence"]
    assert plasmid_after["sequence_checksum"] == plasmid_before["sequence_checksum"]
    assert plasmid_after["revision_id"] == plasmid_before["revision_id"]


def test_formal_result_and_step5_paths_use_r4_product_wiring_not_legacy_map_output() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def function_source(name: str) -> str:
        node = next(
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == name
        )
        return ast.get_source_segment(source, node) or ""

    step5 = function_source("_render_step_5_complete")
    step6_result = function_source("_render_results_export_content")
    multi_tu_result = function_source("_render_multi_tu_assembly_results")
    product_renderer = function_source("_render_publication_map_svg")

    assert "build_publication_map_svg_artifact" in product_renderer
    assert "artifact.svg_text" in product_renderer
    assert "data=artifact.svg_bytes" in product_renderer
    assert "_render_publication_map_svg(" in step5
    assert step6_result.count("_render_publication_map_svg(") == 3
    assert 'view_type="linear_active_expression_construct"' in step6_result
    assert 'view_type="complete_linear_plasmid"' in step6_result
    assert "_render_publication_map_svg(" in multi_tu_result
    assert "if publication_map_current:" in multi_tu_result
    assert "publication_map_current=publication_map_current" in step6_result
    assert "_render_canonical_plasmid_maps(" not in step6_result
    assert "_render_canonical_plasmid_maps(" not in multi_tu_result
    assert step5.index("if result_is_current:") < step5.index(
        "_step5_construct_preview_html(plasmid)"
    )
    assert step5.index("elif plasmid:") < step5.index(
        "_step5_construct_preview_html(plasmid)"
    )
