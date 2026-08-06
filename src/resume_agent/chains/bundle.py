"""Construct the workflow's explicit set of specialized chains."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from resume_agent.chains.matching import MatchingChain
from resume_agent.chains.planning import GrowthPlanChain, InterviewPrepChain
from resume_agent.chains.requirements import RequirementsChain
from resume_agent.chains.resume import ResumeSectionChain, VerificationChain


@dataclass(frozen=True)
class ChainBundle:
    requirements: RequirementsChain
    matching: MatchingChain
    resume: ResumeSectionChain
    verification: VerificationChain
    growth: GrowthPlanChain
    interview: InterviewPrepChain


def build_chain_bundle(model: BaseChatModel | None) -> ChainBundle:
    return ChainBundle(
        requirements=RequirementsChain(model),
        matching=MatchingChain(model),
        resume=ResumeSectionChain(model),
        verification=VerificationChain(model),
        growth=GrowthPlanChain(model),
        interview=InterviewPrepChain(model),
    )
