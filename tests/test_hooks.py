#!/usr/bin/env python3
"""Self-test of the shipyard plugin's Claude Code hooks and of the vendored commit gate.

Usage:
  python3 -m unittest discover -s tests -p 'test_hooks.py'   # from the plugin repository
  python3 tests/test_hooks.py -v                              # this file alone

Guarantees: every refusal, every look-alike that must pass, the parser's verdicts, the gates,
the secret, wip and branch checks, the pull-request check at Stop/SubagentStop, the session
notes (branch, worktrees, deliveries, vendored version, team identity), the post-edit report,
the inertness of every hook in a repository without scripts/lib/tooling.conf, the vendored
.githooks/pre-commit + scripts/precommit.py pair, and the hooks/hooks.json wiring are run
against throwaway git sandboxes. Offline and in seconds: a fake ``gh`` on PATH reads a JSON
scenario, a stub ``scripts/check.sh`` records what it was asked, a fake plugin root carries
the ``plugin.json`` version, and the sandbox points a GitHub URL at a local bare repository
through ``url.<path>.insteadOf``. Sandboxes and stubs: tests/_hooks_support.py.

Does not cover: the real GitHub API, a real project's gates (scripts/check.sh is a stub), the
real bin/vendor.py and scripts/owners.py (stubs with their contract interface), or Claude
Code's own hook runner (the hooks run as plain processes with the documented payload).

Why it exists: the interesting cases are the ones that look like a violation and are not.
Without this table run on every push, the first rule change breaks a guard silently — and a
broken guard is indistinguishable from one that lets things through.
"""

import ast
import concurrent.futures
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hooks_support import (API_KEY, CLOUD_KEY, HOOKS, HOOKS_JSON, KEBAB_LOOK_ALIKES,  # noqa: E402
                            NOT_BOOTSTRAPPED, NS, PLUGIN, PRE_COMMIT, PRECOMMIT_PY, PRIVATE_KEY,
                            SERVICE_ACCOUNT, Sandbox, SandboxCase, run_hook)

sys.path.insert(0, str(HOOKS))
import parse_command  # noqa: E402


# =========================================================================== refusals

class TestRefusalsAndLookAlikes(unittest.TestCase):
    """Commands judged without running them: one shared sandbox."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def judge_all(self, commands):
        """Run the guard on (command, cwd) pairs concurrently: none of them writes anything."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda pair: self.sb.guard(pair[0], cwd=pair[1]), commands))

    def test_refused(self):
        sb = self.sb
        wt, main = str(sb.wt), str(sb.main)
        cases = [
            ("git push --force origin feat/x", wt, "force-push"),
            ("git push -f origin feat/x", wt, "force-push"),
            ("git push -fu origin feat/x", wt, "force-push"),
            ("git push origin +feat/x", wt, "force-push"),
            ("git push --force-with-lease origin feat/x", wt, "force-push"),
            ("git push --force-with-lease=feat/x:abc origin feat/x", wt, "force-push"),
            ("git push --force-if-includes origin feat/x", wt, "force-push"),
            ("git push --mirror origin", wt, "force-push"),
            ("git push origin main", wt, "push-main"),
            ("git push origin feat/x:main", wt, "push-main"),
            ("git push origin HEAD:refs/heads/main", wt, "push-main"),
            ("git push --all origin", wt, "push-main"),
            ("git push origin --delete main", wt, "push-main"),
            ("git push", main, "push-main"),
            ("git push origin HEAD", main, "push-main"),
            ("gh pr create --base feat/y --title t --body b", wt, "stacked-pr"),
            ("gh pr create --base=feat/y", wt, "stacked-pr"),
            ("gh pr create -B feat/y", wt, "stacked-pr"),
            ("gh pr merge 12", wt, "merge-squash"),
            ("gh pr merge 12 --merge", wt, "merge-squash"),
            ("gh pr merge 12 --rebase", wt, "merge-squash"),
            ("gh pr merge 12 -r", wt, "merge-squash"),
            ("gh pr merge 12 --admin --squash", wt, "merge-admin"),
            ("gh api -X PUT repos/o/r/pulls/12/merge", wt, "merge-api"),
            ("git config {}.allowStackedPr true".format(NS), wt, "user-only-config"),
            ("git config --add {}.deliveryAcknowledged 12".format(NS), wt, "user-only-config"),
            ("sudo -u x git push -f", wt, "force-push"),
            ("env A=1 git push -f", wt, "force-push"),
            ("time git push --force", wt, "force-push"),
            ("git -c a.b=c -C {} push --force".format(wt), main, "force-push"),
            ("bash -c 'git push --force'", wt, "force-push"),
            ('sh -lc "git push origin main"', wt, "push-main"),
            ('eval "git push -f"', wt, "force-push"),
        ]
        results = self.judge_all([(command, cwd) for command, cwd, _ in cases])
        for (command, _cwd, rule), (code, _, err) in zip(cases, results):
            with self.subTest(command=command):
                self.assertEqual(code, 2, err)
                self.assertIn("({})".format(rule), err)
                self.assertIn("Remedy", err)

    def test_look_alikes_pass(self):
        sb = self.sb
        wt = str(sb.wt)
        heredoc = "cat > notes.md <<'EOF'\ngit push --force origin main\nEOF"
        cases = [
            "git push --dry-run --force origin feat/x",
            "git push --help",
            "git push -u origin feat/x",
            "git push",
            "git push origin HEAD",
            "gh pr create --base main --title t --body 'stacked on feat/y'",
            "gh pr create --title t --body b",
            "gh pr merge 12 --squash --delete-branch",
            "gh pr merge 12 --squash --match-head-commit 0123abc",
            "gh pr merge 12 -sd",
            'gh pr merge 12 --squash --body "never use --admin"',
            "gh pr merge --help",
            "gh api -X PUT repos/o/r/pulls/12/update-branch",
            "git config --get {}.allowStackedPr".format(NS),
            "git config branch.feat/x.noPullRequest true",
            "git config --unset {}.allowStackedPr".format(NS),
            'echo "git push --force"',
            heredoc,
            'git commit -m "never git push --force"',
            "grep -- --force f",
        ]
        results = self.judge_all([(command, wt) for command in cases])
        for command, (code, _, err) in zip(cases, results):
            with self.subTest(command=command):
                self.assertEqual(code, 0, err)

    def test_merge_remedies_name_the_head_commit(self):
        """The remedy recommends --match-head-commit, never --delete-branch (which errors after
        a successful merge when a worktree holds the branch); the hook still accepts it."""
        commands = ["gh pr merge 12", "gh pr merge 12 --admin --squash",
                    "gh api -X PUT repos/o/r/pulls/12/merge"]
        results = self.judge_all([(command, str(self.sb.wt)) for command in commands])
        for command, (code, _, err) in zip(commands, results):
            with self.subTest(command=command):
                self.assertEqual(code, 2, err)
                self.assertIn("gh pr merge <n> --squash --match-head-commit <sha>", err)
                self.assertNotIn("--delete-branch", err)

    def test_stacked_pr_allowed_by_user_key(self):
        sb = Sandbox()
        self.addCleanup(sb.cleanup)
        sb.git("config", "{}.allowStackedPr".format(NS), "true")
        code, _, err = sb.guard("gh pr create --base feat/y")
        self.assertEqual(code, 0, err)


