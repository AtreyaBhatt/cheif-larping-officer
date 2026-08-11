"""
Phase 1 pipeline entrypoint: fetch -> generate -> store -> deliver.

Run manually with:  python -m brandos.run_digest
Called daily by host cron via scripts/run_daily_digest.sh (see README).

Delivery defaults to console/log output (see brandos/delivery.py) — the
primary way to review and act on generated ideas is the TUI
(python -m brandos.tui), which reads directly from the same
content_ideas table this script writes to.
"""
from __future__ import annotations

import logging
import sys

from brandos import db
from brandos.delivery import format_digest, get_delivery_provider
from brandos.digest import get_generator
from brandos.sources.hackernews import fetch_top_stories

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run(article_limit: int = 15, dry_run: bool = False) -> None:
    logger.info("=== Starting daily digest run (dry_run=%s) ===", dry_run)

    logger.info("Step 1/4: fetching articles")
    articles = fetch_top_stories(limit=article_limit)
    if not articles:
        logger.warning("No articles fetched — aborting run, nothing to generate.")
        return

    logger.info("Step 2/4: generating content ideas")
    generator = get_generator()
    ideas = generator.generate(articles)
    if not ideas:
        logger.warning("Generator produced no ideas — aborting run.")
        return

    if dry_run:
        logger.info("Dry run: skipping DB writes and delivery.")
        print(format_digest(ideas))
        return

    logger.info("Step 3/4: writing %d ideas to database", len(ideas))
    idea_ids = db.insert_content_ideas(ideas)
    logger.info("Wrote ids: %s", idea_ids)

    logger.info("Step 4/4: delivering digest")
    digest_text = format_digest(ideas)
    get_delivery_provider().deliver(digest_text)

    logger.info("=== Run complete: %d ideas generated and delivered ===", len(ideas))


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    try:
        run(dry_run=dry_run)
    except Exception:
        logger.exception("Digest run failed")
        sys.exit(1)
