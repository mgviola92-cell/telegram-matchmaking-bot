# လူတောင်းပွဲ Bot — agreed implementation contract

This file records the approved behavior so later batches do not silently change the UX.
Status labels: **agreed** = specification, **implemented** = in source, **pending** = not complete. Never confuse these.

## Product identity
- Telegram Bot API only; works in groups and private chat. No Mini App.
- Natural, witty Burmese matchmaking voice; context-appropriate responses and button labels, never robotic.
- Dynamic response target: **100–300+ genuinely suitable variations per event**. The current `responses.py` has fourteen event families, each with 144 **combinations**, not 144 individually authored lines. This is an expanded but still partial implementation. Anti-repeat is currently in-memory and resets on restart.
- No AI API needed for bot responses.

## Registration
- Group `/register` offers private deep-link registration; membership verified.
- User self-declares 18+ exactly once during profile creation before continuing. No numeric age question, ID verification or repeat request checks. A declaration is not proof of age. An under-18 answer stops registration.
- Display name, no precise age question, exactly one photo or video (max 30 seconds), optional bio. Only Telegram media file_id in database, never media bytes.
- Separate profile per group. Group intro card is voluntary; edits should not duplicate it.
- Missing profile on `/match` must invite registration with a working button, not simply reject.
- Age confirmation is part of registration, not a repeated question at every request.

## Discovery — agreed, mostly pending
- One active `/match` card per viewer per group. Buttons usable by its owner only. Navigation, per-group session storage and Public switch are coded. One-shot asynchronous five-minute inactivity button cleanup is coded, with a one-time restart recovery query; runtime behavior still requires end-to-end testing.
- Prev/Next edit the same card, unseen-first shuffled order, 5-minute inactivity timeout, timer reset on interaction, persisted across restarts.
- Group Only default. Public Browse toggle adds profiles voluntarily made public, including from the current group.
- One public profile per person across all groups; switching public profile demotes the former.
- Pending request from a sender is shown to its recipient with a contextual reply button.

## Requests — agreed, mostly pending
- Sender confirms in source group; recipient gets sender's full profile card in the recipient profile's group, not unsolicited DM.
- Recipient responds privately; accept/reject restricted to recipient.
- Acceptance congratulates both groups (once if same group), then sends mutual Telegram contact links privately.
- Rejection may include optional reason, only published with recipient's consent. Recipient-authorized optional reason entry, preview and share confirmation are coded; runtime E2E test pending.
- Pending expires after 24h. Reject cooldown 12h; accept cooldown 24h. Decision-time cooldown queries are now coded, but integration tests pending. Unlimited distinct recipients; no duplicate active request to same recipient.
- Unified private incoming inbox newest first; outgoing list and withdraw with confirmation. Atomic/idempotent transitions.

## Profile and group management — agreed, pending
- `/profile` selects among group profiles; picker, public selection, display name/bio/media edits and confirmed deletion are coded, with runtime user testing still pending. Private inline text pages edit the existing message; media pages first remove the prior picker and avoid creating a duplicate when Telegram refuses deletion.
- Delete removes profile and pending requests, disables old buttons where feasible, informs affected requesters privately; no group announcement; reset cooldown. Database deletion and sender notifications are coded; stale browse-session deletion and best-effort old-button disable are implemented; Telegram may disallow editing older messages.
- Leaving group archives profile; rejoining restores. Telegram chat-member update handler and webhook subscription are coded (requires Telegram delivery and adequate group permissions).
- Per-group admin `/settings`: matchmaking, registration, requests, public browse, intros, cleanup toggles. No group-link settings. Toggle UI/storage is implemented; enforcement of registration, matchmaking, and outgoing requests is implemented. Public browse, intros and cleanup enforcement are pending.

## Infrastructure
- On-demand SQL, no high-frequency polling, lazy small PostgreSQL pool, proper indexes and durable state for sessions.
- Current FastAPI Telegram webhook requires BOT_TOKEN, DATABASE_URL, WEBHOOK_SECRET, PUBLIC_BASE_URL. Health endpoint does not prove full feature readiness.
- Do not touch unrelated services or repos.
- Never mark unimplemented or untested features as completed.

## Current verified implementation snapshot
- Registration and self-declaration: partial, in-memory conversation draft.
- One-card match browse and request delivery: basic prototype, **not** full navigation. Private reply, accept/reject, inbox, outgoing, and confirmed withdrawal handlers are now present, but runtime integration remains unverified.
- Dynamic responses: fourteen families (144 combinations each) are coded; handlers for saved/updated/deleted profiles, accepted/rejected/withdrawn requests, intro publish, active browse session and other core events use them. Remaining edge-case validation/error messages are fixed copy.
- PostgreSQL schema (including durable browse sessions), small lazy pool, webhook: present. See `DATABASE_SETUP.md`; a dedicated Neon project and five tables have been created; the matchmaking Render service is connected and latest deployments have been live, but real user E2E verification is pending.
- Offline source/response regression tests and Docker build gates are present. Some Render builds have passed and deployed live; no complete Telegram end-to-end acceptance test has been confirmed.
