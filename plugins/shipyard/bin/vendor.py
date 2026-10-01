#!/usr/bin/env python3
"""Copy the plugin's script templates into a project, or check that its copies are current.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" <project-root>            # write the copies
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" <project-root> --check    # write nothing
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/vendor.py" <project-root> --force    # replace local edits

What is copied, byte for byte, from this plugin's templates/:
    templates/scripts/{ci_scope,cleanup_local,pr_size,wiki_lint,wip,lane_paths,owners,
                       precommit}.py                       -> scripts/          (executable)
    templates/scripts/worktree_setup.sh, selftest.sh      -> scripts/          (executable)
    templates/scripts/lib/{conf,dead_paths}.py            -> scripts/lib/
    templates/scripts/selftest/test_*.py                  -> scripts/selftest/
    templates/githooks/pre-commit                         -> .githooks/pre-commit (executable)
and scripts/lib/VENDORED.json records what was written:
    {"shipyard": "<version of .claude-plugin/plugin.json>", "files": {"<path>": "<sha256>"}}

Write mode: a copy whose content differs from its recorded sha256 was edited by hand (a file
present but never recorded, and different from the template, counts as edited too); then nothing
is written, each such file is listed as `modified <path>`, and the exit is 1 — unless --force,
which replaces them. A file recorded by an earlier version but no longer shipped is removed
(same rule if it was edited). Output: `added`, `updated`, `replaced`, `removed <path>` lines,
then `vendored shipyard <version>: …`. Exit 0 done, 1 refused, 2 usage error (or a file that
cannot be read or written).

--check writes nothing and prints, one per line: `outdated <from> -> <to>` (the recorded version
differs from the plugin's, or a template changed, appeared or disappeared since the recorded
copy; `none` when there is no VENDORED.json), `modified <path>` (a copy edited by hand),
`missing <path>` (a copy absent from the project, VENDORED.json included); or `ok` alone.
Exit 0 nothing to do, 1 something to synchronise, 2 usage error.

Guarantees: never touches scripts/lib/tooling.conf, scripts/check.sh, nor any path outside the
list above; each write is atomic (temporary file, then rename); a second run writes nothing.
Does not cover: committing the result, project-specific values (they live in tooling.conf),
deciding when to synchronise (the sync-tooling skill and the SessionStart hook do).
Why: the code the CI and humans run without Claude must live in the repository, since a GitHub
runner has no plugin; generic code is still written and tested once, here, and a fix reaches
every project with the plugin update. A copy edited in place is drift to report, not a silent
customisation: a project-specific value belongs in tooling.conf.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import tempfile

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")
PLUGIN_JSON = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
RECORD = "scripts/lib/VENDORED.json"

SCRIPTS = (
    "ci_scope",
    "cleanup_local",
    "pr_size",
    "wiki_lint",
    "wip",
    "lane_paths",
    "owners",
    "precommit",
)
SHELL_SCRIPTS = ("worktree_setup.sh", "selftest.sh")
LIBS = ("conf", "dead_paths")
NEVER_TOUCHED = frozenset({"scripts/lib/tooling.conf", "scripts/check.sh", RECORD})


class UsageError(Exception):
    """Exit 2: a wrong argument, an unreadable plugin.json or VENDORED.json, a missing template."""


def manifest():
    """[(project path, template path, executable)] in a stable order."""
    entries = []
    for name in SCRIPTS:
        entries.append((f"scripts/{name}.py", os.path.join("scripts", f"{name}.py"), True))
    for name in SHELL_SCRIPTS:
        entries.append((f"scripts/{name}", os.path.join("scripts", name), True))
    for name in LIBS:
        rel = os.path.join("scripts", "lib", f"{name}.py")
        entries.append((f"scripts/lib/{name}.py", rel, False))
    for path in sorted(glob.glob(os.path.join(TEMPLATES, "scripts", "selftest", "test_*.py"))):
        name = os.path.basename(path)
        rel = os.path.join("scripts", "selftest", name)
        entries.append((f"scripts/selftest/{name}", rel, False))
    entries.append((".githooks/pre-commit", os.path.join("githooks", "pre-commit"), True))
    result = []
    for dest, rel, executable in entries:
        if dest in NEVER_TOUCHED:  # a guard against a future template, never expected to fire
            raise UsageError(f"the plugin would overwrite {dest}; refusing")
        src = os.path.join(TEMPLATES, rel)
        if not os.path.isfile(src):
            missing = os.path.relpath(src, PLUGIN_ROOT)
            raise UsageError(f"the plugin is incomplete: missing template {missing}")
        result.append((dest, src, executable))
    return result


def plugin_version():
    try:
        with open(PLUGIN_JSON, encoding="utf-8") as fh:
            version = json.load(fh).get("version")
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read {PLUGIN_JSON}: {exc}") from None
    if not isinstance(version, str) or not version:
        raise UsageError(f"{PLUGIN_JSON} has no version")
    return version


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def project_path(root, rel):
    return os.path.join(root, *rel.split("/"))


def load_record(root):
    """(version, {path: sha256}) from VENDORED.json, or (None, {}) when it does not exist."""
    path = project_path(root, RECORD)
    if not os.path.exists(path):
        return None, {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        version, files = data["shipyard"], data["files"]
        if not isinstance(files, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in files.items()
        ):
            raise ValueError("files is not a {path: sha256} object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UsageError(f"{RECORD} is unreadable ({exc}); fix it or delete it") from None
    return str(version), files


def edited(root, rel, recorded, template_sha):
    """True when the project's copy of `rel` was changed by hand."""
    path = project_path(root, rel)
    if not os.path.isfile(path):
        return False
    current = sha256(path)
    if rel in recorded:
        return current != recorded[rel]
    return template_sha is None or current != template_sha


