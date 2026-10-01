"""Selftest of scripts/pr_size.py on hand-written diffs.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Table-driven: (description, diff, expected count). The script runs in a sandbox repository
(tempfile.mkdtemp) whose tooling.conf holds the default SIZE_EXCLUDE_RE of a bootstrapped project,
so the cases do not depend on the project's own value; the `Project` case checks that value
compiles once this file is vendored. `gh` is a stub on PATH (a script answering from an
environment variable): no network, no GitHub account needed.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "pr_size.py")
IN_PROJECT = os.path.isfile(os.path.join(ROOT, "scripts", "lib", "tooling.conf"))
CONF = r"""# sandbox tooling.conf
SIZE_EXCLUDE_RE='\.md$|^wip/|^\.llmwiki/|^docs/|(^|/)tests?/|(^|/)__snapshots__/|\.lock$|-lock\.json$|\.snap$|^generated/'
"""
SANDBOX = {}


def setUpModule():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="pr-size-repo-"))
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "scripts", "lib"))
    env = clean_env(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "init", "-q", repo], check=True, env=env, timeout=30)
    with open(os.path.join(repo, "scripts", "lib", "tooling.conf"), "w", encoding="utf-8") as fh:
        fh.write(CONF)
    SANDBOX.update(tmp=tmp, repo=repo)


def tearDownModule():
    shutil.rmtree(SANDBOX.get("tmp", ""), ignore_errors=True)


def hunk_file(path, added, removed=0, header_extra=""):
    lines = [f"diff --git a/{path} b/{path}", "index 1111111..2222222 100644"]
    lines += [header_extra] if header_extra else []
    lines += [f"--- a/{path}", f"+++ b/{path}", f"@@ -1,{removed + 1} +1,{added + 1} @@", " ctx"]
    lines += [f"-old {i}" for i in range(removed)] + [f"+new {i}" for i in range(added)]
    return "\n".join(lines) + "\n"


DOCS_ONLY = hunk_file("README.md", 5) + hunk_file(".llmwiki/Testing.md", 7)
NEW_FILE = textwrap.dedent(
    """\
    diff --git a/src/app/plan.py b/src/app/plan.py
    new file mode 100644
    index 0000000..3333333
    --- /dev/null
    +++ b/src/app/plan.py
    @@ -0,0 +1,10 @@
    """
) + "".join(f"+line {i}\n" for i in range(10))
MODIFIED = hunk_file("src/app/cli.py", 3, removed=3)
DELETED = textwrap.dedent(
    """\
    diff --git a/src/app/old.py b/src/app/old.py
    deleted file mode 100644
    index 4444444..0000000
    --- a/src/app/old.py
    +++ /dev/null
    @@ -1,5 +0,0 @@
    -a
    -b
    -c
    -d
    -e
    """
)
RENAMED = textwrap.dedent(
    """\
    diff --git a/tests/helpers.py b/src/app/helpers.py
    similarity index 90%
    rename from tests/helpers.py
    rename to src/app/helpers.py
    index 5555555..6666666 100644
    --- a/tests/helpers.py
    +++ b/src/app/helpers.py
    @@ -1,2 +1,4 @@
     keep
    +added one
    +added two
     keep
    """
)
RENAMED_PURE = textwrap.dedent(
    """\
    diff --git a/src/app/a.py b/src/app/b.py
    similarity index 100%
    rename from src/app/a.py
    rename to src/app/b.py
    """
)
PLUS_CONTENT = textwrap.dedent(
    """\
    diff --git a/src/app/ops.py b/src/app/ops.py
    index 7777777..8888888 100644
    --- a/src/app/ops.py
    +++ b/src/app/ops.py
    @@ -1,1 +1,4 @@
     x = 1
    ++x
    +++y
    +++ b/not-a-header
    """
)
BINARY = textwrap.dedent(
    """\
    diff --git a/src/app/icon.png b/src/app/icon.png
    new file mode 100644
    index 0000000..9999999
    Binary files /dev/null and b/src/app/icon.png differ
    diff --git a/src/app/logo.png b/src/app/logo.png
    index 1111111..2222222 100644
    GIT binary patch
    literal 12
    TcmZ?wbhEHbRA2x?3%1Cl
    """
)
QUOTED = textwrap.dedent(
    """\
    diff --git "a/src/\\303\\251t\\303\\251 x.py" "b/src/\\303\\251t\\303\\251 x.py"
    index 1111111..2222222 100644
    --- "a/src/\\303\\251t\\303\\251 x.py"
    +++ "b/src/\\303\\251t\\303\\251 x.py"
    @@ -1 +1,3 @@
     a
    +b
    +c
    diff --git "a/docs/caf\\303\\251.md" "b/docs/caf\\303\\251.md"
    index 1111111..2222222 100644
    --- "a/docs/caf\\303\\251.md"
    +++ "b/docs/caf\\303\\251.md"
    @@ -1 +1,2 @@
     a
    +excluded once unquoted
    """
)
SPACES = textwrap.dedent(
    """\
    diff --git a/src/app/my module.py b/src/app/my module.py
    index 1111111..2222222 100644
    --- a/src/app/my module.py\t
    +++ b/src/app/my module.py\t
    @@ -1 +1,2 @@
     a
    +b
    diff --git a/docs/user guide.md b/docs/user guide.md
    index 1111111..2222222 100644
    --- a/docs/user guide.md\t
    +++ b/docs/user guide.md\t
    @@ -1 +1,2 @@
     a
    +b
    """
)

CASES = [
    ("empty diff", "", 0),
    ("docs only", DOCS_ONLY, 0),
    ("10 added lines of code", NEW_FILE, 10),
    ("3 modified lines count once", MODIFIED, 3),
    ("deleted file", DELETED, 0),
    ("test file excluded", hunk_file("tests/test_cli.py", 40), 0),
    ("lock excluded", hunk_file("uv.lock", 50), 0),
    ("wip entry excluded", hunk_file("wip/todo/2026-10-01-x.md", 9), 0),
    ("rename with changes counts under the new path", RENAMED, 2),
    ("rename without change", RENAMED_PURE, 0),
    ("content lines starting with ++ count", PLUS_CONTENT, 3),
    ("binary files", BINARY, 0),
    ("quoted paths are unquoted before the exclusion", QUOTED, 2),
    ("paths with spaces", SPACES, 1),
    ("several files add up", NEW_FILE + MODIFIED + DOCS_ONLY + hunk_file("tests/t.py", 4), 13),
]


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def run(args, stdin="", env=None, cwd=None):
    env = env or clean_env()
    env.setdefault("GIT_CEILING_DIRECTORIES", SANDBOX["tmp"])
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd or SANDBOX["repo"],
        env=env,
        timeout=60,
    )


GH_STUB = """#!{python}
import os, sys
args = sys.argv[1:]
if args[:2] == ["pr", "diff"]:
    path = os.environ.get("GH_STUB_DIFF")
    if not path:
        sys.stderr.write("could not resolve to a PullRequest\\n")
        sys.exit(1)
    sys.stdout.write(open(path, encoding="utf-8").read())
    sys.exit(0)
