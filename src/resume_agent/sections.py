"""Deterministic Markdown sectioning without changing source facts."""

import re

from resume_agent.domain import (
    GeneratedSection,
    ResumeEditDecision,
    ResumeEntry,
    ResumeSection,
    VerifiedSection,
)


HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
BULLET = re.compile(r"^\s*[-*+]\s+(.+)$")


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
    ordered = sorted(enumerate(sections), key=lambda item: (item[1].priority, item[0]))
    content = [
        item.markdown if isinstance(item, GeneratedSection) else item.corrected_markdown
        for _, item in ordered
    ]
    return "\n\n".join(part.strip() for part in content if part.strip()).strip() + "\n"


def parse_resume_entries(section: ResumeSection) -> list[ResumeEntry]:
    """Turn one Markdown section into stable, line-grained editable entries."""

    entries = []
    for line in section.source_markdown.splitlines():
        stripped = line.strip()
        if not stripped or HEADING.match(stripped):
            continue
        bullet = BULLET.match(line)
        entries.append(ResumeEntry(
            id=f"{section.id}-entry-{len(entries) + 1:02d}",
            section_id=section.id,
            kind="bullet" if bullet else "paragraph",
            source_text=(bullet.group(1) if bullet else stripped),
            source_index=len(entries),
        ))
    return entries


def render_resume_section(
    section: ResumeSection,
    entries: list[ResumeEntry],
    decisions: list[ResumeEditDecision],
) -> str:
    """Render trusted edit decisions into stable Markdown owned by the application."""

    decision_by_id = {item.source_entry_id: item for item in decisions}
    ranked = sorted(
        entries,
        key=lambda entry: (
            decision_by_id.get(entry.id, ResumeEditDecision(
                source_entry_id=entry.id, action="keep"
            )).priority,
            entry.source_index,
        ),
    )
    source_heading = next(
        (HEADING.match(line.strip()) for line in section.source_markdown.splitlines()
         if HEADING.match(line.strip())),
        None,
    )
    lines = []
    if source_heading:
        level = "#" if len(source_heading.group(1)) == 1 else "##"
        lines.extend([f"{level} {section.heading}", ""])
    previous_kind = None
    for entry in ranked:
        decision = decision_by_id.get(entry.id)
        if decision and decision.action == "omit":
            continue
        text = (
            _plain_model_text(decision.revised_text)
            if decision and decision.action == "rewrite" and decision.revised_text.strip()
            else entry.source_text
        )
        if entry.kind == "bullet":
            if previous_kind == "paragraph" and lines and lines[-1]:
                lines.append("")
            lines.append(f"- {text}")
        else:
            if lines and lines[-1]:
                lines.append("")
            lines.append(text)
        previous_kind = entry.kind
    return "\n".join(lines).strip()


def _plain_model_text(text: str) -> str:
    """Keep model output as prose; Markdown structure belongs to the renderer."""

    value = re.sub(r"^\s*(?:#{1,6}|[-*+])\s+", "", text.strip())
    return value.replace("<", "&lt;").replace(">", "&gt;")
