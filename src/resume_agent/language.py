"""Deterministic language detection and small artifact message catalogs."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


Language = str
MIN_LANGUAGE_CHARACTERS = 20
ZH_THRESHOLD = 0.30

URL_OR_EMAIL = re.compile(r"https?://\S+|www\.\S+|\b\S+@\S+\.\S+\b", re.I)
FENCED_CODE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class LanguageDetection:
    language: Language | None
    han_count: int
    latin_count: int
    source: str

    @property
    def language_characters(self) -> int:
        return self.han_count + self.latin_count

    def as_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "han_count": self.han_count,
            "latin_count": self.latin_count,
            "language_characters": self.language_characters,
            "threshold": ZH_THRESHOLD,
            "source": self.source,
        }


def inspect_language(text: str, source: str) -> LanguageDetection:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = FENCED_CODE.sub(" ", normalized)
    normalized = INLINE_CODE.sub(" ", normalized)
    normalized = URL_OR_EMAIL.sub(" ", normalized)
    normalized = re.sub(r"\d+", " ", normalized)
    han = sum("\u4e00" <= character <= "\u9fff" for character in normalized)
    latin = sum(character.isascii() and character.isalpha() for character in normalized)
    total = han + latin
    language = None
    if total >= MIN_LANGUAGE_CHARACTERS:
        language = "zh" if han / total >= ZH_THRESHOLD else "en"
    return LanguageDetection(language, han, latin, source)


def detect_run_languages(jd_text: str, resume_text: str) -> tuple[LanguageDetection, LanguageDetection]:
    jd = inspect_language(jd_text, "jd")
    resume = inspect_language(resume_text, "resume")
    if jd.language is None and resume.language is not None:
        jd = LanguageDetection(
            resume.language, jd.han_count, jd.latin_count, "resume_fallback"
        )
    if resume.language is None and jd.language is not None:
        resume = LanguageDetection(
            jd.language, resume.han_count, resume.latin_count, "jd_fallback"
        )
    if jd.language is None and resume.language is None:
        fallback = "zh" if jd.han_count + resume.han_count else "en"
        jd = LanguageDetection(fallback, jd.han_count, jd.latin_count, "default")
        resume = LanguageDetection(
            fallback, resume.han_count, resume.latin_count, "default"
        )
    return jd, resume


LANGUAGE_NAMES = {"zh": "Chinese", "en": "English"}


MESSAGES = {
    "zh": {
        "match_report": "匹配报告",
        "match": "匹配程度",
        "priority": "优先级",
        "evidence": "证据",
        "retrieval": "检索方式",
        "rationale": "判断依据",
        "gap": "待提升",
        "none": "无",
        "warnings": "规范化与安全回退记录",
        "growth_plan": "提升路线",
        "no_gaps": "未发现需要优先提升的能力差距。",
        "requirement": "对应要求",
        "effort": "预计投入",
        "work": "行动",
        "acceptance": "验收标准",
        "evidence_to_keep": "需要保留的成果证据",
        "future_statement": "完成后可使用的简历表述",
        "interview_prep": "面试准备",
        "do_not_claim": "不要声称",
        "target_resume": "目标简历（不可投递）",
        "target_warning": "⚠ 以下内容仅代表完成提升任务后的目标状态，目前不可用于投递。",
        "aspirational_additions": "完成提升任务后可补充的内容",
    },
    "en": {
        "match_report": "Match Report",
        "match": "Match",
        "priority": "Priority",
        "evidence": "Evidence",
        "retrieval": "Retrieval",
        "rationale": "Rationale",
        "gap": "Gap",
        "none": "None",
        "warnings": "Normalization and fallback warnings",
        "growth_plan": "Growth Plan",
        "no_gaps": "No important capability gaps were identified.",
        "requirement": "Requirement",
        "effort": "Estimated effort",
        "work": "Work",
        "acceptance": "Acceptance",
        "evidence_to_keep": "Evidence to keep",
        "future_statement": "Future resume statement",
        "interview_prep": "Interview Preparation",
        "do_not_claim": "Do not claim",
        "target_resume": "Target Resume — NOT FOR SUBMISSION",
        "target_warning": "⚠ TARGET: The statements below are aspirational until their linked tasks are completed.",
        "aspirational_additions": "Aspirational additions",
    },
}


def message(language: Language, key: str) -> str:
    return MESSAGES.get(language, MESSAGES["en"])[key]
