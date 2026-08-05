# Current Tasks

## [In Progress] Fix retry loops, context failures, and cancellation
- Status: In Progress
- Goal: Make failed-node recovery deterministic, event streaming idempotent, and production Run cancellation immediate.
- Acceptance: SSE resumes without replay loops; evidence prompts avoid duplicate content; failures identify LLM context exhaustion; retry is single-shot; a production worker process can be terminated; regressions pass.
