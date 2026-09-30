from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from io import BytesIO
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree

from services.publication_map_adapter import publication_map_document_from_runtime
from services.publication_map_contract import (
    PUBLICATION_MAP_REVISION_PROVENANCE_FIELD,
    PublicationMapContractError,
    PublicationMapViewType,
)
from services.publication_map_renderer import render_publication_map_svg


PUBLICATION_MAP_SVG_MIME = "image/svg+xml"
PUBLICATION_MAP_PDF_MIME = "application/pdf"
PUBLICATION_MAP_PNG_MIME = "image/png"
_FILENAME_TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_SVG_CSS_PIXELS_PER_INCH = 96.0
_PUBLICATION_MAP_PNG_WIDTH_PX = 3000
_PUBLICATION_MAP_PNG_DPI = 300
_FIXED_PDF_DATE = b"D:20000101000000+00'00'"
_PDF_DATE_PATTERN = re.compile(rb"/(CreationDate|ModDate)\s*\(D:[^)]*\)")


@dataclass(frozen=True, slots=True)
class PublicationMapSvgArtifact:
    """One identity-bound SVG payload shared by preview and download."""

    svg_bytes: bytes
    file_name: str
    mime: str
    construct_identifier: str
    revision_id: str
    sequence_checksum: str
    view_type: PublicationMapViewType

    @property
    def svg_text(self) -> str:
        return self.svg_bytes.decode("utf-8")


@dataclass(frozen=True, slots=True)
class PublicationMapExportArtifact(PublicationMapSvgArtifact):
    """One frozen canonical map projected into SVG, PDF, and PNG payloads."""

    pdf_bytes: bytes
    png_bytes: bytes
    pdf_file_name: str
    png_file_name: str


def _svg_canvas_and_metadata(svg_bytes: bytes) -> tuple[int, int, dict[str, Any]]:
    """Read the renderer canvas and identity without reinterpreting its geometry."""

    try:
        root = ElementTree.fromstring(svg_bytes)
        width = float(root.attrib["width"])
        height = float(root.attrib["height"])
    except (ElementTree.ParseError, KeyError, TypeError, ValueError) as exc:
        raise PublicationMapContractError(
            "Publication Map export requires an SVG with a finite pixel canvas."
        ) from exc
    if (
        width <= 0
        or height <= 0
        or not width.is_integer()
        or not height.is_integer()
    ):
        raise PublicationMapContractError(
            "Publication Map export requires positive integer SVG pixel dimensions."
        )
    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise PublicationMapContractError(
            "Publication Map export requires an explicit SVG viewBox."
        )
    try:
        origin_x, origin_y, view_width, view_height = map(float, view_box)
    except ValueError as exc:
        raise PublicationMapContractError(
            "Publication Map export requires a numeric SVG viewBox."
        ) from exc
    if (origin_x, origin_y, view_width, view_height) != (0.0, 0.0, width, height):
        raise PublicationMapContractError(
            "Publication Map export requires canvas and viewBox identity."
        )
    metadata_node = next(
        (
            node
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "metadata"
            and node.attrib.get("id") == "publication-map-metadata"
        ),
        None,
    )
    try:
        metadata = json.loads(metadata_node.text or "") if metadata_node is not None else {}
    except json.JSONDecodeError as exc:
        raise PublicationMapContractError(
            "Publication Map export requires valid SVG identity metadata."
        ) from exc
    return int(width), int(height), metadata


