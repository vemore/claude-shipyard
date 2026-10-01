#!/usr/bin/env python3
"""Size a pull request: the number of added lines of code, outside SIZE_EXCLUDE_RE.

Usage:
    scripts/pr_size.py <number>        # reads `gh pr diff <number>` (network, 60 s timeout)
    scripts/pr_size.py -               # reads a unified git diff on stdin
    scripts/pr_size.py -v <number>     # also lists per-file counts and excluded files on stderr

Prints one integer. Exit 0; 2 when `gh` is missing, fails or times out, on a usage error, or when
scripts/lib/tooling.conf is unreadable.

What is counted: the `+` lines inside the hunks of every file whose path does not match
SIZE_EXCLUDE_RE (scripts/lib/tooling.conf: docs, wip/, the wiki, tests, locks, generated files).
A file's path is the new path of its `diff --git a/X b/Y` header (quoted paths unquoted; a `+++`
or `rename to` line refines it). Only the lines after a file's first `@@` count, so the `+++ b/...`
header never does while a content line starting with `++` does. A deleted file and a binary file
count 0; a modified line is a `-`/`+` pair and counts once.
Does not cover: deleted lines, renames without content change, the meaning of a change.
Why: the size is the backstop for a lane misjudged at planning: above SIZE_THRESHOLD a pull
request is lane B whatever the plan said. It counts the production code a review must hold in
mind, not what is verified: counting deletions made a clean-up that removed dead guides look
huge, and counting tests made a well-tested change look bigger than an untested one.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf

ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f"}
ESCAPES.update({"r": "\r", "v": "\v"})


def unquote(token):
    """Undo git's C-style quoting of a path ("a/sp\\303\\251cial.py")."""
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        return token
    body, out, i = token[1:-1], bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            octal = body[i + 1 : i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8) & 0xFF)
                i += 4
                continue
            out += ESCAPES.get(body[i + 1], body[i + 1]).encode("utf-8")
            i += 2
            continue
        out += ch.encode("utf-8")
        i += 1
    return out.decode("utf-8", "replace")


def split_tokens(text):
    """Split a header into tokens; a token is either "quoted" or runs to the next space."""
    tokens, i = [], 0
    while i < len(text):
        if text[i] == " ":
            i += 1
            continue
        if text[i] == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            tokens.append(text[i : j + 1])
            i = j + 1
        else:
            j = text.find(" ", i)
            j = len(text) if j < 0 else j
            tokens.append(text[i:j])
            i = j
    return tokens


def strip_prefix(path, prefix):
    return path[len(prefix) :] if path.startswith(prefix) else path


def header_path(rest):
    """The new path of `diff --git <rest>`."""
    if '"' in rest:
        tokens = split_tokens(rest)
        if len(tokens) == 2:
            return strip_prefix(unquote(tokens[1]), "b/")
    # Unquoted, same path on both sides (the common case, spaces allowed): "a/P b/P".
    if len(rest) % 2 == 1 and rest[len(rest) // 2] == " ":
        old, new = rest[: len(rest) // 2], rest[len(rest) // 2 + 1 :]
        if strip_prefix(old, "a/") == strip_prefix(new, "b/"):
            return strip_prefix(new, "b/")
    idx = rest.rfind(" b/")
    if idx >= 0:
        return rest[idx + 3 :]
    return rest.split(" ")[-1]


def count(diff_text, exclude):
    """Return (total, per_file) where per_file is a list of (path, added, excluded)."""
    files = []
    current = None  # [path, added, in_hunk]
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = [header_path(line[len("diff --git ") :]), 0, False]
            files.append(current)
            continue
        if current is None:
            continue
        if not current[2]:
            if line.startswith("@@"):
                current[2] = True
            elif line.startswith("+++ "):
                name = line[4:].rstrip("\t")
                if name != "/dev/null":
                    current[0] = strip_prefix(unquote(name), "b/")
            elif line.startswith(("rename to ", "copy to ")):
                current[0] = unquote(line.split(" to ", 1)[1])
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            current[1] += 1
    per_file, total = [], 0
    for path, added, _ in files:
        excluded = bool(exclude) and re.search(exclude, path) is not None
        per_file.append((path, added, excluded))
        if not excluded:
            total += added
    return total, per_file


def read_pr_diff(number):
    try:
        proc = subprocess.run(
            ["gh", "pr", "diff", number], capture_output=True, timeout=60, check=False
        )
    except FileNotFoundError:
        print(
            "pr_size.py: gh is not installed; use `scripts/pr_size.py -` with a diff on stdin",
            file=sys.stderr,
        )
        return None
    except subprocess.TimeoutExpired:
        print(f"pr_size.py: gh pr diff {number} timed out after 60 s", file=sys.stderr)
        return None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        print(
            f"pr_size.py: gh pr diff {number} failed: {err or 'exit ' + str(proc.returncode)}",
            file=sys.stderr,
        )
        return None
    return proc.stdout.decode("utf-8", "replace")


def main(argv):
    parser = argparse.ArgumentParser(
        prog="pr_size.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", help="pull request number, or - for a diff on stdin")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="per-file counts and excluded files on stderr"
    )
    args = parser.parse_args(argv[1:])
    target = args.target.lstrip("#")
    if target != "-" and not target.isdigit():
        parser.error(f"not a pull request number: {args.target}")
    try:
        exclude = conf.load_conf(conf.repo_root())["SIZE_EXCLUDE_RE"]
        re.compile(exclude)
    except conf.ConfError as exc:
        print(f"pr_size.py: {exc}", file=sys.stderr)
        return 2
    except re.error as exc:
        print(f"pr_size.py: SIZE_EXCLUDE_RE is not a valid regex: {exc}", file=sys.stderr)
        return 2
    if target == "-":
        diff = sys.stdin.buffer.read().decode("utf-8", "replace")
    else:
        diff = read_pr_diff(target)
        if diff is None:
            return 2
    total, per_file = count(diff, exclude)
    if args.verbose:
        for path, added, excluded in per_file:
            label = "excluded" if excluded else "counted "
            print(f"  {label} {added:6d}  {path}", file=sys.stderr)
    print(total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
