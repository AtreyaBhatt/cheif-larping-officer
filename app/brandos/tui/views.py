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

        # digest_summary is the informational summary; content is kept
        # only as a fallback for old rows inserted before the split.
        body = idea.get("digest_summary") or idea.get("content") or ""
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


class PostBrowser(IdeaBrowser):
    """
    Same list/selection mechanics as IdeaBrowser, but the detail pane
    shows the actual copy-pasteable LinkedIn/X post text instead of the
    informational digest summary. Used by the Posts tab.

    Respects a platform filter (None/LINKEDIN/X) — when a platform is
    set, only that platform's post text is shown in detail (still both
    are shown when filter is None/"All"). Terminal apps can't reliably
    write to the system clipboard over SSH, so the design here is:
    render the raw text clearly delimited so the person can mouse-select
    and copy it with their terminal's own copy mechanism.
    """

    def __init__(self, list_id: str, **kwargs):
        super().__init__(list_id=list_id, **kwargs)
        self.platform_filter: str | None = None

    def show_detail(self, idea: dict) -> None:
        headline = self.query_one(f"#{self.list_id}-headline", Static)
        meta = self.query_one(f"#{self.list_id}-meta", Static)
        content = self.query_one(f"#{self.list_id}-content", Static)

        headline.update(idea["headline"])

        status_icon = STATUS_ICONS.get(idea["status"], idea["status"])
        meta_parts = [f"Status: {status_icon}", f"Category: {idea.get('category') or 'uncategorized'}"]
        meta_parts.append(relative_day(idea["created_at"]))
        meta.update("  •  ".join(meta_parts))

        sections = []
        show_linkedin = self.platform_filter in (None, "LINKEDIN")
        show_x = self.platform_filter in (None, "X")

        if show_linkedin:
            li_text = idea.get("linkedin_post") or "[no LinkedIn post generated for this idea]"
            sections.append(f"[bold]── LinkedIn ─────────────────[/bold]\n{li_text}")

        if show_x:
            x_text = idea.get("x_post")
            if not x_text:
                sections.append("[bold]── X ────────────────────────[/bold]\n[no X post generated for this idea]")
            else:
                tweets = [t.strip() for t in x_text.split("\n---\n")]
                if len(tweets) > 1:
                    x_rendered = "\n\n".join(
                        f"[dim]Tweet {i}/{len(tweets)}:[/dim]\n{t}" for i, t in enumerate(tweets, 1)
                    )
                else:
                    x_rendered = x_text
                sections.append(f"[bold]── X ────────────────────────[/bold]\n{x_rendered}")

        content.update("\n\n".join(sections))

    def _clear_detail(self) -> None:
        self.query_one(f"#{self.list_id}-headline", Static).update("")
        self.query_one(f"#{self.list_id}-meta", Static).update("")
        self.query_one(f"#{self.list_id}-content", Static).update("No posts in this view yet.")


PROJECT_STATUS_ICONS = {
    "IDEA": "○",
    "BUILDING": "🔨",
    "DONE": "✔",
}

PROJECT_STATUS_STYLES = {
    "IDEA": "yellow",
    "BUILDING": "cyan",
    "DONE": "bold green",
}


class ProjectListItem(ListItem):
    """One row in the project list: status icon + title + relative date."""

    def __init__(self, project: dict):
        self.project = project
        icon = PROJECT_STATUS_ICONS.get(project["status"], "?")
        style = PROJECT_STATUS_STYLES.get(project["status"], "white")
        day = relative_day(project["created_at"])
        label_text = f"[{style}]{icon}[/{style}] {project['title'][:55]}  [dim]({day})[/dim]"
        super().__init__(Label(label_text))


class ProjectBrowser(Horizontal):
    """
    Left: ListView of projects. Right: detail pane showing description,
    status, category, links, and (if present) the linked digest idea
    that inspired it. Structurally similar to IdeaBrowser but projects
    are a genuinely different entity (own table, own fields), so this
    doesn't subclass IdeaBrowser — it composes the same layout pattern
    independently rather than forcing a shared parent for two things
    that only look alike, not are alike.
    """

    DEFAULT_CSS = """
    ProjectBrowser {
        height: 1fr;
    }
    ProjectBrowser > ListView {
        width: 45%;
        border-right: solid $panel;
    }
    ProjectBrowser > VerticalScroll {
        width: 55%;
        padding: 1 2;
    }
    """

    def __init__(self, list_id: str = "project", **kwargs):
        kwargs.setdefault("id", f"{list_id}-browser")
        super().__init__(**kwargs)
        self.list_id = list_id
        self.projects: list[dict] = []

    def compose(self) -> ComposeResult:
        yield ListView(id=f"{self.list_id}-list")
        with VerticalScroll():
            yield Static("", classes="detail-headline", id=f"{self.list_id}-headline")
            yield Static("", classes="detail-meta", id=f"{self.list_id}-meta")
            yield Static("", id=f"{self.list_id}-content")

    def load(self, projects: list[dict]) -> None:
        self.projects = projects
        list_view = self.query_one(f"#{self.list_id}-list", ListView)
        list_view.clear()
        for project in projects:
            list_view.append(ProjectListItem(project))

        if projects:
            list_view.index = 0
            self.show_detail(projects[0])
        else:
            self._clear_detail()

    def show_detail(self, project: dict) -> None:
        headline = self.query_one(f"#{self.list_id}-headline", Static)
        meta = self.query_one(f"#{self.list_id}-meta", Static)
        content = self.query_one(f"#{self.list_id}-content", Static)

        headline.update(project["title"])

        status_icon = PROJECT_STATUS_ICONS.get(project["status"], project["status"])
        meta_parts = [
            f"Status: {status_icon}",
            f"Category: {project.get('category') or 'uncategorized'}",
            f"Source: {project.get('source', 'MANUAL')}",
            relative_day(project["created_at"]),
        ]
        meta.update("  •  ".join(meta_parts))

        lines = [project.get("description") or "(no description)"]

        links = []
        if project.get("github_url"):
            links.append(f"GitHub: {project['github_url']}")
        if project.get("demo_url"):
            links.append(f"Demo: {project['demo_url']}")
        if project.get("blog_url"):
            links.append(f"Blog: {project['blog_url']}")
        if links:
            lines.append("\n" + "\n".join(links))

        if project.get("linked_idea_headline"):
            lines.append(f"\n[dim]Demonstrates: {project['linked_idea_headline']}[/dim]")

        content.update("\n".join(lines))

    def _clear_detail(self) -> None:
        self.query_one(f"#{self.list_id}-headline", Static).update("")
        self.query_one(f"#{self.list_id}-meta", Static).update("")
        self.query_one(f"#{self.list_id}-content", Static).update(
            "No projects yet. Press 'n' to add one manually, or trigger "
            "a suggestion from an idea in the Digest/Posts tab."
        )

    @property
    def selected_project(self) -> dict | None:
        list_view = self.query_one(f"#{self.list_id}-list", ListView)
        if list_view.index is None or not self.projects or list_view.index >= len(self.projects):
            return None
        return self.projects[list_view.index]
