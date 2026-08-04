from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from resume_agent.backends import HeuristicBackend
from resume_agent.models import EvidenceChunk
from resume_agent.workflow import build_graph


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
