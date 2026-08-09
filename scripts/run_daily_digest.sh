#!/usr/bin/env bash
# Called by host cron once a day. Runs the app container as a one-shot
# job (not a daemon) and logs output, so you have a record of every run
# even without docker compose logs (which would otherwise rotate/vanish
# for a container that immediately exits).
#
# Install with:
#   crontab -e
# then add:
#   0 7 * * * /opt/cheif-larping-officer/scripts/run_daily_digest.sh
#
# (adjust the path to wherever this repo actually lives on your VPS)
set -euo pipefail

cd "$(dirname "$0")/.."  # project root, regardless of where cron invokes from

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/digest_$(date +%Y-%m-%d_%H-%M-%S).log"

echo "=== Digest run started at $(date -Iseconds) ===" | tee -a "$LOG_FILE"

docker compose run --rm app python -m brandos.run_digest 2>&1 | tee -a "$LOG_FILE"

echo "=== Digest run finished at $(date -Iseconds) ===" | tee -a "$LOG_FILE"
