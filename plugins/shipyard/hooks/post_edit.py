#!/usr/bin/env python3
"""PostToolUse (Edit|Write|MultiEdit): report a quick check of the edited file, never block.

Usage: Claude Code hook of the shipyard plugin; JSON payload on stdin
(``tool_input.file_path``).

Guarantees: runs ``scripts/check.sh edit <path>`` of the repository that contains the edited
file (not of the launch checkout) and, when it exits 1 with a report, hands that report to the
model as ``additionalContext``. Always exits 0; silent in a repository without
``scripts/lib/tooling.conf``.

Does not cover: files written by a Bash command (PostToolUse does not fire for them). This
hook is a comfort; the guarantee is the commit gate in guard_bash.py.

Why it exists: an early hint saves a red commit later, but a multi-file change is legitimately
inconsistent midway, so a refusal here would invite the model to undo good work.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as common  # noqa: E402

EDIT_TIMEOUT = 50
MAX_REPORT_CHARS = 8000


def main() -> int:
    payload = common.read_payload()
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(file_path, str) or not file_path:
        return 0
    if not os.path.isabs(file_path):
        file_path = os.path.join(payload.get("cwd") or os.getcwd(), file_path)
    # Resolve the directory, not the file: a symlinked file still belongs to this repository.
    file_path = os.path.join(os.path.realpath(os.path.dirname(file_path)),
                             os.path.basename(file_path))
    root = common.repo_root(file_path)
    if root is None:
        return 0
    rel = os.path.relpath(file_path, root)
    if rel.startswith("..") or ".git" in rel.split(os.sep):
        return 0
    if not common.is_bootstrapped(root):
        return 0   # shipyard has not bootstrapped this repository: inert
    script = os.path.join(root, "scripts", "check.sh")
    if not (os.path.isfile(script) and os.access(script, os.X_OK)):
        return 0
    rc, out = common.run_capped([script, "edit", rel], root, EDIT_TIMEOUT, merge_stderr=False)
    report = out.strip()
    if rc != 1 or not report:
        return 0
    if len(report) > MAX_REPORT_CHARS:
        report = "[... truncated ...]\n" + report[-MAX_REPORT_CHARS:]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "Post-edit check on {}:\n{}".format(rel, report)}}))
    return 0


if __name__ == "__main__":
    common.run_main(main)