# =========================================================================== parser

class TestParser(unittest.TestCase):
    """Verdicts of parse_command.parse (no repository needed)."""

    CONF = {"DEFAULT_BRANCH": "main", "GIT_CONFIG_NS": NS}
    WT = "/abs/wt"
    CWD = "/abs/main"

    def verdict(self, command, cwd=None):
        return parse_command.parse(command, cwd or self.CWD, self.CONF)

    def commit(self, command):
        commits = self.verdict(command)["commits"]
        self.assertEqual(len(commits), 1, commits)
        return commits[0]

    def test_commit_repository(self):
        wt = self.WT
        cases = [
            ("cd {} && git commit -m x".format(wt), wt),
            ("git -C {} commit -m x".format(wt), wt),
            ('W={}; git -C "$W" commit -m x'.format(wt), wt),
            ("export W={}; cd $W && git commit -m x".format(wt), wt),
            ('W={} git -C "$W" commit -m x'.format(wt), None),
            ('cd "$INHERITED" && git commit -m x', None),
            ("cd $(git rev-parse --show-toplevel) && git commit -m x", None),
            ("X=$(date); git commit -m x", self.CWD),
            ("(cd /tmp); git commit -m x", self.CWD),
            ("git -C /abs -C wt commit -m x", wt),
            ("pushd {} && git commit -m x".format(wt), wt),
            ("cd {} && popd; git commit -m x".format(wt), None),
            ("cd - && git commit -m x", None),
            ("git --git-dir=/abs/wt/.git commit -m x", None),
            ("bash -c 'cd {} && git commit -m x'".format(wt), wt),
            ("cd sub && git commit -m x", self.CWD + "/sub"),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(self.commit(command)["cwd"], expected)

    def test_commit_shape(self):
        self.assertTrue(self.commit("git add . && git commit -am x")["all"])
        self.assertTrue(self.commit("git commit --amend --no-edit")["amend"])
        self.assertEqual(self.commit("git commit -m x -- a.py b.py")["pathspecs"],
                         ["a.py", "b.py"])
        self.assertEqual(self.commit("git commit -m 'a b' -F f.txt c.py")["pathspecs"], ["c.py"])
        self.assertFalse(self.commit("git commit -m x")["all"])

    def test_not_a_commit(self):
        for command in ("git commit --dry-run", "git log --grep=commit", "git commit -h",
                        "echo git commit", "ls | xargs git rm"):
            with self.subTest(command=command):
                verdict = self.verdict(command)
                self.assertEqual(verdict["commits"], [])
                self.assertEqual(verdict["blocks"], [])

    def test_heredoc_message_is_a_commit(self):
        command = ("git commit -m \"$(cat <<'EOF'\nfix: x\n\ngit push --force origin main\n"
                   "EOF\n)\"")
        verdict = self.verdict(command)
        self.assertTrue(verdict["parse_ok"])
        self.assertEqual(len(verdict["commits"]), 1)
        self.assertEqual(verdict["blocks"], [])

    def test_unreadable_line(self):
        verdict = self.verdict('git commit -m "unclosed')
        self.assertFalse(verdict["parse_ok"])
        self.assertEqual(verdict["blocks"], [])
        commit = verdict["commits"][0]
        self.assertEqual((commit["all"], commit["amend"], commit["cwd"]),
                         (True, True, self.CWD))
        verdict = self.verdict('cd /abs/wt && git commit -m "unclosed')
        self.assertIsNone(verdict["commits"][0]["cwd"])
        verdict = self.verdict("git push --force 'unclosed")
        self.assertEqual(verdict["blocks"], [])

    def test_launchers_are_unwrapped(self):
        for command in ("timeout 10 git push -f origin x", "timeout -s KILL 5 git push -f",
                        "nice -n 5 git push --force", "nohup git push --force &",
                        "ls | xargs git push --force", "if true; then git push -f; fi",
                        "command git push -f", "bash -c 'bash -c \"git push -f\"'"):
            with self.subTest(command=command):
                rules = [b["rule"] for b in self.verdict(command)["blocks"]]
                self.assertEqual(rules, ["force-push"])
        self.assertIsNone(self.commit("ls | xargs -I{} git -C {} commit -m x")["cwd"])
        self.assertTrue(self.commit("echo a.py | xargs git commit -m x")["all"])

    def test_glued_punctuation(self):
        self.assertEqual(len(self.verdict("X=$(pwd);git commit -m x")["commits"]), 1)
        self.assertEqual(len(self.verdict("(git status)&&git commit -m x")["commits"]), 1)

    def test_comments_and_hashes(self):
        self.assertEqual(self.verdict("echo hi # git push --force")["blocks"], [])
        rules = [b["rule"] for b in self.verdict("git push origin feat#1 --force")["blocks"]]
        self.assertEqual(rules, ["force-push"])

    def test_pushes(self):
        push = self.verdict("git push")["pushes"][0]
        self.assertTrue(push["bare"])
        push = self.verdict("git push origin @")["pushes"][0]
        self.assertTrue(push["head_ref"])
        self.assertFalse(self.verdict("git push --tags")["pushes"][0]["bare"])
        rules = [b["rule"] for b in self.verdict("git push origin :main")["blocks"]]
        self.assertEqual(rules, ["push-main"])

    def test_gh_flags(self):
        self.assertEqual(self.verdict("gh pr create -Bfeat/y")["blocks"][0]["rule"], "stacked-pr")
        self.assertEqual(self.verdict("gh pr create -t 'base -B x' --base main")["blocks"], [])
        self.assertEqual(self.verdict("gh api --method=PUT /repos/o/r/pulls/3/merge")
                         ["blocks"][0]["rule"], "merge-api")
        self.assertEqual(self.verdict("gh api repos/o/r/pulls/3/merge")["blocks"], [])
        self.assertEqual(self.verdict("gh pr merge 3 --disable-auto")["blocks"], [])

    def test_config_writes(self):
        verdict = self.verdict("git config set {}.allowStackedPr true".format(NS))
        self.assertEqual(verdict["blocks"][0]["rule"], "user-only-config")
        self.assertEqual(verdict["config_writes"][0]["key"], NS + ".allowstackedpr")
        self.assertEqual(self.verdict("git config --bool {}.allowStackedPr".format(NS))
                         ["blocks"], [])

    def test_staging_is_recorded(self):
        verdict = self.verdict("git add -f .env && git commit -m x")
        stage = verdict["stages"][0]
        self.assertTrue(stage["force"])
        self.assertLess(stage["seq"], verdict["commits"][0]["seq"])

    def test_unknown_repo_is_refused_by_the_hook(self):
        sb = Sandbox()
        self.addCleanup(sb.cleanup)
        wt = str(sb.wt)
        for command in ('W={} git -C "$W" commit -m x'.format(wt),
                        'cd "$INHERITED" && git commit -m x',
                        "cd $(git rev-parse --show-toplevel) && git commit -m x",
                        'cd {} && git commit -m "unclosed'.format(wt),
                        "cd - && git push"):
            with self.subTest(command=command):
                code, _, err = sb.guard(command)
                self.assertEqual(code, 2, err)
                self.assertIn("(unknown-repo)", err)
                self.assertIn("git -C <absolute path>", err)
        code, _, err = sb.guard("cd - && git push origin feat/x")
        self.assertEqual(code, 0, err)


# =========================================================================== gates

class TestGates(SandboxCase):

    def test_green_gate_passes_with_the_staged_paths(self):
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 0, err)
        call = self.sb.gate_calls()[-1]
        self.assertEqual(call["args"][:2], ["fast", "--paths-from"])
        self.assertIn("src/new.py", call["paths"])

    def test_red_gate_refuses_with_the_tail(self):
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x", CHECK_STUB_EXIT=1)
        self.assertEqual(code, 2)
        self.assertIn("(gates)", err)
        self.assertIn("stub: E501 line too long", err)
        self.assertIn("Reproduce with: scripts/check.sh fast", err)
        self.assertNotIn("stub gate line 0\n", err)

    def test_missing_tool_names_the_setup_command(self):
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x", CHECK_STUB_EXIT=3)
        self.assertEqual(code, 2)
        self.assertIn("stub-install", err)
        self.assertIn("own Bash call", err)

    def test_absent_check_passes_with_a_note(self):
        (self.sb.wt / "scripts" / "check.sh").unlink()
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 0, err)
        self.assertIn("note:", err)

    def test_timeout_refuses(self):
        self.sb.stage("src/new.py", "x = 1\n")
        started = time.monotonic()
        code, _, err = self.sb.guard("git commit -m x", CHECK_STUB_SLEEP=10, HOOK_GATE_TIMEOUT=1)
        self.assertEqual(code, 2)
        self.assertIn("timed out", err)
        self.assertLess(time.monotonic() - started, 8)

    def test_other_exit_code_refuses(self):
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x", CHECK_STUB_EXIT=5)
        self.assertEqual(code, 2)
        self.assertIn("(gates-error)", err)

    def test_commit_all_sees_modified_files(self):
        self.sb.write("README.md", "# changed\n")
        code, _, err = self.sb.guard("git commit -am x")
        self.assertEqual(code, 0, err)
        self.assertIn("README.md", self.sb.gate_calls()[-1]["paths"])

    def test_amend_sees_the_head_files(self):
        code, _, err = self.sb.guard("git commit --amend --no-edit")
        self.assertEqual(code, 0, err)
        self.assertIn("src/app.py", self.sb.gate_calls()[-1]["paths"])

    def test_pathspec_is_in_the_set(self):
        self.sb.write("src/app.py", "print('changed')\n")
        code, _, err = self.sb.guard("git commit -m x -- src/app.py")
        self.assertEqual(code, 0, err)
        self.assertIn("src/app.py", self.sb.gate_calls()[-1]["paths"])

    def test_same_line_add_is_in_the_set(self):
        self.sb.write("src/later.py", "y = 2\n")
        code, _, err = self.sb.guard("git add src/later.py && git commit -m x")
        self.assertEqual(code, 0, err)
        self.assertIn("src/later.py", self.sb.gate_calls()[-1]["paths"])

    def test_merge_in_progress_judges_the_branch_side(self):
        sb = self.sb
        sb.commit_direct("feature.txt", "feature\n")
        sb.commit_direct("upstream.txt", "upstream\n", root=sb.main)
        sb.git("push", "-q", "origin", "main")
        sb.git("fetch", "-q", "origin", cwd=sb.wt)
        sb.git("merge", "-q", "--no-commit", "--no-ff", "origin/main", cwd=sb.wt)
        code, _, err = sb.guard("git commit --no-edit")
        self.assertEqual(code, 0, err)
        paths = sb.gate_calls()[-1]["paths"]
        self.assertIn("feature.txt", paths)
        self.assertNotIn("upstream.txt", paths)

    def test_git_C_from_the_main_checkout_judges_the_worktree(self):
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git -C {} commit -m x".format(self.sb.wt), cwd=self.sb.main)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sb.gate_calls()[-1]["root"], str(self.sb.wt))


