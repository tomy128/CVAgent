"""Typed Web API contracts with explicit secret handling."""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


class ModelSettings(BaseModel):
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str
    timeout_seconds: float = Field(default=120, ge=1, le=3600)
    max_retries: int = Field(default=1, ge=0, le=5)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = "none"
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    context_window: int | None = Field(default=None, ge=2048, le=1048576)
    resolved_context_window: int | None = Field(default=None, ge=2048, le=1048576)
    context_source: str = "automatic"
    use_server_key: bool = False

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model is required")
        return value.strip()

    def secret(self, server_key: str | None) -> str:
        if self.use_server_key:
            if not server_key:
                raise ValueError("Server API key is not configured")
            return server_key
        if not self.api_key:
            raise ValueError("API key is required")
        return self.api_key.get_secret_value()

    def redacted(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "context_window": self.context_window,
            "resolved_context_window": self.resolved_context_window,
            "context_source": self.context_source,
            "has_api_key": bool(self.api_key),
            "use_server_key": self.use_server_key,
        }

    @property
    def effective_context_window(self) -> int:
        return self.context_window or self.resolved_context_window or 4096


class EmbeddingSettings(ModelSettings):
    dimensions: int | None = Field(default=None, ge=1)

    def redacted(self) -> dict[str, object]:
        return {**super().redacted(), "dimensions": self.dimensions}


class RunSettings(BaseModel):
    llm: ModelSettings
    embedding: EmbeddingSettings
    demo: bool = False

    def redacted(self) -> dict[str, object]:
        return {
            "llm": self.llm.redacted(),
            "embedding": self.embedding.redacted(),
            "demo": self.demo,
        }


class ConnectionTestRequest(BaseModel):
    service: Literal["llm", "embedding"]
    settings: EmbeddingSettings


class ReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    resume_markdown: str | None = None


class RunPublic(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    current_node: str | None = None
    error: dict[str, object] | None = None
    config: dict[str, object]
    results: dict[str, str] = Field(default_factory=dict)
    events: list["EventPublic"] = Field(default_factory=list)


class EventPublic(BaseModel):
    id: int
    run_id: str
    timestamp: str
    type: str
    node: str | None = None
    status: str
    summary: str
    details: dict[str, object] = Field(default_factory=dict)


RunPublic.model_rebuild()
