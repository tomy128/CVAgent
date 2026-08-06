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
                    self._fallback_task(item, f"task-{index:02d}")
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
        gaps_by_id = {item["requirement"]["id"]: item for item in gaps}
        tasks_by_requirement: dict[str, GrowthTask] = {}
        used_task_ids: set[str] = set()
        for task in result.tasks:
            if (
                task.requirement_id not in gaps_by_id
                or task.requirement_id in tasks_by_requirement
                or task.id in used_task_ids
            ):
                continue
            tasks_by_requirement[task.requirement_id] = task
            used_task_ids.add(task.id)

        normalized = []
        for index, item in enumerate(gaps, start=1):
            requirement_id = item["requirement"]["id"]
            task = tasks_by_requirement.get(requirement_id)
            if task is None:
                task_id = f"task-{index:02d}"
                while task_id in used_task_ids:
                    task_id += "-gap"
                task = self._fallback_task(item, task_id)
                used_task_ids.add(task_id)
            normalized.append(task)
        return GrowthPlan(tasks=normalized)

    @staticmethod
    def _fallback_task(item: dict, task_id: str) -> GrowthTask:
        description = item["requirement"]["description"]
        return GrowthTask(
            id=task_id,
            requirement_id=item["requirement"]["id"],
            target_capability=description,
            priority="high",
            estimated_effort="1-3 days",
            work="Build a small, reviewable project demonstrating this capability.",
            acceptance_checks=["Working code", "Automated test", "Short design note"],
            evidence_to_keep=["Repository", "Test output", "Design note"],
            future_resume_statement=f"Demonstrated {description} in a portfolio project.",
        )


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