# =========================================================================== secrets

class TestSecrets(SandboxCase):

    def assert_refused(self, command="git commit -m x", rule="secret-"):
        code, _, err = self.sb.guard(command)
        self.assertEqual(code, 2, err)
        self.assertIn("(" + rule, err)
        return err

    def assert_passes(self, command="git commit -m x"):
        code, _, err = self.sb.guard(command)
        self.assertEqual(code, 0, err)

    def test_secret_paths(self):
        cases = [(".env", "TOKEN=x\n", True), (".env.example", "TOKEN=\n", False),
                 ("config/deploy.env", "HOST=x\n", True), ("key.pem", "x\n", True)]
        for rel, text, refused in cases:
            with self.subTest(path=rel):
                self.sb.git("reset", "-q", cwd=self.sb.wt)
                self.sb.stage(rel, text, force=True)
                if refused:
                    self.assert_refused(rule="secret-path")
                else:
                    self.assert_passes()

    def test_service_account_by_content(self):
        self.sb.stage("creds-1234.json", SERVICE_ACCOUNT)
        err = self.assert_refused(rule="secret-content")
        self.assertIn("creds-1234.json", err)
        self.assertIn("service-account", err)

    def test_private_key_by_content(self):
        self.sb.stage("notes/keyfile.txt", PRIVATE_KEY)
        self.assertIn("private key header", self.assert_refused(rule="secret-content"))

    def test_ordinary_json_passes(self):
        self.sb.stage("data.json", '{"type": "user", "name": "x"}\n')
        self.assert_passes()

    def test_same_line_forced_add_of_env(self):
        self.sb.write(".env", "TOKEN=x\n")
        self.assert_refused("git add -f .env && git commit -m x", rule="secret-path")

    def test_same_line_add_of_a_key_file(self):
        self.sb.write("creds.json", SERVICE_ACCOUNT)
        self.assert_refused("git add creds.json && git commit -m x", rule="secret-content")

    def test_commit_all_with_a_key_and_no_echo(self):
        self.sb.write("src/app.py", "KEY = '{}'\n".format(CLOUD_KEY))
        err = self.assert_refused("git commit -am x", rule="secret-content")
        self.assertNotIn(CLOUD_KEY, err)
        self.assertIn("cloud access key", err)

    def test_fixture_marker_passes(self):
        self.sb.stage("tests/fixtures/fake_key.txt",
                      "# secret-scan: fixture\n" + PRIVATE_KEY)
        self.assert_passes()

    def test_binary_file_passes(self):
        self.sb.stage("assets/blob.bin", b"\x00\x01\x02" + PRIVATE_KEY.encode())
        self.assert_passes()

    def test_kebab_case_look_alikes_pass(self):
        self.sb.stage("wip/todo/2026-09-01-desk-booking-calendar-export.md",
                      "\n".join(KEBAB_LOOK_ALIKES) + "\n")
        self.sb.stage("src/tasks.py", "QUEUE = 'task-queue-processing-worker'\n")
        self.assert_passes()

    def test_api_key_at_a_word_start_is_refused(self):
        self.sb.stage("src/client.py", 'KEY = "{}"\n'.format(API_KEY))
        err = self.assert_refused(rule="secret-content")
        self.assertIn("API secret key", err)
        self.assertNotIn(API_KEY, err)

    def test_invalid_regex_refuses(self):
        conf = self.sb.wt / "scripts" / "lib" / "tooling.conf"
        conf.write_text(conf.read_text() + "SECRET_PATH_RE='(unclosed'\n")
        self.sb.stage("src/new.py", "x = 1\n")
        self.assert_refused(rule="bad-config")


