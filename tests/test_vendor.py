"""Tests of plugins/shipyard/bin/vendor.py: copies, VENDORED.json, refusals, --check states.

Run: python3 -m unittest discover -s tests -p 'test_vendor.py'

Most cases build a small synthetic plugin (tempfile.mkdtemp): a copy of the real vendor.py, a
plugin.json whose version the case chooses, and one tiny template per file of the manifest, so
that a version bump, a changed template or a dropped one is a one-line change. `EndToEnd` uses
the real plugin (its plugin.json, or a temporary tree with one when the file does not exist):
it vendors into a fresh project with a complete tooling.conf and ci.yml, then runs that
project's scripts/selftest.sh, the command its CI runs. No network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "plugins", "shipyard")
VENDOR = os.path.join(PLUGIN, "bin", "vendor.py")
PLUGIN_JSON = os.path.join(PLUGIN, ".claude-plugin", "plugin.json")


def load_vendor():
    spec = importlib.util.spec_from_file_location("vendor_under_test", VENDOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = load_vendor()
SELFTESTS = ("test_alpha.py", "test_beta.py")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    if mode is not None:
        os.chmod(path, mode)


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def default_templates():
    """{template path under templates/: content} covering the whole manifest."""
    files = {}
    for name in V.SCRIPTS:
        files[f"scripts/{name}.py"] = f"#!/usr/bin/env python3\n# {name}\n"
    for name in V.SHELL_SCRIPTS:
        files[f"scripts/{name}"] = f"#!/usr/bin/env bash\n# {name}\n"
    for name in V.LIBS:
        files[f"scripts/lib/{name}.py"] = f"# lib {name}\n"
    for name in SELFTESTS:
        files[f"scripts/selftest/{name}"] = f"# {name}\n"
    files["githooks/pre-commit"] = "#!/usr/bin/env bash\nexit 0\n"
    return files


EXPECTED = {
    **{f"scripts/{n}.py": True for n in V.SCRIPTS},
    **{f"scripts/{n}": True for n in V.SHELL_SCRIPTS},
    **{f"scripts/lib/{n}.py": False for n in V.LIBS},
    **{f"scripts/selftest/{n}": False for n in SELFTESTS},
    ".githooks/pre-commit": True,
}


def template_for(dest):
    return "githooks/pre-commit" if dest == ".githooks/pre-commit" else dest


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="vendor-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.plugin = os.path.join(self.tmp, "plugin")
        self.project = os.path.join(self.tmp, "project")
        os.makedirs(self.project)
        write(os.path.join(self.plugin, "bin", "vendor.py"), read(VENDOR), 0o755)
        self.templates = default_templates()
        self.publish("1.0.0")

    def publish(self, version, **changes):
        """(Re)write the synthetic plugin: plugin.json at `version`, templates with `changes`
        (a value of None drops that template)."""
        write(
            os.path.join(self.plugin, ".claude-plugin", "plugin.json"),
            json.dumps({"name": "shipyard", "version": version}),
        )
        for rel, text in changes.items():
            rel = rel.replace("__", "/")
            if text is None:
                self.templates.pop(rel, None)
                path = os.path.join(self.plugin, "templates", rel)
                if os.path.exists(path):
                    os.remove(path)
            else:
                self.templates[rel] = text
        for rel, text in self.templates.items():
            write(os.path.join(self.plugin, "templates", rel), text)

    def vendor(self, *args, root=None):
        return subprocess.run(
            [sys.executable, self.vendor_py(), root or self.project, *args],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def vendor_py(self):
        return os.path.join(self.plugin, "bin", "vendor.py")

    def ppath(self, rel):
        return os.path.join(self.project, rel)

    def snapshot(self):
        state = {}
        for dirpath, _dirs, files in os.walk(self.project):
            for name in files:
                path = os.path.join(dirpath, name)
                st = os.lstat(path)
                state[os.path.relpath(path, self.project)] = (read(path), st.st_mode, st.st_mtime_ns)
        return state

    def record(self):
        with open(self.ppath("scripts/lib/VENDORED.json"), encoding="utf-8") as fh:
            return json.load(fh)

    # --- write mode ---

    def test_fresh_project(self):
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines()[-1],
            f"vendored shipyard 1.0.0: {len(EXPECTED)} written, 0 unchanged, 0 removed",
        )
        for dest, executable in EXPECTED.items():
            with self.subTest(dest):
                self.assertEqual(read(self.ppath(dest)), self.templates[template_for(dest)].encode())
                mode = stat.S_IMODE(os.stat(self.ppath(dest)).st_mode)
                self.assertEqual(mode, 0o755 if executable else 0o644)
                self.assertIn(f"added {dest}", proc.stdout.splitlines())
        record = self.record()
        self.assertEqual(list(record), ["shipyard", "files"])
        self.assertEqual(record["shipyard"], "1.0.0")
        self.assertEqual(
            record["files"],
            {d: sha(self.templates[template_for(d)].encode()) for d in EXPECTED},
        )
        self.assertFalse(os.path.exists(self.ppath("scripts/lib/tooling.conf")))
        self.assertFalse(os.path.exists(self.ppath("scripts/check.sh")))

    def test_revendor_is_idempotent(self):
        self.assertEqual(self.vendor().returncode, 0)
        before = self.snapshot()
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(),
            [f"vendored shipyard 1.0.0: 0 written, {len(EXPECTED)} unchanged, 0 removed"],
        )
        self.assertEqual(self.snapshot(), before, "a second run must write nothing")

    def test_mode_is_restored_without_rewriting(self):
        self.vendor()
        os.chmod(self.ppath("scripts/wip.py"), 0o644)
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(self.ppath("scripts/wip.py")).st_mode), 0o755)

    def test_tooling_conf_and_check_sh_are_never_touched(self):
        write(self.ppath("scripts/lib/tooling.conf"), "PROJECT_SLUG=mine\n", 0o600)
        write(self.ppath("scripts/check.sh"), "#!/usr/bin/env bash\n# mine\n", 0o700)
        write(self.ppath("scripts/other.py"), "# not vendored\n")
        mine = ("scripts/lib/tooling.conf", "scripts/check.sh", "scripts/other.py")
        before = {rel: self.snapshot()[rel] for rel in mine}
        for args in ((), ("--force",)):
            with self.subTest(args):
                self.assertEqual(self.vendor(*args).returncode, 0)
                after = self.snapshot()
                for rel, value in before.items():
                    self.assertEqual(after[rel], value, rel)
        self.assertNotIn("scripts/lib/tooling.conf", self.record()["files"])
        self.assertNotIn("scripts/check.sh", self.record()["files"])

    def test_modified_file_is_refused_then_forced(self):
        self.vendor()
        write(self.ppath("scripts/wip.py"), "# edited by hand\n")
        self.publish("1.1.0", **{"scripts__pr_size.py": "# pr_size v1.1\n"})
        before = self.snapshot()
        proc = self.vendor()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.splitlines(), ["modified scripts/wip.py"])
        self.assertIn("--force", proc.stderr)
        self.assertEqual(self.snapshot(), before, "a refusal writes nothing, not even the rest")
        proc = self.vendor("--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertIn("replaced scripts/wip.py", lines)
        self.assertIn("updated scripts/pr_size.py", lines)
        self.assertEqual(
            read(self.ppath("scripts/wip.py")), self.templates["scripts/wip.py"].encode()
        )
        self.assertEqual(self.record()["shipyard"], "1.1.0")
        self.assertEqual(self.vendor("--check").stdout, "ok\n")

    def test_unrecorded_file_is_adopted_when_identical_refused_otherwise(self):
        write(self.ppath("scripts/wip.py"), self.templates["scripts/wip.py"])
        write(self.ppath("scripts/owners.py"), "# a project's own owners.py\n")
        proc = self.vendor()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.splitlines(), ["modified scripts/owners.py"])
        os.remove(self.ppath("scripts/owners.py"))
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("added scripts/wip.py", proc.stdout.splitlines())
        self.assertIn("scripts/wip.py", self.record()["files"])

    def test_new_version_updates_adds_and_removes(self):
        self.vendor()
        self.publish(
            "2.0.0",
            **{
                "scripts__wip.py": "# wip v2\n",
                "scripts__selftest__test_gamma.py": "# gamma\n",
                "scripts__selftest__test_beta.py": None,
            },
        )
        proc = self.vendor()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertIn("updated scripts/wip.py", lines)
        self.assertIn("added scripts/selftest/test_gamma.py", lines)
        self.assertIn("removed scripts/selftest/test_beta.py", lines)
        self.assertFalse(os.path.exists(self.ppath("scripts/selftest/test_beta.py")))
        record = self.record()
        self.assertEqual(record["shipyard"], "2.0.0")
        self.assertNotIn("scripts/selftest/test_beta.py", record["files"])
        self.assertEqual(self.vendor("--check").stdout, "ok\n")

    def test_an_edited_file_the_plugin_dropped_is_refused(self):
        self.vendor()
        write(self.ppath("scripts/selftest/test_beta.py"), "# edited\n")
        self.publish("2.0.0", **{"scripts__selftest__test_beta.py": None})
        proc = self.vendor()
        self.assertEqual(
            (proc.returncode, proc.stdout), (1, "modified scripts/selftest/test_beta.py\n")
        )
        self.assertTrue(os.path.exists(self.ppath("scripts/selftest/test_beta.py")))
        self.assertEqual(self.vendor("--force").returncode, 0)
        self.assertFalse(os.path.exists(self.ppath("scripts/selftest/test_beta.py")))

    # --- --check ---

    def check(self):
        before = self.snapshot()
        proc = self.vendor("--check")
        self.assertEqual(self.snapshot(), before, "--check writes nothing")
        return proc.returncode, proc.stdout.splitlines()

    def test_check_states(self):
        rc, lines = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(lines[0], "outdated none -> 1.0.0")
        self.assertEqual(
            sorted(lines[1:]),
            sorted([f"missing {d}" for d in EXPECTED] + ["missing scripts/lib/VENDORED.json"]),
        )

        self.vendor()
        self.assertEqual(self.check(), (0, ["ok"]))

        self.publish("1.0.1")  # a version bump alone
        self.assertEqual(self.check(), (1, ["outdated 1.0.0 -> 1.0.1"]))
        self.vendor()
        self.assertEqual(self.check(), (0, ["ok"]))

        self.publish("1.0.1", **{"scripts__wip.py": "# changed, same version\n"})
        self.assertEqual(self.check(), (1, ["outdated 1.0.1 -> 1.0.1"]))
        self.vendor()

        write(self.ppath("scripts/owners.py"), "# edited\n")
        self.assertEqual(self.check(), (1, ["modified scripts/owners.py"]))

        os.remove(self.ppath("scripts/pr_size.py"))
        self.assertEqual(
            self.check(), (1, ["modified scripts/owners.py", "missing scripts/pr_size.py"])
        )

        self.publish("1.1.0")
        self.assertEqual(
            self.check(),
            (
                1,
                [
                    "outdated 1.0.1 -> 1.1.0",
                    "modified scripts/owners.py",
                    "missing scripts/pr_size.py",
                ],
            ),
        )

    def test_check_sees_a_template_added_or_dropped(self):
        self.vendor()
        self.publish("1.0.0", **{"scripts__selftest__test_gamma.py": "# gamma\n"})
        self.assertEqual(
            self.check(), (1, ["outdated 1.0.0 -> 1.0.0", "missing scripts/selftest/test_gamma.py"])
        )
        self.vendor()
        self.publish("1.0.0", **{"scripts__selftest__test_gamma.py": None})
        self.assertEqual(self.check(), (1, ["outdated 1.0.0 -> 1.0.0"]))

    # --- usage errors ---

    def test_usage_errors_exit_2(self):
        missing_root = os.path.join(self.tmp, "nope")
        cases = [
            ("no root", ()),
            ("root does not exist", (missing_root,)),
            ("check and force", (self.project, "--check", "--force")),
            ("unknown option", (self.project, "--bogus")),
            ("root inside the plugin", (os.path.join(self.plugin, "templates"),)),
        ]
        for desc, args in cases:
            with self.subTest(desc):
                proc = subprocess.run(
                    [sys.executable, self.vendor_py(), *args],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_broken_plugin_or_record_exits_2(self):
        self.vendor()
        write(self.ppath("scripts/lib/VENDORED.json"), "{not json")
        for args in ((), ("--check",)):
            with self.subTest(f"bad record {args}"):
                proc = self.vendor(*args)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("VENDORED.json is unreadable", proc.stderr)
        os.remove(self.ppath("scripts/lib/VENDORED.json"))
        os.remove(os.path.join(self.plugin, "templates", "scripts", "owners.py"))
        proc = self.vendor()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing template templates/scripts/owners.py", proc.stderr)
        os.remove(os.path.join(self.plugin, ".claude-plugin", "plugin.json"))
        proc = self.vendor("--check")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("plugin.json", proc.stderr)

    def test_help(self):
        proc = self.vendor("--help", root="--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("VENDORED.json", proc.stdout)
        self.assertIn("Why", proc.stdout)


class RealPlugin(unittest.TestCase):
    def test_manifest_matches_the_templates(self):
        entries = V.manifest()  # raises when a template of the contract is missing
        dests = [d for d, _, _ in entries]
        self.assertEqual(len(dests), len(set(dests)))
        templates = os.path.join(PLUGIN, "templates")
        selftests = sorted(
            n for n in os.listdir(os.path.join(templates, "scripts", "selftest"))
            if n.startswith("test_") and n.endswith(".py")
        )
        self.assertEqual(
            sorted(d.rsplit("/", 1)[1] for d in dests if d.startswith("scripts/selftest/")), selftests
        )
        top = sorted(
            n for n in os.listdir(os.path.join(templates, "scripts"))
            if os.path.isfile(os.path.join(templates, "scripts", n))
        )
        self.assertEqual(
            sorted(d.split("/", 1)[1] for d in dests if d.count("/") == 1 and d.startswith("scripts/")),
            top,
            "a file in templates/scripts/ is not vendored, or the reverse",
        )
        for dest, src, executable in entries:
            if executable:
                with self.subTest(dest):
                    self.assertTrue(os.access(src, os.X_OK), f"template {src} is not executable")

    @unittest.skipUnless(os.path.isfile(PLUGIN_JSON), "plugin.json not written yet")
    def test_version_comes_from_plugin_json(self):
        with open(PLUGIN_JSON, encoding="utf-8") as fh:
            version = json.load(fh)["version"]
        empty = tempfile.mkdtemp(prefix="vendor-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        proc = subprocess.run(
            [sys.executable, VENDOR, empty, "--check"], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[0], f"outdated none -> {version}")
        self.assertEqual(os.listdir(empty), [])


TOOLING_CONF = r"""# scripts/lib/tooling.conf — single source for values shared by hooks, scripts, CI and skills.
# kebab-case, prefix of every local name
PROJECT_SLUG=acme-api
# the only protected branch
DEFAULT_BRANCH=main
# namespace of the project's git config keys
GIT_CONFIG_NS=acme-api
# marker written by worktree_setup.sh, honoured by cleanup_local.py
SETUP_MARKER=.acme-api-setup-in-progress
# once-a-day stamp of the scheduled-runs check
SCHEDULED_STAMP=.acme-api-scheduled-check
# manual worktrees: <prefix><topic>
WORKTREE_PREFIX=../acme-api-
# component ids, in CI job order
COMPONENTS='api web'
# paths of the api component
COMPONENT_API_RE='^api/|^PRIVACY\.md$'
# paths of the web component
COMPONENT_WEB_RE='^web/|^package(-lock)?\.json$'
# solo or team
TEAM_MODE=team
# merge-deploy, merge or pr
AUTONOMY=merge
# continuous or planned
RELEASE_MODE=continuous
# added lines of code past which a pull request is lane B
SIZE_THRESHOLD=1500
# paths not counted by pr_size.py
SIZE_EXCLUDE_RE='\.md$|^wip/|^\.llmwiki/|^docs/|(^|/)tests?/|(^|/)__snapshots__/|\.lock$|-lock\.json$|\.snap$|^generated/'
# sensitive paths: lane C
LANE_C_RE='^api/auth/|^migrations/|PRIVACY\.md$'
# what a merge deploys
DEPLOY_PATHS_RE='^api/|^web/'
# untracked file of the deploy targets
DEPLOY_ENV_FILE=deploy.env
# paths refused at commit
SECRET_PATH_RE='(^|/)\.env$|(^|/)\.env\.|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|\.keystore$|(^|/)id_(rsa|ed25519|ecdsa)$|(^|/)deploy\.env$'
# exceptions to SECRET_PATH_RE
SECRET_ALLOW_RE='\.example$|\.template$|\.sample$'
# content refused in a committed file
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|"type"[ \t]*:[ \t]*"service_account"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}'
# max entries in wip/todo/
WIP_LIMIT=12
# size of wip/todo_nr/ past which a refinement is suggested
REFINE_THRESHOLD=30
# an entry idle this many days is stale
STALE_DAYS=60
# more open entries on a theme than this: merge candidates
CROWDED_THEME=4
# max lines of a wiki page
WIKI_PAGE_BUDGET=400
# max lines of CLAUDE.md
CLAUDE_MD_BUDGET=120
# a worktree modified more recently is kept by the cleanup
CLEANUP_IDLE_MINUTES=30
# roots whose backticked paths are checked
DEAD_PATH_ROOTS='api|web|scripts|docs|\.claude|\.llmwiki|\.github|wip'
# max simultaneous implementing agents
CONCURRENCY_CAP=4
# pruning pass cadence in continuous delivery
PRUNE_EVERY_MERGES=30
# essentiel or complet
TOOLING_LEVEL=essentiel
"""

CI_YML = """# .github/workflows/ci.yml — the only workflow carrying required checks.
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  scope:
    name: Scope
    runs-on: ubuntu-latest
    outputs:
      api: ${{ steps.flags.outputs.api }}
      web: ${{ steps.flags.outputs.web }}
    steps:
      - id: flags
        run: |
          gh api "repos/$REPO/pulls/$PR/files?per_page=100" --paginate \\
             --jq '.[] | .filename, (.previous_filename // empty)' \\
            | python3 scripts/ci_scope.py | tee -a "$GITHUB_OUTPUT"

  tooling:
    name: Tooling — selftests, wiki, wip
    runs-on: ubuntu-24.04
    steps:
      - run: scripts/selftest.sh

  api:
    name: Api — lint, tests
    needs: scope
    if: ${{ !cancelled() && needs.scope.outputs.api != 'false' }}
    runs-on: ubuntu-latest
    steps:
      - run: scripts/check.sh ci api

  web:
    name: Web — lint, tests
    needs: scope
    if: ${{ !cancelled() && needs.scope.outputs.web != 'false' }}
    runs-on: ubuntu-latest
    steps:
      - run: scripts/check.sh ci web
