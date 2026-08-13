"""
Terminal UI for reviewing and logging decisions on generated content ideas.

Tabs:
  Digest      — today's freshly generated batch (status GENERATED),
                informational summaries only, NOT meant to be posted
  Posts       — the same generated ideas, but showing the actual
                copy-pasteable LinkedIn/X post text, filterable by
                platform (All / LinkedIn / X) — this is what you
                actually paste into the platform
  Projects    — durable, user-curated projects that demonstrate real
                technologies covered in the Digest. Added manually (press
                'n') or suggested by the LLM from a specific Digest/Posts
                idea (press 'g' while that idea is selected). Optionally
                linked back to the idea that inspired them.
  Posted      — everything marked posted, with a platform filter
                (All / LinkedIn / X) and the LARP Score panel

Run with:  python -m brandos.tui
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, ListView, Static, TabbedContent, TabPane

from brandos import db
from brandos.project_suggester import ProjectSuggestionError, suggest_project
from brandos.tui.add_project_modal import AddProjectModal, NewProjectData
from brandos.tui.larp_panel import LarpScorePanel
from brandos.tui.larp_score import calculate_larp_score
from brandos.tui.views import IdeaBrowser, PostBrowser, ProjectBrowser

DIGEST_STATUSES = ["GENERATED"]
POSTS_STATUSES = ["GENERATED", "SKIPPED", "ARCHIVED"]  # posts not yet posted or set aside
POSTED_STATUSES = ["POSTED_LINKEDIN", "POSTED_X", "POSTED_BOTH"]
PROJECT_STATUS_CYCLE = ["IDEA", "BUILDING", "DONE"]

PLATFORM_CYCLE = [None, "LINKEDIN", "X"]  # None = All
PLATFORM_LABELS = {None: "All", "LINKEDIN": "LinkedIn", "X": "X"}


class DigestApp(App):
    """
    Keys:
      1/2/3/4          switch tabs (Digest / Posts / Projects / Posted)
      j/k or up/down   move selection within the active tab's list
      p                cycle platform filter (Posts or Posted tab: All -> LinkedIn -> X)
      l                mark selected idea POSTED_LINKEDIN (Digest/Posts/Posted)
      x                mark selected idea POSTED_X (Digest/Posts/Posted)
      b                mark selected idea POSTED_BOTH (Digest/Posts/Posted)
      s                mark selected idea SKIPPED (Digest/Posts/Posted)
      a                mark selected idea ARCHIVED (Digest/Posts/Posted)
      n                new project (Projects tab: opens add form;
                       Digest/Posts tab: no-op, use 'g' instead)
      g                generate an LLM project suggestion from the
                       selected Digest/Posts idea
      c                cycle selected project's status (Projects tab only:
                       IDEA -> BUILDING -> DONE)
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
    """

    BINDINGS = [
        Binding("1", "switch_tab('digest')", "Digest"),
        Binding("2", "switch_tab('posts')", "Posts"),
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
        Binding("n", "new_project", "New Project"),
        Binding("g", "suggest_project", "Suggest Project"),
        Binding("c", "cycle_project_status", "Cycle Status"),
        Binding("r", "refresh_all", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    posts_platform: reactive[str | None] = reactive(None)
    posted_platform: reactive[str | None] = reactive(None)
    _had_error: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="platform-indicator")
        with TabbedContent(initial="digest"):
            with TabPane("Digest", id="digest"):
                yield IdeaBrowser(list_id="digest")
            with TabPane("Posts", id="posts"):
                yield PostBrowser(list_id="posts")
            with TabPane("Projects", id="projects"):
                yield ProjectBrowser(list_id="project")
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
        # Each tab's browser widget owns one internal ListView. Walk up
        # from whichever ListView fired to find its parent browser, so
        # navigating in one tab doesn't touch another tab's detail pane.
        if event.item is None:
            return
        browser = event.list_view.parent
        while browser is not None and not isinstance(browser, (IdeaBrowser, ProjectBrowser)):
            browser = browser.parent
        if browser is None:
            return
        if hasattr(event.item, "idea"):
            browser.show_detail(event.item.idea)
        elif hasattr(event.item, "project"):
            browser.show_detail(event.item.project)

    # --- data loading -----------------------------------------------

    def refresh_all_tabs(self) -> None:
        self._had_error = False
        self._load_digest()
        self._load_posts()
        self._load_projects()
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

    def _load_posts(self) -> None:
        try:
            ideas = db.get_ideas_by_status(POSTS_STATUSES, platform=self.posts_platform)
        except Exception as e:
            self._set_status(f"[red]DB error (Posts): {e}[/red]")
            self._had_error = True
            ideas = []
        browser = self.query_one("#posts-browser", PostBrowser)
        browser.platform_filter = self.posts_platform
        browser.load(ideas)

    def _load_projects(self) -> None:
        try:
            projects = db.get_projects()
        except Exception as e:
            self._set_status(f"[red]DB error (Projects): {e}[/red]")
            self._had_error = True
            projects = []
        self.query_one("#project-browser", ProjectBrowser).load(projects)

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
        tabs = self.query_one(TabbedContent)
        if tabs.active == "posts":
            label = PLATFORM_LABELS[self.posts_platform]
            tab_name = "Posts"
        elif tabs.active == "posted":
            label = PLATFORM_LABELS[self.posted_platform]
            tab_name = "Posted"
        else:
            self.query_one("#platform-indicator", Static).update(
                "Platform filter applies to the Posts and Posted tabs (press 'p' there to cycle)"
            )
            return
        self.query_one("#platform-indicator", Static).update(
            f"{tab_name} tab filter: [bold]{label}[/bold]  (press 'p' to cycle)"
        )

    def _set_status(self, message: str) -> None:
        self.query_one("#status-bar", Static).update(message)

    # --- actions -------------------------------------------------------

    def _active_browser(self) -> IdeaBrowser | None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        list_id_map = {
            "digest": "digest-browser",
            "posts": "posts-browser",
            "posted": "posted-browser",
        }
        list_id = list_id_map.get(active)
        if not list_id:
            return None
        return self.query_one(f"#{list_id}", IdeaBrowser)

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
        self._update_platform_indicator()

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
        if tabs.active == "posts":
            current_index = PLATFORM_CYCLE.index(self.posts_platform)
            self.posts_platform = PLATFORM_CYCLE[(current_index + 1) % len(PLATFORM_CYCLE)]
            self._update_platform_indicator()
            self._load_posts()
        elif tabs.active == "posted":
            current_index = PLATFORM_CYCLE.index(self.posted_platform)
            self.posted_platform = PLATFORM_CYCLE[(current_index + 1) % len(PLATFORM_CYCLE)]
            self._update_platform_indicator()
            self._load_posted()
        else:
            self._set_status("Platform filter only applies to the Posts and Posted tabs")

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

    def action_new_project(self) -> None:
        tabs = self.query_one(TabbedContent)
        if tabs.active != "projects":
            self._set_status("Press 'n' while on the Projects tab to add one manually")
            return
        self.push_screen(AddProjectModal(), self._on_new_project_submitted)

    def _on_new_project_submitted(self, data: NewProjectData | None) -> None:
        if data is None:
            self._set_status("New project cancelled")
            return

        try:
            db.insert_project(
                title=data.title,
                description=data.description,
                category=data.category,
                github_url=data.github_url,
                demo_url=data.demo_url,
                source="MANUAL",
            )
        except Exception as e:
            self._set_status(f"[red]Failed to create project: {e}[/red]")
            return

        self._set_status(f"Created project '{data.title}'")
        self.refresh_all_tabs()

    def action_suggest_project(self) -> None:
        tabs = self.query_one(TabbedContent)
        if tabs.active not in ("digest", "posts"):
            self._set_status("Select an idea in the Digest or Posts tab, then press 'g' to suggest a project")
            return

        browser = self._active_browser()
        idea = browser.selected_idea if browser else None
        if idea is None:
            self._set_status("No idea selected")
            return

        self._set_status(f"Asking the LLM to suggest a project for '{idea['headline'][:40]}...'")
        self._run_project_suggestion(idea)

    def _run_project_suggestion(self, idea: dict) -> None:
        summary = idea.get("digest_summary") or idea.get("content") or ""
        try:
            suggestion = suggest_project(idea["headline"], summary)
        except ProjectSuggestionError as e:
            self._set_status(f"[red]Project suggestion failed: {e}[/red]")
            return

        try:
            db.insert_project(
                title=suggestion.title,
                description=suggestion.description,
                category=suggestion.category,
                source="LLM_SUGGESTED",
                linked_idea_id=idea["id"],
            )
        except Exception as e:
            self._set_status(f"[red]Failed to save suggested project: {e}[/red]")
            return

        self._set_status(f"Added suggested project '{suggestion.title}' (linked to this idea)")
        self.refresh_all_tabs()

    def action_cycle_project_status(self) -> None:
        tabs = self.query_one(TabbedContent)
        if tabs.active != "projects":
            self._set_status("Status cycling only applies to the Projects tab")
            return

        browser = self.query_one("#project-browser", ProjectBrowser)
        project = browser.selected_project
        if project is None:
            self._set_status("No project selected")
            return

        current_index = PROJECT_STATUS_CYCLE.index(project["status"])
        new_status = PROJECT_STATUS_CYCLE[(current_index + 1) % len(PROJECT_STATUS_CYCLE)]

        try:
            db.update_project_status(project["id"], new_status)
        except Exception as e:
            self._set_status(f"[red]Failed to update project status: {e}[/red]")
            return

        self._set_status(f"'{project['title'][:40]}...' is now {new_status}")
        self.refresh_all_tabs()
