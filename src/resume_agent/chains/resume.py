"""Generate and verify one resume section at a time."""

import json

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.domain import (
    EvidenceChunk,
    GeneratedSection,
    Requirement,
    RequirementMatch,
    ResumeSection,
    VerificationIssue,
    VerifiedSection,
)


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
    ) -> GeneratedSection:
        if self.model is None:
            return GeneratedSection(section_id=section.id, markdown=section.source_markdown)
        result = self._generate(section, requirements, matches, evidence)
        issues = self._grounding_issues(result, section, evidence)
        if not issues:
            return result

        repaired = self._generate(
            section,
            requirements,
            matches,
            evidence,
            previous=result,
            issues=issues,
        )
        repaired_issues = self._grounding_issues(repaired, section, evidence)
        if repaired_issues:
            raise SectionGroundingError(repaired_issues)
        return repaired

    def _generate(
        self,
        section: ResumeSection,
        requirements: list[Requirement],
        matches: list[RequirementMatch],
        evidence: list[EvidenceChunk],
        previous: GeneratedSection | None = None,
        issues: list[str] | None = None,
    ) -> GeneratedSection:
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
            GeneratedSection,
            "Rewrite this resume section for the job using only supplied evidence. Preserve "
            "facts. Claims must be verified or reframed and cite evidence IDs. Never include "
            "aspirational content in the application resume.",
            "Section ID: {section_id}\nSource section:\n{section}\n\nRequirements and "
            "matches:\n{matches}\n\nEvidence:\n{evidence}{repair_context}",
            {
                "section_id": section.id,
                "section": section.source_markdown,
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
            },
        )

    @staticmethod
    def _grounding_issues(
        result: GeneratedSection,
        section: ResumeSection,
        evidence: list[EvidenceChunk],
    ) -> list[str]:
        issues: list[str] = []
        if result.section_id != section.id:
            issues.append("Resume generator changed the section ID")
        valid_ids = {item.id for item in evidence}
        for claim in result.claims:
            if claim.status == "aspirational":
                issues.append(f"Aspirational claim is forbidden: {claim.text}")
            if not claim.evidence_ids or any(item not in valid_ids for item in claim.evidence_ids):
                issues.append(f"Claim lacks assigned evidence: {claim.text}")
            if claim.status == "reframed" and (not claim.original_text or not claim.rationale):
                issues.append(f"Reframed claim lacks provenance: {claim.text}")
        return issues


class VerificationChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, section: GeneratedSection, evidence: list[EvidenceChunk]
    ) -> VerifiedSection:
        if self.model is None:
            return VerifiedSection(
                section_id=section.section_id,
                corrected_markdown=section.markdown,
                supported_claims=section.claims,
            )
        result = invoke_structured(
            self.model,
            VerifiedSection,
            "Verify every factual change in this application-resume section against supplied "
            "evidence. Remove or weaken unsupported content. Aspirational claims are forbidden.",
            "Generated section:\n{section}\n\nCited evidence:\n{evidence}",
            {
                "section": section.model_dump_json(),
                "evidence": json.dumps(
                    [item.model_dump() for item in evidence], ensure_ascii=False
                ),
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
        })
