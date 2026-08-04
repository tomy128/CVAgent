"""LangGraph workflow for auditable resume tailoring."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from resume_agent.backends import AgentBackend
from resume_agent.models import (
    DraftPackage,
    EvidenceChunk,
    EvidenceMap,
    Requirement,
    VerificationResult,
)


class ResumeState(TypedDict, total=False):
    jd_text: str
    master_resume: str
    evidence_chunks: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    evidence_map: dict[str, Any]
    draft: dict[str, Any]
    verification: dict[str, Any]
    final_resume: str
    review_status: str


def build_graph(backend: AgentBackend, checkpointer: Any):
    def extract_requirements(state: ResumeState) -> dict[str, Any]:
        result = backend.extract_requirements(state["jd_text"])
        return {"requirements": [item.model_dump() for item in result.requirements]}

    def retrieve_evidence(state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        result = backend.map_evidence(requirements, chunks)
        return {"evidence_map": result.model_dump()}

    def draft_resume(state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        result = backend.draft_resume(
            state["jd_text"],
            state["master_resume"],
            requirements,
            EvidenceMap.model_validate(state["evidence_map"]),
            chunks,
        )
        return {"draft": result.model_dump()}

    def verify_claims(state: ResumeState) -> dict[str, Any]:
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        result = backend.verify_resume(DraftPackage.model_validate(state["draft"]), chunks)
        return {"verification": result.model_dump()}

    def human_review(state: ResumeState) -> Command:
        verification = VerificationResult.model_validate(state["verification"])
        response = interrupt(
            {
                "instruction": "Review the verified resume. Approve, edit, or reject it.",
                "resume_markdown": verification.corrected_resume_markdown,
                "unsupported_claims": [item.model_dump() for item in verification.unsupported_claims],
            }
        )
        approved = bool(response.get("approved"))
        edited = str(response.get("resume_markdown") or verification.corrected_resume_markdown)
        return Command(
            update={
                "final_resume": edited,
                "review_status": "approved" if approved else "rejected",
            },
            goto="finalize" if approved else "reject",
        )

    def finalize(state: ResumeState) -> dict[str, str]:
        return {"review_status": "approved"}

    def reject(state: ResumeState) -> dict[str, str]:
        return {"review_status": "rejected"}

    builder = StateGraph(ResumeState)
    builder.add_node("extract_requirements", extract_requirements)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("draft_resume", draft_resume)
    builder.add_node("verify_claims", verify_claims)
    builder.add_node("human_review", human_review, ends=("finalize", "reject"))
    builder.add_node("finalize", finalize)
    builder.add_node("reject", reject)
    builder.add_edge(START, "extract_requirements")
    builder.add_edge("extract_requirements", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "draft_resume")
    builder.add_edge("draft_resume", "verify_claims")
    builder.add_edge("verify_claims", "human_review")
    builder.add_edge("finalize", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=checkpointer)
