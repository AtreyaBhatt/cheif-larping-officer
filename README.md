# Personal Brand OS — Phase 1

The real daily loop: fetch Hacker News → generate content ideas (stubbed
LLM for now) → store in Postgres → deliver a digest (console by default,
Twilio WhatsApp optional).

## What changed from Phase 0

- The always-on JS scheduler container is **gone**. Triggering a
  container from inside another container (via the Docker socket) is
  more complexity and attack surface than a solo daily job needs.
  Replaced with **host cron** calling a one-shot `docker compose run`.
- New `app/` service: Python, does the actual work.
- `db/` and its migration are unchanged from Phase 0.

## Project layout

```
personal-brand-os/
├── docker-compose.yml       # db + app (app has no `restart`, runs on demand)
├── .env.example
├── db/
│   ├── migrations/
│   │   ├── 001_create_content_ideas.sql
│   │   ├── 002_add_platform_posts.sql   # splits content -> digest_summary/linkedin_post/x_post
│   │   └── 003_create_projects.sql      # new projects table
│   └── smoke_test.sh
├── scripts/
│   └── run_daily_digest.sh  # what host cron calls
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── brandos/
    │   ├── sources/hackernews.py   # fetches HN top stories, no API key needed
    │   ├── digest.py               # daily digest LLM abstraction; stub + OpenRouter generators
    │   ├── openrouter_client.py    # shared OpenRouter call/parse logic (used by digest.py's
    │   │                           # newer code paths and project_suggester.py)
    │   ├── project_suggester.py    # on-demand (not cron) LLM project suggestions
    │   ├── delivery.py             # delivery abstraction; console default, Twilio optional
    │   ├── db.py                   # Postgres read/write for content_ideas AND projects
    │   ├── run_digest.py           # entrypoint: fetch -> generate -> store -> deliver
    │   └── tui/
    │       ├── __main__.py         # enables `python -m brandos.tui`
    │       ├── app.py              # tabbed Textual app: Digest/Posts/Projects/Posted
    │       ├── views.py            # IdeaBrowser, PostBrowser, ProjectBrowser widgets
    │       ├── add_project_modal.py # manual "new project" form (ModalScreen)
    │       ├── larp_score.py       # LARP score calculation, pure logic, no Textual
    │       └── larp_panel.py       # LARP score display widget
    └── tests/
        ├── test_pipeline.py          # offline, mocked — no Docker required to run these
        ├── test_tui.py               # headless Textual Pilot tests for the TUI
        ├── test_larp_score.py        # LARP score calculation unit tests
        └── test_project_suggester.py # on-demand project suggestion unit tests
```

## Setup

1. `.env` should already exist from Phase 0. Add the new variables from
   `.env.example` if you don't have them (delivery provider, and
   commented-out Twilio/LLM vars for later).

2. Bring up the DB (unchanged from Phase 0):
   ```bash
   docker compose up -d db
   ./db/smoke_test.sh   # optional, confirms Phase 0 still holds
   ```

3. **If upgrading from an earlier version of this repo**, apply the new
   migration that splits the old blended `content` field into
   `digest_summary` / `linkedin_post` / `x_post`:
   ```bash
   docker compose exec db psql -U larpmax -d larpmax -f /migrations/002_add_platform_posts.sql
   ```
   (swap `larpmax` for whatever `POSTGRES_USER`/`POSTGRES_DB` you're
   using). This is additive — old rows keep their data, `content` isn't
   dropped, `digest_summary` is backfilled from it automatically.

4. Also apply the projects table migration (new — adds the `projects`
   table backing the Projects tab):
   ```bash
   docker compose exec db psql -U larpmax -d larpmax -f /migrations/003_create_projects.sql
   ```

5. Run the digest manually to see it work end to end:
   ```bash
   docker compose run --rm app python -m brandos.run_digest
   ```
   This fetches real HN stories, runs them through the stub generator,
   writes rows to `content_ideas`, and prints the digest to the console
   (since `DELIVERY_PROVIDER=console` by default).

   Add `--dry-run` to skip the DB write and delivery — useful for
   testing the fetch/generate steps in isolation:
   ```bash
   docker compose run --rm app python -m brandos.run_digest --dry-run
   ```

