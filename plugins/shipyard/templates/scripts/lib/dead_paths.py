"""Dead-path detection shared by scripts/wiki_lint.py and scripts/wip.py refine.

Rule: in Markdown text, a single-backtick span whose content starts with one of the roots of
DEAD_PATH_ROOTS (scripts/lib/tooling.conf) followed by `/` is a path reference. A span holding
`*`, `?`, `<`, `>`, `{`, `}`, `$`, a space or `...` is a pattern or a placeholder, not a
reference, and is ignored. A `:<line>` or `:<l1>-<l2>` suffix is kept aside for the line check,
then a `#anchor` and a trailing `/` are dropped; the rest resolves from the repository root and
is dead when it does not exist. Fenced code blocks are skipped whole: they hold examples.

Guarantees: the same text gives the same references to both tools.
Does not cover: links (`[[Name]]`, Markdown links), paths outside the roots, indented code
blocks.
Why: a page or an entry that names a file which no longer exists is the first thing that lies to
the next agent; one rule, in one place, so that the wiki lint and the backlog agree.
"""

from __future__ import annotations

import os
import re
from collections import namedtuple

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
SPAN_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
LINE_SUFFIX_RE = re.compile(r":(\d+)(?:-(\d+))?$")
IGNORED_CHARS = frozenset("*?<>{}$ ")

Ref = namedtuple("Ref", "lineno raw path last_line")


def outside_fences(text):
    """Yield (lineno, line) for every line outside fenced code blocks (fence lines excluded)."""
    fence = None
    for lineno, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                continue
            yield lineno, line
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
            fence = None


def roots_regex(roots):
    """Compile DEAD_PATH_ROOTS ('src|tests|...') into a prefix regex."""
    return re.compile(r"^(?:" + roots + r")/")


def iter_refs(text, roots):
    """Yield a Ref for each backticked path under one of the roots, outside fenced blocks."""
    if not roots:  # an empty DEAD_PATH_ROOTS checks nothing
        return
    prefix = roots_regex(roots) if isinstance(roots, str) else roots
    for lineno, line in outside_fences(text):
        for m in SPAN_RE.finditer(line):
            raw = m.group(1)
            if not prefix.match(raw):
                continue
            if "..." in raw or any(c in IGNORED_CHARS for c in raw):
                continue
            path, last_line = raw, None
            suffix = LINE_SUFFIX_RE.search(path)
            if suffix:
                last_line = int(suffix.group(2) or suffix.group(1))
                path = path[: suffix.start()]
            path = path.split("#", 1)[0].rstrip("/")
            if path:
                yield Ref(lineno, raw, path, last_line)


def count_lines(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def problems(root, text, roots, check_lines=True):
    """Return (lineno, raw, message) for each dead path, and each line past the end of a file."""
    found = []
    for ref in iter_refs(text, roots):
        full = os.path.join(root, ref.path)
        if not os.path.exists(full):
            found.append((ref.lineno, ref.raw, f"dead path `{ref.raw}`"))
        elif check_lines and ref.last_line and os.path.isfile(full):
            total = count_lines(full)
            if ref.last_line > total:
                found.append(
                    (
                        ref.lineno,
                        ref.raw,
                        f"`{ref.raw}`: line {ref.last_line} is past the end of "
                        f"{ref.path} ({total} lines)",
                    )
                )
    return found


def dead(root, text, roots):
    """The raw references of `text` that do not exist (no line check), in order, deduplicated."""
    seen = []
    for ref in iter_refs(text, roots):
        if not os.path.exists(os.path.join(root, ref.path)) and ref.raw not in seen:
            seen.append(ref.raw)
    return seen
