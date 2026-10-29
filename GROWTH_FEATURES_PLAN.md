# လူတောင်းပွဲ Bot — Organic Growth Feature Research & Integration Plan
Updated: 2026-10-29 (Asia/Yangon)
Status: **RESEARCH / IMPLEMENTATION PROPOSAL ONLY. No runtime features are activated by this document.**

## Non-negotiable project constraints
- One Telegram user = one global, public profile across all eligible bot groups. **No Group Only profile system, no public-mode selector, no per-group duplicate profiles.**
- Existing PV-centric ReplyKeyboard matching, request confirmation, source/destination group provenance, 24-hour pending expiry, 12-hour rejection cooldown, 24-hour acceptance cooldown, and 3-minute browse inactivity window stay intact.
- A profile can only be created through an eligible group; existing eligibility and current group membership checks remain as specified.
- Telegram-native group/PV flows only; **no Mini App**.
- Profile media bytes are never copied to Neon or Render storage. Reuse Telegram `media_file_id`, textual metadata and small counters only.
- Do not add the previously proposed "**Block, Report & Privacy**" as **growth feature #8**. Keep established eligibility, recipient-consent and contact-disclosure rules unchanged; this proposal does not remove them.
- User-facing text and reply/inline button labels: natural, playful Burmese; avoid robotic terminology. Do not reintroduce a group-wide ReplyKeyboard.
- Render auto-deploy stays OFF; implementation/test batches only after planned review. Real two-user/two-group live E2E remains outstanding.

## Research verdict and constraints (official sources)
- Telegram's deep linking includes `?startgroup=...` for user-triggered group bot additions; no unsolicited auto-joins. https://core.telegram.org/api/links
- Telegram share URLs prefill a URL/text in a selected chat; **they do not automatically send a Telegram photo/video card**. For a shareable *profile*, use an opaque bot `?start=...` link and render the card in the recipient's bot PV after checks. https://core.telegram.org/widgets/share
- Inline Mode is possible without Mini Apps but must be enabled in BotFather, and forwarding inline profile media has implementation and privacy constraints; not prerequisite for initial launch. https://core.telegram.org/bots/inline
- Bot API 10.3 (2026-08-24) offers recipient-targeted ephemeral group messages, but the app currently declares `python-telegram-bot>=22,<23`; stable v22.8 documentation does not expose the new `ephemeral_message_parameters` in `send_message`. **Treat as compatibility spike / opt-in experiment**, not as an already-built capability. https://core.telegram.org/bots/api-changelog ; https://docs.python-telegram-bot.org/en/stable/telegram.bot.html
- Telegram prohibits unsolicited bots starting private chats: private notifications require prior user start/permission. https://core.telegram.org/bots
- Telegram's bots FAQ notes approximately 20 group messages/minute and 30 messages/second for broadcasts; avoid per-click group messages. https://core.telegram.org/bots/faq
- Hinge's published product research supports prompts and thoughtful conversation starters as ideas worth experimenting with; those numbers are not guaranteed to transfer to this Myanmar Telegram audience. https://hinge.co/newsroom/convo-starters ; https://hinge.co/newsroom/prompt-feedback
- Telegram Ads policies prohibit the promotion of dating services, so don't rely on buying Telegram Ads. https://ads.telegram.org/guidelines

## Feature plan (nine items, numbering corrected)