# =========================================================================== wip

class TestWip(SandboxCase):

    def test_root_todo_list_refused(self):
        self.sb.stage("TODO.md", "- a\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(wip-shared-list)", err)

    def test_root_todo_list_without_wip_passes(self):
        sb = Sandbox(wip=False)
        self.addCleanup(sb.cleanup)
        sb.stage("TODO.md", "- a\n")
        code, _, err = sb.guard("git commit -m x")
        self.assertEqual(code, 0, err)

    def test_deleted_entry_refused(self):
        self.sb.git("rm", "-q", "wip/todo_nr/x.md", cwd=self.sb.wt)
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(wip-entry-deleted)", err)

    def test_deleted_entry_on_the_same_line_refused(self):
        code, _, err = self.sb.guard("git rm wip/todo_nr/x.md && git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(wip-entry-deleted)", err)

    def test_moved_entry_passes(self):
        self.sb.git("mv", "wip/todo/x.md", "wip/done/x.md", cwd=self.sb.wt)
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 0, err)

    def test_moved_entry_on_the_same_line_passes(self):
        code, _, err = self.sb.guard("git mv wip/todo/x.md wip/done/ && git commit -m x")
        self.assertEqual(code, 0, err)


# =========================================================================== branch

class TestBranchDiscipline(SandboxCase):

    def test_commit_on_default_branch_refused(self):
        self.sb.stage("src/new.py", "x = 1\n", root=self.sb.main)
        code, _, err = self.sb.guard("git commit -m x", cwd=self.sb.main)
        self.assertEqual(code, 2)
        self.assertIn("(default-branch)", err)
        self.assertIn("deployed from", err)
        self.assertIn("git worktree add ../demo-<topic> -b <type>/<topic> origin/main", err)

    def test_first_commit_without_origin_passes(self):
        fresh = self.sb.tmp / "fresh"
        self.sb.git("init", "-q", str(fresh), cwd=self.sb.tmp)
        self.sb.populate(fresh)
        self.sb.git("add", "-A", cwd=fresh)
        code, _, err = self.sb.guard("git commit -m init", cwd=fresh)
        self.assertEqual(code, 0, err)

    def test_detached_head_refused(self):
        self.sb.git("checkout", "-q", "--detach", cwd=self.sb.wt)
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(detached-head)", err)

    def test_gone_upstream_refused(self):
        self.sb.make_stale()
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(stale-branch)", err)
        self.assertIn("git cherry -v origin/main feat/x", err)

    def test_commit_already_on_default_refused(self):
        sb = self.sb
        sb.commit_direct("own.txt", "own\n")   # diverge, or the cherry-pick replays the same commit
        sha = sb.commit_direct("hotfix.txt", "fix\n", root=sb.main)
        sb.git("push", "-q", "origin", "main")
        sb.git("fetch", "-q", "origin", cwd=sb.wt)
        sb.git("cherry-pick", sha, cwd=sb.wt)
        sb.stage("src/new.py", "x = 1\n")
        code, _, err = sb.guard("git commit -m x")
        self.assertEqual(code, 2)
        self.assertIn("(already-on-default)", err)

    def test_fresh_branch_passes(self):
        self.sb.commit_direct()
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("git commit -m x")
        self.assertEqual(code, 0, err)

    def test_worktree_commit_while_main_is_on_main(self):
        self.assertEqual(self.sb.git("branch", "--show-current"), "main")
        self.sb.stage("src/new.py", "x = 1\n")
        code, _, err = self.sb.guard("cd {} && git commit -m x".format(self.sb.wt),
                                     cwd=self.sb.main)
        self.assertEqual(code, 0, err)


