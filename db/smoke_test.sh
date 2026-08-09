#!/usr/bin/env bash
# Phase 0 smoke test: insert a row, read it back, restart the stack,
# confirm the row survived. Run this from the project root:
#   ./db/smoke_test.sh
set -euo pipefail

source .env

echo "== 1. Applying migration =="
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -f /migrations/001_create_content_ideas.sql

echo "== 2. Inserting a test row =="
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
INSERT INTO content_ideas (headline, content, source_articles, category, estimated_quality, reasoning, status, platform, notes)
VALUES (
    'Phase 0 smoke test',
    'This row exists to prove the DB round-trips and persists.',
    '[{\"title\": \"example source\", \"url\": \"https://example.com\"}]'::jsonb,
    'meta',
    9.5,
    'Manual smoke test insert from db/smoke_test.sh',
    'GENERATED',
    NULL,
    'safe to delete'
);
"

echo "== 3. Reading it back =="
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT id, created_at, headline, category, estimated_quality, status
FROM content_ideas
WHERE headline = 'Phase 0 smoke test';
"

echo "== 4. Restarting the stack to test persistence =="
docker compose down
docker compose up -d
echo "Waiting for db healthcheck..."
until docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
    sleep 1
done

echo "== 5. Confirming the row survived the restart =="
ROW_COUNT=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
SELECT count(*) FROM content_ideas WHERE headline = 'Phase 0 smoke test';
")

if [ "$ROW_COUNT" -ge 1 ]; then
    echo "PASS: row persisted across restart (found $ROW_COUNT match)."
else
    echo "FAIL: row did not survive restart. Check the pgdata volume."
    exit 1
fi
