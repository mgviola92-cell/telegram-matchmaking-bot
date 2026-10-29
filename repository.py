"""On-demand, transactional persistence; expired rows are filtered by time, not polled."""
from datetime import datetime, timezone, timedelta
from db import pool

async def upsert_profile(user_id, group_id, name, media_type, file_id, bio=None, *, age=None, location=None):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""INSERT INTO profiles(user_id,group_id,display_name,age,bio,media_type,media_file_id,archived,adult_self_confirmed,location)
            VALUES($1,$2,$3,$7,$4,$5,$6,false,true,$8)
            ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name, age=COALESCE(excluded.age,profiles.age),
            bio=excluded.bio,media_type=excluded.media_type,media_file_id=excluded.media_file_id,
            location=COALESCE(excluded.location,profiles.location),archived=false,
            adult_self_confirmed=true
            RETURNING *""",user_id,group_id,name,bio,media_type,file_id,age,location)

async def get_profile(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("SELECT * FROM profiles WHERE user_id=$1 AND NOT archived",user_id)

async def archive_profile(user_id, group_id):
    """Global profiles remain visible when a member leaves one group."""
    return None

async def restore_profile(user_id, group_id):
    """One global profile does not require re-registration after joining a group."""
    return None

async def browse_profiles(viewer_id, group_id, limit=50):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT p.user_id,COALESCE(venue.group_id,p.group_id) AS group_id,
                   p.display_name,p.age,p.location,p.bio,p.media_type,p.media_file_id
            FROM profiles p
            LEFT JOIN LATERAL (
                SELECT group_id FROM profile_presence
                WHERE user_id=p.user_id
                ORDER BY last_seen_at DESC LIMIT 1
            ) venue ON true
            LEFT JOIN viewed_profiles v ON
                v.viewer_id=$1 AND v.viewer_group_id=$2
                AND v.target_id=p.user_id AND
                    v.target_group_id=COALESCE(venue.group_id,p.group_id)
            WHERE NOT p.archived AND p.adult_self_confirmed AND p.user_id<>$1
               
            ORDER BY (v.target_id IS NOT NULL), random() LIMIT $3""",viewer_id,group_id,limit)

async def send_request(sender_id, sender_group_id, recipient_id, recipient_group_id):
    if sender_id == recipient_id:
        return None
    p = await pool()
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock($1,$2)",sender_id % 2147483647,recipient_id % 2147483647)
            exists = await c.fetchval("""SELECT 1 FROM requests WHERE sender_id=$1 AND recipient_id=$2
              AND status='pending' AND expires_at>now() LIMIT 1""",sender_id,recipient_id)
            if exists:
                return None
            # 12h after rejection, 24h after acceptance; withdrawn/expired pending
            # invitations never impose a cooldown.
            cooldown = await c.fetchval("""SELECT 1 FROM requests
                WHERE sender_id=$1 AND recipient_id=$2
                  AND ((status='rejected' AND COALESCE(decided_at,created_at)>now()-interval '12 hours')
                    OR (status='accepted' AND COALESCE(decided_at,created_at)>now()-interval '24 hours'))
                LIMIT 1""", sender_id, recipient_id)
            if cooldown:
                return None
            return await c.fetchrow("""INSERT INTO requests(sender_id,sender_group_id,recipient_id,recipient_group_id)
              VALUES($1,$2,$3,$4) RETURNING *""",sender_id,sender_group_id,recipient_id,recipient_group_id)

async def incoming_requests(recipient_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT * FROM requests WHERE recipient_id=$1 AND status='pending'
          AND expires_at>now() ORDER BY created_at DESC LIMIT 100""",recipient_id)

async def resolve_request(request_id, recipient_id, action):
    if action not in ("accepted","rejected"):
        raise ValueError("Invalid action")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE requests r SET status=$3,decided_at=now()
          WHERE r.id=$1 AND r.recipient_id=$2 AND r.status='pending' AND r.expires_at>now()
            AND EXISTS (SELECT 1 FROM profiles sender
              WHERE sender.user_id=r.sender_id
                AND NOT sender.archived AND sender.adult_self_confirmed)
            AND EXISTS (SELECT 1 FROM profiles recipient
              WHERE recipient.user_id=r.recipient_id
                AND NOT recipient.archived AND recipient.adult_self_confirmed)
          RETURNING r.*""",request_id,recipient_id,action)

