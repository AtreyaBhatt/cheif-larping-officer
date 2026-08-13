"""
Tests for on-demand project suggestions. All HTTP mocked — no real
OpenRouter key or network call needed.

Run with:  python -m pytest app/tests/test_project_suggester.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from brandos.project_suggester import ProjectSuggestionError, suggest_project


def _fake_response(content: str):
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp


class TestSuggestProject:
    def test_happy_path_returns_parsed_suggestion(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps({
            "title": "GitHub PR Diff Summarizer",
            "description": "A Slack bot that summarizes PR diffs. Weekend project.",
            "category": "Developer Tools",
        })
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            result = suggest_project("Some AI news", "Summary of the news")

        assert result.title == "GitHub PR Diff Summarizer"
        assert "Slack bot" in result.description
        assert result.category == "Developer Tools"

    def test_sends_correct_default_model(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps({"title": "T", "description": "D", "category": "AI"})
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)) as mock_post:
            suggest_project("headline", "summary")
        assert mock_post.call_args.kwargs["json"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"

    def test_missing_api_key_raises_project_suggestion_error(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ProjectSuggestionError, match="OPENROUTER_API_KEY"):
            suggest_project("headline", "summary")

    def test_malformed_json_raises_project_suggestion_error(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response("not json")):
            with pytest.raises(ProjectSuggestionError):
                suggest_project("headline", "summary")

    def test_empty_title_or_description_raises(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps({"title": "", "description": "", "category": "AI"})
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            with pytest.raises(ProjectSuggestionError, match="missing required"):
                suggest_project("headline", "summary")

    def test_non_dict_response_raises(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        # LLM returns a JSON array instead of an object
        fake_json = json.dumps([{"title": "T", "description": "D"}])
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            with pytest.raises(ProjectSuggestionError, match="Expected a JSON object"):
                suggest_project("headline", "summary")

    def test_strips_markdown_fences(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fenced = '```json\n{"title": "T", "description": "D", "category": "AI"}\n```'
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fenced)):
            result = suggest_project("headline", "summary")
        assert result.title == "T"
