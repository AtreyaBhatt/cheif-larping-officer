"""
LLM abstraction for generating the digest + content ideas from raw articles.

Phase 1 ships with a stub provider so the rest of the pipeline (DB writes,
delivery, logging) can be built and tested without an API key or cost.
Swapping in a real provider later means implementing DigestGenerator and
pointing get_generator() at it — nothing else in the app changes.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

from brandos.sources.hackernews import Article

logger = logging.getLogger(__name__)


@dataclass
class ContentIdea:
    """
    Mirrors the content_ideas DB row shape (minus id/created_at/status/
    platform/notes, which are set at insert time, not generation time).

    content: kept for backward compatibility with old rows/tests; new
             code should read digest_summary / linkedin_post / x_post.
    digest_summary: the informational summary shown in the Digest tab —
                     what happened and why it matters, NOT meant to be
                     posted as-is.
    linkedin_post: full, platform-native, copy-pasteable LinkedIn post.
    x_post: full, platform-native, copy-pasteable X post. May contain
            multiple tweets joined by "\\n---\\n" if the idea warranted
            a short thread (2-3 tweets); the TUI splits on that
            separator for display.
    """
    headline: str
    content: str
    digest_summary: str | None = None
    linkedin_post: str | None = None
    x_post: str | None = None
    source_articles: list[dict] = field(default_factory=list)
    category: str | None = None
    estimated_quality: float | None = None
    reasoning: str | None = None


class DigestGenerator(ABC):
    """Interface every LLM provider must implement."""

    @abstractmethod
    def generate(self, articles: list[Article]) -> list[ContentIdea]:
        """Given raw articles, return a list of ranked content ideas."""
        raise NotImplementedError


class StubDigestGenerator(DigestGenerator):
    """
    No LLM call at all. Deterministically turns the top N articles (by
    score) into placeholder ContentIdea objects so the pipeline can be
    exercised end-to-end before an API key exists.
    """

    def __init__(self, max_ideas: int = 5):
        self.max_ideas = max_ideas

    def generate(self, articles: list[Article]) -> list[ContentIdea]:
        ranked = sorted(articles, key=lambda a: a.score, reverse=True)
        ideas: list[ContentIdea] = []

        for article in ranked[: self.max_ideas]:
            summary = (
                f"[STUB] No LLM configured yet. Raw article: "
                f"\"{article.title}\" (score {article.score}, "
                f"{article.num_comments} comments)."
            )
            ideas.append(
                ContentIdea(
                    headline=article.title,
                    content=summary,
                    digest_summary=summary,
                    linkedin_post="[STUB] No LLM configured — no LinkedIn post generated.",
                    x_post="[STUB] No LLM configured — no X post generated.",
                    source_articles=[article.to_dict()],
                    category="uncategorized",
                    estimated_quality=None,
                    reasoning="Stub generator: ranked by raw HN score only, no analysis performed.",
                )
            )

        logger.info("StubDigestGenerator produced %d ideas from %d articles", len(ideas), len(articles))
        return ideas


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

SYSTEM_PROMPT = """You are a ghostwriter producing publish-ready social \
media posts for a software professional's technical brand, based on AI/tech \
news articles.

For each article given, produce ONE content package with these fields:

- headline: a short, punchy internal label for this idea (not the article \
title, not meant to be posted anywhere — just for organizing)

- digest_summary: 2-4 sentences summarizing what happened and why it \
matters technically. This is informational only, NOT meant to be posted \
as-is — it's for the person's own morning reading.

- linkedin_post: a COMPLETE, publish-ready LinkedIn post, written in first \
person as the author's own take (not "here's an article about X" but an \
actual opinion/insight). Structure: a strong hook line, 2-4 short \
paragraphs of substance, optionally a closing question to invite \
discussion. Roughly 100-200 words. This must be copy-pasteable exactly as \
written — no placeholders, no brackets, no "[your take here]".

- x_post: a COMPLETE, publish-ready X/Twitter post or short thread, \
written in the same first-person voice. If the idea fits in one post, \
write ONE string under 280 characters. If it genuinely needs more room \
(2-3 tweets), write each tweet separated by the literal string "\\n---\\n" \
between tweets, with EACH individual tweet under 280 characters on its \
own. Do not number the tweets yourself (no "1/3") — that's added \
automatically. Prefer a single tweet unless the idea truly needs a thread.

- category: one of AI, LLMs, Startups, Open Source, Python, Rust, Linux, \
Infrastructure, System Design, Machine Learning, Agents, Developer Tools, \
Research, Business, or "other" if none fit

- estimated_quality: a float 0.0-10.0 rating how strong this is as a post \
idea (originality, technical depth, discussion potential)

- reasoning: one sentence on why you rated it that way

