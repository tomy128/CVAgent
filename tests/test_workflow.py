from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from resume_agent.chains import build_chain_bundle
from resume_agent.context_budget import ContextBudget
from resume_agent.domain import EvidenceChunk
from resume_agent.graph import build_graph
from resume_agent.retrieval import DeterministicHashEmbeddings, HybridRetriever


def invoke_demo(thread_id: str = "demo"):
    events = []
    graph = build_graph(
        build_chain_bundle(None),
        InMemorySaver(),
        HybridRetriever(DeterministicHashEmbeddings()),
        ContextBudget(4096, 1024),
        event_sink=events.append,
    )
    state = graph.invoke(
        {
            "jd_text": "- Python backend\n- Kubernetes production experience",
            "master_resume": "# Resume\n\nPython backend engineer",
            "evidence_chunks": [
                EvidenceChunk(
                    id="ev-1",
                    source="resume.md",
                    source_kind="resume",
                    content="Python backend engineer",
                ).model_dump()
            ],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return graph, state, events


def test_graph_generates_safe_resume_growth_plan_and_review_interrupt() -> None:
    graph, state, events = invoke_demo()

    assert "__interrupt__" in state
    assert state["application_resume"].strip() == "# Resume\n\nPython backend engineer"
    assert state["growth_plan"]["tasks"]
    assert "NOT FOR SUBMISSION" in state["target_resume"]
    assert any(event.get("phase") == "matching" for event in events)
    assert any(event.get("phase") == "generation" for event in events)
    assert any(event.get("phase") == "verification" for event in events)

    final = graph.invoke(
        Command(resume={"approved": True, "resume_markdown": state["application_resume"]}),
        config={"configurable": {"thread_id": "demo"}},
    )
    assert final["review_status"] == "approved"


def test_each_batch_crosses_a_graph_checkpoint_boundary() -> None:
    graph, state, _ = invoke_demo("checkpoint")
    history = list(graph.get_state_history({"configurable": {"thread_id": "checkpoint"}}))

    completed_nodes = {task.name for snapshot in history for task in snapshot.tasks if task.result is not None}

    assert state["matching_cursor"] >= 1
    assert {"match_batch", "generate_section", "verify_section"} <= completed_nodes