# =========================================================================== Stop

class TestRequirePullRequest(SandboxCase):

    def setUp(self):
        SandboxCase.setUp(self)
        self.sb.commit_direct()

    def assert_silent(self, result):
        code, out, err = result
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "")

    def assert_blocks(self, result, *needles):
        code, out, err = result
        self.assertEqual(code, 0, err)
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        for needle in needles:
            self.assertIn(needle, decision["reason"])
        return decision["reason"]

    def test_stop_hook_active_is_silent(self):
        self.assert_silent(self.sb.stop(active=True))

    def test_default_branch_is_silent(self):
        self.assert_silent(self.sb.stop(cwd=self.sb.main))

    def test_nothing_ahead_is_silent(self):
        self.sb.git("reset", "-q", "--hard", "origin/main", cwd=self.sb.wt)
        self.assert_silent(self.sb.stop())

    def test_no_pull_request_blocks(self):
        reason = self.assert_blocks(self.sb.stop(), "no pull request covers",
                                    "gh pr create --base main")
        self.assertNotIn("Commit the remaining changes first", reason)

    def test_modified_file_asks_for_a_commit(self):
        self.sb.write("a.txt", "changed\n")
        self.assert_blocks(self.sb.stop(), "Commit the remaining changes first")

    def test_untracked_file_asks_for_a_commit(self):
        self.sb.write("untracked.txt", "new\n")
        self.assert_blocks(self.sb.stop(), "Commit the remaining changes first")

    def test_merged_is_silent(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "MERGED", "url": "u"}]})
        self.assert_silent(self.sb.stop())

    def test_closed_blocks(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "CLOSED", "url": "u"}]})
        self.assert_blocks(self.sb.stop(), "#3 was closed", "noPullRequest true")

    def test_open_green_is_silent(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "OPEN", "url": "u"}],
                              "checks": [{"name": "CLI", "bucket": "pass"}]})
        self.assert_silent(self.sb.stop())

    def test_open_red_blocks_naming_the_check(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "OPEN", "url": "u"}],
                              "checks": [{"name": "CLI — lint", "bucket": "fail"},
                                         {"name": "Tooling", "bucket": "pass"}]})
        reason = self.assert_blocks(self.sb.stop(), "#3 has failing checks", "CLI — lint")
        self.assertNotIn("Tooling", reason)

    def test_open_pending_is_silent(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "OPEN", "url": "u"}],
                              "checks": [{"name": "CLI", "bucket": "pending"}]})
        self.assert_silent(self.sb.stop())

    def test_required_error_falls_back_to_all_checks(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "OPEN", "url": "u"}],
                              "required_error": True,
                              "checks": [{"name": "Scope", "bucket": "fail"}]})
        self.assert_blocks(self.sb.stop(), "Scope")

    def test_text_fallback_when_json_is_unsupported(self):
        self.sb.set_scenario({"pr_list": [{"number": 3, "state": "OPEN", "url": "u"}],
                              "json_unsupported": True,
                              "checks": [{"name": "CLI", "bucket": "fail"}]})
        self.assert_blocks(self.sb.stop(), "failing checks: CLI")

    def test_no_pull_request_key_is_silent(self):
        self.sb.git("config", "branch.feat/x.noPullRequest", "true")
        self.assert_silent(self.sb.stop())

    def test_gh_missing_is_silent(self):
        self.assert_silent(self.sb.stop(gh=False))

    def test_gh_unauthenticated_is_silent(self):
        self.sb.set_scenario({"auth": 1})
        self.assert_silent(self.sb.stop())

    def test_non_github_origin_is_silent(self):
        self.sb.git("remote", "set-url", "origin", str(self.sb.remote))
        self.assert_silent(self.sb.stop())

    def test_slow_gh_is_silent_within_the_limit(self):
        self.sb.set_scenario({"sleep": 5})
        started = time.monotonic()
        self.assert_silent(self.sb.stop())
        self.assertLess(time.monotonic() - started, 4.5)

    def test_subagent_stop_judges_its_worktree(self):
        self.assert_blocks(self.sb.stop(event="SubagentStop", cwd=self.sb.wt),
                           "Branch feat/x has 1 commit(s)")


# =========================================================================== SessionStart

class TestSessionStart(SandboxCase):

    def test_on_main_prints_branch_and_recipe(self):
        code, out, err = self.sb.session()
        self.assertEqual(code, 0, err)
        self.assertIn("Branch: main (0 ahead, 0 behind origin/main)", out)
        self.assertIn("git worktree add ../demo-<topic> -b <type>/<topic> origin/main", out)
        self.assertIn("deployed from", out)
        self.assertNotIn("vendored tooling", out)
        self.assertNotIn("code owner", out)
        self.assertLessEqual(len(out.splitlines()), 15)

    def test_other_worktree_and_cleanup_pointer(self):
        code, out, _ = self.sb.session()
        self.assertIn(str(self.sb.wt), out)
        self.assertIn("(feat/x)", out)
        self.assertIn("scripts/cleanup_local.py", out)

    def test_gone_branches_are_counted(self):
        self.sb.git("branch", "feat/old")
        self.sb.make_stale("feat/old", root=self.sb.main)
        code, out, _ = self.sb.session()
        self.assertIn("upstream is gone: 1", out)

    def test_stale_current_branch(self):
        self.sb.make_stale()
        code, out, _ = self.sb.session(cwd=self.sb.wt)
        self.assertIn("not safe to commit on", out)

    def test_missing_tooling_conf_prints_the_one_line(self):
        self.sb.unbootstrap()
        code, out, err = self.sb.session(cwd=self.sb.wt)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), NOT_BOOTSTRAPPED)

    def test_gh_missing_is_reported(self):
        code, out, err = self.sb.session(gh=False)
        self.assertEqual(code, 0, err)
        self.assertIn("degraded", out)

    def test_pull_request_merged_off_default(self):
        self.sb.set_scenario({"pr_merged": [
            {"number": 7, "baseRefName": "feat/y", "mergeCommit": {"oid": "abc123"}},
            {"number": 8, "baseRefName": "main", "mergeCommit": {"oid": "def456"}}],
            "compare": {"abc123": "ahead"}})
        code, out, _ = self.sb.session()
        self.assertIn("PR #7 merged into feat/y, not into main", out)
        self.assertNotIn("#8", out)
        self.sb.git("config", "--add", NS + ".deliveryAcknowledged", "7")
        code, out, _ = self.sb.session()
        self.assertNotIn("PR #7", out)

    def test_wrapper_without_python(self):
        empty = self.sb.tmp / "empty-bin"
        empty.mkdir()
        env = self.sb.env()
        env["PATH"] = str(empty)
        code, out, _ = run_hook("session_start.sh", {"cwd": str(self.sb.main)}, env,
                                cwd=self.sb.main / "src")
        self.assertEqual(code, 0)
        self.assertIn("WARNING: python3 is not installed", out)
        self.sb.unbootstrap()
        code, out, _ = run_hook("session_start.sh", {"cwd": str(self.sb.wt)}, env, cwd=self.sb.wt)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), NOT_BOOTSTRAPPED)

    def test_wrapper_runs_the_python_hook(self):
        code, out, err = run_hook("session_start.sh", {"cwd": str(self.sb.main)}, self.sb.env(),
                                  cwd=self.sb.main)
        self.assertEqual(code, 0, err)
        self.assertIn("Branch: main", out)


