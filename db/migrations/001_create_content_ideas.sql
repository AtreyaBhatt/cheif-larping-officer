-- 001_create_content_ideas.sql
-- Core table for Personal Brand OS. One row = one generated content idea,
-- tracked from generation through publish/skip decision.

-- Required for gen_random_uuid() used as the id default below.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS content_ideas (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    headline          TEXT NOT NULL,
    content           TEXT NOT NULL,
    source_articles   JSONB NOT NULL DEFAULT '[]'::jsonb,
    category          TEXT,
    estimated_quality NUMERIC(3,1),   -- e.g. 0.0–10.0 scale, app-level validated
    reasoning         TEXT,

    -- app-level enum, kept as TEXT for easy evolution early on:
    -- GENERATED | POSTED_LINKEDIN | POSTED_X | POSTED_BOTH | SKIPPED | ARCHIVED
    status            TEXT NOT NULL DEFAULT 'GENERATED',
    platform          TEXT,           -- LINKEDIN | X | BOTH | NULL
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_ideas_status     ON content_ideas (status);
CREATE INDEX IF NOT EXISTS idx_content_ideas_created_at ON content_ideas (created_at);
CREATE INDEX IF NOT EXISTS idx_content_ideas_category   ON content_ideas (category);
