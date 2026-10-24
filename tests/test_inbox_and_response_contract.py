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
        for event in ("welcome", "register_invite", "no_matches", "request_sent"):
            self.assertGreaterEqual(variants_count(event), 100)
            self.assertEqual(len(OPENINGS[event]), len(ENDINGS[event]))
            seen = [say(event, user_id=994441) for _ in range(24)]
            self.assertEqual(len(seen), len(set(seen)))

    def test_private_invitation_commands_exist(self):
        source = (ROOT / "handlers.py").read_text(encoding="utf-8")
        for command in ('CommandHandler("inbox", inbox)', 'CommandHandler("outgoing", outgoing)'):
            self.assertIn(command, source)


if __name__ == "__main__":
    unittest.main()