6. Confirm rows landed in the DB:
   ```bash
   docker compose exec db psql -U brandos -d brandos -c \
     "SELECT headline, category, status, created_at FROM content_ideas ORDER BY created_at DESC LIMIT 5;"
   ```

## Running the offline test suite

No Docker needed for this — pure Python, all I/O mocked:
```bash
cd app
pip install -r requirements.txt pytest
PYTHONPATH=. python -m pytest tests/ -v
```

## Wiring up daily cron

```bash
chmod +x scripts/run_daily_digest.sh
crontab -e
```
Add a line (adjust the path to wherever this repo lives on your VPS):
```
0 7 * * * /opt/cheif-larping-officer/scripts/run_daily_digest.sh
```

Each run's output is logged to `logs/digest_<timestamp>.log` in the
project root (gitignored) so you have a record even though the `app`
container exits immediately after each run rather than staying up.

## Using a real LLM (OpenRouter)

`brandos/digest.py` now includes `OpenRouterDigestGenerator`, wired up
and tested. It pre-filters articles by HN score first (same as the stub),
then sends only the survivors to the LLM to write real headlines,
summaries, categories, quality scores, and LinkedIn/X angles — one API
call per digest run, not per article.

To turn it on:

1. Get an API key at https://openrouter.ai/keys
2. In `.env`, set:
   ```
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-...
   ```
3. Optional — override the model (defaults to the free Nemotron 3 Ultra
   tier if unset):
   ```
   OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
   ```
4. Run it:
   ```bash
   docker compose run --rm app python -m brandos.run_digest --dry-run
   ```
   Check the output actually reads like real content ideas (not
   `[STUB]` placeholders) before removing `--dry-run` and letting it
   write to the DB.

Swapping to a different provider later (Claude direct, OpenAI direct,
a different OpenRouter model) means adding a new class implementing
`DigestGenerator.generate()` and pointing `get_generator()` at it via
`LLM_PROVIDER` — nothing else in the pipeline changes.

## Reviewing ideas with the TUI

