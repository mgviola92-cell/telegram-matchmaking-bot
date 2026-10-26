CREATE TABLE IF NOT EXISTS profiles (
 user_id BIGINT NOT NULL,
 group_id BIGINT NOT NULL,
 display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60),
 age SMALLINT CHECK(age BETWEEN 18 AND 120),
 adult_self_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
 bio TEXT CHECK(length(bio)<=300),
 media_type TEXT NOT NULL CHECK(media_type IN ('photo','video')),
 media_file_id TEXT NOT NULL,
 is_public BOOLEAN NOT NULL DEFAULT FALSE,
 archived BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,group_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_public_profile_per_user ON profiles(user_id) WHERE is_public;
CREATE TABLE IF NOT EXISTS requests (
 id BIGSERIAL PRIMARY KEY,
 sender_id BIGINT NOT NULL,
 sender_group_id BIGINT NOT NULL,
 recipient_id BIGINT NOT NULL,
 recipient_group_id BIGINT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','withdrawn')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT (now()+interval '24 hours')
);
CREATE INDEX IF NOT EXISTS pending_requests_recipient ON requests(recipient_id,created_at DESC) WHERE status='pending';
CREATE INDEX IF NOT EXISTS request_sender_target ON requests(sender_id,recipient_id,created_at DESC);

-- Group administrators control these features without recurring polling.
CREATE TABLE IF NOT EXISTS group_settings (
 group_id BIGINT PRIMARY KEY,
 matchmaking BOOLEAN NOT NULL DEFAULT TRUE,
 registration BOOLEAN NOT NULL DEFAULT TRUE,
 requests BOOLEAN NOT NULL DEFAULT TRUE,
 public_browse BOOLEAN NOT NULL DEFAULT TRUE,
 intros BOOLEAN NOT NULL DEFAULT TRUE,
 cleanup BOOLEAN NOT NULL DEFAULT TRUE
);

-- Resolve-time cooldowns must measure from decision time, not request creation.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS request_decision_cooldown
    ON requests(sender_id,recipient_id,decided_at DESC)
    WHERE status IN ('accepted','rejected');

-- Only Telegram IDs and lightweight browsing state; never media binaries.
CREATE TABLE IF NOT EXISTS browse_sessions (
 viewer_id BIGINT NOT NULL,
 group_id BIGINT NOT NULL,
 message_id BIGINT,
 public_mode BOOLEAN NOT NULL DEFAULT FALSE,
 profile_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
 position INTEGER NOT NULL DEFAULT 0,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(viewer_id,group_id),
 CONSTRAINT browse_position_nonnegative CHECK (position>=0)
);
CREATE INDEX IF NOT EXISTS browse_sessions_activity ON browse_sessions(updated_at);

-- Small per-viewer seen marker, never media bytes.
CREATE TABLE IF NOT EXISTS viewed_profiles (
 viewer_id BIGINT NOT NULL,
 viewer_group_id BIGINT NOT NULL,
 target_id BIGINT NOT NULL,
 target_group_id BIGINT NOT NULL,
 last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(viewer_id,viewer_group_id,target_id,target_group_id)
);
CREATE INDEX IF NOT EXISTS viewed_profiles_viewer ON viewed_profiles(viewer_id,viewer_group_id);

-- An optional recipient-authored rejection note is shared only after explicit consent.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Self-declared adult eligibility replaces asking for exact age.
ALTER TABLE profiles ALTER COLUMN age DROP NOT NULL;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS adult_self_confirmed BOOLEAN NOT NULL DEFAULT FALSE;

-- Telegram group messages belonging to a request, for cleanup on private handoff.
-- IDs are message references only; no profile media is stored.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS group_card_message_id BIGINT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS group_prompt_message_id BIGINT;

-- Owner-selected QA group is configured once through the bot's private panel.
CREATE TABLE IF NOT EXISTS owner_qa_settings (
 owner_id BIGINT PRIMARY KEY,
 test_group_id BIGINT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Safely collapse legacy per-group profiles: preserve the most recently created
-- public/active profile per user as the single canonical global profile.
-- Provenance group_id remains a home group ID for request routing.
WITH ranked AS (
 SELECT user_id,group_id,
 ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY
   (NOT archived) DESC, is_public DESC, created_at DESC, group_id DESC) AS rn
 FROM profiles
)
DELETE FROM profiles p USING ranked r
 WHERE p.user_id=r.user_id AND p.group_id=r.group_id AND r.rn>1;
UPDATE profiles SET is_public=true, archived=false WHERE NOT is_public OR archived;
DROP INDEX IF EXISTS one_public_profile_per_user;
CREATE UNIQUE INDEX IF NOT EXISTS one_global_profile_per_user ON profiles(user_id);
-- Old sessions refer to legacy per-group IDs and their cursors must be regenerated.
DELETE FROM browse_sessions WHERE public_mode=true;
