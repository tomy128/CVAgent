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
        return self._normalize(batch, result)

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
    def _normalize(batch: EvidenceBatch, result: MatchBatchResult) -> MatchBatchResult:
        allowed = {
            item.requirement.id: {candidate.id for candidate in item.candidates}
            for item in batch.assignments
        }
        returned: dict[str, RequirementMatch] = {}
        warnings = list(result.warnings)
        for match in result.matches:
            if match.requirement_id not in allowed:
                warnings.append(
                    f"Ignored matcher result for unknown requirement {match.requirement_id}."
                )
                continue
            if match.requirement_id in returned:
                warnings.append(
                    f"Ignored duplicate matcher result for {match.requirement_id}."
                )
                continue
            valid_ids = [item for item in match.evidence_ids if item in allowed[match.requirement_id]]
            if valid_ids != match.evidence_ids:
                warnings.append(
                    f"Removed unassigned evidence references from {match.requirement_id}."
                )
            normalized = match.model_copy(update={"evidence_ids": valid_ids})
            if normalized.status in {"strong", "partial", "transferable"} and not valid_ids:
                normalized = normalized.model_copy(update={
                    "status": "gap",
                    "missing_capability": normalized.missing_capability
                    or "The model returned no assigned evidence for this requirement.",
                    "rationale": normalized.rationale
                    + " The unsupported match was downgraded to a gap.",
                })
                warnings.append(
                    f"Downgraded {match.requirement_id} to gap because no assigned evidence remained."
                )
            returned[match.requirement_id] = normalized

        matches = []
        for assignment in batch.assignments:
            requirement_id = assignment.requirement.id
            match = returned.get(requirement_id)
            if match is None:
                match = RequirementMatch(
                    requirement_id=requirement_id,
                    status="gap",
                    rationale="The model omitted this requirement; treated as an evidence gap.",
                    missing_capability="No reliable match result was returned.",
                )
                warnings.append(f"Created a gap for omitted requirement {requirement_id}.")
            matches.append(match)
        return MatchBatchResult(matches=matches, warnings=warnings)
