"""
Terminal UI for reviewing and logging decisions on generated content ideas.

Replaces the WhatsApp/Twilio delivery path from earlier in Phase 1 — instead
of the digest being pushed to you, you pull it up here, browse ideas, and
log your decision (posted to LinkedIn/X/both, or skipped) directly against
the same content_ideas table.

Run with:  python -m brandos.tui
"""
from __future__ import annotations

from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Header, ListItem, ListView, Label, Static

from brandos import db

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


def _relative_day(dt: datetime) -> str:
    """'Today', 'Yesterday', or the date — keeps the list scannable."""
    now = datetime.now(timezone.utc)
    delta_days = (now.date() - dt.date()).days
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    return dt.strftime("%b %d")


class IdeaListItem(ListItem):
    """One row in the left-hand list: status icon + headline + relative date."""

    def __init__(self, idea: dict):
        self.idea = idea
        icon = STATUS_ICONS.get(idea["status"], "?")
        style = STATUS_STYLES.get(idea["status"], "white")
        day = _relative_day(idea["created_at"])
        label_text = f"[{style}]{icon}[/{style}] {idea['headline'][:60]}  [dim]({day})[/dim]"
        super().__init__(Label(label_text))


class DigestApp(App):
    """
    Keys:
      j/k or up/down   move selection
      1                mark POSTED_LINKEDIN
      2                mark POSTED_X
      3                mark POSTED_BOTH
      s                mark SKIPPED
      a                mark ARCHIVED
      r                refresh from DB
      q                quit
    """

    CSS = """
    Screen {
        layout: horizontal;
    }
    #idea-list {
        width: 45%;
        border-right: solid $panel;
    }
    #detail-pane {
        width: 55%;
        padding: 1 2;
    }
    #detail-headline {
        text-style: bold;
        margin-bottom: 1;
    }
    #detail-meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    #detail-content {
        margin-bottom: 1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("j,down", "cursor_down", "Down", show=False),
        Binding("k,up", "cursor_up", "Up", show=False),
        Binding("1", "mark('POSTED_LINKEDIN')", "Posted LI"),
        Binding("2", "mark('POSTED_X')", "Posted X"),
        Binding("3", "mark('POSTED_BOTH')", "Posted Both"),
        Binding("s", "mark('SKIPPED')", "Skip"),
        Binding("a", "mark('ARCHIVED')", "Archive"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    ideas: reactive[list[dict]] = reactive([], recompose=False)
    status_message: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield ListView(id="idea-list")
            with VerticalScroll(id="detail-pane"):
                yield Static("", id="detail-headline")
                yield Static("", id="detail-meta")
                yield Static("", id="detail-content")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Personal Brand OS"
        self.sub_title = "Content Idea Review"
        self.load_ideas()

    def load_ideas(self) -> None:
        try:
            self.ideas = db.get_recent_ideas(limit=50)
        except Exception as e:
            self._set_status(f"[red]DB error: {e}[/red]")
            self.ideas = []
            return

        list_view = self.query_one("#idea-list", ListView)
        list_view.clear()
        for idea in self.ideas:
            list_view.append(IdeaListItem(idea))

        if self.ideas:
            list_view.index = 0
            self._show_detail(self.ideas[0])
            self._set_status(f"{len(self.ideas)} ideas loaded")
        else:
            self._set_status("No ideas found — run the digest pipeline first")

    def _show_detail(self, idea: dict) -> None:
        headline = self.query_one("#detail-headline", Static)
        meta = self.query_one("#detail-meta", Static)
        content = self.query_one("#detail-content", Static)

        headline.update(idea["headline"])

        status_icon = STATUS_ICONS.get(idea["status"], idea["status"])
        meta_parts = [f"Status: {status_icon}", f"Category: {idea.get('category') or 'uncategorized'}"]
        if idea.get("estimated_quality") is not None:
            meta_parts.append(f"Quality: {idea['estimated_quality']}/10")
        meta_parts.append(_relative_day(idea["created_at"]))
        meta.update("  •  ".join(meta_parts))

        body = idea["content"] or ""
        if idea.get("reasoning"):
            body += f"\n\n[dim]Reasoning: {idea['reasoning']}[/dim]"
        content.update(body)

    def _set_status(self, message: str) -> None:
        self.status_message = message
        self.query_one("#status-bar", Static).update(message)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is not None and isinstance(event.item, IdeaListItem):
            self._show_detail(event.item.idea)

    def action_cursor_down(self) -> None:
        self.query_one("#idea-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#idea-list", ListView).action_cursor_up()

    def action_refresh(self) -> None:
        self.load_ideas()

    def action_mark(self, status: str) -> None:
        list_view = self.query_one("#idea-list", ListView)
        if list_view.index is None or not self.ideas:
            return

        idea = self.ideas[list_view.index]
        platform_map = {
            "POSTED_LINKEDIN": "LINKEDIN",
            "POSTED_X": "X",
            "POSTED_BOTH": "BOTH",
        }
        platform = platform_map.get(status)

        try:
            db.update_status(idea["id"], status, platform=platform)
        except Exception as e:
            self._set_status(f"[red]Update failed: {e}[/red]")
            return

        idea["status"] = status
        self._set_status(f"Marked '{idea['headline'][:40]}...' as {status}")
        self.load_ideas()  # simplest correct refresh; dataset is small
