"""Real PostgreSQL migration QA, runnable only against a local disposable CI DB.

PRODUCTION SAFEGUARD: refuses non-loopback hosts, unexpected database names,
and execution without the dedicated migration-test environment flag.
"""
import os
import pathlib
import unittest
from unittest.mock import AsyncMock,patch
from urllib.parse import urlparse

import asyncpg
import repository

ROOT=pathlib.Path(__file__).resolve().parents[1]
DB_NAME="matchmaking_migration_test"
ENABLED=os.getenv("RUN_POSTGRES_MIGRATION_TESTS")=="1"


@unittest.skipUnless(ENABLED,"Only runs against disposable PostgreSQL in CI")
class LivePostgresMigrationQA(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dsn=os.getenv("MIGRATION_TEST_DATABASE_URL","")
        url=urlparse(self.dsn)
        if url.hostname not in ("127.0.0.1","localhost") or url.path!="/"+DB_NAME:
            raise RuntimeError("Migration QA may only use disposable loopback matchmaking_migration_test")
        self.conn=await asyncpg.connect(self.dsn)
        # This DROP is confined to the disposable CI postgres instance only.
        await self.conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        await self.conn.execute("""
            CREATE TABLE profiles (
              user_id BIGINT NOT NULL, group_id BIGINT NOT NULL,
              display_name TEXT NOT NULL, age INTEGER,
              adult_self_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
              bio TEXT, media_type TEXT NOT NULL, media_file_id TEXT NOT NULL,
              archived BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY(user_id,group_id)
            );
            CREATE TABLE profiles_legacy_backup (
              user_id BIGINT NOT NULL, group_id BIGINT NOT NULL,
              display_name TEXT, age SMALLINT,
              adult_self_confirmed BOOLEAN, bio TEXT, media_type TEXT,
              media_file_id TEXT, archived BOOLEAN, created_at TIMESTAMPTZ,
              PRIMARY KEY(user_id,group_id)
            );
        """)
        await self.conn.execute("""
            INSERT INTO profiles
            (user_id,group_id,display_name,age,adult_self_confirmed,bio,
             media_type,media_file_id,created_at)
            VALUES
            (9001,-1001,'Old profile',25,true,'before','photo','tg-file-A',
             now()-interval '2 days'),
            (9001,-1002,'Canonical profile',999999999,true,'after','photo','tg-file-B',
             now()-interval '1 day'),
            (9002,-1003,'Other person',22,true,'bio','photo','tg-file-C',
             now()-interval '1 day')
        """)
        sql=(ROOT/"schema.sql").read_text(encoding="utf-8")
        # Exact real DDL used by Render; no migration mock here.
        await self.conn.execute(sql)
        self.dbpool=await asyncpg.create_pool(self.dsn,min_size=0,max_size=2)

    async def asyncTearDown(self):
        await self.dbpool.close()
        await self.conn.close()

    async def test_migration_backup_global_profile_and_idempotence(self):
        profiles=await self.conn.fetch(
            "SELECT user_id,group_id,age,media_file_id FROM profiles ORDER BY user_id")
        self.assertEqual(len(profiles),2)
        self.assertEqual(profiles[0]["group_id"],-1002)
        self.assertEqual(profiles[0]["age"],999999999)
        self.assertEqual(profiles[0]["media_file_id"],"tg-file-B")
        self.assertEqual(await self.conn.fetchval(
            "SELECT count(*) FROM profiles_legacy_backup WHERE user_id=9001"),2)
        self.assertEqual(await self.conn.fetchval(
            "SELECT max(age) FROM profiles_legacy_backup"),999999999)
        self.assertFalse(await self.conn.fetchval("""
            SELECT EXISTS(SELECT 1 FROM information_schema.columns
            WHERE table_name='profiles' AND column_name='is_public')"""))
        self.assertFalse(await self.conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM group_settings WHERE questions OR events)"))
        await self.conn.execute((ROOT/"schema.sql").read_text(encoding="utf-8"))
        self.assertEqual(await self.conn.fetchval(
            "SELECT count(*) FROM profiles_legacy_backup WHERE user_id=9001"),2)
        self.assertEqual(await self.conn.fetchval(
            "SELECT count(*) FROM profiles WHERE user_id=9001"),1)

    async def test_notification_preference_and_atomic_twelve_hour_digest(self):
        with patch.object(repository,"pool",AsyncMock(return_value=self.dbpool)):
            # Opted out by default, even for an adult-confirmed global profile.
            self.assertFalse((await repository.get_notification_preference(9001))
                             ["expiring_inbox"])
            self.assertIsNone(await repository.claim_expiring_inbox_digest(9001))
            saved=await repository.set_notification_preference(9001,True)
            self.assertTrue(saved["expiring_inbox"])
            await self.conn.execute("""
                INSERT INTO requests
                (sender_id,sender_group_id,recipient_id,recipient_group_id,
                 status,expires_at)
                VALUES (9002,-1003,9001,-1002,'pending',now()+interval '2 hours')
            """)
            self.assertEqual(await repository.claim_expiring_inbox_digest(9001),1)
            self.assertIsNone(await repository.claim_expiring_inbox_digest(9001))
            await repository.set_notification_preference(9001,False)
            await self.conn.execute("""
                UPDATE user_notification_preferences
                SET last_reminded_at=now()-interval '15 hours'
                WHERE user_id=9001
            """)
            self.assertIsNone(await repository.claim_expiring_inbox_digest(9001))

    async def test_group_features_default_off_and_cascade_cleanup(self):
        with patch.object(repository,"pool",AsyncMock(return_value=self.dbpool)):
            row=await repository.group_settings(-1009)
            self.assertFalse(row["questions"])
            self.assertFalse(row["events"])
            self.assertTrue(row["matchmaking"])
            await repository.set_notification_preference(9001,True)
        await self.conn.execute("DELETE FROM profiles WHERE user_id=9001")
        self.assertEqual(await self.conn.fetchval(
            "SELECT count(*) FROM user_notification_preferences WHERE user_id=9001"),0)

if __name__=="__main__":
    unittest.main()
