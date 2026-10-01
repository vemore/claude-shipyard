#!/usr/bin/env python3
"""Who owns a path, by the repository's CODEOWNERS; or which patterns a login owns.

Usage:
    git diff --name-only origin/<default-branch>...HEAD | scripts/owners.py
    scripts/owners.py --who LOGIN

Without --who: paths on stdin, one per line (blank lines ignored, edge spaces and a leading `./`
or `/` stripped); one output line per path, `<path><TAB><owner> <owner>…`, the owners as written
in CODEOWNERS (`@login`, `@org/team`, an e-mail). A path no pattern matches, or whose last
matching pattern lists no owner, prints with an empty owner list.
With --who LOGIN (with or without the `@`): the patterns that list @LOGIN among their owners, one
per line, in file order; stdin is not read. Logins compare without case, as on GitHub.
Exit: 0; 1 with --who when LOGIN owns no pattern; 2 no CODEOWNERS file, not a git repository, or
a usage error.

CODEOWNERS is the first of `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS` at the root of
the repository (`git rev-parse --show-toplevel`), GitHub's order. Semantics, GitHub's:
  - one pattern per line, then its owners; `#` starts a comment, also after the owners; `\\ `
    escapes a space in a pattern;
  - the LAST pattern that matches a path wins (a later pattern with no owner un-owns a path);
  - patterns are gitignore-style and case-sensitive: a leading `/`, or a `/` inside the pattern,
    anchors it to the root, otherwise it matches at any depth (`*.js`, `apps/`, `logs`);
    `*` and `?` never cross a `/`; `**/` matches any leading directories, `/**` everything
    below, `/**/` zero or more directories; a trailing `/` matches a directory's contents only;
    a pattern naming a directory owns everything below it (`/apps/github`), except that a
    final `/*` owns the files directly in that directory and not deeper (`docs/*`).
  - lines GitHub refuses are skipped with a warning on stderr: a `!` negation; `[ ]` is taken
    literally (GitHub does not support ranges either).
Does not cover: team membership (`@org/team` is never expanded, so --who matches only a login
listed by name); whether an owner has write access; GitHub's 3 MB limit.
Why: in a team, a pull request that touches another member's zone waits for that owner's
approval, and the session hook tells a member which zones they own. One parser of the file
GitHub reads keeps the planning (ship-parallel), the hook and GitHub in agreement.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf

LOCATIONS = (
    os.path.join(".github", "CODEOWNERS"),
    "CODEOWNERS",
    os.path.join("docs", "CODEOWNERS"),
)

Rule = namedtuple("Rule", "lineno pattern owners regex")


def find_codeowners(root):
    for rel in LOCATIONS:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            return path
    return None


def split_line(line):
    """Split on unescaped whitespace; `\\ ` is a literal space inside a token."""
    tokens, cur, i = [], "", 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] in " \t":
            cur += line[i + 1]
            i += 2
            continue
        if ch in " \t":
            if cur:
                tokens.append(cur)
                cur = ""
        else:
            cur += ch
        i += 1
    if cur:
        tokens.append(cur)
    return tokens


def translate_segment(seg):
    if seg == "*":
        return "[^/]+"
    out = []
    for ch in seg:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def compile_pattern(pattern):
    """The regex a path (no leading slash) must match in full, or None for an invalid pattern."""
    if not pattern or pattern.startswith("!"):
        return None
    dir_only = pattern.endswith("/")
    body = pattern[1:] if pattern.startswith("/") else pattern
    body = body.rstrip("/")
    if not body:
        return None
    anchored = pattern.startswith("/") or "/" in body
    segs = [s for s in body.split("/") if s]
    parts, need_sep = [], False
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == "**":
            if len(segs) == 1:
                parts.append(".*")
            elif i == 0:
                parts.append("(?:.*/)?")
                need_sep = False
            elif last:
                parts.append("/.*")
            else:
                parts.append("(?:/.*)?")
                need_sep = True
            continue
        if need_sep:
            parts.append("/")
        parts.append(translate_segment(seg))
        need_sep = True
    if segs[-1] == "**":
        suffix = ""
    elif dir_only:
        suffix = "/.*"
    elif segs[-1] == "*":
        suffix = ""  # `docs/*`: the files directly in docs/, not deeper (GitHub)
    else:
        suffix = "(?:/.*)?"  # the file itself, or everything below a directory of that name
    prefix = r"\A" if anchored else r"\A(?:.*/)?"
    return re.compile(prefix + "".join(parts) + suffix + r"\Z")


def parse(text, warn=None):
    rules = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = split_line(line)
        pattern, owners = tokens[0], []
        for token in tokens[1:]:
            if token.startswith("#"):
                break
            owners.append(token)
        regex = compile_pattern(pattern)
        if regex is None:
            if warn:
                warn(f"line {lineno}: pattern {pattern!r} is not supported by GitHub; skipped")
            continue
        rules.append(Rule(lineno, pattern, owners, regex))
    return rules


def normalize(path):
    path = path.strip()
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def owners_of(path, rules):
    """The owners of the last rule matching `path` ([] when none matches)."""
    found = []
    for rule in rules:
        if rule.regex.match(path):
            found = rule.owners
    return found


def owned_by(login, rules):
    """The patterns listing @login among their owners, in file order, each once."""
    want = "@" + login.lstrip("@").lower()
    patterns = []
    for rule in rules:
        if any(owner.lower() == want for owner in rule.owners) and rule.pattern not in patterns:
            patterns.append(rule.pattern)
    return patterns


def main(argv):
    parser = argparse.ArgumentParser(
        prog="owners.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--who", metavar="LOGIN", help="list the patterns LOGIN owns")
    args = parser.parse_args(argv[1:])
    if args.who is not None and not args.who.lstrip("@"):
        parser.error("--who needs a login")
    data = None
    if args.who is None:
        data = sys.stdin.buffer.read().decode("utf-8", "replace")  # to the end: no SIGPIPE
    try:
        root = conf.repo_root()
    except conf.ConfError as exc:
        print(f"owners.py: {exc}", file=sys.stderr)
        return 2
    path = find_codeowners(root)
    if path is None:
        print(
            "owners.py: no CODEOWNERS file (looked for .github/CODEOWNERS, CODEOWNERS, "
            "docs/CODEOWNERS)",
            file=sys.stderr,
        )
        return 2
    with open(path, encoding="utf-8", errors="replace") as fh:
        rel = os.path.relpath(path, root)
        rules = parse(fh.read(), warn=lambda msg: print(f"owners.py: {rel} {msg}", file=sys.stderr))
    if args.who is not None:
        patterns = owned_by(args.who, rules)
        for pattern in patterns:
            print(pattern)
        return 0 if patterns else 1
    for line in data.splitlines():
        file_path = normalize(line)
        if file_path:
            print(f"{file_path}\t{' '.join(owners_of(file_path, rules))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
