"""Extract typed requirements from one job description."""

import re

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.common import invoke_structured
from resume_agent.domain import Requirement, RequirementSet
from resume_agent.evidence import tokenize
from resume_agent.language import LANGUAGE_NAMES


class RequirementsChain:
    def __init__(self, model: BaseChatModel | None) -> None:
        self.model = model

    def invoke(self, jd_text: str, language: str = "en") -> RequirementSet:
        if self.model is None:
            return self._heuristic(jd_text)
        return invoke_structured(
            self.model,
            RequirementSet,
            "Extract only concrete job requirements. Assign stable IDs req-01 onward. "
            "Separate required, preferred, and contextual requirements. Write descriptions, "
            "categories, and keywords in {language}.",
            "Job description:\n{jd}",
            {"jd": jd_text, "language": LANGUAGE_NAMES.get(language, "English")},
        )

    @staticmethod
    def _heuristic(jd_text: str) -> RequirementSet:
        lines = [
            re.sub(r"^[\s\-*\d.、]+", "", line).strip()
            for line in jd_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return RequirementSet(
            requirements=[
                Requirement(
                    id=f"req-{index:02d}",
                    category="job requirement",
                    description=line,
                    keywords=sorted(
                        tokenize(line), key=lambda item: (-len(item), item)
                    )[:8],
                )
                for index, line in enumerate(lines[:12], start=1)
            ]
        )
