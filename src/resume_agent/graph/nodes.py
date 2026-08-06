"""Typed LangGraph node implementations; each method performs one state transition."""

from collections.abc import Callable
import threading
import time
from typing import Any

from langgraph.types import interrupt

from resume_agent.chains import ChainBundle
from resume_agent.chains.resume import SectionGroundingError
from resume_agent.context_budget import (
    ContextBudget,
    EvidenceBatch,
    is_context_overflow,
    plan_batches,
    select_candidates,
)
from resume_agent.domain import (
    EvidenceChunk,
    GeneratedSection,
    GrowthPlan,
    Requirement,
    RequirementMatch,
    ResumeSection,
    VerifiedSection,
)
from resume_agent.evidence import search_evidence
from resume_agent.graph.state import ResumeState
from resume_agent.graph.subgraphs import (
    deserialize_batch,
    invoke_with_reduced_evidence,
    serialize_batch,
    split_markdown_block,
)
from resume_agent.language import detect_run_languages, message
from resume_agent.retrieval import HybridRetriever
from resume_agent.sections import merge_sections, split_markdown_sections


class SafetyGateError(RuntimeError):
    def __init__(self, issues: list[dict[str, str]]) -> None:
        self.issues = issues
        super().__init__("Application resume still contains unsupported claims")


