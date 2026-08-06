"""Deterministic Markdown sectioning without changing source facts."""

import re

from resume_agent.domain import GeneratedSection, ResumeSection, VerifiedSection


HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def split_markdown_sections(
    markdown: str, max_tokens: int | None = None
) -> list[ResumeSection]:
    sections: list[ResumeSection] = []
    heading = "Profile"
    lines: list[str] = []

    def append_section() -> None:
        content = "\n".join(lines).strip()
        if content:
            sections.append(
                ResumeSection(
                    id=f"section-{len(sections) + 1:02d}",
                    heading=heading,
                    source_markdown=content,
                )
            )

    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match and lines:
            append_section()
            lines = []
        if match:
            heading = match.group(2).strip()
        lines.append(line)
    append_section()
    if max_tokens is None:
        return sections
    bounded: list[ResumeSection] = []
    from resume_agent.context_budget import estimate_tokens

    for section in sections:
        if estimate_tokens(section.source_markdown) <= max_tokens:
            bounded.append(section)
            continue
        paragraphs = [item.strip() for item in section.source_markdown.split("\n\n") if item.strip()]
        current: list[str] = []
        for paragraph in paragraphs:
            proposed = "\n\n".join([*current, paragraph])
            if current and estimate_tokens(proposed) > max_tokens:
                bounded.append(
                    ResumeSection(
                        id=f"section-{len(bounded) + 1:02d}",
                        heading=section.heading,
                        source_markdown="\n\n".join(current),
                    )
                )
                current = [paragraph]
            else:
                current.append(paragraph)
        if current:
            bounded.append(
                ResumeSection(
                    id=f"section-{len(bounded) + 1:02d}",
                    heading=section.heading,
                    source_markdown="\n\n".join(current),
                )
            )
    return [item.model_copy(update={"id": f"section-{index:02d}"}) for index, item in enumerate(bounded, 1)]


def merge_sections(sections: list[GeneratedSection | VerifiedSection]) -> str:
    content = [
        item.markdown if isinstance(item, GeneratedSection) else item.corrected_markdown
        for item in sections
    ]
    return "\n\n".join(part.strip() for part in content if part.strip()).strip() + "\n"
