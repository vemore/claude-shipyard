#!/usr/bin/env python3
"""PreToolUse (Bash) guard: refuse dangerous git/gh forms, and run the gates before a commit.

Usage: Claude Code hook of the shipyard plugin; JSON payload on stdin (``cwd``,
``tool_input.command``); exit 2 + stderr refuses the command. ``--help`` prints this text.

Guarantees: refuses force-push, push to the default branch, stacked pull requests, merges
that are not squash or that use --admin or the merge API, agent writes of the user-only git
config keys, and commits or pushes whose repository cannot be told. Before a commit, in the
repository the commit runs in: refuses secret paths and secret content, a shared TODO list
or a deleted wip/ entry, a commit on the default branch, on a detached HEAD or on a stale
branch, and red, missing or timed-out gates (``scripts/check.sh fast``). Each rule applies
only where the command runs in a repository that carries ``scripts/lib/tooling.conf`` (for a
command whose directory cannot be told: the session's repository); elsewhere it is inert.

Does not cover: what a launched script does (``bash scripts/x.sh``), merges through the web
interface, ``git merge``/``rebase``/``revert``/``cherry-pick``, the freshness of ``origin``
(it never fetches), and test suites (CI runs them). Commits made outside Claude Code go
through the project's ``.githooks/pre-commit`` and ``scripts/precommit.py`` instead. See
annex 04 section 11 / Hooks wiki page.

Why it exists: rules a script can decide become mechanical refusals instead of prose that
holds only while the agent remembers it; CI would only catch them after the push.
"""

import os
import re
import sys
import tempfile
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as common  # noqa: E402
from parse_command import parse, push_main_message  # noqa: E402

MAX_SCAN_BYTES = 1024 * 1024
FIXTURE_MARKER = "secret-scan: fixture"
GATE_TAIL_LINES = 40
WIP_ENTRY_DIRS = ("wip/todo/", "wip/todo_nr/", "wip/done/")
CONTENT_LABELS = [("PRIVATE KEY", "private key header"),
                  ("service_account", "cloud service-account key file"),
                  ("AKIA", "cloud access key id"),
                  ("ghp_", "GitHub token"), ("github_pat_", "GitHub token"),
                  ("xox", "Slack token"), ("sk-", "API secret key")]


class Refusal(Exception):
    def __init__(self, rule: str, message: str):
        Exception.__init__(self, message)
        self.rule = rule
        self.message = message

    def text(self) -> str:
        return "BLOCKED ({}) {}".format(self.rule, self.message)


# --------------------------------------------------------------------------- path set (5.1)

class PathSet:
    """Root-relative paths a commit may contain, with their statuses and where to read them."""

    def __init__(self) -> None:
        self.entries = {}  # type: Dict[str, Dict]

    def add(self, status: str, path: str, worktree: bool) -> None:
        if not path:
            return
        entry = self.entries.setdefault(path, {"statuses": set(), "index": False,
                                               "worktree": False})
        entry["statuses"].add(status)
        entry["worktree" if worktree else "index"] = True

    def add_name_status(self, data: bytes, worktree: bool) -> None:
        parts = data.decode("utf-8", "surrogateescape").split("\0")
        i = 0
        while i < len(parts):
            status = parts[i]
            if not status:
                i += 1
                continue
            letter = status[0]
            if letter in "RC" and i + 2 < len(parts):
                if letter == "R":
                    self.add("D", parts[i + 1], worktree)
                self.add("A", parts[i + 2], worktree)
                i += 3
            elif i + 1 < len(parts):
                self.add(letter, parts[i + 1], worktree)
                i += 2
            else:
                break

    def add_list(self, data: bytes, status: str, worktree: bool) -> None:
        for path in data.decode("utf-8", "surrogateescape").split("\0"):
            self.add(status, path, worktree)

    def paths(self) -> List[str]:
        return list(self.entries)


def _name_status(pathset: PathSet, cwd: str, args: List[str], worktree: bool) -> bool:
    rc, out = common.git_bytes(cwd, *args)
    if rc == 0:
        pathset.add_name_status(out, worktree)
    return rc == 0


def _ls_files(pathset: PathSet, cwd: str, args: List[str], status: str) -> None:
    rc, out = common.git_bytes(cwd, "ls-files", "--full-name", "-z", *args)
    if rc == 0:
        pathset.add_list(out, status, worktree=True)


