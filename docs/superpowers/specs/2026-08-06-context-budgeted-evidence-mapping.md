# Context-Budgeted Evidence Mapping

## Goal

Allow ordinary resumes and optional sources to run reliably against small local models with limited context windows. The application, rather than the user, must bound each evidence-mapping request while preserving source facts and structured output.

## Configuration and Budget

Add an explicit `context_window` Web LLM setting, defaulting to 4096. Keep it distinct from `max_output_tokens`, and persist and redact it through the existing Web configuration path. The shared backend also defaults to 4096 so the CLI remains compatible without adding another CLI option in this iteration.

Introduce a provider-neutral `ContextBudget` module. It conservatively estimates ASCII at roughly four characters per token, non-ASCII at one character per token, includes fixed prompt/schema overhead, adds a 10% safety margin, and reserves at most 25% of the context window for output with a 512-token floor. A call's effective output limit is bounded by this reserve even when the configured maximum is larger.

The estimator is a planning guard, not an exact tokenizer. Provider context-overflow errors remain the final safety signal.

## Candidate Selection and Batching

Retrieval rankings remain authoritative. Extend the evidence-mapping boundary to receive each requirement's ranked retrieval result instead of only a global chunk list. For each requirement, select at most five ranked evidence chunks and avoid unrelated global candidates. Preserve complete chunk text; do not summarize or truncate factual sentences.

Pack requirements and their deduplicated candidates into sequential batches while the estimated request remains within the input budget. A requirement is never split across normal batches. Shared evidence appears once per batch and results retain requirement IDs for deterministic merging.

Keep the algorithm in a focused module with typed values and pure functions: token estimation, budget calculation, candidate selection from retrieval IDs, batch planning, and batch splitting. LangChain continues to provide prompts and structured model output. LangGraph owns the surrounding workflow, checkpoint, and progress events. The heuristic backend retains deterministic behavior through the same expanded mapping interface.

## Recovery and Failure Handling

Execute batches sequentially to avoid concurrent Ollama memory pressure. Emit progress containing the current batch and total batch count without exposing uploaded content.

If a provider reports context overflow, bisect a multi-requirement batch and retry each half. If a single requirement still overflows, remove the lowest-ranked candidate and retry until one candidate remains. Report `context_length` only when that minimum request fails. Timeout, authentication, connection, parsing, and other errors are not treated as context failures.

Merge successful `EvidenceMap` batches in original requirement order. Every requirement must occur exactly once; missing or duplicate results are workflow errors rather than silently accepted output.

## Product and Engineering Tradeoff

Conservative planning can produce more model calls, but each call is shorter and more reliable on limited hardware. LLM-generated summarization is deliberately excluded because it can erase qualifiers or alter evidence meaning. LangGraph `Send` workers are also excluded for now because parallel local-model calls increase resource contention without improving user value.

## Implementation Outline

1. Extend typed LLM settings, Web persistence, form controls, and shared model construction with `context_window`; keep the CLI default implicit.
2. Add the isolated context-budget and batch-planning module.
3. Refactor evidence mapping to invoke bounded batches, merge results, and degrade only on context overflow.
4. Surface batch progress through existing Graph/Web events.
5. Add unit tests for estimation, planning, candidate reduction, overflow bisection, result merging, configuration persistence, and non-context failures.
6. Run the full Python suite, JavaScript syntax check, compile check, and a local Web smoke test.

## Acceptance

- A 4096-token model can process a normal resume by automatically producing bounded evidence-mapping calls.
- The Web UI clearly distinguishes context window from maximum output tokens and restores both values.
- Context overflow retries are finite, deterministic, and visible.
- Evidence text is neither summarized nor silently altered.
- Existing CLI, safety verification, checkpoint recovery, and user-owned example changes remain intact.
