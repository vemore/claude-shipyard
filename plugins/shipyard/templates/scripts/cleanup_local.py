#!/usr/bin/env python3
"""Remove the worktrees and local branches that are provably finished; keep everything else.

Usage:
    scripts/cleanup_local.py            # dry run: say what would go, and why each kept item stays
    scripts/cleanup_local.py --apply    # act on it

Output lines: `keep ... — <reason>`, `would remove ...` / `would delete branch ...`, `removed ...`
/ `deleted branch ...`, `FAILED ...` followed by git's error indented by four spaces. Always exit
0: this is a report, not a gate.

What it does. It runs from the main checkout (the parent of `--git-common-dir`), reads that
checkout's scripts/lib/tooling.conf, then runs `git fetch --prune origin` (60 s) — the only
process script that fetches, because its whole job is to judge against the remote and an
operator launches it on purpose. A branch is deletable when it has no commit ahead of
origin/<DEFAULT_BRANCH>, or when GitHub proves a merge: `gh pr list --head <branch> --state
merged` finds a pull request and `gh api .../compare/<merged head>...<local tip>` answers
`identical` or `behind` (every local commit is in what was merged). `git cherry` would call every
squash-merged branch unmerged, a local comparison misses heads updated on GitHub, and
`git merge-tree` reports old versions of rewritten lines as changes; the compare answers the real
question.

Worktrees (never the main checkout), guards in this order; each guard keeps the worktree AND its
branch:
  1. locked by a running session: the lock reason holds `pid N` (Claude Code writes
     `claude agent <name> (pid N start T)`), N is alive and, where /proc/N/stat is readable
     (Linux), its start time (field 22) equals T. On macOS (no /proc) only "pid alive" is checked.
  2. locked by hand: a lock without a pid.
  3. setup in progress: <worktree>/<SETUP_MARKER> exists (scripts/worktree_setup.sh).
  4. modified in the last CLEANUP_IDLE_MINUTES minutes: any file under it, ignored files
     included (an agent may be between two commits). The CLEANUP_IDLE_MINUTES environment
     variable overrides tooling.conf; 0 disables this guard only.
  5. uncommitted changes (`git status --porcelain`).
  6. detached HEAD: removed when HEAD is in origin/<DEFAULT_BRANCH>, or when GitHub says HEAD
     is the head of a merged pull request (`gh pr list --state merged --search <sha>`, then the
     compare of that merged head against HEAD answers `identical`: a reviewer's worktree,
     detached on a head that a squash merge left outside the default branch); kept otherwise.
  7. its branch: removed when the branch is deletable (above).
A lock whose pid is dead or recycled is stale: the worktree goes through the other guards, and is
removed with `git worktree remove -f -f`. Branches: the default branch and the main checkout's
current branch are never deleted; a deletable one is deleted with `git branch -D` (a squash-merged
branch is never "merged" in git's sense).

Does not cover — the honest limit: no guard makes --apply safe while agents are working. An
unlocked worktree, idle for longer than the window, on a branch with no commit yet, looks
abandoned. The guards cover the windows that cost work in practice (a live agent session, the
few minutes of a setup, an agent between two commits). Run --apply only once every agent has
reported. Without `gh` (missing, not authenticated, timing out) a branch with commits is kept.
Why: every parallel loop leaves agent worktrees, abandoned `worktree-<name>` branches and one
local branch per merged pull request; proving each one deletable by hand took three attempts for
twenty branches. This script makes that proof and keeps whatever it cannot prove.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf

LOCK_PID_RE = re.compile(r"\bpid (\d+)(?: start (\d+))?")
DASH = "—"


def run(args, cwd=None, timeout=20):
    """Run a command; never raises. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return 127, "", f"{args[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{args[0]}: timed out after {timeout} s"
    return proc.returncode, proc.stdout, proc.stderr


def git(*args, cwd=None, timeout=20):
    return run(["git", *args], cwd=cwd, timeout=timeout)


