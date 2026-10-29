# Telegram matchmaking bot — 90-day adult-only launch roadmap

**Scope correction, 2026-10-29:** All profiles are one global public profile per user; Group Only mode is abolished. Do **not** add the proposed Block/Report/Privacy growth feature (#8). Full nine-feature research is in [GROWTH_FEATURES_PLAN.md](GROWTH_FEATURES_PLAN.md).
Updated: 2026-10-29 (Myanmar time). This is a planning document, not a guarantee of user growth.

## Positioning and launch boundaries
- Purpose: consent-based, group-rooted **18+** private Telegram introductions. Profiles and interactions are voluntary; never disclose private group invite links or another user's Telegram contact before both sides agree.
- The one-time adult confirmation is a necessary eligibility gate; the separate decorative profile number is **not age verification**. A public launch should have a clear 18+ policy, age eligibility safeguards, and an existing owner support route for serious concerns. This roadmap does not add a new block/report/privacy product feature.
- No mass unsolicited DMs, contact scraping, bots posting to groups without admin approval, fake reviews/fake users, or auto-joining groups.
- **Do not buy Telegram Ads for this dating/matchmaking product.** Telegram's official Ads Guidelines section 5.1 explicitly lists dating services as prohibited. Verify any other marketing channel's own age and advertising policies before use.
- Ask adult-led group administrators for permission before showing promo instructions. Keep private chats/groups private, and ask permission before publicizing examples or testimonials.

## Phase 0 — launch readiness, days 1–7
1. Finish the two-account/two-group live acceptance QA checklist, including cleanup, 3-minute expiry, cold restart and permissions.
2. Publish a short Burmese /help, community rules and a contact method for deletion or serious concerns. Keep the existing 18+ eligibility, consent, contact-disclosure and owner support rules operational before broad invitations; do not add the excluded Block/Report/Privacy feature.
3. Fill the BotFather avatar, About, Description and command list; present /start -> profile -> browse in three steps. State 18+ clearly.
4. Prepare a Group Admin onboarding card: what the bot does, permissions needed, what messages it will send, when it sends them, how to disable it, and how to remove it.
5. Privacy-safe measurement: daily unique opt-in starters, successfully created profiles, successful first views, requests, completed responses, 7-day return usage, error rate. Use aggregate counts, do not export identifiable profiles.
6. Operational runbook: one-click rollback commit, manual Render deploy, startup logs, Neon size, rate limits, and on-call owner notifications.

### Pilot success gates (suggested goals, not observed results)
- 100% of privacy/deletion/eligibility tests pass; 0 unresolved high-severity incidents.
- 10 consecutive cross-group request journeys manually completed on real test accounts without misplaced cards or leaked links.
- User feedback indicates each major private action is discoverable without reading commands.

## Phase 1 — closed adult pilot, days 8–14
- Invite 2–5 **adult-only** Telegram communities, each with admin opt-in. Let admins approve the launch post and quiet hours.
- Aim for ~20–50 consenting adult pilot profiles as an initial experiment, not as a guarantee.
- Invite only people who choose to participate. Admins should not bulk-enroll group members.
- One short Burmese how-it-works post and 20–30 second screen recording showing /start, Reply Keyboard, and consent-based requests without showing real participants' data.
- Collect 3 voluntary feedback answers after the first interaction: ease of use, unclear steps, trust/privacy concerns. Fix repeated friction before expansion.
- Monitor 429 Bot API rate-limit errors, message deletion failures, time-to-first-profile, timeout confusion, and serious support cases daily.

## Phase 2 — discoverability, days 15–30
- Expand only after pilot safety and reliability gates pass. Trial 5–10 additional consenting, adult-moderated groups matched to the product's actual community niche.
- Offer admins a lightweight setup note and a unique tagged start link (only non-sensitive campaign identifiers) to distinguish where opt-in users found the bot.
- Enable optional one-tap **share bot** and **add to group** links, never forcibly repost or tag contacts. Use official start/startgroup links. Do not run referral contests for volume or rank users by invitations.
- Improve the first profile card delivery and helpful empty-state behavior before adding more features.
- Review weekly funnel (opt-in start -> eligibility confirmed -> profile created -> first view -> first request -> response), not raw group membership counts.
- Proposed exploratory target: 100–300 consented adult profiles by day 30, if communities respond positively. If incidents spike, pause and address safety instead.

## Phase 3 — retention and safety-led scale, days 31–60
- Preserve the existing consent, eligibility, and request validation rules. Review request throttling and owner-support responsiveness without introducing the excluded new Block/Report/Privacy feature.
- Allow voluntary quality feedback on reply-keyboard wording; improve false-click prevention and moderation copy.
- Opt-in, low-frequency reminders for requests approaching expiry (not unsolicited bulk broadcasts). Offer an explicit opt-out.
- Create a read-only release changelog, status note and short transparent privacy disclosure.
- Monitor active communities, weekly returning adult participants, response completion, and serious support cases. Do not target minors.

## Phase 4 — scalable operations, days 61–90
- Review PostgreSQL query/index plans and Render free-tier cold starts, deployment success, webhook latency and Telegram API 429s.
- Put a tested database backup/restore plan in place and keep media in Telegram file_id only, as designed.
- Expand to more adult-led groups only when moderation response time and usage quality hold.
- Optional volunteer adult community moderators for participating groups, with clear limits to their access. Admins should never inspect other users' private profile data.
- Do not use illegal data brokerage, mass invitations, scraping, automated spam, or Telegram paid Ads for dating services.

## Practical KPI definitions (small weekly dashboard)
| KPI | Definition | Example healthy direction |
| --- | --- | --- |
| Activation | Completed adult-confirmed profiles / opt-in PV /start users | Rising |
| Time to first view | Time from opted-in /start to first eligible card | Falling |
| Match supply | Eligible, currently present profiles per active group | Sufficient for browsing |
| Request response | Requests answered / requests sent (24h window) | Rising |
| Return usage | Consent-based users opening PV 7 days after signup | Rising |
| Failed group delivery | Failed group card sends / attempted sends | Approaching zero |
| Trust/safety | Serious owner-support cases and resolution time | Addressed promptly |
| Reliability | 429s, application errors, timed-out edits and startup failures | Falling |

Do not publish usernames, Telegram IDs, private group names or raw match data in any growth dashboard.

## Admin outreach copy — optional, send only with consent
"မင်္ဂလာပါ Admin။ Group ထဲမှာ အသက် ၁၈ နှစ်ပြည့်ပြီး ပါဝင်ဖို့ သဘောတူထားသူတွေအတွက် Telegram PV ကနေ Profile လှည့်ကြည့်ပြီး နှစ်ဖက်သဘောတူမှ မိတ်ဆက်ပေးတဲ့ Bot တစ်ခုရှိပါတယ်။ Group မှာ မိတ်ဆက် Post တင်ခွင့်ပြုမလားဆိုတာ အရင်မေးချင်ပါတယ်။ မလိုလားရင် မပို့ပါဘူး။"

## Primary sources checked
- Telegram Bot Features (official deep linking and privacy mode): https://core.telegram.org/bots/features
- Telegram Bot API (official keyboards, bot message/delete behavior): https://core.telegram.org/bots/api
- Telegram Ads Guidelines (dating services prohibited under section 5.1): https://ads.telegram.org/guidelines
- Telegram Spam FAQ (avoid unsolicited promotion): https://telegram.org/faq_spam
- DataReportal Digital 2026 Myanmar (late-2025 connectivity baseline; not Telegram users): https://datareportal.com/reports/digital-2026-myanmar
