"""
Postgres access for content_ideas. Deliberately thin — no ORM, just
psycopg with parameterized queries. Matches the schema in
db/migrations/001_create_content_ideas.sql exactly.
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
                    (headline, content, source_articles, category,
                     estimated_quality, reasoning, status)
                VALUES
                    (%s, %s, %s, %s, %s, %s, 'GENERATED')
                RETURNING id;
                """,
                (
                    idea.headline,
                    idea.content,
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
                SELECT id, created_at, headline, content, category, status
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
                SELECT id, created_at, headline, content, category,
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
      - Digest tab:     statuses=['GENERATED']
      - Post Ideas tab: statuses=['GENERATED', 'SKIPPED', 'ARCHIVED'] (reviewed, not yet posted, or set aside)
      - Posted tab:     statuses=['POSTED_LINKEDIN', 'POSTED_X', 'POSTED_BOTH'], platform='LINKEDIN'|'X'|None

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
                    SELECT id, created_at, headline, content, category,
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
                    SELECT id, created_at, headline, content, category,
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
