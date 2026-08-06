"""Assemble the visible business topology from typed nodes and pure routes."""

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from resume_agent.chains import ChainBundle
from resume_agent.context_budget import ContextBudget
from resume_agent.graph.nodes import WorkflowNodes
from resume_agent.graph.routes import (
    after_gap_analysis,
    after_generation,
    after_matching,
    after_verification,
    after_verification_batch,
)
from resume_agent.graph.state import ResumeState
from resume_agent.retrieval import HybridRetriever


def build_graph(
    chains: ChainBundle,
    checkpointer: Any,
    retriever: HybridRetriever,
    budget: ContextBudget,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    heartbeat_interval_seconds: float = 5,
):
    workflow = WorkflowNodes(
        chains, retriever, budget, event_sink, heartbeat_interval_seconds
    )
    builder = StateGraph(ResumeState)
    nodes = {
        "extract_requirements": workflow.extract_requirements,
        "build_evidence_index": workflow.build_evidence_index,
        "prepare_matching": workflow.prepare_matching,
        "match_batch": workflow.match_batch,
        "prepare_resume": workflow.prepare_resume,
        "generate_section": workflow.generate_section,
        "prepare_verification": workflow.prepare_verification,
        "verify_section": workflow.verify_section,
        "finalize_verification": workflow.finalize_verification,
        "analyze_gaps": workflow.analyze_gaps,
        "generate_growth_plan": workflow.generate_growth_plan,
        "generate_target_resume": workflow.generate_target_resume,
        "generate_interview_prep": workflow.generate_interview_prep,
        "human_review": workflow.human_review,
    }
    for name, function in nodes.items():
        builder.add_node(name, workflow.observed(name, function))

    builder.add_edge(START, "extract_requirements")
    builder.add_edge("extract_requirements", "build_evidence_index")
    builder.add_edge("build_evidence_index", "prepare_matching")
    builder.add_edge("prepare_matching", "match_batch")
    builder.add_conditional_edges("match_batch", after_matching)
    builder.add_edge("prepare_resume", "generate_section")
    builder.add_conditional_edges("generate_section", after_generation)
    builder.add_edge("prepare_verification", "verify_section")
    builder.add_conditional_edges("verify_section", after_verification_batch)
    builder.add_conditional_edges("finalize_verification", after_verification)
    builder.add_conditional_edges("analyze_gaps", after_gap_analysis)
    builder.add_edge("generate_growth_plan", "generate_target_resume")
    builder.add_edge("generate_target_resume", "generate_interview_prep")
    builder.add_edge("generate_interview_prep", "human_review")
    builder.add_edge("human_review", END)
    return builder.compile(checkpointer=checkpointer)