"""


class EndToEnd(unittest.TestCase):
    """The real templates, vendored into a fresh project whose own selftest.sh then runs."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="vendor-e2e-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vendor_py = VENDOR
        if not os.path.isfile(PLUGIN_JSON):  # B5 has not written it yet: a temporary plugin tree
            plugin = os.path.join(self.tmp, "plugin")
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
            shutil.copytree(os.path.join(PLUGIN, "bin"), os.path.join(plugin, "bin"), ignore=ignore)
            shutil.copytree(
                os.path.join(PLUGIN, "templates"), os.path.join(plugin, "templates"), ignore=ignore
            )
            write(
                os.path.join(plugin, ".claude-plugin", "plugin.json"), '{"version": "0.0.0-test"}'
            )
            self.vendor_py = os.path.join(plugin, "bin", "vendor.py")
        self.project = os.path.join(self.tmp, "acme-api")
        self.env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("GIT_", "GH_", "CLAUDE")) and k != "PYTHONDONTWRITEBYTECODE"
        }
        self.env.update(
            GIT_AUTHOR_NAME="Selftest",
            GIT_AUTHOR_EMAIL="selftest@example.invalid",
            GIT_COMMITTER_NAME="Selftest",
            GIT_COMMITTER_EMAIL="selftest@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=self.tmp,
            SELFTEST_PYTHON=sys.executable,
        )
        os.makedirs(self.project)
        self.git("init", "-q", "-b", "main")
        write(os.path.join(self.project, "scripts", "lib", "tooling.conf"), TOOLING_CONF)
        write(os.path.join(self.project, ".github", "workflows", "ci.yml"), CI_YML)
        write(
            os.path.join(self.project, ".github", "CODEOWNERS"),
            "# Kept by /shipyard:join, read by scripts/owners.py.\n* @lead\n/api/ @alice\n",
        )
        write(
            os.path.join(self.project, ".gitignore"), "__pycache__/\n/.acme-api-setup-in-progress\n"
        )

    def git(self, *args):
        subprocess.run(
            ["git", *args],
            cwd=self.project,
            env=self.env,
            check=True,
            capture_output=True,
            timeout=60,
        )

    def run_in_project(self, args, timeout=600):
        return subprocess.run(
            args, cwd=self.project, env=self.env, capture_output=True, text=True, timeout=timeout
        )

    def test_vendor_then_the_project_selftests_pass(self):
        proc = self.run_in_project([sys.executable, self.vendor_py, self.project])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "chore: vendor shipyard tooling")

        proc = self.run_in_project(["bash", "scripts/selftest.sh"])
        self.assertEqual(proc.returncode, 0, proc.stdout[-6000:] + proc.stderr[-3000:])
        self.assertRegex(
            proc.stdout.splitlines()[-1], r"^selftest\.sh: OK, [1-9][0-9]* tests in 1 folder\(s\)$"
        )

        # The project-only cases ran, instead of being skipped as they are inside the plugin.
        proc = self.run_in_project(
            [sys.executable, "-m", "unittest", "discover", "-v", "-s", "scripts/selftest"]
            + ["-p", "test_ci_scope.py"]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("project contract", proc.stderr)
        self.assertIn("test_component_jobs_carry_the_exact_condition", proc.stderr)

        proc = self.run_in_project([sys.executable, self.vendor_py, self.project, "--check"])
        self.assertEqual((proc.returncode, proc.stdout), (0, "ok\n"), proc.stderr)
        status = self.run_in_project(["git", "status", "--porcelain"])
        self.assertEqual(status.stdout, "", "vendoring and the selftests left the tree dirty")


if __name__ == "__main__":
    unittest.main()
