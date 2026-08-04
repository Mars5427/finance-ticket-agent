from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.llm.config import LLMConfig


@dataclass(frozen=True)
class LLMCompletion:
    content: str
    elapsed_ms: int


class LLMClientProtocol(Protocol):
    def complete_json(self, messages: list[dict[str, str]], config: LLMConfig) -> LLMCompletion:
        ...


class OpenAICompatibleLLMClient:
    def complete_json(self, messages: list[dict[str, str]], config: LLMConfig) -> LLMCompletion:
        started = perf_counter()
        payload = build_chat_completions_payload(messages, config)
        request = urllib.request.Request(
            f"{config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {error_body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

        decoded = json.loads(response_body)
        try:
            content = decoded["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not contain choices[0].message.content") from exc
        if not isinstance(content, str):
            raise RuntimeError("LLM message content is not a string")
        return LLMCompletion(content=content, elapsed_ms=int((perf_counter() - started) * 1000))


def build_chat_completions_payload(messages: list[dict[str, str]], config: LLMConfig) -> dict[str, object]:
    return {
        "model": config.model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "max_tokens": config.max_tokens,
    }