class TestSessionStartScheduled(SandboxCase):
    level = "complet"

    def runs(self):
        log = self.sb.sched_log
        return len(log.read_text().splitlines()) if log.exists() else 0

    def test_once_a_day(self):
        code, out, _ = self.sb.session(SCHED_STUB_EXIT=1)
        self.assertIn("nightly.yml is disabled", out)
        self.sb.session(SCHED_STUB_EXIT=1)
        self.assertEqual(self.runs(), 1)

    def test_unverifiable_buys_no_silence(self):
        self.sb.session(SCHED_STUB_EXIT=3)
        self.assertFalse((self.sb.main / ".demo-scheduled-check").exists())
        self.sb.session(SCHED_STUB_EXIT=3)
        self.assertEqual(self.runs(), 2)


# =========================================================================== post_edit

class TestPostEdit(SandboxCase):

    def edit(self, path, **env):
        return self.sb.edit(path, **env)

    def test_reports_from_the_worktree_of_the_file(self):
        code, out, err = self.edit(self.sb.wt / "src" / "app.py", CHECK_STUB_EXIT=1)
        self.assertEqual(code, 0, err)
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "PostToolUse")
        self.assertIn("Post-edit check on src/app.py", context["additionalContext"])
        self.assertIn("E999", context["additionalContext"])
        call = self.sb.gate_calls()[-1]
        self.assertEqual(call["root"], str(self.sb.wt))
        self.assertEqual(call["args"], ["edit", "src/app.py"])

    def test_clean_check_is_silent(self):
        code, out, _ = self.edit(self.sb.wt / "src" / "app.py")
        self.assertEqual((code, out), (0, ""))

    def test_file_outside_a_repository_is_silent(self):
        outside = self.sb.tmp / "home" / "notes.txt"
        outside.write_text("x\n")
        code, out, _ = self.edit(outside, CHECK_STUB_EXIT=1)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.sb.gate_calls(), [])

    def test_absent_check_is_silent(self):
        (self.sb.wt / "scripts" / "check.sh").unlink()
        code, out, _ = self.edit(self.sb.wt / "src" / "app.py", CHECK_STUB_EXIT=1)
        self.assertEqual((code, out), (0, ""))

    def test_crashing_check_is_silent(self):
        code, out, _ = self.edit(self.sb.wt / "src" / "app.py", CHECK_STUB_CRASH=1)
        self.assertEqual((code, out), (0, ""))


# =========================================================================== inert

class TestInertWithoutToolingConf(SandboxCase):
    """Contract §6: no scripts/lib/tooling.conf in the judged repository → every hook is inert
    (exit 0, nothing printed), except SessionStart's one line."""

    def setUp(self):
        SandboxCase.setUp(self)
        self.sb.commit_direct()          # wt is ahead of origin/main with no pull request
        self.sb.unbootstrap()            # ... and no longer bootstrapped

    def assert_inert(self, result):
        code, out, err = result
        self.assertEqual((code, out, err), (0, "", ""))

    def test_guard_refuses_nothing(self):
        wt = str(self.sb.wt)
        for command in ("git push --force origin feat/x", "git push origin main",
                        "gh pr merge 12 --admin", "gh pr create --base feat/y",
                        "git config project.allowStackedPr true", "git push",
                        'cd "$INHERITED" && git commit -m x', 'git commit -m "unclosed',
                        "bash -c 'git push -f origin main'"):
            with self.subTest(command=command):
                self.assert_inert(self.sb.guard(command, cwd=wt))

    def test_guard_runs_no_secret_scan_and_no_gate(self):
        self.sb.write(".env", "TOKEN=x\n")
        self.assert_inert(self.sb.guard("git add -f .env && git commit -m x", CHECK_STUB_EXIT=1))
        self.assertEqual(self.sb.gate_calls(), [])

    def test_guard_judges_each_command_in_its_own_repository(self):
        sb = self.sb
        code, _, err = sb.guard("git -C {} push --force origin x".format(sb.main), cwd=sb.wt)
        self.assertEqual(code, 2, err)
        self.assertIn("(force-push)", err)
        self.assert_inert(sb.guard("git -C {} push --force origin feat/x".format(sb.wt),
                                   cwd=sb.main))
        sb.stage("src/new.py", "x = 1\n")
        self.assert_inert(sb.guard("git -C {} commit -m x".format(sb.wt), cwd=sb.main,
                                   CHECK_STUB_EXIT=1))
        self.assertEqual(sb.gate_calls(), [])

    def test_unknown_repository_is_judged_by_the_session(self):
        code, _, err = self.sb.guard('cd "$INHERITED" && git commit -m x', cwd=self.sb.main)
        self.assertEqual(code, 2, err)
        self.assertIn("(unknown-repo)", err)

    def test_post_edit_is_silent(self):
        self.assert_inert(self.sb.edit(self.sb.wt / "src" / "app.py", CHECK_STUB_EXIT=1))
        self.assertEqual(self.sb.gate_calls(), [])

    def test_stop_and_subagent_stop_are_silent(self):
        for event in ("Stop", "SubagentStop"):
            with self.subTest(event=event):
                self.assert_inert(self.sb.stop(event=event))

    def test_session_start_prints_one_line(self):
        code, out, err = self.sb.session(cwd=self.sb.wt)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, NOT_BOOTSTRAPPED + "\n")
        self.assertEqual(self.sb.gh_calls(), [])

    def test_session_start_outside_a_repository(self):
        code, out, _ = self.sb.session(cwd=self.sb.home)
        self.assertEqual((code, out), (0, NOT_BOOTSTRAPPED + "\n"))
        code, out, _ = run_hook("session_start.sh", {"cwd": str(self.sb.home)}, self.sb.env(),
                                cwd=self.sb.home)
        self.assertEqual((code, out), (0, NOT_BOOTSTRAPPED + "\n"))

    def test_invalid_stdin_is_silent(self):
        for name in ("guard_bash.py", "post_edit.py", "require_pull_request.py"):
            with self.subTest(hook=name):
                self.assert_inert(run_hook(name, raw="{not json", env=self.sb.env(),
                                           cwd=self.sb.wt))