Respond with ONLY a JSON array of objects with exactly these fields:
headline, digest_summary, linkedin_post, x_post, category, estimated_quality, reasoning.
No markdown fences, no preamble, no explanation outside the JSON."""

X_CHAR_LIMIT = 280


class OpenRouterDigestGenerator(DigestGenerator):
    """
    Calls an LLM via OpenRouter's OpenAI-compatible API to turn
    pre-filtered articles into real content ideas (not placeholders).

    Ranking/filtering to the top N articles happens BEFORE this class is
    invoked (by score, same as StubDigestGenerator) — this class's job is
    only to write good content for articles that already survived that
    cut, not to do the ranking itself. Keeps token usage predictable and
    avoids paying an LLM to re-derive what HN's own score already tells us.

    Requires OPENROUTER_API_KEY in the environment. Model is configurable
    via OPENROUTER_MODEL (defaults to a free Nemotron Ultra tier).
    """

    def __init__(self, max_ideas: int = 5, model: str | None = None):
        self.max_ideas = max_ideas
        self.api_key = os.environ["OPENROUTER_API_KEY"]
        self.model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)

    def _prefilter(self, articles: list[Article]) -> list[Article]:
        return sorted(articles, key=lambda a: a.score, reverse=True)[: self.max_ideas]

    def _build_user_prompt(self, articles: list[Article]) -> str:
        lines = ["Articles:\n"]
        for i, a in enumerate(articles, start=1):
            lines.append(
                f"{i}. Title: {a.title}\n"
                f"   URL: {a.url or a.hn_url}\n"
                f"   HN score: {a.score}, comments: {a.num_comments}\n"
            )
        lines.append(
            f"\nReturn a JSON array with exactly {len(articles)} objects, "
            "one per article, in the same order as listed above."
        )
        return "\n".join(lines)

    def _call_openrouter(self, user_prompt: str) -> str:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            # OpenRouter returns HTTP 200 with an {"error": {...}} body
            # for some failure modes (rate limits, model
            # overloaded/unavailable) rather than a non-2xx status, so
            # raise_for_status() above doesn't catch it. Surface the
            # real reason instead of letting a raw KeyError fire below.
            message = data["error"].get("message", str(data["error"])) if isinstance(data["error"], dict) else str(data["error"])
            logger.error("OpenRouter returned an error payload: %s", message)
            raise ValueError(f"OpenRouter API error: {message}")

        if "choices" not in data or not data["choices"]:
            logger.error("OpenRouter response missing 'choices': %r", data)
            raise ValueError(f"OpenRouter response had no choices: {data!r}")

        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            # handles ```json ... ``` or plain ``` ... ```
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
        return text.strip()

    def generate(self, articles: list[Article]) -> list[ContentIdea]:
        filtered = self._prefilter(articles)
        if not filtered:
            return []

        user_prompt = self._build_user_prompt(filtered)

        try:
            raw_response = self._call_openrouter(user_prompt)
        except requests.RequestException as e:
            logger.error("OpenRouter API call failed: %s", e)
            raise

        cleaned = self._strip_markdown_fences(raw_response)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON: %s\nRaw response: %r", e, raw_response)
            raise ValueError("LLM did not return valid JSON") from e

        if not isinstance(parsed, list):
            raise ValueError(f"Expected a JSON array from LLM, got {type(parsed)}")

        ideas: list[ContentIdea] = []
        for i, item in enumerate(parsed):
            if i >= len(filtered):
                logger.warning("LLM returned more items than articles sent, ignoring extras")
                break

            source_article = filtered[i].to_dict()

            digest_summary = item.get("digest_summary", "").strip()
            linkedin_post = item.get("linkedin_post", "").strip()
            x_post = self._validate_x_post(item.get("x_post", ""), headline=item.get("headline", filtered[i].title))

            ideas.append(
                ContentIdea(
                    headline=item.get("headline", filtered[i].title),
                    content=digest_summary,  # backward-compat mirror
                    digest_summary=digest_summary,
                    linkedin_post=linkedin_post,
                    x_post=x_post,
                    source_articles=[source_article],
                    category=item.get("category", "other"),
                    estimated_quality=_safe_float(item.get("estimated_quality")),
                    reasoning=item.get("reasoning"),
                )
            )

        logger.info("OpenRouterDigestGenerator produced %d ideas from %d articles (model=%s)", len(ideas), len(filtered), self.model)
        return ideas

    @staticmethod
    def _validate_x_post(x_post: str, headline: str) -> str:
        """
        LLMs are unreliable at exact character counting, so validate
        each tweet in the (possibly multi-tweet) response and log a
        warning if any segment exceeds X's limit — better to flag it
        for manual trimming in the TUI than silently post something
        that gets rejected or truncated on the actual platform.
        """
        x_post = x_post.strip()
        if not x_post:
            return x_post

        segments = [s.strip() for s in x_post.split("\n---\n")]
        for i, segment in enumerate(segments, start=1):
            if len(segment) > X_CHAR_LIMIT:
                logger.warning(
                    "X post segment %d/%d for %r is %d chars, over the %d limit — "
                    "will need manual trimming before posting",
                    i, len(segments), headline, len(segment), X_CHAR_LIMIT,
                )
        return x_post


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def get_generator() -> DigestGenerator:
    """
    Single place the rest of the app asks for "the current generator".
    Reads LLM_PROVIDER env var: "stub" (default) or "openrouter".
    """
    provider = os.environ.get("LLM_PROVIDER", "stub").lower()
    if provider == "openrouter":
        return OpenRouterDigestGenerator()
    return StubDigestGenerator()


if __name__ == "__main__":
    # Quick manual check: python -m brandos.digest
    from brandos.sources.hackernews import Article

    logging.basicConfig(level=logging.INFO)
    fake_articles = [
        Article(title="Test article one", url="https://example.com/1", hn_url="https://news.ycombinator.com/item?id=1", score=200, num_comments=50),
        Article(title="Test article two", url=None, hn_url="https://news.ycombinator.com/item?id=2", score=90, num_comments=10),
    ]
    gen = get_generator()
    for idea in gen.generate(fake_articles):
        print(json.dumps(idea.__dict__, indent=2))
