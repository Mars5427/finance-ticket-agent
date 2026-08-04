from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    provider: str = "disabled"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 10.0
    max_tokens: int = 800

    @property
    def available(self) -> bool:
        return self.enabled and self.provider != "disabled" and bool(self.api_key) and bool(self.model) and bool(self.base_url)

    @property
    def skip_reason(self) -> str:
        if not self.enabled:
            return "LLM_ENABLED is not true."
        if self.provider == "disabled":
            return "LLM_PROVIDER is disabled."
        if not self.api_key:
            return "LLM_API_KEY is not configured."
        if not self.model:
            return "LLM_MODEL is not configured."
        if not self.base_url:
            return "LLM_BASE_URL is not configured."
        return "LLM is available."


def get_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "disabled").strip().lower() or "disabled"
    enabled = _env_bool(os.getenv("LLM_ENABLED", "false")) and provider != "disabled"
    model = os.getenv("LLM_MODEL", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip() or _default_base_url(provider)
    timeout_seconds = _env_float(os.getenv("LLM_TIMEOUT_SECONDS", "10"), default=10.0)
    max_tokens = _env_int(os.getenv("LLM_MAX_TOKENS", "800"), default=800)
    return LLMConfig(
        enabled=enabled,
        provider=provider,
        api_key=os.getenv("LLM_API_KEY", "").strip(),
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )


def _default_base_url(provider: str) -> str:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "deepseek":
        return "https://api.deepseek.com"
    return ""


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(value: str | None, default: float) -> float:
    try:
        parsed = float(value or "")
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return parsed if parsed > 0 else default
