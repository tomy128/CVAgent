import pytest

from resume_agent.context_budget import (
    ContextBudget,
    EvidenceBatch,
    batch_payload,
    estimate_batch_tokens,
    estimate_tokens,
    plan_batches,
    select_candidates,
)
from resume_agent.domain import (
    EvidenceChunk,
    Requirement,
    RequirementRetrieval,
    RetrievalHit,
)
from resume_agent.sections import split_markdown_sections
from resume_agent.graph.subgraphs import invoke_with_reduced_evidence


def requirement(index: int) -> Requirement:
    return Requirement(
        id=f"req-{index:02d}",
        category="skill",
        description=f"Requirement {index} " + "Python backend " * 8,
        keywords=["Python", "backend"],
    )


def retrieval(requirement_id: str, evidence_ids: list[str]) -> RequirementRetrieval:
    return RequirementRetrieval(
        requirement_id=requirement_id,
        query="Python backend",
        hits=[
            RetrievalHit(
                evidence_id=evidence_id,
                methods=["semantic"],
                semantic_rank=index,
                fused_score=1 / index,
            )
            for index, evidence_id in enumerate(evidence_ids, start=1)
        ],
    )


def chunks(count: int, size: int = 180) -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            id=f"ev-{index}",
            source="resume.md",
            content=(f"Evidence {index} Python backend " * size),
        )
        for index in range(1, count + 1)
    ]


def test_estimator_is_conservative_for_non_ascii_text() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("简历事实") == 4
    assert estimate_tokens("Python工程师") >= 4


def test_selection_uses_ranked_top_five_and_deduplicates_shared_body() -> None:
    requirements = [requirement(1), requirement(2)]
    evidence = chunks(7, size=1)
    assignments = select_candidates(
        requirements,
        evidence,
        [retrieval(item.id, [chunk.id for chunk in evidence]) for item in requirements],
    )
    requirement_payload, evidence_payload = batch_payload(EvidenceBatch(tuple(assignments)))

    assert [item.id for item in assignments[0].candidates] == [
        "ev-1", "ev-2", "ev-3", "ev-4", "ev-5"
    ]
    assert requirement_payload.count('"candidate_ids"') == 2
    assert evidence_payload.count('"id":"ev-1"') == 1


def test_planner_creates_batches_within_input_budget() -> None:
    requirements = [requirement(index) for index in range(1, 4)]
    evidence = chunks(3, size=45)
    assignments = select_candidates(
        requirements,
        evidence,
        [retrieval(item.id, [evidence[index - 1].id]) for index, item in enumerate(requirements, 1)],
    )
    budget = ContextBudget(context_window=2048, max_output_tokens=512)

    batches = plan_batches(assignments, budget)

    assert len(batches) > 1
    assert all(estimate_batch_tokens(batch) <= budget.input_tokens for batch in batches)


def test_long_resume_sections_split_without_truncating_paragraphs() -> None:
    markdown = "# Experience\n\n" + "A" * 800 + "\n\n" + "B" * 800

    sections = split_markdown_sections(markdown, max_tokens=250)

    assert len(sections) == 2
    assert "A" * 800 in sections[0].source_markdown
    assert "B" * 800 in sections[1].source_markdown


def test_context_overflow_reduces_lowest_ranked_evidence_only() -> None:
    calls = []

    def invoke(evidence):
        calls.append([item.id for item in evidence])
        if len(evidence) > 1:
            raise RuntimeError("maximum context length exceeded")
        return evidence[0].id

    result = invoke_with_reduced_evidence(invoke, chunks(3, size=1))

    assert result == "ev-1"
    assert calls == [["ev-1", "ev-2", "ev-3"], ["ev-1", "ev-2"], ["ev-1"]]


def test_non_context_failure_is_not_retried() -> None:
    calls = 0

    def invoke(evidence):
        nonlocal calls
        calls += 1
        raise TimeoutError("model timed out")

    with pytest.raises(TimeoutError):
        invoke_with_reduced_evidence(invoke, chunks(3, size=1))
    assert calls == 1