sys.stderr.write("unexpected gh call: %r\\n" % (args,))
sys.exit(4)
"""


class Counting(unittest.TestCase):
    def test_cases(self):
        for desc, diff, expected in CASES:
            with self.subTest(desc):
                proc = run(["-"], stdin=diff)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), str(expected))

    def test_verbose_names_the_new_path_and_the_exclusions(self):
        proc = run(["--verbose", "-"], stdin=RENAMED + hunk_file("tests/test_x.py", 4))
        self.assertEqual(proc.stdout.strip(), "2")
        self.assertIn("src/app/helpers.py", proc.stderr)
        self.assertRegex(proc.stderr, r"excluded\s+4\s+tests/test_x\.py")

    def test_help(self):
        proc = run(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("SIZE_EXCLUDE_RE", proc.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/pr_size.py")

    def test_not_a_number(self):
        self.assertEqual(run(["abc"]).returncode, 2)

    def test_unreadable_conf_exits_2(self):
        outside = os.path.realpath(tempfile.mkdtemp(prefix="pr-size-outside-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        env = clean_env(GIT_CEILING_DIRECTORIES=outside)
        proc = run(["-"], stdin=NEW_FILE, env=env, cwd=outside)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


@unittest.skipUnless(IN_PROJECT, "project contract: runs once vendored into a project")
class Project(unittest.TestCase):
    def test_the_project_exclusion_compiles_and_excludes_the_wiki(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "-"],
            input=hunk_file(".llmwiki/INDEX.md", 3) + hunk_file("wip/todo/2026-01-01-x.md", 2),
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=clean_env(),
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "0", "SIZE_EXCLUDE_RE must exclude wip/ and the wiki")


class WithGh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pr-size-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        git = shutil.which("git")
        self.assertIsNotNone(git)
        os.symlink(git, os.path.join(self.bin, "git"))

    def install_gh(self):
        stub = os.path.join(self.bin, "gh")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write(GH_STUB.format(python=sys.executable))
        os.chmod(stub, 0o755)

    def test_number_reads_gh_pr_diff(self):
        self.install_gh()
        diff = os.path.join(self.tmp, "pr.diff")
        with open(diff, "w", encoding="utf-8") as fh:
            fh.write(NEW_FILE + DOCS_ONLY)
        proc = run(["12"], env=clean_env(PATH=self.bin, GH_STUB_DIFF=diff))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "10")

    def test_gh_missing_exits_2(self):
        proc = run(["12"], env=clean_env(PATH=self.bin))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("gh", proc.stderr)

    def test_gh_failing_exits_2(self):
        self.install_gh()
        proc = run(["12"], env=clean_env(PATH=self.bin))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
