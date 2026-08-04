from resume_agent.models import EvidenceChunk, Requirement
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever


def test_hybrid_retrieval_records_methods_and_favors_lexical_match() -> None:
    chunks = [
        EvidenceChunk(id="ev-python", source="resume.md", content="Built Python APIs"),
        EvidenceChunk(id="ev-rust", source="project.md", content="Built Rust services"),
    ]
    requirement = Requirement(
        id="req-01",
        category="skill",
        description="Python backend development",
        keywords=["Python"],
    )

    result = HybridRetriever(DeterministicHashEmbeddings()).retrieve(requirement, chunks)

    assert result.hits[0].evidence_id == "ev-python"
    assert "lexical" in result.hits[0].methods
    assert "semantic" in result.hits[0].methods
    assert result.attempt == 0


def test_retry_expands_query_and_result_limit() -> None:
    chunks = [
        EvidenceChunk(id=f"ev-{index}", source="resume.md", content=f"Python project {index}")
        for index in range(10)
    ]
    requirement = Requirement(
        id="req-01",
        category="skill",
        description="Python",
        keywords=["Python"],
    )

    result = HybridRetriever(DeterministicHashEmbeddings()).retrieve(
        requirement,
        chunks,
        attempt=1,
        retry_context=["high concurrency"],
    )

    assert result.attempt == 1
    assert "high concurrency" in result.query
    assert len(result.hits) == 8
