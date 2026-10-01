"""Shared helpers for the Claude Code hooks of the shipyard plugin.

Usage: imported by the other hooks in this directory; not run on its own.

Guarantees: tells whether the repository being judged is bootstrapped (it carries
``scripts/lib/tooling.conf``; every hook is inert otherwise), reads that file (falling back to
the launch checkout, then to built-in defaults), resolves which repository a path belongs to,
locates the plugin root, and runs ``git`` and ``gh`` under a time limit without ever raising
to the caller.

Does not cover: fetching. No hook ever runs ``git fetch``: the refs of a clone are shared by
every worktree, and a fetch under another session's feet changes what it sees. Everything the
hooks know about ``origin`` dates from the agent's last ``git fetch --prune``.

Why it exists: every hook needs the same three things (configuration, repository, ``gh``),
and one copy of each keeps them from drifting apart.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import traceback
from typing import Callable, Dict, List, Optional, Tuple

CONF_RELPATH = os.path.join("scripts", "lib", "tooling.conf")

# Where shipyard has not bootstrapped the repository (no scripts/lib/tooling.conf), every hook
# stays silent — the plugin is usually installed for the whole user, so it is enabled in every
# repository. The one exception (contract §6): SessionStart in an EMPTY folder prints this hint,
# because that is exactly where /shipyard:bootstrap is meant to run.
EMPTY_FOLDER_HINT = ("This folder is empty and shipyard is enabled: run /shipyard:bootstrap "
                     "<what you want to build> to start a project with its tooling.")


def is_empty_dir(path):
    # type: (str) -> bool
    """True when `path` is an existing directory with no entry at all (hidden ones included)."""
    try:
        with os.scandir(path) as entries:
            return next(iter(entries), None) is None
    except OSError:
        return False

# Built-in defaults, used when no tooling.conf can be read. An empty regex disables its rule.
DEFAULTS = {
    "PROJECT_SLUG": "project",
    "DEFAULT_BRANCH": "main",
    "GIT_CONFIG_NS": "project",
    "WORKTREE_PREFIX": "../project-",
    "SCHEDULED_STAMP": "",
    "TOOLING_LEVEL": "essentiel",
    "SECRET_PATH_RE": "",
    "SECRET_ALLOW_RE": "",
    "SECRET_CONTENT_RE": "",
}

_GIT_ENV_OVERRIDES = {"LC_ALL": "C", "LANG": "C", "LANGUAGE": ""}


# --------------------------------------------------------------------------- configuration

def parse_conf(text: str) -> Dict[str, str]:
    """Parse ``KEY=value`` lines: no interpolation, one pair of outer quotes removed."""
    values = {}  # type: Dict[str, str]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def conf_file(root: Optional[str]) -> Optional[str]:
    """The tooling.conf that applies to ``root``: the judged repository's own copy first."""
    candidates = []
    if root:
        candidates.append(os.path.join(root, CONF_RELPATH))
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        candidates.append(os.path.join(project_dir, CONF_RELPATH))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load_conf(root: Optional[str]) -> Dict[str, str]:
    conf = dict(DEFAULTS)
    path = conf_file(root)
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                conf.update(parse_conf(handle.read()))
        except OSError:
            pass
    return conf


def is_bootstrapped(root: Optional[str]) -> bool:
    """True when ``root`` is a repository that carries scripts/lib/tooling.conf."""
    return bool(root) and os.path.isfile(os.path.join(str(root), CONF_RELPATH))


