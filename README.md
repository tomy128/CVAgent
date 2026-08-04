# NoNote Resume Agent

An evidence-grounded CLI that tailors a master resume to a job description without inventing experience. LangGraph owns workflow state and human approval; LangChain provides model integration and structured output.

## MVP workflow

```text
JD extraction → evidence retrieval → resume draft → claim verification
             → human approval → Markdown artifacts
```

Generated runs contain:

- `requirement-map.md`
- `tailored-resume.md`
- `evidence-report.md`
- `interview-questions.md`
- `run.json`

## Setup

Requires Python 3.13 and `uv`.

```bash
uv sync --group dev
```

Run the included deterministic demo without an API key:

```bash
uv run resume-agent tailor \
  --jd examples/jd.md \
  --resume examples/resume.md \
  --evidence examples/evidence \
  --demo --yes
```

For an OpenAI-compatible model:

```bash
export OPENAI_API_KEY="..."
export RESUME_AGENT_MODEL="gpt-5-mini"
# Optional: export OPENAI_BASE_URL="https://provider.example/v1"

uv run resume-agent tailor \
  --jd path/to/jd.md \
  --resume path/to/master-resume.md \
  --evidence path/to/evidence
```

The CLI pauses before final output. Review the verified draft and approve it, edit it in the prompt flow, or reject it. Inputs remain read-only. SQLite checkpoints and generated files are stored under `output/<run-id>/` by default.

## Architecture boundaries

The CLI is the product entrypoint. LangGraph coordinates explicit workflow state, checkpointing, and human approval. Backend adapters handle either deterministic offline behavior or structured model calls. Evidence loading and claim verification remain separate from generation so every resume claim can be traced to an input source. The MVP accepts Markdown or plain text and writes only to the selected output directory; web UI, document conversion, and external system integrations are outside its scope.

## Validate

```bash
uv run pytest
uv run resume-agent tailor --help
```
