"""Selftest of scripts/lib/dead_paths.py: the dead-path rule shared by wiki_lint.py and wip.py.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Table-driven, on a sandbox tree (tempfile.mkdtemp); no git, no network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import dead_paths  # noqa: E402

ROOTS = r"src|scripts|\.llmwiki"


class DeadPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dead-paths-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for rel, text in (("src/app.py", "a\nb\nc\n"), ("scripts/lib/x.conf", "")):
            path = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    def refs(self, text):
        return [(r.path, r.last_line) for r in dead_paths.iter_refs(text, ROOTS)]

    def test_references(self):
        cases = [
            ("plain", "see `src/app.py`", [("src/app.py", None)]),
            ("line suffix", "`src/app.py:3`", [("src/app.py", 3)]),
            ("range suffix keeps the last line", "`src/app.py:2-9`", [("src/app.py", 9)]),
            ("anchor dropped", "`src/app.py#top`", [("src/app.py", None)]),
            ("trailing slash dropped", "`src/`", [("src", None)]),
            ("outside the roots", "`docs/a.md` `lib/x`", []),
            ("root must be followed by a slash", "`srcx/a`", []),
            ("glob ignored", "`src/*.py`", []),
            ("placeholder ignored", "`src/<name>.py`", []),
            ("braces ignored", "`src/{a,b}.py`", []),
            ("variable ignored", "`src/$X`", []),
            ("space ignored", "`src/a b.py`", []),
            ("ellipsis ignored", "`src/.../x.py`", []),
            ("double backticks are not a span", "``src/app.py``", []),
            ("two on a line", "`src/a` and `scripts/b`", [("src/a", None), ("scripts/b", None)]),
        ]
        for desc, text, want in cases:
            with self.subTest(desc):
                self.assertEqual(self.refs(text), want)

    def test_fenced_blocks_are_skipped(self):
        text = "`src/a`\n```\n`src/in-fence`\n```\n~~~~\n`src/tilde`\n~~~~\n`src/b`\n"
        self.assertEqual([p for p, _ in self.refs(text)], ["src/a", "src/b"])

    def test_line_numbers(self):
        refs = list(dead_paths.iter_refs("x\n\n`src/a`\n", ROOTS))
        self.assertEqual(refs[0].lineno, 3)

    def test_empty_roots_check_nothing(self):
        self.assertEqual(list(dead_paths.iter_refs("`src/missing`", "")), [])

    def test_problems(self):
        text = "`src/app.py` `src/missing.py` `src/app.py:3` `src/app.py:4` `scripts/lib/x.conf:1`"
        messages = [m for _, _, m in dead_paths.problems(self.tmp, text, ROOTS)]
        self.assertEqual(len(messages), 3, messages)
        self.assertIn("dead path `src/missing.py`", messages)
        self.assertIn("`src/app.py:4`: line 4 is past the end of src/app.py (3 lines)", messages)
        self.assertIn(
            "`scripts/lib/x.conf:1`: line 1 is past the end of scripts/lib/x.conf (0 lines)",
            messages,
        )

    def test_dead_deduplicates_and_skips_line_checks(self):
        text = "`src/gone` `src/gone` `src/app.py:99` `src/other`"
        self.assertEqual(dead_paths.dead(self.tmp, text, ROOTS), ["src/gone", "src/other"])

    def test_count_lines(self):
        cases = [("", 0), ("a", 1), ("a\n", 1), ("a\nb", 2), ("a\nb\n", 2)]
        path = os.path.join(self.tmp, "count.txt")
        for text, want in cases:
            with self.subTest(repr(text)):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.assertEqual(dead_paths.count_lines(path), want)


if __name__ == "__main__":
    unittest.main()
