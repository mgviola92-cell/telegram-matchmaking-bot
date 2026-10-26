"""Small, lazy PostgreSQL connection pool. No periodic DB polling."""
import os
import asyncio
import asyncpg
import hashlib
import logging

_pool = None
_pool_lock = asyncio.Lock()

async def pool():
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                url = os.getenv("DATABASE_URL")
                if not url:
                    raise RuntimeError("DATABASE_URL is not configured")
                _pool = await asyncpg.create_pool(dsn=url, min_size=0, max_size=3, max_inactive_connection_lifetime=30, command_timeout=10, statement_cache_size=0)
    return _pool

async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

async def init_schema():
    """Apply each exact schema version once, not all DDL on every warm restart.

    Repeating ALTER TABLE on a live database can invalidate asyncpg's prepared
    query plans in existing instances and break /match or /profile calls.
    """
    with open("schema.sql", encoding="utf-8") as f:
        sql = f.read()
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    p = await pool()
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(20261027, 12041)")
            await c.execute("""CREATE TABLE IF NOT EXISTS applied_schema_versions (
                digest TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
            seen = await c.fetchval(
                "SELECT EXISTS(SELECT 1 FROM applied_schema_versions WHERE digest=$1)", digest)
            if seen:
                logging.info("Schema already applied; skipping repeat DDL")
                return
            await c.execute(sql)
            await c.execute(
                "INSERT INTO applied_schema_versions(digest) VALUES($1)",digest)
            logging.info("Schema version applied successfully")
