# Resume Agent CLI MVP Design

## User goal

Turn a real master resume and project evidence into a job-specific resume while preventing unsupported claims. The first user is a job seeker who needs repeatable, auditable tailoring rather than generic prose generation.

## Core tradeoff

The MVP favors evidence traceability over polished automation. It uses local Markdown/text inputs and an interactive CLI. It does not scrape job sites, edit PDFs, submit applications, or provide a web UI.

## Workflow

1. Extract structured requirements from the JD.
2. Split the master resume and evidence files into source-addressable chunks.
3. Retrieve candidate evidence for every requirement.
4. Draft a tailored resume whose claims carry evidence IDs.
5. Verify every claim in a separate node and remove unsupported wording.
6. Pause with a LangGraph interrupt for human approval or editing.
7. Write auditable Markdown and JSON artifacts.

## Architecture

- LangGraph: state, nodes, conditional routing, checkpointing, interrupt/resume.
- LangChain: OpenAI-compatible model adapter and Pydantic structured output.
- SQLite: local run checkpoint persistence.
- Deterministic demo backend: offline workflow verification and tests.

Input files are never modified. Evidence chunks retain source paths and stable IDs. A rejected run still emits an audit bundle, but its status remains rejected.

## Risks

- LLMs may create plausible but unsupported wording. Independent verification and evidence IDs reduce, but do not eliminate, this risk.
- Lexical retrieval may miss semantic matches. Embedding retrieval can follow after an evaluation set proves the need.
- Resume quality is subjective. The MVP measures unsupported-claim rate and human edit rate before optimizing style.

## Evolution

After CLI validation, add evaluation fixtures, semantic retrieval, FastAPI streaming, and a Vue review interface. External job platforms and automatic submission remain out of scope until there is a demonstrated user need.