def check(root):
    version = plugin_version()
    entries = manifest()
    old_version, recorded = load_record(root)
    shipped = {dest for dest, _, _ in entries}
    outdated = old_version != version
    modified, missing = [], []
    for dest, src, _ in entries:
        template_sha = sha256(src)
        if recorded.get(dest) != template_sha:
            outdated = True
        if not os.path.isfile(project_path(root, dest)):
            missing.append(dest)
        elif edited(root, dest, recorded, template_sha):
            modified.append(dest)
    for dest in sorted(set(recorded) - shipped):
        outdated = True
        if edited(root, dest, recorded, None):
            modified.append(dest)
    if old_version is None:
        missing.append(RECORD)
    lines = []
    if outdated:
        lines.append(f"outdated {old_version or 'none'} -> {version}")
    lines += [f"modified {p}" for p in modified]
    lines += [f"missing {p}" for p in missing]
    for line in lines or ["ok"]:
        print(line)
    return 1 if lines else 0


def write_atomic(path, data, mode):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".vendor-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def vendor(root, force):
    version = plugin_version()
    entries = manifest()
    _, recorded = load_record(root)
    shipped = {dest for dest, _, _ in entries}
    obsolete = sorted(set(recorded) - shipped)
    conflicts = [dest for dest, src, _ in entries if edited(root, dest, recorded, sha256(src))]
    conflicts += [dest for dest in obsolete if edited(root, dest, recorded, None)]
    if conflicts and not force:
        for dest in conflicts:
            print(f"modified {dest}")
        print(
            f"vendor.py: refusing to overwrite {len(conflicts)} file(s) edited by hand; a "
            "project-specific value belongs in scripts/lib/tooling.conf. Re-run with --force "
            "to replace them.",
            file=sys.stderr,
        )
        return 1
    files, written, removed = {}, 0, 0
    for dest, src, executable in entries:
        with open(src, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha256(data).hexdigest()
        files[dest] = digest
        path = project_path(root, dest)
        mode = 0o755 if executable else 0o644
        regular = os.path.isfile(path) and not os.path.islink(path)
        if regular and sha256(path) == digest:
            if os.stat(path).st_mode & 0o777 != mode:
                os.chmod(path, mode)
            continue
        verb = "added" if not os.path.lexists(path) else "updated"
        if dest in conflicts:
            verb = "replaced"
        write_atomic(path, data, mode)
        written += 1
        print(f"{verb} {dest}")
    for dest in obsolete:
        path = project_path(root, dest)
        if os.path.lexists(path):
            os.remove(path)
            removed += 1
            print(f"removed {dest}")
    record = json.dumps({"shipyard": version, "files": dict(sorted(files.items()))}, indent=2)
    record = (record + "\n").encode("utf-8")
    record_path = project_path(root, RECORD)
    current = None
    if os.path.isfile(record_path):
        with open(record_path, "rb") as fh:
            current = fh.read()
    if current != record:
        write_atomic(record_path, record, 0o644)
    print(
        f"vendored shipyard {version}: {written} written, {len(entries) - written} unchanged, "
        f"{removed} removed"
    )
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        prog="vendor.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("root", help="the project's root directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="write nothing; report what differs")
    group.add_argument("--force", action="store_true", help="replace copies edited by hand")
    args = parser.parse_args(argv[1:])
    root = os.path.abspath(args.root)
    try:
        if not os.path.isdir(root):
            raise UsageError(f"not a directory: {args.root}")
        real, plugin = os.path.realpath(root), os.path.realpath(PLUGIN_ROOT)
        if real == plugin or real.startswith(plugin + os.sep):
            raise UsageError("the project root is inside the plugin itself")
        return check(root) if args.check else vendor(root, args.force)
    except (UsageError, OSError) as exc:
        print(f"vendor.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
