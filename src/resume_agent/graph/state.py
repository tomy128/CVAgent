"""Serializable Run state; large runtime objects stay outside checkpoints."""

from typing import Any, TypedDict


class ResumeState(TypedDict, total=False):
    jd_text: str
    master_resume: str
    evidence_chunks: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    retrievals: list[dict[str, Any]]
    matching_batches: list[list[dict[str, Any]]]
    matching_cursor: int
    matches: list[dict[str, Any]]
    resume_sections: list[dict[str, Any]]
    generation_cursor: int
    generated_sections: list[dict[str, Any]]
    verification_cursor: int
    verified_sections: list[dict[str, Any]]
    repair_attempt: int
    application_resume: str
    has_gaps: bool
    growth_plan: dict[str, Any]
    target_resume: str
    interview_prep: dict[str, Any]
    review_status: str
    final_resume: str
