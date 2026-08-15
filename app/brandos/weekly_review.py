"""
Weekly review / writing coach (Phase 3). Given the week's posting
history and its LARP score, ask an LLM for a short coaching note:
what actually got posted, what got neglected, one concrete suggestion
for next week.

Explicitly on-demand and cached, not part of the daily cron pipeline —
this fires only when the person presses 'w' in the TUI, and the result
is stored in weekly_reviews (one row per ISO week) so re-opening the
Posted tab never re-triggers an LLM call. Mirrors the shape of
project_suggester.py: a pure function that talks to the LLM, plus a
thin orchestration function the TUI calls that handles the
get-existing-or-generate-and-store logic.

Requires OPENROUTER_API_KEY in the environment, same as the digest
generator and project suggester. Model configurable via OPENROUTER_MODEL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from brandos import db
from brandos.openrouter_client import call_openrouter_json, get_api_key, get_model
from brandos.tui.larp_score import LarpScore, calculate_larp_score

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a blunt, encouraging writing coach reviewing \
one week of someone's content posting activity. You're given raw stats \
(not the actual post text) about what they generated, posted, skipped, \
and archived this week, plus their category spread.

Respond with ONLY a JSON object (not an array) with exactly this field:
- summary: 3-5 sentences of coaching. Be specific using the numbers \
given (cite actual counts/categories, don't be vague). Call out what's \
working, what's being neglected, and end with ONE concrete, actionable \
suggestion for next week. Tone: direct and a little wry, not corporate \
or falsely enthusiastic. If the week was genuinely quiet (few or no \
posts), say so plainly rather than padding around it.

No markdown fences, no preamble, no explanation outside the JSON."""


@dataclass
class WeeklyReview:
    week_start: date
    summary: str
    stats: dict


class WeeklyReviewError(Exception):
    """Raised when the LLM call fails or returns something unusable."""


def week_start_for(day: date) -> date:
    """Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.weekday())


def _week_ideas(all_ideas: list[dict], week_start: date) -> list[dict]:
    """Ideas created within [week_start, week_start + 7 days)."""
    week_end = week_start + timedelta(days=7)
    result = []
    for idea in all_ideas:
        created = idea["created_at"]
        created_date = created.date() if hasattr(created, "date") else created
        if week_start <= created_date < week_end:
            result.append(idea)
    return result


def _stats_payload(week_ideas: list[dict], score: LarpScore) -> dict:
    status_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for idea in week_ideas:
        status_counts[idea["status"]] = status_counts.get(idea["status"], 0) + 1
        cat = idea.get("category") or "uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total_generated_this_week": len(week_ideas),
        "status_counts": status_counts,
        "category_counts": category_counts,
        "overall_score": score.overall,
        "consistency": score.consistency,
        "execution": score.execution,
        "diversity": score.diversity,
        "current_streak_days": score.current_streak_days,
        "top_category": score.top_category,
    }


def generate_weekly_review(stats: dict, model: str | None = None) -> str:
    """
    stats: the dict produced by _stats_payload (or equivalent). Talks to
    the LLM only — no DB access, no caching logic, so it's directly
    testable the same way suggest_project() is.
    """
    user_prompt = (
        f"This week's stats:\n"
        f"- Ideas generated: {stats['total_generated_this_week']}\n"
        f"- Status breakdown: {stats['status_counts']}\n"
        f"- Category breakdown: {stats['category_counts']}\n"
        f"- LARP score: {stats['overall_score']}/100 "
        f"(consistency {stats['consistency']}, execution {stats['execution']}, "
        f"diversity {stats['diversity']})\n"
        f"- Current streak: {stats['current_streak_days']} days\n"
        f"- Top category overall: {stats['top_category']}\n\n"
        f"Write the coaching summary."
    )

    try:
        api_key = get_api_key()
    except KeyError as e:
        raise WeeklyReviewError("OPENROUTER_API_KEY is not set") from e

    try:
        parsed = call_openrouter_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=api_key,
            model=get_model(model),
        )
    except requests.RequestException as e:
        logger.error("OpenRouter API call failed during weekly review: %s", e)
        raise WeeklyReviewError(f"API call failed: {e}") from e
    except ValueError as e:
        raise WeeklyReviewError(f"LLM returned invalid JSON: {e}") from e

    if not isinstance(parsed, dict):
        raise WeeklyReviewError(f"Expected a JSON object from LLM, got {type(parsed)}")

    summary = parsed.get("summary", "").strip()
    if not summary:
        raise WeeklyReviewError("LLM response missing required summary field")

    return summary


def get_or_generate_weekly_review(today: date | None = None) -> WeeklyReview:
    """
    The function the TUI calls. Looks up the stored review for the
    current ISO week first; if one already exists, returns it without
    touching the LLM. Otherwise computes this week's stats from
    db.get_recent_ideas(), calls the LLM, stores the result, and
    returns it. Raises WeeklyReviewError on any failure (missing key,
    API error, bad response) — same error-surfacing contract as
    project_suggester.suggest_project.
    """
    today = today or date.today()
    week_start = week_start_for(today)

    existing = db.get_weekly_review(week_start)
    if existing is not None:
        return WeeklyReview(
            week_start=existing["week_start"],
            summary=existing["summary"],
            stats=existing["stats_json"],
        )

    all_ideas = db.get_recent_ideas(limit=500)
    week_ideas = _week_ideas(all_ideas, week_start)
    score = calculate_larp_score(all_ideas, today=today)
    stats = _stats_payload(week_ideas, score)

    summary = generate_weekly_review(stats)

    db.insert_weekly_review(week_start, summary, stats)

    return WeeklyReview(week_start=week_start, summary=summary, stats=stats)
