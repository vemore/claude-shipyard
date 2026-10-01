"""Selftest of scripts/selftest.sh in a sandbox project.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Each case copies the real selftest.sh into a throwaway project (tempfile.mkdtemp) whose
scripts/selftest/ and .claude/skills/*/scripts/ hold tiny generated test files, runs it with
SELFTEST_PYTHON set to this interpreter, and checks the exit code and the summary line. No network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "selftest.sh")


def test_file(passing=1, failing=0):
    lines = ["import unittest", "", "", "class T(unittest.TestCase):"]
    for i in range(passing):
        lines += [f"    def test_ok_{i}(self):", "        self.assertTrue(True)", ""]
    for i in range(failing):
        lines += [f"    def test_ko_{i}(self):", "        self.assertTrue(False)", ""]
    if not passing and not failing:
        lines += ["    pass", ""]
    return "\n".join(lines) + "\n"


class Selftest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="selftest-sh-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = os.path.join(self.tmp, "project")
        os.makedirs(os.path.join(self.project, "scripts"))
        shutil.copy2(SCRIPT, os.path.join(self.project, "scripts", "selftest.sh"))

    def write(self, rel, text):
        path = os.path.join(self.project, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_selftest(self, *args, cwd=None):
        env = dict(os.environ, SELFTEST_PYTHON=sys.executable)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        return subprocess.run(
            ["bash", os.path.join(self.project, "scripts", "selftest.sh"), *args],
            capture_output=True,
            text=True,
            cwd=cwd or self.project,
            env=env,
            timeout=120,
        )

    def standard_tree(self):
        self.write("scripts/selftest/test_a.py", test_file(2))
        self.write(".claude/skills/one/scripts/test_x.py", test_file(1))
        self.write(".claude/skills/two/scripts/test_x.py", test_file(3))  # same module name
        self.write(".claude/skills/three/scripts/probe.sh", "echo probe\n")  # no test file

    def test_every_folder_runs_and_the_total_adds_up(self):
        self.standard_tree()
        proc = self.run_selftest()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[-1], "selftest.sh: OK, 6 tests in 3 folder(s)")
        self.assertIn("skip .claude/skills/three/scripts: no test_*.py", proc.stdout)
        for folder in (
            "scripts/selftest",
            ".claude/skills/one/scripts",
            ".claude/skills/two/scripts",
        ):
            self.assertIn(f"== {folder}", proc.stdout)

    def test_a_failure_fails_the_run_and_the_others_still_run(self):
        self.standard_tree()
        self.write(".claude/skills/one/scripts/test_x.py", test_file(1, failing=1))
        proc = self.run_selftest()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAILED in .claude/skills/one/scripts", proc.stderr)
        self.assertIn("== .claude/skills/two/scripts", proc.stdout, "the next folder still ran")
        self.assertRegex(proc.stderr, r"\(7 tests ran in 3 folder\(s\)\)")

    def test_an_import_error_fails_the_run(self):
        self.write("scripts/selftest/test_a.py", test_file(1))
        self.write("scripts/selftest/test_broken.py", "import no_such_module_for_selftest\n")
        proc = self.run_selftest()
        self.assertEqual(proc.returncode, 1, proc.stdout)

    def test_zero_tests_is_a_failure(self):
        cases = [
            ("nothing at all", {}),
            ("an empty selftest folder", {"scripts/selftest/README": "x\n"}),
            ("test files without tests", {"scripts/selftest/test_a.py": test_file(0)}),
        ]
        for desc, files in cases:
            with self.subTest(desc):
                shutil.rmtree(os.path.join(self.project, "scripts", "selftest"), ignore_errors=True)
                for rel, text in files.items():
                    self.write(rel, text)
                proc = self.run_selftest()
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("FAILED", proc.stderr)

    def test_a_folder_that_runs_nothing_fails_even_next_to_green_ones(self):
        # Python 3.9 says "Ran 0 tests, OK", 3.12 exits 5: the script answers the same on both.
        self.write("scripts/selftest/test_a.py", test_file(2))
        self.write(".claude/skills/one/scripts/test_empty.py", test_file(0))
        proc = self.run_selftest()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(
            ".claude/skills/one/scripts holds test_*.py files but ran no test", proc.stderr
        )

    def test_runs_from_any_directory(self):
        self.standard_tree()
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.mkdir(elsewhere)
        proc = self.run_selftest(cwd=elsewhere)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.endswith("OK, 6 tests in 3 folder(s)\n"), proc.stdout)

    def test_writes_no_bytecode(self):
        self.write("scripts/selftest/helper_mod.py", "VALUE = 1\n")
        self.write(
            "scripts/selftest/test_a.py",
            test_file(1).replace("import unittest", "import unittest\nimport helper_mod"),
        )
        proc = self.run_selftest()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        found = [d for d, _, _ in os.walk(self.project) if os.path.basename(d) == "__pycache__"]
        self.assertEqual(found, [], "a run must leave no untracked __pycache__")

    def test_usage(self):
        proc = self.run_selftest("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Why", proc.stdout)
        self.assertNotIn("set -uo", proc.stdout)
        proc = self.run_selftest("extra")
        self.assertEqual(proc.returncode, 2)

    def test_executable_and_bash_3_2_compatible(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/selftest.sh")
        with open(SCRIPT, encoding="utf-8") as fh:
            code = "\n".join(ln for ln in fh.read().splitlines() if not ln.lstrip().startswith("#"))
        constructs = (r"\bmapfile\b", r"\breadarray\b", r"declare -A", r"\$\{[a-z_]+,,", r"&>>")
        for construct in constructs:
            self.assertIsNone(re.search(construct, code), f"not in bash 3.2: {construct}")
        self.assertEqual(
            subprocess.run(["bash", "-n", SCRIPT], capture_output=True, timeout=30).returncode, 0
        )


if __name__ == "__main__":
    unittest.main()
