"""LangGraph workflow for auditable resume tailoring."""

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from resume_agent.backends import AgentBackend
from resume_agent.models import (
    DraftPackage,
    EvidenceChunk,
    EvidenceMap,
    Requirement,
    RequirementRetrieval,
    VerificationResult,
)
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever


class ResumeState(TypedDict, total=False):
    jd_text: str
    master_resume: str
    evidence_chunks: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    evidence_map: dict[str, Any]
    draft: dict[str, Any]
    verification: dict[str, Any]
    retrieval_attempt: int
    retrieval_history: list[dict[str, Any]]
    retry_reason: str
    final_resume: str
    review_status: str


def build_graph(
    backend: AgentBackend,
    checkpointer: Any,
    retriever: HybridRetriever | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
):
    retrieval_engine = retriever or HybridRetriever(DeterministicHashEmbeddings(size=64))

    def observed(name: str, function: Callable[[ResumeState], dict[str, Any]]):
        def wrapped(state: ResumeState) -> dict[str, Any]:
            if event_sink:
                event_sink({"type": "node_started", "node": name, "status": "running"})
            try:
                result = function(state)
            except Exception as error:
                if event_sink:
                    event_sink(
                        {
                            "type": "node_failed",
                            "node": name,
                            "status": "failed",
                            "error_type": type(error).__name__,
                        }
                    )
                raise
            if event_sink:
                event_sink({"type": "node_completed", "node": name, "status": "complete"})
            return result

        return wrapped

    def extract_requirements(state: ResumeState) -> dict[str, Any]:
        result = backend.extract_requirements(state["jd_text"])
        return {"requirements": [item.model_dump() for item in result.requirements]}

    def build_evidence_index(state: ResumeState) -> dict[str, Any]:
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        retrieval_engine.build(chunks)
        return {
            "retrieval_attempt": state.get("retrieval_attempt", 0),
            "retrieval_history": state.get("retrieval_history", []),
        }

    def retrieve_evidence(state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        attempt = state.get("retrieval_attempt", 0)
        verification = VerificationResult.model_validate(state["verification"]) if attempt else None
        retry_context = [item.claim for item in verification.unsupported_claims] if verification else []
        retrievals = [
            retrieval_engine.retrieve(requirement, chunks, attempt, retry_context)
            for requirement in requirements
        ]
        if attempt:
            previous = {
                item.requirement_id: item
                for item in (
                    RequirementRetrieval.model_validate(raw)
                    for raw in state.get("retrieval_history", [])
                )
                if item.attempt == 0
            }
            retrievals = [
                item.model_copy(
                    update={
                        "hits": [
                            *item.hits,
                            *[
                                hit
                                for hit in previous.get(item.requirement_id, item).hits
                                if hit.evidence_id not in {current.evidence_id for current in item.hits}
                            ],
                        ]
                    }
                )
                for item in retrievals
            ]
        candidate_ids = {
            hit.evidence_id for retrieval in retrievals for hit in retrieval.hits
        }
        candidates = [item for item in chunks if item.id in candidate_ids]
        result = backend.map_evidence(requirements, candidates)
        history = [*state.get("retrieval_history", []), *[item.model_dump() for item in retrievals]]
        return {"evidence_map": result.model_dump(), "retrieval_history": history}

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

    def route_after_verification(state: ResumeState) -> str:
        result = VerificationResult.model_validate(state["verification"])
        if result.unsupported_claims and state.get("retrieval_attempt", 0) < 1:
            return "prepare_retry"
        return "safety_gate"

    def prepare_retry(state: ResumeState) -> dict[str, Any]:
        result = VerificationResult.model_validate(state["verification"])
        return {
            "retrieval_attempt": 1,
            "retry_reason": "; ".join(item.claim for item in result.unsupported_claims),
        }

    def safety_gate(state: ResumeState) -> dict[str, Any]:
        result = VerificationResult.model_validate(state["verification"])
        draft = DraftPackage.model_validate(state["draft"])
        valid_ids = {
            EvidenceChunk.model_validate(item).id for item in state["evidence_chunks"]
        }
        invalid_claims = [
            claim.text
            for claim in result.supported_claims
            if not claim.evidence_ids or any(item not in valid_ids for item in claim.evidence_ids)
        ]
        classified = {
            " ".join(claim.text.lower().split()) for claim in result.supported_claims
        } | {
            " ".join(issue.claim.lower().split()) for issue in result.unsupported_claims
        }
        unclassified = [
            claim.text
            for claim in draft.claims
            if " ".join(claim.text.lower().split()) not in classified
        ]
        normalized_resume = " ".join(result.corrected_resume_markdown.lower().split())
        remaining = [
            item.claim
            for item in result.unsupported_claims
            if " ".join(item.claim.lower().split()) in normalized_resume
        ]
        if invalid_claims or unclassified or remaining:
            details = ", ".join([*invalid_claims, *unclassified, *remaining])
            raise RuntimeError(f"Final evidence safety gate failed: {details}")
        return {}

    def human_review(state: ResumeState) -> Command:
        verification = VerificationResult.model_validate(state["verification"])
        if event_sink:
            event_sink(
                {"type": "review_required", "node": "human_review", "status": "waiting"}
            )
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
    builder.add_node("extract_requirements", observed("extract_requirements", extract_requirements))
    builder.add_node("build_evidence_index", observed("build_evidence_index", build_evidence_index))
    builder.add_node("retrieve_evidence", observed("retrieve_evidence", retrieve_evidence))
    builder.add_node("draft_resume", observed("draft_resume", draft_resume))
    builder.add_node("verify_claims", observed("verify_claims", verify_claims))
    builder.add_node("prepare_retry", observed("prepare_retry", prepare_retry))
    builder.add_node("safety_gate", observed("safety_gate", safety_gate))
    builder.add_node("human_review", human_review, ends=("finalize", "reject"))
    builder.add_node("finalize", observed("finalize", finalize))
    builder.add_node("reject", observed("reject", reject))
    builder.add_edge(START, "extract_requirements")
    builder.add_edge("extract_requirements", "build_evidence_index")
    builder.add_edge("build_evidence_index", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "draft_resume")
    builder.add_edge("draft_resume", "verify_claims")
    builder.add_conditional_edges("verify_claims", route_after_verification)
    builder.add_edge("prepare_retry", "retrieve_evidence")
    builder.add_edge("safety_gate", "human_review")
    builder.add_edge("finalize", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=checkpointer)
