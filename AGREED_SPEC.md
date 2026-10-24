# လူတောင်းပွဲ Bot — agreed implementation contract

This file records the approved behavior so later batches do not silently change the UX.
Status labels: **agreed** = specification, **implemented** = in source, **pending** = not complete. Never confuse these.

## Product identity
- Telegram Bot API only; works in groups and private chat. No Mini App.
- Natural, witty Burmese matchmaking voice; context-appropriate responses and button labels, never robotic.
- Dynamic response target: **100–300+ genuinely suitable variations per event**. The current `responses.py` has four event families, each with 144 **combinations**, not 144 individually authored lines. This is a partial implementation. Anti-repeat is currently in-memory and resets on restart.
- No AI API needed for bot responses.

## Registration
- Group `/register` offers private deep-link registration; membership verified.
- User self-declares 18+ before continuing. A declaration is not proof of age. An under-18 answer stops registration.
- Display name, age, exactly one photo or video (max 30 seconds), optional bio. Only Telegram media file_id in database, never media bytes.
- Separate profile per group. Group intro card is voluntary; edits should not duplicate it.
- Missing profile on `/match` must invite registration with a working button, not simply reject.
- Age confirmation is part of registration, not a repeated question at every request.

## Discovery — agreed, mostly pending
- One active `/match` card per viewer per group. Buttons usable by its owner only.
- Prev/Next edit the same card, unseen-first shuffled order, 5-minute inactivity timeout, timer reset on interaction, persisted across restarts.
- Group Only default. Public Browse toggle adds profiles voluntarily made public, including from the current group.
- One public profile per person across all groups; switching public profile demotes the former.
- Pending request from a sender is shown to its recipient with a contextual reply button.

## Requests — agreed, mostly pending
- Sender confirms in source group; recipient gets sender's full profile card in the recipient profile's group, not unsolicited DM.
- Recipient responds privately; accept/reject restricted to recipient.
- Acceptance congratulates both groups (once if same group), then sends mutual Telegram contact links privately.
- Rejection may include optional reason, only published with recipient's consent.
- Pending expires after 24h. Reject cooldown 12h; accept cooldown 24h. Unlimited distinct recipients; no duplicate active request to same recipient.
- Unified private incoming inbox newest first; outgoing list and withdraw with confirmation. Atomic/idempotent transitions.

## Profile and group management — agreed, pending
- `/profile` selects among group profiles; edit, delete, and public selection.
- Delete removes profile and pending requests, disables old buttons where feasible, informs affected requesters privately; no group announcement; reset cooldown.
- Leaving group archives profile; rejoining restores.
- Per-group admin `/settings`: matchmaking, registration, requests, public browse, intros, cleanup toggles. No group-link settings.

## Infrastructure
- On-demand SQL, no high-frequency polling, lazy small PostgreSQL pool, proper indexes and durable state for sessions.
- Current FastAPI Telegram webhook requires BOT_TOKEN, DATABASE_URL, WEBHOOK_SECRET, PUBLIC_BASE_URL. Health endpoint does not prove full feature readiness.
- Do not touch unrelated services or repos.
- Never mark unimplemented or untested features as completed.

## Current verified implementation snapshot
- Registration and self-declaration: partial, in-memory conversation draft.
- One-card match browse and request delivery: basic prototype, **not** full navigation. Private reply, accept/reject, inbox, outgoing, and confirmed withdrawal handlers are now present, but runtime integration remains unverified.
- Dynamic responses: four families connected; all other bot copy pending.
- PostgreSQL schema, small lazy pool, webhook: present.
- Offline source/response regression tests were added, but have **not been executed**. Runtime integration tests and Render deployment: **not yet verified**.
