import io
import json

from resume_agent.web import context
from resume_agent.web.context import discover_context_window
from resume_agent.web.app import resolve_run_context
from resume_agent.web.schemas import EmbeddingSettings, ModelSettings, RunSettings


class FakeModel:
    def __init__(self, profile=None) -> None:
        self.profile = profile


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_langchain_profile_has_priority() -> None:
    result = discover_context_window(
        FakeModel({"max_input_tokens": 32768}), "known-model", None
    )

    assert result.tokens == 32768
    assert result.source == "langchain_profile"


def test_loopback_ollama_theoretical_context_is_capped(monkeypatch) -> None:
    payload = {"model_info": {"qwen.context_length": 32768}}
    monkeypatch.setattr(
        context,
        "urlopen",
        lambda request, timeout: Response(json.dumps(payload).encode()),
    )

    result = discover_context_window(
        FakeModel(), "qwen", "http://localhost:11434/v1"
    )

    assert result.tokens == 8192
    assert result.source == "ollama_model_capped"


def test_remote_compatible_endpoint_is_not_probed(monkeypatch) -> None:
    monkeypatch.setattr(
        context,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not probe")),
    )

    result = discover_context_window(
        FakeModel(), "private-model", "https://models.example/v1"
    )

    assert result.tokens == 4096
    assert result.source == "conservative_default"


def test_demo_run_records_its_effective_context() -> None:
    settings = RunSettings(
        demo=True,
        llm=ModelSettings(model="demo"),
        embedding=EmbeddingSettings(model="demo"),
    )

    resolved = resolve_run_context(settings)

    assert resolved.llm.effective_context_window == 4096
    assert resolved.llm.context_source == "demo_default"