async def withdraw_request(request_id, sender_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE requests SET status='withdrawn' WHERE id=$1 AND sender_id=$2
          AND status='pending' AND expires_at>now() RETURNING *""",request_id,sender_id)

async def pending_request_for_recipient(request_id, recipient_id):
    """Read a live request only for its intended recipient."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT * FROM requests
            WHERE id=$1 AND recipient_id=$2 AND status='pending'
            AND expires_at>now()""", request_id, recipient_id)

async def outgoing_requests(sender_id):
    """Latest still-pending invitations across all source groups."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT * FROM requests
            WHERE sender_id=$1 AND status='pending' AND expires_at>now()
            ORDER BY created_at DESC LIMIT 100""", sender_id)

async def user_profiles(user_id):
    """List the user's active group profiles, newest first."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT * FROM profiles WHERE user_id=$1
            AND NOT archived ORDER BY created_at DESC LIMIT 1""", user_id)

async def update_profile_text(user_id, group_id, field, value):
    """Only allowlisted text fields, never user-supplied SQL identifiers."""
    columns = {"display_name": "display_name", "bio": "bio", "location": "location", "age": "age"}
    if field not in columns:
        raise ValueError("Unsupported profile field")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow(
            f"UPDATE profiles SET {columns[field]}=$2 WHERE user_id=$1 AND NOT archived RETURNING *",
            user_id, value)

SETTING_NAMES = ("matchmaking", "registration", "requests", "intros", "cleanup")

async def group_settings(group_id):
    p = await pool()
    async with p.acquire() as c:
        row = await c.fetchrow("SELECT * FROM group_settings WHERE group_id=$1", group_id)
        return dict(row) if row else {"group_id": group_id, **{name: True for name in SETTING_NAMES}}

async def set_group_setting(group_id, name, enabled):
    if name not in SETTING_NAMES:
        raise ValueError("Unknown group setting")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow(
            f"""INSERT INTO group_settings(group_id,{name}) VALUES($1,$2)
                ON CONFLICT(group_id) DO UPDATE SET {name}=excluded.{name} RETURNING *""",
            group_id, enabled)

async def save_browse_session(user_id, group_id, message_id, keys, position=0):
    """One global-mode browsing cursor per user and group."""
    import json
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""INSERT INTO browse_sessions
            (viewer_id,group_id,message_id,profile_keys,position,updated_at)
            VALUES($1,$2,$3,$4::jsonb,$5,now())
            ON CONFLICT(viewer_id,group_id) DO UPDATE SET
            message_id=excluded.message_id,profile_keys=excluded.profile_keys,
            position=excluded.position,updated_at=now()
            RETURNING *""",user_id,group_id,message_id,json.dumps(keys),position)

async def get_browse_session(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT * FROM browse_sessions
            WHERE viewer_id=$1 AND group_id=$2""",user_id,group_id)

async def advance_browse_session(user_id, group_id, message_id, delta):
    """Move one step if the session is active; old cards cannot control a new one."""
    p = await pool()
    async with p.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("""SELECT * FROM browse_sessions
                WHERE viewer_id=$1 AND group_id=$2 FOR UPDATE""",user_id,group_id)
            if not row or row["message_id"]!=message_id:
                return None
            if (datetime.now(timezone.utc)-row["updated_at"]).total_seconds()>180:
                return None
            import json
            keys = row["profile_keys"]
            if isinstance(keys, str):
                keys = json.loads(keys)
            pos = row["position"]+delta
            if pos<0 or pos>=len(keys):
                return await c.fetchrow("""UPDATE browse_sessions SET updated_at=now()
                    WHERE viewer_id=$1 AND group_id=$2 RETURNING *""",user_id,group_id)
            return await c.fetchrow("""UPDATE browse_sessions
                SET position=$3,updated_at=now() WHERE viewer_id=$1 AND group_id=$2
                RETURNING *""",user_id,group_id,pos)

async def active_browse_session(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT * FROM browse_sessions
            WHERE viewer_id=$1 AND group_id=$2
            AND updated_at>now()-interval '3 minutes'""",user_id,group_id)

