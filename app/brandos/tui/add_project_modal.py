"""
Modal for manually adding a new project. Pushed via app.push_screen()
with a callback that receives the created project's fields (or None if
cancelled), so the caller (DigestApp) owns the actual db.insert_project
call rather than this screen reaching into the DB itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea


@dataclass
class NewProjectData:
    title: str
    description: str
    category: str
    github_url: str | None = None
    demo_url: str | None = None


class AddProjectModal(ModalScreen[NewProjectData | None]):
    """
    Simple form: title, description, category, optional GitHub/demo
    URLs. Submitting with an empty title is rejected (title is the only
    required field) rather than silently creating a blank project.
    """

    DEFAULT_CSS = """
    AddProjectModal {
        align: center middle;
    }
    AddProjectModal > Container {
        width: 70;
        height: auto;
        border: thick $panel;
        background: $surface;
        padding: 1 2;
    }
    AddProjectModal Label {
        margin-top: 1;
    }
    AddProjectModal Input {
        width: 100%;
    }
    AddProjectModal TextArea {
        width: 100%;
        height: 5;
    }
    AddProjectModal #buttons {
        margin-top: 1;
        align: right middle;
        height: auto;
    }
    AddProjectModal #error {
        color: $error;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("New Project", id="modal-title")
            yield Label("Title *")
            yield Input(placeholder="Project title", id="title-input")
            yield Label("Description")
            yield TextArea(id="description-input")
            yield Label("Category (e.g. AI, Rust, Developer Tools)")
            yield Input(placeholder="Category", id="category-input")
            yield Label("GitHub URL (optional)")
            yield Input(placeholder="https://github.com/...", id="github-input")
            yield Label("Demo URL (optional)")
            yield Input(placeholder="https://...", id="demo-input")
            yield Label("", id="error")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button("Create", id="create-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return

        if event.button.id == "create-btn":
            title = self.query_one("#title-input", Input).value.strip()
            if not title:
                self.query_one("#error", Label).update("Title is required.")
                return

            description = self.query_one("#description-input", TextArea).text.strip()
            category = self.query_one("#category-input", Input).value.strip() or "other"
            github_url = self.query_one("#github-input", Input).value.strip() or None
            demo_url = self.query_one("#demo-input", Input).value.strip() or None

            self.dismiss(NewProjectData(
                title=title,
                description=description,
                category=category,
                github_url=github_url,
                demo_url=demo_url,
            ))
