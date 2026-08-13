-- 002_add_platform_posts.sql
-- Splits the previously-blended `content` field into three distinct
-- pieces: the informational digest summary, and two genuinely
-- copy-pasteable platform posts (LinkedIn and X). Existing rows keep
-- their old `content` as the digest summary (nothing is deleted); the
-- new post columns are backfilled as NULL for old rows since no LLM
-- call generated platform-native copy for them.

ALTER TABLE content_ideas
    ADD COLUMN IF NOT EXISTS digest_summary TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_post   TEXT,
    ADD COLUMN IF NOT EXISTS x_post          TEXT;

-- Backfill: for existing rows, treat the old blended `content` as the
-- digest summary so nothing already generated is lost. New rows going
-- forward will have digest_summary populated directly at insert time,
-- and linkedin_post / x_post populated by the LLM as real platform copy.
UPDATE content_ideas
SET digest_summary = content
WHERE digest_summary IS NULL;

-- `content` itself stays in place (not dropped) for backward
-- compatibility with anything still reading it directly, but new code
-- should read digest_summary / linkedin_post / x_post instead.
