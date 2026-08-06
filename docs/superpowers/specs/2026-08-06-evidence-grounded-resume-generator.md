# Evidence-Grounded Resume Generator

## Product Goal

Given a job description, master resume, and optional supporting sources, generate the strongest honestly submittable resume available from the user's current evidence. Requirements that cannot yet be supported become a concrete growth plan, target resume, and interview preparation rather than fabricated claims.

The MVP is a local Web tool and a learning-oriented LangChain/LangGraph project. It does not include a CLI, multi-agent collaboration, long-term memory platform, project execution, or task tracking.

## Product Outputs

- `application-resume.md` contains only verified facts and evidence-preserving reframes. It is the only approvable resume.
- `match-report.md` classifies every requirement as `strong`, `partial`, `transferable`, or `gap`, with evidence and handling rationale.
- `growth-plan.md` turns important gaps into bounded learning or portfolio tasks with priority, estimated effort, acceptance checks, evidence to retain, and a future resume statement.
- `target-resume.md` is an explicitly non-submittable future version. Every aspirational statement is visibly marked and linked to a growth-plan task. It may be omitted when there are no important gaps.
- `interview-prep.md` provides evidence-backed questions and answer points, honest transferable-experience framing, and safe responses for current gaps.
- `run.json` remains the machine-readable audit of retrieval, generation, budgets, routing, and evidence lineage.

## Content States and Safety

Generated content has one of three states:

- `verified`: directly supported by evidence IDs.
- `reframed`: changes emphasis but adds no unsupported employer, duration, technology, scale, responsibility, or outcome. It retains the original wording, revised wording, rationale, and evidence IDs.
- `aspirational`: currently unsupported and linked to a gap and action task.

Only verified and deterministically validated reframed content may enter the application resume. Aspirational content is restricted to the target resume, growth plan, and interview preparation. The LLM proposes classifications; ordinary Python validation enforces output boundaries. Edited application resumes must pass the same evidence verification before approval.

## Architecture

Retain the existing Web workbench, local Run process, SSE events, Markdown review, checkpoint foundation, uploads, and model configuration. Remove `src/resume_agent/cli.py`, the `resume-agent` script entry, CLI documentation, and CLI-only compatibility options.

Rebuild the domain core around explicit boundaries:

```text
src/resume_agent/
├── domain.py
├── context_budget.py
├── retrieval.py
├── chains/
│   ├── requirements.py
│   ├── matching.py
│   ├── resume.py
│   ├── gaps.py
│   └── planning.py
├── graph/
│   ├── state.py
│   ├── nodes.py
│   ├── routes.py
│   ├── subgraphs.py
│   └── builder.py
├── output.py
└── web/
```

LangChain owns prompts, model adaptation, retrieval integration, and structured output for one bounded AI task. LangGraph owns business-stage orchestration, structured Run state, checkpoints, conditional routes, one repair cycle, and human review. Plain Python owns context budgeting, sectioning, merging, evidence validation, and content-state enforcement. Chains are not autonomous agents.

## Graph

```text
ingest_inputs
→ extract_requirements
→ build_evidence_index
→ match_requirements
→ classify_matches
→ generate_application_resume
→ verify_application_resume
    ├─ first failure → repair_resume → verify once more
    └─ second failure → stop with actionable report
→ analyze_gaps
    ├─ important gaps → generate_growth_plan → generate_target_resume
    └─ no important gaps → skip target resume
→ generate_interview_prep
→ human_review
→ write_outputs
```

Graph state stores structured requirements, evidence IDs and rankings, matches, resume sections, gaps, tasks, batch progress, and retry state. It avoids repeated prompts and duplicate source bodies. Matching, resume generation, and verification use small batch subgraphs or explicit loop nodes: prepare batches, process one batch, persist its result, route to the next batch, then finalize. Each batch therefore crosses a real LangGraph node boundary and is checkpointed. The Web groups these internal nodes under one product stage.

## Context Discovery and Budgeting

The LLM context setting defaults to automatic. Discovery priority is:

1. A user override, which is never replaced automatically.
2. Reliable LangChain model profile metadata.
3. Ollama `/api/show` metadata when a loopback endpoint is explicitly identifiable as Ollama.
4. A conservative 4096-token fallback.

The UI displays the effective value and source. A theoretical Ollama model maximum is capped at a conservative automatic operating limit such as 8192; users may explicitly raise it. Standard OpenAI-compatible `/v1/models` metadata is not assumed to expose context capacity. Non-standard Ollama probes are never sent to arbitrary remote OpenAI-compatible hosts, and no API key is forwarded to an Ollama discovery endpoint.

A provider-neutral estimator counts mixed ASCII and non-ASCII text conservatively, reserves prompt/schema overhead, a 10% safety margin, and bounded output space. It is a planning guard rather than an exact provider tokenizer.

Budgeting applies to every heavy stage:

- Requirement matching uses ranked Top-K evidence per requirement and deduplicates shared evidence per batch.
- Resume generation splits Markdown by section, then paragraph when necessary.
- Verification uses generated sections and only their cited evidence.

Calls execute sequentially to avoid local-model memory contention. On a provider context-overflow error, multi-item batches bisect. A single requirement drops its lowest-ranked candidate until one remains. A single resume section splits by paragraph. One indivisible item that still exceeds the context window fails with an actionable error. Timeout, authentication, parsing, and connection errors do not trigger context reduction.

## Web Experience

The Run graph displays product stages while node details show internal batches, section names, and estimated input budget without exposing source content. Results open in this order: application resume, match report, growth plan, target resume, interview preparation, Run details.

`target-resume.md` always carries a prominent non-submittable warning and has no approval action. Human approval applies only to `application-resume.md`. Configuration remains local and persistent; automatic context discovery occurs during LLM connection testing and preserves manual overrides.

## Growth Plan Quality

Each important gap produces a specific, achievable learning or portfolio task rather than generic advice. A task contains a stable ID, target capability, priority, estimated effort, concrete work, acceptance checks, evidence artifacts to retain, and the future resume statement it could support. The MVP generates this plan but does not execute projects or track completion.

## Implementation Boundaries

1. Replace old domain models, monolithic backend, workflow, and outputs with the new domain/chains/graph layout.
2. Remove CLI code and dependencies on CLI compatibility while retaining reusable non-CLI modules.
3. Add automatic context discovery and manual override semantics.
4. Generalize context budgeting across matching, sectioned generation, and sectioned verification.
5. Update Web stages, progress details, result permissions, labels, and configuration persistence.
6. Remove obsolete tests and add focused pure-function, chain, graph, checkpoint, process, and Web tests.

Existing user-edited example files are preserved and serve as realistic MVP inputs. Git history and reusable Web infrastructure remain intact; obsolete domain code may be deleted rather than wrapped in compatibility layers.

## Acceptance

- The current example JD and resume complete the full workflow under a 4096-token strategy.
- Application output contains no aspirational statement and every factual change is traceable.
- Every important gap has an actionable task, acceptance criteria, and required evidence.
- Every target-resume aspiration links to a growth-plan task and is visibly non-submittable.
- Context discovery reports its source, falls back safely, and respects manual overrides.
- Matching, generation, and verification remain bounded and recover at batch granularity.
- Restart, retry, and cancel behavior remain deterministic.
- Code clearly demonstrates LangChain Chain responsibilities versus LangGraph orchestration without multi-agent complexity.
