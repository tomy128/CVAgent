"""Render auditable run artifacts."""

import json
from pathlib import Path
from typing import Any

from resume_agent.models import (
    EvidenceChunk,
    EvidenceMap,
    Requirement,
    RequirementRetrieval,
    VerificationResult,
)


def write_artifacts(run_dir: Path, state: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    requirements = [Requirement.model_validate(item) for item in state.get("requirements", [])]
    evidence_map = EvidenceMap.model_validate(state.get("evidence_map", {"matches": []}))
    verification = VerificationResult.model_validate(state["verification"])
    chunks = {
        item.id: item for item in (
            EvidenceChunk.model_validate(raw) for raw in state.get("evidence_chunks", [])
        )
    }

    match_by_requirement = {item.requirement_id: item for item in evidence_map.matches}
    retrievals = [
        RequirementRetrieval.model_validate(item)
        for item in state.get("retrieval_history", [])
    ]
    latest_retrieval = {item.requirement_id: item for item in retrievals}
    requirement_lines = ["# Requirement Map", ""]
    for requirement in requirements:
        match = match_by_requirement.get(requirement.id)
        coverage = match.coverage if match else "missing"
        evidence_ids = ", ".join(match.evidence_ids) if match and match.evidence_ids else "None"
        retrieval = latest_retrieval.get(requirement.id)
        methods = {
            method for hit in retrieval.hits for method in hit.methods
        } if retrieval else set()
        requirement_lines.extend(
            [
                f"## {requirement.id}: {requirement.description}",
                f"- Priority: {requirement.priority}",
                f"- Coverage: {coverage}",
                f"- Evidence: {evidence_ids}",
                f"- Retrieval: {', '.join(sorted(methods)) or 'None'}",
                f"- Attempt: {retrieval.attempt if retrieval else 0}",
                "",
            ]
        )

    evidence_lines = ["# Evidence Report", ""]
    for evidence_id in sorted({eid for match in evidence_map.matches for eid in match.evidence_ids}):
        chunk = chunks.get(evidence_id)
        if chunk:
            evidence_lines.extend(
                [f"## {chunk.id}", f"Source: `{chunk.source}`", "", chunk.content, ""]
            )
    if verification.unsupported_claims:
        evidence_lines.extend(["# Unsupported Claims", ""])
        for issue in verification.unsupported_claims:
            evidence_lines.extend([f"- {issue.claim}", f"  - Reason: {issue.reason}"])

    questions = state.get("draft", {}).get("interview_questions", [])
    question_lines = ["# Interview Questions", "", *[f"- {item}" for item in questions], ""]

    (run_dir / "requirement-map.md").write_text("\n".join(requirement_lines), encoding="utf-8")
    (run_dir / "evidence-report.md").write_text("\n".join(evidence_lines), encoding="utf-8")
    (run_dir / "interview-questions.md").write_text("\n".join(question_lines), encoding="utf-8")
    (run_dir / "tailored-resume.md").write_text(state.get("final_resume", ""), encoding="utf-8")
    summary = {
        "status": state.get("review_status"),
        "requirement_count": len(requirements),
        "unsupported_claim_count": len(verification.unsupported_claims),
        "retrieval_attempt": state.get("retrieval_attempt", 0),
        "retry_reason": state.get("retry_reason", ""),
        "retrievals": [item.model_dump() for item in retrievals],
    }
    (run_dir / "run.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
