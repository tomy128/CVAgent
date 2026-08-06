"""Map one context-bounded requirement batch to evidence."""

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.context_budget import EvidenceBatch, batch_payload
from resume_agent.domain import MatchBatchResult, RequirementMatch
from resume_agent.evidence import search_evidence
from resume_agent.language import LANGUAGE_NAMES


class MatchingChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(self, batch: EvidenceBatch, language: str = "en") -> MatchBatchResult:
        if self.model is None:
            return MatchBatchResult(
                matches=[
                    self._heuristic_match(
                        assignment.requirement, list(assignment.candidates), language
                    )
                    for assignment in batch.assignments
                ]
            )
        requirements, candidates = batch_payload(batch)
        result = invoke_structured(
            self.model,
            MatchBatchResult,
            "Classify each requirement as strong, partial, transferable, or gap. Cite only "
            "candidate IDs assigned to that requirement. Similar experience is transferable, "
            "not direct experience. Never invent facts. Write explanations in {language}.",
            "Requirements:\n{requirements}\n\nEvidence:\n{candidates}",
            {
                "requirements": requirements,
                "candidates": candidates,
                "language": LANGUAGE_NAMES.get(language, "English"),
            },
        )
        return self._normalize(batch, result, language)

    @staticmethod
    def _heuristic_match(requirement, candidates, language="en") -> RequirementMatch:
        found = search_evidence(requirement, candidates)
        status = "strong" if len(found) >= 2 else "partial" if found else "gap"
        return RequirementMatch(
            requirement_id=requirement.id,
            status=status,
            evidence_ids=[item.id for item in found],
            rationale=(
                "演示模式下使用确定性词汇重合判断。"
                if language == "zh" else "Deterministic lexical overlap for demo mode."
            ),
            missing_capability=(
                "未找到直接证据。" if language == "zh" else "No direct evidence found."
            ) if not found else "",
        )

    @staticmethod
    def _normalize(
        batch: EvidenceBatch, result: MatchBatchResult, language: str = "en"
    ) -> MatchBatchResult:
        zh = language == "zh"
        allowed = {
            item.requirement.id: {candidate.id for candidate in item.candidates}
            for item in batch.assignments
        }
        returned: dict[str, RequirementMatch] = {}
        warnings = list(result.warnings)
        for match in result.matches:
            if match.requirement_id not in allowed:
                warnings.append(
                    ("忽略了未知要求的匹配结果：" if zh else "Ignored matcher result for unknown requirement ")
                    + f"{match.requirement_id}."
                )
                continue
            if match.requirement_id in returned:
                warnings.append(
                    ("忽略了重复匹配结果：" if zh else "Ignored duplicate matcher result for ")
                    + f"{match.requirement_id}."
                )
                continue
            valid_ids = [item for item in match.evidence_ids if item in allowed[match.requirement_id]]
            if valid_ids != match.evidence_ids:
                warnings.append(
                    ("移除了未分配的证据引用：" if zh else "Removed unassigned evidence references from ")
                    + f"{match.requirement_id}."
                )
            normalized = match.model_copy(update={"evidence_ids": valid_ids})
            if normalized.status in {"strong", "partial", "transferable"} and not valid_ids:
                normalized = normalized.model_copy(update={
                    "status": "gap",
                    "missing_capability": normalized.missing_capability
                    or ("模型没有为该要求返回已分配证据。" if zh else "The model returned no assigned evidence for this requirement."),
                    "rationale": normalized.rationale
                    + (" 无可靠证据的匹配已降级为差距。" if zh else " The unsupported match was downgraded to a gap."),
                })
                warnings.append(
                    (f"由于没有有效证据，{match.requirement_id} 已降级为差距。" if zh
                     else f"Downgraded {match.requirement_id} to gap because no assigned evidence remained.")
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
                    rationale=("模型遗漏了该要求，按证据差距处理。" if zh else "The model omitted this requirement; treated as an evidence gap."),
                    missing_capability=("未返回可靠的匹配结果。" if zh else "No reliable match result was returned."),
                )
                warnings.append(
                    f"为遗漏的要求 {requirement_id} 创建了差距。" if zh
                    else f"Created a gap for omitted requirement {requirement_id}."
                )
            matches.append(match)
        return MatchBatchResult(matches=matches, warnings=warnings)
