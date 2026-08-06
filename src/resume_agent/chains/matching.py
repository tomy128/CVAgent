"""Map one context-bounded requirement batch to evidence."""

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.context_budget import EvidenceBatch, batch_payload
from resume_agent.domain import MatchBatchResult, RequirementMatch
from resume_agent.evidence import search_evidence


class MatchingChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(self, batch: EvidenceBatch) -> MatchBatchResult:
        if self.model is None:
            return MatchBatchResult(
                matches=[
                    self._heuristic_match(assignment.requirement, list(assignment.candidates))
                    for assignment in batch.assignments
                ]
            )
        requirements, candidates = batch_payload(batch)
        result = invoke_structured(
            self.model,
            MatchBatchResult,
            "Classify each requirement as strong, partial, transferable, or gap. Cite only "
            "candidate IDs assigned to that requirement. Similar experience is transferable, "
            "not direct experience. Never invent facts.",
            "Requirements:\n{requirements}\n\nEvidence:\n{candidates}",
            {"requirements": requirements, "candidates": candidates},
        )
        self._validate(batch, result)
        return result

    @staticmethod
    def _heuristic_match(requirement, candidates) -> RequirementMatch:
        found = search_evidence(requirement, candidates)
        status = "strong" if len(found) >= 2 else "partial" if found else "gap"
        return RequirementMatch(
            requirement_id=requirement.id,
            status=status,
            evidence_ids=[item.id for item in found],
            rationale="Deterministic lexical overlap for demo mode.",
            missing_capability="No direct evidence found." if not found else "",
        )

    @staticmethod
    def _validate(batch: EvidenceBatch, result: MatchBatchResult) -> None:
        expected = {item.requirement.id for item in batch.assignments}
        actual = [item.requirement_id for item in result.matches]
        if set(actual) != expected or len(actual) != len(set(actual)):
            raise RuntimeError("Requirement matcher returned missing or duplicate results")
        allowed = {
            item.requirement.id: {candidate.id for candidate in item.candidates}
            for item in batch.assignments
        }
        for match in result.matches:
            if any(item not in allowed[match.requirement_id] for item in match.evidence_ids):
                raise RuntimeError("Requirement matcher cited unassigned evidence")
            if match.status in {"strong", "partial", "transferable"} and not match.evidence_ids:
                raise RuntimeError("Supported match status requires evidence")
