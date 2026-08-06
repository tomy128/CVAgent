"""Shared chat-model construction and structured invocation."""

from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


Output = TypeVar("Output", bound=BaseModel)


def build_chat_model(
    model: str,
    api_key: str,
    base_url: str | None = None,
    timeout: float = 90,
    max_retries: int = 2,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
) -> ChatOpenAI:
    options: dict[str, object] = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": 0,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if reasoning_effort is not None:
        options["reasoning_effort"] = reasoning_effort
    if max_output_tokens is not None:
        options["max_tokens"] = max_output_tokens
    return ChatOpenAI(**options)


def invoke_structured(
    model: BaseChatModel,
    output: type[Output],
    system: str,
    human: str,
    values: dict[str, object],
) -> Output:
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    return (prompt | model.with_structured_output(output)).invoke(values)
