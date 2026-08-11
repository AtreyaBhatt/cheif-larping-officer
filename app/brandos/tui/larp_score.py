"""
LARP Score: a synthetic, admittedly-silly metric summarizing posting
consistency and diversity from real content_ideas history. Not a
measure of actual influence — a measure of whether you're actually
showing up, computed entirely from your own logged decisions.

Kept as a standalone module (not inline in the TUI) so the scoring
logic is unit-testable without spinning up Textual at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

POSTED_STATUSES = {"POSTED_LINKEDIN", "POSTED_X", "POSTED_BOTH"}


@dataclass
class LarpScore:
    overall: int              # 0-100
    consistency: int          # 0-100, streak-based
    execution: int            # 0-100, posted / generated ratio
    diversity: int            # 0-100, category spread
    current_streak_days: int
    longest_streak_days: int
    total_generated: int
    total_posted: int
    posts_last_7_days: int
    posts_last_30_days: int
    top_category: str | None


def _post_dates(ideas: list[dict]) -> list[date]:
    """Distinct calendar dates (UTC) on which at least one idea was posted."""
    dates = set()
    for idea in ideas:
        if idea["status"] in POSTED_STATUSES:
            created = idea["created_at"]
            if isinstance(created, datetime):
                dates.add(created.astimezone(timezone.utc).date())
    return sorted(dates)


def _current_streak(post_dates: list[date], today: date) -> int:
    """
    Consecutive days up to and including today (or yesterday, if nothing
    posted yet today) with at least one post. Simple day-granularity
    streak — doesn't care how many posts landed on a given day.
    """
    if not post_dates:
        return 0

    date_set = set(post_dates)
    # Allow the streak to still count if today has no post yet but
    # yesterday does — otherwise every streak resets to 0 first thing
    # each morning before you've had a chance to post.
    cursor = today if today in date_set else today - timedelta(days=1)
    if cursor not in date_set:
        return 0

    streak = 0
    while cursor in date_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _longest_streak(post_dates: list[date]) -> int:
    if not post_dates:
        return 0

    longest = 1
    current = 1
    for prev, curr in zip(post_dates, post_dates[1:]):
        if (curr - prev).days == 1:
            current += 1
            longest = max(longest, current)
        elif (curr - prev).days > 1:
            current = 1
    return longest


def _category_diversity(posted_ideas: list[dict]) -> tuple[int, str | None]:
    """
    Returns (diversity_score_0_100, top_category). Diversity is based on
    how evenly posts spread across categories — all-one-category scores
    low, evenly spread across many scores high. Uses normalized Shannon
    entropy so it's comparable regardless of how many categories exist.
    """
    if not posted_ideas:
        return 0, None

    counts: dict[str, int] = {}
    for idea in posted_ideas:
        cat = idea.get("category") or "uncategorized"
        counts[cat] = counts.get(cat, 0) + 1

    top_category = max(counts, key=counts.get)

    if len(counts) == 1:
        return 0, top_category

    import math
    total = sum(counts.values())
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    max_entropy = math.log2(len(counts))
    normalized = entropy / max_entropy if max_entropy > 0 else 0
    return round(normalized * 100), top_category


def calculate_larp_score(ideas: list[dict], today: date | None = None) -> LarpScore:
    """
    ideas: rows from db.get_recent_ideas() or equivalent — dicts with at
    least 'created_at', 'status', 'category'.
    today: injectable for testing; defaults to real UTC today.
    """
    today = today or datetime.now(timezone.utc).date()

    posted_ideas = [i for i in ideas if i["status"] in POSTED_STATUSES]
    total_generated = len(ideas)
    total_posted = len(posted_ideas)

    post_dates = _post_dates(ideas)
    current_streak = _current_streak(post_dates, today)
    longest_streak = _longest_streak(post_dates)

    cutoff_7 = today - timedelta(days=7)
    cutoff_30 = today - timedelta(days=30)
    posts_last_7 = sum(1 for d in post_dates if d > cutoff_7)
    posts_last_30 = sum(1 for d in post_dates if d > cutoff_30)

    # Consistency: longest realistic streak we'd expect to reward is ~30
    # days for a daily-posting habit; cap the score there so a single
    # very long streak doesn't make the number meaningless.
    consistency = min(100, round((current_streak / 30) * 100)) if current_streak else 0

    # Execution: posted / generated, as a percentage. Naturally penalizes
    # generating a ton of ideas and posting almost none of them.
    execution = round((total_posted / total_generated) * 100) if total_generated else 0

    diversity, top_category = _category_diversity(posted_ideas)

    overall = round(0.4 * consistency + 0.35 * execution + 0.25 * diversity)

    return LarpScore(
        overall=overall,
        consistency=consistency,
        execution=execution,
        diversity=diversity,
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        total_generated=total_generated,
        total_posted=total_posted,
        posts_last_7_days=posts_last_7,
        posts_last_30_days=posts_last_30,
        top_category=top_category,
    )