def _diff_head(pathset: PathSet, cwd: str, pathspecs: List[str]) -> None:
    """Tracked changes (staged or not) against HEAD; on an unborn branch, against the index."""
    tail = ["--"] + pathspecs if pathspecs else []
    if not _name_status(pathset, cwd, ["diff", "--name-status", "-z", "HEAD"] + tail, True):
        _name_status(pathset, cwd, ["diff", "--name-status", "-z"] + tail, True)


def _rel(root: str, cwd: str, path: str) -> Optional[str]:
    """Root-relative form of a literal path given relative to ``cwd``; None if outside."""
    if any(ch in path for ch in "*?[$`") or path.startswith(":"):
        return None
    full = os.path.normpath(os.path.join(os.path.realpath(cwd), path))
    rel = os.path.relpath(full, root)
    if rel == "." or rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


def collect_paths(root: str, commit: Dict, stages: List[Dict]) -> PathSet:
    pathset = PathSet()
    if common.ref_exists(root, "MERGE_HEAD"):
        _name_status(pathset, root, ["diff", "--cached", "--name-status", "-z", "MERGE_HEAD"],
                     False)
    else:
        _name_status(pathset, root, ["diff", "--cached", "--name-status", "-z"], False)
    if commit.get("all"):
        _name_status(pathset, root, ["diff", "--name-status", "-z"], True)
    if commit.get("amend"):
        _name_status(pathset, root, ["diff-tree", "--no-commit-id", "--name-status", "-r",
                                     "--root", "-z", "HEAD"], False)
    cwd = commit.get("cwd") or root
    if commit.get("pathspecs"):
        _diff_head(pathset, cwd, commit["pathspecs"])
        for spec in commit["pathspecs"]:
            rel = _rel(root, cwd, spec)
            if rel:
                pathset.add("M", rel, worktree=True)
    for stage in stages:
        _collect_stage(pathset, root, stage)
    return pathset


def _collect_stage(pathset: PathSet, root: str, stage: Dict) -> None:
    """Paths of a ``git add/rm/mv`` that runs before the commit on the same line.

    The hook runs before the whole line, so such a command has not staged anything yet.
    """
    cwd = stage.get("cwd")
    specs = stage.get("pathspecs") or []
    if cwd is None or any("$" in s for s in specs):
        if stage["op"] == "add":   # cannot resolve: everything that could be added
            _diff_head(pathset, root, [])
            _ls_files(pathset, root, ["--others", "--exclude-standard"], "A")
        return
    if stage["op"] == "add":
        if not specs:
            if stage.get("all") or stage.get("update"):
                _diff_head(pathset, root, [])
            if stage.get("all"):
                _ls_files(pathset, root, ["--others", "--exclude-standard"], "A")
            return
        _diff_head(pathset, cwd, specs)
        if not stage.get("update"):
            extra = [] if stage.get("force") else ["--exclude-standard"]
            _ls_files(pathset, cwd, ["--others"] + extra + ["--"] + specs, "A")
    elif stage["op"] == "rm" and specs:
        _ls_files(pathset, cwd, ["--"] + specs, "D")
    elif stage["op"] == "mv" and len(specs) >= 2:
        sources, dest = specs[:-1], specs[-1]
        dest_rel = _rel(root, cwd, dest)
        if dest_rel is None:
            return
        into_dir = len(sources) > 1 or os.path.isdir(os.path.join(cwd, dest))
        for source in sources:
            src_rel = _rel(root, cwd, source)
            if src_rel is None:
                continue
            rc, out = common.git_bytes(cwd, "ls-files", "--full-name", "-z", "--", source)
            base = dest_rel + "/" + os.path.basename(src_rel) if into_dir else dest_rel
            for tracked in out.decode("utf-8", "surrogateescape").split("\0") if rc == 0 else []:
                if not tracked:
                    continue
                pathset.add("D", tracked, worktree=True)
                suffix = tracked[len(src_rel):] if tracked != src_rel else ""
                pathset.add("A", base + suffix, worktree=True)


# --------------------------------------------------------------------------- secrets (5.2)

def _alternatives(pattern: str) -> List[str]:
    """Top-level alternatives of a regex, so a match can be named without quoting it."""
    parts, buf, depth, in_class, i = [], "", 0, False, 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            buf += pattern[i:i + 2]
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0:
            parts.append(buf)
            buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return parts


