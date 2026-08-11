"""
Terminal UI for reviewing and logging decisions on generated content ideas.

Tabs:
  Digest      — today's freshly generated batch (status GENERATED)
  Post Ideas  — reviewed short-form post ideas, not yet posted or skipped
  Projects    — stub for now; longer-term project/research ideas are a
                separate concept the user is still defining, not the
                same pipeline as daily post ideas. Placeholder tab keeps
                the nav structure right without guessing at a schema.
  Posted      — everything marked posted, with a platform filter
                (All / LinkedIn / X) and the LARP Score panel

Run with:  python -m brandos.tui
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, ListView, Static, TabbedContent, TabPane

from brandos import db
from brandos.tui.larp_panel import LarpScorePanel
from brandos.tui.larp_score import calculate_larp_score
from brandos.tui.views import IdeaBrowser

DIGEST_STATUSES = ["GENERATED"]
POST_IDEAS_STATUSES = ["GENERATED", "SKIPPED", "ARCHIVED"]
POSTED_STATUSES = ["POSTED_LINKEDIN", "POSTED_X", "POSTED_BOTH"]

PLATFORM_CYCLE = [None, "LINKEDIN", "X"]  # None = All
PLATFORM_LABELS = {None: "All", "LINKEDIN": "LinkedIn", "X": "X"}


class DigestApp(App):
    """
    Keys:
      1/2/3/4          switch tabs (Digest / Post Ideas / Projects / Posted)
      j/k or up/down   move selection within the active tab's list
      p                cycle platform filter (Posted tab only: All -> LinkedIn -> X)
      l                mark selected idea POSTED_LINKEDIN
      x                mark selected idea POSTED_X
      b                mark selected idea POSTED_BOTH
      s                mark selected idea SKIPPED
      a                mark selected idea ARCHIVED
      r                refresh all tabs from DB
      q                quit
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    #platform-indicator {
        dock: top;
        height: 1;
        background: $boost;
        padding: 0 1;
    }
    #projects-stub {
        padding: 2 4;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("1", "switch_tab('digest')", "Digest"),
        Binding("2", "switch_tab('post_ideas')", "Post Ideas"),
        Binding("3", "switch_tab('projects')", "Projects"),
        Binding("4", "switch_tab('posted')", "Posted"),
        Binding("j,down", "cursor_down", "Down", show=False),
        Binding("k,up", "cursor_up", "Up", show=False),
        Binding("p", "cycle_platform", "Platform filter"),
        Binding("l", "mark('POSTED_LINKEDIN')", "Posted LI"),
        Binding("x", "mark('POSTED_X')", "Posted X"),
        Binding("b", "mark('POSTED_BOTH')", "Posted Both"),
        Binding("s", "mark('SKIPPED')", "Skip"),
        Binding("a", "mark('ARCHIVED')", "Archive"),
        Binding("r", "refresh_all", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    posted_platform: reactive[str | None] = reactive(None)
    _had_error: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="platform-indicator")
        with TabbedContent(initial="digest"):
            with TabPane("Digest", id="digest"):
                yield IdeaBrowser(list_id="digest")
            with TabPane("Post Ideas", id="post_ideas"):
                yield IdeaBrowser(list_id="post-ideas")
            with TabPane("Projects", id="projects"):
                yield Vertical(
                    Static(
                        "Projects / research ideas aren't wired up yet — "
                        "this is a placeholder tab. The pipeline currently "
                        "only generates short-form post ideas from Hacker "
                        "News; longer-term project inspiration is a "
                        "separate concept still being defined.",
                        id="projects-stub",
                    )
                )
            with TabPane("Posted", id="posted"):
                yield LarpScorePanel(id="larp-panel")
                yield IdeaBrowser(list_id="posted")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Personal Brand OS"
        self.sub_title = "Content Idea Review"
        self._update_platform_indicator()
        self.refresh_all_tabs()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        # Each tab's IdeaBrowser owns one internal ListView. Walk up from
        # whichever ListView fired to find its parent IdeaBrowser, so
        # navigating in one tab doesn't touch another tab's detail pane.
        if event.item is None:
            return
        browser = event.list_view.parent
        while browser is not None and not isinstance(browser, IdeaBrowser):
            browser = browser.parent
        if browser is not None and hasattr(event.item, "idea"):
            browser.show_detail(event.item.idea)

    # --- data loading -----------------------------------------------

    def refresh_all_tabs(self) -> None:
        self._had_error = False
        self._load_digest()
        self._load_post_ideas()
        self._load_posted()
        if not self._had_error:
            self._set_status("Refreshed")

    def _load_digest(self) -> None:
        try:
            ideas = db.get_ideas_by_status(DIGEST_STATUSES)
        except Exception as e:
            self._set_status(f"[red]DB error (Digest): {e}[/red]")
            self._had_error = True
            ideas = []
        self.query_one("#digest-browser", IdeaBrowser).load(ideas)

    def _load_post_ideas(self) -> None:
        try:
            ideas = db.get_ideas_by_status(POST_IDEAS_STATUSES)
        except Exception as e:
            self._set_status(f"[red]DB error (Post Ideas): {e}[/red]")
            self._had_error = True
            ideas = []
        self.query_one("#post-ideas-browser", IdeaBrowser).load(ideas)

    def _load_posted(self) -> None:
        try:
            ideas = db.get_ideas_by_status(POSTED_STATUSES, platform=self.posted_platform)
        except Exception as e:
            self._set_status(f"[red]DB error (Posted): {e}[/red]")
            self._had_error = True
            ideas = []
        self.query_one("#posted-browser", IdeaBrowser).load(ideas)

        # LARP score is computed from ALL history (not just posted, and
        # not just the platform-filtered view) — execution rate needs
        # the full generated/posted picture regardless of which platform
        # tab is currently selected.
        try:
            all_ideas = db.get_recent_ideas(limit=500)
        except Exception:
            all_ideas = []
        score = calculate_larp_score(all_ideas)
        self.query_one("#larp-panel", LarpScorePanel).update_score(score)

    def _update_platform_indicator(self) -> None:
        label = PLATFORM_LABELS[self.posted_platform]
        self.query_one("#platform-indicator", Static).update(
            f"Posted tab filter: [bold]{label}[/bold]  (press 'p' to cycle)"
        )

    def _set_status(self, message: str) -> None:
        self.query_one("#status-bar", Static).update(message)

    # --- actions -------------------------------------------------------

    def _active_browser(self) -> IdeaBrowser | None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        list_id_map = {
            "digest": "digest-browser",
            "post_ideas": "post-ideas-browser",
            "posted": "posted-browser",
        }
        list_id = list_id_map.get(active)
        if not list_id:
            return None
        return self.query_one(f"#{list_id}", IdeaBrowser)

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_cursor_down(self) -> None:
        browser = self._active_browser()
        if browser:
            browser.query_one(ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        browser = self._active_browser()
        if browser:
            browser.query_one(ListView).action_cursor_up()

    def action_cycle_platform(self) -> None:
        tabs = self.query_one(TabbedContent)
        if tabs.active != "posted":
            self._set_status("Platform filter only applies to the Posted tab")
            return
        current_index = PLATFORM_CYCLE.index(self.posted_platform)
        self.posted_platform = PLATFORM_CYCLE[(current_index + 1) % len(PLATFORM_CYCLE)]
        self._update_platform_indicator()
        self._load_posted()

    def action_refresh_all(self) -> None:
        self.refresh_all_tabs()

    def action_mark(self, status: str) -> None:
        browser = self._active_browser()
        if not browser:
            self._set_status("Nothing to mark in this tab")
            return

        idea = browser.selected_idea
        if idea is None:
            self._set_status("No idea selected")
            return

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

        self._set_status(f"Marked '{idea['headline'][:40]}...' as {status}")
        self.refresh_all_tabs()