async def profile_at(user_id, group_id):
    return await get_profile(user_id,group_id)

async def delete_profile(user_id, group_id):
    """Atomically delete the global profile, requests, and all browse cursors.

    Return message IDs for best-effort Telegram cleanup *after* committing.
    Unlike the old implementation, request references are captured before their
    rows are deleted; cooldowns disappear with the profile.
    """
    p=await pool()
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock($1,$2)",
                            user_id % 2147483647, group_id % 2147483647)
            found=await c.fetchrow(
                "DELETE FROM profiles WHERE user_id=$1 RETURNING user_id,group_id",user_id)
            if not found:
                return None
            affected=await c.fetch("""DELETE FROM requests
                WHERE sender_id=$1 OR recipient_id=$1
                RETURNING id,sender_id,recipient_id,sender_group_id,
                    recipient_group_id,status,group_card_message_id,
                    group_prompt_message_id,sender_card_message_id""",user_id)
            group_cards=await c.fetch("""DELETE FROM browse_sessions
                WHERE viewer_id=$1 OR EXISTS(
                    SELECT 1 FROM jsonb_array_elements(profile_keys) AS item(value)
                    WHERE (item.value->>0)::bigint=$1)
                RETURNING viewer_id,group_id,message_id""",user_id)
            pv_cards=await c.fetch("""DELETE FROM pv_match_sessions
                WHERE user_id=$1 OR EXISTS(
                    SELECT 1 FROM jsonb_array_elements(profile_keys) AS item(value)
                    WHERE (item.value->>0)::bigint=$1)
                RETURNING user_id,card_message_id""",user_id)
            intros=await c.fetch("""DELETE FROM profile_intro_messages
                WHERE user_id=$1 RETURNING group_id,message_id""",user_id)
            await c.execute("""DELETE FROM viewed_profiles
                WHERE viewer_id=$1 OR target_id=$1""",user_id)
            await c.execute("DELETE FROM profile_presence WHERE user_id=$1",user_id)
            return {
                "affected":[dict(r) for r in affected if r["status"]=="pending"],
                "affected_requests":[dict(r) for r in affected],
                "old_cards":[dict(r) for r in group_cards],
                "pv_cards":[dict(r) for r in pv_cards],
                "intro_cards":[dict(r) for r in intros],
            }

async def remember_intro_message(user_id,group_id,message_id):
    """Keep only Telegram message references, not image/video bytes."""
    p=await pool()
    async with p.acquire() as c:
        await c.execute("""INSERT INTO profile_intro_messages
            (user_id,group_id,message_id) VALUES($1,$2,$3)
            ON CONFLICT DO NOTHING""",user_id,group_id,message_id)

async def update_profile_media(user_id, group_id, media_type, file_id):
    if media_type not in ("photo","video"):
        raise ValueError("Unsupported media type")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE profiles SET media_type=$2,media_file_id=$3
            WHERE user_id=$1 AND NOT archived RETURNING *""",
            user_id,media_type,file_id)

async def recent_browse_sessions():
    """One-time startup recovery; do not periodically poll."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT viewer_id,group_id,message_id,updated_at
            FROM browse_sessions WHERE updated_at>now()-interval '3 minutes'
              AND message_id IS NOT NULL LIMIT 500""")

async def touch_browse_session(user_id,group_id,message_id):
    """Reset inactivity only if the current card still belongs to this viewer."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE browse_sessions SET updated_at=now()
            WHERE viewer_id=$1 AND group_id=$2 AND message_id=$3
            AND updated_at>now()-interval '3 minutes' RETURNING *""",
            user_id,group_id,message_id)

async def mark_profile_viewed(viewer_id,viewer_group_id,target_id,target_group_id):
    """One write when a profile is actually shown; no background polling."""
    p = await pool()
    async with p.acquire() as c:
        await c.execute("""INSERT INTO viewed_profiles(viewer_id,viewer_group_id,target_id,target_group_id)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(viewer_id,viewer_group_id,target_id,target_group_id)
            DO UPDATE SET last_seen_at=now()""",
            viewer_id,viewer_group_id,target_id,target_group_id)

async def rejected_request_owned(request_id,recipient_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT id,sender_id,recipient_id,rejection_reason FROM requests
            WHERE id=$1 AND recipient_id=$2 AND status='rejected'
              AND decided_at>now()-interval '24 hours'""",request_id,recipient_id)

