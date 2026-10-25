"""Context-safe, curated Burmese variation regression checks."""
import ast
import pathlib
import unittest
from unittest.mock import patch
import notices

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DynamicNoticeTests(unittest.TestCase):
    def test_all_families_have_six_independent_complete_lines(self):
        self.assertGreaterEqual(len(notices.NOTICES), 20)
        for event, variants in notices.NOTICES.items():
            with self.subTest(event=event):
                self.assertGreaterEqual(len(variants), 6)
                self.assertEqual(len(variants), len(set(variants)))
                self.assertTrue(all(variant.strip() for variant in variants))

    def test_no_short_term_repeats_for_single_event(self):
        for event in notices.NOTICES:
            seen=[notices.say_notice(event, 99112233) for _ in range(5)]
            self.assertEqual(len(seen), len(set(seen)),event)

    def test_handler_uses_only_existing_notice_families(self):
        code=(ROOT/"handlers.py").read_text(encoding="utf-8")
        tree=ast.parse(code)
        references=[]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="say_notice":
                self.assertEqual(len(node.args),2)
                self.assertIsInstance(node.args[0],ast.Constant)
                references.append(node.args[0].value)
        self.assertGreaterEqual(len(references),65)
        self.assertTrue(set(references).issubset(notices.NOTICES))

    def test_no_unbound_query_context_in_commands(self):
        code=(ROOT/"handlers.py").read_text(encoding="utf-8")
        tree=ast.parse(code)
        for node in ast.walk(tree):
            if not isinstance(node,ast.AsyncFunctionDef):
                continue
            notice_calls=[n for n in ast.walk(node)
                          if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                          and n.func.id=="say_notice"]
            if notice_calls and any(isinstance(n,ast.Name) and n.id=="q"
                                    for call in notice_calls for n in ast.walk(call)):
                self.assertTrue(
                    any(isinstance(n,ast.Assign) and
                        any(isinstance(t,ast.Name) and t.id=="q" for t in n.targets)
                        for n in node.body),
                    "Missing callback query in "+node.name)

    def test_notice_has_localizable_burmese_text(self):
        for variants in notices.NOTICES.values():
            for line in variants:
                self.assertTrue(any("\\u1000" <= c <= "\\u109f" for c in line))
