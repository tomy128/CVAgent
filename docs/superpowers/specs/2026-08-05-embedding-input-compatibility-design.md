# Embedding Input Compatibility Design

## Problem

The Web connection test receives `400 invalid input type` from Ollama's OpenAI-compatible Embeddings endpoint. `langchain-openai` can tokenize text locally and submit token ID arrays when context-length checking is enabled. Some compatible endpoints accept only raw strings or string arrays.

## Decision

Construct every OpenAI-compatible `OpenAIEmbeddings` instance through one focused helper and set `check_embedding_ctx_length=False`. This keeps the integration provider-neutral: LangChain sends raw text through the advertised OpenAI-compatible API without detecting Ollama or adding a provider selector.

Both the Web connection test and production evidence retrieval must use the helper so successful testing represents the real workflow configuration. Existing model, endpoint, dimensions, timeout, retry, and API-key behavior remains unchanged.

## Error Handling

Classify responses containing `invalid input type` as `incompatible_input`. The Web UI should explain that the endpoint rejected the Embedding input format while preserving the server's bounded diagnostic message. Secrets must not enter metadata or event details.

## Verification

Add regression tests proving that the shared constructor disables client-side context-length tokenization and that connection testing uses the shared path. Run the complete Python suite and JavaScript syntax check. Existing CLI behavior and user-modified example files are outside this change.
