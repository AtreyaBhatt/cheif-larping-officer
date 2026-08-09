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
│   ├── migrations/001_create_content_ideas.sql
│   └── smoke_test.sh
├── scripts/
│   └── run_daily_digest.sh  # what host cron calls
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── brandos/
    │   ├── sources/hackernews.py   # fetches HN top stories, no API key needed
    │   ├── digest.py               # LLM abstraction; StubDigestGenerator ships by default
    │   ├── delivery.py             # delivery abstraction; ConsoleDelivery ships by default
    │   ├── db.py                   # Postgres read/write for content_ideas
    │   └── run_digest.py           # entrypoint: fetch -> generate -> store -> deliver
    └── tests/
        └── test_pipeline.py         # offline, mocked — no Docker required to run these
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

3. Run the digest manually to see it work end to end:
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

4. Confirm rows landed in the DB:
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

## Swapping in a real LLM (when ready)

`brandos/digest.py` has a `DigestGenerator` interface and a
`get_generator()` factory function. To add Claude or OpenAI:

1. Add a new class implementing `DigestGenerator.generate()`
2. Point `get_generator()` at it (env-var gated, e.g. `LLM_PROVIDER=claude`)
3. Nothing else in the pipeline changes — `run_digest.py`, `db.py`, and
   `delivery.py` don't know or care which generator is active.

## Swapping in real WhatsApp delivery (when ready)

`brandos/delivery.py` already has `TwilioWhatsAppDelivery` implemented,
just not active by default. To turn it on:

1. Sign up for Twilio, activate the WhatsApp sandbox (free):
   https://www.twilio.com/docs/whatsapp/sandbox
2. Fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_WHATSAPP_FROM`, `TWILIO_WHATSAPP_TO` in `.env`
3. Set `DELIVERY_PROVIDER=twilio` in `.env`
4. Note: Twilio's free sandbox requires re-joining every 72 hours by
   texting the join code from your phone. Fine for now; revisit if this
   becomes annoying (paid Twilio sender, or Meta's Cloud API directly).

## What's NOT built yet (later phases)

- Reply-based logging (marking ideas as posted via WhatsApp reply) —
  this needs a webhook receiver, which is a bigger addition than
  Phase 1's fetch/generate/store/deliver loop. Planned for a Phase 1.5
  or folded into Phase 2 alongside the dashboard.
- Dashboard (Phase 2)
- Weekly review / writing coach / LARP score (Phase 3)

## Before considering Phase 1 done

- [ ] `docker compose run --rm app python -m brandos.run_digest` runs
      cleanly against real HN data and writes rows to Postgres
- [ ] Cron entry installed and confirmed to fire (check `logs/` the
      morning after installing it)
- [ ] You've manually reviewed at least a few days of stub digests —
      the *point* of Phase 1 is proving the loop runs unattended before
      spending money/complexity on a real LLM