Push-based delivery (WhatsApp/Twilio) turned out to be more hassle than
it's worth for a solo project — sandbox rejoin timers, Meta business
verification, all overhead for "read a digest once a day." Instead,
`brandos/tui/` is a terminal UI (built with
[Textual](https://textual.textualize.io/)) that reads directly from
`content_ideas` — same table `run_digest.py` writes to, no delivery
layer in between.

Run it:
```bash
docker compose run --rm app python -m brandos.tui
```

### Tabs

- **Digest** — today's freshly generated batch (`status = GENERATED`),
  showing the informational summary (what happened, why it matters).
  Not meant to be posted as-is — this is for your own morning reading.
- **Posts** — the same generated ideas, but showing the actual
  **copy-pasteable** LinkedIn and X post text the LLM wrote — ready to
  select and paste directly into the platform, no editing needed.
  Filterable by platform (All / LinkedIn / X) with the `p` key, same as
  the Posted tab. X posts that need more room show as a numbered thread
  (Tweet 1/3, 2/3, etc.) rather than one oversized block.
- **Projects** — durable, user-curated projects that demonstrate real
  technologies covered in the Digest. Two ways in: press `n` on this
  tab to add one manually (title, description, category, optional
  GitHub/demo links), or select an idea in Digest/Posts and press `g`
  to ask the LLM to suggest a project demonstrating that specific
  technology — it's saved automatically, linked back to the idea that
  inspired it. Press `c` to cycle a project's status (IDEA → BUILDING →
  DONE). The LLM suggestion is on-demand only — it never runs as part
  of the daily cron, so it adds zero cost unless you explicitly ask for it.
- **Posted** — everything marked posted, filterable by platform (All /
  LinkedIn / X), plus the **LARP Score** panel at the top — a synthetic
  metric (not a real influence measure) combining posting consistency
  (streaks), execution rate (posted ÷ generated), and category
  diversity. See `brandos/tui/larp_score.py` for the full calculation.

### Controls

- `1` / `2` / `3` / `4` — switch to Digest / Posts / Projects / Posted
- `j`/`k` or arrow keys — move through the active tab's list
- `p` — cycle platform filter (Posts or Posted tab: All → LinkedIn → X)
- `l` — mark selected idea posted to LinkedIn (Digest/Posts/Posted)
- `x` — mark selected idea posted to X (Digest/Posts/Posted)
- `b` — mark selected idea posted to both (Digest/Posts/Posted)
- `s` — skip (Digest/Posts/Posted)
- `a` — archive (Digest/Posts/Posted)
- `n` — new project (Projects tab: opens an add form)
- `g` — ask the LLM to suggest a project from the selected Digest/Posts idea
- `c` — cycle a project's status (Projects tab: IDEA → BUILDING → DONE)
- `r` — refresh all tabs from DB
- `q` — quit

Marking an idea from either the Digest or Posts tab calls
`db.update_status()` immediately and reloads all tabs, so the Posted
tab and LARP Score reflect the change right away.

This becomes your daily loop: run cron in the morning to populate the
DB, open the Posts tab, copy whichever LinkedIn/X text you like
directly into the platform, then mark it posted — no reformatting, no
re-writing, no re-reading the digest to figure out what to say. When
something in the Digest inspires an actual project idea, press `g` on
it right there instead of losing the thought.

## Optional: WhatsApp delivery (Twilio)

Not the primary interface anymore (see TUI above), but still built and
tested in `brandos/delivery.py` if you want push notifications on top
of the TUI later — e.g. a ping that ideas are ready, even if you still
log decisions in the TUI.

To turn it on:

1. Sign up for Twilio, activate the WhatsApp sandbox (free):
   https://www.twilio.com/docs/whatsapp/sandbox
2. From your phone, send the sandbox's join code to their WhatsApp
   number to opt your own number in (required by Twilio, not this app)
3. In `.env`, set:
   ```
   DELIVERY_PROVIDER=twilio
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   TWILIO_WHATSAPP_TO=whatsapp:+91XXXXXXXXXX
   ```
4. Run it and check your phone:
   ```bash
   docker compose run --rm app python -m brandos.run_digest
   ```

Note: Twilio's free sandbox requires re-joining every 72 hours by
texting the join code again — one of the reasons the TUI became the
primary path instead.

## What's NOT built yet (later phases)

- Dashboard (Phase 2) — the TUI covers this need for now
- Weekly review / writing coach (Phase 3) — LARP Score already exists
  in the Posted tab, but the weekly-digest-style review isn't built
- Editing an existing project's fields (title/description/links) after
  creation — `db.update_project()` exists but isn't wired into the TUI
  yet, only status cycling (`c`) is
- Deleting a project from the TUI — `db.delete_project()` exists but
  has no key binding yet

## Before considering Phase 1 done

- [ ] `docker compose run --rm app python -m brandos.run_digest` runs
      cleanly against real HN data and writes rows to Postgres
- [ ] Cron entry installed and confirmed to fire (check `logs/` the
      morning after installing it)
- [ ] `docker compose run --rm app python -m brandos.tui` opens
      cleanly, shows generated ideas in the Digest tab, and marking one
      as posted/skipped actually persists (confirm with a `psql` query
      afterward)
- [ ] Posts tab shows real, copy-pasteable LinkedIn and X text (not
      `[STUB]` placeholders, once `LLM_PROVIDER=openrouter` is set) —
      try actually copying one into LinkedIn/X to confirm it needs no
      editing
- [ ] Post a few ideas to different platforms and check the Posted tab
      — platform filter (`p` key) should correctly show/hide LinkedIn vs
      X posts, and the LARP Score panel should update with real numbers
- [ ] On the Projects tab, press `n` and manually create a project —
      confirm it persists after a refresh (`r`)
- [ ] From the Digest tab, select a real idea and press `g` — confirm
      an LLM-suggested project appears in the Projects tab, linked back
      to that idea ("Demonstrates: ...")
- [ ] Cycle a project's status with `c` a few times and confirm it
      actually moves IDEA → BUILDING → DONE → IDEA
- [ ] You've manually reviewed at least a few days of real digests —
      the *point* of Phase 1 is proving the loop runs unattended before
      spending money/complexity on a real LLM
