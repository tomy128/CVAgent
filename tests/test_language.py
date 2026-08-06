from resume_agent.language import detect_run_languages, inspect_language


def test_detector_uses_exact_minimum_and_han_threshold() -> None:
    assert inspect_language("中" * 19, "jd").language is None
    assert inspect_language("中" * 20, "jd").language == "zh"
    assert inspect_language("中" * 6 + "a" * 14, "jd").language == "zh"
    assert inspect_language("中" * 5 + "a" * 15, "jd").language == "en"


def test_detector_ignores_urls_code_and_numbers_but_counts_technology_names() -> None:
    result = inspect_language(
        "https://example.com `ignoredCode` 2026 Python FastAPI backend engineering",
        "jd",
    )

    assert result.language == "en"
    assert result.han_count == 0
    assert result.latin_count > len("backendengineering")


def test_jd_and_resume_languages_are_independent_with_fallback() -> None:
    analysis, resume = detect_run_languages(
        "We need an experienced Python backend engineer for production systems.",
        "资深后端开发工程师，负责统计分析平台接口设计与长期维护。",
    )
    assert analysis.language == "en"
    assert resume.language == "zh"

    short_analysis, short_resume = detect_run_languages("Go", "中文简历内容过短")
    assert short_analysis.language == short_resume.language == "zh"
    assert short_analysis.source == "default"
