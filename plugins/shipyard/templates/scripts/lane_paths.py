#!/usr/bin/env python3
"""Which changed paths put a pull request in lane C, or need a deploy.

Usage:
    gh pr diff <n> --name-only | scripts/lane_paths.py lane-c
    git diff --name-only <sha>^ <sha> | scripts/lane_paths.py deploy

Reads paths on stdin, one per line (blank lines ignored, edge spaces stripped; a path may hold
spaces), loads scripts/lib/tooling.conf from the root of the git repository it runs in
(`git rev-parse --show-toplevel`), and prints the paths that match LANE_C_RE (lane-c) or
DEPLOY_PATHS_RE (deploy), one per line, in input order, each once.

Exit: 0 at least one path matches; 1 no path matches (an empty regex matches nothing: no lane C,
nothing to deploy); 2 usage error, not a git repository, or tooling.conf unreadable, without
the key, or holding an invalid regex.

Guarantees: the regex is evaluated by Python's `re` (re.search), like every *_RE value of
tooling.conf; stdin is read to the end before anything else, so the producer of the paths never
gets SIGPIPE; no network access.
Does not cover: deciding the lane — that is the planning step of the ship-parallel skill, which
judges what a change will touch before the code exists; this is its backstop on the real diff.
Why: the regexes of tooling.conf are Python regexes, and a `grep -E` line with nested quoting
copied by an agent is exactly what breaks without a sound (`\\d`, `(?<!…)` and `[[:space:]]` do
not mean the same thing to both).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf

KEYS = {"lane-c": "LANE_C_RE", "deploy": "DEPLOY_PATHS_RE"}


def main(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    # Read everything first: the producer must never see a closed pipe.
    data = sys.stdin.buffer.read().decode("utf-8", "replace")
    if len(argv) != 2 or argv[1] not in KEYS:
        print(f"usage: lane_paths.py {{{'|'.join(sorted(KEYS))}}} < paths", file=sys.stderr)
        return 2
    key = KEYS[argv[1]]
    try:
        cfg = conf.load_conf(conf.repo_root())
        pattern = cfg[key]
        regex = cfg.get_regex(key) if pattern else None
    except conf.ConfError as exc:
        print(f"lane_paths.py: {exc}", file=sys.stderr)
        return 2
    if regex is None:
        return 1  # an empty regex matches nothing, by contract
    matched, seen = [], set()
    for line in data.splitlines():
        path = line.strip()
        if path and path not in seen and regex.search(path):
            seen.add(path)
            matched.append(path)
    for path in matched:
        print(path)
    return 0 if matched else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
