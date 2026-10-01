"""Selftest of scripts/owners.py: CODEOWNERS semantics and the command line.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
The matching cases are a table (patterns, path, expected owners) taken from GitHub's CODEOWNERS
documentation and from gitignore's pattern rules, run against the pure functions; the command
line runs in sandbox repositories (tempfile.mkdtemp). The `Project` case reads the project's own
CODEOWNERS, when there is one, once this file is vendored. No network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "owners.py")
IN_PROJECT = os.path.isfile(os.path.join(ROOT, "scripts", "lib", "tooling.conf"))


def load_module():
    spec = importlib.util.spec_from_file_location("owners_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# (description, CODEOWNERS text, path, expected owners)
MATCHING = [
    ("star owns everything", "* @all", "a/b/c.txt", ["@all"]),
    ("star owns a root file", "* @all", "README.md", ["@all"]),
    ("extension at any depth", "*.js @js", "web/src/app.js", ["@js"]),
    ("extension does not match another", "*.js @js", "web/src/app.ts", []),
    ("last match wins", "* @all\n*.js @js", "x/a.js", ["@js"]),
    ("earlier match loses", "*.js @js\n* @all", "x/a.js", ["@all"]),
    ("anchored directory, contents", "/build/logs/ @doc", "build/logs/a/b.log", ["@doc"]),
    ("anchored directory, not elsewhere", "/build/logs/ @doc", "x/build/logs/a.log", []),
    ("docs/* direct file", "docs/* @d", "docs/getting-started.md", ["@d"]),
    ("docs/* not nested", "docs/* @d", "docs/build-app/troubleshooting.md", []),
    ("docs/* anchored", "docs/* @d", "x/docs/a.md", []),
    ("unanchored directory anywhere", "apps/ @oc", "deep/apps/x.py", ["@oc"]),
    ("unanchored directory at root", "apps/ @oc", "apps/x.py", ["@oc"]),
    ("trailing slash needs a directory", "apps/ @oc", "apps", []),
    ("leading /docs/", "/docs/ @doc", "docs/a/b.md", ["@doc"]),
    ("leading /docs/ is anchored", "/docs/ @doc", "src/docs/a.md", []),
    ("**/logs at root", "**/logs @oc", "logs/a.txt", ["@oc"]),
    ("**/logs nested", "**/logs @oc", "deeply/nested/logs/a.txt", ["@oc"]),
    ("**/logs not a prefix", "**/logs @oc", "mylogs/a.txt", []),
    ("trailing /**", "docs/** @d", "docs/a/b/c.md", ["@d"]),
    ("middle /**/ zero dirs", "a/**/b @x", "a/b", ["@x"]),
    ("middle /**/ many dirs", "a/**/b @x", "a/1/2/b/c", ["@x"]),
    ("middle /**/ not a suffix", "a/**/b @x", "a/xb", []),
    ("subdirectory un-owned", "/apps/ @oc\n/apps/github", "apps/github/x", []),
    ("subdirectory sibling kept", "/apps/ @oc\n/apps/github", "apps/other/x", ["@oc"]),
    ("subdirectory reassigned", "/apps/ @oc\n/apps/github @doc", "apps/github/x", ["@doc"]),
    ("name without slash anywhere", "Makefile @m", "tools/Makefile", ["@m"]),
    ("anchored name only at root", "/Makefile @m", "tools/Makefile", []),
    ("path pattern anchored", "src/app @s", "src/app/main.py", ["@s"]),
    ("path pattern not elsewhere", "src/app @s", "lib/src/app/main.py", []),
    ("question mark one char", "file?.txt @q", "file1.txt", ["@q"]),
    ("question mark not a slash", "a?b @q", "a/b", []),
    ("star does not cross a slash", "/src/*.py @p", "src/a/b.py", []),
    ("case sensitive", "/Docs/ @d", "docs/a.md", []),
    ("several owners", "* @a @org/team b@example.com", "x", ["@a", "@org/team", "b@example.com"]),
    ("inline comment", "*.js @js #This is an inline comment.", "a.js", ["@js"]),
    ("comment line", "# * @nobody\n*.go @go", "a.go", ["@go"]),
    ("escaped space", "/my\\ dir/ @sp", "my dir/a.txt", ["@sp"]),
    ("brackets are literal", "/a[1].txt @b", "a[1].txt", ["@b"]),
    ("brackets are not a range", "/a[1].txt @b", "a1.txt", []),
    ("negation is skipped", "* @all\n!*.md @none", "a.md", ["@all"]),
    ("no pattern matches", "/src/ @s", "lib/a.py", []),
]


class Matching(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_table(self):
        for desc, text, path, expected in MATCHING:
            with self.subTest(desc):
                rules = self.m.parse(text)
                self.assertEqual(self.m.owners_of(path, rules), expected, f"{text!r} on {path}")

    def test_owned_by(self):
        text = "* @Lead\n/api/ @alice @bob\n/web/ @org/alice\n/api/ @alice\n/docs/ alice@x.io"
        rules = self.m.parse(text)
        self.assertEqual(self.m.owned_by("alice", rules), ["/api/"])
        self.assertEqual(self.m.owned_by("@ALICE", rules), ["/api/"])
        self.assertEqual(self.m.owned_by("lead", rules), ["*"])
        self.assertEqual(self.m.owned_by("carol", rules), [])

    def test_normalize(self):
        for raw, want in (("  ./a/b  ", "a/b"), ("/a", "a"), ("././a", "a"), ("", "")):
            with self.subTest(raw):
                self.assertEqual(self.m.normalize(raw), want)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="owners-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", self.repo], check=True, env=self.env(), timeout=30)

    def env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=self.tmp,
        )
        return env

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def owners(self, *args, stdin="", cwd=None):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=cwd or self.repo,
            env=self.env(),
            timeout=30,
        )

    def test_paths_to_owners(self):
        self.write(
            ".github/CODEOWNERS",
            "# Kept by /shipyard:join, read by scripts/owners.py.\n"
            "* @lead\n/api/ @alice @bob\n/docs/\n",
        )
        proc = self.owners(stdin="api/a.py\n\n  ./README.md \ndocs/x.md\napi/a.py\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(),
            ["api/a.py\t@alice @bob", "README.md\t@lead", "docs/x.md\t", "api/a.py\t@alice @bob"],
        )

    def test_who(self):
        self.write(".github/CODEOWNERS", "* @lead\n/api/ @alice\n/web/ @bob @alice\n")
        proc = self.owners("--who", "alice")
        self.assertEqual((proc.returncode, proc.stdout.splitlines()), (0, ["/api/", "/web/"]))
        proc = self.owners("--who", "@Lead")
        self.assertEqual((proc.returncode, proc.stdout.splitlines()), (0, ["*"]))
        proc = self.owners("--who", "carol")
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))

    def test_who_does_not_read_stdin(self):
        # The session hook calls it without stdin: it must not wait for one.
        self.write("CODEOWNERS", "* @lead\n")
        proc = subprocess.Popen(
            [sys.executable, SCRIPT, "--who", "lead"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.repo,
            env=self.env(),
        )
        try:
            proc.wait(timeout=20)  # stdin stays open: a script reading it would hang here
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            self.fail("owners.py --who waited for stdin")
        out = proc.stdout.read().decode()
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()
        self.assertEqual((proc.returncode, out.splitlines()), (0, ["*"]))

    def test_location_order(self):
        self.write("docs/CODEOWNERS", "* @docs-file\n")
        self.assertEqual(self.owners(stdin="a\n").stdout, "a\t@docs-file\n")
        self.write("CODEOWNERS", "* @root-file\n")
        self.assertEqual(self.owners(stdin="a\n").stdout, "a\t@root-file\n")
        self.write(".github/CODEOWNERS", "* @github-file\n")
        self.assertEqual(self.owners(stdin="a\n").stdout, "a\t@github-file\n")

    def test_runs_from_a_subdirectory(self):
        self.write(".github/CODEOWNERS", "/api/ @alice\n")
        sub = os.path.join(self.repo, "api", "deep")
        os.makedirs(sub)
        proc = self.owners(stdin="api/a.py\n", cwd=sub)
        self.assertEqual(proc.stdout, "api/a.py\t@alice\n", proc.stderr)

    def test_no_codeowners_exits_2(self):
        for args in ((), ("--who", "alice")):
            with self.subTest(args):
                proc = self.owners(*args, stdin="a\n")
                self.assertEqual(proc.returncode, 2)
                self.assertIn("no CODEOWNERS", proc.stderr)

    def test_outside_a_repository_exits_2(self):
        outside = os.path.join(self.tmp, "outside")
        os.mkdir(outside)
        proc = self.owners(stdin="a\n", cwd=outside)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not inside a git repository", proc.stderr)

    def test_usage_errors_exit_2(self):
        self.write("CODEOWNERS", "* @lead\n")
        for args in (("--who",), ("--who", "@"), ("--bogus",)):
            with self.subTest(args):
                self.assertEqual(self.owners(*args).returncode, 2)

    def test_unsupported_line_is_skipped_with_a_warning(self):
        self.write("CODEOWNERS", "* @lead\n!*.md @nobody\n")
        proc = self.owners(stdin="a.md\n")
        self.assertEqual(proc.stdout, "a.md\t@lead\n")
        self.assertIn("line 2", proc.stderr)

    def test_reads_stdin_to_the_end(self):
        self.write("CODEOWNERS", "* @lead\n")
        payload = "".join(f"dir/file-{i}.txt\n" for i in range(20000)).encode()
        proc = subprocess.Popen(
            [sys.executable, SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.repo,
            env=self.env(),
        )
        out, err = proc.communicate(payload, timeout=60)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(len(out.splitlines()), 20000)

    def test_help_and_executable(self):
        proc = self.owners("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("the LAST pattern that matches a path wins", " ".join(proc.stdout.split()))
        self.assertIn("Why", proc.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/owners.py")


@unittest.skipUnless(IN_PROJECT, "project contract: runs once vendored into a project")
class Project(unittest.TestCase):
    def test_the_project_codeowners_parses(self):
        m = load_module()
        path = m.find_codeowners(ROOT)
        if path is None:
            self.skipTest("this project has no CODEOWNERS (solo mode)")
        warnings = []
        with open(path, encoding="utf-8") as fh:
            rules = m.parse(fh.read(), warn=warnings.append)
        self.assertEqual(warnings, [], "CODEOWNERS holds lines GitHub skips")
        for rule in rules:
            with self.subTest(rule.pattern):
                for owner in rule.owners:
                    self.assertRegex(
                        owner, r"^@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9._-]+)?$|^[^@\s]+@[^@\s]+$"
                    )


if __name__ == "__main__":
    unittest.main()
