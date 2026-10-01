"""Selftest of scripts/wip.py on a sandbox backlog.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Each case builds wip/ in a throwaway git repository (tempfile.mkdtemp) with its own
scripts/lib/tooling.conf (small limits, so a threshold is crossed with three entries), runs the
real script there, and asserts the presence or the absence of a line. Commit dates are fixed
with GIT_AUTHOR_DATE/GIT_COMMITTER_DATE for the `stale` flag.
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
SCRIPT = os.path.join(ROOT, "scripts", "wip.py")

CONF = """# sandbox tooling.conf
COMPONENTS='cli web'
WIP_LIMIT=2
REFINE_THRESHOLD=2
STALE_DAYS=60
CROWDED_THEME=2
DEAD_PATH_ROOTS='src|wip'
"""


def entry(
    title="Something is wrong",
    theme="core",
    area="cli",
    blocks="no",
    body=None,
    status=None,
    noted="2026-10-01 — while testing",
):
    lines = [f"# {title}", ""]
    if status:
        lines += [status, ""]
    if noted is not None:
        lines.append(f"- **Noted:** {noted}")
    if theme is not None:
        lines.append(f"- **Theme:** {theme}")
    if area is not None:
        lines.append(f"- **Area:** {area}")
    if blocks is not None:
        lines.append(f"- **Blocks release:** {blocks}")
    lines.append("")
    if body is None:
        body = (
            "The problem, with evidence.\n\n"
            "**Fix:** change the thing.\n"
            "**Acceptance:** the thing is changed; a test proves it."
        )
    lines.append(body)
    return "\n".join(lines) + "\n"


class Wip(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="wip-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(
            GIT_AUTHOR_NAME="Selftest",
            GIT_AUTHOR_EMAIL="selftest@example.invalid",
            GIT_COMMITTER_NAME="Selftest",
            GIT_COMMITTER_EMAIL="selftest@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=self.tmp,
        )
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.write("scripts/lib/tooling.conf", CONF)
        for folder in ("todo", "todo_nr", "done"):
            self.write(f"wip/{folder}/.gitkeep", "")
        self.write("src/app.py", "x = 1\n")

    def git(self, *args, env=None):
        subprocess.run(
            ["git", *args], cwd=self.repo, env=env or self.env, check=True, capture_output=True
        )

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, rel, date=None):
        env = dict(self.env)
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        self.git("add", rel, env=env)
        self.git("commit", "-q", "-m", f"add {rel}", env=env)

    def wip(self, *args):
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self.env,
            timeout=60,
        )
        return proc.returncode, proc.stdout

    def check_errors(self):
        rc, out = self.wip("check")
        errors = [ln for ln in out.splitlines() if ln.startswith("wip/")]
        return rc, errors, out

    def refine_line(self, out, stem):
        for line in out.splitlines():
            if line.split("  ")[0].endswith("/" + stem):
                return line
        self.fail(f"no refine line for {stem}:\n{out}")

    # --- check ---

    def test_valid_entry(self):
        self.write("wip/todo/2026-10-01-valid.md", entry())
        rc, errors, out = self.check_errors()
        self.assertEqual((rc, errors), (0, []), out)

    def test_theme_or_area_missing(self):
        self.write("wip/todo/2026-10-01-no-theme.md", entry(theme=None))
        self.write("wip/todo_nr/2026-10-01-no-area.md", entry(area=None))
        rc, errors, out = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertTrue(any("no-theme.md: no `- **Theme:**`" in e for e in errors), out)
        self.assertTrue(any("no-area.md: no `- **Area:**`" in e for e in errors), out)

    def test_area_values(self):
        for area in ("cli", "web", "tooling", "docs", "ci", "infra", "`cli`"):
            with self.subTest(area):
                self.write("wip/todo_nr/2026-10-01-area.md", entry(area=area))
                self.assertEqual(self.check_errors()[0], 0)
        self.write("wip/todo_nr/2026-10-01-area.md", entry(area="backend"))
        rc, errors, _ = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertIn("Area `backend` is not one of", errors[0])

    def test_blocks_release_missing_outside_done(self):
        self.write("wip/todo/2026-10-01-x.md", entry(blocks=None))
        rc, errors, _ = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertIn("no `- **Blocks release:**` line", errors[0])
        self.write("wip/todo/2026-10-01-x.md", entry(blocks="maybe"))
        self.assertIn("must start with yes or no", self.check_errors()[1][0])

    def test_done_entry_without_status(self):
        self.write("wip/done/2026-10-01-closed.md", entry(blocks=None))
        rc, errors, _ = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertIn("in wip/done/ without a `**Status:** done|dropped` line", errors[0])

    def test_status_forms_accepted_in_done(self):
        forms = [
            "**Status:** done (2026-10-02) — closed by fix/x. Fixed.",
            "- **Status:** done (2026-10-02) — closed by #3.",
            "**Status:** dropped (2026-10-02) — merged into [[2026-10-01-other]].",
        ]
        for status in forms:
            with self.subTest(status):
                self.write("wip/done/2026-10-01-closed.md", entry(status=status, blocks=None))
                rc, errors, out = self.check_errors()
                self.assertEqual((rc, errors), (0, []), out)

    def test_open_entry_with_a_status(self):
        self.write("wip/todo/2026-10-01-x.md", entry(status="**Status:** done (2026-10-02)"))
        rc, errors, _ = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertIn("is not in wip/done/", errors[0])

    def test_invalid_file_names(self):
        for name in (
            "fix-the-thing.md",
            "2026-10-01-Upper.md",
            "2026-10-01_x.md",
            "2026-02-30-bad-date.md",
        ):
            with self.subTest(name):
                self.write(f"wip/todo_nr/{name}", entry())
                rc, errors, out = self.check_errors()
                self.assertEqual(rc, 1, out)
                self.assertTrue(errors[0].startswith(f"wip/todo_nr/{name}: "), out)
                os.remove(os.path.join(self.repo, "wip", "todo_nr", name))

    def test_same_name_in_two_folders(self):
        self.write("wip/todo/2026-10-01-copied.md", entry())
        self.write("wip/done/2026-10-01-copied.md", entry(status="**Status:** done (2026-10-02)"))
        rc, errors, _ = self.check_errors()
        self.assertEqual(rc, 1)
        self.assertTrue(any("is in todo and done" in e for e in errors), errors)

    def test_wip_limit_is_a_warning(self):
        for i in range(3):
            self.write(f"wip/todo/2026-10-01-e{i}.md", entry())
        rc, out = self.wip("check")
        self.assertEqual(rc, 0, out)
        self.assertIn("warning: wip/todo/ holds 3 entries, over the WIP limit of 2", out)

    def test_ignored_files(self):
        self.write("wip/README.md", "# wip/\n")
        self.write("wip/todo/README.md", "# not an entry\n")
        self.write("wip/assets/2026-10-01-x/notes.md", "# not an entry\n")
        self.write("wip/done/ARCHIVE-2025.md", "# an archive\n")
        self.write("wip/todo/2026-10-01-valid.md", entry())
        rc, errors, out = self.check_errors()
        self.assertEqual((rc, errors), (0, []), out)
        self.assertIn("in 1 entries", out)

    # --- sections and synonyms ---

    def test_section_synonyms(self):
        bodies = {
            "heading-fix": "## Fix\n\nDo it.\n\n## Acceptance\n\n- done",
            "french": "**Correctif :** le faire.\n\n## Critères d'acceptation\n\n- c'est fait",
            "bullets": "- **Proposed fix:** do it\n- **Acceptance criteria:** it is done",
            "heading-colon": "### Fix:\nDo it.\n#### Acceptation\nOK",
        }
        for name, body in bodies.items():
            self.write(f"wip/todo_nr/2026-10-01-{name}.md", entry(body=body))
        rc, out = self.wip("refine", "todo_nr")
        self.assertEqual(rc, 0)
        for name in bodies:
            with self.subTest(name):
                line = self.refine_line(out, f"2026-10-01-{name}")
                self.assertNotIn("no-fix", line)
                self.assertNotIn("no-acceptance", line)

    # --- refine flags ---

    def test_refine_flags(self):
        self.write(
            "wip/done/2026-09-01-closed.md",
            entry(status="**Status:** done (2026-09-02)", blocks=None),
        )
        cases = {
            "no-acceptance": (entry(body="**Fix:** do it."), ["no-acceptance"], ["no-fix"]),
            "no-fix": (entry(body="**Acceptance:** it works."), ["no-fix"], ["no-acceptance"]),
            "empty-fix": (entry(body="**Fix:**\n**Acceptance:** ok"), ["no-fix"], []),
            "question": (
                entry(body="**Fix:** a\n**Acceptance:** b\n**Open question:** which one?"),
                ["open-question"],
                [],
            ),
            "no-question": (
                entry(body="**Fix:** a\n**Acceptance:** b\n**Open question:** none"),
                [],
                ["open-question"],
            ),
            "dead": (
                entry(body="In `src/gone.py` and `src/app.py`.\n**Fix:** a\n**Acceptance:** b"),
                ["dead-path:[src/gone.py]"],
                [],
            ),
            "links": (
                entry(body="See [[2026-09-01-closed]].\n**Fix:** a\n**Acceptance:** b"),
                ["links-closed:[2026-09-01-closed]"],
                [],
            ),
            "links-bare": (
                entry(body="Like 2026-09-01-closed.md.\n**Fix:** a\n**Acceptance:** b"),
                ["links-closed:[2026-09-01-closed]"],
                [],
            ),
            "blocker": (entry(blocks="yes — data loss"), ["BLOCKS-RELEASE"], []),
            "clean": (
                entry(),
                [],
                [
                    "no-fix",
                    "no-acceptance",
                    "open-question",
                    "stale",
                    "dead-path",
                    "links-closed",
                    "BLOCKS-RELEASE",
                ],
            ),
        }
        for name, (text, _, _) in cases.items():
            self.write(f"wip/todo_nr/2026-10-01-{name}.md", text)
        rc, out = self.wip("refine")
        self.assertEqual(rc, 0, out)
        for name, (_, present, absent) in cases.items():
            with self.subTest(name):
                line = self.refine_line(out, f"2026-10-01-{name}")
                for flag in present:
                    self.assertIn(flag, line.split())
                for flag in absent:
                    self.assertFalse(any(tok.startswith(flag) for tok in line.split()[5:]), line)

    def test_stale_follows_the_last_commit(self):
        self.write("wip/todo_nr/2026-01-01-old.md", entry(noted="2020-01-01"))
        self.commit("wip/todo_nr/2026-01-01-old.md", date="2020-01-01T12:00:00+00:00")
        self.write("wip/todo_nr/2026-01-01-fresh.md", entry(noted="2020-01-01"))
        self.commit("wip/todo_nr/2026-01-01-fresh.md")
        rc, out = self.wip("refine")
        self.assertEqual(rc, 0)
        self.assertIn("stale", self.refine_line(out, "2026-01-01-old").split())
        fresh = self.refine_line(out, "2026-01-01-fresh")
        self.assertNotIn("stale", fresh.split())
        self.assertIn("idle 0d", fresh)
        self.assertRegex(fresh, r"age \d{4,}d", "age counts from Noted")

    def test_crowded_theme_and_thresholds(self):
        for i in range(3):
            self.write(f"wip/todo_nr/2026-10-01-crowd-{i}.md", entry(theme="crowd"))
        self.write("wip/todo/2026-10-01-alone.md", entry(theme="alone"))
        rc, out = self.wip("refine")
        self.assertEqual(rc, 0)
        self.assertIn("crowded theme: crowd (3)", out)
        self.assertNotIn("crowded theme: alone", out)
        self.assertIn("open: 4", out)
        self.assertIn("wip/todo/: 1 of a WIP limit of 2", out)
        self.assertIn("wip/todo_nr/: 3 — refinement suggested", out)

    def test_below_refinement_threshold(self):
        self.write("wip/todo_nr/2026-10-01-one.md", entry())
        _, out = self.wip("refine")
        self.assertIn("wip/todo_nr/: 1", out)
        self.assertNotIn("refinement suggested", out)

    # --- list, themes, help ---

    def test_list_marks_blockers(self):
        self.write("wip/todo/2026-10-01-blocker.md", entry(title="Data loss", blocks="yes — x"))
        self.write("wip/todo/2026-10-01-normal.md", entry(title="Cosmetic"))
        self.write("wip/todo_nr/2026-10-01-later.md", entry(title="Later"))
        rc, out = self.wip("list")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"(?m)^\s+! 2026-10-01-blocker — Data loss$")
        self.assertRegex(out, r"(?m)^\s+2026-10-01-normal — Cosmetic$")
        self.assertNotIn("2026-10-01-later", out, "list defaults to todo")
        self.assertIn("2026-10-01-later", self.wip("list", "all")[1])

    def test_themes(self):
        self.write("wip/todo/2026-10-01-a.md", entry(theme="alpha"))
        self.write("wip/todo_nr/2026-10-01-b.md", entry(theme="alpha"))
        self.write("wip/todo_nr/2026-10-01-c.md", entry(theme="beta"))
        rc, out = self.wip("themes")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"(?m)^alpha\s+1\s+1\s+0\s+2$")
        self.assertRegex(out, r"(?m)^beta\s+0\s+1\s+0\s+1$")

    def test_help_and_usage(self):
        rc, out = self.wip("--help")
        self.assertEqual(rc, 0)
        self.assertIn("refine", out)
        self.assertEqual(self.wip("bogus")[0], 2)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/wip.py")


if __name__ == "__main__":
    unittest.main()
