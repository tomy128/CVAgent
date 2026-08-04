# Archived Tasks

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
