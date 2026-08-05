# Run Recovery and Cancellation

## Failure Chain

The apparent Graph loop is an SSE replay loop: reconnecting starts at event 1, the historical `run_failed` triggers another reload, and the cycle repeats. The underlying retry executes `retrieve_evidence` once. That node combines semantic retrieval and LLM evidence mapping, so node-based error attribution incorrectly labels an LLM `LengthFinishReasonError` as Embedding. Evidence mapping also repeats candidate bodies per requirement, inflating a small Run to the model's 4096-token context limit.

## Event and Retry Contract

Track the highest event ID in the browser, reconnect with `after=<id>`, and ignore duplicate IDs. Close SSE and periodic refresh for terminal states. `node_progress` events distinguish `embedding_retrieval` from `llm_evidence_mapping`; duration and errors inherit that phase. Retry and cancel controls become disabled immediately and reject duplicate API requests.

Checkpoint retry resumes the failed Graph node once with current credentials. The in-memory retriever may rebuild lazily from checkpoint evidence. It must not replay completed Graph nodes in the UI.

## Context Control

Pass requirements once and unique candidate evidence once to the evidence-mapping model. Do not duplicate full chunks per requirement. Classify output truncation and `LengthFinishReasonError` as `context_length`, attribute it to LLM, and explain that the user can increase provider context, reduce inputs, or lower generated scope. Maximum output tokens are not presented as model context size.

## Immediate Cancellation

Production Runs and retries execute in a dedicated spawned process. The parent Web process owns lifecycle state and can terminate/kill the worker, persist `cancelled`, and append one durable cancellation event immediately. SQLite transactions and checkpoint files remain recoverable. The parent refreshes in-memory status from atomic metadata written by the worker. Tests may retain in-process threads for speed, but process lifecycle behavior receives focused tests.

Human review remains in the Web process because it is already paused and non-running; cancellation while waiting remains immediate. Provider-specific commands such as `ollama stop` are prohibited.

## Verification

Cover event cursor de-duplication, terminal disconnect, prompt uniqueness, phase attribution, context classification, idempotent controls, process termination, and existing Graph/CLI behavior. Run the full Python suite, JavaScript syntax checks, and a local Web smoke test.
