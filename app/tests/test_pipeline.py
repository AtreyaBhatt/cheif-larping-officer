"""
Tests for the Phase 1 pipeline. Run with:  python -m pytest app/tests -v

These mock all external I/O (HN API, DB, delivery) so they run offline
and don't require Docker/Postgres — useful for quick iteration before
testing against the real stack on your VPS.
"""
from unittest.mock import patch

import pytest

from brandos.digest import ContentIdea, StubDigestGenerator
from brandos.delivery import ConsoleDelivery, format_digest
from brandos.sources.hackernews import Article, fetch_top_stories


class TestHackerNewsFetcher:
    def test_filters_non_story_types(self):
        fake_ids = [1, 2]
        fake_items = {
            1: {"type": "story", "title": "A real story", "score": 100, "descendants": 10},
            2: {"type": "job", "title": "We are hiring"},
        }

        def fake_get(path):
            if path == "topstories.json":
                return fake_ids
            item_id = int(path.split("/")[1].split(".")[0])
            return fake_items[item_id]

        with patch("brandos.sources.hackernews._get", side_effect=fake_get):
            articles = fetch_top_stories(limit=5)

        assert len(articles) == 1
        assert articles[0].title == "A real story"

    def test_handles_text_posts_without_url(self):
        fake_ids = [1]
        fake_items = {1: {"type": "story", "title": "Ask HN: question", "score": 50, "descendants": 5}}

        def fake_get(path):
            if path == "topstories.json":
                return fake_ids
            return fake_items[1]

        with patch("brandos.sources.hackernews._get", side_effect=fake_get):
            articles = fetch_top_stories(limit=5)

        assert articles[0].url is None
        assert "item?id=1" in articles[0].hn_url

    def test_skips_items_that_fail_to_fetch(self):
        import requests

        fake_ids = [1, 2]

        def fake_get(path):
            if path == "topstories.json":
                return fake_ids
            if "1.json" in path:
                raise requests.RequestException("simulated network error")
            return {"type": "story", "title": "Survivor", "score": 1, "descendants": 0}

        with patch("brandos.sources.hackernews._get", side_effect=fake_get):
            articles = fetch_top_stories(limit=5)

        assert len(articles) == 1
        assert articles[0].title == "Survivor"


class TestStubDigestGenerator:
    def test_ranks_by_score_descending(self):
        articles = [
            Article(title="Low", url=None, hn_url="x", score=10, num_comments=0),
            Article(title="High", url=None, hn_url="x", score=500, num_comments=0),
            Article(title="Mid", url=None, hn_url="x", score=100, num_comments=0),
        ]
        ideas = StubDigestGenerator(max_ideas=10).generate(articles)
        assert [i.headline for i in ideas] == ["High", "Mid", "Low"]

    def test_respects_max_ideas_cap(self):
        articles = [
            Article(title=f"Story {i}", url=None, hn_url="x", score=i, num_comments=0)
            for i in range(10)
        ]
        ideas = StubDigestGenerator(max_ideas=3).generate(articles)
        assert len(ideas) == 3

    def test_empty_input_produces_empty_output(self):
        assert StubDigestGenerator().generate([]) == []


class TestFormatDigest:
    def test_empty_ideas_produces_placeholder_message(self):
        text = format_digest([])
        assert "No ideas generated today" in text

    def test_includes_headline_and_source(self):
        idea = ContentIdea(
            headline="Test headline",
            content="Test body",
            source_articles=[{"url": "https://example.com/x"}],
            category="ai",
        )
        text = format_digest([idea])
        assert "Test headline" in text
        assert "https://example.com/x" in text
        assert "ai" in text


class TestConsoleDelivery:
    def test_deliver_does_not_raise(self, capsys):
        ConsoleDelivery().deliver("some digest text")
        captured = capsys.readouterr()
        assert "some digest text" in captured.out
