"""
Tests for the tabbed Textual TUI. Uses Textual's headless Pilot API to
simulate real keypresses against a running app instance, with db.py
mocked out so no Postgres connection is needed.

Run with:  python -m pytest app/tests/test_tui.py -v
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from textual.widgets import Button, TabbedContent

from brandos.tui.app import DigestApp
from brandos.tui.views import relative_day
from brandos.weekly_review import WeeklyReview, WeeklyReviewError


def _fake_idea(id_, headline, status="GENERATED", category="AI", platform=None, days_ago=0):
    return {
        "id": id_,
        "created_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "headline": headline,
        "content": f"Body for {headline}",
        "digest_summary": f"Digest summary for {headline}",
        "linkedin_post": f"LinkedIn post for {headline}",
        "x_post": f"X post for {headline}",
        "category": category,
        "estimated_quality": 7.0,
        "reasoning": "test reasoning",
        "status": status,
        "platform": platform,
        "notes": None,
    }


def _fake_project(id_, title, status="IDEA", **overrides):
    base = {
        "id": id_,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "title": title,
        "description": f"Description for {title}",
        "status": status,
        "github_url": None,
        "demo_url": None,
        "blog_url": None,
        "category": "AI",
        "source": "MANUAL",
        "linked_idea_id": None,
        "linked_idea_headline": None,
    }
    base.update(overrides)
    return base


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
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                assert app.query_one(TabbedContent).active == "digest"

    @pytest.mark.parametrize("key,expected_tab", [
        ("1", "digest"),
        ("2", "posts"),
        ("3", "projects"),
        ("4", "posted"),
    ])
    async def test_number_keys_switch_tabs(self, key, expected_tab):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press(key)
                await pilot.pause()
                assert app.query_one(TabbedContent).active == expected_tab

    async def test_projects_tab_shows_empty_state_when_no_projects(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                content = app.query_one("#project-content")
                assert "No projects yet" in str(content.content)


class TestDigestTab:
    async def test_loads_only_generated_ideas(self):
        generated = [_fake_idea("g1", "Gen idea", status="GENERATED")]

        def fake_query(statuses, platform=None, limit=100):
            return generated if statuses == ["GENERATED"] else []

        with patch("brandos.tui.app.db.get_ideas_by_status", side_effect=fake_query), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=generated), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                headline = app.query_one("#digest-headline")
                assert "Gen idea" in str(headline.content)

    async def test_marking_from_digest_tab_calls_db_correctly(self):
        generated = [_fake_idea("g1", "Gen idea", status="GENERATED")]
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=generated), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=generated), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
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
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
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


class TestPostsTab:
    async def test_shows_copy_pasteable_linkedin_and_x_content_by_default(self):
        idea = _fake_idea("p1", "Idea one")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "LinkedIn post for Idea one" in content
                assert "X post for Idea one" in content
                assert "LinkedIn" in content
                assert "X" in content

    async def test_platform_filter_linkedin_hides_x_content(self):
        idea = _fake_idea("p1", "Idea one")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                await pilot.press("p")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "LinkedIn post for Idea one" in content
                assert "X post for Idea one" not in content

    async def test_platform_filter_x_hides_linkedin_content(self):
        idea = _fake_idea("p1", "Idea one")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                await pilot.press("p")
                await pilot.pause()
                await pilot.press("p")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "X post for Idea one" in content
                assert "LinkedIn post for Idea one" not in content

    async def test_missing_linkedin_post_shows_placeholder_not_crash(self):
        idea = _fake_idea("p1", "Idea one")
        idea["linkedin_post"] = None
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "no LinkedIn post generated" in content

    async def test_multi_tweet_thread_split_and_numbered(self):
        idea = _fake_idea("p1", "Idea one")
        idea["x_post"] = "First tweet.\n---\nSecond tweet.\n---\nThird tweet."
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "First tweet." in content
                assert "Second tweet." in content
                assert "Third tweet." in content
                assert "Tweet 1/3" in content
                assert "Tweet 2/3" in content
                assert "Tweet 3/3" in content

    async def test_single_tweet_not_split_or_numbered(self):
        idea = _fake_idea("p1", "Idea one")
        idea["x_post"] = "Just one tweet, no thread."
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                content = str(app.query_one("#posts-content").content)
                assert "Just one tweet, no thread." in content
                assert "Tweet 1/" not in content

    async def test_marking_from_posts_tab_updates_status(self):
        idea = _fake_idea("p1", "Idea one")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("2")
                await pilot.pause()
                await pilot.press("b")
                await pilot.pause()
                mock_update.assert_called_once_with("p1", "POSTED_BOTH", platform="BOTH")


class TestProjectsTab:
    async def test_shows_existing_projects(self):
        projects = [_fake_project("p1", "Existing project")]
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=projects):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                headline = app.query_one("#project-headline")
                assert "Existing project" in str(headline.content)

    async def test_cycle_status_advances_idea_to_building(self):
        project = _fake_project("p1", "My project", status="IDEA")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[project]), \
             patch("brandos.tui.app.db.update_project_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                await pilot.press("c")
                await pilot.pause()
                mock_update.assert_called_once_with("p1", "BUILDING")

    async def test_cycle_status_wraps_from_done_to_idea(self):
        project = _fake_project("p1", "My project", status="DONE")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[project]), \
             patch("brandos.tui.app.db.update_project_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                await pilot.press("c")
                await pilot.pause()
                mock_update.assert_called_once_with("p1", "IDEA")

    async def test_cycle_status_outside_projects_tab_is_noop(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.update_project_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("c")
                await pilot.pause()
                mock_update.assert_not_called()

    async def test_new_project_modal_creates_manual_project(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.insert_project", return_value="new-id") as mock_insert:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("3")
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()

                title_input = app.screen.query_one("#title-input")
                title_input.value = "My New Project"
                create_btn = app.screen.query_one("#create-btn")
                app.screen.on_button_pressed(Button.Pressed(create_btn))
                await pilot.pause()

                mock_insert.assert_called_once()
                assert mock_insert.call_args.kwargs["title"] == "My New Project"
                assert mock_insert.call_args.kwargs["source"] == "MANUAL"

    async def test_new_project_key_outside_projects_tab_is_noop(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.insert_project", return_value="new-id") as mock_insert:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("n")
                await pilot.pause()
                mock_insert.assert_not_called()

    async def test_suggest_project_from_digest_creates_linked_project(self):
        from brandos.project_suggester import ProjectSuggestion
        idea = _fake_idea("i1", "Docker Sandboxes announcement")
        fake_suggestion = ProjectSuggestion(
            title="Sandbox Runner CLI",
            description="A CLI that spins up Docker sandboxes.",
            category="Developer Tools",
        )
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.suggest_project", return_value=fake_suggestion), \
             patch("brandos.tui.app.db.insert_project", return_value="new-id") as mock_insert:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("g")
                await pilot.pause()

                mock_insert.assert_called_once()
                call_kwargs = mock_insert.call_args.kwargs
                assert call_kwargs["title"] == "Sandbox Runner CLI"
                assert call_kwargs["source"] == "LLM_SUGGESTED"
                assert call_kwargs["linked_idea_id"] == "i1"

    async def test_suggest_project_failure_surfaces_error_not_crash(self):
        from brandos.project_suggester import ProjectSuggestionError
        idea = _fake_idea("i1", "Some idea")
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[idea]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[idea]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.suggest_project", side_effect=ProjectSuggestionError("API down")):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("g")
                await pilot.pause()
                status = app.query_one("#status-bar")
                assert "API down" in str(status.content)

    async def test_suggest_project_with_nothing_selected_does_not_crash(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.insert_project", return_value="new-id") as mock_insert:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("g")
                await pilot.pause()
                mock_insert.assert_not_called()


class TestPostedTabAndPlatformFilter:
    async def test_platform_cycles_all_linkedin_x(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
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

    async def test_platform_cycle_ignored_outside_posts_or_posted_tab(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("p")
                await pilot.pause()
                assert app.posted_platform is None

    async def test_posted_query_receives_platform_filter(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]) as mock_query, \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                await pilot.press("p")
                await pilot.pause()

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
             patch("brandos.tui.app.db.get_recent_ideas", return_value=posted), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                overall = str(app.query_one("#larp-overall").content)
                assert "LARP Score" in overall
                stats = str(app.query_one("#larp-stats").content)
                assert "Current streak: 2d" in stats


class TestWeeklyReview:
    async def test_shows_prompt_when_no_review_exists_yet(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.get_weekly_review", return_value=None):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                review_text = str(app.query_one("#larp-review").content)
                assert "press 'w'" in review_text

    async def test_shows_cached_summary_without_generating(self):
        cached = {"week_start": "2026-08-10", "summary": "You posted twice this week.", "stats_json": {}}
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.get_weekly_review", return_value=cached), \
             patch("brandos.tui.app.get_or_generate_weekly_review") as mock_generate:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                review_text = str(app.query_one("#larp-review").content)
                assert "You posted twice this week." in review_text
                mock_generate.assert_not_called()

    async def test_pressing_w_generates_and_displays_review(self):
        review = WeeklyReview(week_start="2026-08-10", summary="Solid week, keep it up.", stats={})
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.get_weekly_review", return_value=None), \
             patch("brandos.tui.app.get_or_generate_weekly_review", return_value=review) as mock_generate:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                await pilot.press("w")
                await pilot.pause()
                review_text = str(app.query_one("#larp-review").content)
                assert "Solid week, keep it up." in review_text
                mock_generate.assert_called_once()

    async def test_pressing_w_outside_posted_tab_is_noop(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.get_weekly_review", return_value=None), \
             patch("brandos.tui.app.get_or_generate_weekly_review") as mock_generate:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("1")
                await pilot.pause()
                await pilot.press("w")
                await pilot.pause()
                mock_generate.assert_not_called()
                status = app.query_one("#status-bar")
                assert "Posted tab" in str(status.content)

    async def test_weekly_review_error_surfaced_not_raised(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.get_weekly_review", return_value=None), \
             patch("brandos.tui.app.get_or_generate_weekly_review", side_effect=WeeklyReviewError("no key set")):
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("4")
                await pilot.pause()
                await pilot.press("w")
                await pilot.pause()
                status = app.query_one("#status-bar")
                assert "Weekly review failed" in str(status.content)
                review_text = str(app.query_one("#larp-review").content)
                assert "Failed to generate review" in review_text


class TestErrorHandling:
    async def test_db_error_on_digest_load_is_surfaced_not_raised(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", side_effect=Exception("connection refused")), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]):
            app = DigestApp()
            async with app.run_test() as pilot:
                status = app.query_one("#status-bar")
                assert "DB error" in str(status.content)

    async def test_marking_with_nothing_selected_does_not_crash(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
             patch("brandos.tui.app.db.update_status", return_value=True) as mock_update:
            app = DigestApp()
            async with app.run_test() as pilot:
                await pilot.press("l")
                await pilot.pause()
                mock_update.assert_not_called()

    async def test_marking_on_projects_tab_is_a_safe_noop(self):
        with patch("brandos.tui.app.db.get_ideas_by_status", return_value=[]), \
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]), \
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
             patch("brandos.tui.app.db.get_recent_ideas", return_value=[]), \
             patch("brandos.tui.app.db.get_projects", return_value=[]) as mock_projects:
            app = DigestApp()
            async with app.run_test() as pilot:
                initial_calls = mock_query.call_count
                initial_project_calls = mock_projects.call_count
                await pilot.press("r")
                await pilot.pause()
                assert mock_query.call_count == initial_calls + 3
                assert mock_projects.call_count == initial_project_calls + 1
