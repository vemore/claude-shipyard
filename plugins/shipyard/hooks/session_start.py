#!/usr/bin/env python3
"""SessionStart: tell the session, in a few lines, what it must know before it works.

Usage: launched by session_start.sh (JSON payload on stdin, ``cwd``). Plain stdout enters the
session's context, so it prints only what is relevant, at most 15 lines. Always exits 0.

Guarantees: in a repository without ``scripts/lib/tooling.conf``, one line saying shipyard is
not set up here, and nothing else. In a bootstrapped one: says when python3 < 3.9, git or an
authenticated gh is missing; when the vendored tooling (``scripts/lib/VENDORED.json``) is
older than the plugin or was modified (``bin/vendor.py --check``); in team mode, whether the
session's GitHub login owns any path in CODEOWNERS (``scripts/owners.py --who``); the current
branch against ``origin/<default>`` with the worktree recipe when on the default branch, and
"not safe to commit on" for a stale branch; the other worktrees and the local branches whose
upstream is gone; pull requests merged in the last 14 days into a branch other than the
default one whose work GitHub does not find on it; and, at tooling level ``complet``, the
scheduled-workflow check once a day.

Does not cover: it never fetches, so it reports the state of the last ``git fetch --prune``;
the login is cached a day in ``<git-common-dir>/shipyard/identity``.

Why it exists: a session that starts on a stale branch, in a crowded clone, on outdated
tooling, or after a pull request merged into the wrong base should hear it before its first
commit, not after.
"""

import datetime
import json
import os
import re
import shutil
import sys
import time
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as common  # noqa: E402

MAX_LINES = 15
MAX_WORKTREES_LISTED = 4
MAX_PATTERNS_LISTED = 8
MAX_DRIFT_LISTED = 3
DELIVERY_DAYS = 14
BUDGET_SECONDS = 25
VENDOR_CHECK_TIMEOUT = 10
OWNERS_TIMEOUT = 10
IDENTITY_TTL_SECONDS = 24 * 3600
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
VERSION_RE = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


# --------------------------------------------------------------------------- vendored tooling

