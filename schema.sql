CREATE TABLE IF NOT EXISTS profiles (
 user_id BIGINT NOT NULL,
 group_id BIGINT NOT NULL,
 display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60),
 age SMALLINT NOT NULL CHECK(age BETWEEN 13 AND 17),
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
