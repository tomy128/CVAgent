# NoNote Resume Generator

A local, evidence-grounded Web tool that turns a job description, master resume, and optional career sources into the strongest honestly submittable resume available today—and a concrete route for closing the remaining gaps.

## Outputs

- `application-resume.md` — verified, submittable resume.
- `match-report.md` — strong, partial, transferable, and missing requirements.
- `growth-plan.md` — bounded learning or portfolio tasks with acceptance evidence.
- `target-resume.md` — visibly aspirational future version; never approvable.
- `interview-prep.md` — evidence-backed answers and honest gap handling.
- `run.json` — retrieval, context, routing, and execution audit.

Resume artifacts (`application-resume.md` and `target-resume.md`) follow the master resume's language. JD-analysis artifacts (`match-report.md`, `growth-plan.md`, and `interview-prep.md`) follow the JD's language.

## Run locally

Requires Python 3.13 and `uv`.

```bash
uv sync --group dev
uv run resume-agent-web
```

Open `http://localhost:8765`, configure separate OpenAI-compatible LLM and Embedding services, upload a JD and master resume, and optionally add Markdown or text Sources. Demo mode runs the complete workflow without model credentials.

Model settings and API keys remain in this browser's `localStorage`. Uploaded inputs, SQLite checkpoints, events, and generated artifacts stay under local `output/<run-id>/` directories. Run metadata and events redact secrets.

## Architecture

LangChain implements small typed tasks: requirement extraction, evidence matching, structured resume-edit decisions, verification, growth planning, and interview preparation. LangGraph orchestrates those chains with explicit state, conditional routes, checkpointed batch loops, one repair pass, explicit skipped stages, and human review. Ordinary Python detects artifact languages, renders stable Markdown, enforces context budgets, and prevents aspirational or unsupported content from entering the application resume.

The model does not own final resume layout. It chooses whether source entries should be kept, reordered, minimally rewritten, or omitted. Deterministic rendering preserves source identity and produces consistent headings, spacing, and lists. Clear source wording remains unchanged; unsafe or generic rewrites fall back to the original entry.

Heavy stages execute sequentially for local models. Context size is discovered from a user override, LangChain model profile, loopback Ollama metadata, or a conservative 4096-token fallback. Matching, resume generation, and verification split at real Graph node boundaries so interrupted Runs resume from completed batches.

## Validate

```bash
uv run pytest
```
