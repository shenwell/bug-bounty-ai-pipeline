"""LLM provider abstraction."""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

from portfolio.common.config import AppConfig
from portfolio.common.logging import get_logger
from portfolio.guardrails.audit import AuditTrail

logger = get_logger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict[str, str]], actor: str = "system") -> str: ...

    def complete_json(self, messages: list[dict[str, str]], actor: str = "system") -> dict[str, Any]:
        text = self.complete(messages, actor)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)


class AnthropicProvider(LLMProvider):
    def __init__(self, config: AppConfig, audit: AuditTrail | None = None):
        self._model = config.llm.model
        self._max_tokens = config.llm.max_tokens
        self._api_key = config.llm.api_key()
        self._audit = audit
        if not self._api_key:
            raise ValueError(f"Missing API key env: {config.llm.api_key_env}")

    def complete(self, messages: list[dict[str, str]], actor: str = "system") -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        system = ""
        chat = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                chat.append({"role": m["role"], "content": m["content"]})

        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system or anthropic.NOT_GIVEN,
            messages=chat,
        )
        text = response.content[0].text if response.content else ""
        if self._audit:
            self._audit.log(
                actor,
                "llm_call",
                "llm",
                self._model,
                input_data={"messages_len": len(messages)},
                output_data={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
        return text


class OpenAIProvider(LLMProvider):
    def __init__(self, config: AppConfig, audit: AuditTrail | None = None):
        self._model = config.llm.model
        self._max_tokens = config.llm.max_tokens
        self._api_key = config.llm.api_key()
        self._audit = audit
        if not self._api_key:
            raise ValueError(f"Missing API key env: {config.llm.api_key_env}")

    def complete(self, messages: list[dict[str, str]], actor: str = "system") -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=messages,
        )
        text = response.choices[0].message.content or ""
        if self._audit:
            self._audit.log(
                actor,
                "llm_call",
                "llm",
                self._model,
                output_data={"usage": str(response.usage)},
            )
        return text


class StubProvider(LLMProvider):
    """Deterministic fallback when no external LLM is configured (e.g. Cursor-assisted runs)."""

    def __init__(self, config: AppConfig):
        self._model = "stub"

    def complete(self, messages: list[dict[str, str]], actor: str = "system") -> str:
        logger.info("stub_llm_complete", actor=actor, messages=len(messages))
        return (
            '{"adjustment": 1.0, "vectors": ["sqli", "xss", "idor"], "mismatch": ""}'
        )


class HermesLocalProvider(LLMProvider):
    """Stub interface for future local Hermes inference."""

    def __init__(self, config: AppConfig):
        self._endpoint = os.environ.get("HERMES_LOCAL_URL", "http://localhost:11434")

    def complete(self, messages: list[dict[str, str]], actor: str = "system") -> str:
        import httpx

        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{self._endpoint}/v1/chat/completions",
                json={"messages": messages, "stream": False},
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


class LLMProviderFactory:
    @staticmethod
    def create(config: AppConfig, audit: AuditTrail | None = None) -> LLMProvider:
        provider = config.llm.provider.lower()
        if provider == "stub":
            return StubProvider(config)
        if provider in ("anthropic", "openai") and not config.llm.api_key():
            logger.warning("llm_api_key_missing_using_stub", provider=provider)
            return StubProvider(config)
        if provider == "anthropic":
            return AnthropicProvider(config, audit)
        if provider == "openai":
            return OpenAIProvider(config, audit)
        if provider == "hermes_local":
            return HermesLocalProvider(config)
        raise ValueError(f"Unknown LLM provider: {provider}")
