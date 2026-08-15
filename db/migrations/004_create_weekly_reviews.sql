-- 004_create_weekly_reviews.sql
-- Weekly review / writing coach (Phase 3). One row per ISO week,
-- generated on-demand (not on a schedule) and cached — pressing 'w' in
-- the TUI generates it once and re-reads the stored row on every
-- subsequent view/refresh, so re-opening the Posted tab never re-calls
-- the LLM. week_start is always a Monday (ISO week start), used as the
-- natural dedup key: one review per week, ever.

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Monday of the ISO week this review covers. Unique so a given week
    -- can only ever have one stored review (regenerate = separate action,
    -- not modeled yet — delete the row manually if you want a redo).
    week_start   DATE NOT NULL UNIQUE,

    -- LLM-authored coaching note: what got posted, what got neglected,
    -- one concrete suggestion for next week. Free text, not JSON, since
    -- it's meant to be read as prose in the TUI.
    summary      TEXT NOT NULL,

    -- Snapshot of the LarpScore (and raw counts) at generation time, so
    -- the review stays historically accurate even as new ideas/posts
    -- accumulate later and the live score moves on. Stored as JSONB
    -- rather than separate columns since this is a point-in-time
    -- snapshot, not something queried/filtered on.
    stats_json   JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_weekly_reviews_week_start ON weekly_reviews (week_start);