def _label(pattern: str, text: str) -> str:
    for index, alternative in enumerate(_alternatives(pattern), 1):
        try:
            if not re.search(alternative, text):
                continue
        except re.error:
            continue
        for needle, label in CONTENT_LABELS:
            if needle in alternative:
                return label
        return "secret pattern #{} of SECRET_CONTENT_RE".format(index)
    return "secret pattern of SECRET_CONTENT_RE"


def _scan(data: bytes, content_re: "re.Pattern") -> Optional[str]:
    if b"\0" in data[:8192]:
        return None
    text = data.decode("utf-8", "replace")
    if any(FIXTURE_MARKER in line for line in text.split("\n", 5)[:5]):
        return None
    if not content_re.search(text):
        return None
    return _label(content_re.pattern, text)


def _contents(root: str, path: str, entry: Dict) -> List[bytes]:
    blobs = []
    if entry["index"]:
        rc, size = common.git(root, "cat-file", "-s", ":" + path)
        if rc == 0 and size.strip().isdigit() and int(size.strip()) <= MAX_SCAN_BYTES:
            rc, data = common.git_bytes(root, "cat-file", "blob", ":" + path)
            if rc == 0:
                blobs.append(data)
    if entry["worktree"]:
        full = os.path.join(root, path)
        try:
            if os.path.isfile(full) and os.path.getsize(full) <= MAX_SCAN_BYTES:
                with open(full, "rb") as handle:
                    blobs.append(handle.read())
        except OSError:
            pass
    return blobs


def check_secrets(root: str, pathset: PathSet, conf: Dict[str, str]) -> None:
    path_re = common.conf_regex(conf, "SECRET_PATH_RE")
    allow_re = common.conf_regex(conf, "SECRET_ALLOW_RE")
    content_re = common.conf_regex(conf, "SECRET_CONTENT_RE")
    remedy = ("Remedy: `git -C {root} reset -- {path}` (or `git rm --cached {path}`), move the "
              "value to an untracked file, and revoke it if it was ever pushed.")
    for path, entry in pathset.entries.items():
        if not entry["statuses"] - {"D"}:
            continue
        if allow_re and allow_re.search(path):
            continue
        if path_re and path_re.search(path):
            raise Refusal("secret-path", "{} matches SECRET_PATH_RE: secrets live in untracked "
                          "files only. ".format(path) + remedy.format(root=root, path=path))
        if content_re:
            for blob in _contents(root, path, entry):
                label = _scan(blob, content_re)
                if label:
                    raise Refusal("secret-content",
                                  "{} contains what looks like a {} (the match is not shown, so "
                                  "it stays out of the transcript). A test fixture carries "
                                  "`{}` in its first five lines. ".format(path, label,
                                                                          FIXTURE_MARKER)
                                  + remedy.format(root=root, path=path))


# --------------------------------------------------------------------------- wip (5.3)

def check_wip(root: str, pathset: PathSet) -> None:
    if not os.path.isdir(os.path.join(root, "wip", "done")):
        return
    for name in ("TODO.md", "DONE.md"):
        entry = pathset.entries.get(name)
        if entry and "A" in entry["statuses"]:
            raise Refusal("wip-shared-list",
                          "{} at the repository root is a shared list: it conflicts on every "
                          "parallel pull request. Remedy: one file per entry under wip/ (see "
                          "wip/README.md), then `git -C {} reset -- {}`.".format(name, root, name))
    added = {os.path.basename(p) for p, e in pathset.entries.items()
             if p.startswith("wip/") and "A" in e["statuses"]}
    for path, entry in pathset.entries.items():
        if "D" in entry["statuses"] and path.startswith(WIP_ENTRY_DIRS) \
                and os.path.basename(path) not in added:
            raise Refusal("wip-entry-deleted",
                          "{} is deleted: a wip/ entry is never deleted, it moves to wip/done/ "
                          "with a `dropped` status. Remedy: `git -C {} restore --staged "
                          "--worktree -- {}`, then `git mv` it to wip/done/ and set its status."
                          .format(path, root, path))


# --------------------------------------------------------------------------- branch (5.4)

