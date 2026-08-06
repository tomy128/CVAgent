"""Generate actionable growth tasks and interview preparation."""

import json

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.domain import (
    GrowthPlan,
    GrowthTask,
    InterviewItem,
    InterviewPrep,
    Requirement,
    RequirementMatch,
)


class GrowthPlanChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, requirements: list[Requirement], matches: list[RequirementMatch]
    ) -> GrowthPlan:
        gaps = [
            {"requirement": requirement.model_dump(), "match": match.model_dump()}
            for requirement, match in zip(requirements, matches, strict=False)
            if match.status in {"transferable", "gap"}
        ]
        if not gaps:
            return GrowthPlan()
        if self.model is None:
            return GrowthPlan(
                tasks=[
                    GrowthTask(
                        id=f"task-{index:02d}",
                        requirement_id=item["requirement"]["id"],
                        target_capability=item["requirement"]["description"],
                        priority="high",
                        estimated_effort="1-3 days",
                        work="Build a small, reviewable project demonstrating this capability.",
                        acceptance_checks=["Working code", "Automated test", "Short design note"],
                        evidence_to_keep=["Repository", "Test output", "Design note"],
                        future_resume_statement=(
                            f"Demonstrated {item['requirement']['description']} in a portfolio project."
                        ),
                    )
                    for index, item in enumerate(gaps, start=1)
                ]
            )
        result = invoke_structured(
            self.model,
            GrowthPlan,
            "Turn each important transferable or missing requirement into a small executable "
            "learning or portfolio task. Include objective acceptance checks, evidence to keep, "
            "and a future resume statement. Do not claim the task is already complete.",
            "Gaps:\n{gaps}",
            {"gaps": json.dumps(gaps, ensure_ascii=False)},
        )
        gap_ids = {item["requirement"]["id"] for item in gaps}
        task_ids = [item.id for item in result.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise RuntimeError("Growth plan contains duplicate task IDs")
        if any(item.requirement_id not in gap_ids for item in result.tasks):
            raise RuntimeError("Growth plan targets a requirement without a gap")
        return result


class InterviewPrepChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, requirements: list[Requirement], matches: list[RequirementMatch]
    ) -> InterviewPrep:
        context = [
            {"requirement": requirement.model_dump(), "match": match.model_dump()}
            for requirement, match in zip(requirements, matches, strict=False)
        ]
        if self.model is None:
            return InterviewPrep(
                items=[
                    InterviewItem(
                        requirement_id=item["requirement"]["id"],
                        question=f"请说明：{item['requirement']['description']}",
                        answer_points=[item["match"]["rationale"]],
                        avoid_claiming=(
                            item["match"]["missing_capability"]
                            if item["match"]["status"] in {"transferable", "gap"}
                            else ""
                        ),
                    )
                    for item in context
                ]
            )
        return invoke_structured(
            self.model,
            InterviewPrep,
            "Create interview questions and honest answer points from the match report. For "
            "transferable experience and gaps, state what must not be claimed.",
            "Requirement matches:\n{context}",
            {"context": json.dumps(context, ensure_ascii=False)},
        )