def version_key(version: Optional[str]) -> Optional[Tuple[int, int, int]]:
    match = VERSION_RE.match(version or "")
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def read_json_field(path: str, field: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle).get(field)
    except (OSError, ValueError, AttributeError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def vendor_check(root: str, plugin: str) -> Tuple[Optional[int], List[str]]:
    """(code, lines) of ``bin/vendor.py <root> --check``; (None, []) when it cannot answer."""
    script = os.path.join(plugin, "bin", "vendor.py")
    if not os.path.isfile(script):
        return None, []
    rc, out = common.run_capped([sys.executable, script, root, "--check"], root,
                                VENDOR_CHECK_TIMEOUT, merge_stderr=False)
    if rc not in (0, 1):
        return None, []
    return rc, [line.strip() for line in out.splitlines() if line.strip()]


def tooling_lines(root: str) -> List[str]:
    plugin = common.plugin_root()
    plugin_version = read_json_field(os.path.join(plugin, ".claude-plugin", "plugin.json"),
                                     "version")
    vendored = read_json_field(os.path.join(root, "scripts", "lib", "VENDORED.json"),
                               "shipyard")
    have, want = version_key(vendored), version_key(plugin_version)
    shown = "{} is {}, plugin is {}".format("vendored tooling", vendored or "absent",
                                            plugin_version or "unknown")
    if have and want and have > want:
        return ["{}: this plugin is older than the project's tooling — run /plugin update "
                "(and restart) before working here.".format(shown)]
    rc, report = vendor_check(root, plugin)
    if rc is None:   # no vendor.py, or it could not answer: compare the versions only
        stale = bool(want) and (have is None or have < want)
        drift = []  # type: List[str]
    else:
        stale = rc == 1
        drift = [line for line in report if line.split(" ", 1)[0] in ("modified", "missing")]
    if not stale:
        return []
    line = "{} — run /shipyard:sync-tooling".format(shown)   # contract §6 wording
    if drift:
        more = len(drift) - MAX_DRIFT_LISTED
        line += " ({}{})".format(", ".join(drift[:MAX_DRIFT_LISTED]),
                                 ", and {} more".format(more) if more > 0 else "")
    return [line]


# --------------------------------------------------------------------------- team mode

def cached_login(cache: Optional[str]) -> Optional[str]:
    if not cache:
        return None
    try:
        with open(cache, encoding="utf-8") as handle:
            data = json.load(handle)
        age = time.time() - float(data.get("checked", 0))
        login = data.get("login")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if 0 <= age < IDENTITY_TTL_SECONDS and isinstance(login, str) and LOGIN_RE.match(login):
        return login
    return None


def session_login(root: str) -> Optional[str]:
    """The GitHub login of this session (``gh api user``), cached a day per clone."""
    common_dir = common.git_common_dir(root)
    cache = os.path.join(common_dir, "shipyard", "identity") if common_dir else None
    login = cached_login(cache)
    if login:
        return login
    out = common.gh_run(["api", "user", "--jq", ".login"], root)
    login = (out or "").strip()
    if not LOGIN_RE.match(login):
        return None
    if cache:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as handle:
                json.dump({"login": login, "checked": int(time.time())}, handle)
        except OSError:
            pass
    return login


def team_lines(root: str, conf: dict) -> List[str]:
    if (conf.get("TEAM_MODE") or "").strip().lower() != "team":
        return []
    owners = os.path.join(root, "scripts", "owners.py")
    if not os.path.isfile(owners):
        return []
    login = session_login(root)
    if not login:
        return []   # no gh, not authenticated, or no answer: say nothing
    rc, out = common.run_capped([sys.executable, owners, "--who", login], root, OWNERS_TIMEOUT,
                                merge_stderr=False)
    if rc == 1:   # contract §6 wording, relied on by /shipyard:join
        return ["You (@{}) are not a code owner of this repository yet — run /shipyard:join "
                "before starting work: the team records who owns which part of the code."
                .format(login)]
    if rc != 0:
        return []   # no CODEOWNERS, usage error, timeout: nothing reliable to say
    patterns = [line.split()[0] for line in out.splitlines() if line.strip()]
    if not patterns:
        return []
    more = len(patterns) - MAX_PATTERNS_LISTED
    return ["You own: {}{}".format(" ".join(patterns[:MAX_PATTERNS_LISTED]),
                                   " (and {} more)".format(more) if more > 0 else "")]


# --------------------------------------------------------------------------- branch

def branch_lines(root: str, conf: dict) -> List[str]:
    default = conf.get("DEFAULT_BRANCH") or "main"
    prefix = conf.get("WORKTREE_PREFIX") or "../"
    upstream = "origin/" + default
    has_upstream = common.ref_exists(root, "refs/remotes/" + upstream)
    branch = common.current_branch(root)
    if branch is None:
        return ["Branch: detached HEAD in {}.".format(root)]
    if has_upstream:
        rc, out = common.git(root, "rev-list", "--left-right", "--count", upstream + "...HEAD")
        parts = out.split()
        if rc == 0 and len(parts) == 2:
            line = "Branch: {} ({} ahead, {} behind {})".format(branch, parts[1], parts[0],
                                                                upstream)
        else:
            line = "Branch: {}".format(branch)
    else:
        line = "Branch: {} (no {} yet)".format(branch, upstream)
    lines = [line]
    if branch == default:
        lines.append("The main checkout stays on {} (it is fast-forwarded, deployed from, and "
                     "branched off for agent worktrees); start work in its own worktree:"
                     .format(default))
        lines.append("  git fetch --prune origin && git worktree add {p}<topic> -b <type>/<topic>"
                     " {u} && scripts/worktree_setup.sh {p}<topic>".format(p=prefix, u=upstream))
    elif has_upstream:
        reason = None
        if common.upstream_gone(root, branch):
            reason = "its upstream is gone (merged and deleted)"
        else:
            ahead = common.ahead_count(root, upstream)
            if ahead and ahead <= 50 and common.cherry_has_minus(root, upstream):
                reason = "it carries commits already on {}".format(upstream)
        if reason:
            lines.append("Branch {} is not safe to commit on: {}. Recipe: git fetch --prune "
                         "origin && git switch -c <type>/<topic> {}, then cherry-pick the "
                         "commits marked + by git cherry -v {} {}.".format(
                             branch, reason, upstream, upstream, branch))
    return lines


def worktree_lines(root: str) -> List[str]:
    lines = []
    rc, out = common.git(root, "worktree", "list", "--porcelain")
    others = []
    if rc == 0:
        path, label = None, ""
        for raw in out.splitlines() + [""]:
            if raw.startswith("worktree "):
                path, label = raw[len("worktree "):], "detached"
            elif raw.startswith("branch "):
                label = raw[len("branch "):].replace("refs/heads/", "", 1)
            elif raw == "bare":
                label = "bare"
            elif raw == "" and path:
                if os.path.realpath(path) != root and label != "bare":
                    others.append("{} ({})".format(path, label))
                path = None
    rc, out = common.git(root, "for-each-ref", "--format=%(upstream:track)", "refs/heads")
    gone = sum(1 for line in out.splitlines() if line.strip() == "[gone]") if rc == 0 else 0
    if others:
        shown = others[:MAX_WORKTREES_LISTED]
        more = len(others) - len(shown)
        lines.append("Other worktrees ({}): {}{}".format(
            len(others), ", ".join(shown), ", and {} more".format(more) if more else ""))
    if gone:
        lines.append("Local branches whose upstream is gone: {}.".format(gone))
    if others or gone:
        lines.append("Once no agent is working in them: `scripts/cleanup_local.py` (dry run), "
                     "then `--apply`.")
    return lines


def delivery_lines(root: str, conf: dict, deadline: float) -> List[str]:
    default = conf.get("DEFAULT_BRANCH") or "main"
    ns = conf.get("GIT_CONFIG_NS") or "project"
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=DELIVERY_DAYS)).date().isoformat()
    out = common.gh_run(["pr", "list", "--state", "merged", "--search", "merged:>=" + since,
                         "--limit", "50", "--json", "number,baseRefName,mergeCommit"], root)
    if out is None:
        return []
    try:
        prs = json.loads(out)
    except ValueError:
        return []
    rc, acked = common.git(root, "config", "--get-all", ns + ".deliveryAcknowledged")
    acknowledged = {v.strip().lstrip("#") for v in acked.split()} if rc == 0 else set()
    lines = []
    for pr in prs if isinstance(prs, list) else []:
        if time.monotonic() > deadline:
            break
        if not isinstance(pr, dict) or pr.get("baseRefName") in (None, default):
            continue
        number = str(pr.get("number"))
        sha = (pr.get("mergeCommit") or {}).get("oid") if isinstance(pr.get("mergeCommit"),
                                                                       dict) else None
        if number in acknowledged or not sha:
            continue
        status = common.gh_run(["api", "repos/{owner}/{repo}/compare/" + default + "..." + sha,
                                "--jq", ".status"], root)
        if status is None or status.strip() in ("identical", "behind"):
            continue
        lines.append("PR #{n} merged into {b}, not into {d}: its work may never have reached {d}."
                     " Reopen it against {d} (cherry-pick onto a fresh branch), or ask the user "
                     "to acknowledge it: git config --add {ns}.deliveryAcknowledged {n}".format(
                         n=number, b=pr.get("baseRefName"), d=default, ns=ns))
    return lines


