# Embedding Input Compatibility Implementation

1. Add a Web-layer factory for `OpenAIEmbeddings` that forwards existing settings and disables client-side context-length tokenization.
2. Use the factory in connection testing and production evidence retrieval.
3. Classify `invalid input type` as an actionable compatibility failure in the API and UI.
4. Add regression tests, run the full suite and JavaScript syntax check, then commit implementation separately.
