#!/usr/bin/env python3
"""Decide which component CI jobs a change needs: changed paths in, one flag per component out.

Usage:
    git diff --name-only origin/<default-branch>...HEAD | scripts/ci_scope.py

Input: changed paths on stdin, one per line (blank lines ignored, edge spaces stripped). A rename
must give both the old and the new path. Output: one line `<component>=true|false` per component
of COMPONENTS (scripts/lib/tooling.conf), in that order. Exit 0; 2 when tooling.conf is missing
or inconsistent (in CI a failed `scope` step makes every component job run, and
`scripts/check.sh fast` runs every component when this script fails).

The rules, for each path, in this order:
  1. every component whose COMPONENT_<ID>_RE matches the path (re.search) is selected; a path
     two regexes match (a shared schema, a root manifest) selects both;
  2. otherwise documentation selects nothing: `\\.md$`, `^wip/`, `^\\.llmwiki/`, `^docs/`;
  3. otherwise the path selects every component (the catch-all): `.github/`, `.claude/` outside
     Markdown, `scripts/` (check.sh and tooling.conf included: changing a gate must run it), and
     any path no rule knows.
The flags add up (OR) over all the paths. <ID> is the component id in upper case with `-` turned
into `_` (`my-api` -> COMPONENT_MY_API_RE). Components come first so that a file that looks like
documentation but that a component checks (a published privacy policy, a docs site, a SKILL.md
read by a test) is written into that component's regex; Markdown inside a component's directory
therefore runs that component, unless its regex excludes it (`^api/(?!.*\\.md$)`).

Configuration errors (exit 2): a component of COMPONENTS without its COMPONENT_<ID>_RE key, an
empty or invalid regex (an empty one would match every path), a COMPONENT_*_RE key that names no
component of COMPONENTS (a renamed component whose old key stayed behind).

Guarantees: a pure function of the paths and tooling.conf, with no network and no `gh`, so a
past pull request replays with a plain `git diff`. stdin is always read to the end, even when the
answer is already "everything" or the configuration is broken: an early exit would SIGPIPE the
producer and fail the CI step under `pipefail`. Empty input means every flag false.
Does not cover: the `tooling` job, which always runs and is not in the output; the 3000-file
limit of the GitHub files API, which the CI step handles before calling this script.
Why: the paths-to-components table exists once, in tooling.conf. CI scopes its jobs with it, and
the commit hook (`scripts/check.sh fast --paths-from`) runs the gates of exactly the components
whose CI jobs will run. Getting it wrong must cost a slow run, never an untested merge: a rule
that is too narrow turns nothing red, it lets through what nothing tested.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf

DOCS_RE = re.compile(r"\.md$|^wip/|^\.llmwiki/|^docs/")
COMPONENT_KEY_RE = re.compile(r"^COMPONENT_[A-Z0-9_]+_RE$")


def load_rules(cfg):
    """[(component, compiled regex)] in COMPONENTS order; ConfError on any inconsistency."""
    components = cfg.components()
    rules = []
    for comp in components:
        key = conf.component_key(comp)
        if not cfg[key].strip():
            raise conf.ConfError(
                f"key {key} in scripts/lib/tooling.conf is empty: it would match every path"
            )
        rules.append((comp, cfg.get_regex(key)))
    expected = {conf.component_key(c) for c in components}
    stray = sorted(k for k in cfg if COMPONENT_KEY_RE.match(k) and k not in expected)
    if stray:
        raise conf.ConfError(
            f"{', '.join(stray)} in scripts/lib/tooling.conf name(s) no component of "
            f"COMPONENTS ({' '.join(components) or 'empty'})"
        )
    return rules


def targets(path, rules):
    """The components `path` selects: a set, possibly empty (documentation), or None for all."""
    hit = {comp for comp, regex in rules if regex.search(path)}
    if hit:
        return hit
    if DOCS_RE.search(path):
        return set()
    return None


def scope(paths, rules):
    """Map each component of `rules` to True when at least one path selects it."""
    flags = {comp: False for comp, _ in rules}
    for path in paths:
        selected = targets(path, rules)
        for comp in flags if selected is None else selected:
            flags[comp] = True
    return flags


def main(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    data = sys.stdin.buffer.read().decode("utf-8", "replace")  # to the end: no SIGPIPE upstream
    if len(argv) > 1:
        print(f"ci_scope.py: unexpected argument: {argv[1]} (paths come on stdin)", file=sys.stderr)
        return 2
    try:
        rules = load_rules(conf.load_conf(conf.repo_root()))
    except conf.ConfError as exc:
        print(f"ci_scope.py: {exc}", file=sys.stderr)
        return 2
    paths = [line.strip() for line in data.splitlines() if line.strip()]
    flags = scope(paths, rules)
    for comp, _ in rules:
        print(f"{comp}={'true' if flags[comp] else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
