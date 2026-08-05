# LLM Execution Observability Design

## Problem

The connection test asks for a trivial `OK`, while the workflow uses validated structured output. With Ollama `qwen3.5:4b`, thinking is enabled by default: the real `extract_requirements` call can run until timeout although the basic test succeeds. Graph events currently expose only node start and completion, so a blocking model call appears frozen.

## Runtime Controls

Add provider-neutral LLM settings for reasoning effort (`none`, `low`, `medium`, `high`, or automatic) and maximum output tokens. Default reasoning to `none` because resume extraction, mapping, drafting, and verification prioritize bounded structured output over extended reasoning. Default maximum output to 4096. Pass optional controls through `ChatOpenAI` for connection tests and workflow calls.

## Representative Testing

The LLM connection test must request a small Pydantic-validated structured response using the same model construction as production. A passing test therefore verifies endpoint access and the structured-output capability required by the Graph.

## Progress Events

While any observed Graph node runs, emit a heartbeat every five seconds with elapsed seconds. Completion and failure events include total duration. Heartbeats are operational events only; model tokens and hidden reasoning are not streamed. The UI displays the active node and elapsed time, and explains after 30 seconds that the model is still processing.

Cancellation remains cooperative: a synchronous provider request cannot be forcibly stopped safely and ends on provider response or configured timeout.

## Verification

Test model option propagation, structured connection testing, heartbeat lifecycle, duration details, and existing Run behavior. Run all Python tests, JavaScript syntax validation, and an actual Ollama structured call with thinking disabled.