def indent(text):
    lines = text.strip().splitlines() or ["(no output)"]
    return "\n".join("    " + line for line in lines)


# --- process liveness ----------------------------------------------------------------------


def pid_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OverflowError, OSError):
        return False
    return True


def proc_start_time(pid):
    """Field 22 of /proc/<pid>/stat (start time in clock ticks), or None when unreadable."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
    except OSError:
        return None
    # Field 2 (the command name) may hold spaces and parentheses: cut after the LAST ')'.
    rest = data[data.rfind(")") + 1 :].split()
    return rest[19] if len(rest) > 19 else None


def lock_state(reason):
    """('live', pid) for a running session's lock, ('stale', pid), or ('manual', None)."""
    m = LOCK_PID_RE.search(reason or "")
    if not m:
        return "manual", None
    pid = int(m.group(1))
    if not pid_alive(pid):
        return "stale", pid
    if m.group(2) is not None:
        start = proc_start_time(pid)
        if start is not None and start != m.group(2):
            return "stale", pid  # the pid was recycled by another process
    return "live", pid


# --- worktrees -----------------------------------------------------------------------------


def list_worktrees(main):
    """Parse `git worktree list --porcelain` into dicts (path, head, branch, locked, ...)."""
    rc, out, _ = git("worktree", "list", "--porcelain", cwd=main)
    trees, cur = [], None
    for line in out.splitlines() if rc == 0 else []:
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree ") :], "branch": None, "detached": False}
            trees.append(cur)
        elif cur is None:
            continue
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch ") :].removeprefix("refs/heads/")
        elif line == "detached":
            cur["detached"] = True
        elif line == "bare":
            cur["bare"] = True
        elif line == "locked" or line.startswith("locked "):
            cur["locked"] = line[len("locked ") :] if line.startswith("locked ") else ""
        elif line == "prunable" or line.startswith("prunable "):
            cur["prunable"] = True
    return trees


def recently_modified(path, minutes):
    """True when any file under `path` (ignored files included) changed in the last N minutes."""
    cutoff = time.time() - minutes * 60
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                if os.lstat(os.path.join(dirpath, name)).st_mtime > cutoff:
                    return True
            except OSError:
                continue
    return False


def same_path(a, b):
    return os.path.realpath(a) == os.path.realpath(b)


