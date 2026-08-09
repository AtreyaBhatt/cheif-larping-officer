"""
Fetches top stories from Hacker News via the official Firebase API
(https://github.com/HackerNews/API). No API key required.

This is the single news source for Phase 1. Designed so adding a second
source later (arXiv, RSS, etc.) means writing another fetch_* function
with the same return shape, not touching this one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

HN_BASE = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class Article:
    """A single news item, source-agnostic shape used across the app."""
    title: str
    url: str | None          # external link, if the HN post has one
    hn_url: str               # link to the HN discussion itself
    score: int
    num_comments: int
    source: str = "hackernews"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "hn_url": self.hn_url,
            "score": self.score,
            "num_comments": self.num_comments,
            "source": self.source,
        }


def _get(path: str) -> dict | list:
    resp = requests.get(f"{HN_BASE}/{path}", timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_top_stories(limit: int = 15) -> list[Article]:
    """
    Fetch the top N stories from HN's front page ranking.

    Returns a plain list of Article objects, already sorted by HN's own
    ranking (which factors in score + recency). No further ranking is
    done here — the LLM step later decides what's actually worth a post.
    """
    story_ids = _get("topstories.json")
    if not isinstance(story_ids, list):
        raise ValueError("Unexpected response shape from HN topstories.json")

    articles: list[Article] = []
    for story_id in story_ids[:limit]:
        try:
            item = _get(f"item/{story_id}.json")
        except requests.RequestException as e:
            logger.warning("Failed to fetch HN item %s: %s", story_id, e)
            continue

        if not item or item.get("type") != "story":
            continue

        articles.append(
            Article(
                title=item.get("title", "(no title)"),
                url=item.get("url"),  # None for Ask/Show HN text posts
                hn_url=HN_ITEM_URL.format(id=story_id),
                score=item.get("score", 0),
                num_comments=item.get("descendants", 0),
            )
        )

    logger.info("Fetched %d HN stories", len(articles))
    return articles


if __name__ == "__main__":
    # Quick manual check: python -m brandos.sources.hackernews
    logging.basicConfig(level=logging.INFO)
    for a in fetch_top_stories(limit=5):
        print(f"[{a.score:>4}] {a.title} — {a.url or a.hn_url}")
