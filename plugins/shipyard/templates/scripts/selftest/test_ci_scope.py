"""Selftest of scripts/ci_scope.py, plus the scoping contract of .github/workflows/ci.yml.

Run: python3 -m unittest discover -s scripts/selftest -p 'test_*.py'
Table-driven: (description, paths, expected components) in four groups (nothing, one component,
everything, mixes), against a sandbox repository (tempfile.mkdtemp) whose tooling.conf declares
two components with their COMPONENT_<ID>_RE keys; then the configuration errors (exit 2). The
`Project` cases read the repository's own files and run only once this file is vendored into a
project (a scripts/lib/tooling.conf next to scripts/selftest/); inside the plugin they are
skipped. No network.
"""

# ruff: noqa: PT009 -- stdlib unittest is the harness (the tooling job runs Python 3.9)

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "ci_scope.py")
PROJECT_CONF = os.path.join(ROOT, "scripts", "lib", "tooling.conf")
IN_PROJECT = os.path.isfile(PROJECT_CONF)
CI_YML = os.path.join(ROOT, ".github", "workflows", "ci.yml")

CONF = """# sandbox tooling.conf
PROJECT_SLUG=sbx
COMPONENTS='api web-app'
COMPONENT_API_RE='^api/|^schema/|^PRIVACY\\.md$'
COMPONENT_WEB_APP_RE='^web/|^schema/|^package(-lock)?\\.json$'
"""
COMPONENTS = ["api", "web-app"]
ALL = "ALL"

NOTHING = [
    ("root README", ["README.md"]),
    ("wiki page", [".llmwiki/Architecture.md"]),
    ("wip entry", ["wip/todo/2026-01-01-x.md"]),
    ("wip asset", ["wip/assets/2026-01-01-x/shot.png"]),
    ("skill prompt", [".claude/skills/ship-parallel/SKILL.md"]),
    ("agent prompt", [".claude/agents/reviewer.md"]),
    ("docs folder", ["docs/guide.md"]),
    ("docs folder, not Markdown", ["docs/diagram.svg"]),
    ("pull request template", [".github/PULL_REQUEST_TEMPLATE.md"]),
]
ONE_COMPONENT = [
    ("api source", ["api/main.py"], {"api"}),
    ("web source", ["web/src/app.ts"], {"web-app"}),
    ("web lock", ["package-lock.json"], {"web-app"}),
    ("web manifest", ["package.json"], {"web-app"}),
    ("doc exception in a component regex", ["PRIVACY.md"], {"api"}),
    ("Markdown inside a component directory runs it", ["api/NOTES.md"], {"api"}),
]
EVERYTHING = [
    ("ci workflow", [".github/workflows/ci.yml"]),
    ("the gates", ["scripts/check.sh"]),
    ("the shared values", ["scripts/lib/tooling.conf"]),
    ("claude settings", [".claude/settings.json"]),
    ("a skill-local script", [".claude/skills/ship-parallel/scripts/probe.py"]),
    ("the commit hook", [".githooks/pre-commit"]),
    ("an unknown path", ["Makefile"]),
    ("a dotfile", [".gitignore"]),
    ("LICENSE is not documentation", ["LICENSE"]),
]
MIXES = [
    ("doc + one component", ["README.md", "api/main.py"], {"api"}),
    ("rename across components gives both paths", ["api/x.py", "web/x.py"], {"api", "web-app"}),
    ("a shared file selects both", ["schema/user.json"], {"api", "web-app"}),
    ("doc + unknown", ["wip/todo/2026-01-01-x.md", "Makefile"], ALL),
    ("component + catch-all", ["api/a.py", "scripts/check.sh"], ALL),
]


