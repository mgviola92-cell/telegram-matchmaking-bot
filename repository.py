"""On-demand, transactional persistence; expired rows are filtered by time, not polled."""
from datetime import datetime, timezone, timedelta
from db import pool

async def upsert_profile(user_id, group_id, name, age, media_type, file_id, bio=None):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""INSERT INTO profiles(user_id,group_id,display_name,age,bio,media_type,media_file_id,archived)
            VALUES($1,$2,$3,$4,$5,$6,$7,false)
            ON CONFLICT(user_id,group_id) DO UPDATE SET display_name=excluded.display_name, age=excluded.age,
            bio=excluded.bio,media_type=excluded.media_type,media_file_id=excluded.media_file_id,archived=false
            RETURNING *""",user_id,group_id,name,age,bio,media_type,file_id)

async def get_profile(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("SELECT * FROM profiles WHERE user_id=$1 AND group_id=$2 AND NOT archived",user_id,group_id)

async def set_public_profile(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock($1)",user_id)
            exists = await c.fetchval("SELECT 1 FROM profiles WHERE user_id=$1 AND group_id=$2 AND NOT archived",user_id,group_id)
            if not exists:
                return None
            await c.execute("UPDATE profiles SET is_public=false WHERE user_id=$1",user_id)
            return await c.execute("UPDATE profiles SET is_public=true WHERE user_id=$1 AND group_id=$2 AND NOT archived",user_id,group_id)

async def archive_profile(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        await c.execute("UPDATE profiles SET archived=true,is_public=false WHERE user_id=$1 AND group_id=$2",user_id,group_id)

async def browse_profiles(viewer_id, group_id, public=False, limit=50):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetch("""SELECT user_id,group_id,display_name,age,bio,media_type,media_file_id
            FROM profiles WHERE NOT archived AND age>=18 AND user_id<>$1 AND (group_id=$2 OR ($3 AND is_public))
            ORDER BY random() LIMIT $4""",viewer_id,group_id,public,limit)

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
        return await c.fetchrow("""UPDATE requests SET status=$3,decided_at=now() WHERE id=$1 AND recipient_id=$2
          AND status='pending' AND expires_at>now() RETURNING *""",request_id,recipient_id,action)

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
            AND NOT archived ORDER BY created_at DESC LIMIT 100""", user_id)

async def set_private_profile(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.execute("""UPDATE profiles SET is_public=false
            WHERE user_id=$1 AND group_id=$2 AND NOT archived""", user_id, group_id)

async def update_profile_text(user_id, group_id, field, value):
    """Only allowlisted text fields, never user-supplied SQL identifiers."""
    columns = {"display_name": "display_name", "bio": "bio"}
    if field not in columns:
        raise ValueError("Unsupported profile field")
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow(
            f"UPDATE profiles SET {columns[field]}=$3 WHERE user_id=$1 AND group_id=$2 AND NOT archived RETURNING *",
            user_id, group_id, value)

SETTING_NAMES = ("matchmaking", "registration", "requests", "public_browse", "intros", "cleanup")

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

async def save_browse_session(user_id, group_id, message_id, public_mode, keys, position=0):
    """Replace browsing cursor with compact ID pairs, never photos or captions."""
    import json
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""INSERT INTO browse_sessions
            (viewer_id,group_id,message_id,public_mode,profile_keys,position,updated_at)
            VALUES($1,$2,$3,$4,$5::jsonb,$6,now())
            ON CONFLICT(viewer_id,group_id) DO UPDATE SET
            message_id=excluded.message_id,public_mode=excluded.public_mode,
            profile_keys=excluded.profile_keys,position=excluded.position,updated_at=now()
            RETURNING *""", user_id,group_id,message_id,public_mode,json.dumps(keys),position)

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
            if (datetime.now(timezone.utc)-row["updated_at"]).total_seconds()>300:
                return None
            import json
            keys = row["profile_keys"]
            if isinstance(keys, str):
                keys = json.loads(keys)
            pos = row["position"]+delta
            if pos<0 or pos>=len(keys):
                return row
            return await c.fetchrow("""UPDATE browse_sessions
                SET position=$3,updated_at=now() WHERE viewer_id=$1 AND group_id=$2
                RETURNING *""",user_id,group_id,pos)

async def active_browse_session(user_id, group_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""SELECT * FROM browse_sessions
            WHERE viewer_id=$1 AND group_id=$2
            AND updated_at>now()-interval '5 minutes'""",user_id,group_id)

async def profile_at(user_id, group_id):
    return await get_profile(user_id,group_id)
