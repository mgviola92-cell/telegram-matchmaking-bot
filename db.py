"""Small, lazy PostgreSQL connection pool. No periodic DB polling."""
import os
import asyncpg

_pool = None

async def pool():
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _pool = await asyncpg.create_pool(dsn=url, min_size=0, max_size=3, max_inactive_connection_lifetime=30, command_timeout=10)
    return _pool

async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

async def init_schema():
    p = await pool()
    with open("schema.sql", encoding="utf-8") as f:
        sql = f.read()
    async with p.acquire() as c:
        await c.execute(sql)