def scheduled_lines(root: str, conf: dict) -> List[str]:
    if (conf.get("TOOLING_LEVEL") or "").lower() != "complet":
        return []
    stamp_name = conf.get("SCHEDULED_STAMP") or ""
    script = os.path.join(root, "scripts", "check_scheduled_runs.py")
    if not stamp_name or not os.path.isfile(script):
        return []
    stamp = os.path.join(root, stamp_name)
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        with open(stamp, encoding="utf-8") as handle:
            if handle.read().strip() == today:
                return []
    except OSError:
        pass
    rc, out = common.run_capped([sys.executable, script], root, 20, merge_stderr=False)
    if rc is not None and rc != 3 and rc != common.TIMED_OUT:
        try:
            with open(stamp, "w", encoding="utf-8") as handle:
                handle.write(today + "\n")
        except OSError:
            pass
    if rc == 1 and out.strip():
        report = out.strip().splitlines()
        return ["Scheduled workflows: " + report[0]] + report[1:4]
    return []


def conf_upward(start: str) -> bool:
    """Without git: does ``start`` or a parent carry scripts/lib/tooling.conf?"""
    path = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(path, common.CONF_RELPATH)):
            return True
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent


def main() -> int:
    started = time.monotonic()
    payload = common.read_payload()
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not shutil.which("git"):
        if conf_upward(cwd):
            print("WARNING: git is not installed: the shipyard hooks cannot judge anything.")
        else:
            print(common.NOT_BOOTSTRAPPED)
        return 0
    root = common.repo_root(cwd)
    if not common.is_bootstrapped(root):
        print(common.NOT_BOOTSTRAPPED)
        return 0
    lines = []  # type: List[str]
    if sys.version_info < (3, 9):
        lines.append("WARNING: python3 is {}.{}; the shipyard hooks need Python 3.9+.".format(
            *sys.version_info[:2]))
    conf = common.load_conf(root)
    ready = False
    if common.origin_is_github(root):
        if not shutil.which("gh"):
            lines.append("gh is not installed: pull-request checks and the merge loop are "
                         "degraded.")
        elif common.gh_run(["auth", "status"], root) is None:
            lines.append("gh is not authenticated (or did not answer): pull-request checks and "
                         "the merge loop are degraded.")
        else:
            ready = True
    lines += tooling_lines(root)
    lines += team_lines(root, conf)
    lines += branch_lines(root, conf)
    lines += worktree_lines(root)
    if ready:
        lines += delivery_lines(root, conf, started + BUDGET_SECONDS)
    lines += scheduled_lines(root, conf)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + ["(more session notes were cut)"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    common.run_main(main)
