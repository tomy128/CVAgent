# Semantic Evidence Workflow Design

## User goal

Tailor a master resume to a job description using semantically relevant, traceable career facts. The workflow should provide realistic LangChain retrieval experience and LangGraph orchestration without requiring users to prepare a separate evidence library before receiving value.

## Product scope

The master resume is required and always acts as the primary evidence source. An optional `--sources` directory may contain project notes, old resumes, work records, or other supporting Markdown and text files. The existing `--evidence` option remains temporarily as a compatibility alias. When the master resume is sufficient, no supplemental directory is needed.

The MVP builds an in-memory index for each run. Persistent indexes, incremental updates, PDF/Word conversion, web UI, and external integrations remain out of scope.

## Architecture

LangChain owns operations inside workflow nodes:

- Convert source text into Documents with source metadata.
- Split documents into traceable chunks.
- Generate embeddings in real model mode.
- Store vectors in an in-memory VectorStore and expose a Retriever.
- Execute prompt templates and typed structured model output.

LangGraph owns workflow behavior:

1. Extract JD requirements.
2. Build the temporary evidence index.
3. Retrieve evidence for each requirement.
4. Draft the tailored resume.
5. Verify generated claims.
6. Route failed verification through at most one expanded retrieval and rewrite cycle.
7. Pause for human approval, then finalize or reject.

The VectorStore is process-local and never enters Graph State or SQLite checkpoints. Serializable evidence chunks, queries, rankings, retry state, and verification results are checkpointed. On process recovery, the index is rebuilt from the original inputs.

## Retrieval

Each requirement produces a query from its description, keywords, and category. Retrieval combines the existing lexical search with semantic results. Results are deduplicated by evidence ID; exact keyword matches remain high priority while semantic matches improve recall.

Real mode uses an OpenAI-compatible embedding model. Demo mode uses deterministic local embeddings so tests and demonstrations require no API key. An embedding failure in real mode is reported explicitly rather than silently pretending semantic retrieval occurred.

## Verification loop

Graph State records `retrieval_attempt`, queries, ranked results, retry reason, and verification output. If verification finds unsupported claims on the first attempt, the workflow derives supplemental queries from those claims, increases retrieval breadth, redrafts, and verifies again. A second failure cannot loop again: unsupported wording is removed and the corrected draft proceeds to human review.

Retry requires new queries and retrieval results; merely asking the model to try again is not a valid retry. Missing evidence is reported as a coverage gap and must never be rewritten as candidate experience.

## Outputs and errors

`requirement-map.md` reports coverage, retrieval method, evidence source, and retry status. `run.json` records queries, rankings, methods, attempts, and routing reasons. Existing resume, evidence report, interview question, and checkpoint outputs remain.

Empty supplemental files are skipped with their sources recorded. The run stops when no usable evidence exists. Structured model output may retry once inside its node; a second parsing failure terminates while preserving the checkpoint. Rejected runs retain their audit output with rejected status.

## Testing and acceptance

- Unit-test deterministic embeddings, hybrid deduplication and ranking, query expansion, and retry limits.
- Graph-test first-pass success, retry success, retry exhaustion, and human rejection.
- Run the complete CLI in `--demo --yes` mode without network access.
- Verify every retained resume claim references evidence and no run exceeds one retrieval retry.
- Confirm both resume-only input and resume-plus-sources input work.
- Confirm audit output explains whether each result came from lexical or semantic retrieval.

The feature is complete when the offline demo visibly exercises semantic retrieval, a failure fixture exercises exactly one LangGraph loop, and all generated claims remain traceable to the master resume or optional supplemental sources.
