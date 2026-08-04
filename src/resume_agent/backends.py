"""Deterministic and LangChain-backed reasoning implementations."""

import re
from abc import ABC, abstractmethod

from langchain_core.prompts import ChatPromptTemplate
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
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Extract concrete job requirements. Assign stable IDs req-01, req-02, "
                    "and so on. Separate required, preferred, and context. Never add absent "
                    "requirements.",
                ),
                ("human", "JD:\n{jd_text}"),
            ]
        )
        chain = prompt | self.model.with_structured_output(RequirementSet)
        return chain.invoke({"jd_text": jd_text})

    def map_evidence(
        self, requirements: list[Requirement], chunks: list[EvidenceChunk]
    ) -> EvidenceMap:
        candidates = {
            requirement.id: [chunk.model_dump() for chunk in search_evidence(requirement, chunks, 6)]
            for requirement in requirements
        }
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Map every requirement to only supplied evidence IDs. Mark missing when "
                    "evidence is insufficient. Never infer employment, production use, "
                    "duration, scale, or outcomes.",
                ),
                ("human", "Requirements:\n{requirements}\n\nCandidate evidence:\n{candidates}"),
            ]
        )
        chain = prompt | self.model.with_structured_output(EvidenceMap)
        return chain.invoke(
            {
                "requirements": RequirementSet(requirements=requirements).model_dump_json(),
                "candidates": str(candidates),
            }
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
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Tailor the master resume using only supplied evidence. Preserve dates, "
                    "employers, technologies, scale, and outcomes. Every changed or emphasized "
                    "factual claim must cite evidence IDs. Omit unsupported requirements. Return "
                    "concise Markdown and interview questions for matches and gaps.",
                ),
                (
                    "human",
                    "JD:\n{jd}\n\nMaster resume:\n{resume}\n\nRequirements:\n{requirements}"
                    "\n\nEvidence map:\n{evidence_map}\n\nEvidence:\n{evidence}",
                ),
            ]
        )
        chain = prompt | self.model.with_structured_output(DraftPackage)
        return chain.invoke(
            {
                "jd": jd_text,
                "resume": master_resume,
                "requirements": RequirementSet(requirements=requirements).model_dump_json(),
                "evidence_map": evidence_map.model_dump_json(),
                "evidence": str(allowed),
            }
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
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Act as a strict resume fact checker. Support claims only when cited evidence "
                    "explicitly demonstrates them. Remove or weaken unsupported claims without "
                    "adding facts, and preserve the rest of the resume.",
                ),
                ("human", "Draft:\n{draft}\n\nCited evidence:\n{evidence}"),
            ]
        )
        chain = prompt | self.model.with_structured_output(VerificationResult)
        return chain.invoke({"draft": draft.model_dump_json(), "evidence": str(cited)})
