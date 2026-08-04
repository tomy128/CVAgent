"""OpenAI-compatible Embedding construction for the Web workbench."""

import os
from typing import Any

from langchain_openai import OpenAIEmbeddings

from resume_agent.web.schemas import EmbeddingSettings


def build_openai_embeddings(
    settings: EmbeddingSettings,
    server_key: str | None = None,
) -> OpenAIEmbeddings:
    """Build a client that sends raw text to compatible Embeddings APIs."""
    options: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.secret(server_key or os.getenv("OPENAI_API_KEY")),
        "base_url": settings.base_url,
        "request_timeout": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "check_embedding_ctx_length": False,
    }
    if settings.dimensions:
        options["dimensions"] = settings.dimensions
    return OpenAIEmbeddings(**options)
