"""
Displays the LARP Score panel: overall score plus its component
breakdown, shown at the top of the Posted tab.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from brandos.tui.larp_score import LarpScore


def _bar(value: int, width: int = 20) -> str:
    """Simple ASCII progress bar for a 0-100 value."""
    filled = round((value / 100) * width)
    return "█" * filled + "░" * (width - filled)


def _score_color(value: int) -> str:
    if value >= 70:
        return "green"
    if value >= 40:
        return "yellow"
    return "red"


class LarpScorePanel(Vertical):
    """Renders a LarpScore dataclass as a compact stats panel."""

    DEFAULT_CSS = """
    LarpScorePanel {
        height: auto;
        border: solid $panel;
        padding: 1 2;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="larp-overall")
        yield Static("", id="larp-breakdown")
        yield Static("", id="larp-stats")
        yield Static("", id="larp-review")

    def update_review(self, message: str) -> None:
        """
        Renders the weekly review section: either the coaching summary
        text, a loading/error message, or a prompt to generate one.
        Kept as free text (not a WeeklyReview object) so this widget
        doesn't need to know about the weekly_review module's types —
        the app formats the message, this just displays it.
        """
        self.query_one("#larp-review", Static).update(message)

    def update_score(self, score: LarpScore) -> None:
        overall_color = _score_color(score.overall)
        overall = self.query_one("#larp-overall", Static)
        overall.update(
            f"[bold]LARP Score: [{overall_color}]{score.overall}/100[/{overall_color}][/bold]  "
            f"(not a real influence metric, just whether you're showing up)"
        )

        breakdown = self.query_one("#larp-breakdown", Static)
        lines = [
            f"Consistency  {_bar(score.consistency)}  {score.consistency:>3}",
            f"Execution    {_bar(score.execution)}  {score.execution:>3}",
            f"Diversity    {_bar(score.diversity)}  {score.diversity:>3}",
        ]
        breakdown.update("\n".join(lines))

        stats = self.query_one("#larp-stats", Static)
        top_cat = score.top_category or "—"
        stats.update(
            f"\n[dim]"
            f"Current streak: {score.current_streak_days}d  •  "
            f"Longest streak: {score.longest_streak_days}d  •  "
            f"Last 7d: {score.posts_last_7_days}  •  "
            f"Last 30d: {score.posts_last_30_days}  •  "
            f"Top category: {top_cat}  •  "
            f"Posted {score.total_posted}/{score.total_generated} generated"
            f"[/dim]"
        )
