"""
Postgres access for content_ideas. Deliberately thin — no ORM, just
psycopg with parameterized queries. Matches the schema in
db/migrations/001_create_content_ideas.sql and
db/migrations/002_add_platform_posts.sql.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from brandos.digest import ContentIdea

logger = logging.getLogger(__name__)


def _connection_string() -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"host={host} port={port} dbname={db} user={user} password={password}"


@contextmanager
def get_connection():
    conn = psycopg.connect(_connection_string(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_content_idea(idea: ContentIdea) -> str:
    """Insert one ContentIdea, return its generated id (uuid as str)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_ideas
                    (headline, content, digest_summary, linkedin_post, x_post,
                     source_articles, category, estimated_quality, reasoning, status)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'GENERATED')
                RETURNING id;
                """,
                (
                    idea.headline,
                    idea.content,           # kept for backward compat; new code reads digest_summary
                    idea.digest_summary or idea.content,
                    idea.linkedin_post,
                    idea.x_post,
                    json.dumps(idea.source_articles),
                    idea.category,
                    idea.estimated_quality,
                    idea.reasoning,
                ),
            )
            row = cur.fetchone()
            logger.info("Inserted content_idea id=%s headline=%r", row["id"], idea.headline)
            return str(row["id"])


def insert_content_ideas(ideas: list[ContentIdea]) -> list[str]:
    return [insert_content_idea(idea) for idea in ideas]


def get_pending_ideas(limit: int = 20) -> list[dict]:
    """Ideas still in GENERATED status, most recent first."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, headline, category,
                       digest_summary, linkedin_post, x_post, status
                FROM content_ideas
                WHERE status = 'GENERATED'
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def get_recent_ideas(limit: int = 50) -> list[dict]:
    """
    All ideas regardless of status, most recent first. Used by the TUI to
    show today's batch plus recent history in one view, not just what's
    still pending a decision.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, headline, category,
                       digest_summary, linkedin_post, x_post,
                       estimated_quality, reasoning, status, platform, notes
                FROM content_ideas
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def get_ideas_by_status(statuses: list[str], platform: str | None = None, limit: int = 100) -> list[dict]:
    """
    Ideas matching any of the given statuses, optionally filtered by
    platform. Used by the tabbed TUI views:
      - Digest tab: statuses=['GENERATED']
      - Posts tab:  statuses=['GENERATED', 'SKIPPED', 'ARCHIVED'], platform='LINKEDIN'|'X'|None
      - Posted tab: statuses=['POSTED_LINKEDIN', 'POSTED_X', 'POSTED_BOTH'], platform='LINKEDIN'|'X'|None

    platform=None returns all platforms. When platform is given, it
    matches POSTED_BOTH as well as the exact platform, since a "both"
    post is relevant to both the LinkedIn and X views.
    """
    if not statuses:
        return []

    with get_connection() as conn:
        with conn.cursor() as cur:
            if platform:
                cur.execute(
                    """
                    SELECT id, created_at, headline, category,
                           digest_summary, linkedin_post, x_post,
                           estimated_quality, reasoning, status, platform, notes
                    FROM content_ideas
                    WHERE status = ANY(%s)
                      AND (platform = %s OR platform = 'BOTH')
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (statuses, platform, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, created_at, headline, category,
                           digest_summary, linkedin_post, x_post,
                           estimated_quality, reasoning, status, platform, notes
                    FROM content_ideas
                    WHERE status = ANY(%s)
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (statuses, limit),
                )
            return cur.fetchall()


