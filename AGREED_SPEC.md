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
- Prev/Next edit one Telegram media card. No group-only mode switch. Cards expire after three minutes inactivity; the bot first deletes the entire match media message (regardless of the general group cleanup setting), falling back to removing action buttons if Telegram refuses deletion. Expired actions are blocked regardless.
- The active card is usable only by its original viewer.

## Requests and group provenance
- Request confirmation is required before writing a new request.
- The recipient's most recently observed active bot group receives the request media card, falling back to the original registration group if no activity has been observed. The header uses nicknames:
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
- Routing caveat: a group switch is learned through group use or chat-member events; a user who has never interacted with a destination group may still route via the original registration group until detected. Real Telegram end-to-end verification remains necessary.

## Match-card display and expiry (October 27)
- Every /match card includes the viewed user's nickname, bio, and the most recently observed group title below them. Public group titles link to the group; private group titles remain plain text. This applies to first card and Next/Previous edits.
- The bot attempts to delete its own /match message after 180 seconds of inactivity. If Telegram denies deletion, only then disable buttons. Do not delete group introduction cards or request cards under this browse-only timer.

## Mobile layout and request privacy (October 27)
- /match caption displays the nickname and bio, then a blank line, then `🏡 Group - <group title>`; keep group title clickable only for public groups.
- Request media captions use a short first line containing both profile nicknames and request ID, a blank line, then source-group → destination-group titles. Profile bio follows with whitespace, avoiding cramped mobile wrapping.
- Before acceptance, the sender nickname on request cards and private reply previews is plain escaped text, not a Telegram account hyperlink. The recipient nickname is a clickable text mention; no @username is printed.
- Once a recipient has opened the private reply, the bot attempts to delete the group request media card itself as well as the group handoff prompt. If Telegram denies removal, it removes actionable buttons where possible. It must not delete unrelated group intros.
- Telegram HTML blockquotes exist, but plain blank lines are used in the tight media captions to avoid extra block framing on narrow screens.
- Approval/acceptance may reveal account links afterward; no account links should appear in pre-acceptance previews.

## Compact profile captions and Group blockquote
- Match-media caption: `<profile nickname>၊ <self-reported age if present>၊ <self-provided city/region if present> — <bio if present>`, followed by a Telegram HTML `<blockquote>🏡 Group - <group title / link></blockquote>`.
- Unknown fields are never guessed. Existing profiles with null age/location display only known fields.
- For new registrations, one 18+ self-confirmation remains mandatory, followed by self-reported age (18–120), and optional broad city/region (max 50 characters or /skip). Never request precise addresses or GPS location.
- Private profile management allows age/city edits. Match media is still posted in groups; Leo's private-chat matching flow is not being substituted without separately agreeing on navigation changes.
- Photo/video captions use Telegram HTML parse mode; blockquotes are supported by Telegram Bot API. Existing group-only mode remains removed.

## Two separated Telegram HTML blockquotes on request cards
- Request media caption shows profile nickname, available age, broad city and bio first. Below are two separate blockquotes: the sender to recipient line plus request ID, and the source group to destination group line. A zero-width spacer line separates the quotes on mobile.
- Before acceptance, the sender is plain nickname text, while the recipient may be an account-linked nickname. Public group names can link to their group; private group names remain plain.
- This is a formatting change to existing request cards. PV Reply Keyboard and two-sided group cards remain future work; do not claim they are implemented.

## Live private reply-keyboard /match workflow (2026-10-27)
- Group `/match` offers an explicit deep link into bot PV; no media browse card is sent to group. The PV /start match_GROUPID handler verifies source group membership, matchmaking toggle, confirmed adult profile, and shows a reply keyboard with `👎 ကျော်မယ်`, `💌 တောင်းမယ်`, `❌ ပွဲသိမ်းမယ်`.
- Each user has a global PV cursor bound to verified source group, with three-minute inactivity expiration and Telegram keyboard removal. Skipping replaces the displayed media card; sending requires explicit private confirmation and revalidates the current cursor and memberships. Text command messages are deleted on a best-effort basis.
- On confirmed request: requester's Group A receives the target recipient's original image/video and compact profile; recipient's Group B receives the sender's image/video and original profile, with reply handoff button. Each has two distinct blockquotes for nicknames and source-group → target-group. A card links only the local group's own member's nickname. Group B request card and prompt are deleted when the recipient opens PV. Sender Group A card remains a historical request record until resolved, subject to sender withdrawal cleanup.
- Both group delivery failures are reported to the sender. No binary media is stored, only Telegram file IDs, minimal cursor data, and group card message IDs. Owner QA controls continue to be separate.

## Persistent private bot reply keyboard (2026-10-27)
- Plain /start in PV displays persistent ReplyKeyboardMarkup with Search, My Profile, Incoming, Outgoing and Help. Match-specific Skip/Request/Stop keyboard temporarily replaces the main menu; ending or timing out switches back to the main menu.
- Direct PV Search requires an existing 18+ confirmed global profile and a source group where the viewer is currently a member and group matchmaking and requests are enabled. For one eligible group, browse starts immediately; for multiple eligible groups, bot shows a per-group inline picker, validating both its server-recorded provenance and live membership on selection.
- Telegram doesn't emit an update merely because a user opens a chat. The already-visible keyboard persists; first-time and previously started users may use /start to show it if absent.
- Request cards continue to use the origin group chosen in PV and the destination profile's recorded group; no anonymous fallback or guest browsing is offered.