def plugin_root() -> str:
    """``$CLAUDE_PLUGIN_ROOT`` when it names a directory, else the parent of this hooks dir."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and os.path.isdir(env):
        return os.path.realpath(env)
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class ConfigError(Exception):
    """A regex in tooling.conf does not compile."""


def conf_regex(conf: Dict[str, str], key: str) -> "Optional[re.Pattern]":
    """Compile ``conf[key]``; ``None`` when empty (rule off); ConfigError when invalid."""
    value = conf.get(key, "")
    if not value:
        return None
    try:
        return re.compile(value)
    except re.error as exc:
        raise ConfigError("{} in scripts/lib/tooling.conf is not a valid regex: {}".format(key, exc))


# --------------------------------------------------------------------------- repository

def _git_env() -> Dict[str, str]:
    env = dict(os.environ)
    env.update(_GIT_ENV_OVERRIDES)
    return env


def git(root: Optional[str], *args: str, timeout: float = 10) -> Tuple[int, str]:
    """Run ``git -C root args``; (return code, stdout). Never raises."""
    rc, out = git_bytes(root, *args, timeout=timeout)
    return rc, out.decode("utf-8", "replace")


def git_bytes(root: Optional[str], *args: str, timeout: float = 10) -> Tuple[int, bytes]:
    cmd = ["git"]
    if root:
        cmd += ["-C", root]
    cmd += list(args)
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, timeout=timeout, env=_git_env())
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError):
        return 127, b""


def existing_dir(path: str) -> Optional[str]:
    """``path`` if it is a directory, else its nearest existing parent directory."""
    path = os.path.abspath(path)
    if os.path.isdir(path):
        return path
    path = os.path.dirname(path)
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return path or None


def repo_root(path: Optional[str]) -> Optional[str]:
    """Top level of the work tree that contains ``path`` (file or directory), or None."""
    if not path:
        return None
    start = existing_dir(path)
    if not start:
        return None
    rc, out = git(start, "rev-parse", "--show-toplevel")
    top = out.strip()
    if rc != 0 or not top:
        return None
    return os.path.realpath(top)


def current_branch(root: str) -> Optional[str]:
    """Short name of the checked-out branch; None for a detached HEAD."""
    rc, out = git(root, "symbolic-ref", "-q", "--short", "HEAD")
    name = out.strip()
    return name if rc == 0 and name else None


def ref_exists(root: str, ref: str) -> bool:
    rc, _ = git(root, "rev-parse", "-q", "--verify", ref)
    return rc == 0


def origin_is_github(root: str) -> bool:
    # The raw URL, not `git remote get-url`: that one applies insteadOf rewrites, which the
    # self-test uses to point a GitHub URL at a local bare repository.
    rc, out = git(root, "config", "--get", "remote.origin.url")
    return rc == 0 and "github.com" in out


def git_common_dir(root: str) -> Optional[str]:
    """Absolute path of the directory every worktree of this clone shares (``.git``)."""
    rc, out = git(root, "rev-parse", "--git-common-dir")
    path = out.strip()
    if rc != 0 or not path:
        return None
    return os.path.normpath(os.path.join(root, path))


def upstream_gone(root: str, branch: str) -> bool:
    rc, out = git(root, "for-each-ref", "--format=%(upstream:track)", "refs/heads/" + branch)
    return rc == 0 and out.strip() == "[gone]"


def ahead_count(root: str, base: str) -> Optional[int]:
    rc, out = git(root, "rev-list", "--count", base + "..HEAD")
    try:
        return int(out.strip()) if rc == 0 else None
    except ValueError:
        return None


def cherry_has_minus(root: str, base: str) -> bool:
    """True when ``git cherry base HEAD`` finds a commit whose patch is already on ``base``."""
    rc, out = git(root, "cherry", base, "HEAD")
    return rc == 0 and any(line.startswith("-") for line in out.splitlines())


def config_bool(root: str, key: str) -> bool:
    rc, out = git(root, "config", "--bool", key)
    return rc == 0 and out.strip() == "true"


# --------------------------------------------------------------------------- gh

def gh_timeout(default: float = 20) -> float:
    try:
        return float(os.environ.get("HOOK_GH_TIMEOUT", default))
    except ValueError:
        return default


def gh_run(args: List[str], cwd: Optional[str], timeout: Optional[float] = None,
           ok_codes: Tuple[int, ...] = (0,)) -> Optional[str]:
    """stdout of ``gh args``; None when gh is missing, slow, unauthenticated or fails. Silent."""
    if not shutil.which("gh"):
        return None
    rc, out = run_capped(["gh"] + list(args), cwd, timeout if timeout is not None else gh_timeout(),
                         merge_stderr=False)
    if rc is None or rc not in ok_codes:
        return None
    return out


_GH_READY = {}  # type: Dict[str, bool]


def gh_ready(root: str) -> bool:
    """gh on PATH, origin on GitHub, and `gh auth status` succeeds (cached per run)."""
    if root in _GH_READY:
        return _GH_READY[root]
    ready = bool(shutil.which("gh")) and origin_is_github(root) and \
        gh_run(["auth", "status"], root) is not None
    _GH_READY[root] = ready
    return ready


# --------------------------------------------------------------------------- processes

TIMED_OUT = -999   # run_capped's code for a child killed at its time limit


def run_capped(cmd: List[str], cwd: Optional[str], timeout: float, merge_stderr: bool = True,
               env: Optional[Dict[str, str]] = None) -> Tuple[Optional[int], str]:
    """Run ``cmd``; (code, output). Code None = could not start; -999 = timed out.

    The child gets its own process group so a timeout kills what it started too.
    """
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
                                start_new_session=True, env=env)
    except OSError as exc:
        return None, str(exc)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            proc.kill()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.SubprocessError:
            out = b""
        return TIMED_OUT, (out or b"").decode("utf-8", "replace")


# --------------------------------------------------------------------------- hook plumbing

def read_payload() -> Dict:
    """The hook's JSON payload from stdin; {} when absent or invalid."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def run_main(main: Callable[[], int]) -> None:
    """Run a hook's main(); an internal error never blocks: trace on stderr, exit 0."""
    try:
        code = main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a hook must never block on its own bug
        sys.stderr.write("[hook internal error, ignored]\n" + traceback.format_exc())
        code = 0
    sys.exit(code or 0)
