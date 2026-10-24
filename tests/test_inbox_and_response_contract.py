"""Small offline checks: imports not needed for Python syntax verification."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SourceChecks(unittest.TestCase):
    def test_python_files_parse(self):
        for filename in ("main.py", "db.py", "repository.py", "handlers.py", "responses.py"):
            with self.subTest(filename=filename):
                ast.parse((ROOT / filename).read_text(encoding="utf-8"), filename=filename)

    def test_response_variants(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from responses import OPENINGS, ENDINGS, say, variants_count
        for event in ("welcome", "register_invite", "no_matches", "request_sent", "inbox_empty", "outgoing_empty", "request_rejected", "profile_saved"):
            self.assertGreaterEqual(variants_count(event), 100)
            self.assertEqual(len(OPENINGS[event]), len(ENDINGS[event]))
            seen = [say(event, user_id=994441) for _ in range(24)]
            self.assertEqual(len(seen), len(set(seen)))

    def test_request_flow_requires_confirmation(self):
        source = (ROOT / "handlers.py").read_text(encoding="utf-8")
        self.assertIn('async def ask_confirm_callback', source)
        self.assertIn('callback_data=f"ask_confirm:', source)
        self.assertIn('async def intro_view', source)
        self.assertIn('async def profile_delete_do', source)

    def test_request_resolution_requires_active_profiles(self):
        source = (ROOT / "repository.py").read_text(encoding="utf-8")
        self.assertIn('sender.age>=18', source)
        self.assertIn('recipient.age>=18', source)
        self.assertIn('viewed_profiles', source)

    def test_private_invitation_commands_exist(self):
        source = (ROOT / "handlers.py").read_text(encoding="utf-8")
        for command in ('CommandHandler("inbox", inbox)', 'CommandHandler("outgoing", outgoing)'):
            self.assertIn(command, source)


if __name__ == "__main__":
    unittest.main()
