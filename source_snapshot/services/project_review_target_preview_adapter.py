from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.generated_output_boundary import assert_no_misleading_generated_claims


SECTION_TITLE = "Target Design Preview"
SECTION_STATUS_ATTACHED = "ATTACHED_READ_ONLY"
SECTION_STATUS_EMPTY = "NOT_ATTACHED"
EMPTY_STATE_MESSAGE = (
    "No Target Design Preview readback is attached to this report section. "
    "Create or copy the read-only preview from Expression Constructs before manual review."
)
BOUNDARY_NOTES = [
    "Target Design Preview is a documentation-only route preview.",
    "This is a read-only report section.",
    "It is not saved as construct/cassette records.",
    "Manual review and source confirmation required.",
    "It is not experimental validation.",
]


def _clean_markdown(markdown: Any) -> str:
    return "\n".join(str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


@dataclass(frozen=True)
class ProjectReviewTargetPreviewSection:
    title: str
    status: str
    source_surface: str
    boundary_notes: tuple[str, ...]
    markdown_readback: str
    empty_state_message: str

    @property
    def has_markdown_readback(self) -> bool:
        return bool(self.markdown_readback)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "status": self.status,
            "source_surface": self.source_surface,
            "has_markdown_readback": self.has_markdown_readback,
            "boundary_notes": list(self.boundary_notes),
            "markdown_readback": self.markdown_readback,
            "empty_state_message": self.empty_state_message,
        }

    def as_markdown(self) -> str:
        lines = [
            f"## {self.title}",
            "- Target Design Preview",
            "- Documentation-only route preview.",
            "- Read-only report section.",
            "- Not saved as construct/cassette records.",
            "- Manual review and source confirmation required.",
            "- Not experimental validation.",
            "",
            "### Boundary notes",
        ]
        lines.extend(f"- {note}" for note in self.boundary_notes)
        lines.extend(["", "### Markdown readback"])
        if self.markdown_readback:
            lines.append(self.markdown_readback)
        else:
            lines.append(f"- {self.empty_state_message}")
        rendered = "\n".join(lines).rstrip() + "\n"
        assert_no_misleading_generated_claims(rendered, context="project review target preview report section")
        return rendered


def build_project_review_target_preview_section(
    target_preview_markdown: str | None = None,
) -> ProjectReviewTargetPreviewSection:
    """Adapt optional Target Design Preview Markdown into read-only Project Review report text."""
    cleaned_markdown = _clean_markdown(target_preview_markdown)
    section = ProjectReviewTargetPreviewSection(
        title=SECTION_TITLE,
        status=SECTION_STATUS_ATTACHED if cleaned_markdown else SECTION_STATUS_EMPTY,
        source_surface="Expression Constructs Target Design Preview markdown readback",
        boundary_notes=tuple(BOUNDARY_NOTES),
        markdown_readback=cleaned_markdown,
        empty_state_message="" if cleaned_markdown else EMPTY_STATE_MESSAGE,
    )
    assert_no_misleading_generated_claims(section.as_dict(), context="project review target preview report section")
    return section
