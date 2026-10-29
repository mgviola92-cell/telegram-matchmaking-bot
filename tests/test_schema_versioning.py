"""Prevent recurring DDL from invalidating pooled queries on bot restarts."""
import pathlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import db

ROOT=pathlib.Path(__file__).resolve().parents[1]

class FakeConnection:
    def __init__(self,seen):
        self.seen=seen
        self.execute=AsyncMock()
        self.fetchval=AsyncMock(return_value=seen)
    def transaction(self):
        tx=MagicMock()
        tx.__aenter__=AsyncMock()
        tx.__aexit__=AsyncMock()
        return tx

class FakePool:
    def __init__(self,conn):
        self.conn=conn
    def acquire(self):
        ctx=MagicMock()
        ctx.__aenter__=AsyncMock(return_value=self.conn)
        ctx.__aexit__=AsyncMock()
        return ctx

class SchemaVersionTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_startup_skips_schema_ddl(self):
        conn=FakeConnection(True)
        with patch.object(db,"pool",AsyncMock(return_value=FakePool(conn))):
            await db.init_schema()
        sent=" ".join(call.args[0] for call in conn.execute.await_args_list)
        self.assertIn("applied_schema_versions",sent)
        self.assertNotIn("ALTER TABLE profiles",sent)
        self.assertNotIn("INSERT INTO applied_schema_versions",sent)

    async def test_new_schema_runs_and_records_digest(self):
        conn=FakeConnection(False)
        with patch.object(db,"pool",AsyncMock(return_value=FakePool(conn))):
            await db.init_schema()
        sent=" ".join(call.args[0] for call in conn.execute.await_args_list)
        self.assertIn("ALTER TABLE profiles",sent)
        self.assertIn("INSERT INTO applied_schema_versions",sent)

    def test_backup_widened_before_large_profile_values_are_copied(self):
        sql=(ROOT/"schema.sql").read_text(encoding="utf-8")
        alter="ALTER TABLE profiles_legacy_backup ALTER COLUMN age TYPE INTEGER;"
        copy="INSERT INTO profiles_legacy_backup"
        self.assertIn(alter,sql)
        self.assertLess(sql.index(alter),sql.index(copy))
        self.assertIn("age INTEGER",sql)

    def test_asyncpg_prepared_statement_cache_disabled(self):
        source=(ROOT/"db.py").read_text(encoding="utf-8")
        self.assertIn("statement_cache_size=0",source)
        self.assertIn("pg_advisory_xact_lock",source)
