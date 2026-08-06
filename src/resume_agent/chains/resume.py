"""Generate and verify one resume section at a time."""

import json
import re

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.domain import (
    EvidenceChunk,
    GeneratedSection,
    Requirement,
    RequirementMatch,
    ResumeClaim,
    ResumeEditDecision,
    ResumeEditResult,
    ResumeSection,
    VerificationIssue,
    VerifiedSection,
)
from resume_agent.language import LANGUAGE_NAMES
from resume_agent.sections import parse_resume_entries, render_resume_section


PROMOTIONAL_PHRASES = (
    "赋能", "深耕", "卓越", "全面提升", "显著推动",
    "results-driven", "spearheaded", "empowered", "significantly improved",
)
TECHNOLOGY_TOKEN = re.compile(
    r"\b(?:Python|Golang|Java|JavaScript|TypeScript|FastAPI|Django|Flask|Vue|React|"
    r"LangChain|LangGraph|Kubernetes|Docker|PostgreSQL|MySQL|Redis|Kafka|AWS|GCP|Azure)\b",
    re.I,
)
NUMBER = re.compile(r"(?<!\w)\d+(?:\.\d+)?%?")


class SectionGroundingError(RuntimeError):
    """The model answered, but its section cannot safely enter the resume."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


class ResumeSectionChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self,
        section: ResumeSection,
        requirements: list[Requirement],
        matches: list[RequirementMatch],
        evidence: list[EvidenceChunk],
        language: str = "en",
        warning_language: str | None = None,
    ) -> GeneratedSection:
        entries = parse_resume_entries(section)
        if self.model is None:
            decisions = [
                ResumeEditDecision(
                    source_entry_id=item.id, action="keep", priority=item.source_index
                )
                for item in entries
            ]
            return GeneratedSection(
                section_id=section.id,
                markdown=render_resume_section(section, entries, decisions),
            )
        if not entries:
            return GeneratedSection(section_id=section.id, markdown=section.source_markdown)
        first = self._generate(section, entries, requirements, matches, evidence, language)
        accepted, invalid = self._normalize(first, entries, evidence)
        warnings = []
        if invalid:
            repair = self._generate(
                section, entries, requirements, matches, evidence, language,
                previous=first, issues=list(invalid.values()),
            )
            repaired, still_invalid = self._normalize(repair, entries, evidence)
            repaired_by_id = {item.source_entry_id: item for item in repaired}
            accepted = [
                repaired_by_id.get(item.source_entry_id, item)
                if item.source_entry_id in invalid
                and item.source_entry_id not in still_invalid
                else item
                for item in accepted
            ]
            warnings = [
                (
                    f"条目 {entry_id} 修复后仍不可靠，已保留原始表述。"
                    if (warning_language or language) == "zh"
                    else f"Entry {entry_id} remained unsafe after one repair and kept its source wording."
                )
                for entry_id in still_invalid
            ]
        markdown = render_resume_section(section, entries, accepted)
        claims = [
            ResumeClaim(
                text=item.revised_text,
                status="reframed",
                evidence_ids=item.evidence_ids,
                original_text=next(
                    entry.source_text for entry in entries if entry.id == item.source_entry_id
                ),
                rationale=item.rationale,
            )
            for item in accepted
            if item.action == "rewrite"
        ]
        return GeneratedSection(
            section_id=section.id,
            markdown=markdown,
            claims=claims,
            priority=(
                -100 if section.id == "section-01"
                else max(0, min(first.section_priority, 1000))
            ),
            warnings=warnings,
        )

    def _generate(
        self,
        section: ResumeSection,
        entries,
        requirements: list[Requirement],
        matches: list[RequirementMatch],
        evidence: list[EvidenceChunk],
        language: str,
        previous: ResumeEditResult | None = None,
        issues: list[str] | None = None,
    ) -> ResumeEditResult:
        repair_context = ""
        if previous is not None:
            repair_context = (
                "\n\nPrevious invalid output:\n"
                + previous.model_dump_json()
                + "\nValidation issues:\n- "
                + "\n- ".join(issues or [])
                + "\nReturn a corrected replacement, not an explanation."
            )
        return invoke_structured(
            self.model,
            ResumeEditResult,
            "Act as a restrained resume editor. Return typed decisions, never Markdown. Default "
            "to keep when source wording is concrete and relevant. Reorder for JD relevance and "
            "rewrite only when clarity requires it. Preserve personal voice, proper nouns, facts, "
            "ownership, numbers, and technologies. Avoid generic promotional language. Every "
            "rewrite must cite assigned evidence. Omit unsupported JD requirements. Write revised "
            "text and rationales in {language}.",
            "Section ID: {section_id}\nSource entries:\n{entries}\n\nRequirements and "
            "matches:\n{matches}\n\nEvidence:\n{evidence}{repair_context}",
            {
                "section_id": section.id,
                "entries": json.dumps([item.model_dump() for item in entries], ensure_ascii=False),
                "matches": json.dumps(
                    [
                        {"requirement": requirement.model_dump(), "match": match.model_dump()}
                        for requirement, match in zip(requirements, matches, strict=False)
                    ],
                    ensure_ascii=False,
                ),
                "evidence": json.dumps(
                    [item.model_dump() for item in evidence], ensure_ascii=False
                ),
                "repair_context": repair_context,
                "language": LANGUAGE_NAMES.get(language, "English"),
            },
        )

    @staticmethod
    def _normalize(
        result: ResumeEditResult,
        entries,
        evidence: list[EvidenceChunk],
    ) -> tuple[list[ResumeEditDecision], dict[str, str]]:
        entry_by_id = {item.id: item for item in entries}
        valid_ids = {item.id for item in evidence}
        evidence_by_id = {item.id: item.content for item in evidence}
        returned = {}
        invalid = {}
        expected_section = entries[0].section_id if entries else ""
        if result.section_id != expected_section:
            invalid.update({
                entry.id: "Resume editor changed the section ID" for entry in entries
            })
        for decision in result.decisions:
            if decision.source_entry_id not in entry_by_id or decision.source_entry_id in returned:
                continue
            issue = invalid.get(decision.source_entry_id, "")
            if decision.action == "rewrite" and (
                not decision.revised_text.strip()
                or not decision.rationale.strip()
                or not decision.evidence_ids
                or any(item not in valid_ids for item in decision.evidence_ids)
            ):
                issue = f"Rewrite for {decision.source_entry_id} lacks grounded provenance"
            if decision.action == "rewrite" and not issue:
                source = entry_by_id[decision.source_entry_id].source_text
                support = " ".join([
                    source,
                    *[
                        evidence_by_id[item]
                        for item in decision.evidence_ids
                        if item in evidence_by_id
                    ],
                ])
                unsupported_numbers = set(NUMBER.findall(decision.revised_text)) - set(
                    NUMBER.findall(support)
                )
                unsupported_technologies = {
                    item.lower()
                    for item in TECHNOLOGY_TOKEN.findall(decision.revised_text)
                } - {
                    item.lower() for item in TECHNOLOGY_TOKEN.findall(support)
                }
                promotional = [
                    phrase
                    for phrase in PROMOTIONAL_PHRASES
                    if phrase.lower() in decision.revised_text.lower()
                    and phrase.lower() not in support.lower()
                ]
                if unsupported_numbers or unsupported_technologies or promotional:
                    issue = (
                        f"Rewrite for {decision.source_entry_id} introduced unsupported "
                        "numbers, technologies, or promotional language"
                    )
            if issue:
                invalid[decision.source_entry_id] = issue
                returned[decision.source_entry_id] = ResumeEditDecision(
                    source_entry_id=decision.source_entry_id,
                    action="keep",
                    priority=decision.priority,
                )
            else:
                returned[decision.source_entry_id] = decision
        decisions = [
            returned.get(entry.id, ResumeEditDecision(
                source_entry_id=entry.id, action="keep", priority=entry.source_index
            ))
            for entry in entries
        ]
        return decisions, invalid


class VerificationChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, section: GeneratedSection, evidence: list[EvidenceChunk], language: str = "en"
    ) -> VerifiedSection:
        if self.model is None:
            return VerifiedSection(
                section_id=section.section_id,
                corrected_markdown=section.markdown,
                supported_claims=section.claims,
                priority=section.priority,
            )
        result = invoke_structured(
            self.model,
            VerifiedSection,
            "Verify every factual change in this application-resume section against supplied "
            "evidence. Remove or weaken unsupported content. Aspirational claims are forbidden. "
            "Keep corrected Markdown in {language}.",
            "Generated section:\n{section}\n\nCited evidence:\n{evidence}",
            {
                "section": section.model_dump_json(),
                "evidence": json.dumps(
                    [item.model_dump() for item in evidence], ensure_ascii=False
                ),
                "language": LANGUAGE_NAMES.get(language, "English"),
            },
        )
        issues = list(result.unsupported_claims)
        if result.section_id != section.section_id:
            issues.append(VerificationIssue(
                claim=section.section_id, reason="Verifier changed the section ID"
            ))
        valid_ids = {item.id for item in evidence}
        supported = []
        for claim in result.supported_claims:
            if claim.status == "aspirational" or not claim.evidence_ids:
                issues.append(VerificationIssue(
                    claim=claim.text, reason="Verifier accepted an ungrounded claim"
                ))
            elif any(item not in valid_ids for item in claim.evidence_ids):
                issues.append(VerificationIssue(
                    claim=claim.text, reason="Verifier cited unavailable evidence"
                ))
            else:
                supported.append(claim)
        return result.model_copy(update={
            "section_id": section.section_id,
            "supported_claims": supported,
            "unsupported_claims": issues,
            "priority": section.priority,
        })
