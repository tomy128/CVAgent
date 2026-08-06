"""Provider-neutral context budgeting for evidence-mapping model calls."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from resume_agent.domain import EvidenceChunk, Requirement, RequirementRetrieval


PROMPT_OVERHEAD_TOKENS = 500
MAX_CANDIDATES_PER_REQUIREMENT = 5


def estimate_tokens(text: str) -> int:
    """Conservatively estimate mixed English and CJK token usage.

    This intentionally favors extra batches over provider-specific tokenizers.
    Context-overflow handling remains the final guard for tokenizer differences.
    """

    ascii_count = sum(character.isascii() for character in text)
    non_ascii_count = len(text) - ascii_count
    return max(1, math.ceil(ascii_count / 4) + non_ascii_count)


@dataclass(frozen=True)
class ContextBudget:
    context_window: int = 4096
    max_output_tokens: int = 4096
    prompt_overhead_tokens: int = PROMPT_OVERHEAD_TOKENS

    @property
    def safety_tokens(self) -> int:
        return math.ceil(self.context_window * 0.10)

    @property
    def output_tokens(self) -> int:
        target = max(512, math.floor(self.context_window * 0.25))
        return min(self.max_output_tokens, target)

    @property
    def input_tokens(self) -> int:
        available = (
            self.context_window
            - self.safety_tokens
            - self.output_tokens
            - self.prompt_overhead_tokens
        )
        if available < 256:
            raise ValueError(
                "Context window leaves fewer than 256 tokens for evidence input"
            )
        return available


@dataclass(frozen=True)
class EvidenceAssignment:
    requirement: Requirement
    candidates: tuple[EvidenceChunk, ...]

    def without_lowest_ranked_candidate(self) -> "EvidenceAssignment":
        if len(self.candidates) <= 1:
            return self
        return EvidenceAssignment(self.requirement, self.candidates[:-1])


@dataclass(frozen=True)
class EvidenceBatch:
    assignments: tuple[EvidenceAssignment, ...]

    @property
    def requirements(self) -> list[Requirement]:
        return [item.requirement for item in self.assignments]

    @property
    def candidates(self) -> list[EvidenceChunk]:
        unique: dict[str, EvidenceChunk] = {}
        for assignment in self.assignments:
            for candidate in assignment.candidates:
                unique.setdefault(candidate.id, candidate)
        return list(unique.values())

    def split(self) -> tuple["EvidenceBatch", "EvidenceBatch"]:
        midpoint = len(self.assignments) // 2
        if midpoint == 0:
            raise ValueError("A single-requirement batch cannot be split")
        return EvidenceBatch(self.assignments[:midpoint]), EvidenceBatch(
            self.assignments[midpoint:]
        )


def select_candidates(
    requirements: list[Requirement],
    chunks: list[EvidenceChunk],
    retrievals: list[RequirementRetrieval],
    limit: int = MAX_CANDIDATES_PER_REQUIREMENT,
) -> list[EvidenceAssignment]:
    """Join ranked retrieval IDs to immutable evidence chunks."""

    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    retrievals_by_requirement = {item.requirement_id: item for item in retrievals}
    assignments = []
    for requirement in requirements:
        retrieval = retrievals_by_requirement.get(requirement.id)
        ranked = retrieval.hits[:limit] if retrieval else []
        candidates = tuple(
            chunks_by_id[hit.evidence_id]
            for hit in ranked
            if hit.evidence_id in chunks_by_id
        )
        assignments.append(EvidenceAssignment(requirement, candidates))
    return assignments


def batch_payload(batch: EvidenceBatch) -> tuple[str, str]:
    """Serialize only fields the evidence mapper needs."""

    requirements = [
        {
            "id": assignment.requirement.id,
            "description": assignment.requirement.description,
            "priority": assignment.requirement.priority,
            "keywords": assignment.requirement.keywords,
            "candidate_ids": [item.id for item in assignment.candidates],
        }
        for assignment in batch.assignments
    ]
    candidates = [
        {"id": item.id, "source": item.source, "content": item.content}
        for item in batch.candidates
    ]
    return (
        json.dumps(requirements, ensure_ascii=False, separators=(",", ":")),
        json.dumps(candidates, ensure_ascii=False, separators=(",", ":")),
    )


def estimate_batch_tokens(batch: EvidenceBatch) -> int:
    requirements, candidates = batch_payload(batch)
    return estimate_tokens(requirements) + estimate_tokens(candidates)


def _fit_single_assignment(
    assignment: EvidenceAssignment, budget: ContextBudget
) -> EvidenceAssignment:
    fitted = assignment
    while (
        len(fitted.candidates) > 1
        and estimate_batch_tokens(EvidenceBatch((fitted,))) > budget.input_tokens
    ):
        fitted = fitted.without_lowest_ranked_candidate()
    return fitted


def plan_batches(
    assignments: list[EvidenceAssignment], budget: ContextBudget
) -> list[EvidenceBatch]:
    """Greedily pack requirements without crossing the conservative input budget."""

    batches: list[EvidenceBatch] = []
    current: list[EvidenceAssignment] = []
    for raw_assignment in assignments:
        assignment = _fit_single_assignment(raw_assignment, budget)
        proposed = EvidenceBatch(tuple([*current, assignment]))
        if current and estimate_batch_tokens(proposed) > budget.input_tokens:
            batches.append(EvidenceBatch(tuple(current)))
            current = [assignment]
        else:
            current.append(assignment)
    if current:
        batches.append(EvidenceBatch(tuple(current)))
    return batches


def is_context_overflow(error: Exception) -> bool:
    """Recognize common provider-neutral context overflow signals."""

    if type(error).__name__ in {"LengthFinishReasonError", "ContextOverflowError"}:
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "context length",
            "context window",
            "maximum context",
            "max context",
            "length limit was reached",
            "too many tokens",
        )
    )
