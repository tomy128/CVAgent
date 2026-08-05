# NoNote Resume Agent

An evidence-grounded CLI that tailors a master resume to a job description without inventing experience. LangGraph owns workflow state, bounded retry, and human approval; LangChain provides document splitting, hybrid semantic retrieval, model integration, and structured output.

## MVP workflow

```text
JD extraction → lexical + semantic retrieval → resume draft → claim verification
                    ↑                         retry once ↵
                    └──────── unsupported claim ─────────┘
                              ↓
                    human approval → Markdown artifacts
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
  --demo --yes
```

The master resume is always the primary evidence source. Add optional supporting material only when it contains relevant details omitted from the resume:

```bash
uv run resume-agent tailor \
  --jd examples/jd.md \
  --resume examples/resume.md \
  --sources examples/evidence \
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
  --sources path/to/optional-career-materials
```

The CLI pauses before final output. Review the verified draft and approve it, edit it in the prompt flow, or reject it. Inputs remain read-only. SQLite checkpoints and generated files are stored under `output/<run-id>/` by default.

## Architecture boundaries

The CLI is the product entrypoint. LangGraph coordinates explicit workflow state, checkpointing, one evidence-retrieval retry, and human approval. LangChain builds a per-run in-memory vector index and combines semantic matches with exact lexical evidence. Backend adapters handle either deterministic offline behavior or structured model calls. Evidence loading and claim verification remain separate from generation so changed claims can be traced to an input source. The MVP accepts Markdown or plain text and writes only to the selected output directory; web UI, persistent indexes, document conversion, and external system integrations are outside its scope.

## Validate

```bash
uv run pytest
uv run resume-agent tailor --help
```

## Local Web workbench

Start the framework-free Web interface on the loopback address:

```bash
uv run resume-agent-web
```

Open `http://localhost:8765`. The page provides independent LLM and Embedding configuration, representative connection tests, reasoning and output controls, JD and resume upload, optional supporting sources, live LangGraph node events, and full-screen Markdown review. Reasoning defaults to `none` for bounded structured resume tasks. Model tokens are not streamed; five-second workflow heartbeats keep slow model calls observable and report node duration.

Non-secret model settings stay in browser storage. API keys remain in page memory unless the page is configured to use `OPENAI_API_KEY` from the server environment. Uploaded inputs and generated artifacts stay under the local `output/<run-id>/` directory.
