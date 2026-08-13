-- 003_create_projects.sql
-- Projects are durable, user-curated content demonstrating real
-- technologies covered in the Digest — distinct from content_ideas
-- (which is daily-disposable, auto-generated). A project can
-- optionally trace back to the specific digest idea that inspired it.

CREATE TABLE IF NOT EXISTS projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    title           TEXT NOT NULL,
    description     TEXT,

    -- app-level enum, kept as TEXT for easy evolution:
    -- IDEA | BUILDING | DONE
    status          TEXT NOT NULL DEFAULT 'IDEA',

    github_url      TEXT,
    demo_url        TEXT,
    blog_url        TEXT,

    category        TEXT,

    -- MANUAL | LLM_SUGGESTED — tracks how the project originated
    source          TEXT NOT NULL DEFAULT 'MANUAL',

    -- Optional link back to the content_ideas row that inspired this
    -- project. Nullable — projects can stand alone. ON DELETE SET NULL
    -- so removing an old digest entry doesn't cascade-delete a project
    -- you're still actively building.
    linked_idea_id  UUID REFERENCES content_ideas(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status         ON projects (status);
CREATE INDEX IF NOT EXISTS idx_projects_created_at      ON projects (created_at);
CREATE INDEX IF NOT EXISTS idx_projects_linked_idea_id  ON projects (linked_idea_id);
