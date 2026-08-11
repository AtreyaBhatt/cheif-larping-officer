"""
Tests for the Textual TUI. Uses Textual's headless Pilot testing API to
simulate real keypresses against a running app instance, with db.py
mocked out so no Postgres connection is needed.

Run with:  python -m pytest app/tests/test_tui.py -v
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from brandos.tui.app import DigestApp, _relative_day


def _fake_idea(id_, headline, status="GENERATED", **overrides):
    base = {
        "id": id_,
        "created_at": datetime.now(timezone.utc),
        "headline": headline,
        "content": f"Body for {headline}",
        "category": "AI",
        "estimated_quality": 7.0,
        "reasoning": "test reasoning",
        "status": status,
        "platform": None,
        "notes": None,
    }
    base.update(overrides)
    return base


class TestRelativeDay:
    def test_today(self):
        assert _relative_day(datetime.now(timezone.utc)) == "Today"

    def test_yesterday(self):
        from datetime import timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert _relative_day(yesterday) == "Yesterday"

    def test_older_date_shows_month_day(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=10)
        result = _relative_day(old)
        assert result not in ("Today", "Yesterday")


@pytest.mark.asyncio
class TestDigestAppInteraction:
    async def test_loads_ideas_and_shows_first_in_detail_pane(self):
        fake_ideas = [_fake_idea("aaa", "First idea"), _fake_idea("bbb", "Second idea")]
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=fake_ideas):
            app = DigestApp()
            async with app.run_test() as pilot:
                assert len(app.ideas) == 2
                headline = app.query_one("#detail-headline")
                assert "First idea" in str(headline.content)

    async def test_navigation_updates_detail_pane(self):
        fake_ideas = [_fake_idea("aaa", "First idea"), _fake_idea("bbb", "Second idea")]
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=fake_ideas):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("j")
                await pilot.pause()
                headline = app.query_one("#detail-headline")
                assert "Second idea" in str(headline.content)

    async def test_marking_posted_linkedin_calls_db_with_correct_args(self):
        fake_ideas = [_fake_idea("aaa", "First idea")]
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=fake_ideas), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("1")
                await pilot.pause()
                mock_update.assert_called_once_with("aaa", "POSTED_LINKEDIN", platform="LINKEDIN")

    async def test_marking_skipped_calls_db_with_no_platform(self):
        fake_ideas = [_fake_idea("aaa", "First idea")]
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=fake_ideas), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("s")
                await pilot.pause()
                mock_update.assert_called_once_with("aaa", "SKIPPED", platform=None)

    async def test_empty_ideas_list_does_not_crash(self):
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                assert app.ideas == []
                status = app.query_one("#status-bar")
                assert "No ideas found" in str(status.content)

    async def test_db_error_on_load_is_surfaced_not_raised(self):
        with patch("brandos.tui.app.db.get_recent_ideas", side_effect=Exception("connection refused")):
            app = DigestApp()
            async with app.run_test() as pilot:
                status = app.query_one("#status-bar")
                assert "DB error" in str(status.content)

    async def test_marking_reloads_ideas_from_db(self):
        fake_ideas = [_fake_idea("aaa", "First idea")]
        with patch("brandos.tui.app.db.get_recent_ideas", return_value=fake_ideas) as mock_get, \
             patch("brandos.tui.app.db.update_status", return_value=True):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("1")
                await pilot.pause()
                # once on mount, once after marking
                assert mock_get.call_count == 2
