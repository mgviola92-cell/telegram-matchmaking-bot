# Database deployment and operating plan

## Isolation
Use a **new, dedicated Neon PostgreSQL project** for this bot. Never reuse
`mudyar-game-db` or `card-catcher-db`, and never reuse another bot's Render
service. As of 2026-10-24 the user has created a Render **project** (which is not itself a web service). The Render connector lists no matchmaking web service; its service creation action has no project association field.

## Setup checklist
1. **DONE:** Created dedicated Neon project `matchmaking-bot-db`, project ID `young-smoke-26864930`, database `matchmaking_bot`. Applied the current schema using a transaction; confirmed four tables: `profiles`, `requests`, `group_settings`, `browse_sessions`.
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
**Dedicated Neon database created and schema verified** on 2026-10-24. No DATABASE_URL has yet been set in a matchmaking Render service; the user's Render project exists, but the service is not listed by the connector. Do not create a service outside that project accidentally. Production smoke tests are outstanding.