def check_branch(root: str, conf: Dict[str, str]) -> None:
    default = conf.get("DEFAULT_BRANCH") or "main"
    upstream = "origin/" + default
    if not common.ref_exists(root, "refs/remotes/" + upstream):
        return   # the very first commit of a new repository
    branch = common.current_branch(root)
    recipe = ("`git fetch --prune origin && git switch -c <type>/<topic> {u}`, then cherry-pick "
              "the commits marked + by `git cherry -v {u} {b}`.")
    if branch is None:
        raise Refusal("detached-head", "{} is on a detached HEAD: a commit there belongs to no "
                      "branch. Remedy: `git -C {} switch -c <type>/<topic>` first, then commit."
                      .format(root, root))
    if branch == default:
        raise Refusal("default-branch",
                      "{r} is on {d}: the main checkout stays on {d} — it is what gets "
                      "fast-forwarded, deployed from, and branched off for agent worktrees — and "
                      "never commits. Remedy: start the work in its own worktree: `git fetch "
                      "--prune origin && git worktree add {p}<topic> -b <type>/<topic> {u}`."
                      .format(r=root, d=default, p=conf.get("WORKTREE_PREFIX", "../"),
                              u=upstream))
    if common.upstream_gone(root, branch):
        raise Refusal("stale-branch",
                      "branch {} tracks an upstream that is gone: its pull request was merged and"
                      " the remote branch deleted. Remedy: ".format(branch)
                      + recipe.format(u=upstream, b=branch))
    ahead = common.ahead_count(root, upstream)
    if ahead is not None and 1 <= ahead <= 50 and common.cherry_has_minus(root, upstream):
        raise Refusal("already-on-default",
                      "branch {} carries commits whose patch is already on {} (replayed or "
                      "cherry-picked; the hook cannot tell which). Remedy: ".format(branch,
                                                                                   upstream)
                      + recipe.format(u=upstream, b=branch))


# --------------------------------------------------------------------------- gates (5.6)

def run_gates(root: str, paths: List[str]) -> None:
    script = os.path.join(root, "scripts", "check.sh")
    if not (os.path.isfile(script) and os.access(script, os.X_OK)):
        sys.stderr.write("note: {} is missing or not executable: commit gates skipped.\n"
                         .format(script))
        return
    try:
        timeout = float(os.environ.get("HOOK_GATE_TIMEOUT", "280"))
    except ValueError:
        timeout = 280.0
    handle = tempfile.NamedTemporaryFile("w", suffix=".paths", delete=False, encoding="utf-8",
                                         errors="surrogateescape")
    try:
        with handle:
            handle.write("".join(p + "\n" for p in paths))
        rc, out = common.run_capped([script, "fast", "--paths-from", handle.name], root, timeout)
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    if rc == 0:
        return
    lines = out.rstrip("\n").splitlines()
    tail = lines[-GATE_TAIL_LINES:]
    reproduce = [line for line in lines if line.startswith("Reproduce with:")]
    if reproduce and reproduce[-1] not in tail:
        tail.append(reproduce[-1])
    if rc == 1:
        raise Refusal("gates", "`scripts/check.sh fast` failed in {}:\n{}\nRemedy: fix what it "
                      "reports, then commit again.".format(root, "\n".join(tail)))
    if rc == 3:
        setup = [line for line in lines if line.startswith("SETUP:")]
        command = setup[-1][len("SETUP:"):].strip() if setup else "(no SETUP line printed)"
        raise Refusal("gates-tool-missing",
                      "a tool the gates need is missing in {}. Remedy: run `{}` in its own Bash "
                      "call, then commit again — the hook judges the whole line before anything"
                      " runs, so `install && git commit` never passes.".format(root, command))
    what = "timed out after {:g}s".format(timeout) if rc == common.TIMED_OUT else \
        "could not start" if rc is None else "exited {}".format(rc)
    raise Refusal("gates-error", "`scripts/check.sh fast` {} in {}:\n{}\nRemedy: run "
                  "`scripts/check.sh fast` yourself in that directory, fix it, then commit "
                  "again.".format(what, root, "\n".join(tail)))


# --------------------------------------------------------------------------- driver

