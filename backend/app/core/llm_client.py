"""Unified LLM client factory — cached singleton + shared chat_completion helper."""

from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AiServiceException

_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client configured from settings.

    Falls back to nvidia_* settings when llm_* fields are empty.
    """
    global _client
    if _client is not None:
        return _client

    api_key = settings.llm_api_key or settings.nvidia_api_key
    base_url = settings.llm_base_url or settings.nvidia_base_url

    if not api_key:
        raise AiServiceException("No LLM API key configured (set llm_api_key or nvidia_api_key)")

    _client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return _client


async def chat_completion(system: str, user: str, **kwargs: object) -> str:
    """Send a chat completion request using the cached LLM client."""
    client = get_llm_client()
    model = settings.llm_model or settings.nvidia_model

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=settings.nvidia_temperature,
        max_tokens=settings.nvidia_max_tokens,
        **kwargs,
    )
    return response.choices[0].message.content or ""
