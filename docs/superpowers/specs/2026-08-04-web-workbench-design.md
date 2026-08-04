# Resume Agent Web Workbench Design

## User goal

Allow an individual job seeker to configure separate LLM and embedding services, upload a JD and master resume with optional supporting sources, observe the LangGraph workflow, and review evidence-grounded results without using a CLI. The Web interface must make local-model latency and timeout failures diagnosable.

## MVP scope

The application is a local, single-user responsive Web tool started from the Python project. It has no accounts, cloud deployment, collaboration, run-history browser, PDF/Word ingestion, persistent vector index, or frontend framework. Only one Run may be active at a time.

The existing CLI and Web layer share the same Agent core. The Web layer does not duplicate workflow or evidence logic.

## Technology

- FastAPI serves API endpoints and static assets.
- The frontend uses native HTML, CSS, SVG, and JavaScript modules with no build step.
- Server-Sent Events deliver workflow events; LLM tokens are not streamed.
- `markdown-it` renders Markdown, `highlight.js` highlights code, and DOMPurify sanitizes rendered output. Raw Markdown HTML is disabled. Pinned browser assets are stored locally rather than loaded from a runtime CDN.
- SQLite checkpoints and `output/<run-id>/` remain the source of durable Run state and artifacts.

## Backend structure

Add a bounded Web package under `src/resume_agent/web/`:

- `app.py`: FastAPI creation, static serving, and routes.
- `schemas.py`: redacted configuration, Run, event, and review models.
- `service.py`: Run lifecycle, background Graph execution, cancellation, and recovery.
- `events.py`: ordered event storage and SSE subscriptions.
- `static/`: the HTML shell, CSS, JavaScript modules, icons, and pinned vendor assets.

Move reusable CLI construction into shared functions so CLI and Web both create backends, retrievers, checkpoints, and run directories from typed configuration.

## Configuration

LLM and Embedding configurations are independent. Each supports Base URL, API Key, model, timeout seconds, and maximum retries. Embedding additionally supports optional dimensions. Timeout is passed to the underlying LangChain/OpenAI-compatible client rather than implemented only at the route level.

`POST /api/connections/test` tests exactly one service and returns duration plus a typed result: success, timeout, authentication, model-not-found, connection-refused, invalid-response, or unknown. Connection tests are recommended but do not block Run creation.

The browser stores non-secret configuration locally. API keys remain in page memory. A server environment key can be selected without exposing its value to the browser. API keys are excluded from responses, events, checkpoints, artifacts, and logs.

## Inputs

`POST /api/runs` accepts multipart form data containing JSON configuration, one JD, one master resume, and zero or more source files. MVP accepts UTF-8 `.md` and `.txt`. Each file is limited to 5 MB and all inputs to 20 MB. Filenames are normalized to safe basenames and duplicate names receive deterministic suffixes.

Inputs are stored under `output/<run-id>/inputs/` so a checkpoint can be resumed after refresh or server restart. The master resume remains the primary evidence source; uploaded sources are supplemental.

## Run API and state

- `POST /api/runs`: validate inputs, create a Run, and start background execution.
- `GET /api/runs/{run_id}`: return redacted configuration, lifecycle state, Graph snapshot, and available results.
- `GET /api/runs/{run_id}/events`: stream ordered SSE events and honor `Last-Event-ID` on reconnect.
- `POST /api/runs/{run_id}/review`: approve, approve edited Markdown, or reject the LangGraph interrupt.
- `POST /api/runs/{run_id}/cancel`: request bounded cancellation.
- `POST /api/runs/{run_id}/retry`: update allowed model timeout fields and resume from a failed or interrupted node.

Lifecycle states are preparing, running, waiting_review, approved, rejected, failed, cancelling, cancelled, and interrupted. A browser disconnect never cancels a Run. Cancellation is checked between Graph nodes; an active HTTP request may continue until response or timeout.

After server restart, an unfinished Run becomes interrupted. The user explicitly resumes it from its checkpoint; the server never silently repeats an external model request.

## Event model

Every event has monotonically increasing ID, Run ID, timestamp, type, node, status, public summary, duration, and redacted details. Event types cover Run lifecycle, node started/completed/failed/skipped, progress, retry, review required, and result available.

Embedding progress reports completed and total chunks or batches when observable. Events never contain API keys, full prompts, complete uploaded documents, or full generated resumes. Detailed model errors may include endpoint host, model, timeout, HTTP status, and sanitized response summary.

## Interface

Use the approved split workbench. The fixed left sidebar contains separate LLM and Embedding sections, test actions, uploaded inputs, and the Run action. The main workspace contains Run identity, elapsed time, cancel control, Graph, current-node progress, recent public events, and result summaries.

The Graph shows the fixed workflow and bounded retry edge. Node states are pending, running, complete, waiting, failed, skipped, and retry. Selecting a node opens an adjacent inspector with model, timeout, timing, progress, input/output summaries, retry reason, and recovery actions. An ordered semantic list mirrors the SVG for assistive technology.

Model timeout errors explicitly show elapsed time, endpoint, model, configured timeout, and actions to increase timeout, test connection, retry, or cancel.

## Result review

Results open in a full-viewport review surface with tabs for tailored resume, requirement map, evidence report, interview questions, and Run details. Markdown results provide rendered and source modes. Source edits update the preview after a short debounce and are submitted with approval.

The fixed review header provides back, reject, and approve actions. A review inspector shows verification status, edits from the master resume, evidence markers, and changed-claim highlighting. The interface never confines the resume to a small dashboard card.

## Visual and responsive design

Follow `DESIGN.md` and the Quiet Instrument direction: literal white background, cool neutral surfaces, sky-teal primary, and semantic green/amber/red states. Use system-product typography, restrained borders, and state-driven motion. Avoid chatbot structure, decorative cards, gradients, glows, and default raw logs.

Desktop is primary. Below 900px configuration collapses above the workspace, Graph becomes horizontally scrollable, and review content/metadata become separate tabs. All interactions remain keyboard accessible and honor reduced motion.

## Errors and security

Validation errors attach to their fields. Service errors use typed categories and recovery actions. SSE automatically reconnects without restarting work. Refresh restores the most recent Run ID from browser storage and reloads server state.

Uploaded filenames cannot escape the Run input directory. Markdown raw HTML is disabled and output is sanitized. Secrets are represented only as presence flags. Logs and exception serialization use explicit allowlists rather than attempting to redact arbitrary dictionaries afterward.

## Testing and acceptance

- Preserve all existing CLI tests and behavior.
- API-test configuration validation, secret omission, upload constraints, active-Run exclusion, Run reads, SSE replay, review, cancellation, retry, and recovery.
- Integration-test deterministic Graph event order, one retry, review interrupt, timeout classification, and interrupted checkpoint recovery.
- Security-test filename normalization, upload limits, Markdown HTML blocking, and key exclusion from responses/events/logs.
- Test pure JavaScript state and formatting modules with Node's built-in test runner; perform browser acceptance for the complete workflow and accessibility states.

The MVP is complete when a user can test separate local services, run with JD and resume only or optional sources, observe Graph and embedding progress, diagnose a simulated timeout, recover without re-uploading, edit rendered/source Markdown in full-screen review, approve or reject, refresh, and still see the final result.
