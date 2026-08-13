"""
On-demand project suggestions: given a content_ideas row (from the
Digest or Posts tab), ask an LLM to suggest a real project that would
demonstrate the underlying technology. Explicitly NOT part of the daily
cron pipeline — this fires only when the person presses a key in the
TUI on a specific idea, so it never adds uncontrolled daily LLM cost.

Requires OPENROUTER_API_KEY in the environment, same as the digest
generator. Model configurable via OPENROUTER_MODEL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from brandos.openrouter_client import call_openrouter_json, get_api_key, get_model

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You suggest small, concrete, buildable side projects \
that demonstrate a specific technology or news item to a technical \
audience. Given one article/idea, suggest ONE project.

Respond with ONLY a JSON object (not an array) with exactly these fields:
- title: a short, specific project name (not generic like "AI Chatbot" —
  specific like "Slack bot that summarizes GitHub PR diffs using <the
  specific tech from the idea>")
- description: 2-4 sentences describing what the project does, why it's a
  good demonstration of the underlying technology, and roughly how hard it
  would be to build (a weekend project vs a multi-week effort)
- category: one of AI, LLMs, Startups, Open Source, Python, Rust, Linux,
  Infrastructure, System Design, Machine Learning, Agents, Developer Tools,
  Research, Business, or "other" if none fit

No markdown fences, no preamble, no explanation outside the JSON."""


@dataclass
class ProjectSuggestion:
    title: str
    description: str
    category: str | None = None


class ProjectSuggestionError(Exception):
    """Raised when the LLM call fails or returns something unusable."""


def suggest_project(idea_headline: str, idea_summary: str, model: str | None = None) -> ProjectSuggestion:
    """
    idea_headline / idea_summary: pulled from a content_ideas row (its
    headline and digest_summary) — the caller (TUI) is responsible for
    fetching that row; this function only talks to the LLM.
    """
    user_prompt = (
        f"Idea headline: {idea_headline}\n"
        f"Idea summary: {idea_summary}\n\n"
        f"Suggest one project that would demonstrate this technology."
    )

    try:
        api_key = get_api_key()
    except KeyError as e:
        raise ProjectSuggestionError("OPENROUTER_API_KEY is not set") from e

    try:
        parsed = call_openrouter_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=api_key,
            model=get_model(model),
        )
    except requests.RequestException as e:
        logger.error("OpenRouter API call failed during project suggestion: %s", e)
        raise ProjectSuggestionError(f"API call failed: {e}") from e
    except ValueError as e:
        raise ProjectSuggestionError(f"LLM returned invalid JSON: {e}") from e

    if not isinstance(parsed, dict):
        raise ProjectSuggestionError(f"Expected a JSON object from LLM, got {type(parsed)}")

    title = parsed.get("title", "").strip()
    description = parsed.get("description", "").strip()
    if not title or not description:
        raise ProjectSuggestionError("LLM response missing required title/description fields")

    return ProjectSuggestion(
        title=title,
        description=description,
        category=parsed.get("category", "other"),
    )
