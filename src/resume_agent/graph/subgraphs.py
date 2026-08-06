"""Batch serialization and finite context-overflow degradation helpers."""

from collections.abc import Callable
from typing import Any, TypeVar

from resume_agent.context_budget import (
    EvidenceAssignment,
    EvidenceBatch,
    is_context_overflow,
)
from resume_agent.domain import EvidenceChunk, Requirement


Result = TypeVar("Result")


def serialize_batch(batch: EvidenceBatch) -> list[dict[str, Any]]:
    return [
        {
            "requirement": item.requirement.model_dump(),
            "candidates": [candidate.model_dump() for candidate in item.candidates],
        }
        for item in batch.assignments
    ]


def deserialize_batch(raw: list[dict[str, Any]]) -> EvidenceBatch:
    return EvidenceBatch(
        tuple(
            EvidenceAssignment(
                Requirement.model_validate(item["requirement"]),
                tuple(EvidenceChunk.model_validate(value) for value in item["candidates"]),
            )
            for item in raw
        )
    )


def split_markdown_block(markdown: str) -> list[str]:
    paragraphs = [item.strip() for item in markdown.split("\n\n") if item.strip()]
    if len(paragraphs) < 2:
        return []
    midpoint = len(paragraphs) // 2
    return ["\n\n".join(paragraphs[:midpoint]), "\n\n".join(paragraphs[midpoint:])]


def invoke_with_reduced_evidence(
    function: Callable[[list[EvidenceChunk]], Result],
    evidence: list[EvidenceChunk],
) -> Result:
    selected = evidence
    while True:
        try:
            return function(selected)
        except Exception as error:
            if not is_context_overflow(error) or len(selected) <= 1:
                raise
            selected = selected[:-1]
