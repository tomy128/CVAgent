"""Generate and verify one resume section at a time."""

import json

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.domain import (
    EvidenceChunk,
    GeneratedSection,
    Requirement,
    RequirementMatch,
    ResumeClaim,
    ResumeSection,
    VerifiedSection,
)


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
        result = invoke_structured(
            self.model,
            GeneratedSection,
            "Rewrite this resume section for the job using only supplied evidence. Preserve "
            "facts. Claims must be verified or reframed and cite evidence IDs. Never include "
            "aspirational content in the application resume.",
            "Section ID: {section_id}\nSource section:\n{section}\n\nRequirements and "
            "matches:\n{matches}\n\nEvidence:\n{evidence}",
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
            },
        )
        if result.section_id != section.id:
            raise RuntimeError("Resume generator changed the section ID")
        valid_ids = {item.id for item in evidence}
        for claim in result.claims:
            if claim.status == "aspirational":
                raise RuntimeError("Application resume contains aspirational content")
            if not claim.evidence_ids or any(item not in valid_ids for item in claim.evidence_ids):
                raise RuntimeError("Application-resume claim lacks assigned evidence")
            if claim.status == "reframed" and (not claim.original_text or not claim.rationale):
                raise RuntimeError("Reframed claim lacks original wording or rationale")
        return result


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
        if result.section_id != section.section_id:
            raise RuntimeError("Verifier changed the section ID")
        valid_ids = {item.id for item in evidence}
        for claim in result.supported_claims:
            if claim.status == "aspirational" or not claim.evidence_ids:
                raise RuntimeError("Verifier accepted an ungrounded claim")
            if any(item not in valid_ids for item in claim.evidence_ids):
                raise RuntimeError("Verifier cited unavailable evidence")
        return result
