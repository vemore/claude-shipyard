#!/usr/bin/env python3
"""Lint the project wiki (.llmwiki/): the checks a script can make, blocking in CI.

Usage:
    scripts/wiki_lint.py [WIKI_DIR]     # default: .llmwiki at the repository root

Output: one line per finding, `<page>[:<line>]: <message>`; notes prefixed `note: `; then a total
`<N> finding(s), <M> note(s)`. Exit 0 no finding (notes may exist), 1 at least one finding,
2 no INDEX.md (or an unreadable scripts/lib/tooling.conf). Notes never change the exit code.

Findings (blocking):
  1. a page other than INDEX.md longer than WIKI_PAGE_BUDGET lines (scripts/lib/tooling.conf);
  2. a dead path: a backticked path under DEAD_PATH_ROOTS that does not exist, or a `path:<line>`
     past the end of the file (scripts/lib/dead_paths.py; fenced code blocks are skipped);
  3. a page without a `> Updated: YYYY-MM-DD` line holding a valid date, or without a
     `## Decisions & History` heading;
  4. an INDEX row `| [[X]] | <summary> | <date> |` whose date differs from X.md's `> Updated:`,
     that links a page which does not exist, or whose summary is over 25 words;
  5. a page of the folder missing from the INDEX.
Notes (not blocking): a `> **Status: Outdated** (date)` or `> **Status: Contradicted** (date)`
block, which the pruning pass folds; a dangling link `[[Name]]` (a page worth writing, not an
error; a link touching a backtick is a convention example and is ignored).

Not checked: contradictions between pages, an `Updated:` older than the sources a page cites,
answers rebuilt from a pull request instead of captured in the wiki (all three need judgement),
and external links (a link checker run on every pull request is an outbound-request primitive
driven by repository content).
Why: an agent copies what it reads, so a wiki that silently goes stale misleads every later
task. Existing Markdown linters know nothing of `[[links]]`, backticked paths or `Updated:` dates.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf
import dead_paths

UPDATED_RE = re.compile(r"^> Updated:\s*(\S+)")
STATUS_RE = re.compile(
    r"^\s*> \*\*Status: (Outdated|Contradicted)\*\* \([0-9]{4}-[0-9]{2}-[0-9]{2}\)"
)
LINK_RE = re.compile(r"(?<!`)\[\[([A-Za-z0-9_-]+)\]\](?!`)")
INDEX_LINK_RE = re.compile(r"^\[\[([A-Za-z0-9_-]+)\]\]$")
DECISIONS_RE = re.compile(r"^## Decisions & History\s*$")
SUMMARY_MAX_WORDS = 25


def valid_date(text):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text or ""):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def updated_of(text):
    """(lineno, value) of the first line starting with `> Updated:`, or (None, None)."""
    for lineno, line in enumerate(text.splitlines(), 1):
        m = UPDATED_RE.match(line)
        if m:
            return lineno, m.group(1)
    return None, None


def index_rows(text):
    """Yield (lineno, name, summary, date) for each `| [[X]] | summary | date |` row."""
    for lineno, line in dead_paths.outside_fences(text):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = INDEX_LINK_RE.match(cells[0])
        if m:
            yield lineno, m.group(1), cells[1], cells[-1]


class Linter:
    def __init__(self, root, wiki, cfg):
        self.root = root
        self.wiki = wiki
        self.budget = cfg.get_int("WIKI_PAGE_BUDGET")
        self.roots = cfg["DEAD_PATH_ROOTS"]
        self.findings = []
        self.notes = []

    def label(self, name):
        path = os.path.join(self.wiki, name)
        rel = os.path.relpath(path, self.root)
        return path if rel.startswith("..") else rel

    def finding(self, page, lineno, message):
        where = self.label(page) + (f":{lineno}" if lineno else "")
        self.findings.append(f"{where}: {message}")

    def note(self, page, lineno, message):
        where = self.label(page) + (f":{lineno}" if lineno else "")
        self.notes.append(f"note: {where}: {message}")

    def run(self, pages):
        texts = {}
        for name in pages:
            with open(os.path.join(self.wiki, name), encoding="utf-8", errors="replace") as fh:
                texts[name] = fh.read()
        for name in pages:
            self.page(name, texts[name], name == "INDEX.md")
        self.index(texts["INDEX.md"], texts)

    def page(self, name, text, is_index):
        lines = text.splitlines()
        if not is_index:
            if len(lines) > self.budget:
                self.finding(name, None, f"{len(lines)} lines, over the budget of {self.budget}")
            lineno, value = updated_of(text)
            if lineno is None:
                self.finding(name, None, "no `> Updated: YYYY-MM-DD` line")
            elif not valid_date(value):
                self.finding(name, lineno, f"`> Updated:` holds an invalid date: {value}")
            if not any(DECISIONS_RE.match(line) for line in lines):
                self.finding(name, None, "no `## Decisions & History` section")
        for lineno, _raw, message in dead_paths.problems(self.root, text, self.roots):
            self.finding(name, lineno, message)
        for lineno, line in dead_paths.outside_fences(text):
            m = STATUS_RE.match(line)
            if m:
                self.note(name, lineno, f"Status: {m.group(1)} block, to fold at the pruning pass")
            for link in LINK_RE.findall(line):
                if not os.path.isfile(os.path.join(self.wiki, link + ".md")):
                    self.note(name, lineno, f"dangling link [[{link}]]")

    def index(self, index_text, texts):
        listed = set()
        for lineno, name, summary, date in index_rows(index_text):
            listed.add(name)
            page = name + ".md"
            words = len(summary.split())
            if words > SUMMARY_MAX_WORDS:
                self.finding(
                    "INDEX.md",
                    lineno,
                    f"summary of [[{name}]] is {words} words, over {SUMMARY_MAX_WORDS}",
                )
            if page not in texts:
                self.finding("INDEX.md", lineno, f"[[{name}]] links a page that does not exist")
                continue
            _, updated = updated_of(texts[page])
            if updated is not None and date != updated:
                self.finding(
                    "INDEX.md",
                    lineno,
                    f"date {date} of [[{name}]] differs from its `> Updated: {updated}`",
                )
        for page in sorted(texts):
            if page != "INDEX.md" and page[:-3] not in listed:
                self.finding(page, None, "missing from INDEX.md")


def main(argv):
    parser = argparse.ArgumentParser(
        prog="wiki_lint.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("wiki_dir", nargs="?", help="wiki folder (default: <root>/.llmwiki)")
    args = parser.parse_args(argv[1:])
    try:
        root = conf.repo_root()
        cfg = conf.load_conf(root)
        linter = Linter(root, os.path.abspath(args.wiki_dir or os.path.join(root, ".llmwiki")), cfg)
    except conf.ConfError as exc:
        print(f"wiki_lint.py: {exc}", file=sys.stderr)
        return 2
    index = os.path.join(linter.wiki, "INDEX.md")
    if not os.path.isfile(index):
        print(f"{linter.label('INDEX.md')}: missing; nothing to lint")
        return 2
    pages = sorted(n for n in os.listdir(linter.wiki) if n.endswith(".md"))
    linter.run(pages)
    for line in linter.findings + linter.notes:
        print(line)
    print(f"{len(linter.findings)} finding(s), {len(linter.notes)} note(s)")
    return 1 if linter.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
