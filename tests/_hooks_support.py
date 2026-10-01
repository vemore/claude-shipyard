"""Test tooling for tests/test_hooks.py: stubs, a git sandbox, and a hook runner.

Usage: ``from _hooks_support import Sandbox, SandboxCase, run_hook, ...`` (tests/ is on
sys.path under ``python3 -m unittest discover -s tests``).

Guarantees: each Sandbox is a throwaway directory with a bare remote ``remote.git``, a clone
``main/`` on main whose origin reads as GitHub (``url.<bare>.insteadOf``), a worktree ``wt/``
on ``feat/x``, an isolated git configuration, a fake ``gh`` on PATH answering from a JSON
scenario, a stub ``scripts/check.sh`` that records its calls, and a fake plugin root
(``CLAUDE_PLUGIN_ROOT``) whose ``plugin.json`` version and ``bin/vendor.py`` the test picks.
The hooks themselves always run from this repository's ``plugins/shipyard/hooks/``.

Does not cover: the real GitHub API, Claude Code's own hook runner.

Why it exists: test_hooks.py holds the case tables; the plumbing lives here so the tables stay
readable. Private to the hook tests (contract §3: no module shared between lots).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "shipyard"
HOOKS = PLUGIN / "hooks"
HOOKS_JSON = HOOKS / "hooks.json"
PRE_COMMIT = PLUGIN / "templates" / "githooks" / "pre-commit"
PRECOMMIT_PY = PLUGIN / "templates" / "scripts" / "precommit.py"
GITHUB_URL = "https://github.com/acme/demo.git"
NS = "demo"
PLUGIN_VERSION = "1.0.0"
EMPTY_FOLDER_HINT = ("This folder is empty and shipyard is enabled: run /shipyard:bootstrap "
                     "<what you want to build> to start a project with its tooling.")

# Fake secrets are assembled at run time so that the test files themselves never match
# SECRET_CONTENT_RE and need no `secret-scan: fixture` exemption.
PRIVATE_KEY = ("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n"
               "-----END OPENSSH " + "PRIVATE KEY-----\n")
SERVICE_ACCOUNT = '{"type": ' + '"service_account", "project_id": "demo-123"}\n'
CLOUD_KEY = "AKIA" + "QWERTYUIOPASDFGH"
API_KEY = "sk" + "-" + "a1B2c3D4" * 3
# Kebab-case words that contain `sk-` and must never read as a key (annex 04 §5.2).
KEBAB_LOOK_ALIKES = ["risk-assessment-for-payments-module", "task-queue-processing-worker",
                     "[[2026-09-01-desk-booking-calendar-export]]"]

# The SECRET_* values are those of annex 00 §2 (short patterns bounded on the left).
TOOLING_CONF = r"""# test values
PROJECT_SLUG=demo
DEFAULT_BRANCH=main
GIT_CONFIG_NS=demo
WORKTREE_PREFIX=../demo-
SCHEDULED_STAMP=.demo-scheduled-check
TOOLING_LEVEL={level}
TEAM_MODE={team}
COMPONENTS='app'
SECRET_PATH_RE='(^|/)\.env$|(^|/)\.env\.|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|\.keystore$|(^|/)id_(rsa|ed25519|ecdsa)$|(^|/)deploy\.env$'
SECRET_ALLOW_RE='\.example$|\.template$|\.sample$'
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|"type"[ \t]*:[ \t]*"service_account"|AKIA[0-9A-Z]{{16}}|ghp_[A-Za-z0-9]{{36}}|github_pat_[A-Za-z0-9_]{{22,}}|xox[baprs]-[A-Za-z0-9-]{{10,}}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{{20,}}'
"""

CHECK_STUB = r'''#!/usr/bin/env python3
# Stub of scripts/check.sh: records its call, then behaves as CHECK_STUB_* asks.
import json, os, signal, sys, time
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
paths = None
if "--paths-from" in args:
    with open(args[args.index("--paths-from") + 1]) as handle:
        paths = handle.read().splitlines()
log = os.environ.get("CHECK_STUB_LOG")
if log:
    with open(log, "a") as handle:
        handle.write(json.dumps({"root": root, "args": args, "paths": paths}) + "\n")
if os.environ.get("CHECK_STUB_SLEEP"):
    time.sleep(float(os.environ["CHECK_STUB_SLEEP"]))
if os.environ.get("CHECK_STUB_CRASH"):
    os.kill(os.getpid(), signal.SIGSEGV)
code = int(os.environ.get("CHECK_STUB_EXIT", "0"))
if code == 1 and args[:1] == ["edit"]:
    print("stub: src/app.py:1: E999 broken edit")
elif code == 1:
    for i in range(60):
        print("stub gate line %d" % i)
    print("stub: E501 line too long")
    print("Reproduce with: scripts/check.sh fast")
elif code == 3:
    print("stub: ruff not found", file=sys.stderr)
    print("SETUP: stub-install", file=sys.stderr)
sys.exit(code)
'''

SCHEDULED_STUB = r'''#!/usr/bin/env python3
import os, sys
log = os.environ.get("SCHED_STUB_LOG")
if log:
    with open(log, "a") as handle:
        handle.write("run\n")
code = int(os.environ.get("SCHED_STUB_EXIT", "0"))
if code == 1:
    print("nightly.yml is disabled since 2026-01-01")
sys.exit(code)
'''

GH_STUB = r'''#!/usr/bin/env python3
# Fake gh: answers from the JSON scenario in GH_STUB_SCENARIO.
import json, os, sys, time
args = sys.argv[1:]
log = os.environ.get("GH_STUB_LOG")
if log:
    with open(log, "a") as handle:
        handle.write(json.dumps(args) + "\n")
try:
    with open(os.environ["GH_STUB_SCENARIO"]) as handle:
        sc = json.load(handle)
except (KeyError, OSError, ValueError):
    sc = {}
if sc.get("sleep"):
    time.sleep(sc["sleep"])
def out(obj):
    print(obj if isinstance(obj, str) else json.dumps(obj))
if args[:2] == ["auth", "status"]:
    sys.exit(sc.get("auth", 0))
if args[:2] == ["pr", "list"]:
    out(sc.get("pr_list", []) if "--head" in args else sc.get("pr_merged", []))
    sys.exit(0)
if args[:2] == ["pr", "checks"]:
    if "--required" in args and sc.get("required_error"):
        print("no required checks reported on the 'feat/x' branch", file=sys.stderr)
        sys.exit(1)
    if "--json" in args and sc.get("json_unsupported"):
        print("unknown flag: --json", file=sys.stderr)
        sys.exit(1)
    checks = sc.get("checks", [])
    buckets = set(c["bucket"] for c in checks)
    code = 1 if "fail" in buckets else 8 if "pending" in buckets else 0
    if "--json" in args:
        out([{"name": c["name"], "bucket": c["bucket"]} for c in checks])
    else:
        for c in checks:
            print("%s\t%s\t1s\thttps://example.invalid/run" % (c["name"], c["bucket"]))
    sys.exit(code)
if args[:2] == ["api", "user"]:
    login = sc.get("login", "octo")
    if not login:
        print("gh: not logged in", file=sys.stderr)
        sys.exit(1)
    out(login)
    sys.exit(0)
if args[:1] == ["api"]:
    path = [a for a in args[1:] if "/" in a][0]
    for sha, status in sc.get("compare", {}).items():
        if path.endswith(sha):
            out(status)
            sys.exit(0)
    out("identical")
    sys.exit(0)
print("gh stub: unhandled: " + " ".join(args), file=sys.stderr)
sys.exit(4)
'''

VENDOR_STUB = r'''#!/usr/bin/env python3
# Stub of the plugin's bin/vendor.py: records its call, answers VENDOR_STUB_OUT (| = newline).
import json, os, sys
log = os.environ.get("VENDOR_STUB_LOG")
if log:
    with open(log, "a") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")
print(os.environ.get("VENDOR_STUB_OUT", "ok").replace("|", "\n"))
sys.exit(int(os.environ.get("VENDOR_STUB_EXIT", "0")))
'''

OWNERS_STUB = r'''#!/usr/bin/env python3
# Stub of scripts/owners.py --who LOGIN: patterns from OWNERS_STUB_MAP ({"login": [...]}).
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("OWNERS_STUB_LOG")
if log:
    with open(log, "a") as handle:
        handle.write(json.dumps(args) + "\n")
if os.environ.get("OWNERS_STUB_EXIT"):
    sys.exit(int(os.environ["OWNERS_STUB_EXIT"]))
who = args[args.index("--who") + 1] if "--who" in args else None
owned = json.loads(os.environ.get("OWNERS_STUB_MAP", "{}")).get(who, [])
for pattern in owned:
    print(pattern)
sys.exit(0 if owned else 1)
'''

ENV_DROP_PREFIXES = ("GIT_", "CHECK_STUB_", "GH_STUB_", "SCHED_STUB_", "HOOK_", "VENDOR_STUB_",
                     "OWNERS_STUB_")
ENV_DROP = {"CLAUDECODE", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "GH_TOKEN",
            "GITHUB_TOKEN"}


def run_hook(name, payload=None, env=None, raw=None, timeout=60, cwd=None):
    """Run plugins/shipyard/hooks/<name> of this repository; (code, stdout, stderr)."""
    path = HOOKS / name
    cmd = ["/bin/sh", str(path)] if name.endswith(".sh") else [sys.executable, str(path)]
    data = raw if raw is not None else json.dumps(payload or {})
    proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, env=env, cwd=str(cwd or REPO),
                          timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def bash_payload(command, cwd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(cwd),
            "tool_input": {"command": command}}


class Sandbox:
    """A bare remote, a clone ``main/`` on main, a worktree ``wt/`` on ``feat/x``."""

    def __init__(self, level="essentiel", wip=True, team="solo"):
        self.tmp = Path(tempfile.mkdtemp(prefix="hooks-selftest-")).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("[user]\n\tname = Selftest\n\temail = selftest@example.invalid\n"
                                  "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
                                  "[advice]\n\tdetachedHead = false\n")
        self.bin = self.tmp / "bin"
        self.bin_nogh = self.tmp / "bin-nogh"
        for directory in (self.bin, self.bin_nogh):
            directory.mkdir()
            for tool in ("git", "sh", "bash", "env", "dirname", "cat"):
                found = shutil.which(tool)
                if found:
                    os.symlink(found, str(directory / tool))
            os.symlink(sys.executable, str(directory / "python3"))
        self.write_exec(self.bin / "gh", GH_STUB)
        self.scenario = self.tmp / "gh.json"
        self.set_scenario({})
        self.check_log = self.tmp / "check.log"
        self.gh_log = self.tmp / "gh.log"
        self.sched_log = self.tmp / "sched.log"
        self.vendor_log = self.tmp / "vendor.log"
        self.owners_log = self.tmp / "owners.log"
        self.plugin = self.tmp / "plugin"
        self.set_plugin_version(PLUGIN_VERSION)
        self.remote = self.tmp / "remote.git"
        self.main = self.tmp / "main"
        self.wt = self.tmp / "wt"
        self.git("init", "-q", "--bare", str(self.remote), cwd=self.tmp)
        self.git("init", "-q", str(self.main), cwd=self.tmp)
        self.git("remote", "add", "origin", GITHUB_URL)
        self.git("config", "url.{}.insteadOf".format(self.remote), GITHUB_URL)
        self.populate(self.main, level, wip, team)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.git("push", "-q", "-u", "origin", "main")
        self.git("worktree", "add", "-q", str(self.wt), "-b", "feat/x", "origin/main")

    # -- helpers ----------------------------------------------------------------------------
    @staticmethod
    def write_exec(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)

    def populate(self, root, level="essentiel", wip=True, team="solo"):
        """What bootstrap and bin/vendor.py leave in a project (stubs for the stack parts)."""
        (root / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "lib" / "tooling.conf").write_text(
            TOOLING_CONF.format(level=level, team=team))
        self.write_vendored(PLUGIN_VERSION, root)
        self.write_exec(root / "scripts" / "check.sh", CHECK_STUB)
        self.write_exec(root / "scripts" / "check_scheduled_runs.py", SCHEDULED_STUB)
        self.write_exec(root / "scripts" / "precommit.py", PRECOMMIT_PY.read_text())
        self.write_exec(root / ".githooks" / "pre-commit", PRE_COMMIT.read_text())
        (root / "src").mkdir(exist_ok=True)
        (root / "src" / "app.py").write_text("print('hello')\n")
        (root / "README.md").write_text("# demo\n")
        (root / ".gitignore").write_text(".env\n")
        if wip:
            for sub in ("todo", "todo_nr"):
                (root / "wip" / sub).mkdir(parents=True, exist_ok=True)
                (root / "wip" / sub / "x.md").write_text("# entry\n")
            (root / "wip" / "done").mkdir(parents=True, exist_ok=True)
            (root / "wip" / "done" / ".gitkeep").write_text("")

    def set_plugin_version(self, version):
        manifest = self.plugin / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"name": "shipyard", "version": version}))

    def add_vendor_stub(self):
        self.write_exec(self.plugin / "bin" / "vendor.py", VENDOR_STUB)

    def write_vendored(self, version, root=None):
        path = (root or self.main) / "scripts" / "lib" / "VENDORED.json"
        path.write_text(json.dumps({"shipyard": version, "files": {}}))

    def enable_team(self, root=None):
        """TEAM_MODE=team and a stub scripts/owners.py in ``root`` (default: both trees)."""
        for tree in [root] if root else [self.main, self.wt]:
            conf = tree / "scripts" / "lib" / "tooling.conf"
            conf.write_text(conf.read_text().replace("TEAM_MODE=solo", "TEAM_MODE=team"))
            self.write_exec(tree / "scripts" / "owners.py", OWNERS_STUB)

    def env(self, gh=True, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(ENV_DROP_PREFIXES) and k not in ENV_DROP}
        env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=str(self.gitconfig),
                   PATH=str(self.bin if gh else self.bin_nogh),
                   CLAUDE_PLUGIN_ROOT=str(self.plugin),
                   GH_STUB_SCENARIO=str(self.scenario), GH_STUB_LOG=str(self.gh_log),
                   CHECK_STUB_LOG=str(self.check_log), SCHED_STUB_LOG=str(self.sched_log),
                   VENDOR_STUB_LOG=str(self.vendor_log), OWNERS_STUB_LOG=str(self.owners_log),
                   HOOK_GH_TIMEOUT="1", HOOK_GATE_TIMEOUT="2", PYTHONDONTWRITEBYTECODE="1",
                   LC_ALL="C")
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def git(self, *args, cwd=None, check=True, **env):
        proc = subprocess.run(["git"] + list(args), cwd=str(cwd or self.main),
                              env=self.env(**env), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        if check and proc.returncode != 0:
            raise AssertionError("git {} failed: {}".format(" ".join(args), proc.stderr))
        return proc.stdout.strip()

    def set_scenario(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def write(self, rel, text, root=None):
        path = (root or self.wt) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text)
        return path

    def stage(self, rel, text, root=None, force=False):
        self.write(rel, text, root)
        self.git("add", *(["-f"] if force else []), "--", rel, cwd=root or self.wt)

    def commit_direct(self, rel="a.txt", text="a\n", root=None, message="change"):
        """A commit made without any hook (setup only)."""
        self.stage(rel, text, root)
        self.git("commit", "-q", "-m", message, cwd=root or self.wt)
        return self.git("rev-parse", "HEAD", cwd=root or self.wt)

    def unbootstrap(self, root=None):
        """Remove scripts/lib/tooling.conf from a tree: shipyard must go inert there."""
        (root or self.wt).joinpath("scripts", "lib", "tooling.conf").unlink()

    @staticmethod
    def json_lines(path):
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def gate_calls(self):
        return self.json_lines(self.check_log)

    def gh_calls(self):
        return self.json_lines(self.gh_log)

    def guard(self, command, cwd=None, **env):
        return run_hook("guard_bash.py", bash_payload(command, cwd or self.wt), self.env(**env))

    def stop(self, cwd=None, event="Stop", active=False, **env):
        payload = {"hook_event_name": event, "cwd": str(cwd or self.wt),
                   "stop_hook_active": active}
        return run_hook("require_pull_request.py", payload, self.env(**env))

    def session(self, cwd=None, **env):
        payload = {"hook_event_name": "SessionStart", "source": "startup",
                   "cwd": str(cwd or self.main)}
        return run_hook("session_start.py", payload, self.env(**env))

    def edit(self, path, **env):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                   "cwd": str(self.main), "tool_input": {"file_path": str(path)}}
        return run_hook("post_edit.py", payload, self.env(**env))

    def make_stale(self, branch="feat/x", root=None):
        """Push ``branch``, delete it on the remote, prune: its upstream is [gone]."""
        root = root or self.wt
        self.git("push", "-q", "-u", "origin", branch, cwd=root)
        self.git("push", "-q", "origin", "--delete", branch, cwd=self.main)
        self.git("fetch", "-q", "--prune", "origin", cwd=root)

    def cleanup(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)


class SandboxCase(unittest.TestCase):
    """A fresh sandbox per test."""

    level = "essentiel"

    def setUp(self):
        self.sb = Sandbox(level=self.level)
        self.addCleanup(self.sb.cleanup)
