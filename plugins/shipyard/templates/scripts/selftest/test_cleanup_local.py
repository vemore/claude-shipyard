"""Selftest of scripts/cleanup_local.py: a bare remote, a clone, worktrees and a stubbed `gh`.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Each case builds, in tempfile.mkdtemp(), a bare `origin`, a main checkout cloned from it with its
own scripts/lib/tooling.conf, and the branches and worktrees it needs. `gh` is a stub placed
first on PATH that answers from a JSON spec named by GH_STUB_SPEC (auth status, pull requests
per head branch or per searched commit, compare statuses): the GitHub-dependent rules are
exercised without a network or an account. Most cases set CLEANUP_IDLE_MINUTES=0, because every sandbox file is brand new.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "cleanup_local.py")
MARKER = ".sbx-setup-in-progress"
DASH = "—"

CONF = f"""# sandbox tooling.conf
DEFAULT_BRANCH=main
SETUP_MARKER={MARKER}
CLEANUP_IDLE_MINUTES=30
"""

GH_STUB = """#!{python}
import json, os, sys
args = sys.argv[1:]
path = os.environ.get("GH_STUB_SPEC", "")
spec = json.load(open(path)) if path and os.path.exists(path) else {{}}
log = os.environ.get("GH_STUB_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps(args) + "\\n")
def opt(name):
    return args[args.index(name) + 1] if name in args else None
if args[:2] == ["auth", "status"]:
    sys.exit(spec.get("auth", 0))
if args[:2] == ["pr", "list"]:
    state = (opt("--state") or "open").upper()
    if "--search" in args:
        found = spec.get("search", {{}}).get(opt("--search"), [])
    else:
        found = spec.get("prs", {{}}).get(opt("--head"), [])
    prs = [p for p in found if state == "ALL" or p["state"] == state]
    print(json.dumps(prs[: int(opt("--limit") or 30)]))
    sys.exit(0)
if args[:1] == ["api"] and "/compare/" in args[1]:
    status = spec.get("compare", {{}}).get(args[1].split("/compare/", 1)[1])
    if status is None:
        sys.stderr.write("gh: Not Found (HTTP 404)\\n")
        sys.exit(1)
    print(status)
    sys.exit(0)
sys.stderr.write("unexpected gh call: %r\\n" % (args,))
sys.exit(4)
"""


def proc_start(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return None
    return data[data.rfind(")") + 1 :].split()[19]


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="cleanup-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.main = os.path.join(self.tmp, "main")
        self.wts = os.path.join(self.tmp, "wts")
        os.mkdir(self.wts)
        self.spec = {"auth": 0, "prs": {}, "search": {}, "compare": {}}
        self.spec_path = os.path.join(self.tmp, "gh-spec.json")
        bindir = os.path.join(self.tmp, "bin")
        os.mkdir(bindir)
        stub = os.path.join(bindir, "gh")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write(GH_STUB.format(python=sys.executable))
        os.chmod(stub, 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_"))}
        env.pop("CLEANUP_IDLE_MINUTES", None)
        env.update(
            GIT_AUTHOR_NAME="Selftest",
            GIT_AUTHOR_EMAIL="selftest@example.invalid",
            GIT_COMMITTER_NAME="Selftest",
            GIT_COMMITTER_EMAIL="selftest@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=self.tmp,
            GH_STUB_SPEC=self.spec_path,
            GH_STUB_LOG=os.path.join(self.tmp, "gh.log"),
            PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
        )
        self.env = env
        self.git("init", "-q", "--bare", "-b", "main", self.origin, cwd=self.tmp)
        self.git("clone", "-q", self.origin, self.main, cwd=self.tmp)
        os.makedirs(os.path.join(self.main, "scripts", "lib"))
        with open(os.path.join(self.main, "scripts", "lib", "tooling.conf"), "w") as fh:
            fh.write(CONF)
        with open(os.path.join(self.main, ".gitignore"), "w") as fh:
            fh.write(f"/{MARKER}\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "initial")
        self.git("push", "-q", "origin", "main")

    # --- helpers ---

    def git(self, *args, cwd=None):
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd or self.main,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
        return proc.stdout.strip()

    def commit_on(self, branch, base="origin/main", count=1):
        """Create `branch` at `base` plus `count` new commits, without checking it out."""
        tip = self.git("rev-parse", base)
        tree = self.git("rev-parse", f"{tip}^{{tree}}")
        for i in range(count):
            tip = self.git("commit-tree", tree, "-p", tip, "-m", f"{branch} commit {i}")
        self.git("branch", "-f", branch, tip)
        return tip

    def worktree(self, name, branch=None, base="origin/main", parent=None):
        path = os.path.join(parent or self.wts, name)
        if branch is None:
            self.git("worktree", "add", "-q", "--detach", path, base)
        elif self.git("branch", "--list", branch):
            self.git("worktree", "add", "-q", path, branch)
        else:
            self.git("worktree", "add", "-q", "-b", branch, path, base)
        return path

    def age(self, path, seconds=7200):
        past = time.time() - seconds
        for dirpath, _dirs, files in os.walk(path):
            for name in files:
                os.utime(os.path.join(dirpath, name), (past, past), follow_symlinks=False)

    def cleanup(self, *args, cwd=None, **extra_env):
        with open(self.spec_path, "w", encoding="utf-8") as fh:
            json.dump(self.spec, fh)
        env = dict(self.env, **extra_env)
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            cwd=cwd or self.main,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def branches(self):
        return set(self.git("for-each-ref", "refs/heads", "--format=%(refname:short)").split())

    def assert_line(self, out, line):
        self.assertIn(line, out.splitlines(), out)

    def assert_no_line(self, out, fragment):
        self.assertFalse(any(fragment in ln for ln in out.splitlines()), out)


class Branches(Sandbox):
    def test_zero_ahead_is_deleted(self):
        self.commit_on("feat/zero", count=0)
        out = self.cleanup()
        self.assert_line(
            out, f"would delete branch feat/zero {DASH} no commit ahead of origin/main"
        )
        self.assertEqual(out.splitlines()[-1], "Dry run. Re-run with --apply to act.")
        out = self.cleanup("--apply")
        self.assert_line(out, f"deleted branch feat/zero {DASH} no commit ahead of origin/main")
        self.assertNotIn("feat/zero", self.branches())
        self.assertNotIn("Dry run", out)

    def test_merged_and_identical_is_deleted(self):
        tip = self.commit_on("feat/merged")
        self.spec["prs"]["feat/merged"] = [{"number": 1, "state": "MERGED", "headRefOid": tip}]
        self.spec["compare"][f"{tip}...{tip}"] = "identical"
        out = self.cleanup("--apply")
        self.assert_line(
            out, f"deleted branch feat/merged {DASH} merged in #1 (local tip included)"
        )
        self.assertNotIn("feat/merged", self.branches())

    def test_merged_head_ahead_of_local_tip_is_deleted(self):
        tip = self.commit_on("feat/behind")
        merged_head = self.commit_on("tmp-head", base=tip)  # updated on GitHub, never fetched
        self.git("branch", "-D", "tmp-head")
        self.spec["prs"]["feat/behind"] = [
            {"number": 5, "state": "MERGED", "headRefOid": merged_head}
        ]
        self.spec["compare"][f"{merged_head}...{tip}"] = "behind"
        out = self.cleanup()
        self.assert_line(
            out, f"would delete branch feat/behind {DASH} merged in #5 (local tip included)"
        )

    def test_local_commit_beyond_the_merge_is_kept(self):
        merged = self.commit_on("feat/beyond")
        tip = self.commit_on("feat/beyond", base=merged)
        self.spec["prs"]["feat/beyond"] = [{"number": 2, "state": "MERGED", "headRefOid": merged}]
        self.spec["compare"][f"{merged}...{tip}"] = "ahead"
        out = self.cleanup("--apply")
        self.assert_line(
            out, f"keep branch feat/beyond {DASH} local tip has commits beyond merged #2"
        )
        self.assertIn("feat/beyond", self.branches())

    def test_local_tip_unknown_to_github_is_kept(self):
        merged = self.commit_on("feat/unknown")
        self.commit_on("feat/unknown", base=merged)
        self.spec["prs"]["feat/unknown"] = [{"number": 9, "state": "MERGED", "headRefOid": merged}]
        out = self.cleanup()
        self.assert_line(out, f"keep branch feat/unknown {DASH} local tip is not on GitHub")

    def test_open_pull_request_is_kept(self):
        self.commit_on("feat/open")
        self.spec["prs"]["feat/open"] = [{"number": 3, "state": "OPEN", "headRefOid": "x"}]
        out = self.cleanup("--apply")
        self.assert_line(out, f"keep branch feat/open {DASH} pull request #3 OPEN")
        self.assertIn("feat/open", self.branches())

    def test_no_pull_request_is_kept(self):
        self.commit_on("feat/nopr")
        out = self.cleanup("--apply")
        self.assert_line(out, f"keep branch feat/nopr {DASH} no pull request")

    def test_gh_unavailable_keeps_with_reason(self):
        self.commit_on("feat/nopr", count=2)
        self.commit_on("feat/zero", count=0)
        self.spec["auth"] = 1
        out = self.cleanup("--apply")
        self.assert_line(
            out, f"keep branch feat/nopr {DASH} 2 commit(s) ahead; gh unavailable to prove a merge"
        )
        self.assert_line(out, f"deleted branch feat/zero {DASH} no commit ahead of origin/main")

    def test_current_branch_of_the_main_checkout_is_kept(self):
        self.git("switch", "-q", "-c", "feat/cur")
        out = self.cleanup("--apply")
        self.assert_line(
            out,
            f"keep branch feat/cur {DASH} current branch of the main checkout; "
            "switch to main first",
        )
        self.assertIn("feat/cur", self.branches())

    def test_default_branch_is_never_listed(self):
        out = self.cleanup("--apply")
        self.assert_no_line(out, "branch main")

    def test_without_origin_default_branch(self):
        lone = os.path.join(self.tmp, "lone")
        self.git("init", "-q", "-b", "main", lone, cwd=self.tmp)
        os.makedirs(os.path.join(lone, "scripts", "lib"))
        with open(os.path.join(lone, "scripts", "lib", "tooling.conf"), "w") as fh:
            fh.write(CONF)
        empty = os.path.join(self.tmp, "empty.git")
        self.git("init", "-q", "--bare", empty, cwd=self.tmp)
        self.git("remote", "add", "origin", empty, cwd=lone)
        out = self.cleanup(cwd=lone)
        self.assertIn("origin/main does not exist", out)


class Worktrees(Sandbox):
    def test_dirty_worktree_is_kept_with_its_branch(self):
        wt = self.worktree("dirty", "feat/dirty")
        with open(os.path.join(wt, "new.txt"), "w") as fh:
            fh.write("work in progress\n")
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(out, f"keep worktree {wt} (feat/dirty) {DASH} uncommitted changes")
        self.assert_no_line(out, "branch feat/dirty")
        self.assertTrue(os.path.isdir(wt))
        self.assertIn("feat/dirty", self.branches())

    def test_setup_marker_keeps_the_worktree_and_its_branch(self):
        wt = self.worktree("setup", "feat/setup")
        with open(os.path.join(wt, MARKER), "w") as fh:
            fh.write("pid 1 started 2026-10-01T00:00:00Z branch feat/setup\n")
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out, f"keep worktree {wt} (feat/setup) {DASH} setup in progress ({MARKER})"
        )
        self.assertIn("feat/setup", self.branches())
        self.assertTrue(os.path.isdir(wt))

    def test_recent_changes_keep_then_idle_zero_removes(self):
        wt = self.worktree("recent", "feat/recent")
        out = self.cleanup()
        self.assert_line(
            out,
            f"keep worktree {wt} (feat/recent) {DASH} modified in the last 30 "
            "minutes (an agent may be working)",
        )
        self.assert_no_line(out, "branch feat/recent")
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out, f"removed worktree {wt} (feat/recent) {DASH} no commit ahead of origin/main"
        )
        self.assert_line(out, f"deleted branch feat/recent {DASH} no commit ahead of origin/main")
        self.assertFalse(os.path.exists(wt))
        self.assertNotIn("feat/recent", self.branches())

    def test_old_changes_are_not_a_reason_to_keep(self):
        wt = self.worktree("old", "feat/old")
        self.age(wt)
        out = self.cleanup()
        self.assert_line(
            out, f"would remove worktree {wt} (feat/old) {DASH} no commit ahead of origin/main"
        )
        self.assert_line(out, f"would delete branch feat/old {DASH} no commit ahead of origin/main")

    def test_ignored_files_count_as_recent_changes(self):
        wt = self.worktree("ignored", "feat/ignored")
        info = os.path.join(self.main, ".git", "info")
        os.makedirs(info, exist_ok=True)
        with open(os.path.join(info, "exclude"), "a") as fh:
            fh.write("*.log\n")
        self.age(wt)
        with open(os.path.join(wt, "build.log"), "w") as fh:  # the only recent file
            fh.write("x\n")
        self.assertEqual(self.git("-C", wt, "status", "--porcelain"), "", "the file is ignored")
        out = self.cleanup()
        self.assert_line(
            out,
            f"keep worktree {wt} (feat/ignored) {DASH} modified in the last 30 "
            "minutes (an agent may be working)",
        )

    def test_lock_of_a_running_session_is_honoured(self):
        wt = self.worktree("live", "feat/live")
        start = proc_start(os.getpid())
        reason = f"claude agent t (pid {os.getpid()}" + (f" start {start})" if start else ")")
        self.git("worktree", "lock", "--reason", reason, wt)
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out,
            f"keep worktree {wt} (feat/live) {DASH} locked by a running "
            f"session (pid {os.getpid()})",
        )
        self.assertIn("feat/live", self.branches())

    def test_lock_of_a_dead_pid_is_stale(self):
        wt = self.worktree("dead", "feat/dead")
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.git("worktree", "lock", "--reason", f"claude agent t (pid {child.pid} start 1)", wt)
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out,
            f"removed worktree {wt} (feat/dead) {DASH} no commit ahead of "
            f"origin/main; stale lock, pid {child.pid} is gone",
        )
        self.assertFalse(os.path.exists(wt))
        self.assertNotIn("feat/dead", self.branches())

    @unittest.skipUnless(os.path.exists("/proc/self/stat"), "start times need /proc (Linux)")
    def test_lock_of_a_recycled_pid_is_stale(self):
        wt = self.worktree("recycled", "feat/recycled")
        wrong = int(proc_start(os.getpid())) + 1
        self.git(
            "worktree", "lock", "--reason", f"claude agent t (pid {os.getpid()} start {wrong})", wt
        )
        out = self.cleanup(CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out,
            f"would remove worktree {wt} (feat/recycled) {DASH} no commit ahead "
            f"of origin/main; stale lock, pid {os.getpid()} is gone",
        )

    def test_manual_lock_is_kept(self):
        wt = self.worktree("manual", "feat/manual")
        self.git("worktree", "lock", "--reason", "keep for the demo", wt)
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(out, f"keep worktree {wt} (feat/manual) {DASH} locked: keep for the demo")
        self.assertIn("feat/manual", self.branches())

    def test_detached_head(self):
        inside = self.worktree("in", None)
        outside_commit = self.commit_on("tmp-out")
        outside = self.worktree("out", None, base=outside_commit)
        self.git("branch", "-D", "tmp-out")
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out, f"removed worktree {inside} (detached) {DASH} detached on a commit in origin/main"
        )
        self.assert_line(
            out,
            f"keep worktree {outside} (detached) {DASH} detached on a commit not in origin/main",
        )
        self.assertFalse(os.path.exists(inside))
        self.assertTrue(os.path.exists(outside))

    def test_detached_on_the_head_of_a_merged_pull_request(self):
        # A reviewer's worktree: detached on a PR head that the squash merge left out of main.
        heads = {}
        for name in ("merged", "ahead", "unknown", "nogh"):
            heads[name] = self.commit_on(f"tmp-{name}")
        trees = {name: self.worktree(name, None, base=sha) for name, sha in heads.items()}
        for name in heads:
            self.git("branch", "-D", f"tmp-{name}")
        self.spec["search"][heads["merged"]] = [
            {"number": 7, "state": "MERGED", "headRefOid": heads["merged"]}
        ]
        self.spec["compare"][f"{heads['merged']}...{heads['merged']}"] = "identical"
        later = "f" * 40  # the PR got one more commit after the review, then merged
        self.spec["search"][heads["ahead"]] = [
            {"number": 8, "state": "MERGED", "headRefOid": later}
        ]
        self.spec["compare"][f"{later}...{heads['ahead']}"] = "behind"
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out, f"removed worktree {trees['merged']} (detached) {DASH} detached on the head of "
            "merged #7"
        )
        self.assertFalse(os.path.exists(trees["merged"]))
        for name in ("ahead", "unknown", "nogh"):
            self.assert_line(
                out,
                f"keep worktree {trees[name]} (detached) {DASH} detached on a commit not in "
                "origin/main",
            )
            self.assertTrue(os.path.isdir(trees[name]))

    def test_detached_merged_head_needs_gh(self):
        head = self.commit_on("tmp-head")
        tree = self.worktree("review", None, base=head)
        self.git("branch", "-D", "tmp-head")
        self.spec["search"][head] = [{"number": 7, "state": "MERGED", "headRefOid": head}]
        self.spec["compare"][f"{head}...{head}"] = "identical"
        self.spec["auth"] = 1
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(
            out, f"keep worktree {tree} (detached) {DASH} detached on a commit not in origin/main"
        )

    def test_branch_with_unproven_commits_keeps_its_worktree(self):
        wt = self.worktree("work", "feat/work")
        self.git("-C", wt, "commit", "-q", "--allow-empty", "-m", "work")
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        self.assert_line(out, f"keep worktree {wt} (feat/work) {DASH} no pull request")
        self.assertTrue(os.path.isdir(wt))

    def test_dry_run_changes_nothing(self):
        self.commit_on("feat/zero", count=0)
        removable = self.worktree("removable", "feat/removable")
        self.worktree("detached", None)
        tip = self.commit_on("feat/merged")
        self.spec["prs"]["feat/merged"] = [{"number": 1, "state": "MERGED", "headRefOid": tip}]
        self.spec["compare"][f"{tip}...{tip}"] = "identical"
        before = (self.git("worktree", "list", "--porcelain"), self.branches())
        out = self.cleanup(CLEANUP_IDLE_MINUTES="0")
        after = (self.git("worktree", "list", "--porcelain"), self.branches())
        self.assertEqual(before, after)
        self.assertTrue(os.path.isdir(removable))
        self.assertIn(
            f"would remove worktree {removable} (feat/removable) {DASH} no commit "
            "ahead of origin/main",
            out,
        )
        self.assertIn(
            f"would delete branch feat/removable {DASH} no commit ahead of origin/main", out
        )
        self.assertIn(
            f"would delete branch feat/merged {DASH} merged in #1 (local tip included)", out
        )

    def test_runs_from_a_worktree_against_the_main_checkout(self):
        wt = self.worktree("here", "feat/here")
        out = self.cleanup(cwd=wt)
        self.assert_line(
            out,
            f"keep worktree {wt} (feat/here) {DASH} modified in the last 30 "
            "minutes (an agent may be working)",
        )
        self.assert_no_line(out, f"worktree {self.main} ")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores permissions")
    def test_failed_removal_is_reported_and_keeps_the_branch(self):
        parent = os.path.join(self.tmp, "ro")
        os.mkdir(parent)
        wt = self.worktree("wt", "feat/ro", parent=parent)
        os.chmod(parent, 0o555)
        self.addCleanup(os.chmod, parent, 0o755)
        out = self.cleanup("--apply", CLEANUP_IDLE_MINUTES="0")
        lines = out.splitlines()
        self.assertIn(f"FAILED remove worktree {wt}", lines, out)
        following = lines[lines.index(f"FAILED remove worktree {wt}") + 1]
        self.assertTrue(following.startswith("    ") and following.strip(), out)
        self.assertIn("feat/ro", self.branches())
        self.assert_no_line(out, "deleted branch feat/ro")

    def test_help_and_executable(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no guard makes --apply safe", proc.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/cleanup_local.py")


if __name__ == "__main__":
    unittest.main()