def load_module():
    spec = importlib.util.spec_from_file_location("ci_scope_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_env(tmp=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    if tmp:
        env["GIT_CEILING_DIRECTORIES"] = tmp
    return env


def parse_flags(stdout):
    return [tuple(line.split("=", 1)) for line in stdout.splitlines() if line]


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="ci-scope-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts", "lib"))
        subprocess.run(
            ["git", "init", "-q", self.repo], check=True, env=clean_env(self.tmp), timeout=30
        )
        self.write_conf(CONF)

    def write_conf(self, text):
        with open(os.path.join(self.repo, "scripts", "lib", "tooling.conf"), "w") as fh:
            fh.write(text)

    def run_scope(self, text, *args, cwd=None):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=text,
            capture_output=True,
            text=True,
            cwd=cwd or self.repo,
            env=clean_env(self.tmp),
            timeout=30,
        )

    def expect(self, paths, expected, components=None):
        components = components or COMPONENTS
        proc = self.run_scope("\n".join(paths) + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = parse_flags(proc.stdout)
        self.assertEqual([c for c, _ in got], components, "one line per component, in order")
        self.assertTrue(all(v in ("true", "false") for _, v in got), proc.stdout)
        want = set(components) if expected == ALL else expected
        self.assertEqual({c for c, v in got if v == "true"}, want, paths)


class Table(Sandbox):
    def test_nothing(self):
        for desc, paths in NOTHING:
            with self.subTest(desc):
                self.expect(paths, set())

    def test_one_component(self):
        for desc, paths, expected in ONE_COMPONENT:
            with self.subTest(desc):
                self.expect(paths, expected)

    def test_everything(self):
        for desc, paths in EVERYTHING:
            with self.subTest(desc):
                self.expect(paths, ALL)

    def test_mixes(self):
        for desc, paths, expected in MIXES:
            with self.subTest(desc):
                self.expect(paths, expected)

    def test_empty_input_is_all_false(self):
        self.expect([], set())
        proc = self.run_scope("")
        self.assertEqual(parse_flags(proc.stdout), [(c, "false") for c in COMPONENTS])

    def test_blank_lines_and_edge_spaces(self):
        proc = self.run_scope("\n   \n  README.md  \r\n\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(all(v == "false" for _, v in parse_flags(proc.stdout)), proc.stdout)
        proc = self.run_scope("  api/main.py  \n")
        self.assertIn(("api", "true"), parse_flags(proc.stdout))

    def test_conf_is_read_from_the_repository_root(self):
        sub = os.path.join(self.repo, "api", "deep")
        os.makedirs(sub)
        proc = self.run_scope("api/a.py\n", cwd=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(parse_flags(proc.stdout), [("api", "true"), ("web-app", "false")])

    def test_no_component_prints_nothing(self):
        self.write_conf("COMPONENTS=''\n")
        proc = self.run_scope("Makefile\n")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_reads_all_of_a_large_input(self):
        # Everything is true from the first line; the script must still read to the end, or the
        # producer gets SIGPIPE and the CI step fails under pipefail.
        lines = ["scripts/check.sh"] + [f"docs/page-{i}.md" for i in range(9999)]
        payload = ("\n".join(lines) + "\n").encode()
        self.assertGreater(len(payload), 128 * 1024, "larger than any pipe buffer")
        for conf_text, want_rc in ((CONF, 0), (None, 2)):
            with self.subTest("broken conf" if conf_text is None else "valid conf"):
                if conf_text is None:
                    os.remove(os.path.join(self.repo, "scripts", "lib", "tooling.conf"))
                proc = subprocess.Popen(
                    [sys.executable, SCRIPT],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.repo,
                    env=clean_env(self.tmp),
                )
                try:
                    for start in range(0, len(payload), 4096):
                        proc.stdin.write(payload[start : start + 4096])
                    proc.stdin.close()
                except BrokenPipeError:
                    proc.kill()
                    proc.communicate()
                    self.fail("ci_scope.py closed stdin before the end of the input")
                out = proc.stdout.read().decode()
                proc.stdout.close()
                proc.stderr.close()
                self.assertEqual(proc.wait(timeout=30), want_rc)
                if want_rc == 0:
                    self.assertTrue(all(v == "true" for _, v in parse_flags(out)), out)

    def test_help_and_executable(self):
        proc = self.run_scope("", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage", proc.stdout)
        self.assertIn("COMPONENT_<ID>_RE", proc.stdout)
        self.assertIn("Why", proc.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK), "chmod +x scripts/ci_scope.py")

    def test_unexpected_argument(self):
        proc = self.run_scope("README.md\n", "README.md")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("stdin", proc.stderr)


class BadConf(Sandbox):
    CASES = [
        ("missing tooling.conf", None, "cannot read scripts/lib/tooling.conf"),
        ("missing COMPONENTS", "COMPONENT_API_RE='^api/'\n", "missing key COMPONENTS"),
        (
            "component without its key",
            "COMPONENTS='api web-app'\nCOMPONENT_API_RE='^api/'\n",
            "missing key COMPONENT_WEB_APP_RE",
        ),
        (
            "empty regex",
            "COMPONENTS='api'\nCOMPONENT_API_RE=''\n",
            "COMPONENT_API_RE in scripts/lib/tooling.conf is empty",
        ),
        (
            "invalid regex",
            "COMPONENTS='api'\nCOMPONENT_API_RE='^api/(x'\n",
            "COMPONENT_API_RE in scripts/lib/tooling.conf is not a valid Python regex",
        ),
        (
            "key naming no component",
            "COMPONENTS='api'\nCOMPONENT_API_RE='^api/'\nCOMPONENT_OLD_RE='^old/'\n",
            "COMPONENT_OLD_RE in scripts/lib/tooling.conf name(s) no component",
        ),
        (
            "invalid component id",
            "COMPONENTS='Api'\nCOMPONENT_API_RE='^api/'\n",
            "is not made of [a-z0-9-]",
        ),
    ]

    def test_cases(self):
        conf_path = os.path.join(self.repo, "scripts", "lib", "tooling.conf")
        for desc, text, message in self.CASES:
            with self.subTest(desc):
                if text is None:
                    if os.path.exists(conf_path):
                        os.remove(conf_path)
                else:
                    self.write_conf(text)
                proc = self.run_scope("api/a.py\n")
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertEqual(proc.stdout, "")
                self.assertIn(message, proc.stderr)

    def test_outside_a_repository(self):
        outside = os.path.join(self.tmp, "outside")
        os.mkdir(outside)
        proc = self.run_scope("api/a.py\n", cwd=outside)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not inside a git repository", proc.stderr)


class Algorithm(unittest.TestCase):
    """The pure functions, on compiled rules: no subprocess."""

    def setUp(self):
        self.m = load_module()
        self.rules = [("api", re.compile(r"^api/")), ("web", re.compile(r"^web/|^shared/"))]

    def test_targets(self):
        cases = [
            ("api/a.py", {"api"}),
            ("shared/x", {"web"}),
            ("README.md", set()),
            ("docs/a.txt", set()),
            ("Makefile", None),
        ]
        for path, want in cases:
            with self.subTest(path):
                self.assertEqual(self.m.targets(path, self.rules), want)

    def test_scope_accumulates(self):
        self.assertEqual(
            self.m.scope(["README.md", "web/a", "api/b"], self.rules), {"api": True, "web": True}
        )
        self.assertEqual(self.m.scope([], self.rules), {"api": False, "web": False})
        self.assertEqual(self.m.scope(["x"], self.rules), {"api": True, "web": True})

    def test_no_path_table_in_the_script(self):
        # Every project-specific path lives in tooling.conf: the script names no component dir.
        with open(SCRIPT, encoding="utf-8") as fh:
            code = fh.read().split('"""', 2)[2]
        self.assertNotRegex(code, r"\^(src|api|web|app|lib|tests?)/")


@unittest.skipUnless(IN_PROJECT, "project contract: runs once vendored into a project")
class Project(unittest.TestCase):
    """The project's own tooling.conf and ci.yml, read from the repository."""

    def run_scope(self, text):
        return subprocess.run(
            [sys.executable, SCRIPT],
            input=text,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=clean_env(),
            timeout=30,
        )

    def components(self):
        proc = self.run_scope("")
        self.assertEqual(proc.returncode, 0, f"tooling.conf is inconsistent: {proc.stderr}")
        return [c for c, _ in parse_flags(proc.stdout)]

    def selected(self, path):
        proc = self.run_scope(path + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return {c for c, v in parse_flags(proc.stdout) if v == "true"}

    def test_the_conf_loads(self):
        self.components()

    def test_changing_the_tooling_runs_every_component(self):
        everything = set(self.components())
        for path in (
            "scripts/check.sh",
            "scripts/lib/tooling.conf",
            ".github/workflows/ci.yml",
            "no-such-dir-for-ci-scope/unknown.file",
        ):
            with self.subTest(path):
                self.assertEqual(
                    self.selected(path), everything, f"{path} must run every component job"
                )

    def test_the_wiki_and_the_backlog_run_nothing(self):
        for path in (".llmwiki/Architecture.md", "wip/todo/2026-01-01-x.md"):
            with self.subTest(path):
                self.assertEqual(self.selected(path), set(), f"{path} must run no component job")

    def ci_text(self):
        self.assertTrue(os.path.isfile(CI_YML), ".github/workflows/ci.yml is missing")
        with open(CI_YML, encoding="utf-8") as fh:
            return fh.read()

    def jobs(self):
        """{job id: [lines]} for the jobs of ci.yml, parsed without a YAML library."""
        jobs, current, in_jobs = {}, None, False
        for line in self.ci_text().splitlines():
            if re.match(r"^jobs:\s*(#.*)?$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line) and not line.startswith("#"):
                in_jobs, current = False, None
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*(#.*)?$", line)
            if m:
                current = m.group(1)
                jobs[current] = []
            elif current:
                jobs[current].append(line)
        return jobs

    def test_component_jobs_carry_the_exact_condition(self):
        jobs = self.jobs()
        for comp in self.components():
            with self.subTest(comp):
                self.assertIn(comp, jobs, f"no job `{comp}` in ci.yml")
                want = f"if: ${{{{ !cancelled() && needs.scope.outputs.{comp} != 'false' }}}}"
                job_level = [ln.strip() for ln in jobs[comp] if re.match(r"^    if:", ln)]
                self.assertEqual(job_level, [want])

    def test_no_workflow_path_filter(self):
        for lineno, line in enumerate(self.ci_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            self.assertIsNone(
                re.match(r"^\s*(-\s*)?paths(-ignore)?\s*:", code),
                f"ci.yml:{lineno}: a path filter leaves required checks waiting forever",
            )

    def test_scope_step_reads_previous_filename(self):
        jobs = self.jobs()
        self.assertIn("scope", jobs)
        code = "\n".join(ln.split("#", 1)[0] for ln in jobs["scope"])
        self.assertIn("previous_filename", code, "a rename must scope its old path too")
        self.assertIn("ci_scope.py", code)


if __name__ == "__main__":
    unittest.main()
