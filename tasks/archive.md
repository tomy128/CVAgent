# Archived Tasks

## [Completed] Persist all local Web configuration
- Status: Completed
- Goal: Keep all model settings, secrets, and current Run context across refreshes and browser restarts.
- Acceptance: LLM and Embedding fields save consistently while editing, restore from localStorage, and regressions pass.

## [Completed] Explain and recover from safety gate failures
- Status: Completed
- Goal: Turn evidence safety rejection into an understandable, actionable Web state without allowing unsafe override.
- Acceptance: Failed claims, reports, recovery guidance, and server diagnostics are visible; deterministic retry is hidden; regressions pass.

## [Completed] Make slow LLM execution observable and controllable
- Status: Completed
- Goal: Prevent unnecessary local-model thinking and show continued progress during blocking Graph nodes.
- Acceptance: LLM reasoning/output controls affect tests and Runs consistently; connection testing exercises structured output; active nodes emit elapsed-time heartbeats; regressions pass.

## [Completed] Fix OpenAI-compatible Embedding input
- Status: Completed
- Goal: Send raw text through OpenAI-compatible Embedding endpoints instead of client-tokenized input.
- Acceptance: Ollama connection tests and production retrieval share the compatible configuration, errors are actionable, and all regression tests pass.

## [Completed] Implement local Web workbench
- Status: Completed
- Goal: Build the approved FastAPI and native Web interface over the existing Resume Agent workflow.
- Acceptance: Separate model configuration, uploads, durable Graph events, timeout diagnosis, full-screen Markdown review, secure local APIs, recovery, and existing CLI regression tests all pass.

## [Completed] Plan Web implementation
- Status: Completed
- Goal: Create an actionable implementation plan with planning and functional commit boundaries.
- Acceptance: Plan is ready for code implementation.

## [Completed] Document and review Web design
- Status: Completed
- Goal: Persist and independently review the approved specification.
- Acceptance: Design spec is committed separately and approved for implementation planning.

## [Completed] Design Web application
- Status: Completed
- Goal: Define architecture, page structure, graph observability, states, errors, and testing.
- Acceptance: User approves the complete Web MVP design.

## [Completed] Define product and interface direction
- Status: Completed
- Goal: Confirm users, workflow, product personality, accessibility, and UI approach.
- Acceptance: PRODUCT.md inputs and preferred design approach are approved.

## [Completed] Explore Web workflow context
- Status: Completed
- Goal: Understand the Web configuration, upload, observability, and result-review requirements.
- Acceptance: Product scope, existing backend constraints, and success criteria are clear.

## [Completed] Implement semantic evidence workflow
- Status: Completed
- Goal: Add meaningful LangChain semantic retrieval and a bounded LangGraph verification retry loop.
- Acceptance: Resume-only and optional-source CLI flows pass offline; hybrid retrieval is auditable; verification retries at most once; all tests pass.

## [Completed] Plan implementation
- Status: Completed
- Goal: Produce an actionable implementation plan with planning and code commit boundaries.
- Acceptance: Plan is ready for implementation.

## [Completed] Document and review the design
- Status: Completed
- Goal: Persist the approved specification and review it before implementation planning.
- Acceptance: Design document is committed separately and approved for planning.

## [Completed] Design semantic retrieval and verification loop
- Status: Completed
- Goal: Define architecture, data flow, failure handling, and tests.
- Acceptance: User approves the proposed design.

## [Completed] Compare implementation approaches
- Status: Completed
- Goal: Compare practical LangChain retrieval designs and recommend the smallest useful option.
- Acceptance: Two or three approaches are evaluated with explicit tradeoffs.

## [Completed] Explore semantic evidence workflow
- Status: Completed
- Goal: Confirm the product and technical scope for meaningful LangChain retrieval inside the LangGraph workflow.
- Acceptance: Current architecture, constraints, and success criteria are understood.

## [Completed] Make README self-contained
- Status: Completed
- Goal: Remove references from README to non-source repository documents.
- Acceptance: README explains required architecture boundaries directly and contains no links to `docs/`, `tasks/`, or other planning files.

## [Completed] Separate planning and implementation commits
- Status: Completed
- Goal: Require product planning documents and functional implementation to use separate commits.
- Acceptance: `AGENTS.md` clearly defines planning-file scope, commit boundaries, and example commit messages.

## [Completed] Build evidence-grounded Resume Agent CLI
- Status: Completed
- Goal: Tailor a resume to a JD through an auditable LangGraph workflow.
- Acceptance: Offline demo and tests pass; real model mode supports structured extraction, verification, SQLite checkpoints, human approval, and Markdown outputs.
