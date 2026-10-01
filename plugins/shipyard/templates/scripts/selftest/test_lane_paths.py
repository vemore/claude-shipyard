"""Selftest of scripts/lane_paths.py: sandbox git repositories, no network, a few seconds.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Each case builds a throwaway repository (tempfile.mkdtemp) with its own scripts/lib/tooling.conf
and runs the real script there. The `Project` case reads the project's own tooling.conf and runs
only once this file is vendored into a project.
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
SCRIPT = os.path.join(ROOT, "scripts", "lane_paths.py")
IN_PROJECT = os.path.isfile(os.path.join(ROOT, "scripts", "lib", "tooling.conf"))

CONF = """# sandbox tooling.conf
PROJECT_SLUG=sandbox
LANE_C_RE='^src/auth/|^migrations/|PRIVACY\\.md$'
DEPLOY_PATHS_RE='^src/|^pyproject\\.toml$'
"""


def clean_env(**extra):
    """The caller's environment minus GIT_*: a git hook running this suite sets GIT_DIR or
    GIT_INDEX_FILE, which would point the sandbox's `git rev-parse` at the outer repository."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", **extra)
    return env


class LanePaths(unittest.TestCase):
    def sandbox(self, conf=CONF, git=True):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="lane-paths-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(self.root)
        if git:
            subprocess.run(["git", "init", "-q", self.root], check=True, env=self.env(), timeout=30)
        if conf is not None:
            os.makedirs(os.path.join(self.root, "scripts", "lib"))
            with open(os.path.join(self.root, "scripts", "lib", "tooling.conf"), "w") as fh:
                fh.write(conf)
        return self

    def env(self):
        return clean_env(GIT_CEILING_DIRECTORIES=self.tmp)

    def run_mode(self, mode, stdin, cwd=None):
        args = [mode] if mode is not None else []
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=cwd or self.root,
            env=self.env(),
            timeout=30,
        )

    def test_no_match_exits_1_and_prints_nothing(self):
        out = self.sandbox().run_mode("lane-c", "README.md\ndocs/guide.md\n")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertEqual(out.stdout, "")

    def test_one_match_exits_0_and_prints_only_it(self):
        out = self.sandbox().run_mode("lane-c", "README.md\nsrc/auth/login.py\nsrc/cli.py\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["src/auth/login.py"])

    def test_matches_keep_input_order_and_print_once(self):
        stdin = "docs/PRIVACY.md\nsrc/auth/a.py\nmigrations/001.sql\nsrc/auth/a.py\n"
        out = self.sandbox().run_mode("lane-c", stdin)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            out.stdout.splitlines(), ["docs/PRIVACY.md", "src/auth/a.py", "migrations/001.sql"]
        )

    def test_deploy_mode_reads_deploy_paths_re_not_lane_c_re(self):
        out = self.sandbox().run_mode("deploy", "pyproject.toml\nmigrations/001.sql\nsrc/cli.py\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["pyproject.toml", "src/cli.py"])

    def test_empty_regex_matches_nothing(self):
        box = self.sandbox("LANE_C_RE=''\nDEPLOY_PATHS_RE=\n")
        for mode in ("lane-c", "deploy"):
            out = box.run_mode(mode, "src/auth/login.py\npyproject.toml\nREADME.md\n")
            self.assertEqual(out.returncode, 1, f"{mode}: {out.stderr}")
            self.assertEqual(out.stdout, "", mode)

    def test_one_path_per_line_spaces_included(self):
        out = self.sandbox().run_mode("lane-c", "  src/auth/my file.py  \n\n docs/my PRIVACY.md\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["src/auth/my file.py", "docs/my PRIVACY.md"])

    def test_empty_stdin_exits_1(self):
        out = self.sandbox().run_mode("lane-c", "")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertEqual(out.stdout, "")

    def test_usage_errors_exit_2(self):
        box = self.sandbox()
        for mode in (None, "lane-b"):
            with self.subTest(mode):
                out = box.run_mode(mode, "src/auth/a.py\n")
                self.assertEqual(out.returncode, 2)
                self.assertIn("usage", out.stderr)

    def test_missing_conf_exits_2(self):
        out = self.sandbox(conf=None).run_mode("lane-c", "src/auth/login.py\n")
        self.assertEqual(out.returncode, 2)
        self.assertIn("tooling.conf", out.stderr)

    def test_missing_key_exits_2(self):
        out = self.sandbox("LANE_C_RE='^src/'\n").run_mode("deploy", "src/a.py\n")
        self.assertEqual(out.returncode, 2)
        self.assertIn("missing key DEPLOY_PATHS_RE", out.stderr)

    def test_invalid_regex_exits_2(self):
        out = self.sandbox("LANE_C_RE='^src/(auth'\nDEPLOY_PATHS_RE=''\n").run_mode(
            "lane-c", "src/a\n"
        )
        self.assertEqual(out.returncode, 2)
        self.assertIn("LANE_C_RE", out.stderr)

    def test_outside_a_git_repository_exits_2(self):
        out = self.sandbox(git=False).run_mode("lane-c", "src/auth/login.py\n")
        self.assertEqual(out.returncode, 2)
        self.assertIn("git repository", out.stderr)

    def test_conf_is_read_from_the_repository_root_not_the_cwd(self):
        box = self.sandbox()
        sub = os.path.join(box.root, "src", "deep")
        os.makedirs(sub)
        out = box.run_mode("lane-c", "src/auth/login.py\n", cwd=sub)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_stdin_is_read_to_the_end_even_when_the_conf_is_unreadable(self):
        box = self.sandbox(conf=None)
        proc = subprocess.Popen(
            [sys.executable, SCRIPT, "lane-c"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=box.root,
            env=box.env(),
            bufsize=0,  # unbuffered: a closed pipe surfaces in the loop, not in communicate()
        )
        line = b"some/long/path/that/fills/the/pipe/buffer/quickly.py\n"
        try:
            for _ in range(40000):  # about 2 MB, far above any pipe buffer
                proc.stdin.write(line)
        except BrokenPipeError:
            proc.kill()
            proc.communicate()
            self.fail("lane_paths.py exited before reading stdin: the producer got SIGPIPE")
        _, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 2, err)
        self.assertIn(b"tooling.conf", err)

    def test_help_answers_and_script_is_executable(self):
        out = subprocess.run(
            [sys.executable, SCRIPT, "--help"], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn("lane-c", out.stdout)
        self.assertIn("Why", out.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/lane_paths.py")


@unittest.skipUnless(IN_PROJECT, "project contract: runs once vendored into a project")
class Project(unittest.TestCase):
    def test_the_project_tooling_conf_is_readable(self):
        for mode in ("lane-c", "deploy"):
            with self.subTest(mode):
                out = subprocess.run(
                    [sys.executable, SCRIPT, mode],
                    input="README.md\n",
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                    env=clean_env(),
                    timeout=30,
                )
                self.assertIn(out.returncode, (0, 1), f"{mode}: {out.stderr}")


if __name__ == "__main__":
    unittest.main()