| No. | Feature | Detailed behavior | DB/traffic impact | Priority |
| --- | --- | --- | --- | --- |
| 1 | Organic group invitation | Only user taps `🌷 Group ကို ဖိတ်မယ်`; resolve bot username dynamically; use `startgroup` deep link; an admin-controlled one-time onboarding message explains PV and group permissions | No new media, optional short campaign tag | P1 |
| 2 | Daily icebreaker questions | Admin-enabled, **manual/on-demand** initial release: one brief playful question in eligible group, once/day throttle; no unsolicited per-member DM or repeating media | Group/day small marker only, no cron | P2 |
| 3 | Interest tags + profile prompts | Optional 0–5 approved interest slugs and one short prompt answer; store on the **one global** profile; old profiles remain valid; no AI API calls | Small text columns only | P1 |
| 4 | Post-match icebreakers | After both sides consent/accept, show optional questions in their existing private notice/menus; never expose pre-accept account link | Static templates, no tables | P2 |
| 5 | Smart notifications | Existing request/response notifications first; optional low-frequency reminder with explicit opt-in and opt-out, only after user starts PV; don't flood group/DM | Tiny preferences + event marker | P3 |
| 6 | Weekly group meet-and-greet | Admin triggers a voluntary weekly event; share eligible global profile *links*, never invent additional group profiles or override existing browse and acceptance rules | One group/event row; no binary media; no always-on job | P2 |
| 7 | Shareable global introduction card | From `/profile`, user selects `📣 Profile လေး မိတ်ဆက်မယ်`; `t.me/share/url` opens chosen chat with a link to the bot PV `?start=p_<opaque-token>`; bot checks public eligibility before rendering a compact profile card using its Telegram `file_id`. No Group Only restriction. No raw Telegram ID in URL. | Short opaque token or HMAC; no re-upload | P1 |
| 8 | Private group interaction (ephemeral) | Experimental “how to start” ephemeral reply only for button presser; no private profile/media leaks in group; fallback direct PV deep link until library/API validation succeeds | Zero/low DB; API compatibility QA | P3 |
| 9 | Owner growth dashboard | Owner PV can view aggregated daily starters, completed profiles, first browse, sent/answered requests, eligible group count and 7-day returns. Never show raw Telegram IDs or private group names. | Small aggregated counters/day; no extra media | P1 |

## Concrete entry points in current repository
- `pv_profile.py`: current `SHARE` still sends only toward the profile registration/home group, gated by `group_settings.intros` and membership. Add **separate** global link-share flow instead of silently altering existing intro posting.
- `pv_matching.py`: PV main menu, eligibility checks and global browsing cursor. Do not put a new group-only browse mode back here.
- `handlers.py`: existing /register/group settings/intro callbacks. Add admin onboarding and optional event entry points here without adding a ReplyKeyboard to group chat.
- `repository.py` and `schema.sql`: add optional interests/prompt fields on unique global `profiles.user_id`; migrate idempotently; do not create `profiles_by_group`.
- `pv_owner.py`: owner-only aggregated growth dashboard read path.
- `notices.py` and `responses.py`: style for any newly introduced messages; preserve no-repeat choices where sensible.
- `tests/`: ensure global compatibility, no involuntary messages, no account contact disclosure before acceptance, no image/video binaries, cheap idempotent writes, and no regression in request cooling/cleanup.

## Priority implementation batches
1. **Before feature changes**: run current pytest, check main commit/deploy separation and complete consented adult-only real Telegram two-user/two-group QA. Do not claim live success based on mocked tests.
2. **Batch A (P1):** create optional profile interests/prompt, stable global share deep link, optional group invite link, owner privacy-safe metrics. Add regression tests; do not deploy automatically.
3. **Batch B (P2):** admin-triggered group question/event, and 3–5 optional post-match starter lines. Group event settings default **OFF**; no background poller.
4. **Batch C (P3):** opt-in reminders and ephemeral API compatibility experiment with fallback; no dependency on 2026 ephemeral support for normal matching.
5. **Pilot and measurement:** after E2E gates, coordinate with 2–5 explicitly consenting adult-led groups; compare opt-in start → profile → first view → first request → answered requests and 7-day return rate. Stop expansion if reliability/eligibility fails.

## Suggested test checklist for all batches
- A globally public profile created from Group A is not duplicated when viewed from Group B.
- Share URL includes **no raw user ID, no group invite, no phone number**; voluntarily shared global profile does not disclose pre-accept contact links.
- Deleted or ineligible users' old links stop resolving; profile edits update the card loaded from the canonical profile.
- Telegram Bot cannot DM a user who has never opened PV, so no assumption that every member receives reminders.
- A group invite click must allow selecting a group; no auto-join or mass posting.
- Test temporary loss of bot permissions, idle Render restart, expired cursors, and Telegram 429 retry_after.
- Measure optional growth events without per-view DB writes.
- No feature in this document is claimed deployed, production-tested or already enabled.

## Deliberately excluded
- Group Only profiles or a Public toggle.
- New Block/Report/Privacy feature #8.
- Auto-DM or mass mentions/invite spam, forced forwarding, scraped memberships, fake profiles, referral contests, paid Telegram Ads for dating.
- Mini Apps, media binary storage, heavy periodic DB polling, AI content generation APIs.