def update_status(idea_id: str, status: str, platform: str | None = None) -> bool:
    """
    Used by the WhatsApp-reply logging flow (Phase 1 step 2): mark an
    idea as POSTED_LINKEDIN / POSTED_X / POSTED_BOTH / SKIPPED / ARCHIVED.
    Returns True if a row was actually updated.
    """
    valid_statuses = {
        "GENERATED", "POSTED_LINKEDIN", "POSTED_X",
        "POSTED_BOTH", "SKIPPED", "ARCHIVED",
    }
    if status not in valid_statuses:
        raise ValueError(f"Invalid status {status!r}, must be one of {valid_statuses}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE content_ideas
                SET status = %s, platform = %s
                WHERE id = %s;
                """,
                (status, platform, idea_id),
            )
            updated = cur.rowcount > 0
            logger.info("update_status id=%s status=%s platform=%s updated=%s", idea_id, status, platform, updated)
            return updated


# --- Projects ---------------------------------------------------------
#
# Durable, user-curated content demonstrating real technologies covered
# in the Digest — distinct from content_ideas (daily-disposable,
# auto-generated). See db/migrations/003_create_projects.sql.

VALID_PROJECT_STATUSES = {"IDEA", "BUILDING", "DONE"}
VALID_PROJECT_SOURCES = {"MANUAL", "LLM_SUGGESTED"}


def insert_project(
    title: str,
    description: str | None = None,
    status: str = "IDEA",
    github_url: str | None = None,
    demo_url: str | None = None,
    blog_url: str | None = None,
    category: str | None = None,
    source: str = "MANUAL",
    linked_idea_id: str | None = None,
) -> str:
    """Insert one project, return its generated id (uuid as str)."""
    if status not in VALID_PROJECT_STATUSES:
        raise ValueError(f"Invalid status {status!r}, must be one of {VALID_PROJECT_STATUSES}")
    if source not in VALID_PROJECT_SOURCES:
        raise ValueError(f"Invalid source {source!r}, must be one of {VALID_PROJECT_SOURCES}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects
                    (title, description, status, github_url, demo_url,
                     blog_url, category, source, linked_idea_id)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (title, description, status, github_url, demo_url, blog_url, category, source, linked_idea_id),
            )
            row = cur.fetchone()
            logger.info("Inserted project id=%s title=%r", row["id"], title)
            return str(row["id"])


def get_projects(status: str | None = None, limit: int = 100) -> list[dict]:
    """
    All projects, optionally filtered by status, most recently created
    first. Includes the linked idea's headline (if any) via a LEFT JOIN
    so the TUI can show "demonstrates: <headline>" without a second query.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            base_query = """
                SELECT p.id, p.created_at, p.updated_at, p.title, p.description,
                       p.status, p.github_url, p.demo_url, p.blog_url,
                       p.category, p.source, p.linked_idea_id,
                       ci.headline AS linked_idea_headline
                FROM projects p
                LEFT JOIN content_ideas ci ON ci.id = p.linked_idea_id
            """
            if status:
                cur.execute(
                    base_query + " WHERE p.status = %s ORDER BY p.created_at DESC LIMIT %s;",
                    (status, limit),
                )
            else:
                cur.execute(
                    base_query + " ORDER BY p.created_at DESC LIMIT %s;",
                    (limit,),
                )
            return cur.fetchall()


def update_project_status(project_id: str, status: str) -> bool:
    """Move a project between IDEA / BUILDING / DONE. Returns True if updated."""
    if status not in VALID_PROJECT_STATUSES:
        raise ValueError(f"Invalid status {status!r}, must be one of {VALID_PROJECT_STATUSES}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE projects
                SET status = %s, updated_at = now()
                WHERE id = %s;
                """,
                (status, project_id),
            )
            updated = cur.rowcount > 0
            logger.info("update_project_status id=%s status=%s updated=%s", project_id, status, updated)
            return updated


def update_project(
    project_id: str,
    title: str | None = None,
    description: str | None = None,
    github_url: str | None = None,
    demo_url: str | None = None,
    blog_url: str | None = None,
    category: str | None = None,
) -> bool:
    """
    Partial update for editable project fields (not status — use
    update_project_status for that). Only non-None arguments are
    applied; pass a field explicitly to change it.
    """
    fields, values = [], []
    for column, value in [
        ("title", title), ("description", description), ("github_url", github_url),
        ("demo_url", demo_url), ("blog_url", blog_url), ("category", category),
    ]:
        if value is not None:
            fields.append(f"{column} = %s")
            values.append(value)

    if not fields:
        return False

    fields.append("updated_at = now()")
    values.append(project_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE projects SET {', '.join(fields)} WHERE id = %s;",
                tuple(values),
            )
            updated = cur.rowcount > 0
            logger.info("update_project id=%s updated=%s", project_id, updated)
            return updated


def delete_project(project_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM projects WHERE id = %s;", (project_id,))
            deleted = cur.rowcount > 0
            logger.info("delete_project id=%s deleted=%s", project_id, deleted)
            return deleted
