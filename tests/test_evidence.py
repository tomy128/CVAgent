from pathlib import Path

import pytest

from resume_agent.evidence import load_evidence, read_text_file, search_evidence, split_text
from resume_agent.models import EvidenceChunk, Requirement


def test_read_text_file_rejects_unsupported_input(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"pdf")
    with pytest.raises(ValueError, match="Unsupported"):
        read_text_file(path)


def test_load_evidence_is_recursive_and_keeps_sources(tmp_path: Path) -> None:
    resume = tmp_path / "resume.md"
    resume.write_text("# Resume\n\nPython and RAG experience", encoding="utf-8")
    evidence = tmp_path / "evidence" / "projects"
    evidence.mkdir(parents=True)
    (evidence / "nonote.md").write_text("Vue 3 desktop application", encoding="utf-8")

    chunks = load_evidence(resume, tmp_path / "evidence")

    assert len(chunks) == 3
    assert {Path(chunk.source).name for chunk in chunks} == {"resume.md", "nonote.md"}
    assert sum(Path(chunk.source).name == "resume.md" for chunk in chunks) == 2


def test_lexical_search_returns_matching_chunks() -> None:
    requirement = Requirement(
        id="req-01",
        category="skill",
        description="LangGraph workflow development",
        keywords=["LangGraph", "workflow"],
    )
    chunks = [
        EvidenceChunk(id="ev-1", source="one.md", content="Built a LangGraph workflow."),
        EvidenceChunk(id="ev-2", source="two.md", content="Managed MySQL databases."),
    ]

    assert [item.id for item in search_evidence(requirement, chunks)] == ["ev-1"]


def test_split_text_bounds_large_paragraphs() -> None:
    assert [len(item) for item in split_text("a" * 2500, max_chars=1000)] == [1000, 1000, 500]
