"""Deterministic and LangChain-backed reasoning implementations."""

import re
from abc import ABC, abstractmethod

from langchain_openai import ChatOpenAI

from resume_agent.evidence import search_evidence, tokenize
from resume_agent.models import (
    DraftPackage,
    EvidenceChunk,
    EvidenceMap,
    EvidenceMatch,
    Requirement,
    RequirementSet,
    ResumeClaim,
    VerificationResult,
)


class AgentBackend(ABC):
    @abstractmethod
    def extract_requirements(self, jd_text: str) -> RequirementSet: ...

    @abstractmethod
    def map_evidence(
        self, requirements: list[Requirement], chunks: list[EvidenceChunk]
    ) -> EvidenceMap: ...

    @abstractmethod
    def draft_resume(
        self,
        jd_text: str,
        master_resume: str,
        requirements: list[Requirement],
        evidence_map: EvidenceMap,
        chunks: list[EvidenceChunk],
    ) -> DraftPackage: ...

    @abstractmethod
    def verify_resume(
        self, draft: DraftPackage, chunks: list[EvidenceChunk]
    ) -> VerificationResult: ...


class HeuristicBackend(AgentBackend):
    """Offline backend for workflow verification; it never invents resume prose."""

    def extract_requirements(self, jd_text: str) -> RequirementSet:
        lines = [
            re.sub(r"^[\s\-*\d.、]+", "", line).strip()
            for line in jd_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        requirements = []
        for index, line in enumerate(lines[:12], start=1):
            keywords = sorted(tokenize(line), key=lambda item: (-len(item), item))[:8]
            requirements.append(
                Requirement(
                    id=f"req-{index:02d}",
                    category="job requirement",
                    description=line,
                    keywords=keywords,
                )
            )
        return RequirementSet(requirements=requirements)

    def map_evidence(
        self, requirements: list[Requirement], chunks: list[EvidenceChunk]
    ) -> EvidenceMap:
        matches = []
        for requirement in requirements:
            found = search_evidence(requirement, chunks)
            matches.append(
                EvidenceMatch(
                    requirement_id=requirement.id,
                    evidence_ids=[chunk.id for chunk in found],
                    coverage="strong" if len(found) >= 2 else "partial" if found else "missing",
                    rationale="Deterministic lexical overlap; review before relying on it.",
                )
            )
        return EvidenceMap(matches=matches)

    def draft_resume(
        self,
        jd_text: str,
        master_resume: str,
        requirements: list[Requirement],
        evidence_map: EvidenceMap,
        chunks: list[EvidenceChunk],
    ) -> DraftPackage:
        questions = [f"请说明你与该要求相关的真实案例：{item.description}" for item in requirements[:8]]
        return DraftPackage(
            resume_markdown=master_resume,
            claims=[],
            interview_questions=questions,
        )

    def verify_resume(
        self, draft: DraftPackage, chunks: list[EvidenceChunk]
    ) -> VerificationResult:
        return VerificationResult(
            corrected_resume_markdown=draft.resume_markdown,
            supported_claims=draft.claims,
            unsupported_claims=[],
        )


class LangChainBackend(AgentBackend):
    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        self.model = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            timeout=90,
            max_retries=2,
        )

    def extract_requirements(self, jd_text: str) -> RequirementSet:
        structured = self.model.with_structured_output(RequirementSet)
        return structured.invoke(
            "Extract concrete job requirements from the JD. Assign stable IDs req-01, "
            "req-02, and so on. Separate required, preferred, and context. Do not add "
            f"requirements that are absent.\n\nJD:\n{jd_text}"
        )

    def map_evidence(
        self, requirements: list[Requirement], chunks: list[EvidenceChunk]
    ) -> EvidenceMap:
        candidates = {
            requirement.id: [chunk.model_dump() for chunk in search_evidence(requirement, chunks, 6)]
            for requirement in requirements
        }
        structured = self.model.with_structured_output(EvidenceMap)
        return structured.invoke(
            "Map every requirement to only the supplied evidence IDs. Mark missing when "
            "the evidence does not demonstrate the requirement. Never infer employment, "
            "production use, duration, scale, or outcomes.\n\n"
            f"Requirements:\n{RequirementSet(requirements=requirements).model_dump_json()}\n\n"
            f"Candidate evidence:\n{candidates}"
        )

    def draft_resume(
        self,
        jd_text: str,
        master_resume: str,
        requirements: list[Requirement],
        evidence_map: EvidenceMap,
        chunks: list[EvidenceChunk],
    ) -> DraftPackage:
        allowed_ids = {evidence_id for match in evidence_map.matches for evidence_id in match.evidence_ids}
        allowed = [chunk.model_dump() for chunk in chunks if chunk.id in allowed_ids]
        structured = self.model.with_structured_output(DraftPackage)
        return structured.invoke(
            "Tailor the master resume to the JD using only supplied evidence. Preserve factual "
            "dates, employers, technologies, scale, and outcomes. Every changed or newly "
            "emphasized factual claim must list supporting evidence IDs. Omit unsupported JD "
            "requirements rather than fabricating them. Return concise Markdown and interview "
            "questions that probe the strongest matches and gaps.\n\n"
            f"JD:\n{jd_text}\n\nMaster resume:\n{master_resume}\n\n"
            f"Requirements:\n{RequirementSet(requirements=requirements).model_dump_json()}\n\n"
            f"Evidence map:\n{evidence_map.model_dump_json()}\n\nEvidence:\n{allowed}"
        )

    def verify_resume(
        self, draft: DraftPackage, chunks: list[EvidenceChunk]
    ) -> VerificationResult:
        evidence_by_id = {chunk.id: chunk.model_dump() for chunk in chunks}
        cited = {
            evidence_id: evidence_by_id[evidence_id]
            for claim in draft.claims
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_by_id
        }
        structured = self.model.with_structured_output(VerificationResult)
        return structured.invoke(
            "Act as a strict resume fact checker. A claim is supported only when cited evidence "
            "explicitly demonstrates it. Remove or weaken unsupported claims in the corrected "
            "resume. Do not replace them with new facts. Preserve the rest of the resume.\n\n"
            f"Draft:\n{draft.model_dump_json()}\n\nCited evidence:\n{cited}"
        )