class Cleaner:
    def __init__(self, main, cfg, apply, idle_minutes, gh_ok):
        self.main = main
        self.default = cfg["DEFAULT_BRANCH"]
        self.marker = cfg["SETUP_MARKER"]
        self.apply = apply
        self.idle = idle_minutes
        self.gh_ok = gh_ok
        self.origin = f"origin/{self.default}"
        self.kept = set()
        self.remaining = set()  # branches still checked out in a worktree that stays
        self.cache = {}

    # --- the branch rule ---

    def deletable(self, branch):
        if branch in self.cache:
            return self.cache[branch]
        self.cache[branch] = verdict = self._deletable(branch)
        return verdict

    def _deletable(self, branch):
        rc, out, err = git("rev-list", "--count", f"{self.origin}..{branch}", cwd=self.main)
        if rc != 0:
            return False, f"cannot count commits ahead of {self.origin}: {err.strip()}"
        ahead = int(out.strip() or "0")
        if ahead == 0:
            return True, f"no commit ahead of {self.origin}"
        if not self.gh_ok:
            return False, f"{ahead} commit(s) ahead; gh unavailable to prove a merge"
        merged = self.gh_json(
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "merged",
            "--json",
            "number,headRefOid",
            "--limit",
            "1",
        )
        if merged is None:
            return False, f"{ahead} commit(s) ahead; gh failed to list pull requests"
        if not merged:
            other = self.gh_json(
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number,state",
                "--limit",
                "1",
            )
            if other:
                return False, f"pull request #{other[0].get('number')} {other[0].get('state')}"
            return False, "no pull request"
        number, head = merged[0].get("number"), merged[0].get("headRefOid", "")
        _, tip, _ = git("rev-parse", branch, cwd=self.main)
        rc, out, _ = run(
            [
                "gh",
                "api",
                f"repos/{{owner}}/{{repo}}/compare/{head}...{tip.strip()}",
                "--jq",
                ".status",
            ],
            cwd=self.main,
        )
        status = out.strip() if rc == 0 else ""
        if status in ("identical", "behind"):
            return True, f"merged in #{number} (local tip included)"
        if status in ("ahead", "diverged"):
            return False, f"local tip has commits beyond merged #{number}"
        return False, "local tip is not on GitHub"

    def merged_head(self, path):
        """The number of the merged pull request whose head is HEAD of `path`, else None.

        A reviewer's worktree is detached on a pull request's head; a squash merge leaves that
        commit outside the default branch, so only GitHub can prove it was merged."""
        if not self.gh_ok:
            return None
        rc, sha, _ = git("rev-parse", "HEAD", cwd=path)
        sha = sha.strip()
        if rc != 0 or not sha:
            return None
        found = self.gh_json(
            "pr",
            "list",
            "--state",
            "merged",
            "--search",
            sha,
            "--json",
            "number,headRefOid",
            "--limit",
            "1",
        )
        if not found:
            return None
        number, head = found[0].get("number"), found[0].get("headRefOid", "")
        if not head:
            return None
        rc, out, _ = run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/compare/{head}...{sha}", "--jq", ".status"],
            cwd=self.main,
        )
        return number if rc == 0 and out.strip() == "identical" else None

    def gh_json(self, *args):
        rc, out, _ = run(["gh", *args], cwd=self.main)
        if rc != 0:
            return None
        try:
            data = json.loads(out or "[]")
        except ValueError:
            return None
        return data if isinstance(data, list) else None

    # --- worktrees ---

    def judge_worktree(self, wt):
        """Return (action, reason, stale_pid) with action 'keep' or 'remove' (or 'prune')."""
        path, branch = wt["path"], wt["branch"]
        stale_pid = None
        if "locked" in wt:
            state, pid = lock_state(wt["locked"])
            if state == "live":
                return "keep", f"locked by a running session (pid {pid})", None
            if state == "manual":
                return "keep", f"locked: {wt['locked'] or 'no reason given'}", None
            stale_pid = pid
        if not os.path.isdir(path):
            return "prune", "its directory is missing", stale_pid
        if os.path.exists(os.path.join(path, self.marker)):
            return "keep", f"setup in progress ({self.marker})", stale_pid
        if self.idle > 0 and recently_modified(path, self.idle):
            return (
                "keep",
                f"modified in the last {self.idle} minutes (an agent may be working)",
                stale_pid,
            )
        rc, out, err = git("status", "--porcelain", cwd=path)
        if rc != 0:
            return "keep", f"git status failed: {err.strip()}", stale_pid
        if out.strip():
            return "keep", "uncommitted changes", stale_pid
        if branch is None:
            rc, _, _ = git("merge-base", "--is-ancestor", "HEAD", self.origin, cwd=path)
            if rc == 0:
                return "remove", f"detached on a commit in {self.origin}", stale_pid
            number = self.merged_head(path)
            if number is not None:
                return "remove", f"detached on the head of merged #{number}", stale_pid
            return "keep", f"detached on a commit not in {self.origin}", stale_pid
        ok, reason = self.deletable(branch)
        return ("remove" if ok else "keep"), reason, stale_pid

    def worktrees(self):
        trees = list_worktrees(self.main)
        for wt in trees:
            if same_path(wt["path"], self.main) or wt.get("bare"):
                continue
            label = f"{wt['path']} ({wt['branch'] or 'detached'})"
            action, reason, stale_pid = self.judge_worktree(wt)
            if action == "keep":
                print(f"keep worktree {label} {DASH} {reason}")
                if wt["branch"]:
                    self.kept.add(wt["branch"])
                continue
            if stale_pid is not None:
                reason += f"; stale lock, pid {stale_pid} is gone"
            if action == "prune":
                verb = "pruned" if self.apply else "would prune"
                print(f"{verb} worktree {label} {DASH} {reason}")
                continue
            if not self.apply:
                print(f"would remove worktree {label} {DASH} {reason}")
                continue
            force = ["-f", "-f"] if stale_pid is not None else []
            rc, _, err = git("worktree", "remove", *force, wt["path"], cwd=self.main, timeout=120)
            if rc == 0:
                print(f"removed worktree {label} {DASH} {reason}")
            else:
                print(f"FAILED remove worktree {wt['path']}")
                print(indent(err))
                if wt["branch"]:
                    self.kept.add(wt["branch"])
        if self.apply:
            git("worktree", "prune", cwd=self.main)

    # --- branches ---

    def branches(self):
        _, current, _ = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=self.main)
        current = current.strip()
        rc, out, _ = git("for-each-ref", "refs/heads", "--format=%(refname:short)", cwd=self.main)
        names = out.split() if rc == 0 else []
        for branch in names:
            if branch == self.default or branch in self.kept or branch in self.remaining:
                continue
            ok, reason = self.deletable(branch)
            if branch == current:
                if ok:
                    reason = f"current branch of the main checkout; switch to {self.default} first"
                print(f"keep branch {branch} {DASH} {reason}")
                continue
            if not ok:
                print(f"keep branch {branch} {DASH} {reason}")
            elif not self.apply:
                print(f"would delete branch {branch} {DASH} {reason}")
            else:
                rc, _, err = git("branch", "-D", branch, cwd=self.main)
                if rc == 0:
                    print(f"deleted branch {branch} {DASH} {reason}")
                else:
                    print(f"FAILED delete branch {branch}")
                    print(indent(err))

    def remaining_branches(self):
        """Branches still checked out in a worktree that this run leaves in place."""
        if not self.apply:
            return  # dry run: `kept` already holds every branch whose worktree stays
        for wt in list_worktrees(self.main):
            if wt["branch"] and not same_path(wt["path"], self.main):
                self.remaining.add(wt["branch"])