def _publication_map_svg_engine() -> Path:
    candidates: list[Path] = []
    discovered = shutil.which("msedge")
    if discovered:
        candidates.append(Path(discovered))
    for root_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        root = os.environ.get(root_name)
        if root:
            candidates.append(
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            )
    candidates.extend(
        (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PublicationMapContractError(
        "Publication Map PDF/PNG export requires the installed Microsoft Edge SVG engine."
    )


def _run_svg_engine(
    engine: Path,
    *,
    profile_directory: Path,
    arguments: list[str],
) -> None:
    profile_directory.mkdir(parents=True, exist_ok=True)
    command = [
        str(engine),
        "--headless",
        "--no-sandbox",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-extensions",
        "--disable-sync",
        "--no-default-browser-check",
        "--no-first-run",
        "--hide-scrollbars",
        "--force-color-profile=srgb",
        "--enable-unsafe-swiftshader",
        f"--user-data-dir={profile_directory}",
        *arguments,
    ]
    run_options: dict[str, Any] = {
        "capture_output": True,
        "check": False,
        "timeout": 45,
    }
    if sys.platform == "win32":
        run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(command, **run_options)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationMapContractError(
            "Publication Map SVG conversion engine could not complete."
        ) from exc
    if completed.returncode != 0:
        raise PublicationMapContractError(
            "Publication Map SVG conversion engine returned a non-zero status."
        )


def _normalize_pdf_metadata(pdf_bytes: bytes) -> bytes:
    """Freeze Chromium's clock-only fields while preserving its vector payload."""

    def replace_date(match: re.Match[bytes]) -> bytes:
        return b"/" + match.group(1) + b" (" + _FIXED_PDF_DATE + b")"

    return _PDF_DATE_PATTERN.sub(replace_date, pdf_bytes)


@lru_cache(maxsize=8)
def _build_publication_map_converted_exports(
    svg_bytes: bytes,
    *,
    title: str,
    construct_identifier: str,
    revision_id: str,
    sequence_checksum: str,
) -> tuple[bytes, bytes]:
    """Convert one exact final SVG through a standards-compliant SVG engine."""

    from PIL import Image, PngImagePlugin

    width, height, svg_metadata = _svg_canvas_and_metadata(svg_bytes)
    try:
        sequence_length = int(svg_metadata.get("sequence_length", 0))
    except (TypeError, ValueError) as exc:
        raise PublicationMapContractError(
            "Publication Map export requires numeric SVG sequence-length metadata."
        ) from exc
    if (
        svg_metadata.get("construct_identifier") != construct_identifier
        or svg_metadata.get("revision") != revision_id
        or svg_metadata.get("sequence_checksum") != sequence_checksum
        or sequence_length <= 0
    ):
        raise PublicationMapContractError(
            "Publication Map export identity does not match the final SVG metadata."
        )
    engine = _publication_map_svg_engine()
    scale = _PUBLICATION_MAP_PNG_WIDTH_PX / width
    png_height_px = max(1, round(height * scale))
    page_width_inches = width / _SVG_CSS_PIXELS_PER_INCH
    page_height_inches = height / _SVG_CSS_PIXELS_PER_INCH
    export_title = (
        f"{title}; construct={construct_identifier}; revision={revision_id}; "
        f"length={sequence_length} bp"
    )
    with TemporaryDirectory(prefix="biodesign-publication-map-") as temp_name:
        temp_root = Path(temp_name)
        svg_path = temp_root / "publication-map.svg"
        html_path = temp_root / "publication-map.html"
        pdf_path = temp_root / "publication-map.pdf"
        raw_png_path = temp_root / "publication-map.png"
        svg_path.write_bytes(svg_bytes)
        wrapper = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(export_title)}</title><style>"
            f"@page{{size:{page_width_inches:.8f}in {page_height_inches:.8f}in;margin:0}}"
            f"html,body{{width:{width}px;height:{height}px;margin:0;overflow:hidden;"
            "background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}}"
            f"img{{display:block;width:{width}px;height:{height}px}}"
            "</style></head><body>"
            '<img src="publication-map.svg" alt="Publication Map">'
            "</body></html>"
        )
        html_path.write_text(wrapper, encoding="utf-8", newline="")
        document_uri = html_path.resolve().as_uri()
        _run_svg_engine(
            engine,
            profile_directory=temp_root / "pdf-profile",
            arguments=[
                f"--print-to-pdf={pdf_path}",
                "--print-to-pdf-no-header",
                document_uri,
            ],
        )
        _run_svg_engine(
            engine,
            profile_directory=temp_root / "png-profile",
            arguments=[
                f"--window-size={width},{height}",
                f"--force-device-scale-factor={scale:.12f}",
                "--run-all-compositor-stages-before-draw",
                f"--screenshot={raw_png_path}",
                document_uri,
            ],
        )
        if not pdf_path.is_file() or pdf_path.stat().st_size < 1000:
            raise PublicationMapContractError(
                "Publication Map SVG engine did not produce a valid PDF payload."
            )
        if not raw_png_path.is_file() or raw_png_path.stat().st_size < 1000:
            raise PublicationMapContractError(
                "Publication Map SVG engine did not produce a valid PNG payload."
            )
        pdf_bytes = _normalize_pdf_metadata(pdf_path.read_bytes())
        if not pdf_bytes.startswith(b"%PDF-"):
            raise PublicationMapContractError(
                "Publication Map SVG engine produced an invalid PDF signature."
            )
        with Image.open(raw_png_path) as raw_image:
            raw_image.load()
            if raw_image.size != (_PUBLICATION_MAP_PNG_WIDTH_PX, png_height_px):
                raise PublicationMapContractError(
                    "Publication Map SVG engine produced an unexpected PNG canvas."
                )
            if raw_image.mode == "RGBA":
                image = Image.new("RGB", raw_image.size, "white")
                image.paste(raw_image, mask=raw_image.getchannel("A"))
            else:
                image = raw_image.convert("RGB")
            png_metadata = PngImagePlugin.PngInfo()
            png_metadata.add_text("Title", title)
            png_metadata.add_text("Software", "BioDesign Studio Publication Map export")
            png_metadata.add_text("Construct", construct_identifier)
            png_metadata.add_text("Revision", revision_id)
            png_metadata.add_text("Sequence-Length", str(sequence_length))
            png_metadata.add_text("Sequence-SHA256", sequence_checksum)
            png_output = BytesIO()
            image.save(
                png_output,
                format="PNG",
                dpi=(_PUBLICATION_MAP_PNG_DPI, _PUBLICATION_MAP_PNG_DPI),
                pnginfo=png_metadata,
                compress_level=9,
            )
    return pdf_bytes, png_output.getvalue()


