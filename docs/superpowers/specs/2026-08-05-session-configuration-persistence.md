# Local Browser Configuration Persistence

The local single-user workbench will use `localStorage` as its unified browser persistence layer. LLM and Embedding endpoints, models, API keys, timeouts, retries, generation controls, dimensions, server-key choices, demo mode, and the active Run ID persist across refreshes, closed tabs, and browser restarts.

Configuration is saved on field input and change, not only after a successful connection test or Run creation. This prevents a refresh from discarding partially entered settings. API keys are intentionally included in local storage for consistent local-tool behavior, but remain excluded from server metadata and durable Run events. The UI must state that configuration is stored in this browser.

Add JavaScript regression assertions for unified storage, secret retention, and live persistence; run the full Python and JavaScript checks.
