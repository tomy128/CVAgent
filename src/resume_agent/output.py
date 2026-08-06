"""Render user-facing generator artifacts from typed Graph state."""

import json
from pathlib import Path
from typing import Any

from resume_agent.domain import (
    GrowthPlan,
    InterviewPrep,
    Requirement,
    RequirementMatch,
    RequirementRetrieval,
)


def _match_report(
    requirements: list[Requirement],
    matches: list[RequirementMatch],
    retrievals: list[RequirementRetrieval],
) -> str:
    match_by_id = {item.requirement_id: item for item in matches}
    retrieval_by_id = {item.requirement_id: item for item in retrievals}
    lines = ["# Match Report", ""]
    for requirement in requirements:
        match = match_by_id[requirement.id]
        retrieval = retrieval_by_id.get(requirement.id)
        methods = sorted({method for hit in retrieval.hits for method in hit.methods}) if retrieval else []
        lines.extend([
            f"## {requirement.id}: {requirement.description}",
            f"- Match: **{match.status}**",
            f"- Priority: {requirement.priority}",
            f"- Evidence: {', '.join(match.evidence_ids) or 'None'}",
            f"- Retrieval: {', '.join(methods) or 'None'}",
            f"- Rationale: {match.rationale}",
        ])
        if match.missing_capability:
            lines.append(f"- Gap: {match.missing_capability}")
        lines.append("")
    return "\n".join(lines)


def _growth_plan(plan: GrowthPlan) -> str:
    lines = ["# Growth Plan", ""]
    if not plan.tasks:
        return "\n".join([*lines, "No important capability gaps were identified.", ""])
    for task in plan.tasks:
        lines.extend([
            f"## {task.id}: {task.target_capability}",
            f"- Requirement: `{task.requirement_id}`",
            f"- Priority: {task.priority}",
            f"- Estimated effort: {task.estimated_effort}",
            f"- Work: {task.work}",
            "- Acceptance:",
            *[f"  - {item}" for item in task.acceptance_checks],
            "- Evidence to keep:",
            *[f"  - {item}" for item in task.evidence_to_keep],
            f"- Future resume statement: {task.future_resume_statement}",
            "",
        ])
    return "\n".join(lines)


def _interview_prep(prep: InterviewPrep) -> str:
    lines = ["# Interview Preparation", ""]
    for item in prep.items:
        lines.extend([
            f"## {item.requirement_id}: {item.question}",
            *[f"- {point}" for point in item.answer_points],
        ])
        if item.avoid_claiming:
            lines.append(f"- **Do not claim:** {item.avoid_claiming}")
        lines.append("")
    return "\n".join(lines)


def write_artifacts(run_dir: Path, state: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    requirements = [Requirement.model_validate(item) for item in state.get("requirements", [])]
    matches = [RequirementMatch.model_validate(item) for item in state.get("matches", [])]
    retrievals = [RequirementRetrieval.model_validate(item) for item in state.get("retrievals", [])]
    plan = GrowthPlan.model_validate(state.get("growth_plan", {}))
    prep = InterviewPrep.model_validate(state.get("interview_prep", {}))
    application_resume = state.get("final_resume") or state.get("application_resume", "")

    artifacts = {
        "application-resume.md": application_resume,
        "match-report.md": _match_report(requirements, matches, retrievals),
        "growth-plan.md": _growth_plan(plan),
        "interview-prep.md": _interview_prep(prep),
    }
    if state.get("target_resume"):
        artifacts["target-resume.md"] = state["target_resume"]
    for name, content in artifacts.items():
        (run_dir / name).write_text(content.rstrip() + "\n", encoding="utf-8")

    summary = {
        "status": state.get("review_status", "waiting_review"),
        "requirement_count": len(requirements),
        "match_counts": {
            status: sum(item.status == status for item in matches)
            for status in ("strong", "partial", "transferable", "gap")
        },
        "growth_task_count": len(plan.tasks),
        "repair_attempt": state.get("repair_attempt", 0),
        "matching_batches": len(state.get("matching_batches", [])),
        "resume_sections": len(state.get("resume_sections", [])),
        "retrievals": [item.model_dump() for item in retrievals],
    }
    (run_dir / "run.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_failure_artifacts(
    run_dir: Path, state: dict[str, Any], issues: list[dict[str, str]]
) -> None:
    if state.get("application_resume"):
        (run_dir / "unsafe-draft.md").write_text(
            state["application_resume"], encoding="utf-8"
        )
    lines = [
        "# Evidence Safety Failure",
        "",
        "The application resume still contains unsupported claims after one repair pass.",
        "",
        "## Required changes",
        "",
    ]
    for issue in issues:
        lines.extend([f"- {issue['claim']}", f"  - Reason: {issue['reason']}"])
    (run_dir / "failure-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
