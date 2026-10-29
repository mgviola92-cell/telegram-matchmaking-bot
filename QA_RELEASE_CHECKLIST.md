# Release QA checklist — group-based Telegram matchmaking bot
Updated: 2026-10-29. Owner of testing must use **consenting adult test users** only.
This document separates automated simulation from tests that require real Telegram
accounts and real group memberships. It never claims a live group journey ran
without evidence.

## Release hardening implemented in code
- [x] Global profile deletion atomically removes profile, requests and cooldown records; captures message IDs.
- [x] Best-effort revoke of both group request cards, prompts, voluntary intro cards, legacy browsing media and PV match cards.
- [x] Leaving/not belonging to a destination group, or disabled destination settings, prevents browse display and request delivery.
- [x] Registration / private reply deep links / owner QA / profile / inbox / outbox / request confirm use private contextual ReplyKeyboardMarkup.
- [x] Group-level URL/inline links deliberately remain: they open PV without installing a keyboard in everyone else's group chat.
- [x] On restart, active match timers restore; expired rows/cards are cleaned one time on startup; orphan private buttons lead back to the main menu.
- [x] Automated offline scenarios cover eligible-only registration, source/target checks, cross-group card directions, response/withdrawal access, cleanup and recovery.
- [ ] Full 2-user/2-group Telegram E2E run with real accounts. Requires test accounts and administrator-authorized groups.
- [ ] Independent data restoration and production load tests. Requires a staging DB and realistic concurrency.
- [ ] Confirm the already-agreed 18+ eligibility, consent and contact-disclosure checks, and provide an owner support contact before any broad public rollout. This is not a request to add the excluded Block/Report/Privacy growth feature.

## Manual E2E with two consenting adults
Setup: create test Group A and test Group B. Add bot to both. Check the bot can use getChatMember for both groups (administrator access recommended). Use test accounts A and B, each in their own group, and consent to the test.

1. Registration: A creates a profile from A; B creates one from B. Declining the adult-eligibility check must not create a profile. Editing the display number must not change eligibility.
2. Private menu: /start shows ReplyKeyboard. My Profile, text edits, media edit, share intro, Back/Home, inbox and outbox all use contextual ReplyKeyboard rather than newly-sent inline actions.
3. Browse: A hits PV Search with no group picker. A sees B only when B still belongs to the saved destination group and admin settings permit browsing.
4. Request: A selects B -> confirms in PV. A group displays B's profile and A's local linked nickname. B group displays A's profile and B's local linked nickname; both have independent pair and source→destination blockquotes.
5. Privacy: Until acceptance, Group A must not expose B's account link, and Group B must not expose A's account link. Private group titles must not become auto-created invites.
6. Recipient: B chooses the group request handoff (still a group URL/inline button), then in PV uses ReplyKeyboard to accept or reject. Buttons cannot be used by A.
7. Acceptance: both groups receive the acceptance announcement and both private chats receive appropriate contact mentions. The sender-side group card status updates.
8. Rejection: A receives private notification with no unsolicited contact link. Optional explanation from B is only sent after B explicitly confirms it. Re-request cooldown: 12 hours.
9. Pending: unanswered request stays pending until 24h then expires; after 24h a new attempt is allowed. Acceptance cooldown: 24 hours after acceptance.
10. Withdrawal: A requests withdrawal then confirms; old A/B group cards disappear or have buttons revoked. No cooldown is imposed on a withdrawn pair.
11. Deletion: while B is visible in A's PV browse, delete B's profile. Both request group cards, saved intro cards and PV browse media should be revoked. A must not be able to interact with the removed target.
12. Group leave: B leaves Group B; verify B is hidden from browse, no requests are delivered to B's previous group, and rejoining updates presence appropriately.
13. Restart: during profile editor, during inbox selection, and during active match restart Render once each. Active 3-minute timers survive and expired sessions do not strand ReplyKeyboard. Old edit buttons lead safely to the home menu.
14. Permission failures: temporarily remove group delete/media permission. Confirm no secret contact link is leaked; where deleting is impossible, redact captions or revoke buttons where Telegram permits. Report the failure.
15. Flood controls: try a small test burst under Telegram limits; monitor 429s and confirm no duplicate group cards appear from repeated confirmation clicks.

## Pass/fail evidence
For each case, record date/time, test group labels (not private invites), expected versus observed result, screenshot with names/user IDs obscured, Render deploy commit, and sanitized logs. Avoid storing raw private conversations or photos.

A single successful manual interaction does **not** prove the entire acceptance/rejection/withdrawal/deletion matrix is working.

## Limitations and next gates
Telegram can reject deleting older group messages or messages the bot lacks rights for. It is not possible to guarantee that any already-viewed/downloaded media is retracted from someone else's device. No forced auto-invite, no group-wide ReplyKeyboard. Before public scaling, verify established eligibility, mutual-consent and account-link privacy rules, and an owner route for serious support concerns. Do not add the excluded Block/Report/Privacy growth feature.
