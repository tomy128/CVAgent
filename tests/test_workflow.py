import pytest
import time
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from resume_agent.backends import HeuristicBackend
from resume_agent.models import (
    DraftPackage,
    EvidenceChunk,
    ResumeClaim,
    VerificationIssue,
    VerificationResult,
)
from resume_agent.workflow import SafetyGateError, build_graph


def test_workflow_pauses_for_review_and_resumes() -> None:
    graph = build_graph(HeuristicBackend(), InMemorySaver())
    config = {"configurable": {"thread_id": "test-run"}}
    resume = "# Resume\n\nPython and LangGraph experience."
    initial = graph.invoke(
        {
            "jd_text": "- Python\n- LangGraph",
            "master_resume": resume,
            "evidence_chunks": [
                EvidenceChunk(id="ev-1", source="resume.md", content=resume).model_dump()
            ],
        },
        config=config,
    )

    assert "__interrupt__" in initial
    final = graph.invoke(
        Command(resume={"approved": True, "resume_markdown": resume}),
        config=config,
    )

    assert final["review_status"] == "approved"
    assert final["final_resume"] == resume


class RetryBackend(HeuristicBackend):
    def __init__(self, fail_twice: bool = False) -> None:
        self.calls = 0
        self.fail_twice = fail_twice

    def verify_resume(self, draft, chunks):
        self.calls += 1
        if self.calls == 1 or self.fail_twice:
            return VerificationResult(
                corrected_resume_markdown=(
                    draft.resume_markdown
                    if self.calls == 1 or self.fail_twice
                    else draft.resume_markdown.replace("Python", "")
                ),
                unsupported_claims=[
                    VerificationIssue(claim="Python", reason="Test retry route")
                ],
            )
        return VerificationResult(corrected_resume_markdown=draft.resume_markdown)


def _invoke_retry_graph(backend: RetryBackend, thread_id: str):
    graph = build_graph(backend, InMemorySaver())
    state = graph.invoke(
        {
            "jd_text": "- Python",
            "master_resume": "Python engineer",
            "evidence_chunks": [
                EvidenceChunk(id="ev-1", source="resume.md", content="Python engineer").model_dump()
            ],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return graph, state


def test_workflow_retries_retrieval_once_before_review() -> None:
    backend = RetryBackend()
    _, state = _invoke_retry_graph(backend, "retry-success")

    assert "__interrupt__" in state
    assert state["retrieval_attempt"] == 1
    assert backend.calls == 2
    assert {item["attempt"] for item in state["retrieval_history"]} == {0, 1}
    first = next(item for item in state["retrieval_history"] if item["attempt"] == 0)
    second = next(item for item in state["retrieval_history"] if item["attempt"] == 1)
    assert {hit["evidence_id"] for hit in first["hits"]} <= {
        hit["evidence_id"] for hit in second["hits"]
    }


def test_workflow_stops_when_second_verification_is_still_unsafe() -> None:
    backend = RetryBackend(fail_twice=True)

    with pytest.raises(SafetyGateError, match="safety gate") as caught:
        _invoke_retry_graph(backend, "retry-failure")

    assert backend.calls == 2
    assert caught.value.issues
    assert all(item["claim"] and item["reason"] for item in caught.value.issues)


class UnclassifiedClaimBackend(HeuristicBackend):
    def draft_resume(self, jd_text, master_resume, requirements, evidence_map, chunks):
        return DraftPackage(
            resume_markdown=master_resume,
            claims=[ResumeClaim(text="Python engineer", evidence_ids=["ev-1"])],
        )

    def verify_resume(self, draft, chunks):
        return VerificationResult(corrected_resume_markdown=draft.resume_markdown)


def test_workflow_rejects_claim_omitted_by_verifier() -> None:
    graph = build_graph(UnclassifiedClaimBackend(), InMemorySaver())

    with pytest.raises(RuntimeError, match="safety gate"):
        graph.invoke(
            {
                "jd_text": "- Python",
                "master_resume": "Python engineer",
                "evidence_chunks": [
                    EvidenceChunk(id="ev-1", source="resume.md", content="Python engineer").model_dump()
                ],
            },
            config={"configurable": {"thread_id": "unclassified-claim"}},
        )


def test_workflow_emits_heartbeats_and_node_duration() -> None:
    class SlowBackend(HeuristicBackend):
        def extract_requirements(self, jd_text):
            time.sleep(0.04)
            return super().extract_requirements(jd_text)

    events = []
    graph = build_graph(
        SlowBackend(), InMemorySaver(), event_sink=events.append,
        heartbeat_interval_seconds=0.01,
    )
    graph.invoke(
        {
            "jd_text": "- Python",
            "master_resume": "Python engineer",
            "evidence_chunks": [
                EvidenceChunk(
                    id="ev-1", source="resume.md", content="Python engineer"
                ).model_dump()
            ],
        },
        config={"configurable": {"thread_id": "heartbeat"}},
    )

    heartbeats = [
        event for event in events
        if event["type"] == "node_heartbeat" and event["node"] == "extract_requirements"
    ]
    completed = next(
        event for event in events
        if event["type"] == "node_completed" and event["node"] == "extract_requirements"
    )
    assert heartbeats
    assert completed["duration_seconds"] >= 0.04