async def save_rejection_reason(request_id,recipient_id,reason):
    """One-time, owner-authorized share; cannot overwrite an earlier consent."""
    if not reason or len(reason)>200:
        raise ValueError("Rejection note must be between 1 and 200 characters")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE requests SET rejection_reason=$3
            WHERE id=$1 AND recipient_id=$2 AND status='rejected'
              AND rejection_reason IS NULL AND decided_at>now()-interval '24 hours'
            RETURNING sender_id""",request_id,recipient_id,reason)

async def remember_request_group_message(request_id,recipient_id,kind,message_id):
    """Record only messages posted by our bot for this recipient's request."""
    if kind not in ("card","prompt"):
        raise ValueError("Invalid request message kind")
    column = "group_card_message_id" if kind == "card" else "group_prompt_message_id"
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow(
            f"""UPDATE requests SET {column}=$3
                WHERE id=$1 AND recipient_id=$2 AND status='pending'
                AND expires_at>now() RETURNING id""",
            request_id,recipient_id,message_id)

async def get_request_group_messages(request_id,recipient_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT id, sender_group_id, recipient_group_id,
                sender_card_message_id,group_card_message_id,group_prompt_message_id
            FROM requests WHERE id=$1 AND recipient_id=$2""",request_id,recipient_id)

async def owner_test_request_count(owner_id, test_group_id):
    """Count only owner-originated test requests in the dedicated test group."""
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchval("""SELECT count(*) FROM requests
            WHERE sender_id=$1 AND sender_group_id=$2 AND recipient_group_id=$2""",
            owner_id,test_group_id)

async def reset_owner_test_requests(owner_id, test_group_id):
    """Clean owner-originated request test fixtures only, never arbitrary users' requests.

    Removes request rows solely inside the explicitly configured test group.
    This does not bypass the normal request checks for production groups.
    """
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""DELETE FROM requests
            WHERE sender_id=$1 AND sender_group_id=$2 AND recipient_group_id=$2
            RETURNING id,recipient_id,recipient_group_id,
                      group_card_message_id,group_prompt_message_id""",
            owner_id,test_group_id)

async def get_owner_qa_group(owner_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchval(
            "SELECT test_group_id FROM owner_qa_settings WHERE owner_id=$1",owner_id)

async def set_owner_qa_group(owner_id,test_group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchval("""INSERT INTO owner_qa_settings(owner_id,test_group_id)
            VALUES($1,$2) ON CONFLICT(owner_id) DO UPDATE SET
            test_group_id=excluded.test_group_id,updated_at=now()
            RETURNING test_group_id""",owner_id,test_group_id)

async def record_profile_presence(user_id,group_id):
    """Update only a group routing marker, not a duplicate profile."""
    p = await pool()
    async with p.acquire() as c:
        await c.execute("""INSERT INTO profile_presence(user_id,group_id,last_seen_at)
            VALUES($1,$2,now())
            ON CONFLICT(user_id,group_id)
            DO UPDATE SET last_seen_at=excluded.last_seen_at""",user_id,group_id)

async def remove_profile_presence(user_id,group_id):
    p = await pool()
    async with p.acquire() as c:
        await c.execute("""DELETE FROM profile_presence
            WHERE user_id=$1 AND group_id=$2""",user_id,group_id)

async def candidate_source_groups(user_id):
    """Groups explicitly observed for user; fallback to their profile's home group.

    Membership and group settings are rechecked through Telegram before use.
    """
    p=await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT DISTINCT group_id FROM (
            SELECT group_id, last_seen_at AS seen_at FROM profile_presence
                WHERE user_id=$1
            UNION ALL
            SELECT group_id, created_at AS seen_at FROM profiles
                WHERE user_id=$1 AND NOT archived AND adult_self_confirmed
        ) known ORDER BY group_id LIMIT 30""",user_id)
