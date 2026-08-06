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
from resume_agent.language import LANGUAGE_NAMES


class GrowthPlanChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, requirements: list[Requirement], matches: list[RequirementMatch],
        language: str = "en", resume_language: str = "en",
    ) -> GrowthPlan:
        gaps = [
            {"requirement": requirement.model_dump(), "match": match.model_dump()}
            for requirement, match in zip(requirements, matches, strict=False)
            if match.status in {"partial", "transferable", "gap"}
        ]
        if not gaps:
            return GrowthPlan()
        if self.model is None:
            return GrowthPlan(
                tasks=[
                    self._fallback_task(
                        item, f"task-{index:02d}", language, resume_language
                    )
                    for index, item in enumerate(gaps, start=1)
                ]
            )
        result = invoke_structured(
            self.model,
            GrowthPlan,
            "Turn each important transferable or missing requirement into a small executable "
            "learning or portfolio task. Include objective acceptance checks, evidence to keep, "
            "and a future resume statement. Do not claim the task is already complete. Write task "
            "guidance in {language}, but write future_resume_statement in {resume_language}.",
            "Gaps:\n{gaps}",
            {
                "gaps": json.dumps(gaps, ensure_ascii=False),
                "language": LANGUAGE_NAMES.get(language, "English"),
                "resume_language": LANGUAGE_NAMES.get(resume_language, "English"),
            },
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
                task = self._fallback_task(item, task_id, language, resume_language)
                used_task_ids.add(task_id)
            normalized.append(task)
        return GrowthPlan(tasks=normalized)

    @staticmethod
    def _fallback_task(
        item: dict, task_id: str, language: str = "en", resume_language: str = "en"
    ) -> GrowthTask:
        description = item["requirement"]["description"]
        zh = language == "zh"
        return GrowthTask(
            id=task_id,
            requirement_id=item["requirement"]["id"],
            target_capability=description,
            priority="high",
            estimated_effort="1-3 天" if zh else "1-3 days",
            work=(
                "构建一个可审查的小型项目来证明这项能力。"
                if zh else "Build a small, reviewable project demonstrating this capability."
            ),
            acceptance_checks=(
                ["可运行代码", "自动化测试", "简短设计说明"]
                if zh else ["Working code", "Automated test", "Short design note"]
            ),
            evidence_to_keep=(
                ["代码仓库", "测试结果", "设计说明"]
                if zh else ["Repository", "Test output", "Design note"]
            ),
            future_resume_statement=(
                f"通过作品项目实践并证明了 {description}。"
                if resume_language == "zh"
                else f"Demonstrated {description} in a portfolio project."
            ),
        )


class InterviewPrepChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(
        self, requirements: list[Requirement], matches: list[RequirementMatch],
        language: str = "en",
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
                        question=(
                            f"请说明：{item['requirement']['description']}"
                            if language == "zh"
                            else f"Please explain: {item['requirement']['description']}"
                        ),
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
            "transferable experience and gaps, state what must not be claimed. Write in {language}.",
            "Requirement matches:\n{context}",
            {
                "context": json.dumps(context, ensure_ascii=False),
                "language": LANGUAGE_NAMES.get(language, "English"),
            },
        )
