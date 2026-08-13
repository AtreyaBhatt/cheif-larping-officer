"""
Shared OpenRouter API client: the "call the API, strip markdown fences,
parse JSON" logic that both the daily digest generator (digest.py) and
the on-demand project suggester (project_suggester.py) need. Extracted
here so there's one tested code path for talking to OpenRouter, not two
copies that can drift.
"""
from __future__ import annotations

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


def get_api_key() -> str:
    return os.environ["OPENROUTER_API_KEY"]


def get_model(override: str | None = None) -> str:
    return override or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # handles ```json ... ``` or plain ``` ... ```
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def call_openrouter_json(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    temperature: float = 0.7,
    timeout: int = 60,
) -> list | dict:
    """
    Calls OpenRouter, strips markdown fences from the response, parses
    it as JSON, and returns the parsed structure (list or dict,
    depending on what the prompt asked for). Raises requests.RequestException
    on network/HTTP failure, or ValueError if the response isn't valid JSON.
    """
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    raw_response = data["choices"][0]["message"]["content"]

    cleaned = strip_markdown_fences(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s\nRaw response: %r", e, raw_response)
        raise ValueError("LLM did not return valid JSON") from e
