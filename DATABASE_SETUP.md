# Database deployment and operating plan

## Isolation
Use a **new, dedicated Neon PostgreSQL project** for this bot. Never reuse
`mudyar-game-db` or `card-catcher-db`, and never reuse another bot's Render
service. As of 2026-10-24 there is no matchmaking service or PostgreSQL instance
listed in the selected Render workspace. Provisioning is not yet performed.

## Setup checklist
1. Create a dedicated Neon PostgreSQL project, choosing free/low-cost capacity
   after checking current provider limits and confirming account billing.
2. Copy its PostgreSQL connection string from the Neon dashboard into the
   matchmaking Render web service environment as `DATABASE_URL`; do not commit
   secrets or paste credentials into source code.
3. Create a **new** Render web service from this GitHub repository, rather than
   editing any existing game/card bot service.
4. Build: `pip install -r requirements.txt`.
   Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
   Add `BOT_TOKEN`, `DATABASE_URL`, `WEBHOOK_SECRET`, and `PUBLIC_BASE_URL`.
5. On startup, `init_schema()` executes `schema.sql` with CREATE IF NOT EXISTS
   and carefully scoped migrations. Review changes before deploying to an
   existing production database. Verify webhook delivery and registration end to end.
6. Never expose connection strings in log output, chat replies, or repository files.

## Capacity / cost
- PostgreSQL stores tiny rows: user ID, group ID, text, Telegram `file_id`,
  settings, request statuses, compact match cursor IDs. Media bytes remain
  on Telegram and are never saved in PostgreSQL.
- Lazy asyncpg pool (`min_size=0`, `max_size=3`) avoids holding idle
  connections for the whole lifetime of the service.
- Time expiration uses timestamp predicates when the user interacts; no
  frequent cleanup polling and no per-second writes.
- Existing indexes support profile identity, active incoming requests,
  sender/recipient pair cooldowns, and session access.
- Request and browsing histories will eventually need bounded on-demand
  cleanup; do not launch a cron job or delete live data without testing.
- Inspect Neon compute usage, storage, and provider quotas after launch;
  the code does not guarantee a zero-cost month.

## Current status
Schema and database query code are present in GitHub. **No new Neon project,
connection string, Render service, or live database migration has been created
by this task.** Production smoke tests are still outstanding.
