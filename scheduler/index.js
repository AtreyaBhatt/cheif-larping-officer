const cron = require('node-cron');
const fs = require('fs');
const path = require('path');

const LOG_DIR = '/var/log/brandos';
const LOG_FILE = path.join(LOG_DIR, 'scheduler.log');

// --- Phase 0 verification schedule ---
// Fires every minute so you can confirm it works within seconds of
// `docker compose up`, instead of waiting until tomorrow morning.
// Once confirmed, switch to the daily schedule below and redeploy.
const PHASE_0_SCHEDULE = '* * * * *';

// --- Real schedule, for Phase 1 onward ---
// 7:00 AM every day. Uncomment and use this once Phase 0 is verified.
// const DAILY_SCHEDULE = '0 7 * * *';

const SCHEDULE = PHASE_0_SCHEDULE;

function ensureLogDir() {
    if (!fs.existsSync(LOG_DIR)) {
        fs.mkdirSync(LOG_DIR, { recursive: true });
    }
}

function job() {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] scheduler fired\n`;
    fs.appendFileSync(LOG_FILE, line);
    console.log(line.trim());

    // Phase 1+ will replace this body with:
    //   1. fetch news sources
    //   2. call LLM to rank + summarize
    //   3. write content_ideas rows to Postgres
    //   4. send digest via WhatsApp
}

ensureLogDir();
console.log(`Scheduler starting. Cron expression: "${SCHEDULE}"`);
console.log(`Logging to ${LOG_FILE}`);

cron.schedule(SCHEDULE, job);

// Run once immediately on boot too, so you don't have to wait
// even the first minute to see proof of life in the logs.
job();
