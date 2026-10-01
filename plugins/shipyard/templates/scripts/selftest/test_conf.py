"""Selftest of scripts/lib/conf.py: the one reader of scripts/lib/tooling.conf.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
The parser is checked on a sandbox tooling.conf, and against bash: `. scripts/lib/tooling.conf`
must give every key the value the Python parser gives (the CI and check.sh source the file).
The `Project` case runs that parity check on the project's own tooling.conf once this file is
vendored. No network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "scripts", "lib")
PROJECT_CONF = os.path.join(LIB, "tooling.conf")
IN_PROJECT = os.path.isfile(PROJECT_CONF)
sys.path.insert(0, LIB)
import conf  # noqa: E402

SAMPLE = r"""# scripts/lib/tooling.conf — a sandbox copy.
# A comment line, then a blank one.

PROJECT_SLUG=acme-api
DEFAULT_BRANCH=main
COMPONENTS='api web-app'
SIZE_THRESHOLD=1500
EMPTY=
EMPTY_QUOTED=''
WITH_EQUALS='a=b=c'
SIZE_EXCLUDE_RE='\.md$|^wip/|(^|/)tests?/|\.lock$'
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|"type"[ \t]*:[ \t]*"service_account"|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}'
DEAD_PATH_ROOTS='src|tests|scripts|\.claude|\.llmwiki'
"""


def bash_values(path, keys):
    """{key: value} as bash sees them after `. path`."""
    script = (
        '. "$1" || exit 9\nshift\n'
        'for k in "$@"; do eval "printf \'%s\\0\' \\"\\${$k-}\\""; done'
    )
    proc = subprocess.run(
        ["bash", "-c", script, "bash", path, *keys], capture_output=True, timeout=30
    )
    if proc.returncode != 0:
        raise AssertionError(f"bash cannot source {path}: {proc.stderr.decode()}")
    values = proc.stdout.decode().split("\0")[:-1]
    return dict(zip(keys, values))


class Parsing(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="conf-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts", "lib"))
        self.path = os.path.join(self.repo, "scripts", "lib", "tooling.conf")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)
        self.cfg = conf.load_conf(self.repo)

    def test_values(self):
        self.assertEqual(self.cfg["PROJECT_SLUG"], "acme-api")
        self.assertEqual(self.cfg["COMPONENTS"], "api web-app")
        self.assertEqual(self.cfg["EMPTY"], "")
        self.assertEqual(self.cfg["EMPTY_QUOTED"], "")
        self.assertEqual(self.cfg["WITH_EQUALS"], "a=b=c")
        self.assertEqual(self.cfg["SIZE_EXCLUDE_RE"], r"\.md$|^wip/|(^|/)tests?/|\.lock$")
        self.assertNotIn("# A comment line, then a blank one.", self.cfg.values())

    def test_python_and_bash_agree(self):
        keys = sorted(self.cfg)
        self.assertEqual(bash_values(self.path, keys), {k: self.cfg[k] for k in keys})

    def test_missing_key_is_an_explicit_error(self):
        with self.assertRaises(conf.ConfError) as ctx:
            self.cfg["NO_SUCH_KEY"]
        self.assertEqual(str(ctx.exception), "missing key NO_SUCH_KEY in scripts/lib/tooling.conf")

    def test_get_int(self):
        self.assertEqual(self.cfg.get_int("SIZE_THRESHOLD"), 1500)
        with self.assertRaises(conf.ConfError) as ctx:
            self.cfg.get_int("PROJECT_SLUG")
        self.assertIn("is not an integer", str(ctx.exception))

    def test_get_regex(self):
        self.assertTrue(self.cfg.get_regex("SIZE_EXCLUDE_RE").search("docs/a.md"))
        self.assertTrue(self.cfg.get_regex("SECRET_CONTENT_RE").search("key sk-" + "a" * 24))
        self.assertFalse(self.cfg.get_regex("SECRET_CONTENT_RE").search("risk-" + "a" * 24))
        bad = conf.Conf(BAD_RE="(")
        with self.assertRaises(conf.ConfError) as ctx:
            bad.get_regex("BAD_RE")
        self.assertIn(
            "BAD_RE in scripts/lib/tooling.conf is not a valid Python regex", str(ctx.exception)
        )

    def test_components(self):
        self.assertEqual(self.cfg.components(), ["api", "web-app"])
        for value in ("Api", "a_b", "x.y"):
            with self.subTest(value), self.assertRaises(conf.ConfError):
                conf.Conf(COMPONENTS=value).components()
        self.assertEqual(conf.Conf(COMPONENTS="").components(), [])

    def test_component_key(self):
        self.assertEqual(conf.component_key("api"), "COMPONENT_API_RE")
        self.assertEqual(conf.component_key("web-app"), "COMPONENT_WEB_APP_RE")
        self.assertEqual(conf.component_key("v2"), "COMPONENT_V2_RE")

    def test_missing_file(self):
        os.remove(self.path)
        with self.assertRaises(conf.ConfError) as ctx:
            conf.load_conf(self.repo)
        self.assertIn("cannot read scripts/lib/tooling.conf", str(ctx.exception))

    def test_repo_root(self):
        env_keys = [k for k in os.environ if k.startswith("GIT_")]
        saved = {k: os.environ.pop(k) for k in env_keys}
        self.addCleanup(os.environ.update, saved)
        os.environ["GIT_CEILING_DIRECTORIES"] = self.tmp
        self.addCleanup(os.environ.pop, "GIT_CEILING_DIRECTORIES", None)
        with self.assertRaises(conf.ConfError) as ctx:
            conf.repo_root(self.repo)
        self.assertIn("not inside a git repository", str(ctx.exception))
        subprocess.run(
            ["git", "init", "-q", self.repo],
            check=True,
            env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1"),
            timeout=30,
        )
        sub = os.path.join(self.repo, "scripts", "lib")
        self.assertEqual(os.path.realpath(conf.repo_root(sub)), self.repo)


@unittest.skipUnless(IN_PROJECT, "project contract: runs once vendored into a project")
class Project(unittest.TestCase):
    def test_bash_and_python_read_the_same_values(self):
        cfg = conf.load_conf(ROOT)
        keys = sorted(cfg)
        self.assertTrue(keys, "tooling.conf holds no key")
        self.assertEqual(
            bash_values(PROJECT_CONF, keys),
            {k: cfg[k] for k in keys},
            "a value differs between `. tooling.conf` and the Python parser: no end-of-line "
            "comment, no double quotes, no interpolation",
        )

    def test_every_regex_compiles(self):
        cfg = conf.load_conf(ROOT)
        for key in sorted(k for k in cfg if k.endswith("_RE")):
            with self.subTest(key):
                cfg.get_regex(key)


if __name__ == "__main__":
    unittest.main()
