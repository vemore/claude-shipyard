#!/usr/bin/env python3
"""Gates for commits made outside Claude Code: staged secrets, then the fast gates.

Usage:
  scripts/precommit.py           run by .githooks/pre-commit (activate once per clone with
                                 `git config core.hooksPath .githooks`)
  scripts/precommit.py --help    this text

Guarantees: judges what the commit records — the index git hands its pre-commit hook, so the
files of `git commit -a` or `git commit <paths>` are included. Refuses a staged path that
matches SECRET_PATH_RE (and not SECRET_ALLOW_RE), and a staged file of 1 MB or less, not
binary, whose content matches SECRET_CONTENT_RE, unless it carries `secret-scan: fixture` in
its first five lines; the message names the path and the kind of secret, never the match.
Then runs `scripts/check.sh fast --paths-from <staged paths>` and refuses when it does not
exit 0 (3 = a tool is missing: run the SETUP command it prints). During a merge, the paths
are those that differ from MERGE_HEAD (the branch's own changes and the resolutions).
Exit codes: 0 pass · 1 refused · 2 configuration error (no scripts/lib/tooling.conf, or a
SECRET_* regex that does not compile). Git refuses the commit on any code but 0.

Does not cover: commits made inside Claude Code (CLAUDECODE=1: the shipyard plugin's
PreToolUse hook already judged them, with the branch and wip/ rules on top); test suites (CI
runs them); `git commit --no-verify`, the deliberate human escape hatch.

Why it exists: Claude Code's hooks only see Claude's commands; without this, a commit made in
a terminal or an IDE reaches CI without its gates, and a key file reaches the remote.
"""

import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

CONF_RELPATH = os.path.join("scripts", "lib", "tooling.conf")
MAX_SCAN_BYTES = 1024 * 1024
FIXTURE_MARKER = "secret-scan: fixture"
BYPASS = "(bypass deliberately: git commit --no-verify)"
CONTENT_LABELS = [("PRIVATE KEY", "private key header"),
                  ("service_account", "cloud service-account key file"),
                  ("AKIA", "cloud access key id"),
                  ("ghp_", "GitHub token"), ("github_pat_", "GitHub token"),
                  ("xox", "Slack token"), ("sk-", "API secret key")]


class Refusal(Exception):
    def __init__(self, rule: str, message: str, code: int = 1):
        Exception.__init__(self, message)
        self.rule = rule
        self.message = message
        self.code = code


# --------------------------------------------------------------------------- plumbing