class WorkflowNodes:
    def __init__(
        self,
        chains: ChainBundle,
        retriever: HybridRetriever,
        budget: ContextBudget,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        heartbeat_interval_seconds: float = 5,
    ) -> None:
        self.chains = chains
        self.retriever = retriever
        self.budget = budget
        self.event_sink = event_sink
        self.heartbeat_interval_seconds = heartbeat_interval_seconds

    def observed(self, name: str, function):
        def wrapped(state: ResumeState) -> dict[str, Any]:
            started = time.monotonic()
            stopped = threading.Event()
            self._emit({"type": "node_started", "node": name, "status": "running"})

            def heartbeat() -> None:
                while not stopped.wait(self.heartbeat_interval_seconds):
                    self._emit({
                        "type": "node_heartbeat", "node": name, "status": "running",
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                    })

            if self.event_sink:
                threading.Thread(target=heartbeat, daemon=True).start()
            try:
                result = function(state)
            except Exception as error:
                stopped.set()
                self._emit({
                    "type": "node_failed", "node": name, "status": "failed",
                    "error_type": type(error).__name__,
                    "duration_seconds": round(time.monotonic() - started, 2),
                })
                raise
            stopped.set()
            self._emit({
                "type": "node_completed", "node": name, "status": "complete",
                "duration_seconds": round(time.monotonic() - started, 2),
            })
            return result
        return wrapped

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink:
            self.event_sink(event)

    @staticmethod
    def _language_state(state: ResumeState) -> dict[str, Any]:
        if state.get("analysis_language") and state.get("resume_language"):
            return {}
        analysis, resume = detect_run_languages(
            state.get("jd_text", ""), state.get("master_resume", "")
        )
        return {
            "schema_version": 2,
            "analysis_language": analysis.language or "en",
            "resume_language": resume.language or "en",
            "language_detection": {
                "analysis": analysis.as_dict(), "resume": resume.as_dict()
            },
        }

    def _language(self, state: ResumeState, key: str) -> str:
        return str(state.get(key) or self._language_state(state)[key])

    def extract_requirements(self, state: ResumeState) -> dict[str, Any]:
        analysis, resume = detect_run_languages(
            state["jd_text"], state["master_resume"]
        )
        result = self.chains.requirements.invoke(
            state["jd_text"], analysis.language or "en"
        )
        return {
            "schema_version": 2,
            "analysis_language": analysis.language or "en",
            "resume_language": resume.language or "en",
            "language_detection": {
                "analysis": analysis.as_dict(), "resume": resume.as_dict()
            },
            "requirements": [item.model_dump() for item in result.requirements],
        }

    def build_evidence_index(self, state: ResumeState) -> dict[str, Any]:
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        self.retriever.build(chunks)
        return {}

    def prepare_matching(self, state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        retrievals = [self.retriever.retrieve(item, chunks) for item in requirements]
        batches = plan_batches(
            select_candidates(requirements, chunks, retrievals), self.budget
        )
        return {
            "retrievals": [item.model_dump() for item in retrievals],
            "matching_batches": [serialize_batch(item) for item in batches],
            "matching_cursor": 0,
            "matches": [],
            "warnings": state.get("warnings", []),
        }

    def match_batch(self, state: ResumeState) -> dict[str, Any]:
        cursor = state["matching_cursor"]
        batches = state["matching_batches"]
        self._emit({
            "type": "node_progress", "node": "match_requirements", "status": "running",
            "phase": "matching", "batch_index": cursor + 1, "batch_total": len(batches),
        })
        batch = deserialize_batch(batches[cursor])
        try:
            result = self.chains.matching.invoke(
                batch, self._language(state, "analysis_language")
            )
        except Exception as error:
            if not is_context_overflow(error):
                raise
            if len(batch.assignments) > 1:
                replacement = list(batch.split())
            else:
                assignment = batch.assignments[0]
                reduced = assignment.without_lowest_ranked_candidate()
                if reduced == assignment:
                    raise
                replacement = [EvidenceBatch((reduced,))]
            return {
                "matching_batches": [
                    *batches[:cursor],
                    *[serialize_batch(item) for item in replacement],
                    *batches[cursor + 1 :],
                ]
            }
        return {
            "matches": [
                *state.get("matches", []),
                *[item.model_dump() for item in result.matches],
            ],
            "matching_cursor": cursor + 1,
            "warnings": [*state.get("warnings", []), *result.warnings],
            **self._language_state(state),
        }

    def prepare_resume(self, state: ResumeState) -> dict[str, Any]:
        sections = split_markdown_sections(
            state["master_resume"], max(256, self.budget.input_tokens // 3)
        )
        return {
            "resume_sections": [item.model_dump() for item in sections],
            "generation_cursor": 0,
            "generated_sections": [],
        }

    def generate_section(self, state: ResumeState) -> dict[str, Any]:
        sections = [ResumeSection.model_validate(item) for item in state["resume_sections"]]
        cursor = state["generation_cursor"]
        section = sections[cursor]
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        matches = [RequirementMatch.model_validate(item) for item in state["matches"]]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        evidence = search_evidence(
            Requirement(id=section.id, category="resume section", description=section.source_markdown),
            chunks,
            limit=4,
        )
        self._emit({
            "type": "node_progress", "node": "generate_application_resume",
            "status": "running", "phase": "generation", "batch_index": cursor + 1,
            "batch_total": len(sections), "section": section.heading,
        })
        try:
            result = invoke_with_reduced_evidence(
                lambda selected: self.chains.resume.invoke(
                    section,
                    requirements,
                    matches,
                    selected,
                    self._language(state, "resume_language"),
                    self._language(state, "analysis_language"),
                ),
                evidence,
            )
        except SectionGroundingError as error:
            warning = (
                f"章节“{section.heading}”修复后仍无法可靠核验，已保留原始简历章节。"
                if self._language(state, "analysis_language") == "zh"
                else f"Section '{section.heading}' could not be grounded after one repair; "
                "the original resume section was preserved."
            )
            self._emit({
                "type": "node_progress", "node": "generate_application_resume",
                "status": "running", "phase": "safe_fallback", "section": section.heading,
                "warning": warning,
            })
            return {
                "generated_sections": [
                    *state.get("generated_sections", []),
                    GeneratedSection(
                        section_id=section.id,
                        markdown=section.source_markdown,
                    ).model_dump(),
                ],
                "generation_cursor": cursor + 1,
                "warnings": [*state.get("warnings", []), warning],
                **self._language_state(state),
            }
        except Exception as error:
            if not is_context_overflow(error):
                raise
            parts = split_markdown_block(section.source_markdown)
            if len(parts) < 2:
                raise
            replacements = [
                ResumeSection(
                    id=f"{section.id}-{index}", heading=section.heading, source_markdown=part
                ).model_dump()
                for index, part in enumerate(parts, start=1)
            ]
            return {"resume_sections": [
                *state["resume_sections"][:cursor], *replacements,
                *state["resume_sections"][cursor + 1 :],
            ]}
        return {
            "generated_sections": [
                *state.get("generated_sections", []), result.model_dump()
            ],
            "generation_cursor": cursor + 1,
            "warnings": [*state.get("warnings", []), *result.warnings],
            **self._language_state(state),
        }

    def prepare_verification(self, state: ResumeState) -> dict[str, Any]:
        return {"verification_cursor": 0, "verified_sections": []}

    def verify_section(self, state: ResumeState) -> dict[str, Any]:
        sections = [GeneratedSection.model_validate(item) for item in state["generated_sections"]]
        cursor = state["verification_cursor"]
        section = sections[cursor]
        chunks = [EvidenceChunk.model_validate(item) for item in state["evidence_chunks"]]
        cited = {item for claim in section.claims for item in claim.evidence_ids}
        evidence = [item for item in chunks if item.id in cited]
        if not evidence:
            evidence = search_evidence(
                Requirement(
                    id=section.section_id,
                    category="section",
                    description=section.markdown,
                ),
                chunks,
                limit=4,
            )
        self._emit({
            "type": "node_progress", "node": "verify_application_resume",
            "status": "running", "phase": "verification", "batch_index": cursor + 1,
            "batch_total": len(sections),
        })
        try:
            result = invoke_with_reduced_evidence(
                lambda selected: self.chains.verification.invoke(
                    section, selected, self._language(state, "resume_language")
                ),
                evidence,
            )
        except Exception as error:
            if not is_context_overflow(error):
                raise
            parts = split_markdown_block(section.markdown)
            if len(parts) < 2:
                raise
            replacements = [
                GeneratedSection(
                    section_id=f"{section.section_id}-{index}",
                    markdown=part,
                    claims=[claim for claim in section.claims if claim.text in part],
                ).model_dump()
                for index, part in enumerate(parts, start=1)
            ]
            return {"generated_sections": [
                *state["generated_sections"][:cursor], *replacements,
                *state["generated_sections"][cursor + 1 :],
            ]}
        return {
            "verified_sections": [
                *state.get("verified_sections", []), result.model_dump()
            ],
            "verification_cursor": cursor + 1,
        }

    def finalize_verification(self, state: ResumeState) -> dict[str, Any]:
        verified = [VerifiedSection.model_validate(item) for item in state["verified_sections"]]
        issues = [item for section in verified for item in section.unsupported_claims]
        if issues and state.get("repair_attempt", 0) < 1:
            return {
                "generated_sections": [
                    GeneratedSection(
                        section_id=item.section_id,
                        markdown=item.corrected_markdown,
                        claims=item.supported_claims,
                        priority=item.priority,
                    ).model_dump()
                    for item in verified
                ],
                "repair_attempt": 1,
            }
        if issues:
            source_sections = [
                ResumeSection.model_validate(item) for item in state["resume_sections"]
            ]
            fallback_sections = []
            warnings = list(state.get("warnings", []))
            for section in verified:
                if not section.unsupported_claims:
                    fallback_sections.append(section)
                    continue
                source = max(
                    (
                        item for item in source_sections
                        if section.section_id == item.id
                        or section.section_id.startswith(f"{item.id}-")
                    ),
                    key=lambda item: len(item.id),
                    default=None,
                )
                if source is None:
                    raise SafetyGateError(
                        [item.model_dump() for item in section.unsupported_claims]
                    )
                warning = (
                    f"章节“{source.heading}”核验后仍缺少可靠证据，已保留原始简历章节。"
                    if self._language(state, "analysis_language") == "zh"
                    else f"Section '{source.heading}' remained unsupported after verification; "
                    "the original resume section was preserved."
                )
                warnings.append(warning)
                fallback_sections.append(VerifiedSection(
                    section_id=section.section_id,
                    corrected_markdown=source.source_markdown,
                    priority=section.priority,
                ))
            return {
                "application_resume": merge_sections(fallback_sections),
                "warnings": warnings,
            }
        return {"application_resume": merge_sections(verified)}

    def analyze_gaps(self, state: ResumeState) -> dict[str, Any]:
        matches = [RequirementMatch.model_validate(item) for item in state["matches"]]
        has_gaps = any(item.status in {"partial", "transferable", "gap"} for item in matches)
        if not has_gaps:
            for node in ("generate_growth_plan", "generate_target_resume"):
                self._emit({
                    "type": "node_skipped", "node": node, "status": "skipped",
                    "reason_code": "no_actionable_gap",
                })
        return {"has_gaps": has_gaps, **self._language_state(state)}

    def generate_growth_plan(self, state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        matches = [RequirementMatch.model_validate(item) for item in state["matches"]]
        return {"growth_plan": self.chains.growth.invoke(
            requirements,
            matches,
            self._language(state, "analysis_language"),
            self._language(state, "resume_language"),
        ).model_dump()}

    def generate_target_resume(self, state: ResumeState) -> dict[str, Any]:
        plan = GrowthPlan.model_validate(state["growth_plan"])
        language = self._language(state, "resume_language")
        lines = [
            f"# {message(language, 'target_resume')}", "",
            f"> {message(language, 'target_warning')}",
            "", state["application_resume"].strip(), "",
            f"## {message(language, 'aspirational_additions')}", "",
        ]
        lines.extend(
            f"- ⚠ TARGET `{task.id}`: {task.future_resume_statement}" for task in plan.tasks
        )
        return {"target_resume": "\n".join(lines) + "\n"}

    def generate_interview_prep(self, state: ResumeState) -> dict[str, Any]:
        requirements = [Requirement.model_validate(item) for item in state["requirements"]]
        matches = [RequirementMatch.model_validate(item) for item in state["matches"]]
        return {"interview_prep": self.chains.interview.invoke(
            requirements, matches, self._language(state, "analysis_language")
        ).model_dump()}

    def human_review(self, state: ResumeState) -> dict[str, Any]:
        decision = interrupt({"resume_markdown": state["application_resume"]})
        approved = bool(decision.get("approved"))
        return {
            "review_status": "approved" if approved else "rejected",
            "final_resume": decision.get("resume_markdown", state["application_resume"]),
        }
