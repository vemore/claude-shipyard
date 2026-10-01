#!/usr/bin/env python3
"""The wip/ backlog tool: list, theme counts, format check and refinement signals.

Usage:
    scripts/wip.py list   [todo|todo_nr|done|all]   # default todo: by folder, then theme;
                                                    # `!` marks a release blocker
    scripts/wip.py themes [todo|todo_nr|done|all]   # default all: entries per theme and folder
    scripts/wip.py check  [todo|todo_nr|done|all]   # default all: format check, run in CI
    scripts/wip.py refine [todo|todo_nr|done|all]   # default all = todo + todo_nr: signals for a
                                                    # refinement pass

Exit: `check` 0 clean / 1 at least one error (listed on stdout); the other commands 0; every
command 2 on a usage error or an unreadable scripts/lib/tooling.conf.

An entry is wip/<todo|todo_nr|done>/YYYY-MM-DD-<slug>.md; README.md, .gitkeep, ARCHIVE-*.md and
wip/assets/ are ignored. Parsed: the title (first `# ` line); the metadata lines `- **Noted:**`,
`- **Theme:**`, `- **Area:**`, `- **Blocks release:**` (value starting with yes or no); the
status `**Status:** done|dropped` (optionally as a `- ` bullet) within the first six non-empty
lines; and the sections, written `**Label:**` or `## Label` (`#` to `####`, colon optional,
case-insensitive), with synonyms:
    Fix: fix, proposed fix, fix proposé, correctif, correctif proposé
    Acceptance: acceptance, acceptance criteria, acceptation, critères d'acceptation
    Open question: open question(s), question(s) ouverte(s)
    State of the art: state of the art, état de l'art

check — errors: a file name outside YYYY-MM-DD-<slug>.md or with an invalid date; a missing
title, Theme or Area; an Area outside COMPONENTS + {tooling, docs, ci, infra}; Blocks release
missing outside done/; a done/ entry without a done/dropped status, or an open entry with one;
the same file name in two folders (an entry copied instead of moved). Warning only: wip/todo/
over WIP_LIMIT (a blocking entry must be able to get in; the refinement pass enforces the limit).

refine — one line per entry, `<folder>/<name>  age <N>d  idle <M>d  [flags]`: age from Noted
(else the file-name date), idle from the last commit touching the file (else its mtime). Flags:
no-fix, no-acceptance, open-question (a non-empty section), stale (idle over STALE_DAYS),
dead-path:[...] (scripts/lib/dead_paths.py), links-closed:[...] (names an entry now in done/),
BLOCKS-RELEASE. Then each theme with more than CROWDED_THEME open entries, the open total, the
todo/ count against WIP_LIMIT, and the todo_nr/ count with a refinement suggestion past
REFINE_THRESHOLD.

Does not cover: whether an entry is still true, ready or well scoped (that is the judgement of
the wip-refine skill); the order of the entries.
Why: one file per entry and no index file means two pull requests never collide in wip/; this
script is the index instead, and the check keeps the format the tools rely on.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import conf
import dead_paths

FOLDERS = ("todo", "todo_nr", "done")
OPEN_FOLDERS = ("todo", "todo_nr")
EXTRA_AREAS = ("tooling", "docs", "ci", "infra")
NAME_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})-[a-z0-9-]+\.md$")
META_RE = re.compile(r"^- \*\*(Noted|Theme|Area|Blocks release):\*\*\s*(.*)$", re.IGNORECASE)
STATUS_RE = re.compile(r"^(- )?\*\*Status:\*\* (done|dropped)\b")
BOLD_LABEL_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*:?\s*(.*)$")
HEADING_LABEL_RE = re.compile(r"^#{2,4}\s+(.+?)\s*:?\s*$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
ENTRY_REF_RE = re.compile(r"(?<![0-9A-Za-z])([0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*)")
EMPTY_VALUES = ("", "none", "n/a", "-", "—", "no")

SYNONYMS = {
    "fix": ("fix", "proposed fix", "fix proposé", "correctif", "correctif proposé"),
    "acceptance": ("acceptance", "acceptance criteria", "acceptation", "critères d'acceptation"),
    "open question": ("open question", "open questions", "question ouverte", "questions ouvertes"),
    "state of the art": ("state of the art", "état de l'art"),
}


def norm(label):
    label = unicodedata.normalize("NFC", label).replace("\u2019", "'")
    return " ".join(label.strip().rstrip(":").strip().casefold().split())


CANONICAL = {norm(s): key for key, values in SYNONYMS.items() for s in values}


def parse_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(0))
    except ValueError:
        return None


def section_label(line):
    """The normalized label if `line` opens a section (`**Label:**` or `## Label`), else None."""
    body = line[2:] if line.startswith("- ") else line
    m = BOLD_LABEL_RE.match(body)
    if m:
        return norm(m.group(1)), m.group(2)
    m = HEADING_LABEL_RE.match(body)
    if m:
        return norm(m.group(1)), ""
    return None


class Entry:
    def __init__(self, folder, name, path):
        self.folder, self.name, self.path = folder, name, path
        with open(path, encoding="utf-8", errors="replace") as fh:
            self.text = fh.read()
        self.title = None
        self.meta = {}
        self.status = None
        self.sections = {}  # canonical label -> content
        self.parse()

    @property
    def stem(self):
        return self.name[:-3]

    def parse(self):
        lines = self.text.splitlines()
        non_empty = [line for line in lines if line.strip()]
        for line in non_empty[:6]:
            m = STATUS_RE.match(line.strip())
            if m:
                self.status = m.group(2)
                break
        current = None
        for line in lines:
            stripped = line.strip()
            if self.title is None and stripped.startswith("# "):
                self.title = stripped[2:].strip()
                continue
            m = META_RE.match(stripped)
            if m:
                self.meta.setdefault(m.group(1).lower(), m.group(2).strip())
                current = None
                continue
            label = section_label(stripped)
            if label is not None:
                key = CANONICAL.get(label[0])
                current = key
                if key is not None:
                    self.sections.setdefault(key, [])
                    if label[1]:
                        self.sections[key].append(label[1])
                continue
            if ANY_HEADING_RE.match(stripped):
                current = None
                continue
            if current is not None:
                self.sections[current].append(line)

    def section(self, key):
        """None when absent, else its text stripped (may be empty)."""
        if key not in self.sections:
            return None
        return "\n".join(self.sections[key]).strip()

    def has_content(self, key):
        content = self.section(key)
        return content is not None and content.strip().casefold() not in EMPTY_VALUES

    @property
    def blocks_release(self):
        return self.meta.get("blocks release", "").lower().startswith("yes")

    @property
    def theme(self):
        return self.meta.get("theme", "").strip("` ") or "(no theme)"


class Backlog:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.wip = os.path.join(root, "wip")
        self.entries = {folder: self.load(folder) for folder in FOLDERS}

    def load(self, folder):
        base = os.path.join(self.wip, folder)
        if not os.path.isdir(base):
            return []
        entries = []
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if not os.path.isfile(path) or not name.endswith(".md"):
                continue
            if name == "README.md" or name.startswith("ARCHIVE-"):
                continue
            entries.append(Entry(folder, name, path))
        return entries

    def select(self, which):
        folders = FOLDERS if which == "all" else (which,)
        return [e for folder in folders for e in self.entries[folder]]

    # --- list / themes ---

    def cmd_list(self, which):
        folders = FOLDERS if which == "all" else (which,)
        for folder in folders:
            entries = self.entries[folder]
            print(f"wip/{folder}/ ({len(entries)})")
            themes = {}
            for e in entries:
                themes.setdefault(e.theme, []).append(e)
            for theme in sorted(themes):
                print(f"  {theme} ({len(themes[theme])})")
                for e in themes[theme]:
                    mark = "!" if e.blocks_release else " "
                    print(f"    {mark} {e.stem} — {e.title or '(no title)'}")
        return 0

    def cmd_themes(self, which):
        folders = FOLDERS if which == "all" else (which,)
        counts = {}
        for folder in folders:
            for e in self.entries[folder]:
                counts.setdefault(e.theme, dict.fromkeys(folders, 0))[folder] += 1
        width = max([len("theme")] + [len(t) for t in counts])
        print("theme".ljust(width) + "".join(f"  {f:>7}" for f in folders) + "    total")
        for theme in sorted(counts, key=lambda t: (-sum(counts[t].values()), t)):
            row = counts[theme]
            cells = "".join(f"  {row[f]:>7}" for f in folders)
            print(f"{theme.ljust(width)}{cells}  {sum(row.values()):>7}")
        return 0

    # --- check ---

    def cmd_check(self, which):
        areas = set(self.cfg["COMPONENTS"].split()) | set(EXTRA_AREAS)
        limit = self.cfg.get_int("WIP_LIMIT")
        seen = {}
        for folder in FOLDERS:
            for e in self.entries[folder]:
                seen.setdefault(e.name, []).append(folder)
        errors = []
        for e in self.select(which):
            where = f"wip/{e.folder}/{e.name}"
            m = NAME_RE.match(e.name)
            if not m:
                errors.append(f"{where}: file name is not YYYY-MM-DD-<slug>.md (slug: [a-z0-9-])")
            elif parse_date(m.group(1)) is None:
                errors.append(f"{where}: invalid date in the file name")
            if not e.title:
                errors.append(f"{where}: no title (a first `# ` line)")
            if not e.meta.get("theme", "").strip("` "):
                errors.append(f"{where}: no `- **Theme:**` line")
            area = e.meta.get("area", "").strip("` ").lower()
            if not area:
                errors.append(f"{where}: no `- **Area:**` line")
            elif area not in areas:
                errors.append(f"{where}: Area `{area}` is not one of {', '.join(sorted(areas))}")
            blocks = e.meta.get("blocks release")
            if e.folder != "done":
                if blocks is None:
                    errors.append(f"{where}: no `- **Blocks release:**` line")
                elif not re.match(r"(yes|no)\b", blocks, re.IGNORECASE):
                    errors.append(f"{where}: Blocks release must start with yes or no")
                if e.status:
                    errors.append(
                        f"{where}: has a `**Status:** {e.status}` line but is not in wip/done/"
                    )
            elif not e.status:
                errors.append(
                    f"{where}: in wip/done/ without a `**Status:** done|dropped` line "
                    "in its first six non-empty lines"
                )
            if len(seen.get(e.name, [])) > 1:
                errors.append(
                    f"{where}: the same file name is in {' and '.join(seen[e.name])} "
                    "(an entry is moved with git mv, never copied)"
                )
        for line in errors:
            print(line)
        todo = len(self.entries["todo"])
        if todo > limit:
            print(
                f"warning: wip/todo/ holds {todo} entries, over the WIP limit of {limit} "
                "(not blocking; a refinement pass brings it back)"
            )
        print(f"wip check: {len(errors)} error(s) in {len(self.select(which))} entries")
        return 1 if errors else 0

    # --- refine ---

    def idle_days(self, e, today_ts):
        rc, out = 1, ""
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", e.path],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            rc, out = proc.returncode, proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        stamp = int(out) if rc == 0 and out.isdigit() else os.path.getmtime(e.path)
        return max(0, int((today_ts - stamp) // 86400))

    def cmd_refine(self, which):
        folders = OPEN_FOLDERS if which == "all" else (which,)
        stale_days = self.cfg.get_int("STALE_DAYS")
        crowded = self.cfg.get_int("CROWDED_THEME")
        limit = self.cfg.get_int("WIP_LIMIT")
        threshold = self.cfg.get_int("REFINE_THRESHOLD")
        roots = self.cfg["DEAD_PATH_ROOTS"]
        done_stems = {e.stem for e in self.entries["done"]}
        today = datetime.date.today()
        now = time.time()
        for folder in folders:
            for e in self.entries[folder]:
                noted = parse_date(e.meta.get("noted", "")) or parse_date(e.name)
                age = (today - noted).days if noted else 0
                idle = self.idle_days(e, now)
                flags = []
                if not e.has_content("fix"):
                    flags.append("no-fix")
                if not e.has_content("acceptance"):
                    flags.append("no-acceptance")
                if e.has_content("open question"):
                    flags.append("open-question")
                if idle > stale_days:
                    flags.append("stale")
                dead = dead_paths.dead(self.root, e.text, roots)
                if dead:
                    flags.append(f"dead-path:[{','.join(dead)}]")
                linked = []
                for ref in ENTRY_REF_RE.findall(e.text):
                    if ref in done_stems and ref != e.stem and ref not in linked:
                        linked.append(ref)
                if linked:
                    flags.append(f"links-closed:[{','.join(linked)}]")
                if e.blocks_release:
                    flags.append("BLOCKS-RELEASE")
                print(f"{folder}/{e.stem}  age {age}d  idle {idle}d  {' '.join(flags)}".rstrip())
        open_entries = [e for f in OPEN_FOLDERS for e in self.entries[f]]
        themes = {}
        for e in open_entries:
            themes[e.theme] = themes.get(e.theme, 0) + 1
        for theme in sorted(themes):
            if themes[theme] > crowded:
                print(f"crowded theme: {theme} ({themes[theme]})")
        print(f"open: {len(open_entries)}")
        print(f"wip/todo/: {len(self.entries['todo'])} of a WIP limit of {limit}")
        todo_nr = len(self.entries["todo_nr"])
        suffix = " — refinement suggested" if todo_nr > threshold else ""
        print(f"wip/todo_nr/: {todo_nr}{suffix}")
        return 0


DEFAULTS = {"list": "todo", "themes": "all", "check": "all", "refine": "all"}


def main(argv):
    parser = argparse.ArgumentParser(
        prog="wip.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=sorted(DEFAULTS))
    parser.add_argument("folder", nargs="?", choices=(*FOLDERS, "all"))
    args = parser.parse_args(argv[1:])
    which = args.folder or DEFAULTS[args.command]
    try:
        root = conf.repo_root()
        backlog = Backlog(root, conf.load_conf(root))
        return getattr(backlog, f"cmd_{args.command}")(which)
    except conf.ConfError as exc:
        print(f"wip.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
