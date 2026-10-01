"""Selftest of scripts/wiki_lint.py on a sandbox wiki.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Each case starts from a clean two-page wiki in a throwaway git repository (tempfile.mkdtemp),
changes one thing, and asserts the presence OR the absence of an output line, plus the exit
code. The sandbox has its own scripts/lib/tooling.conf, so the cases do not depend on this
project's budget.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "wiki_lint.py")

CONF = """# sandbox tooling.conf
WIKI_PAGE_BUDGET=30
DEAD_PATH_ROOTS='src|scripts|wip|\\.llmwiki'
"""
DATE = "2026-10-01"

INDEX = f"""# Wiki index

Load this file first.

## Conventions

1. `[[Name]]` resolves to `.llmwiki/<Name>.md`.
2. A stale fact gets `> **Status: Outdated** (YYYY-MM-DD) — what changed.` under it.

## Overview

| Page | Summary | Updated |
|---|---|---|
| [[Alpha]] | The first page. | {DATE} |
| [[Beta]] | The second page. | {DATE} |
"""


def page(name, body="Plain facts.", updated=DATE, decisions=True):
    lines = [f"# {name}", "", "> Scope: a test page.", "> Related: [[Alpha]] · [[Beta]]"]
    if updated is not None:
        lines.append(f"> Updated: {updated}")
    lines += ["", "## Facts", "", body, ""]
    if decisions:
        lines += ["## Decisions & History", "", f"- **Created ({DATE}).** For the test."]
    return "\n".join(lines) + "\n"


class WikiLint(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="wiki-lint-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts", "lib"))
        os.makedirs(os.path.join(self.repo, ".llmwiki"))
        os.makedirs(os.path.join(self.repo, "src"))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=self.tmp
        )
        subprocess.run(["git", "init", "-q", self.repo], check=True, env=self.env)
        self.write("scripts/lib/tooling.conf", CONF)
        self.write("src/app.py", "a = 1\nb = 2\nc = 3\n")
        self.write(".llmwiki/INDEX.md", INDEX)
        self.write(".llmwiki/Alpha.md", page("Alpha"))
        self.write(".llmwiki/Beta.md", page("Beta"))

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def lint(self, *args):
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self.env,
            timeout=60,
        )
        return proc.returncode, proc.stdout

    def findings(self, out):
        lines = out.splitlines()
        return [ln for ln in lines if not ln.startswith("note: ") and "finding(s)" not in ln]

    def notes(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("note: ")]

    def assert_finding(self, fragment):
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(fragment in ln for ln in self.findings(out)), out)
        return out

    def assert_clean(self):
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.findings(out), [], out)
        return out

    # --- cases ---

    def test_clean_wiki(self):
        out = self.assert_clean()
        self.assertEqual(out.strip().splitlines()[-1], "0 finding(s), 0 note(s)")

    def test_page_over_budget(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="\n".join(["fact"] * 40)))
        self.assert_finding("lines, over the budget of 30")

    def test_index_is_never_held_to_the_budget(self):
        self.write(".llmwiki/INDEX.md", INDEX + "\n".join(["filler"] * 40) + "\n")
        out = self.assert_clean()
        self.assertNotIn("over the budget", out)

    def test_outdated_block_is_a_note_not_a_finding(self):
        body = "Old fact.\n> **Status: Outdated** (2026-09-01) — the value moved."
        self.write(".llmwiki/Alpha.md", page("Alpha", body=body))
        out = self.assert_clean()
        self.assertTrue(any("Status: Outdated" in n for n in self.notes(out)), out)

    def test_literal_yyyy_mm_dd_in_a_convention_is_not_a_status_block(self):
        out = self.assert_clean()  # INDEX conventions quote the Status form with YYYY-MM-DD
        self.assertEqual(self.notes(out), [])

    def test_dead_path(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="Lives in `src/missing.py`."))
        self.assert_finding("dead path `src/missing.py`")

    def test_existing_paths_anchors_and_folders(self):
        body = "See `src/app.py`, `src/app.py#top`, `src/` and `scripts/lib/tooling.conf`."
        self.write(".llmwiki/Alpha.md", page("Alpha", body=body))
        self.assert_clean()

    def test_patterns_and_placeholders_are_ignored(self):
        body = "Any `src/*.py`, one `src/<module>.py`, `src/{a,b}.py`, `src/x y.py`, `src/...`."
        self.write(".llmwiki/Alpha.md", page("Alpha", body=body))
        self.assert_clean()

    def test_paths_outside_the_roots_are_ignored(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="Run `docs/nowhere.md` or `x/y`."))
        self.assert_clean()

    def test_path_in_a_fenced_block_is_ignored(self):
        body = "```\n`src/missing.py`\n```\n~~~\n`src/also-missing.py`\n~~~"
        self.write(".llmwiki/Alpha.md", page("Alpha", body=body))
        self.assert_clean()

    def test_line_past_the_end_of_a_file(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="Set at `src/app.py:999`."))
        self.assert_finding("line 999 is past the end of src/app.py (3 lines)")

    def test_line_ranges(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="`src/app.py:2` and `src/app.py:1-3`."))
        self.assert_clean()
        self.write(".llmwiki/Alpha.md", page("Alpha", body="`src/app.py:2-9`."))
        self.assert_finding("line 9 is past the end")

    def test_backticked_link_is_an_example(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="Write `[[Placeholder]]` to link."))
        out = self.assert_clean()
        self.assertEqual(self.notes(out), [])

    def test_dangling_link_is_a_note(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="See [[Nowhere]]."))
        out = self.assert_clean()
        self.assertTrue(any("dangling link [[Nowhere]]" in n for n in self.notes(out)), out)
        self.assertEqual(out.strip().splitlines()[-1], "0 finding(s), 1 note(s)")

    def test_index_date_differs_from_the_page(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", updated="2026-10-02"))
        self.assert_finding("differs from its `> Updated: 2026-10-02`")

    def test_page_missing_from_the_index(self):
        self.write(".llmwiki/Gamma.md", page("Gamma"))
        self.assert_finding("Gamma.md: missing from INDEX.md")

    def test_index_row_to_a_missing_page(self):
        os.remove(os.path.join(self.repo, ".llmwiki", "Beta.md"))
        self.assert_finding("[[Beta]] links a page that does not exist")

    def test_updated_missing(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", updated=None))
        self.assert_finding("no `> Updated: YYYY-MM-DD` line")

    def test_updated_with_an_invalid_date(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", updated="2026-02-30"))
        self.write(
            ".llmwiki/INDEX.md",
            INDEX.replace(
                f"[[Alpha]] | The first page. | {DATE}", "[[Alpha]] | The first page. | 2026-02-30"
            ),
        )
        self.assert_finding("invalid date: 2026-02-30")

    def test_decisions_and_history_missing(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", decisions=False))
        self.assert_finding("no `## Decisions & History` section")

    def test_summary_word_budget(self):
        words25 = " ".join(["word"] * 25)
        self.write(".llmwiki/INDEX.md", INDEX.replace("The first page.", words25))
        self.assert_clean()
        self.write(".llmwiki/INDEX.md", INDEX.replace("The first page.", words25 + " more"))
        self.assert_finding("26 words, over 25")

    def test_exit_2_without_index(self):
        os.remove(os.path.join(self.repo, ".llmwiki", "INDEX.md"))
        rc, out = self.lint()
        self.assertEqual(rc, 2, out)

    def test_exit_0_with_notes_only(self):
        self.write(".llmwiki/Beta.md", page("Beta", body="See [[Later]]."))
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.notes(out)), 1)

    def test_exit_1_with_a_finding_and_line_format(self):
        self.write(".llmwiki/Alpha.md", page("Alpha", body="`src/gone.py`"))
        rc, out = self.lint()
        self.assertEqual(rc, 1)
        self.assertIn(".llmwiki/Alpha.md:9: dead path `src/gone.py`", out)
        self.assertEqual(out.strip().splitlines()[-1], "1 finding(s), 0 note(s)")

    def test_explicit_wiki_dir(self):
        os.rename(os.path.join(self.repo, ".llmwiki"), os.path.join(self.repo, "wiki"))
        rc, _ = self.lint()
        self.assertEqual(rc, 2)
        rc, out = self.lint("wiki")
        self.assertEqual(rc, 0, out)

    def test_missing_conf_key_is_explicit(self):
        self.write("scripts/lib/tooling.conf", "WIKI_PAGE_BUDGET=30\n")
        proc = subprocess.run(
            [sys.executable, SCRIPT],
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self.env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing key DEAD_PATH_ROOTS in scripts/lib/tooling.conf", proc.stderr)

    def test_help_and_executable(self):
        rc, out = self.lint("--help")
        self.assertEqual(rc, 0)
        self.assertIn("Not checked", out)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/wiki_lint.py")


if __name__ == "__main__":
    unittest.main()
