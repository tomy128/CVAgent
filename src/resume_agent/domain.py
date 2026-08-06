"""Typed domain contracts shared by chains, graph state, and outputs."""

from typing import Literal

from pydantic import BaseModel, Field


ContentStatus = Literal["verified", "reframed", "aspirational"]
MatchStatus = Literal["strong", "partial", "transferable", "gap"]


class Requirement(BaseModel):
    id: str
    category: str
    description: str
    priority: Literal["required", "preferred", "context"] = "required"
    keywords: list[str] = Field(default_factory=list)


class RequirementSet(BaseModel):
    requirements: list[Requirement]


class EvidenceChunk(BaseModel):
    id: str
    source: str
    content: str
    chunk_index: int = 1
    content_hash: str = ""
    source_kind: Literal["resume", "supplemental"] = "supplemental"


class RetrievalHit(BaseModel):
    evidence_id: str
    methods: list[Literal["lexical", "semantic"]]
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    fused_score: float


class RequirementRetrieval(BaseModel):
    requirement_id: str
    query: str
    attempt: int = 0
    hits: list[RetrievalHit] = Field(default_factory=list)


class RequirementMatch(BaseModel):
    requirement_id: str
    status: MatchStatus
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    current_strength: str = ""
    missing_capability: str = ""


class MatchBatchResult(BaseModel):
    matches: list[RequirementMatch]
    warnings: list[str] = Field(default_factory=list)


class ResumeClaim(BaseModel):
    text: str
    status: ContentStatus
    evidence_ids: list[str] = Field(default_factory=list)
    original_text: str = ""
    rationale: str = ""


class ResumeSection(BaseModel):
    id: str
    heading: str
    source_markdown: str


class GeneratedSection(BaseModel):
    section_id: str
    markdown: str
    claims: list[ResumeClaim] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    claim: str
    reason: str


class VerifiedSection(BaseModel):
    section_id: str
    corrected_markdown: str
    supported_claims: list[ResumeClaim] = Field(default_factory=list)
    unsupported_claims: list[VerificationIssue] = Field(default_factory=list)


class GrowthTask(BaseModel):
    id: str
    requirement_id: str
    target_capability: str
    priority: Literal["high", "medium", "low"]
    estimated_effort: str
    work: str
    acceptance_checks: list[str]
    evidence_to_keep: list[str]
    future_resume_statement: str


class GrowthPlan(BaseModel):
    tasks: list[GrowthTask] = Field(default_factory=list)


class InterviewItem(BaseModel):
    requirement_id: str
    question: str
    answer_points: list[str]
    avoid_claiming: str = ""


class InterviewPrep(BaseModel):
    items: list[InterviewItem] = Field(default_factory=list)
