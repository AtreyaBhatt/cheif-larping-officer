"""
Tests for the weekly review / writing coach module. LLM calls mocked
via the same requests.post patch pattern as test_project_suggester.py;
DB calls mocked via brandos.weekly_review.db so no Postgres is needed.

Run with:  python -m pytest app/tests/test_weekly_review.py -v
"""
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from brandos.weekly_review import (
    WeeklyReview,
    WeeklyReviewError,
    generate_weekly_review,
    get_or_generate_weekly_review,
    week_start_for,
)


def _fake_response(content: str):
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp


def _fake_idea(status="GENERATED", category="AI", days_ago=0):
    return {
        "id": f"idea-{days_ago}-{status}",
        "created_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "headline": "Some headline",
        "category": category,
        "status": status,
    }


class TestWeekStartFor:
    def test_monday_returns_itself(self):
        monday = date(2026, 8, 10)  # a Monday
        assert week_start_for(monday) == monday

    def test_sunday_returns_preceding_monday(self):
        sunday = date(2026, 8, 16)
        assert week_start_for(sunday) == date(2026, 8, 10)

    def test_wednesday_returns_that_weeks_monday(self):
        wednesday = date(2026, 8, 12)
        assert week_start_for(wednesday) == date(2026, 8, 10)


class TestGenerateWeeklyReview:
    def _stats(self):
        return {
            "total_generated_this_week": 5,
            "status_counts": {"GENERATED": 2, "POSTED_LINKEDIN": 3},
            "category_counts": {"AI": 3, "Rust": 2},
            "overall_score": 62,
            "consistency": 50,
            "execution": 60,
            "diversity": 80,
            "current_streak_days": 3,
            "top_category": "AI",
        }

    def test_happy_path_returns_summary(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps({"summary": "You posted 3 times this week, solid streak."})
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            summary = generate_weekly_review(self._stats())
        assert "3 times" in summary

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(WeeklyReviewError, match="OPENROUTER_API_KEY"):
            generate_weekly_review(self._stats())

    def test_malformed_json_raises(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response("not json")):
            with pytest.raises(WeeklyReviewError):
                generate_weekly_review(self._stats())

    def test_empty_summary_raises(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps({"summary": ""})
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            with pytest.raises(WeeklyReviewError, match="missing required"):
                generate_weekly_review(self._stats())

    def test_non_dict_response_raises(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        fake_json = json.dumps(["not", "a", "dict"])
        with patch("brandos.openrouter_client.requests.post", return_value=_fake_response(fake_json)):
            with pytest.raises(WeeklyReviewError, match="Expected a JSON object"):
                generate_weekly_review(self._stats())


class TestGetOrGenerateWeeklyReview:
    def test_returns_cached_review_without_calling_llm(self, monkeypatch):
        today = date(2026, 8, 15)
        week_start = week_start_for(today)
        cached_row = {
            "week_start": week_start,
            "summary": "Cached summary text",
            "stats_json": {"overall_score": 70},
        }
        with patch("brandos.weekly_review.db.get_weekly_review", return_value=cached_row) as mock_get, \
             patch("brandos.weekly_review.generate_weekly_review") as mock_generate, \
             patch("brandos.weekly_review.db.insert_weekly_review") as mock_insert:
            result = get_or_generate_weekly_review(today=today)

        mock_get.assert_called_once_with(week_start)
        mock_generate.assert_not_called()
        mock_insert.assert_not_called()
        assert isinstance(result, WeeklyReview)
        assert result.summary == "Cached summary text"

    def test_generates_and_stores_when_no_cached_review(self, monkeypatch):
        today = date(2026, 8, 15)
        week_start = week_start_for(today)
        this_week_ideas = [
            _fake_idea(status="POSTED_LINKEDIN", category="AI", days_ago=1),
            _fake_idea(status="GENERATED", category="Rust", days_ago=2),
        ]
        with patch("brandos.weekly_review.db.get_weekly_review", return_value=None), \
             patch("brandos.weekly_review.db.get_recent_ideas", return_value=this_week_ideas), \
             patch("brandos.weekly_review.generate_weekly_review", return_value="Fresh summary") as mock_generate, \
             patch("brandos.weekly_review.db.insert_weekly_review") as mock_insert:
            result = get_or_generate_weekly_review(today=today)

        mock_generate.assert_called_once()
        stats_arg = mock_generate.call_args.args[0]
        assert stats_arg["total_generated_this_week"] == 2
        assert stats_arg["status_counts"] == {"POSTED_LINKEDIN": 1, "GENERATED": 1}

        mock_insert.assert_called_once()
        insert_args = mock_insert.call_args.args
        assert insert_args[0] == week_start
        assert insert_args[1] == "Fresh summary"

        assert result.summary == "Fresh summary"
        assert result.week_start == week_start

    def test_excludes_ideas_outside_the_week(self, monkeypatch):
        today = date(2026, 8, 15)
        old_idea = _fake_idea(status="POSTED_X", category="AI", days_ago=30)
        this_week = _fake_idea(status="POSTED_X", category="AI", days_ago=1)
        with patch("brandos.weekly_review.db.get_weekly_review", return_value=None), \
             patch("brandos.weekly_review.db.get_recent_ideas", return_value=[old_idea, this_week]), \
             patch("brandos.weekly_review.generate_weekly_review", return_value="Summary") as mock_generate, \
             patch("brandos.weekly_review.db.insert_weekly_review"):
            get_or_generate_weekly_review(today=today)

        stats_arg = mock_generate.call_args.args[0]
        assert stats_arg["total_generated_this_week"] == 1

    def test_llm_error_propagates_and_does_not_insert(self, monkeypatch):
        today = date(2026, 8, 15)
        with patch("brandos.weekly_review.db.get_weekly_review", return_value=None), \
             patch("brandos.weekly_review.db.get_recent_ideas", return_value=[]), \
             patch("brandos.weekly_review.generate_weekly_review", side_effect=WeeklyReviewError("boom")), \
             patch("brandos.weekly_review.db.insert_weekly_review") as mock_insert:
            with pytest.raises(WeeklyReviewError, match="boom"):
                get_or_generate_weekly_review(today=today)
        mock_insert.assert_not_called()
