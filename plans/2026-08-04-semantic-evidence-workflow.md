# Semantic Evidence Workflow Implementation Plan

## Outcome

Add per-run LangChain semantic retrieval and a single LangGraph retrieval/redraft loop while preserving offline demo behavior, evidence traceability, and the CLI-first product boundary.

## Commit boundary

This plan and task state form a planning-only commit. Source, tests, dependency metadata, examples, and README changes form a later functional commit.

## Implementation steps

1. Extend evidence models with chunk metadata, retrieval method/rank/score, queries, attempts, and retry reason.
2. Refactor evidence loading to treat the master resume as primary evidence and optional `--sources` as supplemental input; preserve stable IDs.
3. Add a LangChain retrieval module using Documents, a recursive text splitter, deterministic demo embeddings, OpenAI-compatible embeddings, and an in-memory vector store.
4. Implement deterministic reciprocal-rank fusion for lexical and semantic results, including larger retry limits and supplemental queries.
5. Update backend contracts so drafting consumes retrieved evidence and retry context while the verifier returns typed claims.
6. Expand the LangGraph state and routing with index construction, first-pass retrieval, one bounded retry, redraft, re-verification, and a deterministic final safety gate.
7. Update CLI options (`--sources`, compatibility alias `--evidence`), embedding configuration, checkpoint-safe index rebuilding, and audit outputs.
8. Add unit, graph, CLI, and regression tests for resume-only input, supplemental sources, hybrid ranking, retry success/exhaustion, safety failures, and argument conflicts.
9. Update README inline without linking planning documents; sync dependencies with Python 3.13.

## Verification

Run `pytest`, compile all source and tests, inspect CLI help, execute the offline resume-only demo, execute the demo with supplemental sources, and inspect generated audit fields. Stage only functional files for the implementation commit.