def git(root: str, *args: str) -> Tuple[int, bytes]:
    """``git args`` in ``root``, inheriting the environment git gives its hook
    (GIT_INDEX_FILE names the index being committed)."""
    env = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        proc = subprocess.run(["git"] + list(args), cwd=root, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except OSError:
        return 127, b""
    return proc.returncode, proc.stdout


def repo_root() -> Optional[str]:
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    top = proc.stdout.decode("utf-8", "replace").strip()
    return top if proc.returncode == 0 and top else None


def load_conf(root: str) -> Dict[str, str]:
    """``KEY=value`` lines of scripts/lib/tooling.conf; one pair of outer quotes removed."""
    path = os.path.join(root, CONF_RELPATH)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        raise Refusal("bad-config", "{} is missing or unreadable: the secret rules live there."
                      " Remedy: restore it (`git checkout -- {}`).".format(CONF_RELPATH,
                                                                          CONF_RELPATH), 2)
    values = {}  # type: Dict[str, str]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def conf_regex(conf: Dict[str, str], key: str) -> "Optional[re.Pattern]":
    value = conf.get(key, "")
    if not value:
        return None   # an empty regex switches its rule off
    try:
        return re.compile(value)
    except re.error as exc:
        raise Refusal("bad-config", "{} in {} is not a valid regex ({}): no secret check can "
                      "run until it is fixed.".format(key, CONF_RELPATH, exc), 2)


# --------------------------------------------------------------------------- staged paths

def staged(root: str) -> Dict[str, str]:
    """Staged path -> status letter (A, M, D, T…); a rename is a D and an A."""
    args = ["diff", "--cached", "--name-status", "-z", "--no-renames"]
    rc, _ = git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if rc == 0:
        args.append("MERGE_HEAD")
    rc, out = git(root, *args)
    if rc != 0:
        raise Refusal("gates-error", "`git {}` failed: the staged paths cannot be read."
                      .format(" ".join(args)))
    parts = out.decode("utf-8", "surrogateescape").split("\0")
    entries = {}  # type: Dict[str, str]
    for i in range(0, len(parts) - 1, 2):
        if parts[i] and parts[i + 1]:
            entries[parts[i + 1]] = parts[i][0]
    return entries


# --------------------------------------------------------------------------- secrets

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


def label(pattern: str, text: str) -> str:
    for index, alternative in enumerate(_alternatives(pattern), 1):
        try:
            if not re.search(alternative, text):
                continue
        except re.error:
            continue
        for needle, name in CONTENT_LABELS:
            if needle in alternative:
                return name
        return "secret pattern #{} of SECRET_CONTENT_RE".format(index)
    return "secret pattern of SECRET_CONTENT_RE"


def scan(data: bytes, content_re: "re.Pattern") -> Optional[str]:
    """The kind of secret ``data`` holds, or None (binary, fixture, or nothing found)."""
    if b"\0" in data[:8192]:
        return None
    text = data.decode("utf-8", "replace")
    if any(FIXTURE_MARKER in line for line in text.split("\n", 5)[:5]):
        return None
    if not content_re.search(text):
        return None
    return label(content_re.pattern, text)


def staged_blob(root: str, path: str) -> Optional[bytes]:
    rc, size = git(root, "cat-file", "-s", ":" + path)
    size_text = size.decode("ascii", "replace").strip()
    if rc != 0 or not size_text.isdigit() or int(size_text) > MAX_SCAN_BYTES:
        return None
    rc, data = git(root, "cat-file", "blob", ":" + path)
    return data if rc == 0 else None


def check_secrets(root: str, entries: Dict[str, str], conf: Dict[str, str]) -> None:
    path_re = conf_regex(conf, "SECRET_PATH_RE")
    allow_re = conf_regex(conf, "SECRET_ALLOW_RE")
    content_re = conf_regex(conf, "SECRET_CONTENT_RE")
    remedy = ("Remedy: `git reset -- {path}` (or `git rm --cached {path}`), move the value to an "
              "untracked file, and revoke it if it was ever pushed.")
    for path, status in sorted(entries.items()):
        if status == "D" or (allow_re and allow_re.search(path)):
            continue
        if path_re and path_re.search(path):
            raise Refusal("secret-path", "{} matches SECRET_PATH_RE: secrets live in untracked "
                          "files only. ".format(path) + remedy.format(path=path))
        if content_re:
            data = staged_blob(root, path)
            kind = scan(data, content_re) if data is not None else None
            if kind:
                raise Refusal("secret-content",
                              "{} contains what looks like a {} (the match is not shown). A "
                              "test fixture carries `{}` in its first five lines. ".format(
                                  path, kind, FIXTURE_MARKER) + remedy.format(path=path))


# --------------------------------------------------------------------------- gates

def run_gates(root: str, paths: List[str]) -> None:
    script = os.path.join(root, "scripts", "check.sh")
    if not (os.path.isfile(script) and os.access(script, os.X_OK)):
        sys.stderr.write("pre-commit: note: scripts/check.sh is missing or not executable: "
                         "gates skipped.\n")
        return
    handle = tempfile.NamedTemporaryFile("w", suffix=".paths", delete=False, encoding="utf-8",
                                         errors="surrogateescape")
    try:
        with handle:
            handle.write("".join(p + "\n" for p in paths))
        sys.stdout.flush()
        sys.stderr.flush()
        try:   # the output goes straight to the terminal: a person reads it whole
            rc = subprocess.run([script, "fast", "--paths-from", handle.name], cwd=root,
                                stdin=subprocess.DEVNULL).returncode
        except OSError as exc:
            raise Refusal("gates-error", "scripts/check.sh could not start ({}).".format(exc))
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    if rc == 0:
        return
    if rc == 1:
        raise Refusal("gates", "`scripts/check.sh fast` failed (output above). Remedy: fix what "
                      "it reports, stage the fix, and commit again.")
    if rc == 3:
        raise Refusal("gates-tool-missing", "a tool the gates need is missing. Remedy: run the "
                      "command of the `SETUP:` line above, then commit again.")
    raise Refusal("gates-error", "`scripts/check.sh fast` exited {} (output above). Remedy: run"
                  " `scripts/check.sh fast` yourself, fix it, then commit again.".format(rc))


# --------------------------------------------------------------------------- driver

def main(argv: List[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    if os.environ.get("CLAUDECODE") == "1":
        return 0   # inside Claude Code, the plugin's PreToolUse hook already ran all of this
    root = repo_root()
    if root is None:
        return 0
    try:
        conf = load_conf(root)
        entries = staged(root)
        check_secrets(root, entries, conf)
        run_gates(root, sorted(entries))
    except Refusal as refusal:
        sys.stderr.write("BLOCKED ({}) {}\n{}\n".format(refusal.rule, refusal.message, BYPASS))
        return refusal.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
