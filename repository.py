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
        return await c.fetchrow("""UPDATE requests SET status=$3 WHERE id=$1 AND recipient_id=$2
          AND status='pending' AND expires_at>now() RETURNING *""",request_id,recipient_id,action)

async def withdraw_request(request_id, sender_id):
    p = await pool()
    async with p.acquire() as c:
        return await c.fetchrow("""UPDATE requests SET status='withdrawn' WHERE id=$1 AND sender_id=$2
          AND status='pending' AND expires_at>now() RETURNING *""",request_id,sender_id)
