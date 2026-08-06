from types import SimpleNamespace
from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from resume_agent.chains import build_chain_bundle
from resume_agent.chains.matching import MatchingChain
from resume_agent.chains.planning import GrowthPlanChain
from resume_agent.chains.resume import SectionGroundingError
from resume_agent.context_budget import (
    ContextBudget,
    EvidenceAssignment,
    EvidenceBatch,
)
from resume_agent.domain import (
    EvidenceChunk,
    MatchBatchResult,
    Requirement,
    RequirementMatch,
    GeneratedSection,
)
from resume_agent.graph import build_graph
from resume_agent.graph.nodes import WorkflowNodes
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever


def test_matcher_downgrades_unassigned_evidence_and_fills_omissions() -> None:
    first = Requirement(id="req-1", category="skill", description="Kubernetes")
    second = Requirement(id="req-2", category="skill", description="Go")
    evidence = EvidenceChunk(id="ev-1", source="resume.md", content="Python")
    batch = EvidenceBatch((
        EvidenceAssignment(first, (evidence,)),
        EvidenceAssignment(second, (evidence,)),
    ))
    raw = MatchBatchResult(matches=[RequirementMatch(
        requirement_id="req-1",
        status="strong",
        evidence_ids=["invented-id"],
        rationale="Model claimed a match.",
    )])

    normalized = MatchingChain._normalize(batch, raw)

    assert [item.status for item in normalized.matches] == ["gap", "gap"]
    assert normalized.matches[0].evidence_ids == []
    assert len(normalized.warnings) == 3


def test_each_non_strong_match_has_a_deterministic_growth_task_in_demo_mode() -> None:
    requirements = [
        Requirement(id="req-1", category="skill", description="Kubernetes"),
        Requirement(id="req-2", category="skill", description="Go"),
        Requirement(id="req-3", category="skill", description="Python"),
    ]
    matches = [
        RequirementMatch(
            requirement_id=item.id,
            status=status,
            rationale="No evidence",
        )
        for item, status in zip(
            requirements, ("partial", "transferable", "gap"), strict=True
        )
    ]

    plan = GrowthPlanChain(None).invoke(requirements, matches)

    assert [item.requirement_id for item in plan.tasks] == ["req-1", "req-2", "req-3"]


class FailingResumeChain:
    def invoke(self, *_args, **_kwargs):
        raise SectionGroundingError(["Claim lacks assigned evidence"])


class BrokenResumeChain:
    def invoke(self, *_args, **_kwargs):
        raise ConnectionError("model is unavailable")


def make_nodes(resume_chain) -> WorkflowNodes:
    chains = SimpleNamespace(resume=resume_chain)
    return WorkflowNodes(
        chains,
        HybridRetriever(DeterministicHashEmbeddings()),
        ContextBudget(4096, 1024),
    )


def generation_state() -> dict:
    return {
        "resume_sections": [{
            "id": "section-1",
            "heading": "Experience",
            "source_markdown": "## Experience\n\nPython engineer",
        }],
        "generation_cursor": 0,
        "generated_sections": [],
        "requirements": [],
        "matches": [],
        "evidence_chunks": [{
            "id": "ev-1",
            "source": "resume.md",
            "source_kind": "resume",
            "content": "Python engineer",
        }],
    }


def test_generation_preserves_original_section_after_grounding_failure() -> None:
    result = make_nodes(FailingResumeChain()).generate_section(generation_state())

    assert result["generation_cursor"] == 1
    assert result["generated_sections"][0]["markdown"] == "## Experience\n\nPython engineer"
    assert result["generated_sections"][0]["claims"] == []
    assert "preserved" in result["warnings"][0]


def test_generation_does_not_hide_service_failures() -> None:
    with pytest.raises(ConnectionError, match="model is unavailable"):
        make_nodes(BrokenResumeChain()).generate_section(generation_state())


class ResumeChainThatRecovers:
    def __init__(self) -> None:
        self.failing = True

    def invoke(self, section, *_args, **_kwargs):
        if self.failing:
            raise RuntimeError("old strict validation failure")
        return GeneratedSection(
            section_id=section.id,
            markdown=section.source_markdown,
        )


def test_failed_generation_checkpoint_can_resume() -> None:
    resume_chain = ResumeChainThatRecovers()
    chains = replace(build_chain_bundle(None), resume=resume_chain)
    graph = build_graph(
        chains,
        InMemorySaver(),
        HybridRetriever(DeterministicHashEmbeddings()),
        ContextBudget(4096, 1024),
    )
    config = {"configurable": {"thread_id": "recover-generation"}}

    with pytest.raises(RuntimeError, match="old strict validation failure"):
        graph.invoke({
            "jd_text": "- Python backend",
            "master_resume": "# Resume\n\nPython engineer",
            "evidence_chunks": generation_state()["evidence_chunks"],
        }, config=config)

    resume_chain.failing = False
    state = graph.invoke(None, config=config)

    assert "__interrupt__" in state
    assert state["application_resume"].strip() == "# Resume\n\nPython engineer"
