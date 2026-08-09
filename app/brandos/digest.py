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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from brandos.sources.hackernews import Article

logger = logging.getLogger(__name__)


@dataclass
class ContentIdea:
    """
    Mirrors the content_ideas DB row shape (minus id/created_at/status/
    platform/notes, which are set at insert time, not generation time).
    """
    headline: str
    content: str
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

    Replace with ClaudeDigestGenerator / OpenAIDigestGenerator when ready.
    """

    def __init__(self, max_ideas: int = 5):
        self.max_ideas = max_ideas

    def generate(self, articles: list[Article]) -> list[ContentIdea]:
        ranked = sorted(articles, key=lambda a: a.score, reverse=True)
        ideas: list[ContentIdea] = []

        for article in ranked[: self.max_ideas]:
            ideas.append(
                ContentIdea(
                    headline=article.title,
                    content=(
                        f"[STUB] No LLM configured yet. Raw article: "
                        f"\"{article.title}\" (score {article.score}, "
                        f"{article.num_comments} comments)."
                    ),
                    source_articles=[article.to_dict()],
                    category="uncategorized",
                    estimated_quality=None,
                    reasoning="Stub generator: ranked by raw HN score only, no analysis performed.",
                )
            )

        logger.info("StubDigestGenerator produced %d ideas from %d articles", len(ideas), len(articles))
        return ideas


def get_generator() -> DigestGenerator:
    """
    Single place the rest of the app asks for "the current generator".
    Phase 1: always returns the stub. Later: read an env var
    (LLM_PROVIDER=claude|openai) and return the matching implementation.
    """
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