def main(argv):
    parser = argparse.ArgumentParser(
        prog="cleanup_local.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true", help="act instead of a dry run")
    args = parser.parse_args(argv[1:])
    try:
        rc, common, err = git("rev-parse", "--path-format=absolute", "--git-common-dir")
        if rc != 0:
            raise conf.ConfError(f"not inside a git repository ({err.strip()})")
        main_checkout = os.path.dirname(common.strip().rstrip("/"))
        os.chdir(main_checkout)
        cfg = conf.load_conf(main_checkout)
        default, _marker = cfg["DEFAULT_BRANCH"], cfg["SETUP_MARKER"]  # fail early if missing
        idle = os.environ.get("CLEANUP_IDLE_MINUTES", "").strip()
        idle_minutes = int(idle) if idle else cfg.get_int("CLEANUP_IDLE_MINUTES")
    except (conf.ConfError, ValueError) as exc:
        print(f"cleanup_local.py: {exc}")
        return 0
    rc, _, err = git("fetch", "--prune", "--quiet", "origin", cwd=main_checkout, timeout=60)
    if rc != 0:
        print(f"warning: fetch failed; judging against a stale origin/{default}")
        if err.strip():
            print(indent(err))
    rc, _, _ = git(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/remotes/origin/{default}^{{commit}}",
        cwd=main_checkout,
    )
    if rc != 0:
        print(f"origin/{default} does not exist: nothing can be proven merged; nothing to do.")
        return 0
    gh_rc, _, _ = run(["gh", "auth", "status"], cwd=main_checkout, timeout=10)
    cleaner = Cleaner(main_checkout, cfg, args.apply, max(idle_minutes, 0), gh_rc == 0)
    cleaner.worktrees()
    cleaner.remaining_branches()
    cleaner.branches()
    if not args.apply:
        print("Dry run. Re-run with --apply to act.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
