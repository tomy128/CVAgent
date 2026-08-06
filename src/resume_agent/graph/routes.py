"""Pure conditional routes for the resume workflow."""

from resume_agent.graph.state import ResumeState


def after_matching(state: ResumeState) -> str:
    return "match_batch" if state["matching_cursor"] < len(state["matching_batches"]) else "prepare_resume"


def after_generation(state: ResumeState) -> str:
    return "generate_section" if state["generation_cursor"] < len(state["resume_sections"]) else "prepare_verification"


def after_verification_batch(state: ResumeState) -> str:
    return "verify_section" if state["verification_cursor"] < len(state["generated_sections"]) else "finalize_verification"


def after_verification(state: ResumeState) -> str:
    needs_second_pass = state.get("repair_attempt", 0) == 1 and not state.get("application_resume")
    return "prepare_verification" if needs_second_pass else "analyze_gaps"


def after_gap_analysis(state: ResumeState) -> str:
    return "generate_growth_plan" if state.get("has_gaps") else "generate_interview_prep"
