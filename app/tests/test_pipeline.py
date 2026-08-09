"""
Tests for the Phase 1 pipeline. Run with:  python -m pytest app/tests -v

These mock all external I/O (HN API, DB, delivery) so they run offline
and don't require Docker/Postgres — useful for quick iteration before
testing against the real stack on your VPS.
"""
from unittest.mock import patch
import json

import pytest

from brandos.digest import ContentIdea, StubDigestGenerator, OpenRouterDigestGenerator, get_generator
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


class TestOpenRouterDigestGenerator:
    """All tests mock requests.post — no real API key or network call needed."""

    @pytest.fixture(autouse=True)
    def _set_fake_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-for-testing")

    def _fake_response(self, content: str):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": content}}]}
        resp.raise_for_status.return_value = None
        return resp

    def test_happy_path_parses_ideas_correctly(self):
        articles = [
            Article(title="Rust 2.0 released", url="https://example.com/rust", hn_url="x", score=300, num_comments=100),
        ]
        fake_json = (
            '[{"headline": "Rust 2.0 changes everything", "content": "Big release.", '
            '"category": "Rust", "estimated_quality": 8.5, "reasoning": "High interest", '
            '"linkedin_angle": "Migration strategy", "x_angle": "Hot take"}]'
        )
        with patch("brandos.digest.requests.post", return_value=self._fake_response(fake_json)):
            ideas = OpenRouterDigestGenerator(max_ideas=5).generate(articles)

        assert len(ideas) == 1
        assert ideas[0].headline == "Rust 2.0 changes everything"
        assert ideas[0].category == "Rust"
        assert ideas[0].estimated_quality == 8.5
        assert "LinkedIn angle" in ideas[0].content
        assert "X angle" in ideas[0].content

    def test_strips_markdown_fences(self):
        articles = [Article(title="Test", url="https://x.com", hn_url="x", score=100, num_comments=5)]
        fenced = (
            '```json\n[{"headline": "H", "content": "c", "category": "AI", '
            '"estimated_quality": 7.0, "reasoning": "r", "linkedin_angle": "a", "x_angle": "b"}]\n```'
        )
        with patch("brandos.digest.requests.post", return_value=self._fake_response(fenced)):
            ideas = OpenRouterDigestGenerator(max_ideas=5).generate(articles)
        assert len(ideas) == 1
        assert ideas[0].headline == "H"

    def test_malformed_json_raises_value_error(self):
        articles = [Article(title="Test", url="https://x.com", hn_url="x", score=100, num_comments=5)]
        with patch("brandos.digest.requests.post", return_value=self._fake_response("not json")):
            with pytest.raises(ValueError):
                OpenRouterDigestGenerator(max_ideas=5).generate(articles)

    def test_prefilters_to_max_ideas_before_calling_llm(self):
        articles = [
            Article(title=f"Story {i}", url="https://x.com", hn_url="x", score=i, num_comments=0)
            for i in range(10)
        ]
        fake_json = json.dumps([
            {"headline": f"H{i}", "content": "c", "category": "AI", "estimated_quality": 5.0,
             "reasoning": "r", "linkedin_angle": "a", "x_angle": "b"}
            for i in range(3)
        ])
        with patch("brandos.digest.requests.post", return_value=self._fake_response(fake_json)) as mock_post:
            OpenRouterDigestGenerator(max_ideas=3).generate(articles)

        # confirm only 3 articles were sent to the LLM, not all 10
        sent_prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        assert "Story 9" in sent_prompt  # highest score, should survive prefilter
        assert "Story 0" not in sent_prompt  # lowest score, should be filtered out

    def test_empty_articles_returns_empty_without_calling_api(self):
        with patch("brandos.digest.requests.post") as mock_post:
            ideas = OpenRouterDigestGenerator(max_ideas=5).generate([])
        assert ideas == []
        mock_post.assert_not_called()

    def test_default_model_is_free_nemotron(self):
        gen = OpenRouterDigestGenerator()
        assert gen.model == "nvidia/nemotron-3-ultra-550b-a55b:free"


class TestGetGenerator:
    def test_defaults_to_stub(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        assert isinstance(get_generator(), StubDigestGenerator)

    def test_openrouter_provider_selected_via_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
        assert isinstance(get_generator(), OpenRouterDigestGenerator)


class TestTwilioWhatsAppDelivery:
    def test_deliver_calls_twilio_client_correctly(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACfake")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake_token")
        monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        monkeypatch.setenv("TWILIO_WHATSAPP_TO", "whatsapp:+919999999999")

        from unittest.mock import MagicMock

        with patch("twilio.rest.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_message = MagicMock()
            mock_message.sid = "SM1234567890"
            mock_instance.messages.create.return_value = mock_message

            from brandos.delivery import TwilioWhatsAppDelivery
            TwilioWhatsAppDelivery().deliver("Test digest content")

            call_kwargs = mock_instance.messages.create.call_args.kwargs
            assert call_kwargs["from_"] == "whatsapp:+14155238886"
            assert call_kwargs["to"] == "whatsapp:+919999999999"
            assert call_kwargs["body"] == "Test digest content"


class TestConsoleDelivery:
    def test_deliver_does_not_raise(self, capsys):
        ConsoleDelivery().deliver("some digest text")
        captured = capsys.readouterr()
        assert "some digest text" in captured.out
