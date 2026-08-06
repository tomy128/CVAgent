"""Best-effort model context discovery with conservative fallbacks."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from langchain_core.language_models import BaseChatModel


DEFAULT_CONTEXT_WINDOW = 4096
MAX_AUTOMATIC_OLLAMA_CONTEXT = 8192


@dataclass(frozen=True)
class ContextDiscovery:
    tokens: int
    source: str


def discover_context_window(
    model: BaseChatModel,
    model_name: str,
    base_url: str | None,
) -> ContextDiscovery:
    profile = getattr(model, "profile", None) or {}
    profile_tokens = profile.get("max_input_tokens")
    if isinstance(profile_tokens, int) and profile_tokens >= 2048:
        return ContextDiscovery(profile_tokens, "langchain_profile")
    ollama = _discover_loopback_ollama(model_name, base_url)
    return ollama or ContextDiscovery(DEFAULT_CONTEXT_WINDOW, "conservative_default")


def _discover_loopback_ollama(
    model_name: str, base_url: str | None
) -> ContextDiscovery | None:
    if not base_url:
        return None
    parsed = urlparse(base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return None
    root = f"{parsed.scheme or 'http'}://{parsed.netloc}"
    request = Request(
        f"{root}/api/show",
        data=json.dumps({"model": model_name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        return None
    parameters = str(payload.get("parameters", ""))
    configured = re.search(r"(?:^|\n)\s*num_ctx\s+(\d+)", parameters)
    if configured:
        return ContextDiscovery(max(2048, int(configured.group(1))), "ollama_config")
    theoretical = [
        value
        for key, value in payload.get("model_info", {}).items()
        if key.endswith(".context_length") and isinstance(value, int)
    ]
    if theoretical:
        return ContextDiscovery(
            min(max(theoretical), MAX_AUTOMATIC_OLLAMA_CONTEXT),
            "ollama_model_capped",
        )
    return None
