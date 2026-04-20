"""Abstract LLM provider interface and concrete implementations."""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a prompt to the LLM and return the response text."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama local inference provider."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "gemma4:latest",
        keep_alive: str = "10m",
        timeout: int = 480,
    ):
        from urllib.error import URLError
        from urllib.request import Request, urlopen

        self.urlopen = urlopen
        self.Request = Request
        self.URLError = URLError

        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model
        self.keep_alive = keep_alive
        self.timeout = timeout

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Call Ollama's /api/chat endpoint."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0.3},
            }
        ).encode("utf-8")

        req = self.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
                content = data["message"]["content"].strip()
                # Strip <think>...</think> blocks from reasoning models
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                logger.debug(f"Ollama response: {len(content)} chars")
                return content
        except self.URLError as e:
            error_msg = (
                f"Ollama is not reachable at {self.base_url}\n\n"
                f"Troubleshooting:\n"
                f"  1. Is Ollama running? Start it with: ollama serve\n"
                f"  2. Is it on a different host/port? Set OLLAMA_BASE_URL environment variable.\n"
                f"  3. Model {self.model} installed? Run: ollama pull {self.model}\n\n"
                f"Error details: {e}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT models)."""

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: str | None = None,
        timeout: int = 480,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )

        try:
            import openai

            self.openai = openai
            openai.api_key = self.api_key
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Call OpenAI's Chat Completion API."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                timeout=self.timeout,
            )
            content = response.choices[0].message.content.strip()
            logger.debug(f"OpenAI response: {len(content)} chars")
            return content
        except Exception as e:
            error_msg = f"OpenAI API error: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        api_key: str | None = None,
        timeout: int = 480,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter."
            )

        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Call Anthropic's Messages API."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
                timeout=self.timeout,
            )
            content = response.content[0].text.strip()
            logger.debug(f"Anthropic response: {len(content)} chars")
            return content
        except Exception as e:
            error_msg = f"Anthropic API error: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


def get_provider(
    provider_type: str,
    model: str,
    **config: Any,
) -> LLMProvider:
    """Factory function to create an LLM provider instance."""
    provider_type = provider_type.lower().strip()

    logger.debug(f"Loading provider: {provider_type}, model: {model}")

    if provider_type == "ollama":
        return OllamaProvider(
            model=model,
            keep_alive=config.get("keep_alive", "10m"),
            base_url=config.get("base_url"),
        )
    elif provider_type == "openai":
        return OpenAIProvider(
            model=model,
            api_key=config.get("api_key"),
        )
    elif provider_type == "anthropic":
        return AnthropicProvider(
            model=model,
            api_key=config.get("api_key"),
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider_type}. Supported: ollama, openai, anthropic"
        )


def parse_json_response(response: str) -> Any:
    """Extract and parse the first JSON object from an LLM response."""
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", response).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in LLM response:\n{response[:300]}")
