from resume_agent.chains.resume import ResumeSectionChain
from resume_agent.domain import (
    EvidenceChunk,
    ResumeEditDecision,
    ResumeEditResult,
    ResumeSection,
)
from resume_agent.sections import parse_resume_entries, render_resume_section


def test_renderer_owns_markdown_and_preserves_source_order_by_default() -> None:
    section = ResumeSection(
        id="section-01",
        heading="工作经历",
        source_markdown="# 工作经历\n\n公司｜后端工程师\n\n- 负责 Python 接口开发\n- 维护统计分析服务",
    )
    entries = parse_resume_entries(section)
    decisions = [
        ResumeEditDecision(source_entry_id=item.id, action="keep", priority=item.source_index)
        for item in entries
    ]

    assert render_resume_section(section, entries, decisions) == (
        "# 工作经历\n\n公司｜后端工程师\n\n- 负责 Python 接口开发\n- 维护统计分析服务"
    )


def test_unsafe_rewrite_falls_back_to_source_entry() -> None:
    section = ResumeSection(
        id="section-01",
        heading="经历",
        source_markdown="## 经历\n\n- 负责 Python 接口开发",
    )
    entries = parse_resume_entries(section)
    evidence = EvidenceChunk(
        id="ev-1", source="resume.md", source_kind="resume", content="负责 Python 接口开发"
    )
    result = ResumeEditResult(
        section_id=section.id,
        decisions=[ResumeEditDecision(
            source_entry_id=entries[0].id,
            action="rewrite",
            revised_text="全面赋能 Kubernetes 平台并显著提升 80% 效率",
            rationale="更匹配 JD",
            evidence_ids=["ev-1"],
        )],
    )

    decisions, invalid = ResumeSectionChain._normalize(result, entries, [evidence])

    assert entries[0].id in invalid
    assert decisions[0].action == "keep"
    assert render_resume_section(section, entries, decisions).endswith("- 负责 Python 接口开发")