def judge_commit(root: str, commit: Dict, stages: List[Dict]) -> None:
    conf = common.load_conf(root)
    try:
        for key in ("SECRET_PATH_RE", "SECRET_ALLOW_RE", "SECRET_CONTENT_RE"):
            common.conf_regex(conf, key)
    except common.ConfigError as exc:
        raise Refusal("bad-config", "{}. Remedy: fix scripts/lib/tooling.conf; until then no "
                      "secret check can run.".format(exc))
    pathset = collect_paths(root, commit, stages)
    check_secrets(root, pathset, conf)
    check_wip(root, pathset)
    check_branch(root, conf)
    run_gates(root, pathset.paths())


def unknown_repo(what: str, parse_ok: bool) -> str:
    why = ("the command line could not be parsed (an unbalanced quote?) and it changes "
           "directory" if not parse_ok else
           "an unexpanded variable, `$(...)`, `cd -`, `popd`, or `--git-dir`/`--work-tree`")
    return ("BLOCKED (unknown-repo) cannot tell which repository this `{}` runs in ({}), so no "
            "other rule can judge it. Remedy: name the repository explicitly: `git -C <absolute"
            " path> {} ...`.".format(what, why, what.split()[-1]))


class Scope:
    """Which repositories the rules apply in: those that carry scripts/lib/tooling.conf.

    A command whose directory cannot be told is judged by the session's repository (the
    payload's ``cwd``), so an unreadable line in a bootstrapped project is still refused.
    """

    def __init__(self, session_root: Optional[str]):
        self.session_root = session_root
        self.cache = {}  # type: Dict[str, Optional[str]]

    def root(self, cwd: Optional[str]) -> Optional[str]:
        if cwd is None:
            return None
        if cwd not in self.cache:
            self.cache[cwd] = common.repo_root(cwd)
        return self.cache[cwd]

    def active(self, cwd: Optional[str]) -> bool:
        return common.is_bootstrapped(self.root(cwd) if cwd is not None else self.session_root)


def state_blocks(verdict: Dict, scope: Scope) -> List[str]:
    """Blocks from the parser, after the stacked-pr unlock, plus the state-dependent ones."""
    messages = []  # type: List[str]
    for block in verdict["blocks"]:
        cwd = block.get("cwd")
        if not scope.active(cwd):
            continue
        if block["rule"] == "stacked-pr":
            root = scope.root(cwd) if cwd is not None else scope.session_root
            if root:
                ns = common.load_conf(root).get("GIT_CONFIG_NS") or "project"
                if common.config_bool(root, ns + ".allowStackedPr"):
                    continue
        messages.append("BLOCKED ({}) {}".format(block["rule"], block["message"]))
    for push in verdict["pushes"]:
        if not (push["bare"] or push["head_ref"]) or not scope.active(push["cwd"]):
            continue
        if push["cwd"] is None:
            messages.append(unknown_repo("git push", verdict["parse_ok"]))
            continue
        root = scope.root(push["cwd"])
        default = common.load_conf(root).get("DEFAULT_BRANCH") or "main"
        if common.current_branch(root) == default:
            messages.append("BLOCKED (push-main) " + push_main_message(default))
    for commit in verdict["commits"]:
        if commit["cwd"] is None and scope.active(None):
            messages.append(unknown_repo("git commit", verdict["parse_ok"]))
    unique = []  # type: List[str]
    for message in messages:
        if message not in unique:
            unique.append(message)
    return unique


def hook_main() -> int:
    payload = common.read_payload()
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    if "git" not in command and "gh" not in command:
        return 0   # nothing the parser acts on: no git, gh, bash -c or eval of either
    cwd = payload.get("cwd") or os.getcwd()
    scope = Scope(common.repo_root(cwd))
    verdict = parse(command, cwd, common.load_conf(scope.session_root))
    messages = state_blocks(verdict, scope)
    if messages:
        sys.stderr.write("\n\n".join(messages) + "\n")
        return 2
    for commit in verdict["commits"]:
        root = scope.root(commit["cwd"])
        if root is None or not common.is_bootstrapped(root):
            continue   # outside a repository it fails on its own; elsewhere shipyard is inert
        stages = [s for s in verdict.get("stages", [])
                  if s.get("seq", 0) < commit.get("seq", 0)
                  and (s.get("cwd") is None or scope.root(s["cwd"]) == root)]
        try:
            judge_commit(root, commit, stages)
        except Refusal as refusal:
            sys.stderr.write(refusal.text() + "\n")
            return 2
    return 0


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    return hook_main()


if __name__ == "__main__":
    common.run_main(main)
