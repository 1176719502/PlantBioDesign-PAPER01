"""Deterministic PDF transport for a validated formal Step 6 projection."""
from __future__ import annotations

import re
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from services.formal_single_gene_final_review import validate_formal_report_delivery


PDF_TRANSPORT_CONTRACT_VERSION = "formal-report-pdf-v1"
_FIXED_DATE = "D:20000101000000+00'00'"
_CJK_FONT_NAME = "NotoSansSC"
_CJK_FONT_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "fonts"
    / "noto_sans_sc"
    / "NotoSansSC-wght.ttf"
)
_LATIN_FONT_NAME = "Helvetica"
_PRINTABLE_ASCII_RUN = re.compile(r"[\x20-\x7e]+")


class _DeterministicCanvas(Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self.setAuthor("BioDesign Studio")
        self.setCreator(PDF_TRANSPORT_CONTRACT_VERSION)
        self.setProducer(PDF_TRANSPORT_CONTRACT_VERSION)
        self.setSubject("Documentation-only formal design review record")
        self.setTitle("BioDesign Studio Final Review")
        self._doc.info.creationDate = _FIXED_DATE
        self._doc.info.modDate = _FIXED_DATE


def _require_projection(report: Mapping[str, Any]) -> tuple[str, str]:
    decision = validate_formal_report_delivery(report)
    if not decision.eligible:
        raise ValueError("Formal report delivery is blocked.")
    return decision.markdown, decision.content_sha256


def _styles() -> dict[str, ParagraphStyle]:
    if _CJK_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        if not _CJK_FONT_PATH.is_file():
            raise RuntimeError("Bundled Noto Sans SC font asset is unavailable.")
        pdfmetrics.registerFont(TTFont(_CJK_FONT_NAME, str(_CJK_FONT_PATH)))
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "FormalReportTitle",
            parent=base["Title"],
            fontName=_CJK_FONT_NAME,
            fontSize=18,
            leading=23,
            textColor=HexColor("#17324D"),
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "heading": ParagraphStyle(
            "FormalReportHeading",
            parent=base["Heading2"],
            fontName=_CJK_FONT_NAME,
            fontSize=12,
            leading=16,
            textColor=HexColor("#17324D"),
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "FormalReportBody",
            parent=base["BodyText"],
            fontName=_CJK_FONT_NAME,
            fontSize=8.5,
            leading=12,
            textColor=HexColor("#24313D"),
            spaceAfter=1.4 * mm,
            splitLongWords=True,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "FormalReportBullet",
            parent=base["BodyText"],
            fontName=_CJK_FONT_NAME,
            fontSize=8.5,
            leading=12,
            leftIndent=5 * mm,
            firstLineIndent=-3 * mm,
            textColor=HexColor("#24313D"),
            spaceAfter=1.2 * mm,
            splitLongWords=True,
            wordWrap="CJK",
        ),
        "identity": ParagraphStyle(
            "FormalReportIdentity",
            parent=base["BodyText"],
            fontName=_CJK_FONT_NAME,
            fontSize=7.5,
            leading=10,
            textColor=HexColor("#51616F"),
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
            splitLongWords=True,
            wordWrap="CJK",
        ),
    }


def _font_markup(text: str) -> str:
    """Use Latin metrics for ASCII while retaining bundled Noto for CJK glyphs."""
    parts: list[str] = []
    cursor = 0
    for match in _PRINTABLE_ASCII_RUN.finditer(text):
        parts.append(escape(text[cursor : match.start()]))
        parts.append(
            f'<font name="{_LATIN_FONT_NAME}">{escape(match.group(0))}</font>'
        )
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def _build_story(
    markdown: str,
    content_sha256: str,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = []
    section_needs_content = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            if not section_needs_content:
                story.append(Spacer(1, 1.2 * mm))
        elif line.startswith("# "):
            story.append(Paragraph(_font_markup(line[2:]), styles["title"]))
            story.append(
                Paragraph(
                    _font_markup(
                        f"Canonical content identity: sha256:{content_sha256}"
                    ),
                    styles["identity"],
                )
            )
            section_needs_content = False
        elif line.startswith("## "):
            story.append(Paragraph(_font_markup(line[3:]), styles["heading"]))
            section_needs_content = True
        elif line.startswith("- "):
            story.append(Paragraph(_font_markup("- " + line[2:]), styles["bullet"]))
            section_needs_content = False
        elif line.startswith("  "):
            story.append(Paragraph(_font_markup(line.strip()), styles["bullet"]))
            section_needs_content = False
        else:
            story.append(Paragraph(_font_markup(line), styles["body"]))
            section_needs_content = False
    return story


def _footer(canvas: Canvas, document: SimpleDocTemplate, content_identity: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(HexColor("#D7DEE5"))
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFillColor(HexColor("#637381"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 10 * mm, content_identity)
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def render_formal_report_pdf(report: Mapping[str, Any]) -> bytes:
    """Render stable PDF bytes from the verified canonical content projection."""
    markdown, content_sha256 = _require_projection(report)
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="BioDesign Studio Final Review",
        author="BioDesign Studio",
        creator=PDF_TRANSPORT_CONTRACT_VERSION,
        producer=PDF_TRANSPORT_CONTRACT_VERSION,
        subject="Documentation-only formal design review record",
    )
    story = _build_story(markdown, content_sha256, styles)
    content_identity = f"sha256:{content_sha256}"
    document.build(
        story,
        canvasmaker=_DeterministicCanvas,
        onFirstPage=lambda canvas, doc: _footer(canvas, doc, content_identity),
        onLaterPages=lambda canvas, doc: _footer(canvas, doc, content_identity),
    )
    payload = buffer.getvalue()
    if not payload.startswith(b"%PDF-") or len(payload) < 1000:
        raise ValueError("Formal report PDF rendering did not produce a valid transport artifact.")
    return payload
