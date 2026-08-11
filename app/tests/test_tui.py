"""
Tests for the tabbed Textual TUI. Uses Textual's headless Pilot API to
simulate real keypresses against a running app instance, with db.py
mocked out so no Postgres connection is needed.

Run with:  python -m pytest app/tests/test_tui.py -v
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from textual.widgets import TabbedContent

from brandos.tui.app import DigestApp
from brandos.tui.views import relative_day


def _fake_idea(id_, headline, status="GENERATED", category="AI", platform=None, days_ago=0):
    return {
        "id": id_,
        "created_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "headline": headline,
        "content": f"Body for {headline}",
        "category": category,
        "estimated_quality": 7.0,
        "reasoning": "test reasoning",
        "status": status,
        "platform": platform,
        "notes": None,
    }


class TestRelativeDay:
    def test_today(self):
        assert relative_day(datetime.now(timezone.utc)) == "Today"

    def test_yesterday(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert relative_day(yesterday) == "Yesterday"

    def test_older_date_shows_month_day(self):
        old = datetime.now(timezone.utc) - timedelta(days=10)
        assert relative_day(old) not in ("Today", "Yesterday")


class TestTabNavigation:
    async def test_digest_tab_active_by_default(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                assert app.query_one(TabbedContent).active == "digest"

    @pytest.mark.parametrize("key,expected_tab", [
        ("1", "digest"),
        ("2", "post_ideas"),
        ("3", "projects"),
        ("4", "posted"),
    ])
    async def test_number_keys_switch_tabs(self, key, expected_tab):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press(key)
                await pilot.pause()
                assert app.query_one(TabbedContent).active == expected_tab

    async def test_projects_tab_shows_stub_message(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                stub = app.query_one("#projects-stub")
                assert "wired up yet" in str(stub.content)


class TestDigestTab:
    async def test_loads_only_generated_ideas(self):
        generated = [_fake_idea("g1", "Gen idea", status="GENERATED")]

        def fake_query(statuses, platform=None, limit=100):
            if statuses == ["GENERATED"]:
                return generated
            return []

        with patch("brandos.tui.app.db.get_ideas_by_status", side_effect=fake_query), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=generated):
            app = DigestApp()
            async with app.run_test() as pilot:
                headline = app.query_one("#digest-headline")
                assert "Gen idea" in str(headline.content)

    async def test_marking_from_digest_tab_calls_db_correctly(self):
        generated = [_fake_idea("g1", "Gen idea", status="GENERATED")]
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=generated), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=generated), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("l")
                await pilot.pause()
                mock_update.assert_called_once_with("g1", "POSTED_LINKEDIN", platform="LINKEDIN")

    async def test_navigation_within_tab_updates_detail_and_targets_correct_idea(self):
        ideas = [_fake_idea("g1", "First"), _fake_idea("g2", "Second")]
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=ideas), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=ideas), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("j")
                await pilot.pause()
                headline = app.query_one("#digest-headline")
                assert "Second" in str(headline.content)

                await pilot.press("s")
                await pilot.pause()
                mock_update.assert_called_once_with("g2", "SKIPPED", platform=None)


class TestPostedTabAndPlatformFilter:
    async def test_platform_cycles_all_linkedin_x(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                assert app.posted_platform is None

                await pilot.press("p")
                await pilot.pause()
                assert app.posted_platform == "LINKEDIN"

                await pilot.press("p")
                await pilot.pause()
                assert app.posted_platform == "X"

                await pilot.press("p")
                await pilot.pause()
                assert app.posted_platform is None

    async def test_platform_cycle_ignored_outside_posted_tab(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                # still on Digest tab (default)
                await pilot.press("p")
                await pilot.pause()
                assert app.posted_platform is None

    async def test_posted_query_receives_platform_filter(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]) as mock_query, \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                await pilot.press("p")  # -> LINKEDIN
                await pilot.pause()

                # find the call made for the posted tab specifically
                posted_calls = [
                    c for c in mock_query.call_args_list
                    if "POSTED_LINKEDIN" in c.args[0]
                ]
                assert any(c.kwargs.get("platform") == "LINKEDIN" for c in posted_calls)

    async def test_larp_panel_renders_with_data(self):
        posted = [
            _fake_idea("p1", "Post today", status="POSTED_LINKEDIN", category="AI", days_ago=0),
            _fake_idea("p2", "Post yesterday", status="POSTED_X", category="Rust", days_ago=1),
        ]
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=posted), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=posted):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                overall = str(app.query_one("#larp-overall").content)
                assert "LARP Score" in overall
                stats = str(app.query_one("#larp-stats").content)
                assert "Current streak: 2d" in stats


class TestErrorHandling:
    async def test_db_error_on_digest_load_is_surfaced_not_raised(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", side_effect=Exception("connection refused")), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                status = app.query_one("#status-bar")
                assert "DB error" in str(status.content)

    async def test_marking_with_nothing_selected_does_not_crash(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("l")
                await pilot.pause()
                mock_update.assert_not_called()

    async def test_marking_on_projects_tab_is_a_safe_noop(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                await pilot.press("l")
                await pilot.pause()
                mock_update.assert_not_called()


class TestRefresh:
    async def test_refresh_reloads_all_tabs(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]) as mock_query, \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                initial_calls = mock_query.call_count
                await pilot.press("r")
                await pilot.pause()
                # 3 tabs queried again (digest, post_ideas, posted)
                assert mock_query.call_count == initial_calls + 3
