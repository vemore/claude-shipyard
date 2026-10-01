"""Shared helpers of the process scripts: repository root and scripts/lib/tooling.conf.

Usage (from a script under scripts/):

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    import conf
    root = conf.repo_root()        # the worktree the command runs in, not the main checkout
    cfg = conf.load_conf(root)
    cfg["DEFAULT_BRANCH"]          # a missing key raises ConfError, never a silent default
    cfg.get_regex("LANE_C_RE")     # compiled with Python's re; an invalid one raises ConfError
    component_key("my-api")        # "COMPONENT_MY_API_RE", the key of a component's paths

Guarantees: the configuration is read from the root of the repository the command runs in
(`git rev-parse --show-toplevel`), so a worktree uses its own branch's copy; a missing key is an
explicit error naming the key and the file.
Does not cover: shell interpolation or `export` (the file has none by contract); validation of
the values themselves (each script checks what it uses).
Why: one file carries every shared value, and one ten-line parser reads it; a hidden default here
would be exactly the drift that the single file removes.
"""

from __future__ import annotations

import os
import re
import subprocess

CONF_RELPATH = os.path.join("scripts", "lib", "tooling.conf")
COMPONENT_ID_RE = re.compile(r"^[a-z0-9-]+$")


class ConfError(Exception):
    """The repository or its tooling.conf cannot give a value a script needs."""


class Conf(dict):
    """A dict whose missing keys raise ConfError instead of KeyError."""

    def __missing__(self, key):
        raise ConfError(f"missing key {key} in scripts/lib/tooling.conf")

    def get_int(self, key):
        value = self[key]
        try:
            return int(value)
        except ValueError:
            raise ConfError(
                f"key {key} in scripts/lib/tooling.conf is not an integer: {value!r}"
            ) from None

    def get_regex(self, key):
        """The compiled value of a `*_RE` key (an empty value compiles to a match-all regex)."""
        value = self[key]
        try:
            return re.compile(value)
        except re.error as exc:
            raise ConfError(
                f"key {key} in scripts/lib/tooling.conf is not a valid Python regex: {exc}"
            ) from None

    def components(self):
        """The ids of COMPONENTS, in order; an id outside [a-z0-9-] raises ConfError."""
        ids = self["COMPONENTS"].split()
        for comp in ids:
            if not COMPONENT_ID_RE.match(comp):
                raise ConfError(
                    f"component id {comp!r} in COMPONENTS (scripts/lib/tooling.conf) "
                    "is not made of [a-z0-9-]"
                )
        return ids


def component_key(component):
    """The tooling.conf key holding a component's path regex: my-api -> COMPONENT_MY_API_RE."""
    return "COMPONENT_" + component.upper().replace("-", "_") + "_RE"


def repo_root(cwd=None):
    """Top level of the git work tree containing cwd (default: the current directory)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConfError(f"git is unavailable: {exc}") from None
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ConfError(f"not inside a git repository: {os.path.abspath(cwd or os.curdir)}")
    return proc.stdout.strip()


def load_conf(root):
    """Parse scripts/lib/tooling.conf: KEY=value or KEY='value', '#' comments."""
    path = os.path.join(root, CONF_RELPATH)
    conf = Conf()
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] == "'":
                    value = value[1:-1]
                conf[key.strip()] = value
    except OSError as exc:
        raise ConfError(f"cannot read {CONF_RELPATH}: {exc.strerror}") from None
    return conf
