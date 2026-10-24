from pathlib import Path

def test_schema_contains_unique_public_profile():
    sql = Path("schema.sql").read_text()
    assert "one_public_profile_per_user" in sql
    assert "media_file_id" in sql

def test_no_background_db_polling():
    code = Path("db.py").read_text()
    assert "asyncio.sleep" not in code
    assert "max_size=3" in code
