from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = "gemma4:latest"


def chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    keep_alive: str = "10m",
    timeout: int = 480,
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,  # Disable chain-of-thought for Qwen3/thinking models
            "keep_alive": keep_alive,
            "options": {"temperature": 0.3},
        }
    ).encode("utf-8")

    req = Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            content = data["message"]["content"].strip()
            # Strip <think>...</think> blocks emitted by reasoning models (e.g. Qwen3)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            logger.debug(f"Ollama response from {model}: {len(content)} chars")
            return content
    except URLError as e:
        error_msg = (
            f"Ollama is not reachable at {OLLAMA_BASE_URL}\n\n"
            f"Troubleshooting:\n"
            f"  1. Is Ollama running? Start it with: ollama serve\n"
            f"  2. Is it on a different host/port? Set OLLAMA_BASE_URL environment variable.\n"
            f"  3. Model {model} installed? Run: ollama pull {model}\n\n"
            f"Error details: {e}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def parse_json_response(response: str) -> Any:
    """Extract and parse the first JSON object from an LLM response."""
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", response).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in Ollama response:\n{response[:300]}")