def _file_token(value: str, *, fallback: str) -> str:
    token = _FILENAME_TOKEN_PATTERN.sub("-", value.strip()).strip("-._")
    return token[:80] or fallback


def build_publication_map_svg_artifact(
    runtime_payload: Mapping[str, Any],
    *,
    view_type: PublicationMapViewType,
    display_name: str = "",
) -> PublicationMapSvgArtifact:
    """Project the current canonical runtime once and freeze its exact SVG bytes."""

    if not isinstance(runtime_payload, Mapping):
        raise PublicationMapContractError(
            "Publication Map product wiring requires a canonical runtime mapping."
        )
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError

    try:
        document = publication_map_document_from_runtime(
            runtime_payload,
            view_type=view_type,
            display_name=display_name,
        )
    except CanonicalConstructRuntimeError as exc:
        raise PublicationMapContractError(
            f"Canonical runtime is not eligible for Publication Map projection: {exc}"
        ) from exc
    revision_id = dict(document.provenance).get(
        PUBLICATION_MAP_REVISION_PROVENANCE_FIELD, ""
    )
    if not revision_id:
        raise PublicationMapContractError(
            "Publication Map product wiring requires canonical revision identity."
        )
    render_options = None
    if document.topology.value == "circular":
        from services.publication_map_renderer import PublicationMapRenderOptions
        render_options = PublicationMapRenderOptions(width=1800, height=1200)
    svg_bytes = render_publication_map_svg(document, render_options).encode("utf-8")
    construct_token = _file_token(
        document.construct_identifier, fallback="canonical-construct"
    )
    revision_token = _file_token(revision_id, fallback="revision")
    view_token = _file_token(view_type.value, fallback="publication-map")
    return PublicationMapSvgArtifact(
        svg_bytes=svg_bytes,
        file_name=f"{construct_token}_{revision_token}_{view_token}.svg",
        mime=PUBLICATION_MAP_SVG_MIME,
        construct_identifier=document.construct_identifier,
        revision_id=revision_id,
        sequence_checksum=document.sequence_checksum,
        view_type=view_type,
    )


def build_publication_map_export_artifact(
    runtime_payload: Mapping[str, Any], *, view_type: PublicationMapViewType, display_name: str = ""
) -> PublicationMapExportArtifact:
    base = build_publication_map_svg_artifact(runtime_payload, view_type=view_type, display_name=display_name)
    title = f"{display_name or base.construct_identifier} publication map"
    stem = base.file_name[:-4]
    pdf_bytes, png_bytes = _build_publication_map_converted_exports(
        base.svg_bytes,
        title=title,
        construct_identifier=base.construct_identifier,
        revision_id=base.revision_id,
        sequence_checksum=base.sequence_checksum,
    )
    return PublicationMapExportArtifact(
        **{field: getattr(base, field) for field in ("svg_bytes", "file_name", "mime", "construct_identifier", "revision_id", "sequence_checksum", "view_type")},
        pdf_bytes=pdf_bytes,
        png_bytes=png_bytes,
        pdf_file_name=f"{stem}.pdf",
        png_file_name=f"{stem}.png",
    )
