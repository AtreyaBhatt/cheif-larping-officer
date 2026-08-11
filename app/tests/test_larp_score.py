"""
Tests for LARP score calculation. Pure logic, no Textual/DB involved —
fast and runs anywhere.

Run with:  python -m pytest app/tests/test_larp_score.py -v
"""
from datetime import date, datetime, timedelta, timezone

from brandos.tui.larp_score import calculate_larp_score


def _dt(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _posted(id_, days_ago, category="AI", status="POSTED_LINKEDIN"):
    return {
        "id": id_, "created_at": _dt(days_ago), "status": status, "category": category,
    }


def _generated(id_, days_ago, category="AI"):
    return {
        "id": id_, "created_at": _dt(days_ago), "status": "GENERATED", "category": category,
    }


class TestEmptyAndTrivialCases:
    def test_empty_history_scores_zero(self):
        score = calculate_larp_score([])
        assert score.overall == 0
        assert score.current_streak_days == 0
        assert score.longest_streak_days == 0
        assert score.total_generated == 0
        assert score.total_posted == 0
        assert score.top_category is None

    def test_only_generated_no_posts(self):
        ideas = [_generated("g1", 0), _generated("g2", 1)]
        score = calculate_larp_score(ideas)
        assert score.total_posted == 0
        assert score.execution == 0
        assert score.current_streak_days == 0


class TestStreaks:
    def test_five_day_consecutive_streak(self):
        ideas = [_posted(f"p{i}", i) for i in range(5)]
        score = calculate_larp_score(ideas)
        assert score.current_streak_days == 5
        assert score.longest_streak_days == 5

    def test_gap_breaks_current_streak(self):
        ideas = [
            _posted("p1", 0),
            _posted("p2", 1),
            # gap at day 2 (nothing posted)
            _posted("p3", 3),
        ]
        score = calculate_larp_score(ideas)
        assert score.current_streak_days == 2
        assert score.longest_streak_days == 2

    def test_longest_streak_can_exceed_current_streak(self):
        # A long streak in the past, then a gap, then a short current streak
        ideas = [
            _posted("recent", 0),
            # gap
            _posted("old5", 5), _posted("old6", 6), _posted("old7", 7),
            _posted("old8", 8), _posted("old9", 9),
        ]
        score = calculate_larp_score(ideas)
        assert score.current_streak_days == 1
        assert score.longest_streak_days == 5

    def test_no_post_today_but_posted_yesterday_still_counts_streak(self):
        # Streak shouldn't reset to 0 just because today hasn't happened yet
        ideas = [_posted("p1", 1), _posted("p2", 2)]
        score = calculate_larp_score(ideas)
        assert score.current_streak_days == 2

    def test_multiple_posts_same_day_count_as_one_streak_day(self):
        ideas = [
            {"id": "a", "created_at": _dt(0), "status": "POSTED_LINKEDIN", "category": "AI"},
            {"id": "b", "created_at": _dt(0), "status": "POSTED_X", "category": "Rust"},
        ]
        score = calculate_larp_score(ideas)
        assert score.current_streak_days == 1


class TestExecutionRate:
    def test_half_posted_half_generated(self):
        ideas = [_posted("p1", 0), _generated("g1", 0)]
        score = calculate_larp_score(ideas)
        assert score.execution == 50

    def test_all_posted_is_100_percent(self):
        ideas = [_posted("p1", 0), _posted("p2", 1)]
        score = calculate_larp_score(ideas)
        assert score.execution == 100

    def test_skipped_and_archived_count_toward_denominator_not_numerator(self):
        ideas = [_posted("p1", 0), {"id": "s1", "created_at": _dt(0), "status": "SKIPPED", "category": "AI"}]
        score = calculate_larp_score(ideas)
        assert score.total_generated == 2
        assert score.execution == 50


class TestDiversity:
    def test_single_category_scores_zero_diversity(self):
        ideas = [_posted(f"p{i}", i, category="AI") for i in range(4)]
        score = calculate_larp_score(ideas)
        assert score.diversity == 0
        assert score.top_category == "AI"

    def test_perfectly_even_spread_scores_100(self):
        ideas = [
            _posted("p1", 0, category="AI"),
            _posted("p2", 1, category="Rust"),
            _posted("p3", 2, category="Business"),
            _posted("p4", 3, category="LLMs"),
        ]
        score = calculate_larp_score(ideas)
        assert score.diversity == 100

    def test_skewed_spread_scores_between_zero_and_100(self):
        ideas = [
            _posted("p1", 0, category="AI"),
            _posted("p2", 1, category="AI"),
            _posted("p3", 2, category="AI"),
            _posted("p4", 3, category="Rust"),
        ]
        score = calculate_larp_score(ideas)
        assert 0 < score.diversity < 100

    def test_top_category_is_the_most_frequent(self):
        ideas = [
            _posted("p1", 0, category="AI"),
            _posted("p2", 1, category="AI"),
            _posted("p3", 2, category="Rust"),
        ]
        score = calculate_larp_score(ideas)
        assert score.top_category == "AI"

    def test_missing_category_treated_as_uncategorized(self):
        ideas = [{"id": "p1", "created_at": _dt(0), "status": "POSTED_LINKEDIN", "category": None}]
        score = calculate_larp_score(ideas)
        assert score.top_category == "uncategorized"


class TestRecentWindows:
    def test_posts_last_7_and_30_days_counted_correctly(self):
        ideas = [
            _posted("p1", 0),   # within both windows
            _posted("p2", 5),   # within both
            _posted("p3", 15),  # within 30 only
            _posted("p4", 40),  # outside both
        ]
        score = calculate_larp_score(ideas)
        assert score.posts_last_7_days == 2
        assert score.posts_last_30_days == 3


class TestOverallScore:
    def test_overall_is_weighted_combination_within_bounds(self):
        ideas = [_posted(f"p{i}", i, category=f"cat{i}") for i in range(10)]
        score = calculate_larp_score(ideas)
        assert 0 <= score.overall <= 100

    def test_injected_today_produces_deterministic_result(self):
        fixed_today = date(2026, 6, 15)
        ideas = [
            {
                "id": "p1",
                "created_at": datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                "status": "POSTED_LINKEDIN",
                "category": "AI",
            }
        ]
        score = calculate_larp_score(ideas, today=fixed_today)
        assert score.current_streak_days == 1
