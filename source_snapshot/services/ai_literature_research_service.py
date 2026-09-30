"""Deterministic local service for V2.6 AI Literature Research draft briefs.

This module intentionally performs no network calls, no API calls, and no database
writes. It creates documentation-only draft research briefs for human review.
"""
from __future__ import annotations

from dataclasses import dataclass


SECTION_TITLES: tuple[str, ...] = (
    "Research target",
    "Literature context summary",
    "Key terms / search keywords",
    "Source notes placeholder",
    "Documented biology background",
    "Uncertainty / human review notes",
    "Follow-up review questions",
    "Boundary note: documentation-only, not experimental guidance",
)

BOUNDARY_NOTE = (
    "This draft research brief is documentation-only. It is a local documentation "
    "assistant output for literature context and human review. It is not experimental "
    "guidance, not a protocol, not a biological selection, and not a claim of "
    "experimental readiness."
)

UNAVAILABLE_MESSAGE = (
    "AI Literature Research is available as a local deterministic stub only. "
    "External AI, web search, and external source lookup are not enabled in V2.6-R2."
)


@dataclass(frozen=True)
class LiteratureResearchBrief:
    """Structured draft brief returned by the local research stub."""

    target: str
    sections: dict[str, list[str]]
    source_mode: str = "local deterministic stub"
    requires_source_review: bool = True
    unavailable_message: str = UNAVAILABLE_MESSAGE

    def as_markdown(self) -> str:
        """Render the brief as stable markdown for UI display and tests."""
        parts = ["# Draft research brief", "", f"Source mode: {self.source_mode}", ""]
        for title in SECTION_TITLES:
            parts.append(f"## {title}")
            for item in self.sections.get(title, []):
                parts.append(f"- {item}")
            parts.append("")
        return "\n".join(parts).strip()


def normalize_target(raw_target: str | None) -> str:
    """Normalize a user-entered research target without changing its meaning."""
    return " ".join((raw_target or "").strip().split())


def is_albumin_target(target: str) -> bool:
    """Return True when the target is an albumin-related example input."""
    normalized = target.casefold()
    return any(token in normalized for token in ("albumin", "白蛋白", "human serum albumin"))


def empty_input_state() -> dict[str, str]:
    """Return bounded UI copy for the empty input state."""
    return {
        "title": "Enter a research target to create a draft research brief.",
        "body": (
            "Examples: albumin, 白蛋白, or human serum albumin. The local stub will "
            "create structured literature context with source review needed."
        ),
    }


def unavailable_state(reason: str | None = None) -> dict[str, str]:
    """Return a bounded unavailable/failure state without exposing internals."""
    detail = normalize_target(reason) if reason else UNAVAILABLE_MESSAGE
    return {
        "title": "Literature research source lookup unavailable",
        "body": detail,
        "boundary": BOUNDARY_NOTE,
    }


def generate_literature_research_brief(raw_target: str | None) -> LiteratureResearchBrief:
    """Generate a deterministic documentation-only research brief.

    Raises:
        ValueError: if the target is empty after normalization.
    """
    target = normalize_target(raw_target)
    if not target:
        raise ValueError("Research target is required.")

    if is_albumin_target(target):
        sections = _albumin_sections(target)
    else:
        sections = _generic_sections(target)

    return LiteratureResearchBrief(target=target, sections=sections)


def _albumin_sections(target: str) -> dict[str, list[str]]:
    return {
        "Research target": [
            f"User-entered target: {target}",
            "Draft scope: albumin / 白蛋白 literature context for documentation planning.",
            "This is a source-placeholder brief; source review needed before using text as confirmed project documentation.",
        ],
        "Literature context summary": [
            "Albumin is commonly discussed as a soluble protein family with roles in transport, osmotic pressure context, and clinical or biochemical reference literature.",
            "Human serum albumin is often referenced in biomedical literature as an abundant plasma protein; this brief does not inspect live sources in V2.6-R2.",
            "Claims should be checked against primary literature, curated databases, or reviewer-selected references before inclusion in project records.",
        ],
        "Key terms / search keywords": [
            "albumin; 白蛋白; human serum albumin; serum albumin; ALB gene",
            "protein family; plasma protein; ligand binding; transport protein; provenance/source notes",
            "review keywords may include organism context, protein isoform, sequence accession, and literature context.",
        ],
        "Source notes placeholder": [
            "No external source lookup was performed by this local stub.",
            "Add reviewer-selected citations, database accessions, DOI/URL notes, and short usage notes here.",
            "Separate source-backed facts from draft interpretation during human review.",
        ],
        "Documented biology background": [
            "Albumin-related documentation may include protein identity, organism context, synonyms, sequence record references, and known biological role summaries.",
            "The brief avoids host, promoter, construct, protocol, or wet-lab setup guidance.",
            "Use this section as draft background text only after source review.",
        ],
        "Uncertainty / human review notes": [
            "Human review needed before treating this draft text as confirmed documentation.",
            "Terminology may vary by organism, isoform, source type, and publication context.",
            "Unresolved claims should be checked by a domain reviewer and linked to provenance/source notes.",
        ],
        "Follow-up review questions": [
            "Which organism, isoform, accession, or naming convention should the documentation use?",
            "Which source records or papers will support the background summary?",
            "What assumptions should be marked as unresolved until reviewer confirmation?",
            "Which local documentation records should receive provenance/source notes?",
        ],
        "Boundary note: documentation-only, not experimental guidance": [BOUNDARY_NOTE],
    }


def _generic_sections(target: str) -> dict[str, list[str]]:
    return {
        "Research target": [
            f"User-entered target: {target}",
            "Draft scope: literature context and documentation planning for human review.",
        ],
        "Literature context summary": [
            "This local stub creates a structured placeholder summary without external AI, web search, or database lookup.",
            "Use reviewer-selected sources to replace or support this draft literature context.",
        ],
        "Key terms / search keywords": [
            f"{target}; synonyms; organism context; sequence accession; review record; provenance/source notes",
            "Add reviewer-selected terminology after source review.",
        ],
        "Source notes placeholder": [
            "No external source lookup was performed by this local stub.",
            "Record source title, organization or authors, DOI/URL/accession when available, and how each source was used.",
        ],
        "Documented biology background": [
            "Draft background should describe documented biology context at a high level.",
            "Do not use this draft as experimental guidance or as a claim about biological outcome.",
        ],
        "Uncertainty / human review notes": [
            "Human review needed before using this text as confirmed project documentation.",
            "Assumptions, missing sources, and ambiguous terminology should remain visible for review.",
        ],
        "Follow-up review questions": [
            "Which source-backed facts should be added after review?",
            "Which terminology or synonyms need reviewer confirmation?",
            "Which local project records should capture provenance/source notes?",
        ],
        "Boundary note: documentation-only, not experimental guidance": [BOUNDARY_NOTE],
    }
