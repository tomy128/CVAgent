"""Typed workflow inputs and outputs."""

from typing import Literal

from pydantic import BaseModel, Field


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


class EvidenceMatch(BaseModel):
    requirement_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    coverage: Literal["strong", "partial", "missing"] = "missing"
    rationale: str = ""


class EvidenceMap(BaseModel):
    matches: list[EvidenceMatch]


class ResumeClaim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class DraftPackage(BaseModel):
    resume_markdown: str
    claims: list[ResumeClaim] = Field(default_factory=list)
    interview_questions: list[str] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    claim: str
    reason: str


class VerificationResult(BaseModel):
    corrected_resume_markdown: str
    supported_claims: list[ResumeClaim] = Field(default_factory=list)
    unsupported_claims: list[VerificationIssue] = Field(default_factory=list)
