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

## Using real WhatsApp delivery (Twilio)

`brandos/delivery.py` has `TwilioWhatsAppDelivery`, wired up and tested.

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
   (`TWILIO_WHATSAPP_FROM` is Twilio's shared sandbox number, same for
   everyone in sandbox mode; `TWILIO_WHATSAPP_TO` is your own number)
4. Run it and check your phone:
   ```bash
   docker compose run --rm app python -m brandos.run_digest
   ```

Note: Twilio's free sandbox requires re-joining every 72 hours by
texting the join code again. Fine for now; revisit if this becomes
annoying (paid Twilio sender, or Meta's Cloud API directly).

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
