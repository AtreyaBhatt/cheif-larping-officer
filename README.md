# Personal Brand OS — Phase 0

Foundations only: Docker stack boots, one table exists, scheduler fires
unattended. No AI, no WhatsApp, no dashboard yet.

## What's here

```
personal-brand-os/
├── docker-compose.yml       # db + scheduler services
├── .env.example             # copy to .env and fill in
├── db/
│   ├── migrations/
│   │   └── 001_create_content_ideas.sql
│   └── smoke_test.sh        # end-to-end Phase 0 verification
└── scheduler/
    ├── Dockerfile
    ├── package.json
    └── index.js              # fires every minute, logs to prove it
```

## Setup (on your VPS)

1. Copy the example env file and edit the values — at minimum change
   `POSTGRES_PASSWORD` to something real:
   ```bash
   cp .env.example .env
   ```

2. Bring the stack up:
   ```bash
   docker compose up -d
   ```

3. Confirm both containers are healthy:
   ```bash
   docker compose ps
   ```
   `db` should show `healthy`, `scheduler` should show `running`.

4. Check the scheduler is actually firing:
   ```bash
   docker compose logs -f scheduler
   ```
   You should see a `scheduler fired` line immediately, then one every
   minute after. This is the Phase 0 verification cadence — see the note
   in `scheduler/index.js` about switching to the daily 7am schedule once
   you're satisfied it works.

## Run the full smoke test

This applies the migration, inserts a row, reads it back, restarts the
whole stack, and confirms the row survived — the actual exit criteria
for Phase 0:

```bash
./db/smoke_test.sh
```

Expect to see `PASS: row persisted across restart` at the end. If it
fails, the volume isn't persisting — check that `pgdata` is a named
volume in `docker-compose.yml` and that you didn't accidentally run
`docker compose down -v` (the `-v` flag deletes volumes).

## Manual DB access (for poking around)

```bash
docker compose exec db psql -U brandos -d brandos
```

(or whatever values you set for `POSTGRES_USER` / `POSTGRES_DB` in `.env`)

Useful queries once you're in:
```sql
\d content_ideas          -- describe the table
SELECT * FROM content_ideas ORDER BY created_at DESC LIMIT 5;
```

## Before moving to Phase 1

- [ ] `docker compose up -d` brings up a healthy stack with one command
- [ ] `./db/smoke_test.sh` passes
- [ ] Scheduler has run unattended for at least a few hours without crashing
      (`docker compose logs scheduler | tail -50` — should be a clean
      stream of `scheduler fired` lines, no errors/restarts)
- [ ] Switch `scheduler/index.js` from the every-minute schedule to the
      daily one (`0 7 * * *`), rebuild (`docker compose up -d --build`),
      and confirm it still fires

Once all four are true, Phase 0 is done. Phase 1 replaces the body of
`job()` in `scheduler/index.js` with real news fetching, an LLM call,
and WhatsApp delivery — the scaffold stays the same.
