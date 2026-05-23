"""LangChain ChatOpenAI configured for the NVIDIA NIM endpoint.

NVIDIA NIM exposes an OpenAI-compatible API, so ChatOpenAI works as-is
once base_url and api_key are pointed at it.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from ..config import get_settings


@lru_cache(maxsize=4)
def get_chat_llm(temperature: float = 0.2, max_tokens: int = 1024) -> ChatOpenAI:
    """Return a cached ChatOpenAI client (cached by (temp, max_tokens))."""
    settings = get_settings()
    if not settings.LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY is not set. Put it in the repo-root .env file."
        )
    return ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=90,
    )
