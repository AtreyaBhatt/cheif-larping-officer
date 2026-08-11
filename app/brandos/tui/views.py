"""
Reusable widget: a list of content ideas on the left, full detail on the
right. Used inside each TabPane (Digest / Post Ideas / Posted) so the
browsing/marking interaction is written once and configured per-tab via
which statuses/platform it loads and which action keys it exposes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import ListItem, ListView, Label, Static

STATUS_ICONS = {
    "GENERATED": "○",
    "POSTED_LINKEDIN": "✔ LI",
    "POSTED_X": "✔ X",
    "POSTED_BOTH": "✔ LI+X",
    "SKIPPED": "✗",
    "ARCHIVED": "▪",
}

STATUS_STYLES = {
    "GENERATED": "yellow",
    "POSTED_LINKEDIN": "green",
    "POSTED_X": "green",
    "POSTED_BOTH": "bold green",
    "SKIPPED": "dim red",
    "ARCHIVED": "dim",
}


def relative_day(dt: datetime) -> str:
    """'Today', 'Yesterday', or the date — keeps the list scannable."""
    now = datetime.now(timezone.utc)
    delta_days = (now.date() - dt.date()).days
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    return dt.strftime("%b %d")


class IdeaListItem(ListItem):
    """One row in an idea list: status icon + headline + relative date."""

    def __init__(self, idea: dict):
        self.idea = idea
        icon = STATUS_ICONS.get(idea["status"], "?")
        style = STATUS_STYLES.get(idea["status"], "white")
        day = relative_day(idea["created_at"])
        label_text = f"[{style}]{icon}[/{style}] {idea['headline'][:55]}  [dim]({day})[/dim]"
        super().__init__(Label(label_text))


class IdeaBrowser(Horizontal):
    """
    Left: ListView of ideas. Right: detail pane for the selected one.
    Does not fetch data itself — call load(ideas) with whatever the
    parent already queried, so each tab controls its own filter.
    """

    DEFAULT_CSS = """
    IdeaBrowser {
        height: 1fr;
    }
    IdeaBrowser > ListView {
        width: 45%;
        border-right: solid $panel;
    }
    IdeaBrowser > VerticalScroll {
        width: 55%;
        padding: 1 2;
    }
    .detail-headline {
        text-style: bold;
        margin-bottom: 1;
    }
    .detail-meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def __init__(self, list_id: str, **kwargs):
        # list_id is used as a prefix for all internal widget IDs
        # (ListView, detail labels). The IdeaBrowser container itself
        # gets its own id, separate from list_id, so callers can query
        # for the IdeaBrowser instance and the internal ListView without
        # a collision — e.g. list_id="digest" gives an internal ListView
        # id of "digest-list" and a container id of "digest-browser".
        kwargs.setdefault("id", f"{list_id}-browser")
        super().__init__(**kwargs)
        self.list_id = list_id
        self.ideas: list[dict] = []

    def compose(self) -> ComposeResult:
        yield ListView(id=f"{self.list_id}-list")
        with VerticalScroll():
            yield Static("", classes="detail-headline", id=f"{self.list_id}-headline")
            yield Static("", classes="detail-meta", id=f"{self.list_id}-meta")
            yield Static("", id=f"{self.list_id}-content")

    def load(self, ideas: list[dict]) -> None:
        self.ideas = ideas
        list_view = self.query_one(f"#{self.list_id}-list", ListView)
        list_view.clear()
        for idea in ideas:
            list_view.append(IdeaListItem(idea))

        if ideas:
            list_view.index = 0
            self.show_detail(ideas[0])
        else:
            self._clear_detail()

    def show_detail(self, idea: dict) -> None:
        headline = self.query_one(f"#{self.list_id}-headline", Static)
        meta = self.query_one(f"#{self.list_id}-meta", Static)
        content = self.query_one(f"#{self.list_id}-content", Static)

        headline.update(idea["headline"])

        status_icon = STATUS_ICONS.get(idea["status"], idea["status"])
        meta_parts = [f"Status: {status_icon}", f"Category: {idea.get('category') or 'uncategorized'}"]
        if idea.get("estimated_quality") is not None:
            meta_parts.append(f"Quality: {idea['estimated_quality']}/10")
        meta_parts.append(relative_day(idea["created_at"]))
        meta.update("  •  ".join(meta_parts))

        body = idea["content"] or ""
        if idea.get("reasoning"):
            body += f"\n\n[dim]Reasoning: {idea['reasoning']}[/dim]"
        content.update(body)

    def _clear_detail(self) -> None:
        self.query_one(f"#{self.list_id}-headline", Static).update("")
        self.query_one(f"#{self.list_id}-meta", Static).update("")
        self.query_one(f"#{self.list_id}-content", Static).update("No ideas in this view yet.")

    @property
    def selected_idea(self) -> dict | None:
        list_view = self.query_one(f"#{self.list_id}-list", ListView)
        if list_view.index is None or not self.ideas or list_view.index >= len(self.ideas):
            return None
        return self.ideas[list_view.index]
