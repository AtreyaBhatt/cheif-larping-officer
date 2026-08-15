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
    timeout: int = 30,
) -> list | dict:
    """
    Calls OpenRouter, strips markdown fences from the response, parses
    it as JSON, and returns the parsed structure (list or dict,
    depending on what the prompt asked for). Raises requests.RequestException
    on network/HTTP failure, or ValueError if the response isn't valid JSON
    or if OpenRouter returned a 200 with an error payload instead of a
    completion (e.g. rate-limited, model unavailable) — that shape has
    no "choices" key, so it's treated as a ValueError rather than
    letting a raw KeyError escape to the caller.
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

    if "error" in data:
        # OpenRouter returns HTTP 200 with an {"error": {...}} body for
        # some failure modes (rate limits, model overloaded/unavailable)
        # rather than a non-2xx status, so raise_for_status() above
        # doesn't catch it. Surface the real reason instead of letting
        # the KeyError below fire on data["choices"].
        message = data["error"].get("message", str(data["error"])) if isinstance(data["error"], dict) else str(data["error"])
        logger.error("OpenRouter returned an error payload: %s", message)
        raise ValueError(f"OpenRouter API error: {message}")

    if "choices" not in data or not data["choices"]:
        logger.error("OpenRouter response missing 'choices': %r", data)
        raise ValueError(f"OpenRouter response had no choices: {data!r}")

    raw_response = data["choices"][0]["message"]["content"]

    cleaned = strip_markdown_fences(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s\nRaw response: %r", e, raw_response)
        raise ValueError("LLM did not return valid JSON") from e
