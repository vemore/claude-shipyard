"""Selftest of scripts/precommit.py and of .githooks/pre-commit, on throwaway repositories.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'   (in a project)
     python3 -m unittest discover -s plugins/shipyard/templates/scripts/selftest -p 'test_precommit.py'
                                                                     (in the plugin repository)

Guarantees: the script under test is located relative to this file (``../precommit.py``), so
the same file tests the plugin's template and a project's vendored copy; the git hook is
looked for at ``../../.githooks/pre-commit`` (project) or ``../../githooks/pre-commit``
(plugin), and its cases are skipped when neither exists. Each case runs in a sandbox
repository with its own tooling.conf (the annex 00 SECRET_* values), a stub
``scripts/check.sh`` that records its call, and an isolated git configuration. When this file
runs in a project, one more case checks that the project's own SECRET_CONTENT_RE lets the
kebab-case look-alikes through.

Does not cover: a project's real gates (check.sh is a stub); commits made inside Claude Code
(the shipyard plugin's hook judges those; its tests live in the plugin repository).

Why it exists: a commit gate that breaks lets everything through silently; a human commit is
the one path no other check sees before CI.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "precommit.py")
TOP = os.path.dirname(os.path.dirname(HERE))   # the project root, or the plugin's templates/
GITHOOK = next((p for p in (os.path.join(TOP, ".githooks", "pre-commit"),
                            os.path.join(TOP, "githooks", "pre-commit")) if os.path.isfile(p)),
               None)
PROJECT_CONF = os.path.join(TOP, "scripts", "lib", "tooling.conf")

# Fake secrets are assembled at run time so that this file never matches SECRET_CONTENT_RE.
PRIVATE_KEY = ("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n"
               "-----END OPENSSH " + "PRIVATE KEY-----\n")
SERVICE_ACCOUNT = '{"type": ' + '"service_account", "project_id": "demo-123"}\n'
CLOUD_KEY = "AKIA" + "QWERTYUIOPASDFGH"
API_KEY = "sk" + "-" + "a1B2c3D4" * 3
KEBAB_LOOK_ALIKES = ["risk-assessment-for-payments-module", "task-queue-processing-worker",
                     "[[2026-09-01-desk-booking-calendar-export]]"]

TOOLING_CONF = r"""# test values (annex 00 defaults for the SECRET_* keys)
DEFAULT_BRANCH=main
SECRET_PATH_RE='(^|/)\.env$|(^|/)\.env\.|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|\.keystore$|(^|/)id_(rsa|ed25519|ecdsa)$|(^|/)deploy\.env$'
SECRET_ALLOW_RE='\.example$|\.template$|\.sample$'
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|"type"[ \t]*:[ \t]*"service_account"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}'
"""

CHECK_STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
paths = None
if "--paths-from" in args:
    with open(args[args.index("--paths-from") + 1]) as handle:
        paths = handle.read().splitlines()
with open(os.environ["CHECK_STUB_LOG"], "a") as handle:
    handle.write(json.dumps({"args": args, "paths": paths}) + "\n")
code = int(os.environ.get("CHECK_STUB_EXIT", "0"))
if code == 1:
    print("stub: E501 line too long")
    print("Reproduce with: scripts/check.sh fast")
elif code == 3:
    print("SETUP: stub-install", file=sys.stderr)
sys.exit(code)
'''


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(text, bytes) else "w") as handle:
        handle.write(text)
    if mode:
        os.chmod(path, mode)


class Repo:
    """A sandbox repository with the vendored pair, a test tooling.conf and a stub check.sh."""

    def __init__(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="precommit-selftest-"))
        self.root = os.path.join(self.tmp, "repo")
        self.log = os.path.join(self.tmp, "check.log")
        self.gitconfig = os.path.join(self.tmp, "gitconfig")
        write(self.gitconfig, "[user]\n\tname = Selftest\n\temail = selftest@example.invalid\n"
                              "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n")
        os.makedirs(os.path.join(self.tmp, "home"))
        self.git("init", "-q", self.root, cwd=self.tmp)
        write(self.path("scripts/lib/tooling.conf"), TOOLING_CONF)
        write(self.path("scripts/check.sh"), CHECK_STUB, 0o755)
        with open(SCRIPT) as handle:
            write(self.path("scripts/precommit.py"), handle.read(), 0o755)
        if GITHOOK:
            with open(GITHOOK) as handle:
                write(self.path(".githooks/pre-commit"), handle.read(), 0o755)
        write(self.path("src/app.py"), "print('hello')\n")
        write(self.path(".gitignore"), ".env\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def path(self, rel):
        return os.path.join(self.root, rel)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "CHECK_STUB_")) and k != "CLAUDECODE"}
        env.update(HOME=os.path.join(self.tmp, "home"), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=self.gitconfig, CHECK_STUB_LOG=self.log, LC_ALL="C")
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def git(self, *args, cwd=None, check=True, **env):
        proc = subprocess.run(["git"] + list(args), cwd=cwd or self.root, env=self.env(**env),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        if check and proc.returncode != 0:
            raise AssertionError("git {} failed: {}".format(" ".join(args), proc.stderr))
        return proc

    def stage(self, rel, text, force=False):
        write(self.path(rel), text)
        self.git("add", *(["-f"] if force else []), "--", rel)

    def precommit(self, *args, cwd=None, **env):
        return subprocess.run([sys.executable, self.path("scripts/precommit.py")] + list(args),
                              cwd=cwd or self.root, env=self.env(**env), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)

    def gate_calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as handle:
            return [json.loads(line) for line in handle.read().splitlines()]

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class RepoCase(unittest.TestCase):

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def assert_code(self, proc, code, rule=None):
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        if rule:
            self.assertIn("BLOCKED ({})".format(rule), proc.stderr)
            self.assertIn("--no-verify", proc.stderr)
        return proc.stderr


class TestPrecommitScript(RepoCase):

    def test_help(self):
        proc = self.repo.precommit("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage", proc.stdout)

    def test_inside_claude_code_it_steps_aside(self):
        self.repo.stage(".env", "TOKEN=x\n", force=True)
        self.assert_code(self.repo.precommit(CLAUDECODE=1, CHECK_STUB_EXIT=1), 0)
        self.assertEqual(self.repo.gate_calls(), [])

    def test_outside_a_repository_passes(self):
        proc = self.repo.precommit(cwd=os.path.join(self.repo.tmp, "home"))
        self.assert_code(proc, 0)

    def test_green_gates_get_the_staged_paths(self):
        self.repo.stage("src/new.py", "x = 1\n")
        self.repo.git("rm", "-q", "src/app.py")
        self.assert_code(self.repo.precommit(), 0)
        call = self.repo.gate_calls()[-1]
        self.assertEqual(call["args"][:2], ["fast", "--paths-from"])
        self.assertEqual(call["paths"], ["src/app.py", "src/new.py"])

    def test_gate_outcomes(self):
        self.repo.stage("src/new.py", "x = 1\n")
        cases = [(1, "gates", "stub: E501"), (3, "gates-tool-missing", "SETUP: stub-install"),
                 (5, "gates-error", "exited 5")]
        for code, rule, needle in cases:
            with self.subTest(exit=code):
                proc = self.repo.precommit(CHECK_STUB_EXIT=code)
                self.assert_code(proc, 1, rule)
                self.assertIn(needle, proc.stdout + proc.stderr)

    def test_absent_check_passes_with_a_note(self):
        os.unlink(self.repo.path("scripts/check.sh"))
        self.repo.stage("src/new.py", "x = 1\n")
        self.assertIn("gates skipped", self.assert_code(self.repo.precommit(), 0))

    def test_secret_paths(self):
        cases = [(".env", True), (".env.example", False), ("config/deploy.env", True),
                 ("key.pem", True), ("certs/id_ed25519", True), ("docs/env.md", False)]
        for rel, refused in cases:
            with self.subTest(path=rel):
                self.repo.git("reset", "-q")
                self.repo.stage(rel, "VALUE=x\n", force=True)
                proc = self.repo.precommit()
                if refused:
                    self.assertIn(rel, self.assert_code(proc, 1, "secret-path"))
                else:
                    self.assert_code(proc, 0)

    def test_rename_to_a_secret_path_is_refused(self):
        self.repo.git("mv", "src/app.py", "src/app.pem")
        self.assert_code(self.repo.precommit(), 1, "secret-path")

    def test_secret_content(self):
        cases = [("creds-1234.json", SERVICE_ACCOUNT, "service-account"),
                 ("notes/keyfile.txt", PRIVATE_KEY, "private key header"),
                 ("src/cloud.py", "KEY = '{}'\n".format(CLOUD_KEY), "cloud access key"),
                 ("src/client.py", 'KEY = "{}"\n'.format(API_KEY), "API secret key")]
        for rel, text, kind in cases:
            with self.subTest(path=rel):
                self.repo.git("reset", "-q")
                self.repo.stage(rel, text)
                err = self.assert_code(self.repo.precommit(), 1, "secret-content")
                self.assertIn(rel, err)
                self.assertIn(kind, err)
                for secret in (CLOUD_KEY, API_KEY, "service_account", "b3BlbnNzaC1rZXktdjEAAAAA"):
                    self.assertNotIn(secret, err)
        self.assertEqual(self.repo.gate_calls(), [])

    def test_content_is_read_from_the_index(self):
        self.repo.stage("src/cloud.py", "KEY = '{}'\n".format(CLOUD_KEY))
        write(self.repo.path("src/cloud.py"), "KEY = None\n")   # clean copy, dirty index
        self.assert_code(self.repo.precommit(), 1, "secret-content")

    def test_look_alikes_pass(self):
        self.repo.stage("wip/todo/2026-09-01-desk-booking-calendar-export.md",
                        "\n".join(KEBAB_LOOK_ALIKES) + "\n")
        self.repo.stage("data.json", '{"type": "user", "name": "x"}\n')
        self.repo.stage(".env.example", "TOKEN=\n")
        self.assert_code(self.repo.precommit(), 0)

    def test_fixture_marker_and_binary_pass(self):
        self.repo.stage("tests/fixtures/fake_key.txt", "# secret-scan: fixture\n" + PRIVATE_KEY)
        self.repo.stage("assets/blob.bin", b"\x00\x01\x02" + PRIVATE_KEY.encode())
        self.assert_code(self.repo.precommit(), 0)

    def test_marker_after_line_five_does_not_count(self):
        self.repo.stage("notes.txt", "1\n2\n3\n4\n5\n# secret-scan: fixture\n" + PRIVATE_KEY)
        self.assert_code(self.repo.precommit(), 1, "secret-content")

    def test_deleting_a_secret_file_passes(self):
        self.repo.stage("old.pem", "x\n", force=True)
        self.repo.git("commit", "-q", "--no-verify", "-m", "legacy")
        self.repo.git("rm", "-q", "--cached", "old.pem")
        self.assert_code(self.repo.precommit(), 0)

    def test_invalid_regex_is_a_configuration_error(self):
        with open(self.repo.path("scripts/lib/tooling.conf"), "a") as handle:
            handle.write("SECRET_PATH_RE='(unclosed'\n")
        self.repo.stage("src/new.py", "x = 1\n")
        self.assert_code(self.repo.precommit(), 2, "bad-config")

    def test_missing_conf_is_a_configuration_error(self):
        os.unlink(self.repo.path("scripts/lib/tooling.conf"))
        self.repo.stage("src/new.py", "x = 1\n")
        self.assert_code(self.repo.precommit(), 2, "bad-config")

    def test_merge_judges_the_branch_side(self):
        repo = self.repo
        repo.git("switch", "-q", "-c", "feat/x")
        repo.stage("feature.txt", "feature\n")
        repo.git("commit", "-q", "-m", "feature")
        repo.git("switch", "-q", "main")
        repo.stage("upstream.txt", "upstream\n")
        repo.git("commit", "-q", "-m", "upstream")
        repo.git("switch", "-q", "feat/x")
        repo.git("merge", "-q", "--no-commit", "--no-ff", "main")
        self.assert_code(repo.precommit(), 0)
        paths = repo.gate_calls()[-1]["paths"]
        self.assertIn("feature.txt", paths)
        self.assertNotIn("upstream.txt", paths)


@unittest.skipUnless(GITHOOK, "no .githooks/pre-commit next to this copy")
class TestGitHook(RepoCase):

    def setUp(self):
        RepoCase.setUp(self)
        self.repo.git("config", "core.hooksPath", ".githooks")

    def commit(self, *extra, **env):
        return self.repo.git("commit", "-q", "-m", "x", *extra, check=False, **env)

    def test_green_commit_goes_through(self):
        self.repo.stage("src/new.py", "x = 1\n")
        self.assert_code(self.commit(), 0)
        self.assertEqual(self.repo.gate_calls()[-1]["paths"], ["src/new.py"])

    def test_red_gates_refuse_the_commit(self):
        self.repo.stage("src/new.py", "x = 1\n")
        proc = self.commit(CHECK_STUB_EXIT=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BLOCKED (gates)", proc.stderr)

    def test_inside_claude_code_it_steps_aside(self):
        self.repo.stage("src/new.py", "x = 1\n")
        self.assert_code(self.commit(CLAUDECODE=1, CHECK_STUB_EXIT=1), 0)
        self.assertEqual(self.repo.gate_calls(), [])

    def test_commit_all_and_pathspec_commits_are_judged(self):
        write(self.repo.path("src/app.py"), "KEY = '{}'\n".format(CLOUD_KEY))
        for extra in (["-a"], ["--", "src/app.py"]):
            with self.subTest(args=extra):
                proc = self.commit(*extra)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("BLOCKED (secret-content)", proc.stderr)
                self.assertNotIn(CLOUD_KEY, proc.stderr)

    def test_no_verify_is_the_escape_hatch(self):
        self.repo.stage("src/new.py", "x = 1\n")
        self.assert_code(self.commit("--no-verify", CHECK_STUB_EXIT=1), 0)
        self.assertEqual(self.repo.gate_calls(), [])


@unittest.skipUnless(os.path.isfile(PROJECT_CONF), "runs in a project only (its tooling.conf)")
class TestProjectSecretRegex(unittest.TestCase):

    def test_kebab_case_look_alikes_pass_the_project_regex(self):
        values = {}
        with open(PROJECT_CONF, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                        value = value[1:-1]
                    values[key.strip()] = value
        pattern = values.get("SECRET_CONTENT_RE", "")
        if not pattern:
            self.skipTest("SECRET_CONTENT_RE is empty: the content scan is off")
        compiled = re.compile(pattern)
        for text in KEBAB_LOOK_ALIKES:
            with self.subTest(text=text):
                self.assertIsNone(compiled.search(text), "SECRET_CONTENT_RE matches " + text)


if __name__ == "__main__":
    unittest.main()
