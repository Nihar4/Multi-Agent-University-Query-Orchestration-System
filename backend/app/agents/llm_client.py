"""Thin wrapper around the NVIDIA NIM OpenAI-compatible client."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from ..config import get_settings

_settings = get_settings()
_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not _settings.LLM_API_KEY:
            raise RuntimeError(
                "LLM_API_KEY is not set. Put it in the repo-root .env file."
            )
        _client = OpenAI(base_url=_settings.LLM_BASE_URL, api_key=_settings.LLM_API_KEY)
    return _client


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    tool_choice: str | dict | None = None,
):
    """Single non-streaming chat completion. Returns the raw OpenAI response object."""
    client = get_client()
    kwargs: dict[str, Any] = dict(
        model=_settings.LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    return client.chat.completions.create(**kwargs)


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response."""
    text = text.strip()
    # Strip code fences if present
    if text.startswith("```"):
        # remove first fence line and trailing fence
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```"))
    # Try to locate first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in: {text!r}")
    return json.loads(text[start : end + 1])
