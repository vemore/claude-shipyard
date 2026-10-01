"""Selftest of scripts/worktree_setup.sh in a sandbox repository.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
The sandbox (tempfile.mkdtemp) is a git repository with its own scripts/lib/tooling.conf (two
components, a deploy file) and a fake scripts/check.sh that records each call, notes whether the
setup marker existed at that moment, and fails on demand. The real worktree_setup.sh is run
against it with DIR. No network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "worktree_setup.sh")
MARKER = ".sbx-setup-in-progress"

CONF = f"""# sandbox tooling.conf
PROJECT_SLUG=sbx
SETUP_MARKER={MARKER}
COMPONENTS='api web'
DEPLOY_ENV_FILE=deploy.env
"""

FAKE_CHECK = f"""#!/usr/bin/env bash
# fake check.sh: records the call and whether the setup marker exists; fails on demand.
root=$(git rev-parse --show-toplevel)
if [ -e "$root/{MARKER}" ]; then m=present; else m=absent; fi
echo "$* marker=$m" >> "$FAKE_CHECK_LOG"
if [ "${{FAKE_CHECK_FAIL:-}}" = "$2" ]; then echo "boom" >&2; exit 3; fi
exit 0
"""


class WorktreeSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="wt-setup-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.main = os.path.join(self.tmp, "main")
        self.log = os.path.join(self.tmp, "check.log")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(
            GIT_AUTHOR_NAME="Selftest",
            GIT_AUTHOR_EMAIL="selftest@example.invalid",
            GIT_COMMITTER_NAME="Selftest",
            GIT_COMMITTER_EMAIL="selftest@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=self.tmp,
            FAKE_CHECK_LOG=self.log,
        )
        self.env.pop("FAKE_CHECK_FAIL", None)
        os.makedirs(os.path.join(self.main, "scripts", "lib"))
        self.write("scripts/lib/tooling.conf", CONF)
        self.write("scripts/check.sh", FAKE_CHECK)
        os.chmod(os.path.join(self.main, "scripts", "check.sh"), 0o755)
        self.write(".gitignore", f"/{MARKER}\n/deploy.env\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "sandbox")

    def write(self, rel, text):
        with open(os.path.join(self.main, rel), "w", encoding="utf-8") as fh:
            fh.write(text)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.main, env=self.env, check=True, capture_output=True)

    def setup_tree(self, *args, cwd=None, **env):
        full_env = dict(self.env, **env)
        return subprocess.run(
            ["bash", SCRIPT, *args],
            capture_output=True,
            text=True,
            cwd=cwd or self.tmp,
            env=full_env,
            timeout=60,
        )

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def add_worktree(self, name="wt", branch="feat/x"):
        path = os.path.join(self.tmp, name)
        self.git("worktree", "add", "-q", "-b", branch, path)
        return path

    def test_success_marker_during_setup_then_removed(self):
        proc = self.setup_tree(self.main)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), ["setup api marker=present", "setup web marker=present"])
        self.assertFalse(os.path.exists(os.path.join(self.main, MARKER)))
        last = proc.stdout.strip().splitlines()[-1]
        self.assertEqual(last, f"ready: {os.path.realpath(self.main)} (main)")

    def test_failure_leaves_the_marker(self):
        proc = self.setup_tree(self.main, FAKE_CHECK_FAIL="web")
        self.assertNotEqual(proc.returncode, 0)
        marker = os.path.join(self.main, MARKER)
        self.assertTrue(os.path.exists(marker), "the marker stays on failure, on purpose")
        with open(marker, encoding="utf-8") as fh:
            content = fh.read().strip()
        self.assertRegex(content, r"^pid \d+ started \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ branch main$")
        self.assertIn(f"rm {marker}", proc.stderr)
        self.assertNotIn("ready:", proc.stdout)

    def test_no_component_skips_exactly_that_one(self):
        proc = self.setup_tree(self.main, "--no-web")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), ["setup api marker=present"])

    def test_unknown_component_is_an_error(self):
        proc = self.setup_tree(self.main, "--no-bogus")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("'bogus' is not a component", proc.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(os.path.exists(os.path.join(self.main, MARKER)))

    def test_deploy_links_the_main_checkout_file(self):
        self.write("deploy.env", "TARGET=example.invalid\n")
        tree = self.add_worktree()
        proc = self.setup_tree("--deploy", tree)  # flag before DIR, as the skills write it
        self.assertEqual(proc.returncode, 0, proc.stderr)
        link = os.path.join(tree, "deploy.env")
        self.assertTrue(os.path.islink(link), "linked, never copied")
        self.assertEqual(
            os.path.realpath(link), os.path.realpath(os.path.join(self.main, "deploy.env"))
        )
        self.assertEqual(
            proc.stdout.strip().splitlines()[-1], f"ready: {os.path.realpath(tree)} (feat/x)"
        )

    def test_deploy_without_a_source_file_warns(self):
        tree = self.add_worktree()
        proc = self.setup_tree(tree, "--deploy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("warning:", proc.stderr)
        self.assertFalse(os.path.lexists(os.path.join(tree, "deploy.env")))

    def test_no_link_without_deploy(self):
        self.write("deploy.env", "TARGET=example.invalid\n")
        tree = self.add_worktree()
        proc = self.setup_tree(tree)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.lexists(os.path.join(tree, "deploy.env")))

    def test_deploy_without_a_deploy_target(self):
        self.write(
            "scripts/lib/tooling.conf",
            CONF.replace("DEPLOY_ENV_FILE=deploy.env", "DEPLOY_ENV_FILE="),
        )
        proc = self.setup_tree(self.main, "--deploy")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("this project has no deploy target", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.main, MARKER)))

    def test_dir_outside_a_repository(self):
        outside = os.path.join(self.tmp, "outside")
        os.mkdir(outside)
        proc = self.setup_tree(outside)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not inside a git repository", proc.stderr)

    def test_default_dir_is_the_current_directory(self):
        tree = self.add_worktree()
        proc = self.setup_tree(cwd=os.path.join(tree, "scripts"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip().endswith(f"ready: {os.path.realpath(tree)} (feat/x)"))

    def test_missing_conf_key(self):
        self.write("scripts/lib/tooling.conf", "SETUP_MARKER=.m\nCOMPONENTS='api'\n")
        proc = self.setup_tree(self.main)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing key DEPLOY_ENV_FILE in scripts/lib/tooling.conf", proc.stderr)

    def test_arguments_in_any_order(self):
        self.write("deploy.env", "TARGET=example.invalid\n")
        tree = self.add_worktree()
        proc = self.setup_tree("--no-web", tree, "--deploy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.calls(), ["setup api marker=present"])
        self.assertTrue(os.path.islink(os.path.join(tree, "deploy.env")))

    def test_argument_errors_write_no_marker(self):
        cases = [
            ("unknown option", ("--bogus", self.main), "unknown option: --bogus"),
            ("two directories", (self.main, self.main), "only one DIR is accepted"),
            ("unknown component after DIR", (self.main, "--deploy", "--no-x"), "'x' is not a"),
        ]
        for desc, args, message in cases:
            with self.subTest(desc):
                proc = self.setup_tree(*args)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertIn(message, proc.stderr)
                self.assertFalse(os.path.exists(os.path.join(self.main, MARKER)))
                self.assertEqual(self.calls(), [])

    def test_missing_check_sh_is_refused_before_the_marker(self):
        os.remove(os.path.join(self.main, "scripts", "check.sh"))
        proc = self.setup_tree(self.main)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("scripts/check.sh is missing or not executable", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.main, MARKER)))
        proc = self.setup_tree(self.main, "--no-api", "--no-web")  # nothing to install
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ready:", proc.stdout)

    def test_idempotent(self):
        self.assertEqual(self.setup_tree(self.main).returncode, 0)
        proc = self.setup_tree(self.main)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(re.search(r"ready: .* \(main\)$", proc.stdout.strip()))

    def test_help_and_executable(self):
        proc = self.setup_tree("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("rm <tree>/<SETUP_MARKER>", proc.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/worktree_setup.sh")


if __name__ == "__main__":
    unittest.main()
