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
from resume_agent.language import detect_run_languages, message


def _match_report(
    requirements: list[Requirement],
    matches: list[RequirementMatch],
    retrievals: list[RequirementRetrieval],
    warnings: list[str],
    language: str,
) -> str:
    match_by_id = {item.requirement_id: item for item in matches}
    retrieval_by_id = {item.requirement_id: item for item in retrievals}
    lines = [f"# {message(language, 'match_report')}", ""]
    for requirement in requirements:
        match = match_by_id[requirement.id]
        retrieval = retrieval_by_id.get(requirement.id)
        methods = sorted({method for hit in retrieval.hits for method in hit.methods}) if retrieval else []
        lines.extend([
            f"## {requirement.id}: {requirement.description}",
            f"- {message(language, 'match')}: **{match.status}**",
            f"- {message(language, 'priority')}: {requirement.priority}",
            f"- {message(language, 'evidence')}: {', '.join(match.evidence_ids) or message(language, 'none')}",
            f"- {message(language, 'retrieval')}: {', '.join(methods) or message(language, 'none')}",
            f"- {message(language, 'rationale')}: {match.rationale}",
        ])
        if match.missing_capability:
            lines.append(f"- {message(language, 'gap')}: {match.missing_capability}")
        lines.append("")
    if warnings:
        lines.extend([f"## {message(language, 'warnings')}", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    return "\n".join(lines)


def _growth_plan(plan: GrowthPlan, language: str) -> str:
    lines = [f"# {message(language, 'growth_plan')}", ""]
    if not plan.tasks:
        return "\n".join([*lines, message(language, "no_gaps"), ""])
    for task in plan.tasks:
        lines.extend([
            f"## {task.id}: {task.target_capability}",
            f"- {message(language, 'requirement')}: `{task.requirement_id}`",
            f"- {message(language, 'priority')}: {task.priority}",
            f"- {message(language, 'effort')}: {task.estimated_effort}",
            f"- {message(language, 'work')}: {task.work}",
            f"- {message(language, 'acceptance')}:",
            *[f"  - {item}" for item in task.acceptance_checks],
            f"- {message(language, 'evidence_to_keep')}:",
            *[f"  - {item}" for item in task.evidence_to_keep],
            f"- {message(language, 'future_statement')}: {task.future_resume_statement}",
            "",
        ])
    return "\n".join(lines)


def _interview_prep(prep: InterviewPrep, language: str) -> str:
    lines = [f"# {message(language, 'interview_prep')}", ""]
    for item in prep.items:
        lines.extend([
            f"## {item.requirement_id}: {item.question}",
            *[f"- {point}" for point in item.answer_points],
        ])
        if item.avoid_claiming:
            lines.append(f"- **{message(language, 'do_not_claim')}:** {item.avoid_claiming}")
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
    warnings = list(state.get("warnings", []))
    detected_analysis, detected_resume = detect_run_languages(
        state.get("jd_text", ""), state.get("master_resume", "")
    )
    analysis_language = state.get("analysis_language") or detected_analysis.language or "en"
    resume_language = state.get("resume_language") or detected_resume.language or "en"

    artifacts = {
        "application-resume.md": application_resume,
        "match-report.md": _match_report(
            requirements, matches, retrievals, warnings, analysis_language
        ),
        "growth-plan.md": _growth_plan(plan, analysis_language),
        "interview-prep.md": _interview_prep(prep, analysis_language),
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
        "warnings": warnings,
        "schema_version": state.get("schema_version", 1),
        "analysis_language": analysis_language,
        "resume_language": resume_language,
        "language_detection": state.get("language_detection", {}),
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