# =========================================================================== vendored tooling

class TestSessionStartVendoredVersion(SandboxCase):

    SYNC = " — run /shipyard:sync-tooling"

    def test_same_version_is_silent(self):
        code, out, err = self.sb.session()
        self.assertEqual(code, 0, err)
        self.assertNotIn("vendored tooling", out)

    def test_older_vendored_version(self):
        self.sb.set_plugin_version("1.2.0")
        code, out, err = self.sb.session()
        self.assertEqual(code, 0, err)
        self.assertIn("vendored tooling is 1.0.0, plugin is 1.2.0" + self.SYNC + "\n", out)
        self.assertLessEqual(len(out.splitlines()), 15)

    def test_versions_compare_as_numbers(self):
        self.sb.write_vendored("1.9.0")
        self.sb.set_plugin_version("1.10.0")
        _, out, _ = self.sb.session()
        self.assertIn("vendored tooling is 1.9.0, plugin is 1.10.0" + self.SYNC, out)

    def test_missing_vendored_file(self):
        (self.sb.main / "scripts" / "lib" / "VENDORED.json").unlink()
        _, out, _ = self.sb.session()
        self.assertIn("vendored tooling is absent, plugin is 1.0.0" + self.SYNC, out)

    def test_newer_vendored_version_asks_for_a_plugin_update(self):
        self.sb.write_vendored("2.0.0")
        _, out, _ = self.sb.session()
        self.assertIn("vendored tooling is 2.0.0, plugin is 1.0.0", out)
        self.assertIn("/plugin update", out)
        self.assertNotIn("sync-tooling", out)

    def test_vendor_check_reports_a_modified_copy(self):
        self.sb.add_vendor_stub()
        code, out, err = self.sb.session(VENDOR_STUB_EXIT=1,
                                         VENDOR_STUB_OUT="modified scripts/wip.py")
        self.assertEqual(code, 0, err)
        self.assertIn("vendored tooling is 1.0.0, plugin is 1.0.0" + self.SYNC
                      + " (modified scripts/wip.py)", out)
        self.assertEqual(self.sb.json_lines(self.sb.vendor_log),
                         [[str(self.sb.main), "--check"]])

    def test_vendor_check_ok_is_silent(self):
        self.sb.add_vendor_stub()
        _, out, _ = self.sb.session(VENDOR_STUB_EXIT=0, VENDOR_STUB_OUT="ok")
        self.assertNotIn("vendored tooling", out)

    def test_vendor_check_that_cannot_answer_falls_back_to_versions(self):
        self.sb.add_vendor_stub()
        self.sb.set_plugin_version("1.1.0")
        _, out, _ = self.sb.session(VENDOR_STUB_EXIT=2, VENDOR_STUB_OUT="usage")
        self.assertIn("vendored tooling is 1.0.0, plugin is 1.1.0" + self.SYNC, out)


# =========================================================================== team mode

class TestSessionStartTeam(SandboxCase):

    NOT_OWNER = ("You (@octo) are not a code owner of this repository yet — run /shipyard:join "
                 "before starting work: the team records who owns which part of the code.")

    def setUp(self):
        SandboxCase.setUp(self)
        self.sb.enable_team()

    def login_calls(self):
        return [c for c in self.sb.gh_calls() if c[:2] == ["api", "user"]]

    def test_not_an_owner(self):
        code, out, err = self.sb.session(OWNERS_STUB_MAP="{}")
        self.assertEqual(code, 0, err)
        self.assertIn(self.NOT_OWNER + "\n", out)
        self.assertEqual(self.sb.json_lines(self.sb.owners_log), [["--who", "octo"]])

    def test_owner_sees_their_patterns(self):
        owned = json.dumps({"octo": ["/src/", "/docs/"]})
        code, out, err = self.sb.session(OWNERS_STUB_MAP=owned)
        self.assertEqual(code, 0, err)
        self.assertIn("You own: /src/ /docs/\n", out)
        self.assertNotIn("not a code owner", out)

    def test_login_is_cached_a_day_for_every_worktree(self):
        self.sb.session(OWNERS_STUB_MAP="{}")
        cache = self.sb.main / ".git" / "shipyard" / "identity"
        self.assertEqual(json.loads(cache.read_text())["login"], "octo")
        _, out, _ = self.sb.session(cwd=self.sb.wt, OWNERS_STUB_MAP="{}")
        self.assertIn(self.NOT_OWNER, out)
        self.assertEqual(len(self.login_calls()), 1)
        cache.write_text(json.dumps({"login": "octo", "checked": int(time.time()) - 2 * 86400}))
        self.sb.session(OWNERS_STUB_MAP="{}")
        self.assertEqual(len(self.login_calls()), 2)

    def test_without_gh_says_nothing(self):
        code, out, err = self.sb.session(gh=False, OWNERS_STUB_MAP="{}")
        self.assertEqual(code, 0, err)
        self.assertNotIn("code owner", out)
        self.assertNotIn("You own", out)

    def test_unauthenticated_gh_says_nothing(self):
        self.sb.set_scenario({"login": ""})
        _, out, _ = self.sb.session(OWNERS_STUB_MAP="{}")
        self.assertNotIn("code owner", out)

    def test_without_owners_script_says_nothing(self):
        (self.sb.main / "scripts" / "owners.py").unlink()
        _, out, _ = self.sb.session()
        self.assertNotIn("code owner", out)
        self.assertEqual(self.login_calls(), [])

    def test_owners_without_codeowners_says_nothing(self):
        _, out, _ = self.sb.session(OWNERS_STUB_EXIT=2)
        self.assertNotIn("code owner", out)
        self.assertNotIn("You own", out)

    def test_solo_mode_never_asks(self):
        conf = self.sb.main / "scripts" / "lib" / "tooling.conf"
        conf.write_text(conf.read_text().replace("TEAM_MODE=team", "TEAM_MODE=solo"))
        _, out, _ = self.sb.session(OWNERS_STUB_MAP="{}")
        self.assertNotIn("code owner", out)
        self.assertEqual(self.login_calls(), [])
        self.assertEqual(self.sb.json_lines(self.sb.owners_log), [])


