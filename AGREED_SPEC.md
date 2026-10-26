# လူတောင်းပွဲ Bot — current canonical specification

## Identity and tone
- Telegram native bot (group chat + private), no Mini App.
- Natural, playful Burmese; nicknames from the profile's display_name. Where a Telegram account link is useful, the clickable label MUST be the profile nickname, never a generic role label or a visible @username.
- Dynamic responses: 14 combination-based event families in responses.py and 26 curated six-line notice families in notices.py. Validation rules remain fixed while phrasing varies.

## One global profile per Telegram user
- Create a profile once from any group with the bot. The same card is automatically visible when using /match from all bot groups; no Group Only/Public modes, toggles or admin Public Browse control.
- There is one canonical profile per user in profiles (unique user_id). group_id is preserved as the registration/home group provenance for destination routing; it is not a visibility filter.
- On startup, legacy per-group rows are backed up as lightweight metadata in profiles_legacy_backup before choosing the most recent active row as the canonical global profile. No images or video binaries are stored.
- A user leaving one group does NOT archive or remove a global profile. Deleting via /profile deletes the user's one global card and cancels pending requests for that user.
- Existing profile holders are never required to register again in another group. Editing name, bio or media updates the same global card. New registrations self-declare 18+ once.

## Discovery
- /match in any bot group shows the global pool, excluding the viewer's own profile. Unseen-first ordering is scoped to the viewer/group.
- Prev/Next edit one Telegram media card. No group-only mode switch. Cards expire after three minutes inactivity; per-group cleanup setting determines whether stale buttons can be physically removed. Expired actions are blocked regardless.
- The active card is usable only by its original viewer.

## Requests and group provenance
- Request confirmation is required before writing a new request.
- The recipient's currently recorded home group receives the request media card. The header uses nicknames:
  "💌 <sender nickname> → <recipient nickname> · #ID"
  "🎀 <source group title> → <recipient group title>"
- When a group has a public @username, the **group title** is a clickable link. Private groups show their title only; no invite link is auto-created.
- Personal account links are clickable nickname labels (Telegram user-ID mention internally), with no visible raw user ID, @username, or generic 'sender/recipient' role label. Applies to group request cards, private reply cards, acceptance, and rejection notices.
- Only the intended recipient may open the request's private response. Group card buttons and handoff prompts are cleaned when opening a private reply or deciding.
- Pending expires in 24h; 12h cooldown after rejection, 24h after acceptance; sender may withdraw a pending request. Duplicate pending requests to the same person are prevented.
- Accept announcements go to source and destination groups (once if same) and use linked nicknames. Both private notices use clickable linked nicknames; rejected-request sender notices also show the recipient's nickname and both group names.
- Rejection can include an optional reason shared only after explicit confirmation.

## Private and group controls
- /start, /profile, /inbox, /outgoing in private. /register, /match in groups. Group admin /settings toggles matchmaking, registration, requests, intro posting, cleanup.
- /owner is silent for all non-owners and in groups. The configured owner selects a QA group once through a private conversation, with request reset scoped to that owner and group only.
- Profile media is referred to by Telegram file_id; no media bytes in Neon.

## Deployment discipline and verification
- Render Auto Deploy OFF; batch updates then one manual deploy after offline tests pass.
- Deploy/build success is not proof of complete live Telegram end-to-end behavior. Track E2E verification separately.
- The profile migration is idempotent. A permanent backup table retains old per-group profile metadata in case the canonical selection needs review.
- Remaining operational consideration: destination routing currently prefers the profile's recorded registration/home group; if a user leaves that group, a new routing-home selection should be added without making new profile registration necessary.
