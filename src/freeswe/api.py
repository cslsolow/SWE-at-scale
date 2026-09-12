"""Small OpenAI-compatible chat client with no provider-specific defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class Generation:
    content: str
    raw: Any


class ChatClient:
    """Call the configured model without persisting credentials or endpoints.

    The official SDK default is used when ``OPENAI_BASE_URL`` is unset. A
    caller may set that environment variable at runtime for any compatible
    local server; it is deliberately not hard-coded in this repository.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 1_800.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required")
        endpoint = base_url or os.getenv("OPENAI_BASE_URL")
        kwargs: dict[str, Any] = {
            "api_key": key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if endpoint:
            kwargs["base_url"] = endpoint
        self._client = OpenAI(**kwargs)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 8_192,
    ) -> Generation:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        return Generation(content=content, raw=response)