# =========================================================================== pre-commit

class TestGitPreCommit(SandboxCase):
    """The vendored pair: .githooks/pre-commit (template) runs scripts/precommit.py."""

    def setUp(self):
        SandboxCase.setUp(self)
        self.sb.git("config", "core.hooksPath", ".githooks")
        self.sb.stage("src/new.py", "x = 1\n")

    def commit(self, *extra, **env):
        return subprocess.run(["git", "commit", "-q", "-m", "x"] + list(extra),
                              cwd=str(self.sb.wt), env=self.sb.env(**env),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_inside_claude_code_it_steps_aside(self):
        proc = self.commit(CLAUDECODE=1, CHECK_STUB_EXIT=1)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.sb.gate_calls(), [])

    def test_outside_claude_code_it_runs_the_gates(self):
        proc = self.commit(CHECK_STUB_EXIT=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BLOCKED (gates)", proc.stderr)
        self.assertIn("--no-verify", proc.stderr)
        self.assertEqual(self.sb.gate_calls()[-1]["paths"], ["src/new.py"])
        direct = subprocess.run([str(self.sb.wt / ".githooks" / "pre-commit")],
                                cwd=str(self.sb.wt), env=self.sb.env(CHECK_STUB_EXIT=1),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(direct.returncode, 1)

    def test_green_gates_let_the_commit_through(self):
        proc = self.commit()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(self.sb.gate_calls()), 1)

    def test_commit_all_is_judged_on_what_git_records(self):
        self.sb.git("reset", "-q", cwd=self.sb.wt)
        self.sb.write("src/app.py", "KEY = '{}'\n".format(CLOUD_KEY))
        proc = self.commit("-a")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BLOCKED (secret-content)", proc.stderr)
        self.assertNotIn(CLOUD_KEY, proc.stderr)
        self.assertEqual(self.sb.gate_calls(), [])

    def test_missing_precommit_script_skips_with_a_note(self):
        (self.sb.wt / "scripts" / "precommit.py").unlink()
        proc = self.commit(CHECK_STUB_EXIT=1)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gates skipped", proc.stderr)


# =========================================================================== wiring

class TestWiring(unittest.TestCase):

    HOOK_FILES = ["guard_bash.py", "post_edit.py", "require_pull_request.py",
                  "session_start.py", "session_start.sh"]
    EXPECTED = {"SessionStart": (None, "session_start.sh", 60),
                "PreToolUse": ("Bash", "guard_bash.py", 300),
                "PostToolUse": ("Edit|Write|MultiEdit", "post_edit.py", 60),
                "Stop": (None, "require_pull_request.py", 60),
                "SubagentStop": (None, "require_pull_request.py", 60)}

    def test_hooks_json_wiring(self):
        manifest = json.loads(HOOKS_JSON.read_text())
        self.assertLessEqual(set(manifest), {"description", "hooks"})
        self.assertEqual(set(manifest["hooks"]), set(self.EXPECTED))
        for event, groups in manifest["hooks"].items():
            matcher, script, timeout = self.EXPECTED[event]
            self.assertEqual(len(groups), 1, event)
            self.assertEqual(groups[0].get("matcher"), matcher, event)
            for hook in groups[0]["hooks"]:
                with self.subTest(event=event, command=hook["command"]):
                    self.assertEqual(hook["type"], "command")
                    self.assertEqual(hook["timeout"], timeout)
                    quoted = '"${CLAUDE_PLUGIN_ROOT}/hooks/' + script + '"'
                    expected = quoted if script.endswith(".sh") else "python3 " + quoted
                    self.assertEqual(hook["command"], expected)
                    command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
                    target = Path([t for t in command.replace('"', " ").split()
                                   if "/hooks/" in t][0])
                    self.assertTrue(target.is_file(), target)
                    self.assertTrue(os.access(str(target), os.X_OK), target)

    def test_vendored_templates_are_executable(self):
        for path in (PRE_COMMIT, PRECOMMIT_PY):
            with self.subTest(path=path.name):
                self.assertTrue(os.access(str(path), os.X_OK), path)

    def test_no_project_hook_paths_left(self):
        for path in sorted(HOOKS.iterdir()):
            if path.is_file() and path.suffix in (".py", ".sh", ".json"):
                with self.subTest(path=path.name):
                    self.assertNotIn(".claude/hooks", path.read_text())

    def python_files(self):
        here = Path(__file__).resolve().parent
        return (sorted(HOOKS.glob("*.py")) + [PRECOMMIT_PY, here / "_hooks_support.py",
                                              Path(__file__).resolve()])

    def test_hooks_compile(self):
        out = tempfile.mkdtemp(prefix="hooks-compile-")
        self.addCleanup(shutil.rmtree, out, True)
        for path in self.python_files():
            with self.subTest(path=path.name):
                py_compile.compile(str(path), cfile=os.path.join(out, path.name + "c"),
                                   doraise=True)

    def test_standard_library_only(self):
        stdlib = getattr(sys, "stdlib_module_names", None)
        if stdlib is None:
            self.skipTest("sys.stdlib_module_names needs Python 3.10+")
        local = {p.stem for p in self.python_files()}
        for path in self.python_files():
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    with self.subTest(path=path.name, module=top):
                        self.assertTrue(top in stdlib or top in local, top)

    def test_invalid_stdin_never_blocks(self):
        sb = Sandbox()   # fake gh on PATH: no hook may reach the network from here
        self.addCleanup(sb.cleanup)
        for name in self.HOOK_FILES:
            with self.subTest(hook=name):
                code, out, _ = run_hook(name, raw="this is {not json", env=sb.env(),
                                        cwd=sb.wt)
                self.assertEqual(code, 0)
                if name not in ("session_start.py", "session_start.sh"):
                    self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
