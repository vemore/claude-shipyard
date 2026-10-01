#!/usr/bin/env python3
"""Stop / SubagentStop: no end of turn with commits that no pull request covers, or a red one.

Usage: Claude Code hook of the shipyard plugin; JSON payload on stdin (``cwd``,
``stop_hook_active``). Blocks by printing ``{"decision": "block", "reason": ...}``; the model
resumes with ``reason``.

Guarantees: judged on the payload's ``cwd`` (for an agent, its worktree). Blocks once per turn
when the branch is ahead of ``origin/<default>`` and has no pull request, a closed one, or an
open one with a failing check. Reads GitHub, never writes to it.

Does not cover: silent when not a repository, in a repository without
``scripts/lib/tooling.conf``, on the default branch or a detached HEAD, when
``branch.<b>.noPullRequest`` is true, without ``origin/<default>``, with nothing ahead, when
origin is not GitHub, or when gh is missing, unauthenticated or slow. A worktree an
orchestrator drives with ``git -C`` without being in it is not judged.

Why it exists: a commit that never becomes a pull request is not delivered — nobody reviewed
it, CI never saw it, it lives on one machine — and a red pull request is not delivered either.
"""

import json
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as common  # noqa: E402


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def failing_checks(number: int, root: str) -> Optional[List[str]]:
    """Names of failing checks; None when they cannot be read."""
    # gh pr checks exits 1 when a check fails and 8 while some are pending: still an answer.
    for extra in (["--required"], []):
        out = common.gh_run(["pr", "checks", str(number)] + extra + ["--json", "name,bucket"],
                            root, ok_codes=(0, 1, 8))
        if out is None:
            continue
        try:
            checks = json.loads(out)
        except ValueError:
            continue
        if isinstance(checks, list):
            return [str(c.get("name")) for c in checks
                    if isinstance(c, dict) and c.get("bucket") == "fail"]
    out = common.gh_run(["pr", "checks", str(number)], root, ok_codes=(0, 1, 8))
    if out is None:
        return None
    failing = []
    for line in out.splitlines():
        columns = line.split("\t")
        if len(columns) >= 2 and columns[1].strip() == "fail":
            failing.append(columns[0].strip())
    return failing


def main() -> int:
    payload = common.read_payload()
    if payload.get("stop_hook_active"):
        return 0
    root = common.repo_root(payload.get("cwd") or os.getcwd())
    if root is None or not common.is_bootstrapped(root):
        return 0
    conf = common.load_conf(root)
    default = conf.get("DEFAULT_BRANCH") or "main"
    branch = common.current_branch(root)
    if branch is None or branch == default:
        return 0
    if common.config_bool(root, "branch.{}.noPullRequest".format(branch)):
        return 0
    upstream = "origin/" + default
    if not common.ref_exists(root, "refs/remotes/" + upstream):
        return 0
    ahead = common.ahead_count(root, upstream)
    if not ahead:
        return 0
    if not common.origin_is_github(root) or not common.gh_ready(root):
        return 0
    out = common.gh_run(["pr", "list", "--head", branch, "--state", "all", "--limit", "1",
                         "--json", "number,state,url"], root)
    if out is None:
        return 0
    try:
        prs = json.loads(out)
    except ValueError:
        return 0
    hold = ("If this branch is deliberately held back, say so and run `git config "
            "branch.{}.noPullRequest true`.".format(branch))
    if not prs:
        reason = "Branch {} has {} commit(s) that no pull request covers.".format(branch, ahead)
        rc, status = common.git(root, "status", "--porcelain")
        if rc == 0 and status.strip():
            reason += " Commit the remaining changes first."
        reason += (" Then `git push -u origin {b}`, `gh pr create --base {d}` with a body saying "
                   "what changed and why, watch `gh pr checks <n> --watch`, and report the URL "
                   "and the check state. ".format(b=branch, d=default)) + hold
        return block(reason)
    pr = prs[0] if isinstance(prs, list) and isinstance(prs[0], dict) else {}  # type: dict
    state = str(pr.get("state", "")).upper()
    number = pr.get("number")
    if state == "MERGED":
        return 0
    if state == "CLOSED":
        return block("#{n} was closed without being merged. If the work is abandoned, say so to "
                     "the user and run `git config branch.{b}.noPullRequest true`; otherwise open"
                     " a new pull request.".format(n=number, b=branch))
    if state == "OPEN" and number is not None:
        failing = failing_checks(number, root)
        if failing:
            return block("Pull request #{} has failing checks: {}. A change is not finished "
                         "while its CI is red: fix them — or, if a failure is unrelated to this "
                         "change, say so to the user explicitly.".format(number,
                                                                         ", ".join(failing)))
    return 0


if __name__ == "__main__":
    common.run_main(main)
